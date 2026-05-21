from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop
from finance_browser_agent.playwright_runner import (
    PlaywrightRunConfig,
    build_user_data_dir,
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

    assert profile_locks.keys == ["bank/profile-01"]


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
