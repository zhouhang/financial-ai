"""recon 内部 API。

提供程序化对账入口，供 cron / 内部系统直接触发，
不依赖聊天上传文件流程。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from graphs.recon.execution_service import build_execution_request, normalize_recon_inputs, run_recon_execution
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

    execution_request, request_error = build_execution_request(
        rule_code=body.rule_code,
        rule_id=body.rule_id,
        auth_token=auth_token,
        recon_inputs=recon_inputs,
        run_context={
            **body.run_context,
            "trigger_type": body.trigger_type,
            "entry_mode": body.entry_mode,
        },
    )
    if request_error:
        raise HTTPException(status_code=400, detail=request_error)

    recon_result, exec_error = await run_recon_execution(execution_request)
    if exec_error:
        raise HTTPException(status_code=500, detail=exec_error)

    success = bool(recon_result.get("success"))
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
            "run_context": body.run_context,
            "recon_inputs": recon_inputs,
            "execution_request": execution_request,
            "execution_result": recon_result,
            "phase": "completed" if success else "exec_failed",
            "exec_status": recon_result.get("status", "success" if success else "error"),
            "exec_error": recon_result.get("error", ""),
        },
        "execution_result": recon_result,
    }
