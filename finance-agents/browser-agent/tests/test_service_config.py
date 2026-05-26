from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.tally_client import BrowserAgentConfig


def test_browser_agent_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_AGENT_ID", "agent-test")
    monkeypatch.setenv("BROWSER_AGENT_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("BROWSER_AGENT_POLL_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("BROWSER_AGENT_WAITING_POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("DATA_AGENT_WS_URL", "wss://10.0.0.1/browser-agent")
    config = BrowserAgentConfig.from_env()
    assert config.agent_id == "agent-test"
    assert config.max_concurrency == 3
    assert config.poll_interval_seconds == 5
    assert config.waiting_poll_interval_seconds == 60
    assert config.data_agent_ws_url == "wss://10.0.0.1/browser-agent"


def test_browser_agent_config_min_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_AGENT_MAX_CONCURRENCY", "0")
    config = BrowserAgentConfig.from_env()
    assert config.max_concurrency == 1
