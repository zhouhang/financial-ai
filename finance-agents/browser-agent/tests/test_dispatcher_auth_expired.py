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
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from finance_browser_agent import data_agent_ws as data_agent_ws_module
from finance_browser_agent.data_agent_ws import DataAgentWsClient
from finance_browser_agent import dispatcher_loop as dl_module
from finance_browser_agent.playbook_interpreter import validate_step_actions
from finance_browser_agent import playwright_runner as pr
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


class _FakeLoginModeCandidate:
    """Records click attempts; only succeeds for configured selectors."""

    def __init__(self, succeeds_for: set[str]) -> None:
        self.succeeds_for = succeeds_for
        self.click_attempts: list[str] = []

    def click(self, selector: str, timeout: int = 0) -> None:
        self.click_attempts.append(selector)
        if selector not in self.succeeds_for:
            raise RuntimeError(f"no such element: {selector}")


class _FakeRiskyLoginModeCandidate(_FakeLoginModeCandidate):
    url = "https://fxg.jinritemai.com/login/common"
    typed: list[tuple[str, str]]

    def __init__(self, succeeds_for: set[str]) -> None:
        super().__init__(succeeds_for)
        self.typed = []

    def locator(self, _selector: str):
        page = self
        selector = _selector

        class _First:
            def inner_text(self, timeout: int = 0) -> str:
                if page.click_attempts:
                    return "邮箱登录"
                return "手机登录 请输入验证码 获取验证码 邮箱登录"

            def wait_for(self, timeout: int = 0) -> None:
                if not page.click_attempts:
                    raise RuntimeError("login controls are not visible yet")

            def input_value(self, timeout: int = 0) -> str:
                for filled_selector, value in reversed(page.typed):
                    if filled_selector == selector:
                        return value
                return ""

        class _Locator:
            first = _First()

        return _Locator()

    def content(self) -> str:
        if self.click_attempts:
            return "邮箱登录"
        return "手机登录 请输入验证码 获取验证码 邮箱登录"

    def fill(self, selector: str, value: str, timeout: int = 0) -> None:
        if not self.click_attempts:
            raise RuntimeError("login controls are not visible yet")
        self.typed.append((selector, value))

    def wait_for_timeout(self, delay_ms: int) -> None:
        return None


class _FakeLoginWithAgreementCandidate(_FakeRiskyLoginModeCandidate):
    agreement_checked = False

    def click(self, selector: str, timeout: int = 0) -> None:
        self.click_attempts.append(selector)
        if selector == "input[type=checkbox]":
            self.agreement_checked = True
            return
        if selector not in self.succeeds_for:
            raise RuntimeError(f"no such element: {selector}")


class _FakeNavigateSmsLoginPage:
    url = "https://fxg.jinritemai.com/login/common"

    def __init__(self) -> None:
        self.goto_calls: list[str] = []

    def goto(self, url: str, wait_until: str = "load", timeout: int = 0) -> None:
        self.goto_calls.append(url)

    def locator(self, _selector: str):
        class _First:
            def inner_text(self, timeout: int = 0) -> str:
                return "手机登录 请输入验证码 获取验证码 邮箱登录"

        class _Locator:
            first = _First()

        return _Locator()

    def content(self) -> str:
        return "手机登录 请输入验证码 获取验证码 邮箱登录"


class _FakeRiskVerificationPage:
    url = "https://fxg.jinritemai.com/login/common"
    frames: list[Any] = []

    def locator(self, _selector: str):
        class _First:
            def inner_text(self, timeout: int = 0) -> str:
                return "请完成下列验证后继续 按住左边按钮拖动完成上方拼图"

        class _Locator:
            first = _First()

        return _Locator()

    def content(self) -> str:
        return "请完成下列验证后继续 按住左边按钮拖动完成上方拼图"

    def wait_for_timeout(self, delay_ms: int) -> None:
        return None


class _FakeOptionalClickLocator:
    def __init__(self, page: "_FakeOptionalClickPage", selector: str = "") -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "_FakeOptionalClickLocator":
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        if self.page.visible_selectors is not None:
            return self.selector in self.page.visible_selectors
        return self.page.visible


class _FakeOptionalClickPage:
    def __init__(
        self,
        *,
        visible: bool,
        visible_selectors: set[str] | None = None,
    ) -> None:
        self.visible = visible
        self.visible_selectors = visible_selectors
        self.clicks: list[str] = []

    def locator(self, selector: str) -> _FakeOptionalClickLocator:
        return _FakeOptionalClickLocator(self, selector)

    def click(self, selector: str, timeout: int = 0) -> None:
        self.clicks.append(selector)

    def wait_for_timeout(self, delay_ms: int) -> None:
        return None


class _FakePostLoginSelectorPage:
    url = "https://fxg.jinritemai.com/login/common"

    def __init__(self) -> None:
        self.waited_selectors: list[str] = []

    def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
        self.waited_selectors.append(selector)
        if selector == "text=请选择店铺":
            return
        raise RuntimeError(f"not found: {selector}")

    def locator(self, _selector: str):
        class _First:
            def inner_text(self, timeout: int = 0) -> str:
                return "请选择店铺 博宽数娱"

            def is_visible(self, timeout: int = 0) -> bool:
                return False

        class _Locator:
            first = _First()

        return _Locator()

    def content(self) -> str:
        return "请选择店铺 博宽数娱"


class _FakeLoginAlreadyAtShopPickerPage(_FakePostLoginSelectorPage):
    def __init__(self) -> None:
        super().__init__()
        self.typed: list[tuple[str, str]] = []

    def locator(self, selector: str):
        page = self

        class _First:
            def inner_text(self, timeout: int = 0) -> str:
                return "请选择店铺 博宽数娱"

            def is_visible(self, timeout: int = 0) -> bool:
                return selector == "text=请选择店铺"

            def wait_for(self, timeout: int = 0) -> None:
                if selector == "text=请选择店铺":
                    return
                raise RuntimeError(f"not found: {selector}")

            def input_value(self, timeout: int = 0) -> str:
                raise RuntimeError(f"not an input: {selector}")

        class _Locator:
            first = _First()

        return _Locator()

    def fill(self, selector: str, value: str, timeout: int = 0) -> None:
        self.typed.append((selector, value))
        raise RuntimeError("login fields are not visible")


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


async def test_default_ws_connector_disables_protocol_ping_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_connect(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.delenv("BROWSER_AGENT_WS_PING_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_WS_PING_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(data_agent_ws_module.websockets, "connect", fake_connect)

    result = await data_agent_ws_module._default_connector("wss://example.invalid/api/browser-agent")

    assert result is not None
    assert captured["url"] == "wss://example.invalid/api/browser-agent"
    assert captured["ping_interval"] is None
    assert captured["ping_timeout"] == 20.0
    assert captured["max_size"] is None
    assert captured["proxy"] is None


async def test_default_ws_connector_allows_protocol_ping_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_connect(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("BROWSER_AGENT_WS_PING_INTERVAL_SECONDS", "45")
    monkeypatch.setenv("BROWSER_AGENT_WS_PING_TIMEOUT_SECONDS", "90")
    monkeypatch.setattr(data_agent_ws_module.websockets, "connect", fake_connect)

    result = await data_agent_ws_module._default_connector("wss://example.invalid/api/browser-agent")

    assert result is not None
    assert captured["ping_interval"] == 45.0
    assert captured["ping_timeout"] == 90.0


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


def test_login_mode_click_prefers_playbook_selectors_before_builtin_tabs() -> None:
    candidate = _FakeLoginModeCandidate(succeeds_for={"text=邮箱登录"})

    clicked = pr._try_click_password_login_mode(
        [candidate],
        timeout_ms=1000,
        login_mode_selectors=["text=邮箱登录"],
    )

    assert clicked is True
    assert candidate.click_attempts[0] == "text=邮箱登录"


def test_login_mode_click_runs_before_risk_detection_for_configured_selector() -> None:
    candidate = _FakeRiskyLoginModeCandidate(
        succeeds_for={"text=邮箱登录", "button:has-text('登录')"}
    )

    context = pr._find_login_context(
        candidate,
        username_selector="#username",
        password_selector="#password",
        submit_selector="button:has-text('登录')",
        login_mode_selectors=["text=邮箱登录"],
        username="user@example.com",
        password="secret",
        timeout_ms=1000,
    )

    assert context is candidate
    assert candidate.click_attempts[0] == "text=邮箱登录"
    assert "button:has-text('登录')" in candidate.click_attempts


def test_navigate_sms_login_page_defers_to_following_login_step() -> None:
    page = _FakeNavigateSmsLoginPage()

    result = pr._execute_action(
        page,
        {
            "id": "open_order_list",
            "action": "navigate",
            "url": "https://fxg.jinritemai.com/ffa/morder/order/list",
        },
        params={},
        extracted={},
        capture_files=[],
        download_dir=Path("/tmp"),
        allow_auth_redirect=True,
    )

    assert result == {"auth_required": True}


def test_login_clicks_pre_submit_selectors_before_submit() -> None:
    candidate = _FakeLoginWithAgreementCandidate(
        succeeds_for={"text=邮箱登录", "button:has-text('登录')"}
    )

    context = pr._find_login_context(
        candidate,
        username_selector="#username",
        password_selector="#password",
        submit_selector="button:has-text('登录')",
        login_mode_selectors=["text=邮箱登录"],
        pre_submit_click_selectors=["input[type=checkbox]"],
        username="user@example.com",
        password="secret",
        timeout_ms=1000,
    )

    assert context is candidate
    assert candidate.click_attempts.index("input[type=checkbox]") < candidate.click_attempts.index(
        "button:has-text('登录')"
    )


def test_detects_slider_puzzle_verification_after_login_submit() -> None:
    assert pr._detect_auth_or_risk(_FakeRiskVerificationPage()) == "RISK_VERIFICATION"


def test_login_context_treats_slider_puzzle_as_risk_verification() -> None:
    run_config = pr.PlaywrightRunConfig(
        profile_root="/tmp/profiles",
        download_root="/tmp/downloads",
        headless=True,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        risk_manual_timeout_ms=1,
    )

    with pytest.raises(pr.BrowserActionError) as exc_info:
        pr._find_login_context(
            _FakeRiskVerificationPage(),
            username_selector="#username",
            password_selector="#password",
            submit_selector="button:has-text('登录')",
            username="user@example.com",
            password="secret",
            timeout_ms=1000,
            run_config=run_config,
        )

    assert exc_info.value.fail_reason == "RISK_VERIFICATION"


def test_click_if_present_clicks_visible_selector() -> None:
    page = _FakeOptionalClickPage(visible=True)

    result = pr._execute_action(
        page,
        {"id": "select_shop_if_present", "action": "click_if_present", "selector": "text=博宽数娱"},
        params={},
        extracted={},
        capture_files=[],
        download_dir=Path("/tmp"),
    )

    assert result == {}
    assert page.clicks == ["text=博宽数娱"]


def test_click_if_present_skips_missing_selector() -> None:
    page = _FakeOptionalClickPage(visible=False)

    result = pr._execute_action(
        page,
        {"id": "select_shop_if_present", "action": "click_if_present", "selector": "text=博宽数娱"},
        params={},
        extracted={},
        capture_files=[],
        download_dir=Path("/tmp"),
    )

    assert result == {"skipped": True}
    assert page.clicks == []


def test_click_if_present_tries_split_selector_candidates() -> None:
    page = _FakeOptionalClickPage(visible=False, visible_selectors={"text=博宽数娱"})

    result = pr._execute_action(
        page,
        {
            "id": "select_shop_if_present",
            "action": "click_if_present",
            "selector": "[class*='index_roleItem']:has-text('博宽数娱'), text=博宽数娱",
        },
        params={},
        extracted={},
        capture_files=[],
        download_dir=Path("/tmp"),
    )

    assert result == {}
    assert page.clicks == ["text=博宽数娱"]


def test_playbook_validator_accepts_optional_click_action() -> None:
    validate_step_actions([{"id": "select_shop_if_present", "action": "click_if_present"}])


def test_post_login_selector_splits_mixed_selector_candidates() -> None:
    page = _FakePostLoginSelectorPage()

    pr._wait_for_post_login_selector(
        page,
        login_context=page,
        selector=".auxo-btn-dashed, .auxo-pagination-next, text=请选择店铺",
        timeout_ms=1000,
    )

    assert "text=请选择店铺" in page.waited_selectors


def test_login_if_needed_returns_when_shop_picker_is_already_ready() -> None:
    page = _FakeLoginAlreadyAtShopPickerPage()

    pr._execute_login_action(
        page,
        {
            "id": "login_if_needed",
            "action": "login_if_needed",
            "username_selector": 'input[name="email"]',
            "password_selector": 'input[name="password"]',
            "submit_selector": 'button:has-text("登录")',
            "username_value": "merchant@example.com",
            "password_value": "secret",
            "post_login_wait_selector": ".auxo-btn-dashed, .auxo-pagination-next, text=请选择店铺",
        },
        params={},
        extracted={},
        timeout_ms=1000,
    )

    assert page.typed == []
