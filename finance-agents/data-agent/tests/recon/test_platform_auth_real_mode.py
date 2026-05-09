from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.datastructures import Headers

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

mcp_client = importlib.import_module("tools.mcp_client")
platform_api = importlib.import_module("graphs.platform.api")


class MemoryUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self.headers = Headers({"content-type": content_type})

    async def read(self) -> bytes:
        return self._content


@pytest.mark.anyio
async def test_platform_create_auth_session_defaults_to_real_mcp_call(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool_name, payload))
        return {
            "success": True,
            "mode": payload["mode"],
            "platform_code": payload["platform_code"],
            "session_id": "session-1",
            "state": "state-1",
            "auth_url": "https://oauth.taobao.com/authorize?state=state-1",
            "expires_in": 1800,
        }

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    result = await mcp_client.platform_create_auth_session("token", "taobao", return_path="/connections")

    assert result["success"] is True
    assert result["mode"] == "real"
    assert calls == [
        (
            "platform_create_auth_session",
            {
                "auth_token": "token",
                "platform_code": "taobao",
                "return_path": "/connections",
                "mode": "real",
            },
        )
    ]


def test_mock_platform_list_exposes_only_taobao_and_alipay() -> None:
    result = mcp_client._mock_list_connections("token")

    assert [item["platform_code"] for item in result["platforms"]] == ["taobao", "alipay"]
    assert [item["platform_name"] for item in result["platforms"]] == ["淘宝/天猫", "支付宝"]


@pytest.mark.anyio
async def test_platform_auth_callback_defaults_to_real_mcp_call(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool_name, payload))
        return {
            "success": True,
            "mode": payload["mode"],
            "platform_code": payload["platform_code"],
            "return_path": "/connections",
            "message": "淘宝/天猫授权成功",
        }

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    result = await mcp_client.platform_handle_auth_callback("taobao", code="code-1", state="state-1")

    assert result["success"] is True
    assert result["mode"] == "real"
    assert calls == [
        (
            "platform_handle_auth_callback",
            {
                "platform_code": "taobao",
                "code": "code-1",
                "state": "state-1",
                "error": "",
                "error_description": "",
                "mode": "real",
            },
        )
    ]


@pytest.mark.anyio
async def test_platform_auth_callback_passes_callback_payload_to_mcp(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool_name, payload))
        return {
            "success": False,
            "mode": payload["mode"],
            "platform_code": payload["platform_code"],
            "return_path": "/connections",
            "message": "支付宝授权回调处理待接入",
        }

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    result = await mcp_client.platform_handle_auth_callback(
        "alipay",
        state="state-1",
        code="",
        mode="real",
        callback_payload={
            "state": "state-1",
            "app_auth_code": "app-auth-code",
            "auth_app_id": "2021000000000001",
        },
    )

    assert result["success"] is False
    assert calls == [
        (
            "platform_handle_auth_callback",
            {
                "platform_code": "alipay",
                "code": "",
                "state": "state-1",
                "error": "",
                "error_description": "",
                "mode": "real",
                "callback_payload": {
                    "state": "state-1",
                    "app_auth_code": "app-auth-code",
                    "auth_app_id": "2021000000000001",
                },
            },
        )
    ]


@pytest.mark.anyio
async def test_platform_app_config_wrappers_call_mcp(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool_name, payload))
        return {
            "success": True,
            "configured": True,
            "config": {"platform_code": payload["platform_code"], "app_key": payload.get("app_key", "")},
        }

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    get_result = await mcp_client.platform_get_app_config("token", "taobao")
    save_result = await mcp_client.platform_upsert_app_config(
        "token",
        "alipay",
        app_key="2021006152656574",
        app_secret="PRIVATE-KEY",
        redirect_uri="https://tally.example.com/api/platform-auth/callback/alipay",
        app_public_cert="APP-CERT",
        alipay_public_cert="ALIPAY-CERT",
        alipay_root_cert="ROOT-CERT",
    )

    assert get_result["success"] is True
    assert save_result["success"] is True
    assert calls == [
        ("platform_get_app_config", {"auth_token": "token", "platform_code": "taobao", "mode": "real"}),
        (
            "platform_upsert_app_config",
            {
                "auth_token": "token",
                "platform_code": "alipay",
                "mode": "real",
                "app_key": "2021006152656574",
                "app_secret": "PRIVATE-KEY",
                "redirect_uri": "https://tally.example.com/api/platform-auth/callback/alipay",
                "app_public_cert": "APP-CERT",
                "alipay_public_cert": "ALIPAY-CERT",
                "alipay_root_cert": "ROOT-CERT",
                "merchant_auth_mode": "",
                "merchant_auth_pc_url": "",
                "merchant_auth_qr_url": "",
            },
        ),
    ]


@pytest.mark.anyio
async def test_platform_pending_authorization_wrappers_call_mcp(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool_name, payload))
        return {"success": True, "platform_code": payload["platform_code"]}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call_mcp_tool)

    list_result = await mcp_client.platform_list_pending_authorizations(
        "token",
        "alipay",
        status="pending_claim",
    )
    claim_result = await mcp_client.platform_claim_pending_authorization(
        "token",
        "alipay",
        "pending-1",
        claim_code="ALIPAY-123456",
        merchant_display_name="福游网络",
    )

    assert list_result["success"] is True
    assert claim_result["success"] is True
    assert calls == [
        (
            "platform_list_pending_authorizations",
            {
                "auth_token": "token",
                "platform_code": "alipay",
                "status": "pending_claim",
                "mode": "real",
            },
        ),
        (
            "platform_claim_pending_authorization",
            {
                "auth_token": "token",
                "platform_code": "alipay",
                "pending_authorization_id": "pending-1",
                "claim_code": "ALIPAY-123456",
                "merchant_display_name": "福游网络",
                "mode": "real",
            },
        ),
    ]


@pytest.mark.anyio
async def test_platform_app_config_route_forces_real_mode(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_platform_upsert_app_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        return {
            "success": True,
            "mode": kwargs["mode"],
            "platform_code": args[1],
            "configured": True,
            "config": {"platform_code": args[1], "app_key": kwargs["app_key"]},
        }

    monkeypatch.setattr(platform_api, "platform_upsert_app_config", fake_platform_upsert_app_config)

    result = await platform_api.upsert_platform_app_config(
        "alipay",
        platform_api.UpsertPlatformAppConfigRequest(
            app_key="2021006152656574",
            app_secret="PRIVATE-KEY",
            redirect_uri="https://tally.example.com/api/platform-auth/callback/alipay",
            app_public_cert="APP-CERT",
            alipay_public_cert="ALIPAY-CERT",
            alipay_root_cert="ROOT-CERT",
            mode="mock",
        ),
        authorization="Bearer token",
    )

    assert result.mode == "real"
    assert calls[0]["kwargs"]["mode"] == "real"


@pytest.mark.anyio
async def test_platform_app_config_route_preserves_alipay_merchant_auth_links(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_platform_upsert_app_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        return {
            "success": True,
            "mode": kwargs["mode"],
            "platform_code": args[1],
            "configured": True,
            "config": {
                "platform_code": args[1],
                "app_key": kwargs["app_key"],
                "merchant_auth_mode": kwargs["merchant_auth_mode"],
                "merchant_auth_pc_url": kwargs["merchant_auth_pc_url"],
                "merchant_auth_qr_url": kwargs["merchant_auth_qr_url"],
            },
        }

    monkeypatch.setattr(platform_api, "platform_upsert_app_config", fake_platform_upsert_app_config)

    result = await platform_api.upsert_platform_app_config(
        "alipay",
        platform_api.UpsertPlatformAppConfigRequest(
            app_key="2021006152656574",
            app_secret="PRIVATE-KEY",
            redirect_uri="https://dev.tallyai.cn/api/platform-auth/callback/alipay",
            app_public_cert="APP-CERT",
            alipay_public_cert="ALIPAY-CERT",
            alipay_root_cert="ROOT-CERT",
            merchant_auth_mode="static_invite",
            merchant_auth_pc_url="https://b.alipay.com/page/message/tasksDetail?bizData=abc",
            merchant_auth_qr_url="",
        ),
        authorization="Bearer token",
    )

    assert result.config.merchant_auth_pc_url == "https://b.alipay.com/page/message/tasksDetail?bizData=abc"
    assert result.config.merchant_auth_qr_url == ""
    assert calls[0]["kwargs"]["merchant_auth_mode"] == "static_invite"
    assert calls[0]["kwargs"]["merchant_auth_pc_url"] == "https://b.alipay.com/page/message/tasksDetail?bizData=abc"
    assert calls[0]["kwargs"]["merchant_auth_qr_url"] == ""


@pytest.mark.anyio
async def test_upload_alipay_merchant_auth_qr_saves_image_and_updates_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    saved_payloads: list[dict[str, Any]] = []

    async def fake_platform_get_app_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "platform_code": args[1],
            "configured": True,
            "config": {
                "app_key": "2021006152656574",
                "has_app_secret": True,
                "has_app_public_cert": True,
                "has_alipay_public_cert": True,
                "has_alipay_root_cert": True,
                "redirect_uri": "https://dev.tallyai.cn/api/platform-auth/callback/alipay",
                "merchant_auth_mode": "static_invite",
                "merchant_auth_pc_url": "https://b.alipay.com/page/message/tasksDetail?bizData=abc",
                "merchant_auth_qr_url": "",
            },
        }

    async def fake_platform_upsert_app_config(*args: Any, **kwargs: Any) -> dict[str, Any]:
        saved_payloads.append({"args": args, "kwargs": kwargs})
        return {
            "success": True,
            "mode": kwargs["mode"],
            "platform_code": args[1],
            "configured": True,
            "config": {
                "platform_code": args[1],
                "app_key": kwargs["app_key"],
                "merchant_auth_qr_url": kwargs["merchant_auth_qr_url"],
            },
            "message": "支付宝商家授权二维码已上传",
        }

    monkeypatch.setattr(platform_api, "ALIPAY_AUTH_ASSET_ROOT", tmp_path)
    monkeypatch.setattr(platform_api, "platform_get_app_config", fake_platform_get_app_config)
    monkeypatch.setattr(platform_api, "platform_upsert_app_config", fake_platform_upsert_app_config)

    result = await platform_api.upload_alipay_merchant_auth_qr(
        MemoryUploadFile("qr.png", b"\x89PNG\r\n\x1a\nqr-content", "image/png"),
        authorization="Bearer token",
    )

    assert result.success is True
    assert result.merchant_auth_qr_url == "/api/platform-connections/alipay/assets/merchant-auth-qr.png"
    assert (tmp_path / "merchant-auth-qr.png").read_bytes() == b"\x89PNG\r\n\x1a\nqr-content"
    assert saved_payloads[0]["kwargs"]["merchant_auth_pc_url"] == "https://b.alipay.com/page/message/tasksDetail?bizData=abc"
    assert saved_payloads[0]["kwargs"]["merchant_auth_qr_url"] == "/api/platform-connections/alipay/assets/merchant-auth-qr.png"


@pytest.mark.anyio
async def test_platform_pending_authorization_routes_forward_to_mcp(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_list_pending(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"name": "list", "args": args, "kwargs": kwargs})
        return {
            "success": True,
            "platform_code": args[1],
            "pending_authorizations": [
                {
                    "id": "pending-1",
                    "platform_code": "alipay",
                    "claim_code": "ALIPAY-123456",
                    "status": "pending_claim",
                }
            ],
            "count": 1,
        }

    async def fake_claim_pending(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"name": "claim", "args": args, "kwargs": kwargs})
        return {
            "success": True,
            "platform_code": args[1],
            "shop": {"id": "shop-1", "platform_code": "alipay", "external_shop_name": "福游网络"},
            "message": "支付宝商户授权已绑定",
        }

    monkeypatch.setattr(platform_api, "platform_list_pending_authorizations", fake_list_pending)
    monkeypatch.setattr(platform_api, "platform_claim_pending_authorization", fake_claim_pending)

    list_response = await platform_api.list_platform_pending_authorizations(
        "alipay",
        status="pending_claim",
        mode="real",
        authorization="Bearer token",
    )
    claim_response = await platform_api.claim_platform_pending_authorization(
        "alipay",
        "pending-1",
        platform_api.ClaimPendingAuthorizationRequest(
            claim_code="ALIPAY-123456",
            merchant_display_name="福游网络",
            mode="mock",
        ),
        authorization="Bearer token",
    )

    assert list_response.count == 1
    assert claim_response.shop["id"] == "shop-1"
    assert calls == [
        {
            "name": "list",
            "args": ("token", "alipay"),
            "kwargs": {"status": "pending_claim", "mode": "real"},
        },
        {
            "name": "claim",
            "args": ("token", "alipay", "pending-1"),
            "kwargs": {
                "claim_code": "ALIPAY-123456",
                "merchant_display_name": "福游网络",
                "mode": "real",
            },
        },
    ]


@pytest.mark.anyio
async def test_platform_shop_list_route_preserves_authorization_fields(monkeypatch) -> None:
    async def fake_platform_list_shops(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "mode": kwargs["mode"],
            "platform_code": args[1],
            "platform_name": "支付宝",
            "shops": [
                {
                    "id": "shop-alipay-1",
                    "company_id": "company-1",
                    "platform_code": "alipay",
                    "platform_name": "支付宝",
                    "external_shop_id": "2088123412341234",
                    "external_shop_name": "对对科技",
                    "auth_status": "authorized",
                    "status": "authorized",
                    "token_status": "authorized",
                    "token_expires_at": "2027-05-09T12:00:00+08:00",
                    "last_refresh_at": "2026-05-09T12:00:00+08:00",
                    "last_sync_at": "2026-05-09T12:30:00+08:00",
                    "last_status": "success",
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(platform_api, "platform_list_shops", fake_platform_list_shops)

    response = await platform_api.get_platform_shops(
        "alipay",
        mode="real",
        authorization="Bearer token",
    )

    shop = response.shops[0]
    assert shop.auth_status == "authorized"
    assert shop.token_expires_at == "2027-05-09T12:00:00+08:00"
    assert shop.last_refresh_at == "2026-05-09T12:00:00+08:00"
    assert shop.last_sync_at == "2026-05-09T12:30:00+08:00"
    assert shop.last_status == "success"


@pytest.mark.anyio
async def test_platform_auth_callback_forwards_full_query_payload(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_platform_handle_auth_callback(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        return {
            "success": False,
            "mode": kwargs["mode"],
            "platform_code": args[0],
            "return_path": "/data-connections?mode=platform&platform=alipay",
            "error": "支付宝授权回调处理待接入",
        }

    monkeypatch.setattr(
        platform_api,
        "platform_handle_auth_callback",
        fake_platform_handle_auth_callback,
    )

    response = await platform_api.handle_platform_auth_callback(
        "alipay",
        request=platform_api.Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/platform-auth/callback/alipay",
                "query_string": (
                    b"state=state-1&app_auth_code=app-auth-code&auth_app_id=2021000000000001"
                    b"&mode=real"
                ),
                "headers": [],
            }
        ),
        state="state-1",
        code="",
        error="",
        error_description="",
        mode="real",
    )

    redirect_query = parse_qs(urlsplit(response.headers["location"]).query)

    assert response.status_code == 303
    assert redirect_query["platform_auth_status"] == ["failed"]
    assert calls == [
        {
            "args": ("alipay",),
            "kwargs": {
                "code": "",
                "state": "state-1",
                "error": "",
                "error_description": "",
                "mode": "real",
                "callback_payload": {
                    "state": "state-1",
                    "app_auth_code": "app-auth-code",
                    "auth_app_id": "2021000000000001",
                    "mode": "real",
                },
            },
        }
    ]


@pytest.mark.anyio
async def test_platform_auth_callback_redirect_includes_pending_claim_params(monkeypatch) -> None:
    async def fake_platform_handle_auth_callback(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "mode": kwargs["mode"],
            "platform_code": args[0],
            "return_path": "/data-connections?mode=platform&platform=alipay",
            "message": "支付宝授权已收到，请填写支付宝商户名称完成绑定",
            "pending_authorization_id": "pending-1",
            "claim_code": "ALIPAY-123456",
        }

    monkeypatch.setattr(
        platform_api,
        "platform_handle_auth_callback",
        fake_platform_handle_auth_callback,
    )

    response = await platform_api.handle_platform_auth_callback(
        "alipay",
        request=platform_api.Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/platform-auth/callback/alipay",
                "query_string": b"app_auth_code=P0161-auth-code&app_id=2021006152656574&mode=real",
                "headers": [],
            }
        ),
        state="",
        code="",
        error="",
        error_description="",
        mode="real",
    )

    redirect_query = parse_qs(urlsplit(response.headers["location"]).query)

    assert response.status_code == 303
    assert redirect_query["platform_auth_status"] == ["success"]
    assert redirect_query["platform_auth_message"] == ["支付宝授权已收到，请填写支付宝商户名称完成绑定"]
    assert redirect_query["pending_authorization_id"] == ["pending-1"]
    assert redirect_query["claim_code"] == ["ALIPAY-123456"]
