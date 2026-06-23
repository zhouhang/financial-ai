from __future__ import annotations
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Mock heavy optional deps that are absent in the test environment
for _mod in (
    "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio",
    "psycopg",
    "psycopg.conninfo",
    "psycopg.sql",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import server
from services import browser_agent_gateway as gw

_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def _token(role="system"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": "browser-agent:a1", "role": role, "iat": now, "exp": now + timedelta(hours=2)},
                      _SECRET, algorithm="HS256")


def test_rejects_non_system_token():
    client = TestClient(server.app)
    with client.websocket_connect("/browser-agent") as ws:
        ws.send_json({"type": "hello", "token": _token("member"), "agent_id": "a1"})
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack" and ack["ok"] is False


def test_hello_then_claim_relays_to_mcp(monkeypatch):
    async def fake_call(tool, args):
        assert tool == "browser_sync_job_claim"
        assert args["worker_token"] and args["agent_id"] == "a1" and args["max_concurrency"] == 2
        return {"job": {"id": "job-1"}}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    client = TestClient(server.app)
    with client.websocket_connect("/browser-agent") as ws:
        ws.send_json({"type": "hello", "token": _token("system"), "agent_id": "a1", "max_concurrency": 2})
        assert ws.receive_json() == {"type": "hello_ack", "ok": True}
        ws.send_json({"type": "claim", "id": "r1"})
        reply = ws.receive_json()
        assert reply == {"type": "result", "id": "r1", "ok": True, "data": {"job": {"id": "job-1"}}}


def test_main_configures_browser_agent_ws_max_size(monkeypatch):
    captured = {}

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
    monkeypatch.setattr(server, "BROWSER_AGENT_WS_MAX_SIZE", 64 * 1024 * 1024)

    server.main()

    assert captured["args"] == ("server:app",)
    assert captured["kwargs"]["ws_max_size"] == 64 * 1024 * 1024
