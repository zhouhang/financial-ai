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
