from __future__ import annotations

import sys
from datetime import date
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


def test_service_provider_app_company_id_is_fixed() -> None:
    assert platform_connections.SERVICE_PROVIDER_COMPANY_ID == "00000000-0000-0000-0000-00000000dd01"


def test_public_platforms_collapse_taobao_and_tmall() -> None:
    platforms = platform_connections.SUPPORTED_PLATFORMS

    assert [item["platform_code"] for item in platforms] == ["taobao", "alipay"]
    assert {
        "platform_code": "taobao",
        "platform_name": "淘宝/天猫",
        "status": "supported",
    } in platforms
    assert {
        "platform_code": "alipay",
        "platform_name": "支付宝",
        "status": "supported",
    } in platforms
    assert not any(item["platform_code"] == "tmall" for item in platforms)
    assert not any(item["platform_code"] in {"douyin_shop", "kuaishou", "jd"} for item in platforms)


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
        "initial_days": 1,
        "initial_end_offset_days": 1,
    }


def test_taobao_initial_collection_uses_t_minus_1_only() -> None:
    jobs = platform_connections.build_taobao_initial_collection_job_payloads(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        shop_connection_id="00000000-0000-0000-0000-000000000004",
        anchor_date="2026-05-07",
    )

    assert len(jobs) == 1
    assert jobs[0]["params"]["biz_date"] == "2026-05-06"
    assert jobs[0]["idempotency_key"].endswith(":2026-05-06")
    assert jobs[-1]["params"]["biz_date"] == "2026-05-06"
    assert all(job["trigger_mode"] == "initial" for job in jobs)


def test_taobao_initial_collection_defaults_to_t_minus_1_when_initial_days_missing() -> None:
    jobs = platform_connections._build_taobao_initial_collection_jobs(
        source_id="source-1",
        dataset_id="dataset-1",
        resource_key="taobao_order_lines:shop-1",
        sync_strategy={"initial_end_offset_days": 1},
        anchor_date=date(2026, 5, 7),
    )

    assert len(jobs) == 1
    assert jobs[0]["params"]["biz_date"] == "2026-05-06"
    assert jobs[0]["idempotency_key"].endswith(":2026-05-06")


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
    assert dataset_call["sync_strategy"]["initial_days"] == 1
    assert calls["callbacks"][0]["callback_payload"]["taobao_order_dataset_id"] == "dataset-1"
    assert len(calls["scheduled"]) == 1


@pytest.mark.anyio
async def test_taobao_callback_redacts_raw_auth_payload(monkeypatch) -> None:
    authorizations: list[dict[str, Any]] = []

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
            auth_mode="real",
        ),
    )

    class FakeConnector:
        def exchange_code_for_token(self, **kwargs: Any) -> PlatformTokenBundle:
            return PlatformTokenBundle(
                access_token="access-secret",
                refresh_token="refresh-secret",
                raw_payload={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "session_key": "session-secret",
                    "taobao_user_id": "seller-1",
                    "taobao_user_nick": "旗舰店",
                },
            )

        def fetch_shop_profile(self, **kwargs: Any) -> PlatformShopProfile:
            return PlatformShopProfile(
                external_shop_id="seller-1",
                external_shop_name="旗舰店",
                external_seller_id="seller-1",
                auth_subject_name="旗舰店",
            )

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_shop_connection",
        lambda **kwargs: {"id": "shop-1", **kwargs},
    )

    def fake_create_shop_authorization(**kwargs: Any) -> dict[str, Any]:
        authorizations.append(kwargs)
        return {"id": "authorization-1", **kwargs}

    monkeypatch.setattr(platform_connections.auth_db, "create_shop_authorization", fake_create_shop_authorization)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_sync_source", lambda **kwargs: {"id": "sync-1"})
    monkeypatch.setattr(
        platform_connections,
        "_upsert_taobao_order_line_dataset",
        lambda **kwargs: ({"id": "source-1"}, {"id": "dataset-1", "resource_key": "taobao_order_lines:shop-1"}),
    )
    monkeypatch.setattr(platform_connections.asyncio, "create_task", lambda coro: coro.close())
    monkeypatch.setattr(platform_connections.auth_db, "update_auth_session_callback", lambda **kwargs: None)
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_shop_connection_by_id",
        lambda shop_id: {"id": shop_id, "company_id": "company-1", "platform_code": "taobao", "status": "active"},
    )
    monkeypatch.setattr(platform_connections, "_build_shop_view", lambda connection: connection)

    result = await platform_connections._handle_auth_callback(
        {"platform_code": "taobao", "state": "state-1", "code": "code-1", "mode": "real"}
    )

    assert result["success"] is True
    raw_payload = authorizations[0]["raw_auth_payload"]
    assert raw_payload["access_token"] == "***REDACTED***"
    assert raw_payload["refresh_token"] == "***REDACTED***"
    assert raw_payload["session_key"] == "***REDACTED***"
    assert raw_payload["taobao_user_id"] == "seller-1"


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
async def test_taobao_auth_session_uses_service_provider_app_config(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "customer-company-1", "user_id": "user-1"},
    )

    def fake_get_platform_app(**kwargs: Any) -> dict[str, Any] | None:
        calls.append(kwargs)
        if kwargs["company_id"] != platform_connections.SERVICE_PROVIDER_COMPANY_ID:
            return None
        return {
            "id": "app-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "app_name": "Tally Taobao",
            "app_key": "tally-app-key",
            "app_secret": "tally-app-secret",
            "app_type": "isv",
            "auth_base_url": "https://oauth.taobao.com/authorize",
            "token_url": "https://oauth.taobao.com/token",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"redirect_uri": "https://tally.example.com/api/platform-auth/callback/taobao"},
            "status": "active",
        }

    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", fake_get_platform_app)

    class FakeConnector:
        def __init__(self, app_config: PlatformAppConfig):
            assert app_config.company_id == platform_connections.SERVICE_PROVIDER_COMPANY_ID
            assert app_config.app_key == "tally-app-key"

        def build_auth_url(self, *, state: str) -> str:
            return f"https://oauth.taobao.com/authorize?state={state}"

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector(app_config))
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_auth_session",
        lambda **kwargs: {"id": "session-1", "state_token": kwargs["state_token"], **kwargs},
    )

    result = await platform_connections._handle_create_auth_session(
        {"auth_token": "token", "platform_code": "taobao", "mode": "real"}
    )

    assert result["success"] is True
    assert result["session"]["company_id"] == "customer-company-1"
    assert calls[0]["company_id"] == platform_connections.SERVICE_PROVIDER_COMPANY_ID


@pytest.mark.anyio
async def test_tmall_auth_session_request_is_accepted_as_taobao(monkeypatch) -> None:
    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
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
async def test_taobao_auth_session_defaults_to_real_app_config(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_platform_app",
        lambda **kwargs: {
            "id": "app-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "app_name": "Taobao App",
            "app_key": "real-app-key",
            "app_secret": "real-app-secret",
            "app_type": "isv",
            "auth_base_url": "https://oauth.taobao.com/authorize",
            "token_url": "https://oauth.taobao.com/token",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"redirect_uri": "https://tally.example.com/api/platform-auth/callback/taobao"},
            "status": "active",
        },
    )

    class FakeConnector:
        def __init__(self, app_config: PlatformAppConfig):
            captured["auth_mode"] = app_config.auth_mode
            captured["redirect_uri"] = app_config.redirect_uri

        def build_auth_url(self, *, state: str) -> str:
            return f"https://oauth.taobao.com/authorize?state={state}"

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector(app_config))
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_auth_session",
        lambda **kwargs: {"id": "session-1", "state_token": kwargs["state_token"], **kwargs},
    )

    result = await platform_connections._handle_create_auth_session(
        {"auth_token": "token", "platform_code": "taobao"}
    )

    assert result["success"] is True
    assert result["auth_mode"] == "real"
    assert result["mode"] == "real"
    assert result["requires_mock_authorize"] is False
    assert result["auth_url"].startswith("https://oauth.taobao.com/authorize?")
    assert captured["auth_mode"] == "real"


@pytest.mark.anyio
async def test_taobao_auth_session_requires_configured_real_app_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", lambda **kwargs: None)
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_platform_app",
        lambda **kwargs: pytest.fail("real auth session must not create a mock app implicitly"),
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_auth_session",
        lambda **kwargs: pytest.fail("auth session should not be created without a real app"),
    )

    result = await platform_connections._handle_create_auth_session(
        {"auth_token": "token", "platform_code": "taobao"}
    )

    assert result["success"] is False
    assert "平台应用未配置" in result["error"]


@pytest.mark.anyio
async def test_alipay_auth_session_requires_merchant_display_name(monkeypatch) -> None:
    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )

    result = await platform_connections._handle_create_auth_session(
        {"auth_token": "token", "platform_code": "alipay", "mode": "real"}
    )

    assert result["success"] is False
    assert result["platform_code"] == "alipay"
    assert "支付宝授权需要填写商户显示名称" in result["error"]


@pytest.mark.anyio
async def test_platform_app_config_is_saved_as_service_provider_config(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "customer-company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", lambda **kwargs: None)

    def fake_upsert_platform_app(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "app-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "app_name": kwargs["app_name"],
            "app_key": kwargs["app_key"],
            "app_secret": kwargs["app_secret"],
            "app_type": kwargs["app_type"],
            "auth_base_url": kwargs["auth_base_url"],
            "token_url": kwargs["token_url"],
            "refresh_url": kwargs["refresh_url"],
            "scopes_config": kwargs["scopes_config"],
            "extra": kwargs["extra"],
            "status": kwargs["status"],
        }

    monkeypatch.setattr(platform_connections.auth_db, "upsert_platform_app", fake_upsert_platform_app)

    result = await platform_connections._handle_upsert_app_config(
        {
            "auth_token": "token",
            "platform_code": "taobao",
            "app_key": "tally-app-key",
            "app_secret": "tally-app-secret",
            "redirect_uri": "https://tally.example.com/api/platform-auth/callback/taobao",
        }
    )

    assert result["success"] is True
    assert captured["company_id"] == platform_connections.SERVICE_PROVIDER_COMPANY_ID
    assert captured["extra"]["owner_scope"] == "service_provider"
    assert captured["extra"]["configured_by_company_id"] == "customer-company-1"


@pytest.mark.anyio
async def test_platform_app_config_can_be_saved_without_returning_secret(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )

    def fake_upsert_platform_app(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "app-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "app_name": kwargs["app_name"],
            "app_key": kwargs["app_key"],
            "app_secret": kwargs["app_secret"],
            "app_type": kwargs["app_type"],
            "auth_base_url": kwargs["auth_base_url"],
            "token_url": kwargs["token_url"],
            "refresh_url": kwargs["refresh_url"],
            "scopes_config": kwargs["scopes_config"],
            "extra": kwargs["extra"],
            "status": kwargs["status"],
        }

    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", lambda **kwargs: None)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_platform_app", fake_upsert_platform_app)

    result = await platform_connections._handle_upsert_app_config(
        {
            "auth_token": "token",
            "platform_code": "taobao",
            "app_key": "real-app-key",
            "app_secret": "real-app-secret",
            "redirect_uri": "https://tally.example.com/api/platform-auth/callback/taobao",
        }
    )

    assert result["success"] is True
    assert result["configured"] is True
    assert result["config"]["platform_code"] == "taobao"
    assert result["config"]["app_key"] == "real-app-key"
    assert result["config"]["app_secret"] == ""
    assert result["config"]["has_app_secret"] is True
    assert captured["app_secret"] == "real-app-secret"
    assert captured["extra"]["mode"] == "real"
    assert captured["extra"]["redirect_uri"] == "https://tally.example.com/api/platform-auth/callback/taobao"


@pytest.mark.anyio
async def test_platform_app_config_reuses_existing_secret_when_secret_blank(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_platform_app",
        lambda **kwargs: {
            "id": "app-1",
            "company_id": "company-1",
            "platform_code": "taobao",
            "app_name": "Old app",
            "app_key": "old-key",
            "app_secret": "existing-secret",
            "app_type": "isv",
            "auth_base_url": "https://old.example.com/authorize",
            "token_url": "https://old.example.com/token",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "real", "redirect_uri": "https://old.example.com/callback"},
            "status": "active",
        },
    )

    def fake_upsert_platform_app(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "app-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "app_name": kwargs["app_name"],
            "app_key": kwargs["app_key"],
            "app_secret": kwargs["app_secret"],
            "app_type": kwargs["app_type"],
            "auth_base_url": kwargs["auth_base_url"],
            "token_url": kwargs["token_url"],
            "refresh_url": kwargs["refresh_url"],
            "scopes_config": kwargs["scopes_config"],
            "extra": kwargs["extra"],
            "status": kwargs["status"],
        }

    monkeypatch.setattr(platform_connections.auth_db, "upsert_platform_app", fake_upsert_platform_app)

    result = await platform_connections._handle_upsert_app_config(
        {
            "auth_token": "token",
            "platform_code": "taobao",
            "app_key": "new-key",
            "app_secret": "",
            "redirect_uri": "https://new.example.com/callback",
        }
    )

    assert result["success"] is True
    assert captured["app_secret"] == "existing-secret"
    assert captured["app_key"] == "new-key"
    assert captured["extra"]["redirect_uri"] == "https://new.example.com/callback"


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


@pytest.mark.anyio
async def test_taobao_initial_collection_jobs_run_sequentially(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeDataSources:
        @staticmethod
        async def trigger_dataset_collection_for_company(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"success": True}

    import tools

    monkeypatch.setattr(tools, "data_sources", FakeDataSources, raising=False)

    jobs = [
        {
            "source_id": "source-1",
            "dataset_id": "dataset-1",
            "resource_key": "taobao_order_lines:shop-1",
            "trigger_mode": "initial",
            "idempotency_key": "day-1",
            "background": True,
            "params": {"biz_date": "2026-05-05"},
        },
        {
            "source_id": "source-1",
            "dataset_id": "dataset-1",
            "resource_key": "taobao_order_lines:shop-1",
            "trigger_mode": "initial",
            "idempotency_key": "day-2",
            "background": True,
            "params": {"biz_date": "2026-05-06"},
        },
    ]

    await platform_connections._run_taobao_initial_collection_jobs(
        company_id="company-1",
        jobs=jobs,
    )

    assert [call["idempotency_key"] for call in calls] == ["day-1", "day-2"]
    assert all(call["background"] is False for call in calls)
