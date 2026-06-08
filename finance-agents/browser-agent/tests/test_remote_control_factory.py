from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.remote_control_factory import (
    RemoteControlFactory,
    resolve_backend_kind,
)


def test_resolve_auto_per_platform():
    assert resolve_backend_kind("auto", platform_system="Windows") == "os_windows"
    assert resolve_backend_kind("auto", platform_system="Darwin") == "os_macos"
    assert resolve_backend_kind("auto", platform_system="Linux") == "playwright"


def test_explicit_backend_overrides_platform():
    assert resolve_backend_kind("playwright", platform_system="Windows") == "playwright"
    assert resolve_backend_kind("os_windows", platform_system="Darwin") == "os_windows"


def test_factory_freezes_kind_at_construction_not_per_call():
    factory = RemoteControlFactory(configured_backend="auto", platform_system="Windows")
    assert factory.backend_kind == "os_windows"
    assert factory.backend_kind == "os_windows"


def test_factory_diagnostics_when_os_selfcheck_fails_downgrades_to_playwright():
    def failing_selfcheck():
        return {"available": False, "reason": "screen_capture_permission_missing"}

    factory = RemoteControlFactory(
        configured_backend="auto",
        platform_system="Windows",
        os_selfcheck=failing_selfcheck,
        allow_downgrade=True,
    )
    diag = factory.diagnostics()
    assert diag["backend"] == "os_windows"
    assert diag["status"] == "unavailable"
    assert diag["reason"] == "screen_capture_permission_missing"
    assert factory.effective_backend_kind == "playwright"


def test_factory_keeps_os_when_selfcheck_ok():
    factory = RemoteControlFactory(
        configured_backend="auto",
        platform_system="Windows",
        os_selfcheck=lambda: {"available": True, "reason": ""},
    )
    assert factory.effective_backend_kind == "os_windows"
    assert factory.diagnostics()["status"] == "available"


def test_factory_uses_windows_backend_builder(monkeypatch):
    import finance_browser_agent.remote_control_os_windows as windows_backend

    calls = {}

    def fake_builder(*, page, chrome, risk_contexts):
        calls["page"] = page
        calls["chrome"] = chrome
        calls["risk_contexts"] = risk_contexts
        return {"backend": "fake-os-windows"}

    monkeypatch.setattr(windows_backend, "build_windows_backend", fake_builder)
    factory = RemoteControlFactory(
        configured_backend="os_windows",
        platform_system="Windows",
        os_selfcheck=lambda: {"available": True, "reason": ""},
    )
    result = factory.create_backend(page="page", chrome="chrome", risk_contexts=["ctx"])
    assert result == {"backend": "fake-os-windows"}
    assert calls == {"page": "page", "chrome": "chrome", "risk_contexts": ["ctx"]}
