from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PREFIX_V1 = "enc:v1:"
_PREFIX_FALLBACK = "enc:fallback:v1:"
_ENV_SECRET_KEY = "FINANCE_MCP_SECRET_KEY"


def _build_keystream(secret_key: str, length: int) -> bytes:
    seed = hashlib.sha256(secret_key.encode("utf-8")).digest()
    stream = bytearray()
    current = seed
    while len(stream) < length:
        current = hashlib.sha256(current + seed).digest()
        stream.extend(current)
    return bytes(stream[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _open_secret(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX_V1):
        payload = value[len(_PREFIX_V1):]
        secret_key = (os.getenv(_ENV_SECRET_KEY) or "").strip()
        if not secret_key:
            logger.error(
                "credential_ref uses %s encryption but %s is not configured",
                _PREFIX_V1,
                _ENV_SECRET_KEY,
            )
            return ""
        encrypted = base64.urlsafe_b64decode(payload.encode("ascii"))
        keystream = _build_keystream(secret_key, len(encrypted))
        return _xor_bytes(encrypted, keystream).decode("utf-8")
    if value.startswith(_PREFIX_FALLBACK):
        payload = value[len(_PREFIX_FALLBACK):]
        return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
    return value


def open_credential_ref(credential_ref: str) -> dict[str, Any]:
    raw = _open_secret(credential_ref).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.error("credential_ref is not valid JSON")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def inject_credentials_into_params(params: dict[str, Any], credential_ref: str) -> dict[str, Any]:
    merged = dict(params)
    credentials = open_credential_ref(credential_ref)
    username = str(credentials.get("username") or "")
    password = str(credentials.get("password") or "")
    if username and not str(merged.get("login_username") or ""):
        merged["login_username"] = username
    if password and not str(merged.get("login_password") or ""):
        merged["login_password"] = password
    return merged
