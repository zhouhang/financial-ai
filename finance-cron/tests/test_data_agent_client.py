from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location(
    "finance_cron_data_agent_client",
    PROJECT_ROOT / "data_agent_client.py",
)
assert spec and spec.loader
data_agent_client = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = data_agent_client
spec.loader.exec_module(data_agent_client)


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, object]:
        return dict(self._body)


class _FakeAsyncClient:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _FakeResponse:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_trigger_run_plan_retries_after_connect_error(monkeypatch) -> None:
    client = _FakeAsyncClient(
        [
            httpx.ConnectError("connect failed"),
            _FakeResponse(200, {"success": True, "run_plan_code": "plan_001"}),
        ]
    )

    monkeypatch.setattr(data_agent_client.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_count", lambda: 2)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_delay_seconds", lambda: 0.0)

    result = asyncio.run(
        data_agent_client.trigger_run_plan(
            "token",
            run_plan_code="plan_001",
            biz_date="2026-04-12",
            trigger_mode="manual",
        )
    )

    assert result["success"] is True
    assert client.calls == 2


def test_trigger_run_plan_retries_after_502(monkeypatch) -> None:
    client = _FakeAsyncClient(
        [
            _FakeResponse(502, {"detail": "bad gateway"}),
            _FakeResponse(200, {"success": True, "run_plan_code": "plan_001"}),
        ]
    )

    monkeypatch.setattr(data_agent_client.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_count", lambda: 2)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_delay_seconds", lambda: 0.0)

    result = asyncio.run(
        data_agent_client.trigger_run_plan(
            "token",
            run_plan_code="plan_001",
            biz_date="2026-04-12",
            trigger_mode="manual",
        )
    )

    assert result["success"] is True
    assert client.calls == 2


def test_sync_pending_todo_exceptions_posts_to_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _CapturingClient(_FakeAsyncClient):
        async def post(self, url, *, headers, json):
            captured["url"] = url
            captured["json"] = json
            return await super().post(url, headers=headers, json=json)

    client = _CapturingClient(
        [_FakeResponse(200, {"success": True, "completed": 2, "updated_count": 5})]
    )
    monkeypatch.setattr(data_agent_client.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_count", lambda: 1)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_delay_seconds", lambda: 0.0)

    result = asyncio.run(
        data_agent_client.sync_pending_todo_exceptions("token", limit=50, max_age_days=7)
    )

    assert result["success"] is True
    assert result["completed"] == 2
    assert captured["url"].endswith("/recon/exceptions/sync-pending-todos")
    assert captured["json"]["limit"] == 50
    assert captured["json"]["max_age_days"] == 7


def test_trigger_run_plan_treats_queued_response_as_success(monkeypatch) -> None:
    client = _FakeAsyncClient(
        [
            _FakeResponse(200, {"queued": True, "run_plan_code": "plan_001", "message": "submitted"}),
        ]
    )

    monkeypatch.setattr(data_agent_client.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_count", lambda: 1)
    monkeypatch.setattr(data_agent_client, "_get_local_request_retry_delay_seconds", lambda: 0.0)

    result = asyncio.run(
        data_agent_client.trigger_run_plan(
            "token",
            run_plan_code="plan_001",
            biz_date="2026-04-12",
            trigger_mode="schedule",
        )
    )

    assert result["success"] is True
    assert result["queued"] is True
    assert client.calls == 1
