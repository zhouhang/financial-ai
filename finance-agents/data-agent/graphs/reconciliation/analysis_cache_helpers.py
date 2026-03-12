"""对账分析缓存与中断闸门辅助函数。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def _normalize_uploaded_files(uploaded_files: list[Any]) -> list[dict[str, str]]:
    """标准化 uploaded_files（兼容 str 和 dict 两种结构）。"""
    normalized: list[dict[str, str]] = []
    for item in uploaded_files or []:
        if isinstance(item, dict):
            file_path = str(item.get("file_path") or item.get("path") or "").strip()
            original_filename = str(item.get("original_filename") or item.get("name") or "").strip()
        else:
            file_path = str(item).strip()
            original_filename = ""
        if file_path:
            normalized.append({
                "file_path": file_path,
                "original_filename": original_filename,
            })

    # 排序后再 hash，避免上传顺序影响 analysis_key
    normalized.sort(key=lambda x: (x.get("original_filename", ""), x.get("file_path", "")))
    return normalized


def _get_reconciliation_ctx(state: dict[str, Any]) -> dict[str, Any]:
    ctx = state.get("reconciliation_ctx") or {}
    if not isinstance(ctx, dict):
        return {}
    return dict(ctx)


def build_reconciliation_ctx_update(state: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """基于当前 state 构建 reconciliation_ctx 增量更新。"""
    ctx = _get_reconciliation_ctx(state)
    ctx.update(changes)
    return {"reconciliation_ctx": ctx}


def compute_analysis_key(uploaded_files: list[Any], rule_ctx: dict[str, Any]) -> str:
    """根据文件与规则上下文生成稳定的 analysis_key。"""
    payload = {
        "uploaded_files": _normalize_uploaded_files(uploaded_files),
        "rule_ctx": {
            "intent": rule_ctx.get("intent", ""),
            "selected_rule_id": rule_ctx.get("selected_rule_id", ""),
            "selected_rule_name": rule_ctx.get("selected_rule_name", ""),
            # field_roles 快照（若存在）用于保证规则上下文变化会触发重算
            "business_field_roles": rule_ctx.get("business_field_roles", {}),
            "finance_field_roles": rule_ctx.get("finance_field_roles", {}),
        },
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_analysis_cache_hit(state: dict[str, Any], key: str) -> bool:
    """判断当前 key 是否命中对账分析缓存。"""
    ctx = _get_reconciliation_ctx(state)

    cache = ctx.get("analysis_cache")
    if not isinstance(cache, dict):
        cache = state.get("analysis_cache") if isinstance(state.get("analysis_cache"), dict) else {}

    cached_key = ctx.get("analysis_key") or state.get("analysis_key")
    if cached_key != key:
        return False

    analyses = cache.get("file_analyses", [])
    return isinstance(analyses, list) and len(analyses) > 0


def write_analysis_cache(
    state: dict[str, Any],
    key: str,
    file_analyses: list[dict[str, Any]],
    suggested_mappings: dict[str, Any],
) -> dict[str, Any]:
    """写入对账分析缓存，并同步兼容字段。"""
    cache_payload = {
        "analysis_key": key,
        "file_analyses": file_analyses,
        "suggested_mappings": suggested_mappings,
        "updated_at": datetime.utcnow().isoformat(),
    }

    update: dict[str, Any] = {
        "analysis_key": key,
        "analysis_cache": cache_payload,
    }
    update.update(
        build_reconciliation_ctx_update(
            state,
            analysis_key=key,
            analysis_cache=cache_payload,
        )
    )
    return update


def check_pending_interrupt(
    state: dict[str, Any],
    node_name: str,
    analysis_key: str,
    run_id: str,
) -> bool:
    """检查是否存在当前节点未消费的中断标记。"""
    ctx = _get_reconciliation_ctx(state)
    pending = ctx.get("pending_interrupt")
    if not isinstance(pending, dict):
        pending = state.get("pending_interrupt") if isinstance(state.get("pending_interrupt"), dict) else {}

    if not pending:
        return False

    return (
        pending.get("status") == "waiting"
        and pending.get("node") == node_name
        and pending.get("analysis_key") == analysis_key
        and pending.get("run_id") == run_id
    )


def set_pending_interrupt(
    state: dict[str, Any],
    node_name: str,
    analysis_key: str,
    run_id: str,
) -> dict[str, Any]:
    """设置 pending_interrupt。"""
    pending = {
        "node": node_name,
        "analysis_key": analysis_key,
        "run_id": run_id,
        "status": "waiting",
        "created_at": datetime.utcnow().isoformat(),
    }
    update: dict[str, Any] = {"pending_interrupt": pending}
    update.update(build_reconciliation_ctx_update(state, pending_interrupt=pending))
    return update


def clear_pending_interrupt(state: dict[str, Any], node_name: str | None = None) -> dict[str, Any]:
    """清理 pending_interrupt（可选按节点名清理）。"""
    ctx = _get_reconciliation_ctx(state)
    pending = ctx.get("pending_interrupt")
    if not isinstance(pending, dict):
        pending = state.get("pending_interrupt") if isinstance(state.get("pending_interrupt"), dict) else {}

    if node_name and pending.get("node") and pending.get("node") != node_name:
        return {}

    resolved = {
        "node": pending.get("node", node_name or ""),
        "analysis_key": pending.get("analysis_key", ""),
        "run_id": pending.get("run_id", ""),
        "status": "resolved",
        "resolved_at": datetime.utcnow().isoformat(),
    }

    update: dict[str, Any] = {"pending_interrupt": resolved}
    update.update(build_reconciliation_ctx_update(state, pending_interrupt=resolved))
    return update
