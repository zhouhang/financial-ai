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


def test_browser_collection_records_loader_accepts_date_field_metadata(monkeypatch):
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {
            "data_source_id",
            "dataset_id",
            "resource_key",
            "biz_date",
            "payload",
            "captured_at",
        },
    )

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-001"
        assert query["dataset_id"] == "dataset-001"
        assert query["resource_key"] == "browser-collection-001@1"
        assert query["biz_date"] == "2026-05-25"
        assert query["date_field"] == "确认收货时间"
        return [
            {
                "payload": {
                    "订单号": "order-001",
                    "确认收货时间": "2026-05-25 15:52:39",
                    "订单实际金额（元）": "103",
                }
            },
            {
                "payload": {
                    "订单号": "order-002",
                    "确认收货时间": "2026-05-24 23:59:59",
                    "订单实际金额（元）": "88",
                }
            },
        ]

    monkeypatch.setattr(dataset_loader, "_load_browser_collection_record_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "source-001",
            "query": {
                "dataset_id": "dataset-001",
                "resource_key": "browser-collection-001@1",
                "biz_date": "2026-05-25",
                "date_field": "确认收货时间",
                "filters": {"确认收货时间": "2026-05-25"},
            },
        },
        "收支账单",
    )

    # date_field 的 filter 值是纯日期(date-only),现在这类业务日二次过滤被跳过(数据范围由
    # biz_date 列在 _load_browser_collection_record_rows 层收口),所以两条都保留 ——
    # payload 日期字段不再做第二道过滤。
    assert list(df["订单号"]) == ["order-001", "order-002"]
    assert list(df["订单实际金额（元）"]) == ["103", "88"]


def test_date_only_filter_does_not_empty_nonempty_collection(monkeypatch):
    """雷系京东账单回归:采到的行(biz_date 列已收口)其 payload 日期字段都 != 业务日时,
    旧逻辑会在内存里按 date-only 过滤成 0 并报"过滤后为空"。现在 date-only 过滤被跳过,
    采到的行保留、对账照常跑;非日期 filter 仍正常生效(见下一个用例)。"""
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {"data_source_id", "dataset_id", "biz_date", "payload", "captured_at"},
    )
    monkeypatch.setattr(
        dataset_loader,
        "_load_browser_collection_record_rows",
        lambda *, source_key, query: [
            {"payload": {"订单号": "o1", "费用发生时间": "2026-06-18 10:00:00"}},
            {"payload": {"订单号": "o2", "费用发生时间": "2026-06-17 09:00:00"}},
        ],
    )

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "source-001",
            "query": {
                "dataset_id": "dataset-001",
                "biz_date": "2026-06-19",
                "date_field": "费用发生时间",
                "filters": {"费用发生时间": "2026-06-19"},
            },
        },
        "京东账单",
    )

    assert list(df["订单号"]) == ["o1", "o2"]


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


def test_browser_collection_records_loader_accepts_successful_empty_collection(monkeypatch):
    """A browser sync job may validly succeed with zero rows. The loader should
    expose that as an empty dataframe with the published dataset schema instead
    of reporting that no collection has happened."""
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {
            "data_source_id",
            "dataset_id",
            "resource_key",
            "biz_date",
            "payload",
            "captured_at",
        },
    )
    monkeypatch.setattr(dataset_loader, "_load_browser_collection_record_rows", lambda **_kwargs: [])
    monkeypatch.setattr(
        dataset_loader,
        "_empty_browser_collection_schema_columns_for_success_job",
        lambda *, source_key, query: ["订单编号", "订单付款时间", "买家实付金额"],
        raising=False,
    )

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "browser_collection_records",
            "source_key": "source-001",
            "query": {
                "dataset_id": "dataset-001",
                "resource_key": "browser-collection-001@1",
                "biz_date": "2026-06-02",
                "filters": {"订单付款时间": "2026-06-02"},
            },
        },
        "店铺订单",
    )

    assert df.empty
    assert list(df.columns) == ["订单编号", "订单付款时间", "买家实付金额"]


def test_browser_collection_records_loader_still_rejects_missing_collection(monkeypatch):
    monkeypatch.setattr(
        dataset_loader,
        "_table_columns",
        lambda table_name: {
            "data_source_id",
            "dataset_id",
            "resource_key",
            "biz_date",
            "payload",
            "captured_at",
        },
    )
    monkeypatch.setattr(dataset_loader, "_load_browser_collection_record_rows", lambda **_kwargs: [])
    monkeypatch.setattr(
        dataset_loader,
        "_empty_browser_collection_schema_columns_for_success_job",
        lambda *, source_key, query: None,
    )

    with pytest.raises(dataset_loader.DatasetLoadError) as exc_info:
        dataset_loader.load_dataset_as_df(
            {
                "source_type": "browser_collection_records",
                "source_key": "source-001",
                "query": {
                    "dataset_id": "dataset-001",
                    "resource_key": "browser-collection-001@1",
                    "biz_date": "2026-06-02",
                },
            },
            "店铺订单",
        )

    assert "暂无浏览器采集记录" in str(exc_info.value)
