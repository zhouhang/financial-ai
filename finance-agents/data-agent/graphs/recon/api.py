"""recon 内部 API。

提供程序化对账入口，供 cron / 内部系统直接触发，
不依赖聊天上传文件流程。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from graphs.recon.execution_service import (
    build_execution_request,
    build_recon_ctx_update_from_execution,
    build_recon_observation,
    normalize_recon_inputs,
    run_recon_execution,
)
from graphs.recon.pipeline_service import execute_headless_recon_pipeline
from tools.mcp_client import get_file_validation_rule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal/recon", tags=["recon-internal"])


class ReconInputPayload(BaseModel):
    table_name: str
    input_type: str = Field(default="dataset")
    payload: dict[str, Any] = Field(default_factory=dict)


class InternalReconRunRequest(BaseModel):
    rule_code: str
    rule_id: str = ""
    trigger_type: str = "api"
    entry_mode: str = "dataset"
    run_context: dict[str, Any] = Field(default_factory=dict)
    recon_inputs: list[ReconInputPayload] = Field(default_factory=list)


@router.post("/run")
async def run_internal_recon(
    body: InternalReconRunRequest,
    authorization: Optional[str] = Header(None),
):
    """内部程序化对账入口。"""
    auth_token = ""
    if authorization:
        auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    if not auth_token:
        raise HTTPException(status_code=401, detail="缺少 Authorization token")

    rule_response = await get_file_validation_rule(body.rule_code, auth_token)
    if not rule_response.get("success"):
        raise HTTPException(status_code=404, detail=f"未找到规则: {body.rule_code}")

    rule_record = rule_response.get("data") or {}
    rule_data = rule_record.get("rule") or {}
    rule_name = str(rule_data.get("rule_name") or rule_record.get("name") or body.rule_code)
    recon_inputs = normalize_recon_inputs([item.model_dump() for item in body.recon_inputs])
    if not recon_inputs:
        raise HTTPException(status_code=400, detail="recon_inputs 不能为空")

    merged_run_context = {
        **body.run_context,
        "trigger_type": body.trigger_type,
        "entry_mode": body.entry_mode,
    }

    # Use unified headless pipeline to keep API/cron path aligned with chat execution semantics.
    pipeline_result = await execute_headless_recon_pipeline(
        rule_code=body.rule_code,
        rule_id=body.rule_id,
        rule_name=rule_name,
        rule=rule_data if isinstance(rule_data, dict) else {},
        auth_token=auth_token,
        recon_inputs=recon_inputs,
        run_context=merged_run_context,
        run_id=str(merged_run_context.get("run_id") or ""),
        trigger_type=body.trigger_type,
        entry_mode=body.entry_mode,
        ref_to_display_name={},
        # Keep injection points patchable for existing tests/in-process callers.
        build_execution_request_fn=build_execution_request,
        run_recon_execution_fn=run_recon_execution,
        build_recon_observation_fn=build_recon_observation,
        build_recon_ctx_update_fn=build_recon_ctx_update_from_execution,
    )
    exec_status = str(pipeline_result.get("execution_status") or "error").strip() or "error"
    exec_error = str(pipeline_result.get("exec_error") or "").strip()
    failure_stage = str(pipeline_result.get("failure_stage") or "").strip()
    if not bool(pipeline_result.get("ok")):
        if failure_stage == "request_build_failed":
            raise HTTPException(status_code=400, detail=exec_error or "对账执行请求构建失败")
        if failure_stage == "execution_call_failed":
            raise HTTPException(status_code=502, detail=exec_error or "调用对账执行服务失败")
        if failure_stage == "execution_result_failed":
            raise HTTPException(status_code=422, detail=exec_error or "对账执行失败")
        raise HTTPException(status_code=500, detail=exec_error or "对账执行失败")

    execution_result = pipeline_result.get("execution_result") if isinstance(pipeline_result.get("execution_result"), dict) else {}
    recon_observation = pipeline_result.get("recon_observation") if isinstance(pipeline_result.get("recon_observation"), dict) else {}
    ctx_update = pipeline_result.get("ctx_update") if isinstance(pipeline_result.get("ctx_update"), dict) else {}
    normalized_run_context = pipeline_result.get("run_context") if isinstance(pipeline_result.get("run_context"), dict) else merged_run_context

    non_error_statuses = {"success", "partial_success", "skipped"}
    success = exec_status in non_error_statuses

    return {
        "success": success,
        "trigger_type": body.trigger_type,
        "entry_mode": body.entry_mode,
        "rule_code": body.rule_code,
        "rule_name": rule_name,
        "recon_ctx": {
            "trigger_type": body.trigger_type,
            "entry_mode": body.entry_mode,
            "rule_code": body.rule_code,
            "rule_name": rule_name,
            "rule": rule_data,
            "run_context": normalized_run_context,
            **ctx_update,
            "phase": "completed" if exec_status in non_error_statuses else "exec_failed",
            "exec_status": exec_status,
            "exec_error": exec_error,
        },
        "execution_result": execution_result,
        "recon_observation": recon_observation,
    }
