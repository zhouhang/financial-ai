"""REST APIs for AI rule generation."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graphs.rule_generation.common.events import encode_sse
from graphs.rule_generation.service import get_rule_generation_service

router = APIRouter(prefix="/rule-generation", tags=["rule-generation"])


class ProcSideGenerationRequest(BaseModel):
    side: str
    target_table: str
    rule_text: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    proc_json_examples: list[dict[str, Any]] = Field(default_factory=list)
    max_retries: int = 2


class ProcGenerationRequest(BaseModel):
    rule_text: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    target_tables: list[str] = Field(default_factory=list)
    proc_json_examples: list[dict[str, Any]] = Field(default_factory=list)
    max_retries: int = 2


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1)
    return authorization


@router.post("/proc/side")
async def generate_proc_side(
    body: ProcSideGenerationRequest,
    authorization: Optional[str] = Header(None),
):
    """Run proc rule generation and return the final payload."""
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_rule_generation_service()
    return await service.run_proc_side(auth_token=auth_token, payload=body.model_dump(mode="json"))


@router.post("/proc")
async def generate_proc(
    body: ProcGenerationRequest,
    authorization: Optional[str] = Header(None),
):
    """Run generic proc rule generation and return the final payload."""
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_rule_generation_service()
    return await service.run_proc(auth_token=auth_token, payload=body.model_dump(mode="json"))


@router.post("/proc/side/stream")
async def stream_generate_proc_side(
    body: ProcSideGenerationRequest,
    authorization: Optional[str] = Header(None),
):
    """Stream proc rule generation node events."""
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_rule_generation_service()
    payload = body.model_dump(mode="json")

    async def event_generator():
        async for event in service.stream_proc_side(auth_token=auth_token, payload=payload):
            yield encode_sse(str(event.get("event") or "message"), event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/proc/stream")
async def stream_generate_proc(
    body: ProcGenerationRequest,
    authorization: Optional[str] = Header(None),
):
    """Stream generic proc rule generation node events."""
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    service = get_rule_generation_service()
    payload = body.model_dump(mode="json")

    async def event_generator():
        async for event in service.stream_proc(auth_token=auth_token, payload=payload):
            yield encode_sse(str(event.get("event") or "message"), event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
