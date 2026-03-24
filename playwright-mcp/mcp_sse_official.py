#!/usr/bin/env python3
"""
基于官方 MCP SDK 的 Playwright SSE 服务器
使用 mcp 官方包实现 SSE 传输
"""
import asyncio
import json
import sys
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

# 导入 Playwright（修复命名冲突：本地 playwright 目录会干扰导入）
# 需要确保从 site-packages 导入，而不是本地 playwright 目录
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_script_dir)
# 将 site-packages 放在最前面，确保优先导入安装的包
_site_packages = os.path.join(_parent_dir, '.venv', 'lib', 'python3.12', 'site-packages')
if os.path.exists(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)

# 现在导入 playwright（会从 site-packages 导入）
# 使用 async_api 以支持在 asyncio 事件循环中使用
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright, Dialog, FileChooser


# 浏览器会话管理（复用原有逻辑）
@dataclass
class BrowserSession:
    """浏览器会话管理"""
    session_id: str
    playwright: Playwright
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    headless: bool = False
    tabs: Optional[Dict[int, Page]] = None
    console_messages: Optional[List[Dict[str, Any]]] = None
    network_requests: Optional[List[Dict[str, Any]]] = None
    console_listener_set: bool = False
    network_listener_set: bool = False
    
    def __post_init__(self):
        if self.tabs is None:
            self.tabs = {}
        if self.console_messages is None:
            self.console_messages = []
        if self.network_requests is None:
            self.network_requests = []
        if self.console_messages is None:
            self.console_messages = []
        if self.network_requests is None:
            self.network_requests = []


class PlaywrightBrowserManager:
    """Playwright 浏览器管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self.playwright: Optional[Playwright] = None
        self.default_session_id: Optional[str] = None  # 默认会话ID
    
    async def start(self):
        """启动 Playwright（异步）"""
        if self.playwright is None:
            self.playwright = await async_playwright().start()
    
    async def stop(self):
        """停止 Playwright 并清理所有会话（异步）"""
        for session in list(self.sessions.values()):
            await self.close_session(session.session_id)
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    
    async def create_session(self, headless: bool = False) -> str:
        """创建新的浏览器会话（异步）"""
        if self.playwright is None:
            await self.start()
        
        session_id = str(uuid.uuid4())
        session = BrowserSession(
            session_id=session_id,
            playwright=self.playwright,
            headless=headless
        )
        self.sessions[session_id] = session
        return session_id
    
    def get_session(self, session_id: str) -> BrowserSession:
        """获取会话"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        return self.sessions[session_id]
    
    def get_page(self, session_id: str, tab_index: Optional[int] = None) -> Page:
        """获取页面对象（支持标签页）"""
        session = self.get_session(session_id)
        if session.page is None:
            raise ValueError("Browser not launched. Call browser_launch first.")
        
        if tab_index is not None:
            if tab_index in session.tabs:
                return session.tabs[tab_index]
            else:
                raise ValueError(f"Tab {tab_index} not found")
        return session.page
    
    async def close_session(self, session_id: str):
        """关闭会话（异步）"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            try:
                for tab in list(session.tabs.values()):
                    try:
                        await tab.close()
                    except Exception:
                        pass
                if session.page:
                    await session.page.close()
                if session.context:
                    await session.context.close()
                if session.browser:
                    await session.browser.close()
            except Exception:
                pass
            del self.sessions[session_id]
    
    # 所有浏览器操作方法（异步版本）
    async def get_or_create_default_session(self) -> str:
        """获取或创建默认会话，如果不存在则自动创建并启动浏览器（异步）"""
        if self.default_session_id is None or self.default_session_id not in self.sessions:
            self.default_session_id = await self.create_session(headless=False)
            # 自动启动浏览器
            session = self.get_session(self.default_session_id)
            session.browser = await session.playwright.chromium.launch(headless=False)
            session.context = await session.browser.new_context()
            session.page = await session.context.new_page()
            session.tabs[0] = session.page
        return self.default_session_id
    
    async def browser_launch(self, headless: bool = False) -> Dict[str, Any]:
        """启动浏览器（异步，自动管理 session_id）"""
        # 自动获取或创建默认会话
        session_id = await self.get_or_create_default_session()
        session = self.get_session(session_id)
        
        # 如果浏览器未启动，则启动
        if session.browser is None:
            session.browser = await session.playwright.chromium.launch(headless=session.headless or headless)
            session.context = await session.browser.new_context()
            session.page = await session.context.new_page()
            session.tabs[0] = session.page
        
        return {
            "session_id": session_id,
            "status": "launched",
            "headless": session.headless or headless
        }
    
    async def browser_close(self) -> Dict[str, Any]:
        """关闭浏览器会话（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        await self.close_session(session_id)
        if session_id == self.default_session_id:
            self.default_session_id = None
        return {
            "session_id": session_id,
            "status": "closed"
        }
    
    async def browser_resize(self, width: int, height: int) -> Dict[str, Any]:
        """调整浏览器窗口大小（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        session = self.get_session(session_id)
        if session.context is None:
            raise ValueError("Browser not launched.")
        
        await session.context.set_viewport_size(width=width, height=height)
        return {
            "session_id": session_id,
            "width": width,
            "height": height,
            "status": "resized"
        }
    
    async def browser_navigate(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> Dict[str, Any]:
        """导航到指定 URL（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        
        return {
            "session_id": session_id,
            "url": page.url,
            "title": await page.title(),
            "status": "navigated"
        }
    
    async def browser_click(self, selector: str, timeout: int = 30000) -> Dict[str, Any]:
        """点击元素（异步，自动管理 session_id）
        
        支持多种定位方式：
        - CSS 选择器：如 "#button", ".class", "button"
        - 文本定位器：如 "邮箱登录" 会自动使用 get_by_text()
        - 显式文本定位器：如 "text=邮箱登录"
        """
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        # 判断是否为文本定位器（不是 CSS 选择器）
        is_text_locator = self._is_text_selector(selector)
        
        if is_text_locator:
            # 使用文本定位器
            try:
                # 先尝试精确匹配
                await page.get_by_text(selector, exact=True).click(timeout=timeout)
            except Exception:
                # 如果精确匹配失败，尝试模糊匹配
                await page.get_by_text(selector, exact=False).click(timeout=timeout)
        else:
            # 使用 CSS 选择器或其他定位器
            await page.click(selector, timeout=timeout)
        
        return {
            "session_id": session_id,
            "action": "clicked",
            "selector": selector,
            "locator_type": "text" if is_text_locator else "css"
        }
    
    def _is_text_selector(self, selector: str) -> bool:
        """判断选择器是否为文本定位器（而非 CSS 选择器）"""
        # 如果已经明确指定了定位器类型，按指定类型处理
        if selector.startswith(("text=", "xpath=", "role=", "label=", "placeholder=", "testid=")):
            return selector.startswith("text=")
        
        # CSS 选择器特征字符
        css_indicators = ["#", ".", "[", ">", "+", "~", ":", "::", " ", "\t"]
        
        # 如果包含 CSS 选择器特征字符，认为是 CSS 选择器
        if any(char in selector for char in css_indicators):
            return False
        
        # 如果看起来像标签名（单个单词，且是常见 HTML 标签）
        common_tags = ["html", "body", "div", "span", "p", "a", "button", "input", 
                      "form", "img", "ul", "li", "table", "tr", "td", "th", 
                      "h1", "h2", "h3", "h4", "h5", "h6", "select", "option"]
        if selector.lower() in common_tags:
            return False
        
        # 否则认为是文本定位器
        return True
    
    async def browser_type(self, selector: str, text: str, submit: bool = False, slowly: bool = False) -> Dict[str, Any]:
        """在元素中输入文本（异步，自动管理 session_id）
        
        支持多种定位方式：
        - CSS 选择器：如 "#input", ".class", "input[type='text']"
        - Placeholder 定位器：如 "输入注册邮箱地址" 会自动使用 get_by_placeholder()
        - 显式定位器：如 "placeholder=输入注册邮箱地址"
        """
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        # 判断是否为 placeholder 定位器
        is_placeholder = self._is_placeholder_selector(selector)
        is_text = self._is_text_selector(selector) and not is_placeholder
        
        if is_placeholder:
            # 使用 placeholder 定位器
            element = page.get_by_placeholder(selector)
            if slowly:
                await element.type(text, delay=100)
            else:
                await element.fill(text)
        elif is_text:
            # 使用文本定位器（通常用于按钮或链接，但也可以用于输入框）
            try:
                element = page.get_by_text(selector, exact=True)
            except Exception:
                element = page.get_by_text(selector, exact=False)
            if slowly:
                await element.type(text, delay=100)
            else:
                await element.fill(text)
        else:
            # 使用 CSS 选择器或其他定位器
            if slowly:
                await page.type(selector, text, delay=100)
            else:
                await page.fill(selector, text)
        
        if submit:
            await page.keyboard.press("Enter")
        
        return {
            "session_id": session_id,
            "action": "typed",
            "selector": selector,
            "text_length": len(text),
            "submitted": submit
        }
    
    def _is_placeholder_selector(self, selector: str) -> bool:
        """判断选择器是否为 placeholder 定位器"""
        if selector.startswith("placeholder="):
            return True
        
        # 如果包含常见 placeholder 关键词，可能是 placeholder
        placeholder_keywords = ["输入", "请输入", "输入注册", "输入密码", "输入邮箱", "输入手机"]
        if any(keyword in selector for keyword in placeholder_keywords):
            # 但不是 CSS 选择器
            css_indicators = ["#", ".", "[", ">", "+", "~"]
            if not any(char in selector for char in css_indicators):
                return True
        
        return False
    
    async def browser_snapshot(self) -> Dict[str, Any]:
        """获取页面快照（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        snapshot = {
            "session_id": session_id,
            "url": page.url,
            "title": await page.title(),
            "text": (await page.inner_text("body"))[:10000],
        }
        
        return snapshot
    
    async def browser_wait_for(self, timeout: Optional[int] = None, text: Optional[str] = None, text_gone: Optional[str] = None) -> Dict[str, Any]:
        """等待指定时间或文本出现/消失（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        if text:
            await page.wait_for_selector(f"text={text}", timeout=timeout or 30000)
            return {
                "session_id": session_id,
                "action": "waited_for_text",
                "text": text,
                "status": "text_found"
            }
        elif text_gone:
            await page.wait_for_selector(f"text={text_gone}", state="hidden", timeout=timeout or 30000)
            return {
                "session_id": session_id,
                "action": "waited_for_text_gone",
                "text": text_gone,
                "status": "text_gone"
            }
        elif timeout:
            await page.wait_for_timeout(timeout)
            return {
                "session_id": session_id,
                "action": "waited",
                "timeout_ms": timeout
            }
        else:
            raise ValueError("Either timeout, text, or text_gone must be provided")
    
    async def browser_press_key(self, key: str) -> Dict[str, Any]:
        """按下键盘按键（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        await page.keyboard.press(key)
        
        return {
            "session_id": session_id,
            "key": key,
            "status": "pressed"
        }
    
    async def browser_navigate_back(self) -> Dict[str, Any]:
        """返回上一页（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        await page.go_back()
        
        return {
            "session_id": session_id,
            "url": page.url,
            "title": await page.title(),
            "status": "navigated_back"
        }
    
    async def browser_take_screenshot(self, filename: Optional[str] = None, full_page: bool = False, element: Optional[str] = None, ref: Optional[str] = None) -> Dict[str, Any]:
        """截取页面或元素截图（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        if filename is None:
            # 使用 uuid 生成唯一文件名，避免使用 time.time()
            filename = f"screenshot-{uuid.uuid4().hex[:8]}.png"
        
        screenshot_dir = Path(".playwright-mcp")
        screenshot_dir.mkdir(exist_ok=True)
        filepath = screenshot_dir / filename
        
        if element and ref:
            await page.locator(element).screenshot(path=str(filepath))
        else:
            await page.screenshot(path=str(filepath), full_page=full_page)
        
        return {
            "session_id": session_id,
            "filename": filename,
            "filepath": str(filepath),
            "status": "screenshot_taken"
        }
    
    async def browser_hover(self, selector: str, ref: Optional[str] = None) -> Dict[str, Any]:
        """悬停在元素上（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        await page.hover(selector)
        
        return {
            "session_id": session_id,
            "action": "hovered",
            "selector": selector
        }
    
    async def browser_select_option(self, selector: str, values: List[str], ref: Optional[str] = None) -> Dict[str, Any]:
        """在下拉框中选择选项（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        await page.select_option(selector, values)
        
        return {
            "session_id": session_id,
            "action": "option_selected",
            "selector": selector,
            "values": values
        }
    
    async def browser_drag(self, start_selector: str, end_selector: str, start_ref: Optional[str] = None, end_ref: Optional[str] = None) -> Dict[str, Any]:
        """拖拽元素（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        start_element = page.locator(start_selector)
        end_element = page.locator(end_selector)
        
        await start_element.drag_to(end_element)
        
        return {
            "session_id": session_id,
            "action": "dragged",
            "start_selector": start_selector,
            "end_selector": end_selector
        }
    
    async def browser_evaluate(self, function: str, element: Optional[str] = None, ref: Optional[str] = None) -> Dict[str, Any]:
        """在页面或元素上执行 JavaScript（异步，自动管理 session_id）
        
        支持两种格式：
        1. 函数体（包含 return）：会自动包装成箭头函数 `() => { ... }`
        2. 完整函数表达式：如 `() => { ... }` 或 `function() { ... }`
        """
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        # 检测代码格式，如果是函数体（包含 return 但不是函数表达式），则包装成箭头函数
        code = function.strip()
        
        # 检查是否是函数表达式（以 function、async function、箭头函数、括号等开头）
        is_function_expression = (
            code.startswith('function') or
            code.startswith('async function') or
            code.startswith('(') or
            code.startswith('async (') or
            code.startswith('()') or
            code.startswith('async ()')
        )
        
        # 如果包含 return 但不是函数表达式，则包装成箭头函数
        if 'return' in code and not is_function_expression:
            code = f"() => {{\n{code}\n}}"
        
        # 如果指定了元素，使用 locator.evaluate
        if element and ref:
            locator = page.locator(element)
            result = await locator.evaluate(code)
        else:
            result = await page.evaluate(code)
        
        # 尝试将结果转换为 JSON 可序列化格式
        try:
            if isinstance(result, (dict, list, str, int, float, bool, type(None))):
                serializable_result = result
            else:
                serializable_result = str(result)
        except Exception:
            serializable_result = str(result)
        
        return {
            "session_id": session_id,
            "result": serializable_result,
            "status": "evaluated"
        }
    
    async def browser_tabs(self, action: str, index: Optional[int] = None) -> Dict[str, Any]:
        """管理浏览器标签页（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        session = self.get_session(session_id)
        
        if action == "list":
            tabs_info = []
            for idx, tab in session.tabs.items():
                tabs_info.append({
                    "index": idx,
                    "url": tab.url,
                    "title": await tab.title()
                })
            return {
                "session_id": session_id,
                "action": "list",
                "tabs": tabs_info,
                "count": len(session.tabs)
            }
        
        elif action == "new":
            new_page = await session.context.new_page()
            new_index = max(session.tabs.keys(), default=-1) + 1
            session.tabs[new_index] = new_page
            return {
                "session_id": session_id,
                "action": "new",
                "tab_index": new_index,
                "url": new_page.url
            }
        
        elif action == "close":
            if index is None:
                if session.page:
                    await session.page.close()
                    for idx, tab in list(session.tabs.items()):
                        if tab == session.page:
                            del session.tabs[idx]
                            break
                    session.page = None
            else:
                if index in session.tabs:
                    await session.tabs[index].close()
                    del session.tabs[index]
                else:
                    raise ValueError(f"Tab {index} not found")
            
            return {
                "session_id": session_id,
                "action": "close",
                "tab_index": index
            }
        
        elif action == "select":
            if index is None:
                raise ValueError("index is required for select action")
            if index not in session.tabs:
                raise ValueError(f"Tab {index} not found")
            session.page = session.tabs[index]
            return {
                "session_id": session_id,
                "action": "select",
                "tab_index": index,
                "url": session.page.url
            }
        
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def browser_console_messages(self, level: Optional[str] = None) -> Dict[str, Any]:
        """获取控制台消息（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        # 收集控制台消息（需要在会话中存储）
        session = self.get_session(session_id)
        
        # 设置控制台消息监听器（如果还没有设置）
        if not session.console_listener_set:
            def handle_console(msg):
                msg_data = {
                    "type": msg.type,
                    "text": msg.text,
                    "location": {
                        "url": msg.location.get("url", ""),
                        "line": msg.location.get("lineNumber", 0),
                        "column": msg.location.get("columnNumber", 0)
                    } if msg.location else {}
                }
                session.console_messages.append(msg_data)
            
            page.on("console", handle_console)
            session.console_listener_set = True
        
        # 过滤消息级别
        messages = session.console_messages
        if level:
            messages = [m for m in messages if m["type"] == level]
        
        return {
            "session_id": session_id,
            "messages": messages[-50:],  # 返回最近50条消息
            "total": len(session.console_messages),
            "level": level
        }
    
    async def browser_handle_dialog(self, accept: bool = True, prompt_text: Optional[str] = None) -> Dict[str, Any]:
        """处理对话框（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        # 设置对话框处理器
        dialog_handled = {"handled": False, "message": "", "type": ""}
        
        def handle_dialog(dialog: Dialog):
            dialog_handled["handled"] = True
            dialog_handled["message"] = dialog.message
            dialog_handled["type"] = dialog.type
            if accept:
                if prompt_text and dialog.type == "prompt":
                    dialog.accept(prompt_text)
                else:
                    dialog.accept()
            else:
                dialog.dismiss()
        
        page.on("dialog", handle_dialog)
        
        return {
            "session_id": session_id,
            "action": "dialog_handler_set",
            "accept": accept,
            "prompt_text": prompt_text,
            "note": "对话框处理器已设置，下次出现对话框时会自动处理"
        }
    
    async def browser_file_upload(self, selector: str, paths: List[str], ref: Optional[str] = None) -> Dict[str, Any]:
        """上传文件（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        # 验证文件路径是否存在
        import os
        valid_paths = []
        for path in paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                return {
                    "session_id": session_id,
                    "action": "error",
                    "error": f"文件不存在: {path}",
                    "selector": selector
                }
        
        # 等待文件选择器出现并上传
        file_input = page.locator(selector)
        
        # 等待文件选择器并上传（只点击一次）
        async with page.expect_file_chooser() as fc_info:
            await file_input.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(valid_paths)
        
        return {
            "session_id": session_id,
            "action": "uploaded",
            "selector": selector,
            "files": valid_paths,
            "count": len(valid_paths)
        }
    
    async def browser_fill_form(self, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量填写表单（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        filled_fields = []
        
        for field in fields:
            field_type = field.get("type", "textbox")
            selector = field.get("selector") or field.get("ref")
            name = field.get("name", "")
            value = field.get("value", "")
            
            if not selector:
                continue
            
            try:
                if field_type == "textbox":
                    await page.fill(selector, str(value))
                elif field_type == "checkbox":
                    checkbox = page.locator(selector)
                    if value:
                        await checkbox.check()
                    else:
                        await checkbox.uncheck()
                elif field_type == "radio":
                    await page.locator(selector).check()
                elif field_type == "combobox" or field_type == "select":
                    await page.select_option(selector, value)
                elif field_type == "slider":
                    # 滑块需要特殊处理
                    slider = page.locator(selector)
                    await slider.fill(str(value))
                
                filled_fields.append({
                    "name": name,
                    "type": field_type,
                    "selector": selector,
                    "value": value,
                    "status": "filled"
                })
            except Exception as e:
                filled_fields.append({
                    "name": name,
                    "type": field_type,
                    "selector": selector,
                    "value": value,
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "session_id": session_id,
            "action": "form_filled",
            "fields": filled_fields,
            "total": len(fields),
            "success": len([f for f in filled_fields if f.get("status") == "filled"])
        }
    
    async def browser_install(self) -> Dict[str, Any]:
        """安装浏览器（异步，非阻塞）"""
        import sys
        import shutil
        
        # 先检查 playwright 是否已安装（使用异步方式）
        playwright_path = shutil.which("playwright")
        if not playwright_path:
            # 尝试使用 python -m playwright（异步检查）
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "playwright", "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
                if process.returncode != 0:
                    return {
                        "status": "error",
                        "error": "Playwright 未安装，请先运行: pip install playwright"
                    }
            except asyncio.TimeoutError:
                return {
                    "status": "error",
                    "error": "Playwright 检查超时"
                }
            except Exception:
                return {
                    "status": "error",
                    "error": "Playwright 未安装，请先运行: pip install playwright"
                }
        
        # 检查浏览器是否已安装（快速检查）
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                # 尝试启动浏览器，如果能启动说明已安装
                try:
                    browser = await p.chromium.launch(headless=True)
                    await browser.close()
                    return {
                        "status": "already_installed",
                        "message": "浏览器已安装，无需重复安装"
                    }
                except Exception:
                    # 浏览器未安装，需要安装
                    pass
        except Exception:
            pass
        
        # 使用异步 subprocess 执行安装（避免阻塞事件循环）
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "playwright", "install", "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待完成，但设置超时
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300.0  # 5分钟超时
                )
                
                output = (stdout.decode() + stderr.decode()).strip()
                
                return {
                    "status": "installed" if process.returncode == 0 else "failed",
                    "message": output,
                    "returncode": process.returncode
                }
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "status": "timeout",
                    "error": "安装超时（超过5分钟），请手动运行: python -m playwright install chromium"
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "suggestion": "请手动运行: python -m playwright install chromium"
            }
    
    async def browser_network_requests(self, include_static: bool = False) -> Dict[str, Any]:
        """获取网络请求（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        context = page.context
        
        # 收集网络请求（需要在会话中存储）
        session = self.get_session(session_id)
        
        # 设置网络请求监听器（如果还没有设置）
        if not session.network_listener_set:
            async def handle_request(request):
                if include_static or not any(
                    ext in request.url.lower() 
                    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.woff', '.woff2', '.ttf', '.ico', '.svg']
                ):
                    try:
                        response = await request.response()
                        request_data = {
                            "url": request.url,
                            "method": request.method,
                            "headers": dict(request.headers),
                            "post_data": request.post_data
                        }
                        if response:
                            request_data.update({
                                "status": response.status,
                                "status_text": response.status_text,
                                "response_headers": dict(response.headers)
                            })
                        session.network_requests.append(request_data)
                    except Exception:
                        pass
            
            context.on("request", handle_request)
            session.network_listener_set = True
        
        # 获取已完成的请求（从 context 中获取）
        response_data = []
        try:
            # 获取所有请求
            all_requests = session.network_requests
            
            # 过滤静态资源
            if not include_static:
                all_requests = [
                    req for req in all_requests
                    if not any(ext in req.get("url", "").lower() 
                              for ext in ['.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.woff', '.woff2', '.ttf', '.ico', '.svg'])
                ]
            
            response_data = all_requests[-50:]  # 返回最近50条
        except Exception as e:
            pass
        
        return {
            "session_id": session_id,
            "requests": response_data,
            "total": len(session.network_requests),
            "include_static": include_static
        }
    
    async def browser_run_code(self, code: str) -> Dict[str, Any]:
        """运行 Playwright 代码（异步，自动管理 session_id）
        
        注意：代码中的阻塞操作可能会影响事件循环。
        建议使用 await 进行异步操作。
        """
        session_id = await self.get_or_create_default_session()
        session = self.get_session(session_id)
        page = self.get_page(session_id)
        
        # 在安全的上下文中执行代码
        # 提供 page, browser, context 等对象
        try:
            # 创建执行环境（包含异步支持）
            exec_globals = {
                "page": page,
                "browser": session.browser,
                "context": session.context,
                "playwright": session.playwright,
                "asyncio": asyncio,
                "await": None,  # 提示可以使用 await
                "__builtins__": __builtins__
            }
            
            # 如果代码是异步的，需要特殊处理
            # 检查代码是否包含 async/await
            if "async" in code or "await" in code:
                # 尝试编译为异步函数
                try:
                    # 包装为异步函数
                    wrapped_code = f"async def _run():\n    {code.replace(chr(10), chr(10) + '    ')}"
                    exec(wrapped_code, exec_globals)
                    # 执行异步函数
                    result = await exec_globals["_run"]()
                    return {
                        "session_id": session_id,
                        "status": "executed",
                        "result": str(result) if result is not None else "None",
                        "code": code[:200]
                    }
                except Exception as async_error:
                    # 如果异步执行失败，尝试同步执行
                    pass
            
            # 同步执行代码（在 executor 中运行，避免阻塞）
            loop = asyncio.get_event_loop()
            def run_sync():
                exec(code, exec_globals)
                return "executed"
            
            result = await loop.run_in_executor(None, run_sync)
            
            return {
                "session_id": session_id,
                "status": result,
                "code": code[:200]
            }
        except Exception as e:
            return {
                "session_id": session_id,
                "status": "error",
                "error": str(e),
                "code": code[:200]
            }


# 全局浏览器管理器实例
browser_manager = PlaywrightBrowserManager()


# 创建 MCP 服务器
app = Server("playwright-mcp-server", version="1.0.0")


# 注册所有工具
@app.list_tools()
async def list_tools() -> List[Tool]:
    """列出所有可用的浏览器工具"""
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


# 注册工具调用处理器
@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """处理工具调用（异步版本，所有方法都是异步的）"""
    # 工具方法映射（所有方法都是异步的，直接调用即可）
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
    
    # 直接调用异步方法（所有方法内部自动管理 session_id，无需传递）
    result = await method(**arguments)
    
    return [
        TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )
    ]


# 创建 SSE 传输
sse_transport = SseServerTransport("/messages/")


# SSE 连接处理器
async def handle_sse(request):
    """处理 SSE 连接"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 添加日志记录
    print(f"[SSE] 收到请求: {request.method} {request.url}")
    logger.info(f"收到 SSE 连接请求: {request.method} {request.url}")
    
    # 检查请求方法
    if request.method not in ["GET", "POST"]:
        print(f"[SSE] 方法不允许: {request.method}")
        return Response(
            content=json.dumps({"error": "Method not allowed"}),
            status_code=405,
            media_type="application/json"
        )
    
    try:
        print("[SSE] 开始建立 SSE 连接...")
        # SSE 传输的 connect_sse 会处理所有响应，包括 HTTP 响应头
        # 它会在 context manager 内部发送响应，所以这里不需要返回 Response
        # connect_sse 内部会调用 send 函数发送响应，包括初始的 HTTP 200 和 SSE 头
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            print("[SSE] 连接已建立，启动 MCP 会话...")
            init_options = app.create_initialization_options()
            await app.run(streams[0], streams[1], init_options)
        print("[SSE] MCP 会话已结束")
        # connect_sse 的 context manager 已经处理了响应，包括发送了 HTTP 响应
        # 不要返回 Response，否则会导致双重响应或空响应错误
        # 如果函数没有返回值，Starlette 会正确处理
    except Exception as e:
        import traceback
        error_msg = f"SSE 连接错误: {e}"
        print(f"[SSE] {error_msg}")
        traceback.print_exc()
        logger.error(error_msg, exc_info=True)
        # 只有在异常情况下才返回错误响应
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )


# 创建 Starlette 应用
starlette_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
        Route("/mcp", endpoint=handle_sse, methods=["GET", "POST"]),  # 添加 /mcp 端点作为 /sse 的别名
        Mount("/messages/", app=sse_transport.handle_post_message),
        Route("/health", endpoint=lambda r: Response(content='{"status":"ok"}', media_type="application/json"), methods=["GET"]),
    ]
)


def main():
    """启动 SSE 服务器"""
    import uvicorn
    
    port = 3334
    host = "0.0.0.0"
    
    print("=" * 60)
    print("Playwright MCP SSE Server (Official SDK)")
    print("=" * 60)
    print(f"服务器地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    print(f"SSE 端点: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/sse")
    print(f"消息端点: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/messages/")
    print("\nDify 配置信息:")
    print(f"  MCP 服务器地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/mcp")
    print(f"  备用地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/sse")
    print(f"  服务器类型: SSE (Server-Sent Events)")
    print("\n按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    try:
        uvicorn.run(starlette_app, host=host, port=port)
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        # 使用 asyncio 运行异步停止方法
        import asyncio
        try:
            asyncio.run(browser_manager.stop())
        except RuntimeError:
            # 如果事件循环已经在运行，使用 get_event_loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，创建任务
                asyncio.create_task(browser_manager.stop())
            else:
                loop.run_until_complete(browser_manager.stop())


if __name__ == "__main__":
    main()

