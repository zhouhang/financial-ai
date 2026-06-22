from __future__ import annotations

import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

from tools import execution_runs


FUND_RULE = {
    "rules": [
        {
            "recon": {
                "key_columns": {
                    "mappings": [{"source_field": "订单编号", "target_field": "订单号"}],
                },
                "compare_columns": {
                    "columns": [
                        {
                            "source_column": "买家实付金额",
                            "target_column": "订单实际金额（元）",
                        }
                    ]
                },
            }
        }
    ]
}


def test_plan_create_infers_rollup_meta_before_persisting(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda _token: {"company_id": "co-1", "user_id": "user-1"},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_scheme",
        lambda **_: {"scheme_code": "scheme-1", "recon_rule_code": "rule-1"},
    )

    def fake_create_execution_run_plan(**kwargs):
        captured.update(kwargs)
        return {
            "id": "plan-id",
            "plan_code": "plan-1",
            "plan_name": kwargs["plan_name"],
            "plan_meta_json": kwargs["plan_meta_json"],
        }

    monkeypatch.setattr(
        execution_runs.auth_db,
        "create_execution_run_plan",
        fake_create_execution_run_plan,
    )
    monkeypatch.setattr(
        execution_runs,
        "_replace_dataset_bindings_for_scope",
        lambda **_: {"success": True},
    )
    from tools import rules

    monkeypatch.setattr(rules, "get_rule", lambda _rule_code: {"rule": FUND_RULE})

    result = execution_runs._plan_create(
        {
            "auth_token": "token",
            "plan_name": "万游引力数娱资金对账",
            "scheme_code": "scheme-1",
            "schedule_type": "daily",
            "input_bindings_json": [
                {"side": "left", "query": {"display_date_field": "订单付款时间"}},
                {"side": "right", "query": {"display_date_field": "打款时间"}},
            ],
        }
    )

    assert result["success"] is True
    assert captured["plan_meta_json"]["rollup"]["recon_type"] == "fund"
    assert captured["plan_meta_json"]["rollup"]["field_mapping"]["canonical"]["settle_time"] == {
        "side": "target",
        "from": "打款时间",
        "type": "datetime",
    }


def test_plan_create_infers_rollup_meta_from_embedded_scheme_rule(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda _token: {"company_id": "co-1", "user_id": "user-1"},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_scheme",
        lambda **_: {
            "scheme_code": "scheme-1",
            "recon_rule_code": "stale-rule-code",
            "scheme_meta_json": {"recon_rule_json": FUND_RULE},
        },
    )

    def fake_create_execution_run_plan(**kwargs):
        captured.update(kwargs)
        return {
            "id": "plan-id",
            "plan_code": "plan-1",
            "plan_name": kwargs["plan_name"],
            "plan_meta_json": kwargs["plan_meta_json"],
        }

    monkeypatch.setattr(
        execution_runs.auth_db,
        "create_execution_run_plan",
        fake_create_execution_run_plan,
    )
    monkeypatch.setattr(
        execution_runs,
        "_replace_dataset_bindings_for_scope",
        lambda **_: {"success": True},
    )
    from tools import rules

    monkeypatch.setattr(rules, "get_rule", lambda _rule_code: None)

    result = execution_runs._plan_create(
        {
            "auth_token": "token",
            "plan_name": "万游引力数娱资金对账",
            "scheme_code": "scheme-1",
            "schedule_type": "daily",
            "input_bindings_json": [
                {"side": "left", "query": {"display_date_field": "订单付款时间"}},
                {"side": "right", "query": {"display_date_field": "打款时间"}},
            ],
        }
    )

    assert result["success"] is True
    rollup_meta = captured["plan_meta_json"]["rollup"]
    assert rollup_meta["enabled"] is True
    assert rollup_meta["field_mapping"]["canonical"]["settled_amount"] == {
        "side": "target",
        "from": "订单实际金额（元）",
        "type": "money",
    }


def test_plan_create_allows_daily_plan_when_rollup_cannot_be_inferred(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda _token: {"company_id": "co-1", "user_id": "user-1"},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_scheme",
        lambda **_: {"scheme_code": "scheme-1", "recon_rule_code": "rule-1"},
    )
    from tools import rules

    monkeypatch.setattr(rules, "get_rule", lambda _rule_code: {"rule": {"rules": []}})
    monkeypatch.setattr(
        execution_runs,
        "_replace_dataset_bindings_for_scope",
        lambda **_: {"success": True},
    )

    def fake_create_execution_run_plan(**kwargs):
        captured.update(kwargs)
        return {
            "id": "plan-id",
            "plan_code": "plan-1",
            "plan_name": kwargs["plan_name"],
            "plan_meta_json": kwargs["plan_meta_json"],
        }

    monkeypatch.setattr(
        execution_runs.auth_db,
        "create_execution_run_plan",
        fake_create_execution_run_plan,
    )

    result = execution_runs._plan_create(
        {
            "auth_token": "token",
            "plan_name": "未知资金对账",
            "scheme_code": "scheme-1",
            "schedule_type": "daily",
            "is_enabled": True,
        }
    )

    assert result["success"] is True
    plan_meta = captured["plan_meta_json"]
    assert plan_meta["rollup"] == {
        "enabled": False,
        "warning": "无法从对账规则推导日报 rollup 字段映射",
    }


def test_plan_update_infers_rollup_meta_from_existing_plan(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        execution_runs,
        "_require_user",
        lambda _token: {"company_id": "co-1", "user_id": "user-1"},
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_run_plan",
        lambda **_: {
            "id": "plan-id",
            "plan_code": "plan-1",
            "plan_name": "万游引力数娱资金对账",
            "scheme_code": "scheme-1",
            "schedule_type": "daily",
            "input_bindings_json": [
                {"side": "left", "query": {"display_date_field": "订单付款时间"}},
                {"side": "right", "query": {"display_date_field": "打款时间"}},
            ],
            "plan_meta_json": {},
            "is_enabled": True,
        },
    )
    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_execution_scheme",
        lambda **_: {"scheme_code": "scheme-1", "recon_rule_code": "rule-1"},
    )

    def fake_update_execution_run_plan(**kwargs):
        captured.update(kwargs)
        return {
            "id": kwargs["plan_id"],
            "plan_code": "plan-1",
            "plan_name": "万游引力数娱资金对账",
            "plan_meta_json": kwargs["plan_meta_json"],
        }

    monkeypatch.setattr(
        execution_runs.auth_db,
        "update_execution_run_plan",
        fake_update_execution_run_plan,
    )
    from tools import rules

    monkeypatch.setattr(rules, "get_rule", lambda _rule_code: {"rule": FUND_RULE})

    result = execution_runs._plan_update({"auth_token": "token", "run_plan_id": "plan-id"})

    assert result["success"] is True
    assert captured["plan_meta_json"]["rollup"]["recon_type"] == "fund"
