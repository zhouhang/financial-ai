"""调用 finance-mcp 工具的 HTTP 客户端包装器。

所有规则管理和认证操作均通过 finance-mcp 的 MCP 工具完成，
data-agent 不再直接读取 JSON 配置文件或操作数据库。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import FINANCE_MCP_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


# ===========================================================================
# 底层：通过进程内导入调用 MCP 工具
# ===========================================================================

async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """调用 finance-mcp 工具。

    优先使用进程内直接调用（两个服务在同一台机器上），
    失败则回退到 HTTP 方式。
    """
    try:
        return await _call_tool_in_process(tool_name, arguments)
    except Exception:
        logger.warning("进程内 MCP 调用失败，回退到 HTTP", exc_info=True)
        return await _call_tool_http(tool_name, arguments)


async def _call_tool_in_process(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """导入 finance-mcp 工具处理器并直接调用。"""
    import sys
    mcp_root = str(Path(__file__).resolve().parents[4] / "finance-mcp")
    if mcp_root not in sys.path:
        sys.path.insert(0, mcp_root)
    
    # 认证和规则管理工具 -> auth/tools.py
    _auth_tools = {
        "auth_register", "auth_login", "auth_me",
        "list_reconciliation_rules", "get_reconciliation_rule",
        "save_reconciliation_rule", "update_reconciliation_rule",
        "delete_reconciliation_rule",
    }

    if tool_name in _auth_tools:
        from auth.tools import handle_auth_tool_call  # type: ignore
        return await handle_auth_tool_call(tool_name, arguments)
    else:
        from reconciliation.mcp_server.tools import handle_tool_call  # type: ignore
        return await handle_tool_call(tool_name, arguments)


async def _call_tool_http(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """回退：HTTP 方式调用。"""
    raise NotImplementedError("基于 HTTP 的 MCP 工具调用未实现；使用进程内调用")


# ===========================================================================
# 高级辅助函数 - 对账执行
# ===========================================================================

async def start_reconciliation(reconciliation_type: str, files: list[str]) -> dict[str, Any]:
    """通过 MCP 工具启动对账任务。"""
    return await call_mcp_tool("reconciliation_start", {
        "reconciliation_type": reconciliation_type,
        "files": files,
    })


async def get_reconciliation_status(task_id: str) -> dict[str, Any]:
    """轮询对账任务状态。"""
    return await call_mcp_tool("reconciliation_status", {"task_id": task_id})


async def get_reconciliation_result(task_id: str) -> dict[str, Any]:
    """获取对账结果。"""
    return await call_mcp_tool("reconciliation_result", {"task_id": task_id})


async def list_reconciliation_tasks() -> dict[str, Any]:
    """列出所有对账任务。"""
    return await call_mcp_tool("reconciliation_list_tasks", {})


# ===========================================================================
# 高级辅助函数 - 认证
# ===========================================================================

async def auth_login(username: str, password: str) -> dict[str, Any]:
    """用户登录"""
    return await call_mcp_tool("auth_login", {
        "username": username,
        "password": password,
    })


async def auth_register(username: str, password: str, **kwargs) -> dict[str, Any]:
    """用户注册"""
    args = {"username": username, "password": password}
    args.update(kwargs)
    return await call_mcp_tool("auth_register", args)


async def auth_me(token: str) -> dict[str, Any]:
    """获取当前用户信息"""
    return await call_mcp_tool("auth_me", {"auth_token": token})


# ===========================================================================
# 高级辅助函数 - 规则管理（全部通过 MCP 工具，需要 auth_token）
# ===========================================================================

async def list_available_rules(auth_token: str) -> list[dict[str, str]]:
    """查询当前用户可见的对账规则列表。

    Returns:
        [{"id": "...", "name": "...", "description": "...", ...}, ...]
    """
    result = await call_mcp_tool("list_reconciliation_rules", {
        "auth_token": auth_token,
    })
    if result.get("success"):
        return result.get("rules", [])
    logger.error(f"查询规则列表失败: {result.get('error')}")
    return []


async def get_rule_detail(auth_token: str, rule_id: str = None,
                          rule_name: str = None) -> dict[str, Any] | None:
    """获取规则详情（含 rule_template）"""
    args: dict[str, Any] = {"auth_token": auth_token}
    if rule_id:
        args["rule_id"] = rule_id
    if rule_name:
        args["rule_name"] = rule_name
    result = await call_mcp_tool("get_reconciliation_rule", args)
    if result.get("success"):
        return result.get("rule")
        return None


async def save_rule(auth_token: str, name: str, rule_template: dict,
                    description: str = "", visibility: str = "private",
                    tags: list[str] = None) -> dict[str, Any]:
    """保存新规则"""
    return await call_mcp_tool("save_reconciliation_rule", {
        "auth_token": auth_token,
        "name": name,
        "description": description or name,
        "rule_template": rule_template,
        "visibility": visibility,
        "tags": tags or [],
    })


async def update_rule(auth_token: str, rule_id: str, **kwargs) -> dict[str, Any]:
    """更新规则"""
    args: dict[str, Any] = {"auth_token": auth_token, "rule_id": rule_id}
    args.update(kwargs)
    return await call_mcp_tool("update_reconciliation_rule", args)


async def delete_rule(auth_token: str, rule_id: str) -> dict[str, Any]:
    """删除规则"""
    return await call_mcp_tool("delete_reconciliation_rule", {
        "auth_token": auth_token,
        "rule_id": rule_id,
    })
