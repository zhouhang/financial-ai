from __future__ import annotations

import sys
import time
from pathlib import Path

import jwt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.tally_client import (
    BrowserAgentConfig,
    BrowserAgentTallyClient,
    create_system_token,
)


def test_create_system_token_has_system_role(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    token = create_system_token(agent_id="browser-agent-local")
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert payload["role"] == "system"
    assert payload["username"] == "browser-agent"
    assert payload["sub"] == "browser-agent:browser-agent-local"


def test_browser_agent_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_AGENT_ID", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_MAX_CONCURRENCY", raising=False)
    config = BrowserAgentConfig.from_env()
    assert config.agent_id
    assert config.poll_interval_seconds >= 1
    assert config.max_concurrency >= 1


def test_browser_agent_config_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_AGENT_ID", "agent-test")
    monkeypatch.setenv("BROWSER_AGENT_MAX_CONCURRENCY", "3")
    config = BrowserAgentConfig.from_env()
    assert config.agent_id == "agent-test"
    assert config.max_concurrency == 3


def test_browser_agent_client_refreshes_token_before_expiry(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    config = BrowserAgentConfig.from_env()
    client = BrowserAgentTallyClient(config=config)
    first = client.worker_token
    # Force expiry deadline to past so the next access triggers refresh.
    client._token_expires_at = 0
    # Sleep one second to guarantee a different `iat` in the new JWT payload.
    time.sleep(1.1)
    second = client.worker_token
    assert first != second


def test_browser_agent_client_sends_heartbeat() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeSession:
        async def call_tool(self, tool_name, args):
            calls.append((tool_name, args))
            return {"success": True, "agent": {"agent_id": args["agent_id"], "status": "online"}}

    config = BrowserAgentConfig(
        agent_id="browser-agent-local",
        company_id="company-001",
        mcp_base_url="http://127.0.0.1:3335",
        poll_interval_seconds=1,
        max_concurrency=2,
        waiting_poll_interval_seconds=30,
        heartbeat_interval_seconds=30,
    )
    client = BrowserAgentTallyClient(config=config, session=FakeSession())

    import asyncio

    result = asyncio.run(client.heartbeat(company_id="company-001"))

    assert result["success"] is True
    assert calls[0][0] == "browser_agent_heartbeat"
    assert calls[0][1]["agent_id"] == "browser-agent-local"
    assert calls[0][1]["company_id"] == "company-001"
    assert calls[0][1]["worker_token"]
