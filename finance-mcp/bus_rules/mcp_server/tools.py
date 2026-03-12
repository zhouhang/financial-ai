"""
Bus Rules MCP 工具定义和实现

提供通过 MCP 协议访问 bus_rules 表的工具接口，支持所有 rule_type：
- rule_type=1: 文件校验规则
- rule_type=2: 数据整理规则
- rule_type=3+: 后续扩展的其他规则类型
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, Optional
from mcp import Tool
from mcp import types as mcp_types

# 导入数据库配置
from db_config import get_db_connection

# 配置日志
logger = logging.getLogger("bus_rules.mcp_server.tools")

# 规则缓存，避免重复查询数据库
_rule_cache: Dict[tuple[str, int], Optional[Dict[str, Any]]] = {}


def get_rule_from_bus(rule_code: str, rule_type: int) -> Optional[Dict[str, Any]]:
    """从 bus_rules 表获取指定 rule_code 和 rule_type 的规则完整记录
    
    Args:
        rule_code: 规则编码
        rule_type: 规则类型（1=文件校验，2=数据整理）
        
    Returns:
        规则字典，包含 id, rule_code, rule, memo 等字段；未找到返回 None
    """
    cache_key = (rule_code, rule_type)
    
    # 优先读缓存
    if cache_key in _rule_cache:
        logger.info(f"[Cache] 命中缓存: rule_code={rule_code}, rule_type={rule_type}")
        return _rule_cache[cache_key]
    
    conn = None
    try:
        logger.info(f"[SQL] 查询 bus_rules: rule_code={rule_code}, rule_type={rule_type}")
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT id, rule_code, rule, memo
            FROM bus_rules
            WHERE rule_code = %s AND rule_type = %s::varchar
            LIMIT 1
        """
        cur.execute(sql, (rule_code, rule_type))
        row = cur.fetchone()
        cur.close()
        
        if row is None:
            logger.warning(f"[SQL] 未找到规则: rule_code={rule_code}, rule_type={rule_type}")
            _rule_cache[cache_key] = None
            return None
        
        result = {
            "id": row[0],
            "rule_code": row[1],
            "rule": row[2],
            "memo": row[3]
        }
        
        # 写入缓存
        _rule_cache[cache_key] = result
        logger.info(f"[SQL] 查询成功，已缓存: rule_code={rule_code}, rule_type={rule_type}")
        return result
        
    except Exception as e:
        logger.error(f"[SQL] 查询 bus_rules 失败: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()


def create_tools() -> list[Tool]:
    """创建 Bus Rules MCP 工具列表"""
    return [
        Tool(
            name="get_rule_from_bus",
            description="从 bus_rules 表获取指定 rule_code 和 rule_type 的规则完整记录。支持所有 rule_type：1=文件校验规则, 2=数据整理规则, 3+=后续扩展类型。",
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（rule_code）"
                    },
                    "rule_type": {
                        "type": "integer",
                        "description": "规则类型：1=文件校验规则, 2=数据整理规则, 3+=其他类型"
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验用户身份（可选）"
                    }
                },
                "required": ["rule_code", "rule_type"]
            }
        ),

    ]


async def handle_tool_call(name: str, arguments: dict) -> dict:
    """
    处理 Bus Rules MCP 工具调用
    
    Args:
        name: 工具名称
        arguments: 工具参数
        
    Returns:
        工具执行结果
    """
    try:
        if name == "get_rule_from_bus":
            return await _handle_get_rule_from_bus(arguments)

        else:
            return {"error": f"未知的工具: {name}"}
            
    except Exception as e:
        logger.error(f"工具调用失败 [{name}]: {e}", exc_info=True)
        return {"error": f"工具调用失败: {str(e)}"}


async def _handle_get_rule_from_bus(arguments: dict) -> dict:
    """
    处理 get_rule_from_bus 工具调用
    
    Args:
        arguments: 工具参数，包含 rule_code 和 rule_type
        
    Returns:
        规则记录
    """
    rule_code = arguments.get("rule_code", "").strip()
    rule_type = arguments.get("rule_type")
    
    if not rule_code:
        return {
            "success": False,
            "error": "rule_code 不能为空"
        }
    
    if rule_type is None:
        return {
            "success": False,
            "error": "rule_type 不能为空"
        }
    
    try:
        # 转换 rule_type 为整数
        rule_type = int(rule_type)
    except (ValueError, TypeError):
        return {
            "success": False,
            "error": f"rule_type 必须是整数，当前值: {rule_type}"
        }
    
    try:
        # 获取规则
        rule = get_rule_from_bus(rule_code, rule_type)
        
        if rule is None:
            return {
                "success": False,
                "rule_code": rule_code,
                "rule_type": rule_type,
                "error": f"未找到 rule_code 为 '{rule_code}' 且 rule_type 为 {rule_type} 的规则"
            }
        
        return {
            "success": True,
            "rule_code": rule_code,
            "rule_type": rule_type,
            "data": rule,
            "message": f"成功获取规则"
        }
        
    except Exception as e:
        logger.error(f"获取规则失败: {e}")
        return {
            "success": False,
            "error": f"获取规则失败: {str(e)}"
        }



