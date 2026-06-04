"""Mac 开发后端:仅用于本机联调,不承诺与 Windows 生产体验一致。

截图用 mss;注入用 Quartz(CGEvent),坐标走全屏点坐标。屏幕录制 / 辅助功能权限缺失时
selfcheck 返回明确错误码。平台依赖注入,逻辑可在无权限的 CI 上单测。
"""
from __future__ import annotations

import base64
import queue
import time
from typing import Any

from finance_browser_agent.remote_control_codes import ControlErrorCode


def selfcheck(*, screen_recording_ok: bool | None = None, accessibility_ok: bool | None = None) -> dict[str, Any]:
    # 真机用 Quartz/CGPreflight 探测;测试可直接传入布尔
    if screen_recording_ok is None or accessibility_ok is None:
        try:
            import Quartz  # type: ignore
            screen_recording_ok = bool(Quartz.CGPreflightScreenCaptureAccess())
            accessibility_ok = bool(Quartz.AXIsProcessTrusted())
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "reason": ControlErrorCode.CONTROL_UNAVAILABLE.value, "detail": str(exc)}
    if not screen_recording_ok:
        return {"available": False, "reason": ControlErrorCode.SCREEN_CAPTURE_PERMISSION_MISSING.value}
    if not accessibility_ok:
        return {"available": False, "reason": ControlErrorCode.INPUT_PERMISSION_MISSING.value}
    return {"available": True, "reason": ""}


class MacControlBackend:
    def __init__(self, *, page: Any = None, chrome: Any = None, risk_contexts: list[Any] | None = None,
                 mss: Any = None, pillow: Any = None, quartz: Any = None,
                 capture_rect: dict[str, int] | None = None) -> None:
        self.page = page
        self.chrome = chrome
        self.risk_contexts = risk_contexts or []
        self.handoff_session_id = ""
        self.controller_id = ""
        self._mss = mss
        self._pillow = pillow
        self._quartz = quartz
        self._rect = capture_rect or {"left": 0, "top": 0, "width": 1280, "height": 800}
        self.stream_active = False
        self.idle_fps = 1.0
        self.interactive_fps = 5.0
        self._last_frame_at = 0.0
        self._interactive_until = 0.0
        self._resume_check_requested = False
        self._input_queue: queue.Queue[dict[str, Any]] = queue.Queue()

    def bind_window(self) -> None:
        return None

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
        if not self.stream_active:
            return False
        fps = self.interactive_fps if time.monotonic() <= self._interactive_until else self.idle_fps
        return time.monotonic() - self._last_frame_at >= 1.0 / max(0.2, fps)

    def capture_frame(self) -> dict[str, Any]:
        self._last_frame_at = time.monotonic()
        shot = self._mss.grab(self._rect)
        w, h = int(shot.size[0]), int(shot.size[1])
        jpeg = self._pillow.encode_jpeg(w, h, shot.bgra)
        return {"mime": "image/jpeg", "width": w, "height": h,
                "data": base64.b64encode(jpeg).decode("ascii"), "backend": "os_macos"}

    def _point(self, event):
        x = max(0.0, min(1.0, float(event.get("x") or 0)))
        y = max(0.0, min(1.0, float(event.get("y") or 0)))
        return self._rect["left"] + x * self._rect["width"], self._rect["top"] + y * self._rect["height"]

    def inject_mouse(self, event: dict[str, Any]) -> None:
        kind = str(event.get("kind") or "")
        if kind == "wheel":
            self._quartz.wheel(float(event.get("delta_x") or 0), float(event.get("delta_y") or 0)); return
        px, py = self._point(event)
        button = str(event.get("button") or "left")
        if kind == "click":
            self._quartz.click(px, py, button)
        elif kind == "mouse_down":
            self._quartz.button(px, py, button, True)
        elif kind == "mouse_move":
            self._quartz.move(px, py)
        elif kind == "mouse_up":
            self._quartz.button(px, py, button, False)

    def inject_key(self, event: dict[str, Any]) -> None:
        self._quartz.key(str(event.get("key") or ""), str(event.get("kind")) == "key_down")

    def inject_text(self, text: str) -> None:
        if text:
            self._quartz.type_text(text)

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
            "backend": "os_macos", "platform": "Darwin", "capture": "mss",
            "can_capture": self._mss is not None,
            "can_inject_mouse": self._quartz is not None,
            "can_inject_keyboard": self._quartz is not None,
            "can_clipboard_paste": False,
        }


def build_test_backend() -> MacControlBackend:
    class _Mss:
        def grab(self, r):
            class S:
                size = (r["width"], r["height"]); bgra = b"\x00" * 4
            return S()

    class _Pillow:
        @staticmethod
        def encode_jpeg(w, h, b): return b"jpeg"

    class _Quartz:
        def click(self, *a): pass
        def button(self, *a): pass
        def move(self, *a): pass
        def wheel(self, *a): pass
        def key(self, *a): pass
        def type_text(self, *a): pass

    return MacControlBackend(mss=_Mss(), pillow=_Pillow(), quartz=_Quartz())
