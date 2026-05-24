from __future__ import annotations
import sys, types
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# mirror tests/test_browser_agent_ws_endpoint.py: stub heavy deps before importing server
for _m in ["langgraph.checkpoint.postgres","langgraph.checkpoint.postgres.aio","psycopg","psycopg.conninfo","psycopg.sql"]:
    sys.modules[_m]=MagicMock()
from fastapi.testclient import TestClient
import server
from graphs.platform import api as platform_api


def test_handoff_landing_renders(monkeypatch):
    async def fake_describe(token):
        return {"success": True, "session": {"status":"pending","reason":"RISK_VERIFICATION",
                "agent_id":"browser-agent-local","profile_key":"单枪旗舰店","expires_at":"2026-05-24 22:00:00"}}
    monkeypatch.setattr(platform_api, "browser_handoff_session_describe", fake_describe, raising=False)
    r=TestClient(server.app).get("/p/handoff?t=sometoken")
    assert r.status_code==200
    assert "单枪旗舰店" in r.text and "人工验证" in r.text


def test_handoff_landing_invalid_token(monkeypatch):
    async def fake_describe(token):
        return {"success": False, "error": "链接无效或已过期"}
    monkeypatch.setattr(platform_api, "browser_handoff_session_describe", fake_describe, raising=False)
    r=TestClient(server.app).get("/p/handoff?t=bad")
    assert r.status_code in (200,400) and ("失效" in r.text or "无效" in r.text)
