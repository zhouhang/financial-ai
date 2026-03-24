"""
数据模型定义
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright


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

