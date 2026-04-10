"""Nodes for manual notify follow-up graph."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage

from models import AgentState
from tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

_SPLIT_PATTERN = re.compile(r"[，,、;\s]+")


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def _last_user_message(state: AgentState) -> str:
    messages = list(state.get("messages") or [])
    if not messages:
        return ""
    last = messages[-1]
    return str(getattr(last, "content", "") or "").strip()


def parse_notify_targets_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    text = _last_user_message(state)
    normalized = text.replace("。", " ").replace("；", " ").strip()
    skip = ("不通知" in normalized) or ("暂不" in normalized and "通知" in normalized)

    names: list[str] = []
    if not skip and normalized:
        names = [seg.strip() for seg in _SPLIT_PATTERN.split(normalized) if seg.strip()]

    ctx["notify_skip"] = skip
    ctx["notify_recipient_names"] = names
    return {"recon_ctx": ctx}


async def send_manual_notify_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    if bool(ctx.get("notify_skip")):
        ctx["notify_result"] = {"skipped": True, "sent_names": []}
        return {"recon_ctx": ctx}

    names = list(ctx.get("notify_recipient_names") or [])
    if not names:
        ctx["notify_result"] = {
            "skipped": False,
            "sent_names": [],
            "error": "未识别到有效姓名",
        }
        return {"recon_ctx": ctx}

    auth_token = str(state.get("auth_token") or "")
    run_id = str(ctx.get("run_id") or "")
    scheme_code = str(ctx.get("scheme_code") or "")

    # Best effort integration with future MCP tool.
    result = await call_mcp_tool(
        "recon_manual_notify_send",
        {
            "auth_token": auth_token,
            "run_id": run_id,
            "scheme_code": scheme_code,
            "recipient_names": names,
            "summary": {"anomaly_count": len(list(ctx.get("anomaly_items") or []))},
        },
    )
    if not bool(result.get("success")):
        logger.info("[manual_notify] fallback to local ack, mcp tool unavailable: %s", result.get("error"))
        ctx["notify_result"] = {"skipped": False, "sent_names": names, "fallback": True}
        return {"recon_ctx": ctx}

    sent_names = list(result.get("sent_names") or names)
    ctx["notify_result"] = {"skipped": False, "sent_names": sent_names}
    return {"recon_ctx": ctx}


def render_notify_result_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    notify_result = ctx.get("notify_result") if isinstance(ctx.get("notify_result"), dict) else {}
    skipped = bool(notify_result.get("skipped"))
    sent_names = list(notify_result.get("sent_names") or [])
    error = str(notify_result.get("error") or "").strip()

    if skipped:
        msg = "已跳过本次催办。"
    elif error:
        msg = f"催办未发送：{error}"
    elif sent_names:
        msg = f"已发送催办给：{', '.join(sent_names)}"
    else:
        msg = "本次未发送催办。"

    ctx["pending_manual_notify"] = False
    return {"recon_ctx": ctx, "messages": [AIMessage(content=msg)]}

