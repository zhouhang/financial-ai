from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import recon_rollup_db


class _Cursor:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None) -> None:
        self.last_sql = str(sql)
        self.captured.setdefault("queries", []).append((self.last_sql, params))

    def fetchone(self):
        if "RETURNING id" in self.last_sql:
            return ("row-001",)
        if "RETURNING *" in self.last_sql:
            return {"id": "alert-001", "amount": 50}
        return {
            "id": "rollup-001",
            "company_id": "company-001",
            "plan_code": "plan-001",
        }

    def fetchall(self):
        return [{"id": "rollup-001"}]


class _Conn:
    def __init__(self, captured: dict[str, Any]) -> None:
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        self.captured.setdefault("cursor_calls", []).append({"args": args, "kwargs": kwargs})
        return _Cursor(self.captured)

    def commit(self) -> None:
        self.captured["committed"] = True


def _patch_conn(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(recon_rollup_db, "get_conn", lambda: _Conn(captured))
    return captured


def test_upsert_recon_period_rollup_uses_unique_key(monkeypatch) -> None:
    captured = _patch_conn(monkeypatch)

    row_id = recon_rollup_db.upsert_recon_period_rollup(
        company_id="company-001",
        domain="ecom",
        plan_code="plan-001",
        plan_name_snapshot="计划 1",
        recon_type="fund",
        biz_date="2026-06-05",
        as_of_ts="2026-06-06T00:00:00+08:00",
        receivable_amount_total=100,
        settled_amount_total=90,
    )

    assert row_id == "row-001"
    sql, params = captured["queries"][0]
    assert "ON CONFLICT (company_id, plan_code, biz_date, recon_type)" in sql
    assert params[:7] == [
        "company-001",
        "ecom",
        "plan-001",
        "计划 1",
        "fund",
        "2026-06-05",
        "2026-06-06T00:00:00+08:00",
    ]
    assert captured["committed"] is True


def test_replace_canonical_lines_delete_then_bulk_insert(monkeypatch) -> None:
    captured = _patch_conn(monkeypatch)
    inserted: dict[str, Any] = {}

    def fake_execute_values(cur, sql, values):
        inserted["sql"] = sql
        inserted["values"] = values

    monkeypatch.setattr(recon_rollup_db.psycopg2.extras, "execute_values", fake_execute_values)

    count = recon_rollup_db.replace_canonical_recon_lines(
        company_id="company-001",
        domain="ecom",
        plan_code="plan-001",
        plan_name_snapshot="计划 1",
        recon_type="fund",
        biz_date="2026-06-05",
        execution_run_id="",
        rows=[
            {
                "order_no": "A",
                "receivable_amount": 100,
                "refund_amount": 10,
                "settled_amount": 80,
                "pay_time": "2026-06-05 10:00:00",
                "settle_time": "NaT",
                "finish_time": "",
                "match_status": "matched_with_diff",
            }
        ],
    )

    assert count == 1
    assert "DELETE FROM public.canonical_recon_line" in captured["queries"][0][0]
    assert "INSERT INTO public.canonical_recon_line" in inserted["sql"]
    assert inserted["values"][0][7] == "A"
    assert inserted["values"][0][12] == 90
    assert inserted["values"][0][14] == 10
    assert inserted["values"][0][15] == "2026-06-05 10:00:00"
    assert inserted["values"][0][16] is None
    assert inserted["values"][0][17] is None


def test_replace_stuck_alert_deletes_and_inserts_only_when_over_threshold(monkeypatch) -> None:
    captured = _patch_conn(monkeypatch)

    alert = recon_rollup_db.replace_stuck_recon_alert(
        company_id="company-001",
        domain="ecom",
        plan_code="plan-001",
        plan_name_snapshot="计划 1",
        biz_date="2026-06-05",
        stuck_amount=50,
        stuck_count=2,
        stuck_days_n=5,
        threshold_amount=0,
    )

    assert alert is not None
    assert "DELETE FROM public.recon_alert" in captured["queries"][0][0]
    assert "INSERT INTO public.recon_alert" in captured["queries"][1][0]
    assert captured["committed"] is True
