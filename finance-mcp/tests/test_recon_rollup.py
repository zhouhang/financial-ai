from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

MCP_SERVER_DIR = Path(__file__).resolve().parents[1] / "recon" / "mcp_server"
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

import recon_rollup  # noqa: E402


FIELD_MAPPING = {
    "domain": "ecom",
    "canonical": {
        "order_no": {"side": "source", "from": "订单编号", "type": "id"},
        "receivable_amount": {"side": "source", "from": "买家实付金额", "type": "money"},
        "refund_amount": {"side": "source", "from": "退款金额", "type": "money"},
        "pay_time": {"side": "source", "from": "订单付款时间", "type": "datetime"},
        "settled_amount": {"side": "target", "from": "订单实际金额（元）", "type": "money"},
        "settle_time": {"side": "target", "from": "打款时间", "type": "datetime"},
    },
}


def test_project_bucket_renames_and_casts_and_tags_match_status() -> None:
    bucket = pd.DataFrame(
        [
            {
                "source_订单编号": "A1",
                "source_买家实付金额": "99.90",
                "source_退款金额": "0",
                "source_订单付款时间": "2026-06-05 10:00:00",
                "target_订单实际金额（元）": " 97.50 ",
                "target_打款时间": "2026-06-06 09:00:00",
            },
        ]
    )

    out = recon_rollup.project_bucket_to_canonical(bucket, "matched_exact", FIELD_MAPPING)
    row = out.iloc[0]

    assert row["order_no"] == "A1"
    assert float(row["receivable_amount"]) == 99.90
    assert float(row["settled_amount"]) == 97.50
    assert row["match_status"] == "matched_exact"
    assert pd.notna(row["pay_time"]) and pd.notna(row["settle_time"])


def test_project_bucket_missing_side_columns_yield_nan_not_crash() -> None:
    bucket = pd.DataFrame(
        [
            {
                "source_订单编号": "B2",
                "source_买家实付金额": "50",
                "source_退款金额": "0",
                "source_订单付款时间": "2026-06-01 08:00:00",
            },
        ]
    )

    out = recon_rollup.project_bucket_to_canonical(bucket, "left_only", FIELD_MAPPING)
    row = out.iloc[0]

    assert float(row["receivable_amount"]) == 50.0
    assert pd.isna(row["settled_amount"])
    assert row["match_status"] == "left_only"


def test_project_bucket_empty_dataframe_returns_empty_with_columns() -> None:
    out = recon_rollup.project_bucket_to_canonical(pd.DataFrame(), "right_only", FIELD_MAPPING)

    assert out.empty
    assert "match_status" in out.columns


def test_validate_rollup_field_mapping_fails_missing_required_canonical_fields() -> None:
    invalid = {"domain": "ecom", "canonical": {"order_no": {"side": "source", "from": "订单编号"}}}

    with pytest.raises(ValueError, match="missing required canonical fields"):
        recon_rollup.validate_rollup_field_mapping(invalid)


def test_compute_rollup_golden_fixture() -> None:
    df = pd.DataFrame(
        [
            {
                "order_no": "A",
                "receivable_amount": 99.9,
                "refund_amount": 0.0,
                "settled_amount": 97.5,
                "pay_time": pd.Timestamp("2026-06-05 10:00"),
                "settle_time": pd.Timestamp("2026-06-06 10:00"),
                "match_status": "matched_exact",
            },
            {
                "order_no": "B",
                "receivable_amount": 200.0,
                "refund_amount": 0.0,
                "settled_amount": 150.0,
                "pay_time": pd.Timestamp("2026-06-04 10:00"),
                "settle_time": pd.Timestamp("2026-06-06 10:00"),
                "match_status": "matched_with_diff",
            },
            {
                "order_no": "C",
                "receivable_amount": 50.0,
                "refund_amount": 0.0,
                "settled_amount": pd.NA,
                "pay_time": pd.Timestamp("2026-06-05 10:00"),
                "settle_time": pd.NaT,
                "match_status": "left_only",
            },
            {
                "order_no": "D",
                "receivable_amount": 80.0,
                "refund_amount": 30.0,
                "settled_amount": pd.NA,
                "pay_time": pd.Timestamp("2026-05-28 10:00"),
                "settle_time": pd.NaT,
                "match_status": "left_only",
            },
            {
                "order_no": "E",
                "receivable_amount": pd.NA,
                "refund_amount": pd.NA,
                "settled_amount": 40.0,
                "pay_time": pd.NaT,
                "settle_time": pd.Timestamp("2026-06-06 10:00"),
                "match_status": "right_only",
            },
        ]
    )

    rollup = recon_rollup.compute_recon_rollup(
        df,
        as_of_ts=pd.Timestamp("2026-06-06 09:00"),
        stuck_days_n=3,
    )

    assert rollup["receivable_amount_total"] == 429.9
    assert rollup["refund_amount_total"] == 30.0
    assert rollup["net_receivable_amount_total"] == 399.9
    assert rollup["settled_amount_total"] == 247.5
    assert rollup["normal_in_transit_amount_total"] == 50.0
    assert rollup["stuck_amount_total"] == 50.0
    assert rollup["net_deduction_total"] == pytest.approx(52.4)
    assert rollup["net_deduction_rate"] == pytest.approx(52.4 / 299.9)
    assert rollup["diff_amount_total"] == pytest.approx(50.0)
    assert rollup["cohort_order_count"] == 4
    assert rollup["settled_order_count"] == 2
    assert rollup["normal_in_transit_count"] == 1
    assert rollup["stuck_order_count"] == 1
    assert rollup["matched_with_diff_count"] == 1
    assert rollup["source_only_count"] == 2
    assert rollup["target_only_count"] == 1
    assert rollup["payback_days_sum"] == 3.0
    assert rollup["payback_days_count"] == 2


def test_compute_rollup_zero_denominator_rate_is_none() -> None:
    df = pd.DataFrame(
        [
            {
                "order_no": "C",
                "receivable_amount": 50.0,
                "refund_amount": 0.0,
                "settled_amount": pd.NA,
                "pay_time": pd.Timestamp("2026-06-05 10:00"),
                "settle_time": pd.NaT,
                "match_status": "left_only",
            },
        ]
    )

    rollup = recon_rollup.compute_recon_rollup(
        df,
        as_of_ts=pd.Timestamp("2026-06-06 09:00"),
        stuck_days_n=3,
    )

    assert rollup["net_deduction_rate"] is None
    assert rollup["settled_order_count"] == 0


def test_compute_rollup_empty_is_all_zero() -> None:
    rollup = recon_rollup.compute_recon_rollup(
        pd.DataFrame(columns=recon_rollup.CANONICAL_FIELDS + ["match_status"]),
        as_of_ts=pd.Timestamp("2026-06-06 09:00"),
        stuck_days_n=3,
    )

    assert rollup["cohort_order_count"] == 0
    assert rollup["receivable_amount_total"] == 0
    assert rollup["net_deduction_rate"] is None


def test_rollup_from_diff_result_concats_all_buckets() -> None:
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
                    "source_订单编号": "D",
                    "source_买家实付金额": "80",
                    "source_退款金额": "30",
                    "source_订单付款时间": "2026-05-28 10:00",
                },
            ]
        ),
        "target_only": pd.DataFrame(
            [
                {
                    "target_订单实际金额（元）": "40",
                    "target_打款时间": "2026-06-06 10:00",
                },
            ]
        ),
    }

    rollup = recon_rollup.rollup_from_diff_result(
        diff_result,
        FIELD_MAPPING,
        as_of_ts=pd.Timestamp("2026-06-06 09:00"),
        stuck_days_n=3,
    )

    assert rollup["cohort_order_count"] == 2
    assert rollup["settled_order_count"] == 1
    assert rollup["stuck_order_count"] == 1
    assert rollup["target_only_count"] == 1
    assert rollup["net_deduction_total"] == pytest.approx(2.4)
