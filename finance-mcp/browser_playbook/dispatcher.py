"""Browser playbook sync job dispatcher."""

from __future__ import annotations

from typing import Any

from browser_playbook.agent_connection import AgentConnectionManager


class BrowserPlaybookDispatcher:
    def __init__(self, *, db: Any, connections: AgentConnectionManager, agent_max_concurrency: int = 2) -> None:
        self.db = db
        self.connections = connections
        self.agent_max_concurrency = agent_max_concurrency

    def run_once(self) -> dict[str, Any]:
        job = self.db.claim_next_browser_sync_job(agent_max_concurrency=self.agent_max_concurrency)
        if not job:
            return {"status": "idle"}

        company_id = str(job["company_id"])
        data_source_id = str(job["data_source_id"])
        binding = self.db.get_shop_runtime_binding_for_source(
            company_id=company_id,
            data_source_id=data_source_id,
        )
        if binding.get("profile_status") != "active" or binding.get("playbook_status") != "ok":
            self.db.mark_browser_sync_job_failed(
                sync_job_id=str(job["id"]),
                error_message="shop runtime binding is not healthy",
                fail_reason="unhealthy_binding",
            )
            return {"status": "failed", "reason": "unhealthy_binding"}

        playbook = self.db.get_active_playbook(
            company_id=company_id,
            playbook_id=str(binding["playbook_id"]),
        )
        payload = dict(job.get("request_payload") or {})
        message = {
            "job_id": str(job["id"]),
            "shop_id": str(binding["shop_id"]),
            "playbook_id": str(playbook["playbook_id"]),
            "playbook_version": str(playbook["version"]),
            "playbook_body": dict(playbook["playbook_body"]),
            "params": {
                **payload,
                "biz_date": str(payload.get("biz_date") or ""),
            },
            "runtime_profile_ref": f"profiles/{binding['shop_id']}",
            "egress_group": str(binding.get("egress_group") or ""),
            "credential_ref": str(binding.get("credential_ref") or ""),
            "timeout_ms": int(payload.get("timeout_ms") or 900000),
        }
        result = self.connections.dispatch(str(binding["agent_id"]), message, int(message["timeout_ms"]))
        if result.get("status") != "success":
            fail_reason = str(result.get("fail_reason") or "OTHER")
            self.db.mark_browser_sync_job_failed(
                sync_job_id=str(job["id"]),
                error_message=str(result.get("error_info") or result.get("message") or "browser task failed"),
                fail_reason=fail_reason,
            )
            return {"status": "failed", "reason": fail_reason}

        summary = self.db.upsert_browser_collection_records(
            company_id=company_id,
            data_source_id=data_source_id,
            dataset_id=str(payload.get("dataset_id") or ""),
            dataset_code=str(payload.get("dataset_code") or ""),
            resource_key=str(job.get("resource_key") or ""),
            shop_id=str(binding["shop_id"]),
            playbook_id=str(playbook["playbook_id"]),
            biz_date=str(payload.get("biz_date") or ""),
            sync_job_id=str(job["id"]),
            records=list(result.get("records") or []),
        )
        file_summary = self.db.insert_browser_capture_files(
            company_id=company_id,
            data_source_id=data_source_id,
            dataset_id=str(payload.get("dataset_id") or ""),
            sync_job_id=str(job["id"]),
            resource_key=str(job.get("resource_key") or ""),
            shop_id=str(binding["shop_id"]),
            playbook_id=str(playbook["playbook_id"]),
            biz_date=str(payload.get("biz_date") or ""),
            capture_files=list(result.get("capture_files") or []),
        )
        summary = dict(summary or {})
        summary["capture_file_count"] = int((file_summary or {}).get("inserted_count") or 0)
        self.db.mark_browser_sync_job_success(sync_job_id=str(job["id"]), summary=summary)
        return {"status": "success", "summary": summary}

