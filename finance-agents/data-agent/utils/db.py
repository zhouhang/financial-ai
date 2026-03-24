"""兼容旧版 data-agent 数据库接口。

旧的 reconciliation_rules 表已下线，当前规则统一由 finance-mcp
中的 rule_detail / user_tasks 提供。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def ensure_tables() -> None:
    """兼容保留：旧 reconciliation_rules 表已删除，启动时无需建表。"""
    logger.info("跳过旧 reconciliation_rules 初始化，规则已迁移到 rule_detail/user_tasks")


def _legacy_api_removed(name: str) -> RuntimeError:
    return RuntimeError(
        f"{name} 已废弃：旧 reconciliation_rules 表已删除，请改用 finance-mcp 的 "
        "get_rule / list_user_tasks 工具。"
    )


def save_rule(name: str, type_key: str, schema: dict, description: str = "") -> str:
    """兼容保留：旧规则写入接口已下线。"""
    raise _legacy_api_removed("save_rule")


def load_rule(name: str) -> Optional[dict[str, Any]]:
    """兼容保留：旧规则读取接口已下线。"""
    raise _legacy_api_removed("load_rule")


def list_rules() -> list[dict[str, Any]]:
    """兼容保留：旧规则列表接口已下线。"""
    raise _legacy_api_removed("list_rules")
