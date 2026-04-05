"""Notification adapter registry and facade."""

from __future__ import annotations

from typing import Callable

from config import DINGTALK_DWS_ENABLED, NOTIFICATION_PROVIDER

from .base import NotificationAdapter
from .dingtalk_dws import DingTalkDWSNotificationAdapter
from .models import NotificationProvider

AdapterFactory = Callable[[], NotificationAdapter]


class NotificationAdapterRegistry:
    """Registry for provider adapter factories."""

    def __init__(self):
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, provider: str, factory: AdapterFactory) -> None:
        self._factories[provider] = factory

    def create(self, provider: str) -> NotificationAdapter:
        if provider not in self._factories:
            raise ValueError(f"Unsupported notification provider: {provider}")
        return self._factories[provider]()


def create_default_registry() -> NotificationAdapterRegistry:
    registry = NotificationAdapterRegistry()
    if DINGTALK_DWS_ENABLED:
        registry.register(NotificationProvider.DINGTALK_DWS.value, DingTalkDWSNotificationAdapter)
    return registry


class NotificationService:
    """Provider facade with future extension points for Feishu / WeCom."""

    def __init__(
        self,
        *,
        provider: str | None = None,
        registry: NotificationAdapterRegistry | None = None,
    ):
        self._provider = (provider or NOTIFICATION_PROVIDER).strip()
        self._registry = registry or create_default_registry()

    def get_adapter(self) -> NotificationAdapter:
        return self._registry.create(self._provider)
