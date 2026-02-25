"""JWT 工具函数：创建与验证 token"""

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt  # PyJWT

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
# Warn if using default secret in production
if JWT_SECRET == "tally-secret-change-in-production":
    logger.warning("警告: 使用默认 JWT 密钥，生产环境应设置环境变量 JWT_SECRET")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


def create_token(user_id: str, username: str, role: str,
                 company_id: Optional[str] = None,
                 department_id: Optional[str] = None) -> str:
    """创建 JWT token。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,               # 用户 ID
        "username": username,
        "role": role,                  # admin / manager / member
        "company_id": company_id,
        "department_id": department_id,
        "iat": now,                    # 签发时间
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        "jti": str(uuid.uuid4()),      # token 唯一标识
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """验证 JWT token，返回 payload 或 None。"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT token 无效: {e}")
        return None


def get_user_from_token(token: str) -> Optional[dict]:
    """从 token 提取用户信息（简化结构）。"""
    payload = verify_token(token)
    if not payload:
        return None
    return {
        "user_id": payload.get("sub"),
        "username": payload.get("username"),
        "role": payload.get("role"),
        "company_id": payload.get("company_id"),
        "department_id": payload.get("department_id"),
    }
