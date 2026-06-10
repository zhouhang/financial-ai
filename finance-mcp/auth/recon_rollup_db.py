"""Repository helpers for recon rollup artifact persistence."""
from __future__ import annotations

from typing import Any

import psycopg2.extras

from auth.db import _normalize_record, get_conn

ROLLUP_METRIC_FIELDS = [
    "receivable_amount_total",
    "refund_amount_total",
    "net_receivable_amount_total",
    "settled_amount_total",
    "normal_in_transit_amount_total",
    "stuck_amount_total",
    "net_deduction_total",
    "net_deduction_rate",
    "diff_amount_total",
    "cohort_order_count",
    "settled_order_count",
    "normal_in_transit_count",
    "stuck_order_count",
    "matched_with_diff_count",
    "source_only_count",
    "target_only_count",
    "payback_days_sum",
    "payback_days_count",
]


def _rows(cur) -> list[dict[str, Any]]:
    return [_normalize_record(dict(row)) for row in (cur.fetchall() or [])]


def _row(cur) -> dict[str, Any] | None:
    row = cur.fetchone()
    return _normalize_record(dict(row)) if row else None


def _as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"<NA>", "NaT", "nan", "None", "null"}:
        return ""
    return text


def _clean_timestamp(value: Any) -> Any:
    text = str(value or "").strip()
    if not text or text in {"<NA>", "NaT", "nan", "None", "null"}:
        return None
    return value


def upsert_recon_period_rollup(
    *,
    company_id: str,
    plan_code: str,
    biz_date: str,
    as_of_ts: str,
    recon_type: str,
    plan_name_snapshot: str = "",
    domain: str = "ecom",
    **metrics: Any,
) -> str:
    cols = [
        "company_id",
        "domain",
        "plan_code",
        "plan_name_snapshot",
        "recon_type",
        "biz_date",
        "as_of_ts",
        *ROLLUP_METRIC_FIELDS,
    ]
    values = [
        company_id,
        domain,
        plan_code,
        plan_name_snapshot,
        recon_type,
        biz_date,
        as_of_ts,
        *[metrics.get(field) for field in ROLLUP_METRIC_FIELDS],
    ]
    placeholders = ", ".join(["%s"] * len(cols))
    update_cols = ["domain", "plan_name_snapshot", "as_of_ts", *ROLLUP_METRIC_FIELDS]
    set_clause = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_cols)
    sql = f"""
        INSERT INTO public.recon_period_rollup ({", ".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT (company_id, plan_code, biz_date, recon_type)
        DO UPDATE SET {set_clause}, updated_at = CURRENT_TIMESTAMP
        RETURNING id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
            row = cur.fetchone()
            conn.commit()
            return str(row[0]) if row else ""


def get_recon_period_rollup(
    *,
    company_id: str,
    plan_code: str,
    biz_date: str,
    recon_type: str,
) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM public.recon_period_rollup
                WHERE company_id = %s AND plan_code = %s
                  AND biz_date = %s AND recon_type = %s
                LIMIT 1
                """,
                (company_id, plan_code, biz_date, recon_type),
            )
            return _row(cur)


def list_recon_period_rollup(*, company_id: str, biz_date: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM public.recon_period_rollup
                WHERE company_id = %s AND biz_date = %s
                ORDER BY plan_code, recon_type
                """,
                (company_id, biz_date),
            )
            return _rows(cur)


def _canonical_line_params(
    row: dict[str, Any],
    *,
    company_id: str,
    domain: str,
    execution_run_id: str,
    plan_code: str,
    plan_name_snapshot: str,
    recon_type: str,
    biz_date: str,
) -> tuple[Any, ...]:
    receivable = _as_float(row.get("receivable_amount"))
    refund = _as_float(row.get("refund_amount"))
    settled = _as_float(row.get("settled_amount"))
    left_amount = max(receivable - refund, 0.0)
    right_amount = settled
    return (
        company_id,
        domain,
        execution_run_id or None,
        plan_code,
        plan_name_snapshot,
        recon_type,
        biz_date,
        _clean_text(row.get("order_no")),
        _clean_text(row.get("channel")),
        receivable,
        settled,
        refund,
        left_amount,
        right_amount,
        left_amount - right_amount,
        _clean_timestamp(row.get("pay_time")),
        _clean_timestamp(row.get("settle_time")),
        _clean_timestamp(row.get("finish_time")),
        _clean_text(row.get("match_status")),
        _clean_text(row.get("order_status")),
    )


def replace_canonical_recon_lines(
    *,
    company_id: str,
    domain: str,
    plan_code: str,
    recon_type: str,
    biz_date: str,
    rows: list[dict[str, Any]],
    plan_name_snapshot: str = "",
    execution_run_id: str = "",
) -> int:
    """Replace canonical rows for one plan/date/type. Avoid duplicates on reruns."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM public.canonical_recon_line
                WHERE company_id = %s AND domain = %s
                  AND plan_code = %s AND recon_type = %s AND biz_date = %s
                """,
                (company_id, domain, plan_code, recon_type, biz_date),
            )
            if rows:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO public.canonical_recon_line (
                        company_id, domain, execution_run_id, plan_code, plan_name_snapshot,
                        recon_type, biz_date, order_no, channel, receivable_amount,
                        settled_amount, refund_amount, left_amount, right_amount,
                        diff_amount, pay_time, settle_time, finish_time, match_status,
                        order_status
                    ) VALUES %s
                    """,
                    [
                        _canonical_line_params(
                            row,
                            company_id=company_id,
                            domain=domain,
                            execution_run_id=execution_run_id,
                            plan_code=plan_code,
                            plan_name_snapshot=plan_name_snapshot,
                            recon_type=recon_type,
                            biz_date=biz_date,
                        )
                        for row in rows
                    ],
                )
            conn.commit()
            return len(rows)


def replace_stuck_recon_alert(
    *,
    company_id: str,
    domain: str,
    plan_code: str,
    plan_name_snapshot: str,
    biz_date: str,
    stuck_amount: Any,
    stuck_count: Any,
    stuck_days_n: int,
    threshold_amount: Any = 0,
) -> dict[str, Any] | None:
    amount = _as_float(stuck_amount)
    count = _as_int(stuck_count)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                DELETE FROM public.recon_alert
                WHERE company_id = %s AND domain = %s AND plan_code = %s
                  AND biz_date = %s AND alert_code = 'unsettled_amount_aged'
                """,
                (company_id, domain, plan_code, biz_date),
            )
            if amount <= _as_float(threshold_amount) or count <= 0:
                conn.commit()
                return None
            cur.execute(
                """
                INSERT INTO public.recon_alert (
                    company_id, domain, biz_date, plan_code, plan_name_snapshot,
                    alert_code, severity, title, explain_text, amount, evidence,
                    first_seen_biz_date, last_seen_biz_date
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    'unsettled_amount_aged', 'warning', %s, %s, %s, %s::jsonb,
                    %s, %s
                )
                RETURNING *
                """,
                (
                    company_id,
                    domain,
                    biz_date,
                    plan_code,
                    plan_name_snapshot,
                    f"{plan_name_snapshot or plan_code} {count} 笔款项超 {int(stuck_days_n)} 天未结清，共 {amount:.0f} 元",
                    "按通用 canonical 口径识别：源侧已发生、目标侧截至 as_of 仍未结清。",
                    amount,
                    psycopg2.extras.Json(
                        {
                            "threshold_days": int(stuck_days_n),
                            "stuck_count": count,
                            "threshold_amount": _as_float(threshold_amount),
                        }
                    ),
                    biz_date,
                    biz_date,
                ),
            )
            row = _row(cur)
            conn.commit()
            return row
