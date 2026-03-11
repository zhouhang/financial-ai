"""
Playwright 浏览器管理器核心类
包含所有浏览器操作方法
"""
import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    async_playwright,
    Dialog,
    FileChooser,
)

from .models import BrowserSession
from .config import SCREENSHOT_DIR


class PlaywrightBrowserManager:
    """Playwright 浏览器管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self.playwright = None
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
    
    def get_page(self, session_id: str, tab_index: Optional[int] = None):
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
    
    # 会话管理
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
    
    # 基础浏览器操作
    async def browser_launch(self, headless: bool = False) -> Dict[str, Any]:
        """启动浏览器（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        session = self.get_session(session_id)
        
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
    
    # 导航操作
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
    
    # 页面交互
    async def browser_click(self, selector: str, timeout: int = 30000) -> Dict[str, Any]:
        """点击元素（异步，自动管理 session_id）
        
        支持多种定位方式：
        - CSS 选择器：如 "#button", ".class", "button"
        - 文本定位器：如 "邮箱登录" 会自动使用 get_by_text()
        - 显式文本定位器：如 "text=邮箱登录"
        """
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        is_text_locator = self._is_text_selector(selector)
        
        if is_text_locator:
            try:
                await page.get_by_text(selector, exact=True).click(timeout=timeout)
            except Exception:
                await page.get_by_text(selector, exact=False).click(timeout=timeout)
        else:
            await page.click(selector, timeout=timeout)
        
        return {
            "session_id": session_id,
            "action": "clicked",
            "selector": selector,
            "locator_type": "text" if is_text_locator else "css"
        }
    
    async def browser_type(self, selector: str, text: str, submit: bool = False, slowly: bool = False) -> Dict[str, Any]:
        """在元素中输入文本（异步，自动管理 session_id）
        
        支持多种定位方式：
        - CSS 选择器：如 "#input", ".class", "input[type='text']"
        - Placeholder 定位器：如 "输入注册邮箱地址" 会自动使用 get_by_placeholder()
        - 显式定位器：如 "placeholder=输入注册邮箱地址"
        """
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        is_placeholder = self._is_placeholder_selector(selector)
        is_text = self._is_text_selector(selector) and not is_placeholder
        
        if is_placeholder:
            element = page.get_by_placeholder(selector)
            if slowly:
                await element.type(text, delay=100)
            else:
                await element.fill(text)
        elif is_text:
            try:
                element = page.get_by_text(selector, exact=True)
            except Exception:
                element = page.get_by_text(selector, exact=False)
            if slowly:
                await element.type(text, delay=100)
            else:
                await element.fill(text)
        else:
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
    
    # 页面信息获取
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
    
    async def browser_take_screenshot(self, filename: Optional[str] = None, full_page: bool = False, element: Optional[str] = None, ref: Optional[str] = None) -> Dict[str, Any]:
        """截取页面或元素截图（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
        if filename is None:
            filename = f"screenshot-{uuid.uuid4().hex[:8]}.png"
        
        screenshot_dir = Path(SCREENSHOT_DIR)
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
    
    # 等待操作
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
    
    # 表单操作
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
    
    async def browser_file_upload(self, selector: str, paths: List[str], ref: Optional[str] = None) -> Dict[str, Any]:
        """上传文件（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
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
        
        file_input = page.locator(selector)
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
    
    # 高级操作
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
        
        code = function.strip()
        
        is_function_expression = (
            code.startswith('function') or
            code.startswith('async function') or
            code.startswith('(') or
            code.startswith('async (') or
            code.startswith('()') or
            code.startswith('async ()')
        )
        
        if 'return' in code and not is_function_expression:
            code = f"() => {{\n{code}\n}}"
        
        if element and ref:
            locator = page.locator(element)
            result = await locator.evaluate(code)
        else:
            result = await page.evaluate(code)
        
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
    
    async def browser_run_code(self, code: str) -> Dict[str, Any]:
        """运行 Playwright 代码（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        session = self.get_session(session_id)
        page = self.get_page(session_id)
        
        try:
            exec_globals = {
                "page": page,
                "browser": session.browser,
                "context": session.context,
                "playwright": session.playwright,
                "asyncio": asyncio,
                "await": None,
                "__builtins__": __builtins__
            }
            
            if "async" in code or "await" in code:
                try:
                    wrapped_code = f"async def _run():\n    {code.replace(chr(10), chr(10) + '    ')}"
                    exec(wrapped_code, exec_globals)
                    result = await exec_globals["_run"]()
                    return {
                        "session_id": session_id,
                        "status": "executed",
                        "result": str(result) if result is not None else "None",
                        "code": code[:200]
                    }
                except Exception:
                    pass
            
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
    
    # 标签页管理
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
    
    # 调试和监控
    async def browser_console_messages(self, level: Optional[str] = None) -> Dict[str, Any]:
        """获取控制台消息（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        session = self.get_session(session_id)
        
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
        
        messages = session.console_messages
        if level:
            messages = [m for m in messages if m["type"] == level]
        
        return {
            "session_id": session_id,
            "messages": messages[-50:],
            "total": len(session.console_messages),
            "level": level
        }
    
    async def browser_network_requests(self, include_static: bool = False) -> Dict[str, Any]:
        """获取网络请求（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        context = page.context
        session = self.get_session(session_id)
        
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
        
        response_data = []
        try:
            all_requests = session.network_requests
            
            if not include_static:
                all_requests = [
                    req for req in all_requests
                    if not any(ext in req.get("url", "").lower() 
                              for ext in ['.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.woff', '.woff2', '.ttf', '.ico', '.svg'])
                ]
            
            response_data = all_requests[-50:]
        except Exception:
            pass
        
        return {
            "session_id": session_id,
            "requests": response_data,
            "total": len(session.network_requests),
            "include_static": include_static
        }
    
    async def browser_handle_dialog(self, accept: bool = True, prompt_text: Optional[str] = None) -> Dict[str, Any]:
        """处理对话框（异步，自动管理 session_id）"""
        session_id = await self.get_or_create_default_session()
        page = self.get_page(session_id)
        
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
    
    # 浏览器安装
    async def browser_install(self) -> Dict[str, Any]:
        """安装浏览器（异步，非阻塞）"""
        import sys
        import shutil
        
        playwright_path = shutil.which("playwright")
        if not playwright_path:
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
        
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                    await browser.close()
                    return {
                        "status": "already_installed",
                        "message": "浏览器已安装，无需重复安装"
                    }
                except Exception:
                    pass
        except Exception:
            pass
        
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "playwright", "install", "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300.0
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
    
    # 辅助方法
    def _is_text_selector(self, selector: str) -> bool:
        """判断选择器是否为文本定位器（而非 CSS 选择器）"""
        if selector.startswith(("text=", "xpath=", "role=", "label=", "placeholder=", "testid=")):
            return selector.startswith("text=")
        
        css_indicators = ["#", ".", "[", ">", "+", "~", ":", "::", " ", "\t"]
        if any(char in selector for char in css_indicators):
            return False
        
        common_tags = ["html", "body", "div", "span", "p", "a", "button", "input", 
                      "form", "img", "ul", "li", "table", "tr", "td", "th", 
                      "h1", "h2", "h3", "h4", "h5", "h6", "select", "option"]
        if selector.lower() in common_tags:
            return False
        
        return True
    
    def _is_placeholder_selector(self, selector: str) -> bool:
        """判断选择器是否为 placeholder 定位器"""
        if selector.startswith("placeholder="):
            return True
        
        placeholder_keywords = ["输入", "请输入", "输入注册", "输入密码", "输入邮箱", "输入手机"]
        if any(keyword in selector for keyword in placeholder_keywords):
            css_indicators = ["#", ".", "[", ">", "+", "~"]
            if not any(char in selector for char in css_indicators):
                return True
        
        return False

