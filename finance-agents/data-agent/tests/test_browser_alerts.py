from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.browser_alerts as browser_alerts
from services.browser_alerts import BrowserAlertEvent, BrowserAlertService
from services.notifications.models import (
    BotMessageResult,
    NotificationUser,
    UserResolveResult,
)


class FakeAdapter:
    provider = "dingtalk_dws"

    def __init__(self, *, bot_success: bool = True, resolve_success: bool = True) -> None:
        self.reminder_calls: list[dict[str, object]] = []
        self.bot_calls: list[dict[str, object]] = []
        self.bot_success = bot_success
        self.resolve_success = resolve_success

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        if not self.resolve_success:
            return UserResolveResult(
                success=False,
                provider=self.provider,
                message="not found",
                code="not_found",
            )
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

    def send_bot_message(
        self,
        *,
        title: str,
        content: str,
        to_user_id: str,
        content_type: str = "text",
        **_: object,
    ) -> BotMessageResult:
        self.bot_calls.append(
            {
                "title": title,
                "content": content,
                "to_user_id": to_user_id,
                "content_type": content_type,
            }
        )
        return BotMessageResult(
            success=self.bot_success,
            provider=self.provider,
            message="ok" if self.bot_success else "bot failed",
            code="" if self.bot_success else "cli_error",
            message_id="msg-browser-alert" if self.bot_success else "",
            receiver_user_id=to_user_id,
        )


def test_browser_alert_service_sends_terminal_failure_to_zhouhang_by_bot_only() -> None:
    adapter = FakeAdapter()
    sent_keys: list[str] = []
    factory_calls: list[str] = []
    service = BrowserAlertService(
        adapter_factory=lambda: factory_calls.append("env_adapter") or adapter,
        dedupe_checker=lambda key: False,
        alert_recorder=lambda key, result: sent_keys.append(key),
        recipient_keyword="周行",
    )

    result = service.send_alert(
        BrowserAlertEvent(
            event_type="browser_sync_failed",
            company_id="merchant-company-001",
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
    assert factory_calls == ["env_adapter"]
    assert adapter.reminder_calls == []
    assert adapter.bot_calls
    call = adapter.bot_calls[0]
    assert call["to_user_id"] == "ding-zhouhang"
    assert call["content_type"] == "markdown"
    assert "千牛资金日账单" in str(call["content"])
    assert "RISK_VERIFICATION" in str(call["content"])
    assert sent_keys == ["browser_sync_failed:merchant-company-001:shop-001:2026-05-19:sync-001:RISK_VERIFICATION"]


def test_browser_alert_service_default_adapter_uses_env_dingtalk_credentials(monkeypatch) -> None:
    built: list[str] = []

    class EnvAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            built.append("dingtalk-env-adapter")

    assert not hasattr(browser_alerts, "get_notification_adapter")
    monkeypatch.setattr("services.browser_alerts.DingTalkDwsAdapter", EnvAdapter, raising=False)

    result = BrowserAlertService(
        dedupe_checker=lambda key: False,
        alert_recorder=lambda key, result: None,
        recipient_keyword="周行",
    ).send_alert(
        BrowserAlertEvent(
            event_type="browser_sync_failed",
            company_id="merchant-company-001",
            shop_id="shop-001",
            data_source_name="千牛资金日账单",
            biz_date="2026-05-19",
            sync_job_id="sync-env-001",
            severity="critical",
            reason="ENV_CHANNEL_TEST",
            message="环境钉钉凭证验证",
        )
    )

    assert result["status"] == "sent"
    assert built == ["dingtalk-env-adapter"]


def test_browser_alert_content_explains_agent_interrupted_in_plain_language() -> None:
    content = browser_alerts._compose_alert_content(
        BrowserAlertEvent(
            event_type="browser_sync_failed",
            company_id="merchant-company-001",
            shop_id="browser-collection-04576bddc3",
            data_source_name="tb0131100248-收支账单",
            biz_date="2026-05-26",
            sync_job_id="sync-agent-interrupted",
            severity="critical",
            reason="AGENT_INTERRUPTED",
            message="AGENT_INTERRUPTED: browser-agent restarted while this job was running",
        )
    )

    assert "直观原因: 采集任务运行中，浏览器采集机或本地服务被重启/中断，任务未正常跑完。" in content
    assert "处理建议: 确认是否刚执行过服务重启/发版；确认采集机在线后，重新采集或重新触发本次对账。" in content


def test_browser_alert_service_dedupes_existing_alert() -> None:
    adapter = FakeAdapter()
    service = BrowserAlertService(
        adapter_factory=lambda: adapter,
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
    assert adapter.bot_calls == []


def test_browser_alert_service_fails_without_external_side_effect_when_bot_send_fails() -> None:
    adapter = FakeAdapter(bot_success=False)
    recorded: list[tuple[str, dict[str, object]]] = []
    service = BrowserAlertService(
        adapter_factory=lambda: adapter,
        dedupe_checker=lambda key: False,
        alert_recorder=lambda key, result: recorded.append((key, result)),
        recipient_keyword="周行",
    )

    result = service.send_alert(
        BrowserAlertEvent(
            event_type="browser_sync_failed",
            company_id="company-001",
            shop_id="shop-001",
            data_source_name="千牛资金日账单",
            biz_date="2026-05-19",
            sync_job_id="sync-002",
            severity="critical",
            reason="PARTIAL_TEST",
            message="bot 失败但待办已创建",
        )
    )

    assert result["status"] == "failed"
    assert result["message_id"] == ""
    assert "todo_id" not in result
    assert recorded == []
