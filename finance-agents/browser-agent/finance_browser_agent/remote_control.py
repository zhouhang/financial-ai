from __future__ import annotations

import base64
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


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

    # 焦点上报:返回当前焦点元素是否可编辑(None=未知),用于点亮操作端"发送"按钮
    def current_focus_editable(self) -> bool | None: ...

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
    _cdp_sess: Any = None
    # 抓帧降采样:在 Chrome 内按 scale 缩放后再编码 JPEG,直接减小过 WS 的字节数(治"卡")。
    # 都可用环境变量调:FRAME_SCALE 缩放比(0~1)、FRAME_QUALITY JPEG 质量(1~100)。
    _frame_scale: float = field(default_factory=lambda: min(1.0, _env_float("BROWSER_AGENT_HANDOFF_FRAME_SCALE", 0.6)))
    _frame_quality: int = field(default_factory=lambda: _env_int("BROWSER_AGENT_HANDOFF_FRAME_QUALITY", 50))

    def _cdp(self) -> Any:
        if self._cdp_sess is not None:
            return self._cdp_sess
        try:
            context = getattr(self.page, "context", None)
            new_cdp_session = getattr(context, "new_cdp_session", None)
            if callable(new_cdp_session):
                self._cdp_sess = new_cdp_session(self.page)
        except Exception:
            self._cdp_sess = None
        return self._cdp_sess

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
            # 只认 handoff_session(事件已按 sync_job_id 路由到本 backend);不再按 controller_id 拦截。
            # 旧逻辑下手机端关闭重开会换 controller_id,导致新点击被静默丢弃(同一 session 同一时刻只有
            # 一个有效 controller,云端 open_controller 已撤销旧的)。
            if kind not in ("mouse_move", "wheel"):
                logger.info(
                    "handoff input applied: kind=%s controller=%s session=%s",
                    kind, str(event.get("controller_id") or ""), self.handoff_session_id,
                )
            self.apply_input_event(event)

    def pop_resume_check_requested(self) -> bool:
        requested = self._resume_check_requested
        self._resume_check_requested = False
        return requested

    def capture_frame(self) -> dict[str, Any]:
        self._last_frame_at = time.monotonic()
        viewport = getattr(self.page, "viewport_size", None) or {}
        vw = int(viewport.get("width") or 0)
        vh = int(viewport.get("height") or 0)
        scale = self._frame_scale
        cdp = self._cdp()
        # 首选 CDP Page.captureScreenshot 带 clip.scale:缩放在 Chrome 内完成,过 WS 的图直接变小。
        if cdp is not None and vw > 0 and vh > 0 and 0 < scale < 1:
            try:
                shot = cdp.send(
                    "Page.captureScreenshot",
                    {
                        "format": "jpeg",
                        "quality": self._frame_quality,
                        "clip": {"x": 0, "y": 0, "width": vw, "height": vh, "scale": scale},
                    },
                )
                data = str(shot.get("data") or "")
                if data:
                    return {
                        "mime": "image/jpeg",
                        "width": int(vw * scale),
                        "height": int(vh * scale),
                        "data": data,
                    }
            except Exception:
                logger.debug("handoff CDP 缩放抓帧失败,回退整帧", exc_info=True)
        # 回退:Playwright 整帧截图(不缩放)
        raw = self.page.screenshot(type="jpeg", quality=self._frame_quality, full_page=False)
        return {
            "mime": "image/jpeg",
            "width": vw,
            "height": vh,
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

    def current_focus_editable(self) -> bool | None:
        try:
            return bool(self.page.evaluate(
                """
                () => {
                  const el = document.activeElement;
                  if (!el) return false;
                  const tag = String(el.tagName || '').toLowerCase();
                  return tag === 'input' || tag === 'textarea' || el.isContentEditable === true;
                }
                """
            ))
        except Exception:
            return None

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
                logger.info("handoff_start 暂存(backend 未就绪): sync_job_id=%s", sync_job_id)
                return
        if backend is None:
            input_kind = str((msg.get("input") or {}).get("kind") or "")
            if input_kind not in ("mouse_move", "wheel"):
                logger.warning(
                    "handoff 事件无匹配 backend(链接可能指向已结束/重试的任务): event=%s sync_job_id=%s",
                    event, sync_job_id,
                )
            return
        if event == "handoff_start":
            self._start_backend(backend, msg)
            await self._emit_current_focus_state(sync_job_id=sync_job_id, backend=backend)
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

    async def _emit_current_focus_state(
        self,
        *,
        sync_job_id: str,
        backend: RemoteControlBackend,
    ) -> None:
        focus_fn = getattr(backend, "current_focus_editable", None)
        if not callable(focus_fn):
            return
        try:
            editable = focus_fn()
        except Exception:
            logger.exception("handoff current focus state failed")
            return
        if editable is None:
            return
        await self.emit_focus_state(sync_job_id=sync_job_id, backend=backend, editable=bool(editable))

    async def emit_frame(self, *, sync_job_id: str, backend: RemoteControlBackend, frame: dict[str, Any]) -> None:
        await self._send_event({
            "type": "handoff_frame",
            "sync_job_id": str(sync_job_id),
            "handoff_session_id": backend.handoff_session_id,
            "controller_id": backend.controller_id,
            **frame,
        })

    async def emit_focus_state(self, *, sync_job_id: str, backend: RemoteControlBackend, editable: bool) -> None:
        await self._send_event({
            "type": "handoff_focus_state",
            "sync_job_id": str(sync_job_id),
            "handoff_session_id": backend.handoff_session_id,
            "controller_id": backend.controller_id,
            "editable": bool(editable),
        })

    async def emit_status(self, payload: dict[str, Any]) -> None:
        await self._send_event(payload)
