"""Scheme design service for button-driven scheme configuration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import jwt

from models import (
    SchemeDesignMessage,
    SchemeDesignRuleStepState,
    SchemeDesignSession,
    SchemeDesignStatus,
    SchemeDesignTargetState,
)
from tools.mcp_client import (
    data_source_list_published_snapshot_rows,
    execution_proc_draft_trial,
    execution_proc_rule_compatibility_check,
    execution_recon_draft_trial,
    execution_recon_rule_compatibility_check,
    execution_scheme_create,
    get_file_validation_rule,
)
from graphs.recon.scheme_rule_registry import ensure_scheme_rule_saved

from .executor import (
    DeepAgentSchemeDesignExecutor,
    SingleShotSchemeDesignExecutor,
    SchemeDesignExecutor,
)
from .rule_text_renderer import (
    render_proc_draft_text,
    render_proc_rule_summary,
    render_recon_draft_text,
    render_recon_rule_summary,
)
from .semantic_utils import ensure_dataset_semantic_context, infer_raw_field_names
from .session_store import InMemorySchemeDesignSessionStore

JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
JWT_ALGORITHM = "HS256"
logger = logging.getLogger(__name__)

_GENERATION_LABELS = {
    "proc": "整理配置生成器",
    "recon": "对账逻辑生成器",
}

_READY_FIELD_LABELS = {
    "biz_key": "业务主键",
    "amount": "金额",
    "biz_date": "业务日期",
    "source_name": "来源标识",
}


@dataclass(slots=True)
class StartSessionInput:
    scheme_name: str = ""
    biz_goal: str = ""
    source_description: str = ""
    sample_files: list[str] | None = None
    sample_datasets: list[dict[str, Any]] | None = None
    initial_message: str = ""
    run_trial: bool = False


@dataclass(slots=True)
class TargetStepInput:
    left_datasets: list[dict[str, Any]] | None = None
    right_datasets: list[dict[str, Any]] | None = None
    left_description: str = ""
    right_description: str = ""


@dataclass(slots=True)
class RuleGenerateInput:
    instruction_text: str = ""


@dataclass(slots=True)
class UseExistingRuleInput:
    rule_code: str = ""
    rule_json: dict[str, Any] | None = None


@dataclass(slots=True)
class ConfirmSessionInput:
    scheme_name: str = ""
    file_rule_code: str = ""
    proc_rule_code: str = ""
    recon_rule_code: str = ""
    confirmation_note: str = ""


@dataclass(slots=True)
class ProcTrialInput:
    proc_rule_json: dict[str, Any]
    sample_datasets: list[dict[str, Any]] | None = None
    uploaded_files: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class ReconTrialInput:
    recon_rule_json: dict[str, Any]
    sample_datasets: list[dict[str, Any]] | None = None
    validated_inputs: list[dict[str, Any]] | None = None


def _decode_user(auth_token: str) -> dict[str, Any] | None:
    token = str(auth_token or "").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
    return {
        "user_id": str(payload.get("sub") or "").strip(),
        "username": payload.get("username"),
        "company_id": payload.get("company_id"),
    }


def _compose_source_description(left_description: str, right_description: str) -> str:
    return "\n".join(
        [
            f"左侧数据描述：{left_description.strip() or '--'}",
            f"右侧数据描述：{right_description.strip() or '--'}",
        ]
    )


def _infer_side(value: str) -> str:
    text = (value or "").strip().lower()
    if text.startswith("right"):
        return "right"
    return "left"


def _infer_schema_summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            field_name = str(key or "").strip()
            if not field_name or field_name in seen:
                continue
            if isinstance(value, bool):
                data_type = "boolean"
            elif isinstance(value, int):
                data_type = "integer"
            elif isinstance(value, float):
                data_type = "number"
            elif isinstance(value, str) and value[:10].count("-") == 2:
                data_type = "date"
            else:
                data_type = "string"
            columns.append({"name": field_name, "type": data_type})
            seen.add(field_name)
    return {"columns": columns}


def _schema_summary_to_field_map(schema_summary: Any) -> dict[str, str]:
    if not isinstance(schema_summary, dict):
        return {}
    columns = schema_summary.get("columns")
    if isinstance(columns, list):
        result: dict[str, str] = {}
        for column in columns:
            if not isinstance(column, dict):
                continue
            field_name = str(column.get("name") or column.get("column_name") or "").strip()
            field_type = str(column.get("type") or column.get("data_type") or "string").strip() or "string"
            if field_name:
                result[field_name] = field_type
        return result
    return {
        str(key).strip(): str(value or "string").strip() or "string"
        for key, value in schema_summary.items()
        if str(key).strip() and str(key).strip() != "columns"
    }


def _merge_schema_summary(existing: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    inferred = _infer_schema_summary_from_rows(rows)
    inferred_map = _schema_summary_to_field_map(inferred)
    existing_map = _schema_summary_to_field_map(existing)
    merged_map = dict(inferred_map)
    merged_map.update(existing_map)
    if not merged_map:
        return inferred
    prefer_columns = isinstance(existing, dict) and isinstance(existing.get("columns"), list)
    if prefer_columns or not existing_map:
        return {
            "columns": [
                {"name": field_name, "type": field_type}
                for field_name, field_type in merged_map.items()
            ]
        }
    return merged_map


def _resolve_dataset_table_name(dataset: dict[str, Any]) -> str:
    return str(
        dataset.get("table_name")
        or dataset.get("resource_key")
        or dataset.get("dataset_code")
        or dataset.get("dataset_name")
        or dataset.get("source_id")
        or dataset.get("source_key")
        or ""
    ).strip()


def _resolve_dataset_source_id(dataset: dict[str, Any]) -> str:
    return str(
        dataset.get("source_id")
        or dataset.get("source_key")
        or dataset.get("data_source_id")
        or ""
    ).strip()


def _resolve_dataset_resource_key(dataset: dict[str, Any]) -> str:
    return str(
        dataset.get("resource_key")
        or dataset.get("table_name")
        or dataset.get("dataset_code")
        or dataset.get("dataset_name")
        or "default"
    ).strip()


def _has_dict_rows(value: Any) -> bool:
    return any(isinstance(row, dict) for row in list(value or []))


def _normalize_target_dataset(dataset: dict[str, Any], *, default_side: str = "") -> dict[str, Any]:
    resolved = ensure_dataset_semantic_context(dict(dataset or {}))
    side = _infer_side(str(resolved.get("side") or default_side))
    resolved["side"] = side
    table_name = _resolve_dataset_table_name(resolved)
    if table_name:
        resolved["table_name"] = table_name
    resource_key = _resolve_dataset_resource_key(resolved)
    if resource_key:
        resolved["resource_key"] = resource_key
    source_id = _resolve_dataset_source_id(resolved)
    if source_id:
        resolved["source_id"] = source_id
    return resolved


def _build_ready_field_label_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            field_name = str(key or "").strip()
            if not field_name:
                continue
            labels[field_name] = _READY_FIELD_LABELS.get(field_name, field_name)
    return labels


def _target_dataset_identity(dataset: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _infer_side(str(dataset.get("side") or "")),
        _resolve_dataset_source_id(dataset),
        _resolve_dataset_resource_key(dataset),
        _resolve_dataset_table_name(dataset),
    )


def _normalize_existing_rule_json(raw: dict[str, Any]) -> dict[str, Any]:
    rule_json = raw.get("rule")
    if isinstance(rule_json, dict):
        return rule_json
    return raw if isinstance(raw, dict) else {}


def _force_recon_table_names(rule_json: dict[str, Any]) -> dict[str, Any]:
    """Patch every rule item's source/target file identification to use
    the canonical left_recon_ready / right_recon_ready table names so that
    an existing rule from another scheme connects to the current proc output."""
    import copy
    patched = copy.deepcopy(rule_json)
    for rule_item in list(patched.get("rules") or []):
        if not isinstance(rule_item, dict):
            continue
        for file_key, table_name in (("source_file", "left_recon_ready"), ("target_file", "right_recon_ready")):
            file_cfg = rule_item.get(file_key)
            if not isinstance(file_cfg, dict):
                file_cfg = {}
                rule_item[file_key] = file_cfg
            ident = file_cfg.get("identification")
            if not isinstance(ident, dict):
                ident = {}
                file_cfg["identification"] = ident
            ident["match_by"] = "table_name"
            ident["match_value"] = table_name
    return patched


def _summarize_proc_rule(rule_json: dict[str, Any]) -> str:
    return render_proc_rule_summary(rule_json)


def _summarize_recon_rule(rule_json: dict[str, Any]) -> str:
    return render_recon_rule_summary(rule_json)


def _collect_display_maps(
    datasets: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    field_label_map: dict[str, str] = {}
    table_label_map: dict[str, str] = {}
    for item in datasets:
        if not isinstance(item, dict):
            continue
        normalized = ensure_dataset_semantic_context(dict(item))
        table_name = str(normalized.get("table_name") or "").strip()
        business_name = str(normalized.get("business_name") or "").strip()
        if table_name and business_name:
            table_label_map[table_name] = business_name
        raw_map = normalized.get("field_label_map") if isinstance(normalized.get("field_label_map"), dict) else {}
        for raw_name, display_name in raw_map.items():
            raw = str(raw_name or "").strip()
            if not raw:
                continue
            display = str(display_name or "").strip() or raw
            field_label_map.setdefault(raw, display)
    return field_label_map, table_label_map


def _collect_proc_display_maps(session: SchemeDesignSession) -> tuple[dict[str, str], dict[str, str]]:
    datasets = [
        *(item for item in session.target_step.left_datasets if isinstance(item, dict)),
        *(item for item in session.target_step.right_datasets if isinstance(item, dict)),
        *(item for item in session.sample_datasets if isinstance(item, dict)),
    ]
    return _collect_display_maps(datasets)


def _collect_recon_display_maps(session: SchemeDesignSession) -> tuple[dict[str, str], dict[str, str]]:
    datasets = [item for item in session.sample_datasets if isinstance(item, dict)]
    return _collect_display_maps(datasets)


def _render_proc_draft_text_for_session(session: SchemeDesignSession, rule_json: dict[str, Any]) -> str:
    field_label_map, table_label_map = _collect_proc_display_maps(session)
    return render_proc_draft_text(
        rule_json,
        goal_hint=session.biz_goal,
        field_label_map=field_label_map,
        table_label_map=table_label_map,
    )


def _render_recon_draft_text_for_session(session: SchemeDesignSession, rule_json: dict[str, Any]) -> str:
    field_label_map, _ = _collect_recon_display_maps(session)
    return render_recon_draft_text(
        rule_json,
        goal_hint=session.biz_goal,
        field_label_map=field_label_map,
    )


def _build_rule_step_state(
    *,
    mode: str,
    rule_json: dict[str, Any],
    summary_builder: Any,
    draft_text: str = "",
    selected_rule_code: str = "",
    compatibility_result: dict[str, Any] | None = None,
    validation_result: dict[str, Any] | None = None,
    trial_result: dict[str, Any] | None = None,
    status: str = "idle",
    generation_used_fallback: bool = False,
    generation_note: str = "",
) -> SchemeDesignRuleStepState:
    normalized_rule_json = dict(rule_json or {})
    rule_summary = summary_builder(normalized_rule_json) if normalized_rule_json else ""
    draft_text_str = str(draft_text or "").strip()
    resolved_draft_text = draft_text_str or rule_summary
    return SchemeDesignRuleStepState(
        mode=mode,
        selected_rule_code=selected_rule_code,
        draft_text=resolved_draft_text,
        rule_summary=rule_summary,
        effective_rule_json=normalized_rule_json,
        compatibility_result=dict(compatibility_result or {}),
        validation_result=dict(validation_result or {}),
        trial_result=dict(trial_result or {}),
        status=status,
        generation_used_fallback=bool(generation_used_fallback),
        generation_note=str(generation_note or "").strip(),
    )


def _normalize_generation_meta(
    meta: dict[str, Any] | None,
    *,
    fallback_message: str,
) -> dict[str, Any]:
    raw = dict(meta or {})
    used_fallback = bool(raw.get("used_fallback"))
    message = str(raw.get("message") or "").strip() or fallback_message
    details = [
        str(item).strip()
        for item in list(raw.get("details") or [])
        if str(item).strip()
    ]
    return {
        "status": "warning" if used_fallback else "passed",
        "compatible": True,
        "used_fallback": used_fallback,
        "message": message,
        "issues": details,
    }


def _truncate_log_text(value: Any, *, limit: int = 320) -> str:
    text = str(value or "").strip().replace("\n", " | ")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


class SchemeDesignService:
    """Configuration-phase scheme design service."""

    def __init__(
        self,
        *,
        store: InMemorySchemeDesignSessionStore,
        executor: SchemeDesignExecutor,
    ):
        self._store = store
        self._executor = executor
        self._generation_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._generation_tasks_lock = asyncio.Lock()

    async def start_session(self, *, auth_token: str, payload: StartSessionInput) -> SchemeDesignSession:
        user = self._require_user(auth_token)
        now = datetime.now(timezone.utc)
        session_id = f"design_{uuid.uuid4().hex}"
        normalized_datasets = [
            _normalize_target_dataset(item)
            for item in list(payload.sample_datasets or [])
            if isinstance(item, dict)
        ]
        left_datasets = [
            item for item in normalized_datasets if str(item.get("side") or "").strip() == "left"
        ]
        right_datasets = [
            item for item in normalized_datasets if str(item.get("side") or "").strip() == "right"
        ]
        session = SchemeDesignSession(
            session_id=session_id,
            status=SchemeDesignStatus.DRAFT,
            owner_user_id=str(user.get("user_id") or ""),
            scheme_name=(payload.scheme_name or "").strip(),
            biz_goal=(payload.biz_goal or "").strip(),
            source_description=(payload.source_description or "").strip(),
            sample_files=list(payload.sample_files or []),
            sample_datasets=normalized_datasets,
            target_step=SchemeDesignTargetState(
                left_datasets=left_datasets,
                right_datasets=right_datasets,
                left_description="",
                right_description="",
            ),
            executor_name=self._executor.name,
            created_at=now,
            updated_at=now,
            messages=[
                SchemeDesignMessage(
                    role="system",
                    content="Design session started. Drafts are in-memory only.",
                    created_at=now,
                )
            ],
        )
        if payload.initial_message.strip():
            session.messages.append(
                SchemeDesignMessage(role="user", content=payload.initial_message.strip(), created_at=now)
            )
            turn_result = await self._executor.run_turn(
                session=session,
                user_message=payload.initial_message.strip(),
                is_resume=False,
            )
            self._apply_legacy_executor_result(session, turn_result)
            await self._run_trials_if_needed(session, auth_token=auth_token, run_trial=payload.run_trial)
        await self._store.create(session)
        return session

    async def update_target(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: TargetStepInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        left_datasets = [
            _normalize_target_dataset(item, default_side="left")
            for item in list(payload.left_datasets or [])
            if isinstance(item, dict)
        ]
        right_datasets = [
            _normalize_target_dataset(item, default_side="right")
            for item in list(payload.right_datasets or [])
            if isinstance(item, dict)
        ]
        session.target_step = SchemeDesignTargetState(
            left_datasets=left_datasets,
            right_datasets=right_datasets,
            left_description=(payload.left_description or "").strip(),
            right_description=(payload.right_description or "").strip(),
        )
        session.sample_datasets = [
            *left_datasets,
            *right_datasets,
        ]
        session.source_description = _compose_source_description(
            session.target_step.left_description,
            session.target_step.right_description,
        )
        session.updated_at = datetime.now(timezone.utc)
        await self._store.upsert(session)
        return session

    async def start_generate_proc_step(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: RuleGenerateInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        if not session.target_step.left_datasets or not session.target_step.right_datasets:
            raise ValueError("请先完成左右数据集选择")
        if await self._has_active_generation_task(session_id, "proc"):
            return session

        now = datetime.now(timezone.utc)
        session.proc_step.mode = "ai_generated"
        session.proc_step.status = "generating"
        session.proc_step.generation_phase = "preparing_context"
        session.proc_step.generation_message = "正在准备左右数据集样例"
        session.proc_step.generation_skill = _GENERATION_LABELS["proc"]
        session.proc_step.generation_started_at = now
        session.proc_step.generation_finished_at = None
        session.proc_step.validation_result = {}
        session.updated_at = now
        await self._store.upsert(session)
        await self._schedule_generation_task(
            stage="proc",
            session_id=session_id,
            auth_token=auth_token,
            payload=payload,
        )
        return session

    async def start_generate_recon_step(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: RuleGenerateInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        if not self._build_recon_sample_datasets(session):
            raise ValueError("请先完成数据整理试跑，再生成对账逻辑")
        if await self._has_active_generation_task(session_id, "recon"):
            return session

        now = datetime.now(timezone.utc)
        session.recon_step.mode = "ai_generated"
        session.recon_step.status = "generating"
        session.recon_step.generation_phase = "preparing_context"
        session.recon_step.generation_message = "正在准备数据整理后的左右输出样例"
        session.recon_step.generation_skill = _GENERATION_LABELS["recon"]
        session.recon_step.generation_started_at = now
        session.recon_step.generation_finished_at = None
        session.recon_step.validation_result = {}
        session.updated_at = now
        await self._store.upsert(session)
        await self._schedule_generation_task(
            stage="recon",
            session_id=session_id,
            auth_token=auth_token,
            payload=payload,
        )
        return session

    async def _has_active_generation_task(self, session_id: str, stage: str) -> bool:
        async with self._generation_tasks_lock:
            task = self._generation_tasks.get((session_id, stage))
            if task is None:
                return False
            if task.done():
                self._generation_tasks.pop((session_id, stage), None)
                return False
            return True

    async def _schedule_generation_task(
        self,
        *,
        stage: str,
        session_id: str,
        auth_token: str,
        payload: RuleGenerateInput,
    ) -> None:
        key = (session_id, stage)
        async with self._generation_tasks_lock:
            existing = self._generation_tasks.get(key)
            if existing is not None and not existing.done():
                return
            task = asyncio.create_task(
                self._run_generation_task(
                    stage=stage,
                    session_id=session_id,
                    auth_token=auth_token,
                    payload=payload,
                )
            )
            self._generation_tasks[key] = task

    async def _clear_generation_task(self, session_id: str, stage: str) -> None:
        async with self._generation_tasks_lock:
            self._generation_tasks.pop((session_id, stage), None)

    async def _run_generation_task(
        self,
        *,
        stage: str,
        session_id: str,
        auth_token: str,
        payload: RuleGenerateInput,
    ) -> None:
        try:
            if stage == "proc":
                await self._run_proc_generation_task(
                    session_id=session_id,
                    auth_token=auth_token,
                    payload=payload,
                )
            else:
                await self._run_recon_generation_task(
                    session_id=session_id,
                    auth_token=auth_token,
                    payload=payload,
                )
        finally:
            await self._clear_generation_task(session_id, stage)

    async def _update_generation_progress(
        self,
        *,
        auth_token: str,
        session_id: str,
        stage: str,
        phase: str,
        message: str,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        step_state = session.proc_step if stage == "proc" else session.recon_step
        step_state.status = "generating"
        step_state.generation_phase = phase
        step_state.generation_message = message
        step_state.generation_skill = _GENERATION_LABELS["proc" if stage == "proc" else "recon"]
        if step_state.generation_started_at is None:
            step_state.generation_started_at = datetime.now(timezone.utc)
        step_state.generation_finished_at = None
        session.updated_at = datetime.now(timezone.utc)
        await self._store.upsert(session)
        return session

    async def _mark_generation_failed(
        self,
        *,
        auth_token: str,
        session_id: str,
        stage: str,
        error: Exception,
    ) -> None:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return
        step_state = session.proc_step if stage == "proc" else session.recon_step
        step_state.status = "generate_failed"
        step_state.generation_phase = "failed"
        step_state.generation_message = str(error) or "生成失败"
        step_state.generation_skill = _GENERATION_LABELS["proc" if stage == "proc" else "recon"]
        step_state.generation_finished_at = datetime.now(timezone.utc)
        step_state.validation_result = {"success": False, "message": step_state.generation_message}
        session.updated_at = datetime.now(timezone.utc)
        await self._store.upsert(session)

    async def _run_proc_generation_task(
        self,
        *,
        session_id: str,
        auth_token: str,
        payload: RuleGenerateInput,
    ) -> None:
        started_at = datetime.now(timezone.utc)
        started_perf = perf_counter()
        try:
            session = await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="proc",
                phase="preparing_context",
                message="正在准备左右数据集样例",
            )
            if session is None:
                return
            working_session = session.model_copy(deep=True)
            sample_started_perf = perf_counter()
            target_sample_datasets = await self._build_target_sample_datasets(
                session,
                auth_token=auth_token,
            )
            logger.info(
                "[scheme_design][proc] prepared target samples session_id=%s datasets=%s elapsed=%.2fs",
                session_id,
                len(target_sample_datasets),
                perf_counter() - sample_started_perf,
            )
            working_session.sample_datasets = target_sample_datasets
            session.sample_datasets = [dict(item) for item in target_sample_datasets]
            working_session.source_description = _compose_source_description(
                session.target_step.left_description,
                session.target_step.right_description,
            )
            await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="proc",
                phase="generating_rule",
                message="正在根据目标、描述和样例生成数据整理配置",
            )
            turn_result = await self._executor.run_turn(
                session=working_session,
                user_message=f"只生成proc。\n{(payload.instruction_text or '').strip()}".strip(),
                is_resume=False,
            )
            proc_rule_json = dict(turn_result.proc_draft_json or {})
            if not proc_rule_json:
                raise ValueError("AI 未返回有效的数据整理配置")
            await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="proc",
                phase="validating_rule",
                message="正在校验数据整理配置是否可执行",
            )
            await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="proc",
                phase="rendering_draft_text",
                message="正在整理可编辑的数据整理说明",
            )
            session = await self._get_owned_session(auth_token, session_id, touch=False)
            if session is None:
                return
            session.drafts.proc_draft_json = proc_rule_json
            proc_generation_meta = _normalize_generation_meta(
                turn_result.proc_generation_meta,
                fallback_message="AI 已生成数据整理配置。",
            )
            session.proc_step = _build_rule_step_state(
                mode="ai_generated",
                rule_json=proc_rule_json,
                summary_builder=_summarize_proc_rule,
                draft_text=(turn_result.proc_draft_text or "").strip(),
                compatibility_result=proc_generation_meta,
                validation_result={
                    "success": True,
                    "used_fallback": bool(proc_generation_meta.get("used_fallback")),
                    "message": str(proc_generation_meta.get("message") or "").strip(),
                },
                status="generated",
                generation_used_fallback=bool(proc_generation_meta.get("used_fallback")),
                generation_note=str(proc_generation_meta.get("message") or "").strip(),
            )
            session.proc_step.generation_phase = "completed"
            session.proc_step.generation_message = str(proc_generation_meta.get("message") or "已生成数据整理配置")
            session.proc_step.generation_skill = _GENERATION_LABELS["proc"]
            session.proc_step.generation_started_at = started_at
            session.proc_step.generation_finished_at = datetime.now(timezone.utc)
            session.updated_at = datetime.now(timezone.utc)
            self._refresh_session_status(session)
            await self._store.upsert(session)
            logger.info(
                "[scheme_design][proc] generation audit session_id=%s used_fallback=%s summary=%s draft_preview=%s json_preview=%s",
                session_id,
                bool(proc_generation_meta.get("used_fallback")),
                _truncate_log_text(session.proc_step.rule_summary),
                _truncate_log_text(session.proc_step.draft_text),
                _truncate_log_text(json.dumps(proc_rule_json, ensure_ascii=False)),
            )
            logger.info(
                "[scheme_design][proc] generation completed session_id=%s elapsed=%.2fs",
                session_id,
                perf_counter() - started_perf,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("异步生成 proc 配置失败: session_id=%s", session_id)
            await self._mark_generation_failed(
                auth_token=auth_token,
                session_id=session_id,
                stage="proc",
                error=exc,
            )
            logger.warning(
                "[scheme_design][proc] generation failed session_id=%s elapsed=%.2fs",
                session_id,
                perf_counter() - started_perf,
            )

    async def _run_recon_generation_task(
        self,
        *,
        session_id: str,
        auth_token: str,
        payload: RuleGenerateInput,
    ) -> None:
        started_at = datetime.now(timezone.utc)
        started_perf = perf_counter()
        try:
            session = await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="recon",
                phase="preparing_context",
                message="正在准备数据整理后的左右输出样例",
            )
            if session is None:
                return
            prepared_datasets = self._build_recon_sample_datasets(session)
            if not prepared_datasets:
                raise ValueError("请先完成数据整理试跑，再生成对账逻辑")
            working_session = session.model_copy(deep=True)
            working_session.sample_datasets = prepared_datasets
            working_session.source_description = (
                f"{_compose_source_description(session.target_step.left_description, session.target_step.right_description)}\n"
                "当前输入为数据整理后的左右输出样例。"
            )
            await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="recon",
                phase="generating_rule",
                message="正在根据整理结果样例生成数据对账配置",
            )
            turn_result = await self._executor.run_turn(
                session=working_session,
                user_message=f"只生成recon。\n{(payload.instruction_text or '').strip()}".strip(),
                is_resume=False,
            )
            recon_rule_json = dict(turn_result.recon_draft_json or {})
            if not recon_rule_json:
                raise ValueError("AI 未返回有效的数据对账逻辑")
            await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="recon",
                phase="validating_rule",
                message="正在校验对账配置是否可执行",
            )
            await self._update_generation_progress(
                auth_token=auth_token,
                session_id=session_id,
                stage="recon",
                phase="rendering_draft_text",
                message="正在整理可编辑的数据对账说明",
            )
            session = await self._get_owned_session(auth_token, session_id, touch=False)
            if session is None:
                return
            session.drafts.recon_draft_json = recon_rule_json
            recon_generation_meta = _normalize_generation_meta(
                turn_result.recon_generation_meta,
                fallback_message="AI 已生成数据对账逻辑。",
            )
            session.recon_step = _build_rule_step_state(
                mode="ai_generated",
                rule_json=recon_rule_json,
                summary_builder=_summarize_recon_rule,
                draft_text=(turn_result.recon_draft_text or "").strip(),
                compatibility_result=recon_generation_meta,
                validation_result={
                    "success": True,
                    "used_fallback": bool(recon_generation_meta.get("used_fallback")),
                    "message": str(recon_generation_meta.get("message") or "").strip(),
                },
                status="generated",
                generation_used_fallback=bool(recon_generation_meta.get("used_fallback")),
                generation_note=str(recon_generation_meta.get("message") or "").strip(),
            )
            session.recon_step.generation_phase = "completed"
            session.recon_step.generation_message = str(recon_generation_meta.get("message") or "已生成数据对账逻辑")
            session.recon_step.generation_skill = _GENERATION_LABELS["recon"]
            session.recon_step.generation_started_at = started_at
            session.recon_step.generation_finished_at = datetime.now(timezone.utc)
            session.updated_at = datetime.now(timezone.utc)
            self._refresh_session_status(session)
            await self._store.upsert(session)
            logger.info(
                "[scheme_design][recon] generation audit session_id=%s used_fallback=%s summary=%s draft_preview=%s json_preview=%s",
                session_id,
                bool(recon_generation_meta.get("used_fallback")),
                _truncate_log_text(session.recon_step.rule_summary),
                _truncate_log_text(session.recon_step.draft_text),
                _truncate_log_text(json.dumps(recon_rule_json, ensure_ascii=False)),
            )
            logger.info(
                "[scheme_design][recon] generation completed session_id=%s elapsed=%.2fs",
                session_id,
                perf_counter() - started_perf,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("异步生成 recon 配置失败: session_id=%s", session_id)
            await self._mark_generation_failed(
                auth_token=auth_token,
                session_id=session_id,
                stage="recon",
                error=exc,
            )
            logger.warning(
                "[scheme_design][recon] generation failed session_id=%s elapsed=%.2fs",
                session_id,
                perf_counter() - started_perf,
            )

    async def use_existing_proc_rule(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: UseExistingRuleInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        rule_json = await self._resolve_rule_json(auth_token, payload.rule_code, payload.rule_json)
        target_sample_datasets = await self._build_target_sample_datasets(
            session,
            auth_token=auth_token,
        )
        compatibility = await execution_proc_rule_compatibility_check(
            auth_token,
            {
                "proc_rule_json": rule_json,
                "sample_datasets": target_sample_datasets,
            },
        )
        normalized_rule = compatibility.get("normalized_rule") if isinstance(compatibility.get("normalized_rule"), dict) else rule_json
        session.drafts.proc_draft_json = dict(normalized_rule)
        session.sample_datasets = [dict(item) for item in target_sample_datasets]
        draft_text = _render_proc_draft_text_for_session(session, dict(normalized_rule)) or _summarize_proc_rule(normalized_rule)
        session.proc_step = _build_rule_step_state(
            mode="existing",
            rule_json=dict(normalized_rule),
            summary_builder=_summarize_proc_rule,
            selected_rule_code=(payload.rule_code or "").strip(),
            draft_text=draft_text,
            compatibility_result=compatibility if isinstance(compatibility, dict) else {},
            validation_result={"success": bool(compatibility.get("success"))},
            status="compatible" if compatibility.get("compatible") else "incompatible",
        )
        session.updated_at = datetime.now(timezone.utc)
        self._refresh_session_status(session)
        await self._store.upsert(session)
        return session

    async def trial_proc_step(
        self,
        *,
        auth_token: str,
        session_id: str,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        proc_rule_json = self._current_proc_rule_json(session)
        if not proc_rule_json:
            raise ValueError("当前没有可试跑的数据整理配置")
        target_sample_datasets = await self._build_target_sample_datasets(
            session,
            auth_token=auth_token,
        )
        trial_result = await self.run_proc_trial(
            auth_token=auth_token,
            payload=ProcTrialInput(
                proc_rule_json=proc_rule_json,
                sample_datasets=target_sample_datasets,
                uploaded_files=self._build_uploaded_files(session.sample_files),
            ),
        )
        normalized_rule = trial_result.get("normalized_rule")
        if isinstance(normalized_rule, dict) and normalized_rule:
            proc_rule_json = dict(normalized_rule)
        session.drafts.proc_draft_json = proc_rule_json
        session.drafts.proc_trial_result = trial_result
        session.sample_datasets = [dict(item) for item in target_sample_datasets]
        session.proc_step.effective_rule_json = proc_rule_json
        session.proc_step.rule_summary = _summarize_proc_rule(proc_rule_json)
        session.proc_step.validation_result = {"success": bool(trial_result.get("success"))}
        session.proc_step.trial_result = trial_result
        session.proc_step.status = "trial_passed" if trial_result.get("ready_for_confirm") else "trial_failed"
        if not session.proc_step.draft_text:
            session.proc_step.draft_text = session.proc_step.rule_summary
        session.updated_at = datetime.now(timezone.utc)
        self._refresh_session_status(session)
        await self._store.upsert(session)
        return session

    async def use_existing_recon_rule(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: UseExistingRuleInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        prepared_datasets = self._build_recon_sample_datasets(session)
        if not prepared_datasets:
            raise ValueError("请先完成数据整理试跑，再选择已有对账逻辑")
        rule_json = await self._resolve_rule_json(auth_token, payload.rule_code, payload.rule_json)
        compatibility = await execution_recon_rule_compatibility_check(
            auth_token,
            {
                "recon_rule_json": rule_json,
                "sample_datasets": prepared_datasets,
            },
        )
        normalized_rule = compatibility.get("normalized_rule") if isinstance(compatibility.get("normalized_rule"), dict) else rule_json
        # Force source/target table names to canonical left/right_recon_ready so the
        # rule connects to this session's proc output regardless of its origin.
        normalized_rule = _force_recon_table_names(dict(normalized_rule))
        session.drafts.recon_draft_json = dict(normalized_rule)
        draft_text = _render_recon_draft_text_for_session(session, dict(normalized_rule)) or _summarize_recon_rule(normalized_rule)
        session.recon_step = _build_rule_step_state(
            mode="existing",
            rule_json=dict(normalized_rule),
            summary_builder=_summarize_recon_rule,
            selected_rule_code=(payload.rule_code or "").strip(),
            draft_text=draft_text,
            compatibility_result=compatibility if isinstance(compatibility, dict) else {},
            validation_result={"success": bool(compatibility.get("success"))},
            status="compatible" if compatibility.get("compatible") else "incompatible",
        )
        session.updated_at = datetime.now(timezone.utc)
        self._refresh_session_status(session)
        await self._store.upsert(session)
        return session

    async def trial_recon_step(
        self,
        *,
        auth_token: str,
        session_id: str,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        recon_rule_json = self._current_recon_rule_json(session)
        if not recon_rule_json:
            raise ValueError("当前没有可试跑的数据对账逻辑")
        prepared_datasets = self._build_recon_sample_datasets(session)
        if not prepared_datasets:
            raise ValueError("请先完成数据整理试跑，再进行对账试跑")
        trial_result = await self.run_recon_trial(
            auth_token=auth_token,
            payload=ReconTrialInput(
                recon_rule_json=recon_rule_json,
                sample_datasets=prepared_datasets,
            ),
        )
        normalized_rule = trial_result.get("normalized_rule")
        if isinstance(normalized_rule, dict) and normalized_rule:
            recon_rule_json = dict(normalized_rule)
        session.drafts.recon_draft_json = recon_rule_json
        session.drafts.recon_trial_result = trial_result
        session.recon_step.effective_rule_json = recon_rule_json
        session.recon_step.rule_summary = _summarize_recon_rule(recon_rule_json)
        session.recon_step.validation_result = {"success": bool(trial_result.get("success"))}
        session.recon_step.trial_result = trial_result
        session.recon_step.status = "trial_passed" if trial_result.get("ready_for_confirm") else "trial_failed"
        if not session.recon_step.draft_text:
            session.recon_step.draft_text = session.recon_step.rule_summary
        session.updated_at = datetime.now(timezone.utc)
        self._refresh_session_status(session)
        await self._store.upsert(session)
        return session

    async def handle_message(
        self,
        *,
        auth_token: str,
        session_id: str,
        message: str,
        is_resume: bool,
        run_trial: bool,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        if session.status in (SchemeDesignStatus.DISCARDED, SchemeDesignStatus.EXPIRED):
            return session
        now = datetime.now(timezone.utc)
        session.messages.append(SchemeDesignMessage(role="user", content=message.strip(), created_at=now))
        session.updated_at = now
        turn_result = await self._executor.run_turn(
            session=session,
            user_message=message.strip(),
            is_resume=is_resume,
        )
        self._apply_legacy_executor_result(session, turn_result)
        await self._run_trials_if_needed(session, auth_token=auth_token, run_trial=run_trial)
        await self._store.upsert(session)
        return session

    async def get_session(self, auth_token: str, session_id: str) -> Optional[SchemeDesignSession]:
        return await self._get_owned_session(auth_token, session_id, touch=True)

    async def confirm_session(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: ConfirmSessionInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None

        if payload.confirmation_note.strip():
            session.drafts.user_confirmations.append(payload.confirmation_note.strip())

        proc_rule_json = self._current_proc_rule_json(session)
        recon_rule_json = self._current_recon_rule_json(session)
        scheme_name = (payload.scheme_name or session.scheme_name or "").strip() or "未命名方案"
        file_rule_code = (payload.file_rule_code or "").strip()
        proc_rule_code = (payload.proc_rule_code or session.proc_step.selected_rule_code or "").strip()
        recon_rule_code = (payload.recon_rule_code or session.recon_step.selected_rule_code or "").strip()
        if not recon_rule_code and not recon_rule_json:
            session.status = SchemeDesignStatus.WAITING_CONFIRM
            session.persist_result = {
                "success": False,
                "error": "缺少可执行的对账规则",
                "backend": "validation",
            }
            await self._store.upsert(session)
            return session

        if proc_rule_json and not proc_rule_code:
            proc_save = await ensure_scheme_rule_saved(
                auth_token,
                scheme_name=scheme_name,
                rule_type="proc",
                rule_json=proc_rule_json,
                remark="方案设计自动生成整理规则",
                supported_entry_modes=['dataset'],
            )
            proc_rule_code = str(proc_save.get("rule_code") or proc_rule_code).strip()

        if recon_rule_json and not recon_rule_code:
            recon_save = await ensure_scheme_rule_saved(
                auth_token,
                scheme_name=scheme_name,
                rule_type="recon",
                rule_json=recon_rule_json,
                remark="方案设计自动生成对账逻辑",
                supported_entry_modes=['dataset'],
            )
            recon_rule_code = str(recon_save.get("rule_code") or recon_rule_code).strip()

        persist_payload: dict[str, Any] = {
            "scheme_name": scheme_name,
            "file_rule_code": file_rule_code,
            "proc_rule_code": proc_rule_code,
            "recon_rule_code": recon_rule_code,
            "scheme_meta_json": {
                "business_goal": session.biz_goal,
                "left_sources": session.target_step.left_datasets,
                "right_sources": session.target_step.right_datasets,
                "left_description": session.target_step.left_description,
                "right_description": session.target_step.right_description,
                "proc_rule_name": scheme_name + " 整理规则",
                "recon_rule_name": scheme_name + " 对账逻辑",
                "proc_draft_text": session.proc_step.draft_text,
                "recon_draft_text": session.recon_step.draft_text,
                "proc_trial_status": session.proc_step.status,
                "proc_trial_summary": str(session.proc_step.trial_result.get("summary") or ""),
                "recon_trial_status": session.recon_step.status,
                "recon_trial_summary": str(session.recon_step.trial_result.get("summary") or ""),
            },
        }
        if proc_rule_json:
            persist_payload["scheme_meta_json"]["proc_rule_json"] = proc_rule_json
        if recon_rule_json:
            persist_payload["scheme_meta_json"]["recon_rule_json"] = recon_rule_json
        persist_result = await execution_scheme_create(auth_token, persist_payload)

        now = datetime.now(timezone.utc)
        if bool(persist_result.get("success")):
            session.status = SchemeDesignStatus.CONFIRMED
            session.confirmed_at = now
        else:
            session.status = SchemeDesignStatus.WAITING_CONFIRM
        session.updated_at = now
        session.persist_result = persist_result
        session.messages.append(
            SchemeDesignMessage(
                role="assistant",
                content=(
                    "已确认当前设计会话。"
                    if persist_result.get("success")
                    else f"当前草稿已保留，但后端持久化未完成：{persist_result.get('error', 'unknown')}"
                ),
                created_at=now,
            )
        )
        await self._store.upsert(session)
        return session

    async def discard_session(self, auth_token: str, session_id: str) -> bool:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return False
        return await self._store.delete(session_id)

    async def run_proc_trial(self, *, auth_token: str, payload: ProcTrialInput) -> dict[str, Any]:
        return await execution_proc_draft_trial(
            auth_token,
            {
                "proc_rule_json": payload.proc_rule_json,
                "sample_datasets": list(payload.sample_datasets or []),
                "uploaded_files": list(payload.uploaded_files or []),
            },
        )

    async def run_recon_trial(self, *, auth_token: str, payload: ReconTrialInput) -> dict[str, Any]:
        return await execution_recon_draft_trial(
            auth_token,
            {
                "recon_rule_json": payload.recon_rule_json,
                "sample_datasets": list(payload.sample_datasets or []),
                "validated_inputs": list(payload.validated_inputs or []),
            },
        )

    async def _get_owned_session(
        self,
        auth_token: str,
        session_id: str,
        *,
        touch: bool,
    ) -> Optional[SchemeDesignSession]:
        user = self._require_user(auth_token)
        session = await self._store.get(session_id, touch=touch)
        if session is None:
            return None
        if session.owner_user_id and session.owner_user_id != str(user.get("user_id") or ""):
            raise ValueError("当前设计会话不属于你，无法访问")
        return session

    def _require_user(self, auth_token: str) -> dict[str, Any]:
        user = _decode_user(auth_token)
        if not user or not str(user.get("user_id") or "").strip():
            raise ValueError("未提供认证 token，或 token 已失效")
        return user

    async def _resolve_rule_json(
        self,
        auth_token: str,
        rule_code: str,
        rule_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(rule_json, dict) and rule_json:
            return dict(rule_json)
        normalized_rule_code = (rule_code or "").strip()
        if not normalized_rule_code:
            raise ValueError("缺少 rule_code 或 rule_json")
        result = await get_file_validation_rule(normalized_rule_code, auth_token)
        if not result.get("success"):
            raise ValueError(str(result.get("error") or "加载规则失败"))
        rule_record = result.get("data")
        if not isinstance(rule_record, dict):
            raise ValueError("规则详情为空")
        resolved = _normalize_existing_rule_json(rule_record)
        if not resolved:
            raise ValueError("规则 JSON 为空")
        return resolved

    def _build_uploaded_files(self, sample_files: list[str]) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for raw in sample_files:
            file_path = str(raw or "").strip()
            if not file_path:
                continue
            files.append(
                {
                    "file_path": file_path,
                    "file_name": Path(file_path).name or os.path.basename(file_path),
                    "table_name": Path(file_path).stem or "uploaded_file",
                }
            )
        return files

    async def _build_target_sample_datasets(
        self,
        session: SchemeDesignSession,
        *,
        auth_token: str,
    ) -> list[dict[str, Any]]:
        cached = self._get_cached_target_sample_datasets(session)
        if cached:
            logger.info(
                "[scheme_design][proc] reuse cached published snapshot samples session_id=%s datasets=%s",
                session.session_id,
                len(cached),
            )
            return cached
        raw_datasets = [
            *[
                _normalize_target_dataset(dict(item), default_side="left")
                for item in session.target_step.left_datasets
                if isinstance(item, dict)
            ],
            *[
                _normalize_target_dataset(dict(item), default_side="right")
                for item in session.target_step.right_datasets
                if isinstance(item, dict)
            ],
        ]
        return await self._hydrate_target_sample_datasets(auth_token, raw_datasets)

    def _get_cached_target_sample_datasets(
        self,
        session: SchemeDesignSession,
    ) -> list[dict[str, Any]]:
        current_target = [
            *[
                _normalize_target_dataset(dict(item), default_side="left")
                for item in session.target_step.left_datasets
                if isinstance(item, dict)
            ],
            *[
                _normalize_target_dataset(dict(item), default_side="right")
                for item in session.target_step.right_datasets
                if isinstance(item, dict)
            ],
        ]
        cached = [
            _normalize_target_dataset(dict(item))
            for item in session.sample_datasets
            if isinstance(item, dict)
        ]
        if not current_target or len(cached) != len(current_target):
            return []
        current_keys = sorted(_target_dataset_identity(item) for item in current_target)
        cached_keys = sorted(_target_dataset_identity(item) for item in cached)
        if current_keys != cached_keys:
            return []
        if not all(
            str(item.get("sample_origin") or "").strip() == "published_snapshot"
            and _has_dict_rows(item.get("sample_rows"))
            for item in cached
        ):
            return []
        return cached

    async def _hydrate_target_sample_datasets(
        self,
        auth_token: str,
        datasets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized = [_normalize_target_dataset(item) for item in datasets if isinstance(item, dict)]
        if not auth_token or not normalized:
            return normalized
        resolved = await asyncio.gather(
            *(self._hydrate_single_target_dataset(auth_token, item) for item in normalized),
            return_exceptions=True,
        )
        hydrated: list[dict[str, Any]] = []
        for original, item in zip(normalized, resolved, strict=False):
            hydrated.append(_normalize_target_dataset(item if isinstance(item, dict) else original))
        return hydrated

    async def _hydrate_single_target_dataset(
        self,
        auth_token: str,
        dataset: dict[str, Any],
    ) -> dict[str, Any]:
        source_id = _resolve_dataset_source_id(dataset)
        if not auth_token or not source_id:
            return dict(dataset)
        resource_key = _resolve_dataset_resource_key(dataset)
        result = await data_source_list_published_snapshot_rows(
            auth_token,
            source_id,
            resource_key=resource_key,
            limit=3,
        )
        rows = [row for row in list(result.get("rows") or []) if isinstance(row, dict)]
        if not bool(result.get("success")) or not rows:
            return _normalize_target_dataset(dict(dataset))
        resolved = dict(dataset)
        table_name = _resolve_dataset_table_name(resolved)
        if table_name:
            resolved["table_name"] = table_name
        if resource_key:
            resolved["resource_key"] = resource_key
        resolved["sample_rows"] = rows[:3]
        resolved["schema_summary"] = _merge_schema_summary(resolved.get("schema_summary"), rows)
        published_snapshot = result.get("published_snapshot")
        if isinstance(published_snapshot, dict):
            resolved["snapshot_id"] = str(
                published_snapshot.get("snapshot_id") or published_snapshot.get("id") or ""
            )
        resolved["sample_origin"] = "published_snapshot"
        return _normalize_target_dataset(resolved)

    def _build_recon_sample_datasets(self, session: SchemeDesignSession) -> list[dict[str, Any]]:
        trial_result = session.proc_step.trial_result or session.drafts.proc_trial_result
        output_samples = trial_result.get("output_samples")
        prepared_datasets: list[dict[str, Any]] = []
        if not isinstance(output_samples, list):
            return prepared_datasets
        for item in output_samples:
            if not isinstance(item, dict):
                continue
            rows = [row for row in list(item.get("rows") or []) if isinstance(row, dict)][:3]
            table_name = str(item.get("target_table") or item.get("title") or "").strip()
            if not table_name or not rows:
                continue
            side = _infer_side(str(item.get("side") or table_name))
            field_label_map = _build_ready_field_label_map(rows)
            fallback_business_name = "左侧整理结果数据集" if side == "left" else "右侧整理结果数据集"
            prepared_datasets.append(
                _normalize_target_dataset(
                    {
                    "side": side,
                    "dataset_name": table_name,
                    "table_name": table_name,
                    "source_id": table_name,
                    "source_key": table_name,
                    "resource_key": table_name,
                    "business_name": fallback_business_name,
                    "field_label_map": field_label_map,
                    "fields": [
                        {"raw_name": field_name, "display_name": field_label_map.get(field_name, field_name)}
                        for field_name in infer_raw_field_names({"sample_rows": rows})
                    ],
                    "description": (
                        session.target_step.left_description if side == "left" else session.target_step.right_description
                    ),
                    "schema_summary": _infer_schema_summary_from_rows(rows),
                    "sample_rows": rows,
                    },
                    default_side=side,
                )
            )
        return prepared_datasets

    def _current_proc_rule_json(self, session: SchemeDesignSession) -> dict[str, Any]:
        if session.proc_step.effective_rule_json:
            return dict(session.proc_step.effective_rule_json)
        return dict(session.drafts.proc_draft_json or {})

    def _current_recon_rule_json(self, session: SchemeDesignSession) -> dict[str, Any]:
        if session.recon_step.effective_rule_json:
            return dict(session.recon_step.effective_rule_json)
        return dict(session.drafts.recon_draft_json or {})

    def _refresh_session_status(self, session: SchemeDesignSession) -> None:
        if session.status == SchemeDesignStatus.CONFIRMED:
            return
        if self._current_proc_rule_json(session) and self._current_recon_rule_json(session):
            session.status = SchemeDesignStatus.WAITING_CONFIRM
        else:
            session.status = SchemeDesignStatus.DRAFT

    def _apply_legacy_executor_result(self, session: SchemeDesignSession, result: Any) -> None:
        now = datetime.now(timezone.utc)
        if result.proc_draft_json is not None:
            proc_rule_json = dict(result.proc_draft_json)
            session.drafts.proc_draft_json = proc_rule_json
            session.proc_step = _build_rule_step_state(
                mode="ai_generated",
                rule_json=proc_rule_json,
                summary_builder=_summarize_proc_rule,
                draft_text=(result.proc_draft_text or "").strip(),
                validation_result={"success": True},
                compatibility_result=_normalize_generation_meta(
                    result.proc_generation_meta,
                    fallback_message="AI 已生成数据整理配置。",
                ),
                status="generated",
                generation_used_fallback=bool((result.proc_generation_meta or {}).get("used_fallback")),
                generation_note=str((result.proc_generation_meta or {}).get("message") or "").strip(),
            )
        if result.recon_draft_json is not None:
            recon_rule_json = dict(result.recon_draft_json)
            session.drafts.recon_draft_json = recon_rule_json
            session.recon_step = _build_rule_step_state(
                mode="ai_generated",
                rule_json=recon_rule_json,
                summary_builder=_summarize_recon_rule,
                draft_text=(result.recon_draft_text or "").strip(),
                validation_result={"success": True},
                compatibility_result=_normalize_generation_meta(
                    result.recon_generation_meta,
                    fallback_message="AI 已生成数据对账逻辑。",
                ),
                status="generated",
                generation_used_fallback=bool((result.recon_generation_meta or {}).get("used_fallback")),
                generation_note=str((result.recon_generation_meta or {}).get("message") or "").strip(),
            )
        if result.proc_trial_result is not None:
            session.drafts.proc_trial_result = result.proc_trial_result
            session.proc_step.trial_result = result.proc_trial_result
        if result.recon_trial_result is not None:
            session.drafts.recon_trial_result = result.recon_trial_result
            session.recon_step.trial_result = result.recon_trial_result
        session.drafts.open_questions = list(result.open_questions or [])
        session.messages.append(
            SchemeDesignMessage(role="assistant", content=result.assistant_message, created_at=now)
        )
        session.updated_at = now
        self._refresh_session_status(session)

    async def _run_trials_if_needed(
        self,
        session: SchemeDesignSession,
        *,
        auth_token: str,
        run_trial: bool,
    ) -> None:
        if not run_trial or not auth_token:
            return
        if self._current_proc_rule_json(session):
            target_sample_datasets = await self._build_target_sample_datasets(
                session,
                auth_token=auth_token,
            )
            session.sample_datasets = [dict(item) for item in target_sample_datasets]
            session.drafts.proc_trial_result = await self.run_proc_trial(
                auth_token=auth_token,
                payload=ProcTrialInput(
                    proc_rule_json=self._current_proc_rule_json(session),
                    sample_datasets=target_sample_datasets,
                    uploaded_files=self._build_uploaded_files(session.sample_files),
                ),
            )
            session.proc_step.trial_result = session.drafts.proc_trial_result
        if self._current_recon_rule_json(session):
            prepared_datasets = self._build_recon_sample_datasets(session)
            if prepared_datasets:
                session.drafts.recon_trial_result = await self.run_recon_trial(
                    auth_token=auth_token,
                    payload=ReconTrialInput(
                        recon_rule_json=self._current_recon_rule_json(session),
                        sample_datasets=prepared_datasets,
                    ),
                )
                session.recon_step.trial_result = session.drafts.recon_trial_result


_service_singleton: SchemeDesignService | None = None


def _build_default_executor() -> SchemeDesignExecutor:
    try:
        executor = DeepAgentSchemeDesignExecutor()
        logger.info("scheme design executor initialized: %s", executor.name)
        return executor
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "scheme design DeepAgent executor init failed, fallback to single-shot executor: %s",
            exc,
        )
        return SingleShotSchemeDesignExecutor()


def get_scheme_design_service() -> SchemeDesignService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = SchemeDesignService(
            store=InMemorySchemeDesignSessionStore(),
            executor=_build_default_executor(),
        )
    return _service_singleton
