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

from config import FINANCE_MCP_BASE_URL

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
    mcp_root = str(Path(__file__).resolve().parents[3] / "finance-mcp")
    if mcp_root not in sys.path:
        sys.path.insert(0, mcp_root)
    
    logger.info(f"尝试进程内调用工具: {tool_name}, mcp_root={mcp_root}")
    
    # 认证和规则管理工具 -> auth/tools.py
    _auth_tools = {
        "auth_register", "auth_login", "auth_me",
        "list_reconciliation_rules", "get_reconciliation_rule",
        "save_reconciliation_rule", "update_reconciliation_rule",
        "delete_reconciliation_rule",
        "search_rules_by_mapping", "copy_reconciliation_rule",
        "batch_get_reconciliation_rules",
        # 管理员功能
        "admin_login", "create_company", "create_department",
        "list_companies", "list_departments", "get_admin_view",
        # 公开 API
        "list_companies_public", "list_departments_public",
        # 会话管理
        "create_conversation", "list_conversations", "get_conversation",
        "update_conversation", "delete_conversation", "save_message",
        # 游客认证
        "create_guest_token", "verify_guest_token", "list_recommended_rules",
    }

    # Proc 模块工具（数字员工和规则管理）
    _proc_tools = {
        "list_digital_employees",
        "list_rules_by_employee",
        "get_file_validation_rule",
        "get_proc_rule",
        "validate_uploaded_files",
        "sync_rule_execute",
    }

    try:
        if tool_name in _auth_tools:
            logger.info(f"导入认证工具处理器: {tool_name}")
            from auth.tools import handle_auth_tool_call  # type: ignore
            result = await handle_auth_tool_call(tool_name, arguments)
            logger.info(f"认证工具调用成功: {tool_name}, 结果: {result.get('success', '未知')}")
            return result
        elif tool_name in _proc_tools:
            logger.info(f"导入 Proc 工具处理器: {tool_name}")
            # validate_uploaded_files 在单独的 file_validate_tool 模块中
            if tool_name == "validate_uploaded_files":
                from proc.mcp_server.file_validate_tool import handle_file_validate_tool_call  # type: ignore
                result = await handle_file_validate_tool_call(tool_name, arguments)
            elif tool_name == "sync_rule_execute":
                from proc.mcp_server.sync_rule import handle_sync_rule_tool_call  # type: ignore
                result = await handle_sync_rule_tool_call(tool_name, arguments)
            else:
                from proc.mcp_server.tools import handle_tool_call as handle_proc_tool_call  # type: ignore
                result = await handle_proc_tool_call(tool_name, arguments)
            logger.info(f"Proc 工具调用成功: {tool_name}, 结果: {result.get('success', '未知')}")
            return result
        else:
            logger.info(f"导入对账工具处理器: {tool_name}")
            from reconciliation.mcp_server.tools import handle_tool_call  # type: ignore
            result = await handle_tool_call(tool_name, arguments)
            logger.info(f"对账工具调用成功: {tool_name}, result.get('success')={result.get('success')}, result.get('error')={result.get('error')}")
            return result
    except ImportError as e:
        logger.error(f"导入模块失败: {e}, 工具名: {tool_name}, sys.path 前3项: {sys.path[:3]}")
        raise
    except Exception as e:
        logger.error(f"工具调用失败: {e}, 工具名: {tool_name}")
        raise


async def _call_tool_http(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """通过 HTTP 调用 MCP 服务的工具。
    
    向 MCP 服务的消息端点发送请求。
    """
    try:
        logger.info(f"使用 HTTP 调用 MCP 工具: {tool_name}")
        
        # 构建 MCP 协议的工具调用请求
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            }
        }
        
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{FINANCE_MCP_BASE_URL}/messages/",
                json=request_body,
            )
            
            if response.status_code != 200:
                logger.error(f"MCP 服务返回错误: {response.status_code}, 内容: {response.text}")
                return {
                    "success": False,
                    "error": f"MCP 服务错误: {response.status_code}",
                }
            
            result = response.json()
            logger.info(f"HTTP MCP 调用成功: {tool_name}")
            return result.get("result", result)
            
    except Exception as e:
        logger.error(f"HTTP MCP 调用失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"HTTP 调用失败: {str(e)}",
        }


# ===========================================================================
# 高级辅助函数 - 对账执行
# ===========================================================================

async def start_reconciliation(
    files: list[str],
    rule_name: str = None,
    rule_id: str = None,
    rule_template: dict = None,
    auth_token: str = "",
    guest_token: str = None,
) -> dict[str, Any]:
    """通过 MCP 工具启动对账任务。支持从 PostgreSQL 查询规则，或直接传入 rule_template。
    
    Args:
        files: 文件列表
        rule_name: 规则名称（与 rule_id、rule_template 三选一）
        rule_id: 规则 ID（与 rule_name、rule_template 三选一）
        rule_template: 规则模板 JSON（新建规则流程直接传入，先对账再保存）
        auth_token: JWT token，用于身份验证
        guest_token: 游客token（当 auth_token 为空时使用）
    """
    args: dict[str, Any] = {"files": files}
    if auth_token and auth_token.strip():
        args["auth_token"] = auth_token
    elif guest_token:
        args["guest_token"] = guest_token
    if rule_template:
        args["rule_template"] = rule_template
    elif rule_id:
        args["rule_id"] = rule_id
    elif rule_name:
        args["rule_name"] = rule_name
    else:
        raise ValueError("必须提供 rule_id、rule_name 或 rule_template")
    
    return await call_mcp_tool("reconciliation_start", args)


async def get_reconciliation_status(task_id: str = "", auth_token: str = "", guest_token: str = None) -> dict[str, Any]:
    """轮询对账任务状态。
    
    Args:
        task_id: 任务 ID
        auth_token: JWT token，用于身份验证
        guest_token: 游客token（当 auth_token 为空时使用）
    """
    args: dict[str, Any] = {"task_id": task_id}
    if auth_token:
        args["auth_token"] = auth_token
    elif guest_token:
        args["guest_token"] = guest_token
    return await call_mcp_tool("reconciliation_status", args)


async def get_reconciliation_result(task_id: str = "", auth_token: str = "", guest_token: str = None) -> dict[str, Any]:
    """获取对账结果。
    
    Args:
        task_id: 任务 ID
        auth_token: JWT token，用于身份验证
        guest_token: 游客token（当 auth_token 为空时使用）
    """
    args: dict[str, Any] = {"task_id": task_id}
    if auth_token:
        args["auth_token"] = auth_token
    elif guest_token:
        args["guest_token"] = guest_token
    return await call_mcp_tool("reconciliation_result", args)


async def list_reconciliation_tasks(auth_token: str) -> dict[str, Any]:
    """列出当前用户的所有对账任务。
    
    Args:
        auth_token: JWT token，用于身份验证
    """
    return await call_mcp_tool("reconciliation_list_tasks", {"auth_token": auth_token})


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
# 高级辅助函数 - 游客认证
# ===========================================================================

async def create_guest_token(session_id: str, ip_address: str = None, user_agent: str = None) -> dict[str, Any]:
    """创建游客临时token"""
    args = {"session_id": session_id}
    if ip_address:
        args["ip_address"] = ip_address
    if user_agent:
        args["user_agent"] = user_agent
    return await call_mcp_tool("create_guest_token", args)


async def verify_guest_token(guest_token: str) -> dict[str, Any]:
    """验证游客token"""
    return await call_mcp_tool("verify_guest_token", {"guest_token": guest_token})


async def list_recommended_rules(guest_token: str) -> dict[str, Any]:
    """获取系统推荐规则列表（游客专用）"""
    return await call_mcp_tool("list_recommended_rules", {"guest_token": guest_token})


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


async def delete_rule(auth_token: str, rule_id: str, rule_name: str = "") -> dict[str, Any]:
    """删除规则。传入 rule_name 用于后端校验，防止误删其他规则。"""
    args: dict[str, Any] = {"auth_token": auth_token, "rule_id": rule_id}
    if rule_name:
        args["rule_name"] = rule_name
    return await call_mcp_tool("delete_reconciliation_rule", args)


# ══════════════════════════════════════════════════════════════════════════════
# 管理员功能
# ══════════════════════════════════════════════════════════════════════════════

async def admin_login(username: str, password: str) -> dict[str, Any]:
    """管理员登录"""
    return await call_mcp_tool("admin_login", {
        "username": username,
        "password": password,
    })


async def create_company(admin_token: str, name: str) -> dict[str, Any]:
    """管理员创建公司"""
    return await call_mcp_tool("create_company", {
        "admin_token": admin_token,
        "name": name,
    })


async def create_department(admin_token: str, company_id: str, name: str) -> dict[str, Any]:
    """管理员创建部门"""
    return await call_mcp_tool("create_department", {
        "admin_token": admin_token,
        "company_id": company_id,
        "name": name,
    })


async def list_companies(admin_token: str) -> dict[str, Any]:
    """获取公司列表"""
    return await call_mcp_tool("list_companies", {
        "admin_token": admin_token,
    })


async def list_departments(admin_token: str, company_id: str = None) -> dict[str, Any]:
    """获取部门列表"""
    args = {"admin_token": admin_token}
    if company_id:
        args["company_id"] = company_id
    return await call_mcp_tool("list_departments", args)


async def get_admin_view(admin_token: str) -> dict[str, Any]:
    """获取管理员视图"""
    return await call_mcp_tool("get_admin_view", {
        "admin_token": admin_token,
    })


async def list_companies_public() -> dict[str, Any]:
    """获取公司列表（公开，用于注册）"""
    return await call_mcp_tool("list_companies_public", {})


async def list_departments_public(company_id: str) -> dict[str, Any]:
    """获取指定公司的部门列表（公开，用于注册）"""
    return await call_mcp_tool("list_departments_public", {
        "company_id": company_id,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════════════════════

async def create_conversation(auth_token: str, title: str = None) -> dict[str, Any]:
    """创建新会话"""
    args = {"auth_token": auth_token}
    if title:
        args["title"] = title
    return await call_mcp_tool("create_conversation", args)


async def list_conversations(auth_token: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """获取用户的会话列表"""
    return await call_mcp_tool("list_conversations", {
        "auth_token": auth_token,
        "limit": limit,
        "offset": offset,
    })


async def get_conversation(auth_token: str, conversation_id: str) -> dict[str, Any]:
    """获取单个会话详情（包含消息）"""
    return await call_mcp_tool("get_conversation", {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
    })


async def update_conversation(auth_token: str, conversation_id: str, title: str = None, status: str = None) -> dict[str, Any]:
    """更新会话"""
    args = {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
    }
    if title:
        args["title"] = title
    if status:
        args["status"] = status
    return await call_mcp_tool("update_conversation", args)


async def delete_conversation(auth_token: str, conversation_id: str) -> dict[str, Any]:
    """删除会话"""
    return await call_mcp_tool("delete_conversation", {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
    })


async def save_message(auth_token: str, conversation_id: str, role: str, content: str, metadata: dict = None, attachments: list = None) -> dict[str, Any]:
    """保存消息到会话（支持附件）"""
    args = {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    if metadata:
        args["metadata"] = metadata
    if attachments:
        args["attachments"] = attachments
    return await call_mcp_tool("save_message", args)


# ══════════════════════════════════════════════════════════════════════════════
# 高级辅助函数 - Proc 模块（数字员工和规则管理）
# ══════════════════════════════════════════════════════════════════════════════

async def list_digital_employees(auth_token: str = "") -> dict[str, Any]:
    """获取数字员工列表
    
    Args:
        auth_token: JWT token（可选）
        
    Returns:
        {
            "success": bool,
            "count": int,
            "employees": list[dict],
            "message": str
        }
    """
    args: dict[str, Any] = {}
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("list_digital_employees", args)


async def list_rules_by_employee(employee_code: str, auth_token: str = "") -> dict[str, Any]:
    """根据数字员工 code 获取规则列表
    
    Args:
        employee_code: 数字员工的 code
        auth_token: JWT token（可选）
        
    Returns:
        {
            "success": bool,
            "count": int,
            "employee_code": str,
            "rules": list[dict],
            "message": str
        }
    """
    args: dict[str, Any] = {"employee_code": employee_code}
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("list_rules_by_employee", args)


async def get_file_validation_rule(rule_code: str, auth_token: str = "") -> dict[str, Any]:
    """根据 rule_code 获取文件校验规则 JSON
    
    Args:
        rule_code: 规则编码
        auth_token: JWT token（可选）
        
    Returns:
        {
            "success": bool,
            "rule_code": str,
            "rule": dict,  # 文件校验规则 JSON
            "message": str
        }
    """
    args: dict[str, Any] = {"rule_code": rule_code}
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("get_file_validation_rule", args)


async def get_proc_rule(rule_code: str, auth_token: str = "") -> dict[str, Any]:
    """根据 rule_code 获取整理规则 JSON
    
    Args:
        rule_code: 规则编码
        auth_token: JWT token（可选）
        
    Returns:
        {
            "success": bool,
            "rule_code": str,
            "rule": dict,  # 整理规则 JSON
            "message": str
        }
    """
    args: dict[str, Any] = {"rule_code": rule_code}
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("get_proc_rule", args)


async def validate_uploaded_files(
    uploaded_files: list[dict[str, Any]],
    rule_code: str,
) -> dict[str, Any]:
    """根据规则编码校验上传文件列表，判断每个文件属于哪个预定义的表。
    
    Args:
        uploaded_files: 上传文件列表，格式 [{"file_name": "xxx.xlsx", "columns": ["列1", ...]}]
        rule_code: 文件校验规则编码，用于从数据库查询对应的校验规则配置
        
    Returns:
        {
            "success": bool,
            "matched_results": [{"file_name": str, "table_id": str, "table_name": str}],
            "unmatched_files": [str],
            "message": str,
            # 失败时还包含:
            "error": str,
            "missing_necessary_tables": [{"table_id": str, "table_name": str}]
        }
    """
    return await call_mcp_tool("validate_uploaded_files", {
        "uploaded_files": uploaded_files,
        "rule_code": rule_code,
    })


async def execute_sync_rule(
    uploaded_files: list[dict[str, Any]],
    rule_code: str,
) -> dict[str, Any]:
    """根据规则编码执行数据整理规则，生成目标 Excel 文件。
    
    Args:
        uploaded_files: 文件校验结果列表，格式 [{"file_name": str, "file_path": str, "table_id": str, "table_name": str}]
        rule_code: 整理规则编码，用于从数据库查询对应的规则 JSON；输出目录由 MCP 服务端的 config 决定
        
    Returns:
        {
            "success": bool,
            "rule_code": str,
            "generated_files": [{"rule_id": str, "target_table": str, "output_file": str, "row_count": int}],
            "generated_count": int,
            "errors": [str],
            "message": str
        }
    """
    return await call_mcp_tool("sync_rule_execute", {
        "uploaded_files": uploaded_files,
        "rule_code": rule_code,
    })
