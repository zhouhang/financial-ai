"""data-agent ↔ browser-agent WebSocket 网关(纯逻辑)。

校验采集机的 system JWT,把"领域消息"映射成 finance-mcp 工具调用并经 call_mcp_tool 转发,
注入 worker_token(连接级已校验 token)与 agent_id。data-agent 是唯一 finance-mcp 调用方。
"""
from __future__ import annotations

import logging
import os
from typing import Any

import jwt

from services.notifications import get_notification_adapter
from services.notifications.repository import load_company_channel_config_by_id
from tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

_JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
_JWT_ALG = "HS256"

_NOTIFIED_RISK_JOBS: set[str] = set()

# 领域消息类型 → finance-mcp 工具(白名单:只有这些可被采集机触发)
_DOMAIN_TOOL_MAP: dict[str, str] = {
    "claim": "browser_sync_job_claim",
    "heartbeat": "browser_agent_heartbeat",
    "self_check": "browser_agent_self_check",
    "startup_cleanup": "browser_sync_job_startup_cleanup",
    "job_complete": "browser_sync_job_complete",
    "job_fail": "browser_sync_job_fail",
    "queue_requeue_ready": "recon_queue_requeue_ready_waiting",
    "queue_fail_failed": "recon_queue_fail_failed_collection_waiting",
    "queue_fail_expired": "recon_queue_fail_expired_waiting",
}


def _force_handoff_to_alert_recipient() -> bool:
    """人工接管通知是否统一发给采集告警接收人(.env BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD,周行)。

    默认开启:当前采集账号都是该接管人的、风控短信码也发到其手机,所以接管必须找他。
    置 HANDOFF_FORCE_ALERT_RECIPIENT=false 可回到"按对账责任人(店主)路由接管通知"的旧行为。
    在调用时读取(非模块级常量),便于测试用 monkeypatch 切换。
    """
    return os.getenv("HANDOFF_FORCE_ALERT_RECIPIENT", "true").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_handoff_recipient(adapter: Any, owner: dict[str, Any]) -> str:
    recipient = str(owner.get("identifier") or owner.get("user_id") or "").strip()
    owner_name = str(owner.get("name") or owner.get("display_name") or "").strip()
    if not recipient:
        return ""
    try:
        resolved = adapter.resolve_user(user_id=recipient, keyword=owner_name)
    except Exception:
        logger.exception("handoff 责任人解析失败 owner=%s", owner)
        return recipient
    resolved_user = getattr(resolved, "resolved_user", None)
    resolved_user_id = str(getattr(resolved_user, "user_id", "") or "").strip()
    if bool(getattr(resolved, "success", False)) and resolved_user_id:
        return resolved_user_id
    return recipient


def _handoff_web_base_url() -> str:
    """Resolve the public web base URL for mobile handoff links."""
    for key in ("TALLY_PUBLIC_WEB_BASE_URL", "TALLY_WEB_BASE_URL", "PUBLIC_WEB_BASE_URL"):
        value = os.getenv(key, "").strip().rstrip("/")
        if value:
            return value

    value = os.getenv("TALLY_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if value.endswith("/api"):
        return value[:-4].rstrip("/")
    return value


def _build_handoff_link(token: str) -> str:
    base = _handoff_web_base_url()
    return f"{base}/handoff?t={token}" if base else f"/handoff?t={token}"



def _handoff_reason_label(reason: str) -> str:
    """Return a human-readable label for the handoff reason used in notifications."""
    if reason == "AUTH_EXPIRED":
        return "千牛登录已过期，请点击链接远程接管重新登录"
    return "采集店铺需要人工验证，请打开链接完成验证后点击“我已完成验证”"


def _notify_handoff_fallback(
    *, company_id: str, sync_job_id: str, shop_id: str, reason: str, link: str
) -> bool:
    """没配责任人(或主通道未发出)时的兜底:直接复用浏览器采集告警发送方法,把验证链接
    发给 BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD 解析出的接收人(不重写收件人解析/发送/去重)。"""
    try:
        from services.browser_alerts import BrowserAlertEvent, BrowserAlertService

        result = BrowserAlertService().send_alert(
            BrowserAlertEvent(
                event_type="risk_blocked",
                company_id=company_id,
                shop_id=shop_id,
                data_source_name="",
                sync_job_id=sync_job_id,
                reason=reason,
                message=(
                    f"采集店铺需要人工验证，请打开链接完成：[打开验证链接]({link})"
                    "（完成后点页面底部“我已完成验证”）"
                ),
            )
        )
        return str(result.get("status") or "") == "sent"
    except Exception:
        logger.exception("handoff 兜底通知发送失败 sync_job_id=%s", sync_job_id)
        return False


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
        elif msg_type in {"heartbeat", "startup_cleanup"}:
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
    created = await call_mcp_tool("browser_handoff_session_create", {
        "worker_token": conn.token, "company_id": company_id, "sync_job_id": sync_job_id,
        "agent_id": conn.agent_id, "profile_key": str(msg.get("shop_id") or ""),
        "reason": str(msg.get("reason") or "RISK_VERIFICATION"),
        "data_source_id": (msg.get("data_source_id") or None),
        # 链接 TTL 与采集机人工等待窗口对齐(45min),否则窗口未到链接先失效→重开提示"采集机暂未连接"
        "expires_in_seconds": 2700,
    })
    if not created.get("success"):
        return {"type": "result", "id": req_id, "ok": False, "error": str(created.get("error") or "create session failed")}
    token = created.get("handoff_token") or ""
    link = _build_handoff_link(str(token))
    owner = created.get("owner") or {}
    if not isinstance(owner, dict):
        owner = {}
    channel_id = str(created.get("channel_config_id") or "").strip()
    recipient = str(owner.get("identifier") or owner.get("user_id") or "").strip()
    reason = str(msg.get("reason") or "RISK_VERIFICATION")
    notified = False
    if _force_handoff_to_alert_recipient():
        # 人工接管通知统一发给 .env BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD(周行):采集账号与
        # 风控短信验证码都在该接管人处,接管链接必须发给他,而非店铺责任人(店主收不到码也接管不了)。
        # 对账差异通知仍按 owner(店主)经各自通道发送(不走这里),不受影响。
        # 设 HANDOFF_FORCE_ALERT_RECIPIENT=false 可恢复"按对账责任人路由"的旧行为。
        logger.info("handoff 统一发给采集接管人(周行) sync_job_id=%s", sync_job_id)
        notified = _notify_handoff_fallback(
            company_id=company_id,
            sync_job_id=sync_job_id,
            shop_id=str(msg.get("shop_id") or ""),
            reason=reason,
            link=link,
        )
    elif recipient:
        # 配了责任人:走 per-company 通道。通道缺失/发送失败只记日志,不兜底(兜底仅针对"没配责任人")。
        if channel_id:
            channel = load_company_channel_config_by_id(channel_id=channel_id)
            if channel is None:
                logger.warning("handoff 通知通道不存在或不可用 channel_id=%s sync_job_id=%s", channel_id, sync_job_id)
            else:
                try:
                    adapter = get_notification_adapter(provider=getattr(channel, "provider", ""), channel_config=channel)
                    target = _resolve_handoff_recipient(adapter, owner)
                    if target:
                        adapter.send_bot_message(
                            content=(
                                f"{_handoff_reason_label(reason)}\n\n"
                                f"[打开验证链接]({link})\n\n"
                                "完成后请点击页面底部“我已完成验证”。"
                            ),
                            content_type="markdown",
                            title="Tally 浏览器人工验证",
                            to_user_id=target,
                        )
                        notified = True
                except Exception:
                    logger.exception("handoff 通知发送失败 sync_job_id=%s", sync_job_id)
        else:
            logger.info("handoff 有责任人但未配置通知通道,跳过通知 sync_job_id=%s", sync_job_id)
    else:
        # 没配责任人 → 兜底发给 .env 的 BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD 接收人
        logger.info("handoff 无对账任务责任人,走采集告警兜底接收人 sync_job_id=%s", sync_job_id)
        notified = _notify_handoff_fallback(
            company_id=company_id,
            sync_job_id=sync_job_id,
            shop_id=str(msg.get("shop_id") or ""),
            reason=reason,
            link=link,
        )
    _NOTIFIED_RISK_JOBS.add(sync_job_id)
    return {"type": "result", "id": req_id, "ok": True,
            "data": {"handoff_session_id": created.get("handoff_session_id"), "notified": notified}}
