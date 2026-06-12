"""Browser-agent dispatcher loop.

Owns the local execution side of the browser collection pipeline:

  1. ``claim_browser_job`` via tally_client — pulls an enriched sync_job.
  2. Acquire a global concurrency slot (``asyncio.Semaphore(max_concurrency)``) AND a per-shop
     profile lock so concurrent jobs for different shops can run in parallel but jobs for the
     same shop serialize.
  3. Run the sync Playwright ``runner`` inside ``asyncio.to_thread`` so the event loop stays
     free for other workers — without this, ``max_concurrency`` is fake because sync Playwright
     monopolizes the loop for the entire 5-10 min playbook.
  4. On success, push records + capture_files back to finance-mcp.
  5. On failure, classify via ``failure_policy`` and report retryable/terminal back to
     finance-mcp; cloud-side ``mark_browser_sync_job_failed`` handles the reschedule vs
     terminal decision.

``create_worker_tasks`` launches N independent ``worker_loop`` coroutines that each repeatedly
call ``run_once``. The semaphore inside ``_process_job`` is mostly a safety net; the real
concurrency parallelism comes from having multiple worker coroutines.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from finance_browser_agent.credentials import inject_credentials_into_params
from finance_browser_agent.failure_policy import classify_failure
from finance_browser_agent.playwright_runner import sanitize_profile_key
from finance_browser_agent.profile_locks import ProfileLockRegistry

logger = logging.getLogger(__name__)

# Per-shop AUTH_EXPIRED notification dedup: shop_id → date of last notification.
# A single shop often has two dataset jobs that both fail with AUTH_EXPIRED on the
# same day; we only want to send one handoff notification per shop per day.
_AUTH_EXPIRED_NOTIFIED: dict[str, date] = {}


class BrowserDispatcherLoop:
    def __init__(
        self,
        *,
        client: Any,
        runner: Callable[[dict[str, Any]], dict[str, Any]],
        max_concurrency: int,
        profile_locks: ProfileLockRegistry | None = None,
    ) -> None:
        self.client = client
        self.runner = runner
        self.max_concurrency = max(1, max_concurrency)
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.profile_locks = profile_locks or ProfileLockRegistry()

    async def run_once(self) -> dict[str, Any]:
        claim = await self.client.claim_browser_job()
        job = claim.get("job") if isinstance(claim, dict) else None
        if not job:
            return {"status": "idle"}
        logger.info(
            "browser job claimed: sync_job_id=%s playbook_id=%s shop_id=%s "
            "runtime_profile_ref=%s is_verification=%s",
            job.get("id") or "",
            job.get("playbook_id") or "",
            job.get("shop_id") or "",
            job.get("runtime_profile_ref") or "",
            job.get("is_verification"),
        )
        return await self._process_job(dict(job))

    async def _process_job(self, job: dict[str, Any]) -> dict[str, Any]:
        sync_job_id = str(job.get("id") or "")
        payload = dict(job.get("request_payload") or {})
        profile_key = sanitize_profile_key(
            str(job.get("runtime_profile_ref") or job.get("shop_id") or "unknown")
        )
        async with self.semaphore:
            async with self.profile_locks.lock_for_shop(profile_key):
                # Sync Playwright must run off the event loop, otherwise other workers stall.
                logger.info(
                    "browser runner starting: sync_job_id=%s playbook_id=%s shop_id=%s "
                    "profile_key=%s",
                    sync_job_id,
                    job.get("playbook_id") or "",
                    job.get("shop_id") or "",
                    profile_key,
                )
                loop = asyncio.get_running_loop()

                def _on_risk_waiting(reason: str = "RISK_VERIFICATION") -> None:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.client.report_risk_waiting(
                                sync_job_id=str(job.get("id") or ""),
                                reason=str(reason or "RISK_VERIFICATION"),
                                company_id=str(job.get("company_id") or ""),
                                shop_id=str(job.get("shop_id") or ""),
                                data_source_id=str(job.get("data_source_id") or ""),
                            ),
                            loop,
                        )
                    except Exception:
                        logger.exception("report_risk_waiting schedule failed")

                message = self._message_from_job(job, payload)
                message["on_risk_waiting"] = _on_risk_waiting
                result = await asyncio.to_thread(self.runner, message)
        if isinstance(result, dict) and result.get("status") == "success":
            try:
                ack = await self.client.mark_browser_job_success(
                    {
                        "sync_job_id": sync_job_id,
                        "summary": {
                            "record_count": len(result.get("records") or []),
                            "quality_summary": result.get("quality_summary") or {},
                        },
                        "records": list(result.get("records") or []),
                        "capture_files": list(result.get("capture_files") or []),
                    }
                )
                ack_rejected = isinstance(ack, dict) and ack.get("success") is False
                ack_error = str((ack or {}).get("error") or "completion persist failed")
            except Exception as exc:  # noqa: BLE001
                ack_rejected = True
                ack_error = f"completion call raised: {exc}"
            if ack_rejected:
                # Runner succeeded but the server explicitly rejected the completion write
                # (e.g. a transient DB error). Do NOT claim success — re-fail as retryable so the
                # job re-collects and re-completes.
                #
                # SAFE ONLY because the server-side completion writes are idempotent:
                # capture-files upsert via ON CONFLICT and records via key-field upsert (see
                # _handle_browser_sync_job_complete). If a non-idempotent side effect is ever
                # added to that handler, this retry path would duplicate it.
                error_message = ack_error
                await self.client.mark_browser_job_failed(
                    {
                        "sync_job_id": sync_job_id,
                        "fail_reason": "COMPLETE_PERSIST_FAILED",
                        "error_message": error_message,
                        # Bounded retries: a transient persist error tends to clear within the 60s
                        # backoff; a deterministic one (e.g. schema mismatch) exhausts max_attempts
                        # and goes terminal-failed, then surfaces via the finance-cron reaper.
                        "retryable": True,
                        "max_attempts": 3,
                        "retry_delay_seconds": 60,
                    }
                )
                logger.warning(
                    "browser completion persist failed, re-failing as retryable: sync_job_id=%s error=%s",
                    sync_job_id,
                    error_message,
                )
                return {"status": "failed", "sync_job_id": sync_job_id, "retryable": True}
            logger.info(
                "browser runner succeeded: sync_job_id=%s record_count=%s capture_file_count=%s",
                sync_job_id,
                len(result.get("records") or []),
                len(result.get("capture_files") or []),
            )
            return {"status": "success", "sync_job_id": sync_job_id}
        result = result if isinstance(result, dict) else {}
        policy = classify_failure(str(result.get("fail_reason") or "OTHER"))
        error_message = str((result.get("error_info") or {}).get("message") or "browser task failed")

        # AUTH_EXPIRED: fire a handoff notification so someone can re-login via
        # the remote-control link.  Dedup per shop per day because the same shop
        # typically has two dataset jobs that both fail on the same day.
        if policy.normalized_reason == "AUTH_EXPIRED":
            shop_id_str = str(job.get("shop_id") or "")
            today = date.today()
            if _AUTH_EXPIRED_NOTIFIED.get(shop_id_str) != today:
                _AUTH_EXPIRED_NOTIFIED[shop_id_str] = today
                try:
                    await self.client.report_risk_waiting(
                        sync_job_id=sync_job_id,
                        reason="AUTH_EXPIRED",
                        company_id=str(job.get("company_id") or ""),
                        shop_id=shop_id_str,
                        data_source_id=str(job.get("data_source_id") or ""),
                    )
                    logger.info(
                        "browser auth expired notification sent: sync_job_id=%s shop_id=%s",
                        sync_job_id,
                        shop_id_str,
                    )
                except Exception:
                    logger.exception(
                        "browser auth expired notification failed: sync_job_id=%s", sync_job_id
                    )
            else:
                logger.info(
                    "browser auth expired notification deduped (already sent today): "
                    "sync_job_id=%s shop_id=%s",
                    sync_job_id,
                    shop_id_str,
                )

        await self.client.mark_browser_job_failed(
            {
                "sync_job_id": sync_job_id,
                "fail_reason": policy.normalized_reason,
                "error_message": error_message,
                "retryable": policy.retryable,
                "max_attempts": policy.max_attempts,
                "retry_delay_seconds": policy.retry_delay_seconds,
            }
        )
        logger.warning(
            "browser runner failed: sync_job_id=%s fail_reason=%s retryable=%s error=%s",
            sync_job_id,
            policy.normalized_reason,
            policy.retryable,
            error_message,
        )
        return {"status": "failed", "sync_job_id": sync_job_id, "retryable": policy.retryable}

    def create_worker_tasks(self) -> list[asyncio.Task]:
        return [
            asyncio.create_task(self.worker_loop(worker_index=index))
            for index in range(self.max_concurrency)
        ]

    async def worker_loop(self, *, worker_index: int) -> None:
        while True:
            try:
                result = await self.run_once()
                if result.get("status") == "idle":
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("browser dispatcher worker failed: worker_index=%s", worker_index)
                await asyncio.sleep(5)

    def _message_from_job(self, job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload.get("params") or payload)
        credential_ref = str(job.get("credential_ref") or "")
        params = inject_credentials_into_params(params, credential_ref)
        return {
            "job_id": str(job.get("id") or ""),
            "company_id": str(job.get("company_id") or ""),
            "shop_id": str(job.get("shop_id") or ""),
            "playbook_id": str(job.get("playbook_id") or ""),
            "playbook_version": str(job.get("playbook_version") or ""),
            "playbook_body": dict(job.get("playbook_body") or {}),
            "params": params,
            "runtime_profile_ref": str(job.get("runtime_profile_ref") or ""),
            "egress_group": str(job.get("egress_group") or ""),
            "credential_ref": credential_ref,
            "timeout_ms": int(params.get("timeout_ms") or payload.get("timeout_ms") or 900000),
            "handoff_coordinator": getattr(self.client, "handoff_coordinator", None),
            "handoff_backend_factory": getattr(self.client, "handoff_backend_factory", None),
        }
