"""Scheme design REST APIs."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .service import ConfirmSessionInput, StartSessionInput, get_scheme_design_service

router = APIRouter(prefix="/recon/schemes/design", tags=["recon-scheme-design"])


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1)
    return authorization


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


class ConfirmDesignSessionRequest(BaseModel):
    scheme_name: str = ""
    file_rule_code: str = ""
    proc_rule_code: str = ""
    recon_rule_code: str = ""
    confirmation_note: str = ""


@router.post("/start")
async def start_design_session(
    body: StartDesignSessionRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
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
    session = await service.handle_message(
        auth_token=auth_token,
        session_id=session_id,
        message=body.message,
        is_resume=False,
        run_trial=body.run_trial,
    )
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
    session = await service.handle_message(
        auth_token=auth_token,
        session_id=session_id,
        message=body.message,
        is_resume=True,
        run_trial=body.run_trial,
    )
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
    session = await service.get_session(session_id)
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
    if session is None:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "session": session.model_dump(mode="json")}


@router.delete("/{session_id}")
async def delete_design_session(
    session_id: str,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_scheme_design_service()
    deleted = await service.discard_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="design session 不存在")
    return {"success": True, "deleted": True}

