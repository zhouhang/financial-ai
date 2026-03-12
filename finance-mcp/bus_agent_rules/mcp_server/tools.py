"""
Bus Agent Rules MCP 工具定义和实现

提供对 bus_agent_rules 表的 MCP 服务访问
"""
import json
import logging
from typing import Dict, Any, List, Optional
from mcp import Tool
from mcp import types as mcp_types

# 导入数据库配置
from db_config import get_db_connection
from auth.jwt_utils import get_user_from_token

# 配置日志（使用根 logger 确保日志能正确输出）
logger = logging.getLogger("bus_agent_rules.mcp_server.tools")

# 确保 logger 有 handler（如果还没有配置，添加默认的 StreamHandler）
if not logger.handlers and not logging.getLogger().handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def create_tools() -> list[Tool]:
    """创建 Bus Agent Rules MCP 工具列表"""
    return [
        Tool(
            name="list_digital_employees",
            description="获取数字员工列表。从 bus_agent_rules 表中查询 type=1 的数字员工记录。需要登录 token。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用户登录后获取的身份证书"
                    }
                },
                "required": ["auth_token"]
            }
        ),
        Tool(
            name="list_rules_by_employee",
            description="根据数字员工 code 获取对应的规则列表。从 bus_agent_rules 表中查询指定 parent_code 的规则记录。需要登录 token。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用户登录后获取的身份证书"
                    },
                    "employee_code": {
                        "type": "string",
                        "description": "数字员工的 code（parent_code）"
                    }
                },
                "required": ["auth_token", "employee_code"]
            }
        ),
    ]


def _get_digital_employees() -> List[Dict[str, Any]]:
    """
    从 bus_agent_rules 表中获取 type='1' 的数字员工列表
    
    Returns:
        数字员工列表，每个员工包含 code, name, desc_text 等字段
    """
    conn = None
    try:
        logger.info("[SQL] 开始查询数字员工列表")
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
        
        logger.debug(f"[SQL] 执行查询: {sql.strip()}")
        cur.execute(sql)
        rows = cur.fetchall()
        logger.info(f"[SQL] 查询数字员工列表成功，返回 {len(rows)} 条记录")
        
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
        logger.error(f"[SQL] 获取数字员工列表失败: {e}", exc_info=True)
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
        logger.info(f"[SQL] 开始查询员工规则列表，employee_code={employee_code}")
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
        
        logger.debug(f"[SQL] 执行查询: {sql.strip()}, 参数: employee_code={employee_code}")
        cur.execute(sql, (employee_code,))
        rows = cur.fetchall()
        logger.info(f"[SQL] 查询员工规则列表成功，employee_code={employee_code}，返回 {len(rows)} 条记录")
        
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
        logger.error(f"[SQL] 获取规则列表失败，employee_code={employee_code}: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


async def handle_tool_call(name: str, arguments: dict) -> dict:
    """
    处理 Bus Agent Rules MCP 工具调用
    
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
        arguments: 工具参数，必须包含 auth_token
        
    Returns:
        数字员工列表
    """
    # 校验 auth_token
    auth_token = arguments.get("auth_token", "").strip()
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    user_info = get_user_from_token(auth_token)
    if not user_info:
        return {"success": False, "error": "token 无效或已过期，请重新登录"}
    
    try:
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
        arguments: 工具参数，必须包含 auth_token 和 employee_code
        
    Returns:
        规则列表
    """
    # 校验 auth_token
    auth_token = arguments.get("auth_token", "").strip()
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    user_info = get_user_from_token(auth_token)
    if not user_info:
        return {"success": False, "error": "token 无效或已过期，请重新登录"}

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
