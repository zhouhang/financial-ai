"""
MCP Playwright Server - 模块化结构

将原有的 1400+ 行代码拆分为清晰的模块：
- models: 数据模型
- browser_manager: 浏览器管理器核心类
- tools: MCP 工具定义
- config: 配置常量
"""

from .models import BrowserSession
from .browser_manager import PlaywrightBrowserManager
from .tools import create_tools, handle_tool_call
from .config import DEFAULT_PORT, DEFAULT_HOST, SCREENSHOT_DIR

__all__ = [
    "BrowserSession",
    "PlaywrightBrowserManager",
    "create_tools",
    "handle_tool_call",
    "DEFAULT_PORT",
    "DEFAULT_HOST",
    "SCREENSHOT_DIR",
]

