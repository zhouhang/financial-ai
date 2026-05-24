"""浏览器风控 handoff 的一次性 HS256 token。

token 是无状态 bearer 能力,只编码 handoff_session_id + company_id,供责任人链接打开时
换取 session 描述。不编码任何凭证/profile 路径/CDP 端口。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

_PURPOSE = "browser_handoff"
_ALG = "HS256"
_DEFAULT_TTL_SECONDS = 900  # 15 分钟


def _secret() -> str:
    return os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def build_handoff_token(*, handoff_session_id: str, company_id: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": _PURPOSE,
        "handoff_session_id": str(handoff_session_id),
        "company_id": str(company_id),
        "iat": now,
        "exp": now + timedelta(seconds=int(ttl_seconds) if ttl_seconds else _DEFAULT_TTL_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALG)


def verify_handoff_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(str(token or ""), _secret(), algorithms=[_ALG])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    if not payload.get("handoff_session_id") or not payload.get("company_id"):
        return None
    return payload
