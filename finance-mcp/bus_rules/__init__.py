"""
Bus Rules 模块

提供对 bus_rules 表的统一访问接口，包括：
- mcp_server/: MCP 服务接口
"""
from __future__ import annotations

# 从 MCP 服务模块导出
from .mcp_server import create_tools, handle_tool_call

__all__ = [
    # MCP 服务接口
    "create_tools",
    "handle_tool_call",
]
