"""Nodes for auto scheme run graph."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from models import AgentState
from tools.mcp_client import (
    call_mcp_tool,
    data_source_get_published_snapshot,
    get_file_validation_rule,
    recon_auto_task_get,
)

logger = logging.getLogger(__name__)

COLLECT_MAX_RETRIES = 3
COLLECT_RETRY_INTERVAL_SECONDS = 1.0


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def _is_unknown_tool_error(error: Any) -> bool:
    text = str(error or "").lower()
    return "unknown tool" in text or "未知的工具" in text or "no such tool" in text


def _get_binding_source_id(binding: dict[str, Any]) -> str:
    return str(binding.get("data_source_id") or binding.get("source_id") or "").strip()


def _get_binding_resource_key(binding: dict[str, Any]) -> str:
    return str(binding.get("resource_key") or "default").strip() or "default"


def _get_binding_required(binding: dict[str, Any]) -> bool:
    if "required" not in binding:
        return True
    return bool(binding.get("required"))


def _build_recon_inputs_from_ready_snapshots(
    ready_snapshots: list[dict[str, Any]],
    *,
    biz_date: str,
) -> list[dict[str, Any]]:
    recon_inputs: list[dict[str, Any]] = []
    for item in ready_snapshots:
        binding = _safe_dict(item.get("binding"))
        snapshot = _safe_dict(item.get("published_snapshot"))
        table_name = str(binding.get("table_name") or "").strip()
        source_id = _get_binding_source_id(binding)
        if not table_name or not source_id:
            continue
        query = {"resource_key": _get_binding_resource_key(binding)}
        snapshot_id = str(snapshot.get("snapshot_id") or snapshot.get("id") or "").strip()
        if snapshot_id:
            query["snapshot_id"] = snapshot_id

        raw_query = _safe_dict(binding.get("query"))
        filters = _safe_dict(raw_query.get("filters"))
        # Keep simple and explicit: bind biz_date to configured date field when provided.
        biz_date_field = str(
            raw_query.get("biz_date_field")
            or raw_query.get("date_field")
            or ""
        ).strip()
        if biz_date_field:
            filters[biz_date_field] = biz_date
        if filters:
            query["filters"] = filters

        dataset_source_type = str(binding.get("dataset_source_type") or "snapshot").strip() or "snapshot"
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


def _normalize_biz_date_offset(offset: str) -> int:
    normalized = str(offset or "").strip().lower()
    if not normalized:
        return -1
    if normalized in {"t", "t+0", "today", "current_day"}:
        return 0
    if normalized in {"t-1", "previous_day", "yesterday"}:
        return -1
    if normalized.startswith("t+") or normalized.startswith("t-"):
        sign = 1 if normalized.startswith("t+") else -1
        try:
            return sign * int(normalized[2:])
        except ValueError:
            return -1
    return -1


def _compute_biz_date(run_plan: dict[str, Any], run_context: dict[str, Any], explicit_biz_date: str) -> str:
    if explicit_biz_date:
        return explicit_biz_date
    date_from_ctx = str(run_context.get("biz_date") or "").strip()
    if date_from_ctx:
        return date_from_ctx
    offset = _normalize_biz_date_offset(str(run_plan.get("biz_date_offset") or "t-1"))
    return (date.today() + timedelta(days=offset)).isoformat()


async def _persist_execution_run(
    *,
    auth_token: str,
    ctx: dict[str, Any],
    execution_status: str,
    failed_stage: str = "",
    failed_reason: str = "",
) -> dict[str, Any]:
    scheme_code = str(ctx.get("scheme_code") or "").strip()
    if not auth_token or not scheme_code:
        return {}

    run_record = _safe_dict(ctx.get("execution_run_record"))
    subtasks_json = [item for item in _safe_list(ctx.get("subtasks_json")) if isinstance(item, dict)]
    run_context = _safe_dict(ctx.get("run_context"))
    source_snapshot_json = _safe_dict(ctx.get("source_snapshot_json"))
    recon_observation = _safe_dict(ctx.get("recon_observation"))
    summary = _safe_dict(recon_observation.get("summary"))
    artifacts = _safe_dict(recon_observation.get("artifacts"))
    anomaly_items = _safe_list(recon_observation.get("anomaly_items"))

    if run_record.get("id"):
        result = await call_mcp_tool(
            "execution_run_update",
            {
                "auth_token": auth_token,
                "run_id": str(run_record.get("id")),
                "execution_status": execution_status,
                "failed_stage": failed_stage,
                "failed_reason": failed_reason,
                "run_context_json": run_context,
                "source_snapshot_json": source_snapshot_json,
                "subtasks_json": subtasks_json,
                "recon_result_summary_json": summary,
                "artifacts_json": artifacts,
                "anomaly_count": len(anomaly_items),
                "finished_at_now": execution_status not in {"running", "queued"},
            },
        )
        if bool(result.get("success")):
            return _safe_dict(result.get("run"))
        return run_record

    result = await call_mcp_tool(
        "execution_run_create",
        {
            "auth_token": auth_token,
            "run_code": str(uuid.uuid4()),
            "scheme_code": scheme_code,
            "plan_code": str(ctx.get("run_plan_code") or ""),
            "scheme_type": str(ctx.get("scheme_type") or "recon"),
            "trigger_type": str(run_context.get("trigger_type") or "schedule"),
            "entry_mode": str(run_context.get("entry_mode") or "dataset"),
            "execution_status": execution_status,
            "failed_stage": failed_stage,
            "failed_reason": failed_reason,
            "run_context_json": run_context,
            "source_snapshot_json": source_snapshot_json,
            "subtasks_json": subtasks_json,
            "recon_result_summary_json": summary,
            "artifacts_json": artifacts,
            "anomaly_count": len(anomaly_items),
            "started_at_now": True,
            "finished_at_now": execution_status not in {"running", "queued"},
        },
    )
    if bool(result.get("success")):
        return _safe_dict(result.get("run"))
    return {}


async def load_run_plan_node(state: AgentState) -> dict[str, Any]:
    """Load run plan by execution_* tools, fallback to legacy auto task."""
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run_plan_code = str(
        ctx.get("run_plan_code")
        or ctx.get("plan_code")
        or ctx.get("auto_task_id")
        or ""
    ).strip()
    if not run_plan_code:
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = "缺少 run_plan_code"
        return {"recon_ctx": ctx}

    ctx["run_plan_code"] = run_plan_code
    plan_result = await call_mcp_tool(
        "execution_run_plan_get",
        {"auth_token": auth_token, "plan_code": run_plan_code},
    )
    if bool(plan_result.get("success")):
        run_plan = _safe_dict(plan_result.get("run_plan"))
        ctx["run_plan"] = run_plan
        ctx["scheme_code"] = str(run_plan.get("scheme_code") or "").strip()
        return {"recon_ctx": ctx}

    # Compatibility fallback to legacy auto task model.
    legacy_task_result = await recon_auto_task_get(auth_token, run_plan_code)
    if not bool(legacy_task_result.get("success")):
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = str(plan_result.get("error") or legacy_task_result.get("error") or "运行计划不存在")
        return {"recon_ctx": ctx}

    legacy_task = _safe_dict(legacy_task_result.get("task"))
    task_meta = _safe_dict(legacy_task.get("task_meta_json"))
    input_bindings = [v for v in _safe_list(legacy_task.get("input_bindings")) if isinstance(v, dict)]
    if not input_bindings:
        input_bindings = [v for v in _safe_list(task_meta.get("input_bindings")) if isinstance(v, dict)]
    run_plan = {
        "plan_code": run_plan_code,
        "plan_name": str(legacy_task.get("task_name") or run_plan_code),
        "scheme_code": "",
        "schedule_type": str(legacy_task.get("schedule_type") or "daily"),
        "schedule_expr": str(legacy_task.get("schedule_expr") or ""),
        "biz_date_offset": str(legacy_task.get("biz_date_offset") or "t-1"),
        "is_enabled": bool(legacy_task.get("is_enabled", True)),
        "input_bindings_json": input_bindings,
        "channel_config_id": str(legacy_task.get("channel_config_id") or ""),
        "owner_mapping_json": _safe_dict(legacy_task.get("owner_mapping_json")),
        "legacy_auto_task_id": str(legacy_task.get("id") or run_plan_code),
        "legacy_rule_code": str(legacy_task.get("rule_code") or ""),
    }
    ctx["run_plan"] = run_plan
    return {"recon_ctx": ctx}


def validate_run_plan_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    run_plan = _safe_dict(ctx.get("run_plan"))
    if not run_plan:
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = "运行计划不存在"
        return {"recon_ctx": ctx}
    if run_plan.get("is_enabled") is False:
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = "运行计划已停用"
        return {"recon_ctx": ctx}
    return {"recon_ctx": ctx}


async def load_scheme_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run_plan = _safe_dict(ctx.get("run_plan"))
    scheme_code = str(run_plan.get("scheme_code") or ctx.get("scheme_code") or "").strip()
    scheme: dict[str, Any] = {}
    if scheme_code:
        scheme_result = await call_mcp_tool(
            "execution_scheme_get",
            {"auth_token": auth_token, "scheme_code": scheme_code},
        )
        if bool(scheme_result.get("success")):
            scheme = _safe_dict(scheme_result.get("scheme"))
        else:
            ctx["failed_stage"] = "config"
            ctx["failed_reason"] = str(scheme_result.get("error") or "方案不存在")
            return {"recon_ctx": ctx}

    recon_rule_code = str(
        scheme.get("recon_rule_code")
        or run_plan.get("legacy_rule_code")
        or ctx.get("rule_code")
        or ""
    ).strip()
    if not recon_rule_code:
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = "运行计划未绑定 recon 规则"
        return {"recon_ctx": ctx}

    rule_resp = await get_file_validation_rule(recon_rule_code, auth_token)
    if not bool(rule_resp.get("success")):
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = str(rule_resp.get("error") or f"未找到规则 {recon_rule_code}")
        return {"recon_ctx": ctx}

    rule_record = _safe_dict(rule_resp.get("data"))
    rule_payload = _safe_dict(rule_record.get("rule"))
    ctx.update(
        {
            "scheme": scheme,
            "scheme_code": scheme_code or str(ctx.get("scheme_code") or ""),
            "rule_code": recon_rule_code,
            "rule_name": str(rule_payload.get("rule_name") or rule_record.get("name") or recon_rule_code),
            "rule": rule_payload,
            "file_rule_code": str(
                scheme.get("file_rule_code")
                or rule_payload.get("file_rule_code")
                or ""
            ).strip(),
            "proc_rule_code": str(scheme.get("proc_rule_code") or "").strip(),
            "scheme_type": str(scheme.get("scheme_type") or "recon"),
        }
    )
    return {"recon_ctx": ctx}


def validate_scheme_rules_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    if not str(ctx.get("rule_code") or "").strip():
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = "方案未配置 recon 规则"
    return {"recon_ctx": ctx}


def resolve_plan_inputs_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    run_plan = _safe_dict(ctx.get("run_plan"))
    bindings = [v for v in _safe_list(run_plan.get("input_bindings_json")) if isinstance(v, dict)]
    ctx["plan_input_bindings"] = bindings
    return {"recon_ctx": ctx}


def resolve_biz_date_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    run_plan = _safe_dict(ctx.get("run_plan"))
    run_context = _safe_dict(ctx.get("run_context"))
    explicit = str(ctx.get("biz_date") or "").strip()
    biz_date = _compute_biz_date(run_plan, run_context, explicit)
    ctx["biz_date"] = biz_date
    return {"recon_ctx": ctx}


async def check_dataset_ready_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    bindings = [v for v in _safe_list(ctx.get("plan_input_bindings")) if isinstance(v, dict)]
    ready_snapshots: list[dict[str, Any]] = []
    missing_bindings: list[dict[str, Any]] = []

    for binding in bindings:
        source_id = _get_binding_source_id(binding)
        table_name = str(binding.get("table_name") or "").strip()
        if not source_id or not table_name:
            missing_bindings.append({**binding, "error": "缺少 data_source_id/source_id 或 table_name"})
            continue
        result = await data_source_get_published_snapshot(
            auth_token,
            source_id,
            resource_key=_get_binding_resource_key(binding),
        )
        snapshot = _safe_dict(result.get("published_snapshot"))
        if bool(result.get("success")) and snapshot:
            ready_snapshots.append({"binding": binding, "published_snapshot": snapshot})
        else:
            missing_bindings.append({**binding, "error": str(result.get("error") or "暂无可用快照")})

    ctx["ready_snapshots"] = ready_snapshots
    ctx["missing_bindings"] = missing_bindings
    return {"recon_ctx": ctx}


def trigger_collection_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    missing_bindings = [v for v in _safe_list(ctx.get("missing_bindings")) if isinstance(v, dict)]
    ctx["collection_targets"] = missing_bindings
    return {"recon_ctx": ctx}


async def retry_collection_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    targets = [v for v in _safe_list(ctx.get("collection_targets")) if isinstance(v, dict)]
    ready_snapshots = [v for v in _safe_list(ctx.get("ready_snapshots")) if isinstance(v, dict)]
    subtasks = [v for v in _safe_list(ctx.get("subtasks_json")) if isinstance(v, dict)]
    unresolved: list[dict[str, Any]] = []

    for binding in targets:
        source_id = _get_binding_source_id(binding)
        table_name = str(binding.get("table_name") or "").strip()
        if not source_id or not table_name:
            unresolved.append(binding)
            continue

        succeeded = False
        for attempt in range(1, COLLECT_MAX_RETRIES + 1):
            result = await data_source_get_published_snapshot(
                auth_token,
                source_id,
                resource_key=_get_binding_resource_key(binding),
            )
            snapshot = _safe_dict(result.get("published_snapshot"))
            ok = bool(result.get("success")) and bool(snapshot)
            subtasks.append(
                {
                    "type": "collect",
                    "dataset_code": str(binding.get("dataset_code") or table_name),
                    "source_id": source_id,
                    "table_name": table_name,
                    "attempt": attempt,
                    "status": "success" if ok else "failed",
                    "error": "" if ok else str(result.get("error") or "暂无可用快照"),
                }
            )
            if ok:
                ready_snapshots.append({"binding": binding, "published_snapshot": snapshot})
                succeeded = True
                break
            if attempt < COLLECT_MAX_RETRIES:
                await asyncio.sleep(COLLECT_RETRY_INTERVAL_SECONDS)

        if not succeeded:
            unresolved.append(binding)

    ctx["ready_snapshots"] = ready_snapshots
    ctx["missing_bindings"] = unresolved
    ctx["subtasks_json"] = subtasks
    ctx["collect_failed"] = len(unresolved) > 0
    return {"recon_ctx": ctx}


def bind_ready_snapshot_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    ready_snapshots = [v for v in _safe_list(ctx.get("ready_snapshots")) if isinstance(v, dict)]
    biz_date = str(ctx.get("biz_date") or "")
    recon_inputs = _build_recon_inputs_from_ready_snapshots(ready_snapshots, biz_date=biz_date)
    ctx["recon_inputs"] = recon_inputs
    ctx["source_snapshot_json"] = {
        "ready_count": len(ready_snapshots),
        "missing_count": len(_safe_list(ctx.get("missing_bindings"))),
        "snapshots": ready_snapshots,
        "biz_date": biz_date,
    }
    return {"recon_ctx": ctx}


def return_collection_failed_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    ctx["failed_stage"] = "collect"
    ctx["failed_reason"] = "数据采集失败"
    ctx["exec_status"] = "failed"
    return {"recon_ctx": ctx}


def validate_dataset_completeness_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    recon_inputs = [v for v in _safe_list(ctx.get("recon_inputs")) if isinstance(v, dict)]
    missing_bindings = [v for v in _safe_list(ctx.get("missing_bindings")) if isinstance(v, dict)]

    required_missing = [b for b in missing_bindings if _get_binding_required(b)]
    if required_missing:
        ctx["failed_stage"] = "validate_dataset"
        ctx["failed_reason"] = "关键数据集未就绪"
    elif not recon_inputs:
        ctx["failed_stage"] = "validate_dataset"
        ctx["failed_reason"] = "未构建出有效的 dataset 输入"
    return {"recon_ctx": ctx}


def build_auto_run_context_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    run_context = _safe_dict(ctx.get("run_context"))
    run_context.update(
        {
            "trigger_type": str(run_context.get("trigger_type") or "schedule"),
            "entry_mode": "dataset",
            "biz_date": str(ctx.get("biz_date") or ""),
            "run_plan_code": str(ctx.get("run_plan_code") or ""),
            "scheme_code": str(ctx.get("scheme_code") or ""),
        }
    )
    if not str(run_context.get("run_id") or "").strip():
        run_context["run_id"] = str(uuid.uuid4())
    ctx["run_context"] = run_context
    ctx["run_id"] = str(run_context.get("run_id") or "")
    return {"recon_ctx": ctx}


async def persist_failed_run_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run = await _persist_execution_run(
        auth_token=auth_token,
        ctx=ctx,
        execution_status="failed",
        failed_stage=str(ctx.get("failed_stage") or ""),
        failed_reason=str(ctx.get("failed_reason") or ""),
    )
    if run:
        ctx["execution_run_record"] = run
    return {"recon_ctx": ctx}


async def persist_auto_run_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    status = str(ctx.get("exec_status") or "success")
    normalized_status = "succeeded" if status in {"success", "partial_success", "skipped"} else "failed"
    run = await _persist_execution_run(
        auth_token=auth_token,
        ctx=ctx,
        execution_status=normalized_status,
        failed_stage=str(ctx.get("failed_stage") or ""),
        failed_reason=str(ctx.get("failed_reason") or ""),
    )
    if run:
        ctx["execution_run_record"] = run
    return {"recon_ctx": ctx}


async def create_exception_tasks_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run = _safe_dict(ctx.get("execution_run_record"))
    run_id = str(run.get("id") or "").strip()
    scheme_code = str(ctx.get("scheme_code") or "").strip()
    anomalies = [v for v in _safe_list(ctx.get("anomaly_items")) if isinstance(v, dict)]
    if not run_id or not scheme_code or not anomalies:
        return {"recon_ctx": ctx}

    created = 0
    for idx, item in enumerate(anomalies, start=1):
        anomaly_key = str(item.get("item_id") or item.get("anomaly_key") or f"{run_id}:{idx}")
        payload = {
            "auth_token": auth_token,
            "run_id": run_id,
            "scheme_code": scheme_code,
            "anomaly_key": anomaly_key,
            "anomaly_type": str(item.get("anomaly_type") or "unknown"),
            "summary": str(item.get("summary") or "异常"),
            "detail_json": item,
            "owner_name": "",
            "owner_identifier": "",
            "owner_contact_json": {},
        }
        result = await call_mcp_tool("execution_run_exception_create", payload)
        if bool(result.get("success")):
            created += 1

    ctx["exception_created_count"] = created
    return {"recon_ctx": ctx}


def maybe_auto_notify_node(state: AgentState) -> dict[str, Any]:
    """Auto notify placeholder. Real channel dispatch stays outside this graph for now."""
    ctx = _get_recon_ctx(state)
    ctx["auto_notify_status"] = "skipped"
    return {"recon_ctx": ctx}

