"""自动对账任务与异常闭环 MCP 工具。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp import Tool

from auth import db as auth_db
from auth.jwt_utils import get_user_from_token


def create_tools() -> list[Tool]:
    return [
        Tool(
            name="recon_auto_task_list",
            description="查询自动对账任务配置列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "include_disabled": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="recon_auto_task_get",
            description="查询单个自动对账任务配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_task_id": {"type": "string"},
                },
                "required": ["auth_token", "auto_task_id"],
            },
        ),
        Tool(
            name="recon_auto_task_create",
            description="创建自动对账任务配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "task_name": {"type": "string"},
                    "rule_code": {"type": "string"},
                    "is_enabled": {"type": "boolean"},
                    "schedule_type": {"type": "string"},
                    "schedule_expr": {"type": "string"},
                    "biz_date_offset": {"type": "string"},
                    "max_wait_until": {"type": "string"},
                    "retry_policy_json": {"type": "object"},
                    "input_mode": {"type": "string"},
                    "bound_data_source_ids": {"type": "array"},
                    "completeness_policy_json": {"type": "object"},
                    "auto_create_exceptions": {"type": "boolean"},
                    "auto_remind": {"type": "boolean"},
                    "channel_config_id": {"type": "string"},
                    "reminder_policy_json": {"type": "object"},
                    "owner_mapping_json": {"type": "object"},
                    "task_meta_json": {"type": "object"},
                    "input_bindings": {"type": "array"},
                },
                "required": ["auth_token", "task_name", "rule_code"],
            },
        ),
        Tool(
            name="recon_auto_task_update",
            description="更新自动对账任务配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_task_id": {"type": "string"},
                    "task_name": {"type": "string"},
                    "rule_code": {"type": "string"},
                    "is_enabled": {"type": "boolean"},
                    "schedule_type": {"type": "string"},
                    "schedule_expr": {"type": "string"},
                    "biz_date_offset": {"type": "string"},
                    "max_wait_until": {"type": "string"},
                    "retry_policy_json": {"type": "object"},
                    "input_mode": {"type": "string"},
                    "bound_data_source_ids": {"type": "array"},
                    "completeness_policy_json": {"type": "object"},
                    "auto_create_exceptions": {"type": "boolean"},
                    "auto_remind": {"type": "boolean"},
                    "channel_config_id": {"type": "string"},
                    "reminder_policy_json": {"type": "object"},
                    "owner_mapping_json": {"type": "object"},
                    "task_meta_json": {"type": "object"},
                    "input_bindings": {"type": "array"},
                },
                "required": ["auth_token", "auto_task_id"],
            },
        ),
        Tool(
            name="recon_auto_task_delete",
            description="逻辑删除自动对账任务（置为停用）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_task_id": {"type": "string"},
                },
                "required": ["auth_token", "auto_task_id"],
            },
        ),
        Tool(
            name="recon_auto_run_create",
            description="创建自动对账运行批次（run 业务记录）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_task_id": {"type": "string"},
                    "biz_date": {"type": "string"},
                    "trigger_mode": {"type": "string"},
                    "run_status": {"type": "string"},
                    "readiness_status": {"type": "string"},
                    "closure_status": {"type": "string"},
                    "task_snapshot_json": {"type": "object"},
                    "source_snapshot_json": {"type": "object"},
                    "recon_result_summary_json": {"type": "object"},
                    "anomaly_count": {"type": "integer"},
                },
                "required": ["auth_token", "auto_task_id", "biz_date"],
            },
        ),
        Tool(
            name="recon_auto_run_update",
            description="更新自动对账运行批次状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                    "run_status": {"type": "string"},
                    "readiness_status": {"type": "string"},
                    "closure_status": {"type": "string"},
                    "recon_result_summary_json": {"type": "object"},
                    "anomaly_count": {"type": "integer"},
                    "error_message": {"type": "string"},
                    "started_at_now": {"type": "boolean"},
                    "finished_at_now": {"type": "boolean"},
                },
                "required": ["auth_token", "auto_run_id"],
            },
        ),
        Tool(
            name="recon_auto_run_list",
            description="查询自动对账运行批次列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_task_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="recon_auto_run_get",
            description="查询单个自动对账运行批次。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                },
                "required": ["auth_token", "auto_run_id"],
            },
        ),
        Tool(
            name="recon_auto_run_rerun",
            description="对某次运行发起重跑，生成新 run 记录与 run_job。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["auth_token", "auto_run_id"],
            },
        ),
        Tool(
            name="recon_auto_run_verify",
            description="对某次运行发起人工验证，生成 verify run 与 verify job。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["auth_token", "auto_run_id"],
            },
        ),
        Tool(
            name="recon_auto_run_job_create",
            description="创建自动对账短动作执行记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                    "job_type": {"type": "string"},
                    "job_status": {"type": "string"},
                    "attempt_no": {"type": "integer"},
                    "idempotency_key": {"type": "string"},
                    "input_json": {"type": "object"},
                    "output_json": {"type": "object"},
                    "error_message": {"type": "string"},
                },
                "required": ["auth_token", "auto_run_id", "job_type"],
            },
        ),
        Tool(
            name="recon_auto_run_job_update",
            description="更新自动对账短动作执行记录状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_job_id": {"type": "string"},
                    "job_status": {"type": "string"},
                    "output_json": {"type": "object"},
                    "error_message": {"type": "string"},
                    "started_at_now": {"type": "boolean"},
                    "finished_at_now": {"type": "boolean"},
                },
                "required": ["auth_token", "run_job_id"],
            },
        ),
        Tool(
            name="recon_auto_run_exceptions",
            description="按某次运行查询异常列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["auth_token", "auto_run_id"],
            },
        ),
        Tool(
            name="recon_exception_get",
            description="查询单个异常任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "exception_id": {"type": "string"},
                },
                "required": ["auth_token", "exception_id"],
            },
        ),
        Tool(
            name="recon_exception_create",
            description="创建或更新异常任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "auto_task_id": {"type": "string"},
                    "auto_run_id": {"type": "string"},
                    "anomaly_key": {"type": "string"},
                    "anomaly_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "detail_json": {"type": "object"},
                    "owner_name": {"type": "string"},
                    "owner_identifier": {"type": "string"},
                    "owner_contact_json": {"type": "object"},
                    "reminder_status": {"type": "string"},
                    "processing_status": {"type": "string"},
                    "fix_status": {"type": "string"},
                    "latest_feedback": {"type": "string"},
                    "feedback_json": {"type": "object"},
                    "verify_required": {"type": "boolean"},
                    "verify_run_id": {"type": "string"},
                    "is_closed": {"type": "boolean"},
                },
                "required": ["auth_token", "auto_task_id", "auto_run_id", "anomaly_key", "anomaly_type", "summary"],
            },
        ),
        Tool(
            name="recon_exception_update",
            description="更新异常任务状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "exception_id": {"type": "string"},
                    "owner_name": {"type": "string"},
                    "owner_identifier": {"type": "string"},
                    "owner_contact_json": {"type": "object"},
                    "reminder_status": {"type": "string"},
                    "processing_status": {"type": "string"},
                    "fix_status": {"type": "string"},
                    "latest_feedback": {"type": "string"},
                    "feedback_json": {"type": "object"},
                    "verify_required": {"type": "boolean"},
                    "verify_run_id": {"type": "string"},
                    "is_closed": {"type": "boolean"},
                },
                "required": ["auth_token", "exception_id"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "recon_auto_task_list":
        return _task_list(arguments)
    if name == "recon_auto_task_get":
        return _task_get(arguments)
    if name == "recon_auto_task_create":
        return _task_create(arguments)
    if name == "recon_auto_task_update":
        return _task_update(arguments)
    if name == "recon_auto_task_delete":
        return _task_delete(arguments)
    if name == "recon_auto_run_create":
        return _run_create(arguments)
    if name == "recon_auto_run_update":
        return _run_update(arguments)
    if name == "recon_auto_run_list":
        return _run_list(arguments)
    if name == "recon_auto_run_get":
        return _run_get(arguments)
    if name == "recon_auto_run_rerun":
        return _run_rerun(arguments)
    if name == "recon_auto_run_verify":
        return _run_verify(arguments)
    if name == "recon_auto_run_job_create":
        return _run_job_create(arguments)
    if name == "recon_auto_run_job_update":
        return _run_job_update(arguments)
    if name == "recon_auto_run_exceptions":
        return _run_exceptions(arguments)
    if name == "recon_exception_get":
        return _exception_get(arguments)
    if name == "recon_exception_create":
        return _exception_create(arguments)
    if name == "recon_exception_update":
        return _exception_update(arguments)
    return {"success": False, "error": f"未知工具: {name}"}


def _require_user(auth_token: str) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("未提供认证 token，请先登录")
    user = get_user_from_token(token)
    if not user:
        raise ValueError("token 无效或已过期，请重新登录")
    if not user.get("company_id"):
        raise ValueError("当前用户未绑定公司")
    return user


def _parse_biz_date(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("biz_date 不能为空")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("biz_date 格式必须为 YYYY-MM-DD") from exc


def _merge_task_meta(arguments: dict[str, Any]) -> dict[str, Any]:
    task_meta = dict(arguments.get("task_meta_json") or {})
    input_bindings = arguments.get("input_bindings")
    if input_bindings is not None:
        task_meta["input_bindings"] = [
            item for item in list(input_bindings or []) if isinstance(item, dict)
        ]
    return task_meta


def _normalize_task_view(task: dict[str, Any]) -> dict[str, Any]:
    task_meta = dict(task.get("task_meta_json") or {})
    return {
        **task,
        "input_bindings": list(task_meta.get("input_bindings") or []),
    }


def _task_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    limit = max(1, min(int(arguments.get("limit") or 100), 500))
    offset = max(0, int(arguments.get("offset") or 0))
    include_disabled = bool(arguments.get("include_disabled", True))
    tasks = auth_db.list_recon_auto_tasks(
        company_id=company_id,
        include_disabled=include_disabled,
        limit=limit,
        offset=offset,
    )
    return {"success": True, "count": len(tasks), "tasks": [_normalize_task_view(task) for task in tasks]}


def _task_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_task_id = str(arguments.get("auto_task_id") or "").strip()
    task = auth_db.get_recon_auto_task(company_id=company_id, auto_task_id=auto_task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    return {"success": True, "task": _normalize_task_view(task)}


def _task_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    task_name = str(arguments.get("task_name") or "").strip()
    rule_code = str(arguments.get("rule_code") or "").strip()
    if not task_name:
        return {"success": False, "error": "task_name 不能为空"}
    if not rule_code:
        return {"success": False, "error": "rule_code 不能为空"}
    row = auth_db.create_recon_auto_task(
        company_id=company_id,
        task_name=task_name,
        rule_code=rule_code,
        is_enabled=bool(arguments.get("is_enabled", True)),
        schedule_type=str(arguments.get("schedule_type") or "daily"),
        schedule_expr=str(arguments.get("schedule_expr") or ""),
        biz_date_offset=str(arguments.get("biz_date_offset") or "T-1"),
        max_wait_until=str(arguments.get("max_wait_until") or ""),
        retry_policy_json=dict(arguments.get("retry_policy_json") or {}),
        input_mode=str(arguments.get("input_mode") or "bound_source"),
        bound_data_source_ids=list(arguments.get("bound_data_source_ids") or []),
        completeness_policy_json=dict(arguments.get("completeness_policy_json") or {}),
        auto_create_exceptions=bool(arguments.get("auto_create_exceptions", True)),
        auto_remind=bool(arguments.get("auto_remind", False)),
        channel_config_id=str(arguments.get("channel_config_id") or "") or None,
        reminder_policy_json=dict(arguments.get("reminder_policy_json") or {}),
        owner_mapping_json=dict(arguments.get("owner_mapping_json") or {}),
        task_meta_json=_merge_task_meta(arguments),
    )
    if not row:
        return {"success": False, "error": "创建任务失败"}
    return {"success": True, "task": _normalize_task_view(row)}


def _task_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_task_id = str(arguments.get("auto_task_id") or "").strip()
    if not auto_task_id:
        return {"success": False, "error": "auto_task_id 不能为空"}
    row = auth_db.update_recon_auto_task(
        company_id=company_id,
        auto_task_id=auto_task_id,
        task_name=arguments.get("task_name"),
        rule_code=arguments.get("rule_code"),
        is_enabled=arguments.get("is_enabled"),
        schedule_type=arguments.get("schedule_type"),
        schedule_expr=arguments.get("schedule_expr"),
        biz_date_offset=arguments.get("biz_date_offset"),
        max_wait_until=arguments.get("max_wait_until"),
        retry_policy_json=arguments.get("retry_policy_json"),
        input_mode=arguments.get("input_mode"),
        bound_data_source_ids=arguments.get("bound_data_source_ids"),
        completeness_policy_json=arguments.get("completeness_policy_json"),
        auto_create_exceptions=arguments.get("auto_create_exceptions"),
        auto_remind=arguments.get("auto_remind"),
        channel_config_id=arguments.get("channel_config_id"),
        reminder_policy_json=arguments.get("reminder_policy_json"),
        owner_mapping_json=arguments.get("owner_mapping_json"),
        task_meta_json=_merge_task_meta(arguments),
    )
    if not row:
        return {"success": False, "error": "任务不存在或更新失败"}
    return {"success": True, "task": _normalize_task_view(row)}


def _task_delete(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_task_id = str(arguments.get("auto_task_id") or "").strip()
    row = auth_db.disable_recon_auto_task(company_id=company_id, auto_task_id=auto_task_id)
    if not row:
        return {"success": False, "error": "任务不存在或删除失败"}
    return {"success": True, "task": row, "message": "任务已停用"}


def _run_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_task_id = str(arguments.get("auto_task_id") or "").strip()
    if not auto_task_id:
        return {"success": False, "error": "auto_task_id 不能为空"}
    biz_date = _parse_biz_date(str(arguments.get("biz_date") or ""))
    task = auth_db.get_recon_auto_task(company_id=company_id, auto_task_id=auto_task_id)
    if not task:
        return {"success": False, "error": "任务不存在"}
    run = auth_db.create_recon_auto_run(
        company_id=company_id,
        auto_task_id=auto_task_id,
        biz_date=biz_date,
        trigger_mode=str(arguments.get("trigger_mode") or "cron"),
        run_status=str(arguments.get("run_status") or "scheduled"),
        readiness_status=str(arguments.get("readiness_status") or "waiting_data"),
        closure_status=str(arguments.get("closure_status") or "open"),
        task_snapshot_json=dict(arguments.get("task_snapshot_json") or task),
        source_snapshot_json=dict(arguments.get("source_snapshot_json") or {}),
        recon_result_summary_json=dict(arguments.get("recon_result_summary_json") or {}),
        anomaly_count=max(0, int(arguments.get("anomaly_count") or 0)),
        error_message=str(arguments.get("error_message") or ""),
    )
    if not run:
        return {"success": False, "error": "创建运行记录失败"}
    return {"success": True, "run": run}


def _run_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    if not auto_run_id:
        return {"success": False, "error": "auto_run_id 不能为空"}
    run = auth_db.update_recon_auto_run_status(
        company_id=company_id,
        auto_run_id=auto_run_id,
        run_status=arguments.get("run_status"),
        readiness_status=arguments.get("readiness_status"),
        closure_status=arguments.get("closure_status"),
        recon_result_summary_json=arguments.get("recon_result_summary_json"),
        anomaly_count=arguments.get("anomaly_count"),
        error_message=arguments.get("error_message"),
        started_at_now=bool(arguments.get("started_at_now", False)),
        finished_at_now=bool(arguments.get("finished_at_now", False)),
    )
    if not run:
        return {"success": False, "error": "运行记录不存在或更新失败"}
    return {"success": True, "run": run}


def _run_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    limit = max(1, min(int(arguments.get("limit") or 100), 500))
    offset = max(0, int(arguments.get("offset") or 0))
    auto_task_id = str(arguments.get("auto_task_id") or "").strip() or None
    runs = auth_db.list_recon_auto_runs(
        company_id=company_id,
        auto_task_id=auto_task_id,
        limit=limit,
        offset=offset,
    )
    return {"success": True, "count": len(runs), "runs": runs}


def _run_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    run = auth_db.get_recon_auto_run(company_id=company_id, auto_run_id=auto_run_id)
    if not run:
        return {"success": False, "error": "运行记录不存在"}
    return {"success": True, "run": run}


def _run_rerun(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    reason = str(arguments.get("reason") or "").strip()
    source_run = auth_db.get_recon_auto_run(company_id=company_id, auto_run_id=auto_run_id)
    if not source_run:
        return {"success": False, "error": "源运行记录不存在"}

    new_run = auth_db.create_recon_auto_run(
        company_id=company_id,
        auto_task_id=str(source_run.get("auto_task_id") or ""),
        biz_date=str(source_run.get("biz_date") or ""),
        trigger_mode="rerun",
        run_status="scheduled",
        readiness_status="waiting_data",
        closure_status="open",
        task_snapshot_json=dict(source_run.get("task_snapshot_json") or {}),
        source_snapshot_json=dict(source_run.get("source_snapshot_json") or {}),
        recon_result_summary_json={},
        anomaly_count=0,
        error_message="",
    )
    if not new_run:
        return {"success": False, "error": "创建重跑记录失败"}

    run_job = auth_db.create_recon_run_job(
        company_id=company_id,
        auto_run_id=str(new_run.get("id") or ""),
        job_type="recon_job",
        job_status="queued",
        attempt_no=1,
        input_json={"source_run_id": auto_run_id, "reason": reason},
        output_json={},
    )
    return {"success": True, "run": new_run, "run_job": run_job}


def _run_verify(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    reason = str(arguments.get("reason") or "").strip()
    source_run = auth_db.get_recon_auto_run(company_id=company_id, auto_run_id=auto_run_id)
    if not source_run:
        return {"success": False, "error": "源运行记录不存在"}

    auth_db.update_recon_auto_run_status(
        company_id=company_id,
        auto_run_id=auto_run_id,
        run_status="waiting_verify",
        closure_status="waiting_verify",
    )

    verify_run = auth_db.create_recon_auto_run(
        company_id=company_id,
        auto_task_id=str(source_run.get("auto_task_id") or ""),
        biz_date=str(source_run.get("biz_date") or ""),
        trigger_mode="verify",
        run_status="verifying",
        readiness_status="data_ready",
        closure_status="in_progress",
        task_snapshot_json=dict(source_run.get("task_snapshot_json") or {}),
        source_snapshot_json=dict(source_run.get("source_snapshot_json") or {}),
        recon_result_summary_json={},
        anomaly_count=0,
        error_message="",
    )
    if not verify_run:
        return {"success": False, "error": "创建验证记录失败"}

    run_job = auth_db.create_recon_run_job(
        company_id=company_id,
        auto_run_id=str(verify_run.get("id") or ""),
        job_type="verify_recon_job",
        job_status="queued",
        attempt_no=1,
        input_json={"source_run_id": auto_run_id, "reason": reason},
        output_json={},
    )
    return {"success": True, "run": verify_run, "run_job": run_job}


def _run_job_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    job_type = str(arguments.get("job_type") or "").strip()
    if not auto_run_id:
        return {"success": False, "error": "auto_run_id 不能为空"}
    if not job_type:
        return {"success": False, "error": "job_type 不能为空"}
    run_job = auth_db.create_recon_run_job(
        company_id=company_id,
        auto_run_id=auto_run_id,
        job_type=job_type,
        job_status=str(arguments.get("job_status") or "queued"),
        attempt_no=max(1, int(arguments.get("attempt_no") or 1)),
        idempotency_key=str(arguments.get("idempotency_key") or ""),
        input_json=dict(arguments.get("input_json") or {}),
        output_json=dict(arguments.get("output_json") or {}),
        error_message=str(arguments.get("error_message") or ""),
    )
    if not run_job:
        return {"success": False, "error": "创建 run_job 失败"}
    return {"success": True, "run_job": run_job}


def _run_job_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    run_job_id = str(arguments.get("run_job_id") or "").strip()
    if not run_job_id:
        return {"success": False, "error": "run_job_id 不能为空"}
    run_job = auth_db.update_recon_run_job(
        company_id=company_id,
        run_job_id=run_job_id,
        job_status=arguments.get("job_status"),
        output_json=arguments.get("output_json"),
        error_message=arguments.get("error_message"),
        started_at_now=bool(arguments.get("started_at_now", False)),
        finished_at_now=bool(arguments.get("finished_at_now", False)),
    )
    if not run_job:
        return {"success": False, "error": "run_job 不存在或更新失败"}
    return {"success": True, "run_job": run_job}


def _run_exceptions(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    limit = max(1, min(int(arguments.get("limit") or 500), 1000))
    offset = max(0, int(arguments.get("offset") or 0))
    items = auth_db.list_recon_exception_tasks(
        company_id=company_id,
        auto_run_id=auto_run_id,
        limit=limit,
        offset=offset,
    )
    return {"success": True, "count": len(items), "exceptions": items}


def _exception_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    exception_id = str(arguments.get("exception_id") or "").strip()
    if not exception_id:
        return {"success": False, "error": "exception_id 不能为空"}
    item = auth_db.get_recon_exception_task(company_id=company_id, exception_id=exception_id)
    if not item:
        return {"success": False, "error": "异常任务不存在"}
    return {"success": True, "exception": item}


def _exception_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    auto_task_id = str(arguments.get("auto_task_id") or "").strip()
    auto_run_id = str(arguments.get("auto_run_id") or "").strip()
    anomaly_key = str(arguments.get("anomaly_key") or "").strip()
    anomaly_type = str(arguments.get("anomaly_type") or "").strip()
    summary = str(arguments.get("summary") or "").strip()
    if not auto_task_id or not auto_run_id or not anomaly_key or not anomaly_type or not summary:
        return {"success": False, "error": "auto_task_id、auto_run_id、anomaly_key、anomaly_type、summary 不能为空"}
    item = auth_db.create_recon_exception_task(
        company_id=company_id,
        auto_task_id=auto_task_id,
        auto_run_id=auto_run_id,
        anomaly_key=anomaly_key,
        anomaly_type=anomaly_type,
        summary=summary,
        detail_json=dict(arguments.get("detail_json") or {}),
        owner_name=str(arguments.get("owner_name") or ""),
        owner_identifier=str(arguments.get("owner_identifier") or ""),
        owner_contact_json=dict(arguments.get("owner_contact_json") or {}),
        reminder_status=str(arguments.get("reminder_status") or "pending"),
        processing_status=str(arguments.get("processing_status") or "pending"),
        fix_status=str(arguments.get("fix_status") or "pending"),
        latest_feedback=str(arguments.get("latest_feedback") or ""),
        feedback_json=dict(arguments.get("feedback_json") or {}),
        verify_required=bool(arguments.get("verify_required", False)),
        verify_run_id=str(arguments.get("verify_run_id") or "") or None,
        is_closed=bool(arguments.get("is_closed", False)),
    )
    if not item:
        return {"success": False, "error": "创建异常任务失败"}
    return {"success": True, "exception": item}


def _exception_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    exception_id = str(arguments.get("exception_id") or "").strip()
    if not exception_id:
        return {"success": False, "error": "exception_id 不能为空"}
    updated = auth_db.update_recon_exception_task(
        company_id=company_id,
        exception_id=exception_id,
        owner_name=arguments.get("owner_name"),
        owner_identifier=arguments.get("owner_identifier"),
        owner_contact_json=arguments.get("owner_contact_json"),
        reminder_status=arguments.get("reminder_status"),
        processing_status=arguments.get("processing_status"),
        fix_status=arguments.get("fix_status"),
        latest_feedback=arguments.get("latest_feedback"),
        feedback_json=arguments.get("feedback_json"),
        verify_required=arguments.get("verify_required"),
        verify_run_id=arguments.get("verify_run_id"),
        is_closed=arguments.get("is_closed"),
    )
    if not updated:
        return {"success": False, "error": "异常任务不存在或更新失败"}
    return {"success": True, "exception": updated}
