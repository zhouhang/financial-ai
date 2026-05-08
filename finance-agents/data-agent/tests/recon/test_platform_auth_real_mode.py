from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

mcp_client = importlib.import_module("tools.mcp_client")
platform_api = importlib.import_module("graphs.platform.api")


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
