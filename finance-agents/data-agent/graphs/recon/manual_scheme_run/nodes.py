"""Nodes for manual scheme run graph."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage

from models import AgentState, ReconAgentPhase
from tools.mcp_client import call_mcp_tool, get_file_validation_rule
from graphs.recon.nodes import check_file_node_for_recon, recon_result_node

logger = logging.getLogger(__name__)


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def _is_unknown_tool_error(error: Any) -> bool:
    text = str(error or "").lower()
    return "unknown tool" in text or "未知的工具" in text or "no such tool" in text


async def load_scheme_node(state: AgentState) -> dict[str, Any]:
    """Load scheme config, fallback to selected recon rule for compatibility."""
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")

    scheme_code = str(
        ctx.get("scheme_code")
        or ctx.get("run_scheme_code")
        or ""
    ).strip()

    # First try execution_scheme model.
    if scheme_code and auth_token:
        scheme_result = await call_mcp_tool(
            "execution_scheme_get",
            {"auth_token": auth_token, "scheme_code": scheme_code},
        )
        if bool(scheme_result.get("success")):
            scheme = scheme_result.get("scheme") if isinstance(scheme_result.get("scheme"), dict) else {}
            scheme_meta = (
                scheme.get("scheme_meta_json")
                if isinstance(scheme.get("scheme_meta_json"), dict)
                else scheme.get("scheme_meta")
                if isinstance(scheme.get("scheme_meta"), dict)
                else scheme.get("meta")
                if isinstance(scheme.get("meta"), dict)
                else {}
            )
            embedded_rule = (
                scheme_meta.get("recon_rule_json")
                if isinstance(scheme_meta.get("recon_rule_json"), dict)
                else {}
            )
            recon_rule_code = str(
                scheme.get("recon_rule_code")
                or scheme.get("recon_rule")
                or scheme.get("rule_code")
                or ""
            ).strip()
            proc_rule_code = str(scheme.get("proc_rule_code") or "").strip()
            file_rule_code = str(
                scheme.get("file_rule_code")
                or ctx.get("file_rule_code")
                or state.get("file_rule_code")
                or ""
            ).strip()
            if embedded_rule:
                embedded_rule_code = recon_rule_code or f"embedded:{scheme_code or 'scheme'}"
                ctx.update(
                    {
                        "scheme_code": scheme_code,
                        "scheme": scheme,
                        "proc_rule_code": proc_rule_code,
                        "rule_code": embedded_rule_code,
                        "rule_name": str(
                            embedded_rule.get("rule_name")
                            or scheme_meta.get("recon_rule_name")
                            or scheme.get("name")
                            or embedded_rule_code
                        ),
                        "rule": embedded_rule,
                        "file_rule_code": file_rule_code or str(embedded_rule.get("file_rule_code") or "").strip(),
                        "phase": ReconAgentPhase.CHECKING_FILES.value,
                    }
                )
                return {"recon_ctx": ctx}
            if recon_rule_code:
                ctx.update(
                    {
                        "scheme_code": scheme_code,
                        "scheme": scheme,
                        "proc_rule_code": proc_rule_code,
                        "rule_code": recon_rule_code,
                        "rule_name": str(scheme.get("name") or recon_rule_code),
                        "file_rule_code": file_rule_code,
                        "phase": ReconAgentPhase.CHECKING_FILES.value,
                    }
                )
                return {"recon_ctx": ctx}
        else:
            error = scheme_result.get("error")
            if not _is_unknown_tool_error(error):
                logger.warning("[manual_scheme] execution_scheme_get failed: %s", error)

    # Compatibility fallback: use selected recon rule directly.
    rule_code = str(ctx.get("rule_code") or state.get("selected_rule_code") or "").strip()
    rule_name = str(ctx.get("rule_name") or state.get("selected_rule_name") or rule_code).strip()
    file_rule_code = str(ctx.get("file_rule_code") or state.get("file_rule_code") or "").strip()
    if not rule_code:
        ctx.update(
            {
                "phase": ReconAgentPhase.RULE_NOT_FOUND.value,
                "error": "未提供对账方案或对账规则。",
            }
        )
        return {
            "recon_ctx": ctx,
            "messages": [AIMessage(content="未提供对账方案或对账规则，请先在左侧选择对账规则。")],
        }

    rule_response = await get_file_validation_rule(rule_code, auth_token) if auth_token else {"success": False}
    if not rule_response.get("success"):
        ctx.update(
            {
                "phase": ReconAgentPhase.RULE_NOT_FOUND.value,
                "error": f"未找到规则: {rule_code}",
            }
        )
        return {
            "recon_ctx": ctx,
            "messages": [AIMessage(content=f"未找到规则：{rule_code}")],
        }

    rule_record = rule_response.get("data") if isinstance(rule_response.get("data"), dict) else {}
    rule_payload = rule_record.get("rule") if isinstance(rule_record.get("rule"), dict) else {}
    resolved_name = str(rule_payload.get("rule_name") or rule_record.get("name") or rule_name or rule_code)
    if not file_rule_code:
        file_rule_code = str(rule_payload.get("file_rule_code") or "").strip()

    ctx.update(
        {
            "scheme_code": scheme_code,
            "rule_code": rule_code,
            "rule_name": resolved_name,
            "rule": rule_payload,
            "file_rule_code": file_rule_code,
            "phase": ReconAgentPhase.CHECKING_FILES.value,
        }
    )
    return {"recon_ctx": ctx}


def resolve_manual_inputs_node(state: AgentState) -> dict[str, Any]:
    """Resolve manual input metadata and default run context."""
    ctx = _get_recon_ctx(state)
    run_context = ctx.get("run_context") if isinstance(ctx.get("run_context"), dict) else {}
    run_context.update(
        {
            "trigger_type": "chat",
            "entry_mode": "file",
        }
    )
    if not str(run_context.get("run_id") or "").strip():
        run_context["run_id"] = str(uuid.uuid4())
    if ctx.get("scheme_code"):
        run_context["scheme_code"] = str(ctx.get("scheme_code"))
    ctx["run_context"] = run_context
    ctx["run_id"] = str(run_context.get("run_id") or "")
    return {"recon_ctx": ctx}


async def check_manual_files_node(state: AgentState) -> dict[str, Any]:
    """Reuse existing file-check node for recon."""
    return await check_file_node_for_recon(state)


def build_manual_run_context_node(state: AgentState) -> dict[str, Any]:
    """Finalize run context before entering shared execution graph."""
    ctx = _get_recon_ctx(state)
    run_context = ctx.get("run_context") if isinstance(ctx.get("run_context"), dict) else {}
    run_context["trigger_type"] = str(run_context.get("trigger_type") or "chat")
    run_context["entry_mode"] = str(run_context.get("entry_mode") or "file")
    if ctx.get("scheme_code"):
        run_context["scheme_code"] = str(ctx.get("scheme_code"))
    ctx["run_context"] = run_context
    return {"recon_ctx": ctx}


def render_manual_result_node(state: AgentState) -> dict[str, Any]:
    """Render recon result with existing formatter."""
    return recon_result_node(state)


def maybe_offer_notify_node(state: AgentState) -> dict[str, Any]:
    """Offer manual notify follow-up when anomalies exist."""
    ctx = _get_recon_ctx(state)
    messages: list[AIMessage] = []
    status = str(ctx.get("exec_status") or "")
    anomalies = list(ctx.get("anomaly_items") or [])
    if status in {"success", "partial_success"} and anomalies:
        ctx["pending_manual_notify"] = True
        prompt = (
            "检测到本次对账存在异常。\n\n"
            "如需催办，请直接回复需要通知的人员姓名（可多个，使用顿号或逗号分隔）。\n"
            "回复“暂不通知”将跳过催办。"
        )
        messages.append(AIMessage(content=prompt))
    else:
        ctx["pending_manual_notify"] = False
    return {"recon_ctx": ctx, "messages": messages}
