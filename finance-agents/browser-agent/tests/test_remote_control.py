from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.remote_control import PlaywrightControlBackend, RemoteControlCoordinator


class FakeMouse:
    def __init__(self) -> None:
        self.calls = []

    def click(self, x, y, button="left"):
        self.calls.append(("click", round(x), round(y), button))

    def down(self, button="left"):
        self.calls.append(("down", button))

    def move(self, x, y):
        self.calls.append(("move", round(x), round(y)))

    def up(self, button="left"):
        self.calls.append(("up", button))

    def wheel(self, dx, dy):
        self.calls.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self) -> None:
        self.calls = []

    def type(self, text):
        self.calls.append(("type", text))

    def down(self, key):
        self.calls.append(("down", key))

    def up(self, key):
        self.calls.append(("up", key))


class FakePage:
    viewport_size = {"width": 1000, "height": 800}

    def __init__(self) -> None:
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    def screenshot(self, **kwargs):
        return b"jpg-bytes"


def test_backend_maps_normalized_input_to_playwright_mouse_and_keyboard():
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])

    backend.apply_input_event({"kind": "click", "x": 0.25, "y": 0.5, "button": "left"})
    backend.apply_input_event({"kind": "text", "text": "123456"})
    backend.apply_input_event({"kind": "key_down", "key": "Enter"})
    backend.apply_input_event({"kind": "key_up", "key": "Enter"})

    assert page.mouse.calls == [("click", 250, 400, "left")]
    assert page.keyboard.calls == [("type", "123456"), ("down", "Enter"), ("up", "Enter")]


def test_backend_capture_frame_base64_encodes_screenshot():
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])

    frame = backend.capture_frame()

    assert frame["mime"] == "image/jpeg"
    assert frame["width"] == 1000
    assert frame["height"] == 800
    assert base64.b64decode(frame["data"]) == b"jpg-bytes"


def test_coordinator_queues_downlink_until_runner_thread_drains():
    sent = []

    async def emit(payload):
        sent.append(payload)

    coordinator = RemoteControlCoordinator(send_event=emit)
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])
    coordinator.register_backend(sync_job_id="j1", backend=backend)

    asyncio.run(coordinator.handle_event({
        "type": "event",
        "event": "handoff_start",
        "sync_job_id": "j1",
        "handoff_session_id": "h1",
        "controller_id": "ctrl-1",
    }))
    asyncio.run(coordinator.handle_event({
        "type": "event",
        "event": "handoff_input",
        "sync_job_id": "j1",
        "handoff_session_id": "h1",
        "controller_id": "ctrl-1",
        "input": {"kind": "click", "x": 0.1, "y": 0.2},
    }))
    backend.drain_pending_input()

    assert page.mouse.calls == [("click", 100, 160, "left")]


def test_coordinator_emits_frame_and_status_via_send_event():
    sent = []

    async def emit(payload):
        sent.append(payload)
        return {"success": True}

    coordinator = RemoteControlCoordinator(send_event=emit)
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])
    backend.start_stream(
        handoff_session_id="h1",
        controller_id="ctrl-1",
        idle_fps=1,
        interactive_fps=5,
    )

    asyncio.run(coordinator.emit_frame(sync_job_id="j1", backend=backend, frame=backend.capture_frame()))
    asyncio.run(coordinator.emit_status({"type": "handoff_completed", "sync_job_id": "j1"}))

    assert sent[0]["type"] == "handoff_frame"
    assert sent[0]["handoff_session_id"] == "h1"
    assert sent[1] == {"type": "handoff_completed", "sync_job_id": "j1"}
