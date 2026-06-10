from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import recon_tool


FIELD_MAPPING = {
    "domain": "ecom",
    "canonical": {
        "order_no": {"side": "source", "from": "订单编号"},
        "receivable_amount": {"side": "source", "from": "买家实付金额", "type": "money"},
        "refund_amount": {"side": "source", "from": "退款金额", "type": "money"},
        "pay_time": {"side": "source", "from": "订单付款时间", "type": "datetime"},
        "settled_amount": {"side": "target", "from": "订单实际金额（元）", "type": "money"},
        "settle_time": {"side": "target", "from": "打款时间", "type": "datetime"},
    },
}


def test_maybe_attach_rollup_computes_and_persists_when_config_present() -> None:
    diff_result = {
        "matched_exact": pd.DataFrame(
            [
                {
                    "source_订单编号": "A",
                    "source_买家实付金额": "99.9",
                    "source_退款金额": "0",
                    "source_订单付款时间": "2026-06-05 10:00",
                    "target_订单实际金额（元）": "97.5",
                    "target_打款时间": "2026-06-06 10:00",
                },
            ]
        ),
        "matched_with_diff": pd.DataFrame(),
        "source_only": pd.DataFrame(
            [
                {
                    "source_订单编号": "B",
                    "source_买家实付金额": "50",
                    "source_退款金额": "0",
                    "source_订单付款时间": "2026-06-05 11:00",
                },
            ]
        ),
        "target_only": pd.DataFrame(),
    }
    rule_meta = {
        "rollup": {
            "plan_code": "p-1",
            "plan_name_snapshot": "单枪资金对账",
            "recon_type": "fund",
            "biz_date": "2026-06-05",
            "as_of_ts": "2026-06-06 09:00:00",
            "stuck_days_n": 3,
            "field_mapping": FIELD_MAPPING,
        }
    }
    result = {}

    with (
        patch.object(recon_tool, "upsert_recon_period_rollup", return_value="rid-1") as upsert,
        patch.object(recon_tool, "replace_canonical_recon_lines", return_value=1) as replace_lines,
        patch.object(recon_tool, "replace_stuck_recon_alert", return_value=None) as replace_alert,
    ):
        recon_tool._maybe_attach_period_rollup(
            result,
            diff_result,
            rule_meta,
            company_id="co-1",
        )

    assert result["period_rollup_status"] == "succeeded"
    assert result["period_rollup"]["cohort_order_count"] == 2
    assert result["period_rollup"]["net_deduction_total"] == pytest.approx(2.4)
    assert result["canonical_recon_line_count"] == 1
    upsert.assert_called_once()
    assert upsert.call_args.kwargs["company_id"] == "co-1"
    assert upsert.call_args.kwargs["plan_code"] == "p-1"
    replace_lines.assert_called_once()
    assert replace_lines.call_args.kwargs["rows"][0]["order_no"] == "B"
    assert replace_lines.call_args.kwargs["rows"][0]["match_status"] == "left_only"
    replace_alert.assert_called_once()


def test_maybe_attach_rollup_noop_without_config() -> None:
    result = {}

    recon_tool._maybe_attach_period_rollup(
        result,
        {"matched_exact": pd.DataFrame()},
        {},
        company_id="co-1",
    )

    assert "period_rollup" not in result


def test_maybe_attach_rollup_marks_failed_when_configured_but_input_invalid() -> None:
    result = {}

    recon_tool._maybe_attach_period_rollup(
        result,
        {"matched_exact": pd.DataFrame()},
        {"rollup": {"plan_code": "p-1", "recon_type": "fund", "biz_date": "2026-06-05"}},
        company_id="co-1",
    )

    assert result["period_rollup_status"] == "failed"
    assert "period_rollup_error" in result


def test_runtime_rollup_config_is_merged_without_persisted_rule_rollup() -> None:
    rule_content = {
        "rules": [
            {
                "enabled": True,
                "source_file": {"table_name": "left_recon_ready"},
                "target_file": {"table_name": "right_recon_ready"},
            }
        ],
    }
    run_context = {
        "rollup": {
            "enabled": True,
            "plan_code": "p-1",
            "field_mapping": FIELD_MAPPING,
        }
    }

    merged = recon_tool._merge_runtime_rollup_config(rule_content, run_context)

    assert "rollup" not in rule_content
    assert merged["rollup"]["plan_code"] == "p-1"
    assert merged["rollup"]["field_mapping"] == FIELD_MAPPING
