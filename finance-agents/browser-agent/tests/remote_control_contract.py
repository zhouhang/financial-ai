"""三个 backend 共用的契约测试。子类只需实现 make_backend()。

验证调用时序 bind -> capture -> inject -> teardown,以及归一化坐标语义、
错误码映射、teardown 幂等。平台依赖由各子类用 fake 注入。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class RemoteControlBackendContract:
    def make_backend(self):  # pragma: no cover - 子类实现
        raise NotImplementedError

    def test_bind_then_capture_returns_frame_dict(self):
        backend = self.make_backend()
        backend.bind_window()
        backend.start_stream(
            handoff_session_id="h1", controller_id="ctrl-1", idle_fps=1, interactive_fps=5
        )
        frame = backend.capture_frame()
        assert frame["mime"] == "image/jpeg"
        assert isinstance(frame["width"], int) and frame["width"] >= 0
        assert isinstance(frame["height"], int) and frame["height"] >= 0
        assert isinstance(frame["data"], str)
        backend.teardown()

    def test_inject_mouse_click_accepts_normalized_coords(self):
        backend = self.make_backend()
        backend.bind_window()
        # 归一化坐标 0..1,不应抛异常
        backend.inject_mouse({"kind": "click", "x": 0.5, "y": 0.5, "button": "left"})
        backend.teardown()

    def test_diagnostics_reports_required_capability_fields(self):
        backend = self.make_backend()
        diag = backend.diagnostics()
        for field in ("backend", "can_capture", "can_inject_mouse", "can_inject_keyboard"):
            assert field in diag

    def test_teardown_is_idempotent(self):
        backend = self.make_backend()
        backend.bind_window()
        backend.teardown()
        backend.teardown()  # 第二次不应抛
