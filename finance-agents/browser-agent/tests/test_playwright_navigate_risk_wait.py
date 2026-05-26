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



def test_navigate_risk_wait_registers_handoff_backend(monkeypatch):
    class FakeRiskPage:
        url = "https://example.com/identity_verify"
        frames = []
        viewport_size = {"width": 100, "height": 80}

        def wait_for_timeout(self, delay_ms):
            return None

        def screenshot(self, **kwargs):
            return b"fake-jpeg"

    registered = []
    unregistered = []
    emitted_frames = []

    class FakeCoordinator:
        def register_backend(self, *, sync_job_id, backend):
            registered.append((sync_job_id, backend))
            backend.start_stream(
                handoff_session_id="h1",
                controller_id="ctrl-1",
                idle_fps=1000,
                interactive_fps=1000,
            )

        def unregister_backend(self, *, sync_job_id):
            unregistered.append(sync_job_id)

        async def emit_frame(self, **kwargs):
            emitted_frames.append(kwargs)

        async def emit_status(self, payload):
            return None

    from finance_browser_agent import playwright_runner as pr

    page = FakeRiskPage()
    monkeypatch.setattr(pr, "_detect_auth_or_risk", lambda context: "RISK_VERIFICATION")

    cleared = pr._wait_for_risk_to_clear_with_handoff(
        page,
        [page],
        timeout_ms=10,
        poll_interval_ms=1,
        sync_job_id="j1",
        coordinator=FakeCoordinator(),
    )

    assert cleared is False
    assert registered[0][0] == "j1"
    assert unregistered == ["j1"]
    assert emitted_frames[0]["sync_job_id"] == "j1"
    assert emitted_frames[0]["frame"]["mime"] == "image/jpeg"
