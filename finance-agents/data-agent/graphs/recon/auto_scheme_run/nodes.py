"""Nodes for auto scheme run graph."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import psycopg2
import psycopg2.extras

from config import DATABASE_URL
from graphs.recon.binding_date_fields import normalize_binding_query_date_field
from models import AgentState
from services.notifications import get_notification_adapter
from services.notifications.repository import load_company_channel_config_by_id
from tools.mcp_client import (
    call_mcp_tool,
    data_source_get,
    data_source_get_dataset,
    data_source_get_sync_job,
    data_source_list_collection_records,
    data_source_trigger_dataset_collection,
    execution_run_exception_get,
    execution_run_exception_update,
    get_file_validation_rule,
    recon_auto_task_get,
)

logger = logging.getLogger(__name__)

_FAILED_STAGE_LABELS: dict[str, str] = {
    "config": "配置错误，请检查对账方案配置",
    "prepare": "数据整理阶段失败",
    "build_inputs": "输入数据构建失败",
    "validate_dataset": "数据就绪校验失败",
    "execution_result_failed": "对账执行失败，结果未通过校验",
    "recon": "对账执行失败",
}


_ANOMALY_TYPE_LABELS: dict[str, str] = {
    "source_only": "仅左侧基础表存在（右侧基础表缺失）",
    "target_only": "仅右侧基础表存在（左侧基础表缺失）",
    "matched_with_diff": "金额或字段存在差异",
    "value_mismatch": "金额或字段存在差异",
    "unknown": "未知异常",
}

_DEFAULT_NOTIFY_EXPLOSION_LIMIT = 50


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


def _replace_generic_side_labels(text: str, *, left_name: str = "", right_name: str = "") -> str:
    value = str(text or "")
    left = str(left_name or "").strip()
    right = str(right_name or "").strip()
    if left:
        for token in ("源数据", "源文件", "左侧数据", "左侧基础表"):
            value = value.replace(token, left)
    if right:
        for token in ("目标数据", "目标文件", "右侧数据", "右侧基础表"):
            value = value.replace(token, right)
    return value


def _build_anomaly_summary(
    anomaly_type: str,
    item: dict[str, Any],
    *,
    left_name: str = "",
    right_name: str = "",
    field_labels: dict[str, str] | None = None,
) -> str:
    """Build a finance-friendly one-line summary for an anomaly item."""
    src = str(left_name or "左侧基础表").strip()
    tgt = str(right_name or "右侧基础表").strip()
    atype = str(anomaly_type or "").strip()
    fl = field_labels or {}

    _type_labels: dict[str, str] = {
        "source_only": f"仅 {src} 存在（{tgt} 缺失）",
        "target_only": f"仅 {tgt} 存在（{src} 缺失）",
        "matched_with_diff": f"{src} 与 {tgt} 金额差异",
        "value_mismatch": f"{src} 与 {tgt} 金额差异",
        "unknown": "未知异常",
    }
    label = _type_labels.get(atype) or _label_anomaly_type(anomaly_type)

    # ── 主键定位信息（所有类型都附加，便于财务定位记录）─────────────────────────
    join_key = [k for k in _safe_list(item.get("join_key")) if isinstance(k, dict)]
    key_parts: list[str] = []
    for k in join_key[:2]:
        raw_field = str(k.get("field") or k.get("source_field") or k.get("target_field") or "")
        display_field = fl.get(raw_field) or raw_field
        if atype == "target_only":
            value = k.get("target_value") or k.get("value") or ""
        else:
            value = k.get("source_value") or k.get("value") or ""
        if display_field and value is not None and str(value).strip():
            key_parts.append(f"{display_field}={value}")

    # ── 对比字段：差异记录显示两侧值；单侧存在记录显示现有侧的字段值 ────────────────
    compare_values = [c for c in _safe_list(item.get("compare_values")) if isinstance(c, dict)]
    diff_parts: list[str] = []
    if compare_values:
        for cv in compare_values[:3]:
            raw_field = str(cv.get("source_field") or "").strip()
            name = str(cv.get("name") or fl.get(raw_field) or raw_field).strip()
            left_val = cv.get("source_value")
            right_val = cv.get("target_value")
            diff_val = cv.get("diff_value")
            if not name:
                continue
            if atype == "source_only":
                if left_val is not None and str(left_val).strip() not in {"", "None", "null"}:
                    diff_parts.append(f"{name}：{src} {left_val}")
                continue
            if atype == "target_only":
                if right_val is not None and str(right_val).strip() not in {"", "None", "null"}:
                    diff_parts.append(f"{name}：{tgt} {right_val}")
                continue
            if atype in {"matched_with_diff", "value_mismatch"}:
                if left_val is None or right_val is None:
                    continue
                diff_str = f"差额 {diff_val}" if diff_val is not None and str(diff_val).strip() not in {"", "0", "0.0"} else ""
                part = f"{name}：{src} {left_val} / {tgt} {right_val}"
                if diff_str:
                    part += f"（{diff_str}）"
                diff_parts.append(part)

    parts: list[str] = []
    if key_parts:
        parts.append("、".join(key_parts))
    if diff_parts:
        parts.append("；".join(diff_parts))

    if parts:
        return f"{label}：{'  '.join(parts)}"
    return label


def _source_display_name(src: dict[str, Any]) -> str:
    """Extract the most human-friendly name from a source/binding dict.

    Checks in priority order: dataset_name → business_name → display_name → name → dataset_code.
    Skips raw table identifiers so finance-facing messages do not expose physical table names.
    """
    for key in ("dataset_name", "business_name", "display_name", "name"):
        val = str(src.get(key) or "").strip()
        if val:
            return val
    for key in ("dataset_code", "resource_key", "table_name", "table"):
        val = str(src.get(key) or "").strip()
        if val and not _looks_like_physical_table_name(val):
            return val
    return ""


def _looks_like_physical_table_name(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if "." in text:
        return True
    return text.startswith(("ods_", "dwd_", "dws_", "dim_", "fact_"))


def _source_identity_values(src: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    query = _safe_dict(src.get("query"))
    for key in ("dataset_id", "id", "table_name", "resource_key", "dataset_code", "table"):
        value = str(src.get(key) or "").strip()
        if value:
            values.add(value)
    for key in ("dataset_id", "resource_key"):
        value = str(query.get(key) or "").strip()
        if value:
            values.add(value)
    return values


def _base_source_names_from_input_plan(scheme_meta: dict[str, Any]) -> tuple[str, str]:
    entries = _flatten_input_plan_entries(scheme_meta)
    if not entries:
        return "", ""
    sources_by_side = {
        "left": [s for s in _safe_list(scheme_meta.get("left_sources")) if isinstance(s, dict)],
        "right": [s for s in _safe_list(scheme_meta.get("right_sources")) if isinstance(s, dict)],
    }
    result: dict[str, str] = {}
    for side in ("left", "right"):
        base_entries = [
            entry for entry in entries
            if str(entry.get("side") or "").strip().lower() == side
            and str(entry.get("read_mode") or "base").strip().lower() == "base"
        ]
        if not base_entries:
            base_entries = [
                entry for entry in entries
                if str(entry.get("target_table") or "").strip() == f"{side}_recon_ready"
                and str(entry.get("read_mode") or "base").strip().lower() == "base"
            ]
        for entry in base_entries:
            entry_ids = _source_identity_values(entry)
            matched_source = next(
                (
                    source for source in sources_by_side[side]
                    if entry_ids and entry_ids & _source_identity_values(source)
                ),
                {},
            )
            name = _source_display_name(matched_source) if matched_source else _source_display_name(entry)
            if name:
                result[side] = name
                break
    return result.get("left", ""), result.get("right", "")


def _build_field_label_map(scheme_meta: dict[str, Any]) -> dict[str, str]:
    """Build a {internal_field_name: display_label} map from scheme meta.

    Sources (in merge order, later overrides earlier):
    1. Static fallback for known internal field names
    2. compare_columns[].name mapped to source_column and target_column
    3. field_label_map in left_sources / right_sources (if present)
    """
    # 1. Static fallbacks for commonly-used internal field names
    labels: dict[str, str] = {
        "biz_key": "业务单号",
        "biz_date": "业务日期",
        "amount": "金额",
        "fee": "手续费",
        "refund_amount": "退款金额",
        "order_no": "订单号",
        "trade_no": "交易号",
        "trans_no": "交易流水号",
        "merchant_order_no": "商户订单号",
        "source_name": "来源名称",
    }
    # 2. compare_columns from recon rules
    for rule in _safe_list((scheme_meta.get("recon_rule_json") or {}).get("rules")):
        if not isinstance(rule, dict):
            continue
        compare = _safe_dict((rule.get("recon") or {}).get("compare_columns"))
        for col in _safe_list(compare.get("columns")):
            if not isinstance(col, dict):
                continue
            col_name = str(col.get("name") or "").strip()
            if not col_name:
                continue
            for fk in ("source_column", "target_column"):
                field = str(col.get(fk) or "").strip()
                if field:
                    labels[field] = col_name
    # 3. Explicit field_label_map on each source
    for src in _safe_list(scheme_meta.get("left_sources")) + _safe_list(scheme_meta.get("right_sources")):
        if not isinstance(src, dict):
            continue
        flm = src.get("field_label_map")
        if isinstance(flm, dict):
            for k, v in flm.items():
                if k and v:
                    labels[str(k)] = str(v)
    return labels


def _resolve_side_names(ctx: dict[str, Any]) -> tuple[str, str]:
    """Return (left_name, right_name) from ctx for use in anomaly summaries.

    Priority:
    1. ready_collections binding dataset_name (runtime hydrated, most reliable)
    2. plan_input_bindings dataset_name
    3. scheme_meta_json input_plan base source / left_sources / right_sources
    4. ("", "") — caller falls back to generic labels
    """
    def _normalize_side(value: Any, target_table: Any = "") -> str:
        text = str(value or "").strip().lower()
        target = str(target_table or "").strip().lower()
        if text == "left" or text.startswith("left_") or target == "left_recon_ready":
            return "left"
        if text == "right" or text.startswith("right_") or target == "right_recon_ready":
            return "right"
        return ""

    def _first_name(sources: list[Any]) -> str:
        for src in sources:
            if not isinstance(src, dict):
                continue
            name = _source_display_name(src)
            if name:
                return name
        return ""

    def _collection_items() -> list[dict[str, Any]]:
        items = [v for v in _safe_list(ctx.get("ready_collections")) if isinstance(v, dict)]
        if items:
            return items
        source_collection_json = _safe_dict(ctx.get("source_collection_json"))
        return [v for v in _safe_list(source_collection_json.get("collections")) if isinstance(v, dict)]

    # 1. ready_collections / source_collection_json binding side + dataset_name
    side_map: dict[str, str] = {}
    for collection in _collection_items():
        binding = _safe_dict(collection.get("binding"))
        side = _normalize_side(
            binding.get("side") or binding.get("role_code"),
            binding.get("input_plan_target_table") or binding.get("target_table"),
        )
        name = _source_display_name(binding)
        if side in {"left", "right"} and name and side not in side_map:
            side_map[side] = name
    if "left" in side_map or "right" in side_map:
        return side_map.get("left", ""), side_map.get("right", "")

    # 2. plan_input_bindings
    for binding in _safe_list(ctx.get("plan_input_bindings")):
        if not isinstance(binding, dict):
            continue
        side = _normalize_side(
            binding.get("side") or binding.get("role_code"),
            binding.get("input_plan_target_table") or binding.get("target_table"),
        )
        name = _source_display_name(binding)
        if side in {"left", "right"} and name and side not in side_map:
            side_map[side] = name
    if "left" in side_map or "right" in side_map:
        return side_map.get("left", ""), side_map.get("right", "")

    # 3. scheme_meta_json
    scheme = _safe_dict(ctx.get("scheme"))
    scheme_meta = _safe_dict(
        scheme.get("scheme_meta_json") or scheme.get("scheme_meta") or scheme.get("meta")
    )
    base_left, base_right = _base_source_names_from_input_plan(scheme_meta)
    if base_left or base_right:
        return base_left, base_right

    left_sources = [s for s in _safe_list(scheme_meta.get("left_sources")) if isinstance(s, dict)]
    right_sources = [s for s in _safe_list(scheme_meta.get("right_sources")) if isinstance(s, dict)]
    if left_sources or right_sources:
        left = _first_name(left_sources)
        right = _first_name(right_sources)
        if left or right:
            return left, right

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


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def _normalize_execution_trigger_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"chat", "schedule", "api", "manual", "rerun"}:
        return normalized
    if normalized in {"cron", "scheduler", "scheduled"}:
        return "schedule"
    if normalized == "manual_trigger":
        return "manual"
    if normalized == "retry":
        return "rerun"
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


def _normalize_collection_trigger_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"schedule", "scheduled", "cron", "scheduler"}:
        return "scheduled"
    if normalized in {"rerun", "retry"}:
        return "retry"
    return "manual"


def _should_collect_before_recon(value: Any) -> bool:
    return _normalize_collection_trigger_mode(value) in {"scheduled", "manual", "retry"}


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
        "dataset_source_type": "collection_records",
        "query": query,
    }


def _resolve_time_semantics(run_plan: dict[str, Any]) -> tuple[str, str]:
    plan_meta = _safe_dict(
        run_plan.get("plan_meta_json")
        or run_plan.get("plan_meta")
        or run_plan.get("meta")
    )
    left = str(plan_meta.get("left_time_semantic") or "").strip()
    right = str(plan_meta.get("right_time_semantic") or "").strip()
    return left, right


def _get_scheme_meta(ctx: dict[str, Any]) -> dict[str, Any]:
    scheme = _safe_dict(ctx.get("scheme"))
    return _safe_dict(
        scheme.get("scheme_meta_json")
        or scheme.get("scheme_meta")
        or scheme.get("meta")
    )


def _normalize_semantic_role(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_plan_binding(
    item: dict[str, Any],
    *,
    left_time_semantic: str = "",
    right_time_semantic: str = "",
    scheme_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    source_id = _get_binding_source_id(item)
    table_name = str(item.get("table_name") or "").strip()
    if not source_id or not table_name:
        return None
    role_code = str(item.get("role_code") or "").strip()
    query = _safe_dict(item.get("query"))
    query = normalize_binding_query_date_field(
        binding=item,
        query=query,
        left_time_semantic=left_time_semantic,
        right_time_semantic=right_time_semantic,
        scheme_meta=_safe_dict(scheme_meta),
    )
    return {
        "data_source_id": source_id,
        "table_name": table_name,
        "resource_key": _get_binding_resource_key(item),
        "required": _get_binding_required(item),
        "query": query,
        "dataset_source_type": str(item.get("dataset_source_type") or "collection_records").strip() or "collection_records",
        "role_code": role_code,
        "dataset_code": str(item.get("dataset_code") or "").strip(),
        "dataset_id": str(item.get("dataset_id") or query.get("dataset_id") or "").strip(),
        "dataset_name": str(item.get("dataset_name") or item.get("display_name") or "").strip(),
        "display_name": str(item.get("display_name") or item.get("dataset_name") or "").strip(),
        "source_kind": str(item.get("source_kind") or "").strip(),
        "provider_code": str(item.get("provider_code") or "").strip(),
        "input_plan_key": str(item.get("input_plan_key") or "").strip(),
        "input_plan_alias": str(item.get("input_plan_alias") or "").strip(),
        "input_plan_read_mode": str(item.get("input_plan_read_mode") or "").strip(),
        "input_plan_target_table": str(item.get("input_plan_target_table") or "").strip(),
        "input_plan_apply_biz_date_filter": item.get("input_plan_apply_biz_date_filter"),
    }


def _build_plan_binding_from_dataset_binding(
    *,
    binding: dict[str, Any],
    left_time_semantic: str,
    right_time_semantic: str,
    scheme_meta: dict[str, Any] | None = None,
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

    table_name = str(
        mapping_config.get("table_name")
        or mapping_config.get("dataset_code")
        or resource_key
    ).strip()
    if not table_name:
        return None
    binding_for_query = {
        **binding,
        "role_code": role_code,
        "data_source_id": source_id,
        "resource_key": resource_key,
        "table_name": table_name,
        "mapping_config": mapping_config,
        "query": query,
    }
    query = normalize_binding_query_date_field(
        binding=binding_for_query,
        query=query,
        left_time_semantic=left_time_semantic,
        right_time_semantic=right_time_semantic,
        scheme_meta=_safe_dict(scheme_meta),
    )

    return {
        "data_source_id": source_id,
        "table_name": table_name,
        "resource_key": resource_key,
        "required": bool(binding.get("is_required", True)),
        "query": query,
        "dataset_id": str(mapping_config.get("dataset_id") or binding.get("dataset_id") or query.get("dataset_id") or "").strip(),
        "dataset_source_type": str(mapping_config.get("dataset_source_type") or "collection_records").strip() or "collection_records",
        "role_code": role_code,
        "dataset_code": str(mapping_config.get("dataset_code") or resource_key).strip() or resource_key,
        "source_kind": str(mapping_config.get("source_kind") or binding.get("source_kind") or "").strip(),
        "provider_code": str(mapping_config.get("provider_code") or binding.get("provider_code") or "").strip(),
        "input_plan_key": str(mapping_config.get("input_plan_key") or binding.get("input_plan_key") or "").strip(),
        "input_plan_alias": str(mapping_config.get("input_plan_alias") or binding.get("input_plan_alias") or "").strip(),
        "input_plan_read_mode": str(mapping_config.get("input_plan_read_mode") or binding.get("input_plan_read_mode") or "").strip(),
        "input_plan_target_table": str(mapping_config.get("input_plan_target_table") or binding.get("input_plan_target_table") or "").strip(),
        "input_plan_apply_biz_date_filter": (
            mapping_config.get("input_plan_apply_biz_date_filter")
            if "input_plan_apply_biz_date_filter" in mapping_config
            else binding.get("input_plan_apply_biz_date_filter")
        ),
    }


def _collection_record_count(collection: dict[str, Any]) -> int:
    for key in ("record_count", "row_count"):
        try:
            return int(collection.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _binding_display_name(binding: dict[str, Any]) -> str:
    return str(
        binding.get("display_name")
        or binding.get("dataset_name")
        or binding.get("resource_key")
        or binding.get("table_name")
        or "未知数据集"
    ).strip()


def _is_required_collection_empty(binding: dict[str, Any], collection: dict[str, Any]) -> bool:
    return _get_binding_required(binding) and _collection_record_count(collection) <= 0


def _flatten_input_plan_entries(scheme_meta: dict[str, Any]) -> list[dict[str, Any]]:
    input_plan = _safe_dict(scheme_meta.get("input_plan_json"))
    if not input_plan:
        return []
    plans = [item for item in _safe_list(input_plan.get("plans")) if isinstance(item, dict)]
    if not plans and isinstance(input_plan.get("datasets"), list):
        plans = [input_plan]

    entries: list[dict[str, Any]] = []
    for raw_plan in plans:
        plan = _safe_dict(raw_plan)
        side = str(plan.get("side") or "").strip().lower()
        target_table = str(plan.get("target_table") or "").strip()
        for raw_dataset in _safe_list(plan.get("datasets")):
            if not isinstance(raw_dataset, dict):
                continue
            entry = dict(raw_dataset)
            if side:
                entry.setdefault("side", side)
            if target_table:
                entry.setdefault("target_table", target_table)
            entries.append(entry)
    return entries


def _entry_resource_keys(entry: dict[str, Any]) -> set[str]:
    return {
        value
        for value in (
            str(entry.get("resource_key") or "").strip(),
            str(entry.get("table") or "").strip(),
            str(entry.get("dataset_code") or "").strip(),
        )
        if value
    }


def _binding_resource_keys(binding: dict[str, Any]) -> set[str]:
    query = _safe_dict(binding.get("query"))
    return {
        value
        for value in (
            str(binding.get("resource_key") or "").strip(),
            str(binding.get("table_name") or "").strip(),
            str(binding.get("dataset_code") or "").strip(),
            str(query.get("resource_key") or "").strip(),
        )
        if value
    }


def _input_plan_entry_matches_binding(entry: dict[str, Any], binding: dict[str, Any]) -> bool:
    entry_side = str(entry.get("side") or "").strip().lower()
    binding_side = str(binding.get("side") or binding.get("role_code") or "").strip().lower()
    if binding_side.startswith("left"):
        binding_side = "left"
    elif binding_side.startswith("right"):
        binding_side = "right"
    if entry_side in {"left", "right"} and binding_side in {"left", "right"} and entry_side != binding_side:
        return False

    entry_alias = str(entry.get("alias") or "").strip()
    binding_alias = str(binding.get("input_plan_alias") or "").strip()
    if entry_alias and binding_alias and entry_alias != binding_alias:
        return False

    entry_target = str(entry.get("target_table") or "").strip()
    binding_target = str(binding.get("input_plan_target_table") or "").strip()
    if entry_target and binding_target and entry_target != binding_target:
        return False

    entry_source_id = str(entry.get("source_id") or entry.get("data_source_id") or "").strip()
    binding_source_id = _get_binding_source_id(binding)
    if entry_source_id and binding_source_id and entry_source_id != binding_source_id:
        return False

    entry_dataset_id = str(entry.get("dataset_id") or entry.get("id") or "").strip()
    binding_dataset_id = str(binding.get("dataset_id") or _safe_dict(binding.get("query")).get("dataset_id") or "").strip()
    if entry_dataset_id and binding_dataset_id and entry_dataset_id == binding_dataset_id:
        return True

    return bool(_entry_resource_keys(entry) & _binding_resource_keys(binding))


def _enrich_binding_with_input_plan(binding: dict[str, Any], scheme_meta: dict[str, Any]) -> dict[str, Any]:
    if not scheme_meta:
        return binding
    matched = next(
        (entry for entry in _flatten_input_plan_entries(scheme_meta) if _input_plan_entry_matches_binding(entry, binding)),
        None,
    )
    if not matched:
        return binding

    enriched = dict(binding)
    enriched["input_plan_alias"] = str(enriched.get("input_plan_alias") or matched.get("alias") or "").strip()
    enriched["input_plan_read_mode"] = str(enriched.get("input_plan_read_mode") or matched.get("read_mode") or "base").strip() or "base"
    enriched["input_plan_target_table"] = str(
        enriched.get("input_plan_target_table") or matched.get("target_table") or ""
    ).strip()
    if "input_plan_apply_biz_date_filter" not in enriched or enriched.get("input_plan_apply_biz_date_filter") is None:
        enriched["input_plan_apply_biz_date_filter"] = matched.get("apply_biz_date_filter", True)
    if not str(enriched.get("dataset_id") or "").strip():
        enriched["dataset_id"] = str(matched.get("dataset_id") or matched.get("id") or "").strip()
    for src_key, dst_key in (
        ("business_name", "dataset_name"),
        ("display_name", "display_name"),
    ):
        value = str(matched.get(src_key) or "").strip()
        if value and not str(enriched.get(dst_key) or "").strip():
            enriched[dst_key] = value
    return enriched


def _binding_apply_biz_date_filter(binding: dict[str, Any]) -> bool:
    value = binding.get("input_plan_apply_biz_date_filter")
    if value is None:
        return True
    return bool(value)


def _is_manual_or_static_dataset(binding: dict[str, Any]) -> bool:
    extract_config = _safe_dict(binding.get("dataset_extract_config"))
    collection_config = _safe_dict(binding.get("dataset_collection_config"))
    metadata = _safe_dict(binding.get("dataset_metadata"))
    mode_values = {
        str(extract_config.get(key) or "").strip().lower()
        for key in ("mode", "source_mode", "execution_mode", "type")
    }
    mode_values.update(
        str(collection_config.get(key) or "").strip().lower()
        for key in ("mode", "source_mode", "execution_mode", "type")
    )
    catalog = _safe_dict(metadata.get("catalog_profile"))
    mode_values.update(
        str(catalog.get(key) or "").strip().lower()
        for key in ("mode", "source_mode", "execution_mode", "type")
    )
    origin_type = str(binding.get("dataset_origin_type") or "").strip().lower()
    dataset_kind = str(binding.get("dataset_kind") or "").strip().lower()
    non_collectable_modes = {"manual_seed", "sample", "screenshot", "static", "mock", "seed"}
    return bool(mode_values & non_collectable_modes) or dataset_kind in {"sample", "screenshot"} or origin_type in {"sample"}


def _should_trigger_collection_for_binding(binding: dict[str, Any]) -> bool:
    read_mode = str(binding.get("input_plan_read_mode") or "base").strip().lower() or "base"
    if read_mode != "base" and not _binding_apply_biz_date_filter(binding):
        return False
    if _is_manual_or_static_dataset(binding):
        return False
    return True


def _sync_job_id(job: Any) -> str:
    job_dict = _safe_dict(job)
    return str(job_dict.get("sync_job_id") or job_dict.get("id") or "").strip()


def _sync_job_status(job: Any) -> str:
    job_dict = _safe_dict(job)
    return str(job_dict.get("status") or job_dict.get("job_status") or "").strip().lower()


def _sync_job_error(job: Any) -> str:
    job_dict = _safe_dict(job)
    return str(
        job_dict.get("error_message")
        or job_dict.get("last_error_message")
        or job_dict.get("error")
        or ""
    ).strip()


async def _wait_dataset_collection_job(
    *,
    auth_token: str,
    sync_job_id: str,
    timeout_seconds: int = 300,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    if not sync_job_id:
        return {"success": False, "error": "采集任务未返回 sync_job_id，无法确认采集结果"}

    deadline = asyncio.get_running_loop().time() + max(timeout_seconds, 1)
    last_job: dict[str, Any] = {}
    last_error = ""
    while True:
        result = await data_source_get_sync_job(auth_token, sync_job_id, mode="real")
        if bool(result.get("success")):
            last_job = _safe_dict(result.get("job"))
            status = _sync_job_status(last_job)
            if status in {"success", "succeeded", "completed", "done"}:
                return {"success": True, "job": last_job}
            if status in {"failed", "error", "cancelled", "canceled"}:
                return {
                    "success": False,
                    "job": last_job,
                    "error": _sync_job_error(last_job) or "采集任务执行失败",
                }
        else:
            last_error = str(result.get("error") or result.get("detail") or "").strip()

        if asyncio.get_running_loop().time() >= deadline:
            return {
                "success": False,
                "job": last_job,
                "error": last_error or "采集任务执行超时，请稍后重试",
            }
        await asyncio.sleep(poll_interval_seconds)


async def _trigger_and_wait_collection(
    *,
    auth_token: str,
    source_id: str,
    dataset_id: str,
    resource_key: str,
    biz_date: str,
    trigger_mode: str,
) -> dict[str, Any]:
    collect_result = await data_source_trigger_dataset_collection(
        auth_token,
        source_id,
        dataset_id=dataset_id,
        resource_key=resource_key,
        biz_date=biz_date,
        trigger_mode=trigger_mode,
        background=True,
        mode="real",
    )
    if not bool(collect_result.get("success")):
        return collect_result

    job = _safe_dict(collect_result.get("job"))
    status = _sync_job_status(job)
    if not bool(collect_result.get("queued")) and status not in {"queued", "pending", "running"}:
        return collect_result

    wait_result = await _wait_dataset_collection_job(
        auth_token=auth_token,
        sync_job_id=_sync_job_id(job),
    )
    if bool(wait_result.get("success")):
        return {
            **collect_result,
            "job": _safe_dict(wait_result.get("job")) or job,
            "queued": bool(collect_result.get("queued")),
        }
    return {
        **collect_result,
        "success": False,
        "job": _safe_dict(wait_result.get("job")) or job,
        "error": str(wait_result.get("error") or "采集任务执行失败"),
        "queued": bool(collect_result.get("queued")),
    }


async def _hydrate_binding_source_meta(
    *,
    auth_token: str,
    binding: dict[str, Any],
) -> dict[str, Any]:
    hydrated = dict(binding)
    source_id = _get_binding_source_id(binding)
    if source_id and not (
        str(binding.get("source_kind") or "").strip()
        and str(binding.get("provider_code") or "").strip()
    ):
        result = await data_source_get(auth_token, source_id, mode="real")
        source = _safe_dict(result.get("source"))
        if bool(result.get("success")) and source:
            hydrated["source_kind"] = str(hydrated.get("source_kind") or source.get("source_kind") or "").strip()
            hydrated["provider_code"] = str(hydrated.get("provider_code") or source.get("provider_code") or "").strip()

    dataset_id = str(hydrated.get("dataset_id") or _safe_dict(hydrated.get("query")).get("dataset_id") or "").strip()
    resource_key = _get_binding_resource_key(hydrated)
    if source_id and (dataset_id or resource_key):
        dataset_result = await data_source_get_dataset(
            auth_token,
            dataset_id=dataset_id,
            source_id=source_id,
            resource_key=resource_key,
            mode="real",
        )
        dataset = _safe_dict(dataset_result.get("dataset"))
        if bool(dataset_result.get("success")) and dataset:
            hydrated["dataset_id"] = str(hydrated.get("dataset_id") or dataset.get("id") or "").strip()
            hydrated["dataset_code"] = str(hydrated.get("dataset_code") or dataset.get("dataset_code") or "").strip()
            hydrated["dataset_name"] = str(hydrated.get("dataset_name") or dataset.get("business_name") or dataset.get("dataset_name") or "").strip()
            hydrated["display_name"] = str(hydrated.get("display_name") or dataset.get("business_name") or dataset.get("dataset_name") or "").strip()
            hydrated["dataset_kind"] = str(dataset.get("dataset_kind") or "").strip()
            hydrated["dataset_origin_type"] = str(dataset.get("origin_type") or "").strip()
            hydrated["dataset_extract_config"] = _safe_dict(dataset.get("extract_config"))
            hydrated["dataset_collection_config"] = _safe_dict(dataset.get("collection_config"))
            hydrated["dataset_metadata"] = _safe_dict(dataset.get("metadata"))
            hydrated["source_kind"] = str(hydrated.get("source_kind") or dataset.get("source_kind") or "").strip()
            hydrated["provider_code"] = str(hydrated.get("provider_code") or dataset.get("provider_code") or "").strip()
    return hydrated


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


def _build_recon_inputs_from_ready_collections(
    ready_collections: list[dict[str, Any]],
    *,
    biz_date: str,
) -> list[dict[str, Any]]:
    recon_inputs: list[dict[str, Any]] = []
    for item in ready_collections:
        binding = _safe_dict(item.get("binding"))
        collection = _safe_dict(item.get("collection_records"))
        table_name = str(binding.get("table_name") or "").strip()
        source_id = _get_binding_source_id(binding)
        if not table_name or not source_id:
            continue
        query = {"resource_key": _get_binding_resource_key(binding)}
        dataset_id = str(collection.get("dataset_id") or binding.get("dataset_id") or "").strip()
        if dataset_id:
            query["dataset_id"] = dataset_id

        raw_query = _safe_dict(binding.get("query"))
        filters = _safe_dict(raw_query.get("filters"))
        biz_date_field = str(
            raw_query.get("biz_date_field")
            or raw_query.get("date_field")
            or ""
        ).strip()
        if biz_date and _binding_apply_biz_date_filter(binding):
            query["biz_date"] = biz_date
            if biz_date_field:
                filters[biz_date_field] = biz_date
                query["date_field"] = biz_date_field
        if filters:
            query["filters"] = filters

        dataset_source_type = str(binding.get("dataset_source_type") or "collection_records").strip() or "collection_records"
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
    source_collection_json = _safe_dict(ctx.get("source_collection_json"))
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
                "source_snapshot_json": source_collection_json,
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
            "source_snapshot_json": source_collection_json,
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
    scheme_meta = _get_scheme_meta(ctx)
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
                scheme_meta=scheme_meta,
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
                    scheme_meta=scheme_meta,
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
                scheme_meta=scheme_meta,
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
                    scheme_meta=scheme_meta,
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
            normalized = _normalize_plan_binding(
                row,
                left_time_semantic=left_time_semantic,
                right_time_semantic=right_time_semantic,
                scheme_meta=scheme_meta,
            )
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

    bindings = [_enrich_binding_with_input_plan(item, scheme_meta) for item in bindings]
    bindings = [
        await _hydrate_binding_source_meta(auth_token=auth_token, binding=item)
        for item in bindings
    ]

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
    ready_collections: list[dict[str, Any]] = []
    missing_bindings: list[dict[str, Any]] = []
    collection_attempts: list[dict[str, Any]] = []
    biz_date = str(ctx.get("biz_date") or "").strip()
    run_context = _safe_dict(ctx.get("run_context"))
    collection_trigger_mode = _normalize_collection_trigger_mode(run_context.get("trigger_type"))
    should_collect_first = _should_collect_before_recon(run_context.get("trigger_type"))

    for binding in bindings:
        source_id = _get_binding_source_id(binding)
        table_name = str(binding.get("table_name") or "").strip()
        if not source_id or not table_name:
            missing_bindings.append({**binding, "error": "缺少 data_source_id/source_id 或 table_name"})
            continue
        if should_collect_first and _should_trigger_collection_for_binding(binding):
            collect_result = await _trigger_and_wait_collection(
                auth_token=auth_token,
                source_id=source_id,
                dataset_id=str(binding.get("dataset_id") or "").strip(),
                resource_key=_get_binding_resource_key(binding),
                biz_date=biz_date,
                trigger_mode=collection_trigger_mode,
            )
            collection_success = bool(collect_result.get("success"))
            collection_error = "" if collection_success else str(
                collect_result.get("error") or collect_result.get("detail") or "采集失败"
            )
            collection_attempts.append(
                {
                    "binding": binding,
                    "success": collection_success,
                    "job": _safe_dict(collect_result.get("job")),
                    "error": collection_error,
                }
            )
            if not collection_success:
                missing_bindings.append({**binding, "error": f"先同步失败：{collection_error}"})
                continue
        list_biz_date = biz_date if _binding_apply_biz_date_filter(binding) else ""
        result = await data_source_list_collection_records(
            auth_token,
            source_id,
            dataset_id=str(binding.get("dataset_id") or "").strip(),
            resource_key=_get_binding_resource_key(binding),
            biz_date=list_biz_date,
            limit=1,
        )
        record_count = int(result.get("record_count") or result.get("count") or 0)
        records = _safe_list(result.get("records") or result.get("rows"))
        collection = {
            "dataset_id": str(result.get("dataset_id") or binding.get("dataset_id") or ""),
            "resource_key": str(result.get("resource_key") or _get_binding_resource_key(binding)),
            "record_count": record_count or len(records),
            "sample_records": records[:1],
        }
        if bool(result.get("success")) and not _is_required_collection_empty(binding, collection):
            ready_binding = {**binding, "dataset_source_type": "collection_records"}
            ready_collections.append({"binding": ready_binding, "collection_records": collection})
        else:
            error = str(result.get("error") or "暂无采集记录，请先采集数据")
            if bool(result.get("success")) and _is_required_collection_empty(binding, collection):
                error = "暂无采集记录，请先采集数据"
            missing_bindings.append({**binding, "error": error})

    ctx["ready_collections"] = ready_collections
    ctx["missing_bindings"] = missing_bindings
    if collection_attempts:
        ctx["collection_attempts"] = collection_attempts
    return {"recon_ctx": ctx}


def bind_ready_collection_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    ready_collections = [v for v in _safe_list(ctx.get("ready_collections")) if isinstance(v, dict)]
    collection_attempts = [v for v in _safe_list(ctx.get("collection_attempts")) if isinstance(v, dict)]
    biz_date = str(ctx.get("biz_date") or "")
    recon_inputs = _build_recon_inputs_from_ready_collections(ready_collections, biz_date=biz_date)
    ctx["recon_inputs"] = recon_inputs
    source_collection_json = {
        "ready_count": len(ready_collections),
        "missing_count": len(_safe_list(ctx.get("missing_bindings"))),
        "collections": ready_collections,
        "biz_date": biz_date,
    }
    if collection_attempts:
        source_collection_json["collection_attempts"] = collection_attempts
    ctx["source_collection_json"] = source_collection_json
    return {"recon_ctx": ctx}


def validate_dataset_completeness_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    recon_inputs = [v for v in _safe_list(ctx.get("recon_inputs")) if isinstance(v, dict)]
    missing_bindings = [v for v in _safe_list(ctx.get("missing_bindings")) if isinstance(v, dict)]

    required_missing = [b for b in missing_bindings if _get_binding_required(b)]
    if required_missing:
        names = [
            f"{_binding_display_name(b)}（{str(b.get('error') or '数据未就绪')}）"
            for b in required_missing
        ]
        ctx["failed_stage"] = "validate_dataset"
        biz_date = str(ctx.get("biz_date") or "").strip()
        date_hint = f"业务日期 {biz_date} 的" if biz_date else ""
        ctx["failed_reason"] = (
            f"数据未就绪，无法执行对账：{' / '.join(names)}。"
            f"请先在数据连接中完成{date_hint}数据采集，或等待自动采集成功后重试。"
        )
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


def _lookup_local_user(user_id: str) -> dict[str, Any]:
    normalized = str(user_id or "").strip()
    if not normalized:
        return {}
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, email, phone, role, company_id, department_id
                    FROM users
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (normalized,),
                )
                row = cur.fetchone()
                return dict(row) if row else {}
    except Exception as exc:
        logger.warning("[auto_scheme_run] 查询发起人用户失败 user_id=%s err=%s", normalized, exc)
        return {}


def _resolve_run_initiator(ctx: dict[str, Any]) -> dict[str, Any]:
    run_context = _safe_dict(ctx.get("run_context"))
    trigger_user = _safe_dict(run_context.get("trigger_user"))
    if trigger_user:
        user_id = str(trigger_user.get("user_id") or trigger_user.get("id") or "").strip()
        username = str(trigger_user.get("username") or "").strip()
        raw_contact = _safe_dict(
            trigger_user.get("contact_json")
            or trigger_user.get("contact")
            or trigger_user.get("owner_contact_json")
        )
        mobile = str(
            trigger_user.get("mobile")
            or trigger_user.get("phone")
            or trigger_user.get("telephone")
            or raw_contact.get("mobile")
            or raw_contact.get("phone")
            or raw_contact.get("telephone")
            or ""
        ).strip()
        dingtalk_user_id = str(
            trigger_user.get("dingtalk_user_id")
            or trigger_user.get("ding_user_id")
            or trigger_user.get("unionid")
            or raw_contact.get("dingtalk_user_id")
            or raw_contact.get("ding_user_id")
            or raw_contact.get("unionid")
            or ""
        ).strip()
        if user_id:
            local_user = _lookup_local_user(user_id)
            if local_user:
                local_mobile = str(local_user.get("phone") or "").strip()
                return {
                    "name": str(local_user.get("username") or username or ""),
                    "identifier": dingtalk_user_id,
                    "contact_json": {
                        "phone": local_mobile or mobile,
                        "local_user_id": user_id,
                    },
                    "source": "trigger_user",
                }
            return {
                "name": username,
                "identifier": dingtalk_user_id,
                "contact_json": {"phone": mobile, "local_user_id": user_id},
                "source": "trigger_user",
            }
        if username:
            return {
                "name": username,
                "identifier": dingtalk_user_id,
                "contact_json": {"phone": mobile},
                "source": "trigger_user",
            }

    run_plan = _safe_dict(ctx.get("run_plan"))
    created_by = str(run_plan.get("created_by") or "").strip()
    if created_by:
        local_user = _lookup_local_user(created_by)
        return {
            "name": str(local_user.get("username") or ""),
            "identifier": "",
            "contact_json": {
                "phone": str(local_user.get("phone") or ""),
                "local_user_id": created_by,
            },
            "source": "run_plan_created_by",
        }
    return {"name": "", "identifier": "", "contact_json": {}, "source": "missing"}


def _extract_todo_key_hint(
    exception: dict[str, Any],
    field_labels: dict[str, str] | None = None,
    left_name: str = "",
    right_name: str = "",
) -> str:
    """Extract a short key identifier from the exception for use in the todo title.

    Priority: join_key fields + compare values → first ：-separated segment of summary.
    Returns a compact string like "业务单号=ORD-001、金额=17" or empty string.
    """
    fl = field_labels or {}
    atype = str(exception.get("anomaly_type") or "").strip()
    detail = _safe_dict(exception.get("detail_json"))
    join_key = [k for k in _safe_list(detail.get("join_key") or exception.get("join_key")) if isinstance(k, dict)]
    raw_record = _safe_dict(exception.get("raw_record") or detail.get("raw_record"))

    def _raw_key_val(field: str) -> str:
        prefix = "right_recon_ready." if atype == "target_only" else "left_recon_ready."
        v = raw_record.get(prefix + field) or raw_record.get(field)
        return str(v).strip() if v is not None and str(v).strip() not in {"None", "null", ""} else ""

    if join_key:
        parts: list[str] = []
        for k in join_key[:2]:
            field = str(k.get("field") or k.get("source_field") or k.get("target_field") or "").strip()
            value = k.get("target_value" if atype == "target_only" else "source_value") or k.get("value")
            val_str = str(value).strip() if value is not None and str(value).strip() not in {"None", "null", ""} else ""
            if not val_str and field:
                val_str = _raw_key_val(field)
            if field and val_str:
                display_field = fl.get(field) or field
                parts.append(f"{display_field}={val_str}")
        compare_values = [
            c for c in _safe_list(detail.get("compare_values") or exception.get("compare_values"))
            if isinstance(c, dict)
        ]
        for cv in compare_values[:2]:
            if atype == "target_only":
                field = str(cv.get("target_field") or "").strip()
                value = cv.get("target_value")
            else:
                field = str(cv.get("source_field") or "").strip()
                value = cv.get("source_value")
            val_str = str(value).strip() if value is not None and str(value).strip() not in {"None", "null", ""} else ""
            if field and val_str:
                display_field = fl.get(field) or field
                text = f"{display_field}={val_str}"
                if text not in parts:
                    parts.append(text)
        if parts:
            return "、".join(parts)

    # Fallback: extract from summary text (after first ：, before double-space)
    summary = str(exception.get("summary") or "")
    if "：" in summary:
        after_colon = _replace_generic_side_labels(
            summary.split("：", 1)[1].strip(),
            left_name=left_name,
            right_name=right_name,
        )
        key_part = after_colon.split("  ")[0].strip()
        if key_part and len(key_part) <= 60 and "public." not in key_part:
            return key_part
    return ""


def _compose_execution_exception_reminder_text(
    *,
    run_plan: dict[str, Any],
    scheme: dict[str, Any],
    biz_date: str,
    exception: dict[str, Any],
) -> tuple[str, str, str]:
    """Return (todo_title, bot_message_title, bot_message_content)."""
    plan_name = str(
        run_plan.get("plan_name")
        or run_plan.get("name")
        or scheme.get("scheme_name")
        or scheme.get("name")
        or "自动对账任务"
    ).strip()
    scheme_name = str(scheme.get("scheme_name") or scheme.get("name") or "").strip()

    # Extract dataset names from scheme_meta_json for user-friendly labels
    meta = _safe_dict(scheme.get("scheme_meta_json") or scheme.get("scheme_meta") or scheme.get("meta"))
    left_name, right_name = _base_source_names_from_input_plan(meta)
    if not left_name:
        left_name = next(
            (_source_display_name(s) for s in _safe_list(meta.get("left_sources")) if isinstance(s, dict) and _source_display_name(s)),
            ""
        )
    if not right_name:
        right_name = next(
            (_source_display_name(s) for s in _safe_list(meta.get("right_sources")) if isinstance(s, dict) and _source_display_name(s)),
            ""
        )

    field_labels = _build_field_label_map(meta)
    anomaly_type = str(exception.get("anomaly_type") or "unknown").strip()
    anomaly_label = _label_anomaly_type(anomaly_type, left_name=left_name, right_name=right_name)
    summary = _replace_generic_side_labels(
        str(exception.get("summary") or "详见对账结果"),
        left_name=left_name,
        right_name=right_name,
    )

    # Todo title: include key field so finance staff can identify the record directly
    key_hint = _extract_todo_key_hint(
        exception,
        field_labels=field_labels,
        left_name=left_name,
        right_name=right_name,
    )
    if key_hint:
        todo_title = f"【对账异常】{anomaly_label} | {key_hint}"
    else:
        todo_title = f"【对账异常】{anomaly_label}"
    if biz_date:
        todo_title += f" | {biz_date}"

    bot_title = f"{plan_name} 对账异常催办"
    lines = [
        f"任务：{plan_name}",
        f"业务日期：{biz_date}" if biz_date else "",
        f"对账方案：{scheme_name}" if scheme_name else "",
        f"异常详情：{summary}",
        "请尽快处理完成，并在钉钉待办中标记完成后同步给财务复核。",
    ]
    bot_content = "\n\n".join(line for line in lines if line)
    return todo_title, bot_title, bot_content


def _format_anomaly_type_stats(
    anomalies: list[dict[str, Any]],
    *,
    left_name: str = "",
    right_name: str = "",
) -> list[str]:
    counts = Counter(str(item.get("anomaly_type") or "unknown") for item in anomalies)
    if not counts:
        return ["无异常"]
    return [
        f"{_label_anomaly_type(atype, left_name=left_name, right_name=right_name)}：{count} 条"
        for atype, count in counts.most_common()
    ]


def _format_recon_result_summary_lines(summary: dict[str, Any], *, left_name: str = "", right_name: str = "") -> list[str]:
    left = str(left_name or "左侧基础表").strip()
    right = str(right_name or "右侧基础表").strip()
    source_only = _safe_int(summary.get("source_only"), 0)
    target_only = _safe_int(summary.get("target_only"), 0)
    matched_with_diff = _safe_int(summary.get("matched_with_diff"), 0)
    matched_exact = _safe_int(summary.get("matched_exact"), 0)
    return [
        f"- 仅 {left} 存在（{right} 缺失）：{source_only} 条",
        f"- 仅 {right} 存在（{left} 缺失）：{target_only} 条",
        f"- 金额/字段差异：{matched_with_diff} 条",
        f"- 完全匹配：{matched_exact} 条",
    ]


def _resolve_notify_policy(run_plan: dict[str, Any]) -> dict[str, int]:
    meta = _safe_dict(run_plan.get("plan_meta_json") or run_plan.get("plan_meta") or run_plan.get("meta"))
    policy = _safe_dict(meta.get("reminder_policy_json") or meta.get("reminder_policy"))
    limit = _safe_int(
        policy.get("explosion_threshold")
        or policy.get("max_detail_reminders")
        or os.getenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT"),
        _DEFAULT_NOTIFY_EXPLOSION_LIMIT,
    )
    limit = max(1, limit)
    return {
        "explosion_threshold": limit,
        "explosion_sample_limit": limit,
    }


def _get_nested_value(payload: Any, path: str) -> Any:
    current: Any = payload
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _extract_collection_date_sample(binding: dict[str, Any], collection: dict[str, Any]) -> str:
    query = _safe_dict(binding.get("query"))
    date_field = str(query.get("date_field") or query.get("biz_date_field") or "").strip()
    if not date_field:
        return ""
    for row in _safe_list(collection.get("records") or collection.get("rows") or collection.get("sample_records")):
        if not isinstance(row, dict):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        value = _get_nested_value(payload, date_field)
        if value is not None and str(value).strip() not in {"", "None", "null"}:
            return str(value).strip()
    return ""


def _date_field_format_hint(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "未取到样例"
    if len(text) == 8 and text.isdigit():
        return "yyyyMMdd"
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return "yyyy-MM-dd"
    return "按样例值识别"


def _format_date_binding_lines(ctx: dict[str, Any]) -> list[str]:
    ready = [v for v in _safe_list(ctx.get("ready_collections")) if isinstance(v, dict)]
    if not ready:
        ready = [v for v in _safe_list(_safe_dict(ctx.get("source_collection_json")).get("collections")) if isinstance(v, dict)]
    lines: list[str] = []
    for item in ready:
        binding = _safe_dict(item.get("binding"))
        collection = _safe_dict(item.get("collection_records"))
        query = _safe_dict(binding.get("query"))
        date_field = str(query.get("date_field") or query.get("biz_date_field") or "").strip()
        if not date_field:
            continue
        sample = _extract_collection_date_sample(binding, collection)
        side = str(binding.get("side") or binding.get("role_code") or "").strip().lower()
        side_label = "左侧" if side == "left" else "右侧" if side == "right" else "数据集"
        display_name = _binding_display_name(binding)
        display_date_field = str(query.get("display_date_field") or date_field).strip()
        sample_text = sample or "未取到样例"
        lines.append(
            f"{side_label} {display_name}：日期字段 {display_date_field}（{date_field}），"
            f"格式 {_date_field_format_hint(sample)}，样例 {sample_text}"
        )
    return lines


def _compose_run_summary_notification_text(
    *,
    ctx: dict[str, Any],
    anomalies: list[dict[str, Any]],
    threshold: int,
    explosion: bool,
) -> tuple[str, str]:
    run_plan = _safe_dict(ctx.get("run_plan"))
    scheme = _safe_dict(ctx.get("scheme"))
    plan_name = str(
        run_plan.get("plan_name")
        or run_plan.get("name")
        or scheme.get("scheme_name")
        or scheme.get("name")
        or "自动对账任务"
    ).strip()
    scheme_name = str(scheme.get("scheme_name") or scheme.get("name") or "").strip()
    biz_date = str(ctx.get("biz_date") or _safe_dict(ctx.get("run_context")).get("biz_date") or "").strip()
    left_name, right_name = _resolve_side_names(ctx)
    summary = _safe_dict(ctx.get("recon_result_summary_json") or _safe_dict(ctx.get("execution_run_record")).get("recon_result_summary_json"))

    total = len(anomalies)
    status = "异常数过高，已暂停逐条催办" if explosion else "执行完成"
    title = f"{plan_name} 对账结果汇总"
    lines = [
        f"任务：{plan_name}",
        f"对账方案：{scheme_name}" if scheme_name else "",
        f"业务日期：{biz_date}" if biz_date else "",
        f"执行结果：{status}",
        f"异常总数：{total} 条",
    ]
    if threshold:
        lines.append(f"爆炸保护阈值：{threshold} 条")
    if summary:
        lines.append("对账结果摘要：")
        lines.extend(_format_recon_result_summary_lines(summary, left_name=left_name, right_name=right_name))
    else:
        lines.append("异常统计：")
        lines.extend(f"- {line}" for line in _format_anomaly_type_stats(anomalies, left_name=left_name, right_name=right_name))
    date_lines = _format_date_binding_lines(ctx)
    if date_lines:
        lines.append("对账日期字段：")
        lines.extend(f"- {line}" for line in date_lines)
    if explosion:
        lines.append("请优先检查对账方案、匹配字段、对账日期字段和值格式，确认是否配置导致异常数异常放大。")
    else:
        lines.append("如异常数量或类型不符合预期，请检查方案配置或数据日期范围。")
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
    patch: dict[str, Any] = {
        "reminder_status": reminder_status,
        "latest_feedback": latest_feedback,
        "feedback_json": feedback_json,
    }
    if owner_name is not None:
        patch["owner_name"] = owner_name
    if owner_identifier is not None:
        patch["owner_identifier"] = owner_identifier
    if owner_contact_json is not None:
        patch["owner_contact_json"] = owner_contact_json

    update_result = await execution_run_exception_update(auth_token, exception_id, patch)
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

    todo_title, bot_title, bot_content = _compose_execution_exception_reminder_text(
        run_plan=run_plan,
        scheme=scheme,
        biz_date=biz_date,
        exception=exception,
    )
    reminder = adapter.send_reminder(
        title=bot_title,
        content=bot_content,
        todo_title=todo_title,
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


async def _send_run_summary_notification(
    *,
    ctx: dict[str, Any],
    auth_token: str,
    channel_config: Any | None,
    anomalies: list[dict[str, Any]],
    threshold: int,
    explosion: bool,
) -> dict[str, Any]:
    if channel_config is None:
        return {"status": "skipped", "reason": "channel_missing", "error": "运行计划未配置协作通道"}

    run_plan = _safe_dict(ctx.get("run_plan"))
    plan_meta = _safe_dict(run_plan.get("plan_meta_json") or run_plan.get("plan_meta") or run_plan.get("meta"))
    summary_recipient = _safe_dict(plan_meta.get("summary_recipient"))
    recipient_channel_id = str(summary_recipient.get("channel_config_id") or "").strip()
    channel_id = str(getattr(channel_config, "id", "") or "").strip()
    if summary_recipient and recipient_channel_id and recipient_channel_id != channel_id:
        return {
            "status": "skipped",
            "reason": "summary_recipient_channel_mismatch",
            "error": "对账汇总接收人与当前协作通道不一致，请重新保存运行计划",
            "summary_recipient": summary_recipient,
        }

    initiator = _resolve_run_initiator(ctx)
    recipient = summary_recipient or initiator
    identifier = str(
        recipient.get("user_id")
        or recipient.get("identifier")
        or recipient.get("provider_user_id")
        or ""
    ).strip()
    name = str(recipient.get("display_name") or recipient.get("name") or "").strip()
    contact = _safe_dict(recipient.get("contact_json") or recipient.get("contact"))
    mobile = str(contact.get("mobile") or contact.get("phone") or contact.get("telephone") or "").strip()
    if not any([identifier, mobile, name]):
        return {"status": "skipped", "reason": "summary_recipient_missing", "error": "未找到可通知的对账汇总接收人"}

    adapter = get_notification_adapter(
        provider=str(getattr(channel_config, "provider", "") or ""),
        channel_config=channel_config,
    )
    resolved = None
    last_error = ""
    if identifier:
        result = adapter.resolve_user(user_id=identifier)
        if result.success:
            resolved = result.resolved_user or (result.users[0] if result.users else None)
        last_error = result.message
    if resolved is None and mobile:
        result = adapter.resolve_user(mobile=mobile)
        if result.success:
            resolved = result.resolved_user or (result.users[0] if result.users else None)
        last_error = result.message
    if resolved is None and name:
        result = adapter.resolve_user(keyword=name)
        if result.success:
            resolved = result.resolved_user or (result.users[0] if result.users else None)
        last_error = result.message
    if resolved is None:
        return {
            "status": "skipped",
            "reason": "summary_recipient_unresolved",
            "error": last_error or "对账汇总接收人无法解析为可触达用户",
            "summary_recipient": recipient,
        }

    title, content = _compose_run_summary_notification_text(
        ctx=ctx,
        anomalies=anomalies,
        threshold=threshold,
        explosion=explosion,
    )
    run = _safe_dict(ctx.get("execution_run_record"))
    result = adapter.send_bot_message(
        title=title,
        content=content,
        to_user_id=str(resolved.user_id or ""),
        content_type="text",
    )
    if not result.success:
        return {
            "status": "failed",
            "reason": "send_failed",
            "error": str(result.message or "发送对账结果汇总失败"),
            "summary_recipient": recipient,
        }
    return {
        "status": "sent",
        "reason": "",
        "error": "",
        "summary_recipient": {
            "name": str(resolved.display_name or name),
            "identifier": str(resolved.user_id or identifier),
            "mobile": str(resolved.mobile or mobile),
            "source": "plan_meta" if summary_recipient else str(initiator.get("source") or ""),
        },
        "message_id": str(result.message_id or ""),
        "run_id": str(run.get("id") or ""),
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
    notify_policy = _resolve_notify_policy(run_plan)
    explosion_threshold = int(notify_policy["explosion_threshold"])
    explosion_sample_limit = int(notify_policy["explosion_sample_limit"])
    total_anomaly_count = len(anomalies)
    notify_explosion = total_anomaly_count > explosion_threshold
    anomalies_to_create = anomalies
    if notify_explosion:
        anomalies_to_create = anomalies[:explosion_sample_limit]
    ctx["auto_notify_policy"] = {
        **notify_policy,
        "anomaly_count": total_anomaly_count,
        "explosion": notify_explosion,
        "created_exception_sample_limit": len(anomalies_to_create),
    }

    # 提取左右数据集业务名称和字段标签，用于生成财务友好的异常摘要
    left_name, right_name = _resolve_side_names(ctx)
    scheme = _safe_dict(ctx.get("scheme"))
    scheme_meta = _safe_dict(
        scheme.get("scheme_meta_json") or scheme.get("scheme_meta") or scheme.get("meta")
    )
    field_labels = _build_field_label_map(scheme_meta)

    created = 0
    created_exceptions: list[dict[str, Any]] = []
    for idx, item in enumerate(anomalies_to_create, start=1):
        anomaly_key = str(item.get("item_id") or item.get("anomaly_key") or f"{run_id}:{idx}")
        atype = str(item.get("anomaly_type") or "unknown")
        payload = {
            "auth_token": auth_token,
            "run_id": run_id,
            "scheme_code": scheme_code,
            "anomaly_key": anomaly_key,
            "anomaly_type": atype,
            "summary": _build_anomaly_summary(
                atype, item, left_name=left_name, right_name=right_name, field_labels=field_labels
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
    if notify_explosion:
        ctx["exception_creation_limited"] = True
        ctx["exception_total_count"] = total_anomaly_count
        ctx["exception_created_sample_count"] = created
    return {"recon_ctx": ctx}


async def maybe_auto_notify_node(state: AgentState) -> dict[str, Any]:
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run_plan = _safe_dict(ctx.get("run_plan"))
    policy = _safe_dict(ctx.get("auto_notify_policy")) or _resolve_notify_policy(run_plan)
    threshold = int(policy.get("explosion_threshold") or _DEFAULT_NOTIFY_EXPLOSION_LIMIT)
    anomalies = [item for item in _safe_list(ctx.get("anomaly_items")) if isinstance(item, dict)]
    explosion = bool(policy.get("explosion")) or len(anomalies) > threshold
    created_exceptions = [item for item in _safe_list(ctx.get("created_exceptions")) if isinstance(item, dict)]
    channel_config_id = str(run_plan.get("channel_config_id") or "").strip()
    channel_config = load_company_channel_config_by_id(channel_id=channel_config_id) if channel_config_id else None
    summary_result = await _send_run_summary_notification(
        ctx=ctx,
        auth_token=auth_token,
        channel_config=channel_config,
        anomalies=anomalies,
        threshold=threshold,
        explosion=explosion,
    )

    if not created_exceptions:
        ctx["auto_notify_status"] = "skipped_no_exception"
        ctx["auto_notify_result"] = {
            "total": len(anomalies),
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "items": [],
            "summary_notification": summary_result,
        }
        return {"recon_ctx": ctx}

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
            "summary_notification": summary_result,
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
            "summary_notification": summary_result,
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

    if explosion:
        summary_status = str(summary_result.get("status") or "").strip()
        summary_error = str(summary_result.get("error") or summary_result.get("reason") or "").strip()
        summary_sent = summary_status == "sent"
        latest_feedback = (
            "异常数量超过阈值，已发送汇总给发起人，跳过逐条责任人催办"
            if summary_sent
            else f"异常数量超过阈值，已跳过逐条责任人催办；发起人汇总通知发送失败：{summary_error or '未知原因'}"
        )
        updated_refs = await _mark_created_exceptions_skipped(
            auth_token=auth_token,
            created_exceptions=created_exceptions,
            reminder_status="summary_only",
            latest_feedback=latest_feedback,
            feedback_patch={
                "auto_notify_skipped_reason": "anomaly_explosion",
                "anomaly_count": len(anomalies),
                "explosion_threshold": threshold,
                "summary_notification": summary_result,
            },
        )
        ctx["created_exceptions"] = updated_refs
        ctx["auto_notify_status"] = "summary_only" if summary_sent else "summary_failed"
        ctx["auto_notify_result"] = {
            "total": len(anomalies),
            "created_exception_sample_count": len(created_exceptions),
            "sent": 0,
            "failed": 0,
            "skipped": len(created_exceptions),
            "channel_config_id": channel_config_id,
            "provider": str(getattr(channel_config, "provider", "") or ""),
            "channel_name": str(getattr(channel_config, "name", "") or ""),
            "explosion": True,
            "explosion_threshold": threshold,
            "summary_notification": summary_result,
            "items": [
                {
                    "exception_id": str(item.get("exception_id") or ""),
                    "status": "skipped",
                    "reason": "anomaly_explosion",
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
            "summary_notification": summary_result,
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
        "summary_notification": summary_result,
        "items": results,
    }
    return {"recon_ctx": ctx}


async def update_rerun_exception_verification_node(state: AgentState) -> dict[str, Any]:
    """After a rerun, update the original exception's verification status."""
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    run_context = _safe_dict(ctx.get("run_context"))
    exception_id = str(run_context.get("rerun_exception_id") or "").strip()
    if not auth_token or not exception_id:
        return {"recon_ctx": ctx}

    run = _safe_dict(ctx.get("execution_run_record"))
    run_id = str(run.get("id") or "").strip()
    execution_status = str(run.get("execution_status") or ctx.get("exec_status") or "").strip()
    if not run_id or execution_status not in {"success", "partial_success"}:
        return {"recon_ctx": ctx}

    anomalies = [item for item in _safe_list(ctx.get("anomaly_items")) if isinstance(item, dict)]
    existing_result = await execution_run_exception_get(auth_token, exception_id)
    existing = _safe_dict(existing_result.get("exception")) if bool(existing_result.get("success")) else {}
    feedback_json = _merge_feedback(
        existing.get("feedback_json"),
        {
            "verify_run_id": run_id,
            "verify_trigger_type": "rerun",
            "verify_anomaly_count": len(anomalies),
            "verified_at": datetime.now().isoformat(),
            "rerun_from_run_id": str(run_context.get("rerun_from_run_id") or ""),
        },
    )

    if anomalies:
        patch = {
            "processing_status": "reopened",
            "fix_status": "pending",
            "latest_feedback": f"重新对账验证仍发现 {len(anomalies)} 条差异，请继续处理",
            "feedback_json": feedback_json,
            "is_closed": False,
        }
    else:
        patch = {
            "processing_status": "verified_closed",
            "fix_status": "fixed",
            "latest_feedback": "重新对账验证通过，差异已消除",
            "feedback_json": feedback_json,
            "is_closed": True,
        }

    update_result = await execution_run_exception_update(auth_token, exception_id, patch)
    if bool(update_result.get("success")):
        ctx["rerun_exception_verification"] = _safe_dict(update_result.get("exception"))
    else:
        ctx["rerun_exception_verification_error"] = str(update_result.get("error") or "更新重新对账验证状态失败")
    return {"recon_ctx": ctx}
