from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import browser_handoff_gateway as hg


class FakeAgent:
    def __init__(self, agent_id: str = "agent-A") -> None:
        self.agent_id = agent_id
        self.token = "worker-token"
        self.sent: list[dict] = []

    async def send_event(self, payload: dict) -> None:
        self.sent.append(payload)


class FakeController:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_controller_open_starts_online_agent_and_revokes_previous(monkeypatch):
    hg.reset_for_tests()
    calls: list[tuple[str, dict]] = []

    async def fake_call(tool: str, args: dict):
        calls.append((tool, args))
        if tool == "browser_handoff_session_describe":
            return {
                "success": True,
                "session": {
                    "handoff_session_id": "h1",
                    "sync_job_id": "j1",
                    "agent_id": "agent-A",
                    "profile_key": "店铺A",
                    "reason": "RISK_VERIFICATION",
                    "status": "pending",
                    "expires_at": "2026-05-25T12:00:00Z",
                },
            }
        if tool == "browser_handoff_session_control_open":
            return {
                "success": True,
                "session": {
                    "handoff_session_id": "h1",
                    "sync_job_id": "j1",
                    "agent_id": "agent-A",
                    "profile_key": "店铺A",
                    "reason": "RISK_VERIFICATION",
                    "status": "active",
                    "controller_id": args["controller_id"],
                    "expires_at": "2026-05-25T12:00:00Z",
                },
            }
        return {"success": True}

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    agent = FakeAgent()
    await hg.register_browser_agent(
        agent_id="agent-A",
        token="worker-token",
        send_event=agent.send_event,
    )

    first = FakeController()
    first_controller = await hg.open_controller(token="TKN", send_json=first.send_json)
    second = FakeController()
    second_controller = await hg.open_controller(token="TKN", send_json=second.send_json)

    assert first_controller.controller_id != second_controller.controller_id
    assert any(msg["type"] == "controller_revoked" for msg in first.sent)
    assert agent.sent[-1]["type"] == "event"
    assert agent.sent[-1]["event"] == "handoff_start"
    assert agent.sent[-1]["handoff_session_id"] == "h1"


@pytest.mark.asyncio
async def test_controller_open_waits_when_agent_offline(monkeypatch):
    hg.reset_for_tests()

    async def fake_call(tool: str, args: dict):
        if tool == "browser_handoff_session_describe":
            return {
                "success": True,
                "session": {
                    "handoff_session_id": "h1",
                    "sync_job_id": "j1",
                    "agent_id": "agent-A",
                    "profile_key": "店铺A",
                    "reason": "RISK_VERIFICATION",
                    "status": "pending",
                    "expires_at": "2026-05-25T12:00:00Z",
                },
            }
        if tool == "browser_handoff_session_control_open":
            assert args["agent_online"] is False
            return {
                "success": True,
                "session": {
                    "handoff_session_id": "h1",
                    "agent_id": "agent-A",
                    "status": "waiting_agent",
                    "expires_at": "2026-05-25T12:00:00Z",
                },
            }
        raise AssertionError(tool)

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    controller = FakeController()

    await hg.open_controller(token="TKN", send_json=controller.send_json)

    assert any(msg["type"] == "status" and msg["status"] == "waiting_agent" for msg in controller.sent)


@pytest.mark.asyncio
async def test_frame_routes_only_to_current_controller(monkeypatch):
    hg.reset_for_tests()
    controller = FakeController()
    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1",
        controller_id="ctrl-current",
        token="TKN",
        session={"handoff_session_id": "h1", "agent_id": "agent-A"},
        send_json=controller.send_json,
    )

    await hg.route_agent_message(
        agent_id="agent-A",
        token="worker-token",
        msg={
            "type": "handoff_frame",
            "handoff_session_id": "h1",
            "controller_id": "ctrl-current",
            "frame_id": 1,
            "mime": "image/jpeg",
            "width": 100,
            "height": 80,
            "data": "abc",
        },
    )

    assert controller.sent == [{
        "type": "frame",
        "handoff_session_id": "h1",
        "frame_id": 1,
        "mime": "image/jpeg",
        "width": 100,
        "height": 80,
        "data": "abc",
    }]


@pytest.mark.asyncio
async def test_agent_message_from_wrong_agent_is_ignored(monkeypatch):
    hg.reset_for_tests()
    calls: list[tuple[str, dict]] = []

    async def fake_call(tool: str, args: dict):
        calls.append((tool, args))
        return {"success": True}

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    controller = FakeController()
    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1",
        controller_id="ctrl-current",
        token="TKN",
        session={"handoff_session_id": "h1", "agent_id": "agent-A"},
        send_json=controller.send_json,
    )

    frame_handled = await hg.route_agent_message(
        agent_id="agent-B",
        token="worker-token",
        msg={
            "type": "handoff_frame",
            "handoff_session_id": "h1",
            "controller_id": "ctrl-current",
            "frame_id": 1,
            "data": "abc",
        },
    )
    done_handled = await hg.route_agent_message(
        agent_id="agent-B",
        token="worker-token",
        msg={"type": "handoff_completed", "handoff_session_id": "h1"},
    )

    assert frame_handled is True
    assert done_handled is True
    assert controller.sent == []
    assert calls == []


@pytest.mark.asyncio
async def test_controller_input_and_resume_relay_to_agent(monkeypatch):
    hg.reset_for_tests()
    calls: list[tuple[str, dict]] = []

    async def fake_call(tool: str, args: dict):
        calls.append((tool, args))
        return {"success": True}

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    agent = FakeAgent()
    await hg.register_browser_agent(
        agent_id="agent-A",
        token="worker-token",
        send_event=agent.send_event,
    )
    controller_socket = FakeController()
    controller = hg.HandoffController(
        handoff_session_id="h1",
        controller_id="ctrl-current",
        token="TKN",
        session={"handoff_session_id": "h1", "agent_id": "agent-A"},
        send_json=controller_socket.send_json,
    )
    hg._controllers["h1"] = controller

    await hg.route_controller_message(
        controller,
        {"type": "handoff_input", "event": {"kind": "click", "x": 0.4, "y": 0.5}},
    )
    await hg.route_controller_message(controller, {"type": "resume_requested"})

    assert agent.sent[0]["event"] == "handoff_input"
    assert agent.sent[0]["input"]["kind"] == "click"
    assert agent.sent[1]["event"] == "handoff_resume_check"
    assert calls[-1] == (
        "browser_handoff_session_event",
        {
            "token": "TKN",
            "controller_id": "ctrl-current",
            "event_type": "resume_requested",
            "status": "resuming",
        },
    )
    assert any(msg["type"] == "status" and msg["status"] == "resuming" for msg in controller_socket.sent)


@pytest.mark.asyncio
async def test_agent_heartbeat_timeout_downgrades_active_to_waiting_then_expired(monkeypatch):
    hg.reset_for_tests()

    async def fake_call(tool, payload):
        return {"success": True}
    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)

    sent = []
    async def send(p):
        sent.append(p)

    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1", controller_id="c1", token="t",
        session={"agent_id": "agentA", "status": "active"}, send_json=send,
    )
    # 心跳超时(>30s)→ waiting_agent
    await hg.on_agent_heartbeat_timeout(agent_id="agentA", elapsed_seconds=31)
    assert any(p.get("status") == "waiting_agent" for p in sent)
    # 超过 5min → expired/failed
    await hg.on_agent_heartbeat_timeout(agent_id="agentA", elapsed_seconds=301)
    assert any(p.get("status") in {"expired", "failed"} for p in sent)


@pytest.mark.asyncio
async def test_agent_reports_control_unavailable_maps_to_web_status(monkeypatch):
    hg.reset_for_tests()

    async def fake_call(tool, payload):
        return {"success": True}
    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)

    sent = []
    async def send(p):
        sent.append(p)

    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1", controller_id="c1", token="t",
        session={"agent_id": "agentA"}, send_json=send,
    )
    handled = await hg.route_agent_message(
        agent_id="agentA", token="t",
        msg={"type": "handoff_control_status", "handoff_session_id": "h1",
             "code": "control_unavailable"},
    )
    assert handled is True
    assert sent[-1]["type"] == "status"
    assert sent[-1]["status"] == "control_unavailable"


@pytest.mark.asyncio
async def test_relay_does_not_log_frame_data_text_or_metadata(monkeypatch, caplog):
    import logging
    hg.reset_for_tests()

    async def fake_call(tool, payload):
        return {"success": True}
    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)

    sent = []
    async def send(p):
        sent.append(p)

    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1", controller_id="c1", token="t",
        session={"agent_id": "agentA"}, send_json=send,
    )
    hg._agents["agentA"] = hg.BrowserAgentPeer(agent_id="agentA", token="t", send_event=send)

    with caplog.at_level(logging.DEBUG):
        await hg.route_agent_message(agent_id="agentA", token="t", msg={
            "type": "handoff_frame", "handoff_session_id": "h1", "controller_id": "c1",
            "data": "BASE64SECRETFRAME", "window_title": "店铺机密标题",
        })
        await hg.route_controller_message(hg._controllers["h1"], {
            "type": "handoff_input", "event": {"kind": "text", "text": "SMSCODE123"},
        })

    blob = caplog.text
    assert "BASE64SECRETFRAME" not in blob
    assert "SMSCODE123" not in blob
    assert "店铺机密标题" not in blob


@pytest.mark.asyncio
async def test_agent_focus_state_relayed_to_controller(monkeypatch):
    hg.reset_for_tests()
    async def fake_call(tool, payload):
        return {"success": True}
    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    sent = []
    async def send(p):
        sent.append(p)
    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1", controller_id="c1", token="t",
        session={"agent_id": "agentA"}, send_json=send,
    )
    handled = await hg.route_agent_message(agent_id="agentA", token="t", msg={
        "type": "handoff_focus_state", "handoff_session_id": "h1", "editable": False,
    })
    assert handled is True
    assert sent[-1] == {"type": "focus_state", "editable": False}
