from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import db as auth_db


def test_upsert_platform_alipay_bill_lines_promotes_recon_fields(monkeypatch):
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

    summary = auth_db.upsert_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        external_shop_id="alipay-shop-001",
        bill_type="trade",
        bill_date="2026-05-06",
        rows=[
            {
                "source_file_name": "bill.csv",
                "source_row_number": "12",
                "source_row_key": "row-key-1",
                "alipay_trade_no": "A001",
                "merchant_order_no": "M001",
                "business_order_no": "B001",
                "raw": {
                    "金额": "12.30",
                    "收入": "12.30",
                    "支出": "",
                    "入账时间": "2026-05-06 12:30:00",
                },
            }
        ],
    )

    assert summary == {
        "input_count": 1,
        "upserted_count": 1,
        "inserted_count": 1,
        "updated_count": 0,
    }
    assert "INSERT INTO platform_alipay_bill_lines" in executed_sql[0]
    assert (
        "ON CONFLICT (company_id, shop_connection_id, bill_type, bill_date, source_row_key)"
        in executed_sql[0]
    )
    combined_params = [str(value) for value in params_seen[0]]
    assert "A001" in combined_params
    assert "M001" in combined_params
    assert "B001" in combined_params
    assert combined_params.count("12.30") >= 2


def test_upsert_platform_alipay_bill_lines_generates_distinct_fallback_row_keys(monkeypatch):
    params_seen: list[tuple] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            params_seen.append(tuple(params or ()))

        def fetchone(self):
            return {"inserted": True}

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

    summary = auth_db.upsert_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        external_shop_id="alipay-shop-001",
        bill_type="trade",
        bill_date="2026-05-06",
        rows=[
            {
                "source_file_name": "bill.csv",
                "source_row_number": 12,
                "source_row_key": " ",
                "raw": {"金额": "12.30", "支付宝交易号": "A100"},
            },
            {
                "source_file_name": "bill.csv",
                "source_row_number": 13,
                "raw": {"金额": "45.60", "支付宝交易号": "A101"},
            },
        ],
    )

    assert summary["upserted_count"] == 2
    assert len(params_seen) == 2
    source_row_keys = [params[9] for params in params_seen]
    assert all(source_row_keys)
    assert all(len(key) <= 128 for key in source_row_keys)
    assert source_row_keys[0] != source_row_keys[1]


def test_upsert_platform_alipay_bill_lines_promotes_raw_only_identifiers(monkeypatch):
    params_seen: list[tuple] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            params_seen.append(tuple(params or ()))

        def fetchone(self):
            return {"inserted": True}

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

    auth_db.upsert_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        external_shop_id="alipay-shop-001",
        bill_type="trade",
        bill_date="2026-05-06",
        rows=[
            {
                "source_file_name": "bill.csv",
                "source_row_number": 12,
                "source_row_key": "row-key-1",
                "raw": {
                    "支付宝交易号": "A100",
                    "商户订单号": "M100",
                    "业务订单号": "B100",
                    "金额": "12.30",
                },
            }
        ],
    )

    params = params_seen[0]
    assert params[10:13] == ("A100", "M100", "B100")
    payload = params[17].adapted
    assert payload["alipay_trade_no"] == "A100"
    assert payload["merchant_order_no"] == "M100"
    assert payload["business_order_no"] == "B100"


def test_list_platform_alipay_bill_lines_filters_resource_key(monkeypatch):
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
            return [{"payload": {"source_row_key": "row-key-1"}}]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    rows = auth_db.list_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        resource_key="alipay_bill:trade:shop-001",
        biz_date="2026-05-06",
        filters={"merchant_order_no": "M001"},
        limit=20,
        offset=5,
    )

    assert rows == [{"payload": {"source_row_key": "row-key-1"}}]
    assert "FROM platform_alipay_bill_lines" in str(captured["sql"])
    assert "bill_type = %s" in str(captured["sql"])
    assert "shop_connection_id = %s" in str(captured["sql"])
    assert "bill_date = %s" in str(captured["sql"])
    assert "merchant_order_no = %s" in str(captured["sql"])
    assert captured["params"] == (
        "company-001",
        "source-001",
        "dataset-001",
        "trade",
        "shop-001",
        "2026-05-06",
        "M001",
        5,
        20,
    )


def test_list_platform_alipay_bill_lines_conflicting_resource_shop_returns_empty(monkeypatch):
    captured = {"execute_count": 0}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["execute_count"] += 1

        def fetchall(self):
            return [{"payload": {"source_row_key": "unexpected"}}]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    rows = auth_db.list_platform_alipay_bill_lines(
        company_id="company-001",
        shop_connection_id="shop-b",
        resource_key="alipay_bill:trade:shop-a",
    )

    assert rows == []
    assert captured["execute_count"] == 0
