"""
MCP 工具定义和调用处理
包含所有 23 个浏览器自动化工具的定义
"""
import json
from typing import Any, Dict, List

from mcp.types import Tool, TextContent


def create_tools() -> List[Tool]:
    """创建并返回所有可用的浏览器工具列表"""
    return [
        Tool(
            name="browser_launch",
            description="启动浏览器会话（如果浏览器未启动，会自动启动）",
            inputSchema={
                "type": "object",
                "properties": {
                    "headless": {"type": "boolean", "description": "是否无头模式", "default": False}
                }
            }
        ),
        Tool(
            name="browser_close",
            description="关闭浏览器会话",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="browser_resize",
            description="调整浏览器窗口大小",
            inputSchema={
                "type": "object",
                "properties": {
                    "width": {"type": "integer", "description": "窗口宽度"},
                    "height": {"type": "integer", "description": "窗口高度"}
                },
                "required": ["width", "height"]
            }
        ),
        Tool(
            name="browser_navigate",
            description="导航到指定URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "目标URL"},
                    "wait_until": {"type": "string", "description": "等待条件", "default": "domcontentloaded"},
                    "timeout": {"type": "integer", "description": "超时时间（毫秒）", "default": 30000}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="browser_click",
            description="点击页面元素。支持多种定位方式：1) CSS选择器（如 '#button', '.class'）；2) 文本内容（如 '邮箱登录' 会自动匹配包含该文本的元素）；3) 显式定位器（如 'text=邮箱登录'）",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS选择器、文本内容或显式定位器。如果传入纯文本（如'邮箱登录'），会自动使用文本定位器匹配包含该文本的元素"},
                    "timeout": {"type": "integer", "description": "超时时间（毫秒）", "default": 30000}
                },
                "required": ["selector"]
            }
        ),
        Tool(
            name="browser_type",
            description="在元素中输入文本。支持多种定位方式：1) CSS选择器（如 '#input', 'input[type=\"text\"]'）；2) Placeholder文本（如 '输入注册邮箱地址' 会自动匹配placeholder属性）；3) 显式定位器（如 'placeholder=输入注册邮箱地址'）",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS选择器、placeholder文本或显式定位器。如果传入placeholder文本（如'输入注册邮箱地址'），会自动匹配placeholder属性"},
                    "text": {"type": "string", "description": "要输入的文本"},
                    "submit": {"type": "boolean", "description": "是否在输入后按Enter", "default": False},
                    "slowly": {"type": "boolean", "description": "是否逐字符输入", "default": False}
                },
                "required": ["selector", "text"]
            }
        ),
        Tool(
            name="browser_snapshot",
            description="获取页面快照和内容",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="browser_wait_for",
            description="等待指定时间或文本出现/消失",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {"type": "integer", "description": "等待时间（毫秒）"},
                    "text": {"type": "string", "description": "等待出现的文本"},
                    "text_gone": {"type": "string", "description": "等待消失的文本"}
                }
            }
        ),
        Tool(
            name="browser_press_key",
            description="按下键盘按键",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "按键名称（如Enter, ArrowLeft等）"}
                },
                "required": ["key"]
            }
        ),
        Tool(
            name="browser_navigate_back",
            description="返回上一页",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="browser_take_screenshot",
            description="截取页面或元素截图",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "截图文件名（可选）"},
                    "full_page": {"type": "boolean", "description": "是否截取整页", "default": False},
                    "element": {"type": "string", "description": "元素选择器（可选）"},
                    "ref": {"type": "string", "description": "元素引用（可选）"}
                }
            }
        ),
        Tool(
            name="browser_hover",
            description="悬停在元素上",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "元素选择器"},
                    "ref": {"type": "string", "description": "元素引用（可选）"}
                },
                "required": ["selector"]
            }
        ),
        Tool(
            name="browser_select_option",
            description="在下拉框中选择选项",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "下拉框选择器"},
                    "values": {"type": "array", "items": {"type": "string"}, "description": "要选择的选项值列表"},
                    "ref": {"type": "string", "description": "元素引用（可选）"}
                },
                "required": ["selector", "values"]
            }
        ),
        Tool(
            name="browser_drag",
            description="拖拽元素",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_selector": {"type": "string", "description": "起始元素选择器"},
                    "end_selector": {"type": "string", "description": "目标元素选择器"},
                    "start_ref": {"type": "string", "description": "起始元素引用（可选）"},
                    "end_ref": {"type": "string", "description": "目标元素引用（可选）"}
                },
                "required": ["start_selector", "end_selector"]
            }
        ),
        Tool(
            name="browser_evaluate",
            description="在页面或元素上执行JavaScript代码。支持两种格式：1) 函数体（包含return语句，会自动包装成箭头函数）；2) 完整函数表达式（如 () => { ... } 或 function() { ... }）",
            inputSchema={
                "type": "object",
                "properties": {
                    "function": {"type": "string", "description": "要执行的JavaScript代码。可以是函数体（包含return，会自动包装）或完整函数表达式（如 () => { ... }）"},
                    "element": {"type": "string", "description": "元素选择器（可选，如果提供则在指定元素上执行）"},
                    "ref": {"type": "string", "description": "元素引用（可选）"}
                },
                "required": ["function"]
            }
        ),
        Tool(
            name="browser_tabs",
            description="管理浏览器标签页（列出、新建、关闭、选择）",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "new", "close", "select"], "description": "操作类型"},
                    "index": {"type": "integer", "description": "标签页索引（close和select时需要）"}
                },
                "required": ["action"]
            }
        ),
        Tool(
            name="browser_console_messages",
            description="获取浏览器控制台消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["error", "warning", "info", "debug"], "description": "消息级别过滤"}
                }
            }
        ),
        Tool(
            name="browser_handle_dialog",
            description="处理浏览器对话框（alert、confirm、prompt）",
            inputSchema={
                "type": "object",
                "properties": {
                    "accept": {"type": "boolean", "description": "是否接受对话框", "default": True},
                    "prompt_text": {"type": "string", "description": "prompt对话框的输入文本"}
                }
            }
        ),
        Tool(
            name="browser_file_upload",
            description="上传文件到文件输入框",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "文件输入框的选择器"},
                    "paths": {"type": "array", "items": {"type": "string"}, "description": "要上传的文件路径列表"},
                    "ref": {"type": "string", "description": "元素引用（可选）"}
                },
                "required": ["selector", "paths"]
            }
        ),
        Tool(
            name="browser_fill_form",
            description="批量填写表单字段",
            inputSchema={
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "字段名称"},
                                "type": {"type": "string", "enum": ["textbox", "checkbox", "radio", "combobox", "slider"], "description": "字段类型"},
                                "selector": {"type": "string", "description": "字段选择器"},
                                "value": {"type": "string", "description": "字段值"}
                            },
                            "required": ["selector", "value"]
                        },
                        "description": "要填写的字段列表"
                    }
                },
                "required": ["fields"]
            }
        ),
        Tool(
            name="browser_install",
            description="安装 Playwright 浏览器（chromium）。注意：通常浏览器已安装，此工具会先检查，如果已安装则立即返回。只有在首次使用或浏览器缺失时才需要调用此工具。如果 browser_launch 失败，可以尝试调用此工具。",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="browser_network_requests",
            description="获取页面的网络请求记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_static": {"type": "boolean", "description": "是否包含静态资源（图片、CSS、JS等）", "default": False}
                }
            }
        ),
        Tool(
            name="browser_run_code",
            description="在浏览器上下文中执行 Playwright 代码",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码（可以使用 page, browser, context, playwright 变量）"}
                },
                "required": ["code"]
            }
        ),
    ]




async def handle_tool_call(browser_manager, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """处理工具调用"""
    tool_methods = {
        "browser_launch": browser_manager.browser_launch,
        "browser_close": browser_manager.browser_close,
        "browser_resize": browser_manager.browser_resize,
        "browser_navigate": browser_manager.browser_navigate,
        "browser_click": browser_manager.browser_click,
        "browser_type": browser_manager.browser_type,
        "browser_snapshot": browser_manager.browser_snapshot,
        "browser_wait_for": browser_manager.browser_wait_for,
        "browser_press_key": browser_manager.browser_press_key,
        "browser_navigate_back": browser_manager.browser_navigate_back,
        "browser_take_screenshot": browser_manager.browser_take_screenshot,
        "browser_hover": browser_manager.browser_hover,
        "browser_select_option": browser_manager.browser_select_option,
        "browser_drag": browser_manager.browser_drag,
        "browser_evaluate": browser_manager.browser_evaluate,
        "browser_tabs": browser_manager.browser_tabs,
        "browser_console_messages": browser_manager.browser_console_messages,
        "browser_handle_dialog": browser_manager.browser_handle_dialog,
        "browser_file_upload": browser_manager.browser_file_upload,
        "browser_fill_form": browser_manager.browser_fill_form,
        "browser_install": browser_manager.browser_install,
        "browser_network_requests": browser_manager.browser_network_requests,
        "browser_run_code": browser_manager.browser_run_code,
    }
    
    if name not in tool_methods:
        raise ValueError(f"Unknown tool: {name}")
    
    method = tool_methods[name]
    result = await method(**arguments)
    
    return [
        TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )
    ]
