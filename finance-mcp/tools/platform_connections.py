"""平台连接 MCP 工具。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from mcp import Tool

from auth import db as auth_db
from auth.jwt_utils import get_user_from_token
from platforms.base import PlatformAppConfig
from platforms.factory import build_connector

logger = logging.getLogger("tools.platform_connections")

SUPPORTED_PLATFORMS: tuple[dict[str, str], ...] = (
    {"platform_code": "taobao", "platform_name": "淘宝/天猫", "status": "supported"},
    {"platform_code": "douyin_shop", "platform_name": "抖店", "status": "supported"},
    {"platform_code": "kuaishou", "platform_name": "快手小店", "status": "planned"},
    {"platform_code": "jd", "platform_name": "京东", "status": "planned"},
)

TAOBAO_ORDER_SYNC_STRATEGY: dict[str, Any] = {
    "mode": "full_then_incremental",
    "schedule_type": "cron",
    "schedule_expr": "0 */2 * * *",
    "lookback_minutes": 10,
    "page_size": 100,
    "initial_days": 1,
    "initial_end_offset_days": 1,
}

TAOBAO_ORDER_EXTRACT_CONFIG: dict[str, Any] = {
    "storage": "platform_order_lines",
    "platform_code": "taobao",
    "date_field": "biz_date",
    "api": {
        "init_method": "taobao.trades.sold.get",
        "incremental_method": "taobao.trades.sold.increment.get",
    },
}

_RAW_AUTH_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "session_key",
    "top_session",
    "sub_taobao_user_id",
    "sub_taobao_user_nick",
}


def create_tools() -> list[Tool]:
    return [
        Tool(
            name="platform_list_connections",
            description="获取当前企业的平台连接概览或某个平台下的店铺连接列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "platform_code": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="platform_create_auth_session",
            description="创建店铺授权会话，返回授权链接。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "platform_code": {"type": "string"},
                    "return_path": {"type": "string"},
                    "redirect_uri": {"type": "string"},
                    "shop_connection_id": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "platform_code"],
            },
        ),
        Tool(
            name="platform_handle_auth_callback",
            description="处理平台授权回调，完成 token 与店铺绑定。",
            inputSchema={
                "type": "object",
                "properties": {
                    "platform_code": {"type": "string"},
                    "state": {"type": "string"},
                    "code": {"type": "string"},
                    "error": {"type": "string"},
                    "error_description": {"type": "string"},
                    "callback_payload": {"type": "object"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["platform_code", "state"],
            },
        ),
        Tool(
            name="platform_reauthorize_shop",
            description="为现有店铺重新发起授权。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "shop_connection_id": {"type": "string"},
                    "return_path": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "shop_connection_id"],
            },
        ),
        Tool(
            name="platform_disable_shop",
            description="停用某个店铺连接。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "shop_connection_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "shop_connection_id"],
            },
        ),
        Tool(
            name="platform_get_shop_detail",
            description="获取单个店铺连接详情。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "shop_connection_id": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "shop_connection_id"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "platform_list_connections":
        return await _handle_list_connections(arguments)
    if name == "platform_create_auth_session":
        return await _handle_create_auth_session(arguments)
    if name == "platform_handle_auth_callback":
        return await _handle_auth_callback(arguments)
    if name == "platform_reauthorize_shop":
        return await _handle_reauthorize_shop(arguments)
    if name == "platform_disable_shop":
        return await _handle_disable_shop(arguments)
    if name == "platform_get_shop_detail":
        return await _handle_get_shop_detail(arguments)
    return {"success": False, "error": f"未知工具: {name}"}


def _require_user(auth_token: str) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("未提供认证 token，请先登录")
    user = get_user_from_token(token)
    if not user:
        raise ValueError("token 无效或已过期，请重新登录")
    if not user.get("company_id"):
        raise ValueError("当前用户未绑定公司，无法配置平台连接")
    return user


def _normalize_mode(mode: Any) -> str:
    normalized = str(mode or "").strip().lower()
    return normalized if normalized in {"mock", "real"} else "mock"


def _normalize_platform_code(platform_code: Any) -> str:
    normalized = str(platform_code or "").strip()
    return "taobao" if normalized == "tmall" else normalized


def _safe_raw_auth_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        normalized_key = str(key or "").strip()
        if normalized_key.lower() in _RAW_AUTH_SECRET_KEYS:
            cleaned[normalized_key] = "***REDACTED***"
        else:
            cleaned[normalized_key] = value
    return cleaned


def _platform_name(platform_code: str) -> str:
    matched = next((item["platform_name"] for item in SUPPORTED_PLATFORMS if item["platform_code"] == platform_code), "")
    return matched or platform_code


def _build_mock_app_config(company_id: str, platform_code: str, redirect_uri: str = "") -> PlatformAppConfig:
    resolved_redirect_uri = redirect_uri or f"https://tally-placeholder.example.com/api/platform-auth/callback/{platform_code}"
    record = auth_db.upsert_platform_app(
        company_id=company_id,
        platform_code=platform_code,
        app_key=f"mock_{platform_code}",
        app_secret="mock_secret",
        app_name=f"{_platform_name(platform_code)} Mock App",
        app_type="system",
        auth_base_url="",
        token_url="",
        refresh_url="",
        scopes_config=[],
        extra={"mode": "mock", "redirect_uri": resolved_redirect_uri},
        status="active",
        include_secrets=True,
    )
    return PlatformAppConfig(
        id=str((record or {}).get("id") or ""),
        company_id=str((record or {}).get("company_id") or company_id),
        platform_code=platform_code,
        app_name=str((record or {}).get("app_name") or ""),
        app_key=str((record or {}).get("app_key") or ""),
        app_secret=str((record or {}).get("app_secret") or ""),
        app_type=str((record or {}).get("app_type") or "system"),
        auth_base_url=str((record or {}).get("auth_base_url") or ""),
        token_url=str((record or {}).get("token_url") or ""),
        refresh_url=str((record or {}).get("refresh_url") or ""),
        redirect_uri=str(((record or {}).get("extra") or {}).get("redirect_uri") or resolved_redirect_uri),
        scopes=list((record or {}).get("scopes_config") or []),
        extra=dict((record or {}).get("extra") or {}),
        status=str((record or {}).get("status") or "active"),
        auth_mode="mock",
    )


def _load_app_config(
    company_id: str,
    platform_code: str,
    *,
    mode: str,
    redirect_uri: str = "",
) -> PlatformAppConfig:
    record = auth_db.get_platform_app(
        company_id=company_id,
        platform_code=platform_code,
        include_secrets=True,
    )
    if record is None:
        return _build_mock_app_config(company_id, platform_code, redirect_uri=redirect_uri)
    auth_mode = _normalize_mode(
        mode or ((record.get("extra") or {}).get("mode") if isinstance(record.get("extra"), dict) else "")
    )
    return PlatformAppConfig(
        id=str(record.get("id") or ""),
        company_id=str(record.get("company_id") or "") or None,
        platform_code=str(record.get("platform_code") or platform_code),
        app_name=str(record.get("app_name") or ""),
        app_key=str(record.get("app_key") or ""),
        app_secret=str(record.get("app_secret") or ""),
        app_type=str(record.get("app_type") or "isv"),
        auth_base_url=str(record.get("auth_base_url") or ""),
        token_url=str(record.get("token_url") or ""),
        refresh_url=str(record.get("refresh_url") or ""),
        redirect_uri=str(redirect_uri or ((record.get("extra") or {}).get("redirect_uri")) or f"https://tally-placeholder.example.com/api/platform-auth/callback/{platform_code}"),
        scopes=list(record.get("scopes_config") or []),
        extra=dict(record.get("extra") or {}),
        status=str(record.get("status") or "active"),
        auth_mode=auth_mode,
    )


def _compute_expire_at(seconds: int | None) -> str | None:
    if not seconds:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=int(seconds))).isoformat()


def _dataset_code_suffix(shop_connection_id: str) -> str:
    suffix = "".join(
        ch if ch.isalnum() else "_"
        for ch in str(shop_connection_id or "").strip().lower()
    ).strip("_")
    return (suffix or "shop")[:12]


def _source_code_suffix(shop_connection_id: str) -> str:
    suffix = "".join(
        ch if ch.isalnum() else "_"
        for ch in str(shop_connection_id or "").strip().lower()
    ).strip("_")
    return suffix or "shop"


def build_taobao_order_line_dataset_payload(
    *,
    company_id: str,
    data_source_id: str,
    shop_connection_id: str,
    shop_name: str,
    external_shop_id: str,
) -> dict[str, Any]:
    """构建淘宝/天猫店铺订单明细数据集目录 payload。"""
    display_shop_name = str(shop_name or "").strip() or "未命名店铺"
    extract_config = {
        **TAOBAO_ORDER_EXTRACT_CONFIG,
        "shop_connection_id": shop_connection_id,
        "external_shop_id": str(external_shop_id or ""),
    }
    return {
        "company_id": company_id,
        "data_source_id": data_source_id,
        "dataset_code": f"taobao_order_lines_{_dataset_code_suffix(shop_connection_id)}",
        "dataset_name": f"淘宝/天猫订单明细 - {display_shop_name}"[:255],
        "resource_key": f"taobao_order_lines:{shop_connection_id}",
        "dataset_kind": "api_endpoint",
        "origin_type": "fixed",
        "publish_status": "published",
        "business_domain": "ecommerce",
        "business_object_type": "platform_order",
        "grain": "shop_order_line",
        "extract_config": extract_config,
        "schema_summary": {
            "source": "taobao_order_lines",
            "storage": "platform_order_lines",
            "columns": [],
        },
        "sync_strategy": dict(TAOBAO_ORDER_SYNC_STRATEGY),
        "status": "active",
        "is_enabled": True,
        "health_status": "unknown",
        "meta": {
            "platform_code": "taobao",
            "shop_connection_id": shop_connection_id,
            "shop_name": display_shop_name,
            "external_shop_id": str(external_shop_id or ""),
        },
    }


def build_taobao_initial_collection_job_payloads(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    shop_connection_id: str,
    anchor_date: str | date | datetime | None = None,
) -> list[dict[str, Any]]:
    """构建淘宝/天猫 T-1 初始化采集任务 payload；本任务只生成，不触发。"""
    if isinstance(anchor_date, datetime):
        resolved_anchor = anchor_date.date()
    elif isinstance(anchor_date, date):
        resolved_anchor = anchor_date
    elif anchor_date:
        resolved_anchor = date.fromisoformat(str(anchor_date))
    else:
        resolved_anchor = datetime.now(timezone.utc).date()

    return _build_taobao_initial_collection_jobs(
        source_id=data_source_id,
        dataset_id=dataset_id,
        resource_key=f"taobao_order_lines:{shop_connection_id}",
        sync_strategy=TAOBAO_ORDER_SYNC_STRATEGY,
        anchor_date=resolved_anchor,
    )


def _build_taobao_initial_collection_jobs(
    *,
    source_id: str,
    dataset_id: str,
    resource_key: str,
    sync_strategy: dict[str, Any],
    anchor_date: date | None = None,
) -> list[dict[str, Any]]:
    """构建淘宝/天猫 T-1 初始化采集任务 payload。"""
    resolved_anchor = anchor_date or datetime.now(timezone(timedelta(hours=8))).date()
    initial_days = max(1, int(sync_strategy.get("initial_days") or 90))
    end_offset_days = max(1, int(sync_strategy.get("initial_end_offset_days") or 1))
    end_biz_date = resolved_anchor - timedelta(days=end_offset_days)
    start_biz_date = end_biz_date - timedelta(days=initial_days - 1)
    jobs: list[dict[str, Any]] = []
    for day_offset in range(initial_days):
        biz_date = start_biz_date + timedelta(days=day_offset)
        biz_date_text = biz_date.isoformat()
        jobs.append(
            {
                "source_id": source_id,
                "dataset_id": dataset_id,
                "resource_key": resource_key,
                "trigger_mode": "initial",
                "idempotency_key": f"taobao-initial:{dataset_id}:{biz_date_text}",
                "background": True,
                "params": {
                    "dataset_id": dataset_id,
                    "resource_key": resource_key,
                    "biz_date": biz_date_text,
                    "force_mode": "initial",
                },
            }
        )
    return jobs


def _upsert_taobao_order_line_dataset(
    *,
    company_id: str,
    connection: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    shop_connection_id = str(connection.get("id") or "")
    shop_name = str(connection.get("external_shop_name") or "")
    source = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=f"platform_oauth_taobao_{_source_code_suffix(shop_connection_id)}",
        name=f"淘宝/天猫授权 - {shop_name or shop_connection_id}"[:255],
        source_kind="platform_oauth",
        domain_type="ecommerce",
        provider_code="taobao",
        execution_mode="deterministic",
        description="淘宝/天猫店铺 OAuth 授权数据源",
        status="active",
        is_enabled=True,
        health_status="unknown",
        last_error_message="",
        meta={
            "platform_code": "taobao",
            "shop_connection_id": shop_connection_id,
            "external_shop_id": str(connection.get("external_shop_id") or ""),
            "shop_name": shop_name,
        },
    )
    if source is None:
        raise ValueError("保存淘宝/天猫数据源失败")

    dataset_payload = build_taobao_order_line_dataset_payload(
        company_id=company_id,
        data_source_id=str(source["id"]),
        shop_connection_id=shop_connection_id,
        shop_name=shop_name,
        external_shop_id=str(connection.get("external_shop_id") or ""),
    )
    dataset = auth_db.upsert_unified_data_source_dataset(**dataset_payload)
    if dataset is None:
        raise ValueError("保存淘宝/天猫订单明细数据集失败")
    return source, dataset


async def _run_taobao_initial_collection_jobs(
    *,
    company_id: str,
    jobs: list[dict[str, Any]],
) -> None:
    """按日期顺序串行执行淘宝/天猫 T-1 初始化采集任务。"""
    from tools import data_sources

    for job_payload in jobs:
        try:
            await data_sources.trigger_dataset_collection_for_company(
                company_id=company_id,
                source_id=str(job_payload.get("source_id") or ""),
                dataset_id=str(job_payload.get("dataset_id") or ""),
                resource_key=str(job_payload.get("resource_key") or ""),
                trigger_mode=str(job_payload.get("trigger_mode") or "initial"),
                idempotency_key=str(job_payload.get("idempotency_key") or ""),
                background=False,
                params=dict(job_payload.get("params") or {}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "淘宝/天猫初始化采集任务执行失败: company_id=%s dataset_id=%s resource_key=%s error=%s",
                company_id,
                job_payload.get("dataset_id"),
                job_payload.get("resource_key"),
                exc,
                exc_info=True,
            )


def _build_shop_view(connection: dict[str, Any]) -> dict[str, Any]:
    shop_id = str(connection.get("id") or "")
    company_id = str(connection.get("company_id") or "")
    auth = auth_db.get_current_shop_authorization(shop_connection_id=shop_id)
    sync_sources = auth_db.list_sync_sources(company_id=company_id, shop_connection_id=shop_id)
    sync_last = max(
        [item.get("last_sync_at") for item in sync_sources if item.get("last_sync_at")],
        default=None,
    )
    last_status = next(
        (item.get("last_status") for item in sync_sources if str(item.get("last_status") or "") in {"error", "failed", "running"}),
        sync_sources[0].get("last_status") if sync_sources else None,
    )
    auth_status = str((auth or {}).get("auth_status") or "")
    display_status = "disabled" if str(connection.get("status") or "") == "disabled" else (auth_status or "authorized")
    return {
        **connection,
        "platform_name": _platform_name(str(connection.get("platform_code") or "")),
        "auth_status": auth_status or display_status,
        "status": display_status,
        "token_status": auth_status or display_status,
        "token_expires_at": (auth or {}).get("token_expires_at"),
        "last_refresh_at": (auth or {}).get("last_refresh_at"),
        "last_sync_at": sync_last,
        "last_status": last_status,
    }


async def _handle_list_connections(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    shops_all = [
        _build_shop_view(connection)
        for connection in auth_db.list_shop_connections(company_id=company_id)
    ]
    if platform_code:
        shops = [shop for shop in shops_all if shop.get("platform_code") == platform_code]
        return {
            "success": True,
            "platform_code": platform_code,
            "connections": shops,
            "count": len(shops),
            "mode": _normalize_mode(arguments.get("mode")),
        }

    summaries = []
    for platform in SUPPORTED_PLATFORMS:
        shops = [shop for shop in shops_all if shop.get("platform_code") == platform["platform_code"]]
        active = [shop for shop in shops if str(shop.get("status") or "") != "disabled"]
        errors = [
            shop for shop in shops
            if str(shop.get("status") or "") in {"reauth_required", "sync_error", "token_expired", "error", "failed"}
            or str(shop.get("last_status") or "") in {"error", "failed"}
        ]
        configured_app = auth_db.get_platform_app(company_id=company_id, platform_code=platform["platform_code"])
        summaries.append(
            {
                **platform,
                "configured": configured_app is not None,
                "authorized_shop_count": len(active),
                "error_shop_count": len(errors),
                "last_sync_at": max(
                    [shop.get("last_sync_at") for shop in shops if shop.get("last_sync_at")],
                    default=None,
                ),
            }
        )
    return {"success": True, "platforms": summaries, "connections": shops_all, "count": len(summaries), "mode": _normalize_mode(arguments.get("mode"))}


async def _handle_create_auth_session(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    if platform_code not in {item["platform_code"] for item in SUPPORTED_PLATFORMS}:
        return {"success": False, "error": f"暂不支持的平台: {platform_code}"}

    mode = _normalize_mode(arguments.get("mode"))
    redirect_uri = str(arguments.get("redirect_uri") or "").strip()
    app_config = _load_app_config(company_id, platform_code, mode=mode, redirect_uri=redirect_uri)
    connector = build_connector(app_config)
    state_token = str(uuid.uuid4())
    auth_session = auth_db.create_auth_session(
        company_id=company_id,
        platform_code=platform_code,
        operator_user_id=str(user.get("user_id") or ""),
        shop_connection_id=str(arguments.get("shop_connection_id") or "") or None,
        state_token=state_token,
        return_path=str(arguments.get("return_path") or "/"),
        redirect_uri=app_config.redirect_uri,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    )
    if auth_session is None:
        return {"success": False, "error": "创建授权会话失败"}

    auth_url = connector.build_auth_url(state=str(auth_session.get("state_token") or ""))
    if app_config.auth_mode == "mock":
        redirect_target = urlsplit(str(app_config.redirect_uri or ""))
        redirect_path = redirect_target.path or f"/api/platform-auth/callback/{platform_code}"
        auth_url = (
            f"{redirect_path}?state={auth_session.get('state_token')}"
            f"&code=mock_code_{state_token[:8]}&mode=mock"
        )
    return {
        "success": True,
        "session": auth_session,
        "platform_code": platform_code,
        "auth_mode": app_config.auth_mode,
        "auth_url": auth_url,
        "requires_mock_authorize": app_config.auth_mode == "mock",
        "session_id": str(auth_session.get("id") or ""),
        "state": str(auth_session.get("state_token") or ""),
        "mode": app_config.auth_mode,
        "expires_in": 1800,
        "message": "已生成授权链接",
    }


async def _handle_auth_callback(arguments: dict[str, Any]) -> dict[str, Any]:
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    state = str(arguments.get("state") or "").strip()
    code = str(arguments.get("code") or "").strip()
    error = str(arguments.get("error") or "").strip()
    error_description = str(arguments.get("error_description") or "").strip()
    callback_payload = dict(arguments.get("callback_payload") or {})

    auth_session = auth_db.get_auth_session_by_state(state)
    if auth_session is None:
        return {"success": False, "error": "授权会话不存在或已失效"}
    if _normalize_platform_code(auth_session.get("platform_code")) != platform_code:
        return {"success": False, "error": "平台与授权会话不匹配"}
    if str(auth_session.get("status") or "") != "pending":
        return {"success": False, "error": "授权会话已处理，请勿重复提交"}

    company_id = str(auth_session.get("company_id") or "")
    if error:
        auth_db.update_auth_session_callback(
            session_id=str(auth_session["id"]),
            status="failed",
            callback_code=code,
            callback_error=error_description or error,
            callback_payload=callback_payload,
        )
        return {
            "success": False,
            "platform_code": platform_code,
            "error": error,
            "message": error_description or "授权失败，请重试",
            "return_path": str(auth_session.get("return_path") or "/"),
            "mode": _normalize_mode(arguments.get("mode")),
        }
    try:
        app_config = _load_app_config(
            company_id,
            platform_code,
            mode=arguments.get("mode"),
            redirect_uri=str(auth_session.get("redirect_uri") or ""),
        )
        connector = build_connector(app_config)
        token_bundle = connector.exchange_code_for_token(
            code=code or f"mock_{state[-8:]}",
            auth_session=auth_session,
            callback_payload=callback_payload,
        )
        shop_profile = connector.fetch_shop_profile(
            token_bundle=token_bundle,
            auth_session=auth_session,
            callback_payload=callback_payload,
        )
        connection = auth_db.upsert_shop_connection(
            company_id=company_id,
            platform_code=platform_code,
            external_shop_id=shop_profile.external_shop_id,
            external_shop_name=shop_profile.external_shop_name,
            external_seller_id=shop_profile.external_seller_id,
            auth_subject_name=shop_profile.auth_subject_name,
            shop_type=shop_profile.shop_type,
            status="active",
            meta=shop_profile.metadata,
        )
        if connection is None:
            raise ValueError("保存店铺连接失败")

        authorization = auth_db.create_shop_authorization(
            company_id=company_id,
            shop_connection_id=str(connection["id"]),
            platform_app_id=str(app_config.id or ""),
            auth_type="oauth_code",
            access_token=token_bundle.access_token,
            refresh_token=token_bundle.refresh_token,
            token_expires_at=_compute_expire_at(token_bundle.expires_in),
            refresh_expires_at=_compute_expire_at(token_bundle.refresh_expires_in),
            scope_text=token_bundle.scope_text,
            auth_status="authorized",
            last_error="",
            raw_auth_payload=_safe_raw_auth_payload(token_bundle.raw_payload),
        )
        source_types = ["orders"] if platform_code == "taobao" else ["orders", "refunds", "settlements", "bills"]
        for source_type in source_types:
            auth_db.upsert_sync_source(
                company_id=company_id,
                shop_connection_id=str(connection["id"]),
                source_type=source_type,
            )
        taobao_source: dict[str, Any] | None = None
        taobao_dataset: dict[str, Any] | None = None
        dataset_warning = ""
        if platform_code == "taobao":
            try:
                taobao_source, taobao_dataset = _upsert_taobao_order_line_dataset(
                    company_id=company_id,
                    connection=connection,
                )
                if taobao_source and taobao_dataset:
                    asyncio.create_task(
                        _run_taobao_initial_collection_jobs(
                            company_id=company_id,
                            jobs=_build_taobao_initial_collection_jobs(
                                source_id=str(taobao_source["id"]),
                                dataset_id=str(taobao_dataset["id"]),
                                resource_key=str(taobao_dataset.get("resource_key") or ""),
                                sync_strategy=dict(
                                    taobao_dataset.get("sync_strategy") or TAOBAO_ORDER_SYNC_STRATEGY
                                ),
                            ),
                        )
                    )
            except Exception as dataset_exc:  # noqa: BLE001
                dataset_warning = str(dataset_exc)
                logger.error(
                    "淘宝/天猫授权成功但订单数据集创建失败: company_id=%s shop_connection_id=%s error=%s",
                    company_id,
                    connection.get("id"),
                    dataset_warning,
                    exc_info=True,
                )
        auth_db.update_auth_session_callback(
            session_id=str(auth_session["id"]),
            status="authorized",
            callback_code=code,
            callback_error=dataset_warning,
            callback_payload={
                **callback_payload,
                "shop_connection_id": str(connection["id"]),
                "shop_authorization_id": str((authorization or {}).get("id") or ""),
                "taobao_data_source_id": str((taobao_source or {}).get("id") or ""),
                "taobao_order_dataset_id": str((taobao_dataset or {}).get("id") or ""),
                "taobao_order_dataset_warning": dataset_warning,
            },
        )
        detail = _build_shop_view(
            auth_db.get_shop_connection_by_id(str(connection["id"])) or connection
        )
        return {
            "success": True,
            "platform_code": platform_code,
            "auth_session": auth_db.get_auth_session_by_state(state),
            "shop": detail,
            "connection": detail,
            "message": f"{_platform_name(platform_code)}授权成功",
            "warning": dataset_warning,
            "return_path": str(auth_session.get("return_path") or "/"),
            "mode": app_config.auth_mode,
        }
    except Exception as exc:
        logger.error("处理平台授权回调失败: %s", exc, exc_info=True)
        auth_db.update_auth_session_callback(
            session_id=str(auth_session["id"]),
            status="failed",
            callback_code=code,
            callback_error=str(exc),
            callback_payload=callback_payload,
        )
        return {
            "success": False,
            "error": str(exc),
            "message": str(exc),
            "platform_code": platform_code,
            "return_path": str(auth_session.get("return_path") or "/"),
            "mode": _normalize_mode(arguments.get("mode")),
        }


async def _handle_reauthorize_shop(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    shop_connection_id = str(arguments.get("shop_connection_id") or "").strip()
    if not shop_connection_id:
        return {"success": False, "error": "缺少 shop_connection_id"}
    detail = auth_db.get_shop_connection_by_id(shop_connection_id)
    if detail is None or str(detail.get("company_id") or "") != str(user["company_id"]):
        return {"success": False, "error": "店铺连接不存在"}
    return await _handle_create_auth_session(
        {
            "auth_token": arguments.get("auth_token", ""),
            "platform_code": detail.get("platform_code"),
            "return_path": arguments.get("return_path", "/"),
            "shop_connection_id": shop_connection_id,
            "mode": arguments.get("mode", ""),
        }
    )


async def _handle_disable_shop(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    shop_connection_id = str(arguments.get("shop_connection_id") or "").strip()
    detail = auth_db.get_shop_connection_by_id(shop_connection_id)
    if detail is None or str(detail.get("company_id") or "") != str(user["company_id"]):
        return {"success": False, "error": "店铺连接不存在"}
    if not auth_db.update_shop_connection_status(shop_connection_id=shop_connection_id, status="disabled"):
        return {"success": False, "error": "停用店铺连接失败"}
    authorization = auth_db.get_current_shop_authorization(shop_connection_id=shop_connection_id)
    if authorization:
        auth_db.update_shop_authorization_status(
            authorization_id=str(authorization["id"]),
            auth_status="revoked",
            last_error=str(arguments.get("reason") or ""),
            is_current=False,
        )
    return {"success": True, "message": "店铺连接已停用"}


async def _handle_get_shop_detail(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    shop_connection_id = str(arguments.get("shop_connection_id") or "").strip()
    detail = auth_db.get_shop_connection_by_id(shop_connection_id)
    if detail is None or str(detail.get("company_id") or "") != str(user["company_id"]):
        return {"success": False, "error": "店铺连接不存在"}
    authorization = auth_db.get_current_shop_authorization(shop_connection_id=shop_connection_id)
    sync_sources = auth_db.list_sync_sources(company_id=str(user["company_id"]), shop_connection_id=shop_connection_id)
    return {
        "success": True,
        "shop": _build_shop_view(detail),
        "connection": _build_shop_view(detail),
        "authorization": authorization or {},
        "sync_sources": sync_sources,
        "mode": _normalize_mode(arguments.get("mode")),
    }
