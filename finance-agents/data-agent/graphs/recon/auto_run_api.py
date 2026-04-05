"""自动对账任务与异常闭环 REST API。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from graphs.recon.auto_run_service import (
    execute_auto_task_run,
    send_exception_reminder,
    sync_exception_reminder,
)
from tools.mcp_client import (
    recon_auto_run_create,
    recon_auto_run_exceptions,
    recon_auto_run_get,
    recon_auto_run_list,
    recon_auto_run_rerun,
    recon_auto_run_update,
    recon_auto_run_verify,
    recon_auto_task_create,
    recon_auto_task_delete,
    recon_auto_task_get,
    recon_auto_task_list,
    recon_auto_task_update,
    recon_exception_get,
    recon_exception_update,
)

router = APIRouter(prefix="/recon", tags=["recon-auto"])


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization


class AutoTaskCreateRequest(BaseModel):
    task_name: str
    rule_code: str
    is_enabled: bool = True
    schedule_type: str = "daily"
    schedule_expr: str = ""
    biz_date_offset: str = "T-1"
    max_wait_until: str = ""
    retry_policy_json: dict[str, Any] = Field(default_factory=dict)
    input_mode: str = "bound_source"
    bound_data_source_ids: list[str] = Field(default_factory=list)
    completeness_policy_json: dict[str, Any] = Field(default_factory=dict)
    auto_create_exceptions: bool = True
    auto_remind: bool = False
    channel_config_id: str = ""
    reminder_policy_json: dict[str, Any] = Field(default_factory=dict)
    owner_mapping_json: dict[str, Any] = Field(default_factory=dict)
    task_meta_json: dict[str, Any] = Field(default_factory=dict)
    input_bindings: list[dict[str, Any]] = Field(default_factory=list)


class AutoTaskUpdateRequest(BaseModel):
    task_name: Optional[str] = None
    rule_code: Optional[str] = None
    is_enabled: Optional[bool] = None
    schedule_type: Optional[str] = None
    schedule_expr: Optional[str] = None
    biz_date_offset: Optional[str] = None
    max_wait_until: Optional[str] = None
    retry_policy_json: Optional[dict[str, Any]] = None
    input_mode: Optional[str] = None
    bound_data_source_ids: Optional[list[str]] = None
    completeness_policy_json: Optional[dict[str, Any]] = None
    auto_create_exceptions: Optional[bool] = None
    auto_remind: Optional[bool] = None
    channel_config_id: Optional[str] = None
    reminder_policy_json: Optional[dict[str, Any]] = None
    owner_mapping_json: Optional[dict[str, Any]] = None
    task_meta_json: Optional[dict[str, Any]] = None
    input_bindings: Optional[list[dict[str, Any]]] = None


class AutoRunCreateRequest(BaseModel):
    auto_task_id: str
    biz_date: str
    trigger_mode: str = "cron"
    run_status: str = "scheduled"
    readiness_status: str = "waiting_data"
    closure_status: str = "open"
    task_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    source_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    recon_result_summary_json: dict[str, Any] = Field(default_factory=dict)
    anomaly_count: int = 0


class AutoRunUpdateRequest(BaseModel):
    run_status: Optional[str] = None
    readiness_status: Optional[str] = None
    closure_status: Optional[str] = None
    recon_result_summary_json: Optional[dict[str, Any]] = None
    anomaly_count: Optional[int] = None
    error_message: Optional[str] = None
    started_at_now: bool = False
    finished_at_now: bool = False


class AutoRunActionRequest(BaseModel):
    reason: str = ""


class AutoTaskExecuteRequest(BaseModel):
    biz_date: str
    trigger_mode: str = "manual"
    run_context: dict[str, Any] = Field(default_factory=dict)
    input_bindings: list[dict[str, Any]] = Field(default_factory=list)


class ExceptionUpdateRequest(BaseModel):
    owner_name: Optional[str] = None
    owner_identifier: Optional[str] = None
    owner_contact_json: Optional[dict[str, Any]] = None
    reminder_status: Optional[str] = None
    processing_status: Optional[str] = None
    fix_status: Optional[str] = None
    latest_feedback: Optional[str] = None
    feedback_json: Optional[dict[str, Any]] = None
    verify_required: Optional[bool] = None
    verify_run_id: Optional[str] = None
    is_closed: Optional[bool] = None


class ExceptionRemindRequest(BaseModel):
    provider: str = ""
    channel_code: str = ""
    due_time: str = ""
    title: str = ""
    content: str = ""


class ExceptionSyncRequest(BaseModel):
    provider: str = ""
    channel_code: str = ""
    max_polls: int = 1
    poll_interval_seconds: float = 2.0


@router.get("/auto-tasks")
async def list_auto_tasks(
    include_disabled: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_task_list(
        auth_token,
        include_disabled=include_disabled,
        limit=limit,
        offset=offset,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询自动任务失败"))
    return result


@router.get("/auto-tasks/{auto_task_id}")
async def get_auto_task(
    auto_task_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_task_get(auth_token, auto_task_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "自动任务不存在"))
    return result


@router.post("/auto-tasks")
async def create_auto_task(
    body: AutoTaskCreateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_task_create(auth_token, body.model_dump())
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建自动任务失败"))
    return result


@router.patch("/auto-tasks/{auto_task_id}")
async def update_auto_task(
    auto_task_id: str,
    body: AutoTaskUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_task_update(auth_token, auto_task_id, body.model_dump(exclude_none=True))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新自动任务失败"))
    return result


@router.delete("/auto-tasks/{auto_task_id}")
async def delete_auto_task(
    auto_task_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_task_delete(auth_token, auto_task_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "删除自动任务失败"))
    return result


@router.post("/auto-tasks/{auto_task_id}/run")
async def execute_auto_task(
    auto_task_id: str,
    body: AutoTaskExecuteRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execute_auto_task_run(
        auth_token=auth_token,
        auto_task_id=auto_task_id,
        biz_date=body.biz_date,
        trigger_mode=body.trigger_mode,
        run_context=body.run_context,
        input_bindings=body.input_bindings or None,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "执行自动对账失败"))
    return result


@router.post("/auto-runs")
async def create_auto_run(
    body: AutoRunCreateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_create(auth_token, body.model_dump())
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建运行批次失败"))
    return result


@router.patch("/auto-runs/{auto_run_id}")
async def update_auto_run(
    auto_run_id: str,
    body: AutoRunUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_update(auth_token, auto_run_id, body.model_dump(exclude_none=True))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新运行批次失败"))
    return result


@router.get("/auto-runs")
async def list_auto_runs(
    auto_task_id: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_list(
        auth_token,
        auto_task_id=auto_task_id,
        limit=limit,
        offset=offset,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询运行批次失败"))
    return result


@router.get("/auto-runs/{auto_run_id}")
async def get_auto_run(
    auto_run_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_get(auth_token, auto_run_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "运行批次不存在"))
    return result


@router.post("/auto-runs/{auto_run_id}/rerun")
async def rerun_auto_run(
    auto_run_id: str,
    body: AutoRunActionRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_rerun(auth_token, auto_run_id, reason=body.reason)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "重跑失败"))
    return result


@router.post("/auto-runs/{auto_run_id}/verify")
async def verify_auto_run(
    auto_run_id: str,
    body: AutoRunActionRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_verify(auth_token, auto_run_id, reason=body.reason)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "发起人工验证失败"))
    return result


@router.get("/exceptions/{exception_id}")
async def get_exception(
    exception_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_exception_get(auth_token, exception_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "异常任务不存在"))
    return result


@router.get("/auto-runs/{auto_run_id}/exceptions")
async def list_auto_run_exceptions(
    auto_run_id: str,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_auto_run_exceptions(
        auth_token,
        auto_run_id,
        limit=limit,
        offset=offset,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询异常列表失败"))
    return result


@router.patch("/exceptions/{exception_id}")
async def update_exception(
    exception_id: str,
    body: ExceptionUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await recon_exception_update(auth_token, exception_id, body.model_dump(exclude_none=True))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新异常状态失败"))
    return result


@router.post("/exceptions/{exception_id}/remind")
async def remind_exception(
    exception_id: str,
    body: ExceptionRemindRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await send_exception_reminder(
        auth_token=auth_token,
        exception_id=exception_id,
        provider=body.provider,
        channel_code=body.channel_code,
        due_time=body.due_time,
        title=body.title,
        content=body.content,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "发送催办失败"))
    return result


@router.post("/exceptions/{exception_id}/sync")
async def sync_exception(
    exception_id: str,
    body: ExceptionSyncRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await sync_exception_reminder(
        auth_token=auth_token,
        exception_id=exception_id,
        provider=body.provider,
        channel_code=body.channel_code,
        max_polls=body.max_polls,
        poll_interval_seconds=body.poll_interval_seconds,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "同步待办状态失败"))
    return result
