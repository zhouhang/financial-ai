"""Scheme design REST APIs."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .service import (
    ConfirmSessionInput,
    ProcTrialInput,
    ReconTrialInput,
    RuleGenerateInput,
    StartSessionInput,
    TargetStepInput,
    UseExistingRuleInput,
    get_scheme_design_service,
)

router = APIRouter(prefix="/recon/schemes/design", tags=["recon-scheme-design"])


def _sse_message(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _step_payload(session: Any, stage: str) -> dict[str, Any]:
    session_payload = session.model_dump(mode="json")
    step_payload = session_payload.get("proc_step") if stage == "proc" else session_payload.get("recon_step")
    return {
        "stage": stage,
        "status": (step_payload or {}).get("status", ""),
        "phase": (step_payload or {}).get("generation_phase", ""),
        "skill": (step_payload or {}).get("generation_skill", ""),
        "message": (step_payload or {}).get("generation_message", ""),
        "session": session_payload,
    }


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1)
    return authorization


def _translate_service_error(exc: ValueError) -> HTTPException:
    message = str(exc) or "方案设计请求处理失败"
    if "不属于你" in message:
        return HTTPException(status_code=403, detail=message)
    if "token" in message or "登录" in message or "失效" in message:
        return HTTPException(status_code=401, detail=message)
    return HTTPException(status_code=400, detail=message)


class StartDesignSessionRequest(BaseModel):
    scheme_name: str = ""
    biz_goal: str = ""
    source_description: str = ""
    sample_files: list[str] = Field(default_factory=list)
    sample_datasets: list[dict[str, Any]] = Field(default_factory=list)
    initial_message: str = ""
    run_trial: bool = False


class DesignSessionMessageRequest(BaseModel):
    message: str
    run_trial: bool = True


class TargetStepRequest(BaseModel):
    left_datasets: list[dict[str, Any]] = Field(default_factory=list)
    right_datasets: list[dict[str, Any]] = Field(default_factory=list)
    left_description: str = ""
    right_description: str = ""


class RuleGenerateRequest(BaseModel):
    instruction_text: str = ""


class UseExistingRuleRequest(BaseModel):
    rule_code: str = ""
    rule_json: dict[str, Any] = Field(default_factory=dict)


class ConfirmDesignSessionRequest(BaseModel):
    scheme_name: str = ""
    file_rule_code: str = ""
    proc_rule_code: str = ""
    recon_rule_code: str = ""
    confirmation_note: str = ""


class ProcTrialRequest(BaseModel):
    proc_rule_json: dict[str, Any] = Field(default_factory=dict)
    sample_datasets: list[dict[str, Any]] = Field(default_factory=list)
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)


class ReconTrialRequest(BaseModel):
    recon_rule_json: dict[str, Any] = Field(default_factory=dict)
    sample_datasets: list[dict[str, Any]] = Field(default_factory=list)
    validated_inputs: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/start")
async def start_design_session(
    body: StartDesignSessionRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.start_session(
            auth_token=auth_token,
            payload=StartSessionInput(
                scheme_name=body.scheme_name,
                biz_goal=body.biz_goal,
                source_description=body.source_description,
                sample_files=body.sample_files,
                sample_datasets=body.sample_datasets,
                initial_message=body.initial_message,
                run_trial=body.run_trial,
            ),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    return {
        "success": True,
        "design_session_id": session.session_id,
        "session": session.model_dump(mode="json"),
    }


@router.post("/{session_id}/message")
async def message_design_session(
    session_id: str,
    body: DesignSessionMessageRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.handle_message(
            auth_token=auth_token,
            session_id=session_id,
            message=body.message,
            is_resume=False,
            run_trial=body.run_trial,
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/resume")
async def resume_design_session(
    session_id: str,
    body: DesignSessionMessageRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.handle_message(
            auth_token=auth_token,
            session_id=session_id,
            message=body.message,
            is_resume=True,
            run_trial=body.run_trial,
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.get("/{session_id}")
async def get_design_session(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.get_session(auth_token, session_id)
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/target")
async def update_target_step(
    session_id: str,
    body: TargetStepRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.update_target(
            auth_token=auth_token,
            session_id=session_id,
            payload=TargetStepInput(
                left_datasets=body.left_datasets,
                right_datasets=body.right_datasets,
                left_description=body.left_description,
                right_description=body.right_description,
            ),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/proc/generate/stream")
async def stream_generate_proc_step(
    session_id: str,
    body: RuleGenerateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.start_generate_proc_step(
            auth_token=auth_token,
            session_id=session_id,
            payload=RuleGenerateInput(instruction_text=body.instruction_text),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")

    async def event_generator():
        last_signature: tuple[str, str, str] | None = None
        while True:
            current_session = await service.get_session(auth_token, session_id)
            if current_session is None:
                yield _sse_message("error", {"stage": "proc", "message": "design session 不存在"})
                return
            payload = _step_payload(current_session, "proc")
            signature = (
                str(payload.get("status") or ""),
                str(payload.get("phase") or ""),
                str(payload.get("message") or ""),
            )
            if signature != last_signature:
                yield _sse_message("progress", payload)
                last_signature = signature

            status = str(payload.get("status") or "")
            if status == "generate_failed":
                yield _sse_message("error", payload)
                return
            if status and status != "generating":
                yield _sse_message("completed", payload)
                return
            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/proc/use-existing")
async def use_existing_proc_rule(
    session_id: str,
    body: UseExistingRuleRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.use_existing_proc_rule(
            auth_token=auth_token,
            session_id=session_id,
            payload=UseExistingRuleInput(rule_code=body.rule_code, rule_json=body.rule_json),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/proc/trial")
async def trial_proc_step(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.trial_proc_step(auth_token=auth_token, session_id=session_id)
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/recon/generate/stream")
async def stream_generate_recon_step(
    session_id: str,
    body: RuleGenerateRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.start_generate_recon_step(
            auth_token=auth_token,
            session_id=session_id,
            payload=RuleGenerateInput(instruction_text=body.instruction_text),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")

    async def event_generator():
        last_signature: tuple[str, str, str] | None = None
        while True:
            current_session = await service.get_session(auth_token, session_id)
            if current_session is None:
                yield _sse_message("error", {"stage": "recon", "message": "design session 不存在"})
                return
            payload = _step_payload(current_session, "recon")
            signature = (
                str(payload.get("status") or ""),
                str(payload.get("phase") or ""),
                str(payload.get("message") or ""),
            )
            if signature != last_signature:
                yield _sse_message("progress", payload)
                last_signature = signature

            status = str(payload.get("status") or "")
            if status == "generate_failed":
                yield _sse_message("error", payload)
                return
            if status and status != "generating":
                yield _sse_message("completed", payload)
                return
            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/recon/use-existing")
async def use_existing_recon_rule(
    session_id: str,
    body: UseExistingRuleRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.use_existing_recon_rule(
            auth_token=auth_token,
            session_id=session_id,
            payload=UseExistingRuleInput(rule_code=body.rule_code, rule_json=body.rule_json),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/recon/trial")
async def trial_recon_step(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.trial_recon_step(auth_token=auth_token, session_id=session_id)
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/{session_id}/confirm")
async def confirm_design_session(
    session_id: str,
    body: ConfirmDesignSessionRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        session = await service.confirm_session(
            auth_token=auth_token,
            session_id=session_id,
            payload=ConfirmSessionInput(
                scheme_name=body.scheme_name,
                file_rule_code=body.file_rule_code,
                proc_rule_code=body.proc_rule_code,
                recon_rule_code=body.recon_rule_code,
                confirmation_note=body.confirmation_note,
            ),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.post("/proc-trial")
async def proc_trial(
    body: ProcTrialRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        result = await service.run_proc_trial(
            auth_token=auth_token,
            payload=ProcTrialInput(
                proc_rule_json=body.proc_rule_json,
                sample_datasets=body.sample_datasets,
                uploaded_files=body.uploaded_files,
            ),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    return result


@router.post("/recon-trial")
async def recon_trial(
    body: ReconTrialRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        result = await service.run_recon_trial(
            auth_token=auth_token,
            payload=ReconTrialInput(
                recon_rule_json=body.recon_rule_json,
                sample_datasets=body.sample_datasets,
                validated_inputs=body.validated_inputs,
            ),
        )
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    return result


@router.delete("/{session_id}")
async def delete_design_session(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    try:
        deleted = await service.discard_session(auth_token, session_id)
    except ValueError as exc:
        raise _translate_service_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "deleted": True}
