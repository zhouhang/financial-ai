"""Scheme design service (fallback executor + in-memory sessions)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from models import (
    SchemeDesignMessage,
    SchemeDesignSession,
    SchemeDesignStatus,
)
from tools.mcp_client import (
    execution_proc_draft_trial,
    execution_recon_draft_trial,
    execution_scheme_create,
)

from .executor import FallbackSchemeDesignExecutor, SchemeDesignExecutor
from .session_store import InMemorySchemeDesignSessionStore


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
class ConfirmSessionInput:
    scheme_name: str = ""
    file_rule_code: str = ""
    proc_rule_code: str = ""
    recon_rule_code: str = ""
    confirmation_note: str = ""


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
        now = datetime.now(timezone.utc)
        session_id = f"design_{uuid.uuid4().hex}"
        session = SchemeDesignSession(
            session_id=session_id,
            status=SchemeDesignStatus.DRAFT,
            scheme_name=(payload.scheme_name or "").strip(),
            biz_goal=(payload.biz_goal or "").strip(),
            source_description=(payload.source_description or "").strip(),
            sample_files=list(payload.sample_files or []),
            sample_datasets=list(payload.sample_datasets or []),
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
                SchemeDesignMessage(
                    role="user",
                    content=payload.initial_message.strip(),
                    created_at=now,
                )
            )

        turn_result = await self._executor.run_turn(
            session=session,
            user_message=payload.initial_message.strip(),
            is_resume=False,
        )
        self._apply_executor_result(session, turn_result)
        await self._run_trials_if_needed(session, auth_token=auth_token, run_trial=payload.run_trial)
        await self._store.create(session)
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
        session = await self._store.get(session_id, touch=False)
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
        self._apply_executor_result(session, turn_result)
        await self._run_trials_if_needed(session, auth_token=auth_token, run_trial=run_trial)
        await self._store.upsert(session)
        return session

    async def get_session(self, session_id: str) -> Optional[SchemeDesignSession]:
        return await self._store.get(session_id, touch=True)

    async def confirm_session(
        self,
        *,
        auth_token: str,
        session_id: str,
        payload: ConfirmSessionInput,
    ) -> Optional[SchemeDesignSession]:
        session = await self._store.get(session_id, touch=False)
        if session is None:
            return None

        if payload.confirmation_note.strip():
            session.drafts.user_confirmations.append(payload.confirmation_note.strip())

        scheme_name = (payload.scheme_name or session.scheme_name or "").strip()
        file_rule_code = (payload.file_rule_code or "").strip()
        proc_rule_code = (payload.proc_rule_code or "").strip()
        recon_rule_code = (payload.recon_rule_code or "").strip()

        persist_result: dict[str, Any]
        missing_rule_codes = [name for name, value in (
            ("recon_rule_code", recon_rule_code),
        ) if not value]
        if missing_rule_codes:
            persist_result = {
                "success": False,
                "error": f"缺少必要 rule code: {', '.join(missing_rule_codes)}",
                "backend": "validation",
            }
        else:
            persist_payload: dict[str, Any] = {
                "scheme_name": scheme_name or "未命名方案",
                "recon_rule_code": recon_rule_code,
                "meta_json": {
                    "biz_goal": session.biz_goal,
                    "source_description": session.source_description,
                    "sample_files": session.sample_files,
                    "sample_datasets": session.sample_datasets,
                },
            }
            if file_rule_code:
                persist_payload["file_rule_code"] = file_rule_code
            if proc_rule_code:
                persist_payload["proc_rule_code"] = proc_rule_code
            persist_result = await execution_scheme_create(auth_token, persist_payload)

        now = datetime.now(timezone.utc)
        session.status = SchemeDesignStatus.CONFIRMED
        session.confirmed_at = now
        session.updated_at = now
        session.persist_result = persist_result
        session.messages.append(
            SchemeDesignMessage(
                role="assistant",
                content=(
                    "已确认当前设计会话。"
                    if persist_result.get("success")
                    else f"会话已确认，但后端持久化未完成：{persist_result.get('error', 'unknown')}"
                ),
                created_at=now,
            )
        )
        await self._store.upsert(session)
        return session

    async def discard_session(self, session_id: str) -> bool:
        return await self._store.delete(session_id)

    def _apply_executor_result(self, session: SchemeDesignSession, result: Any) -> None:
        now = datetime.now(timezone.utc)
        if result.proc_draft_json is not None:
            session.drafts.proc_draft_json = result.proc_draft_json
        if result.recon_draft_json is not None:
            session.drafts.recon_draft_json = result.recon_draft_json
        if result.proc_trial_result is not None:
            session.drafts.proc_trial_result = result.proc_trial_result
        if result.recon_trial_result is not None:
            session.drafts.recon_trial_result = result.recon_trial_result
        session.drafts.open_questions = list(result.open_questions or [])
        session.messages.append(
            SchemeDesignMessage(role="assistant", content=result.assistant_message, created_at=now)
        )
        session.updated_at = now
        if session.drafts.proc_draft_json and session.drafts.recon_draft_json:
            session.status = SchemeDesignStatus.WAITING_CONFIRM
        else:
            session.status = SchemeDesignStatus.DRAFT

    async def _run_trials_if_needed(
        self,
        session: SchemeDesignSession,
        *,
        auth_token: str,
        run_trial: bool,
    ) -> None:
        if not run_trial or not auth_token:
            return

        uploaded_files = self._build_uploaded_files(session.sample_files)
        if session.drafts.proc_draft_json:
            payload = {
                "proc_rule_json": session.drafts.proc_draft_json,
                "uploaded_files": uploaded_files,
            }
            session.drafts.proc_trial_result = await execution_proc_draft_trial(auth_token, payload)

        if session.drafts.recon_draft_json:
            payload = {
                "recon_rule_json": session.drafts.recon_draft_json,
                "validated_inputs": self._build_recon_trial_inputs(session),
            }
            session.drafts.recon_trial_result = await execution_recon_draft_trial(auth_token, payload)

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
                }
            )
        return files

    def _build_recon_trial_inputs(self, session: SchemeDesignSession) -> list[dict[str, Any]]:
        inputs: list[dict[str, Any]] = []
        for item in session.sample_datasets:
            table_name = str(item.get("table_name") or item.get("dataset_code") or "").strip()
            source_type = str(item.get("source_type") or "dataset").strip() or "dataset"
            source_key = str(item.get("source_key") or item.get("source_id") or "").strip()
            if not table_name:
                continue
            payload = {"dataset_ref": {"source_type": source_type, "source_key": source_key, "query": {}}}
            inputs.append({"table_name": table_name, "input_type": "dataset", "payload": payload})
        for path in session.sample_files:
            file_path = str(path or "").strip()
            if not file_path:
                continue
            table_name = Path(file_path).stem or "uploaded_file"
            inputs.append(
                {
                    "table_name": table_name,
                    "input_type": "file",
                    "payload": {"file_path": file_path},
                }
            )
        return inputs


_service_singleton: SchemeDesignService | None = None


def get_scheme_design_service() -> SchemeDesignService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = SchemeDesignService(
            store=InMemorySchemeDesignSessionStore(),
            executor=FallbackSchemeDesignExecutor(),
        )
    return _service_singleton

