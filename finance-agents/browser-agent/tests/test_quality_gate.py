from __future__ import annotations

import sys
from pathlib import Path

FINANCE_BROWSER_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_BROWSER_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_BROWSER_AGENT_ROOT))

from finance_browser_agent.quality_gate import validate_rows


def test_validate_rows_enforces_row_count_and_amount_total() -> None:
    result = validate_rows(
        rows=[
            {"bill_no": "BILL-001", "amount": "1,000.10", "biz_date": "2026-05-18"},
            {"bill_no": "BILL-002", "amount": "-0.10", "biz_date": "2026-05-18"},
        ],
        columns=[
            {"name": "bill_no", "type": "string", "required": True},
            {"name": "amount", "type": "decimal", "required": True},
            {"name": "biz_date", "type": "date", "required": True},
        ],
        item_key_fields=["bill_no"],
        amount_field="amount",
        date_field="biz_date",
        biz_date="2026-05-18",
        expected_row_count=2,
        expected_amount_total="1000.00",
    )

    assert result["success"] is True
    assert result["summary"]["amount_total"] == "1000.00"


def test_validate_rows_accepts_expected_row_count_from_page_text() -> None:
    result = validate_rows(
        rows=[
            {"bill_no": "BILL-001", "amount": "1.00", "biz_date": "2026-05-18"},
            {"bill_no": "BILL-002", "amount": "2.00", "biz_date": "2026-05-18"},
        ],
        columns=[
            {"name": "bill_no", "type": "string", "required": True},
            {"name": "amount", "type": "decimal", "required": True},
            {"name": "biz_date", "type": "date", "required": True},
        ],
        item_key_fields=["bill_no"],
        amount_field="amount",
        date_field="biz_date",
        biz_date="2026-05-18",
        expected_row_count="共 2 笔 / 1 页",
        expected_amount_total="3.00",
    )

    assert result["success"] is True
    assert result["summary"]["row_count"] == 2


def test_validate_rows_reports_expected_and_actual_row_count() -> None:
    result = validate_rows(
        rows=[
            {"bill_no": "BILL-001", "amount": "1.00", "biz_date": "2026-05-18"},
            {"bill_no": "BILL-002", "amount": "2.00", "biz_date": "2026-05-18"},
        ],
        columns=[
            {"name": "bill_no", "type": "string", "required": True},
            {"name": "amount", "type": "decimal", "required": True},
            {"name": "biz_date", "type": "date", "required": True},
        ],
        item_key_fields=["bill_no"],
        amount_field="amount",
        date_field="biz_date",
        biz_date="2026-05-18",
        expected_row_count="3",
    )

    assert result["success"] is False
    assert result["fail_reason"] == "DATA_MISMATCH"
    assert result["details"]["actual_row_count"] == 2
    assert result["details"]["expected_row_count"] == 3
    assert "明细 2 行" in result["error"]
    assert "日汇总 3 行" in result["error"]


def test_validate_rows_rejects_duplicate_item_keys() -> None:
    result = validate_rows(
        rows=[
            {"bill_no": "BILL-001", "amount": "1.00", "biz_date": "2026-05-18"},
            {"bill_no": "BILL-001", "amount": "2.00", "biz_date": "2026-05-18"},
        ],
        columns=[
            {"name": "bill_no", "type": "string", "required": True},
            {"name": "amount", "type": "decimal", "required": True},
            {"name": "biz_date", "type": "date", "required": True},
        ],
        item_key_fields=["bill_no"],
        amount_field="amount",
        date_field="biz_date",
        biz_date="2026-05-18",
    )

    assert result["success"] is False
    assert result["fail_reason"] == "DATA_MISMATCH"


def test_validate_rows_accepts_qianniu_payment_and_refund_with_composite_key() -> None:
    result = validate_rows(
        rows=[
            {
                "打款时间": "2026-05-25 10:18:36",
                "订单实际金额（元）": "30.7",
                "业务流水号": "2026052523001146961418525925",
                "退款单号": "",
            },
            {
                "打款时间": "2026-05-25 14:59:36",
                "订单实际金额（元）": "0",
                "业务流水号": "2026052523001146961418525925",
                "退款单号": "267972456644308979",
            },
        ],
        columns=[
            {"name": "打款时间", "type": "date", "required": True},
            {"name": "订单实际金额（元）", "type": "decimal", "required": True},
            {"name": "业务流水号", "type": "string", "required": True},
            {"name": "退款单号", "type": "string", "required": False},
        ],
        item_key_fields=["业务流水号", "退款单号"],
        amount_field="订单实际金额（元）",
        date_field="打款时间",
        biz_date="2026-05-25",
    )

    assert result["success"] is True


def test_validate_rows_rejects_date_mismatch() -> None:
    result = validate_rows(
        rows=[{"bill_no": "BILL-001", "amount": "1.00", "biz_date": "2026-05-17"}],
        columns=[
            {"name": "bill_no", "type": "string", "required": True},
            {"name": "amount", "type": "decimal", "required": True},
            {"name": "biz_date", "type": "date", "required": True},
        ],
        item_key_fields=["bill_no"],
        amount_field="amount",
        date_field="biz_date",
        biz_date="2026-05-18",
    )

    assert result["success"] is False
    assert result["fail_reason"] == "DATA_MISMATCH"
