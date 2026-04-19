"""Notification adapter abstract interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    BotMessageResult,
    ReminderResult,
    TodoListResult,
    TodoResult,
    TodoSyncResult,
    UserResolveResult,
)


class NotificationAdapter(ABC):
    """Provider-agnostic notification adapter contract."""

    provider: str

    @abstractmethod
    def resolve_user(
        self,
        *,
        user_id: str = "",
        mobile: str = "",
        keyword: str = "",
    ) -> UserResolveResult:
        """Resolve users by one of user_id/mobile/keyword."""

    @abstractmethod
    def send_bot_message(
        self,
        *,
        content: str,
        to_user_id: str,
        content_type: str = "text",
        title: str = "",
        bot_id: str = "",
        conversation_id: str = "",
    ) -> BotMessageResult:
        """Send bot message."""

    @abstractmethod
    def create_todo(
        self,
        *,
        assignee_user_id: str,
        title: str,
        content: str = "",
        due_time: str = "",
        source_id: str = "",
        operator_user_id: str = "",
        extra: dict | None = None,
    ) -> TodoResult:
        """Create a todo task."""

    @abstractmethod
    def get_todo(
        self,
        *,
        todo_id: str,
        operator_user_id: str = "",
    ) -> TodoResult:
        """Get one todo task by id."""

    @abstractmethod
    def list_todos(
        self,
        *,
        assignee_user_id: str = "",
        status: str = "",
        page_no: int = 1,
        page_size: int = 20,
        operator_user_id: str = "",
    ) -> TodoListResult:
        """List todo tasks."""

    @abstractmethod
    def update_todo(
        self,
        *,
        todo_id: str,
        status: str = "",
        title: str = "",
        content: str = "",
        done: bool | None = None,
        operator_user_id: str = "",
        extra: dict | None = None,
    ) -> TodoResult:
        """Update todo task fields or status."""

    @abstractmethod
    def complete_todo(
        self,
        *,
        todo_id: str,
        operator_user_id: str = "",
    ) -> TodoResult:
        """Mark todo as completed."""

    @abstractmethod
    def send_reminder(
        self,
        *,
        title: str,
        content: str,
        todo_title: str = "",
        assignee_user_id: str = "",
        mobile: str = "",
        keyword: str = "",
        due_time: str = "",
        source_id: str = "",
        operator_user_id: str = "",
    ) -> ReminderResult:
        """Composite reminder: send bot message + create todo."""

    @abstractmethod
    def sync_todo_status(
        self,
        *,
        todo_id: str,
        operator_user_id: str = "",
        max_polls: int = 1,
        poll_interval_seconds: float = 2.0,
    ) -> TodoSyncResult:
        """Poll/sync todo status and map to unified status."""

