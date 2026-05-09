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
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, RedirectResponse

from config import FINANCE_MCP_UPLOAD_DIR, MAX_FILE_SIZE
from tools.mcp_client import (
    platform_create_auth_session,
    platform_disable_shop,
    platform_get_app_config,
    platform_get_shop_detail,
    platform_handle_auth_callback,
    platform_claim_pending_authorization,
    platform_list_pending_authorizations,
    platform_list_connections,
    platform_list_shops,
    platform_reauthorize_shop,
    platform_upsert_app_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["platform"])

ALIPAY_AUTH_ASSET_ROOT = Path(FINANCE_MCP_UPLOAD_DIR) / "platform" / "alipay" / "auth-assets"
ALIPAY_AUTH_QR_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALIPAY_AUTH_QR_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALIPAY_AUTH_QR_MAX_BYTES = min(MAX_FILE_SIZE, 2 * 1024 * 1024)


def _extract_auth_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization


def _alipay_auth_qr_extension(filename: str, content_type: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALIPAY_AUTH_QR_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 png、jpg、jpeg、webp 二维码图片")
    if content_type and content_type.lower() not in ALIPAY_AUTH_QR_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="二维码图片类型不支持")
    return ".jpg" if ext == ".jpeg" else ext


def _resolve_alipay_auth_asset_path(filename: str) -> Path:
    safe_name = Path(filename).name
    if safe_name != filename or safe_name not in {"merchant-auth-qr.png", "merchant-auth-qr.jpg", "merchant-auth-qr.webp"}:
        raise HTTPException(status_code=404, detail="文件不存在")
    root = ALIPAY_AUTH_ASSET_ROOT.resolve()
    asset_path = (root / safe_name).resolve()
    try:
        asset_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="文件不存在") from None
    return asset_path


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
    auth_status: Optional[str] = None
    status: Optional[str] = None
    token_status: Optional[str] = None
    token_expires_at: Optional[str] = None
    last_refresh_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    last_status: Optional[str] = None
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
    merchant_display_name: str = ""


class PlatformAppConfig(BaseModel):
    id: str = ""
    platform_code: str = ""
    platform_name: str = ""
    app_name: str = ""
    app_key: str = ""
    app_secret: str = ""
    has_app_secret: bool = False
    has_app_public_cert: bool = False
    has_alipay_public_cert: bool = False
    has_alipay_root_cert: bool = False
    redirect_uri: str = ""
    auth_base_url: str = ""
    token_url: str = ""
    refresh_url: str = ""
    merchant_auth_mode: str = ""
    merchant_auth_pc_url: str = ""
    merchant_auth_qr_url: str = ""
    status: str = ""


class PlatformAppConfigResponse(BaseModel):
    success: bool
    mode: str = "mock"
    platform_code: str
    configured: bool = False
    config: PlatformAppConfig = Field(default_factory=PlatformAppConfig)
    message: str = ""


class AlipayMerchantAuthQrUploadResponse(BaseModel):
    success: bool
    mode: str = "real"
    platform_code: str = "alipay"
    merchant_auth_qr_url: str = ""
    config: PlatformAppConfig = Field(default_factory=PlatformAppConfig)
    message: str = ""


class UpsertPlatformAppConfigRequest(BaseModel):
    app_key: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    merchant_auth_mode: str = ""
    merchant_auth_pc_url: str = ""
    merchant_auth_qr_url: str = ""
    app_public_cert: str = ""
    alipay_public_cert: str = ""
    alipay_root_cert: str = ""
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
    connection: Optional[ShopConnection] = None


class ShopDetailResponse(BaseModel):
    success: bool
    mode: str = "mock"
    connection: Optional[ShopConnection] = None
    sync_sources: list[dict[str, Any]] = Field(default_factory=list)
    authorization: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class PendingAuthorizationResponse(BaseModel):
    success: bool
    mode: str = "mock"
    platform_code: str
    pending_authorizations: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    message: str = ""


class ClaimPendingAuthorizationRequest(BaseModel):
    claim_code: str
    merchant_display_name: str = ""
    mode: str = ""


class ClaimPendingAuthorizationResponse(BaseModel):
    success: bool
    mode: str = "mock"
    platform_code: str
    shop: dict[str, Any] = Field(default_factory=dict)
    pending_authorization: dict[str, Any] = Field(default_factory=dict)
    warning: str = ""
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


@router.get(
    "/platform-connections/{platform_code}/app-config",
    response_model=PlatformAppConfigResponse,
)
async def get_platform_app_config(
    platform_code: str,
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_get_app_config(auth_token, platform_code, mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取平台应用配置失败"))

    return PlatformAppConfigResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        platform_code=str(result.get("platform_code") or platform_code),
        configured=bool(result.get("configured")),
        config=result.get("config") or {},
        message=str(result.get("message") or ""),
    )


@router.put(
    "/platform-connections/{platform_code}/app-config",
    response_model=PlatformAppConfigResponse,
)
async def upsert_platform_app_config(
    platform_code: str,
    body: UpsertPlatformAppConfigRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_upsert_app_config(
        auth_token,
        platform_code,
        app_key=body.app_key,
        app_secret=body.app_secret,
        redirect_uri=body.redirect_uri,
        merchant_auth_mode=body.merchant_auth_mode,
        merchant_auth_pc_url=body.merchant_auth_pc_url,
        merchant_auth_qr_url=body.merchant_auth_qr_url,
        app_public_cert=body.app_public_cert,
        alipay_public_cert=body.alipay_public_cert,
        alipay_root_cert=body.alipay_root_cert,
        mode="real",
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "保存平台应用配置失败"))

    return PlatformAppConfigResponse(
        success=True,
        mode=str(result.get("mode") or "real"),
        platform_code=str(result.get("platform_code") or platform_code),
        configured=bool(result.get("configured")),
        config=result.get("config") or {},
        message=str(result.get("message") or "平台应用配置已保存。"),
    )


@router.post(
    "/platform-connections/alipay/app-config/merchant-auth-qr",
    response_model=AlipayMerchantAuthQrUploadResponse,
)
async def upload_alipay_merchant_auth_qr(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = _alipay_auth_qr_extension(file.filename, file.content_type or "")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="二维码图片不能为空")
    if len(content) > ALIPAY_AUTH_QR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="二维码图片不能超过 2MB")

    current = await platform_get_app_config(auth_token, "alipay", mode="real")
    if not current.get("success"):
        raise HTTPException(status_code=400, detail=current.get("error", "加载支付宝应用配置失败"))
    config = current.get("config") if isinstance(current.get("config"), dict) else {}
    app_key = str(config.get("app_key") or "").strip()
    if not app_key:
        raise HTTPException(status_code=400, detail="请先保存支付宝 AppID 和证书配置")

    ALIPAY_AUTH_ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    for stale_ext in ALIPAY_AUTH_QR_ALLOWED_EXTENSIONS:
        stale_path = ALIPAY_AUTH_ASSET_ROOT / f"merchant-auth-qr{'.jpg' if stale_ext == '.jpeg' else stale_ext}"
        if stale_path.exists() and stale_path.suffix != ext:
            stale_path.unlink()
    asset_name = f"merchant-auth-qr{ext}"
    asset_path = ALIPAY_AUTH_ASSET_ROOT / asset_name
    asset_path.write_bytes(content)
    asset_url = f"/api/platform-connections/alipay/assets/{asset_name}"

    result = await platform_upsert_app_config(
        auth_token,
        "alipay",
        app_key=app_key,
        app_secret="",
        redirect_uri=str(config.get("redirect_uri") or ""),
        merchant_auth_mode=str(config.get("merchant_auth_mode") or "static_invite"),
        merchant_auth_pc_url=str(config.get("merchant_auth_pc_url") or ""),
        merchant_auth_qr_url=asset_url,
        app_public_cert="",
        alipay_public_cert="",
        alipay_root_cert="",
        mode="real",
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "保存支付宝二维码配置失败"))

    saved_config = result.get("config") if isinstance(result.get("config"), dict) else {}
    return AlipayMerchantAuthQrUploadResponse(
        success=True,
        mode=str(result.get("mode") or "real"),
        merchant_auth_qr_url=str(saved_config.get("merchant_auth_qr_url") or asset_url),
        config=saved_config,
        message=str(result.get("message") or "支付宝商家授权二维码已上传"),
    )


@router.get("/platform-connections/alipay/assets/{filename}")
async def get_alipay_merchant_auth_asset(filename: str):
    asset_path = _resolve_alipay_auth_asset_path(filename)
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
    }.get(asset_path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(asset_path), media_type=media_type)


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
        merchant_display_name=body.merchant_display_name,
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


@router.get(
    "/platform-connections/{platform_code}/pending-authorizations",
    response_model=PendingAuthorizationResponse,
)
async def list_platform_pending_authorizations(
    platform_code: str,
    status: str = Query("pending_claim", description="待绑定授权状态"),
    mode: str = Query("", description="mock 或 real；为空时使用服务默认模式"),
    authorization: Optional[str] = Header(None),
):
    if platform_code != "alipay":
        raise HTTPException(status_code=400, detail="暂只支持支付宝待绑定授权")
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_list_pending_authorizations(
        auth_token,
        platform_code,
        status=status,
        mode=mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "获取待绑定授权失败"))

    pending_authorizations = result.get("pending_authorizations") or []
    return PendingAuthorizationResponse(
        success=True,
        mode=str(result.get("mode") or mode or "real"),
        platform_code=platform_code,
        pending_authorizations=pending_authorizations,
        count=int(result.get("count") or len(pending_authorizations)),
        message=str(result.get("message") or ""),
    )


@router.post(
    "/platform-connections/{platform_code}/pending-authorizations/{pending_authorization_id}/claim",
    response_model=ClaimPendingAuthorizationResponse,
)
async def claim_platform_pending_authorization(
    platform_code: str,
    pending_authorization_id: str,
    body: ClaimPendingAuthorizationRequest,
    authorization: Optional[str] = Header(None),
):
    if platform_code != "alipay":
        raise HTTPException(status_code=400, detail="暂只支持支付宝待绑定授权")
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await platform_claim_pending_authorization(
        auth_token,
        platform_code,
        pending_authorization_id,
        claim_code=body.claim_code,
        merchant_display_name=body.merchant_display_name,
        mode="real",
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "绑定待绑定授权失败"))

    return ClaimPendingAuthorizationResponse(
        success=True,
        mode=str(result.get("mode") or "real"),
        platform_code=platform_code,
        shop=result.get("shop") or result.get("connection") or {},
        pending_authorization=result.get("pending_authorization") or {},
        warning=str(result.get("warning") or ""),
        message=str(result.get("message") or "支付宝商户授权已绑定"),
    )


@router.get("/platform-auth/callback/{platform_code}")
async def handle_platform_auth_callback(
    platform_code: str,
    request: Request,
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
        callback_payload=dict(request.query_params),
    )

    success = bool(result.get("success"))
    display_message = str(result.get("message") or result.get("error") or "授权失败，请重试")
    redirect_to = _build_callback_redirect_url(
        str(result.get("return_path") or "/"),
        platform_code=platform_code,
        success=success,
        message=display_message,
        shop_name=str(((result.get("connection") or {}).get("external_shop_name")) or ""),
        pending_authorization_id=str(result.get("pending_authorization_id") or ""),
        claim_code=str(result.get("claim_code") or ""),
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
        connection=result.get("connection") or result.get("shop"),
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
    pending_authorization_id: str = "",
    claim_code: str = "",
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
    if pending_authorization_id:
        query_pairs["pending_authorization_id"] = pending_authorization_id
    else:
        query_pairs.pop("pending_authorization_id", None)
    if claim_code:
        query_pairs["claim_code"] = claim_code
    else:
        query_pairs.pop("claim_code", None)

    return urlunsplit(
        (
            "",
            "",
            parsed.path or "/",
            urlencode(query_pairs),
            "",
        )
    )
