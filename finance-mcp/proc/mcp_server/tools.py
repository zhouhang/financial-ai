"""
Proc MCP 工具定义和实现
提供数字员工和规则管理功能
"""
import json
import logging
from typing import Dict, Any, List, Optional
from mcp import Tool
from mcp import types as mcp_types

# 导入数据库配置
from db_config import get_db_connection

# 配置日志
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 工具定义
# ════════════════════════════════════════════════════════════════════════════

def create_tools() -> list[Tool]:
    """创建 Proc MCP 工具列表"""
    return [
        Tool(
            name="list_digital_employees",
            description="获取数字员工列表。从 bus_agent_rules 表中查询 type=1 的数字员工记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份（可选）"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="list_rules_by_employee",
            description="根据数字员工 code 获取对应的规则列表。从 bus_agent_rules 表中查询指定 parent_code 的规则记录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份（可选）"
                    },
                    "employee_code": {
                        "type": "string",
                        "description": "数字员工的 code（parent_code）"
                    }
                },
                "required": ["employee_code"]
            }
        )
    ]


# ════════════════════════════════════════════════════════════════════════════
# 数据库操作函数
# ════════════════════════════════════════════════════════════════════════════

def _get_digital_employees() -> List[Dict[str, Any]]:
    """
    从 bus_agent_rules 表中获取 type='1' 的数字员工列表
    
    Returns:
        数字员工列表，每个员工包含 code, name, desc_text 等字段
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 查询 type='1' 的数字员工记录（type 是 varchar 类型）
        sql = """
            SELECT 
                id,
                code,
                name,
                desc_text,
                type,
                memo
            FROM bus_agent_rules
            WHERE type = '1'
            ORDER BY id DESC
        """
        
        cur.execute(sql)
        rows = cur.fetchall()
        
        employees = []
        for row in rows:
            employees.append({
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "desc_text": row[3],
                "type": row[4],
                "memo": row[5]
            })
        
        cur.close()
        return employees
        
    except Exception as e:
        logger.error(f"获取数字员工列表失败: {e}")
        raise
    finally:
        if conn:
            conn.close()


def _get_rules_by_employee_code(employee_code: str) -> List[Dict[str, Any]]:
    """
    根据数字员工 code 获取对应的规则列表
    
    注意：parent_code 存储的是数字员工的 code（字符串）
    
    Args:
        employee_code: 数字员工的 code
        
    Returns:
        规则列表，每个规则包含 code, name, desc_text 等字段
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 直接使用 employee_code 查询规则（parent_code 存储的是 code）
        sql = """
            SELECT 
                id,
                code,
                name,
                desc_text,
                type,
                parent_code,
                memo
            FROM bus_agent_rules
            WHERE parent_code = %s
            ORDER BY id DESC
        """
        
        cur.execute(sql, (employee_code,))
        rows = cur.fetchall()
        
        rules = []
        for row in rows:
            rules.append({
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "desc_text": row[3],
                "type": row[4],
                "parent_code": row[5],
                "memo": row[6]
            })
        
        cur.close()
        return rules
        
    except Exception as e:
        logger.error(f"获取规则列表失败: {e}")
        raise
    finally:
        if conn:
            conn.close()


# ════════════════════════════════════════════════════════════════════════════
# 工具调用处理函数
# ════════════════════════════════════════════════════════════════════════════

async def handle_tool_call(name: str, arguments: dict) -> dict:
    """
    处理 Proc MCP 工具调用
    
    Args:
        name: 工具名称
        arguments: 工具参数
        
    Returns:
        工具执行结果
    """
    try:
        if name == "list_digital_employees":
            return await _handle_list_digital_employees(arguments)
        elif name == "list_rules_by_employee":
            return await _handle_list_rules_by_employee(arguments)
        else:
            return {"error": f"未知的工具: {name}"}
            
    except Exception as e:
        logger.error(f"工具调用失败 [{name}]: {e}", exc_info=True)
        return {"error": f"工具调用失败: {str(e)}"}


async def _handle_list_digital_employees(arguments: dict) -> dict:
    """
    处理 list_digital_employees 工具调用
    
    Args:
        arguments: 工具参数，包含可选的 auth_token
        
    Returns:
        数字员工列表
    """
    try:
        # 获取数字员工列表
        employees = _get_digital_employees()
        
        return {
            "success": True,
            "count": len(employees),
            "employees": employees,
            "message": f"成功获取 {len(employees)} 个数字员工"
        }
        
    except Exception as e:
        logger.error(f"获取数字员工列表失败: {e}")
        return {
            "success": False,
            "error": f"获取数字员工列表失败: {str(e)}"
        }


async def _handle_list_rules_by_employee(arguments: dict) -> dict:
    """
    处理 list_rules_by_employee 工具调用
    
    Args:
        arguments: 工具参数，包含 employee_code 和可选的 auth_token
        
    Returns:
        规则列表
    """
    employee_code = arguments.get("employee_code", "").strip()
    
    if not employee_code:
        return {
            "success": False,
            "error": "employee_code 不能为空"
        }
    
    try:
        # 获取规则列表
        rules = _get_rules_by_employee_code(employee_code)
        
        return {
            "success": True,
            "count": len(rules),
            "employee_code": employee_code,
            "rules": rules,
            "message": f"成功获取 {len(rules)} 条规则"
        }
        
    except Exception as e:
        logger.error(f"获取规则列表失败: {e}")
        return {
            "success": False,
            "error": f"获取规则列表失败: {str(e)}"
        }
