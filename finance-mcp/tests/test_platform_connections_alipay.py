from __future__ import annotations

import logging
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
        "initial_collection_tasks": [],
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

    def forbidden_create_unified_sync_job(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError(
            "Alipay authorization callback must trigger initial collection, not create deferred sync jobs"
        )

    def fake_update_auth_session_callback(**kwargs: Any) -> dict[str, Any]:
        calls["callbacks"].append(kwargs)
        return {**auth_session, **kwargs}

    created_tasks: list[CompletedTask] = []

    class CompletedTask:
        def __init__(self, coroutine: Any):
            self.coroutine = coroutine
            self.done_callbacks: list[Any] = []

        def add_done_callback(self, callback: Any) -> None:
            self.done_callbacks.append(callback)

    async def fake_run_alipay_initial_collection_jobs(**kwargs: Any) -> None:
        calls["initial_collection_tasks"].append(kwargs)

    def fake_create_task(coroutine: Any) -> CompletedTask:
        task = CompletedTask(coroutine)
        created_tasks.append(task)
        return task

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
        forbidden_create_unified_sync_job,
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
    monkeypatch.setattr(
        platform_connections,
        "_run_alipay_initial_collection_jobs",
        fake_run_alipay_initial_collection_jobs,
        raising=False,
    )
    monkeypatch.setattr(platform_connections.asyncio, "create_task", fake_create_task)

    result = await platform_connections._handle_auth_callback(
        {
            "platform_code": "alipay",
            "state": "state-1",
            "callback_payload": {"app_auth_code": "app-auth-code"},
            "mode": "real",
        }
    )
    assert len(created_tasks) == 1
    await created_tasks[0].coroutine

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
    assert len(calls["initial_collection_tasks"]) == 1
    initial_task = calls["initial_collection_tasks"][0]
    assert initial_task["company_id"] == "company-1"
    jobs = initial_task["jobs"]
    assert len(jobs) == 2
    expected_bill_date = (datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=1)).isoformat()
    assert {job["source_id"] for job in jobs} == {"source-alipay-1"}
    assert {job["dataset_id"] for job in jobs} == {"dataset-0", "dataset-1"}
    assert {job["resource_key"] for job in jobs} == {
        "alipay_bill:signcustomer:shop-alipay-1",
        "alipay_bill:trade:shop-alipay-1",
    }
    assert all(job["trigger_mode"] == "initial" for job in jobs)
    assert {job["idempotency_key"] for job in jobs} == {
        f"alipay-initial:dataset-0:signcustomer:{expected_bill_date}",
        f"alipay-initial:dataset-1:trade:{expected_bill_date}",
    }
    assert all(job["params"]["bill_date"] == expected_bill_date for job in jobs)
    assert all(job["params"]["biz_date"] == expected_bill_date for job in jobs)
    assert {job["params"]["bill_type"] for job in jobs} == {"signcustomer", "trade"}
    assert all("deferred_until" not in job for job in jobs)
    assert all("deferred_until" not in job.get("params", {}) for job in jobs)
    callback_payload = calls["callbacks"][0]["callback_payload"]
    assert callback_payload["alipay_data_source_id"] == "source-alipay-1"
    assert callback_payload["alipay_fund_bill_dataset_id"] == "dataset-0"
    assert callback_payload["alipay_trade_bill_dataset_id"] == "dataset-1"
    assert callback_payload["alipay_dataset_warning"] == ""


@pytest.mark.anyio
async def test_run_alipay_initial_collection_jobs_triggers_dataset_collection(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_trigger_dataset_collection_for_company(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"success": True, "job": {"id": f"job-{len(calls)}"}}

    class FakeDataSources:
        trigger_dataset_collection_for_company = staticmethod(
            fake_trigger_dataset_collection_for_company
        )

    import tools

    monkeypatch.setattr(tools, "data_sources", FakeDataSources, raising=False)

    await platform_connections._run_alipay_initial_collection_jobs(
        company_id="company-1",
        jobs=[
            {
                "source_id": "source-alipay-1",
                "dataset_id": "dataset-fund",
                "resource_key": "alipay_bill:signcustomer:shop-alipay-1",
                "trigger_mode": "initial",
                "idempotency_key": "alipay-initial:dataset-fund:signcustomer:2026-05-08",
                "background": True,
                "params": {
                    "dataset_id": "dataset-fund",
                    "resource_key": "alipay_bill:signcustomer:shop-alipay-1",
                    "bill_type": "signcustomer",
                    "bill_date": "2026-05-08",
                    "biz_date": "2026-05-08",
                    "force_mode": "initial",
                },
            },
            {
                "source_id": "source-alipay-1",
                "dataset_id": "dataset-trade",
                "resource_key": "alipay_bill:trade:shop-alipay-1",
                "trigger_mode": "initial",
                "idempotency_key": "alipay-initial:dataset-trade:trade:2026-05-08",
                "background": True,
                "params": {
                    "dataset_id": "dataset-trade",
                    "resource_key": "alipay_bill:trade:shop-alipay-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-08",
                    "biz_date": "2026-05-08",
                    "force_mode": "initial",
                },
            },
        ],
    )

    assert [call["dataset_id"] for call in calls] == ["dataset-fund", "dataset-trade"]
    assert all(call["company_id"] == "company-1" for call in calls)
    assert all(call["source_id"] == "source-alipay-1" for call in calls)
    assert all(call["trigger_mode"] == "initial" for call in calls)
    assert all(call["background"] is False for call in calls)
    assert [call["resource_key"] for call in calls] == [
        "alipay_bill:signcustomer:shop-alipay-1",
        "alipay_bill:trade:shop-alipay-1",
    ]
    assert [call["params"]["bill_date"] for call in calls] == ["2026-05-08", "2026-05-08"]
    assert [call["params"]["biz_date"] for call in calls] == ["2026-05-08", "2026-05-08"]
    assert [call["params"] for call in calls] == [
        {
            "dataset_id": "dataset-fund",
            "resource_key": "alipay_bill:signcustomer:shop-alipay-1",
            "bill_type": "signcustomer",
            "bill_date": "2026-05-08",
            "biz_date": "2026-05-08",
            "force_mode": "initial",
        },
        {
            "dataset_id": "dataset-trade",
            "resource_key": "alipay_bill:trade:shop-alipay-1",
            "bill_type": "trade",
            "bill_date": "2026-05-08",
            "biz_date": "2026-05-08",
            "force_mode": "initial",
        },
    ]
    assert [call["idempotency_key"] for call in calls] == [
        "alipay-initial:dataset-fund:signcustomer:2026-05-08",
        "alipay-initial:dataset-trade:trade:2026-05-08",
    ]


@pytest.mark.anyio
async def test_run_alipay_initial_collection_jobs_logs_unsuccessful_trigger(
    monkeypatch,
    caplog,
) -> None:
    class FakeDataSources:
        @staticmethod
        async def trigger_dataset_collection_for_company(**kwargs: Any) -> dict[str, Any]:
            return {"success": False, "error": "dataset missing"}

    import tools

    monkeypatch.setattr(tools, "data_sources", FakeDataSources, raising=False)

    with caplog.at_level(logging.ERROR, logger="tools.platform_connections"):
        await platform_connections._run_alipay_initial_collection_jobs(
            company_id="company-1",
            jobs=[
                {
                    "source_id": "source-alipay-1",
                    "dataset_id": "dataset-fund",
                    "resource_key": "alipay_bill:signcustomer:shop-alipay-1",
                    "trigger_mode": "initial",
                    "idempotency_key": "alipay-initial:dataset-fund:signcustomer:2026-05-08",
                    "params": {
                        "bill_type": "signcustomer",
                        "bill_date": "2026-05-08",
                    },
                },
            ],
        )

    assert "支付宝初始化采集任务触发失败" in caplog.text
    assert "company-1" in caplog.text
    assert "dataset-fund" in caplog.text
    assert "alipay_bill:signcustomer:shop-alipay-1" in caplog.text
    assert "alipay-initial:dataset-fund:signcustomer:2026-05-08" in caplog.text
    assert "dataset missing" in caplog.text


def test_create_logged_background_task_logs_unhandled_failure(monkeypatch, caplog) -> None:
    class FailedTask:
        def __init__(self) -> None:
            self.callbacks: list[Any] = []

        def add_done_callback(self, callback: Any) -> None:
            self.callbacks.append(callback)

        def result(self) -> None:
            raise RuntimeError("background failed")

    failed_task = FailedTask()

    async def noop() -> None:
        return None

    def fake_create_task(coroutine: Any) -> FailedTask:
        coroutine.close()
        return failed_task

    monkeypatch.setattr(platform_connections.asyncio, "create_task", fake_create_task)

    task = platform_connections._create_logged_background_task(
        noop(),
        task_name="支付宝初始化采集任务",
    )

    assert task is failed_task
    assert len(failed_task.callbacks) == 1
    with caplog.at_level(logging.ERROR, logger="tools.platform_connections"):
        failed_task.callbacks[0](failed_task)

    assert "支付宝初始化采集任务执行失败" in caplog.text
    assert "background failed" in caplog.text


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


@pytest.mark.anyio
async def test_alipay_no_state_callback_creates_pending_claim(monkeypatch) -> None:
    created: dict[str, Any] = {}
    token_bundle = PlatformTokenBundle(
        access_token="app-auth-token",
        refresh_token="app-refresh-token",
        expires_in=3600,
        refresh_expires_in=7200,
        raw_payload={
            "app_auth_token": "app-auth-token",
            "app_refresh_token": "app-refresh-token",
            "auth_app_id": "2021000000000001",
            "user_id": "2088123412341234",
        },
    )

    class FakeConnector:
        def exchange_code_for_token(self, **kwargs: Any) -> PlatformTokenBundle:
            assert kwargs["code"] == "P0161-auth-code"
            assert kwargs["callback_payload"]["app_auth_code"] == "P0161-auth-code"
            return token_bundle

        def fetch_shop_profile(self, **kwargs: Any) -> PlatformShopProfile:
            return PlatformShopProfile(
                external_shop_id="2088123412341234",
                external_shop_name="2088123412341234",
                external_seller_id="2021000000000001",
                auth_subject_name="2088123412341234",
                shop_type="merchant",
                metadata={"source": "app_auth_token"},
            )

    monkeypatch.setattr(platform_connections.auth_db, "get_auth_session_by_state", lambda state: None)
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
            redirect_uri="https://dev.tallyai.cn/api/platform-auth/callback/alipay",
            scopes=[],
            extra={},
            status="active",
            auth_mode="real",
        ),
    )
    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())

    def fake_create_platform_pending_authorization(**kwargs: Any) -> dict[str, Any]:
        created.update(kwargs)
        return {
            "id": "pending-1",
            "platform_code": kwargs["platform_code"],
            "platform_app_id": kwargs["platform_app_id"],
            "app_id": kwargs["app_id"],
            "source": kwargs["source"],
            "claim_code": "ALIPAY-123456",
            "status": "pending_claim",
            "access_token": "",
            "refresh_token": "",
            "external_shop_id": kwargs["external_shop_id"],
            "external_seller_id": kwargs["external_seller_id"],
            "merchant_display_name": kwargs["merchant_display_name"],
            "expires_at": kwargs["expires_at"],
        }

    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_platform_pending_authorization",
        fake_create_platform_pending_authorization,
        raising=False,
    )

    result = await platform_connections._handle_auth_callback(
        {
            "platform_code": "alipay",
            "state": "",
            "callback_payload": {
                "app_auth_code": "P0161-auth-code",
                "app_id": "2021006152656574",
                "source": "alipay_app_auth",
            },
            "mode": "real",
        }
    )

    assert result["success"] is True
    assert result["pending_authorization"]["id"] == "pending-1"
    assert result["pending_authorization"]["claim_code"] == "ALIPAY-123456"
    assert result["claim_code"] == "ALIPAY-123456"
    assert created["platform_code"] == "alipay"
    assert created["platform_app_id"] == "alipay-app-1"
    assert created["access_token"] == "app-auth-token"
    assert created["refresh_token"] == "app-refresh-token"
    assert created["external_shop_id"] == "2088123412341234"
    assert created["external_seller_id"] == "2021000000000001"
    assert created["callback_payload"]["app_auth_code"] == "P0161-auth-code"
    assert "授权会话不存在或已失效" not in result["message"]


@pytest.mark.anyio
async def test_claim_pending_alipay_authorization_creates_connection_authorization_datasets_and_jobs(
    monkeypatch,
) -> None:
    calls: dict[str, list[Any]] = {
        "authorizations": [],
        "sync_sources": [],
        "claimed": [],
        "jobs": [],
    }
    pending = {
        "id": "pending-1",
        "platform_code": "alipay",
        "platform_app_id": "alipay-app-1",
        "app_id": "2021006152656574",
        "source": "alipay_app_auth",
        "claim_code": "ALIPAY-123456",
        "status": "pending_claim",
        "access_token": "app-auth-token",
        "refresh_token": "app-refresh-token",
        "token_expires_at": None,
        "refresh_expires_at": None,
        "raw_auth_payload": {"user_id": "2088123412341234"},
        "external_shop_id": "2088123412341234",
        "external_seller_id": "2021000000000001",
        "merchant_display_name": "",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    connection = {
        "id": "shop-alipay-1",
        "company_id": "company-1",
        "platform_code": "alipay",
        "external_shop_id": "2088123412341234",
        "external_shop_name": "福游网络",
        "external_seller_id": "2021000000000001",
        "auth_subject_name": "福游网络",
        "shop_type": "merchant",
        "status": "active",
        "meta": {"source": "pending_authorization"},
    }

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_platform_pending_authorization_by_id",
        lambda pending_authorization_id, include_secrets=False: pending,
        raising=False,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "find_shop_connection_by_platform_external_shop",
        lambda platform_code, external_shop_id: None,
        raising=False,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "upsert_shop_connection",
        lambda **kwargs: {**connection, **kwargs},
    )

    def fake_create_shop_authorization(**kwargs: Any) -> dict[str, Any]:
        calls["authorizations"].append(kwargs)
        return {"id": "authorization-1", **kwargs}

    def fake_upsert_sync_source(**kwargs: Any) -> dict[str, Any]:
        calls["sync_sources"].append(kwargs)
        return {"id": f"sync-{kwargs['source_type']}", **kwargs}

    def fake_mark_claimed(**kwargs: Any) -> dict[str, Any]:
        calls["claimed"].append(kwargs)
        return {"id": "pending-1", "status": "claimed", **kwargs}

    async def fake_run_alipay_initial_collection_jobs(**kwargs: Any) -> None:
        calls["jobs"].extend(kwargs["jobs"])

    monkeypatch.setattr(platform_connections.auth_db, "create_shop_authorization", fake_create_shop_authorization)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_sync_source", fake_upsert_sync_source)
    monkeypatch.setattr(
        platform_connections.auth_db,
        "mark_platform_pending_authorization_claimed",
        fake_mark_claimed,
        raising=False,
    )
    monkeypatch.setattr(
        platform_connections,
        "_upsert_alipay_bill_datasets",
        lambda **kwargs: (
            {"id": "source-alipay-1"},
            {"id": "dataset-fund", "resource_key": "alipay_bill:signcustomer:shop-alipay-1"},
            {"id": "dataset-trade", "resource_key": "alipay_bill:trade:shop-alipay-1"},
        ),
    )
    monkeypatch.setattr(
        platform_connections,
        "_build_alipay_initial_collection_jobs",
        lambda **kwargs: [{"dataset_id": kwargs["dataset_id"], "bill_type": kwargs["bill_type"]}],
    )
    monkeypatch.setattr(
        platform_connections,
        "_run_alipay_initial_collection_jobs",
        fake_run_alipay_initial_collection_jobs,
        raising=False,
    )
    monkeypatch.setattr(
        platform_connections,
        "_build_shop_view",
        lambda shop: {**shop, "token_status": "authorized"},
    )

    result = await platform_connections._handle_claim_pending_authorization(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "pending_authorization_id": "pending-1",
            "claim_code": "ALIPAY-123456",
            "merchant_display_name": "福游网络",
        }
    )

    assert result["success"] is True
    assert result["shop"]["id"] == "shop-alipay-1"
    assert calls["authorizations"][0]["access_token"] == "app-auth-token"
    assert calls["authorizations"][0]["refresh_token"] == "app-refresh-token"
    assert calls["authorizations"][0]["auth_type"] == "alipay_app_auth"
    assert {item["source_type"] for item in calls["sync_sources"]} == {
        "orders",
        "refunds",
        "settlements",
        "bills",
    }
    assert {job["bill_type"] for job in calls["jobs"]} == {"signcustomer", "trade"}
    assert calls["claimed"][0]["claimed_company_id"] == "company-1"
    assert calls["claimed"][0]["claimed_by_user_id"] == "user-1"
    assert calls["claimed"][0]["claimed_shop_connection_id"] == "shop-alipay-1"


@pytest.mark.anyio
async def test_claim_pending_alipay_authorization_rejects_wrong_claim_code(monkeypatch) -> None:
    pending = {
        "id": "pending-1",
        "platform_code": "alipay",
        "claim_code": "ALIPAY-123456",
        "status": "pending_claim",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_platform_pending_authorization_by_id",
        lambda pending_authorization_id, include_secrets=False: pending,
        raising=False,
    )

    result = await platform_connections._handle_claim_pending_authorization(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "pending_authorization_id": "pending-1",
            "claim_code": "BAD-CODE",
            "merchant_display_name": "福游网络",
        }
    )

    assert result["success"] is False
    assert result["error"] == "认领码不匹配，请检查后重试"


@pytest.mark.anyio
async def test_claim_pending_alipay_authorization_rejects_other_company_binding(monkeypatch) -> None:
    pending = {
        "id": "pending-1",
        "platform_code": "alipay",
        "claim_code": "ALIPAY-123456",
        "status": "pending_claim",
        "external_shop_id": "2088123412341234",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }

    monkeypatch.setattr(
        platform_connections,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1", "role": "admin"},
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "get_platform_pending_authorization_by_id",
        lambda pending_authorization_id, include_secrets=False: pending,
        raising=False,
    )
    monkeypatch.setattr(
        platform_connections.auth_db,
        "find_shop_connection_by_platform_external_shop",
        lambda platform_code, external_shop_id: {
            "id": "shop-other",
            "company_id": "company-other",
            "external_shop_id": external_shop_id,
        },
        raising=False,
    )

    result = await platform_connections._handle_claim_pending_authorization(
        {
            "auth_token": "token",
            "platform_code": "alipay",
            "pending_authorization_id": "pending-1",
            "claim_code": "ALIPAY-123456",
            "merchant_display_name": "福游网络",
        }
    )

    assert result["success"] is False
    assert result["error"] == "该支付宝主体已绑定到其他企业，请联系服务商管理员处理"
