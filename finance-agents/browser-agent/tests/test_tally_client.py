from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient


class FakeWsClient:
    def __init__(self):
        self.calls = []
        self.next_result = {"ok_marker": True}

    async def request(self, msg_type, payload):
        self.calls.append((msg_type, dict(payload)))
        return self.next_result


def _config():
    return BrowserAgentConfig(
        agent_id="agent-A", company_id="c1", data_agent_ws_url="ws://test/browser-agent",
        poll_interval_seconds=2, max_concurrency=2,
        heartbeat_interval_seconds=30,
    )


def _client():
    ws = FakeWsClient()
    return BrowserAgentTallyClient(config=_config(), ws_client=ws), ws


@pytest.mark.asyncio
async def test_claim_sends_domain_claim_without_tool_name():
    client, ws = _client()
    await client.claim_browser_job()
    assert ws.calls[0][0] == "claim"
    assert "worker_token" not in ws.calls[0][1]
    assert "browser_sync_job_claim" not in str(ws.calls[0])


@pytest.mark.asyncio
async def test_heartbeat_carries_token_and_capabilities():
    client, ws = _client()
    await client.heartbeat()
    msg_type, payload = ws.calls[0]
    assert msg_type == "heartbeat"
    assert payload["token"]
    assert payload["company_id"] == "c1"
    assert "capabilities" in payload


@pytest.mark.asyncio
async def test_complete_and_fail_map_to_domain_types():
    client, ws = _client()
    await client.mark_browser_job_success({"sync_job_id": "j1", "records": []})
    await client.mark_browser_job_failed({"sync_job_id": "j1", "fail_reason": "X"})
    types = [c[0] for c in ws.calls]
    assert types == ["job_complete", "job_fail"]
    assert ws.calls[0][1]["sync_job_id"] == "j1"


@pytest.mark.asyncio
async def test_heartbeat_includes_handoff_control_capabilities():
    client, ws = _client()
    await client.heartbeat(company_id="c1")
    msg_type, payload = ws.calls[0]
    caps = payload["capabilities"]
    assert "handoff_control" in caps
    assert "backend" in caps["handoff_control"]
    assert "status" in caps["handoff_control"]


def test_config_from_env_uses_data_agent_ws_url(monkeypatch):
    monkeypatch.setenv("DATA_AGENT_WS_URL", "wss://cloud/browser-agent")
    cfg = BrowserAgentConfig.from_env()
    assert cfg.data_agent_ws_url == "wss://cloud/browser-agent"
    assert not hasattr(cfg, "mcp_base_url")
