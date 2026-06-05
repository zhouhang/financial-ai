from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from finance_browser_agent.remote_control_os_windows import WindowBinder


class FakeWin32:
    """模拟 win32gui/win32process 的最小子集。"""
    def __init__(self, windows):
        # windows: list of dict(hwnd, pid, visible, title, rect)
        self._windows = windows

    def enum_windows(self):
        return [w["hwnd"] for w in self._windows]

    def get_window_pid(self, hwnd):
        return next(w["pid"] for w in self._windows if w["hwnd"] == hwnd)

    def is_visible(self, hwnd):
        return next(w["visible"] for w in self._windows if w["hwnd"] == hwnd)

    def get_window_text(self, hwnd):
        return next(w["title"] for w in self._windows if w["hwnd"] == hwnd)

    def get_extended_frame_bounds(self, hwnd):
        return next(w["rect"] for w in self._windows if w["hwnd"] == hwnd)


def test_binds_single_window_by_pid():
    win32 = FakeWin32([
        {"hwnd": 11, "pid": 100, "visible": True, "title": "已卖出宝贝 - Google Chrome",
         "rect": {"left": 0, "top": 0, "width": 1280, "height": 800}},
        {"hwnd": 22, "pid": 999, "visible": True, "title": "别的窗口", "rect": {}},
    ])
    binder = WindowBinder(win32=win32, chrome_pids=[100])
    binder.bind(current_page_title="")
    assert binder.window_handle == 11
    assert binder.capture_rect == {"left": 0, "top": 0, "width": 1280, "height": 800}


def test_tie_break_prefers_window_matching_cdp_title():
    win32 = FakeWin32([
        {"hwnd": 11, "pid": 100, "visible": True, "title": "新标签页 - Google Chrome",
         "rect": {"left": 0, "top": 0, "width": 100, "height": 100}},
        {"hwnd": 12, "pid": 100, "visible": True, "title": "短信验证 - Google Chrome",
         "rect": {"left": 5, "top": 5, "width": 200, "height": 200}},
    ])
    binder = WindowBinder(win32=win32, chrome_pids=[100])
    binder.bind(current_page_title="短信验证")
    assert binder.window_handle == 12
    assert binder.candidate_count == 2


def test_invisible_windows_excluded():
    win32 = FakeWin32([
        {"hwnd": 11, "pid": 100, "visible": False, "title": "x - Google Chrome", "rect": {}},
    ])
    binder = WindowBinder(win32=win32, chrome_pids=[100])
    import pytest
    with pytest.raises(Exception):
        binder.bind(current_page_title="")


from finance_browser_agent.remote_control_os_windows import evaluate_session_interactivity
from finance_browser_agent.remote_control_os_windows import selfcheck


def test_session_zero_is_rejected():
    result = evaluate_session_interactivity(process_session_id=0, active_console_session_id=1)
    assert result["available"] is False
    assert result["reason"] == "session_not_interactive"
    assert result["is_interactive_session"] is False


def test_interactive_console_session_ok():
    result = evaluate_session_interactivity(process_session_id=1, active_console_session_id=1)
    assert result["available"] is True
    assert result["is_interactive_session"] is True
    assert result["session_id"] == 1


def test_non_console_session_rejected():
    # 进程会话与活动控制台会话不一致 → 非活动交互式
    result = evaluate_session_interactivity(process_session_id=2, active_console_session_id=1)
    assert result["available"] is False


def test_selfcheck_reports_missing_runtime_dependencies():
    result = selfcheck(
        dependency_check=lambda: {
            "available": False,
            "reason": "control_unavailable",
            "detail": "missing Windows handoff dependencies: win32gui",
        }
    )
    assert result["available"] is False
    assert result["reason"] == ControlErrorCode.CONTROL_UNAVAILABLE.value
    assert "win32gui" in result["detail"]


def test_selfcheck_allows_injected_win32_without_platform_dependencies():
    class FakeSessionWin32:
        def process_session_id(self):
            return 1

        def active_console_session_id(self):
            return 1

    result = selfcheck(win32=FakeSessionWin32())
    assert result["available"] is True


from finance_browser_agent.remote_control_os_windows import WindowCapturer


class FakeMss:
    def grab(self, region):
        class Shot:
            size = (region["width"], region["height"])
            bgra = b"\x00\x00\x00\xff" * (region["width"] * region["height"])
        return Shot()


class FakePillow:
    @staticmethod
    def encode_jpeg(width, height, bgra_bytes):
        return b"jpeg" + bytes([width % 256, height % 256])


def test_capture_frame_uses_capture_rect_and_returns_metadata():
    cap = WindowCapturer(mss=FakeMss(), pillow=FakePillow())
    rect = {"left": 100, "top": 80, "width": 4, "height": 2}
    frame = cap.capture(capture_rect=rect, window_title="短信验证 - Google Chrome")
    assert frame["mime"] == "image/jpeg"
    assert frame["width"] == 4 and frame["height"] == 2
    import base64
    assert base64.b64decode(frame["data"]).startswith(b"jpeg")
    assert frame["capture_rect"] == rect
    assert frame["backend"] == "os_windows"


from finance_browser_agent.remote_control_os_windows import map_normalized_to_virtualdesk


def test_maps_center_of_window_to_virtualdesk_65535():
    rect = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    vd = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    nx, ny = map_normalized_to_virtualdesk(0.5, 0.5, capture_rect=rect, virtual_desktop=vd)
    assert abs(nx - round(960 / 1919 * 65535)) <= 1
    assert abs(ny - round(540 / 1079 * 65535)) <= 1


def test_maps_negative_origin_secondary_monitor():
    rect = {"left": -1280, "top": 0, "width": 1280, "height": 720}
    vd = {"left": -1280, "top": 0, "width": 1280 + 1920, "height": 1080}
    nx, ny = map_normalized_to_virtualdesk(0.0, 0.0, capture_rect=rect, virtual_desktop=vd)
    assert nx == 0
    assert ny == 0


def test_clamps_outside_rect_into_range():
    rect = {"left": 0, "top": 0, "width": 100, "height": 100}
    vd = {"left": 0, "top": 0, "width": 100, "height": 100}
    nx, ny = map_normalized_to_virtualdesk(1.5, -0.2, capture_rect=rect, virtual_desktop=vd)
    assert 0 <= nx <= 65535 and 0 <= ny <= 65535


from finance_browser_agent.remote_control_os_windows import ForegroundGate
from finance_browser_agent.remote_control_codes import ControlErrorCode


class FakeForeground:
    def __init__(self, fg):
        self.fg = fg
    def get_foreground_window(self):
        return self.fg


def test_gate_allows_when_bound_window_is_foreground():
    gate = ForegroundGate(win32=FakeForeground(fg=11), window_handle=11)
    assert gate.check() is True
    assert gate.last_error is None


def test_gate_blocks_and_reports_control_unavailable_when_not_foreground():
    gate = ForegroundGate(win32=FakeForeground(fg=22), window_handle=11)
    assert gate.check() is False
    assert gate.last_error == ControlErrorCode.CONTROL_UNAVAILABLE


from finance_browser_agent.remote_control_os_windows import MouseInjector


class RecordingSendInput:
    def __init__(self):
        self.events = []
    def move_absolute(self, nx, ny):
        self.events.append(("move", nx, ny))
    def button(self, name, down):
        self.events.append(("button", name, down))
    def wheel(self, dx, dy):
        self.events.append(("wheel", dx, dy))


def _injector(fg_handle=11, foreground=11):
    rect = {"left": 0, "top": 0, "width": 1000, "height": 1000}
    vd = {"left": 0, "top": 0, "width": 1000, "height": 1000}
    send = RecordingSendInput()
    gate = ForegroundGate(win32=FakeForeground(fg=foreground), window_handle=fg_handle)
    inj = MouseInjector(send_input=send, gate=gate, capture_rect=rect, virtual_desktop=vd)
    return inj, send


def test_click_moves_then_presses_when_focused():
    inj, send = _injector()
    inj.inject({"kind": "click", "x": 0.5, "y": 0.5, "button": "left"})
    kinds = [e[0] for e in send.events]
    assert kinds == ["move", "button", "button"]
    assert send.events[1] == ("button", "left", True)
    assert send.events[2] == ("button", "left", False)


def test_injection_dropped_when_not_foreground():
    inj, send = _injector(foreground=999)
    inj.inject({"kind": "click", "x": 0.5, "y": 0.5})
    assert send.events == []
    assert inj.last_error == ControlErrorCode.CONTROL_UNAVAILABLE


from finance_browser_agent.remote_control_os_windows import TextBridge


class FakeCdp:
    def __init__(self, *, focused=True, available=True, readback=None):
        self.focused = focused
        self.available = available
        self.inserted = []
        self.readback = readback
    def is_available(self):
        return self.available
    def active_element_editable(self):
        return self.focused
    def insert_text(self, text):
        self.inserted.append(text)
    def read_active_value(self):
        return self.readback


class FakeClipboard:
    def __init__(self):
        self.value = "原始剪贴板"
        self.history = []
        self.pastes = []
    def get_text(self):
        return self.value
    def set_text(self, t):
        self.history.append(t); self.value = t
    def send_paste(self):
        self.pastes.append(self.value)


def test_prefers_cdp_inserttext_when_focused():
    cdp = FakeCdp(focused=True)
    clip = FakeClipboard()
    bridge = TextBridge(cdp=cdp, clipboard=clip)
    assert bridge.send_text("123456") is True
    assert cdp.inserted == ["123456"]
    assert clip.history == []


def test_refuses_when_focus_not_editable():
    cdp = FakeCdp(focused=False)
    bridge = TextBridge(cdp=cdp, clipboard=FakeClipboard())
    ok = bridge.send_text("123456")
    assert ok is False
    assert bridge.last_focus_editable is False


def test_clipboard_fallback_verifies_readback_and_restores():
    cdp = FakeCdp(available=False, focused=True, readback="123456")
    clip = FakeClipboard()
    bridge = TextBridge(cdp=cdp, clipboard=clip)
    assert bridge.send_text("123456") is True
    assert clip.pastes == ["123456"]
    assert clip.value == "原始剪贴板"


def test_clipboard_fallback_fails_on_readback_mismatch():
    cdp = FakeCdp(available=False, focused=True, readback="999999")
    clip = FakeClipboard()
    bridge = TextBridge(cdp=cdp, clipboard=clip)
    assert bridge.send_text("123456") is False
    assert clip.value == "原始剪贴板"


# ---------------------------------------------------------------------------
# Task 15: WindowsControlBackend contract + diagnostics DPI + key whitelist
# ---------------------------------------------------------------------------
from remote_control_contract import RemoteControlBackendContract
from finance_browser_agent.remote_control_os_windows import (
    WindowsControlBackend,
    build_test_backend,
    build_windows_backend,
)


class TestWindowsBackendContract(RemoteControlBackendContract):
    def make_backend(self):
        return build_test_backend()


def test_supported_keys_whitelist():
    backend = build_test_backend()
    backend.bind_window()
    for key in ("Enter", "Backspace", "Tab", "Escape"):
        backend.inject_key({"kind": "key_down", "key": key})
        backend.inject_key({"kind": "key_up", "key": key})


def test_diagnostics_reads_back_dpi_awareness_not_hardcoded():
    backend = build_test_backend(dpi_readback="per_monitor_v2")
    assert backend.diagnostics()["dpi_awareness"] == "per_monitor_v2"
    backend2 = build_test_backend(dpi_readback="system")
    assert backend2.diagnostics()["dpi_awareness"] == "system"


def test_build_windows_backend_assembles_injected_dependencies():
    backend = build_windows_backend(
        page=None,
        chrome=type("Chrome", (), {"process": type("Process", (), {"pid": 100})()})(),
        risk_contexts=[],
        win32=FakeWin32([
            {"hwnd": 11, "pid": 100, "visible": True, "title": "验证 - Google Chrome",
             "rect": {"left": 0, "top": 0, "width": 100, "height": 100}},
        ]),
        mss=FakeMss(),
        pillow=FakePillow(),
        cdp=FakeCdp(focused=True),
        clipboard=FakeClipboard(),
        send_input=RecordingSendInput(),
        virtual_desktop={"left": 0, "top": 0, "width": 100, "height": 100},
        dpi_readback="per_monitor_v2",
    )
    backend.bind_window()
    frame = backend.capture_frame()
    assert backend.diagnostics()["backend"] == "os_windows"
    assert backend.diagnostics()["dpi_awareness"] == "per_monitor_v2"
    assert frame["mime"] == "image/jpeg"
