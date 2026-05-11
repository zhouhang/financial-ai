from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import db as auth_db


def test_upsert_platform_alipay_bill_lines_empty_rows_returns_zero_counts(monkeypatch):
    def raise_if_called():
        raise AssertionError("get_conn should not be called for empty rows")

    monkeypatch.setattr(auth_db, "get_conn", raise_if_called)

    summary = auth_db.upsert_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        external_shop_id="alipay-shop-001",
        bill_type="trade",
        bill_date="2026-05-06",
        rows=[],
    )

    assert summary == {
        "input_count": 0,
        "upserted_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "deleted_stale_count": 0,
    }


def test_upsert_platform_alipay_bill_lines_replace_scope_prunes_when_empty(monkeypatch):
    captured: dict[str, object] = {}

    class FakeCursor:
        rowcount = 3

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = tuple(params or ())

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
        bill_type="signcustomer",
        bill_date="2026-05-06",
        rows=[],
        replace_bill_scope=True,
    )

    assert summary == {
        "input_count": 0,
        "upserted_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "deleted_stale_count": 3,
    }
    assert "DELETE FROM platform_alipay_bill_lines" in str(captured["sql"])
    assert captured["params"] == (
        "company-001",
        "shop-001",
        "signcustomer",
        "2026-05-06",
        "dataset-001",
    )


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
        replace_bill_scope=True,
    )

    assert summary == {
        "input_count": 1,
        "upserted_count": 1,
        "inserted_count": 1,
        "updated_count": 0,
        "deleted_stale_count": 0,
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


def test_upsert_platform_alipay_bill_lines_promotes_signed_fund_amount_columns(monkeypatch):
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
        bill_type="signcustomer",
        bill_date="2026-05-06",
        rows=[
            {
                "source_file_name": "bill.csv",
                "source_row_number": "12",
                "source_row_key": "row-key-1",
                "raw": {
                    "账务流水号": "A001",
                    "业务流水号": "B001",
                    "商户订单号": "M001",
                    "收入金额（+元）": "88.00",
                    "支出金额（-元）": "-0.30",
                    "发生时间": "2026-05-06 12:30:00",
                },
            }
        ],
    )

    params = params_seen[0]
    assert params[10:17] == (
        "A001",
        "M001",
        "B001",
        None,
        "88.00",
        "-0.30",
        "2026-05-06 12:30:00",
    )
    payload = params[17].adapted
    assert payload["income_amount"] == "88.00"
    assert payload["expense_amount"] == "-0.30"
    assert payload["trade_time"] == "2026-05-06 12:30:00"


def test_upsert_platform_alipay_bill_lines_prunes_stale_rows_for_same_bill_file(monkeypatch):
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
        bill_type="signcustomer",
        bill_date="2026-05-06",
        rows=[
            {
                "source_file_name": "bill.csv",
                "source_row_number": 12,
                "source_row_key": "row-key-1",
                "raw": {"账务流水号": "A100", "收入金额（+元）": "12.30"},
            }
        ],
        replace_bill_scope=True,
    )

    assert summary["deleted_stale_count"] == 0
    assert "DELETE FROM platform_alipay_bill_lines" in executed_sql[-1]
    assert "source_row_key <> ALL(%s)" in executed_sql[-1]
    assert params_seen[-1] == (
        "company-001",
        "shop-001",
        "signcustomer",
        "2026-05-06",
        "dataset-001",
        ["row-key-1"],
    )


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
        replace_bill_scope=True,
    )

    assert summary["upserted_count"] == 2
    assert len(params_seen) == 3
    source_row_keys = [params[9] for params in params_seen[:2]]
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


def test_list_platform_alipay_bill_lines_limit_none_keeps_offset_without_limit(monkeypatch):
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
            return []

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
        offset=7,
        limit=None,
    )

    assert rows == []
    assert "OFFSET %s" in str(captured["sql"])
    assert "LIMIT %s" not in str(captured["sql"])
    assert captured["params"] == ("company-001", "source-001", 7)


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


def test_get_platform_alipay_bill_line_stats_filters_dataset_shop_and_date(monkeypatch):
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
                "total_count": 3,
                "biz_date_count": 1,
                "first_seen_at": "2026-05-06T00:00:00",
                "latest_seen_at": "2026-05-06T12:00:00",
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn())

    result = auth_db.get_platform_alipay_bill_line_stats(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        biz_date="2026-05-06",
    )

    assert result["total_count"] == 3
    assert result["biz_date_count"] == 1
    assert "FROM platform_alipay_bill_lines" in str(captured["sql"])
    assert "data_source_id = %s" in str(captured["sql"])
    assert "dataset_id = %s" in str(captured["sql"])
    assert "shop_connection_id = %s" in str(captured["sql"])
    assert "bill_date = %s" in str(captured["sql"])
    assert "COUNT(DISTINCT bill_date)" in str(captured["sql"])
    assert captured["params"] == (
        "company-001",
        "source-001",
        "dataset-001",
        "shop-001",
        "2026-05-06",
    )
