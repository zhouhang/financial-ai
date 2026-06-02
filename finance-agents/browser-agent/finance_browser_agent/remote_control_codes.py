"""handoff 远控的单一错误码 / 能力字段来源。

agent / data-agent / finance-web 三端共用这些语义；agent 事件里的"最近错误码"取值
必须限定在 ControlErrorCode,禁止自由字符串。
"""
from __future__ import annotations

from enum import Enum


class ControlErrorCode(str, Enum):
    SCREEN_CAPTURE_PERMISSION_MISSING = "screen_capture_permission_missing"
    INPUT_PERMISSION_MISSING = "input_permission_missing"
    CONTROL_UNAVAILABLE = "control_unavailable"
    WINDOW_UNAVAILABLE = "window_unavailable"
    DESKTOP_LOCKED = "desktop_locked"
    SESSION_NOT_INTERACTIVE = "session_not_interactive"


# 能力布尔字段名(诊断 JSON 与 capabilities 上报共用)
CAPABILITY_FIELDS = (
    "can_capture",
    "can_inject_mouse",
    "can_inject_keyboard",
    "can_clipboard_paste",
)


def is_valid_error_code(value: str) -> bool:
    return value in {code.value for code in ControlErrorCode}
