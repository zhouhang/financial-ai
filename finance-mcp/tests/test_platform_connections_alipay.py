from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import platform_connections
from platforms.base import PlatformAppConfig, PlatformShopProfile, PlatformTokenBundle


@pytest.fixture
def auth_token() -> str:
    return "token"


def _alipay_record_from_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "alipay-app-1",
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


@pytest.mark.anyio
async def test_alipay_app_config_saves_private_key_certs_and_returns_public_presence(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", lambda **kwargs: None)

    def fake_upsert_platform_app(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _alipay_record_from_kwargs(kwargs)

    monkeypatch.setattr(platform_connections.auth_db, "upsert_platform_app", fake_upsert_platform_app)

    result = await platform_connections._handle_upsert_app_config(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "app_key": "2021006152656574",
            "app_secret": "PRIVATE-KEY",
            "redirect_uri": "https://tally.example.com/api/platform-auth/callback/alipay",
            "app_public_cert": "APP-CERT",
            "alipay_public_cert": "ALIPAY-CERT",
            "alipay_root_cert": "ROOT-CERT",
        }
    )

    assert result["success"] is True
    assert captured["app_key"] == "2021006152656574"
    assert captured["app_secret"] == "PRIVATE-KEY"
    assert captured["extra"]["app_public_cert"] == "APP-CERT"
    assert captured["extra"]["alipay_public_cert"] == "ALIPAY-CERT"
    assert captured["extra"]["alipay_root_cert"] == "ROOT-CERT"
    assert captured["extra"]["mode"] == "real"
    assert captured["auth_base_url"] == "https://openauth.alipay.com/oauth2/appToAppAuth.htm"
    assert captured["token_url"] == "https://openapi.alipay.com/gateway.do"
    assert captured["refresh_url"] == "https://openapi.alipay.com/gateway.do"

    public_config = result["config"]
    assert public_config["app_secret"] == ""
    assert public_config["has_app_secret"] is True
    assert public_config["has_app_public_cert"] is True
    assert public_config["has_alipay_public_cert"] is True
    assert public_config["has_alipay_root_cert"] is True
    assert "app_public_cert" not in public_config
    assert "alipay_public_cert" not in public_config
    assert "alipay_root_cert" not in public_config


@pytest.mark.anyio
async def test_member_cannot_upsert_alipay_app_config(monkeypatch) -> None:
    upsert_called = False

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "member"},
    )

    def fake_upsert_platform_app(**kwargs: Any) -> dict[str, Any]:
        nonlocal upsert_called
        upsert_called = True
        return _alipay_record_from_kwargs(kwargs)

    monkeypatch.setattr(platform_connections.auth_db, "upsert_platform_app", fake_upsert_platform_app)

    result = await platform_connections._handle_upsert_app_config(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "app_key": "2021006152656574",
            "app_secret": "PRIVATE-KEY",
            "redirect_uri": "https://tally.example.com/api/platform-auth/callback/alipay",
            "app_public_cert": "APP-CERT",
            "alipay_public_cert": "ALIPAY-CERT",
            "alipay_root_cert": "ROOT-CERT",
        }
    )

    assert result["success"] is False
    assert result["error"] == "无权配置服务商应用"
    assert upsert_called is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload_overrides", "expected_error"),
    [
        ({"app_key": ""}, "AppID 不能为空"),
        ({"app_secret": ""}, "应用私钥不能为空"),
        ({"app_public_cert": ""}, "应用公钥证书不能为空"),
        ({"alipay_public_cert": ""}, "支付宝公钥证书不能为空"),
        ({"alipay_root_cert": ""}, "支付宝根证书不能为空"),
    ],
)
async def test_alipay_app_config_validates_required_fields_without_existing_values(
    monkeypatch,
    payload_overrides: dict[str, str],
    expected_error: str,
) -> None:
    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", lambda **kwargs: None)

    payload = {
        "auth_token": "token",
        "platform_code": "alipay",
        "app_key": "2021006152656574",
        "app_secret": "PRIVATE-KEY",
        "redirect_uri": "https://tally.example.com/api/platform-auth/callback/alipay",
        "app_public_cert": "APP-CERT",
        "alipay_public_cert": "ALIPAY-CERT",
        "alipay_root_cert": "ROOT-CERT",
        **payload_overrides,
    }

    result = await platform_connections._handle_upsert_app_config(payload)

    assert result["success"] is False
    assert result["error"] == expected_error


@pytest.mark.anyio
async def test_alipay_app_config_reuses_existing_private_key_and_certs(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    existing = {
        "id": "alipay-app-1",
        "company_id": platform_connections.SERVICE_PROVIDER_COMPANY_ID,
        "platform_code": "alipay",
        "app_name": "Old Alipay app",
        "app_key": "old-app-id",
        "app_secret": "EXISTING-PRIVATE-KEY",
        "app_type": "isv",
        "auth_base_url": "https://old.example.com/auth",
        "token_url": "https://old.example.com/token",
        "refresh_url": "https://old.example.com/refresh",
        "scopes_config": [],
        "extra": {
            "mode": "real",
            "redirect_uri": "https://old.example.com/callback",
            "app_public_cert": "EXISTING-APP-CERT",
            "alipay_public_cert": "EXISTING-ALIPAY-CERT",
            "alipay_root_cert": "EXISTING-ROOT-CERT",
        },
        "status": "active",
    }

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(platform_connections.auth_db, "get_platform_app", lambda **kwargs: existing)

    def fake_upsert_platform_app(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _alipay_record_from_kwargs(kwargs)

    monkeypatch.setattr(platform_connections.auth_db, "upsert_platform_app", fake_upsert_platform_app)

    result = await platform_connections._handle_upsert_app_config(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "app_key": "2021006152656574",
            "app_secret": "",
            "redirect_uri": "https://new.example.com/callback/alipay",
            "app_public_cert": "",
            "alipay_public_cert": "",
            "alipay_root_cert": "",
        }
    )

    assert result["success"] is True
    assert captured["app_secret"] == "EXISTING-PRIVATE-KEY"
    assert captured["extra"]["app_public_cert"] == "EXISTING-APP-CERT"
    assert captured["extra"]["alipay_public_cert"] == "EXISTING-ALIPAY-CERT"
    assert captured["extra"]["alipay_root_cert"] == "EXISTING-ROOT-CERT"
    assert captured["extra"]["redirect_uri"] == "https://new.example.com/callback/alipay"


@pytest.mark.anyio
async def test_create_alipay_auth_session_requires_merchant_display_name(auth_token, monkeypatch):
    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda token: {"company_id": "company-1", "user_id": "user-1", "role": "member"},
    )

    result = await platform_connections._handle_create_auth_session(
        {
            "auth_token": auth_token,
            "platform_code": "alipay",
            "mode": "real",
        }
    )

    assert result["success"] is False
    assert "商户显示名称" in result["error"]


@pytest.mark.anyio
async def test_create_alipay_auth_session_stores_merchant_display_name_extra(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "member"},
    )

    monkeypatch.setattr(
        platform_connections,
        "_load_app_config",
        lambda company_id, platform_code, *, mode, redirect_uri="": PlatformAppConfig(
            id="alipay-app-1",
            company_id=platform_connections.SERVICE_PROVIDER_COMPANY_ID,
            platform_code="alipay",
            app_name="支付宝服务商应用",
            app_key="2021006152656574",
            app_secret="PRIVATE-KEY",
            app_type="isv",
            auth_base_url="https://openauth.alipay.com/oauth2/appToAppAuth.htm",
            token_url="https://openapi.alipay.com/gateway.do",
            refresh_url="https://openapi.alipay.com/gateway.do",
            redirect_uri="https://tally.example.com/api/platform-auth/callback/alipay",
            scopes=[],
            extra={},
            status="active",
            auth_mode="real",
        ),
    )

    def fake_create_auth_session(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "auth-session-1",
            "company_id": kwargs["company_id"],
            "platform_code": kwargs["platform_code"],
            "operator_user_id": kwargs["operator_user_id"],
            "shop_connection_id": kwargs["shop_connection_id"],
            "state_token": kwargs["state_token"],
            "return_path": kwargs["return_path"],
            "redirect_uri": kwargs["redirect_uri"],
            "status": "pending",
            "expires_at": kwargs["expires_at"],
            "extra": kwargs["extra"],
        }

    monkeypatch.setattr(platform_connections.auth_db, "create_auth_session", fake_create_auth_session)

    result = await platform_connections._handle_create_auth_session(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "mode": "real",
            "return_path": "/data-connections?mode=platform&platform=alipay",
            "merchant_display_name": "福游网络",
        }
    )

    assert result["success"] is True
    assert captured["extra"] == {
        "merchant_display_name": "福游网络",
        "connection_label": "福游网络",
        "subject_type": "alipay_merchant",
    }
    assert result["auth_url"].startswith("https://openauth.alipay.com/oauth2/appToAppAuth.htm?")
    assert "2021006152656574" in result["auth_url"]


@pytest.mark.anyio
async def test_alipay_callback_creates_merchant_and_two_datasets(monkeypatch) -> None:
    calls: dict[str, list[Any]] = {
        "shop_connections": [],
        "authorizations": [],
        "sync_sources": [],
        "data_sources": [],
        "datasets": [],
        "callbacks": [],
        "scheduled": [],
    }
    auth_session = {
        "id": "auth-session-1",
        "company_id": "company-1",
        "platform_code": "alipay",
        "state_token": "state-1",
        "return_path": "/data-connections?mode=platform&platform=alipay",
        "redirect_uri": "https://tally.example.com/api/platform-auth/callback/alipay",
        "status": "pending",
        "extra": {
            "merchant_display_name": "福游网络",
            "connection_label": "福游网络",
            "subject_type": "alipay_merchant",
        },
    }

    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_auth_session_by_state",
        lambda state: auth_session if state == "state-1" else None,
    )
    monkeypatch.setattr(
        platform_connections,
        "_load_app_config",
        lambda *args, **kwargs: PlatformAppConfig(
            id="alipay-app-1",
            company_id=platform_connections.SERVICE_PROVIDER_COMPANY_ID,
            platform_code="alipay",
            app_name="支付宝服务商应用",
            app_key="2021006152656574",
            app_secret="PRIVATE-KEY",
            app_type="isv",
            auth_base_url="",
            token_url="",
            refresh_url="",
            redirect_uri="https://tally.example.com/api/platform-auth/callback/alipay",
            scopes=[],
            extra={},
            status="active",
            auth_mode="real",
        ),
    )

    class FakeConnector:
        def exchange_code_for_token(self, **kwargs: Any) -> PlatformTokenBundle:
            assert kwargs["code"] == ""
            assert kwargs["callback_payload"]["app_auth_code"] == "app-auth-code"
            return PlatformTokenBundle(
                access_token="app-auth-token",
                refresh_token="app-refresh-token",
                raw_payload={
                    "app_auth_token": "app-auth-token",
                    "app_refresh_token": "app-refresh-token",
                    "auth_app_id": "2021000000000001",
                    "user_id": "2088123412341234",
                },
            )

        def fetch_shop_profile(self, **kwargs: Any) -> PlatformShopProfile:
            return PlatformShopProfile(
                external_shop_id="2088123412341234",
                external_shop_name="福游网络",
                external_seller_id="2021000000000001",
                auth_subject_name="福游网络",
                shop_type="merchant",
                metadata={"source": "test"},
            )

    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())

    def fake_upsert_shop_connection(**kwargs: Any) -> dict[str, Any]:
        calls["shop_connections"].append(kwargs)
        return {"id": "shop-alipay-1", **kwargs}

    def fake_create_shop_authorization(**kwargs: Any) -> dict[str, Any]:
        calls["authorizations"].append(kwargs)
        return {"id": "authorization-1", **kwargs}

    def fake_upsert_sync_source(**kwargs: Any) -> dict[str, Any]:
        calls["sync_sources"].append(kwargs)
        return {"id": f"sync-{kwargs['source_type']}", **kwargs}

    def fake_upsert_data_source(**kwargs: Any) -> dict[str, Any]:
        calls["data_sources"].append(kwargs)
        return {"id": "source-alipay-1", **kwargs}

    def fake_upsert_dataset(**kwargs: Any) -> dict[str, Any]:
        dataset_id = f"dataset-{len(calls['datasets'])}"
        calls["datasets"].append(kwargs)
        return {"id": dataset_id, **kwargs}

    def fake_create_unified_sync_job(**kwargs: Any) -> dict[str, Any]:
        calls["scheduled"].append(kwargs)
        return {"id": f"sync-job-{len(calls['scheduled'])}", **kwargs}

    def fake_update_auth_session_callback(**kwargs: Any) -> dict[str, Any]:
        calls["callbacks"].append(kwargs)
        return {**auth_session, **kwargs}

    monkeypatch.setattr(platform_connections.auth_db, "upsert_shop_connection", fake_upsert_shop_connection)
    monkeypatch.setattr(platform_connections.auth_db, "create_shop_authorization", fake_create_shop_authorization)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_sync_source", fake_upsert_sync_source)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_unified_data_source", fake_upsert_data_source)
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_unified_data_source_dataset",
        fake_upsert_dataset,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_unified_sync_job",
        fake_create_unified_sync_job,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "update_auth_session_callback",
        fake_update_auth_session_callback,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_shop_connection_by_id",
        lambda shop_id: {
            "id": shop_id,
            "company_id": "company-1",
            "platform_code": "alipay",
            "external_shop_name": "福游网络",
            "status": "active",
        },
    )
    monkeypatch.setattr(
        platform_connections,
        "_build_shop_view",
        lambda connection: {**connection, "last_sync_at": None, "last_status": "idle"},
    )

    result = await platform_connections._handle_auth_callback(
        {
            "platform_code": "alipay",
            "state": "state-1",
            "callback_payload": {"app_auth_code": "app-auth-code"},
            "mode": "real",
        }
    )

    assert result["success"] is True
    assert result["platform_code"] == "alipay"
    assert len(calls["shop_connections"]) == 1
    shop_call = calls["shop_connections"][0]
    assert shop_call["platform_code"] == "alipay"
    assert shop_call["external_shop_id"] == "2088123412341234"
    assert shop_call["external_shop_name"] == "福游网络"
    assert shop_call["external_seller_id"] == "2021000000000001"
    assert shop_call["shop_type"] == "merchant"
    assert len(calls["authorizations"]) == 1
    assert calls["authorizations"][0]["access_token"] == "app-auth-token"
    assert calls["authorizations"][0]["refresh_token"] == "app-refresh-token"
    assert len(calls["data_sources"]) == 1
    assert calls["data_sources"][0]["provider_code"] == "alipay"
    assert calls["data_sources"][0]["domain_type"] == "ecommerce"
    assert [dataset["dataset_name"] for dataset in calls["datasets"]] == [
        "支付宝资金账单 - 福游网络",
        "支付宝交易账单 - 福游网络",
    ]
    assert [dataset["dataset_code"] for dataset in calls["datasets"]] == [
        "alipay_fund_bill_shop_alipay_1",
        "alipay_trade_bill_shop_alipay_1",
    ]
    assert [dataset["resource_key"] for dataset in calls["datasets"]] == [
        "alipay_bill:signcustomer:shop-alipay-1",
        "alipay_bill:trade:shop-alipay-1",
    ]
    assert [dataset["business_domain"] for dataset in calls["datasets"]] == ["ecommerce", "ecommerce"]
    assert [dataset["business_object_type"] for dataset in calls["datasets"]] == [
        "platform_fund_bill",
        "platform_trade_bill",
    ]
    assert [dataset["grain"] for dataset in calls["datasets"]] == [
        "merchant_bill_line",
        "merchant_trade_bill_line",
    ]
    assert all(
        dataset["extract_config"]["storage"] == "platform_alipay_bill_lines"
        for dataset in calls["datasets"]
    )
    assert all(
        dataset["schema_summary"]["storage"] == "platform_alipay_bill_lines"
        for dataset in calls["datasets"]
    )
    assert all(
        dataset["schema_summary"]["source"] == "alipay_bill_lines"
        for dataset in calls["datasets"]
    )
    assert all(
        dataset["extract_config"]["key_fields"] == ["bill_type", "bill_date", "source_row_key"]
        for dataset in calls["datasets"]
    )
    assert all(
        dataset["extract_config"]["collection_date_field"] == "bill_date"
        for dataset in calls["datasets"]
    )
    assert len(calls["scheduled"]) == 2
    scheduled_jobs = calls["scheduled"]
    assert {job["data_source_id"] for job in scheduled_jobs} == {"source-alipay-1"}
    assert {job["resource_key"] for job in scheduled_jobs} == {
        "alipay_bill:signcustomer:shop-alipay-1",
        "alipay_bill:trade:shop-alipay-1",
    }
    expected_bill_date = (datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=1)).isoformat()
    assert all(job["idempotency_key"].endswith(f":{expected_bill_date}") for job in scheduled_jobs)
    assert {job["window_start"] for job in scheduled_jobs} == {expected_bill_date}
    assert {job["window_end"] for job in scheduled_jobs} == {expected_bill_date}
    assert all(
        job["request_payload"]["deferred_until"] == "alipay_bill_collector"
        for job in scheduled_jobs
    )
    assert [job["request_payload"]["params"]["bill_date"] for job in scheduled_jobs] == [
        expected_bill_date,
        expected_bill_date,
    ]
    assert all(job["trigger_mode"] == "initial" for job in scheduled_jobs)
    assert {job["request_payload"]["params"]["bill_type"] for job in scheduled_jobs} == {
        "signcustomer",
        "trade",
    }
    callback_payload = calls["callbacks"][0]["callback_payload"]
    assert callback_payload["alipay_data_source_id"] == "source-alipay-1"
    assert callback_payload["alipay_fund_bill_dataset_id"] == "dataset-0"
    assert callback_payload["alipay_trade_bill_dataset_id"] == "dataset-1"
    assert callback_payload["alipay_dataset_warning"] == ""


def test_build_alipay_bill_dataset_payload_starts_unpublished() -> None:
    payload = platform_connections.build_alipay_bill_dataset_payload(
        company_id="company-1",
        data_source_id="source-1",
        shop_connection_id="shop-alipay-1",
        merchant_name="福游网络",
        external_shop_id="2088",
        bill_kind="trade",
        bill_type="trade",
        dataset_label="支付宝交易账单",
        business_object_type="alipay_trade_bill",
        grain="alipay_bill_line",
    )

    assert payload["resource_key"] == "alipay_bill:trade:shop-alipay-1"
    assert payload["publish_status"] == "unpublished"
