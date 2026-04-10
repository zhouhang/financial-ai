"""Notification adapter factory and exports."""

from __future__ import annotations

from config import (
    DINGTALK_CLIENT_ID,
    DINGTALK_CLIENT_SECRET,
    DINGTALK_ROBOT_CODE,
    NOTIFICATION_DEFAULT_CHANNEL_CODE,
    NOTIFICATION_PROVIDER,
)

from .base import NotificationAdapter
from .cli import CLIExecutionResult, SubprocessCLIExecutor
from .dingtalk_dws import DingTalkDwsAdapter
from .models import (
    BotMessageResult,
    NotificationChannelConfig,
    NotificationProvider,
    NotificationUser,
    OperationResult,
    ReminderResult,
    TodoListResult,
    TodoRecord,
    TodoResult,
    TodoSyncResult,
    UnifiedTodoStatus,
    UserResolveResult,
)
from .repository import load_company_channel_config


def get_notification_adapter(
    provider: str | NotificationProvider | None = None,
    *,
    executor: SubprocessCLIExecutor | None = None,
    company_id: str | None = None,
    channel_code: str | None = None,
    channel_config: NotificationChannelConfig | None = None,
) -> NotificationAdapter:
    """Create one notification adapter from configured provider."""
    provider_value = str(provider.value if isinstance(provider, NotificationProvider) else provider or NOTIFICATION_PROVIDER)
    resolved_channel_config = channel_config or load_company_channel_config(
        company_id=company_id,
        provider=provider_value,
        channel_code=channel_code or NOTIFICATION_DEFAULT_CHANNEL_CODE,
    )
    if provider_value == NotificationProvider.DINGTALK_DWS.value:
        return DingTalkDwsAdapter(
            executor=executor,
            client_id=resolved_channel_config.client_id if resolved_channel_config else DINGTALK_CLIENT_ID,
            client_secret=resolved_channel_config.client_secret if resolved_channel_config else DINGTALK_CLIENT_SECRET,
            robot_code=resolved_channel_config.robot_code if resolved_channel_config else DINGTALK_ROBOT_CODE,
        )
    raise ValueError(f"Unsupported notification provider: {provider_value}")


__all__ = [
    "BotMessageResult",
    "CLIExecutionResult",
    "DingTalkDwsAdapter",
    "NotificationAdapter",
    "NotificationChannelConfig",
    "NotificationProvider",
    "NotificationUser",
    "OperationResult",
    "ReminderResult",
    "SubprocessCLIExecutor",
    "TodoListResult",
    "TodoRecord",
    "TodoResult",
    "TodoSyncResult",
    "UnifiedTodoStatus",
    "UserResolveResult",
    "get_notification_adapter",
    "load_company_channel_config",
]
