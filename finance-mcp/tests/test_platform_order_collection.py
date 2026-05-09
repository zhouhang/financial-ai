from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources
from platforms.base import PlatformAppConfig, PlatformTokenBundle


def _platform_order_dataset(**overrides: Any) -> dict[str, Any]:
    dataset = {
        "id": "dataset-1",
        "data_source_id": "source-1",
        "dataset_code": "taobao_order_lines_shop_1",
        "resource_key": "taobao_order_lines:shop-1",
        "extract_config": {
            "storage": "platform_order_lines",
            "platform_code": "taobao",
            "shop_connection_id": "shop-1",
            "external_shop_id": "seller-1",
            "date_field": "biz_date",
        },
        "sync_strategy": {
            "mode": "full_then_incremental",
            "lookback_minutes": 10,
            "page_size": 100,
        },
        "schema_summary": {"storage": "platform_order_lines"},
        "meta": {"shop_name": "旗舰店"},
    }
    dataset.update(overrides)
    return dataset


def _alipay_bill_dataset(**overrides: Any) -> dict[str, Any]:
    dataset = {
        "id": "dataset-alipay-1",
        "data_source_id": "source-alipay-1",
        "dataset_name": "支付宝交易账单 - 福游网络",
        "dataset_code": "alipay_trade_bill_shop_1",
        "resource_key": "alipay_bill:trade:shop-alipay-1",
        "extract_config": {
            "storage": "platform_alipay_bill_lines",
            "platform_code": "alipay",
            "shop_connection_id": "shop-alipay-1",
            "bill_type": "trade",
            "date_field": "bill_date",
            "collection_date_field": "bill_date",
            "key_fields": ["bill_type", "bill_date", "source_row_key"],
        },
        "sync_strategy": {
            "mode": "daily_t_minus_1",
            "schedule_type": "cron",
            "schedule_expr": "30 10 * * *",
            "bill_type": "trade",
            "date_field": "bill_date",
        },
        "schema_summary": {
            "source": "alipay_bill_lines",
            "storage": "platform_alipay_bill_lines",
        },
        "meta": {"merchant_display_name": "福游网络"},
    }
    dataset.update(overrides)
    return dataset


def _alipay_platform_source(**overrides: Any) -> dict[str, Any]:
    source = {
        "id": "source-alipay-1",
        "company_id": "company-1",
        "source_kind": "platform_oauth",
        "provider_code": "alipay",
        "status": "active",
        "is_enabled": True,
    }
    source.update(overrides)
    return source


def _authorized_shop(monkeypatch, authorization: dict[str, Any]) -> None:
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app_by_id",
        lambda **kwargs: {
            "id": kwargs["platform_app_id"],
            "company_id": "00000000-0000-0000-0000-00000000dd01",
            "platform_code": "taobao",
            "app_name": "Tally Taobao",
            "app_key": "key-by-id",
            "app_secret": "secret-by-id",
            "app_type": "isv",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "real"},
            "status": "active",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should use app by id")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "taobao",
            "external_shop_id": "seller-1",
            "external_shop_name": "旗舰店",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "id": "auth-1",
            "platform_app_id": "app-by-id",
            "auth_status": "authorized",
            "scope_text": "trade",
            "raw_auth_payload": {"source": "test"},
            **authorization,
        },
    )


def test_dataset_uses_platform_order_lines_detects_storage_markers() -> None:
    assert data_sources._dataset_uses_platform_order_lines(_platform_order_dataset())
    assert data_sources._dataset_uses_platform_order_lines(
        {"schema_summary": {"source": "platform_order_lines"}}
    )
    assert not data_sources._dataset_uses_platform_order_lines(
        {"extract_config": {"storage": "dataset_collection_records"}}
    )


def test_dataset_uses_alipay_bill_records_detects_platform_and_resource_key() -> None:
    assert data_sources._dataset_uses_alipay_bill_records(_alipay_bill_dataset())
    assert not data_sources._dataset_uses_alipay_bill_records(
        _alipay_bill_dataset(resource_key="taobao_order_lines:shop-1")
    )
    assert not data_sources._dataset_uses_alipay_bill_records(
        _alipay_bill_dataset(extract_config={"platform_code": "taobao"})
    )


def test_resolve_alipay_bill_date_prefers_explicit_params() -> None:
    assert data_sources._resolve_alipay_bill_date({"biz_date": "2026-05-04"}) == "2026-05-04"
    assert data_sources._resolve_alipay_bill_date({"bill_date": "2026-05-05"}) == "2026-05-05"


def test_resolve_alipay_bill_date_defaults_to_t_minus_1_shanghai() -> None:
    resolved = data_sources._resolve_alipay_bill_date(
        {},
        now=datetime(2026, 5, 7, 1, 30, tzinfo=timezone.utc),
    )

    assert resolved == "2026-05-06"


def test_resolve_taobao_collection_window_uses_checkpoint_for_incremental() -> None:
    window = data_sources._resolve_taobao_collection_window(
        dataset_row=_platform_order_dataset(),
        params={},
        checkpoint_before={"last_window_end": "2026-05-06T12:00:00+08:00"},
        now=datetime(2026, 5, 6, 13, 0, tzinfo=timezone.utc),
    )

    assert window["mode"] == "incremental"
    assert window["window_start"] == "2026-05-06 11:50:00"
    assert window["window_end"] == "2026-05-06 21:00:00"


def test_resolve_taobao_collection_window_force_initial_uses_biz_date() -> None:
    window = data_sources._resolve_taobao_collection_window(
        dataset_row=_platform_order_dataset(),
        params={"biz_date": "2026-05-06", "force_mode": "initial"},
        checkpoint_before={"last_window_end": "2026-05-07T12:00:00+08:00"},
        now=datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
    )

    assert window == {
        "mode": "initial",
        "window_start": "2026-05-06 00:00:00",
        "window_end": "2026-05-06 23:59:59",
        "biz_date": "2026-05-06",
    }


@pytest.mark.anyio
async def test_refresh_semantic_profile_reads_platform_order_lines(monkeypatch) -> None:
    calls: dict[str, Any] = {}
    persisted: dict[str, Any] = {}
    dataset = _platform_order_dataset()

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "淘宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "taobao",
        },
    )

    def fake_list_platform_order_lines(**kwargs: Any) -> list[dict[str, Any]]:
        calls["list_platform_order_lines"] = kwargs
        return [
            {
                "payload": {
                    "tid": "T1001",
                    "oid": "O1001",
                    "biz_date": "2026-05-07",
                    "pay_time": "2026-05-07 10:02:03",
                    "payment": "88.00",
                    "order_payment": "88.00",
                    "title": "测试商品",
                }
            }
        ]

    monkeypatch.setattr(data_sources.auth_db, "list_platform_order_lines", fake_list_platform_order_lines)
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        persisted["meta"] = meta
        next_dataset = dict(dataset)
        next_dataset["meta"] = meta
        return next_dataset

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-1", "sample_limit": 20}
    )

    assert result["success"] is True
    assert result["sample_source"] == "platform_order_lines"
    assert calls["list_platform_order_lines"]["dataset_id"] == "dataset-1"
    assert calls["list_platform_order_lines"]["resource_key"] == "taobao_order_lines:shop-1"
    profile = persisted["meta"]["semantic_profile"]
    assert profile["generated_from"]["sample_source"] == "platform_order_lines"
    assert profile["field_label_map"]["tid"] == "主订单号"
    assert profile["field_label_map"]["order_payment"] == "子订单实付金额"
    assert profile["key_fields"] == ["tid", "oid"]


@pytest.mark.anyio
async def test_refresh_semantic_profile_expands_alipay_raw_bill_fields(monkeypatch) -> None:
    persisted: dict[str, Any] = {}
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "支付宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "source_row_key": "row-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-07",
                    "alipay_trade_no": "202605070001",
                    "merchant_order_no": "M1001",
                    "income_amount": "88.00",
                    "raw": {
                        "支付宝交易号": "202605070001",
                        "商户订单号": "M1001",
                        "收入": "88.00",
                        "入账时间": "2026-05-07 10:03:04",
                    },
                }
            }
        ],
    )
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        persisted["meta"] = meta
        next_dataset = dict(dataset)
        next_dataset["meta"] = meta
        return next_dataset

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-alipay-1", "sample_limit": 20}
    )

    assert result["success"] is True
    assert result["sample_source"] == "platform_alipay_bill_lines"
    profile = persisted["meta"]["semantic_profile"]
    assert profile["generated_from"]["sample_source"] == "platform_alipay_bill_lines"
    assert profile["business_name"] == "支付宝交易账单 - 福游网络"
    assert profile["semantic_generator"]["llm_enabled"] is False
    assert profile["field_label_map"]["alipay_trade_no"] == "支付宝交易号"
    assert profile["field_label_map"]["raw.支付宝交易号"] == "支付宝交易号"
    assert profile["field_label_map"]["raw.收入"] == "收入"
    raw_field = next(item for item in profile["fields"] if item["raw_name"] == "raw.收入")
    assert raw_field["field_source"] == "raw_bill"
    assert raw_field["source"] == "platform_preset"
    assert profile["key_fields"] == ["source_row_key"]


@pytest.mark.anyio
async def test_refresh_semantic_profile_names_alipay_fund_bill_without_llm(monkeypatch) -> None:
    persisted: dict[str, Any] = {}
    dataset = _alipay_bill_dataset(
        id="dataset-alipay-fund-1",
        dataset_name="支付宝资金账单 - 对对科技",
        dataset_code="alipay_fund_bill_shop_1",
        resource_key="alipay_bill:signcustomer:shop-alipay-1",
        extract_config={
            "storage": "platform_alipay_bill_lines",
            "platform_code": "alipay",
            "shop_connection_id": "shop-alipay-1",
            "bill_type": "signcustomer",
            "merchant_display_name": "对对科技",
            "date_field": "bill_date",
            "collection_date_field": "bill_date",
            "key_fields": ["bill_type", "bill_date", "source_row_key"],
        },
        schema_summary={
            "source": "alipay_bill_lines",
            "storage": "platform_alipay_bill_lines",
            "columns": [
                {"name": "账务流水号", "data_type": "text", "nullable": True},
                {"name": "商户订单号", "data_type": "text", "nullable": True},
                {"name": "收入金额（+元）", "data_type": "text", "nullable": True},
            ],
        },
    )

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "支付宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "list_platform_alipay_bill_lines", lambda **kwargs: [])
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fail_llm_config() -> dict[str, Any] | None:
        raise AssertionError("支付宝账单固定数据集不应读取 LLM 配置")

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        persisted["meta"] = meta
        next_dataset = dict(dataset)
        next_dataset["meta"] = meta
        return next_dataset

    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", fail_llm_config)
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-alipay-fund-1", "sample_limit": 20}
    )

    assert result["success"] is True
    profile = persisted["meta"]["semantic_profile"]
    assert profile["business_name"] == "支付宝资金账单 - 对对科技"
    assert profile["status"] == "generated_basic"
    assert profile["semantic_generator"]["llm_enabled"] is False
    assert profile["generated_from"]["sample_source"] == "none"
    assert profile["field_label_map"]["账务流水号"] == "账务流水号"


@pytest.mark.anyio
async def test_refresh_semantic_profile_preserves_alipay_presets_when_llm_enabled(
    monkeypatch,
) -> None:
    persisted: dict[str, Any] = {}
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "支付宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "source_row_key": "row-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-07",
                    "alipay_trade_no": "202605070001",
                    "income_amount": "88.00",
                    "raw": {
                        "支付宝交易号": "202605070001",
                        "收入": "88.00",
                    },
                }
            }
        ],
    )
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        persisted["meta"] = meta
        next_dataset = dict(dataset)
        next_dataset["meta"] = meta
        return next_dataset

    def fake_call_semantic_llm(**kwargs: Any) -> dict[str, Any]:
        return {
            "business_name": "LLM 支付宝账单",
            "business_description": "LLM generated",
            "key_fields": ["alipay_trade_no"],
            "fields": [
                {
                    "raw_name": "source_row_key",
                    "display_name": "LLM 行键",
                    "semantic_type": "text",
                    "business_role": "name",
                    "description": "wrong",
                    "confidence": 0.99,
                },
                {
                    "raw_name": "alipay_trade_no",
                    "display_name": "LLM 交易号",
                    "semantic_type": "text",
                    "business_role": "name",
                    "description": "wrong",
                    "confidence": 0.99,
                },
                {
                    "raw_name": "raw.收入",
                    "display_name": "LLM 收款",
                    "semantic_type": "text",
                    "business_role": "name",
                    "description": "wrong",
                    "confidence": 0.99,
                },
            ],
        }

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(
        data_sources,
        "_get_semantic_llm_config",
        lambda: {"provider": "test", "model": "semantic-test", "base_url": "http://example", "api_key": "key"},
    )
    monkeypatch.setattr(data_sources, "_call_semantic_llm", fake_call_semantic_llm)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-alipay-1", "sample_limit": 20}
    )

    assert result["success"] is True
    assert result["sample_source"] == "platform_alipay_bill_lines"
    profile = persisted["meta"]["semantic_profile"]
    assert profile["generated_from"]["sample_source"] == "platform_alipay_bill_lines"
    assert profile["field_label_map"]["alipay_trade_no"] == "支付宝交易号"
    assert profile["field_label_map"]["raw.收入"] == "收入"
    source_row_key = next(item for item in profile["fields"] if item["raw_name"] == "source_row_key")
    raw_income = next(item for item in profile["fields"] if item["raw_name"] == "raw.收入")
    assert source_row_key["source"] == "platform_preset"
    assert source_row_key["field_source"] == "system"
    assert raw_income["source"] == "platform_preset"
    assert raw_income["field_source"] == "raw_bill"
    assert profile["key_fields"] == ["source_row_key"]


@pytest.mark.anyio
async def test_refresh_semantic_profile_prefers_alipay_presets_over_cached_llm(
    monkeypatch,
) -> None:
    persisted: dict[str, Any] = {}
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")
    dataset["meta"] = {
        **dict(dataset.get("meta") or {}),
        "semantic_profile": {
            "version": 1,
            "status": "llm_generated",
            "business_name": "旧 LLM 支付宝账单",
            "business_description": "旧 LLM 描述",
            "key_fields": ["alipay_trade_no"],
            "field_label_map": {
                "source_row_key": "旧 LLM 行键",
                "alipay_trade_no": "旧 LLM 交易号",
                "raw.收入": "旧 LLM 收款",
            },
            "fields": [
                {
                    "raw_name": "source_row_key",
                    "display_name": "旧 LLM 行键",
                    "semantic_type": "text",
                    "business_role": "name",
                    "description": "旧 LLM 错误描述",
                    "confidence": 0.99,
                    "source": "llm_generated",
                    "confirmed_by_user": False,
                },
                {
                    "raw_name": "alipay_trade_no",
                    "display_name": "旧 LLM 交易号",
                    "semantic_type": "text",
                    "business_role": "name",
                    "description": "旧 LLM 错误描述",
                    "confidence": 0.99,
                    "source": "llm_generated",
                    "confirmed_by_user": False,
                },
                {
                    "raw_name": "raw.收入",
                    "display_name": "旧 LLM 收款",
                    "semantic_type": "text",
                    "business_role": "name",
                    "description": "旧 LLM 错误描述",
                    "confidence": 0.99,
                    "source": "llm_generated",
                    "confirmed_by_user": False,
                },
            ],
        },
    }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "支付宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "source_row_key": "row-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-07",
                    "alipay_trade_no": "202605070001",
                    "income_amount": "88.00",
                    "raw": {
                        "支付宝交易号": "202605070001",
                        "收入": "88.00",
                    },
                }
            }
        ],
    )
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        persisted["meta"] = meta
        next_dataset = dict(dataset)
        next_dataset["meta"] = meta
        return next_dataset

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-alipay-1", "sample_limit": 20}
    )

    assert result["success"] is True
    assert result["sample_source"] == "platform_alipay_bill_lines"
    profile = persisted["meta"]["semantic_profile"]
    assert profile["generated_from"]["sample_source"] == "platform_alipay_bill_lines"
    assert profile["field_label_map"]["alipay_trade_no"] == "支付宝交易号"
    assert profile["field_label_map"]["raw.收入"] == "收入"
    assert profile["key_fields"] == ["source_row_key"]
    alipay_trade_no = next(item for item in profile["fields"] if item["raw_name"] == "alipay_trade_no")
    raw_income = next(item for item in profile["fields"] if item["raw_name"] == "raw.收入")
    assert alipay_trade_no["source"] == "platform_preset"
    assert alipay_trade_no["field_source"] == "normalized"
    assert raw_income["source"] == "platform_preset"
    assert raw_income["field_source"] == "raw_bill"


@pytest.mark.anyio
async def test_refresh_semantic_profile_keeps_manual_alipay_field_over_platform_preset(
    monkeypatch,
) -> None:
    persisted: dict[str, Any] = {}
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")
    dataset["meta"] = {
        **dict(dataset.get("meta") or {}),
        "semantic_profile": {
            "version": 1,
            "status": "manual_updated",
            "business_name": "人工支付宝账单",
            "business_description": "人工描述",
            "key_fields": ["alipay_trade_no"],
            "field_label_map": {
                "raw.收入": "人工收入字段",
            },
            "fields": [
                {
                    "raw_name": "raw.收入",
                    "display_name": "人工收入字段",
                    "semantic_type": "amount",
                    "business_role": "manual_amount",
                    "description": "人工确认的收入字段",
                    "confidence": 1.0,
                    "source": "manual_confirmed",
                    "confirmed_by_user": True,
                    "field_source": "raw_bill",
                },
            ],
        },
    }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "支付宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "source_row_key": "row-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-07",
                    "alipay_trade_no": "202605070001",
                    "income_amount": "88.00",
                    "raw": {
                        "收入": "88.00",
                    },
                }
            }
        ],
    )
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        persisted["meta"] = meta
        next_dataset = dict(dataset)
        next_dataset["meta"] = meta
        return next_dataset

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset_meta", fake_update_dataset_meta)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-alipay-1", "sample_limit": 20}
    )

    assert result["success"] is True
    profile = persisted["meta"]["semantic_profile"]
    raw_income = next(item for item in profile["fields"] if item["raw_name"] == "raw.收入")
    assert profile["field_label_map"]["raw.收入"] == "人工收入字段"
    assert raw_income["source"] == "manual_confirmed"
    assert raw_income["confirmed_by_user"] is True
    assert raw_income["description"] == "人工确认的收入字段"
    assert profile["key_fields"] == ["alipay_trade_no"]


@pytest.mark.anyio
async def test_trigger_dataset_collection_for_company_does_not_require_auth_token(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _platform_order_dataset(),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_latest_source_dataset_checkpoint",
        lambda **kwargs: {"last_window_end": "2026-05-06T12:00:00+08:00"},
    )

    async def fake_trigger_sync(
        arguments: dict[str, Any],
        *,
        trusted_company_id: str = "",
    ) -> dict[str, Any]:
        calls["arguments"] = arguments
        calls["trusted_company_id"] = trusted_company_id
        return {"success": True, "job": {"id": "job-1"}}

    monkeypatch.setattr(data_sources, "_handle_data_source_trigger_sync", fake_trigger_sync)

    result = await data_sources.trigger_dataset_collection_for_company(
        company_id="company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        resource_key="taobao_order_lines:shop-1",
        idempotency_key="caller-key",
        params={"biz_date": "2026-05-06", "force_mode": "initial"},
    )

    assert result["success"] is True
    assert calls["trusted_company_id"] == "company-1"
    assert calls["arguments"]["idempotency_key"] == "caller-key"
    assert "auth_token" not in calls["arguments"]
    assert calls["arguments"]["params"]["checkpoint_before"] == {
        "last_window_end": "2026-05-06T12:00:00+08:00"
    }


@pytest.mark.anyio
async def test_execute_sync_job_routes_platform_order_rows_to_order_line_storage(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"upsert_dataset_collection_records": 0}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _platform_order_dataset(),
    )

    def fake_run_platform_order_collection(**kwargs: Any) -> dict[str, Any]:
        calls["platform_order_kwargs"] = kwargs
        return {
            "success": True,
            "healthy": True,
            "rows": [{"tid": "T1", "oid": "O1"}],
            "collection_summary": {
                "input_count": 1,
                "upserted_count": 1,
                "inserted_count": 1,
                "updated_count": 0,
                "dataset_id": "dataset-1",
                "dataset_code": "taobao_order_lines_shop_1",
                "biz_date": "2026-05-06",
                "record_count": 1,
            },
            "next_checkpoint": {"last_window_end": "2026-05-06 23:59:59"},
            "message": "平台订单采集成功",
        }

    monkeypatch.setattr(data_sources, "_run_platform_order_collection", fake_run_platform_order_collection)
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: calls.__setitem__("upsert_dataset_collection_records", 1),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-1",
        resource_key="taobao_order_lines:shop-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "taobao"},
        arguments={
            "params": {
                "dataset_id": "dataset-1",
                "dataset_code": "taobao_order_lines_shop_1",
                "collection_config": {"storage": "platform_order_lines"},
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={"last_window_end": "2026-05-05 23:59:59", "custom": "keep"},
        window_start="2026-05-06 00:00:00",
        window_end="2026-05-06 23:59:59",
    )

    assert result["success"] is True
    assert calls["upsert_dataset_collection_records"] == 0
    assert calls["platform_order_kwargs"]["checkpoint_before"] == {
        "last_window_end": "2026-05-05 23:59:59",
        "custom": "keep",
    }
    assert calls["platform_order_kwargs"]["params"]["platform_order_collection"]["mode"] == "incremental"
    assert result["collection_summary"]["upserted_count"] == 1
    assert calls["attempt"]["metrics"]["collection_upserted"] == 1


@pytest.mark.anyio
async def test_execute_sync_job_routes_alipay_bill_rows_to_platform_alipay_bill_line_storage(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"upsert_dataset_collection_records": 0}
    dataset = _alipay_bill_dataset()

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )

    def fake_run_alipay_bill_download_import(**kwargs: Any) -> dict[str, Any]:
        calls["alipay_kwargs"] = kwargs
        return {
            "success": True,
            "healthy": True,
            "rows": [
                {
                    "bill_type": "trade",
                    "bill_date": "2026-05-06",
                    "source_row_key": "row-1",
                    "amount": "12.30",
                }
            ],
            "original_files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
            "collection_summary": {
                "storage": "platform_alipay_bill_lines",
                "platform_code": "alipay",
                "bill_type": "trade",
                "bill_date": "2026-05-06",
                "input_count": 1,
                "upserted_count": 1,
                "inserted_count": 1,
                "updated_count": 0,
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_1",
                "biz_date": "2026-05-06",
                "record_count": 1,
                "original_files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
            },
            "message": "支付宝账单采集成功",
        }

    monkeypatch.setattr(
        data_sources,
        "_run_alipay_bill_download_import",
        fake_run_alipay_bill_download_import,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: calls.__setitem__("upsert_dataset_collection_records", 1),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_semantic_sample_rows",
        lambda **kwargs: (
            [
                {
                    "source_row_key": "row-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-06",
                    "alipay_trade_no": "A-1",
                    "raw.支付宝交易号": "A-1",
                    "raw.收入": "12.30",
                }
            ],
            "platform_alipay_bill_lines",
        ),
    )
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)
    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        calls["semantic_profile"] = {"dataset_id": dataset_id, "meta": meta}
        return {**dataset, "meta": meta}

    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_dataset_meta",
        fake_update_dataset_meta,
    )

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "params": {
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_1",
                "biz_date": "2026-05-06",
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert calls["upsert_dataset_collection_records"] == 0
    assert calls["alipay_kwargs"]["params"]["bill_date"] == "2026-05-06"
    assert result["collection_summary"]["storage"] == "platform_alipay_bill_lines"
    assert calls["attempt"]["metrics"]["collection_upserted"] == 1
    assert calls["event"]["event_payload"]["original_files"] == [
        {"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}
    ]
    profile = calls["semantic_profile"]["meta"]["semantic_profile"]
    assert profile["status"] == "generated_with_samples"
    assert profile["generated_from"]["sample_source"] == "platform_alipay_bill_lines"
    assert profile["field_label_map"]["raw.收入"] == "收入"


@pytest.mark.anyio
async def test_execute_sync_job_generates_alipay_semantic_from_bill_header_when_no_rows(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"upsert_dataset_collection_records": 0}
    dataset = _alipay_bill_dataset(
        schema_summary={
            "source": "alipay_bill_lines",
            "storage": "platform_alipay_bill_lines",
            "columns": [
                {"name": "旧字段", "data_type": "text", "nullable": True},
                {"name": "#支付宝账务汇总查询", "data_type": "text", "nullable": True},
            ],
        }
    )

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources,
        "_run_alipay_bill_download_import",
        lambda **kwargs: {
            "success": True,
            "healthy": True,
            "rows": [],
            "original_files": [{"file_name": "fund.csv", "path": "uploads/platform/alipay/x"}],
            "collection_summary": {
                "storage": "platform_alipay_bill_lines",
                "platform_code": "alipay",
                "bill_type": "signcustomer",
                "bill_date": "2026-05-08",
                "record_count": 0,
                "columns": [
                    {"name": "账务流水号", "data_type": "text", "nullable": True},
                    {"name": "商户订单号", "data_type": "text", "nullable": True},
                    {"name": "收入金额（+元）", "data_type": "text", "nullable": True},
                ],
                "original_files": [{"file_name": "fund.csv", "path": "uploads/platform/alipay/x"}],
            },
            "message": "支付宝账单采集成功",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: calls.__setitem__("upsert_dataset_collection_records", 1),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_load_dataset_semantic_sample_rows", lambda **kwargs: ([], "none"))
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    def fake_upsert_dataset(**kwargs: Any) -> dict[str, Any]:
        calls["dataset_schema"] = kwargs["schema_summary"]
        return {**dataset, "schema_summary": kwargs["schema_summary"]}

    def fake_update_dataset_meta(dataset_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        calls["semantic_profile"] = {"dataset_id": dataset_id, "meta": meta}
        return {**dataset, "schema_summary": calls["dataset_schema"], "meta": meta}

    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source_dataset",
        fake_upsert_dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_dataset_meta",
        fake_update_dataset_meta,
    )

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill:signcustomer:shop-alipay-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "params": {
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_fund_bill_shop_1",
                "biz_date": "2026-05-08",
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert calls["upsert_dataset_collection_records"] == 0
    assert [column["name"] for column in calls["dataset_schema"]["columns"]] == [
        "账务流水号",
        "商户订单号",
        "收入金额（+元）",
    ]
    assert "#支付宝账务汇总查询" not in [
        column["name"] for column in calls["dataset_schema"]["columns"]
    ]
    profile = calls["semantic_profile"]["meta"]["semantic_profile"]
    assert profile["status"] == "generated_basic"
    assert profile["generated_from"]["sample_source"] == "alipay_bill_header"
    assert profile["field_label_map"]["账务流水号"] == "账务流水号"
    assert profile["field_label_map"]["商户订单号"] == "商户订单号"


@pytest.mark.anyio
async def test_execute_sync_job_keeps_alipay_bill_driver_managed_when_summary_missing_storage(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"upsert_dataset_collection_records": 0}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(),
    )

    def fake_run_alipay_bill_download_import(**kwargs: Any) -> dict[str, Any]:
        calls["alipay_kwargs"] = kwargs
        return {
            "success": True,
            "healthy": True,
            "rows": [
                {
                    "bill_type": "trade",
                    "bill_date": "2026-05-06",
                    "source_row_key": "row-1",
                    "amount": "12.30",
                },
                {
                    "bill_type": "trade",
                    "bill_date": "2026-05-06",
                    "source_row_key": "row-2",
                    "amount": "45.60",
                },
            ],
            "collection_summary": {},
            "message": "支付宝账单采集成功",
        }

    def fail_generic_upsert(**kwargs: Any) -> None:
        calls["upsert_dataset_collection_records"] += 1
        raise AssertionError("Alipay bill download-import must not generic-upsert rows")

    monkeypatch.setattr(
        data_sources,
        "_run_alipay_bill_download_import",
        fake_run_alipay_bill_download_import,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        fail_generic_upsert,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "params": {
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_1",
                "biz_date": "2026-05-06",
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert calls["upsert_dataset_collection_records"] == 0
    assert result["collection_summary"]["storage"] == "platform_alipay_bill_lines"
    assert result["collection_summary"]["dataset_id"] == "dataset-alipay-1"
    assert result["collection_summary"]["dataset_code"] == "alipay_trade_bill_shop_1"
    assert result["collection_summary"]["biz_date"] == "2026-05-06"
    assert result["collection_summary"]["bill_date"] == "2026-05-06"
    assert result["collection_summary"]["record_count"] == 2
    assert calls["attempt"]["metrics"]["collection_upserted"] == 0
    assert calls["event"]["event_payload"]["collection_summary"]["storage"] == (
        "platform_alipay_bill_lines"
    )


@pytest.mark.anyio
async def test_execute_sync_job_failure_includes_collection_summary_diagnostics(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}
    collection_summary = {
        "storage": "platform_alipay_bill_lines",
        "dataset_id": "dataset-alipay-1",
        "dataset_code": "alipay_trade_bill_shop_1",
        "biz_date": "2026-05-06",
        "bill_date": "2026-05-06",
        "record_count": 0,
        "original_files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
    }

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(),
    )
    monkeypatch.setattr(
        data_sources,
        "_run_alipay_bill_download_import",
        lambda **kwargs: {
            "success": False,
            "healthy": False,
            "rows": [],
            "collection_summary": collection_summary,
            "message": "账单未就绪",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_sync_job_by_id",
        lambda sync_job_id: {"id": sync_job_id, "job_status": "failed"},
    )
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "params": {
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_1",
                "biz_date": "2026-05-06",
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is False
    assert result["collection_summary"]["storage"] == "platform_alipay_bill_lines"
    assert result["original_files"] == [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}]
    assert calls["event"]["event_payload"]["collection_summary"]["storage"] == (
        "platform_alipay_bill_lines"
    )
    assert calls["event"]["event_payload"]["original_files"] == [
        {"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}
    ]


@pytest.mark.anyio
async def test_run_platform_order_collection_reads_service_provider_app_by_id(
    monkeypatch,
) -> None:
    app_lookup: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app_by_id",
        lambda **kwargs: app_lookup.update(kwargs)
        or {
            "id": kwargs["platform_app_id"],
            "company_id": "00000000-0000-0000-0000-00000000dd01",
            "platform_code": "taobao",
            "app_name": "Tally Taobao",
            "app_key": "service-provider-key",
            "app_secret": "service-provider-secret",
            "app_type": "isv",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should use service provider app by id")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "customer-company-1",
            "platform_code": "taobao",
            "external_shop_id": "seller-1",
            "external_shop_name": "旗舰店",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "id": "auth-1",
            "platform_app_id": "service-app-1",
            "auth_status": "authorized",
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    class FakeConnector:
        def __init__(self, app_config: PlatformAppConfig):
            assert app_config.company_id == "00000000-0000-0000-0000-00000000dd01"
            assert app_config.app_key == "service-provider-key"

        def fetch_order_lines(self, **kwargs: Any) -> dict[str, Any]:
            return {"success": True, "records": [], "summary": {"upserted_count": 0}}

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector(app_config))

    result = data_sources._run_platform_order_collection(
        company_id="customer-company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        dataset_code="taobao_order_lines_shop_1",
        resource_key="taobao_order_lines:shop-1",
        collection_config={"platform_code": "taobao", "shop_connection_id": "shop-1"},
        params={
            "platform_order_collection": {
                "platform_code": "taobao",
                "shop_connection_id": "shop-1",
                "mode": "incremental",
            }
        },
    )

    assert result["success"] is True
    assert app_lookup["platform_app_id"] == "service-app-1"
    assert app_lookup["company_id"] == "customer-company-1"
    assert app_lookup["owner_company_id"] == "00000000-0000-0000-0000-00000000dd01"


@pytest.mark.anyio
async def test_run_platform_order_collection_uses_connector_and_upserts_lines(
    monkeypatch,
) -> None:
    connector_calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app_by_id",
        lambda **kwargs: {
            "id": kwargs["platform_app_id"],
            "company_id": kwargs["company_id"],
            "platform_code": "taobao",
            "app_name": "Taobao by id",
            "app_key": "key-by-id",
            "app_secret": "secret-by-id",
            "app_type": "system",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should use app by id")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "taobao",
            "external_shop_id": "seller-1",
            "external_shop_name": "旗舰店",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "platform_app_id": "app-by-id",
            "auth_status": "authorized",
            "scope_text": "trade",
            "raw_auth_payload": {"source": "test"},
        },
    )

    class FakeConnector:
        def __init__(self, app_config: Any):
            self.app_config = app_config

        def fetch_order_lines(self, **kwargs: Any) -> dict[str, Any]:
            connector_calls["fetch_order_lines"] = kwargs
            return {
                "success": True,
                "healthy": True,
                "rows": [{"tid": "T1", "oid": "O1", "biz_date": "2026-05-06"}],
            }

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector(app_config))
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_order_lines",
        lambda **kwargs: {"input_count": len(kwargs["rows"]), "upserted_count": len(kwargs["rows"])},
    )

    result = data_sources._run_platform_order_collection(
        company_id="company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        dataset_code="taobao_order_lines_shop_1",
        resource_key="taobao_order_lines:shop-1",
        collection_config=_platform_order_dataset()["extract_config"],
        params={
            "platform_order_collection": {
                "mode": "initial",
                "window_start": "2026-05-06 00:00:00",
                "window_end": "2026-05-06 23:59:59",
                "biz_date": "2026-05-06",
            }
        },
        checkpoint_before={"last_window_end": "2026-05-05 23:59:59", "custom": "keep"},
    )

    assert result["success"] is True
    assert result["collection_summary"]["upserted_count"] == 1
    assert result["next_checkpoint"]["custom"] == "keep"
    assert connector_calls["fetch_order_lines"]["company_id"] == "company-1"
    assert connector_calls["fetch_order_lines"]["data_source_id"] == "source-1"
    assert connector_calls["fetch_order_lines"]["mode"] == "initial"


def test_run_platform_order_collection_rejects_unauthorized_shop(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "taobao",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {"auth_status": "expired", "platform_app_id": "app-1"},
    )

    with pytest.raises(ValueError, match="店铺授权不存在"):
        data_sources._run_platform_order_collection(
            company_id="company-1",
            source_id="source-1",
            dataset_id="dataset-1",
            dataset_code="taobao_order_lines_shop_1",
            resource_key="taobao_order_lines:shop-1",
            collection_config=_platform_order_dataset()["extract_config"],
            params={"platform_order_collection": {"mode": "incremental"}},
        )


def test_run_platform_order_collection_refreshes_expiring_token_before_fetch(monkeypatch) -> None:
    calls: dict[str, Any] = {"updates": []}
    expiring_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    _authorized_shop(
        monkeypatch,
        {
            "access_token": "old-access",
            "refresh_token": "refresh-token",
            "token_expires_at": expiring_at,
        },
    )

    class FakeConnector:
        def __init__(self, app_config: PlatformAppConfig):
            self.app_config = app_config

        def refresh_token(self, *, refresh_token: str) -> PlatformTokenBundle:
            calls["refresh_token"] = refresh_token
            return PlatformTokenBundle(
                access_token="new-access",
                refresh_token="new-refresh",
                expires_in=7200,
                refresh_expires_in=30 * 24 * 3600,
                scope_text="trade,item",
                raw_payload={"source": "refresh"},
            )

        def fetch_order_lines(self, **kwargs: Any) -> dict[str, Any]:
            calls["access_token"] = kwargs["token_bundle"].access_token
            return {"success": True, "healthy": True, "rows": []}

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector(app_config))
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_shop_authorization_tokens",
        lambda **kwargs: calls["updates"].append(kwargs)
        or {
            "id": kwargs["authorization_id"],
            "access_token": kwargs["access_token"],
            "refresh_token": kwargs["refresh_token"],
            "scope_text": kwargs["scope_text"],
            "raw_auth_payload": kwargs["raw_auth_payload"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_order_lines",
        lambda **kwargs: {"input_count": 0, "upserted_count": 0},
    )

    result = data_sources._run_platform_order_collection(
        company_id="company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        dataset_code="taobao_order_lines_shop_1",
        resource_key="taobao_order_lines:shop-1",
        collection_config=_platform_order_dataset()["extract_config"],
        params={"platform_order_collection": {"mode": "incremental"}},
    )

    assert result["success"] is True
    assert calls["refresh_token"] == "refresh-token"
    assert calls["access_token"] == "new-access"
    assert calls["updates"][0]["authorization_id"] == "auth-1"
    assert calls["updates"][0]["access_token"] == "new-access"
    assert calls["updates"][0]["refresh_token"] == "new-refresh"
    assert calls["updates"][0]["token_expires_at"]
    assert calls["updates"][0]["refresh_expires_at"]


def test_run_platform_order_collection_marks_reauth_required_when_refresh_missing(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}
    expiring_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    _authorized_shop(
        monkeypatch,
        {
            "access_token": "old-access",
            "refresh_token": "",
            "token_expires_at": expiring_at,
        },
    )

    class FakeConnector:
        def refresh_token(self, **kwargs: Any) -> PlatformTokenBundle:
            raise AssertionError("missing refresh token should stop before connector refresh")

        def fetch_order_lines(self, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("should not fetch with expiring token and no refresh token")

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_shop_authorization_status",
        lambda **kwargs: calls.setdefault("status", kwargs),
    )

    with pytest.raises(ValueError, match="店铺授权已失效"):
        data_sources._run_platform_order_collection(
            company_id="company-1",
            source_id="source-1",
            dataset_id="dataset-1",
            dataset_code="taobao_order_lines_shop_1",
            resource_key="taobao_order_lines:shop-1",
            collection_config=_platform_order_dataset()["extract_config"],
            params={"platform_order_collection": {"mode": "incremental"}},
        )

    assert calls["status"]["authorization_id"] == "auth-1"
    assert calls["status"]["auth_status"] == "reauth_required"
    assert "refresh token" in calls["status"]["last_error"]


def test_run_alipay_bill_collection_uses_current_merchant_token(monkeypatch) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "alipay",
            "external_shop_name": "福游网络",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "id": "auth-alipay-1",
            "platform_app_id": "app-alipay-1",
            "auth_status": "authorized",
            "access_token": "current-app-auth-token",
            "refresh_token": "refresh-token",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app_by_id",
        lambda **kwargs: {
            "id": kwargs["platform_app_id"],
            "company_id": data_sources.SERVICE_PROVIDER_COMPANY_ID,
            "platform_code": "alipay",
            "app_name": "Tally Alipay",
            "app_key": "app-id",
            "app_secret": "private-key",
            "app_type": "isv",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should use app by id")),
    )

    class FakeConnector:
        def fetch_bill_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
            calls["fetch_bill_rows"] = kwargs
            return [
                {
                    "bill_type": "trade",
                    "bill_date": "2026-05-06",
                    "source_row_key": "row-1",
                }
            ]

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_alipay_bill_lines",
        lambda **kwargs: {"input_count": len(kwargs["rows"]), "upserted_count": len(kwargs["rows"])},
    )

    result = data_sources._run_alipay_bill_collection(
        company_id="company-1",
        source_id="source-alipay-1",
        dataset_id="dataset-alipay-1",
        dataset_code="alipay_trade_bill_shop_1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        collection_config=_alipay_bill_dataset()["extract_config"],
        params={"bill_date": "2026-05-06"},
    )

    assert result["success"] is True
    assert calls["fetch_bill_rows"]["app_auth_token"] == "current-app-auth-token"
    assert calls["fetch_bill_rows"]["bill_type"] == "trade"
    assert calls["fetch_bill_rows"]["bill_date"] == "2026-05-06"
    assert calls["fetch_bill_rows"]["merchant_display_name"] == "福游网络"
    assert result["collection_summary"]["record_count"] == 1


def test_run_alipay_bill_collection_upserts_platform_bill_lines(monkeypatch) -> None:
    calls: dict[str, Any] = {}
    collection_config = _alipay_bill_dataset()["extract_config"]

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "alipay",
            "external_shop_id": "merchant-1",
            "external_shop_name": "福游网络",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "id": "auth-alipay-1",
            "platform_app_id": "app-alipay-1",
            "auth_status": "authorized",
            "access_token": "current-app-auth-token",
            "refresh_token": "refresh-token",
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_platform_app_for_authorization",
        lambda **kwargs: {
            "id": "app-alipay-1",
            "company_id": data_sources.SERVICE_PROVIDER_COMPANY_ID,
            "platform_code": "alipay",
            "app_name": "Tally Alipay",
            "app_key": "app-id",
            "app_secret": "private-key",
            "app_type": "isv",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )

    class FakeConnector:
        def fetch_bill_rows(self, **kwargs: Any) -> dict[str, Any]:
            calls["fetch_bill_rows"] = kwargs
            return {
                "rows": [
                    {
                        "bill_type": "trade",
                        "bill_date": "2026-05-06",
                        "source_row_key": "row-1",
                        "amount": "12.30",
                    }
                ],
                "original_files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
            }

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector())

    def fake_upsert_platform_alipay_bill_lines(**kwargs: Any) -> dict[str, int]:
        calls["upsert_platform_alipay_bill_lines"] = kwargs
        return {"input_count": len(kwargs["rows"]), "upserted_count": len(kwargs["rows"])}

    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_alipay_bill_lines",
        fake_upsert_platform_alipay_bill_lines,
    )

    result = data_sources._run_alipay_bill_collection(
        company_id="company-1",
        source_id="source-alipay-1",
        dataset_id="dataset-alipay-1",
        dataset_code="alipay_trade_bill_shop_1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        collection_config=collection_config,
        params={"biz_date": "2026-05-06"},
        checkpoint_before={"last_bill_date": "2026-05-05", "custom": "keep"},
    )

    assert result["success"] is True
    assert result["collection_summary"]["storage"] == "platform_alipay_bill_lines"
    assert result["collection_summary"]["record_count"] == 1
    assert result["next_checkpoint"]["custom"] == "keep"
    upsert = calls["upsert_platform_alipay_bill_lines"]
    assert upsert["company_id"] == "company-1"
    assert upsert["data_source_id"] == "source-alipay-1"
    assert upsert["dataset_id"] == "dataset-alipay-1"
    assert upsert["shop_connection_id"] == "shop-alipay-1"
    assert upsert["external_shop_id"] == "merchant-1"
    assert upsert["bill_type"] == "trade"
    assert upsert["bill_date"] == "2026-05-06"


def test_run_alipay_bill_collection_refreshes_expiring_token_before_fetch(monkeypatch) -> None:
    calls: dict[str, Any] = {"updates": []}
    expiring_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "alipay",
            "external_shop_name": "福游网络",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "id": "auth-alipay-1",
            "platform_app_id": "app-alipay-1",
            "auth_status": "authorized",
            "access_token": "old-app-auth-token",
            "refresh_token": "refresh-token",
            "token_expires_at": expiring_at,
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_app_by_id",
        lambda **kwargs: {
            "id": kwargs["platform_app_id"],
            "company_id": data_sources.SERVICE_PROVIDER_COMPANY_ID,
            "platform_code": "alipay",
            "app_name": "Tally Alipay",
            "app_key": "app-id",
            "app_secret": "private-key",
            "app_type": "isv",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "get_platform_app", lambda **kwargs: None)

    class FakeConnector:
        def refresh_token(self, *, refresh_token: str) -> PlatformTokenBundle:
            calls["refresh_token"] = refresh_token
            return PlatformTokenBundle(
                access_token="new-app-auth-token",
                refresh_token="new-refresh-token",
                expires_in=7200,
                refresh_expires_in=30 * 24 * 3600,
                raw_payload={"source": "refresh"},
            )

        def fetch_bill_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
            calls["app_auth_token"] = kwargs["app_auth_token"]
            return []

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_shop_authorization_tokens",
        lambda **kwargs: calls["updates"].append(kwargs)
        or {
            "id": kwargs["authorization_id"],
            "access_token": kwargs["access_token"],
            "refresh_token": kwargs["refresh_token"],
            "raw_auth_payload": kwargs["raw_auth_payload"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_alipay_bill_lines",
        lambda **kwargs: {
            "input_count": len(kwargs["rows"]),
            "upserted_count": len(kwargs["rows"]),
            "deleted_stale_count": 0,
        },
    )

    result = data_sources._run_alipay_bill_collection(
        company_id="company-1",
        source_id="source-alipay-1",
        dataset_id="dataset-alipay-1",
        dataset_code="alipay_trade_bill_shop_1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        collection_config=_alipay_bill_dataset()["extract_config"],
        params={"bill_date": "2026-05-06"},
    )

    assert result["success"] is True
    assert calls["refresh_token"] == "refresh-token"
    assert calls["app_auth_token"] == "new-app-auth-token"
    assert calls["updates"][0]["access_token"] == "new-app-auth-token"


def test_run_platform_order_collection_refreshes_once_after_session_expired_error(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"attempt_tokens": [], "updates": []}
    _authorized_shop(
        monkeypatch,
        {
            "access_token": "old-access",
            "refresh_token": "refresh-token",
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        },
    )

    class FakeConnector:
        def refresh_token(self, *, refresh_token: str) -> PlatformTokenBundle:
            calls["refresh_token"] = refresh_token
            return PlatformTokenBundle(
                access_token="new-access",
                refresh_token="new-refresh",
                expires_in=7200,
                refresh_expires_in=30 * 24 * 3600,
                raw_payload={"source": "retry-refresh"},
            )

        def fetch_order_lines(self, **kwargs: Any) -> dict[str, Any]:
            token = kwargs["token_bundle"].access_token
            calls["attempt_tokens"].append(token)
            if token == "old-access":
                raise RuntimeError("Invalid session")
            return {"success": True, "healthy": True, "rows": []}

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_shop_authorization_tokens",
        lambda **kwargs: calls["updates"].append(kwargs)
        or {
            "id": kwargs["authorization_id"],
            "access_token": kwargs["access_token"],
            "refresh_token": kwargs["refresh_token"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_order_lines",
        lambda **kwargs: {"input_count": 0, "upserted_count": 0},
    )

    result = data_sources._run_platform_order_collection(
        company_id="company-1",
        source_id="source-1",
        dataset_id="dataset-1",
        dataset_code="taobao_order_lines_shop_1",
        resource_key="taobao_order_lines:shop-1",
        collection_config=_platform_order_dataset()["extract_config"],
        params={"platform_order_collection": {"mode": "incremental"}},
    )

    assert result["success"] is True
    assert calls["attempt_tokens"] == ["old-access", "new-access"]
    assert calls["refresh_token"] == "refresh-token"
    assert len(calls["updates"]) == 1


@pytest.mark.anyio
async def test_trigger_sync_reuses_existing_idempotent_job(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "company_id": company_id,
            "source_kind": "platform_oauth",
            "status": "active",
            "is_enabled": True,
            "provider_code": "taobao",
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_runtime_source",
        lambda source_row, include_secret=False: {
            "source_kind": "platform_oauth",
            "provider_code": "taobao",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_sync_job",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should reuse before create")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "find_unified_sync_job_by_idempotency_key",
        lambda **kwargs: {
            "id": "job-existing",
            "company_id": kwargs["company_id"],
            "data_source_id": kwargs["data_source_id"],
            "idempotency_key": kwargs["idempotency_key"],
            "job_status": "success",
        },
    )

    result = await data_sources._handle_data_source_trigger_sync(
        {
            "source_id": "source-1",
            "resource_key": "taobao_order_lines:shop-1",
            "idempotency_key": "taobao-initial:dataset-1:2026-05-06",
            "params": {},
        },
        trusted_company_id="company-1",
    )

    assert result["success"] is True
    assert result["reused"] is True
    assert result["job"]["id"] == "job-existing"


@pytest.mark.anyio
async def test_collection_detail_routes_platform_order_dataset_to_order_line_helpers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {"id": data_source_id, "source_kind": "platform_oauth"},
    )
    monkeypatch.setattr(data_sources, "_resolve_dataset_row", lambda **kwargs: _platform_order_dataset())
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [])
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_order_line_stats",
        lambda **kwargs: {"total_count": 2},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_order_lines",
        lambda **kwargs: [{"payload": {"tid": "T1"}}, {"payload": {"tid": "T2"}}],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_dataset_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-1",
            "dataset_id": "dataset-1",
            "sample_limit": 10,
        }
    )

    assert result["success"] is True
    assert result["collection_stats"] == {"total_count": 2}
    assert result["rows"] == [{"tid": "T1"}, {"tid": "T2"}]


@pytest.mark.anyio
async def test_list_collection_records_reads_alipay_platform_bill_lines(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"id": "user-1", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(id=dataset_id),
    )

    def fake_list_platform_alipay_bill_lines(**kwargs: Any) -> list[dict[str, Any]]:
        calls["list_platform_alipay_bill_lines"] = kwargs
        return [{"payload": {"source_row_key": "row-1", "amount": "12.30"}}]

    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        fake_list_platform_alipay_bill_lines,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_alipay_bill_line_stats",
        lambda **kwargs: {"total_count": 1, "biz_date_count": 1},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_dataset_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )

    result = await data_sources._handle_data_source_list_collection_records(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "biz_date": "2026-05-06",
            "item_key": "row-1",
        }
    )

    assert result["success"] is True
    assert result["records"][0]["payload"]["source_row_key"] == "row-1"
    assert result["stats"]["total_count"] == 1
    assert calls["list_platform_alipay_bill_lines"]["filters"] == {
        "source_row_key": "row-1"
    }
    assert calls["list_platform_alipay_bill_lines"]["biz_date"] == "2026-05-06"


@pytest.mark.anyio
async def test_preview_reads_alipay_platform_bill_lines(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"id": "user-1", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(id=dataset_id),
    )

    def fake_list_platform_alipay_bill_lines(**kwargs: Any) -> list[dict[str, Any]]:
        calls["list_platform_alipay_bill_lines"] = kwargs
        return [{"payload": {"source_row_key": "row-1", "amount": "12.30"}}]

    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        fake_list_platform_alipay_bill_lines,
    )
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_dataset_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )

    result = await data_sources._handle_data_source_preview(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "limit": 10,
        }
    )

    assert result["success"] is True
    assert result["rows"] == [{"source_row_key": "row-1", "amount": "12.30"}]
    assert result["message"] == "已返回支付宝账单样例"
    assert calls["list_platform_alipay_bill_lines"]["dataset_id"] == "dataset-alipay-1"


@pytest.mark.anyio
async def test_collection_detail_reads_alipay_platform_bill_lines(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"id": "user-1", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(id=dataset_id),
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [])
    monkeypatch.setattr(
        data_sources,
        "_enrich_jobs_with_latest_attempts",
        lambda company_id, jobs: jobs,
    )

    def fake_list_platform_alipay_bill_lines(**kwargs: Any) -> list[dict[str, Any]]:
        calls["list_platform_alipay_bill_lines"] = kwargs
        return [{"payload": {"source_row_key": "row-1", "amount": "12.30"}}]

    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        fake_list_platform_alipay_bill_lines,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_alipay_bill_line_stats",
        lambda **kwargs: {"total_count": 1, "biz_date_count": 1},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_dataset_collection_record_stats",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_dataset_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong storage")),
    )

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "sample_limit": 10,
        }
    )

    assert result["success"] is True
    assert result["collection_stats"]["total_count"] == 1
    assert result["collection_records"][0]["payload"]["source_row_key"] == "row-1"
    assert result["rows"] == [{"source_row_key": "row-1", "amount": "12.30"}]
    assert calls["list_platform_alipay_bill_lines"]["resource_key"] == (
        "alipay_bill:trade:shop-alipay-1"
    )


@pytest.mark.anyio
async def test_collection_detail_returns_platform_field_groups_and_twenty_rows(
    monkeypatch,
) -> None:
    semantic_profile = {
        "status": "generated_with_samples",
        "generated_from": {"has_sample_rows": True},
        "fields": [
            {
                "raw_name": "alipay_trade_no",
                "display_name": "支付宝交易号",
                "semantic_type": "identifier",
                "field_source": "normalized",
            },
            {
                "raw_name": "raw.收入",
                "display_name": "收入",
                "semantic_type": "amount",
                "field_source": "raw_bill",
            },
            {
                "raw_name": "source_row_key",
                "display_name": "账单行唯一键",
                "semantic_type": "identifier",
                "field_source": "system",
            },
        ],
    }
    dataset = _alipay_bill_dataset(meta={"semantic_profile": semantic_profile})

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"id": "user-1", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [])
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_alipay_bill_line_stats",
        lambda **kwargs: {"total_count": 20, "biz_date_count": 1},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "source_row_key": f"row-{idx}",
                    "alipay_trade_no": f"2026050800{idx:02d}",
                    "raw": {"收入": f"{idx}.00"},
                }
            }
            for idx in range(1, 21)
        ],
    )

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "sample_limit": 20,
        }
    )

    assert result["success"] is True
    assert result["sample_limit"] == 20
    assert result["row_count"] == 20
    assert result["collection_status"]["status"] == "succeeded"
    assert result["semantic_status"]["status"] == "succeeded"
    assert [group["key"] for group in result["field_groups"]] == [
        "normalized",
        "raw_bill",
        "system",
    ]
    assert [group["fields"][0]["raw_name"] for group in result["field_groups"]] == [
        "alipay_trade_no",
        "raw.收入",
        "source_row_key",
    ]
    assert result["rows"][0]["raw.收入"] == "1.00"


@pytest.mark.anyio
async def test_collection_detail_marks_running_job_as_non_actionable(
    monkeypatch,
) -> None:
    dataset = _alipay_bill_dataset(meta={})
    running_job = {
        "id": "job-running",
        "data_source_id": "source-alipay-1",
        "resource_key": "alipay_bill:trade:shop-alipay-1",
        "job_status": "running",
    }

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"id": "user-1", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [running_job])
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_alipay_bill_line_stats",
        lambda **kwargs: {"total_count": 0, "biz_date_count": 0},
    )
    monkeypatch.setattr(data_sources.auth_db, "list_platform_alipay_bill_lines", lambda **kwargs: [])

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "sample_limit": 20,
        }
    )

    assert result["success"] is True
    assert result["sample_limit"] == 20
    assert result["row_count"] == 0
    assert result["collection_status"]["status"] == "running"
    assert result["collection_status"]["message"] == "初始化中"
    assert result["collection_status"]["is_running"] is True
    assert result["collection_status"]["can_initialize"] is False
    assert result["collection_status"]["can_retry_initialize"] is False
    assert result["semantic_status"]["status"] == "waiting_for_samples"
    assert result["semantic_status"]["can_refresh"] is False
    assert [group["key"] for group in result["field_groups"]] == [
        "normalized",
        "raw_bill",
        "system",
    ]


def test_build_collection_status_detail_distinguishes_queued_and_not_started() -> None:
    queued = data_sources._build_collection_status_detail(
        [
            {
                "id": "job-queued",
                "job_status": "queued",
                "resource_key": "alipay_bill:trade:shop-alipay-1",
            }
        ],
        {"total_count": 0},
        0,
    )
    not_started = data_sources._build_collection_status_detail([], {"total_count": 0}, 0)

    assert queued["status"] == "queued"
    assert queued["message"] == "等待初始化"
    assert queued["is_running"] is True
    assert queued["can_initialize"] is False
    assert queued["can_retry_initialize"] is False
    assert not_started["status"] == "not_started"
    assert not_started["message"] == "尚未初始化"
    assert not_started["is_running"] is False
    assert not_started["can_initialize"] is True


def test_semantic_status_waits_for_generation_when_collection_running_with_samples() -> None:
    status = data_sources._build_semantic_status_detail(
        _alipay_bill_dataset(meta={}),
        has_sample_rows=True,
        collection_running=True,
    )

    assert status["status"] == "waiting_for_generation"
    assert status["message"] == "初始化中，暂不可刷新语义"
    assert status["can_refresh"] is False
    assert status["can_retry"] is False


@pytest.mark.anyio
async def test_collection_detail_ignores_non_initial_running_job_for_initialization_status(
    monkeypatch,
) -> None:
    dataset = _alipay_bill_dataset(
        meta={
            "semantic_profile": {
                "status": "generated_with_samples",
                "fields": [{"raw_name": "source_row_key", "display_name": "账单行唯一键"}],
            }
        }
    )
    running_job = {
        "id": "job-incremental",
        "data_source_id": "source-alipay-1",
        "resource_key": "alipay_bill:trade:shop-alipay-1",
        "job_status": "running",
        "trigger_mode": "scheduled",
    }

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"id": "user-1", "company_id": "company-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [running_job])
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_alipay_bill_line_stats",
        lambda **kwargs: {"total_count": 3, "biz_date_count": 1},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [{"payload": {"source_row_key": "row-1"}}],
    )

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
        }
    )

    assert result["sample_limit"] == 20
    assert result["collection_status"]["status"] == "succeeded"
    assert result["collection_status"]["is_running"] is False
    assert result["semantic_status"]["status"] == "succeeded"
    assert result["semantic_status"]["can_refresh"] is True


def test_platform_shop_detail_does_not_publish_dataset_by_itself() -> None:
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")
    dataset["publish_status"] = "unpublished"
    dataset["meta"] = {
        "semantic_profile": {
            "status": "generated_with_samples",
            "fields": [{"raw_name": "source_row_key", "display_name": "账单行唯一键"}],
        }
    }

    view = data_sources._build_dataset_view(dataset)

    assert view["publish_status"] == "unpublished"
    assert view["semantic_status"] == "generated_with_samples"
