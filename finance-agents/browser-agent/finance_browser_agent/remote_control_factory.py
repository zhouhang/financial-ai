"""handoff 远控 backend 的启动期固化选择。

auto 解析只在 agent 启动自检时进行一次并固化,进程生命周期内不每次 handoff 重选。
OS 后端自检失败时,诊断标记 unavailable,并把"下次 handoff 使用"的后端降级为 playwright
(受站点策略约束,千牛等强风控站点按既定决策不推荐 playwright,由调用方决定是否真用)。
"""
from __future__ import annotations

import logging
import platform as _platform
from typing import Any, Callable

logger = logging.getLogger(__name__)

_VALID = {"auto", "playwright", "os_windows", "os_macos"}


def resolve_backend_kind(configured: str, *, platform_system: str | None = None) -> str:
    kind = (configured or "auto").strip().lower()
    if kind not in _VALID:
        kind = "auto"
    if kind != "auto":
        return kind
    system = (platform_system or _platform.system())
    if system == "Windows":
        return "os_windows"
    if system == "Darwin":
        return "os_macos"
    return "playwright"


class RemoteControlFactory:
    def __init__(
        self,
        *,
        configured_backend: str,
        platform_system: str | None = None,
        os_selfcheck: Callable[[], dict[str, Any]] | None = None,
        allow_downgrade: bool = True,
    ) -> None:
        self.backend_kind = resolve_backend_kind(configured_backend, platform_system=platform_system)
        self._allow_downgrade = allow_downgrade
        self._selfcheck_result: dict[str, Any] = {"available": True, "reason": ""}
        if self.backend_kind in {"os_windows", "os_macos"} and os_selfcheck is not None:
            try:
                self._selfcheck_result = dict(os_selfcheck() or {})
            except Exception as exc:  # noqa: BLE001
                logger.exception("OS backend 自检异常")
                self._selfcheck_result = {"available": False, "reason": "control_unavailable", "detail": str(exc)}

    @property
    def effective_backend_kind(self) -> str:
        if self.backend_kind in {"os_windows", "os_macos"} and not self._selfcheck_result.get("available", True):
            return "playwright" if self._allow_downgrade else self.backend_kind
        return self.backend_kind

    def diagnostics(self) -> dict[str, Any]:
        available = bool(self._selfcheck_result.get("available", True))
        return {
            "backend": self.backend_kind,
            "status": "available" if available else "unavailable",
            "reason": str(self._selfcheck_result.get("reason") or ""),
        }

    def create_backend(self, *, page: Any, chrome: Any, risk_contexts: list[Any]) -> Any:
        """按 effective_backend_kind 建后端实例。延迟 import 平台模块,避免在不支持平台 import 失败。"""
        kind = self.effective_backend_kind
        if kind == "os_windows":
            from finance_browser_agent.remote_control_os_windows import build_windows_backend

            return build_windows_backend(page=page, chrome=chrome, risk_contexts=risk_contexts)
        if kind == "os_macos":
            from finance_browser_agent.remote_control_os_macos import MacControlBackend

            return MacControlBackend(page=page, chrome=chrome, risk_contexts=risk_contexts)
        from finance_browser_agent.remote_control import PlaywrightControlBackend

        return PlaywrightControlBackend(page=page, risk_contexts=risk_contexts)
