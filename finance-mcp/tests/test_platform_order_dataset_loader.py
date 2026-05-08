from __future__ import annotations

import sys
from pathlib import Path

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
            "merchant_order_no",
            "amount",
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
                "payload": {"source_row_key": "row-1", "merchant_order_no": "M001", "amount": "12.30"}
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

    assert list(df["merchant_order_no"]) == ["M001"]
    assert list(df["amount"]) == ["12.30"]


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
        return [{"payload": {"merchant_order_no": "M002", "amount": "8.00"}}]

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

    assert list(df["merchant_order_no"]) == ["M002"]
    assert list(df["amount"]) == ["8.00"]
