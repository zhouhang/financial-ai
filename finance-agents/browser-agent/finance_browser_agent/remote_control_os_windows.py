"""Windows OS 级远控后端。

平台依赖(win32/mss/dwm/ctypes/cdp)全部以构造参数注入,使坐标映射、窗口绑定、门禁、
剪贴板恢复等逻辑可在非 Windows CI 上单测。真实 API 行为在 Slice 6 真机验收。
"""
from __future__ import annotations

import base64
import logging
import queue
import time
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


class WindowCapturer:
    def __init__(self, *, mss: Any, pillow: Any) -> None:
        self._mss = mss
        self._pillow = pillow

    def capture(self, *, capture_rect: dict[str, int], window_title: str) -> dict[str, Any]:
        region = {
            "left": int(capture_rect["left"]), "top": int(capture_rect["top"]),
            "width": int(capture_rect["width"]), "height": int(capture_rect["height"]),
        }
        shot = self._mss.grab(region)
        width, height = int(shot.size[0]), int(shot.size[1])
        jpeg = self._pillow.encode_jpeg(width, height, shot.bgra)
        return {
            "mime": "image/jpeg",
            "width": width,
            "height": height,
            "data": base64.b64encode(jpeg).decode("ascii"),
            # 仅供调试的 metadata;window_title 上送前需脱敏(见 data-agent 中转层约束)
            "backend": "os_windows",
            "window_title": window_title,
            "capture_rect": region,
        }


def map_normalized_to_virtualdesk(
    x: float, y: float, *, capture_rect: dict[str, int], virtual_desktop: dict[str, int]
) -> tuple[int, int]:
    """归一化(0..1,相对窗口) → SendInput 绝对坐标(0..65535,相对整个虚拟桌面)。

    注入时必须带 MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK。
    """
    cx = max(0.0, min(1.0, float(x)))
    cy = max(0.0, min(1.0, float(y)))
    phys_x = capture_rect["left"] + cx * capture_rect["width"]
    phys_y = capture_rect["top"] + cy * capture_rect["height"]
    vd_w = max(1, int(virtual_desktop["width"]) - 1)
    vd_h = max(1, int(virtual_desktop["height"]) - 1)
    rel_x = (phys_x - virtual_desktop["left"]) / vd_w
    rel_y = (phys_y - virtual_desktop["top"]) / vd_h
    nx = round(max(0.0, min(1.0, rel_x)) * 65535)
    ny = round(max(0.0, min(1.0, rel_y)) * 65535)
    return int(nx), int(ny)


class ForegroundGate:
    """注入前硬门禁:GetForegroundWindow()==绑定窗口才放行;否则丢弃事件并报 control_unavailable。
    clamp 只约束坐标,不保证事件进入 Chrome,真正隔离靠这道门禁。"""

    def __init__(self, *, win32: Any, window_handle: int) -> None:
        self._win32 = win32
        self._window_handle = int(window_handle)
        self.last_error: ControlErrorCode | None = None

    def check(self) -> bool:
        try:
            fg = self._win32.get_foreground_window()
        except Exception:
            self.last_error = ControlErrorCode.CONTROL_UNAVAILABLE
            return False
        if int(fg) == self._window_handle:
            self.last_error = None
            return True
        self.last_error = ControlErrorCode.CONTROL_UNAVAILABLE
        return False


class MouseInjector:
    def __init__(self, *, send_input: Any, gate: "ForegroundGate",
                 capture_rect: dict[str, int], virtual_desktop: dict[str, int]) -> None:
        self._send = send_input
        self._gate = gate
        self._rect = capture_rect
        self._vd = virtual_desktop
        self.last_error: ControlErrorCode | None = None

    def _move(self, x: float, y: float) -> None:
        nx, ny = map_normalized_to_virtualdesk(x, y, capture_rect=self._rect, virtual_desktop=self._vd)
        self._send.move_absolute(nx, ny)

    def inject(self, event: dict[str, Any]) -> None:
        if not self._gate.check():
            self.last_error = self._gate.last_error
            return
        self.last_error = None
        kind = str(event.get("kind") or "")
        button = str(event.get("button") or "left")
        if kind == "wheel":
            self._send.wheel(float(event.get("delta_x") or 0), float(event.get("delta_y") or 0))
            return
        x, y = float(event.get("x") or 0), float(event.get("y") or 0)
        if kind == "click":
            self._move(x, y); self._send.button(button, True); self._send.button(button, False)
        elif kind == "mouse_down":
            self._move(x, y); self._send.button(button, True)
        elif kind == "mouse_move":
            self._move(x, y)
        elif kind == "mouse_up":
            self._move(x, y); self._send.button(button, False)


class TextBridge:
    """文本桥:优先 CDP Input.insertText(绕开系统剪贴板);CDP 不可用才退回剪贴板粘贴,
    且粘贴后读回校验、立即恢复原剪贴板。任何时候焦点不在可编辑框都拒绝注入。"""

    def __init__(self, *, cdp: Any, clipboard: Any) -> None:
        self._cdp = cdp
        self._clip = clipboard
        self.last_focus_editable: bool | None = None

    def send_text(self, text: str) -> bool:
        text = str(text or "")
        if not text:
            return False
        self.last_focus_editable = bool(self._cdp.active_element_editable())
        if not self.last_focus_editable:
            return False  # 焦点不在输入框,绝不盲注
        if self._cdp.is_available():
            self._cdp.insert_text(text)
            return True
        # 剪贴板回退
        original = self._clip.get_text()
        try:
            self._clip.set_text(text)
            self._clip.send_paste()
            readback = self._cdp.read_active_value()
            return readback == text  # 被抢占/粘错 → False
        finally:
            self._clip.set_text(original)  # 由回执驱动:立即恢复,缩短明文驻留窗口


# ---------------------------------------------------------------------------
# Task 15: WindowsControlBackend — assembles all components into RemoteControlBackend contract
# ---------------------------------------------------------------------------

_SUPPORTED_KEYS = {"Enter", "Backspace", "Tab", "Escape", "Control", "a", "v"}


class WindowsControlBackend:
    def __init__(self, *, page: Any = None, chrome: Any = None, risk_contexts: list[Any] | None = None,
                 win32: Any = None, mss: Any = None, pillow: Any = None, cdp: Any = None,
                 clipboard: Any = None, send_input: Any = None, dpi_readback: str = "",
                 virtual_desktop: dict[str, int] | None = None) -> None:
        self.page = page
        self.chrome = chrome
        self.risk_contexts = risk_contexts or []
        self.handoff_session_id = ""
        self.controller_id = ""
        self._win32 = win32
        self._mss = mss
        self._pillow = pillow
        self._cdp = cdp
        self._clipboard = clipboard
        self._send_input = send_input
        self._dpi_readback = dpi_readback or "unknown"
        self._virtual_desktop = virtual_desktop or {}
        self._binder: WindowBinder | None = None
        self._capturer = WindowCapturer(mss=mss, pillow=pillow)
        self._text_bridge = TextBridge(cdp=cdp, clipboard=clipboard)
        self._last_error: ControlErrorCode | None = None
        self.stream_active = False
        self.idle_fps = 1.0
        self.interactive_fps = 5.0
        self._last_frame_at = 0.0
        self._interactive_until = 0.0
        self._resume_check_requested = False
        self._input_queue: queue.Queue[dict[str, Any]] = queue.Queue()

    def _chrome_pids(self) -> list[int]:
        pid = getattr(getattr(self.chrome, "process", None), "pid", None)
        return [int(pid)] if pid else []

    def _current_page_title(self) -> str:
        try:
            return str(getattr(self.page, "title", lambda: "")() or "")
        except Exception:
            return ""

    def bind_window(self) -> None:
        self._binder = WindowBinder(win32=self._win32, chrome_pids=self._chrome_pids())
        self._binder.bind(current_page_title=self._current_page_title())

    def teardown(self) -> None:
        self.stream_active = False

    def start_stream(self, *, handoff_session_id, controller_id, idle_fps, interactive_fps):
        self.handoff_session_id = handoff_session_id
        self.controller_id = controller_id
        self.idle_fps = max(0.2, float(idle_fps or 1))
        self.interactive_fps = max(self.idle_fps, float(interactive_fps or 5))
        self.stream_active = True

    def stop_stream(self):
        self.stream_active = False

    def should_capture_frame(self) -> bool:
        if not self.stream_active or self._binder is None:
            return False
        fps = self.interactive_fps if time.monotonic() <= self._interactive_until else self.idle_fps
        return time.monotonic() - self._last_frame_at >= 1.0 / max(0.2, fps)

    def capture_frame(self) -> dict[str, Any]:
        assert self._binder is not None
        self._last_frame_at = time.monotonic()
        return self._capturer.capture(
            capture_rect=self._binder.capture_rect, window_title=self._binder.window_title
        )

    def _gate(self) -> "ForegroundGate":
        assert self._binder and self._binder.window_handle is not None
        return ForegroundGate(win32=self._win32, window_handle=self._binder.window_handle)

    def inject_mouse(self, event: dict[str, Any]) -> None:
        assert self._binder is not None
        injector = MouseInjector(
            send_input=self._send_input, gate=self._gate(),
            capture_rect=self._binder.capture_rect, virtual_desktop=self._virtual_desktop,
        )
        injector.inject(event)
        self._last_error = injector.last_error

    def inject_key(self, event: dict[str, Any]) -> None:
        key = str(event.get("key") or "")
        if key not in _SUPPORTED_KEYS:
            return
        if not self._gate().check():
            self._last_error = ControlErrorCode.CONTROL_UNAVAILABLE
            return
        self._send_input.key(key, str(event.get("kind")) == "key_down")

    def inject_text(self, text: str) -> None:
        if not self._text_bridge.send_text(text):
            self._last_error = ControlErrorCode.CONTROL_UNAVAILABLE

    def apply_input_event(self, event: dict[str, Any]) -> None:
        self._interactive_until = time.monotonic() + 2.0
        kind = str(event.get("kind") or "")
        if kind == "text":
            self.inject_text(str(event.get("text") or ""))
        elif kind in {"key_down", "key_up"}:
            self.inject_key(event)
        else:
            self.inject_mouse(event)

    def queue_input_event(self, event: dict[str, Any]) -> None:
        self._input_queue.put(dict(event or {}))

    def drain_pending_input(self) -> None:
        while True:
            try:
                event = self._input_queue.get_nowait()
            except queue.Empty:
                return
            if str(event.get("kind") or "") == "__resume_check__":
                self._resume_check_requested = True
                continue
            ec = str(event.get("controller_id") or "")
            if ec and self.controller_id and ec != self.controller_id:
                continue
            self.apply_input_event(event)

    def pop_resume_check_requested(self) -> bool:
        v = self._resume_check_requested
        self._resume_check_requested = False
        return v

    def diagnostics(self) -> dict[str, Any]:
        return {
            "backend": "os_windows",
            "platform": "Windows",
            "capture": "mss",
            "can_capture": self._mss is not None,
            "can_inject_mouse": self._send_input is not None,
            "can_inject_keyboard": self._send_input is not None,
            "can_clipboard_paste": self._clipboard is not None,
            "dpi_awareness": self._dpi_readback,
            "last_error": self._last_error.value if self._last_error else "",
        }


def build_test_backend(*, dpi_readback: str = "per_monitor_v2") -> WindowsControlBackend:
    """供契约测试用的 fake 组装。"""
    class _Win32:
        def enum_windows(self): return [11]
        def get_window_pid(self, h): return 100
        def is_visible(self, h): return True
        def get_window_text(self, h): return "验证 - Google Chrome"
        def get_extended_frame_bounds(self, h): return {"left": 0, "top": 0, "width": 100, "height": 100}
        def get_foreground_window(self): return 11

    class _Mss:
        def grab(self, region):
            class S:
                size = (region["width"], region["height"]); bgra = b"\x00" * 4
            return S()

    class _Pillow:
        @staticmethod
        def encode_jpeg(w, h, b): return b"jpeg"

    class _Cdp:
        def is_available(self): return True
        def active_element_editable(self): return True
        def insert_text(self, t): pass
        def read_active_value(self): return ""

    class _Send:
        def move_absolute(self, nx, ny): pass
        def button(self, name, down): pass
        def wheel(self, dx, dy): pass
        def key(self, key, down): pass

    class _Chrome:
        class process: pid = 100

    return WindowsControlBackend(
        page=None, chrome=_Chrome(), risk_contexts=[],
        win32=_Win32(), mss=_Mss(), pillow=_Pillow(), cdp=_Cdp(),
        clipboard=object(), send_input=_Send(), dpi_readback=dpi_readback,
        virtual_desktop={"left": 0, "top": 0, "width": 100, "height": 100},
    )
