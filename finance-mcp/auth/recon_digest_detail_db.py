"""Repository helpers for public recon digest detail pages."""
from __future__ import annotations

import copy
import json
import logging
import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg2.extras

from auth.db import _normalize_record, get_conn

logger = logging.getLogger(__name__)

_ALLOWED_VIEWS = {"boss", "finance"}
_DEFAULT_STUCK_DAYS_N = 3


def _rows(cur) -> list[dict[str, Any]]:
    return [_json_safe(_normalize_record(dict(row))) for row in (cur.fetchall() or [])]


def _row(cur) -> dict[str, Any] | None:
    row = cur.fetchone()
    return _json_safe(_normalize_record(dict(row))) if row else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _resolve_stuck_days_n(structured: dict[str, Any]) -> int:
    raw_value = structured.get("stuck_days_n")
    if raw_value in (None, ""):
        return _DEFAULT_STUCK_DAYS_N
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return _DEFAULT_STUCK_DAYS_N


def _apply_stuck_threshold(layout: dict[str, Any], stuck_days_n: int) -> dict[str, Any]:
    """Replace drilldown.filter `aging>N` placeholders with the digest threshold."""
    patched = copy.deepcopy(layout)

    def _visit(value: Any) -> None:
        if isinstance(value, dict):
            drilldown = value.get("drilldown")
            if isinstance(drilldown, dict) and isinstance(drilldown.get("filter"), str):
                drilldown["filter"] = re.sub(
                    r"(aging\s*>\s*)N\b",
                    lambda match: f"{match.group(1)}{int(stuck_days_n)}",
                    drilldown["filter"],
                )
            for child in value.values():
                _visit(child)
        elif isinstance(value, list):
            for item in value:
                _visit(item)

    _visit(patched.get("sections"))
    return patched


_ROLLUP_ALIAS = {
    "receivable_total": "receivable_amount_total",
    "refund_total": "refund_amount_total",
    "net_receivable_total": "net_receivable_amount_total",
    "settled_total": "settled_amount_total",
    "normal_in_transit_amount": "normal_in_transit_amount_total",
    "stuck_amount": "stuck_amount_total",
    "net_deduction_total": "net_deduction_total",
    "net_deduction_rate": "net_deduction_rate",
    "matched_with_diff_count": "matched_with_diff_count",
    "source_only_count": "source_only_count",
    "target_only_count": "target_only_count",
}

_SUMMABLE_TOTALS = [
    "receivable_total",
    "refund_total",
    "net_receivable_total",
    "settled_total",
    "normal_in_transit_amount",
    "stuck_amount",
    "net_deduction_total",
    "matched_exact_count",
    "matched_with_diff_count",
    "source_only_count",
    "target_only_count",
]


def _num(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if math.isfinite(numeric) else 0.0


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _normalize_rollup_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a DB rollup row into renderer-facing metric_code keys."""
    out: dict[str, Any] = {
        "plan_code": row.get("plan_code"),
        "plan_name_snapshot": row.get("plan_name_snapshot"),
        "recon_type": row.get("recon_type"),
        "biz_date": row.get("biz_date"),
    }
    for metric_code, column_name in _ROLLUP_ALIAS.items():
        out[metric_code] = row.get(column_name)

    out["matched_exact_count"] = int(
        _num(row, "settled_order_count") - _num(row, "matched_with_diff_count")
    )
    out["payback_days_avg"] = _ratio(
        _num(row, "payback_days_sum"),
        _num(row, "payback_days_count"),
    )
    in_transit_amount = (
        _num(row, "normal_in_transit_amount_total") + _num(row, "stuck_amount_total")
    )
    out["in_transit_ratio"] = _ratio(
        in_transit_amount,
        _num(row, "net_receivable_amount_total"),
    )
    out["refund_ratio"] = _ratio(
        _num(row, "refund_amount_total"),
        _num(row, "receivable_amount_total"),
    )
    return out


def _compute_totals(normalized_rollups: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum additive metrics and recompute rate/ratio metrics for the company total."""
    totals: dict[str, Any] = {}
    for metric_code in _SUMMABLE_TOTALS:
        totals[metric_code] = sum(_num(row, metric_code) for row in normalized_rollups)

    settled_net_receivable = totals["settled_total"] + totals["net_deduction_total"]
    totals["net_deduction_rate"] = _ratio(
        totals["net_deduction_total"],
        settled_net_receivable,
    )
    in_transit_amount = totals["normal_in_transit_amount"] + totals["stuck_amount"]
    totals["in_transit_ratio"] = _ratio(
        in_transit_amount,
        totals["net_receivable_total"],
    )
    totals["refund_ratio"] = _ratio(
        totals["refund_total"],
        totals["receivable_total"],
    )
    return totals


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        normalized = value.strip()
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(normalized[:10])
            except ValueError:
                return None
    return None


def _normalize_diff_row(row: dict[str, Any], *, as_of_ts: Any = None) -> dict[str, Any]:
    """Normalize a canonical line and derive drilldown display fields."""
    out = dict(row)
    out["net_receivable"] = max(
        _num(row, "receivable_amount") - _num(row, "refund_amount"),
        0.0,
    )
    as_of_date = _parse_date(as_of_ts or row.get("as_of_ts") or row.get("biz_date"))
    pay_date = _parse_date(row.get("pay_time"))
    out["aging_days"] = (as_of_date - pay_date).days if as_of_date and pay_date else None
    return out


_DIFF_ROWS_SQL = """
    SELECT l.*, a.reason_code, a.is_true_diff,
           e.processing_status, e.fix_status, e.latest_feedback
    FROM public.canonical_recon_line AS l
    LEFT JOIN public.recon_attribution AS a ON a.line_id = l.id
    LEFT JOIN public.execution_run_exceptions AS e ON e.id = l.exception_id
    WHERE l.company_id = %s AND l.biz_date = %s AND l.domain = %s
"""


def _scope_filters_from_structured(structured: dict[str, Any]) -> tuple[list[str], list[str]]:
    scope = _as_dict(structured.get("rollup_scope"))
    return _as_str_list(scope.get("plan_codes")), _as_str_list(scope.get("recon_types"))


def _append_scope_filters(
    sql: str,
    params: list[Any],
    *,
    table_alias: str,
    plan_codes: list[str],
    recon_types: list[str],
) -> str:
    if plan_codes:
        sql += f" AND {table_alias}.plan_code = ANY(%s)"
        params.append(plan_codes)
    if recon_types:
        sql += f" AND {table_alias}.recon_type = ANY(%s)"
        params.append(recon_types)
    return sql


def _base_scope_params(
    *,
    company_id: str,
    biz_date: str,
    domain: str,
    plan_codes: list[str],
    recon_types: list[str],
) -> list[Any]:
    params: list[Any] = [company_id, biz_date, domain]
    if plan_codes:
        params.append(plan_codes)
    if recon_types:
        params.append(recon_types)
    return params


def get_public_digest_detail_bundle(
    *,
    digest_id: str,
    company_id: str,
    view: str,
    biz_date: str,
    domain: str = "",
    line_limit: int = 500,
) -> dict[str, Any] | None:
    normalized_digest_id = str(digest_id or "").strip()
    normalized_company_id = str(company_id or "").strip()
    normalized_view = str(view or "").strip().lower()
    normalized_biz_date = str(biz_date or "").strip()
    requested_domain = str(domain or "").strip()

    if (
        not normalized_digest_id
        or not normalized_company_id
        or normalized_view not in _ALLOWED_VIEWS
        or not normalized_biz_date
    ):
        return None

    try:
        safe_line_limit = int(line_limit or 500)
    except (TypeError, ValueError):
        safe_line_limit = 500
    safe_line_limit = max(1, min(safe_line_limit, 1000))

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, subscription_id, company_id, period, period_start, period_end,
                           structured, narrative, completeness, status, delivered_at
                    FROM public.recon_digest
                    WHERE id = %s AND company_id = %s
                    LIMIT 1
                    """,
                    (normalized_digest_id, normalized_company_id),
                )
                digest = _row(cur)
                if not digest:
                    return None

                structured = _as_dict(digest.get("structured"))
                normalized_domain = requested_domain or str(
                    structured.get("domain") or ""
                ).strip()
                if not normalized_domain:
                    return None
                scope_plan_codes, scope_recon_types = _scope_filters_from_structured(structured)

                cur.execute(
                    """
                    SELECT layout_code, domain, view, sections, version, status
                    FROM public.view_layout
                    WHERE domain = %s AND view = %s AND status = 'active'
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (normalized_domain, normalized_view),
                )
                layout = _row(cur)
                if not layout:
                    return None
                layout = _apply_stuck_threshold(layout, _resolve_stuck_days_n(structured))

                rollup_sql = _append_scope_filters(
                    """
                    SELECT *
                    FROM public.recon_period_rollup
                    WHERE company_id = %s AND biz_date = %s AND domain = %s
                    """,
                    [],
                    table_alias="recon_period_rollup",
                    plan_codes=scope_plan_codes,
                    recon_types=scope_recon_types,
                )
                rollup_sql += " ORDER BY plan_code"
                cur.execute(
                    rollup_sql,
                    tuple(
                        _base_scope_params(
                            company_id=normalized_company_id,
                            biz_date=normalized_biz_date,
                            domain=normalized_domain,
                            plan_codes=scope_plan_codes,
                            recon_types=scope_recon_types,
                        )
                    ),
                )
                rollups = _rows(cur)

                alert_sql = """
                    SELECT *
                    FROM public.recon_alert
                    WHERE company_id = %s AND biz_date = %s AND domain = %s
                """
                alert_params: list[Any] = [
                    normalized_company_id,
                    normalized_biz_date,
                    normalized_domain,
                ]
                if scope_plan_codes:
                    alert_sql += " AND plan_code = ANY(%s)"
                    alert_params.append(scope_plan_codes)
                alert_sql += " ORDER BY severity DESC, created_at DESC LIMIT 500"
                cur.execute(alert_sql, tuple(alert_params))
                alerts = _rows(cur)

                count_sql = _append_scope_filters(
                    """
                    SELECT COUNT(*) AS total
                    FROM public.canonical_recon_line
                    WHERE company_id = %s AND biz_date = %s AND domain = %s
                    """,
                    [],
                    table_alias="canonical_recon_line",
                    plan_codes=scope_plan_codes,
                    recon_types=scope_recon_types,
                )
                cur.execute(
                    count_sql,
                    tuple(
                        _base_scope_params(
                            company_id=normalized_company_id,
                            biz_date=normalized_biz_date,
                            domain=normalized_domain,
                            plan_codes=scope_plan_codes,
                            recon_types=scope_recon_types,
                        )
                    ),
                )
                canonical_total = int((_row(cur) or {}).get("total") or 0)

                line_sql = _append_scope_filters(
                    _DIFF_ROWS_SQL,
                    [],
                    table_alias="l",
                    plan_codes=scope_plan_codes,
                    recon_types=scope_recon_types,
                )
                line_params = _base_scope_params(
                    company_id=normalized_company_id,
                    biz_date=normalized_biz_date,
                    domain=normalized_domain,
                    plan_codes=scope_plan_codes,
                    recon_types=scope_recon_types,
                )
                line_sql += " ORDER BY l.plan_code, l.id LIMIT %s"
                line_params.append(safe_line_limit)
                cur.execute(line_sql, tuple(line_params))
                as_of_ts = max(
                    (row.get("as_of_ts") for row in rollups if row.get("as_of_ts")),
                    default=None,
                )
                canonical_lines = [
                    _normalize_diff_row(row, as_of_ts=as_of_ts) for row in _rows(cur)
                ]
                normalized_rollups = [_normalize_rollup_row(row) for row in rollups]

                return {
                    "success": True,
                    "view": normalized_view,
                    "domain": normalized_domain,
                    "biz_date": normalized_biz_date,
                    "digest": digest,
                    "layout": layout,
                    "data": {
                        "rollups": normalized_rollups,
                        "totals": _compute_totals(normalized_rollups),
                        "alerts": alerts,
                        "canonical_lines": canonical_lines,
                        "sampling": {
                            "loaded": len(canonical_lines),
                            "total": canonical_total,
                            "truncated": canonical_total > len(canonical_lines),
                        },
                    },
                }
    except Exception as exc:
        logger.error(f"查询 recon digest detail 失败 (digest_id={digest_id}): {exc}")
        return None


def list_public_digest_diff_rows(
    *,
    company_id: str,
    domain: str,
    biz_date: str,
    recon_type: str = "",
    plan_codes: list[str] | None = None,
    recon_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return full diff rows for public digest export, with optional recon_type filter."""
    normalized_company_id = str(company_id or "").strip()
    normalized_domain = str(domain or "").strip()
    normalized_biz_date = str(biz_date or "").strip()
    normalized_recon_type = str(recon_type or "").strip()
    if not normalized_company_id or not normalized_domain or not normalized_biz_date:
        return []

    normalized_plan_codes = [str(item).strip() for item in (plan_codes or []) if str(item).strip()]
    normalized_recon_types = [str(item).strip() for item in (recon_types or []) if str(item).strip()]
    if normalized_recon_type:
        if normalized_recon_types and normalized_recon_type not in normalized_recon_types:
            return []
        normalized_recon_types = [normalized_recon_type]

    sql = _append_scope_filters(
        _DIFF_ROWS_SQL,
        [],
        table_alias="l",
        plan_codes=normalized_plan_codes,
        recon_types=normalized_recon_types,
    )
    params: list[Any] = [
        normalized_company_id,
        normalized_biz_date,
        normalized_domain,
    ]
    if normalized_plan_codes:
        params.append(normalized_plan_codes)
    if normalized_recon_types:
        params.append(normalized_recon_types)
    sql += " ORDER BY l.plan_code, l.id"

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return [_normalize_diff_row(row) for row in _rows(cur)]
    except Exception as exc:
        logger.error(f"查询 digest 导出全量差异行失败 (company_id={company_id}): {exc}")
        return []
