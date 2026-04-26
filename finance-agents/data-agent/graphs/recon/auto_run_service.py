"""自动对账任务执行与异常催办服务。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from graphs.recon.auto_scheme_run import run_auto_scheme_run_graph
from graphs.recon.execution_service import (
    build_execution_request,
    build_recon_ctx_update_from_execution,
    build_recon_observation,
    run_recon_execution,
)
from graphs.recon.pipeline_service import execute_headless_recon_pipeline
from services.notifications import get_notification_adapter
from services.notifications.models import UnifiedTodoStatus
from services.notifications.repository import load_company_channel_config_by_id
from tools.mcp_client import (
    execution_run_exception_get,
    execution_run_exception_update,
    execution_run_get,
    execution_run_plan_get,
    execution_scheme_get,
    data_source_list_collection_records,
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
_RUN_SUCCESS_STATUSES = {"success", "partial_success", "skipped"}

_ANOMALY_TYPE_LABELS: dict[str, str] = {
    "source_only": "仅左侧数据存在（右侧缺失）",
    "target_only": "仅右侧数据存在（左侧缺失）",
    "matched_with_diff": "金额或字段存在差异",
    "value_mismatch": "金额或字段存在差异",
    "unknown": "未知异常",
}


def _label_anomaly_type(anomaly_type: str, *, left_name: str = "", right_name: str = "") -> str:
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
    """Build a finance-friendly one-line summary for an anomaly item."""
    src = str(left_name or "源数据").strip()
    tgt = str(right_name or "目标数据").strip()
    atype = str(anomaly_type or "").strip()
    _type_labels: dict[str, str] = {
        "source_only": f"仅 {src} 存在（{tgt} 缺失）",
        "target_only": f"仅 {tgt} 存在（{src} 缺失）",
        "matched_with_diff": f"{src} 与 {tgt} 金额差异",
        "value_mismatch": f"{src} 与 {tgt} 金额差异",
        "unknown": "未知异常",
    }
    label = _type_labels.get(atype, _label_anomaly_type(anomaly_type))

    raw_record = _safe_dict(item.get("raw_record"))

    def _raw_val(field: str, side: str = "left") -> str:
        """Extract value from raw_record with table-prefix fallback."""
        prefix = "left_recon_ready." if side == "left" else "right_recon_ready."
        v = raw_record.get(prefix + field)
        if v is None:
            v = raw_record.get(field)
        return str(v).strip() if v is not None and str(v).strip() not in {"None", "null", ""} else ""

    # 主键定位（join_key source_value/target_value 可能为 null，从 raw_record 兜底）
    join_key = [k for k in list(item.get("join_key") or []) if isinstance(k, dict)]
    key_parts: list[str] = []
    for k in join_key[:2]:
        field = str(k.get("field") or k.get("source_field") or k.get("target_field") or "")
        value = k.get("target_value" if atype == "target_only" else "source_value") or k.get("value")
        val_str = str(value).strip() if value is not None and str(value).strip() not in {"None", "null", ""} else ""
        if not val_str and field:
            val_str = _raw_val(field, "right" if atype == "target_only" else "left")
        if field and val_str:
            key_parts.append(f"{field}={val_str}")

    # 差异明细（source_value/target_value 可能为 null，从 raw_record 兜底）
    compare_values = [c for c in list(item.get("compare_values") or []) if isinstance(c, dict)]
    diff_parts: list[str] = []
    if atype in {"matched_with_diff", "value_mismatch"} and compare_values:
        for cv in compare_values[:3]:
            name = str(cv.get("name") or cv.get("source_field") or "").strip()
            src_field = str(cv.get("source_field") or "").strip()
            tgt_field = str(cv.get("target_field") or src_field).strip()
            left_val = cv.get("source_value")
            right_val = cv.get("target_value")
            diff_val = cv.get("diff_value")
            if left_val is None and src_field:
                left_val = _raw_val(src_field, "left") or None
            if right_val is None and tgt_field:
                right_val = _raw_val(tgt_field, "right") or None
            if not name or left_val is None or right_val is None:
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


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _parse_biz_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("biz_date 不能为空")
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def _normalize_status_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_run_plan_execution_success(ctx: dict[str, Any], run_record: dict[str, Any]) -> bool:
    run_status = _normalize_status_text(run_record.get("execution_status"))
    if run_status:
        return run_status in _RUN_SUCCESS_STATUSES

    exec_status = _normalize_status_text(ctx.get("exec_status"))
    failed_reason = str(ctx.get("failed_reason") or ctx.get("exec_error") or "").strip()
    return exec_status in _RUN_SUCCESS_STATUSES and not failed_reason


def _classify_execution_failure(failed_stage: str) -> str:
    normalized = str(failed_stage or "").strip().lower()
    if normalized in {"collect", "validate_dataset"}:
        return "collect_failed"
    if normalized in {"config"}:
        return "config_failed"
    if normalized:
        return "recon_failed"
    return "unknown_failed"


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
        "dataset_source_type": str(item.get("dataset_source_type") or "collection_records").strip() or "collection_records",
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


def _build_source_collection_summary(bindings: list[dict[str, Any]], collection_results: list[dict[str, Any]], missing: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "bindings": bindings,
        "collections": collection_results,
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
    biz_date_filter = _safe_dict(resolved_query.pop("biz_date_filter", None))
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


def _build_recon_inputs_from_collections(collection_results: list[dict[str, Any]], *, biz_date: str) -> list[dict[str, Any]]:
    recon_inputs: list[dict[str, Any]] = []
    for item in collection_results:
        collection_records = _safe_dict(item.get("collection_records"))
        source_id = str(item.get("data_source_id") or "").strip()
        table_name = str(item.get("table_name") or "").strip()
        resource_key = str(item.get("resource_key") or "default").strip() or "default"
        dataset_source_type = str(item.get("dataset_source_type") or "collection_records").strip() or "collection_records"
        if not source_id or not table_name:
            continue
        query = {"resource_key": resource_key}
        dataset_id = str(collection_records.get("dataset_id") or item.get("dataset_id") or "").strip()
        if dataset_id:
            query["dataset_id"] = dataset_id
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
                "summary": str(item.get("summary") or "") or _build_anomaly_summary(str(item.get("anomaly_type") or "unknown"), item),
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


async def prepare_execution_run_rerun(
    *,
    auth_token: str,
    original_run_id: str,
    exception_id: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Validate and build the minimal context required to rerun recon validation.

    This does not claim a new run was created. The caller may enqueue
    execute_run_plan_run only when this returns status=ready.
    """
    source_run_id = str(original_run_id or "").strip()
    if not source_run_id:
        return {"success": False, "status": "todo", "error": "original_run_id 不能为空"}

    run_result = await execution_run_get(auth_token, source_run_id)
    if not run_result.get("success"):
        return {
            "success": False,
            "status": "not_found",
            "error": str(run_result.get("error") or "原运行记录不存在"),
        }

    source_run = _safe_dict(run_result.get("run"))
    run_context = _safe_dict(source_run.get("run_context_json"))
    biz_date = str(
        source_run.get("biz_date")
        or run_context.get("biz_date")
        or _safe_dict(source_run.get("source_snapshot_json")).get("biz_date")
        or ""
    ).strip()
    run_plan_code = str(source_run.get("plan_code") or run_context.get("run_plan_code") or "").strip()

    exception: dict[str, Any] = {}
    exception_ref = str(exception_id or "").strip()
    if exception_ref:
        exception_result = await execution_run_exception_get(auth_token, exception_ref)
        if not exception_result.get("success"):
            return {
                "success": False,
                "status": "not_found",
                "error": str(exception_result.get("error") or "异常处理项不存在"),
            }
        exception = _safe_dict(exception_result.get("exception"))
        exception_run_id = str(exception.get("run_id") or exception.get("execution_run_id") or "").strip()
        if exception_run_id and exception_run_id != source_run_id:
            return {
                "success": False,
                "status": "invalid_request",
                "error": "exception_id 不属于 original_run_id，无法重新对账验证",
            }

    if not run_plan_code:
        return {
            "success": False,
            "status": "todo",
            "error": "原运行缺少 plan_code，暂不能创建重新对账验证流程",
            "todo": "补齐 execution_run 到 execution_run_plan 的反查能力后再启用",
            "source_run": source_run,
        }
    if not biz_date:
        return {
            "success": False,
            "status": "todo",
            "error": "原运行缺少 biz_date，暂不能创建重新对账验证流程",
            "todo": "补齐运行上下文中的业务日期恢复逻辑后再启用",
            "source_run": source_run,
        }

    rerun_context = dict(run_context)
    rerun_context.pop("run_id", None)
    rerun_context.update(
        {
            "rerun_from_run_id": source_run_id,
            "rerun_exception_id": exception_ref,
            "rerun_reason": str(reason or "重新对账验证").strip() or "重新对账验证",
        }
    )
    return {
        "success": True,
        "status": "ready",
        "source_run_id": source_run_id,
        "exception_id": exception_ref,
        "run_plan_code": run_plan_code,
        "biz_date": biz_date,
        "run_context": rerun_context,
        "source_run": source_run,
        "exception": exception,
    }


_COMMON_FIELD_LABELS: dict[str, str] = {
    "biz_key": "业务单号", "biz_date": "业务日期", "amount": "金额",
    "fee": "手续费", "refund_amount": "退款金额", "order_no": "订单号",
    "trade_no": "交易号", "trans_no": "交易流水号",
    "merchant_order_no": "商户订单号", "source_name": "来源名称",
}


def _extract_todo_key_hint(
    exception: dict[str, Any],
    field_labels: dict[str, str] | None = None,
) -> str:
    """Extract a short key identifier from the exception for use in the todo title."""
    fl = {**_COMMON_FIELD_LABELS, **(field_labels or {})}
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
        if parts:
            return "、".join(parts)
    # Fallback: extract from summary text (after first ：, before double-space)
    summary = str(exception.get("summary") or "")
    if "：" in summary:
        after_colon = summary.split("：", 1)[1].strip()
        key_part = after_colon.split("  ")[0].strip()
        if key_part and len(key_part) <= 60:
            return key_part
    return ""


def _compose_reminder_text(
    task: dict[str, Any],
    run: dict[str, Any],
    exception: dict[str, Any],
    *,
    left_name: str = "",
    right_name: str = "",
) -> tuple[str, str, str]:
    """Return (todo_title, bot_message_title, bot_message_content)."""
    task_name = str(task.get("task_name") or task.get("name") or task.get("plan_name") or "对账异常催办")
    run_ctx = run.get("run_context_json") if isinstance(run.get("run_context_json"), dict) else {}
    biz_date = str(run.get("biz_date") or run_ctx.get("biz_date") or "")
    anomaly_label = _label_anomaly_type(exception.get("anomaly_type") or "未知", left_name=left_name, right_name=right_name)
    summary = str(exception.get("summary") or "详见对账结果")

    key_hint = _extract_todo_key_hint(exception)
    if key_hint:
        todo_title = f"【对账异常】{anomaly_label} | {key_hint}"
    else:
        todo_title = f"【对账异常】{anomaly_label}"
    if biz_date:
        todo_title += f" | {biz_date}"

    bot_title = f"{task_name} 对账异常催办"
    lines = [f"任务：{task_name}"]
    if biz_date:
        lines.append(f"业务日期：{biz_date}")
    lines.append(f"异常类型：{anomaly_label}")
    lines.append(f"异常详情：{summary}")
    lines.append("请处理完成后在钉钉待办中标记完成，并同步给财务复核。")
    return todo_title, bot_title, "\n\n".join(lines)


async def execute_run_plan_run(
    *,
    auth_token: str,
    run_plan_code: str,
    biz_date: str = "",
    trigger_mode: str = "manual",
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one run-plan by auto scheme graph (execution_* first)."""
    output = await run_auto_scheme_run_graph(
        auth_token=auth_token,
        run_plan_code=run_plan_code,
        biz_date=biz_date,
        trigger_mode=trigger_mode,
        run_context=run_context,
    )
    ctx = _safe_dict(output.get("recon_ctx"))

    run_record = _safe_dict(ctx.get("execution_run_record"))
    failed_reason = str(
        ctx.get("failed_reason")
        or run_record.get("failed_reason")
        or ctx.get("exec_error")
        or ""
    ).strip()
    failed_stage = str(ctx.get("failed_stage") or run_record.get("failed_stage") or "").strip()
    success = _is_run_plan_execution_success(ctx, run_record)
    return {
        "success": success,
        "error": "" if success else (failed_reason or str(ctx.get("exec_error") or "执行失败")),
        "failed_stage": failed_stage,
        "failure_type": "" if success else _classify_execution_failure(failed_stage),
        "run_plan_code": run_plan_code,
        "scheme_code": str(ctx.get("scheme_code") or ""),
        "biz_date": str(ctx.get("biz_date") or biz_date),
        "run": run_record,
        "subtasks_json": _safe_list(ctx.get("subtasks_json")),
        "execution_result": _safe_dict(ctx.get("execution_result")),
        "recon_observation": _safe_dict(ctx.get("recon_observation")),
        "recon_ctx": ctx,
    }


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

    source_collections: list[dict[str, Any]] = []
    missing_bindings: list[dict[str, Any]] = []
    for binding in bindings:
        collection_result = await data_source_list_collection_records(
            auth_token,
            binding["data_source_id"],
            resource_key=binding["resource_key"],
            biz_date=normalized_biz_date,
            limit=1,
        )
        record_count = int(collection_result.get("record_count") or collection_result.get("count") or 0)
        records = _safe_list(collection_result.get("records") or collection_result.get("rows"))
        if collection_result.get("success") and (record_count > 0 or records):
            source_collections.append(
                {
                    **binding,
                    "dataset_source_type": "collection_records",
                    "collection_records": {
                        "dataset_id": str(collection_result.get("dataset_id") or binding.get("dataset_id") or ""),
                        "resource_key": str(collection_result.get("resource_key") or binding["resource_key"]),
                        "record_count": record_count or len(records),
                    },
                }
            )
        else:
            missing_bindings.append(
                {
                    **binding,
                    "error": str(collection_result.get("error") or collection_result.get("message") or "暂无采集记录，请先采集数据"),
                }
            )

    source_collection_json = _build_source_collection_summary(bindings, source_collections, missing_bindings)
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
            "source_snapshot_json": source_collection_json,
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
        message = "存在未就绪的数据源采集记录，请先采集数据后重试"
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
    recon_inputs = _build_recon_inputs_from_collections(source_collections, biz_date=normalized_biz_date)
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

    # For plan-based runs: fetch execution_run for biz_date and scheme_code
    exec_run: dict[str, Any] = {}
    left_name = right_name = ""
    exec_run_id = str(exception.get("run_id") or "")
    if exec_run_id and not run:
        exec_run_result = await execution_run_get(auth_token, exec_run_id)
        exec_run = _safe_dict(exec_run_result.get("run"))
    if not run:
        run = exec_run
    # Resolve dataset names from scheme_meta_json (most reliable source)
    scheme_code = str(exec_run.get("scheme_code") or run.get("scheme_code") or exception.get("scheme_code") or "")
    if scheme_code:
        scheme_result = await execution_scheme_get(auth_token, scheme_code=scheme_code)
        scheme = _safe_dict(scheme_result.get("scheme"))
        meta = _safe_dict(scheme.get("scheme_meta_json") or scheme.get("scheme_meta") or scheme.get("meta"))
        def _first_name(sources: list) -> str:
            for src in sources:
                if not isinstance(src, dict):
                    continue
                for key in ("dataset_name", "business_name", "display_name", "name"):
                    val = str(src.get(key) or "").strip()
                    if val:
                        return val
            return ""
        left_name = _first_name(_safe_list(meta.get("left_sources")))
        right_name = _first_name(_safe_list(meta.get("right_sources")))

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

    todo_title, reminder_title, reminder_content = _compose_reminder_text(task, run, exception, left_name=left_name, right_name=right_name)
    reminder = adapter.send_reminder(
        title=title or reminder_title,
        content=content or reminder_content,
        todo_title=todo_title if not title else "",
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


async def sync_execution_run_exception_reminder(
    *,
    auth_token: str,
    exception_id: str,
    provider: str = "",
    channel_code: str = "",
    max_polls: int = 1,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    exception_result = await execution_run_exception_get(auth_token, exception_id)
    if not exception_result.get("success"):
        return {"success": False, "error": exception_result.get("error", "异常处理项不存在")}

    exception = _safe_dict(exception_result.get("exception"))
    feedback_json = _safe_dict(exception.get("feedback_json"))
    todo_id = str(feedback_json.get("todo_id") or "").strip()
    if not todo_id:
        return {"success": False, "error": "异常尚未创建待办，无法同步状态", "exception": exception}

    try:
        adapter = None
        channel_config_id = str(feedback_json.get("channel_config_id") or "").strip()
        if channel_config_id:
            channel_config = load_company_channel_config_by_id(channel_id=channel_config_id)
            if channel_config is not None:
                adapter = get_notification_adapter(
                    provider=str(getattr(channel_config, "provider", "") or provider or ""),
                    channel_config=channel_config,
                )

        if adapter is None:
            adapter = get_notification_adapter(
                provider=provider or str(feedback_json.get("provider") or ""),
                company_id=str(exception.get("company_id") or ""),
                channel_code=channel_code or None,
            )

        sync_result = adapter.sync_todo_status(
            todo_id=todo_id,
            max_polls=max(1, max_polls),
            poll_interval_seconds=max(0.5, poll_interval_seconds),
        )
    except Exception as exc:
        message = str(exc) or "同步待办状态失败"
        logger.error("[recon][execution_run_exception] 同步待办状态失败: %s", exc)
        await execution_run_exception_update(
            auth_token,
            exception_id,
            {
                "latest_feedback": message,
            },
        )
        return {"success": False, "error": message, "exception": exception}

    if not sync_result.success:
        await execution_run_exception_update(
            auth_token,
            exception_id,
            {
                "latest_feedback": sync_result.message,
            },
        )
        return {"success": False, "error": sync_result.message, "exception": exception}

    status = sync_result.status
    patch: dict[str, Any] = {
        "feedback_json": _merge_feedback(
            feedback_json,
            {
                "todo_status": status.value,
                "todo_synced_at": datetime.now().isoformat(),
            },
        ),
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

    update_result = await execution_run_exception_update(auth_token, exception_id, patch)
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


async def send_execution_run_exception_reminder(
    *,
    auth_token: str,
    exception_id: str,
    provider: str = "",
    channel_code: str = "",
    due_time: str = "",
    title: str = "",
    content: str = "",
) -> dict[str, Any]:
    """手动对 execution_run_exceptions 单条异常补发钉钉催办通知。

    流程：
    1. 取异常记录，拿到 run_id / owner 信息
    2. 取关联 execution_run，拿到 plan_code / scheme_code / biz_date
    3. 取 execution_run_plan，拿到 channel_config_id / owner_mapping_json（作为兜底）
    4. 取 execution_scheme，拿到 scheme_name（用于通知文案）
    5. 解析责任人，发送钉钉催办 + 创建待办
    6. 更新 reminder_status = 'sent'
    """
    exception_result = await execution_run_exception_get(auth_token, exception_id)
    if not exception_result.get("success"):
        return {"success": False, "error": exception_result.get("error", "异常处理项不存在")}

    exception = _safe_dict(exception_result.get("exception"))

    # ── 1. 解析 owner（异常记录自身携带的优先）─────────────────────────────────
    owner_name = str(exception.get("owner_name") or "").strip()
    owner_identifier = str(exception.get("owner_identifier") or "").strip()
    feedback_json = _safe_dict(exception.get("feedback_json"))
    owner_contact_json = _safe_dict(exception.get("owner_contact_json"))

    # ── 2. 从关联 execution_run 补全上下文 ────────────────────────────────────
    run_id = str(exception.get("run_id") or "").strip()
    run: dict[str, Any] = {}
    plan_code = ""
    scheme_code = str(exception.get("scheme_code") or "").strip()
    biz_date = ""

    if run_id:
        run_result = await execution_run_get(auth_token, run_id)
        if run_result.get("success"):
            run = _safe_dict(run_result.get("run"))
            plan_code = str(run.get("plan_code") or "").strip()
            if not scheme_code:
                scheme_code = str(run.get("scheme_code") or "").strip()
            run_ctx = _safe_dict(run.get("run_context_json"))
            biz_date = str(run_ctx.get("biz_date") or run.get("biz_date") or "").strip()

    # ── 3. 从 execution_run_plan 补 channel_config_id / owner ─────────────────
    run_plan: dict[str, Any] = {}
    channel_config_id = str(feedback_json.get("channel_config_id") or "").strip()

    if plan_code:
        plan_result = await execution_run_plan_get(auth_token, plan_code=plan_code)
        if plan_result.get("success"):
            run_plan = _safe_dict(plan_result.get("run_plan"))
            if not channel_config_id:
                channel_config_id = str(run_plan.get("channel_config_id") or "").strip()
            # 如果异常记录本身没有 owner，从 run_plan.owner_mapping_json.default_owner 补
            if not owner_name and not owner_identifier:
                owner_mapping = _safe_dict(run_plan.get("owner_mapping_json"))
                default_owner = _safe_dict(owner_mapping.get("default_owner"))
                owner_name = str(default_owner.get("name") or default_owner.get("display_name") or "").strip()
                owner_identifier = str(
                    default_owner.get("identifier") or default_owner.get("owner_identifier") or ""
                ).strip()

    if not owner_name and not owner_identifier:
        return {"success": False, "error": "异常未配置责任人，且运行计划未设置默认负责人，无法催办", "exception": exception}

    # ── 4. 取 scheme 名称用于文案 ─────────────────────────────────────────────
    scheme: dict[str, Any] = {}
    if scheme_code:
        scheme_result = await execution_scheme_get(auth_token, scheme_code=scheme_code)
        if scheme_result.get("success"):
            scheme = _safe_dict(scheme_result.get("scheme"))

    # ── 5. 构造通知适配器 ──────────────────────────────────────────────────────
    adapter = None
    if channel_config_id:
        channel_config = load_company_channel_config_by_id(channel_id=channel_config_id)
        if channel_config is not None:
            adapter = get_notification_adapter(
                provider=str(getattr(channel_config, "provider", "") or provider or ""),
                channel_config=channel_config,
            )

    if adapter is None:
        adapter = get_notification_adapter(
            provider=provider or "",
            company_id=str(exception.get("company_id") or ""),
            channel_code=channel_code or None,
        )

    # ── 6. 解析责任人 ─────────────────────────────────────────────────────────
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
        await execution_run_exception_update(
            auth_token,
            exception_id,
            {
                "reminder_status": "owner_unresolved",
                "latest_feedback": "责任人未能解析为可触达用户",
            },
        )
        return {"success": False, "error": "责任人未能解析为可触达用户", "exception": exception}

    # ── 7. 组装通知文案 ───────────────────────────────────────────────────────
    plan_name = str(
        run_plan.get("plan_name")
        or run_plan.get("name")
        or scheme.get("scheme_name")
        or scheme.get("name")
        or "对账异常催办"
    ).strip()
    scheme_name = str(scheme.get("scheme_name") or scheme.get("name") or "").strip()

    # Extract dataset display names for finance-friendly labels
    scheme_meta = _safe_dict(scheme.get("scheme_meta_json") or scheme.get("scheme_meta") or scheme.get("meta"))
    def _first_name_local(sources: list) -> str:
        for src in sources:
            if not isinstance(src, dict):
                continue
            for key in ("dataset_name", "business_name", "display_name", "name"):
                val = str(src.get(key) or "").strip()
                if val:
                    return val
        return ""
    left_name = _first_name_local(_safe_list(scheme_meta.get("left_sources")))
    right_name = _first_name_local(_safe_list(scheme_meta.get("right_sources")))
    anomaly_type = str(exception.get("anomaly_type") or exception.get("exception_type") or "未知")
    anomaly_label = _label_anomaly_type(anomaly_type, left_name=left_name, right_name=right_name)
    summary = str(exception.get("summary") or "详见对账结果")

    key_hint = _extract_todo_key_hint(exception, field_labels=dict(_COMMON_FIELD_LABELS))
    todo_title = f"【对账异常】{anomaly_label} | {key_hint}" if key_hint else f"【对账异常】{anomaly_label}"
    if biz_date:
        todo_title += f" | {biz_date}"

    if not title:
        title = f"{plan_name} 对账异常催办"
    if not content:
        lines = [
            f"任务：{plan_name}",
            f"业务日期：{biz_date}" if biz_date else "",
            f"对账方案：{scheme_name}" if scheme_name else "",
            f"异常类型：{anomaly_label}",
            f"异常详情：{summary}",
            "请尽快处理完成，并在钉钉待办中标记完成后同步给财务复核。",
        ]
        content = "\n\n".join(line for line in lines if line)

    # ── 8. 发送催办 ───────────────────────────────────────────────────────────
    reminder = adapter.send_reminder(
        title=title,
        content=content,
        todo_title=todo_title,
        assignee_user_id=resolved.user_id,
        due_time=due_time,
        source_id=exception_id,
    )

    if not reminder.success:
        await execution_run_exception_update(
            auth_token,
            exception_id,
            {
                "owner_name": resolved.display_name or owner_name,
                "owner_identifier": resolved.user_id,
                "owner_contact_json": {
                    "provider": adapter.provider,
                    "display_name": resolved.display_name,
                    "mobile": resolved.mobile,
                },
                "reminder_status": "send_failed",
                "latest_feedback": reminder.message,
            },
        )
        return {"success": False, "error": reminder.message, "exception": exception}

    # ── 9. 更新异常记录 ────────────────────────────────────────────────────────
    next_feedback = _merge_feedback(
        feedback_json,
        {
            "provider": adapter.provider,
            "channel_config_id": channel_config_id,
            "todo_id": reminder.todo_result.todo.todo_id if reminder.todo_result and reminder.todo_result.todo else "",
            "message_id": reminder.bot_result.message_id if reminder.bot_result else "",
            "last_reminded_at": datetime.now().isoformat(),
        },
    )
    update_result = await execution_run_exception_update(
        auth_token,
        exception_id,
        {
            "owner_name": resolved.display_name or owner_name,
            "owner_identifier": resolved.user_id,
            "owner_contact_json": {
                "provider": adapter.provider,
                "display_name": resolved.display_name,
                "mobile": resolved.mobile,
            },
            "reminder_status": "sent",
            "latest_feedback": "已手动发送催办消息并创建待办",
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
