from __future__ import annotations

import base64
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)


class RemoteControlBackend(Protocol):
    handoff_session_id: str
    controller_id: str

    # 绑定与生命周期
    def bind_window(self) -> None: ...
    def teardown(self) -> None: ...

    # 流式截图(沿用 runner 循环既有契约)
    def start_stream(
        self,
        *,
        handoff_session_id: str,
        controller_id: str,
        idle_fps: float,
        interactive_fps: float,
    ) -> None: ...
    def stop_stream(self) -> None: ...
    def should_capture_frame(self) -> bool: ...
    def capture_frame(self) -> dict[str, Any]: ...

    # 输入注入
    def inject_mouse(self, event: dict[str, Any]) -> None: ...
    def inject_key(self, event: dict[str, Any]) -> None: ...
    def inject_text(self, text: str) -> None: ...

    # 队列分派(coordinator 投递,runner 线程 drain)
    def queue_input_event(self, event: dict[str, Any]) -> None: ...
    def drain_pending_input(self) -> None: ...
    def apply_input_event(self, event: dict[str, Any]) -> None: ...
    def pop_resume_check_requested(self) -> bool: ...

    # 诊断
    def diagnostics(self) -> dict[str, Any]: ...


@dataclass
class PlaywrightControlBackend:
    page: Any
    risk_contexts: list[Any]
    handoff_session_id: str = ""
    controller_id: str = ""
    idle_fps: float = 1.0
    interactive_fps: float = 5.0
    stream_active: bool = False
    _last_frame_at: float = 0.0
    _interactive_until: float = 0.0
    _resume_check_requested: bool = False
    _input_queue: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)

    def start_stream(
        self,
        *,
        handoff_session_id: str,
        controller_id: str,
        idle_fps: float,
        interactive_fps: float,
    ) -> None:
        self.handoff_session_id = handoff_session_id
        self.controller_id = controller_id
        self.idle_fps = max(0.2, float(idle_fps or 1))
        self.interactive_fps = max(self.idle_fps, float(interactive_fps or 5))
        self.stream_active = True

    def stop_stream(self) -> None:
        self.stream_active = False

    def queue_input_event(self, event: dict[str, Any]) -> None:
        self._input_queue.put(dict(event or {}))

    def drain_pending_input(self) -> None:
        while True:
            try:
                event = self._input_queue.get_nowait()
            except queue.Empty:
                return
            kind = str(event.get("kind") or "")
            if kind == "__resume_check__":
                self._resume_check_requested = True
                continue
            event_controller = str(event.get("controller_id") or "")
            if event_controller and self.controller_id and event_controller != self.controller_id:
                logger.warning("丢弃非当前 controller 的 input: got=%s active=%s", event_controller, self.controller_id)
                continue
            self.apply_input_event(event)

    def pop_resume_check_requested(self) -> bool:
        requested = self._resume_check_requested
        self._resume_check_requested = False
        return requested

    def capture_frame(self) -> dict[str, Any]:
        viewport = getattr(self.page, "viewport_size", None) or {}
        raw = self.page.screenshot(type="jpeg", quality=60, full_page=False)
        self._last_frame_at = time.monotonic()
        return {
            "mime": "image/jpeg",
            "width": int(viewport.get("width") or 0),
            "height": int(viewport.get("height") or 0),
            "data": base64.b64encode(raw).decode("ascii"),
        }

    def should_capture_frame(self) -> bool:
        if not self.stream_active:
            return False
        fps = self.interactive_fps if time.monotonic() <= self._interactive_until else self.idle_fps
        return time.monotonic() - self._last_frame_at >= 1.0 / max(0.2, fps)

    def _point(self, event: dict[str, Any]) -> tuple[float, float]:
        viewport = getattr(self.page, "viewport_size", None) or {"width": 0, "height": 0}
        width = float(viewport.get("width") or 0)
        height = float(viewport.get("height") or 0)
        return float(event.get("x") or 0) * width, float(event.get("y") or 0) * height

    def bind_window(self) -> None:
        return None

    def teardown(self) -> None:
        self.stop_stream()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "backend": "playwright",
            "platform": "any",
            "capture": "cdp_screenshot",
            "can_capture": True,
            "can_inject_mouse": True,
            "can_inject_keyboard": True,
            "can_clipboard_paste": False,
        }

    def inject_mouse(self, event: dict[str, Any]) -> None:
        self.apply_input_event(event)

    def inject_key(self, event: dict[str, Any]) -> None:
        self.apply_input_event(event)

    def inject_text(self, text: str) -> None:
        if text:
            self.page.keyboard.type(text)

    def apply_input_event(self, event: dict[str, Any]) -> None:
        kind = str(event.get("kind") or "")
        self._interactive_until = time.monotonic() + 2.0
        if kind == "text":
            self.inject_text(str(event.get("text") or ""))
            return
        if kind in {"key_down", "key_up"}:
            key = str(event.get("key") or "")
            if key:
                (self.page.keyboard.down if kind == "key_down" else self.page.keyboard.up)(key)
            return
        if kind == "wheel":
            self.page.mouse.wheel(float(event.get("delta_x") or 0), float(event.get("delta_y") or 0))
            return
        x, y = self._point(event)
        button = str(event.get("button") or "left")
        if kind == "click":
            self.page.mouse.click(x, y, button=button)
        elif kind == "mouse_down":
            self.page.mouse.move(x, y)
            self.page.mouse.down(button=button)
        elif kind == "mouse_move":
            self.page.mouse.move(x, y)
        elif kind == "mouse_up":
            self.page.mouse.move(x, y)
            self.page.mouse.up(button=button)


class RemoteControlCoordinator:
    def __init__(self, *, send_event: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]) -> None:
        self._send_event = send_event
        self._backends_by_sync_job: dict[str, RemoteControlBackend] = {}
        self._pending_starts: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register_backend(self, *, sync_job_id: str, backend: RemoteControlBackend) -> None:
        with self._lock:
            self._backends_by_sync_job[str(sync_job_id)] = backend
            pending = self._pending_starts.pop(str(sync_job_id), None)
        if pending:
            self._start_backend(backend, pending)

    def unregister_backend(self, *, sync_job_id: str) -> None:
        with self._lock:
            self._backends_by_sync_job.pop(str(sync_job_id), None)
            self._pending_starts.pop(str(sync_job_id), None)

    async def handle_event(self, msg: dict[str, Any]) -> None:
        event = str(msg.get("event") or "")
        sync_job_id = str(msg.get("sync_job_id") or "")
        with self._lock:
            backend = self._backends_by_sync_job.get(sync_job_id)
            if backend is None and event == "handoff_start":
                self._pending_starts[sync_job_id] = dict(msg)
                return
        if backend is None:
            return
        if event == "handoff_start":
            self._start_backend(backend, msg)
        elif event == "handoff_stop":
            backend.stop_stream()
        elif event == "handoff_input":
            payload = dict(msg.get("input") or {})
            payload["controller_id"] = str(msg.get("controller_id") or "")
            backend.queue_input_event(payload)
        elif event == "handoff_frame_rate":
            profile = str(msg.get("profile") or "interactive")
            backend.start_stream(
                handoff_session_id=backend.handoff_session_id,
                controller_id=backend.controller_id,
                idle_fps=0.5 if profile == "idle" else 1,
                interactive_fps=5,
            )
        elif event == "handoff_resume_check":
            backend.queue_input_event({"kind": "__resume_check__"})

    def _start_backend(self, backend: RemoteControlBackend, msg: dict[str, Any]) -> None:
        frame_profile = dict(msg.get("frame_profile") or {})
        backend.start_stream(
            handoff_session_id=str(msg.get("handoff_session_id") or ""),
            controller_id=str(msg.get("controller_id") or ""),
            idle_fps=float(frame_profile.get("idle_fps") or 1),
            interactive_fps=float(frame_profile.get("interactive_fps") or 5),
        )

    async def emit_frame(self, *, sync_job_id: str, backend: RemoteControlBackend, frame: dict[str, Any]) -> None:
        await self._send_event({
            "type": "handoff_frame",
            "sync_job_id": str(sync_job_id),
            "handoff_session_id": backend.handoff_session_id,
            "controller_id": backend.controller_id,
            **frame,
        })

    async def emit_status(self, payload: dict[str, Any]) -> None:
        await self._send_event(payload)
