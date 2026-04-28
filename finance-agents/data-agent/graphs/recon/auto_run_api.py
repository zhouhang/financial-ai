"""自动对账任务与异常闭环 REST API。"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
import jwt
from pydantic import BaseModel, Field

from graphs.recon.auto_run_service import (
    execute_run_plan_run,
    execute_auto_task_run,
    prepare_execution_run_rerun,
    send_exception_reminder,
    send_execution_run_exception_reminder,
    sync_execution_run_exception_reminder,
    sync_exception_reminder,
)
from graphs.recon.binding_date_fields import (
    extract_source_items_from_scheme_meta,
    infer_binding_side,
    normalize_binding_query_date_field,
    safe_list,
    text,
)
from graphs.recon.scheme_rule_registry import ensure_scheme_rule_saved
from tools.mcp_client import (
    execution_run_exception_get,
    execution_run_exception_update,
    execution_run_exceptions,
    execution_run_get,
    execution_run_list,
    execution_run_plan_create,
    execution_run_plan_delete,
    execution_run_plan_get,
    execution_run_plan_list,
    execution_run_plan_update,
    execution_scheme_create,
    execution_scheme_delete,
    execution_scheme_get,
    execution_scheme_list,
    execution_scheme_update,
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
    recon_queue_enqueue,
)

router = APIRouter(prefix="/recon", tags=["recon-auto"])
JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
JWT_ALGORITHM = "HS256"


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization


def _get_user_from_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
    return {
        "user_id": payload.get("sub"),
        "username": payload.get("username"),
        "role": payload.get("role"),
        "company_id": payload.get("company_id"),
        "department_id": payload.get("department_id"),
    }


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


class ExecutionRunRerunRequest(BaseModel):
    original_run_id: str
    exception_id: str = ""
    reason: str = ""


class AutoTaskExecuteRequest(BaseModel):
    biz_date: str
    trigger_mode: str = "manual"
    run_context: dict[str, Any] = Field(default_factory=dict)
    input_bindings: list[dict[str, Any]] = Field(default_factory=list)


class RunPlanExecuteRequest(BaseModel):
    biz_date: str = ""
    trigger_mode: str = "manual"
    run_context: dict[str, Any] = Field(default_factory=dict)


class ExecutionSchemeCreateRequest(BaseModel):
    scheme_name: str
    scheme_code: str = ""
    scheme_type: str = "recon"
    description: str = ""
    file_rule_code: str = ""
    proc_rule_code: str = ""
    recon_rule_code: str = ""
    scheme_meta_json: dict[str, Any] = Field(default_factory=dict)
    dataset_bindings_json: list[dict[str, Any]] = Field(default_factory=list)
    is_enabled: bool = True


class ExecutionSchemeUpdateRequest(BaseModel):
    scheme_name: Optional[str] = None
    scheme_type: Optional[str] = None
    description: Optional[str] = None
    file_rule_code: Optional[str] = None
    proc_rule_code: Optional[str] = None
    recon_rule_code: Optional[str] = None
    scheme_meta_json: Optional[dict[str, Any]] = None
    dataset_bindings_json: Optional[list[dict[str, Any]]] = None
    is_enabled: Optional[bool] = None


class ExecutionTaskCreateRequest(BaseModel):
    plan_name: str
    plan_code: str = ""
    scheme_code: str
    schedule_type: str = "manual_trigger"
    schedule_expr: str = ""
    biz_date_offset: str = "previous_day"
    input_bindings_json: list[dict[str, Any]] = Field(default_factory=list)
    channel_config_id: str = ""
    owner_mapping_json: dict[str, Any] = Field(default_factory=dict)
    plan_meta_json: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class ExecutionTaskUpdateRequest(BaseModel):
    plan_name: Optional[str] = None
    scheme_code: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_expr: Optional[str] = None
    biz_date_offset: Optional[str] = None
    input_bindings_json: Optional[list[dict[str, Any]]] = None
    channel_config_id: Optional[str] = None
    owner_mapping_json: Optional[dict[str, Any]] = None
    plan_meta_json: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None


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


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


async def _normalize_run_plan_payload_date_fields(
    auth_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    scheme_code = text(payload.get("scheme_code"))
    input_bindings = [dict(item) for item in safe_list(payload.get("input_bindings_json")) if isinstance(item, dict)]
    if not scheme_code or not input_bindings:
        return payload

    scheme_result = await execution_scheme_get(auth_token, scheme_code=scheme_code)
    if not scheme_result.get("success"):
        return payload
    scheme = _safe_dict(scheme_result.get("scheme"))
    scheme_meta_json = _safe_dict(scheme.get("scheme_meta_json"))
    if not scheme_meta_json:
        return payload

    normalized_bindings: list[dict[str, Any]] = []
    for raw_binding in input_bindings:
        binding = dict(raw_binding)
        side = infer_binding_side(binding)
        query = _safe_dict(binding.get("query"))
        if not query:
            query = _safe_dict(_safe_dict(binding.get("filter_config")).get("query"))
        if side:
            query = normalize_binding_query_date_field(
                scheme_meta=scheme_meta_json,
                binding=binding,
                query=query,
                side=side,
            )
        binding["query"] = query
        normalized_bindings.append(binding)

    payload["input_bindings_json"] = normalized_bindings
    plan_meta_json = _safe_dict(payload.get("plan_meta_json"))
    if plan_meta_json:
        plan_meta_json["input_bindings"] = normalized_bindings
        payload["plan_meta_json"] = plan_meta_json
    return payload


def _extract_source_bindings_from_scheme_meta(
    *,
    scheme_meta_json: dict[str, Any],
    side: str,
    default_priority_start: int,
) -> list[dict[str, Any]]:
    source_items = extract_source_items_from_scheme_meta(
        scheme_meta=scheme_meta_json,
        side=side,
    )
    if not source_items:
        return []

    bindings: list[dict[str, Any]] = []
    priority = default_priority_start
    for idx, raw in enumerate(source_items, start=1):
        item = _safe_dict(raw)
        source_id = str(item.get("source_id") or item.get("data_source_id") or "").strip()
        resource_key = str(item.get("resource_key") or item.get("dataset_code") or item.get("name") or "").strip()
        if not source_id or not resource_key:
            continue
        dataset_code = str(item.get("dataset_code") or "").strip()
        table_name = str(item.get("table_name") or resource_key).strip()
        binding_name = (
            str(item.get("business_name") or item.get("name") or dataset_code or table_name).strip() or table_name
        )
        query = _safe_dict(item.get("query"))
        query = normalize_binding_query_date_field(
            scheme_meta=scheme_meta_json,
            binding={
                "side": side,
                "data_source_id": source_id,
                "resource_key": resource_key,
                "table_name": table_name,
                "dataset_code": dataset_code,
                "query": query,
            },
            query=query,
            side=side,
        )

        bindings.append(
            {
                "role_code": f"{side}_{idx}",
                "data_source_id": source_id,
                "resource_key": resource_key,
                "binding_name": binding_name,
                "is_required": bool(item.get("required", True)),
                "priority": priority,
                "filter_config": {"query": query},
                "mapping_config": {
                    "side": side,
                    "dataset_code": dataset_code or resource_key,
                    "table_name": table_name,
                    "dataset_source_type": str(item.get("dataset_source_type") or "collection_records").strip() or "collection_records",
                },
            }
        )
        priority += 1
    return bindings


def _normalize_explicit_scheme_binding(raw: Any, *, index: int) -> dict[str, Any] | None:
    item = _safe_dict(raw)
    source_id = str(item.get("data_source_id") or item.get("source_id") or "").strip()
    resource_key = str(item.get("resource_key") or item.get("dataset_code") or item.get("table_name") or "").strip()
    if not source_id or not resource_key:
        return None

    query = _safe_dict(item.get("query"))
    filter_config = _safe_dict(item.get("filter_config"))
    if query:
        filter_config = {**filter_config, "query": query}
    mapping_config = _safe_dict(item.get("mapping_config"))
    for key in ("table_name", "dataset_code", "dataset_source_type", "side"):
        value = str(item.get(key) or "").strip()
        if value:
            mapping_config[key] = value

    role_code = str(item.get("role_code") or item.get("role") or f"source_{index}").strip()
    if not role_code:
        role_code = f"source_{index}"
    try:
        priority = int(item.get("priority") or index)
    except (TypeError, ValueError):
        priority = index
    return {
        "role_code": role_code,
        "data_source_id": source_id,
        "resource_key": resource_key,
        "binding_name": str(item.get("binding_name") or item.get("name") or resource_key).strip() or resource_key,
        "is_required": bool(item.get("is_required", item.get("required", True))),
        "priority": priority,
        "filter_config": filter_config,
        "mapping_config": mapping_config,
    }


def _extract_scheme_dataset_bindings(
    payload: dict[str, Any],
    *,
    allow_empty_explicit: bool,
) -> tuple[list[dict[str, Any]], bool]:
    scheme_meta_json = _safe_dict(payload.get("scheme_meta_json"))
    explicit = payload.get("dataset_bindings_json")
    if isinstance(explicit, list) and (allow_empty_explicit or len(explicit) > 0):
        normalized = [
            binding
            for idx, item in enumerate(explicit, start=1)
            for binding in [_normalize_explicit_scheme_binding(item, index=idx)]
            if binding is not None
        ]
        return normalized, True

    dataset_bindings = _safe_dict(scheme_meta_json.get("dataset_bindings"))
    has_dataset_binding_groups = isinstance(dataset_bindings.get("left"), list) or isinstance(
        dataset_bindings.get("right"),
        list,
    )
    has_side_sources = isinstance(scheme_meta_json.get("left_sources"), list) or isinstance(
        scheme_meta_json.get("right_sources"),
        list,
    )
    if not has_dataset_binding_groups and not has_side_sources:
        return [], False

    left_bindings = _extract_source_bindings_from_scheme_meta(
        scheme_meta_json=scheme_meta_json,
        side="left",
        default_priority_start=10,
    )
    right_bindings = _extract_source_bindings_from_scheme_meta(
        scheme_meta_json=scheme_meta_json,
        side="right",
        default_priority_start=100,
    )
    return left_bindings + right_bindings, True


@router.get("/schemes")
async def list_execution_schemes(
    include_disabled: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_scheme_list(
        auth_token,
        include_disabled=include_disabled,
        limit=limit,
        offset=offset,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询对账方案失败"))
    return result


@router.get("/schemes/{scheme_id}")
async def get_execution_scheme(
    scheme_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_scheme_get(auth_token, scheme_id=scheme_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "对账方案不存在"))
    return result


@router.post("/schemes")
async def create_execution_scheme_api(
    body: ExecutionSchemeCreateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    payload = body.model_dump()
    scheme_meta_json = _safe_dict(payload.get("scheme_meta_json"))
    proc_rule_code = str(payload.get("proc_rule_code") or "").strip()
    recon_rule_code = str(payload.get("recon_rule_code") or "").strip()
    proc_rule_json = _safe_dict(scheme_meta_json.get("proc_rule_json"))
    recon_rule_json = _safe_dict(scheme_meta_json.get("recon_rule_json"))
    proc_trial_status = str(scheme_meta_json.get("proc_trial_status") or "").strip().lower()
    recon_trial_status = str(scheme_meta_json.get("recon_trial_status") or "").strip().lower()
    scheme_name = str(payload.get("scheme_name") or "未命名方案").strip() or "未命名方案"

    if proc_rule_json and proc_trial_status != "passed":
        raise HTTPException(status_code=400, detail="请先完成数据整理试跑验证，再保存方案")
    if recon_rule_json and recon_trial_status != "passed":
        raise HTTPException(status_code=400, detail="请先完成数据对账试跑验证，再保存方案")

    if proc_rule_json and not proc_rule_code:
        proc_saved = await ensure_scheme_rule_saved(
            auth_token,
            scheme_name=scheme_name,
            rule_type="proc",
            rule_json=proc_rule_json,
            remark="API 创建方案自动生成整理规则",
            supported_entry_modes=['dataset'],
        )
        proc_rule_code = str(proc_saved.get("rule_code") or proc_rule_code).strip()

    if recon_rule_json and not recon_rule_code:
        recon_saved = await ensure_scheme_rule_saved(
            auth_token,
            scheme_name=scheme_name,
            rule_type="recon",
            rule_json=recon_rule_json,
            remark="API 创建方案自动生成对账逻辑",
            supported_entry_modes=['dataset'],
        )
        recon_rule_code = str(recon_saved.get("rule_code") or recon_rule_code).strip()

    if not recon_rule_code and not recon_rule_json:
        raise HTTPException(status_code=400, detail="缺少可执行的对账规则，无法保存方案")

    if proc_rule_json:
        scheme_meta_json["proc_rule_json"] = proc_rule_json
    if recon_rule_json:
        scheme_meta_json["recon_rule_json"] = recon_rule_json
    scheme_meta_json["proc_rule_storage"] = "rule_detail" if proc_rule_code else "embedded"
    scheme_meta_json["recon_rule_storage"] = "rule_detail" if recon_rule_code else "embedded"
    scheme_meta_json["proc_rule_code"] = proc_rule_code
    scheme_meta_json["recon_rule_code"] = recon_rule_code
    payload["proc_rule_code"] = proc_rule_code
    payload["recon_rule_code"] = recon_rule_code
    payload["scheme_meta_json"] = scheme_meta_json
    dataset_bindings_json, bindings_provided = _extract_scheme_dataset_bindings(
        payload,
        allow_empty_explicit=False,
    )
    if bindings_provided:
        payload["dataset_bindings_json"] = dataset_bindings_json

    result = await execution_scheme_create(auth_token, payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建对账方案失败"))
    return result


@router.patch("/schemes/{scheme_id}")
async def update_execution_scheme_api(
    scheme_id: str,
    body: ExecutionSchemeUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    payload = body.model_dump(exclude_none=True)
    dataset_bindings_json, bindings_provided = _extract_scheme_dataset_bindings(
        payload,
        allow_empty_explicit=True,
    )
    if bindings_provided:
        payload["dataset_bindings_json"] = dataset_bindings_json
    result = await execution_scheme_update(auth_token, scheme_id, payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新对账方案失败"))
    return result


@router.delete("/schemes/{scheme_id}")
async def delete_execution_scheme_api(
    scheme_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_scheme_delete(auth_token, scheme_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "停用对账方案失败"))
    return result


@router.get("/tasks")
async def list_execution_tasks(
    scheme_code: str = Query(""),
    include_disabled: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_plan_list(
        auth_token,
        scheme_code=scheme_code,
        include_disabled=include_disabled,
        limit=limit,
        offset=offset,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询对账任务失败"))
    return {
        **result,
        "tasks": result.get("run_plans") or [],
    }


@router.get("/tasks/{plan_id}")
async def get_execution_task(
    plan_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_plan_get(auth_token, plan_id=plan_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "对账任务不存在"))
    return {
        **result,
        "task": result.get("run_plan") or {},
    }


@router.post("/tasks")
async def create_execution_task_api(
    body: ExecutionTaskCreateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    payload = await _normalize_run_plan_payload_date_fields(auth_token, body.model_dump())
    result = await execution_run_plan_create(auth_token, payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建对账任务失败"))
    return {
        **result,
        "task": result.get("run_plan") or {},
    }


@router.patch("/tasks/{plan_id}")
async def update_execution_task_api(
    plan_id: str,
    body: ExecutionTaskUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    payload = await _normalize_run_plan_payload_date_fields(auth_token, body.model_dump(exclude_none=True))
    result = await execution_run_plan_update(auth_token, plan_id, payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新对账任务失败"))
    return {
        **result,
        "task": result.get("run_plan") or {},
    }


@router.delete("/tasks/{plan_id}")
async def delete_execution_task_api(
    plan_id: str,
    plan_code: str = Query(""),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_plan_delete(auth_token, plan_id, plan_code=plan_code or None)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "删除对账任务失败"))
    return result


@router.get("/runs")
async def list_execution_runs(
    scheme_code: str = Query(""),
    plan_code: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_list(
        auth_token,
        scheme_code=scheme_code,
        plan_code=plan_code,
        limit=limit,
        offset=offset,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询运行记录失败"))
    return result


@router.get("/runs/{run_id}")
async def get_execution_run_api(
    run_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_get(auth_token, run_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "运行记录不存在"))
    return result


@router.post("/runs/rerun")
async def rerun_execution_run_api(
    body: ExecutionRunRerunRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    user = _get_user_from_token(auth_token)
    if not user or not user.get("company_id"):
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    prepare_result = await prepare_execution_run_rerun(
        auth_token=auth_token,
        original_run_id=body.original_run_id,
        exception_id=body.exception_id,
        reason=body.reason,
    )
    if not prepare_result.get("success"):
        status = str(prepare_result.get("status") or "todo")
        raise HTTPException(
            status_code=400 if status not in {"not_found"} else 404,
            detail={
                "status": status,
                "message": prepare_result.get("error") or "重新对账验证暂不可用",
                "todo": prepare_result.get("todo") or "",
            },
        )

    result = await recon_queue_enqueue(
        company_id=str(user["company_id"]),
        run_plan_code=str(prepare_result.get("run_plan_code") or ""),
        biz_date=str(prepare_result.get("biz_date") or ""),
        trigger_mode="rerun",
        run_context=dict(prepare_result.get("run_context") or {}),
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "入队失败"))
    return {
        "queued": True,
        "status": "queued",
        "job_id": str((result.get("job") or {}).get("id") or ""),
        "source_run_id": prepare_result.get("source_run_id") or body.original_run_id,
        "exception_id": prepare_result.get("exception_id") or body.exception_id,
        "run_plan_code": prepare_result.get("run_plan_code") or "",
        "biz_date": prepare_result.get("biz_date") or "",
        "message": "重新对账验证已进入执行队列，请稍后查询运行结果",
    }


@router.get("/runs/{run_id}/exceptions")
async def list_execution_run_exceptions_api(
    run_id: str,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_exceptions(auth_token, run_id, limit=limit, offset=offset)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询异常处理失败"))
    return result


@router.get("/run-exceptions/{exception_id}")
async def get_execution_run_exception_api(
    exception_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_exception_get(auth_token, exception_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "异常处理项不存在"))
    return result


@router.patch("/run-exceptions/{exception_id}")
async def update_execution_run_exception_api(
    exception_id: str,
    body: ExceptionUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await execution_run_exception_update(
        auth_token,
        exception_id,
        body.model_dump(exclude_none=True),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "更新异常处理失败"))
    return result


@router.post("/run-exceptions/{exception_id}/sync")
async def sync_execution_run_exception_api(
    exception_id: str,
    body: ExceptionSyncRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await sync_execution_run_exception_reminder(
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


@router.post("/run-exceptions/{exception_id}/remind")
async def remind_execution_run_exception_api(
    exception_id: str,
    body: ExceptionRemindRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    result = await send_execution_run_exception_reminder(
        auth_token=auth_token,
        exception_id=exception_id,
        provider=body.provider,
        channel_code=body.channel_code,
        due_time=body.due_time,
        title=body.title,
        content=body.content,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "催办发送失败"))
    return result


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


@router.post("/run-plans/{run_plan_code}/run")
async def execute_run_plan(
    run_plan_code: str,
    body: RunPlanExecuteRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    user = _get_user_from_token(auth_token)
    if not user or not user.get("company_id"):
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    result = await recon_queue_enqueue(
        company_id=str(user["company_id"]),
        run_plan_code=run_plan_code,
        biz_date=str(body.biz_date or ""),
        trigger_mode=str(body.trigger_mode or "schedule"),
        run_context=dict(body.run_context or {}),
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "入队失败"))
    return {"queued": True, "run_plan_code": run_plan_code, "job_id": str((result.get("job") or {}).get("id") or ""), "message": "对账任务已进入执行队列，请稍后查询运行结果"}


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
