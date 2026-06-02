from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop


class FakeClient:
    def __init__(self, jobs: list[dict], result: dict) -> None:
        self.jobs = jobs
        self.result = result
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


@pytest.mark.asyncio
async def test_dispatcher_completes_successful_job() -> None:
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "playbook_body": {"steps": [], "output": {"columns": [], "item_key_fields": []}, "quality_gate": {}},
        "request_payload": {"biz_date": "2026-05-18"},
    }
    client = FakeClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] == "success"
    assert client.completed[0]["sync_job_id"] == "sync-001"


@pytest.mark.asyncio
async def test_dispatcher_fails_deterministic_error_without_retry() -> None:
    job = {"id": "sync-001", "shop_id": "shop-001", "playbook_body": {"steps": []}, "request_payload": {}}
    client = FakeClient(
        [job],
        {"job_id": "sync-001", "status": "failed", "fail_reason": "AUTH_EXPIRED", "error_info": {"message": "login expired"}},
    )
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] == "failed"
    assert client.failed[0]["retryable"] is False
    assert client.failed[0]["fail_reason"] == "AUTH_EXPIRED"


@pytest.mark.asyncio
async def test_dispatcher_passes_retry_policy_for_transient_error() -> None:
    job = {"id": "sync-001", "shop_id": "shop-001", "playbook_body": {"steps": []}, "request_payload": {}}
    client = FakeClient(
        [job],
        {"job_id": "sync-001", "status": "failed", "fail_reason": "TIMEOUT", "error_info": {"message": "timeout"}},
    )
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] == "failed"
    assert client.failed[0]["retryable"] is True
    assert client.failed[0]["max_attempts"] == 3
    assert client.failed[0]["retry_delay_seconds"] == 1800


@pytest.mark.asyncio
async def test_dispatcher_builds_message_from_claim_enrichment_not_raw_payload() -> None:
    captured: dict[str, dict] = {}
    job = {
        "id": "sync-001",
        "company_id": "company-001",
        "request_payload": {"biz_date": "2026-05-18"},
        "shop_id": "shop-001",
        "playbook_id": "qianniu-daily-bill-export",
        "playbook_version": "1.0.0",
        "playbook_body": {"steps": [], "output": {"columns": [], "item_key_fields": []}, "quality_gate": {}},
        "runtime_profile_ref": "profile-001",
        "egress_group": "wan-1",
        "credential_ref": "cred-001",
    }

    def runner(message: dict) -> dict:
        captured["message"] = message
        return {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []}

    client = FakeClient([job], {})
    loop = BrowserDispatcherLoop(client=client, runner=runner, max_concurrency=1)

    await loop.run_once()

    assert captured["message"]["shop_id"] == "shop-001"
    assert captured["message"]["company_id"] == "company-001"
    assert captured["message"]["playbook_body"] == job["playbook_body"]
    assert captured["message"]["runtime_profile_ref"] == "profile-001"
    assert captured["message"]["playbook_version"] == "1.0.0"


def test_dispatcher_message_injects_credentials_without_overwriting() -> None:
    loop = BrowserDispatcherLoop(client=FakeClient([], {}), runner=lambda message: message, max_concurrency=1)
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "playbook_id": "qianniu-income-daily-goods-bill-detail",
        "playbook_version": "1.0.0",
        "playbook_body": {"steps": []},
        "runtime_profile_ref": "profile-001",
        "egress_group": "",
        "credential_ref": (
            "enc:fallback:v1:"
            "eyJwYXNzd29yZCI6ICJzZWNyZXQiLCAidXNlcm5hbWUiOiAiZmluYW5jZV9vcHMifQ=="
        ),
    }
    payload = {
        "params": {
            "biz_date": "2026-05-21",
            "login_username": "manual_user",
        }
    }

    message = loop._message_from_job(job, payload)

    assert message["params"]["login_username"] == "manual_user"
    assert message["params"]["login_password"] == "secret"


def test_dispatcher_message_includes_handoff_coordinator_when_available() -> None:
    client = FakeClient([], {})
    client.handoff_coordinator = object()
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: message, max_concurrency=1)

    message = loop._message_from_job(
        {"id": "j1", "shop_id": "s1", "playbook_body": {}},
        {},
    )

    assert message["handoff_coordinator"] is client.handoff_coordinator


@pytest.mark.asyncio
async def test_dispatcher_runs_sync_runner_in_thread(monkeypatch) -> None:
    """Critical: sync Playwright must NOT block the event loop. Verify asyncio.to_thread is the path."""
    called: dict[str, bool] = {"to_thread": False}
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "playbook_body": {"steps": []},
        "request_payload": {},
    }
    client = FakeClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})

    async def fake_to_thread(func, *args, **kwargs):
        called["to_thread"] = True
        return func(*args, **kwargs)

    monkeypatch.setattr("finance_browser_agent.dispatcher_loop.asyncio.to_thread", fake_to_thread)
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    await loop.run_once()

    assert called["to_thread"] is True


class FailingCompleteClient(FakeClient):
    async def mark_browser_job_success(self, payload: dict) -> dict:
        self.completed.append(payload)
        return {"success": False, "error": "column \"storage_provider\" does not exist"}


@pytest.mark.asyncio
async def test_dispatcher_retries_when_completion_write_fails() -> None:
    job = {
        "id": "sync-001", "shop_id": "shop-001",
        "playbook_body": {"steps": [], "output": {"columns": [], "item_key_fields": []}, "quality_gate": {}},
        "request_payload": {"biz_date": "2026-05-31"},
    }
    client = FailingCompleteClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    # Must NOT report success when the server rejected the completion write.
    assert result["status"] != "success"
    assert client.failed, "expected a retryable failure to be recorded"
    assert client.failed[0]["retryable"] is True
    assert client.failed[0]["fail_reason"] == "COMPLETE_PERSIST_FAILED"


class RaisingCompleteClient(FakeClient):
    async def mark_browser_job_success(self, payload: dict) -> dict:
        self.completed.append(payload)
        raise RuntimeError("ws boom")


@pytest.mark.asyncio
async def test_dispatcher_retries_when_completion_call_raises() -> None:
    job = {
        "id": "sync-001", "shop_id": "shop-001",
        "playbook_body": {"steps": [], "output": {"columns": [], "item_key_fields": []}, "quality_gate": {}},
        "request_payload": {"biz_date": "2026-05-31"},
    }
    client = RaisingCompleteClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] != "success"
    assert client.failed
    assert client.failed[0]["retryable"] is True
    assert client.failed[0]["fail_reason"] == "COMPLETE_PERSIST_FAILED"


@pytest.mark.asyncio
async def test_dispatcher_create_worker_tasks_spawns_n_workers() -> None:
    client = FakeClient([], {"status": "success"})
    loop = BrowserDispatcherLoop(client=client, runner=lambda m: client.result, max_concurrency=2)

    import asyncio as _asyncio

    workers = loop.create_worker_tasks()
    try:
        assert len(workers) == 2
        for task in workers:
            assert not task.done()
    finally:
        for task in workers:
            task.cancel()
        await _asyncio.gather(*workers, return_exceptions=True)
