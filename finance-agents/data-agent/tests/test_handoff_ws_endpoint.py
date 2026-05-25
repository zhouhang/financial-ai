from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
from services import browser_handoff_gateway as hg


def test_p_handoff_removed():
    client = TestClient(server.app)
    response = client.get("/p/handoff?t=anything")
    assert response.status_code == 404


def test_handoff_ws_invalid_token_returns_error(monkeypatch):
    async def fake_call(tool, args):
        assert tool == "browser_handoff_session_describe"
        return {"success": False, "error": "链接无效或已过期"}

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    client = TestClient(server.app)
    with client.websocket_connect("/handoff/ws?t=bad") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["status"] == "expired"
