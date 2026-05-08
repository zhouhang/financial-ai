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
        "dataset_code": "alipay_trade_bill_shop_1",
        "resource_key": "alipay_bill:trade:shop-alipay-1",
        "extract_config": {
            "storage": "dataset_collection_records",
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
        "schema_summary": {"storage": "dataset_collection_records"},
        "meta": {"merchant_display_name": "福游网络"},
    }
    dataset.update(overrides)
    return dataset


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
async def test_execute_sync_job_routes_alipay_bill_rows_to_collection_records(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(),
    )

    def fake_run_alipay_bill_collection(**kwargs: Any) -> dict[str, Any]:
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
            "message": "支付宝账单采集成功",
        }

    monkeypatch.setattr(data_sources, "_run_alipay_bill_collection", fake_run_alipay_bill_collection)
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: calls.setdefault("upsert_dataset_collection_records", kwargs)
        or {"input_count": len(kwargs["records"]), "upserted_count": len(kwargs["records"])},
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
    assert calls["alipay_kwargs"]["params"]["bill_date"] == "2026-05-06"
    upsert = calls["upsert_dataset_collection_records"]
    assert upsert["dataset_id"] == "dataset-alipay-1"
    assert upsert["biz_date"] == "2026-05-06"
    assert upsert["records"][0]["item_key_values"] == {
        "bill_type": "trade",
        "bill_date": "2026-05-06",
        "source_row_key": "row-1",
    }
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
