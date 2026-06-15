from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

auto_run_api = importlib.import_module("graphs.recon.auto_run_api")
mcp_client = importlib.import_module("tools.mcp_client")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auto_run_api.router)
    return TestClient(app)


def _auth_header() -> dict[str, str]:
    token = auto_run_api.jwt.encode(
        {
            "sub": "user-001",
            "username": "tester",
            "role": "member",
            "company_id": "company-001",
        },
        auto_run_api.JWT_SECRET,
        algorithm=auto_run_api.JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


def test_public_digest_bundle_calls_mcp_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_bundle(token: str, view: str, *, line_limit: int = 500) -> dict[str, object]:
        captured.update({"token": token, "view": view, "line_limit": line_limit})
        return {"success": True, "data": {"view": view, "line_limit": line_limit}}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_bundle", fake_bundle)

    response = _client().get("/recon/public/digests/digest-token/boss?line_limit=250")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"view": "boss", "line_limit": 250}}
    assert captured == {"token": "digest-token", "view": "boss", "line_limit": 250}


def test_public_digest_bundle_uses_default_line_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_bundle(token: str, view: str, *, line_limit: int = 500) -> dict[str, object]:
        captured.update({"token": token, "view": view, "line_limit": line_limit})
        return {"success": True}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_bundle", fake_bundle)

    response = _client().get("/recon/public/digests/digest-token/finance")

    assert response.status_code == 200
    assert captured == {"token": "digest-token", "view": "finance", "line_limit": 500}


def test_public_run_exceptions_defaults_to_open_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_bundle(
        run_id: str,
        *,
        owner_identifier: str = "",
        limit: int = 100,
        offset: int = 0,
        include_closed: bool = False,
    ) -> dict[str, object]:
        captured.update(
            {
                "run_id": run_id,
                "owner_identifier": owner_identifier,
                "limit": limit,
                "offset": offset,
                "include_closed": include_closed,
            }
        )
        return {"success": True, "exceptions": [], "total": 0}

    monkeypatch.setattr(auto_run_api, "execution_run_public_exception_bundle", fake_bundle)

    response = _client().get("/recon/public/runs/run-001/exceptions?owner=owner-001")

    assert response.status_code == 200
    assert captured == {
        "run_id": "run-001",
        "owner_identifier": "owner-001",
        "limit": 100,
        "offset": 0,
        "include_closed": False,
    }


def test_public_run_exceptions_can_include_closed_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_bundle(
        run_id: str,
        *,
        owner_identifier: str = "",
        limit: int = 100,
        offset: int = 0,
        include_closed: bool = False,
    ) -> dict[str, object]:
        captured.update(
            {
                "run_id": run_id,
                "owner_identifier": owner_identifier,
                "limit": limit,
                "offset": offset,
                "include_closed": include_closed,
            }
        )
        return {"success": True, "exceptions": [], "total": 0}

    monkeypatch.setattr(auto_run_api, "execution_run_public_exception_bundle", fake_bundle)

    response = _client().get(
        "/recon/public/runs/run-001/exceptions?limit=25&offset=50&include_closed=true"
    )

    assert response.status_code == 200
    assert captured == {
        "run_id": "run-001",
        "owner_identifier": "",
        "limit": 25,
        "offset": 50,
        "include_closed": True,
    }


def test_public_digest_bundle_returns_404_when_mcp_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_bundle(token: str, view: str, *, line_limit: int = 500) -> dict[str, object]:
        return {"success": False, "error": "公开摘要不存在"}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_bundle", fake_bundle)

    response = _client().get("/recon/public/digests/missing-token/boss")

    assert response.status_code == 404
    assert response.json()["detail"] == "公开摘要不存在"


def test_public_digest_bundle_validates_line_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_bundle(token: str, view: str, *, line_limit: int = 500) -> dict[str, object]:
        return {"success": True}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_bundle", fake_bundle)

    response = _client().get("/recon/public/digests/digest-token/boss?line_limit=1001")

    assert response.status_code == 422


def test_public_digest_export_calls_mcp_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_export(token: str, view: str, *, recon_type: str = "") -> dict[str, object]:
        captured.update({"token": token, "view": view, "recon_type": recon_type})
        return {"success": True, "csv": "id,amount\n1,10"}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_export", fake_export)

    response = _client().get("/recon/public/digests/digest-token/finance/export?recon_type=fund")

    assert response.status_code == 200
    assert response.json() == {"success": True, "csv": "id,amount\n1,10"}
    assert captured == {"token": "digest-token", "view": "finance", "recon_type": "fund"}


def test_public_digest_export_uses_default_recon_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_export(token: str, view: str, *, recon_type: str = "") -> dict[str, object]:
        captured.update({"token": token, "view": view, "recon_type": recon_type})
        return {"success": True}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_export", fake_export)

    response = _client().get("/recon/public/digests/digest-token/boss/export")

    assert response.status_code == 200
    assert captured == {"token": "digest-token", "view": "boss", "recon_type": ""}


def test_public_digest_export_returns_400_when_mcp_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_export(token: str, view: str, *, recon_type: str = "") -> dict[str, object]:
        return {"success": False, "error": "导出失败"}

    monkeypatch.setattr(auto_run_api, "recon_digest_public_export", fake_export)

    response = _client().get("/recon/public/digests/digest-token/finance/export")

    assert response.status_code == 400
    assert response.json()["detail"] == "导出失败"


def test_digest_subscription_upsert_api_calls_mcp_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_upsert(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        captured.update({"auth_token": auth_token, "payload": payload})
        return {"success": True, "subscription": {"id": "sub-001"}}

    monkeypatch.setattr(auto_run_api, "recon_digest_subscription_upsert", fake_upsert)

    response = _client().post(
        "/recon/digest-subscriptions",
        headers=_auth_header(),
        json={"view": "boss", "recipient_json": {"user_id": "u1"}},
    )

    assert response.status_code == 200
    assert response.json()["subscription"]["id"] == "sub-001"
    assert captured["payload"]["view"] == "boss"
    assert captured["payload"]["recipient_json"] == {"user_id": "u1"}


def test_digest_finalize_daily_api_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_finalize(**kwargs) -> dict[str, object]:
        captured.update(kwargs)
        return {"success": True, "ready_count": 1, "deliveries": [{"status": "dry_run"}]}

    monkeypatch.setattr(auto_run_api, "finalize_and_deliver_daily_digest", fake_finalize)

    response = _client().post(
        "/recon/digests/finalize-daily",
        headers=_auth_header(),
        json={"biz_date": "2026-06-05", "view": "finance", "dry_run": True},
    )

    assert response.status_code == 200
    assert response.json()["ready_count"] == 1
    assert captured["company_id"] == "company-001"
    assert captured["biz_date"] == "2026-06-05"
    assert captured["view"] == "finance"
    assert captured["dry_run"] is True


@pytest.mark.asyncio
async def test_recon_digest_public_bundle_wrapper_calls_mcp_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        captured.update({"tool_name": tool_name, "arguments": arguments})
        return {"success": True}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call)

    result = await mcp_client.recon_digest_public_bundle("digest-token", "boss", line_limit=123)

    assert result == {"success": True}
    assert captured == {
        "tool_name": "recon_digest_public_bundle",
        "arguments": {"token": "digest-token", "view": "boss", "line_limit": 123},
    }


@pytest.mark.asyncio
async def test_recon_digest_public_export_wrapper_calls_mcp_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        captured.update({"tool_name": tool_name, "arguments": arguments})
        return {"success": True}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call)

    result = await mcp_client.recon_digest_public_export("digest-token", "finance", recon_type="fund")

    assert result == {"success": True}
    assert captured == {
        "tool_name": "recon_digest_public_export",
        "arguments": {"token": "digest-token", "view": "finance", "recon_type": "fund"},
    }


@pytest.mark.asyncio
async def test_recon_digest_finalizer_wrappers_call_mcp_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((tool_name, arguments))
        return {"success": True}

    monkeypatch.setattr(mcp_client, "call_mcp_tool", fake_call)

    await mcp_client.recon_digest_subscription_upsert("token", {"view": "boss"})
    await mcp_client.recon_digest_subscription_list("token", company_id="company-001", view="boss")
    await mcp_client.recon_digest_finalize_daily(
        "token",
        company_id="company-001",
        biz_date="2026-06-05",
        view="finance",
        dry_run=True,
    )
    await mcp_client.recon_digest_delivery_record(
        "token",
        {"digest_id": "digest-001", "subscription_id": "sub-001", "view": "boss", "status": "sent"},
    )

    assert calls == [
        ("recon_digest_subscription_upsert", {"auth_token": "token", "view": "boss"}),
        (
            "recon_digest_subscription_list",
            {
                "auth_token": "token",
                "company_id": "company-001",
                "period": "daily",
                "view": "boss",
            },
        ),
        (
            "recon_digest_finalize_daily",
            {
                "auth_token": "token",
                "company_id": "company-001",
                "biz_date": "2026-06-05",
                "view": "finance",
                "dry_run": True,
            },
        ),
        (
            "recon_digest_delivery_record",
            {
                "auth_token": "token",
                "digest_id": "digest-001",
                "subscription_id": "sub-001",
                "view": "boss",
                "status": "sent",
            },
        ),
    ]
