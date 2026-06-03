"""Windows OS 级远控后端。

平台依赖(win32/mss/dwm/ctypes/cdp)全部以构造参数注入,使坐标映射、窗口绑定、门禁、
剪贴板恢复等逻辑可在非 Windows CI 上单测。真实 API 行为在 Slice 6 真机验收。
"""
from __future__ import annotations

import logging
from typing import Any

from finance_browser_agent.remote_control_codes import ControlErrorCode

logger = logging.getLogger(__name__)


class WindowBindError(Exception):
    def __init__(self, code: ControlErrorCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code


class WindowBinder:
    """按 Chrome 主进程 PID 枚举顶层窗口,DWM 扩展边界为唯一矩形基准,
    多窗口命中时以 CDP 当前页 title 做确定性 tie-break。"""

    def __init__(self, *, win32: Any, chrome_pids: list[int]) -> None:
        self._win32 = win32
        self._chrome_pids = set(int(p) for p in chrome_pids if p)
        self.window_handle: int | None = None
        self.capture_rect: dict[str, int] = {}
        self.window_title: str = ""
        self.candidate_count: int = 0

    def bind(self, *, current_page_title: str) -> None:
        candidates = []
        for hwnd in self._win32.enum_windows():
            try:
                if self._win32.get_window_pid(hwnd) not in self._chrome_pids:
                    continue
                if not self._win32.is_visible(hwnd):
                    continue
            except Exception:
                continue
            candidates.append(hwnd)
        self.candidate_count = len(candidates)
        if not candidates:
            raise WindowBindError(ControlErrorCode.WINDOW_UNAVAILABLE, "no visible chrome window for pids")

        chosen = candidates[0]
        title_key = (current_page_title or "").strip()
        if title_key and len(candidates) > 1:
            for hwnd in candidates:
                if title_key in (self._win32.get_window_text(hwnd) or ""):
                    chosen = hwnd
                    break

        # DWMWA_EXTENDED_FRAME_BOUNDS 是抓帧与坐标映射的唯一基准(不用 GetWindowRect)
        rect = self._win32.get_extended_frame_bounds(chosen)
        if not rect or int(rect.get("width") or 0) <= 0 or int(rect.get("height") or 0) <= 0:
            raise WindowBindError(ControlErrorCode.WINDOW_UNAVAILABLE, "empty window rect")
        self.window_handle = chosen
        self.capture_rect = {
            "left": int(rect["left"]), "top": int(rect["top"]),
            "width": int(rect["width"]), "height": int(rect["height"]),
        }
        self.window_title = self._win32.get_window_text(chosen) or ""


def evaluate_session_interactivity(*, process_session_id: int, active_console_session_id: int) -> dict[str, Any]:
    """Session 0 或非活动控制台会话都判为不可用 —— Task Scheduler"不管用户是否登录"
    常误配落到 Session 0,截图全黑、输入无效,必须拒绝启动 OS 后端。"""
    interactive = process_session_id != 0 and process_session_id == active_console_session_id
    return {
        "available": interactive,
        "reason": "" if interactive else ControlErrorCode.SESSION_NOT_INTERACTIVE.value,
        "session_id": int(process_session_id),
        "is_interactive_session": interactive,
    }


def selfcheck(*, win32=None) -> dict[str, Any]:
    """启动自检:用真实 win32 读会话/权限;import 或调用失败一律 unavailable 而非崩溃。"""
    try:
        if win32 is None:
            import win32process  # type: ignore
            import win32ts  # type: ignore
            pid_session = win32process.ProcessIdToSessionId(__import__("os").getpid())
            console_session = win32ts.WTSGetActiveConsoleSessionId()
        else:
            pid_session = win32.process_session_id()
            console_session = win32.active_console_session_id()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": ControlErrorCode.CONTROL_UNAVAILABLE.value, "detail": str(exc)}
    return evaluate_session_interactivity(
        process_session_id=int(pid_session), active_console_session_id=int(console_session)
    )
