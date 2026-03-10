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

# 配置日志（使用根 logger 确保日志能正确输出）
logger = logging.getLogger("proc.mcp_server.tools")

# 确保 logger 有 handler（如果还没有配置，添加默认的 StreamHandler）
if not logger.handlers and not logging.getLogger().handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


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
        ),
        Tool(
            name="get_file_validation_rule",
            description="根据 rule_code 获取文件校验规则的 JSON 配置。从 bus_file_rules 表中查询对应的 rule 字段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份（可选）"
                    },
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（rule_code）"
                    }
                },
                "required": ["rule_code"]
            }
        ),
        Tool(
            name="get_proc_rule",
            description="根据 rule_code 获取整理规则的 JSON 配置。从 bus_proc_rules 表中查询对应的 rule 字段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份（可选）"
                    },
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（rule_code）"
                    }
                },
                "required": ["rule_code"]
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


def _get_file_validation_rule(rule_code: str) -> Optional[Dict[str, Any]]:
    """
    根据 rule_code 从 bus_file_rules 表获取文件校验规则完整记录
    
    Args:
        rule_code: 规则编码
        
    Returns:
        完整记录对象（包含 id, rule_code, rule, memo 字段），如果未找到则返回 None
    """
    conn = None
    try:
        logger.info(f"[SQL] 开始查询文件校验规则，rule_code={rule_code}")
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 查询表中的所有字段: id, rule_code, rule, memo
        sql = """
            SELECT 
                id,
                rule_code,
                rule,
                memo
            FROM bus_file_rules
            WHERE rule_code = %s
            LIMIT 1
        """
        
        logger.debug(f"[SQL] 执行查询: {sql.strip()}, 参数: rule_code={rule_code}")
        cur.execute(sql, (rule_code,))
        row = cur.fetchone()
        
        cur.close()
        
        if row:
            # 解析 rule 字段（可能是 JSON 字符串）
            rule_data = row[2]
            if isinstance(rule_data, str):
                try:
                    rule_data = json.loads(rule_data)
                except json.JSONDecodeError:
                    pass  # 保持原始字符串
            
            result = {
                "id": row[0],
                "rule_code": row[1],
                "rule": rule_data,
                "memo": row[3]
            }
            
            logger.info(f"[SQL] 查询文件校验规则成功，rule_code={rule_code}，id={result['id']}")
            return result
        
        logger.warning(f"[SQL] 查询文件校验规则，rule_code={rule_code}，未找到记录")
        return None
        
    except Exception as e:
        logger.error(f"[SQL] 获取文件校验规则失败，rule_code={rule_code}: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def _get_proc_rule(rule_code: str) -> Optional[Dict[str, Any]]:
    """
    根据 rule_code 从 bus_proc_rules 表获取整理规则完整记录
    
    Args:
        rule_code: 规则编码
        
    Returns:
        完整记录对象（包含 id, rule_code, rule, memo 字段），如果未找到则返回 None
    """
    conn = None
    try:
        logger.info(f"[SQL] 开始查询整理规则，rule_code={rule_code}")
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 查询表中的所有字段: id, rule_code, rule, memo
        sql = """
            SELECT 
                id,
                rule_code,
                rule,
                memo
            FROM bus_proc_rules
            WHERE rule_code = %s
            LIMIT 1
        """
        
        logger.debug(f"[SQL] 执行查询: {sql.strip()}, 参数: rule_code={rule_code}")
        cur.execute(sql, (rule_code,))
        row = cur.fetchone()
        
        cur.close()
        
        if row:
            # 解析 rule 字段（可能是 JSON 字符串或已解析的 dict）
            rule_data = row[2]
            if isinstance(rule_data, str):
                try:
                    rule_data = json.loads(rule_data)
                except json.JSONDecodeError:
                    pass  # 保持原始字符串
            
            result = {
                "id": row[0],
                "rule_code": row[1],
                "rule": rule_data,
                "memo": row[3]
            }
            
            logger.info(f"[SQL] 查询整理规则成功，rule_code={rule_code}，id={result['id']}")
            return result
        
        logger.warning(f"[SQL] 查询整理规则，rule_code={rule_code}，未找到记录")
        return None
        
    except Exception as e:
        logger.error(f"[SQL] 获取整理规则失败，rule_code={rule_code}: {e}", exc_info=True)
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
        elif name == "get_file_validation_rule":
            return await _handle_get_file_validation_rule(arguments)
        elif name == "get_proc_rule":
            return await _handle_get_proc_rule(arguments)
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


async def _handle_get_file_validation_rule(arguments: dict) -> dict:
    """
    处理 get_file_validation_rule 工具调用
    
    Args:
        arguments: 工具参数，包含 rule_code 和可选的 auth_token
        
    Returns:
        文件校验规则 JSON
    """
    rule_code = arguments.get("rule_code", "").strip()
    
    if not rule_code:
        return {
            "success": False,
            "error": "rule_code 不能为空"
        }
    
    try:
        # 获取文件校验规则
        rule = _get_file_validation_rule(rule_code)
        
        if rule is None:
            return {
                "success": False,
                "rule_code": rule_code,
                "error": f"未找到 rule_code 为 '{rule_code}' 的文件校验规则"
            }
        
        return {
            "success": True,
            "rule_code": rule_code,
            "data": rule,
            "message": f"成功获取文件校验规则"
        }
        
    except Exception as e:
        logger.error(f"获取文件校验规则失败: {e}")
        return {
            "success": False,
            "error": f"获取文件校验规则失败: {str(e)}"
        }


async def _handle_get_proc_rule(arguments: dict) -> dict:
    """
    处理 get_proc_rule 工具调用
    
    Args:
        arguments: 工具参数，包含 rule_code 和可选的 auth_token
        
    Returns:
        整理规则 JSON
    """
    rule_code = arguments.get("rule_code", "").strip()
    
    if not rule_code:
        return {
            "success": False,
            "error": "rule_code 不能为空"
        }
    
    try:
        # 获取整理规则
        rule = _get_proc_rule(rule_code)
        
        if rule is None:
            return {
                "success": False,
                "rule_code": rule_code,
                "error": f"未找到 rule_code 为 '{rule_code}' 的整理规则"
            }
        
        return {
            "success": True,
            "rule_code": rule_code,
            "data": rule,
            "message": f"成功获取整理规则"
        }
        
    except Exception as e:
        logger.error(f"获取整理规则失败: {e}")
        return {
            "success": False,
            "error": f"获取整理规则失败: {str(e)}"
        }
