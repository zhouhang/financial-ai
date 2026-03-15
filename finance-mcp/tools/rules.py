"""
Rules MCP 工具定义和实现

合并了原 rules 和 agent_rules 两个模块的功能：
- get_rule_from_bus    : 从 bus_rules 表获取规则（支持所有 rule_type）
- list_digital_employees  : 获取数字员工列表（bus_agent_rules 表）
- list_rules_by_employee  : 按数字员工获取规则列表（bus_agent_rules 表）
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from mcp import Tool

from db_config import get_db_connection
from auth.jwt_utils import get_user_from_token

logger = logging.getLogger("tools.rules")

# ── bus_rules 规则缓存 ────────────────────────────────────────────────────────
_rule_cache: Dict[str, Optional[Dict[str, Any]]] = {}


# ════════════════════════════════════════════════════════════════════════════
# 工具注册
# ════════════════════════════════════════════════════════════════════════════

def create_tools() -> list[Tool]:
    """创建 Rules MCP 工具列表"""
    return [
        Tool(
            name="get_rule_from_bus",
            description=(
                "从 bus_rules 表获取指定 rule_code 的规则完整记录。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（rule_code）",
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份（可选）",
                    },
                },
                "required": ["rule_code"],
            },
        ),
        Tool(
            name="list_digital_employees",
            description="获取数字员工列表。从 bus_agent_rules 表中查询 type=1 的数字员工记录。需要登录 token。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用户登录后获取的身份证书",
                    },
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="list_rules_by_employee",
            description=(
                "根据数字员工 code 获取对应的规则列表。"
                "从 bus_agent_rules 表中查询指定 parent_code 的规则记录。需要登录 token。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用户登录后获取的身份证书",
                    },
                    "employee_code": {
                        "type": "string",
                        "description": "数字员工的 code（parent_code）",
                    },
                },
                "required": ["auth_token", "employee_code"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict) -> dict:
    """统一工具调用入口"""
    try:
        if name == "get_rule_from_bus":
            return await _handle_get_rule_from_bus(arguments)
        elif name == "list_digital_employees":
            return await _handle_list_digital_employees(arguments)
        elif name == "list_rules_by_employee":
            return await _handle_list_rules_by_employee(arguments)
        else:
            return {"error": f"未知的工具: {name}"}
    except Exception as e:
        logger.error(f"工具调用失败 [{name}]: {e}", exc_info=True)
        return {"error": f"工具调用失败: {str(e)}"}


# ════════════════════════════════════════════════════════════════════════════
# bus_rules：规则查询
# ════════════════════════════════════════════════════════════════════════════

def get_rule_from_bus(rule_code: str) -> Optional[Dict[str, Any]]:
    """从 bus_rules 表获取指定 rule_code 的规则完整记录

    Args:
        rule_code: 规则编码

    Returns:
        规则字典，包含 id, rule_code, rule, memo 等字段；未找到返回 None
    """
    cache_key = rule_code

    if cache_key in _rule_cache:
        logger.info(f"[Cache] 命中缓存: rule_code={rule_code}")
        return _rule_cache[cache_key]

    conn = None
    try:
        logger.info(f"[SQL] 查询 bus_rules: rule_code={rule_code}")
        conn = get_db_connection()
        cur = conn.cursor()

        sql = """
            SELECT id, rule_code, rule, memo
            FROM bus_rules
            WHERE rule_code = %s
            LIMIT 1
        """
        cur.execute(sql, (rule_code,))
        row = cur.fetchone()
        cur.close()

        if row is None:
            logger.warning(f"[SQL] 未找到规则: rule_code={rule_code}")
            _rule_cache[cache_key] = None
            return None

        result = {
            "id": row[0],
            "rule_code": row[1],
            "rule": row[2],
            "memo": row[3],
        }
        _rule_cache[cache_key] = result
        logger.info(f"[SQL] 查询成功，已缓存: rule_code={rule_code}")
        return result

    except Exception as e:
        logger.error(f"[SQL] 查询 bus_rules 失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


async def _handle_get_rule_from_bus(arguments: dict) -> dict:
    rule_code = arguments.get("rule_code", "").strip()

    if not rule_code:
        return {"success": False, "error": "rule_code 不能为空"}

    try:
        rule = get_rule_from_bus(rule_code)
        if rule is None:
            return {
                "success": False,
                "rule_code": rule_code,
                "error": f"未找到 rule_code 为 '{rule_code}' 的规则",
            }
        return {
            "success": True,
            "rule_code": rule_code,
            "data": rule,
            "message": "成功获取规则",
        }
    except Exception as e:
        logger.error(f"获取规则失败: {e}")
        return {"success": False, "error": f"获取规则失败: {str(e)}"}


# ════════════════════════════════════════════════════════════════════════════
# bus_agent_rules：数字员工管理
# ════════════════════════════════════════════════════════════════════════════

def _get_digital_employees() -> List[Dict[str, Any]]:
    """从 bus_agent_rules 表中获取 type='1' 的数字员工列表"""
    conn = None
    try:
        logger.info("[SQL] 开始查询数字员工列表")
        conn = get_db_connection()
        cur = conn.cursor()

        sql = """
            SELECT id, code, name, desc_text, type, memo, file_rule_code
            FROM bus_agent_rules
            WHERE type = '1'
            ORDER BY id DESC
        """
        cur.execute(sql)
        rows = cur.fetchall()
        logger.info(f"[SQL] 查询数字员工列表成功，返回 {len(rows)} 条记录")

        employees = [
            {"id": r[0], "code": r[1], "name": r[2], "desc_text": r[3], "type": r[4], "memo": r[5], "file_rule_code": r[6]}
            for r in rows
        ]
        cur.close()
        return employees

    except Exception as e:
        logger.error(f"[SQL] 获取数字员工列表失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _get_rules_by_employee_code(employee_code: str) -> List[Dict[str, Any]]:
    """根据数字员工 code 获取对应的规则列表（parent_code 存储的是 code 字符串）"""
    conn = None
    try:
        logger.info(f"[SQL] 开始查询员工规则列表，employee_code={employee_code}")
        conn = get_db_connection()
        cur = conn.cursor()

        sql = """
            SELECT id, code, name, desc_text, type, parent_code, memo, file_rule_code
            FROM bus_agent_rules
            WHERE parent_code = %s
            ORDER BY id DESC
        """
        cur.execute(sql, (employee_code,))
        rows = cur.fetchall()
        logger.info(f"[SQL] 查询员工规则列表成功，employee_code={employee_code}，返回 {len(rows)} 条记录")

        rules = [
            {"id": r[0], "code": r[1], "name": r[2], "desc_text": r[3],
             "type": r[4], "parent_code": r[5], "memo": r[6], "file_rule_code": r[7]}
            for r in rows
        ]
        cur.close()
        return rules

    except Exception as e:
        logger.error(f"[SQL] 获取规则列表失败，employee_code={employee_code}: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


async def _handle_list_digital_employees(arguments: dict) -> dict:
    auth_token = arguments.get("auth_token", "").strip()
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not get_user_from_token(auth_token):
        return {"success": False, "error": "token 无效或已过期，请重新登录"}

    try:
        employees = _get_digital_employees()
        return {
            "success": True,
            "count": len(employees),
            "employees": employees,
            "message": f"成功获取 {len(employees)} 个数字员工",
        }
    except Exception as e:
        logger.error(f"获取数字员工列表失败: {e}")
        return {"success": False, "error": f"获取数字员工列表失败: {str(e)}"}


async def _handle_list_rules_by_employee(arguments: dict) -> dict:
    auth_token = arguments.get("auth_token", "").strip()
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not get_user_from_token(auth_token):
        return {"success": False, "error": "token 无效或已过期，请重新登录"}

    employee_code = arguments.get("employee_code", "").strip()
    if not employee_code:
        return {"success": False, "error": "employee_code 不能为空"}

    try:
        rules = _get_rules_by_employee_code(employee_code)
        return {
            "success": True,
            "count": len(rules),
            "employee_code": employee_code,
            "rules": rules,
            "message": f"成功获取 {len(rules)} 条规则",
        }
    except Exception as e:
        logger.error(f"获取规则列表失败: {e}")
        return {"success": False, "error": f"获取规则列表失败: {str(e)}"}
