from __future__ import annotations

import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_load_platform_order_lines_from_dataset_ref(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_order_lines"
        return {"company_id", "data_source_id", "dataset_id", "biz_date", "payload", "updated_at"}

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-001"
        assert query["dataset_id"] == "dataset-001"
        assert query["biz_date"] == "2026-05-06"
        return [{"payload": {"tid": "T1", "oid": "O1", "order_payment": "80.00"}}]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_order_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "platform_order_lines",
            "source_key": "source-001",
            "query": {"dataset_id": "dataset-001", "biz_date": "2026-05-06"},
        },
        "淘宝订单",
    )

    assert list(df["tid"]) == ["T1"]
    assert list(df["order_payment"]) == ["80.00"]


def test_load_platform_alipay_bill_lines_from_dataset_ref(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_alipay_bill_lines"
        return {
            "company_id",
            "data_source_id",
            "dataset_id",
            "shop_connection_id",
            "bill_type",
            "bill_date",
            "source_row_key",
            "payload",
            "updated_at",
        }

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-alipay-001"
        assert query["dataset_id"] == "dataset-alipay-001"
        assert query["resource_key"] == "alipay_bill:trade:shop-alipay-001"
        assert query["biz_date"] == "2026-05-06"
        return [
            {
                "source_row_key": "row-1",
                "bill_date": "2026-05-06",
                "payload": {"商户订单号": "M001", "收入金额（+元）": "12.30"},
            }
        ]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_alipay_bill_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "platform_alipay_bill_lines",
            "source_key": "source-alipay-001",
            "query": {
                "dataset_id": "dataset-alipay-001",
                "resource_key": "alipay_bill:trade:shop-alipay-001",
                "biz_date": "2026-05-06",
            },
        },
        "支付宝交易账单",
    )

    assert list(df["商户订单号"]) == ["M001"]
    assert list(df["收入金额（+元）"]) == ["12.30"]
    assert "source_row_key" not in df.columns
    assert "bill_date" not in df.columns


def test_platform_alipay_bill_lines_rejects_conflicting_bill_type(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_alipay_bill_lines"
        return {
            "data_source_id",
            "shop_connection_id",
            "bill_type",
            "payload",
            "updated_at",
        }

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)

    with pytest.raises(dataset_loader.DatasetLoadError) as exc_info:
        dataset_loader.load_dataset_as_df(
            {
                "source_type": "platform_alipay_bill_lines",
                "source_key": "source-alipay-001",
                "query": {
                    "resource_key": "alipay_bill:trade:shop-alipay-001",
                    "bill_type": "signcustomer",
                },
            },
            "支付宝交易账单",
        )

    assert "resource_key" in str(exc_info.value)
    assert "bill_type" in str(exc_info.value)
    assert "不一致" in str(exc_info.value) or "conflict" in str(exc_info.value)


def test_platform_alipay_bill_lines_accepts_bill_date_alias(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_alipay_bill_lines"
        return {
            "company_id",
            "data_source_id",
            "dataset_id",
            "shop_connection_id",
            "bill_type",
            "bill_date",
            "payload",
            "updated_at",
        }

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-alipay-001"
        assert "biz_date" not in query
        assert query["bill_date"] == "2026-05-06"
        return [{"payload": {"商户订单号": "M003", "收入金额（+元）": "9.00"}}]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_alipay_bill_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "platform_alipay_bill_lines",
            "source_key": "source-alipay-001",
            "query": {"bill_date": "2026-05-06"},
        },
        "支付宝交易账单",
    )

    assert list(df["商户订单号"]) == ["M003"]
    assert list(df["收入金额（+元）"]) == ["9.00"]


def test_load_alipay_bill_lines_alias_from_dataset_ref(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_alipay_bill_lines"
        return {
            "company_id",
            "data_source_id",
            "dataset_id",
            "shop_connection_id",
            "bill_type",
            "bill_date",
            "payload",
            "updated_at",
        }

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-alipay-001"
        return [{"payload": {"商户订单号": "M002", "收入金额（+元）": "8.00"}}]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_alipay_bill_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "alipay_bill_lines",
            "source_key": "source-alipay-001",
            "query": {},
        },
        "支付宝交易账单",
    )

    assert list(df["商户订单号"]) == ["M002"]
    assert list(df["收入金额（+元）"]) == ["8.00"]


def test_load_alipay_bill_lines_alias_accepts_date_field_metadata(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_alipay_bill_lines"
        return {
            "company_id",
            "data_source_id",
            "dataset_id",
            "shop_connection_id",
            "bill_type",
            "bill_date",
            "payload",
            "updated_at",
        }

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-alipay-001"
        assert query["dataset_id"] == "dataset-alipay-001"
        assert query["resource_key"] == "alipay_bill:trade:shop-alipay-001"
        assert query["bill_date"] == "2026-05-06"
        assert query["date_field"] == "bill_date"
        return [{"payload": {"商户订单号": "M004", "收入金额（+元）": "10.00"}}]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_alipay_bill_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "alipay_bill_lines",
            "source_key": "source-alipay-001",
            "query": {
                "dataset_id": "dataset-alipay-001",
                "resource_key": "alipay_bill:trade:shop-alipay-001",
                "bill_date": "2026-05-06",
                "date_field": "bill_date",
            },
        },
        "支付宝交易账单",
    )

    assert list(df["商户订单号"]) == ["M004"]
    assert list(df["收入金额（+元）"]) == ["10.00"]
