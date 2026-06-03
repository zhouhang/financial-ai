from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
