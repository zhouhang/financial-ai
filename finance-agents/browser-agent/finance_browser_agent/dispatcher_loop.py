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
from typing import Any

from finance_browser_agent.failure_policy import classify_failure
from finance_browser_agent.profile_locks import ProfileLockRegistry

logger = logging.getLogger(__name__)


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
        return await self._process_job(dict(job))

    async def _process_job(self, job: dict[str, Any]) -> dict[str, Any]:
        sync_job_id = str(job.get("id") or "")
        payload = dict(job.get("request_payload") or {})
        shop_id = str(job.get("shop_id") or "unknown")
        async with self.semaphore:
            async with self.profile_locks.lock_for_shop(shop_id):
                # Sync Playwright must run off the event loop, otherwise other workers stall.
                result = await asyncio.to_thread(
                    self.runner, self._message_from_job(job, payload)
                )
        if isinstance(result, dict) and result.get("status") == "success":
            await self.client.mark_browser_job_success(
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
            return {"status": "success", "sync_job_id": sync_job_id}
        result = result if isinstance(result, dict) else {}
        policy = classify_failure(str(result.get("fail_reason") or "OTHER"))
        await self.client.mark_browser_job_failed(
            {
                "sync_job_id": sync_job_id,
                "fail_reason": policy.normalized_reason,
                "error_message": str((result.get("error_info") or {}).get("message") or "browser task failed"),
                "retryable": policy.retryable,
                "max_attempts": policy.max_attempts,
                "retry_delay_seconds": policy.retry_delay_seconds,
            }
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
        return {
            "job_id": str(job.get("id") or ""),
            "shop_id": str(job.get("shop_id") or ""),
            "playbook_id": str(job.get("playbook_id") or ""),
            "playbook_version": str(job.get("playbook_version") or ""),
            "playbook_body": dict(job.get("playbook_body") or {}),
            "params": params,
            "runtime_profile_ref": str(job.get("runtime_profile_ref") or ""),
            "egress_group": str(job.get("egress_group") or ""),
            "credential_ref": str(job.get("credential_ref") or ""),
            "timeout_ms": int(params.get("timeout_ms") or payload.get("timeout_ms") or 900000),
        }
