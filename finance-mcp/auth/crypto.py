"""敏感字段加解密工具。

说明：
- 优先使用环境变量 FINANCE_MCP_SECRET_KEY 做可逆加密；
- 未配置密钥时使用 fallback 编码，避免明文裸存；
- 该模块用于 token/app_secret 等敏感字段的持久化接口预留。
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

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


def seal_secret(value: str | None) -> str:
    """将敏感字段密封后入库（避免明文裸存）。"""
    if not value:
        return ""

    if value.startswith(_PREFIX_V1) or value.startswith(_PREFIX_FALLBACK):
        return value

    raw = value.encode("utf-8")
    secret_key = (os.getenv(_ENV_SECRET_KEY) or "").strip()
    if secret_key:
        keystream = _build_keystream(secret_key, len(raw))
        encrypted = _xor_bytes(raw, keystream)
        return _PREFIX_V1 + base64.urlsafe_b64encode(encrypted).decode("ascii")

    logger.warning(
        "未配置 %s，敏感字段将使用 fallback 编码保存（建议生产环境配置密钥）",
        _ENV_SECRET_KEY,
    )
    return _PREFIX_FALLBACK + base64.urlsafe_b64encode(raw).decode("ascii")


def open_secret(value: str | None) -> str:
    """读取敏感字段时解封。"""
    if not value:
        return ""

    if value.startswith(_PREFIX_V1):
        payload = value[len(_PREFIX_V1):]
        secret_key = (os.getenv(_ENV_SECRET_KEY) or "").strip()
        if not secret_key:
            logger.error("密文使用 %s 加密，但环境未配置该密钥", _ENV_SECRET_KEY)
            return ""
        encrypted = base64.urlsafe_b64decode(payload.encode("ascii"))
        keystream = _build_keystream(secret_key, len(encrypted))
        return _xor_bytes(encrypted, keystream).decode("utf-8")

    if value.startswith(_PREFIX_FALLBACK):
        payload = value[len(_PREFIX_FALLBACK):]
        return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")

    # 兼容历史明文
    return value
