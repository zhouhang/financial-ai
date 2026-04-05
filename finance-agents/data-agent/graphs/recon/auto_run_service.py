"""自动对账任务执行与异常催办服务。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from graphs.recon.execution_service import (
    build_execution_request,
    build_recon_ctx_update_from_execution,
    build_recon_observation,
    run_recon_execution,
)
from graphs.recon.pipeline_service import execute_headless_recon_pipeline
from services.notifications import get_notification_adapter
from services.notifications.models import UnifiedTodoStatus
from tools.mcp_client import (
    data_source_get_published_snapshot,
    get_file_validation_rule,
    recon_auto_run_create,
    recon_auto_run_get,
    recon_auto_run_job_create,
    recon_auto_run_job_update,
    recon_auto_run_update,
    recon_auto_task_get,
    recon_exception_create,
    recon_exception_get,
    recon_exception_update,
)

logger = logging.getLogger(__name__)
_BIZ_DATE_PLACEHOLDER = re.compile(r"\{\{\s*biz_date\s*\}\}")


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _parse_biz_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("biz_date 不能为空")
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def _normalize_binding(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    source_id = str(item.get("data_source_id") or item.get("source_id") or "").strip()
    table_name = str(item.get("table_name") or "").strip()
    if not source_id or not table_name:
        return None
    return {
        "data_source_id": source_id,
        "table_name": table_name,
        "resource_key": str(item.get("resource_key") or "default").strip() or "default",
        "required": bool(item.get("required", True)),
        "query": _safe_dict(item.get("query")),
        "dataset_source_type": str(item.get("dataset_source_type") or "snapshot").strip() or "snapshot",
    }


def _extract_input_bindings(task: dict[str, Any], override_bindings: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    raw_bindings = override_bindings
    if raw_bindings is None:
        raw_bindings = _safe_list(task.get("input_bindings"))
    if raw_bindings is None or len(raw_bindings) == 0:
        task_meta = _safe_dict(task.get("task_meta_json"))
        raw_bindings = _safe_list(task_meta.get("input_bindings"))

    result: list[dict[str, Any]] = []
    for item in raw_bindings or []:
        binding = _normalize_binding(item if isinstance(item, dict) else {})
        if binding is not None:
            result.append(binding)
    return result


def _resolve_owner(owner_mapping: dict[str, Any], anomaly: dict[str, Any]) -> dict[str, Any]:
    if not owner_mapping:
        return {}

    anomaly_type = str(anomaly.get("anomaly_type") or "").strip()
    summary = str(anomaly.get("summary") or "").strip()

    by_type = owner_mapping.get("anomaly_type_to_owner")
    if isinstance(by_type, dict):
        owner = by_type.get(anomaly_type)
        if isinstance(owner, dict):
            return owner

    mappings = owner_mapping.get("mappings")
    if isinstance(mappings, list):
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            match_types = mapping.get("anomaly_types")
            if not isinstance(match_types, list):
                single_type = str(mapping.get("anomaly_type") or "").strip()
                match_types = [single_type] if single_type else []
            match_types = [str(item).strip() for item in match_types if str(item).strip()]
            if match_types and anomaly_type not in match_types:
                continue

            keywords = mapping.get("keywords")
            if not isinstance(keywords, list):
                keyword = str(mapping.get("keyword") or "").strip()
                keywords = [keyword] if keyword else []
            keywords = [str(item).strip() for item in keywords if str(item).strip()]
            if keywords and not any(keyword in summary for keyword in keywords):
                continue

            owner = mapping.get("owner")
            if isinstance(owner, dict):
                return owner

    default_owner = owner_mapping.get("default_owner")
    return default_owner if isinstance(default_owner, dict) else {}


def _build_source_snapshot_summary(bindings: list[dict[str, Any]], snapshot_results: list[dict[str, Any]], missing: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "bindings": bindings,
        "snapshots": snapshot_results,
        "missing": missing,
    }


def _resolve_query_placeholders(value: Any, *, biz_date: str) -> Any:
    if isinstance(value, str):
        return _BIZ_DATE_PLACEHOLDER.sub(biz_date, value)
    if isinstance(value, list):
        return [_resolve_query_placeholders(item, biz_date=biz_date) for item in value]
    if isinstance(value, dict):
        return {str(key): _resolve_query_placeholders(item, biz_date=biz_date) for key, item in value.items()}
    return value


def _parse_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        logger.warning("[recon][auto_run] 非法 day offset=%s，已回退为 %s", value, default)
        return default


def _shift_biz_date(biz_date: str, offset_days: int) -> str:
    base_date = datetime.strptime(biz_date, "%Y-%m-%d").date()
    return (base_date + timedelta(days=offset_days)).isoformat()


def _materialize_binding_query(binding: dict[str, Any], *, biz_date: str) -> dict[str, Any]:
    resolved_query = _safe_dict(_resolve_query_placeholders(_safe_dict(binding.get("query")), biz_date=biz_date))
    biz_date_filter = _safe_dict(resolved_query.pop("biz_date_filter"))
    if not biz_date_filter:
        return resolved_query

    field_name = str(
        biz_date_filter.get("field")
        or biz_date_filter.get("date_field")
        or biz_date_filter.get("column")
        or ""
    ).strip()
    if not field_name:
        return resolved_query

    offset_days = _parse_int(biz_date_filter.get("offset_days"), 0)
    filters = _safe_dict(resolved_query.get("filters"))
    filters[field_name] = _shift_biz_date(biz_date, offset_days)
    resolved_query["filters"] = filters
    return resolved_query


def _build_recon_inputs_from_snapshots(snapshot_results: list[dict[str, Any]], *, biz_date: str) -> list[dict[str, Any]]:
    recon_inputs: list[dict[str, Any]] = []
    for item in snapshot_results:
        snapshot = _safe_dict(item.get("published_snapshot"))
        source_id = str(item.get("data_source_id") or "").strip()
        table_name = str(item.get("table_name") or "").strip()
        resource_key = str(item.get("resource_key") or "default").strip() or "default"
        dataset_source_type = str(item.get("dataset_source_type") or "snapshot").strip() or "snapshot"
        if not source_id or not table_name:
            continue
        query = {"resource_key": resource_key}
        snapshot_id = str(snapshot.get("snapshot_id") or snapshot.get("id") or "").strip()
        if snapshot_id:
            query["snapshot_id"] = snapshot_id
        query.update(_materialize_binding_query(item, biz_date=biz_date))
        recon_inputs.append(
            {
                "table_name": table_name,
                "input_type": "dataset",
                "payload": {
                    "dataset_ref": {
                        "source_type": dataset_source_type,
                        "source_key": source_id,
                        "query": query,
                    }
                },
            }
        )
    return recon_inputs


def _build_exception_payloads(task: dict[str, Any], run: dict[str, Any], anomaly_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owner_mapping = _safe_dict(task.get("owner_mapping_json"))
    auto_task_id = str(task.get("id") or "")
    auto_run_id = str(run.get("id") or "")
    payloads: list[dict[str, Any]] = []
    for item in anomaly_items:
        if not isinstance(item, dict):
            continue
        owner = _resolve_owner(owner_mapping, item)
        payloads.append(
            {
                "auto_task_id": auto_task_id,
                "auto_run_id": auto_run_id,
                "anomaly_key": str(item.get("item_id") or item.get("anomaly_key") or ""),
                "anomaly_type": str(item.get("anomaly_type") or "unknown"),
                "summary": str(item.get("summary") or ""),
                "detail_json": item,
                "owner_name": str(owner.get("name") or ""),
                "owner_identifier": str(owner.get("identifier") or ""),
                "owner_contact_json": _safe_dict(owner.get("contact")),
                "reminder_status": "pending",
                "processing_status": "pending",
                "fix_status": "pending",
                "latest_feedback": "",
                "feedback_json": {},
                "verify_required": False,
                "is_closed": False,
            }
        )
    return payloads


def _build_run_job_key(auto_run_id: str, job_type: str, biz_date: str) -> str:
    seed = json.dumps(
        {"auto_run_id": auto_run_id, "job_type": job_type, "biz_date": biz_date},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def _merge_feedback(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return {**_safe_dict(existing), **_safe_dict(patch)}


def _compose_reminder_text(task: dict[str, Any], run: dict[str, Any], exception: dict[str, Any]) -> tuple[str, str]:
    task_name = str(task.get("task_name") or task.get("name") or "自动对账任务")
    biz_date = str(run.get("biz_date") or "")
    title = f"{task_name} 异常催办"
    content = "\n".join(
        [
            f"任务：{task_name}",
            f"业务日期：{biz_date}" if biz_date else "业务日期：未提供",
            f"异常类型：{str(exception.get('anomaly_type') or '未知')}",
            f"异常摘要：{str(exception.get('summary') or '')}",
            "请处理完成后在钉钉待办中标记完成，并同步给财务复核。",
        ]
    )
    return title, content


async def execute_auto_task_run(
    *,
    auth_token: str,
    auto_task_id: str,
    biz_date: str,
    trigger_mode: str = "manual",
    run_context: dict[str, Any] | None = None,
    input_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task_result = await recon_auto_task_get(auth_token, auto_task_id)
    if not task_result.get("success"):
        return {"success": False, "error": task_result.get("error", "自动任务不存在")}
    task = _safe_dict(task_result.get("task"))

    normalized_biz_date = _parse_biz_date(biz_date)
    bindings = _extract_input_bindings(task, override_bindings=input_bindings)
    if not bindings:
        return {"success": False, "error": "任务未配置 input_bindings，无法构建自动对账输入"}

    source_snapshots: list[dict[str, Any]] = []
    missing_bindings: list[dict[str, Any]] = []
    for binding in bindings:
        snapshot_result = await data_source_get_published_snapshot(
            auth_token,
            binding["data_source_id"],
            resource_key=binding["resource_key"],
        )
        published_snapshot = _safe_dict(snapshot_result.get("published_snapshot"))
        if snapshot_result.get("success") and published_snapshot:
            source_snapshots.append({**binding, "published_snapshot": published_snapshot})
        else:
            missing_bindings.append(
                {
                    **binding,
                    "error": str(snapshot_result.get("error") or snapshot_result.get("message") or "暂无已发布快照"),
                }
            )

    source_snapshot_json = _build_source_snapshot_summary(bindings, source_snapshots, missing_bindings)
    run_create = await recon_auto_run_create(
        auth_token,
        {
            "auto_task_id": auto_task_id,
            "biz_date": normalized_biz_date,
            "trigger_mode": trigger_mode,
            "run_status": "waiting_data" if missing_bindings else "ready",
            "readiness_status": "data_partial" if missing_bindings else "data_ready",
            "closure_status": "open",
            "task_snapshot_json": task,
            "source_snapshot_json": source_snapshot_json,
            "recon_result_summary_json": {},
            "anomaly_count": 0,
        },
    )
    if not run_create.get("success"):
        return {"success": False, "error": run_create.get("error", "创建自动运行批次失败")}
    run = _safe_dict(run_create.get("run"))
    auto_run_id = str(run.get("id") or "")

    run_job = await recon_auto_run_job_create(
        auth_token,
        {
            "auto_run_id": auto_run_id,
            "job_type": "recon_job",
            "job_status": "queued",
            "attempt_no": 1,
            "idempotency_key": _build_run_job_key(auto_run_id, "recon_job", normalized_biz_date),
            "input_json": {"bindings": bindings, "biz_date": normalized_biz_date},
            "output_json": {},
            "error_message": "",
        },
    )
    run_job_record = _safe_dict(run_job.get("run_job"))

    if missing_bindings:
        message = "存在未就绪的数据源快照，自动运行已记录为待补数"
        await recon_auto_run_update(
            auth_token,
            auto_run_id,
            {
                "run_status": "waiting_data",
                "readiness_status": "data_partial",
                "closure_status": "open",
                "error_message": message,
            },
        )
        if run_job_record:
            await recon_auto_run_job_update(
                auth_token,
                str(run_job_record.get("id") or ""),
                {
                    "job_status": "failed",
                    "output_json": {"missing_bindings": missing_bindings},
                    "error_message": message,
                    "finished_at_now": True,
                },
            )
        run_detail = await recon_auto_run_get(auth_token, auto_run_id)
        return {
            "success": False,
            "error": message,
            "run": _safe_dict(run_detail.get("run")) or run,
            "run_job": run_job_record,
            "missing_bindings": missing_bindings,
        }

    await recon_auto_run_update(
        auth_token,
        auto_run_id,
        {
            "run_status": "running_recon",
            "readiness_status": "data_ready",
            "closure_status": "in_progress",
            "started_at_now": True,
        },
    )
    if run_job_record:
        await recon_auto_run_job_update(
            auth_token,
            str(run_job_record.get("id") or ""),
            {
                "job_status": "running",
                "started_at_now": True,
            },
        )

    rule_response = await get_file_validation_rule(str(task.get("rule_code") or ""), auth_token)
    if not rule_response.get("success"):
        message = str(rule_response.get("error") or "未找到对账规则")
        await recon_auto_run_update(
            auth_token,
            auto_run_id,
            {
                "run_status": "recon_failed",
                "readiness_status": "data_ready",
                "closure_status": "open",
                "error_message": message,
                "finished_at_now": True,
            },
        )
        if run_job_record:
            await recon_auto_run_job_update(
                auth_token,
                str(run_job_record.get("id") or ""),
                {
                    "job_status": "failed",
                    "error_message": message,
                    "finished_at_now": True,
                },
            )
        return {"success": False, "error": message, "run": run, "run_job": run_job_record}

    rule_record = _safe_dict(rule_response.get("data"))
    rule_data = _safe_dict(rule_record.get("rule"))
    rule_name = str(rule_data.get("rule_name") or rule_record.get("name") or task.get("rule_code") or "")
    recon_inputs = _build_recon_inputs_from_snapshots(source_snapshots, biz_date=normalized_biz_date)
    run_ctx = {
        **_safe_dict(run_context),
        "run_id": auto_run_id,
        "biz_date": normalized_biz_date,
        "auto_task_id": auto_task_id,
        "trigger_type": trigger_mode,
        "entry_mode": "dataset",
        "job_name": str(task.get("task_name") or ""),
    }

    pipeline_result = await execute_headless_recon_pipeline(
        rule_code=str(task.get("rule_code") or ""),
        rule_id="",
        rule_name=rule_name,
        rule=rule_data,
        auth_token=auth_token,
        recon_inputs=recon_inputs,
        run_context=run_ctx,
        run_id=auto_run_id,
        trigger_type=trigger_mode,
        entry_mode="dataset",
        ref_to_display_name={},
        build_execution_request_fn=build_execution_request,
        run_recon_execution_fn=run_recon_execution,
        build_recon_observation_fn=build_recon_observation,
        build_recon_ctx_update_fn=build_recon_ctx_update_from_execution,
    )

    if not pipeline_result.get("ok"):
        error_message = str(pipeline_result.get("exec_error") or "对账执行失败")
        await recon_auto_run_update(
            auth_token,
            auto_run_id,
            {
                "run_status": "recon_failed",
                "readiness_status": "data_ready",
                "closure_status": "open",
                "error_message": error_message,
                "finished_at_now": True,
            },
        )
        if run_job_record:
            await recon_auto_run_job_update(
                auth_token,
                str(run_job_record.get("id") or ""),
                {
                    "job_status": "failed",
                    "output_json": pipeline_result,
                    "error_message": error_message,
                    "finished_at_now": True,
                },
            )
        run_detail = await recon_auto_run_get(auth_token, auto_run_id)
        return {
            "success": False,
            "error": error_message,
            "run": _safe_dict(run_detail.get("run")) or run,
            "run_job": run_job_record,
            "pipeline_result": pipeline_result,
        }

    recon_observation = _safe_dict(pipeline_result.get("recon_observation"))
    execution_result = _safe_dict(pipeline_result.get("execution_result"))
    anomaly_items = [item for item in _safe_list(recon_observation.get("anomaly_items")) if isinstance(item, dict)]

    created_exceptions: list[dict[str, Any]] = []
    if bool(task.get("auto_create_exceptions", True)) and anomaly_items:
        for payload in _build_exception_payloads(task, run, anomaly_items):
            create_result = await recon_exception_create(auth_token, payload)
            if create_result.get("success"):
                created_exceptions.append(_safe_dict(create_result.get("exception")))

    run_status = "closed" if len(anomaly_items) == 0 else "exception_open"
    closure_status = "closed" if len(anomaly_items) == 0 else "open"
    run_update_result = await recon_auto_run_update(
        auth_token,
        auto_run_id,
        {
            "run_status": run_status,
            "readiness_status": "data_ready",
            "closure_status": closure_status,
            "recon_result_summary_json": _safe_dict(recon_observation.get("summary")),
            "anomaly_count": len(anomaly_items),
            "error_message": "",
            "finished_at_now": True,
        },
    )
    if run_job_record:
        await recon_auto_run_job_update(
            auth_token,
            str(run_job_record.get("id") or ""),
            {
                "job_status": "succeeded",
                "output_json": {
                    "recon_summary": _safe_dict(recon_observation.get("summary")),
                    "anomaly_count": len(anomaly_items),
                    "exception_count": len(created_exceptions),
                },
                "finished_at_now": True,
            },
        )

    return {
        "success": True,
        "task": task,
        "run": _safe_dict(run_update_result.get("run")) or run,
        "run_job": run_job_record,
        "exceptions": created_exceptions,
        "execution_result": execution_result,
        "recon_observation": recon_observation,
    }


async def send_exception_reminder(
    *,
    auth_token: str,
    exception_id: str,
    provider: str = "",
    channel_code: str = "",
    due_time: str = "",
    title: str = "",
    content: str = "",
) -> dict[str, Any]:
    exception_result = await recon_exception_get(auth_token, exception_id)
    if not exception_result.get("success"):
        return {"success": False, "error": exception_result.get("error", "异常任务不存在")}
    exception = _safe_dict(exception_result.get("exception"))

    run_result = await recon_auto_run_get(auth_token, str(exception.get("auto_run_id") or ""))
    run = _safe_dict(run_result.get("run"))
    task_result = await recon_auto_task_get(auth_token, str(exception.get("auto_task_id") or ""))
    task = _safe_dict(task_result.get("task"))

    owner_name = str(exception.get("owner_name") or "").strip()
    owner_identifier = str(exception.get("owner_identifier") or "").strip()
    if not owner_name and not owner_identifier:
        return {"success": False, "error": "异常未配置责任人，无法催办"}

    adapter = get_notification_adapter(
        provider=provider or None,
        company_id=str(exception.get("company_id") or ""),
        channel_code=channel_code or None,
    )

    resolved = None
    if owner_identifier:
        resolved_result = adapter.resolve_user(user_id=owner_identifier)
        if resolved_result.success:
            resolved = resolved_result.resolved_user or (resolved_result.users[0] if resolved_result.users else None)
    if resolved is None and owner_name:
        resolved_result = adapter.resolve_user(keyword=owner_name)
        if resolved_result.success:
            resolved = resolved_result.resolved_user or (resolved_result.users[0] if resolved_result.users else None)
    if resolved is None:
        await recon_exception_update(
            auth_token,
            exception_id,
            {
                "reminder_status": "owner_unresolved",
                "latest_feedback": "责任人未能解析为可触达用户",
            },
        )
        return {"success": False, "error": "责任人未能解析为可触达用户", "exception": exception}

    reminder_title, reminder_content = _compose_reminder_text(task, run, exception)
    reminder = adapter.send_reminder(
        title=title or reminder_title,
        content=content or reminder_content,
        assignee_user_id=resolved.user_id,
        due_time=due_time,
        source_id=exception_id,
    )
    if not reminder.success:
        await recon_exception_update(
            auth_token,
            exception_id,
            {
                "owner_identifier": resolved.user_id,
                "owner_contact_json": {"provider": adapter.provider, "display_name": resolved.display_name, "mobile": resolved.mobile},
                "reminder_status": "send_failed",
                "latest_feedback": reminder.message,
            },
        )
        return {"success": False, "error": reminder.message, "exception": exception}

    existing_feedback = _safe_dict(exception.get("feedback_json"))
    next_feedback = _merge_feedback(
        existing_feedback,
        {
            "provider": adapter.provider,
            "todo_id": reminder.todo_result.todo.todo_id if reminder.todo_result and reminder.todo_result.todo else "",
            "message_id": reminder.bot_result.message_id if reminder.bot_result else "",
            "last_reminded_at": datetime.now().isoformat(),
        },
    )
    update_result = await recon_exception_update(
        auth_token,
        exception_id,
        {
            "owner_name": resolved.display_name or owner_name,
            "owner_identifier": resolved.user_id,
            "owner_contact_json": {"provider": adapter.provider, "display_name": resolved.display_name, "mobile": resolved.mobile},
            "reminder_status": "sent",
            "latest_feedback": "已发送催办消息并创建待办",
            "feedback_json": next_feedback,
        },
    )
    return {
        "success": True,
        "exception": _safe_dict(update_result.get("exception")) or exception,
        "reminder": {
            "provider": adapter.provider,
            "todo_id": next_feedback.get("todo_id"),
            "message_id": next_feedback.get("message_id"),
        },
    }


async def sync_exception_reminder(
    *,
    auth_token: str,
    exception_id: str,
    provider: str = "",
    channel_code: str = "",
    max_polls: int = 1,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    exception_result = await recon_exception_get(auth_token, exception_id)
    if not exception_result.get("success"):
        return {"success": False, "error": exception_result.get("error", "异常任务不存在")}
    exception = _safe_dict(exception_result.get("exception"))
    feedback_json = _safe_dict(exception.get("feedback_json"))
    todo_id = str(feedback_json.get("todo_id") or "").strip()
    if not todo_id:
        return {"success": False, "error": "异常尚未创建待办，无法同步状态", "exception": exception}

    adapter = get_notification_adapter(
        provider=provider or None,
        company_id=str(exception.get("company_id") or ""),
        channel_code=channel_code or None,
    )
    sync_result = adapter.sync_todo_status(
        todo_id=todo_id,
        max_polls=max(1, max_polls),
        poll_interval_seconds=max(0.5, poll_interval_seconds),
    )
    if not sync_result.success:
        await recon_exception_update(
            auth_token,
            exception_id,
            {
                "latest_feedback": sync_result.message,
            },
        )
        return {"success": False, "error": sync_result.message, "exception": exception}

    status = sync_result.status
    patch: dict[str, Any] = {
        "feedback_json": _merge_feedback(feedback_json, {"todo_status": status.value, "todo_synced_at": datetime.now().isoformat()}),
        "latest_feedback": f"待办状态已同步为 {status.value}",
    }
    if status == UnifiedTodoStatus.COMPLETED:
        patch.update(
            {
                "processing_status": "owner_done",
                "fix_status": "ready_for_verify",
                "verify_required": True,
                "reminder_status": "completed",
            }
        )
    elif status == UnifiedTodoStatus.CANCELLED:
        patch["reminder_status"] = "cancelled"
    elif status == UnifiedTodoStatus.FAILED:
        patch["reminder_status"] = "sync_failed"

    update_result = await recon_exception_update(auth_token, exception_id, patch)
    return {
        "success": True,
        "exception": _safe_dict(update_result.get("exception")) or exception,
        "sync": {
            "todo_id": todo_id,
            "status": status.value,
            "is_terminal": bool(sync_result.is_terminal),
            "polls": int(sync_result.polls),
        },
    }
