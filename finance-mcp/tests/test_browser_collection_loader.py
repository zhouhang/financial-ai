from __future__ import annotations

import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_load_browser_collection_records_from_dataset_ref(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "browser_collection_records"
        return {
            "company_id",
            "data_source_id",
            "dataset_id",
            "resource_key",
            "biz_date",
            "item_key",
            "payload",
            "record_status",
            "captured_at",
        }

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "00000000-0000-0000-0000-000000000002"
        assert query["dataset_id"] == "00000000-0000-0000-0000-000000000003"
        assert query["resource_key"] == "qianniu:bill:shop-1"
        assert query["biz_date"] == "2026-05-16"
        return [
            {
                "payload": {
                    "bill_no": "B001",
                    "amount": "12.30",
                    "biz_date": "2026-05-16",
                }
            }
        ]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_browser_collection_record_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "00000000-0000-0000-0000-000000000002",
            "query": {
                "dataset_id": "00000000-0000-0000-0000-000000000003",
                "resource_key": "qianniu:bill:shop-1",
                "biz_date": "2026-05-16",
            },
        },
        "千牛资金日账单",
    )

    assert list(df["bill_no"]) == ["B001"]
    assert list(df["amount"]) == ["12.30"]


def test_browser_collection_records_loader_trims_whitespace_from_values(monkeypatch):
    """千牛/淘宝导出在每个值后面带尾部制表符（\\t）。加载时必须 trim，否则匹配键、
    金额、时间都对不上另一侧（实测不 trim 时 订单号匹配 0 条）。"""
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {"data_source_id", "dataset_id", "biz_date", "payload"},
    )
    monkeypatch.setattr(
        dataset_loader,
        "_load_browser_collection_record_rows",
        lambda *, source_key, query: [
            {
                "payload": {
                    "订单号": "3303691179052000067\t",
                    "订单实际金额（元）": "103\t",
                    "确认收货时间": "2026-05-25 15:52:39\t",
                }
            }
        ],
    )

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "source-001",
            "query": {"dataset_id": "dataset-001", "biz_date": "2026-05-25"},
        },
        "收支账单",
    )

    assert list(df["订单号"]) == ["3303691179052000067"]
    assert list(df["订单实际金额（元）"]) == ["103"]
    assert list(df["确认收货时间"]) == ["2026-05-25 15:52:39"]


def test_browser_collection_records_loader_rejects_unknown_query_keys(monkeypatch):
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {"data_source_id", "dataset_id", "biz_date", "payload"},
    )

    with pytest.raises(dataset_loader.DatasetLoadError) as exc_info:
        dataset_loader.load_dataset_as_df(
            {
                "source_type": "browser_collection_records",
                "source_key": "source-001",
                "query": {"dataset_id": "dataset-001", "unknown_option": True},
            },
            "千牛资金日账单",
        )

    assert "不支持字段" in str(exc_info.value)
    assert "unknown_option" in str(exc_info.value)


def test_load_browser_collection_records_applies_payload_filters(monkeypatch):
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {
            "company_id",
            "data_source_id",
            "dataset_id",
            "biz_date",
            "payload",
            "captured_at",
        },
    )
    monkeypatch.setattr(
        dataset_loader,
        "_load_browser_collection_record_rows",
        lambda *, source_key, query: [
            {"payload": {"bill_no": "B001", "amount": "12.30", "status": "settled"}},
            {"payload": {"bill_no": "B002", "amount": "45.60", "status": "pending"}},
        ],
    )

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "source-001",
            "query": {"filters": {"status": "settled"}},
        },
        "千牛资金日账单",
    )

    assert list(df["bill_no"]) == ["B001"]
