"""platform RESTful API 路由。

提供“数据连接”模块的 HTTP 接口：
- GET  /platform-connections
- GET  /platform-connections/{platform_code}/shops
- POST /platform-connections/{platform_code}/auth-sessions
- GET  /platform-auth/callback/{platform_code}
- POST /shop-connections/{connection_id}/reauthorize
- POST /shop-connections/{connection_id}/disable
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse

from tools.mcp_client import (
    platform_create_auth_session,
    platform_disable_shop,
    platform_get_shop_detail,
    platform_handle_auth_callback,
    platform_list_connections,
    platform_list_shops,
    platform_reauthorize_shop,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["platform"])


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization


class PlatformSummary(BaseModel):
    platform_code: str
    platform_name: str
    authorized_shop_count: int = 0
    error_shop_count: int = 0
    last_sync_at: Optional[str] = None
    status: Optional[str] = None


class ShopConnection(BaseModel):
    id: str
    company_id: Optional[str] = None
    platform_code: str
    platform_name: Optional[str] = None
    external_shop_id: Optional[str] = None
    external_shop_name: Optional[str] = None
    status: Optional[str] = None
    token_status: Optional[str] = None
    last_sync_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PlatformConnectionsResponse(BaseModel):
    success: bool
    mode: str = "mock"
    count: int = 0
    platforms: list[PlatformSummary] = Field(default_factory=list)
    connections: list[ShopConnection] = Field(default_factory=list)
    message: str = ""


class PlatformShopsResponse(BaseModel):
    success: bool
    mode: str = "mock"
    platform_code: str
    platform_name: str
    count: int = 0
    shops: list[ShopConnection] = Field(default_factory=list)
    message: str = ""


class CreateAuthSessionRequest(BaseModel):
    return_path: str = "/"
    mode: str = ""


class CreateAuthSessionResponse(BaseModel):
    success: bool
    mode: str = "mock"
    platform_code: str
    session_id: str
    state: str
    auth_url: str
    expires_in: int = 0
    message: str = ""


class ReauthorizeShopRequest(BaseModel):
    return_path: str = "/"
    mode: str = ""


class ReauthorizeShopResponse(BaseModel):
    success: bool
    mode: str = "mock"
    connection_id: str
    auth_url: str
    session_id: Optional[str] = None
    state: Optional[str] = None
    message: str = ""


class DisableShopRequest(BaseModel):
    reason: str = ""
    mode: str = ""


class DisableShopResponse(BaseModel):
    success: bool
    mode: str = "mock"
    connection_id: str
    message: str


class ShopDetailResponse(BaseModel):
    success: bool
    mode: str = "mock"
    connection: Optional[ShopConnection] = None
    sync_sources: list[dict[str, Any]] = Field(default_factory=list)
    authorization: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


@router.get("/platform-connections", response_model=PlatformConnectionsResponse)
async def get_platform_connections(
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    platform_code: str = Query("", description="可选：按平台过滤"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_list_connections(
        auth_token,
        mode=mode,
        platform_code=platform_code,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取平台连接失败"))

    return PlatformConnectionsResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        count=int(result.get("count") or len(result.get("connections") or [])),
        platforms=result.get("platforms") or [],
        connections=result.get("connections") or [],
        message=str(result.get("message") or ""),
    )


@router.get("/platform-connections/{platform_code}/shops", response_model=PlatformShopsResponse)
async def get_platform_shops(
    platform_code: str,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_list_shops(auth_token, platform_code, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取平台店铺失败"))

    return PlatformShopsResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        platform_code=platform_code,
        platform_name=str(result.get("platform_name") or platform_code),
        count=int(result.get("count") or len(result.get("shops") or [])),
        shops=result.get("shops") or [],
        message=str(result.get("message") or ""),
    )


@router.post(
    "/platform-connections/{platform_code}/auth-sessions",
    response_model=CreateAuthSessionResponse,
)
async def create_platform_auth_session(
    platform_code: str,
    body: CreateAuthSessionRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_create_auth_session(
        auth_token,
        platform_code,
        return_path=body.return_path,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建授权会话失败"))

    return CreateAuthSessionResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        platform_code=platform_code,
        session_id=str(result.get("session_id") or ""),
        state=str(result.get("state") or ""),
        auth_url=str(result.get("auth_url") or ""),
        expires_in=int(result.get("expires_in") or 0),
        message=str(result.get("message") or ""),
    )


@router.get("/platform-auth/callback/{platform_code}")
async def handle_platform_auth_callback(
    platform_code: str,
    code: str = Query("", description="授权码"),
    state: str = Query("", description="授权会话状态"),
    error: str = Query("", description="授权错误码"),
    error_description: str = Query("", description="授权错误描述"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
):
    result = await platform_handle_auth_callback(
        platform_code,
        code=code,
        state=state,
        error=error,
        error_description=error_description,
        mode=mode,
    )

    success = bool(result.get("success"))
    display_message = str(result.get("message") or result.get("error") or "授权失败，请重试")
    redirect_to = _build_callback_redirect_url(
        str(result.get("return_path") or "/"),
        platform_code=platform_code,
        success=success,
        message=display_message,
        shop_name=str(((result.get("connection") or {}).get("external_shop_name")) or ""),
    )
    return RedirectResponse(url=redirect_to, status_code=303)


@router.post("/shop-connections/{connection_id}/reauthorize", response_model=ReauthorizeShopResponse)
async def reauthorize_shop_connection(
    connection_id: str,
    body: ReauthorizeShopRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_reauthorize_shop(
        auth_token,
        connection_id,
        return_path=body.return_path,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "重新授权失败"))

    return ReauthorizeShopResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        connection_id=connection_id,
        auth_url=str(result.get("auth_url") or ""),
        session_id=str(result.get("session_id") or "") or None,
        state=str(result.get("state") or "") or None,
        message=str(result.get("message") or "已生成授权链接"),
    )


@router.post("/shop-connections/{connection_id}/disable", response_model=DisableShopResponse)
async def disable_shop_connection(
    connection_id: str,
    body: DisableShopRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_disable_shop(
        auth_token,
        connection_id,
        reason=body.reason,
        mode=body.mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "停用店铺连接失败"))

    return DisableShopResponse(
        success=True,
        mode=str(result.get("mode") or body.mode or "mock"),
        connection_id=connection_id,
        message=str(result.get("message") or "店铺连接已停用"),
    )


@router.get("/shop-connections/{connection_id}", response_model=ShopDetailResponse)
async def get_shop_connection_detail(
    connection_id: str,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_get_shop_detail(auth_token, connection_id, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "店铺连接不存在"))

    return ShopDetailResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        connection=result.get("connection"),
        sync_sources=result.get("sync_sources") or [],
        authorization=result.get("authorization") or {},
        message=str(result.get("message") or ""),
    )
def _build_callback_redirect_url(
    return_path: str,
    *,
    platform_code: str,
    success: bool,
    message: str,
    shop_name: str = "",
) -> str:
    raw_target = (return_path or "/").strip() or "/"
    if not raw_target.startswith("/"):
        raw_target = "/"

    parsed = urlsplit(raw_target)
    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_pairs.update(
        {
            "section": "data-connections",
            "platform_auth_status": "success" if success else "failed",
            "platform_code": platform_code,
            "platform_auth_message": message,
        }
    )
    if shop_name:
        query_pairs["shop_name"] = shop_name
    else:
        query_pairs.pop("shop_name", None)

    return urlunsplit(
        (
            "",
            "",
            parsed.path or "/",
            urlencode(query_pairs),
            "",
        )
    )


