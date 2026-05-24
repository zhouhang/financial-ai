from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import finance_browser_agent.playwright_runner as runner
from finance_browser_agent.playwright_runner import (
    BrowserActionError,
    PlaywrightRunConfig,
    _execute_action,
)


class FakeNavPage:
    def __init__(self):
        self.url = "https://example.com/bill"
        self.frames = []
    def goto(self, *a, **k):
        return None


def _config(timeout_ms: int) -> PlaywrightRunConfig:
    return PlaywrightRunConfig(
        profile_root="/tmp/p", download_root="/tmp/d", headless=True,
        timezone_id="Asia/Shanghai", browser_channel="chrome",
        risk_manual_timeout_ms=timeout_ms,
    )


def _navigate(page, config, **over):
    action = {"action": "navigate", "url": "https://example.com/bill", "id": "nav1"}
    kwargs = dict(params={}, extracted={}, capture_files=[], download_dir=Path("/tmp/d"),
                  allow_auth_redirect=False, run_config=config)
    kwargs.update(over)
    return _execute_action(page, action, **kwargs)


def test_navigate_risk_waits_then_resumes(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "RISK_VERIFICATION")
    calls = {"n": 0}
    def fake_wait(contexts, *, timeout_ms, poll_interval_ms=1000):
        calls["n"] += 1
        return True
    monkeypatch.setattr(runner, "_wait_for_risk_to_clear", fake_wait)
    result = _navigate(FakeNavPage(), _config(3000))
    assert result == {}
    assert calls["n"] == 1


def test_navigate_risk_timeout_raises(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "RISK_VERIFICATION")
    monkeypatch.setattr(runner, "_wait_for_risk_to_clear", lambda *a, **k: False)
    with pytest.raises(BrowserActionError) as exc:
        _navigate(FakeNavPage(), _config(3000))
    assert exc.value.fail_reason == "RISK_VERIFICATION"


def test_navigate_risk_no_wait_when_timeout_zero(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "RISK_VERIFICATION")
    def boom(*a, **k):
        raise AssertionError("timeout=0 不应等待")
    monkeypatch.setattr(runner, "_wait_for_risk_to_clear", boom)
    with pytest.raises(BrowserActionError) as exc:
        _navigate(FakeNavPage(), _config(0))
    assert exc.value.fail_reason == "RISK_VERIFICATION"


def test_navigate_auth_expired_redirect_unaffected(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "AUTH_EXPIRED")
    result = _navigate(FakeNavPage(), _config(3000), allow_auth_redirect=True)
    assert result == {"auth_required": True}
