from __future__ import annotations

import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

from tools.recon_rollup_meta import enrich_plan_meta_with_rollup


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
                            "compare_type": "numeric",
                        }
                    ]
                },
            }
        }
    ]
}


ORDER_RULE = {
    "rules": [
        {
            "recon": {
                "key_columns": {
                    "mappings": [{"source_field": "客户订单号", "target_field": "订单编号"}],
                },
                "compare_columns": {
                    "columns": [
                        {
                            "source_column": "含税销售金额",
                            "target_column": "买家实付金额",
                        }
                    ]
                },
            }
        }
    ]
}


def test_enriches_fund_daily_plan_meta_with_rollup() -> None:
    meta, warnings = enrich_plan_meta_with_rollup(
        plan_name="万游引力数娱资金对账",
        schedule_type="daily",
        plan_meta_json={},
        recon_rule=FUND_RULE,
    )

    assert warnings == []
    assert meta["rollup"]["enabled"] is True
    assert meta["rollup"]["recon_type"] == "fund"
    assert meta["rollup"]["field_mapping"] == {
        "domain": "ecom",
        "canonical": {
            "order_no": {"side": "source", "from": "订单编号", "type": "id"},
            "receivable_amount": {"side": "source", "from": "买家实付金额", "type": "money"},
            "refund_amount": {"side": "source", "from": "退款金额", "type": "money", "default": 0},
            "pay_time": {"side": "source", "from": "订单付款时间", "type": "datetime"},
            "settled_amount": {"side": "target", "from": "订单实际金额（元）", "type": "money"},
            "settle_time": {"side": "target", "from": "打款时间", "type": "datetime"},
        },
    }


def test_enriches_order_daily_plan_meta_with_order_recon_type() -> None:
    meta, warnings = enrich_plan_meta_with_rollup(
        plan_name="万游引力数娱订单对账",
        schedule_type="daily",
        plan_meta_json={},
        recon_rule=ORDER_RULE,
    )

    assert warnings == []
    assert meta["rollup"]["recon_type"] == "order"
    assert meta["rollup"]["field_mapping"]["canonical"]["order_no"] == {
        "side": "source",
        "from": "客户订单号",
        "type": "id",
    }
    assert meta["rollup"]["field_mapping"]["canonical"]["settled_amount"] == {
        "side": "target",
        "from": "买家实付金额",
        "type": "money",
    }
    assert meta["rollup"]["field_mapping"]["canonical"]["settle_time"] == {
        "side": "target",
        "from": "订单付款时间",
        "type": "datetime",
    }


def test_keeps_existing_rollup_unchanged() -> None:
    existing_rollup = {"enabled": True, "recon_type": "custom", "field_mapping": {"canonical": {}}}

    meta, warnings = enrich_plan_meta_with_rollup(
        plan_name="万游引力数娱资金对账",
        schedule_type="daily",
        plan_meta_json={"rollup": existing_rollup},
        recon_rule=FUND_RULE,
    )

    assert warnings == []
    assert meta["rollup"] == existing_rollup


def test_skips_non_daily_plans() -> None:
    meta, warnings = enrich_plan_meta_with_rollup(
        plan_name="手动资金对账",
        schedule_type="manual_trigger",
        plan_meta_json={},
        recon_rule=FUND_RULE,
    )

    assert warnings == []
    assert "rollup" not in meta


def test_returns_warning_when_mapping_cannot_be_inferred() -> None:
    meta, warnings = enrich_plan_meta_with_rollup(
        plan_name="未知资金对账",
        schedule_type="daily",
        plan_meta_json={},
        recon_rule={"rules": [{"recon": {"key_columns": {}, "compare_columns": {"columns": []}}}]},
    )

    assert "rollup" not in meta
    assert warnings == ["无法从对账规则推导日报 rollup 字段映射"]
