from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import db as auth_db


def test_upsert_platform_order_lines_preserves_latest_payload(monkeypatch):
    executed_sql: list[str] = []
    params_seen: list[tuple] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            executed_sql.append(sql)
            params_seen.append(tuple(params or ()))

        def fetchone(self):
            return {"inserted": True}

        def fetchall(self):
            return []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    summary = auth_db.upsert_platform_order_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        platform_code="taobao",
        external_shop_id="tb-shop-001",
        rows=[
            {
                "biz_date": "2026-05-06",
                "tid": "T1",
                "oid": "O1",
                "trade_status": "TRADE_FINISHED",
                "order_status": "TRADE_FINISHED",
                "pay_time": "2026-05-06T12:30:00+08:00",
                "modified": "2026-05-06T12:35:00+08:00",
                "payment": "100.00",
                "order_payment": "80.00",
                "payload": {"tid": "T1", "oid": "O1"},
            }
        ],
    )

    assert summary["input_count"] == 1
    assert summary["upserted_count"] == 1
    assert "INSERT INTO platform_order_lines" in executed_sql[0]
    assert "ON CONFLICT (company_id, shop_connection_id, tid, oid)" in executed_sql[0]
    assert "EXCLUDED.source_modified_at >= platform_order_lines.source_modified_at" in executed_sql[0]
    assert any("T1" in str(params) and "O1" in str(params) for params in params_seen)


def test_upsert_platform_order_lines_preserves_numeric_zero_values(monkeypatch):
    params_seen: list[tuple] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            params_seen.append(tuple(params or ()))

        def fetchone(self):
            return {"inserted": False}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    summary = auth_db.upsert_platform_order_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        platform_code="taobao",
        external_shop_id="tb-shop-001",
        rows=[
            {
                "biz_date": "2026-05-06",
                "tid": "T0",
                "oid": "O0",
                "payment": 0,
                "order_payment": 0,
                "total_fee": 0,
                "order_total_fee": 0,
                "discount_fee": 0,
                "order_discount_fee": 0,
                "post_fee": 0,
                "commission_fee": 0,
                "quantity": 0,
            }
        ],
    )

    assert summary["updated_count"] == 1
    combined = [str(value) for value in params_seen[0]]
    assert combined.count("0") >= 9


def test_upsert_platform_order_lines_skips_stale_conflict(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            return None

        def fetchone(self):
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    summary = auth_db.upsert_platform_order_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        platform_code="taobao",
        external_shop_id="tb-shop-001",
        rows=[
            {
                "biz_date": "2026-05-06",
                "tid": "T1",
                "oid": "O1",
                "modified": "2026-05-06T10:00:00+08:00",
            }
        ],
    )

    assert summary["upserted_count"] == 0
    assert summary["inserted_count"] == 0
    assert summary["updated_count"] == 0


def test_list_platform_order_lines_filters_by_dataset_and_biz_date(monkeypatch):
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = tuple(params or ())

        def fetchall(self):
            return [
                {
                    "tid": "T1",
                    "oid": "O1",
                    "payload": {"tid": "T1", "oid": "O1"},
                    "updated_at": datetime(2026, 5, 6, tzinfo=timezone.utc),
                }
            ]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    rows = auth_db.list_platform_order_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        biz_date="2026-05-06",
        limit=20,
    )

    assert rows[0]["payload"]["tid"] == "T1"
    assert "FROM platform_order_lines" in str(captured["sql"])
    assert "dataset_id = %s" in str(captured["sql"])
    assert "biz_date = %s" in str(captured["sql"])
    assert "dataset-001" in captured["params"]
    assert "2026-05-06" in captured["params"]


def test_get_platform_app_by_id_filters_company_and_opens_secret(monkeypatch):
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = tuple(params or ())

        def fetchone(self):
            return {
                "id": "app-001",
                "company_id": "company-001",
                "platform_code": "taobao",
                "app_name": "淘宝应用",
                "app_key": "app-key",
                "app_secret": "sealed-secret",
                "app_type": "isv",
                "auth_base_url": "",
                "token_url": "",
                "refresh_url": "",
                "scopes_config": [],
                "extra": {"redirect_uri": "https://example.com/callback"},
                "status": "active",
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(auth_db, "open_secret", lambda value: f"opened:{value}")

    app = auth_db.get_platform_app_by_id(
        platform_app_id="app-001",
        company_id="company-001",
        include_secrets=True,
    )

    assert app["app_secret"] == "opened:sealed-secret"
    assert "FROM platform_apps" in str(captured["sql"])
    assert "id = %s" in str(captured["sql"])
    assert "company_id = %s" in str(captured["sql"])
    assert captured["params"] == ("app-001", "company-001")


def test_get_platform_order_line_stats_filters_dataset_and_shop(monkeypatch):
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = tuple(params or ())

        def fetchone(self):
            return {
                "total_count": 2,
                "biz_date_count": 1,
                "first_seen_at": datetime(2026, 5, 6, tzinfo=timezone.utc),
                "latest_seen_at": datetime(2026, 5, 7, tzinfo=timezone.utc),
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    stats = auth_db.get_platform_order_line_stats(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        biz_date="2026-05-06",
    )

    assert stats["total_count"] == 2
    assert "FROM platform_order_lines" in str(captured["sql"])
    assert "data_source_id = %s" in str(captured["sql"])
    assert "dataset_id = %s" in str(captured["sql"])
    assert "shop_connection_id = %s" in str(captured["sql"])
    assert "biz_date = %s" in str(captured["sql"])
    assert captured["params"] == (
        "company-001",
        "source-001",
        "dataset-001",
        "shop-001",
        "2026-05-06",
    )


def test_get_latest_source_dataset_checkpoint_reads_success_job(monkeypatch):
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = tuple(params or ())

        def fetchone(self):
            return {"checkpoint_after": {"last_window_end": "2026-05-06 12:00:00"}}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    checkpoint = auth_db.get_latest_source_dataset_checkpoint(
        company_id="company-001",
        data_source_id="source-001",
        resource_key="taobao_order_lines:shop-001",
    )

    assert checkpoint == {"last_window_end": "2026-05-06 12:00:00"}
    assert "FROM sync_jobs" in str(captured["sql"])
    assert "job_status = 'success'" in str(captured["sql"])
    assert "resource_key = %s" in str(captured["sql"])
    assert captured["params"] == ("company-001", "source-001", "taobao_order_lines:shop-001")
