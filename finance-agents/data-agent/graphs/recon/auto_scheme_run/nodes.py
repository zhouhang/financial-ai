"""Nodes for auto scheme run graph."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from models import AgentState
from services.notifications import get_notification_adapter
from services.notifications.repository import load_company_channel_config_by_id
from tools.mcp_client import (
    call_mcp_tool,
    data_source_get_published_snapshot,
    data_source_trigger_sync,
    execution_run_exception_update,
    get_file_validation_rule,
    recon_auto_task_get,
)

logger = logging.getLogger(__name__)

COLLECT_MAX_RETRIES = 3
COLLECT_RETRY_INTERVAL_SECONDS = 1.0

_FAILED_STAGE_LABELS: dict[str, str] = {
    "config": "配置错误，请检查对账方案配置",
    "prepare": "数据整理阶段失败",
    "build_inputs": "输入数据构建失败",
    "collect": "数据采集失败",
    "validate_dataset": "数据就绪校验失败",
    "execution_result_failed": "对账执行失败，结果未通过校验",
    "recon": "对账执行失败",
}


_ANOMALY_TYPE_LABELS: dict[str, str] = {
    "source_only": "仅源数据存在（目标数据缺失）",
    "target_only": "仅目标数据存在（源数据缺失）",
    "matched_with_diff": "金额或字段存在差异",
    "value_mismatch": "金额或字段存在差异",
    "unknown": "未知异常",
}


def _label_anomaly_type(anomaly_type: str, *, left_name: str = "", right_name: str = "") -> str:
    """Return a finance-friendly label for an anomaly type.

    When left_name / right_name are provided, they replace the generic 源/目标 placeholders.
    """
    atype = str(anomaly_type or "").strip()
    src = str(left_name or "").strip()
    tgt = str(right_name or "").strip()
    if src and tgt:
        dynamic: dict[str, str] = {
            "source_only": f"仅 {src} 存在（{tgt} 缺失）",
            "target_only": f"仅 {tgt} 存在（{src} 缺失）",
            "matched_with_diff": f"{src} 与 {tgt} 存在差异",
            "value_mismatch": f"{src} 与 {tgt} 存在差异",
            "unknown": "未知异常",
        }
        return dynamic.get(atype, str(anomaly_type or "未知异常"))
    return _ANOMALY_TYPE_LABELS.get(atype, str(anomaly_type or "未知异常"))


def _build_anomaly_summary(
    anomaly_type: str,
    item: dict[str, Any],
    *,
    left_name: str = "",
    right_name: str = "",
) -> str:
    """Build a finance-friendly one-line summary for an anomaly item.

    Uses actual dataset business names when available instead of generic 左侧/右侧.
    """
    src = str(left_name or "左侧数据").strip()
    tgt = str(right_name or "右侧数据").strip()

    _type_labels: dict[str, str] = {
        "source_only": f"仅 {src} 存在（{tgt} 缺失）",
        "target_only": f"仅 {tgt} 存在（{src} 缺失）",
        "matched_with_diff": f"{src} 与 {tgt} 存在差异",
        "value_mismatch": f"{src} 与 {tgt} 存在差异",
        "unknown": "未知异常",
    }
    label = _type_labels.get(str(anomaly_type or "").strip()) or _label_anomaly_type(anomaly_type)

    # 附加具体匹配键值，便于财务人员定位记录
    join_key = item.get("join_key") or []
    if isinstance(join_key, list) and join_key:
        key_pairs = []
        for k in join_key[:2]:
            if isinstance(k, dict):
                field = str(k.get("field") or k.get("source_field") or "")
                value = k.get("value") or k.get("source_value") or ""
                if field and value is not None and value != "":
                    key_pairs.append(f"{field}={value}")
        if key_pairs:
            return f"{label}（{' / '.join(key_pairs)}）"

    # 附加差异字段值
    compare_values = item.get("compare_values") or []
    if isinstance(compare_values, list) and compare_values:
        first = compare_values[0] if isinstance(compare_values[0], dict) else {}
        name = str(first.get("name") or first.get("field") or "")
        left_val = first.get("source_value") or first.get("left_value")
        right_val = first.get("target_value") or first.get("right_value")
        if name and left_val is not None and right_val is not None:
            return f"{label}（{name}：{src} {left_val} / {tgt} {right_val}）"

    return label


def _resolve_side_names(ctx: dict[str, Any]) -> tuple[str, str]:
    """Return (left_name, right_name) from ctx for use in anomaly summaries.

    Priority:
    1. scheme_meta_json.left_sources / right_sources (most explicit)
    2. ready_snapshots binding side + dataset_name
    3. plan_input_bindings side + dataset_name
    4. ("", "") — caller falls back to generic labels
    """
    def _first_name(sources: list[Any]) -> str:
        for src in sources:
            if not isinstance(src, dict):
                continue
            name = str(
                src.get("dataset_name") or src.get("business_name")
                or src.get("display_name") or src.get("dataset_code") or ""
            ).strip()
            if name:
                return name
        return ""

    # 1. scheme_meta_json
    scheme = _safe_dict(ctx.get("scheme"))
    scheme_meta = _safe_dict(
        scheme.get("scheme_meta_json") or scheme.get("scheme_meta") or scheme.get("meta")
    )
    left_sources = [s for s in _safe_list(scheme_meta.get("left_sources")) if isinstance(s, dict)]
    right_sources = [s for s in _safe_list(scheme_meta.get("right_sources")) if isinstance(s, dict)]
    if left_sources or right_sources:
        left = _first_name(left_sources)
        right = _first_name(right_sources)
        if left or right:
            return left, right

    # 2. ready_snapshots binding side + dataset_name
    side_map: dict[str, str] = {}
    for snap in _safe_list(ctx.get("ready_snapshots")):
        if not isinstance(snap, dict):
            continue
        binding = _safe_dict(snap.get("binding"))
        side = str(binding.get("side") or binding.get("role_code") or "").strip().lower()
        name = str(
            binding.get("dataset_name") or binding.get("display_name")
            or binding.get("dataset_code") or ""
        ).strip()
        if side in {"left", "right"} and name and side not in side_map:
            side_map[side] = name
    if "left" in side_map or "right" in side_map:
        return side_map.get("left", ""), side_map.get("right", "")

    # 3. plan_input_bindings
    for binding in _safe_list(ctx.get("plan_input_bindings")):
        if not isinstance(binding, dict):
            continue
        side = str(binding.get("side") or binding.get("role_code") or "").strip().lower()
        name = str(
            binding.get("dataset_name") or binding.get("display_name")
            or binding.get("dataset_code") or ""
        ).strip()
        if side in {"left", "right"} and name and side not in side_map:
            side_map[side] = name
    if "left" in side_map or "right" in side_map:
        return side_map.get("left", ""), side_map.get("right", "")

    return "", ""


def _resolve_failed_reason(ctx: dict[str, Any]) -> str:
    """Produce a finance-team-friendly failure reason from ctx.

    Priority: explicit failed_reason > exec_error > stage label fallback.
    """
    reason = str(ctx.get("failed_reason") or "").strip()
    if reason:
        return reason
    exec_error = str(ctx.get("exec_error") or "").strip()
    if exec_error:
        # Wrap raw technical error in a readable sentence
        return f"执行过程中遇到错误：{exec_error}"
    stage = str(ctx.get("failed_stage") or "").strip()
    return _FAILED_STAGE_LABELS.get(stage, "执行失败，请联系系统管理员")


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _merge_feedback(existing: Any, patch: Any) -> dict[str, Any]:
    return {**_safe_dict(existing), **_safe_dict(patch)}


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def _normalize_execution_trigger_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"chat", "schedule", "api"}:
        return normalized
    if normalized in {"cron", "scheduler", "scheduled"}:
        return "schedule"
    if normalized in {"manual", "manual_trigger", "retry"}:
        return "api"
    return "schedule"


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


def _build_plan_binding_from_source(source: dict[str, Any], date_field: str) -> dict[str, Any] | None:
    source_id = str(source.get("source_id") or source.get("data_source_id") or "").strip()
    table_name = str(
        source.get("resource_key")
        or source.get("dataset_code")
        or source.get("name")
        or ""
    ).strip()
    if not source_id or not table_name:
        return None
    query: dict[str, Any] = {"resource_key": table_name}
    if date_field:
        query["date_field"] = date_field
    return {
        "data_source_id": source_id,
        "table_name": table_name,
        "resource_key": table_name,
        "dataset_source_type": "snapshot",
        "query": query,
    }


def _infer_binding_side(role_code: str, mapping_config: dict[str, Any]) -> str:
    side = str(mapping_config.get("side") or "").strip().lower()
    if side in {"left", "right"}:
        return side
    normalized_role = str(role_code or "").strip().lower()
    if normalized_role.startswith("left"):
        return "left"
    if normalized_role.startswith("right"):
        return "right"
    return ""


def _resolve_time_semantics(run_plan: dict[str, Any]) -> tuple[str, str]:
    plan_meta = _safe_dict(
        run_plan.get("plan_meta_json")
        or run_plan.get("plan_meta")
        or run_plan.get("meta")
    )
    left = str(plan_meta.get("left_time_semantic") or "").strip()
    right = str(plan_meta.get("right_time_semantic") or "").strip()
    return left, right


def _normalize_plan_binding(item: dict[str, Any]) -> dict[str, Any] | None:
    source_id = _get_binding_source_id(item)
    table_name = str(item.get("table_name") or "").strip()
    if not source_id or not table_name:
        return None
    return {
        "data_source_id": source_id,
        "table_name": table_name,
        "resource_key": _get_binding_resource_key(item),
        "required": _get_binding_required(item),
        "query": _safe_dict(item.get("query")),
        "dataset_source_type": str(item.get("dataset_source_type") or "snapshot").strip() or "snapshot",
        "role_code": str(item.get("role_code") or "").strip(),
        "dataset_code": str(item.get("dataset_code") or "").strip(),
        "dataset_name": str(item.get("dataset_name") or item.get("display_name") or "").strip(),
        "display_name": str(item.get("display_name") or item.get("dataset_name") or "").strip(),
    }


def _build_plan_binding_from_dataset_binding(
    *,
    binding: dict[str, Any],
    left_time_semantic: str,
    right_time_semantic: str,
) -> dict[str, Any] | None:
    source_id = str(binding.get("data_source_id") or "").strip()
    resource_key = str(binding.get("resource_key") or "").strip()
    if not source_id or not resource_key:
        return None

    mapping_config = _safe_dict(binding.get("mapping_config"))
    filter_config = _safe_dict(binding.get("filter_config"))
    query = _safe_dict(filter_config.get("query") or filter_config)
    if not str(query.get("resource_key") or "").strip():
        query["resource_key"] = resource_key

    role_code = str(binding.get("role_code") or "").strip()
    side = _infer_binding_side(role_code, mapping_config)
    if not str(query.get("date_field") or "").strip():
        if side == "left" and left_time_semantic:
            query["date_field"] = left_time_semantic
        elif side == "right" and right_time_semantic:
            query["date_field"] = right_time_semantic

    table_name = str(
        mapping_config.get("table_name")
        or mapping_config.get("dataset_code")
        or resource_key
    ).strip()
    if not table_name:
        return None

    return {
        "data_source_id": source_id,
        "table_name": table_name,
        "resource_key": resource_key,
        "required": bool(binding.get("is_required", True)),
        "query": query,
        "dataset_source_type": str(mapping_config.get("dataset_source_type") or "snapshot").strip() or "snapshot",
        "role_code": role_code,
        "dataset_code": str(mapping_config.get("dataset_code") or resource_key).strip() or resource_key,
    }


async def _list_dataset_bindings_by_scope(
    *,
    auth_token: str,
    binding_scope: str,
    binding_code: str,
) -> list[dict[str, Any]]:
    if not auth_token or not binding_scope or not binding_code:
        return []
    result = await call_mcp_tool(
        "execution_dataset_binding_list",
        {
            "auth_token": auth_token,
            "binding_scope": binding_scope,
            "binding_code": binding_code,
            "status": "active",
        },
    )
    if bool(result.get("success")):
        return [v for v in _safe_list(result.get("bindings")) if isinstance(v, dict)]
    if _is_unknown_tool_error(result.get("error")):
        return []
    logger.warning(
        "[auto_scheme_run] execution_dataset_binding_list failed scope=%s code=%s err=%s",
        binding_scope,
        binding_code,
        str(result.get("error") or ""),
    )
    return []


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
            "trigger_type": _normalize_execution_trigger_type(run_context.get("trigger_type")),
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
    logger.warning(
        "[auto_scheme_run] execution_run_create failed: scheme_code=%s plan_code=%s trigger_type=%s error=%s",
        scheme_code,
        str(ctx.get("run_plan_code") or ""),
        _normalize_execution_trigger_type(run_context.get("trigger_type")),
        str(result.get("error") or ""),
    )
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

    scheme_meta = _safe_dict(
        scheme.get("scheme_meta_json")
        or scheme.get("scheme_meta")
        or scheme.get("meta")
    )
    embedded_rule = _safe_dict(scheme_meta.get("recon_rule_json"))
    if embedded_rule:
        embedded_rule_code = str(
            scheme.get("recon_rule_code")
            or run_plan.get("legacy_rule_code")
            or ctx.get("rule_code")
            or f"embedded:{scheme_code or 'scheme'}"
        ).strip()
        ctx.update(
            {
                "scheme": scheme,
                "scheme_code": scheme_code or str(ctx.get("scheme_code") or ""),
                "rule_code": embedded_rule_code,
                "rule_name": str(
                    embedded_rule.get("rule_name")
                    or scheme_meta.get("recon_rule_name")
                    or scheme.get("name")
                    or embedded_rule_code
                ),
                "rule": embedded_rule,
                "file_rule_code": str(
                    scheme.get("file_rule_code")
                    or embedded_rule.get("file_rule_code")
                    or ""
                ).strip(),
                "proc_rule_code": str(scheme.get("proc_rule_code") or "").strip(),
                "scheme_type": str(scheme.get("scheme_type") or "recon"),
            }
        )
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


async def resolve_plan_inputs_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run_plan = _safe_dict(ctx.get("run_plan"))
    run_plan_code = str(run_plan.get("plan_code") or ctx.get("run_plan_code") or "").strip()
    scheme_code = str(run_plan.get("scheme_code") or ctx.get("scheme_code") or "").strip()
    left_time_semantic, right_time_semantic = _resolve_time_semantics(run_plan)

    bindings: list[dict[str, Any]] = []
    binding_source = ""

    if run_plan_code:
        plan_scope_rows = await _list_dataset_bindings_by_scope(
            auth_token=auth_token,
            binding_scope="execution_run_plan",
            binding_code=run_plan_code,
        )
        for row in plan_scope_rows:
            normalized = _build_plan_binding_from_dataset_binding(
                binding=row,
                left_time_semantic=left_time_semantic,
                right_time_semantic=right_time_semantic,
            )
            if normalized is not None:
                bindings.append(normalized)
        if bindings:
            binding_source = "dataset_bindings:execution_run_plan"
        else:
            legacy_task_scope_rows = await _list_dataset_bindings_by_scope(
                auth_token=auth_token,
                binding_scope="recon_task",
                binding_code=run_plan_code,
            )
            for row in legacy_task_scope_rows:
                normalized = _build_plan_binding_from_dataset_binding(
                    binding=row,
                    left_time_semantic=left_time_semantic,
                    right_time_semantic=right_time_semantic,
                )
                if normalized is not None:
                    bindings.append(normalized)
            if bindings:
                binding_source = "dataset_bindings:recon_task"

    if not bindings and scheme_code:
        scheme_scope_rows = await _list_dataset_bindings_by_scope(
            auth_token=auth_token,
            binding_scope="execution_scheme",
            binding_code=scheme_code,
        )
        for row in scheme_scope_rows:
            normalized = _build_plan_binding_from_dataset_binding(
                binding=row,
                left_time_semantic=left_time_semantic,
                right_time_semantic=right_time_semantic,
            )
            if normalized is not None:
                bindings.append(normalized)
        if bindings:
            binding_source = "dataset_bindings:execution_scheme"
        else:
            legacy_scheme_scope_rows = await _list_dataset_bindings_by_scope(
                auth_token=auth_token,
                binding_scope="recon_scheme",
                binding_code=scheme_code,
            )
            for row in legacy_scheme_scope_rows:
                normalized = _build_plan_binding_from_dataset_binding(
                    binding=row,
                    left_time_semantic=left_time_semantic,
                    right_time_semantic=right_time_semantic,
                )
                if normalized is not None:
                    bindings.append(normalized)
            if bindings:
                binding_source = "dataset_bindings:recon_scheme"

    if not bindings:
        legacy_raw = [v for v in _safe_list(run_plan.get("input_bindings_json")) if isinstance(v, dict)]
        if not legacy_raw:
            legacy_raw = [
                v
                for v in _safe_list(
                    _safe_dict(
                        run_plan.get("plan_meta_json")
                        or run_plan.get("plan_meta")
                        or run_plan.get("meta")
                    ).get("input_bindings")
                )
                if isinstance(v, dict)
            ]
        for row in legacy_raw:
            normalized = _normalize_plan_binding(row)
            if normalized is not None:
                bindings.append(normalized)
        if bindings:
            binding_source = "run_plan_legacy_input_bindings"

    if not bindings:
        ctx["failed_stage"] = "config"
        ctx["failed_reason"] = "未配置可执行的数据集绑定（dataset_bindings）"
        ctx["plan_input_bindings"] = []
        ctx["plan_input_source"] = ""
        return {"recon_ctx": ctx}

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in bindings:
        dedupe_key = "::".join(
            [
                str(item.get("data_source_id") or ""),
                str(item.get("table_name") or ""),
                str(item.get("resource_key") or ""),
                str(item.get("role_code") or ""),
            ]
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)

    ctx["plan_input_bindings"] = deduped
    ctx["plan_input_source"] = binding_source
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
    biz_date = str(ctx.get("biz_date") or "")
    run_plan_code = str(ctx.get("run_plan_code") or "")

    for binding in targets:
        source_id = _get_binding_source_id(binding)
        table_name = str(binding.get("table_name") or "").strip()
        if not source_id or not table_name:
            unresolved.append(binding)
            continue

        raw_query = _safe_dict(binding.get("query"))
        resource_key = _get_binding_resource_key(binding)
        trigger_result = await data_source_trigger_sync(
            auth_token,
            source_id,
            idempotency_key="::".join(
                [
                    run_plan_code or "run_plan",
                    source_id,
                    resource_key,
                    biz_date or "biz_date_unknown",
                ]
            ),
            params={
                "biz_date": biz_date,
                "resource_key": resource_key,
                "query": raw_query,
            },
        )
        subtasks.append(
            {
                "type": "collect_trigger",
                "dataset_code": str(binding.get("dataset_code") or table_name),
                "source_id": source_id,
                "table_name": table_name,
                "status": "success" if bool(trigger_result.get("success")) else "failed",
                "error": "" if bool(trigger_result.get("success")) else str(trigger_result.get("error") or "触发采集失败"),
            }
        )
        if not bool(trigger_result.get("success")):
            unresolved.append(binding)
            continue

        succeeded = False
        for attempt in range(1, COLLECT_MAX_RETRIES + 1):
            result = await data_source_get_published_snapshot(
                auth_token,
                source_id,
                resource_key=resource_key,
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
    ctx["exec_status"] = "failed"
    missing_bindings = [v for v in _safe_list(ctx.get("missing_bindings")) if isinstance(v, dict)]
    if missing_bindings:
        names = [
            str(b.get("display_name") or b.get("dataset_name") or b.get("resource_key") or "未知数据集")
            for b in missing_bindings
        ]
        ctx["failed_reason"] = f"以下数据集采集失败，超过重试次数上限：{' / '.join(names)}"
    else:
        ctx["failed_reason"] = "数据采集失败，超过重试次数上限"
    return {"recon_ctx": ctx}


def validate_dataset_completeness_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    recon_inputs = [v for v in _safe_list(ctx.get("recon_inputs")) if isinstance(v, dict)]
    missing_bindings = [v for v in _safe_list(ctx.get("missing_bindings")) if isinstance(v, dict)]

    required_missing = [b for b in missing_bindings if _get_binding_required(b)]
    if required_missing:
        names = [
            str(b.get("display_name") or b.get("dataset_name") or b.get("resource_key") or "未知数据集")
            for b in required_missing
        ]
        ctx["failed_stage"] = "validate_dataset"
        ctx["failed_reason"] = f"以下关键数据集尚未就绪，无法执行对账：{' / '.join(names)}"
    elif not recon_inputs:
        ctx["failed_stage"] = "validate_dataset"
        ctx["failed_reason"] = "未能构建出有效的数据集输入，请检查数据源绑定配置"
    return {"recon_ctx": ctx}


def build_auto_run_context_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    run_context = _safe_dict(ctx.get("run_context"))
    run_context.update(
        {
            "trigger_type": _normalize_execution_trigger_type(run_context.get("trigger_type")),
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
        failed_reason=_resolve_failed_reason(ctx),
    )
    if run:
        ctx["execution_run_record"] = run
    return {"recon_ctx": ctx}


async def persist_auto_run_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    status = str(ctx.get("exec_status") or "success")
    normalized_status = "success" if status in {"success", "partial_success", "skipped"} else "failed"
    failed_stage = str(ctx.get("failed_stage") or "")
    if normalized_status == "success":
        # 成功态不应携带历史失败标记，否则 run API 会出现"已成功但返回失败"的语义漂移。
        failed_stage = ""
        failed_reason = ""
        ctx["failed_stage"] = ""
        ctx["failed_reason"] = ""
    else:
        failed_reason = _resolve_failed_reason(ctx)

    run = await _persist_execution_run(
        auth_token=auth_token,
        ctx=ctx,
        execution_status=normalized_status,
        failed_stage=failed_stage,
        failed_reason=failed_reason,
    )
    if run:
        ctx["execution_run_record"] = run
    if normalized_status == "success":
        usage_updates: list[dict[str, Any]] = []
        run_plan_code = str(ctx.get("run_plan_code") or "").strip()
        scheme_code = str(ctx.get("scheme_code") or "").strip()
        plan_input_source = str(ctx.get("plan_input_source") or "").strip()
        scopes_to_touch: list[tuple[str, str]] = []
        if plan_input_source.startswith("dataset_bindings:"):
            scope = plan_input_source.split(":", 1)[1]
            if scope in {"execution_run_plan", "recon_task"} and run_plan_code:
                scopes_to_touch.append((scope, run_plan_code))
            elif scope in {"execution_scheme", "recon_scheme"} and scheme_code:
                scopes_to_touch.append((scope, scheme_code))
        else:
            if run_plan_code:
                scopes_to_touch.append(("execution_run_plan", run_plan_code))
            if scheme_code:
                scopes_to_touch.append(("execution_scheme", scheme_code))

        for binding_scope, binding_code in scopes_to_touch:
            touch_result = await call_mcp_tool(
                "execution_dataset_binding_touch_usage",
                {
                    "auth_token": auth_token,
                    "binding_scope": binding_scope,
                    "binding_code": binding_code,
                },
            )
            usage_updates.append(
                {
                    "binding_scope": binding_scope,
                    "binding_code": binding_code,
                    "success": bool(touch_result.get("success")),
                    "updated_count": int(touch_result.get("updated_count") or 0),
                    "error": str(touch_result.get("error") or ""),
                }
            )
        ctx["binding_usage_updates"] = usage_updates
    return {"recon_ctx": ctx}


def _resolve_run_plan_default_owner(run_plan: dict[str, Any]) -> tuple[str, str, dict[str, Any], bool]:
    owner_mapping = _safe_dict(run_plan.get("owner_mapping_json"))
    default_owner = _safe_dict(owner_mapping.get("default_owner"))
    owner_name = str(default_owner.get("name") or default_owner.get("display_name") or "")
    owner_identifier = str(default_owner.get("identifier") or default_owner.get("owner_identifier") or "")
    raw_contact = (
        default_owner.get("contact")
        or default_owner.get("owner_contact_json")
        or default_owner.get("contact_json")
        or default_owner.get("contact_info")
    )
    owner_contact_json = _safe_dict(raw_contact)
    owner_available = bool(owner_name or owner_identifier or owner_contact_json)
    return owner_name, owner_identifier, owner_contact_json, owner_available


def _compose_execution_exception_reminder_text(
    *,
    run_plan: dict[str, Any],
    scheme: dict[str, Any],
    biz_date: str,
    exception: dict[str, Any],
) -> tuple[str, str]:
    plan_name = str(
        run_plan.get("plan_name")
        or run_plan.get("name")
        or scheme.get("scheme_name")
        or scheme.get("name")
        or "自动对账任务"
    ).strip()
    scheme_name = str(scheme.get("scheme_name") or scheme.get("name") or "").strip()
    title = f"{plan_name} 异常催办"
    lines = [
        f"任务：{plan_name}",
        f"业务日期：{biz_date}" if biz_date else "业务日期：未提供",
        f"对账方案：{scheme_name}" if scheme_name else "",
        f"异常类型：{_label_anomaly_type(exception.get('anomaly_type') or '未知')}",
        f"异常摘要：{str(exception.get('summary') or '详见对账结果')}",
        "请尽快处理，并在待办中标记完成后同步给财务复核。",
    ]
    content = "\n".join(line for line in lines if line)
    return title, content


def _resolve_exception_mobile(exception: dict[str, Any]) -> str:
    contact = _safe_dict(exception.get("owner_contact_json"))
    return str(contact.get("mobile") or contact.get("phone") or contact.get("telephone") or "").strip()


def _resolve_exception_user(adapter: Any, exception: dict[str, Any]) -> tuple[Any | None, str]:
    owner_identifier = str(exception.get("owner_identifier") or "").strip()
    owner_name = str(exception.get("owner_name") or "").strip()
    mobile = _resolve_exception_mobile(exception)
    last_message = ""

    if owner_identifier:
        resolved = adapter.resolve_user(user_id=owner_identifier)
        if resolved.success:
            user = resolved.resolved_user or (resolved.users[0] if resolved.users else None)
            if user is not None:
                return user, ""
        last_message = resolved.message

    if mobile:
        resolved = adapter.resolve_user(mobile=mobile)
        if resolved.success:
            user = resolved.resolved_user or (resolved.users[0] if resolved.users else None)
            if user is not None:
                return user, ""
        last_message = resolved.message

    if owner_name:
        resolved = adapter.resolve_user(keyword=owner_name)
        if resolved.success:
            user = resolved.resolved_user or (resolved.users[0] if resolved.users else None)
            if user is not None:
                return user, ""
        last_message = resolved.message

    return None, last_message or "责任人未能解析为可触达用户"


async def _mark_execution_exception_status(
    *,
    auth_token: str,
    exception: dict[str, Any],
    reminder_status: str,
    latest_feedback: str,
    feedback_patch: dict[str, Any] | None = None,
    owner_name: str | None = None,
    owner_identifier: str | None = None,
    owner_contact_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    exception_id = str(exception.get("id") or exception.get("exception_id") or "").strip()
    if not exception_id:
        return exception

    feedback_json = _merge_feedback(exception.get("feedback_json"), feedback_patch or {})
    update_result = await execution_run_exception_update(
        auth_token,
        exception_id,
        {
            "owner_name": owner_name,
            "owner_identifier": owner_identifier,
            "owner_contact_json": owner_contact_json,
            "reminder_status": reminder_status,
            "latest_feedback": latest_feedback,
            "feedback_json": feedback_json,
        },
    )
    if bool(update_result.get("success")):
        updated = _safe_dict(update_result.get("exception"))
        if updated:
            return updated
    return {
        **exception,
        **({"owner_name": owner_name} if owner_name is not None else {}),
        **({"owner_identifier": owner_identifier} if owner_identifier is not None else {}),
        **({"owner_contact_json": owner_contact_json} if owner_contact_json is not None else {}),
        "reminder_status": reminder_status,
        "latest_feedback": latest_feedback,
        "feedback_json": feedback_json,
    }


async def _send_execution_run_exception_reminder(
    *,
    auth_token: str,
    exception_ref: dict[str, Any],
    channel_config: Any,
    run_plan: dict[str, Any],
    scheme: dict[str, Any],
    biz_date: str,
) -> dict[str, Any]:
    exception = _safe_dict(exception_ref.get("exception"))
    exception_id = str(exception_ref.get("exception_id") or exception.get("id") or "").strip()
    if not exception_id:
        return {
            "status": "skipped",
            "reason": "missing_exception_id",
            "error": "异常记录缺少 exception_id，无法自动催办",
            "exception_id": "",
            "exception": exception,
        }

    if not any(
        [
            str(exception.get("owner_name") or "").strip(),
            str(exception.get("owner_identifier") or "").strip(),
            _resolve_exception_mobile(exception),
        ]
    ):
        updated = await _mark_execution_exception_status(
            auth_token=auth_token,
            exception=exception,
            reminder_status="owner_missing",
            latest_feedback="运行计划未配置可触达的责任人，已跳过自动催办",
            feedback_patch={"auto_notify_skipped_reason": "owner_missing"},
        )
        return {
            "status": "skipped",
            "reason": "owner_missing",
            "error": "缺少责任人信息",
            "exception_id": exception_id,
            "exception": updated,
        }

    adapter = get_notification_adapter(
        provider=str(getattr(channel_config, "provider", "") or ""),
        channel_config=channel_config,
    )
    resolved_user, resolve_error = _resolve_exception_user(adapter, exception)
    if resolved_user is None:
        updated = await _mark_execution_exception_status(
            auth_token=auth_token,
            exception=exception,
            reminder_status="owner_unresolved",
            latest_feedback=resolve_error,
            feedback_patch={"auto_notify_skipped_reason": "owner_unresolved"},
        )
        return {
            "status": "skipped",
            "reason": "owner_unresolved",
            "error": resolve_error,
            "exception_id": exception_id,
            "exception": updated,
        }

    title, content = _compose_execution_exception_reminder_text(
        run_plan=run_plan,
        scheme=scheme,
        biz_date=biz_date,
        exception=exception,
    )
    reminder = adapter.send_reminder(
        title=title,
        content=content,
        assignee_user_id=str(resolved_user.user_id or ""),
        source_id=exception_id,
    )
    if not reminder.success:
        updated = await _mark_execution_exception_status(
            auth_token=auth_token,
            exception=exception,
            owner_name=str(resolved_user.display_name or exception.get("owner_name") or ""),
            owner_identifier=str(resolved_user.user_id or ""),
            owner_contact_json={
                "provider": adapter.provider,
                "display_name": str(resolved_user.display_name or ""),
                "mobile": str(resolved_user.mobile or ""),
            },
            reminder_status="send_failed",
            latest_feedback=str(reminder.message or "自动催办发送失败"),
            feedback_patch={
                "provider": adapter.provider,
                "channel_config_id": str(getattr(channel_config, "id", "") or ""),
            },
        )
        return {
            "status": "failed",
            "reason": "send_failed",
            "error": str(reminder.message or "自动催办发送失败"),
            "exception_id": exception_id,
            "exception": updated,
        }

    feedback_patch = {
        "provider": adapter.provider,
        "channel_config_id": str(getattr(channel_config, "id", "") or ""),
        "message_id": reminder.bot_result.message_id if reminder.bot_result else "",
        "todo_id": reminder.todo_result.todo.todo_id if reminder.todo_result and reminder.todo_result.todo else "",
        "last_reminded_at": datetime.now().isoformat(),
    }
    updated = await _mark_execution_exception_status(
        auth_token=auth_token,
        exception=exception,
        owner_name=str(resolved_user.display_name or exception.get("owner_name") or ""),
        owner_identifier=str(resolved_user.user_id or ""),
        owner_contact_json={
            "provider": adapter.provider,
            "display_name": str(resolved_user.display_name or ""),
            "mobile": str(resolved_user.mobile or ""),
        },
        reminder_status="sent",
        latest_feedback="已自动发送催办消息并创建待办",
        feedback_patch=feedback_patch,
    )
    return {
        "status": "sent",
        "reason": "",
        "error": "",
        "exception_id": exception_id,
        "exception": updated,
        "reminder": {
            "provider": adapter.provider,
            "message_id": feedback_patch.get("message_id"),
            "todo_id": feedback_patch.get("todo_id"),
        },
    }


async def _mark_created_exceptions_skipped(
    *,
    auth_token: str,
    created_exceptions: list[dict[str, Any]],
    reminder_status: str,
    latest_feedback: str,
    feedback_patch: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    updated_refs: list[dict[str, Any]] = []
    for item in created_exceptions:
        item_dict = _safe_dict(item)
        exception = _safe_dict(item_dict.get("exception"))
        updated = await _mark_execution_exception_status(
            auth_token=auth_token,
            exception=exception,
            reminder_status=reminder_status,
            latest_feedback=latest_feedback,
            feedback_patch=feedback_patch,
        )
        updated_refs.append(
            {
                **item_dict,
                "exception_id": str(item_dict.get("exception_id") or updated.get("id") or ""),
                "exception": updated,
            }
        )
    return updated_refs


async def create_exception_tasks_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run = _safe_dict(ctx.get("execution_run_record"))
    run_id = str(run.get("id") or "").strip()
    scheme_code = str(ctx.get("scheme_code") or "").strip()
    anomalies = [v for v in _safe_list(ctx.get("anomaly_items")) if isinstance(v, dict)]
    if not run_id or not scheme_code or not anomalies:
        return {"recon_ctx": ctx}

    run_plan = _safe_dict(ctx.get("run_plan"))
    owner_name, owner_identifier, owner_contact_json, owner_available = _resolve_run_plan_default_owner(run_plan)
    ctx["exception_owner_available"] = owner_available
    ctx["exception_owner_info"] = {
        "name": owner_name,
        "identifier": owner_identifier,
        "contact_json": owner_contact_json,
    }

    # 提取左右数据集业务名称，用于生成财务友好的异常摘要
    left_name, right_name = _resolve_side_names(ctx)

    created = 0
    created_exceptions: list[dict[str, Any]] = []
    for idx, item in enumerate(anomalies, start=1):
        anomaly_key = str(item.get("item_id") or item.get("anomaly_key") or f"{run_id}:{idx}")
        atype = str(item.get("anomaly_type") or "unknown")
        payload = {
            "auth_token": auth_token,
            "run_id": run_id,
            "scheme_code": scheme_code,
            "anomaly_key": anomaly_key,
            "anomaly_type": atype,
            "summary": str(item.get("summary") or "") or _build_anomaly_summary(
                atype, item, left_name=left_name, right_name=right_name
            ),
            "detail_json": item,
            "owner_name": owner_name,
            "owner_identifier": owner_identifier,
            "owner_contact_json": owner_contact_json,
        }
        result = await call_mcp_tool("execution_run_exception_create", payload)
        if bool(result.get("success")):
            created += 1
            exception = _safe_dict(result.get("exception"))
            created_exceptions.append(
                {
                    "anomaly_key": anomaly_key,
                    "exception_id": str(exception.get("id") or exception.get("exception_id") or ""),
                    "exception": exception,
                }
            )

    ctx["exception_created_count"] = created
    ctx["created_exceptions"] = created_exceptions
    return {"recon_ctx": ctx}


async def maybe_auto_notify_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    created_exceptions = [item for item in _safe_list(ctx.get("created_exceptions")) if isinstance(item, dict)]
    if not created_exceptions:
        ctx["auto_notify_status"] = "skipped_no_exception"
        ctx["auto_notify_result"] = {
            "total": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "items": [],
        }
        return {"recon_ctx": ctx}

    run_plan = _safe_dict(ctx.get("run_plan"))
    channel_config_id = str(run_plan.get("channel_config_id") or "").strip()
    if not channel_config_id:
        updated_refs = await _mark_created_exceptions_skipped(
            auth_token=auth_token,
            created_exceptions=created_exceptions,
            reminder_status="channel_missing",
            latest_feedback="运行计划未配置协作通道，已跳过自动催办",
            feedback_patch={"auto_notify_skipped_reason": "channel_missing"},
        )
        ctx["created_exceptions"] = updated_refs
        ctx["auto_notify_status"] = "skipped_no_channel"
        ctx["auto_notify_result"] = {
            "total": len(created_exceptions),
            "sent": 0,
            "failed": 0,
            "skipped": len(created_exceptions),
            "channel_config_id": "",
            "items": [
                {
                    "exception_id": str(item.get("exception_id") or ""),
                    "status": "skipped",
                    "reason": "channel_missing",
                }
                for item in updated_refs
            ],
        }
        return {"recon_ctx": ctx}

    channel_config = load_company_channel_config_by_id(channel_id=channel_config_id)
    if channel_config is None:
        updated_refs = await _mark_created_exceptions_skipped(
            auth_token=auth_token,
            created_exceptions=created_exceptions,
            reminder_status="channel_missing",
            latest_feedback="运行计划协作通道不可用，已跳过自动催办",
            feedback_patch={"auto_notify_skipped_reason": "channel_config_not_found"},
        )
        ctx["created_exceptions"] = updated_refs
        ctx["auto_notify_status"] = "skipped_no_channel"
        ctx["auto_notify_result"] = {
            "total": len(created_exceptions),
            "sent": 0,
            "failed": 0,
            "skipped": len(created_exceptions),
            "channel_config_id": channel_config_id,
            "items": [
                {
                    "exception_id": str(item.get("exception_id") or ""),
                    "status": "skipped",
                    "reason": "channel_config_not_found",
                }
                for item in updated_refs
            ],
        }
        return {"recon_ctx": ctx}

    scheme = _safe_dict(ctx.get("scheme"))
    biz_date = str(
        ctx.get("biz_date")
        or _safe_dict(ctx.get("run_context")).get("biz_date")
        or _safe_dict(ctx.get("execution_run_record")).get("biz_date")
        or ""
    ).strip()

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    results: list[dict[str, Any]] = []
    updated_refs: list[dict[str, Any]] = []

    try:
        for item in created_exceptions:
            item_dict = _safe_dict(item)
            result = await _send_execution_run_exception_reminder(
                auth_token=auth_token,
                exception_ref=item_dict,
                channel_config=channel_config,
                run_plan=run_plan,
                scheme=scheme,
                biz_date=biz_date,
            )
            status = str(result.get("status") or "")
            if status == "sent":
                sent_count += 1
            elif status == "failed":
                failed_count += 1
            else:
                skipped_count += 1

            updated_refs.append(
                {
                    **item_dict,
                    "exception_id": str(result.get("exception_id") or item_dict.get("exception_id") or ""),
                    "exception": _safe_dict(result.get("exception")) or _safe_dict(item_dict.get("exception")),
                }
            )
            results.append(
                {
                    "exception_id": str(result.get("exception_id") or ""),
                    "status": status,
                    "reason": str(result.get("reason") or ""),
                    "error": str(result.get("error") or ""),
                }
            )
    except Exception as exc:
        logger.error("[recon][auto_notify] 自动催办失败: %s", exc)
        ctx["auto_notify_status"] = "failed"
        ctx["auto_notify_result"] = {
            "total": len(created_exceptions),
            "sent": sent_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "channel_config_id": channel_config_id,
            "provider": str(getattr(channel_config, "provider", "") or ""),
            "error": str(exc),
            "items": results,
        }
        return {"recon_ctx": ctx}

    total = len(created_exceptions)
    if sent_count == total:
        auto_notify_status = "sent"
    elif sent_count > 0:
        auto_notify_status = "partial_success"
    elif failed_count > 0:
        auto_notify_status = "failed"
    else:
        auto_notify_status = "skipped"

    ctx["created_exceptions"] = updated_refs
    ctx["auto_notify_status"] = auto_notify_status
    ctx["auto_notify_result"] = {
        "total": total,
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "channel_config_id": channel_config_id,
        "provider": str(getattr(channel_config, "provider", "") or ""),
        "channel_name": str(getattr(channel_config, "name", "") or ""),
        "items": results,
    }
    return {"recon_ctx": ctx}
