"""Unit tests for AUTH_EXPIRED auto-handoff notification in BrowserDispatcherLoop.

Verifies:
- AUTH_EXPIRED runner result triggers exactly one report_risk_waiting call.
- A second AUTH_EXPIRED job for the same shop on the same day is deduped.
- RISK_VERIFICATION path is unaffected (no extra notification beyond the existing
  on_risk_waiting callback mechanism tested elsewhere).
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from finance_browser_agent import data_agent_ws as data_agent_ws_module
from finance_browser_agent.data_agent_ws import DataAgentWsClient
from finance_browser_agent import dispatcher_loop as dl_module
from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop
from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient


def _make_job(
    *,
    job_id: str = "job-1",
    shop_id: str = "shop-42",
    company_id: str = "company-99",
) -> dict[str, Any]:
    return {
        "id": job_id,
        "shop_id": shop_id,
        "company_id": company_id,
        "data_source_id": "ds-1",
        "playbook_id": "pb-1",
        "playbook_body": {},
        "playbook_version": "1",
        "runtime_profile_ref": "",
        "egress_group": "",
        "credential_ref": "",
        "request_payload": {"params": {}},
    }


def _make_loop(runner_result: dict[str, Any]) -> tuple[BrowserDispatcherLoop, AsyncMock, list[dict]]:
    """Return (loop, mock_client, recorded_risk_waiting_calls)."""
    risk_calls: list[dict] = []

    async def fake_report_risk_waiting(
        *, sync_job_id: str, reason: str, company_id: str = "",
        shop_id: str = "", data_source_id: str = "",
    ) -> dict:
        risk_calls.append({
            "sync_job_id": sync_job_id,
            "reason": reason,
            "company_id": company_id,
            "shop_id": shop_id,
        })
        return {"success": True}

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(return_value={"job": _make_job()})
    client.mark_browser_job_failed = AsyncMock(return_value={"success": True})
    client.mark_browser_job_success = AsyncMock(return_value={"success": True})
    client.report_risk_waiting = fake_report_risk_waiting
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    def sync_runner(message: dict[str, Any]) -> dict[str, Any]:
        return runner_result

    loop = BrowserDispatcherLoop(client=client, runner=sync_runner, max_concurrency=1)
    return loop, client, risk_calls


@pytest.fixture(autouse=True)
def reset_notified_dict():
    """Isolate _AUTH_EXPIRED_NOTIFIED between tests."""
    dl_module._AUTH_EXPIRED_NOTIFIED.clear()
    yield
    dl_module._AUTH_EXPIRED_NOTIFIED.clear()


# ---------------------------------------------------------------------------
# Test 1: AUTH_EXPIRED triggers exactly one notification
# ---------------------------------------------------------------------------

async def test_auth_expired_triggers_notification():
    result = {
        "status": "failed",
        "fail_reason": "AUTH_EXPIRED",
        "error_info": {"message": "login.taobao.com redirect"},
    }
    loop, client, risk_calls = _make_loop(result)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    assert len(risk_calls) == 1
    assert risk_calls[0]["reason"] == "AUTH_EXPIRED"
    assert risk_calls[0]["shop_id"] == "shop-42"
    assert risk_calls[0]["company_id"] == "company-99"
    client.mark_browser_job_failed.assert_called_once()


async def test_auth_expired_not_renotified_after_live_handoff_callback():
    risk_calls: list[dict] = []

    async def fake_report_risk_waiting(
        *, sync_job_id: str, reason: str, company_id: str = "",
        shop_id: str = "", data_source_id: str = "",
    ) -> dict:
        risk_calls.append({
            "sync_job_id": sync_job_id,
            "reason": reason,
            "company_id": company_id,
            "shop_id": shop_id,
        })
        return {"success": True}

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(return_value={"job": _make_job()})
    client.mark_browser_job_failed = AsyncMock(return_value={"success": True})
    client.mark_browser_job_success = AsyncMock(return_value={"success": True})
    client.report_risk_waiting = fake_report_risk_waiting
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    def runner(message: dict[str, Any]) -> dict[str, Any]:
        message["on_risk_waiting"]("AUTH_EXPIRED")
        return {
            "status": "failed",
            "fail_reason": "AUTH_EXPIRED",
            "error_info": {"message": "manual handoff timed out"},
        }

    loop = BrowserDispatcherLoop(client=client, runner=runner, max_concurrency=1)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    assert len(risk_calls) == 1
    assert risk_calls[0]["reason"] == "AUTH_EXPIRED"
    client.mark_browser_job_failed.assert_called_once()


async def test_dispatcher_passes_event_loop_to_runner_message():
    seen_loop: asyncio.AbstractEventLoop | None = None

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(return_value={"job": _make_job()})
    client.mark_browser_job_success = AsyncMock(return_value={"success": True})
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    def runner(message: dict[str, Any]) -> dict[str, Any]:
        nonlocal seen_loop
        seen_loop = message.get("handoff_event_loop")
        return {"status": "success", "records": [], "capture_files": []}

    loop = BrowserDispatcherLoop(client=client, runner=runner, max_concurrency=1)

    outcome = await loop.run_once()

    assert outcome["status"] == "success"
    assert seen_loop is asyncio.get_running_loop()


# ---------------------------------------------------------------------------
# Test 2: Second AUTH_EXPIRED for same shop same day → deduped (no second call)
# ---------------------------------------------------------------------------

async def test_auth_expired_deduped_same_shop_same_day():
    result = {
        "status": "failed",
        "fail_reason": "AUTH_EXPIRED",
        "error_info": {"message": "login redirect"},
    }
    loop, client, risk_calls = _make_loop(result)

    # Pre-mark today's notification for this shop as already sent
    dl_module._AUTH_EXPIRED_NOTIFIED["shop-42"] = date.today()

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    # No new notification because deduped
    assert len(risk_calls) == 0
    client.mark_browser_job_failed.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: RISK_VERIFICATION does NOT trigger the AUTH_EXPIRED notification path
# ---------------------------------------------------------------------------

async def test_risk_verification_does_not_trigger_auth_expired_notification():
    result = {
        "status": "failed",
        "fail_reason": "RISK_VERIFICATION",
        "error_info": {"message": "captcha required"},
    }
    loop, client, risk_calls = _make_loop(result)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    # report_risk_waiting is called by _on_risk_waiting callback from within the
    # runner (sync thread), not by our new AUTH_EXPIRED path.
    # Our new path must NOT have injected any risk_calls for RISK_VERIFICATION.
    assert len(risk_calls) == 0


async def test_target_closed_failure_is_reported_as_terminal_browser_closed():
    result = {
        "status": "failed",
        "fail_reason": "OTHER",
        "error_info": {
            "message": "Page.wait_for_timeout: Target page, context or browser has been closed"
        },
    }
    loop, client, _risk_calls = _make_loop(result)

    outcome = await loop.run_once()

    assert outcome["status"] == "failed"
    client.mark_browser_job_failed.assert_called_once()
    payload = client.mark_browser_job_failed.call_args.args[0]
    assert payload["fail_reason"] == "BROWSER_CLOSED"
    assert payload["retryable"] is False


# ---------------------------------------------------------------------------
# Test 4: Different shops on the same day each get their own notification
# ---------------------------------------------------------------------------

async def test_auth_expired_different_shops_each_notified():
    """Two distinct shops both fail with AUTH_EXPIRED → two notifications sent."""
    risk_calls: list[dict] = []

    async def fake_report_risk_waiting(
        *, sync_job_id: str, reason: str, company_id: str = "",
        shop_id: str = "", data_source_id: str = "",
    ) -> dict:
        risk_calls.append({"sync_job_id": sync_job_id, "shop_id": shop_id})
        return {"success": True}

    result = {
        "status": "failed",
        "fail_reason": "AUTH_EXPIRED",
        "error_info": {"message": "redirect"},
    }

    jobs = [_make_job(job_id="j1", shop_id="shop-A"), _make_job(job_id="j2", shop_id="shop-B")]
    job_iter = iter(jobs)

    client = AsyncMock()
    client.claim_browser_job = AsyncMock(side_effect=[{"job": j} for j in jobs])
    client.mark_browser_job_failed = AsyncMock(return_value={"success": True})
    client.report_risk_waiting = fake_report_risk_waiting
    client.handoff_coordinator = None
    client.handoff_backend_factory = None

    loop = BrowserDispatcherLoop(
        client=client,
        runner=lambda msg: result,
        max_concurrency=1,
    )

    await loop.run_once()  # shop-A
    await loop.run_once()  # shop-B

    notified_shops = {c["shop_id"] for c in risk_calls}
    assert "shop-A" in notified_shops
    assert "shop-B" in notified_shops
    assert len(risk_calls) == 2


class _FakeWs:
    def __init__(self, *, disconnect_first_request: bool = False) -> None:
        self.disconnect_first_request = disconnect_first_request
        self.sent: list[dict[str, Any]] = []
        self._queue: asyncio.Queue[Any] = asyncio.Queue()

    async def send(self, raw: str) -> None:
        msg = json.loads(raw)
        self.sent.append(msg)
        msg_type = str(msg.get("type") or "")
        if msg_type == "hello":
            return
        if self.disconnect_first_request:
            await self._queue.put(ConnectionError("data-agent WS 已断开"))
            return
        await self._queue.put(
            json.dumps(
                {
                    "type": "result",
                    "id": msg.get("id"),
                    "ok": True,
                    "data": {"success": True, "sync_job_id": msg.get("sync_job_id")},
                }
            )
        )

    async def recv(self) -> str:
        return json.dumps({"type": "hello_ack", "ok": True})

    def __aiter__(self) -> "_FakeWs":
        return self

    async def __anext__(self) -> str:
        item = await self._queue.get()
        if isinstance(item, BaseException):
            raise item
        return str(item)

    async def close(self) -> None:
        return None


async def test_ws_request_retries_idempotent_completion_after_disconnect() -> None:
    sockets = [_FakeWs(disconnect_first_request=True), _FakeWs()]
    created_sockets: list[_FakeWs] = []

    async def connector(_url: str) -> _FakeWs:
        socket = sockets.pop(0)
        created_sockets.append(socket)
        return socket

    client = DataAgentWsClient(
        ws_url="ws://data-agent/browser-agent",
        agent_id="agent-1",
        max_concurrency=1,
        token_provider=lambda: "token",
        connector=connector,
    )

    result = await client.request(
        "job_complete",
        {"sync_job_id": "sync-001"},
        retry_on_disconnect=True,
    )

    assert result == {"success": True, "sync_job_id": "sync-001"}
    assert [msg["type"] for msg in created_sockets[0].sent] == ["hello", "job_complete"]
    assert [msg["type"] for msg in created_sockets[1].sent] == ["hello", "job_complete"]


async def test_ws_request_retries_idempotent_completion_after_transient_server_error() -> None:
    class _TransientErrorWs(_FakeWs):
        def __init__(self, *, transient_failures: int = 1) -> None:
            super().__init__()
            self.transient_failures = transient_failures

        async def send(self, raw: str) -> None:
            msg = json.loads(raw)
            self.sent.append(msg)
            msg_type = str(msg.get("type") or "")
            if msg_type == "hello":
                return
            if len([sent for sent in self.sent if sent.get("type") == msg_type]) <= self.transient_failures:
                await self._queue.put(
                    json.dumps(
                        {
                            "type": "result",
                            "id": msg.get("id"),
                            "ok": False,
                            "error": "无法建立 MCP SSE 连接",
                        }
                    )
                )
                return
            await self._queue.put(
                json.dumps(
                    {
                        "type": "result",
                        "id": msg.get("id"),
                        "ok": True,
                        "data": {"success": True, "sync_job_id": msg.get("sync_job_id")},
                    }
                )
            )

    socket = _TransientErrorWs()

    async def connector(_url: str) -> _TransientErrorWs:
        return socket

    client = DataAgentWsClient(
        ws_url="ws://data-agent/browser-agent",
        agent_id="agent-1",
        max_concurrency=1,
        token_provider=lambda: "token",
        connector=connector,
    )

    result = await client.request(
        "job_complete",
        {"sync_job_id": "sync-002"},
        retry_on_disconnect=True,
    )

    assert result == {"success": True, "sync_job_id": "sync-002"}
    assert [msg["type"] for msg in socket.sent] == ["hello", "job_complete", "job_complete"]


async def test_ws_request_keeps_retrying_idempotent_completion_through_restart_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_agent_ws_module, "_RETRY_BACKOFF_SECONDS", (0.0, 0.0, 0.0))

    class _RestartWindowWs(_FakeWs):
        async def send(self, raw: str) -> None:
            msg = json.loads(raw)
            self.sent.append(msg)
            msg_type = str(msg.get("type") or "")
            if msg_type == "hello":
                return
            if len([sent for sent in self.sent if sent.get("type") == msg_type]) <= 3:
                await self._queue.put(
                    json.dumps(
                        {
                            "type": "result",
                            "id": msg.get("id"),
                            "ok": False,
                            "error": "server rejected WebSocket connection: HTTP 502",
                        }
                    )
                )
                return
            await self._queue.put(
                json.dumps(
                    {
                        "type": "result",
                        "id": msg.get("id"),
                        "ok": True,
                        "data": {"success": True, "sync_job_id": msg.get("sync_job_id")},
                    }
                )
            )

    socket = _RestartWindowWs()

    async def connector(_url: str) -> _RestartWindowWs:
        return socket

    client = DataAgentWsClient(
        ws_url="ws://data-agent/browser-agent",
        agent_id="agent-1",
        max_concurrency=1,
        token_provider=lambda: "token",
        connector=connector,
    )

    result = await client.request(
        "job_complete",
        {"sync_job_id": "sync-003"},
        retry_on_disconnect=True,
    )

    assert result == {"success": True, "sync_job_id": "sync-003"}
    assert [msg["type"] for msg in socket.sent] == [
        "hello",
        "job_complete",
        "job_complete",
        "job_complete",
        "job_complete",
    ]


async def test_tally_client_marks_terminal_updates_as_disconnect_retryable() -> None:
    class FakeWsClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any], bool]] = []

        async def request(
            self,
            msg_type: str,
            payload: dict[str, Any],
            *,
            retry_on_disconnect: bool = False,
        ) -> dict[str, Any]:
            self.calls.append((msg_type, payload, retry_on_disconnect))
            return {"success": True}

        async def send_event(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"success": True}

    fake_ws = FakeWsClient()
    client = BrowserAgentTallyClient(
        config=BrowserAgentConfig(
            agent_id="agent-1",
            company_id="company-1",
            data_agent_ws_url="ws://data-agent/browser-agent",
            poll_interval_seconds=1,
            max_concurrency=1,
            heartbeat_interval_seconds=30,
        ),
        ws_client=fake_ws,
    )

    await client.mark_browser_job_success({"sync_job_id": "sync-success"})
    await client.mark_browser_job_failed({"sync_job_id": "sync-fail"})

    assert fake_ws.calls == [
        ("job_complete", {"sync_job_id": "sync-success"}, True),
        ("job_fail", {"sync_job_id": "sync-fail"}, True),
    ]
