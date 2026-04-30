"""Provider-agnostic notification models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NotificationProvider(str, Enum):
    DINGTALK_DWS = "dingtalk_dws"
    FEISHU = "feishu"
    WECHAT_WORK = "wechat_work"


class UnifiedTodoStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"


TERMINAL_TODO_STATUSES = {
    UnifiedTodoStatus.COMPLETED,
    UnifiedTodoStatus.CANCELLED,
    UnifiedTodoStatus.FAILED,
}


@dataclass(slots=True)
class NotificationUser:
    user_id: str
    display_name: str = ""
    mobile: str = ""
    organization: str = ""
    departments: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NotificationChannelConfig:
    id: str = ""
    company_id: str = ""
    provider: str = ""
    channel_code: str = "default"
    name: str = ""
    client_id: str = ""
    client_secret: str = ""
    robot_code: str = ""
    is_default: bool = False
    is_enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TodoRecord:
    todo_id: str
    title: str = ""
    content: str = ""
    assignee_user_id: str = ""
    status: UnifiedTodoStatus = UnifiedTodoStatus.UNKNOWN
    due_time: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OperationResult:
    success: bool
    provider: str
    message: str = ""
    code: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UserResolveResult(OperationResult):
    users: list[NotificationUser] = field(default_factory=list)
    resolved_user: NotificationUser | None = None


@dataclass(slots=True)
class BotMessageResult(OperationResult):
    message_id: str = ""
    receiver_user_id: str = ""


@dataclass(slots=True)
class TodoResult(OperationResult):
    todo: TodoRecord | None = None


@dataclass(slots=True)
class TodoListResult(OperationResult):
    todos: list[TodoRecord] = field(default_factory=list)


@dataclass(slots=True)
class ReminderResult(OperationResult):
    bot_result: BotMessageResult | None = None
    todo_result: TodoResult | None = None
    assignee_user_id: str = ""


@dataclass(slots=True)
class TodoSyncResult(OperationResult):
    todo_id: str = ""
    status: UnifiedTodoStatus = UnifiedTodoStatus.UNKNOWN
    is_terminal: bool = False
    polls: int = 0
    history: list[UnifiedTodoStatus] = field(default_factory=list)
    todo: TodoRecord | None = None
