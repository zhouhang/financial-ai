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

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse

from config import FINANCE_MCP_UPLOAD_DIR, MAX_FILE_SIZE
from tools.mcp_client import (
    alipay_auth_invite_continue,
    alipay_auth_invite_describe,
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


# ===========================================================================
# 公开（无需登录）支付宝专属授权链接落地页
# ===========================================================================

_LOGO_DATA_URI_CACHE: str | None = None


def _logo_data_uri() -> str:
    """Base64 data URI for the Tally mark, loaded once and cached.

    Inlined as a data URI (not a static URL) so the standalone landing page works regardless
    of the reverse-proxy /api prefix. Falls back to empty string if the asset is missing —
    the brand header then shows only the wordmark.
    """
    global _LOGO_DATA_URI_CACHE
    if _LOGO_DATA_URI_CACHE is None:
        import base64
        from pathlib import Path

        asset = Path(__file__).resolve().parents[2] / "assets" / "tally-mark.png"
        try:
            _LOGO_DATA_URI_CACHE = "data:image/png;base64," + base64.b64encode(asset.read_bytes()).decode("ascii")
        except Exception:
            _LOGO_DATA_URI_CACHE = ""
    return _LOGO_DATA_URI_CACHE


def _invite_html(*, title: str, inner: str) -> str:
    """Render a Tally-branded standalone landing page. `inner` is the card body HTML.

    Self-contained (inline CSS + base64 logo, no external assets / CDN) since this is served by
    data-agent, not the finance-web SPA. Primary color is Tally blue (#2563eb); surface #f5f7fb;
    text #0f172a/#475569; warning #f59e0b.
    """
    logo = _logo_data_uri()
    logo_html = (
        f"<img class='logo' src='{logo}' alt='Tally'/>" if logo
        else "<div class='logo logo-fallback'>T</div>"
    )
    return f"""<!doctype html><html lang='zh'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title} · Tally</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#f5f7fb;color:#0f172a;
  font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',system-ui,sans-serif;
  padding:24px;line-height:1.6}}
.card{{width:100%;max-width:440px;background:#fff;border:1px solid #e2e8f0;border-radius:16px;
  box-shadow:0 8px 30px rgba(15,23,42,.06);overflow:hidden}}
.brand{{display:flex;align-items:center;gap:10px;padding:18px 24px;border-bottom:1px solid #edf2f7}}
.brand .logo{{width:28px;height:28px;border-radius:8px;object-fit:contain;display:block}}
.brand .logo-fallback{{background:#2563eb;color:#fff;font-weight:800;
  display:flex;align-items:center;justify-content:center;font-size:16px}}
.brand .name{{font-weight:700;font-size:15px;color:#0f172a}}
.brand .sub{{font-size:12px;color:#94a3b8;margin-left:auto}}
.body{{padding:24px}}
.eyebrow{{font-size:13px;color:#64748b;margin:0 0 6px}}
.shop{{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 16px;word-break:break-all}}
.hint{{background:#fff7ed;border:1px solid #fed7aa;border-left:3px solid #f59e0b;border-radius:10px;
  padding:10px 12px;font-size:13px;color:#b45309;margin:0 0 16px}}
.desc{{font-size:14px;color:#475569;margin:0 0 20px}}
.btn{{display:block;width:100%;border:0;border-radius:10px;padding:13px 18px;font-size:15px;font-weight:600;
  cursor:pointer;background:#2563eb;color:#fff;transition:background .15s}}
.btn:hover{{background:#1d4ed8}}
.note{{font-size:12px;color:#94a3b8;text-align:center;margin:14px 0 0}}
.status{{display:flex;align-items:center;gap:10px;margin:0 0 12px}}
.status .ic{{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:20px;flex:none}}
.ok .ic{{background:#dcfce7;color:#16a34a}}
.err .ic{{background:#fee2e2;color:#dc2626}}
.status .t{{font-size:17px;font-weight:700}}
.foot{{padding:12px 24px;border-top:1px solid #edf2f7;font-size:12px;color:#94a3b8;text-align:center}}
</style></head>
<body><div class='card'>
<div class='brand'>{logo_html}<div class='name'>Tally</div><div class='sub'>智能财务助手</div></div>
<div class='body'>{inner}</div>
<div class='foot'>授权在支付宝官方页面完成 · Tally 不会获取你的支付宝密码</div>
</div></body></html>"""


@router.get("/p/alipay-auth", response_class=HTMLResponse)
async def alipay_invite_landing(t: str = Query("", description="invite token")):
    import html as _html

    info = await alipay_auth_invite_describe(t)
    if not info.get("valid"):
        inner = (
            "<div class='status err'><div class='ic'>!</div><div class='t'>链接无效或已过期</div></div>"
            "<p class='desc'>该授权链接无法使用,可能已过期(默认 30 天)或被改动。请联系对接人重新生成专属授权链接。</p>"
        )
        return HTMLResponse(_invite_html(title="链接已失效", inner=inner), status_code=400)

    shop = _html.escape(str(info.get("merchant_display_name", "")))
    if info.get("already_authorized"):
        inner = (
            "<div class='status ok'><div class='ic'>✓</div><div class='t'>该店铺已完成授权</div></div>"
            f"<p class='eyebrow'>店铺</p><p class='shop'>{shop}</p>"
            "<p class='desc'>支付宝数据采集授权已生效,无需重复操作。</p>"
        )
        return HTMLResponse(_invite_html(title="已授权", inner=inner))

    acct = _html.escape(str(info.get("expected_alipay_account", "")))
    acct_hint = (
        f"<div class='hint'>请务必使用账号 <b>{acct}</b> 登录支付宝,登错账号会把数据绑到错误的主体。</div>"
        if acct else ""
    )
    # 表单不写死 action,提交到当前文档 URL(浏览器自动带上反向代理前缀如 /api 与 ?t=)。
    inner = (
        "<p class='eyebrow'>正在为以下店铺授权支付宝数据采集</p>"
        f"<p class='shop'>{shop}</p>"
        f"{acct_hint}"
        "<p class='desc'>点击下方按钮前往支付宝完成授权,授权后 Tally 即可自动采集该店铺的资金/订单账单用于对账。</p>"
        "<form method='post'>"
        f"<input type='hidden' name='t' value='{_html.escape(t)}'/>"
        "<button class='btn' type='submit'>前往支付宝授权</button>"
        "</form>"
    )
    return HTMLResponse(_invite_html(title="支付宝授权", inner=inner))


@router.post("/p/alipay-auth")
async def alipay_invite_continue_route(request: Request):
    # token 同时可能在 query(?t=)和 form body(隐藏字段)里,取任一。
    form = await request.form()
    token = str(form.get("t") or request.query_params.get("t") or "")
    result = await alipay_auth_invite_continue(token)
    if not result.get("success") or not result.get("auth_url"):
        import html as _html
        msg = _html.escape(str(result.get("error") or "请稍后重试"))
        inner = (
            "<div class='status err'><div class='ic'>!</div><div class='t'>无法发起授权</div></div>"
            f"<p class='desc'>{msg}</p>"
        )
        return HTMLResponse(_invite_html(title="无法继续", inner=inner), status_code=400)
    return RedirectResponse(url=str(result["auth_url"]), status_code=303)

