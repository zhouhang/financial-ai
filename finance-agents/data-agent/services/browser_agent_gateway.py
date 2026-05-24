"""data-agent ↔ browser-agent WebSocket 网关(纯逻辑)。

校验采集机的 system JWT,把"领域消息"映射成 finance-mcp 工具调用并经 call_mcp_tool 转发,
注入 worker_token(连接级已校验 token)与 agent_id。data-agent 是唯一 finance-mcp 调用方。
"""
from __future__ import annotations

import logging
import os
from typing import Any

import jwt

from services.notifications import get_notification_adapter, load_company_channel_config
from tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

_JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
_JWT_ALG = "HS256"

_NOTIFIED_RISK_JOBS: set[str] = set()

# 领域消息类型 → finance-mcp 工具(白名单:只有这些可被采集机触发)
_DOMAIN_TOOL_MAP: dict[str, str] = {
    "claim": "browser_sync_job_claim",
    "heartbeat": "browser_agent_heartbeat",
    "job_complete": "browser_sync_job_complete",
    "job_fail": "browser_sync_job_fail",
    "queue_requeue_ready": "recon_queue_requeue_ready_waiting",
    "queue_fail_failed": "recon_queue_fail_failed_collection_waiting",
    "queue_fail_expired": "recon_queue_fail_expired_waiting",
}


def verify_system_token(token: str) -> dict[str, Any] | None:
    """校验 JWT 且必须 role=system,否则返回 None。"""
    try:
        payload = jwt.decode(str(token or ""), _JWT_SECRET, algorithms=[_JWT_ALG])
    except jwt.InvalidTokenError:
        return None
    if payload.get("role") != "system":
        return None
    return payload


class BrowserAgentConnection:
    """单条 WS 连接的状态:已校验 token + agent_id + max_concurrency。"""

    def __init__(self, *, token: str, agent_id: str, max_concurrency: int) -> None:
        self.token = token
        self.agent_id = agent_id
        self.max_concurrency = max_concurrency

    def _maybe_refresh_token(self, msg_type: str, msg: dict[str, Any]) -> None:
        if msg_type == "heartbeat" and msg.get("token"):
            self.token = str(msg["token"])

    def _build_args(self, msg_type: str, msg: dict[str, Any]) -> dict[str, Any]:
        payload = {k: v for k, v in msg.items() if k not in ("type", "id", "token")}
        args: dict[str, Any] = {"worker_token": self.token}
        if msg_type == "claim":
            args["agent_id"] = self.agent_id
            args["max_concurrency"] = self.max_concurrency
        elif msg_type == "heartbeat":
            args["agent_id"] = self.agent_id
            args.update(payload)
        else:
            args.update(payload)
        return args


async def handle_domain_message(conn: BrowserAgentConnection, msg: dict[str, Any]) -> dict[str, Any]:
    msg_type = str(msg.get("type") or "")
    req_id = str(msg.get("id") or "")
    if msg_type == "risk_waiting":
        return await _handle_risk_waiting(conn, msg)
    tool = _DOMAIN_TOOL_MAP.get(msg_type)
    if tool is None:
        return {"type": "result", "id": req_id, "ok": False, "error": f"未知消息类型: {msg_type}"}
    conn._maybe_refresh_token(msg_type, msg)
    args = conn._build_args(msg_type, msg)
    try:
        data = await call_mcp_tool(tool, args)
    except Exception as exc:  # noqa: BLE001 — 转成结果帧,避免拖垮 WS 循环
        return {"type": "result", "id": req_id, "ok": False, "error": str(exc)}
    return {"type": "result", "id": req_id, "ok": True, "data": data}


async def _handle_risk_waiting(conn: "BrowserAgentConnection", msg: dict) -> dict:
    req_id = str(msg.get("id") or "")
    sync_job_id = str(msg.get("sync_job_id") or "")
    company_id = str(msg.get("company_id") or "")
    if not sync_job_id or not company_id:
        return {"type": "result", "id": req_id, "ok": False, "error": "risk_waiting 缺 sync_job_id/company_id"}
    if sync_job_id in _NOTIFIED_RISK_JOBS:
        return {"type": "result", "id": req_id, "ok": True, "data": {"deduped": True}}
    channel = load_company_channel_config(company_id=company_id)
    channel_id = getattr(channel, "id", None) if channel else None
    created = await call_mcp_tool("browser_handoff_session_create", {
        "worker_token": conn.token, "company_id": company_id, "sync_job_id": sync_job_id,
        "agent_id": conn.agent_id, "profile_key": str(msg.get("shop_id") or ""),
        "reason": str(msg.get("reason") or "RISK_VERIFICATION"),
        "data_source_id": (msg.get("data_source_id") or None),
        "channel_config_id": channel_id,
    })
    if not created.get("success"):
        return {"type": "result", "id": req_id, "ok": False, "error": str(created.get("error") or "create session failed")}
    token = created.get("handoff_token") or ""
    base = os.getenv("TALLY_PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base}/p/handoff?t={token}" if base else f"/p/handoff?t={token}"
    if channel is not None:
        try:
            adapter = get_notification_adapter(provider=getattr(channel, "provider", ""), channel_config=channel)
            adapter.send_bot_message(
                content=f"采集店铺需要人工验证({msg.get('reason') or 'RISK_VERIFICATION'})。请在采集机上完成验证,或查看详情:{link}",
                to_user_id="",
            )
        except Exception:
            logger.exception("handoff 通知发送失败 sync_job_id=%s", sync_job_id)
    _NOTIFIED_RISK_JOBS.add(sync_job_id)
    return {"type": "result", "id": req_id, "ok": True,
            "data": {"handoff_session_id": created.get("handoff_session_id"), "notified": channel is not None}}
