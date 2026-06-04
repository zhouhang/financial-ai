from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.remote_control_codes import (
    ControlErrorCode,
    is_valid_error_code,
)


def test_error_codes_are_stable_strings():
    assert ControlErrorCode.SCREEN_CAPTURE_PERMISSION_MISSING.value == "screen_capture_permission_missing"
    assert ControlErrorCode.INPUT_PERMISSION_MISSING.value == "input_permission_missing"
    assert ControlErrorCode.CONTROL_UNAVAILABLE.value == "control_unavailable"
    assert ControlErrorCode.WINDOW_UNAVAILABLE.value == "window_unavailable"
    assert ControlErrorCode.DESKTOP_LOCKED.value == "desktop_locked"
    assert ControlErrorCode.SESSION_NOT_INTERACTIVE.value == "session_not_interactive"


def test_is_valid_error_code_rejects_free_strings():
    assert is_valid_error_code("control_unavailable") is True
    assert is_valid_error_code("oops_random") is False
