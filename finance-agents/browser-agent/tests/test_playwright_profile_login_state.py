from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop
from finance_browser_agent.playwright_runner import (
    BrowserActionError,
    PlaywrightRunConfig,
    _execute_action,
    _profile_is_authenticated,
    build_user_data_dir,
    sanitize_profile_key,
    should_skip_login_action,
)


def test_build_user_data_dir_prefers_runtime_profile_ref_and_sanitizes(tmp_path) -> None:
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
    )

    user_data_dir = build_user_data_dir(
        config=config,
        shop_id="shop-a",
        runtime_profile_ref="../bank/profile-01",
    )

    assert user_data_dir == str(tmp_path / "profiles" / "bankprofile-01")


def test_should_skip_login_action_only_skips_login_steps_when_authenticated() -> None:
    assert should_skip_login_action({"action": "login"}, authenticated=True) is True
    assert should_skip_login_action({"action": "login_if_needed"}, authenticated=True) is True
    assert should_skip_login_action({"action": "login"}, authenticated=False) is False
    assert should_skip_login_action({"action": "click"}, authenticated=True) is False


class FakePage:
    def __init__(self, *, url: str = "about:blank", selectors: set[str] | None = None) -> None:
        self.url = url
        self.selectors = selectors or set()
        self.gotos: list[tuple[str, str, int]] = []
        self.fills: list[tuple[str, str, int]] = []
        self.clicks: list[tuple[str, int]] = []
        self.waits: list[tuple[str, int]] = []

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.gotos.append((url, wait_until, timeout))
        self.url = url

    def content(self) -> str:
        return ""

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.waits.append((selector, timeout))
        if selector not in self.selectors:
            raise TimeoutError(selector)

    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        self.fills.append((selector, value, timeout))

    def click(self, selector: str, *, timeout: int) -> None:
        self.clicks.append((selector, timeout))


def test_login_if_needed_without_logged_in_selector_is_not_skipped_on_about_blank() -> None:
    page = FakePage(url="about:blank")

    authenticated = _profile_is_authenticated(page, {"auth_check": {}})

    assert authenticated is False
    assert should_skip_login_action({"action": "login_if_needed"}, authenticated=authenticated) is False


def test_profile_with_logged_in_selector_authenticates_when_selector_exists() -> None:
    page = FakePage(url="https://seller.example/home", selectors={".account-menu"})

    assert (
        _profile_is_authenticated(
            page,
            {"auth_check": {"logged_in_selector": ".account-menu", "timeout_ms": 1234}},
        )
        is True
    )
    assert page.waits == [(".account-menu", 1234)]
    assert should_skip_login_action({"action": "login_if_needed"}, authenticated=True) is True


def test_login_action_fills_credentials_clicks_submit_and_waits(tmp_path) -> None:
    page = FakePage(url="https://login.example", selectors={".dashboard"})

    _execute_action(
        page,
        {
            "action": "login",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert page.fills == [
        ("#username", "alice", 4321),
        ("#password", "secret", 4321),
    ]
    assert page.clicks == [("button[type='submit']", 4321)]
    assert page.waits == [(".dashboard", 4321)]


def test_navigate_allows_auth_redirect_when_login_step_follows(tmp_path) -> None:
    page = FakePage(url="about:blank")

    result = _execute_action(
        page,
        {
            "action": "navigate",
            "url": "https://login.taobao.com/member/login.htm",
            "timeout_ms": 1234,
        },
        params={},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        allow_auth_redirect=True,
    )

    assert result == {"auth_required": True}
    assert page.gotos == [("https://login.taobao.com/member/login.htm", "load", 1234)]


def test_navigate_still_fails_auth_redirect_without_login_step(tmp_path) -> None:
    page = FakePage(url="about:blank")

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "action": "navigate",
                "url": "https://login.taobao.com/member/login.htm",
                "timeout_ms": 1234,
            },
            params={},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
        )

    assert exc.value.fail_reason == "AUTH_EXPIRED"


def test_sanitize_profile_key_matches_runner_profile_dir() -> None:
    assert sanitize_profile_key("bank/profile-01") == "bankprofile-01"


class FakeClient:
    def __init__(self, job: dict[str, object]) -> None:
        self.jobs = [job]
        self.completed: list[dict] = []
        self.failed: list[dict] = []

    async def claim_browser_job(self) -> dict:
        if not self.jobs:
            return {"success": True, "job": None}
        return {"success": True, "job": self.jobs.pop(0)}

    async def mark_browser_job_success(self, payload: dict) -> dict:
        self.completed.append(payload)
        return {"success": True}

    async def mark_browser_job_failed(self, payload: dict) -> dict:
        self.failed.append(payload)
        return {"success": True}


class FakeProfileLocks:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def lock_for_shop(self, shop_id: str):
        self.keys.append(shop_id)
        return _FakeAsyncLock()


class _FakeAsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_dispatcher_profile_lock_prefers_runtime_profile_ref() -> None:
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "runtime_profile_ref": "bank/profile-01",
        "playbook_body": {"steps": []},
        "request_payload": {},
    }
    client = FakeClient(job)
    profile_locks = FakeProfileLocks()
    loop = BrowserDispatcherLoop(
        client=client,
        runner=lambda message: {
            "job_id": "sync-001",
            "status": "success",
            "records": [],
            "capture_files": [],
        },
        max_concurrency=1,
        profile_locks=profile_locks,
    )

    await loop.run_once()

    assert profile_locks.keys == ["bankprofile-01"]


@pytest.mark.asyncio
async def test_dispatcher_profile_lock_falls_back_to_shop_id() -> None:
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "runtime_profile_ref": "",
        "playbook_body": {"steps": []},
        "request_payload": {},
    }
    client = FakeClient(job)
    profile_locks = FakeProfileLocks()
    loop = BrowserDispatcherLoop(
        client=client,
        runner=lambda message: {
            "job_id": "sync-001",
            "status": "success",
            "records": [],
            "capture_files": [],
        },
        max_concurrency=1,
        profile_locks=profile_locks,
    )

    await loop.run_once()

    assert profile_locks.keys == ["shop-001"]
