from __future__ import annotations

import sys
import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import recon_digest_detail_db


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
        if "COUNT(*)" in sql:
            return self.rows_by_marker.get("count")
        if "FROM public.recon_digest" in sql:
            return self.rows_by_marker.get("digest")
        if "FROM public.view_layout" in sql:
            return self.rows_by_marker.get("layout")
        return None

    def fetchall(self):
        sql = self.last_sql
        if "FROM public.recon_period_rollup" in sql:
            return self.rows_by_marker.get("rollups", [])
        if "FROM public.recon_alert" in sql:
            return self.rows_by_marker.get("alerts", [])
        if "FROM public.canonical_recon_line" in sql:
            return self.rows_by_marker.get("lines", [])
        return []


class _Conn:
    def __init__(self, rows_by_marker: dict[str, Any], captured: dict[str, Any]) -> None:
        self.rows_by_marker = rows_by_marker
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        self.captured.setdefault("cursor_calls", []).append({"args": args, "kwargs": kwargs})
        return _Cursor(self.rows_by_marker, self.captured)


def _patch_conn(monkeypatch, rows: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(recon_digest_detail_db, "get_conn", lambda: _Conn(rows, captured))
    return captured


def test_get_public_digest_detail_bundle_shapes_generic_data(monkeypatch) -> None:
    rows = {
        "digest": {
            "id": "digest-001",
            "company_id": "company-001",
            "period": "daily",
            "period_start": date(2026, 6, 5),
            "period_end": date(2026, 6, 5),
            "structured": {
                "domain": "ecom",
                "totals": {"settled_total": 100},
                "rollup_scope": {
                    "plan_codes": ["p1"],
                    "recon_types": ["fund"],
                },
            },
            "narrative": "今日说明",
            "status": "delivered",
        },
        "layout": {
            "layout_code": "ecom_boss_default_v1",
            "domain": "ecom",
            "view": "boss",
            "sections": [{"type": "narrative", "title": "今日摘要"}],
            "version": 1,
        },
        "rollups": [
            {
                "plan_code": "p1",
                "plan_name_snapshot": "Plan 1",
                "recon_type": "fund",
                "biz_date": date(2026, 6, 5),
                "as_of_ts": datetime(2026, 6, 6, 0, 0, 0),
                "receivable_amount_total": Decimal("150"),
                "refund_amount_total": Decimal("30"),
                "net_receivable_amount_total": Decimal("120"),
                "settled_amount_total": Decimal("100"),
                "normal_in_transit_amount_total": Decimal("10"),
                "stuck_amount_total": Decimal("10"),
                "net_deduction_total": Decimal("2"),
                "settled_order_count": 3,
                "matched_with_diff_count": 1,
                "source_only_count": 4,
                "target_only_count": 5,
                "payback_days_sum": Decimal("9"),
                "payback_days_count": 3,
            }
        ],
        "lines": [
            {
                "id": "line-1",
                "order_no": "O1",
                "recon_type": "fund",
                "receivable_amount": Decimal("50"),
                "refund_amount": Decimal("5"),
                "pay_time": datetime(2026, 6, 3, 12, 0, 0),
                "reason_code": "late_settlement",
                "is_true_diff": True,
                "processing_status": "pending",
                "fix_status": "open",
                "latest_feedback": "wait",
            }
        ],
        "alerts": [{"id": "alert-1", "alert_code": "stale", "status": "open"}],
        "count": {"total": 2},
    }
    captured = _patch_conn(monkeypatch, rows)

    bundle = recon_digest_detail_db.get_public_digest_detail_bundle(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="",
    )

    assert bundle is not None
    assert bundle["digest"]["id"] == "digest-001"
    assert bundle["digest"]["period_start"] == "2026-06-05"
    assert bundle["layout"]["view"] == "boss"
    assert bundle["domain"] == "ecom"

    row = bundle["data"]["rollups"][0]
    assert row["plan_code"] == "p1"
    assert row["biz_date"] == "2026-06-05"
    assert row["receivable_total"] == Decimal("150")
    assert row["refund_total"] == Decimal("30")
    assert row["net_receivable_total"] == Decimal("120")
    assert row["settled_total"] == Decimal("100")
    assert row["matched_exact_count"] == 2
    assert row["payback_days_avg"] == 3
    assert row["in_transit_ratio"] == 20 / 120
    assert row["refund_ratio"] == 30 / 150

    assert bundle["data"]["totals"]["settled_total"] == 100
    assert bundle["data"]["totals"]["matched_exact_count"] == 2
    assert bundle["data"]["sampling"] == {"loaded": 1, "total": 2, "truncated": True}

    line = bundle["data"]["canonical_lines"][0]
    assert line["id"] == "line-1"
    assert line["net_receivable"] == 45
    assert line["aging_days"] == 3
    assert line["reason_code"] == "late_settlement"
    assert line["processing_status"] == "pending"
    assert bundle["data"]["alerts"][0]["id"] == "alert-1"
    assert any("recon_period_rollup.plan_code = ANY" in sql for sql, _ in captured["queries"])
    assert any("l.plan_code = ANY" in sql for sql, _ in captured["queries"])
    assert any(
        params
        and list(params[-3:]) == [["p1"], ["fund"], 500]
        for sql, params in captured["queries"]
        if "ORDER BY l.plan_code" in sql
    )

    assert captured["cursor_calls"]
    assert all(
        call["kwargs"]["cursor_factory"] is recon_digest_detail_db.psycopg2.extras.RealDictCursor
        for call in captured["cursor_calls"]
    )


def test_bundle_resolves_drilldown_aging_threshold_from_structured(monkeypatch) -> None:
    rows = {
        "digest": {
            "id": "digest-001",
            "company_id": "company-001",
            "period": "daily",
            "period_start": "2026-06-05",
            "period_end": "2026-06-05",
            "structured": {"domain": "ecom", "stuck_days_n": 5},
            "narrative": "",
            "status": "delivered",
        },
        "layout": {
            "layout_code": "ecom_boss_default_v1",
            "domain": "ecom",
            "view": "boss",
            "version": 1,
            "sections": [
                {
                    "type": "alert_list",
                    "alert_code": "unsettled_amount_aged",
                    "drilldown": {
                        "source": "canonical",
                        "filter": "match_status=left_only & aging>N",
                        "columns": ["order_no", "net_receivable", "aging_days"],
                    },
                }
            ],
        },
        "rollups": [],
        "lines": [],
        "alerts": [],
        "count": {"total": 0},
    }
    _patch_conn(monkeypatch, rows)

    bundle = recon_digest_detail_db.get_public_digest_detail_bundle(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
        domain="",
    )

    assert bundle is not None
    drill = bundle["layout"]["sections"][0]["drilldown"]
    assert drill["filter"] == "match_status=left_only & aging>5"
    assert rows["layout"]["sections"][0]["drilldown"]["filter"] == (
        "match_status=left_only & aging>N"
    )


def test_public_digest_detail_hides_unavailable_net_deduction_metrics(monkeypatch) -> None:
    rows = {
        "digest": {
            "id": "digest-001",
            "company_id": "company-001",
            "structured": {
                "domain": "ecom",
                "totals": {
                    "settled_total": 90,
                    "net_deduction_total": 10,
                    "net_deduction_rate": 0.1,
                },
            },
        },
        "layout": {
            "layout_code": "layout",
            "domain": "ecom",
            "view": "finance",
            "sections": [
                {
                    "type": "metric_kpi",
                    "title": "资金概览",
                    "metric_label_map": {
                        "settled_total": "已到账",
                        "net_deduction_total": "综合扣减额",
                        "net_deduction_rate": "综合扣减率",
                    },
                    "metrics": [
                        "settled_total",
                        "net_deduction_total",
                        "net_deduction_rate",
                    ],
                },
                {
                    "type": "ranking_table",
                    "title": "扣减率排名",
                    "metric_label_map": {
                        "net_deduction_total": "综合扣减额",
                        "net_deduction_rate": "综合扣减率",
                    },
                    "columns": [
                        "net_deduction_total",
                        "net_deduction_rate",
                    ],
                    "sort": "net_deduction_rate desc",
                },
            ],
            "version": 1,
        },
        "rollups": [
            {
                "plan_code": "p1",
                "settled_amount_total": Decimal("90"),
                "net_deduction_total": Decimal("10"),
                "net_deduction_rate": Decimal("0.1"),
            }
        ],
        "lines": [],
        "alerts": [],
        "count": {"total": 0},
    }
    _patch_conn(monkeypatch, rows)

    bundle = recon_digest_detail_db.get_public_digest_detail_bundle(
        digest_id="digest-001",
        company_id="company-001",
        view="finance",
        biz_date="2026-06-05",
    )

    assert bundle is not None
    assert "net_deduction_total" not in bundle["data"]["totals"]
    assert "net_deduction_rate" not in bundle["data"]["totals"]
    assert "net_deduction_total" not in bundle["data"]["rollups"][0]
    assert "net_deduction_rate" not in bundle["data"]["rollups"][0]
    assert "net_deduction_total" not in bundle["digest"]["structured"]["totals"]
    assert "net_deduction_rate" not in bundle["digest"]["structured"]["totals"]

    sections = bundle["layout"]["sections"]
    assert sections == [
        {
            "type": "metric_kpi",
            "title": "资金概览",
            "metric_label_map": {"settled_total": "已到账"},
            "metrics": ["settled_total"],
        }
    ]
    assert "综合扣减" not in json.dumps(bundle["layout"], ensure_ascii=False)


def test_public_digest_totals_use_delivered_snapshot_when_rollup_changes(monkeypatch) -> None:
    rows = {
        "digest": {
            "id": "digest-001",
            "company_id": "company-001",
            "period": "daily",
            "period_start": "2026-06-05",
            "period_end": "2026-06-05",
            "structured": {
                "domain": "ecom",
                "totals": {
                    "receivable_total": 150,
                    "refund_total": 30,
                    "net_receivable_total": 120,
                    "settled_total": 100,
                    "normal_in_transit_amount": 10,
                    "stuck_amount": 10,
                    "net_deduction_total": 2,
                    "refund_ratio": 0.2,
                    "in_transit_ratio": 20 / 120,
                },
                "rollup_scope": {"plan_codes": ["p1"], "recon_types": ["fund"]},
            },
            "narrative": "",
            "status": "delivered",
        },
        "layout": {
            "layout_code": "layout",
            "domain": "ecom",
            "view": "boss",
            "sections": [],
            "version": 1,
        },
        "rollups": [
            {
                "plan_code": "p1",
                "plan_name_snapshot": "Plan 1",
                "recon_type": "fund",
                "biz_date": date(2026, 6, 5),
                "receivable_amount_total": Decimal("150"),
                "refund_amount_total": Decimal("0"),
                "net_receivable_amount_total": Decimal("150"),
                "settled_amount_total": Decimal("100"),
                "normal_in_transit_amount_total": Decimal("0"),
                "stuck_amount_total": Decimal("0"),
                "net_deduction_total": Decimal("2"),
                "settled_order_count": 3,
                "matched_with_diff_count": 1,
            }
        ],
        "lines": [],
        "alerts": [],
        "count": {"total": 0},
    }
    _patch_conn(monkeypatch, rows)

    bundle = recon_digest_detail_db.get_public_digest_detail_bundle(
        digest_id="digest-001",
        company_id="company-001",
        view="boss",
        biz_date="2026-06-05",
    )

    assert bundle is not None
    assert bundle["data"]["totals"]["refund_total"] == 30
    assert bundle["data"]["totals"]["normal_in_transit_amount"] == 10
    assert bundle["data"]["totals"]["stuck_amount"] == 10
    assert bundle["data"]["totals"]["net_receivable_total"] == 120
    assert bundle["data"]["rollups"][0]["refund_total"] == 0


def test_list_public_digest_diff_rows_uses_shared_join_sql_and_filters_recon_type(
    monkeypatch,
) -> None:
    rows = {
        "lines": [
            {
                "id": "line-1",
                "plan_code": "p1",
                "recon_type": "fund",
                "receivable_amount": Decimal("10"),
                "refund_amount": Decimal("2"),
                "reason_code": "amount_diff",
                "is_true_diff": False,
                "processing_status": "done",
                "fix_status": "fixed",
                "latest_feedback": "ok",
            }
        ]
    }
    captured = _patch_conn(monkeypatch, rows)

    result = recon_digest_detail_db.list_public_digest_diff_rows(
        company_id="company-001",
        domain="ecom",
        biz_date="2026-06-05",
        recon_type="fund",
        plan_codes=["p1"],
        recon_types=["fund", "order"],
    )

    assert result[0]["net_receivable"] == 8
    assert result[0]["reason_code"] == "amount_diff"
    assert result[0]["processing_status"] == "done"
    sql, params = captured["queries"][0]
    assert sql.startswith(recon_digest_detail_db._DIFF_ROWS_SQL)
    assert "LEFT JOIN public.recon_attribution" in sql
    assert "LEFT JOIN public.execution_run_exceptions" in sql
    assert "AND l.plan_code = ANY(%s)" in sql
    assert "AND l.recon_type = ANY(%s)" in sql
    assert "LIMIT" not in sql
    assert params == ("company-001", "2026-06-05", "ecom", ["p1"], ["fund"])


def test_public_digest_detail_sanitizes_non_finite_numbers(monkeypatch) -> None:
    rows = {
        "digest": {
            "id": "digest-001",
            "company_id": "company-001",
            "period": "daily",
            "period_start": "2026-06-05",
            "period_end": "2026-06-05",
            "structured": {"domain": "ecom"},
            "narrative": "",
            "status": "ready",
        },
        "layout": {
            "layout_code": "layout",
            "domain": "ecom",
            "view": "finance",
            "sections": [],
            "version": 1,
        },
        "rollups": [
            {
                "plan_code": "p1",
                "settled_amount_total": Decimal("NaN"),
                "net_deduction_total": Decimal("10"),
            }
        ],
        "lines": [
            {
                "id": "line-1",
                "recon_type": "fund",
                "receivable_amount": Decimal("10"),
                "refund_amount": Decimal("NaN"),
                "settled_amount": Decimal("Infinity"),
            }
        ],
        "alerts": [],
        "count": {"total": 1},
    }
    _patch_conn(monkeypatch, rows)

    bundle = recon_digest_detail_db.get_public_digest_detail_bundle(
        digest_id="digest-001",
        company_id="company-001",
        view="finance",
        biz_date="2026-06-05",
    )
    export_rows = recon_digest_detail_db.list_public_digest_diff_rows(
        company_id="company-001",
        domain="ecom",
        biz_date="2026-06-05",
    )

    assert bundle is not None
    line = bundle["data"]["canonical_lines"][0]
    assert line["refund_amount"] is None
    assert line["settled_amount"] is None
    assert line["net_receivable"] == 10
    assert bundle["data"]["rollups"][0]["settled_total"] is None
    assert bundle["data"]["totals"]["settled_total"] == 0
    assert not _contains_non_finite(bundle)

    assert export_rows[0]["refund_amount"] is None
    assert export_rows[0]["settled_amount"] is None
    assert not _contains_non_finite(export_rows)


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_non_finite(item) for item in value)
    return False


def test_list_public_digest_diff_rows_rejects_recon_type_outside_scope(monkeypatch) -> None:
    captured = _patch_conn(monkeypatch, {"lines": []})

    result = recon_digest_detail_db.list_public_digest_diff_rows(
        company_id="company-001",
        domain="ecom",
        biz_date="2026-06-05",
        recon_type="order",
        recon_types=["fund"],
    )

    assert result == []
    assert captured == {}


def test_repository_returns_none_or_empty_for_invalid_inputs(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        recon_digest_detail_db,
        "get_conn",
        lambda: (_ for _ in ()).throw(AssertionError("database should not be opened")),
    )

    assert (
        recon_digest_detail_db.get_public_digest_detail_bundle(
            digest_id="",
            company_id="company-001",
            view="boss",
            biz_date="2026-06-05",
        )
        is None
    )
    assert (
        recon_digest_detail_db.get_public_digest_detail_bundle(
            digest_id="digest-001",
            company_id="company-001",
            view="unknown",
            biz_date="2026-06-05",
        )
        is None
    )
    assert recon_digest_detail_db.list_public_digest_diff_rows(
        company_id="",
        domain="ecom",
        biz_date="2026-06-05",
    ) == []
    assert captured == {}


def test_repository_returns_none_for_missing_digest_layout_or_domain(monkeypatch) -> None:
    rows = {
        "digest": None,
        "layout": {
            "layout_code": "layout",
            "domain": "ecom",
            "view": "boss",
            "sections": [],
            "version": 1,
        },
        "rollups": [],
        "lines": [],
        "alerts": [],
        "count": {"total": 0},
    }
    _patch_conn(monkeypatch, rows)
    assert (
        recon_digest_detail_db.get_public_digest_detail_bundle(
            digest_id="missing",
            company_id="company-001",
            view="boss",
            biz_date="2026-06-05",
        )
        is None
    )

    rows["digest"] = {"id": "digest-001", "company_id": "company-001", "structured": {}}
    rows["layout"] = None
    assert (
        recon_digest_detail_db.get_public_digest_detail_bundle(
            digest_id="digest-001",
            company_id="company-001",
            view="boss",
            biz_date="2026-06-05",
        )
        is None
    )

    rows["digest"] = {"id": "digest-001", "company_id": "company-001", "structured": {}}
    assert (
        recon_digest_detail_db.get_public_digest_detail_bundle(
            digest_id="digest-001",
            company_id="company-001",
            view="boss",
            biz_date="2026-06-05",
            domain="",
        )
        is None
    )
