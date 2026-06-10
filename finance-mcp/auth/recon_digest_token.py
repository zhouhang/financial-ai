"""Public capability tokens for recon digest detail pages."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

_PURPOSE = "recon_digest_detail"
_RUN_EXCEPTIONS_PURPOSE = "recon_run_exceptions"
_ALG = "HS256"
_ALLOWED_VIEWS = {"boss", "finance"}


def _secret() -> str:
    return os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def build_recon_digest_token(
    *,
    digest_id: str,
    company_id: str,
    view: str,
    biz_date: str,
    domain: str = "",
    ttl_seconds: Optional[int] = None,
) -> str:
    """构造公开详情页 token。默认不设过期；仅显式传入 ttl_seconds 时写入 exp。"""
    normalized_view = str(view or "").strip().lower()
    if normalized_view not in _ALLOWED_VIEWS:
        raise ValueError(f"unsupported digest detail view: {view}")

    now = datetime.now(timezone.utc)
    payload = {
        "purpose": _PURPOSE,
        "digest_id": str(digest_id),
        "company_id": str(company_id),
        "view": normalized_view,
        "biz_date": str(biz_date),
        "domain": str(domain or "").strip(),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    if ttl_seconds is not None:
        payload["exp"] = now + timedelta(seconds=int(ttl_seconds))

    return jwt.encode(payload, _secret(), algorithm=_ALG)


def verify_recon_digest_token(token: str, *, expected_view: str = "") -> Optional[dict]:
    try:
        payload = jwt.decode(str(token or ""), _secret(), algorithms=[_ALG])
    except jwt.InvalidTokenError:
        return None

    if payload.get("purpose") != _PURPOSE:
        return None

    view = str(payload.get("view") or "").strip().lower()
    if view not in _ALLOWED_VIEWS:
        return None
    if expected_view and view != str(expected_view).strip().lower():
        return None

    if not payload.get("digest_id") or not payload.get("company_id") or not payload.get("biz_date"):
        return None

    return payload


def build_recon_run_exceptions_token(
    *,
    run_id: str,
    company_id: str = "",
    ttl_seconds: Optional[int] = None,
) -> str:
    """构造公开异常页 token。默认不设过期，与 digest 详情页 token 保持一致。"""
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": _RUN_EXCEPTIONS_PURPOSE,
        "run_id": str(run_id),
        "company_id": str(company_id or ""),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    if ttl_seconds is not None:
        payload["exp"] = now + timedelta(seconds=int(ttl_seconds))

    return jwt.encode(payload, _secret(), algorithm=_ALG)


def verify_recon_run_exceptions_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(str(token or ""), _secret(), algorithms=[_ALG])
    except jwt.InvalidTokenError:
        return None

    if payload.get("purpose") != _RUN_EXCEPTIONS_PURPOSE:
        return None
    if not payload.get("run_id"):
        return None

    return payload
