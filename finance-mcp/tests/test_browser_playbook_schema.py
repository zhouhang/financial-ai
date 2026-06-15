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
from tools.data_sources import _normalize_browser_playbook_body


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


def test_playbook_accepts_login_action_contract() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        1,
        {
            "id": "login_if_needed",
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".account-menu",
        },
    )

    msg = RunPlaybookMessage.model_validate(
        {
            "job_id": "job-001",
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily-bill-export",
            "playbook_version": "1.0.0",
            "playbook_body": playbook,
            "params": {
                "biz_date": "2026-05-18",
                "login_username": "alice",
                "login_password": "secret",
            },
            "runtime_profile_ref": "profiles/shop-001",
        }
    )

    assert msg.playbook_body.steps[1].action == "login_if_needed"


def test_playbook_accepts_download_history_file_action() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps[6] = {
        "id": "download_completed_file",
        "action": "download_history_file",
        "selector": ".HistoryDataLists--drawer-conent--3FJMg52 tr.next-table-row",
        "value_from": "params.biz_date",
        "download_timeout_ms": 600000,
        "history_open_selectors": [
            ".next-dialog button:has-text('历史下载记录')",
            "button:has-text('历史下载记录')",
        ],
        "history_row_selectors": [
            ".HistoryDataLists--drawer-conent--3FJMg52 tr.next-table-row",
            "tr.next-table-row",
        ],
        "history_close_selectors": [
            ".drawer-close",
            "[aria-label='关闭']",
        ],
        "history_completed_status_text": "已完成",
        "history_download_selector": "button:has-text('下载')",
        "timeout_ms": 900000,
    }

    msg = RunPlaybookMessage.model_validate(
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

    assert msg.playbook_body.steps[6].action == "download_history_file"
    assert msg.playbook_body.steps[6].history_open_selectors == [
        ".next-dialog button:has-text('历史下载记录')",
        "button:has-text('历史下载记录')",
    ]
    assert msg.playbook_body.steps[6].history_row_selectors == [
        ".HistoryDataLists--drawer-conent--3FJMg52 tr.next-table-row",
        "tr.next-table-row",
    ]
    assert msg.playbook_body.steps[6].history_close_selectors == [
        ".drawer-close",
        "[aria-label='关闭']",
    ]
    assert msg.playbook_body.steps[6].history_completed_status_text == "已完成"
    assert msg.playbook_body.steps[6].history_download_selector == "button:has-text('下载')"


def test_playbook_accepts_top_level_overlays() -> None:
    playbook = _valid_playbook_body()
    playbook["overlays"] = [
        {
            "id": "finance_survey",
            "markers": [" .aes-survey-hanging ", " text=财务管理工具 "],
            "close_selectors": [" .aes-survey-hanging--close "],
        }
    ]

    msg = RunPlaybookMessage.model_validate(
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

    assert msg.playbook_body.overlays[0].id == "finance_survey"
    assert msg.playbook_body.overlays[0].markers == [
        ".aes-survey-hanging",
        "text=财务管理工具",
    ]
    assert msg.playbook_body.overlays[0].close_selectors == [".aes-survey-hanging--close"]


def test_playbook_rejects_overlay_without_markers_or_close_selectors() -> None:
    playbook = _valid_playbook_body()
    playbook["overlays"] = [
        {
            "id": "finance_survey",
            "markers": [],
            "close_selectors": [],
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
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

    assert "overlays.markers cannot be empty" in str(exc_info.value)


def test_playbook_rejects_overlay_without_close_selectors() -> None:
    playbook = _valid_playbook_body()
    playbook["overlays"] = [
        {
            "id": "finance_survey",
            "markers": [".aes-survey-hanging"],
            "close_selectors": [" ", ""],
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
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

    assert "overlays.close_selectors cannot be empty" in str(exc_info.value)


def test_playbook_accepts_stop_if_summary_zero_action() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        6,
        {
            "id": "stop_when_no_bill_rows",
            "action": "stop_if_summary_zero",
            "summary_field": "row_count",
            "record_as": "empty_result",
        },
    )

    msg = RunPlaybookMessage.model_validate(
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
    normalized, error = _normalize_browser_playbook_body(playbook)

    assert msg.playbook_body.steps[6].action == "stop_if_summary_zero"
    assert error == ""
    assert normalized["steps"][6]["action"] == "stop_if_summary_zero"  # type: ignore[index]


def test_playbook_accepts_select_checkboxes_and_wait_ms_actions() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        6,
        {
            "id": "select_export_fields",
            "action": "select_checkboxes",
            "selector": ".next-dialog:has-text('批量导出订单')",
            "checked_labels": ["订单编号", "订单状态"],
            "timeout_ms": 30000,
        },
    )
    steps.insert(
        7,
        {
            "id": "wait_report_generation",
            "action": "wait_ms",
            "duration_ms": 1000,
        },
    )

    msg = RunPlaybookMessage.model_validate(
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

    assert msg.playbook_body.steps[6].action == "select_checkboxes"
    assert msg.playbook_body.steps[7].action == "wait_ms"


def test_playbook_accepts_set_date_with_biz_date_template() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps[1] = {
        "id": "set_pay_start_time",
        "action": "set_date",
        "selector": "input[placeholder='起始日期']",
        "value": "{{params.biz_date}} 00:00:00",
        "timeout_ms": 30000,
    }

    msg = RunPlaybookMessage.model_validate(
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

    assert msg.playbook_body.steps[1].action == "set_date"
    assert msg.playbook_body.steps[1].value == "{{params.biz_date}} 00:00:00"


def test_playbook_accepts_qianniu_export_report_download_action() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps[6] = {
        "id": "download_latest_order_report",
        "action": "download_qianniu_export_report",
        "selector": "[class*='order-export_order-block']",
        "requested_after_from": "extracted.report_requested_at",
        "report_type": "订单报表",
        "download_button_text": "下载订单报表",
        "refresh_interval_ms": 10000,
        "download_timeout_ms": 600000,
        "timeout_ms": 900000,
    }

    msg = RunPlaybookMessage.model_validate(
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

    assert msg.playbook_body.steps[6].action == "download_qianniu_export_report"
    assert msg.playbook_body.steps[6].requested_after_from == "extracted.report_requested_at"


def test_playbook_accepts_ensure_page_ready_action() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        1,
        {
            "id": "ensure_bill_page_ready",
            "action": "ensure_page_ready",
            "target_url": "https://myseller.taobao.com/home.htm/whale-accountant/bill/summary",
            "ready_selector": "[data-summary='daily-bill']",
            "error_url_contains": ["error.htm"],
            "auth_url_contains": ["login.taobao.com"],
            "auth_text_contains": ["请先登录"],
            "allow_auth_redirect": True,
            "recover_attempts": 2,
            "wait_after_navigation_ms": 1000,
        },
    )

    msg = RunPlaybookMessage.model_validate(
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

    assert msg.playbook_body.steps[1].action == "ensure_page_ready"
    assert msg.playbook_body.steps[1].target_url.endswith("/whale-accountant/bill/summary")


def test_playbook_rejects_qianniu_export_report_download_without_requested_after() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps[6] = {
        "id": "download_latest_order_report",
        "action": "download_qianniu_export_report",
        "selector": "[class*='order-export_order-block']",
        "download_button_text": "下载订单报表",
    }

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


def test_playbook_rejects_select_checkboxes_without_labels() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        6,
        {
            "id": "select_export_fields",
            "action": "select_checkboxes",
            "selector": ".next-dialog",
        },
    )

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


def test_playbook_preserves_auth_check_for_login_state_detection() -> None:
    playbook = _valid_playbook_body()
    playbook["auth_check"] = {
        "logged_in_selector": ".account-menu",
        "timeout_ms": 1234,
    }

    msg = RunPlaybookMessage.model_validate(
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

    dumped = msg.playbook_body.model_dump()
    assert dumped["auth_check"] == {
        "logged_in_selector": ".account-menu",
        "timeout_ms": 1234,
    }


def test_playbook_rejects_login_action_without_required_selectors() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        1,
        {
            "id": "login_if_needed",
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
        },
    )

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


def test_playbook_rejects_login_action_without_credential_sources() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps.insert(
        1,
        {
            "id": "login_if_needed",
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
        },
    )

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


def test_activate_browser_playbook_allows_already_active_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finalize remains valid after verification success has already marked the binding active."""

    executed_sql: list[str] = []

    class FakeCursor:
        def __init__(self) -> None:
            self._fetch_index = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, *args, **kwargs) -> None:
            executed_sql.append(sql)

        def fetchone(self):
            self._fetch_index += 1
            if self._fetch_index == 1:
                return {"id": "playbook-001", "status": "active"}
            binding_sql = executed_sql[-1]
            if "profile_status = 'verifying'" in binding_sql:
                return None
            return {
                "id": "binding-001",
                "profile_status": "active",
                "playbook_status": "ok",
            }

    class FakeConn:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return self.cursor_obj

        def commit(self) -> None:
            pass

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    result = auth_db.activate_browser_playbook_and_binding(
        company_id="company-001",
        playbook_id="qianniu-daily-bill-export",
        version="1.0.0",
        data_source_id="source-001",
    )

    assert result["playbook"]["status"] == "active"
    assert result["binding"]["profile_status"] == "active"


def test_activate_browser_playbook_is_idempotent_for_already_active_playbook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-finalize (e.g. retrying an already-active task) must keep the playbook active
    instead of failing because its UPDATE WHERE excluded 'active'."""

    executed_sql: list[str] = []

    class FakeCursor:
        def __init__(self) -> None:
            self._fetch_index = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, *args, **kwargs) -> None:
            executed_sql.append(sql)

        def fetchone(self):
            self._fetch_index += 1
            if self._fetch_index == 1:
                return {"id": "playbook-001", "status": "active"}
            return {"id": "binding-001", "profile_status": "active", "playbook_status": "ok"}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self) -> None:
            pass

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    result = auth_db.activate_browser_playbook_and_binding(
        company_id="company-001",
        playbook_id="qianniu-daily-bill-export",
        version="1.0.0",
        data_source_id="source-001",
    )

    assert result["playbook"] and result["binding"]
    playbook_sql = next(sql for sql in executed_sql if "UPDATE playbooks" in sql)
    # 已 active 也要能命中(否则重试时翻不动 → finalize 报"不在 draft/verifying 状态")
    assert "'active'" in playbook_sql
    assert "status IN ('draft', 'replayed', 'approved', 'active')" in playbook_sql
    # 保留原审批时间,不被重试覆盖
    assert "COALESCE(approved_at, CURRENT_TIMESTAMP)" in playbook_sql


def test_clear_page_changed_bindings_matches_canonical_pause_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PAGE_CHANGED failures store an uppercase canonical pause reason."""

    executed: dict[str, object] = {}

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            executed["sql"] = sql
            executed["params"] = params

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self) -> None:
            pass

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    count = auth_db.clear_page_changed_bindings_for_playbook(
        company_id="company-001",
        playbook_id="qianniu-daily-bill-export",
    )

    assert count == 1
    assert "cron_pause_reason = 'PAGE_CHANGED'" in str(executed["sql"])
