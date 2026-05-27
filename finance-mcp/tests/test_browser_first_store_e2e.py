from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from browser_playbook.agent_connection import FakeAgentConnectionManager
from browser_playbook.dispatcher import BrowserPlaybookDispatcher
from recon.mcp_server import dataset_loader


class FakeBrowserDb:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def claim_next_browser_sync_job(self, *, agent_max_concurrency: int = 2) -> dict[str, Any]:
        return {
            "id": "sync-001",
            "company_id": "company-001",
            "data_source_id": "source-001",
            "resource_key": "qianniu-daily-bill-export@1.0.0",
            "request_payload": {
                "dataset_id": "dataset-001",
                "dataset_code": "qianniu_fund_bill",
                "biz_date": "2026-05-18",
            },
        }

    def get_shop_runtime_binding_for_source(self, *, company_id: str, data_source_id: str) -> dict[str, Any]:
        return {
            "shop_id": "shop-001",
            "agent_id": "agent-local-001",
            "playbook_id": "qianniu-daily-bill-export",
            "egress_group": "wan-1",
            "credential_ref": "cred-001",
            "profile_status": "active",
            "playbook_status": "ok",
        }

    def get_active_playbook(self, *, company_id: str, playbook_id: str) -> dict[str, Any]:
        return {
            "playbook_id": playbook_id,
            "version": "1.0.0",
            "playbook_body": {
                "schema_version": "1.0",
                "playbook_id": "qianniu-daily-bill-export",
                "title": "千牛资金日账单导出",
                "target": {
                    "platform": "qianniu",
                    "business_object": "fund_bill",
                    "timezone": "Asia/Shanghai",
                },
                "params_schema": {
                    "required": ["biz_date"],
                    "properties": {"biz_date": {"type": "date", "format": "YYYY-MM-DD"}},
                },
                "steps": [
                    {
                        "id": "read_summary",
                        "action": "extract_summary",
                        "mapping": {"row_count": "#row-count", "amount_total": "#amount-total"},
                    }
                ],
                "output": {
                    "record_type": "browser_collection_records",
                    "item_key_fields": ["bill_no"],
                    "columns": [
                        {"name": "bill_no", "type": "string", "required": True},
                        {"name": "biz_date", "type": "date", "required": True},
                        {"name": "amount", "type": "decimal", "required": True},
                        {"name": "customer_order_no", "type": "string", "required": False},
                    ],
                },
                "quality_gate": {
                    "date_field": "biz_date",
                    "amount_field": "amount",
                    "summary_step_id": "read_summary",
                },
                "accounting_policy": {
                    "date_basis": "账务日期/入账日期",
                    "amount_sign": "source_signed",
                    "included_business_types": ["千牛日汇总口径内全部明细"],
                },
                "failure_mapping": {
                    "selector_missing": "PAGE_CHANGED",
                    "auth_redirect": "AUTH_EXPIRED",
                    "risk_verification": "RISK_VERIFICATION",
                    "quality_mismatch": "DATA_MISMATCH",
                },
            },
        }

    def upsert_browser_collection_records(self, **kwargs: Any) -> dict[str, Any]:
        self.records = list(kwargs["records"])
        return {
            "inserted_count": len(self.records),
            "updated_count": 0,
            "unchanged_count": 0,
            "deleted_count": 0,
        }

    def insert_browser_capture_files(self, **kwargs: Any) -> dict[str, Any]:
        if not hasattr(self, "capture_files"):
            self.capture_files: list[dict[str, Any]] = []
        self.capture_files.append(kwargs)
        return {"inserted_count": len(kwargs.get("capture_files") or [])}

    def mark_browser_sync_job_success(self, *, sync_job_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        return {"id": sync_job_id, "job_status": "success", "summary": summary}


def test_first_store_browser_collection_to_recon_loader(monkeypatch) -> None:
    fake_db = FakeBrowserDb()

    def fake_list_browser_collection_records(**kwargs: Any) -> list[dict[str, Any]]:
        assert kwargs["source_key"] == "source-001"
        assert kwargs["query"]["dataset_id"] == "dataset-001"
        return [{"payload": item["payload"]} for item in fake_db.records]

    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: ["data_source_id", "dataset_id", "biz_date", "payload"]
        if table_name == "browser_collection_records"
        else [],
    )
    monkeypatch.setattr(
        dataset_loader,
        "_load_browser_collection_record_rows",
        fake_list_browser_collection_records,
    )

    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-local-001",
        {
            "job_id": "sync-001",
            "status": "success",
            "records": [
                {
                    "item_key": "BILL-001",
                    "item_key_values": {"bill_no": "BILL-001"},
                    "payload": {
                        "bill_no": "BILL-001",
                        "biz_date": "2026-05-18",
                        "amount": "10.00",
                        "customer_order_no": "TB-001",
                    },
                }
            ],
            "capture_files": [
                {
                    "storage_path": "/var/lib/tally-agent/downloads/shop-001/sync-001/qn.csv",
                    "encoding": "utf-8",
                    "checksum": "sha256:abc",
                    "row_count": 1,
                }
            ],
            "quality_summary": {"row_count": 1, "amount_total": "10.00"},
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    dispatch_result = dispatcher.run_once()

    assert dispatch_result["status"] == "success"

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "source-001",
            "query": {
                "dataset_id": "dataset-001",
                "biz_date": "2026-05-18",
            },
        },
        "right_recon_ready",
    )

    assert df.to_dict("records") == [
        {
            "bill_no": "BILL-001",
            "biz_date": "2026-05-18",
            "amount": "10.00",
            "customer_order_no": "TB-001",
        }
    ]
    # Capture-file metadata audit trail is wired through the dispatcher pipeline.
    assert getattr(fake_db, "capture_files", [])
    assert fake_db.capture_files[0]["sync_job_id"] == "sync-001"
    assert fake_db.capture_files[0]["capture_files"][0]["storage_path"].endswith("qn.csv")


# ---------- Waiting-data queue guards (cross-checks of T2/T12 with DB layer) ----------


class _WaitingCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, sql: str, params=None):
        self.executed.append(sql)

    def fetchall(self):
        return [("queue-001", "company-001", "AGENT_INTERRUPTED: browser-agent restarted")]


class _WaitingConn:
    def __init__(self, cursor: _WaitingCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        return None


class _WaitingConnManager:
    def __init__(self, cursor: _WaitingCursor) -> None:
        self.cursor = cursor

    def __enter__(self):
        return _WaitingConn(self.cursor)

    def __exit__(self, exc_type, exc, tb):
        return None


def test_e2e_waiting_data_empty_collection_jobs_never_requeues(monkeypatch) -> None:
    """End-to-end check that the empty collection_job_ids guard ships in the actual SQL."""
    from auth import db as auth_db

    cursor = _WaitingCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: _WaitingConnManager(cursor))

    auth_db.requeue_ready_waiting_recon_runs()

    sql = "\n".join(cursor.executed)
    assert "jsonb_array_length(collection_job_ids) > 0" in sql
    assert "jsonb_typeof(collection_job_ids) = 'array'" in sql


def test_e2e_waiting_data_failed_browser_job_fast_fails(monkeypatch) -> None:
    """End-to-end check that fail_waiting_recon_runs_with_failed_collection_jobs exists and pulls
    error_message from sync_jobs so the recon error carries the underlying fail_reason context."""
    from auth import db as auth_db

    cursor = _WaitingCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: _WaitingConnManager(cursor))

    auth_db.fail_waiting_recon_runs_with_failed_collection_jobs()

    sql = "\n".join(cursor.executed)
    assert "status = 'failed'" in sql
    assert "s.job_status = 'failed'" in sql
    assert "s.error_message" in sql
    assert "UPDATE execution_runs" in sql


def test_e2e_waiting_data_success_triggers_requeue_with_resume_metadata(monkeypatch) -> None:
    """v1: requeue must bump resume metadata, not retry budget."""
    from auth import db as auth_db

    cursor = _WaitingCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: _WaitingConnManager(cursor))

    auth_db.requeue_ready_waiting_recon_runs()

    sql = "\n".join(cursor.executed)
    assert "data_wait_resume_count = COALESCE(data_wait_resume_count, 0) + 1" in sql
    assert "last_data_wait_resumed_at = CURRENT_TIMESTAMP" in sql
    assert "current_attempt" not in sql  # don't conflate with retries
