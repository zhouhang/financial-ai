"""平台连接 MCP 工具。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from mcp import Tool

from app_config import SERVICE_PROVIDER_COMPANY_ID
from auth import db as auth_db
from auth.jwt_utils import get_user_from_token
from platforms.base import PlatformAppConfig
from platforms.factory import build_connector

logger = logging.getLogger("tools.platform_connections")

SUPPORTED_PLATFORMS: tuple[dict[str, str], ...] = (
    {"platform_code": "taobao", "platform_name": "淘宝/天猫", "status": "supported"},
    {"platform_code": "alipay", "platform_name": "支付宝", "status": "supported"},
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

ALIPAY_BILL_SYNC_STRATEGY: dict[str, Any] = {
    "mode": "daily_t_minus_1",
    "schedule_type": "cron",
    "schedule_expr": "30 10 * * *",
    "initial_days": 1,
    "initial_end_offset_days": 1,
    "date_field": "bill_date",
}

ALIPAY_BILL_DATASETS: tuple[dict[str, str], ...] = (
    {
        "bill_kind": "fund",
        "bill_type": "signcustomer",
        "label": "支付宝资金账单",
        "business_object_type": "platform_fund_bill",
        "grain": "merchant_bill_line",
    },
    {
        "bill_kind": "trade",
        "bill_type": "trade",
        "label": "支付宝交易账单",
        "business_object_type": "platform_trade_bill",
        "grain": "merchant_trade_bill_line",
    },
)

_RAW_AUTH_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "session_key",
    "top_session",
    "sub_taobao_user_id",
    "sub_taobao_user_nick",
    "app_auth_token",
    "app_refresh_token",
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
                    "merchant_display_name": {"type": "string", "description": "支付宝商户显示名称"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "platform_code"],
            },
        ),
        Tool(
            name="platform_get_app_config",
            description="获取平台应用配置状态（不返回 AppSecret 明文）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "platform_code": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "platform_code"],
            },
        ),
        Tool(
            name="platform_upsert_app_config",
            description="保存平台应用配置，用于真实 OAuth 授权。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "platform_code": {"type": "string"},
                    "app_key": {"type": "string"},
                    "app_secret": {"type": "string"},
                    "redirect_uri": {"type": "string"},
                    "app_public_cert": {"type": "string"},
                    "alipay_public_cert": {"type": "string"},
                    "alipay_root_cert": {"type": "string"},
                    "merchant_auth_mode": {"type": "string"},
                    "merchant_auth_pc_url": {"type": "string"},
                    "merchant_auth_qr_url": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "platform_code", "app_key", "redirect_uri"],
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
        Tool(
            name="platform_list_pending_authorizations",
            description="获取支付宝待绑定商家授权列表，不返回 token 明文。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "platform_code": {"type": "string"},
                    "status": {"type": "string", "description": "pending_claim、claimed、expired、failed、discarded"},
                    "limit": {"type": "number"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "platform_code"],
            },
        ),
        Tool(
            name="platform_claim_pending_authorization",
            description="用隐藏校验信息将支付宝待绑定授权绑定到当前企业。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "platform_code": {"type": "string"},
                    "pending_authorization_id": {"type": "string"},
                    "claim_code": {"type": "string"},
                    "merchant_display_name": {"type": "string"},
                    "mode": {"type": "string", "description": "mock 或 real"},
                },
                "required": ["auth_token", "platform_code", "claim_code"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "platform_list_connections":
        return await _handle_list_connections(arguments)
    if name == "platform_create_auth_session":
        return await _handle_create_auth_session(arguments)
    if name == "platform_get_app_config":
        return await _handle_get_app_config(arguments)
    if name == "platform_upsert_app_config":
        return await _handle_upsert_app_config(arguments)
    if name == "platform_handle_auth_callback":
        return await _handle_auth_callback(arguments)
    if name == "platform_reauthorize_shop":
        return await _handle_reauthorize_shop(arguments)
    if name == "platform_disable_shop":
        return await _handle_disable_shop(arguments)
    if name == "platform_get_shop_detail":
        return await _handle_get_shop_detail(arguments)
    if name == "platform_list_pending_authorizations":
        return await _handle_list_pending_authorizations(arguments)
    if name == "platform_claim_pending_authorization":
        return await _handle_claim_pending_authorization(arguments)
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
    return normalized if normalized in {"mock", "real"} else "real"


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


def _generate_claim_code() -> str:
    return f"ALIPAY-{uuid.uuid4().hex[:8].upper()}"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pending_authorization_expired(pending: dict[str, Any]) -> bool:
    expires_at = _parse_datetime(pending.get("expires_at"))
    return expires_at is not None and expires_at <= datetime.now(timezone.utc)


def _public_pending_authorization(record: dict[str, Any] | None) -> dict[str, Any]:
    pending = dict(record or {})
    pending["access_token"] = ""
    pending["refresh_token"] = ""
    raw_payload = pending.get("raw_auth_payload") if isinstance(pending.get("raw_auth_payload"), dict) else {}
    pending["raw_auth_payload"] = _safe_raw_auth_payload(raw_payload)
    return pending


def _platform_name(platform_code: str) -> str:
    matched = next((item["platform_name"] for item in SUPPORTED_PLATFORMS if item["platform_code"] == platform_code), "")
    return matched or platform_code


def _supported_platform_codes() -> set[str]:
    return {item["platform_code"] for item in SUPPORTED_PLATFORMS}


def _platform_app_owner_company_id() -> str:
    return SERVICE_PROVIDER_COMPANY_ID


def _can_configure_service_provider_app(user: dict[str, Any]) -> bool:
    role = str(user.get("role") or user.get("user_role") or "").strip().lower()
    return role in {"admin", "owner", "super_admin"}


def _public_app_config(record: dict[str, Any] | None, *, platform_code: str) -> dict[str, Any]:
    extra = record.get("extra") if isinstance((record or {}).get("extra"), dict) else {}
    return {
        "id": str((record or {}).get("id") or ""),
        "platform_code": platform_code,
        "platform_name": _platform_name(platform_code),
        "app_name": str((record or {}).get("app_name") or ""),
        "app_key": str((record or {}).get("app_key") or ""),
        "app_secret": "",
        "has_app_secret": bool(str((record or {}).get("app_secret") or "").strip()),
        "has_app_public_cert": bool(str(extra.get("app_public_cert") or "").strip()),
        "has_alipay_public_cert": bool(str(extra.get("alipay_public_cert") or "").strip()),
        "has_alipay_root_cert": bool(str(extra.get("alipay_root_cert") or "").strip()),
        "redirect_uri": str(extra.get("redirect_uri") or ""),
        "auth_base_url": str((record or {}).get("auth_base_url") or ""),
        "token_url": str((record or {}).get("token_url") or ""),
        "refresh_url": str((record or {}).get("refresh_url") or ""),
        "merchant_auth_mode": str(extra.get("merchant_auth_mode") or "static_invite"),
        "merchant_auth_pc_url": str(extra.get("merchant_auth_pc_url") or ""),
        "merchant_auth_qr_url": str(extra.get("merchant_auth_qr_url") or ""),
        "status": str((record or {}).get("status") or ""),
    }


def _default_app_urls(platform_code: str) -> dict[str, str]:
    if platform_code == "taobao":
        return {
            "auth_base_url": "https://oauth.taobao.com/authorize",
            "token_url": "https://oauth.taobao.com/token",
            "refresh_url": "",
        }
    if platform_code == "alipay":
        return {
            "auth_base_url": "https://openauth.alipay.com/oauth2/appToAppAuth.htm",
            "token_url": "https://openapi.alipay.com/gateway.do",
            "refresh_url": "https://openapi.alipay.com/gateway.do",
        }
    return {"auth_base_url": "", "token_url": "", "refresh_url": ""}


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


def _is_mock_app_record(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
    if str(extra.get("mode") or "").strip().lower() == "mock":
        return True
    return str(record.get("app_key") or "").strip().lower().startswith("mock_")


def _load_app_config(
    company_id: str,
    platform_code: str,
    *,
    mode: str,
    redirect_uri: str = "",
) -> PlatformAppConfig:
    owner_company_id = _platform_app_owner_company_id()
    record = auth_db.get_platform_app(
        company_id=owner_company_id,
        platform_code=platform_code,
        include_secrets=True,
    )
    requested_mode = _normalize_mode(mode)
    if record is None:
        if requested_mode != "mock":
            if platform_code == "alipay":
                raise ValueError("平台应用未配置，请先配置支付宝 AppID、应用私钥、证书和回调地址")
            raise ValueError("平台应用未配置，请先配置淘宝/天猫 AppKey、AppSecret 和回调地址")
        return _build_mock_app_config(company_id, platform_code, redirect_uri=redirect_uri)
    if requested_mode != "mock" and _is_mock_app_record(record):
        if platform_code == "alipay":
            raise ValueError("平台应用未配置，请先配置支付宝 AppID、应用私钥、证书和回调地址")
        raise ValueError("平台应用未配置，请先配置淘宝/天猫 AppKey、AppSecret 和回调地址")
    auth_mode = requested_mode
    return PlatformAppConfig(
        id=str(record.get("id") or ""),
        company_id=str(record.get("company_id") or "") or owner_company_id,
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


def _alipay_dataset_code_suffix(shop_connection_id: str) -> str:
    suffix = "".join(
        ch if ch.isalnum() else "_"
        for ch in str(shop_connection_id or "").strip().lower()
    ).strip("_")
    return (suffix or "merchant")[:32]


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
        "publish_status": "unpublished",
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
    initial_days = max(1, int(sync_strategy.get("initial_days") or 1))
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


def build_alipay_bill_dataset_payload(
    *,
    company_id: str,
    data_source_id: str,
    shop_connection_id: str,
    merchant_name: str,
    external_shop_id: str,
    bill_kind: str,
    bill_type: str,
    dataset_label: str,
    business_object_type: str,
    grain: str,
) -> dict[str, Any]:
    """构建支付宝账单数据集目录 payload。"""
    display_merchant_name = str(merchant_name or "").strip() or "未命名商户"
    normalized_bill_kind = str(bill_kind or "").strip() or "bill"
    normalized_bill_type = str(bill_type or "").strip() or normalized_bill_kind
    resource_key = f"alipay_bill:{normalized_bill_type}:{shop_connection_id}"
    key_fields = ["bill_type", "bill_date", "source_row_key"]
    semantic_profile = {
        "business_name": f"{dataset_label} - {display_merchant_name}"[:255],
        "business_description": "支付宝授权商户账单采集数据集",
        "key_fields": key_fields,
    }
    return {
        "company_id": company_id,
        "data_source_id": data_source_id,
        "dataset_code": f"alipay_{normalized_bill_kind}_bill_{_alipay_dataset_code_suffix(shop_connection_id)}",
        "dataset_name": f"{dataset_label} - {display_merchant_name}"[:255],
        "resource_key": resource_key,
        "dataset_kind": "api_endpoint",
        "origin_type": "fixed",
        "publish_status": "unpublished",
        "business_domain": "ecommerce",
        "business_object_type": business_object_type,
        "grain": grain,
        "extract_config": {
            "storage": "platform_alipay_bill_lines",
            "platform_code": "alipay",
            "shop_connection_id": shop_connection_id,
            "external_shop_id": str(external_shop_id or ""),
            "bill_kind": normalized_bill_kind,
            "bill_type": normalized_bill_type,
            "date_field": "bill_date",
            "collection_date_field": "bill_date",
            "key_fields": key_fields,
        },
        "schema_summary": {
            "source": "alipay_bill_lines",
            "storage": "platform_alipay_bill_lines",
            "columns": [],
            "key_fields": key_fields,
        },
        "sync_strategy": dict(ALIPAY_BILL_SYNC_STRATEGY),
        "status": "active",
        "is_enabled": True,
        "health_status": "unknown",
        "meta": {
            "platform_code": "alipay",
            "shop_connection_id": shop_connection_id,
            "merchant_name": display_merchant_name,
            "external_shop_id": str(external_shop_id or ""),
            "bill_kind": normalized_bill_kind,
            "bill_type": normalized_bill_type,
            "key_fields": key_fields,
            "semantic_profile": semantic_profile,
        },
    }


def build_alipay_initial_collection_job_payloads(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    shop_connection_id: str,
    bill_kind: str,
    bill_type: str,
    anchor_date: str | date | datetime | None = None,
) -> list[dict[str, Any]]:
    """构建支付宝 T-1 初始化账单采集任务 payload；本任务只生成，不触发。"""
    if isinstance(anchor_date, datetime):
        resolved_anchor = anchor_date.date()
    elif isinstance(anchor_date, date):
        resolved_anchor = anchor_date
    elif anchor_date:
        resolved_anchor = date.fromisoformat(str(anchor_date))
    else:
        resolved_anchor = datetime.now(timezone.utc).date()

    return _build_alipay_initial_collection_jobs(
        source_id=data_source_id,
        dataset_id=dataset_id,
        resource_key=f"alipay_bill:{bill_type}:{shop_connection_id}",
        bill_type=bill_type,
        sync_strategy=ALIPAY_BILL_SYNC_STRATEGY,
        anchor_date=resolved_anchor,
    )


def _build_alipay_initial_collection_jobs(
    *,
    source_id: str,
    dataset_id: str,
    resource_key: str,
    bill_type: str,
    sync_strategy: dict[str, Any],
    anchor_date: date | None = None,
) -> list[dict[str, Any]]:
    """构建支付宝 T-1 初始化账单采集任务 payload。"""
    resolved_anchor = anchor_date or datetime.now(timezone(timedelta(hours=8))).date()
    initial_days = max(1, int(sync_strategy.get("initial_days") or 1))
    end_offset_days = max(1, int(sync_strategy.get("initial_end_offset_days") or 1))
    end_bill_date = resolved_anchor - timedelta(days=end_offset_days)
    start_bill_date = end_bill_date - timedelta(days=initial_days - 1)
    jobs: list[dict[str, Any]] = []
    for day_offset in range(initial_days):
        bill_date = start_bill_date + timedelta(days=day_offset)
        bill_date_text = bill_date.isoformat()
        jobs.append(
            {
                "source_id": source_id,
                "dataset_id": dataset_id,
                "resource_key": resource_key,
                "trigger_mode": "initial",
                "idempotency_key": f"alipay-initial:{dataset_id}:{bill_type}:{bill_date_text}",
                "background": True,
                "params": {
                    "dataset_id": dataset_id,
                    "resource_key": resource_key,
                    "bill_type": bill_type,
                    "bill_date": bill_date_text,
                    "biz_date": bill_date_text,
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


def _upsert_alipay_bill_datasets(
    *,
    company_id: str,
    connection: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    shop_connection_id = str(connection.get("id") or "")
    merchant_name = str(connection.get("external_shop_name") or "")
    source = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=f"platform_oauth_alipay_{_source_code_suffix(shop_connection_id)}",
        name=f"支付宝授权 - {merchant_name or shop_connection_id}"[:255],
        source_kind="platform_oauth",
        domain_type="ecommerce",
        provider_code="alipay",
        execution_mode="deterministic",
        description="支付宝商户 OAuth 授权账单数据源",
        status="active",
        is_enabled=True,
        health_status="unknown",
        last_error_message="",
        meta={
            "platform_code": "alipay",
            "shop_connection_id": shop_connection_id,
            "external_shop_id": str(connection.get("external_shop_id") or ""),
            "merchant_name": merchant_name,
        },
    )
    if source is None:
        raise ValueError("保存支付宝数据源失败")

    datasets: dict[str, dict[str, Any]] = {}
    for spec in ALIPAY_BILL_DATASETS:
        dataset_payload = build_alipay_bill_dataset_payload(
            company_id=company_id,
            data_source_id=str(source["id"]),
            shop_connection_id=shop_connection_id,
            merchant_name=merchant_name,
            external_shop_id=str(connection.get("external_shop_id") or ""),
            bill_kind=spec["bill_kind"],
            bill_type=spec["bill_type"],
            dataset_label=spec["label"],
            business_object_type=spec["business_object_type"],
            grain=spec["grain"],
        )
        dataset = auth_db.upsert_unified_data_source_dataset(**dataset_payload)
        if dataset is None:
            raise ValueError(f"保存{spec['label']}数据集失败")
        datasets[spec["bill_kind"]] = dataset
    return source, datasets.get("fund"), datasets.get("trade")


async def _initialize_alipay_connection_datasets(
    *,
    company_id: str,
    connection: dict[str, Any],
    run_in_background: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, str]:
    alipay_source: dict[str, Any] | None = None
    alipay_fund_dataset: dict[str, Any] | None = None
    alipay_trade_dataset: dict[str, Any] | None = None
    dataset_warning = ""
    try:
        alipay_source, alipay_fund_dataset, alipay_trade_dataset = _upsert_alipay_bill_datasets(
            company_id=company_id,
            connection=connection,
        )
        alipay_jobs: list[dict[str, Any]] = []
        for spec, dataset in (
            (ALIPAY_BILL_DATASETS[0], alipay_fund_dataset),
            (ALIPAY_BILL_DATASETS[1], alipay_trade_dataset),
        ):
            if not alipay_source or not dataset:
                continue
            alipay_jobs.extend(
                _build_alipay_initial_collection_jobs(
                    source_id=str(alipay_source["id"]),
                    dataset_id=str(dataset["id"]),
                    resource_key=str(dataset.get("resource_key") or ""),
                    bill_type=spec["bill_type"],
                    sync_strategy=dict(dataset.get("sync_strategy") or ALIPAY_BILL_SYNC_STRATEGY),
                )
            )
        if alipay_jobs:
            coroutine = _run_alipay_initial_collection_jobs(company_id=company_id, jobs=alipay_jobs)
            if run_in_background:
                _create_logged_background_task(coroutine, task_name="支付宝初始化采集任务")
            else:
                await coroutine
    except Exception as dataset_exc:  # noqa: BLE001
        dataset_warning = str(dataset_exc)
        logger.error(
            "支付宝授权成功但账单数据集创建失败: company_id=%s shop_connection_id=%s error=%s",
            company_id,
            connection.get("id"),
            dataset_warning,
            exc_info=True,
        )
    return alipay_source, alipay_fund_dataset, alipay_trade_dataset, dataset_warning


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


async def _run_alipay_initial_collection_jobs(
    *,
    company_id: str,
    jobs: list[dict[str, Any]],
) -> None:
    """串行执行支付宝 T-1 初始化账单采集任务。"""
    from tools import data_sources

    for job_payload in jobs:
        try:
            result = await data_sources.trigger_dataset_collection_for_company(
                company_id=company_id,
                source_id=str(job_payload.get("source_id") or ""),
                dataset_id=str(job_payload.get("dataset_id") or ""),
                resource_key=str(job_payload.get("resource_key") or ""),
                trigger_mode=str(job_payload.get("trigger_mode") or "initial"),
                idempotency_key=str(job_payload.get("idempotency_key") or ""),
                background=False,
                params=dict(job_payload.get("params") or {}),
            )
            if isinstance(result, dict) and result.get("success") is False:
                logger.error(
                    "支付宝初始化采集任务触发失败: company_id=%s source_id=%s dataset_id=%s "
                    "resource_key=%s idempotency_key=%s error=%s",
                    company_id,
                    job_payload.get("source_id"),
                    job_payload.get("dataset_id"),
                    job_payload.get("resource_key"),
                    job_payload.get("idempotency_key"),
                    result.get("error") or result,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "支付宝初始化采集任务执行失败: company_id=%s dataset_id=%s resource_key=%s error=%s",
                company_id,
                job_payload.get("dataset_id"),
                job_payload.get("resource_key"),
                exc,
                exc_info=True,
            )


def _create_logged_background_task(coroutine: Any, *, task_name: str) -> Any:
    """创建后台任务，并记录未被任务内部捕获的异常。"""
    task = asyncio.create_task(coroutine)

    def _log_task_result(done_task: Any) -> None:
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.warning("%s已取消", task_name)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s执行失败: %s", task_name, exc, exc_info=True)

    task.add_done_callback(_log_task_result)
    return task


def _platform_dataset_sync_summary(*, company_id: str, shop_connection_id: str) -> dict[str, Any]:
    """汇总平台固定数据集同步状态，用于补充店铺/商户列表展示。"""
    try:
        sources = auth_db.list_unified_data_sources(
            company_id=company_id,
            source_kind="platform_oauth",
            status="active",
            include_deleted=False,
        )
        matched_source_ids = {
            str(source.get("id") or "")
            for source in sources
            if str((source.get("meta") or {}).get("shop_connection_id") or "") == shop_connection_id
        }
        if not matched_source_ids:
            return {}
        datasets = auth_db.list_unified_data_source_datasets(
            company_id=company_id,
            status="active",
            include_deleted=False,
            limit=500,
        )
        matched_datasets = [
            dataset
            for dataset in datasets
            if str(dataset.get("data_source_id") or "") in matched_source_ids
        ]
        last_sync_at = max(
            [dataset.get("last_sync_at") for dataset in matched_datasets if dataset.get("last_sync_at")],
            default=None,
        )
        last_error = next(
            (
                dataset.get("last_error_message")
                for dataset in matched_datasets
                if str(dataset.get("last_error_message") or "").strip()
            ),
            "",
        )
        return {
            "last_sync_at": last_sync_at,
            "last_status": "error" if last_error else None,
            "last_error": last_error,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "读取平台固定数据集同步状态失败: company_id=%s shop_connection_id=%s error=%s",
            company_id,
            shop_connection_id,
            exc,
        )
        return {}


def _build_shop_view(connection: dict[str, Any]) -> dict[str, Any]:
    shop_id = str(connection.get("id") or "")
    company_id = str(connection.get("company_id") or "")
    auth = auth_db.get_current_shop_authorization(shop_connection_id=shop_id)
    sync_sources = auth_db.list_sync_sources(company_id=company_id, shop_connection_id=shop_id)
    dataset_sync_summary = _platform_dataset_sync_summary(
        company_id=company_id,
        shop_connection_id=shop_id,
    )
    sync_last = max(
        [
            item
            for item in [
                *[source.get("last_sync_at") for source in sync_sources if source.get("last_sync_at")],
                dataset_sync_summary.get("last_sync_at"),
            ]
            if item
        ],
        default=None,
    )
    last_status = next(
        (item.get("last_status") for item in sync_sources if str(item.get("last_status") or "") in {"error", "failed", "running"}),
        dataset_sync_summary.get("last_status") or (sync_sources[0].get("last_status") if sync_sources else None),
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
        configured_app = auth_db.get_platform_app(
            company_id=_platform_app_owner_company_id(),
            platform_code=platform["platform_code"],
        )
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


async def _handle_get_app_config(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    if platform_code not in _supported_platform_codes():
        return {"success": False, "platform_code": platform_code, "error": f"暂不支持的平台: {platform_code}"}

    record = auth_db.get_platform_app(
        company_id=_platform_app_owner_company_id(),
        platform_code=platform_code,
        include_secrets=True,
    )
    return {
        "success": True,
        "platform_code": platform_code,
        "configured": record is not None and not _is_mock_app_record(record),
        "config": _public_app_config(record, platform_code=platform_code),
        "mode": _normalize_mode(arguments.get("mode")),
    }


async def _handle_upsert_app_config(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    if not _can_configure_service_provider_app(user):
        platform_code = _normalize_platform_code(arguments.get("platform_code"))
        return {"success": False, "platform_code": platform_code, "error": "无权配置服务商应用"}
    operator_company_id = str(user["company_id"])
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    if platform_code not in _supported_platform_codes():
        return {"success": False, "platform_code": platform_code, "error": f"暂不支持的平台: {platform_code}"}

    app_key = str(arguments.get("app_key") or "").strip()
    redirect_uri = str(arguments.get("redirect_uri") or "").strip()
    incoming_secret = str(arguments.get("app_secret") or "").strip()
    if not app_key:
        app_key_label = "AppID" if platform_code == "alipay" else "AppKey"
        return {"success": False, "platform_code": platform_code, "error": f"{app_key_label} 不能为空"}
    if not redirect_uri:
        return {"success": False, "platform_code": platform_code, "error": "回调地址不能为空"}

    existing = auth_db.get_platform_app(
        company_id=_platform_app_owner_company_id(),
        platform_code=platform_code,
        include_secrets=True,
    )
    app_secret = incoming_secret or str((existing or {}).get("app_secret") or "").strip()
    if not app_secret:
        if platform_code == "alipay":
            return {"success": False, "platform_code": platform_code, "error": "应用私钥不能为空"}
        return {"success": False, "platform_code": platform_code, "error": "AppSecret 不能为空"}

    default_urls = _default_app_urls(platform_code)
    extra = dict((existing or {}).get("extra") if isinstance((existing or {}).get("extra"), dict) else {})
    if platform_code == "alipay":
        cert_fields = {
            "app_public_cert": "应用公钥证书",
            "alipay_public_cert": "支付宝公钥证书",
            "alipay_root_cert": "支付宝根证书",
        }
        for field_name, field_label in cert_fields.items():
            cert_value = str(arguments.get(field_name) or "").strip() or str(extra.get(field_name) or "").strip()
            if not cert_value:
                return {"success": False, "platform_code": platform_code, "error": f"{field_label}不能为空"}
            extra[field_name] = cert_value
        extra["merchant_auth_mode"] = str(
            arguments.get("merchant_auth_mode") or extra.get("merchant_auth_mode") or "static_invite"
        ).strip() or "static_invite"
        extra["merchant_auth_pc_url"] = str(
            arguments.get("merchant_auth_pc_url") or extra.get("merchant_auth_pc_url") or ""
        ).strip()
        extra["merchant_auth_qr_url"] = str(
            arguments.get("merchant_auth_qr_url") or extra.get("merchant_auth_qr_url") or ""
        ).strip()
    extra.update(
        {
            "mode": "real",
            "redirect_uri": redirect_uri,
            "owner_scope": "service_provider",
            "configured_by_company_id": operator_company_id,
        }
    )
    record = auth_db.upsert_platform_app(
        company_id=_platform_app_owner_company_id(),
        platform_code=platform_code,
        app_key=app_key,
        app_secret=app_secret,
        app_name=str(arguments.get("app_name") or (existing or {}).get("app_name") or _platform_name(platform_code)),
        app_type=str(arguments.get("app_type") or (existing or {}).get("app_type") or "isv"),
        auth_base_url=str(arguments.get("auth_base_url") or (existing or {}).get("auth_base_url") or default_urls["auth_base_url"]),
        token_url=str(arguments.get("token_url") or (existing or {}).get("token_url") or default_urls["token_url"]),
        refresh_url=str(arguments.get("refresh_url") or (existing or {}).get("refresh_url") or default_urls["refresh_url"]),
        scopes_config=list((existing or {}).get("scopes_config") or []),
        extra=extra,
        status="active",
        include_secrets=True,
    )
    if record is None:
        return {"success": False, "platform_code": platform_code, "error": "保存平台应用配置失败"}
    return {
        "success": True,
        "platform_code": platform_code,
        "configured": True,
        "config": _public_app_config(record, platform_code=platform_code),
        "mode": "real",
        "message": "平台应用配置已保存。",
    }


async def _handle_create_auth_session(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    if platform_code not in _supported_platform_codes():
        return {"success": False, "error": f"暂不支持的平台: {platform_code}"}

    mode = _normalize_mode(arguments.get("mode"))
    merchant_display_name = str(arguments.get("merchant_display_name") or "").strip()
    session_extra: dict[str, Any] = {}
    if platform_code == "alipay":
        if not merchant_display_name:
            return {
                "success": False,
                "platform_code": platform_code,
                "mode": mode,
                "error": "支付宝授权需要填写商户显示名称",
            }
        session_extra = {
            "merchant_display_name": merchant_display_name,
            "connection_label": merchant_display_name,
            "subject_type": "alipay_merchant",
        }
    redirect_uri = str(arguments.get("redirect_uri") or "").strip()
    try:
        app_config = _load_app_config(company_id, platform_code, mode=mode, redirect_uri=redirect_uri)
    except ValueError as exc:
        return {"success": False, "platform_code": platform_code, "mode": mode, "error": str(exc)}
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
        extra=session_extra,
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


async def _handle_alipay_merchant_auth_callback(arguments: dict[str, Any]) -> dict[str, Any]:
    callback_payload = dict(arguments.get("callback_payload") or {})
    code = str(
        callback_payload.get("app_auth_code")
        or callback_payload.get("code")
        or arguments.get("code")
        or ""
    ).strip()
    if not code:
        return {
            "success": False,
            "platform_code": "alipay",
            "error": "缺少支付宝授权码，请重新扫码授权",
            "message": "缺少支付宝授权码，请重新扫码授权",
            "return_path": "/data-connections?mode=platform&platform=alipay",
            "mode": _normalize_mode(arguments.get("mode")),
        }
    try:
        app_config = _load_app_config(
            _platform_app_owner_company_id(),
            "alipay",
            mode=arguments.get("mode"),
            redirect_uri=str(callback_payload.get("redirect_uri") or ""),
        )
        connector = build_connector(app_config)
        token_bundle = connector.exchange_code_for_token(
            code=code,
            auth_session=None,
            callback_payload=callback_payload,
        )
        shop_profile = connector.fetch_shop_profile(
            token_bundle=token_bundle,
            auth_session=None,
            callback_payload=callback_payload,
        )
        pending: dict[str, Any] | None = None
        for _ in range(3):
            pending = auth_db.create_platform_pending_authorization(
                platform_code="alipay",
                platform_app_id=str(app_config.id or "") or None,
                app_id=str(callback_payload.get("app_id") or app_config.app_key or ""),
                source=str(callback_payload.get("source") or "alipay_app_auth"),
                claim_code=_generate_claim_code(),
                access_token=token_bundle.access_token,
                refresh_token=token_bundle.refresh_token,
                token_expires_at=_compute_expire_at(token_bundle.expires_in),
                refresh_expires_at=_compute_expire_at(token_bundle.refresh_expires_in),
                raw_auth_payload=_safe_raw_auth_payload(token_bundle.raw_payload),
                callback_payload=callback_payload,
                external_shop_id=shop_profile.external_shop_id,
                external_seller_id=shop_profile.external_seller_id,
                merchant_display_name=shop_profile.external_shop_name,
                expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
            )
            if pending is not None:
                break
        if pending is None:
            raise ValueError("保存支付宝待绑定授权失败")
        public_pending = _public_pending_authorization(pending)
        claim_code = str(public_pending.get("claim_code") or "")
        return {
            "success": True,
            "platform_code": "alipay",
            "pending_authorization": public_pending,
            "pending_authorization_id": str(public_pending.get("id") or ""),
            "claim_code": claim_code,
            "message": "支付宝授权已收到，请填写支付宝商户名称完成绑定",
            "return_path": "/data-connections?mode=platform&platform=alipay",
            "mode": app_config.auth_mode,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("处理支付宝商家授权回调失败: %s", exc, exc_info=True)
        message = str(exc) or "支付宝授权处理失败，请重新扫码授权"
        return {
            "success": False,
            "platform_code": "alipay",
            "error": message,
            "message": message,
            "return_path": "/data-connections?mode=platform&platform=alipay",
            "mode": _normalize_mode(arguments.get("mode")),
        }


async def _handle_list_pending_authorizations(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_user(arguments.get("auth_token", ""))
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    if platform_code != "alipay":
        return {"success": False, "platform_code": platform_code, "error": "暂只支持支付宝待绑定授权"}
    status = str(arguments.get("status") or "pending_claim").strip() or "pending_claim"
    try:
        limit = int(arguments.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    pending_authorizations = [
        _public_pending_authorization(item)
        for item in auth_db.list_platform_pending_authorizations(
            platform_code=platform_code,
            status=status,
            limit=limit,
        )
    ]
    return {
        "success": True,
        "platform_code": platform_code,
        "pending_authorizations": pending_authorizations,
        "count": len(pending_authorizations),
        "mode": _normalize_mode(arguments.get("mode")),
    }


async def _handle_claim_pending_authorization(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    user_id = str(user.get("user_id") or "")
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    if platform_code != "alipay":
        return {"success": False, "platform_code": platform_code, "error": "暂只支持支付宝待绑定授权"}

    pending_id = str(arguments.get("pending_authorization_id") or "").strip()
    claim_code = str(arguments.get("claim_code") or "").strip()
    merchant_display_name = str(arguments.get("merchant_display_name") or "").strip()
    if not claim_code:
        return {"success": False, "platform_code": platform_code, "error": "授权校验信息不能为空，请重新发起授权"}
    if not merchant_display_name:
        return {"success": False, "platform_code": platform_code, "error": "支付宝商户名称不能为空"}

    pending = (
        auth_db.get_platform_pending_authorization_by_id(pending_id, include_secrets=True)
        if pending_id
        else auth_db.get_platform_pending_authorization_by_claim_code(claim_code, include_secrets=True)
    )
    if not pending:
        return {"success": False, "platform_code": platform_code, "error": "待绑定授权不存在或已失效"}
    if str(pending.get("platform_code") or "") != "alipay":
        return {"success": False, "platform_code": platform_code, "error": "待绑定授权平台不匹配"}
    if str(pending.get("status") or "") != "pending_claim":
        return {"success": False, "platform_code": platform_code, "error": "该授权已处理，请勿重复绑定"}
    if str(pending.get("claim_code") or "").strip() != claim_code:
        return {"success": False, "platform_code": platform_code, "error": "授权校验信息不匹配，请重新发起授权"}
    if _pending_authorization_expired(pending):
        auth_db.mark_platform_pending_authorization_failed(
            pending_authorization_id=str(pending.get("id") or ""),
            status="expired",
            last_error="授权校验信息已过期",
        )
        return {"success": False, "platform_code": platform_code, "error": "授权校验信息已过期，请重新发起授权"}

    external_shop_id = str(pending.get("external_shop_id") or "").strip()
    if not external_shop_id:
        return {"success": False, "platform_code": platform_code, "error": "支付宝主体 ID 为空，无法绑定"}
    existing_binding = auth_db.find_shop_connection_by_platform_external_shop(
        platform_code="alipay",
        external_shop_id=external_shop_id,
    )
    if existing_binding and str(existing_binding.get("company_id") or "") != company_id:
        return {
            "success": False,
            "platform_code": platform_code,
            "error": "该支付宝主体已绑定到其他企业，请联系服务商管理员处理",
        }

    try:
        connection = auth_db.upsert_shop_connection(
            company_id=company_id,
            platform_code="alipay",
            external_shop_id=external_shop_id,
            external_shop_name=merchant_display_name,
            external_seller_id=str(pending.get("external_seller_id") or ""),
            auth_subject_name=merchant_display_name,
            shop_type="merchant",
            status="active",
            meta={
                "source": "pending_authorization",
                "pending_authorization_id": str(pending.get("id") or ""),
                "alipay_app_id": str(pending.get("app_id") or ""),
            },
        )
        if connection is None:
            raise ValueError("保存支付宝商户连接失败")

        authorization = auth_db.create_shop_authorization(
            company_id=company_id,
            shop_connection_id=str(connection["id"]),
            platform_app_id=str(pending.get("platform_app_id") or ""),
            auth_type="alipay_app_auth",
            access_token=str(pending.get("access_token") or ""),
            refresh_token=str(pending.get("refresh_token") or ""),
            token_expires_at=str(pending.get("token_expires_at") or "") or None,
            refresh_expires_at=str(pending.get("refresh_expires_at") or "") or None,
            scope_text="",
            auth_status="authorized",
            last_error="",
            raw_auth_payload=_safe_raw_auth_payload(dict(pending.get("raw_auth_payload") or {})),
        )
        if authorization is None:
            raise ValueError("保存支付宝商户授权失败")

        for source_type in ("orders", "refunds", "settlements", "bills"):
            auth_db.upsert_sync_source(
                company_id=company_id,
                shop_connection_id=str(connection["id"]),
                source_type=source_type,
            )

        alipay_source, alipay_fund_dataset, alipay_trade_dataset, dataset_warning = (
            await _initialize_alipay_connection_datasets(
                company_id=company_id,
                connection=connection,
                run_in_background=False,
            )
        )
        claimed = auth_db.mark_platform_pending_authorization_claimed(
            pending_authorization_id=str(pending.get("id") or ""),
            claimed_company_id=company_id,
            claimed_by_user_id=user_id,
            claimed_shop_connection_id=str(connection["id"]),
            last_error=dataset_warning,
        )
        detail = _build_shop_view(connection)
        return {
            "success": True,
            "platform_code": "alipay",
            "pending_authorization": _public_pending_authorization(claimed or pending),
            "shop": detail,
            "connection": detail,
            "shop_authorization_id": str((authorization or {}).get("id") or ""),
            "alipay_data_source_id": str((alipay_source or {}).get("id") or ""),
            "alipay_fund_bill_dataset_id": str((alipay_fund_dataset or {}).get("id") or ""),
            "alipay_trade_bill_dataset_id": str((alipay_trade_dataset or {}).get("id") or ""),
            "warning": dataset_warning,
            "message": "支付宝商户授权已绑定",
            "mode": _normalize_mode(arguments.get("mode")),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("绑定支付宝待绑定授权失败: %s", exc, exc_info=True)
        return {"success": False, "platform_code": "alipay", "error": str(exc)}


async def _handle_auth_callback(arguments: dict[str, Any]) -> dict[str, Any]:
    platform_code = _normalize_platform_code(arguments.get("platform_code"))
    state = str(arguments.get("state") or "").strip()
    code = str(arguments.get("code") or "").strip()
    error = str(arguments.get("error") or "").strip()
    error_description = str(arguments.get("error_description") or "").strip()
    callback_payload = dict(arguments.get("callback_payload") or {})

    if not state and platform_code == "alipay" and not error:
        callback_code = str(callback_payload.get("app_auth_code") or code or "").strip()
        if callback_code:
            return await _handle_alipay_merchant_auth_callback(arguments)

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
        exchange_code = code if platform_code == "alipay" else (code or f"mock_{state[-8:]}")
        token_bundle = connector.exchange_code_for_token(
            code=exchange_code,
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
        alipay_source: dict[str, Any] | None = None
        alipay_fund_dataset: dict[str, Any] | None = None
        alipay_trade_dataset: dict[str, Any] | None = None
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
        if platform_code == "alipay":
            try:
                alipay_source, alipay_fund_dataset, alipay_trade_dataset = _upsert_alipay_bill_datasets(
                    company_id=company_id,
                    connection=connection,
                )
                alipay_jobs: list[dict[str, Any]] = []
                for spec, dataset in (
                    (ALIPAY_BILL_DATASETS[0], alipay_fund_dataset),
                    (ALIPAY_BILL_DATASETS[1], alipay_trade_dataset),
                ):
                    if not alipay_source or not dataset:
                        continue
                    alipay_jobs.extend(
                        _build_alipay_initial_collection_jobs(
                            source_id=str(alipay_source["id"]),
                            dataset_id=str(dataset["id"]),
                            resource_key=str(dataset.get("resource_key") or ""),
                            bill_type=spec["bill_type"],
                            sync_strategy=dict(dataset.get("sync_strategy") or ALIPAY_BILL_SYNC_STRATEGY),
                        )
                    )
                if alipay_jobs:
                    _create_logged_background_task(
                        _run_alipay_initial_collection_jobs(
                            company_id=company_id,
                            jobs=alipay_jobs,
                        ),
                        task_name="支付宝初始化采集任务",
                    )
            except Exception as dataset_exc:  # noqa: BLE001
                dataset_warning = str(dataset_exc)
                logger.error(
                    "支付宝授权成功但账单数据集创建失败: company_id=%s shop_connection_id=%s error=%s",
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
                "alipay_data_source_id": str((alipay_source or {}).get("id") or ""),
                "alipay_fund_bill_dataset_id": str((alipay_fund_dataset or {}).get("id") or ""),
                "alipay_trade_bill_dataset_id": str((alipay_trade_dataset or {}).get("id") or ""),
                "alipay_dataset_warning": dataset_warning,
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
    payload = {
        "auth_token": arguments.get("auth_token", ""),
        "platform_code": detail.get("platform_code"),
        "return_path": arguments.get("return_path", "/"),
        "shop_connection_id": shop_connection_id,
        "mode": arguments.get("mode", ""),
    }
    if _normalize_platform_code(detail.get("platform_code")) == "alipay":
        payload["merchant_display_name"] = str(
            detail.get("external_shop_name") or detail.get("auth_subject_name") or ""
        ).strip()
    return await _handle_create_auth_session(payload)


async def _handle_disable_shop(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    shop_connection_id = str(arguments.get("shop_connection_id") or "").strip()
    detail = auth_db.get_shop_connection_by_id(shop_connection_id)
    if detail is None or str(detail.get("company_id") or "") != str(user["company_id"]):
        return {"success": False, "error": "店铺连接不存在"}
    disabled_connection = auth_db.update_shop_connection_status(shop_connection_id=shop_connection_id, status="disabled")
    if not disabled_connection:
        return {"success": False, "error": "停用店铺连接失败"}
    authorization = auth_db.get_current_shop_authorization(shop_connection_id=shop_connection_id)
    if authorization:
        auth_db.update_shop_authorization_status(
            authorization_id=str(authorization["id"]),
            auth_status="revoked",
            last_error=str(arguments.get("reason") or ""),
            is_current=False,
        )
    refreshed = auth_db.get_shop_connection_by_id(shop_connection_id) or disabled_connection or detail
    connection_view = _build_shop_view(refreshed)
    platform_code = _normalize_platform_code(refreshed.get("platform_code"))
    subject_name = "支付宝商户" if platform_code == "alipay" else "店铺连接"
    return {
        "success": True,
        "message": f"{subject_name}已停用",
        "connection": connection_view,
        "shop": connection_view,
    }


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
