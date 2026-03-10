"""
MCP Proc 工具调用封装模块

提供对 finance-mcp 中 proc 模块工具调用的同步封装，
供 proc_graph 子图和 RESTful API 使用。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# MCP 服务器配置
MCP_SERVER_URL = "http://localhost:3335"


def _call_mcp_tool(tool_name: str, arguments: dict) -> dict[str, Any]:
    """
    调用 MCP 工具的底层函数
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数
        
    Returns:
        工具调用结果
    """
    try:
        # 使用 HTTP SSE 端点调用 MCP 工具
        # 注意：这里使用简化方式，直接调用 finance-mcp 的内部函数
        # 实际生产环境应该通过 MCP 协议调用
        
        # 临时方案：直接导入 finance-mcp 的 tools 模块
        import sys
        sys.path.insert(0, '/Users/fanyuli/Desktop/workspace/financial-ai/finance-mcp')
        
        from proc.mcp_server.tools import handle_tool_call
        import asyncio
        
        # 运行异步函数
        result = asyncio.run(handle_tool_call(tool_name, arguments))
        return result
        
    except Exception as e:
        logger.error(f"调用 MCP 工具失败 [{tool_name}]: {e}")
        return {
            "success": False,
            "error": f"调用失败: {str(e)}"
        }


def get_digital_employees(auth_token: str = "") -> dict[str, Any]:
    """
    获取数字员工列表
    
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
    arguments = {}
    if auth_token:
        arguments["auth_token"] = auth_token
    
    return _call_mcp_tool("list_digital_employees", arguments)


def get_rules_by_employee(employee_code: str, auth_token: str = "") -> dict[str, Any]:
    """
    根据数字员工 code 获取规则列表
    
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
    arguments = {"employee_code": employee_code}
    if auth_token:
        arguments["auth_token"] = auth_token
    
    return _call_mcp_tool("list_rules_by_employee", arguments)


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    print("测试获取数字员工列表...")
    result = get_digital_employees()
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    if result.get("success") and result.get("employees"):
        emp_code = result["employees"][0]["code"]
        print(f"\n测试获取 {emp_code} 的规则列表...")
        result = get_rules_by_employee(emp_code)
        print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
