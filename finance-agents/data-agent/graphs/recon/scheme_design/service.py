"""Scheme design service for button-driven scheme configuration."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
    FallbackSchemeDesignExecutor,
    SchemeDesignExecutor,
)
from .session_store import InMemorySchemeDesignSessionStore

JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
JWT_ALGORITHM = "HS256"


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


def _normalize_existing_rule_json(raw: dict[str, Any]) -> dict[str, Any]:
    rule_json = raw.get("rule")
    if isinstance(rule_json, dict):
        return rule_json
    return raw if isinstance(raw, dict) else {}


def _summarize_proc_rule(rule_json: dict[str, Any]) -> str:
    steps = rule_json.get("steps")
    if not isinstance(steps, list) or not steps:
        return ""
    lines: list[str] = []
    role_desc = str(rule_json.get("role_desc") or "").strip()
    if role_desc:
        lines.append(role_desc)
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or step.get("step") or "").strip()
        target_table = str(step.get("target_table") or "结果表").strip()
        if action == "create_schema":
            columns = []
            schema = step.get("schema")
            if isinstance(schema, dict):
                for column in schema.get("columns") or []:
                    if not isinstance(column, dict):
                        continue
                    column_name = str(column.get("name") or "").strip()
                    if column_name:
                        columns.append(column_name)
            if columns:
                lines.append(f"步骤{index}：定义 {target_table} 输出结构，包含字段：{'、'.join(columns)}。")
            else:
                lines.append(f"步骤{index}：定义 {target_table} 输出结构。")
            continue
        if action == "write_dataset":
            source_names: list[str] = []
            for source in step.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                source_name = str(source.get("table") or source.get("name") or source.get("alias") or "").strip()
                if source_name:
                    source_names.append(source_name)
            line = f"步骤{index}：将{'、'.join(source_names) or '当前数据集'}整理后写入 {target_table}。"
            mappings = []
            for mapping in step.get("mappings") or []:
                if not isinstance(mapping, dict):
                    continue
                target_field = str(mapping.get("target_field") or "").strip()
                value = mapping.get("value")
                if not target_field or not isinstance(value, dict):
                    continue
                source = value.get("source")
                if isinstance(source, dict):
                    source_field = str(source.get("field") or "").strip()
                    if source_field:
                        mappings.append(f"{source_field} -> {target_field}")
            if mappings:
                line += f" 字段映射：{'；'.join(mappings[:6])}。"
            lines.append(line)
            continue
        lines.append(f"步骤{index}：处理 {target_table}。")
    return "\n".join(lines).strip()


def _summarize_recon_rule(rule_json: dict[str, Any]) -> str:
    rules = rule_json.get("rules")
    if not isinstance(rules, list) or not rules:
        return ""
    first_rule = rules[0] if isinstance(rules[0], dict) else {}
    source_file = first_rule.get("source_file") if isinstance(first_rule, dict) else {}
    target_file = first_rule.get("target_file") if isinstance(first_rule, dict) else {}
    recon = first_rule.get("recon") if isinstance(first_rule, dict) else {}
    if not isinstance(recon, dict):
        recon = {}
    key_columns = recon.get("key_columns")
    compare_columns = recon.get("compare_columns")
    if not isinstance(key_columns, dict):
        key_columns = {}
    if not isinstance(compare_columns, dict):
        compare_columns = {}
    mappings = key_columns.get("mappings") or []
    columns = compare_columns.get("columns") or []
    first_mapping = mappings[0] if isinstance(mappings, list) and mappings and isinstance(mappings[0], dict) else {}
    first_column = columns[0] if isinstance(columns, list) and columns and isinstance(columns[0], dict) else {}
    source_table = str((source_file or {}).get("table_name") or "left_recon_ready").strip()
    target_table = str((target_file or {}).get("table_name") or "right_recon_ready").strip()
    match_key = str(first_mapping.get("source_field") or "biz_key").strip()
    left_amount = str(first_column.get("source_column") or "amount").strip()
    right_amount = str(first_column.get("target_column") or "amount").strip()
    tolerance = str(first_column.get("tolerance") or "0").strip()
    return "\n".join(
        [
            f"输入：{source_table} ↔ {target_table}",
            f"匹配主键：{match_key}",
            f"左金额字段：{left_amount}",
            f"右金额字段：{right_amount}",
            f"容差：{tolerance}",
            "识别方式：按匹配主键对齐左右记录，比较金额差异并输出核对结果。",
        ]
    ).strip()


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

    async def start_session(self, *, auth_token: str, payload: StartSessionInput) -> SchemeDesignSession:
        user = self._require_user(auth_token)
        now = datetime.now(timezone.utc)
        session_id = f"design_{uuid.uuid4().hex}"
        left_datasets = [item for item in list(payload.sample_datasets or []) if isinstance(item, dict) and str(item.get("side") or "").strip() == "left"]
        right_datasets = [item for item in list(payload.sample_datasets or []) if isinstance(item, dict) and str(item.get("side") or "").strip() == "right"]
        session = SchemeDesignSession(
            session_id=session_id,
            status=SchemeDesignStatus.DRAFT,
            owner_user_id=str(user.get("user_id") or ""),
            scheme_name=(payload.scheme_name or "").strip(),
            biz_goal=(payload.biz_goal or "").strip(),
            source_description=(payload.source_description or "").strip(),
            sample_files=list(payload.sample_files or []),
            sample_datasets=list(payload.sample_datasets or []),
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
        session.target_step = SchemeDesignTargetState(
            left_datasets=list(payload.left_datasets or []),
            right_datasets=list(payload.right_datasets or []),
            left_description=(payload.left_description or "").strip(),
            right_description=(payload.right_description or "").strip(),
        )
        session.sample_datasets = [
            *list(payload.left_datasets or []),
            *list(payload.right_datasets or []),
        ]
        session.source_description = _compose_source_description(
            session.target_step.left_description,
            session.target_step.right_description,
        )
        session.updated_at = datetime.now(timezone.utc)
        await self._store.upsert(session)
        return session

    async def generate_proc_step(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: RuleGenerateInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        working_session = session.model_copy(deep=True)
        working_session.sample_datasets = self._build_target_sample_datasets(session)
        working_session.source_description = _compose_source_description(
            session.target_step.left_description,
            session.target_step.right_description,
        )
        turn_result = await self._executor.run_turn(
            session=working_session,
            user_message=f"只生成proc。\n{(payload.instruction_text or '').strip()}".strip(),
            is_resume=False,
        )
        proc_rule_json = dict(turn_result.proc_draft_json or {})
        if not proc_rule_json:
            raise ValueError("AI 未返回有效的数据整理配置")
        normalized_display_text = _summarize_proc_rule(proc_rule_json)
        session.drafts.proc_draft_json = proc_rule_json
        session.proc_step = SchemeDesignRuleStepState(
            mode="ai_generated",
            editable_instruction_text=normalized_display_text,
            normalized_display_text=normalized_display_text,
            candidate_rule_json=proc_rule_json,
            normalized_rule_json=proc_rule_json,
            validation_result={"success": True},
            status="generated",
        )
        session.updated_at = datetime.now(timezone.utc)
        self._refresh_session_status(session)
        await self._store.upsert(session)
        return session

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
        compatibility = await execution_proc_rule_compatibility_check(
            auth_token,
            {
                "proc_rule_json": rule_json,
                "sample_datasets": self._build_target_sample_datasets(session),
            },
        )
        normalized_rule = compatibility.get("normalized_rule") if isinstance(compatibility.get("normalized_rule"), dict) else rule_json
        normalized_display_text = _summarize_proc_rule(normalized_rule)
        session.drafts.proc_draft_json = dict(normalized_rule)
        session.proc_step = SchemeDesignRuleStepState(
            mode="existing",
            selected_rule_code=(payload.rule_code or "").strip(),
            editable_instruction_text=normalized_display_text,
            normalized_display_text=normalized_display_text,
            candidate_rule_json=dict(rule_json),
            normalized_rule_json=dict(normalized_rule),
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
        trial_result = await self.run_proc_trial(
            auth_token=auth_token,
            payload=ProcTrialInput(
                proc_rule_json=proc_rule_json,
                sample_datasets=self._build_target_sample_datasets(session),
                uploaded_files=self._build_uploaded_files(session.sample_files),
            ),
        )
        normalized_rule = trial_result.get("normalized_rule")
        if isinstance(normalized_rule, dict) and normalized_rule:
            proc_rule_json = dict(normalized_rule)
        session.drafts.proc_draft_json = proc_rule_json
        session.drafts.proc_trial_result = trial_result
        session.proc_step.candidate_rule_json = proc_rule_json
        session.proc_step.normalized_rule_json = proc_rule_json
        session.proc_step.validation_result = {"success": bool(trial_result.get("success"))}
        session.proc_step.trial_result = trial_result
        session.proc_step.status = "trial_passed" if trial_result.get("ready_for_confirm") else "trial_failed"
        if not session.proc_step.editable_instruction_text:
            session.proc_step.editable_instruction_text = _summarize_proc_rule(proc_rule_json)
            session.proc_step.normalized_display_text = session.proc_step.editable_instruction_text
        session.updated_at = datetime.now(timezone.utc)
        self._refresh_session_status(session)
        await self._store.upsert(session)
        return session

    async def generate_recon_step(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: RuleGenerateInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._get_owned_session(auth_token, session_id, touch=False)
        if session is None:
            return None
        prepared_datasets = self._build_recon_sample_datasets(session)
        if not prepared_datasets:
            raise ValueError("请先完成数据整理试跑，再生成对账逻辑")
        working_session = session.model_copy(deep=True)
        working_session.sample_datasets = prepared_datasets
        working_session.source_description = (
            f"{_compose_source_description(session.target_step.left_description, session.target_step.right_description)}\n"
            "当前输入为数据整理后的左右输出样例。"
        )
        turn_result = await self._executor.run_turn(
            session=working_session,
            user_message=f"只生成recon。\n{(payload.instruction_text or '').strip()}".strip(),
            is_resume=False,
        )
        recon_rule_json = dict(turn_result.recon_draft_json or {})
        if not recon_rule_json:
            raise ValueError("AI 未返回有效的数据对账逻辑")
        normalized_display_text = _summarize_recon_rule(recon_rule_json)
        session.drafts.recon_draft_json = recon_rule_json
        session.recon_step = SchemeDesignRuleStepState(
            mode="ai_generated",
            editable_instruction_text=normalized_display_text,
            normalized_display_text=normalized_display_text,
            candidate_rule_json=recon_rule_json,
            normalized_rule_json=recon_rule_json,
            validation_result={"success": True},
            status="generated",
        )
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
        normalized_display_text = _summarize_recon_rule(normalized_rule)
        session.drafts.recon_draft_json = dict(normalized_rule)
        session.recon_step = SchemeDesignRuleStepState(
            mode="existing",
            selected_rule_code=(payload.rule_code or "").strip(),
            editable_instruction_text=normalized_display_text,
            normalized_display_text=normalized_display_text,
            candidate_rule_json=dict(rule_json),
            normalized_rule_json=dict(normalized_rule),
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
        session.recon_step.candidate_rule_json = recon_rule_json
        session.recon_step.normalized_rule_json = recon_rule_json
        session.recon_step.validation_result = {"success": bool(trial_result.get("success"))}
        session.recon_step.trial_result = trial_result
        session.recon_step.status = "trial_passed" if trial_result.get("ready_for_confirm") else "trial_failed"
        if not session.recon_step.editable_instruction_text:
            session.recon_step.editable_instruction_text = _summarize_recon_rule(recon_rule_json)
            session.recon_step.normalized_display_text = session.recon_step.editable_instruction_text
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
                "proc_draft_text": session.proc_step.editable_instruction_text,
                "recon_draft_text": session.recon_step.editable_instruction_text,
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

    def _build_target_sample_datasets(self, session: SchemeDesignSession) -> list[dict[str, Any]]:
        return [
            *[dict(item) for item in session.target_step.left_datasets if isinstance(item, dict)],
            *[dict(item) for item in session.target_step.right_datasets if isinstance(item, dict)],
        ]

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
            prepared_datasets.append(
                {
                    "side": side,
                    "dataset_name": table_name,
                    "table_name": table_name,
                    "source_id": table_name,
                    "source_key": table_name,
                    "resource_key": table_name,
                    "description": (
                        session.target_step.left_description if side == "left" else session.target_step.right_description
                    ),
                    "schema_summary": _infer_schema_summary_from_rows(rows),
                    "sample_rows": rows,
                }
            )
        return prepared_datasets

    def _current_proc_rule_json(self, session: SchemeDesignSession) -> dict[str, Any]:
        if session.proc_step.normalized_rule_json:
            return dict(session.proc_step.normalized_rule_json)
        if session.proc_step.candidate_rule_json:
            return dict(session.proc_step.candidate_rule_json)
        return dict(session.drafts.proc_draft_json or {})

    def _current_recon_rule_json(self, session: SchemeDesignSession) -> dict[str, Any]:
        if session.recon_step.normalized_rule_json:
            return dict(session.recon_step.normalized_rule_json)
        if session.recon_step.candidate_rule_json:
            return dict(session.recon_step.candidate_rule_json)
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
            session.proc_step = SchemeDesignRuleStepState(
                mode="ai_generated",
                editable_instruction_text=_summarize_proc_rule(proc_rule_json),
                normalized_display_text=_summarize_proc_rule(proc_rule_json),
                candidate_rule_json=proc_rule_json,
                normalized_rule_json=proc_rule_json,
                validation_result={"success": True},
                status="generated",
            )
        if result.recon_draft_json is not None:
            recon_rule_json = dict(result.recon_draft_json)
            session.drafts.recon_draft_json = recon_rule_json
            session.recon_step = SchemeDesignRuleStepState(
                mode="ai_generated",
                editable_instruction_text=_summarize_recon_rule(recon_rule_json),
                normalized_display_text=_summarize_recon_rule(recon_rule_json),
                candidate_rule_json=recon_rule_json,
                normalized_rule_json=recon_rule_json,
                validation_result={"success": True},
                status="generated",
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
            session.drafts.proc_trial_result = await self.run_proc_trial(
                auth_token=auth_token,
                payload=ProcTrialInput(
                    proc_rule_json=self._current_proc_rule_json(session),
                    sample_datasets=self._build_target_sample_datasets(session),
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


def get_scheme_design_service() -> SchemeDesignService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = SchemeDesignService(
            store=InMemorySchemeDesignSessionStore(),
            executor=DeepAgentSchemeDesignExecutor(),
        )
    return _service_singleton
