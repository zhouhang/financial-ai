"""Repository helpers for recon digest subscriptions, gates, and deliveries."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import Any

import psycopg2.extras

from auth.db import _normalize_record, get_conn

logger = logging.getLogger(__name__)

_ALLOWED_VIEWS = {"boss", "finance"}
_SUCCESS_STATUS = "success"
_DEFAULT_DOMAIN = "ecom"
_DEFAULT_STUCK_DAYS_N = 3
_BOSS_ROLLUP_RECON_TYPES = {"fund"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _rows(cur) -> list[dict[str, Any]]:
    return [_json_safe(_normalize_record(dict(row))) for row in (cur.fetchall() or [])]


def _row(cur) -> dict[str, Any] | None:
    row = cur.fetchone()
    return _json_safe(_normalize_record(dict(row))) if row else None


def _normalize_view(view: str) -> str:
    normalized = str(view or "").strip().lower()
    return normalized if normalized in _ALLOWED_VIEWS else ""


def list_digest_subscriptions(
    *,
    company_id: str,
    period: str = "daily",
    view: str = "",
) -> list[dict[str, Any]]:
    normalized_company_id = str(company_id or "").strip()
    normalized_period = str(period or "daily").strip() or "daily"
    normalized_view = _normalize_view(view)
    if not normalized_company_id:
        return []

    sql = """
        SELECT id, company_id, domain, view, period, scope, channel_config_id,
               target_type, recipient_json, conversation_id, send_window,
               failure_recipients, status, enabled, created_at, updated_at
        FROM public.recon_digest_subscriptions
        WHERE company_id = %s
          AND period = %s
          AND enabled = true
          AND status = 'active'
    """
    params: list[Any] = [normalized_company_id, normalized_period]
    if normalized_view:
        sql += " AND view = %s"
        params.append(normalized_view)
    sql += " ORDER BY view, created_at"

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return _rows(cur)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"查询 recon digest subscriptions 失败 (company_id={company_id}): {exc}")
        return []


def get_digest_subscription(
    *,
    company_id: str,
    subscription_id: str,
) -> dict[str, Any] | None:
    normalized_company_id = str(company_id or "").strip()
    normalized_subscription_id = str(subscription_id or "").strip()
    if not normalized_company_id or not normalized_subscription_id:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, domain, view, period, scope, channel_config_id,
                           target_type, recipient_json, conversation_id, send_window,
                           failure_recipients, status, enabled, created_at, updated_at
                    FROM public.recon_digest_subscriptions
                    WHERE company_id = %s AND id = %s
                    LIMIT 1
                    """,
                    (normalized_company_id, normalized_subscription_id),
                )
                return _row(cur)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "查询 recon digest subscription 失败 "
            f"(company_id={company_id}, subscription_id={subscription_id}): {exc}"
        )
        return None


def create_or_update_digest_subscription(
    *,
    company_id: str,
    view: str,
    domain: str = _DEFAULT_DOMAIN,
    period: str = "daily",
    scope: dict[str, Any] | None = None,
    channel_config_id: str = "",
    target_type: str = "user",
    recipient_json: dict[str, Any] | None = None,
    conversation_id: str = "",
    send_window: dict[str, Any] | None = None,
    failure_recipients: list[Any] | None = None,
    enabled: bool = True,
    subscription_id: str = "",
) -> dict[str, Any] | None:
    normalized_company_id = str(company_id or "").strip()
    normalized_view = _normalize_view(view)
    normalized_domain = str(domain or _DEFAULT_DOMAIN).strip() or _DEFAULT_DOMAIN
    normalized_period = str(period or "daily").strip() or "daily"
    normalized_target_type = str(target_type or "user").strip() or "user"
    normalized_scope = scope or {"mode": "company_all"}
    normalized_recipient_json = recipient_json or {}
    normalized_conversation_id = str(conversation_id or "").strip()
    normalized_scope_key = _stable_json(normalized_scope)
    normalized_recipient_key = _stable_json(normalized_recipient_json)
    if not normalized_company_id or not normalized_view:
        return None

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if not subscription_id:
                    cur.execute(
                        """
                        SELECT id
                        FROM public.recon_digest_subscriptions
                        WHERE company_id = %s
                          AND domain = %s
                          AND view = %s
                          AND period = %s
                          AND target_type = %s
                          AND conversation_id = %s
                          AND scope = %s::jsonb
                          AND recipient_json = %s::jsonb
                          AND status = 'active'
                        ORDER BY created_at
                        LIMIT 1
                        """,
                        (
                            normalized_company_id,
                            normalized_domain,
                            normalized_view,
                            normalized_period,
                            normalized_target_type,
                            normalized_conversation_id,
                            normalized_scope_key,
                            normalized_recipient_key,
                        ),
                    )
                    existing = cur.fetchone()
                    if existing:
                        subscription_id = str(existing["id"])

                if subscription_id:
                    cur.execute(
                        """
                        UPDATE public.recon_digest_subscriptions
                        SET domain = %s,
                            view = %s,
                            period = %s,
                            scope = %s::jsonb,
                            channel_config_id = NULLIF(%s, '')::uuid,
                            target_type = %s,
                            recipient_json = %s::jsonb,
                            conversation_id = %s,
                            send_window = %s::jsonb,
                            failure_recipients = %s::jsonb,
                            enabled = %s,
                            status = 'active',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND company_id = %s
                        RETURNING id, company_id, domain, view, period, scope, channel_config_id,
                                  target_type, recipient_json, conversation_id, send_window,
                            failure_recipients, status, enabled, created_at, updated_at
                        """,
                        (
                            normalized_domain,
                            normalized_view,
                            normalized_period,
                            psycopg2.extras.Json(normalized_scope),
                            str(channel_config_id or "").strip(),
                            normalized_target_type,
                            psycopg2.extras.Json(normalized_recipient_json),
                            normalized_conversation_id,
                            psycopg2.extras.Json(send_window or {}),
                            psycopg2.extras.Json(failure_recipients or []),
                            bool(enabled),
                            str(subscription_id),
                            normalized_company_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO public.recon_digest_subscriptions (
                            company_id, domain, view, period, scope, channel_config_id,
                            target_type, recipient_json, conversation_id, send_window,
                            failure_recipients, enabled
                        ) VALUES (
                            %s, %s, %s, %s, %s::jsonb, NULLIF(%s, '')::uuid,
                            %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s
                        )
                        RETURNING id, company_id, domain, view, period, scope, channel_config_id,
                                  target_type, recipient_json, conversation_id, send_window,
                                  failure_recipients, status, enabled, created_at, updated_at
                        """,
                        (
                            normalized_company_id,
                            normalized_domain,
                            normalized_view,
                            normalized_period,
                            psycopg2.extras.Json(normalized_scope),
                            str(channel_config_id or "").strip(),
                            normalized_target_type,
                            psycopg2.extras.Json(normalized_recipient_json),
                            normalized_conversation_id,
                            psycopg2.extras.Json(send_window or {}),
                            psycopg2.extras.Json(failure_recipients or []),
                            bool(enabled),
                        ),
                    )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error(f"保存 recon digest subscription 失败 (company_id={company_id}): {exc}")
        return None


def _expected_plan_scope_sql(scope: dict[str, Any]) -> tuple[str, list[Any]]:
    mode = str(scope.get("mode") or "company_all").strip()
    if mode == "plan_codes":
        plan_codes = [str(v).strip() for v in _as_list(scope.get("plan_codes")) if str(v).strip()]
        if not plan_codes:
            return "AND false", []
        return "AND p.plan_code = ANY(%s)", [plan_codes]
    # The current digest product is daily-only. Weekly/monthly/manual plans should
    # not block a T-1 daily digest unless the subscription explicitly names them.
    return "AND p.schedule_type = 'daily' AND (p.plan_meta_json->'rollup'->>'enabled') = 'true'", []


def _latest_runs_for_expected_plans(
    cur,
    *,
    company_id: str,
    biz_date: str,
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    scope_sql, scope_params = _expected_plan_scope_sql(scope)
    cur.execute(
        f"""
        WITH expected AS (
            SELECT p.id AS plan_id,
                   p.plan_code,
                   p.plan_name,
                   p.scheme_code,
                   p.schedule_type,
                   p.plan_meta_json
            FROM public.execution_run_plans p
            WHERE p.company_id = %s
              AND p.is_enabled = true
              {scope_sql}
        ),
        latest AS (
            SELECT DISTINCT ON (r.plan_code)
                   r.id AS run_id,
                   r.plan_code,
                   r.execution_status,
                   r.failed_stage,
                   r.failed_reason,
                   r.finished_at,
                   r.run_context_json
            FROM public.execution_runs r
            WHERE r.company_id = %s
              AND COALESCE(r.run_context_json ->> 'biz_date', '') = %s
              AND r.plan_code IN (SELECT plan_code FROM expected)
            ORDER BY r.plan_code, r.finished_at DESC NULLS LAST, r.created_at DESC
        )
        SELECT e.plan_id, e.plan_code, e.plan_name, e.scheme_code,
               e.schedule_type, e.plan_meta_json,
               l.run_id, l.execution_status, l.failed_stage, l.failed_reason,
               l.finished_at, l.run_context_json
        FROM expected e
        LEFT JOIN latest l ON l.plan_code = e.plan_code
        ORDER BY e.plan_code
        """,
        (company_id, *scope_params, company_id, biz_date),
    )
    return _rows(cur)


def _check_gate(rows: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    expected = len(rows)
    missing = [row for row in rows if not row.get("run_id")]
    failed = [
        row
        for row in rows
        if row.get("run_id") and str(row.get("execution_status") or "") != _SUCCESS_STATUS
    ]
    return not missing and not failed and expected > 0, {
        "expected_plan_count": expected,
        "successful_plan_count": expected - len(missing) - len(failed),
        "missing_plan_codes": [str(row.get("plan_code") or "") for row in missing],
        "failed_plan_codes": [str(row.get("plan_code") or "") for row in failed],
        "plans": rows,
        "is_complete": not missing and not failed and expected > 0,
    }


def _rollup_rows(
    cur,
    *,
    company_id: str,
    biz_date: str,
    domain: str,
    expected_plan_codes: list[str],
    recon_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not expected_plan_codes:
        return []
    normalized_recon_types = [str(item).strip() for item in (recon_types or []) if str(item).strip()]
    type_sql = ""
    params: list[Any] = [company_id, biz_date, domain, expected_plan_codes]
    if normalized_recon_types:
        type_sql = " AND recon_type = ANY(%s)"
        params.append(normalized_recon_types)
    cur.execute(
        f"""
        SELECT *
        FROM public.recon_period_rollup
        WHERE company_id = %s
          AND biz_date = %s
          AND domain = %s
          AND plan_code = ANY(%s)
          {type_sql}
        ORDER BY plan_code
        """,
        tuple(params),
    )
    return _rows(cur)


def _rollup_recon_types_for_view(view: str) -> list[str]:
    normalized_view = _normalize_view(view)
    if normalized_view == "boss":
        return sorted(_BOSS_ROLLUP_RECON_TYPES)
    return []


def _alert_rows(
    cur,
    *,
    company_id: str,
    biz_date: str,
    domain: str,
    expected_plan_codes: list[str],
) -> list[dict[str, Any]]:
    if not expected_plan_codes:
        return []
    cur.execute(
        """
        SELECT *
        FROM public.recon_alert
        WHERE company_id = %s
          AND biz_date = %s
          AND domain = %s
          AND plan_code = ANY(%s)
        ORDER BY severity DESC, created_at DESC
        LIMIT 200
        """,
        (company_id, biz_date, domain, expected_plan_codes),
    )
    return _rows(cur)


def _canonical_sampling(
    cur,
    *,
    company_id: str,
    biz_date: str,
    domain: str,
    expected_plan_codes: list[str],
) -> dict[str, Any]:
    if not expected_plan_codes:
        return {"total": 0, "loaded": 0, "truncated": False}
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM public.canonical_recon_line
        WHERE company_id = %s
          AND biz_date = %s
          AND domain = %s
          AND plan_code = ANY(%s)
        """,
        (company_id, biz_date, domain, expected_plan_codes),
    )
    total = int((_row(cur) or {}).get("total") or 0)
    return {"total": total, "loaded": min(total, 500), "truncated": total > 500}


def _build_structured(
    *,
    domain: str,
    biz_date: str,
    view: str,
    rollups: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    sampling: dict[str, Any],
    completeness: dict[str, Any],
) -> dict[str, Any]:
    totals = {
        "receivable_total": sum(_as_float(row.get("receivable_amount_total")) for row in rollups),
        "refund_total": sum(_as_float(row.get("refund_amount_total")) for row in rollups),
        "net_receivable_total": sum(
            _as_float(row.get("net_receivable_amount_total")) for row in rollups
        ),
        "settled_total": sum(_as_float(row.get("settled_amount_total")) for row in rollups),
        "normal_in_transit_amount": sum(
            _as_float(row.get("normal_in_transit_amount_total")) for row in rollups
        ),
        "stuck_amount": sum(_as_float(row.get("stuck_amount_total")) for row in rollups),
        "matched_with_diff_count": sum(
            _as_float(row.get("matched_with_diff_count")) for row in rollups
        ),
        "source_only_count": sum(_as_float(row.get("source_only_count")) for row in rollups),
        "target_only_count": sum(_as_float(row.get("target_only_count")) for row in rollups),
    }
    totals["in_transit_ratio"] = _ratio(
        totals["normal_in_transit_amount"] + totals["stuck_amount"],
        totals["net_receivable_total"],
    )
    totals["refund_ratio"] = _ratio(totals["refund_total"], totals["receivable_total"])

    as_of_ts = max((str(row.get("as_of_ts") or "") for row in rollups), default="")
    stuck_days_n = _DEFAULT_STUCK_DAYS_N
    for alert in alerts:
        evidence = _as_dict(alert.get("evidence"))
        threshold = evidence.get("threshold_days")
        if threshold not in (None, ""):
            try:
                stuck_days_n = int(threshold)
                break
            except (TypeError, ValueError):
                pass

    return {
        "domain": domain,
        "view": view,
        "biz_date": biz_date,
        "as_of_ts": as_of_ts,
        "stuck_days_n": stuck_days_n,
        "totals": totals,
        "sampling": sampling,
        "stuck_alerts": [
            {
                "id": alert.get("id"),
                "plan_code": alert.get("plan_code"),
                "plan_name_snapshot": alert.get("plan_name_snapshot"),
                "alert_code": alert.get("alert_code"),
                "severity": alert.get("severity"),
                "amount": _as_float(alert.get("amount")),
                "title": alert.get("title"),
            }
            for alert in alerts
        ],
        "completeness": completeness,
    }


def _build_narrative(*, biz_date: str, view: str, structured: dict[str, Any]) -> str:
    totals = _as_dict(structured.get("totals"))
    if view == "boss":
        return (
            f"{biz_date} 对账日报已完成。"
            f"买家实付 {totals.get('receivable_total', 0):,.2f}，"
            f"已到账 {totals.get('settled_total', 0):,.2f}，"
            f"在途（未到账）{totals.get('normal_in_transit_amount', 0):,.2f}。"
        )
    return (
        f"{biz_date} 对账底稿已生成。"
        f"金额差异 {int(totals.get('matched_with_diff_count') or 0)} 条，"
        f"源侧单边 {int(totals.get('source_only_count') or 0)} 条，"
        f"目标侧单边 {int(totals.get('target_only_count') or 0)} 条。"
    )


def finalize_digest_subscription(
    *,
    company_id: str,
    subscription_id: str,
    biz_date: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Check completeness and upsert one digest for one subscription."""
    normalized_company_id = str(company_id or "").strip()
    normalized_subscription_id = str(subscription_id or "").strip()
    normalized_biz_date = str(biz_date or "").strip()
    if not normalized_company_id or not normalized_subscription_id or not normalized_biz_date:
        return {"success": False, "status": "invalid", "error": "company_id/subscription_id/biz_date 不能为空"}

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, domain, view, period, scope, channel_config_id,
                           target_type, recipient_json, conversation_id, send_window,
                           failure_recipients, status, enabled
                    FROM public.recon_digest_subscriptions
                    WHERE id = %s AND company_id = %s AND enabled = true AND status = 'active'
                    LIMIT 1
                    """,
                    (normalized_subscription_id, normalized_company_id),
                )
                subscription = _row(cur)
                if not subscription:
                    return {"success": False, "status": "missing_subscription", "error": "日报订阅不存在或未启用"}

                view = _normalize_view(str(subscription.get("view") or ""))
                domain = str(subscription.get("domain") or _DEFAULT_DOMAIN).strip() or _DEFAULT_DOMAIN
                scope = _as_dict(subscription.get("scope")) or {"mode": "company_all"}
                expected_runs = _latest_runs_for_expected_plans(
                    cur,
                    company_id=normalized_company_id,
                    biz_date=normalized_biz_date,
                    scope=scope,
                )
                complete, completeness = _check_gate(expected_runs)
                if not complete:
                    return {
                        "success": True,
                        "status": "blocked",
                        "reason": "run_gate_incomplete",
                        "subscription": subscription,
                        "completeness": completeness,
                    }

                expected_plan_codes = [
                    str(row.get("plan_code") or "") for row in expected_runs if str(row.get("plan_code") or "")
                ]
                all_rollups = _rollup_rows(
                    cur,
                    company_id=normalized_company_id,
                    biz_date=normalized_biz_date,
                    domain=domain,
                    expected_plan_codes=expected_plan_codes,
                )
                rollup_plan_codes = {str(row.get("plan_code") or "") for row in all_rollups}
                missing_rollups = [
                    plan_code for plan_code in expected_plan_codes if plan_code not in rollup_plan_codes
                ]
                if missing_rollups:
                    return {
                        "success": True,
                        "status": "blocked",
                        "reason": "rollup_missing",
                        "subscription": subscription,
                        "completeness": {**completeness, "missing_rollup_plan_codes": missing_rollups},
                    }
                display_recon_types = set(_rollup_recon_types_for_view(view))
                rollups = [
                    row
                    for row in all_rollups
                    if not display_recon_types
                    or str(row.get("recon_type") or "").strip() in display_recon_types
                ]
                if display_recon_types and not rollups:
                    return {
                        "success": True,
                        "status": "blocked",
                        "reason": "display_rollup_missing",
                        "subscription": subscription,
                        "completeness": {
                            **completeness,
                            "missing_display_recon_types": sorted(display_recon_types),
                        },
                    }
                rollup_scope = {
                    "plan_codes": [
                        str(row.get("plan_code") or "")
                        for row in rollups
                        if str(row.get("plan_code") or "")
                    ],
                    "recon_types": sorted(
                        {
                            str(row.get("recon_type") or "").strip()
                            for row in rollups
                            if str(row.get("recon_type") or "").strip()
                        }
                    ),
                }

                alerts = _alert_rows(
                    cur,
                    company_id=normalized_company_id,
                    biz_date=normalized_biz_date,
                    domain=domain,
                    expected_plan_codes=expected_plan_codes,
                )
                sampling = _canonical_sampling(
                    cur,
                    company_id=normalized_company_id,
                    biz_date=normalized_biz_date,
                    domain=domain,
                    expected_plan_codes=expected_plan_codes,
                )
                structured = _build_structured(
                    domain=domain,
                    biz_date=normalized_biz_date,
                    view=view,
                    rollups=rollups,
                    alerts=alerts,
                    sampling=sampling,
                    completeness=completeness,
                )
                structured["rollup_scope"] = rollup_scope
                narrative = _build_narrative(
                    biz_date=normalized_biz_date,
                    view=view,
                    structured=structured,
                )
                if dry_run:
                    return {
                        "success": True,
                        "status": "ready",
                        "dry_run": True,
                        "subscription": subscription,
                        "completeness": completeness,
                        "structured": structured,
                        "narrative": narrative,
                    }

                cur.execute(
                    """
                    INSERT INTO public.recon_digest (
                        subscription_id, company_id, period, period_start, period_end,
                        structured, narrative, completeness, status, delivered_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, 'ready', NULL
                    )
                    ON CONFLICT (subscription_id, period_start, period_end) DO UPDATE SET
                        structured = EXCLUDED.structured,
                        narrative = EXCLUDED.narrative,
                        completeness = EXCLUDED.completeness,
                        status = CASE
                            WHEN public.recon_digest.status = 'delivered' THEN public.recon_digest.status
                            ELSE 'ready'
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, subscription_id, company_id, period, period_start, period_end,
                              structured, narrative, completeness, status, delivered_at
                    """,
                    (
                        normalized_subscription_id,
                        normalized_company_id,
                        str(subscription.get("period") or "daily"),
                        normalized_biz_date,
                        normalized_biz_date,
                        psycopg2.extras.Json(_json_safe(structured)),
                        narrative,
                        psycopg2.extras.Json(_json_safe(completeness)),
                    ),
                )
                digest = _row(cur)
                conn.commit()
                digest_status = str((digest or {}).get("status") or "ready")
                return {
                    "success": True,
                    "status": digest_status if digest_status != "delivered" else "already_delivered",
                    "subscription": subscription,
                    "digest": digest,
                    "completeness": completeness,
                }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "finalize recon digest 失败 "
            f"(company_id={company_id}, subscription_id={subscription_id}, biz_date={biz_date}): {exc}"
        )
        return {"success": False, "status": "error", "error": str(exc)}


def finalize_company_daily_digests(
    *,
    company_id: str,
    biz_date: str,
    view: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    subscriptions = list_digest_subscriptions(company_id=company_id, period="daily", view=view)
    results = [
        finalize_digest_subscription(
            company_id=company_id,
            subscription_id=str(subscription.get("id") or ""),
            biz_date=biz_date,
            dry_run=dry_run,
        )
        for subscription in subscriptions
    ]
    return {
        "success": True,
        "status": "ok",
        "count": len(results),
        "ready_count": sum(1 for item in results if item.get("status") == "ready"),
        "blocked_count": sum(1 for item in results if item.get("status") == "blocked"),
        "results": results,
    }


def upsert_digest_delivery_attempt(
    *,
    digest_id: str,
    company_id: str,
    subscription_id: str,
    view: str,
    status: str,
    reason: str = "",
    error: str = "",
    message_id: str = "",
    detail_url: str = "",
    raw_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_digest_id = str(digest_id or "").strip()
    normalized_company_id = str(company_id or "").strip()
    normalized_subscription_id = str(subscription_id or "").strip()
    normalized_view = _normalize_view(view)
    normalized_status = str(status or "pending").strip() or "pending"
    if not all([normalized_digest_id, normalized_company_id, normalized_subscription_id, normalized_view]):
        return None
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO public.recon_digest_deliveries (
                        digest_id, company_id, subscription_id, view, status,
                        reason, error, message_id, detail_url, attempt_count,
                        last_attempt_at, delivered_at, raw_result
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, 1,
                        CURRENT_TIMESTAMP,
                        CASE WHEN %s = 'sent' THEN CURRENT_TIMESTAMP ELSE NULL END,
                        %s::jsonb
                    )
                    ON CONFLICT (digest_id, view, subscription_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        reason = EXCLUDED.reason,
                        error = EXCLUDED.error,
                        message_id = EXCLUDED.message_id,
                        detail_url = EXCLUDED.detail_url,
                        attempt_count = public.recon_digest_deliveries.attempt_count + 1,
                        last_attempt_at = CURRENT_TIMESTAMP,
                        delivered_at = CASE
                            WHEN EXCLUDED.status = 'sent' THEN CURRENT_TIMESTAMP
                            ELSE public.recon_digest_deliveries.delivered_at
                        END,
                        raw_result = EXCLUDED.raw_result,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, digest_id, company_id, subscription_id, view, status,
                              reason, error, message_id, detail_url, attempt_count,
                              last_attempt_at, delivered_at, raw_result,
                              created_at, updated_at
                    """,
                    (
                        normalized_digest_id,
                        normalized_company_id,
                        normalized_subscription_id,
                        normalized_view,
                        normalized_status,
                        str(reason or ""),
                        str(error or ""),
                        str(message_id or ""),
                        str(detail_url or ""),
                        normalized_status,
                        psycopg2.extras.Json(_json_safe(raw_result or {})),
                    ),
                )
                row = cur.fetchone()
                if normalized_status == "sent":
                    cur.execute(
                        """
                        UPDATE public.recon_digest
                        SET status = 'delivered',
                            delivered_at = COALESCE(delivered_at, CURRENT_TIMESTAMP),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND company_id = %s
                        """,
                        (normalized_digest_id, normalized_company_id),
                    )
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error(f"保存 recon digest delivery 失败 (digest_id={digest_id}): {exc}")
        return None
