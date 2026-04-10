"""Company-scoped collaboration channel REST API."""

from __future__ import annotations

import os
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services.notifications.repository import (
    delete_company_channel_config,
    list_company_channel_configs,
    save_company_channel_config,
)

router = APIRouter(tags=["collaboration"])

JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
JWT_ALGORITHM = "HS256"


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization


def _get_user_from_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
    return {
        "user_id": payload.get("sub"),
        "username": payload.get("username"),
        "role": payload.get("role"),
        "company_id": payload.get("company_id"),
        "department_id": payload.get("department_id"),
    }


def _require_user(authorization: Optional[str]) -> dict[str, Any]:
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    user = _get_user_from_token(auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="token 无效或已过期，请重新登录")
    company_id = str(user.get("company_id") or "").strip()
    if not company_id:
        raise HTTPException(status_code=400, detail="当前用户未绑定公司")
    return user


def _sanitize_channel_payload(channel: dict[str, Any]) -> dict[str, Any]:
    payload = dict(channel or {})
    payload.pop("client_secret", None)
    return payload


class CollaborationChannelUpsertRequest(BaseModel):
    provider: str
    channel_code: str = "default"
    name: str = ""
    client_id: str = ""
    client_secret: str = ""
    robot_code: str = ""
    is_default: bool = False
    is_enabled: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


@router.get("/collaboration-channels")
async def list_collaboration_channels(authorization: Optional[str] = Header(None)):
    user = _require_user(authorization)
    rows = list_company_channel_configs(company_id=str(user.get("company_id") or ""))
    return {
        "success": True,
        "channels": [_sanitize_channel_payload(item) for item in rows],
        "count": len(rows),
    }


@router.post("/collaboration-channels")
async def create_collaboration_channel(
    body: CollaborationChannelUpsertRequest,
    authorization: Optional[str] = Header(None),
):
    user = _require_user(authorization)
    saved = save_company_channel_config(
        company_id=str(user.get("company_id") or ""),
        provider=body.provider,
        channel_code=body.channel_code,
        name=body.name,
        client_id=body.client_id,
        client_secret=body.client_secret,
        robot_code=body.robot_code,
        extra=body.extra,
        is_default=body.is_default,
        is_enabled=body.is_enabled,
    )
    if not saved:
        raise HTTPException(status_code=400, detail="保存协作通道配置失败")
    return {
        "success": True,
        "channel": _sanitize_channel_payload(saved),
    }


@router.put("/collaboration-channels/{channel_id}")
async def update_collaboration_channel(
    channel_id: str,
    body: CollaborationChannelUpsertRequest,
    authorization: Optional[str] = Header(None),
):
    user = _require_user(authorization)
    saved = save_company_channel_config(
        company_id=str(user.get("company_id") or ""),
        channel_id=channel_id,
        provider=body.provider,
        channel_code=body.channel_code,
        name=body.name,
        client_id=body.client_id,
        client_secret=body.client_secret,
        robot_code=body.robot_code,
        extra=body.extra,
        is_default=body.is_default,
        is_enabled=body.is_enabled,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="协作通道不存在或更新失败")
    return {
        "success": True,
        "channel": _sanitize_channel_payload(saved),
    }


@router.delete("/collaboration-channels/{channel_id}")
async def delete_collaboration_channel(
    channel_id: str,
    authorization: Optional[str] = Header(None),
):
    user = _require_user(authorization)
    deleted = delete_company_channel_config(
        company_id=str(user.get("company_id") or ""),
        channel_id=channel_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="协作通道不存在或删除失败")
    return {
        "success": True,
        "message": "协作通道已删除",
    }
