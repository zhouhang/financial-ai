"""Unified headless recon pipeline service.

This module provides a single orchestration entry for recon execution so that:
- chat node path
- internal API / cron path
reuse the same core pipeline steps.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from graphs.recon.execution_service import (
    build_execution_request,
    build_recon_ctx_update_from_execution,
    build_recon_observation,
    run_recon_execution,
)


BuildExecutionRequestFn = Callable[..., tuple[dict[str, Any], str | None]]
RunReconExecutionFn = Callable[[dict[str, Any]], Awaitable[tuple[dict[str, Any], str | None]]]
BuildReconObservationFn = Callable[..., dict[str, Any]]
BuildReconCtxUpdateFn = Callable[..., dict[str, Any]]


def _normalize_run_context(
    *,
    run_context: dict[str, Any] | None,
    trigger_type: str,
    entry_mode: str,
    run_id: str,
) -> dict[str, Any]:
    """Normalize run context for both chat and headless callers."""
    normalized = dict(run_context or {})
    normalized["trigger_type"] = str(normalized.get("trigger_type") or trigger_type or "chat")
    normalized["entry_mode"] = str(normalized.get("entry_mode") or entry_mode or "file")

    resolved_run_id = str(run_id or "").strip()
    if resolved_run_id and not str(normalized.get("run_id") or "").strip():
        normalized["run_id"] = resolved_run_id
    return normalized


async def execute_headless_recon_pipeline(
    *,
    rule_code: str,
    rule_id: str,
    rule_name: str,
    rule: dict[str, Any],
    auth_token: str,
    recon_inputs: list[dict[str, Any]],
    run_context: dict[str, Any] | None,
    run_id: str = "",
    trigger_type: str = "chat",
    entry_mode: str = "file",
    ref_to_display_name: dict[str, str] | None = None,
    build_execution_request_fn: BuildExecutionRequestFn = build_execution_request,
    run_recon_execution_fn: RunReconExecutionFn = run_recon_execution,
    build_recon_observation_fn: BuildReconObservationFn = build_recon_observation,
    build_recon_ctx_update_fn: BuildReconCtxUpdateFn = build_recon_ctx_update_from_execution,
) -> dict[str, Any]:
    """Run the unified recon execution pipeline and return normalized output.

    Returns:
        {
            "ok": bool,
            "execution_status": str,
            "exec_error": str,
            "failure_stage": str,
            "run_context": dict,
            "execution_request": dict,
            "execution_result": dict,
            "recon_observation": dict,
            "ctx_update": dict,
        }
    """
    display_name_map = dict(ref_to_display_name or {})
    normalized_run_context = _normalize_run_context(
        run_context=run_context,
        trigger_type=trigger_type,
        entry_mode=entry_mode,
        run_id=run_id,
    )

    execution_request, request_error = build_execution_request_fn(
        rule_code=rule_code,
        rule_id=rule_id,
        auth_token=auth_token,
        recon_inputs=recon_inputs,
        run_context=normalized_run_context,
    )
    if request_error:
        return {
            "ok": False,
            "execution_status": "error",
            "exec_error": request_error,
            "failure_stage": "request_build_failed",
            "run_context": normalized_run_context,
            "execution_request": {},
            "execution_result": {},
            "recon_observation": {},
            "ctx_update": {},
        }

    recon_result, exec_call_error = await run_recon_execution_fn(execution_request)
    if exec_call_error:
        return {
            "ok": False,
            "execution_status": "error",
            "exec_error": exec_call_error,
            "failure_stage": "execution_call_failed",
            "run_context": normalized_run_context,
            "execution_request": execution_request,
            "execution_result": {},
            "recon_observation": {},
            "ctx_update": {},
        }

    recon_observation = build_recon_observation_fn(
        rule_code=rule_code,
        rule_name=rule_name,
        rule=rule if isinstance(rule, dict) else {},
        trigger_type=str(normalized_run_context.get("trigger_type") or trigger_type or "chat"),
        entry_mode=str(normalized_run_context.get("entry_mode") or entry_mode or "file"),
        recon_inputs=recon_inputs,
        recon_result=recon_result if isinstance(recon_result, dict) else {},
        run_context=normalized_run_context,
        run_id=str(normalized_run_context.get("run_id") or ""),
        ref_to_display_name=display_name_map,
    )

    execution_ctx = build_recon_ctx_update_fn(
        recon_result=recon_result if isinstance(recon_result, dict) else {},
        recon_inputs=recon_inputs,
        execution_request=execution_request,
        ref_to_display_name=display_name_map,
        recon_observation=recon_observation,
    )
    ctx_update = execution_ctx.get("ctx_update") if isinstance(execution_ctx.get("ctx_update"), dict) else {}
    execution_status = str(execution_ctx.get("execution_status") or "")
    if not execution_status:
        execution_status = "success" if recon_result.get("success") else "error"
    ok = bool(execution_ctx.get("ok"))

    return {
        "ok": ok,
        "execution_status": execution_status,
        "exec_error": str(execution_ctx.get("exec_error") or ""),
        "failure_stage": "" if ok else "execution_result_failed",
        "run_context": normalized_run_context,
        "execution_request": execution_request,
        "execution_result": recon_result if isinstance(recon_result, dict) else {},
        "recon_observation": recon_observation if isinstance(recon_observation, dict) else {},
        "ctx_update": ctx_update,
    }
