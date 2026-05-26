from __future__ import annotations
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import browser_agent_gateway as gw

_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def _token(role: str = "system") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": "browser-agent:a1", "role": role, "iat": now, "exp": now + timedelta(hours=2)},
        _SECRET, algorithm="HS256",
    )


def test_verify_system_token_accepts_system_role():
    assert gw.verify_system_token(_token("system")) is not None


def test_verify_system_token_rejects_non_system_and_garbage():
    assert gw.verify_system_token(_token("member")) is None
    assert gw.verify_system_token("not-a-jwt") is None
    assert gw.verify_system_token("") is None


def _conn() -> "gw.BrowserAgentConnection":
    return gw.BrowserAgentConnection(token="tok-1", agent_id="agent-A", max_concurrency=3)


@pytest.mark.asyncio
async def test_claim_maps_to_tool_with_injected_args(monkeypatch):
    calls = []
    async def fake_call(tool, args):
        calls.append((tool, args))
        return {"job": None}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    rid = str(uuid.uuid4())
    reply = await gw.handle_domain_message(_conn(), {"type": "claim", "id": rid})
    assert reply == {"type": "result", "id": rid, "ok": True, "data": {"job": None}}
    tool, args = calls[0]
    assert tool == "browser_sync_job_claim"
    assert args == {"worker_token": "tok-1", "agent_id": "agent-A", "max_concurrency": 3}


@pytest.mark.asyncio
async def test_startup_cleanup_maps_to_tool_with_injected_agent(monkeypatch):
    calls = []

    async def fake_call(tool, args):
        calls.append((tool, args))
        return {"success": True, "failed_count": 2}

    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    reply = await gw.handle_domain_message(_conn(), {"type": "startup_cleanup", "id": "cleanup-1"})

    assert reply == {
        "type": "result",
        "id": "cleanup-1",
        "ok": True,
        "data": {"success": True, "failed_count": 2},
    }
    tool, args = calls[0]
    assert tool == "browser_sync_job_startup_cleanup"
    assert args == {"worker_token": "tok-1", "agent_id": "agent-A"}


@pytest.mark.asyncio
async def test_job_complete_passes_payload_and_injects_token(monkeypatch):
    calls = []
    async def fake_call(tool, args):
        calls.append((tool, args)); return {"success": True}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    reply = await gw.handle_domain_message(
        _conn(), {"type": "job_complete", "id": "x", "sync_job_id": "j1", "records": [], "capture_files": []},
    )
    assert reply["ok"] is True
    tool, args = calls[0]
    assert tool == "browser_sync_job_complete"
    assert args["worker_token"] == "tok-1"
    assert args["sync_job_id"] == "j1" and args["records"] == [] and args["capture_files"] == []
    assert "type" not in args and "id" not in args


@pytest.mark.asyncio
async def test_heartbeat_refreshes_token(monkeypatch):
    captured = {}
    async def fake_call(tool, args):
        captured["args"] = args; return {"success": True}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)
    conn = _conn()
    await gw.handle_domain_message(conn, {"type": "heartbeat", "id": "h", "token": "tok-2", "company_id": "c1"})
    assert conn.token == "tok-2"
    assert captured["args"]["worker_token"] == "tok-2"
    assert captured["args"]["agent_id"] == "agent-A"
    assert captured["args"]["company_id"] == "c1"
    assert "token" not in captured["args"]


@pytest.mark.asyncio
async def test_unknown_type_returns_error(monkeypatch):
    async def fake_call(tool, args):
        raise AssertionError("不应调用 MCP")
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)
    reply = await gw.handle_domain_message(_conn(), {"type": "nope", "id": "z"})
    assert reply["ok"] is False and "未知消息类型" in reply["error"]


@pytest.mark.asyncio
async def test_mcp_exception_becomes_error_result(monkeypatch):
    async def fake_call(tool, args):
        raise RuntimeError("boom")
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)
    reply = await gw.handle_domain_message(_conn(), {"type": "queue_requeue_ready", "id": "q"})
    assert reply["ok"] is False and "boom" in reply["error"]
