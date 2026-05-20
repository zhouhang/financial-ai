from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from browser_playbook.registry import validate_emergency_promote
from browser_playbook.models import RunPlaybookMessage, TaskResult
from auth import db as auth_db


def _valid_playbook_body() -> dict[str, object]:
    return {
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
            "properties": {
                "biz_date": {
                    "type": "date",
                    "format": "YYYY-MM-DD",
                }
            },
        },
        "steps": [
            {
                "id": "open_bill_page",
                "action": "navigate",
                "url": "https://myseller.taobao.com/home.htm/whale-accountant/bill/summary?billType=day&billDirection=income",
            },
            {
                "id": "set_start_date",
                "action": "set_date",
                "selector": "input[name='startDate']",
                "value_from": "params.biz_date",
            },
            {
                "id": "set_end_date",
                "action": "set_date",
                "selector": "input[name='endDate']",
                "value_from": "params.biz_date",
            },
            {
                "id": "search",
                "action": "click",
                "selector": "button[data-action='search']",
            },
            {
                "id": "wait_summary",
                "action": "wait_for",
                "selector": "[data-summary='daily-bill']",
                "timeout_ms": 30000,
            },
            {
                "id": "read_summary",
                "action": "extract_summary",
                "mapping": {
                    "row_count": "[data-summary='row-count']",
                    "amount_total": "[data-summary='amount-total']",
                },
            },
            {
                "id": "export_detail",
                "action": "download",
                "selector": "button[data-action='export-detail']",
                "download_timeout_ms": 600000,
            },
            {
                "id": "parse_detail_file",
                "action": "parse_table",
                "source": "last_download",
                "format": "csv",
            },
        ],
        "output": {
            "record_type": "browser_collection_records",
            "item_key_fields": ["bill_no"],
            "columns": [
                {"name": "bill_no", "type": "string", "required": True, "semantic_name": "账单流水号"},
                {"name": "biz_date", "type": "date", "required": True, "semantic_name": "账务日期"},
                {"name": "amount", "type": "decimal", "required": True, "semantic_name": "发生金额"},
                {"name": "customer_order_no", "type": "string", "required": False, "semantic_name": "客户订单号"},
            ],
        },
        "quality_gate": {
            "date_field": "biz_date",
            "amount_field": "amount",
            "summary_step_id": "read_summary",
            "row_count_field": "row_count",
            "amount_total_field": "amount_total",
            "row_count_equals_summary": True,
            "amount_sum_equals_summary": True,
            "amount_precision": 2,
            "zero_tolerance": True,
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
    }


def test_run_playbook_message_accepts_qianniu_playbook_v1() -> None:
    msg = RunPlaybookMessage.model_validate(
        {
            "job_id": "job-001",
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily-bill-export",
            "playbook_version": "1.0.0",
            "playbook_body": _valid_playbook_body(),
            "params": {"biz_date": "2026-05-18"},
            "runtime_profile_ref": "profiles/shop-001",
            "egress_group": "wan-1",
            "credential_ref": "cred-001",
            "timeout_ms": 900000,
        }
    )

    assert msg.params["biz_date"] == "2026-05-18"
    assert msg.playbook_body.output.item_key_fields == ["bill_no"]


def test_playbook_rejects_unknown_action() -> None:
    playbook = _valid_playbook_body()
    playbook["steps"][0]["action"] = "ask_llm"  # type: ignore[index]

    with pytest.raises(ValidationError):
        RunPlaybookMessage.model_validate(
            {
                "job_id": "job-001",
                "shop_id": "shop-001",
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
                "playbook_body": playbook,
                "params": {"biz_date": "2026-05-18"},
                "runtime_profile_ref": "profiles/shop-001",
            }
        )


@pytest.mark.parametrize(
    ("step_index", "patch"),
    [
        (0, {"url": "/relative/path"}),
        (1, {"value_from": "params.other_date"}),
        (3, {"selector": ""}),
        (5, {"mapping": {}}),
        (7, {"source": "downloaded_file"}),
    ],
)
def test_playbook_rejects_invalid_action_contract(step_index: int, patch: dict[str, object]) -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps[step_index].update(patch)

    with pytest.raises(ValidationError):
        RunPlaybookMessage.model_validate(
            {
                "job_id": "job-001",
                "shop_id": "shop-001",
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
                "playbook_body": playbook,
                "params": {"biz_date": "2026-05-18"},
                "runtime_profile_ref": "profiles/shop-001",
            }
        )


def test_playbook_requires_biz_date_param_schema() -> None:
    playbook = _valid_playbook_body()
    playbook["params_schema"] = {"required": [], "properties": {}}  # type: ignore[index]

    with pytest.raises(ValidationError):
        RunPlaybookMessage.model_validate(
            {
                "job_id": "job-001",
                "shop_id": "shop-001",
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
                "playbook_body": playbook,
                "params": {"biz_date": "2026-05-18"},
                "runtime_profile_ref": "profiles/shop-001",
            }
        )


def test_task_result_accepts_success_records() -> None:
    result = TaskResult.model_validate(
        {
            "job_id": "job-001",
            "status": "success",
            "records": [
                {
                    "item_key": "BILL-001",
                    "item_key_values": {"bill_no": "BILL-001"},
                    "payload": {"bill_no": "BILL-001", "amount": "10.00"},
                }
            ],
            "capture_files": [],
            "quality_summary": {"row_count": 1, "amount_total": "10.00"},
        }
    )

    assert result.records[0].item_key == "BILL-001"


def test_emergency_promote_requires_reason_and_validation_metadata() -> None:
    ok = validate_emergency_promote(
        {
            "emergency_page_changed": True,
            "bypass_canary_reason": "页面改版，验证店 shop-001，验证日期 2026-05-18，审批人 operator-001",
        }
    )

    assert ok["success"] is True


def test_emergency_promote_rejects_empty_reason() -> None:
    result = validate_emergency_promote(
        {
            "emergency_page_changed": True,
            "bypass_canary_reason": "",
        }
    )

    assert result["success"] is False


def test_upsert_playbook_and_binding_helpers_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs) -> None:
            calls.append("execute")

        def fetchone(self):
            return {
                "id": "row-001",
                "company_id": "company-001",
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self) -> None:
            calls.append("commit")

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    playbook = auth_db.upsert_playbook(
        company_id="company-001",
        playbook_id="qianniu-daily-bill-export",
        version="1.0.0",
        title="千牛资金日账单",
        playbook_body={"schema_version": "1.0"},
    )
    binding = auth_db.upsert_shop_runtime_binding(
        company_id="company-001",
        data_source_id="source-001",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        agent_id="agent-001",
        egress_group="wan-1",
        credential_ref="cred-001",
    )

    assert playbook["id"] == "row-001"
    assert binding["id"] == "row-001"
    assert calls.count("execute") == 2
    assert calls.count("commit") == 2
