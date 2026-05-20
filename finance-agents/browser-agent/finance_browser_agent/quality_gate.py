from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _money(value: Any) -> Decimal:
    text = str(value or "0").strip().replace(",", "").replace("￥", "").replace("¥", "")
    if text == "":
        text = "0"
    return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_rows(
    *,
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    item_key_fields: list[str],
    amount_field: str,
    date_field: str,
    biz_date: str,
    expected_row_count: int | None = None,
    expected_amount_total: str | None = None,
) -> dict[str, Any]:
    required_columns = [str(column["name"]) for column in columns if bool(column.get("required", True))]
    missing_columns = [column for column in required_columns if any(column not in row for row in rows)]
    if missing_columns:
        return {
            "success": False,
            "fail_reason": "PAGE_CHANGED",
            "error": f"缺少列: {missing_columns}",
        }

    bad_dates = [row for row in rows if str(row.get(date_field) or "")[:10] != biz_date]
    if bad_dates:
        return {
            "success": False,
            "fail_reason": "DATA_MISMATCH",
            "error": "数据日期与 biz_date 不一致",
        }

    seen_keys: set[str] = set()
    for row in rows:
        key = "|".join(str(row.get(field) or "").strip() for field in item_key_fields)
        if not key.strip("|"):
            return {"success": False, "fail_reason": "PAGE_CHANGED", "error": "item_key 为空"}
        if key in seen_keys:
            return {"success": False, "fail_reason": "DATA_MISMATCH", "error": f"item_key 重复: {key}"}
        seen_keys.add(key)

    total = sum((_money(row.get(amount_field)) for row in rows), Decimal("0.00"))
    total_text = str(total.quantize(Decimal("0.01")))
    if expected_row_count is not None and len(rows) != expected_row_count:
        return {"success": False, "fail_reason": "DATA_MISMATCH", "error": "行数与日汇总不一致"}
    if expected_amount_total is not None and total_text != str(_money(expected_amount_total)):
        return {"success": False, "fail_reason": "DATA_MISMATCH", "error": "金额合计与日汇总不一致"}
    return {"success": True, "summary": {"row_count": len(rows), "amount_total": total_text}}

