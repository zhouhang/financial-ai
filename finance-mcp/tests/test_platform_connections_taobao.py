from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from connectors.base import ConnectorContext
from connectors.providers.platform_oauth import PlatformOAuthConnector
from platforms.base import PlatformAppConfig, PlatformShopProfile, PlatformTokenBundle
from tools import platform_connections


def test_public_platforms_collapse_taobao_and_tmall() -> None:
    platforms = platform_connections.SUPPORTED_PLATFORMS

    assert {
        "platform_code": "taobao",
        "platform_name": "淘宝/天猫",
        "status": "supported",
    } in platforms
    assert not any(item["platform_code"] == "tmall" for item in platforms)


def test_build_taobao_order_line_dataset_payload_is_shop_scoped() -> None:
    payload = platform_connections.build_taobao_order_line_dataset_payload(
        company_id="company-1",
        data_source_id="source-1",
        shop_connection_id="shop-abcdef123456",
        shop_name="旗舰店",
        external_shop_id="seller-1",
    )

    assert payload["dataset_code"] == "taobao_order_lines_shop_abcdef1"
    assert payload["dataset_name"] == "淘宝/天猫订单明细 - 旗舰店"
    assert payload["resource_key"] == "taobao_order_lines:shop-abcdef123456"
    assert payload["dataset_kind"] == "api_endpoint"
    assert payload["origin_type"] == "fixed"
    assert payload["publish_status"] == "published"
    assert payload["business_domain"] == "ecommerce"
    assert payload["business_object_type"] == "platform_order"
    assert payload["grain"] == "shop_order_line"
    assert payload["extract_config"] == {
        "storage": "platform_order_lines",
        "platform_code": "taobao",
        "shop_connection_id": "shop-abcdef123456",
        "external_shop_id": "seller-1",
        "date_field": "biz_date",
        "api": {
            "init_method": "taobao.trades.sold.get",
            "incremental_method": "taobao.trades.sold.increment.get",
        },
    }
    assert payload["sync_strategy"] == {
        "mode": "full_then_incremental",
        "schedule_type": "cron",
        "schedule_expr": "0 */2 * * *",
        "lookback_minutes": 10,
        "page_size": 100,
        "initial_days": 90,
        "initial_end_offset_days": 1,
    }


def test_build_taobao_initial_collection_job_payloads_has_90_days() -> None:
    jobs = platform_connections.build_taobao_initial_collection_job_payloads(
        company_id="company-1",
        data_source_id="source-1",
        dataset_id="dataset-1",
        shop_connection_id="shop-1",
        anchor_date="2026-05-07",
    )

    assert len(jobs) == 90
    assert jobs[0] == {
        "source_id": "source-1",
        "dataset_id": "dataset-1",
        "resource_key": "taobao_order_lines:shop-1",
        "trigger_mode": "initial",
        "idempotency_key": "taobao-initial:dataset-1:2026-02-06",
        "background": True,
        "params": {
            "dataset_id": "dataset-1",
            "resource_key": "taobao_order_lines:shop-1",
            "biz_date": "2026-02-06",
            "force_mode": "initial",
        },
    }
    assert jobs[-1]["params"]["biz_date"] == "2026-05-06"
    assert all(job["trigger_mode"] == "initial" for job in jobs)


@pytest.mark.anyio
async def test_taobao_callback_upserts_order_dataset_and_orders_source(monkeypatch) -> None:
    calls: dict[str, list[Any]] = {
        "data_sources": [],
        "datasets": [],
        "sync_sources": [],
        "callbacks": [],
        "scheduled": [],
    }

    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_auth_session_by_state",
        lambda state: {
            "id": "session-1",
            "company_id": "company-1",
            "platform_code": "taobao",
            "status": "pending",
            "redirect_uri": "http://localhost/callback",
            "return_path": "/connections",
        },
    )
    monkeypatch.setattr(
        platform_connections,
        "_load_app_config",
        lambda *args, **kwargs: PlatformAppConfig(
            id="app-1",
            company_id="company-1",
            platform_code="taobao",
            app_name="Taobao",
            app_key="key",
            app_secret="secret",
            app_type="system",
            auth_base_url="",
            token_url="",
            refresh_url="",
            redirect_uri="http://localhost/callback",
            auth_mode="mock",
        ),
    )

    class FakeConnector:
        def exchange_code_for_token(self, **kwargs: Any) -> PlatformTokenBundle:
            return PlatformTokenBundle(access_token="access", refresh_token="refresh")

        def fetch_shop_profile(self, **kwargs: Any) -> PlatformShopProfile:
            return PlatformShopProfile(
                external_shop_id="seller-1",
                external_shop_name="旗舰店",
                external_seller_id="seller-user-1",
                auth_subject_name="旗舰店",
                metadata={"source": "test"},
            )

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_shop_connection",
        lambda **kwargs: {
            "id": "shop-abcdef123456",
            **kwargs,
        },
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_shop_authorization",
        lambda **kwargs: {"id": "authorization-1", **kwargs},
    )

    def fake_upsert_sync_source(**kwargs: Any) -> dict[str, Any]:
        calls["sync_sources"].append(kwargs)
        return {"id": f"sync-{kwargs['source_type']}", **kwargs}

    def fake_upsert_data_source(**kwargs: Any) -> dict[str, Any]:
        calls["data_sources"].append(kwargs)
        return {"id": "source-1", **kwargs}

    def fake_upsert_dataset(**kwargs: Any) -> dict[str, Any]:
        calls["datasets"].append(kwargs)
        return {"id": "dataset-1", **kwargs}

    monkeypatch.setattr(platform_connections.auth_db, "upsert_sync_source", fake_upsert_sync_source)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_unified_data_source", fake_upsert_data_source)
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_unified_data_source_dataset",
        fake_upsert_dataset,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "update_auth_session_callback",
        lambda **kwargs: calls["callbacks"].append(kwargs),
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_shop_connection_by_id",
        lambda shop_id: {
            "id": shop_id,
            "company_id": "company-1",
            "platform_code": "taobao",
            "external_shop_name": "旗舰店",
            "status": "active",
        },
    )
    monkeypatch.setattr(
        platform_connections,
        "_build_shop_view",
        lambda connection: {**connection, "last_sync_at": None, "last_status": "idle"},
    )

    def fake_create_task(coro: Any) -> None:
        calls["scheduled"].append(coro)
        coro.close()

    monkeypatch.setattr(platform_connections.asyncio, "create_task", fake_create_task)

    result = await platform_connections._handle_auth_callback(
        {"platform_code": "taobao", "state": "state-1", "code": "code-1", "mode": "mock"}
    )

    assert result["success"] is True
    assert [call["source_type"] for call in calls["sync_sources"]] == ["orders"]
    assert len(calls["data_sources"]) == 1
    assert calls["data_sources"][0]["source_kind"] == "platform_oauth"
    assert calls["data_sources"][0]["provider_code"] == "taobao"
    assert calls["data_sources"][0]["code"] == "platform_oauth_taobao_shop_abcdef123456"
    assert len(calls["datasets"]) == 1
    dataset_call = calls["datasets"][0]
    assert dataset_call["data_source_id"] == "source-1"
    assert dataset_call["resource_key"] == "taobao_order_lines:shop-abcdef123456"
    assert dataset_call["sync_strategy"]["schedule_expr"] == "0 */2 * * *"
    assert dataset_call["sync_strategy"]["initial_days"] == 90
    assert calls["callbacks"][0]["callback_payload"]["taobao_order_dataset_id"] == "dataset-1"
    assert len(calls["scheduled"]) == 90


def test_platform_oauth_discover_returns_helpful_empty_for_taobao_and_tmall() -> None:
    from connectors.providers import platform_oauth

    assert platform_oauth._PLATFORM_FIXED_DATASET_OVERRIDES["taobao"] == ()
    assert platform_oauth._PLATFORM_FIXED_DATASET_OVERRIDES["tmall"] == ()

    for provider_code in ("taobao", "tmall"):
        connector = PlatformOAuthConnector(
            ConnectorContext(
                source_id="source-1",
                company_id="company-1",
                source_kind="platform_oauth",
                provider_code=provider_code,
                execution_mode="deterministic",
            )
        )

        result = connector.discover_datasets({})

        assert result["success"] is True
        assert result["datasets"] == []
        assert result["dataset_count"] == 0
        assert "授权成功后" in result["message"]


@pytest.mark.anyio
async def test_tmall_auth_session_request_is_accepted_as_taobao(monkeypatch) -> None:
    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1"},
    )
    monkeypatch.setattr(
        platform_connections,
        "_load_app_config",
        lambda company_id, platform_code, **kwargs: PlatformAppConfig(
            id="app-1",
            company_id=company_id,
            platform_code=platform_code,
            app_name="Taobao",
            app_key="key",
            app_secret="secret",
            app_type="system",
            auth_base_url="",
            token_url="",
            refresh_url="",
            redirect_uri="http://localhost/callback",
            auth_mode="mock",
        ),
    )

    class FakeConnector:
        def build_auth_url(self, *, state: str) -> str:
            return ""

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_auth_session",
        lambda **kwargs: {"id": "session-1", "state_token": kwargs["state_token"], **kwargs},
    )

    result = await platform_connections._handle_create_auth_session(
        {"auth_token": "token", "platform_code": "tmall", "mode": "mock"}
    )

    assert result["success"] is True
    assert result["platform_code"] == "taobao"


@pytest.mark.anyio
async def test_taobao_callback_keeps_auth_success_when_dataset_creation_fails(monkeypatch) -> None:
    callbacks: list[dict[str, Any]] = []

    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_auth_session_by_state",
        lambda state: {
            "id": "session-1",
            "company_id": "company-1",
            "platform_code": "taobao",
            "status": "pending",
            "redirect_uri": "http://localhost/callback",
            "return_path": "/connections",
        },
    )
    monkeypatch.setattr(
        platform_connections,
        "_load_app_config",
        lambda *args, **kwargs: PlatformAppConfig(
            id="app-1",
            company_id="company-1",
            platform_code="taobao",
            app_name="Taobao",
            app_key="key",
            app_secret="secret",
            app_type="system",
            auth_base_url="",
            token_url="",
            refresh_url="",
            redirect_uri="http://localhost/callback",
            auth_mode="mock",
        ),
    )

    class FakeConnector:
        def exchange_code_for_token(self, **kwargs: Any) -> PlatformTokenBundle:
            return PlatformTokenBundle(access_token="access", refresh_token="refresh")

        def fetch_shop_profile(self, **kwargs: Any) -> PlatformShopProfile:
            return PlatformShopProfile(
                external_shop_id="seller-1",
                external_shop_name="旗舰店",
                external_seller_id="seller-user-1",
                auth_subject_name="旗舰店",
            )

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_shop_connection",
        lambda **kwargs: {"id": "shop-1", **kwargs},
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_shop_authorization",
        lambda **kwargs: {"id": "authorization-1", **kwargs},
    )
    monkeypatch.setattr(platform_connections.auth_db, "upsert_sync_source", lambda **kwargs: {"id": "sync-1"})
    monkeypatch.setattr(
        platform_connections,
        "_upsert_taobao_order_line_dataset",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("dataset failed")),
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "update_auth_session_callback",
        lambda **kwargs: callbacks.append(kwargs),
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_shop_connection_by_id",
        lambda shop_id: {"id": shop_id, "company_id": "company-1", "platform_code": "taobao", "status": "active"},
    )
    monkeypatch.setattr(platform_connections, "_build_shop_view", lambda connection: connection)

    result = await platform_connections._handle_auth_callback(
        {"platform_code": "taobao", "state": "state-1", "code": "code-1", "mode": "mock"}
    )

    assert result["success"] is True
    assert result["warning"] == "dataset failed"
    assert callbacks[0]["status"] == "authorized"
    assert callbacks[0]["callback_payload"]["taobao_order_dataset_warning"] == "dataset failed"
