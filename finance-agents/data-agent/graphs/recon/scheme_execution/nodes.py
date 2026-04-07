"""Nodes for shared scheme execution graph."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from models import AgentState
from graphs.recon.execution_service import (
    build_execution_request,
    build_recon_ctx_update_from_execution,
    build_recon_observation,
    normalize_recon_inputs,
    resolve_recon_inputs,
    run_recon_execution,
)
from graphs.recon.pipeline_service import execute_headless_recon_pipeline

logger = logging.getLogger(__name__)


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def decide_prepare_node(state: AgentState) -> dict[str, Any]:
    """Decide whether proc prepare is required before recon."""
    ctx = _get_recon_ctx(state)
    scheme = ctx.get("scheme") if isinstance(ctx.get("scheme"), dict) else {}
    proc_rule_code = str(
        ctx.get("proc_rule_code")
        or scheme.get("proc_rule_code")
        or "",
    ).strip()
    ctx["should_prepare"] = bool(proc_rule_code)
    if proc_rule_code:
        ctx["proc_rule_code"] = proc_rule_code
    return {"recon_ctx": ctx}


def execute_proc_node(state: AgentState) -> dict[str, Any]:
    """Proc placeholder for execution skeleton.

    Real proc orchestration stays in proc graph. Here we only keep the stage contract
    and continue to recon path for compatibility.
    """
    ctx = _get_recon_ctx(state)
    proc_rule_code = str(ctx.get("proc_rule_code") or "").strip()
    if not proc_rule_code:
        ctx["prepare_status"] = "skipped"
        return {"recon_ctx": ctx}

    # Keep compatibility first: don't block recon when proc stage is not yet integrated.
    ctx["prepare_status"] = "not_implemented"
    ctx["prepare_message"] = "当前版本未接入方案内 proc 执行，已继续对账执行。"
    return {"recon_ctx": ctx}


def build_recon_inputs_node(state: AgentState) -> dict[str, Any]:
    """Build recon inputs from explicit inputs or legacy file-match path."""
    ctx = _get_recon_ctx(state)
    raw_inputs = list(ctx.get("recon_inputs") or [])
    recon_inputs = normalize_recon_inputs(raw_inputs)

    if not recon_inputs:
        recon_inputs, ref_map, err = resolve_recon_inputs(state=state, ctx=ctx)
        if err:
            ctx["exec_status"] = "error"
            ctx["exec_error"] = err
            ctx["failed_stage"] = "build_inputs"
            return {"recon_ctx": ctx, "messages": [AIMessage(content=f"对账输入构建失败：{err}")]}
        ctx["ref_to_display_name"] = ref_map
    else:
        ctx["ref_to_display_name"] = dict(ctx.get("ref_to_display_name") or {})

    ctx["recon_inputs"] = recon_inputs
    return {"recon_ctx": ctx}


async def execute_recon_node(state: AgentState) -> dict[str, Any]:
    """Execute recon through the unified headless pipeline."""
    ctx = _get_recon_ctx(state)
    rule_code = str(ctx.get("rule_code") or "").strip()
    if not rule_code:
        ctx["exec_status"] = "error"
        ctx["exec_error"] = "缺少 recon rule_code"
        ctx["failed_stage"] = "config"
        return {"recon_ctx": ctx, "messages": [AIMessage(content="执行失败：缺少对账规则。")]}

    rule = ctx.get("rule") if isinstance(ctx.get("rule"), dict) else {}
    rule_name = str(ctx.get("rule_name") or rule_code).strip()
    run_context = ctx.get("run_context") if isinstance(ctx.get("run_context"), dict) else {}
    trigger_type = str(run_context.get("trigger_type") or "chat")
    entry_mode = str(run_context.get("entry_mode") or "file")
    auth_token = str(state.get("auth_token") or "")

    pipeline_result = await execute_headless_recon_pipeline(
        rule_code=rule_code,
        rule_id=str(ctx.get("rule_id") or ""),
        rule_name=rule_name,
        rule=rule,
        auth_token=auth_token,
        recon_inputs=list(ctx.get("recon_inputs") or []),
        run_context=run_context,
        run_id=str(ctx.get("run_id") or run_context.get("run_id") or ""),
        trigger_type=trigger_type,
        entry_mode=entry_mode,
        ref_to_display_name=dict(ctx.get("ref_to_display_name") or {}),
        build_execution_request_fn=build_execution_request,
        run_recon_execution_fn=run_recon_execution,
        build_recon_observation_fn=build_recon_observation,
        build_recon_ctx_update_fn=build_recon_ctx_update_from_execution,
    )

    ctx.update(
        {
            "exec_status": str(pipeline_result.get("execution_status") or "error"),
            "exec_error": str(pipeline_result.get("exec_error") or ""),
            "recon_result": pipeline_result.get("execution_result")
            if isinstance(pipeline_result.get("execution_result"), dict)
            else {},
            "execution_result": pipeline_result.get("execution_result")
            if isinstance(pipeline_result.get("execution_result"), dict)
            else {},
            "recon_observation": pipeline_result.get("recon_observation")
            if isinstance(pipeline_result.get("recon_observation"), dict)
            else {},
            "run_context": pipeline_result.get("run_context")
            if isinstance(pipeline_result.get("run_context"), dict)
            else run_context,
        }
    )

    ctx_update = pipeline_result.get("ctx_update")
    if isinstance(ctx_update, dict):
        ctx.update(ctx_update)

    if not bool(pipeline_result.get("ok")):
        failure_stage = str(pipeline_result.get("failure_stage") or "recon").strip() or "recon"
        ctx["failed_stage"] = failure_stage
        if not ctx.get("exec_error"):
            ctx["exec_error"] = "对账执行失败"
        logger.error("[scheme_execution] recon failed stage=%s err=%s", failure_stage, ctx["exec_error"])
        return {
            "recon_ctx": ctx,
            "messages": [AIMessage(content=f"对账执行失败：{ctx['exec_error']}")],
        }

    return {"recon_ctx": ctx}


def build_recon_observation_node(state: AgentState) -> dict[str, Any]:
    """Finalize shared execution output contract."""
    ctx = _get_recon_ctx(state)
    status = str(ctx.get("exec_status") or "error")
    if status in {"success", "partial_success", "skipped"}:
        ctx["phase"] = "completed"
    else:
        ctx["phase"] = "exec_failed"
    return {"recon_ctx": ctx}

