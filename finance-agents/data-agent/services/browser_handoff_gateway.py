"""浏览器风控 handoff 的实时 WS 中转。

data-agent 只在内存中保存当前 agent/controller 连接和最新一帧,不落库截图或输入内容。
持久状态、token 校验和审计仍由 finance-mcp 的 handoff 工具负责。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class BrowserAgentPeer:
    agent_id: str
    token: str
    send_event: SendJson


@dataclass
class HandoffController:
    handoff_session_id: str
    controller_id: str
    token: str
    session: dict[str, Any]
    send_json: SendJson


_agents: dict[str, BrowserAgentPeer] = {}
_controllers: dict[str, HandoffController] = {}
_latest_frames: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


def reset_for_tests() -> None:
    _agents.clear()
    _controllers.clear()
    _latest_frames.clear()


def _is_expired(session: dict[str, Any]) -> bool:
    expires_at = str(session.get("expires_at") or "").strip()
    if not expires_at:
        return False
    try:
        normalized = expires_at.replace("Z", "+00:00")
        deadline = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= datetime.now(timezone.utc)


async def _mark_expired(controller: HandoffController, reason: str = "expired") -> None:
    await call_mcp_tool(
        "browser_handoff_session_expire",
        {"token": controller.token, "reason": reason},
    )
    await controller.send_json({
        "type": "status",
        "status": "expired",
        "reason": reason,
    })


async def _send_handoff_start(agent: BrowserAgentPeer, controller: HandoffController) -> None:
    await agent.send_event({
        "type": "event",
        "event": "handoff_start",
        "handoff_session_id": controller.handoff_session_id,
        "controller_id": controller.controller_id,
        "sync_job_id": str(controller.session.get("sync_job_id") or ""),
        "frame_profile": {"idle_fps": 1, "interactive_fps": 5},
    })


async def register_browser_agent(*, agent_id: str, token: str, send_event: SendJson) -> None:
    peer = BrowserAgentPeer(agent_id=str(agent_id), token=str(token), send_event=send_event)
    async with _lock:
        _agents[peer.agent_id] = peer
        controllers = [
            controller
            for controller in _controllers.values()
            if str(controller.session.get("agent_id") or "") == peer.agent_id
        ]

    for controller in controllers:
        await call_mcp_tool(
            "browser_handoff_session_event",
            {
                "worker_token": peer.token,
                "handoff_session_id": controller.handoff_session_id,
                "agent_id": peer.agent_id,
                "event_type": "agent_connected",
                "status": "active",
            },
        )
        await controller.send_json({"type": "status", "status": "active"})
        await _send_handoff_start(peer, controller)


async def unregister_browser_agent(agent_id: str) -> None:
    normalized_agent_id = str(agent_id)
    async with _lock:
        _agents.pop(normalized_agent_id, None)
        affected = [
            controller
            for controller in _controllers.values()
            if str(controller.session.get("agent_id") or "") == normalized_agent_id
        ]

    for controller in affected:
        await controller.send_json({"type": "status", "status": "waiting_agent"})
        try:
            await call_mcp_tool(
                "browser_handoff_session_event",
                {
                    "token": controller.token,
                    "controller_id": controller.controller_id,
                    "event_type": "agent_offline",
                    "status": "waiting_agent",
                    "agent_id": normalized_agent_id,
                },
            )
        except Exception:
            logger.exception("记录 handoff agent_offline 失败 handoff_session_id=%s", controller.handoff_session_id)


async def open_controller(*, token: str, send_json: SendJson) -> HandoffController:
    described = await call_mcp_tool("browser_handoff_session_describe", {"token": token})
    if not described.get("success"):
        await send_json({
            "type": "error",
            "status": "expired",
            "error": str(described.get("error") or "链接无效"),
        })
        raise ValueError(str(described.get("error") or "链接无效"))

    session = dict(described.get("session") or {})
    handoff_session_id = str(session.get("handoff_session_id") or "")
    agent_id = str(session.get("agent_id") or "")
    controller_id = str(uuid.uuid4())

    async with _lock:
        old = _controllers.get(handoff_session_id)
        agent = _agents.get(agent_id)
        controller = HandoffController(
            handoff_session_id=handoff_session_id,
            controller_id=controller_id,
            token=token,
            session=session,
            send_json=send_json,
        )
        _controllers[handoff_session_id] = controller
        latest = _latest_frames.get(handoff_session_id)

    if old is not None:
        await old.send_json({
            "type": "controller_revoked",
            "handoff_session_id": handoff_session_id,
        })

    if _is_expired(session):
        await _mark_expired(controller, "expired")
        return controller

    opened = await call_mcp_tool(
        "browser_handoff_session_control_open",
        {
            "token": token,
            "controller_id": controller_id,
            "agent_online": agent is not None,
        },
    )
    if opened.get("success"):
        controller.session = dict(opened.get("session") or session)
    else:
        await send_json({
            "type": "error",
            "status": "expired",
            "error": str(opened.get("error") or "handoff session 无法打开"),
        })
        return controller

    status = str(controller.session.get("status") or ("active" if agent else "waiting_agent"))
    await send_json({
        "type": "session",
        "controller_id": controller_id,
        "session": controller.session,
        "status": status,
    })
    if latest:
        await send_json({"type": "frame", **latest})
    if agent is None:
        await send_json({"type": "status", "status": "waiting_agent"})
        return controller

    await _send_handoff_start(agent, controller)
    await call_mcp_tool(
        "browser_handoff_session_event",
        {
            "worker_token": agent.token,
            "handoff_session_id": handoff_session_id,
            "agent_id": agent.agent_id,
            "event_type": "stream_started",
            "status": "active",
        },
    )
    return controller


async def close_controller(controller: HandoffController) -> None:
    async with _lock:
        current = _controllers.get(controller.handoff_session_id)
        if current and current.controller_id == controller.controller_id:
            _controllers.pop(controller.handoff_session_id, None)
            agent = _agents.get(str(controller.session.get("agent_id") or ""))
        else:
            agent = None
    if agent is None:
        return
    await agent.send_event({
        "type": "event",
        "event": "handoff_stop",
        "handoff_session_id": controller.handoff_session_id,
        "controller_id": controller.controller_id,
    })
    await call_mcp_tool(
        "browser_handoff_session_event",
        {
            "worker_token": agent.token,
            "handoff_session_id": controller.handoff_session_id,
            "agent_id": agent.agent_id,
            "event_type": "stream_stopped",
            "status": "active",
        },
    )


async def route_controller_message(controller: HandoffController, msg: dict[str, Any]) -> None:
    if _is_expired(controller.session):
        await _mark_expired(controller, "expired")
        return

    async with _lock:
        current = _controllers.get(controller.handoff_session_id)
        agent = _agents.get(str(controller.session.get("agent_id") or ""))
    if current is None or current.controller_id != controller.controller_id:
        await controller.send_json({
            "type": "controller_revoked",
            "handoff_session_id": controller.handoff_session_id,
        })
        return
    if agent is None:
        await controller.send_json({"type": "status", "status": "waiting_agent"})
        return

    msg_type = str(msg.get("type") or "")
    if msg_type == "handoff_input":
        await agent.send_event({
            "type": "event",
            "event": "handoff_input",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
            "input": dict(msg.get("event") or {}),
        })
        return
    if msg_type == "resume_requested":
        await call_mcp_tool(
            "browser_handoff_session_event",
            {
                "token": controller.token,
                "controller_id": controller.controller_id,
                "event_type": "resume_requested",
                "status": "resuming",
            },
        )
        await controller.send_json({"type": "status", "status": "resuming"})
        await agent.send_event({
            "type": "event",
            "event": "handoff_resume_check",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
        })
        return
    if msg_type in {"client_hidden", "client_visible", "reconnect_stream"}:
        await agent.send_event({
            "type": "event",
            "event": "handoff_frame_rate",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
            "profile": "idle" if msg_type == "client_hidden" else "interactive",
        })
        return
    await controller.send_json({"type": "error", "error": f"未知消息类型: {msg_type}"})


async def route_agent_message(*, agent_id: str, token: str, msg: dict[str, Any]) -> bool:
    msg_type = str(msg.get("type") or "")
    handoff_session_id = str(msg.get("handoff_session_id") or "")
    if not msg_type.startswith("handoff_"):
        return False
    async with _lock:
        controller = _controllers.get(handoff_session_id)
    if controller and str(controller.session.get("agent_id") or "") != str(agent_id):
        logger.warning(
            "忽略非绑定 agent 的 handoff 消息 handoff_session_id=%s expected_agent=%s actual_agent=%s",
            handoff_session_id,
            controller.session.get("agent_id"),
            agent_id,
        )
        return True

    if msg_type == "handoff_frame":
        frame = {
            "handoff_session_id": handoff_session_id,
            "frame_id": int(msg.get("frame_id") or 0),
            "mime": str(msg.get("mime") or "image/jpeg"),
            "width": int(msg.get("width") or 0),
            "height": int(msg.get("height") or 0),
            "data": str(msg.get("data") or ""),
        }
        async with _lock:
            _latest_frames[handoff_session_id] = frame
        if controller and controller.controller_id == str(msg.get("controller_id") or ""):
            await controller.send_json({"type": "frame", **frame})
        return True

    if msg_type in {"handoff_completed", "handoff_still_blocked", "handoff_failed"}:
        event_type_by_msg = {
            "handoff_completed": "completed",
            "handoff_still_blocked": "still_blocked",
            "handoff_failed": "failed",
        }
        status_by_msg = {
            "handoff_completed": "completed",
            "handoff_still_blocked": "active",
            "handoff_failed": "failed",
        }
        event_type = event_type_by_msg[msg_type]
        status = status_by_msg[msg_type]
        await call_mcp_tool(
            "browser_handoff_session_event",
            {
                "worker_token": token,
                "handoff_session_id": handoff_session_id,
                "agent_id": agent_id,
                "event_type": event_type,
                "status": status,
                "reason": str(msg.get("reason") or ""),
            },
        )
        if controller:
            web_status = "still_blocked" if msg_type == "handoff_still_blocked" else status
            await controller.send_json({
                "type": "status",
                "status": web_status,
                "reason": str(msg.get("reason") or ""),
            })
        return True

    return False
