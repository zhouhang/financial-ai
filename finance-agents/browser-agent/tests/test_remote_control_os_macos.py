from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from finance_browser_agent.remote_control_os_macos import MacControlBackend, build_test_backend, selfcheck
from finance_browser_agent.remote_control_codes import ControlErrorCode
from remote_control_contract import RemoteControlBackendContract


class TestMacBackendContract(RemoteControlBackendContract):
    def make_backend(self):
        return build_test_backend()


def test_selfcheck_reports_permission_missing():
    result = selfcheck(screen_recording_ok=False, accessibility_ok=True)
    assert result["available"] is False
    assert result["reason"] == ControlErrorCode.SCREEN_CAPTURE_PERMISSION_MISSING.value


def test_selfcheck_reports_input_permission_missing():
    result = selfcheck(screen_recording_ok=True, accessibility_ok=False)
    assert result["available"] is False
    assert result["reason"] == ControlErrorCode.INPUT_PERMISSION_MISSING.value


def test_selfcheck_ok_when_all_permissions_granted():
    assert selfcheck(screen_recording_ok=True, accessibility_ok=True)["available"] is True
