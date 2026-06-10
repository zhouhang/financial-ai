from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import recon_digest_finalizer_db


class _Cursor:
    def __init__(self, rows_by_marker: dict[str, Any], captured: dict[str, Any]) -> None:
        self.rows_by_marker = rows_by_marker
        self.captured = captured
        self.last_sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None) -> None:
        self.last_sql = str(sql)
        self.params = params
        self.captured.setdefault("queries", []).append((self.last_sql, params))

    def fetchone(self):
        sql = self.last_sql
        if "FROM public.recon_digest_subscriptions" in sql:
            if "AND scope = %s::jsonb" in sql and "recipient_json = %s::jsonb" in sql:
                return self.rows_by_marker.get("existing_subscription")
            return self.rows_by_marker.get("subscription")
        if "RETURNING id, company_id, domain, view, period" in sql:
            return self.rows_by_marker.get("subscription")
        if "SELECT COUNT(*) AS total" in sql:
            return self.rows_by_marker.get("canonical_count", {"total": 0})
        if "RETURNING id, subscription_id" in sql:
            return self.rows_by_marker.get("digest")
        if "RETURNING id, digest_id" in sql:
            return self.rows_by_marker.get("delivery")
        return None

    def fetchall(self):
        sql = self.last_sql
        if "FROM public.execution_run_plans" in sql:
            return self.rows_by_marker.get("expected_runs", [])
        if "FROM public.recon_period_rollup" in sql:
            return self.rows_by_marker.get("rollups", [])
        if "FROM public.recon_alert" in sql:
            return self.rows_by_marker.get("alerts", [])
        return []


class _Conn:
    def __init__(self, rows_by_marker: dict[str, Any], captured: dict[str, Any]) -> None:
        self.rows_by_marker = rows_by_marker
        self.captured = captured
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        self.captured.setdefault("cursor_calls", []).append({"args": args, "kwargs": kwargs})
        return _Cursor(self.rows_by_marker, self.captured)

    def commit(self) -> None:
        self.committed = True
        self.captured["committed"] = True


def _patch_conn(monkeypatch, rows: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(recon_digest_finalizer_db, "get_conn", lambda: _Conn(rows, captured))
    return captured


def _subscription(view: str = "boss") -> dict[str, Any]:
    return {
        "id": "sub-001",
        "company_id": "company-001",
        "domain": "ecom",
        "view": view,
        "period": "daily",
        "scope": {"mode": "company_all"},
        "recipient_json": {"user_id": "u1"},
        "enabled": True,
        "status": "active",
    }


def test_finalize_blocks_when_expected_run_is_missing(monkeypatch) -> None:
    captured = _patch_conn(
        monkeypatch,
        {
            "subscription": _subscription(),
            "expected_runs": [
                {
                    "plan_code": "plan-001",
                    "plan_name": "资金对账",
                    "run_id": None,
                    "execution_status": None,
                }
            ],
        },
    )

    result = recon_digest_finalizer_db.finalize_digest_subscription(
        company_id="company-001",
        subscription_id="sub-001",
        biz_date="2026-06-05",
    )

    assert result["success"] is True
    assert result["status"] == "blocked"
    assert result["reason"] == "run_gate_incomplete"
    assert result["completeness"]["missing_plan_codes"] == ["plan-001"]
    assert any("run_context_json ->> 'biz_date'" in sql for sql, _ in captured["queries"])
    assert any("p.schedule_type = 'daily'" in sql for sql, _ in captured["queries"])


def test_finalize_blocks_when_rollup_missing_for_successful_plan(monkeypatch) -> None:
    _patch_conn(
        monkeypatch,
        {
            "subscription": _subscription(),
            "expected_runs": [
                {
                    "plan_code": "plan-001",
                    "plan_name": "资金对账",
                    "run_id": "run-001",
                    "execution_status": "success",
                }
            ],
            "rollups": [],
        },
    )

    result = recon_digest_finalizer_db.finalize_digest_subscription(
        company_id="company-001",
        subscription_id="sub-001",
        biz_date="2026-06-05",
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "rollup_missing"
    assert result["completeness"]["missing_rollup_plan_codes"] == ["plan-001"]


def test_finalize_upserts_digest_when_gate_and_rollup_are_complete(monkeypatch) -> None:
    captured = _patch_conn(
        monkeypatch,
        {
            "subscription": _subscription(view="finance"),
            "expected_runs": [
                {
                    "plan_code": "plan-001",
                    "plan_name": "资金对账",
                    "run_id": "run-001",
                    "execution_status": "success",
                    "finished_at": datetime(2026, 6, 6, 9, 0, 0),
                    "run_context_json": {
                        "biz_date": date(2026, 6, 5),
                        "amount": Decimal("12.50"),
                    },
                }
            ],
            "rollups": [
                {
                    "plan_code": "plan-001",
                    "as_of_ts": datetime(2026, 6, 6, 9, 0, 0),
                    "receivable_amount_total": Decimal("100"),
                    "refund_amount_total": Decimal("10"),
                    "net_receivable_amount_total": Decimal("90"),
                    "settled_amount_total": Decimal("80"),
                    "normal_in_transit_amount_total": Decimal("5"),
                    "stuck_amount_total": Decimal("5"),
                    "net_deduction_total": Decimal("10"),
                    "matched_with_diff_count": 2,
                    "source_only_count": 1,
                    "target_only_count": 0,
                }
            ],
            "alerts": [
                {
                    "id": "alert-001",
                    "plan_code": "plan-001",
                    "alert_code": "unsettled_amount_aged",
                    "severity": "warning",
                    "amount": Decimal("5"),
                    "title": "超期未到账",
                    "evidence": {"threshold_days": 5},
                }
            ],
            "canonical_count": {"total": 7},
            "digest": {
                "id": "digest-001",
                "subscription_id": "sub-001",
                "company_id": "company-001",
                "period": "daily",
                "period_start": date(2026, 6, 5),
                "period_end": date(2026, 6, 5),
                "structured": {"domain": "ecom"},
                "narrative": "ok",
                "completeness": {},
                "status": "ready",
            },
        },
    )

    result = recon_digest_finalizer_db.finalize_digest_subscription(
        company_id="company-001",
        subscription_id="sub-001",
        biz_date="2026-06-05",
    )

    assert result["status"] == "ready"
    assert result["digest"]["id"] == "digest-001"
    assert captured["committed"] is True
    digest_sql, digest_params = captured["queries"][-1]
    assert "ON CONFLICT (subscription_id, period_start, period_end)" in digest_sql
    assert digest_params[6] == "2026-06-05 对账底稿已生成。金额差异 2 条，源侧单边 1 条，目标侧单边 0 条。"
    structured_payload = digest_params[5].adapted
    completeness_payload = digest_params[7].adapted
    json.dumps(structured_payload, ensure_ascii=False)
    json.dumps(completeness_payload, ensure_ascii=False)
    assert structured_payload["stuck_alerts"][0]["amount"] == 5
    assert completeness_payload["plans"][0]["run_context_json"] == {
        "biz_date": "2026-06-05",
        "amount": 12.5,
    }


def test_finalize_returns_already_delivered_for_existing_delivered_digest(monkeypatch) -> None:
    _patch_conn(
        monkeypatch,
        {
            "subscription": _subscription(view="boss"),
            "expected_runs": [
                {
                    "plan_code": "plan-001",
                    "plan_name": "资金对账",
                    "run_id": "run-001",
                    "execution_status": "success",
                }
            ],
            "rollups": [
                {
                    "plan_code": "plan-001",
                    "recon_type": "fund",
                    "as_of_ts": datetime(2026, 6, 6, 9, 0, 0),
                }
            ],
            "alerts": [],
            "canonical_count": {"total": 0},
            "digest": {
                "id": "digest-001",
                "subscription_id": "sub-001",
                "company_id": "company-001",
                "period": "daily",
                "period_start": date(2026, 6, 5),
                "period_end": date(2026, 6, 5),
                "structured": {"domain": "ecom"},
                "narrative": "ok",
                "completeness": {},
                "status": "delivered",
            },
        },
    )

    result = recon_digest_finalizer_db.finalize_digest_subscription(
        company_id="company-001",
        subscription_id="sub-001",
        biz_date="2026-06-05",
    )

    assert result["status"] == "already_delivered"


def test_boss_digest_totals_only_use_fund_rollups_but_gate_accepts_all_plans(monkeypatch) -> None:
    captured = _patch_conn(
        monkeypatch,
        {
            "subscription": _subscription(view="boss"),
            "expected_runs": [
                {
                    "plan_code": "fund-plan",
                    "plan_name": "资金对账",
                    "run_id": "run-fund",
                    "execution_status": "success",
                },
                {
                    "plan_code": "order-plan",
                    "plan_name": "订单对账",
                    "run_id": "run-order",
                    "execution_status": "success",
                },
            ],
            "rollups": [
                {
                    "plan_code": "fund-plan",
                    "recon_type": "fund",
                    "as_of_ts": datetime(2026, 6, 6, 9, 0, 0),
                    "receivable_amount_total": Decimal("100"),
                    "settled_amount_total": Decimal("80"),
                },
                {
                    "plan_code": "order-plan",
                    "recon_type": "order",
                    "as_of_ts": datetime(2026, 6, 6, 9, 0, 0),
                    "receivable_amount_total": Decimal("999"),
                    "settled_amount_total": Decimal("999"),
                },
            ],
            "alerts": [],
            "canonical_count": {"total": 0},
            "digest": {
                "id": "digest-001",
                "subscription_id": "sub-001",
                "company_id": "company-001",
                "period": "daily",
                "period_start": date(2026, 6, 5),
                "period_end": date(2026, 6, 5),
                "structured": {"domain": "ecom"},
                "narrative": "ok",
                "completeness": {},
                "status": "ready",
            },
        },
    )

    result = recon_digest_finalizer_db.finalize_digest_subscription(
        company_id="company-001",
        subscription_id="sub-001",
        biz_date="2026-06-05",
    )

    assert result["status"] == "ready"
    digest_params = captured["queries"][-1][1]
    structured_payload = digest_params[5].adapted
    assert structured_payload["totals"]["receivable_total"] == 100
    assert structured_payload["rollup_scope"] == {
        "plan_codes": ["fund-plan"],
        "recon_types": ["fund"],
    }


def test_delivery_record_marks_digest_delivered_on_sent(monkeypatch) -> None:
    captured = _patch_conn(
        monkeypatch,
        {
            "delivery": {
                "id": "delivery-001",
                "digest_id": "digest-001",
                "company_id": "company-001",
                "subscription_id": "sub-001",
                "view": "boss",
                "status": "sent",
                "attempt_count": 1,
            }
        },
    )

    delivery = recon_digest_finalizer_db.upsert_digest_delivery_attempt(
        digest_id="digest-001",
        company_id="company-001",
        subscription_id="sub-001",
        view="boss",
        status="sent",
        message_id="msg-001",
        detail_url="https://example.test/detail",
    )

    assert delivery is not None
    assert delivery["status"] == "sent"
    assert captured["committed"] is True
    assert any("UPDATE public.recon_digest" in sql for sql, _ in captured["queries"])


def test_subscription_upsert_reuses_existing_active_natural_key(monkeypatch) -> None:
    captured = _patch_conn(
        monkeypatch,
        {
            "existing_subscription": {"id": "sub-existing"},
            "subscription": {
                "id": "sub-existing",
                "company_id": "company-001",
                "domain": "ecom",
                "view": "boss",
                "period": "daily",
            },
        },
    )

    item = recon_digest_finalizer_db.create_or_update_digest_subscription(
        company_id="company-001",
        view="boss",
        scope={"mode": "company_all"},
        recipient_json={"user_id": "u1"},
    )

    assert item["id"] == "sub-existing"
    queries = [sql for sql, _ in captured["queries"]]
    assert any("SELECT id" in sql and "recipient_json" in sql for sql in queries)
    assert any("UPDATE public.recon_digest_subscriptions" in sql for sql in queries)
    assert not any("INSERT INTO public.recon_digest_subscriptions" in sql for sql in queries)
