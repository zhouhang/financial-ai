"""支付宝长效专属授权链接的无状态 token 签发/校验。

token 是 HS256 JWT,编码授权要绑到哪个 Tally 企业 + 店铺显示名。它是一个 bearer 能力,
只能用于发起一次新的支付宝授权会话(换不到 app_auth_token)。供 MCP 工具与后续离线
Excel 批量脚本共用,不依赖任何请求上下文。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

_PURPOSE = "alipay_auth_invite"
_ALG = "HS256"


def _secret() -> str:
    return os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def _ttl_days() -> int:
    try:
        return int(os.getenv("ALIPAY_AUTH_INVITE_TTL_DAYS", "30"))
    except ValueError:
        return 30


def build_alipay_auth_invite_token(
    *,
    company_id: str,
    operator_user_id: str,
    merchant_display_name: str,
    expected_alipay_account: str = "",
    external_shop_id: str = "",
    ttl_days: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    days = _ttl_days() if ttl_days is None else int(ttl_days)
    payload = {
        "purpose": _PURPOSE,
        "company_id": str(company_id),
        "operator_user_id": str(operator_user_id),
        "merchant_display_name": str(merchant_display_name),
        "expected_alipay_account": str(expected_alipay_account or ""),
        "external_shop_id": str(external_shop_id or ""),
        "iat": now,
        "exp": now + timedelta(days=days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALG)


def verify_alipay_auth_invite_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(str(token or ""), _secret(), algorithms=[_ALG])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    if not payload.get("company_id") or not payload.get("merchant_display_name"):
        return None
    return payload
