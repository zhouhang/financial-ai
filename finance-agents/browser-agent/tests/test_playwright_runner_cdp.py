from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import finance_browser_agent.playwright_runner as runner


class FakePage:
    def __init__(self):
        self.url = "https://example.com"
    def wait_for_selector(self, *a, **k):
        return object()


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]
    def new_page(self):
        p = FakePage(); self.pages.append(p); return p
    def close(self):
        pass


class FakeBrowser:
    def __init__(self):
        self.contexts = [FakeContext()]
        self.closed = False
    def new_context(self, **k):
        c = FakeContext(); self.contexts.append(c); return c
    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser
        self.cdp_url = None
    def connect_over_cdp(self, url, **k):
        self.cdp_url = url
        return self._browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class FakeChrome:
    def __init__(self):
        self.port = 9999
        self.terminated = False
    @property
    def cdp_url(self):
        return f"http://127.0.0.1:{self.port}"
    def terminate(self):
        self.terminated = True


def test_runner_attaches_over_cdp_and_terminates_chrome(monkeypatch, tmp_path):
    fake_chrome = FakeChrome()
    fake_browser = FakeBrowser()
    fake_pw = FakePlaywright(fake_browser)

    monkeypatch.setattr(runner, "launch_chrome", lambda **k: fake_chrome)
    monkeypatch.setattr(runner, "sync_playwright", lambda: fake_pw)

    config = runner.PlaywrightRunConfig(
        profile_root=str(tmp_path / "p"), download_root=str(tmp_path / "d"),
        headless=False, timezone_id="Asia/Shanghai", browser_channel="chrome",
    )
    message = {
        "job_id": "j1", "shop_id": "s1", "runtime_profile_ref": "s1",
        "playbook_body": {"steps": [], "auth_check": {}},
        "params": {},
    }
    result = runner.run_playbook_with_playwright(message, config=config)

    assert fake_pw.chromium.cdp_url == fake_chrome.cdp_url
    assert fake_chrome.terminated is True
    assert isinstance(result, dict)


def test_runner_rejects_invalid_playbook_before_launching_chrome(monkeypatch, tmp_path):
    launched = {"called": False}

    def fake_launch_chrome(**kwargs):
        launched["called"] = True
        return FakeChrome()

    monkeypatch.setattr(runner, "launch_chrome", fake_launch_chrome)

    config = runner.PlaywrightRunConfig(
        profile_root=str(tmp_path / "p"), download_root=str(tmp_path / "d"),
        headless=False, timezone_id="Asia/Shanghai", browser_channel="chrome",
    )
    message = {
        "job_id": "j1",
        "shop_id": "s1",
        "runtime_profile_ref": "s1",
        "playbook_body": {"steps": [{"id": "request_detail_file", "action": "c lick"}]},
        "params": {},
    }

    result = runner.run_playbook_with_playwright(message, config=config)

    assert result["status"] == "failed"
    assert result["fail_reason"] == "OTHER"
    assert result["error_info"]["message"] == "unsupported action: c lick"
    assert launched["called"] is False
