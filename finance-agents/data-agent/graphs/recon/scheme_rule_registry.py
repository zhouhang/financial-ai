"""Helpers for persisting scheme-generated proc/recon rules into rule_detail."""

from __future__ import annotations

import re
import uuid
from typing import Any

from tools.mcp_client import list_user_tasks, save_rule

_VALID_ENTRY_MODES = {"upload", "dataset"}
_TASK_NAME_HINTS = {
    "proc": {"数据整理"},
    "recon": {"数据对账"},
}
_TASK_CODE_HINTS = {
    "proc": {"verif_recog"},
    "recon": {"audio_recon"},
}


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_rule_type(rule_type: str) -> str:
    normalized = str(rule_type or "").strip().lower()
    if normalized not in {"proc", "recon"}:
        raise ValueError(f"不支持的规则类型: {rule_type}")
    return normalized


def _normalize_entry_modes(
    supported_entry_modes: list[str] | tuple[str, ...] | None,
    *,
    default_mode: str,
) -> list[str]:
    modes: list[str] = []
    for item in list(supported_entry_modes or []):
        normalized = str(item or "").strip().lower()
        if normalized in _VALID_ENTRY_MODES and normalized not in modes:
            modes.append(normalized)
    if not modes:
        modes.append(default_mode)
    return modes


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return normalized[:32]


def _build_generated_rule_code(scheme_name: str, rule_type: str) -> str:
    slug = _slugify(scheme_name)
    suffix = uuid.uuid4().hex[:8]
    prefix = f"dataset_{rule_type}"
    return f"{prefix}_{slug}_{suffix}" if slug else f"{prefix}_{suffix}"


def _build_default_rule_name(scheme_name: str, rule_type: str) -> str:
    base_name = str(scheme_name or "").strip() or "未命名对账方案"
    return f"{base_name} {'整理规则' if rule_type == 'proc' else '对账逻辑'}"


async def resolve_task_id_for_rule_type(auth_token: str, rule_type: str) -> int | None:
    normalized_rule_type = _normalize_rule_type(rule_type)
    result = await list_user_tasks(auth_token)
    if not bool(result.get("success")):
        return None

    tasks = result.get("tasks")
    if not isinstance(tasks, list):
        return None

    fallback_task_id: int | None = None
    for item in tasks:
        if not isinstance(item, dict):
            continue
        raw_task_id = item.get("id")
        try:
            task_id = int(raw_task_id)
        except (TypeError, ValueError):
            continue
        task_type = str(item.get("task_type") or "").strip().lower()
        if task_type == normalized_rule_type:
            return task_id
        task_name = str(item.get("task_name") or "").strip()
        task_code = str(item.get("task_code") or "").strip()
        if task_name in _TASK_NAME_HINTS[normalized_rule_type] or task_code in _TASK_CODE_HINTS[normalized_rule_type]:
            fallback_task_id = task_id
    return fallback_task_id


async def ensure_scheme_rule_saved(
    auth_token: str,
    *,
    scheme_name: str,
    rule_type: str,
    rule_json: dict[str, Any] | None,
    rule_code: str = "",
    preferred_name: str = "",
    remark: str = "",
    supported_entry_modes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    normalized_rule_type = _normalize_rule_type(rule_type)
    normalized_rule_code = str(rule_code or "").strip()
    normalized_rule_json = _safe_dict(rule_json)
    if normalized_rule_code:
        return {"rule_code": normalized_rule_code, "saved": False}
    if not normalized_rule_json:
        return {"rule_code": "", "saved": False}

    resolved_rule_code = _build_generated_rule_code(scheme_name, normalized_rule_type)
    resolved_name = str(preferred_name or "").strip() or _build_default_rule_name(
        scheme_name,
        normalized_rule_type,
    )
    resolved_task_id = await resolve_task_id_for_rule_type(auth_token, normalized_rule_type)
    result = await save_rule(
        auth_token,
        rule_code=resolved_rule_code,
        name=resolved_name,
        rule=normalized_rule_json,
        rule_type=normalized_rule_type,
        remark=str(remark or "").strip(),
        task_id=resolved_task_id,
        overwrite=False,
        supported_entry_modes=_normalize_entry_modes(
            supported_entry_modes,
            default_mode="dataset",
        ),
    )
    if not bool(result.get("success")):
        raise ValueError(str(result.get("error") or f"{normalized_rule_type} 规则保存失败"))
    saved = result.get("data") if isinstance(result.get("data"), dict) else {}
    return {
        "rule_code": str(saved.get("rule_code") or resolved_rule_code),
        "task_id": resolved_task_id,
        "saved": True,
        "data": saved,
    }
