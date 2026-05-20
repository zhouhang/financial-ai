from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.browser_alerts import BrowserAlertEvent, BrowserAlertService
from services.notifications.models import (
    BotMessageResult,
    NotificationChannelConfig,
    NotificationUser,
    ReminderResult,
    TodoRecord,
    TodoResult,
    UserResolveResult,
    UnifiedTodoStatus,
)


class FakeAdapter:
    provider = "dingtalk_dws"

    def __init__(self) -> None:
        self.reminder_calls: list[dict[str, object]] = []

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        user = NotificationUser(
            user_id=user_id or "ding-zhouhang",
            display_name=keyword or "周行",
            mobile=mobile,
        )
        return UserResolveResult(
            success=True,
            provider=self.provider,
            users=[user],
            resolved_user=user,
        )

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
        self.reminder_calls.append(
            {
                "title": title,
                "content": content,
                "todo_title": todo_title,
                "assignee_user_id": assignee_user_id,
                "keyword": keyword,
                "source_id": source_id,
            }
        )
        todo = TodoRecord(
            todo_id="todo-browser-alert",
            title=todo_title,
            assignee_user_id=assignee_user_id,
            status=UnifiedTodoStatus.OPEN,
        )
        return ReminderResult(
            success=True,
            provider=self.provider,
            bot_result=BotMessageResult(success=True, provider=self.provider, message_id="msg-1"),
            todo_result=TodoResult(success=True, provider=self.provider, todo=todo),
            assignee_user_id=assignee_user_id,
        )


def _channel() -> NotificationChannelConfig:
    return NotificationChannelConfig(
        id="channel-001",
        company_id="company-001",
        provider="dingtalk_dws",
        channel_code="default",
        name="默认钉钉",
        robot_code="robot",
        is_default=True,
        is_enabled=True,
    )


def test_browser_alert_service_sends_terminal_failure_to_zhouhang() -> None:
    adapter = FakeAdapter()
    sent_keys: list[str] = []
    service = BrowserAlertService(
        channel_loader=lambda company_id: _channel(),
        adapter_factory=lambda channel: adapter,
        dedupe_checker=lambda key: False,
        alert_recorder=lambda key, result: sent_keys.append(key),
        recipient_keyword="周行",
    )

    result = service.send_alert(
        BrowserAlertEvent(
            event_type="browser_sync_failed",
            company_id="company-001",
            shop_id="shop-001",
            data_source_name="千牛资金日账单",
            biz_date="2026-05-19",
            sync_job_id="sync-001",
            severity="critical",
            reason="RISK_VERIFICATION",
            message="RISK_VERIFICATION: 平台要求安全验证",
        )
    )

    assert result["status"] == "sent"
    assert adapter.reminder_calls
    call = adapter.reminder_calls[0]
    assert call["keyword"] == "周行"
    assert call["source_id"] == "browser_sync_failed:sync-001"
    assert "千牛资金日账单" in str(call["content"])
    assert "RISK_VERIFICATION" in str(call["content"])
    assert sent_keys == ["browser_sync_failed:company-001:shop-001:2026-05-19:sync-001:RISK_VERIFICATION"]


def test_browser_alert_service_dedupes_existing_alert() -> None:
    adapter = FakeAdapter()
    service = BrowserAlertService(
        channel_loader=lambda company_id: _channel(),
        adapter_factory=lambda channel: adapter,
        dedupe_checker=lambda key: True,
        alert_recorder=lambda key, result: None,
        recipient_keyword="周行",
    )

    result = service.send_alert(
        BrowserAlertEvent(
            event_type="risk_blocked",
            company_id="company-001",
            shop_id="shop-001",
            data_source_name="千牛资金日账单",
            biz_date="2026-05-19",
            sync_job_id="sync-001",
            severity="critical",
            reason="RISK_VERIFICATION",
            message="需要人工过验证",
        )
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "deduped"
    assert adapter.reminder_calls == []
