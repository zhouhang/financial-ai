from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from browser_playbook.agent_connection import FakeAgentConnectionManager
from browser_playbook.dispatcher import BrowserPlaybookDispatcher


class FakeDb:
    def __init__(self) -> None:
        self.dispatched: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.successes: list[dict[str, Any]] = []
        self.binding: dict[str, Any] = {
            "shop_id": "shop-001",
            "agent_id": "agent-001",
            "playbook_id": "qianniu-daily-bill-export",
            "egress_group": "wan-1",
            "credential_ref": "cred-001",
            "profile_status": "active",
            "playbook_status": "ok",
        }

    def claim_next_browser_sync_job(self, *, agent_max_concurrency: int = 2) -> dict[str, Any]:
        return {
            "id": "job-001",
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
        return self.binding

    def get_active_playbook(self, *, company_id: str, playbook_id: str) -> dict[str, Any]:
        return {
            "playbook_id": playbook_id,
            "version": "1.0.0",
            "playbook_body": {
                "schema_version": "1.0",
                "playbook_id": playbook_id,
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
                        {"name": "amount", "type": "decimal", "required": True},
                        {"name": "biz_date", "type": "date", "required": True},
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
        self.dispatched.append(kwargs)
        return {
            "inserted_count": 1,
            "updated_count": 0,
            "unchanged_count": 0,
            "input_count": 1,
        }

    def mark_browser_sync_job_success(self, *, sync_job_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        self.successes.append({"sync_job_id": sync_job_id, "summary": summary})
        return {"id": sync_job_id, "job_status": "success"}

    def mark_browser_sync_job_failed(
        self,
        *,
        sync_job_id: str,
        error_message: str,
        fail_reason: str,
    ) -> dict[str, Any]:
        self.failures.append(
            {
                "sync_job_id": sync_job_id,
                "error_message": error_message,
                "fail_reason": fail_reason,
            }
        )
        return {"id": sync_job_id, "job_status": "failed"}


def test_dispatcher_writes_success_records() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "success",
            "records": [
                {
                    "item_key": "BILL-001",
                    "item_key_values": {"bill_no": "BILL-001"},
                    "payload": {"bill_no": "BILL-001", "amount": "10.00", "biz_date": "2026-05-18"},
                }
            ],
            "capture_files": [],
            "quality_summary": {"row_count": 1},
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager, agent_max_concurrency=2)
    result = dispatcher.run_once()

    assert result["status"] == "success"
    assert fake_db.dispatched[0]["shop_id"] == "shop-001"
    assert fake_db.dispatched[0]["dataset_id"] == "dataset-001"
    assert fake_db.successes[0]["sync_job_id"] == "job-001"
    assert manager.messages[0]["message"]["params"]["biz_date"] == "2026-05-18"


def test_dispatcher_fails_unhealthy_binding_without_dispatch() -> None:
    fake_db = FakeDb()
    fake_db.binding["profile_status"] = "needs_reauth"
    manager = FakeAgentConnectionManager()

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    result = dispatcher.run_once()

    assert result["status"] == "failed"
    assert result["reason"] == "unhealthy_binding"
    assert manager.messages == []
    assert fake_db.failures[0]["fail_reason"] == "unhealthy_binding"


def test_dispatcher_marks_runner_failure() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "failed",
            "fail_reason": "PAGE_CHANGED",
            "error_info": {"message": "selector missing"},
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    result = dispatcher.run_once()

    assert result["status"] == "failed"
    assert result["reason"] == "PAGE_CHANGED"
    assert fake_db.failures[0]["fail_reason"] == "PAGE_CHANGED"

