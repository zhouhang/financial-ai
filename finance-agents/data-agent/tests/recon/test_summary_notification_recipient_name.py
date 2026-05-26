from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

nodes = importlib.import_module("graphs.recon.auto_scheme_run.nodes")
notifications_models = importlib.import_module("services.notifications.models")

NotificationUser = notifications_models.NotificationUser
NotificationChannelConfig = notifications_models.NotificationChannelConfig
UserResolveResult = notifications_models.UserResolveResult
BotMessageResult = notifications_models.BotMessageResult


class _UserIdOnlyAdapter:
    """Mimics the DingTalk dws shortcut: resolving by userId cannot fetch the
    real contact name (contact.user:get needs interactive PAT permission), so
    it returns display_name == userId as a placeholder."""

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        resolved = NotificationUser(user_id=user_id, display_name=user_id)
        return UserResolveResult(
            success=True,
            provider="dingtalk_dws",
            message="ok",
            users=[resolved],
            resolved_user=resolved,
        )

    def send_bot_message(
        self, *, title: str, content: str, to_user_id: str, content_type: str = "text"
    ) -> BotMessageResult:
        return BotMessageResult(
            success=True,
            provider="dingtalk_dws",
            message="ok",
            message_id="msg-001",
            receiver_user_id=to_user_id,
        )


def _channel_config() -> NotificationChannelConfig:
    return NotificationChannelConfig(
        id="channel-001",
        company_id="company-001",
        provider="dingtalk_dws",
        channel_code="default",
        name="默认钉钉",
        robot_code="robot",
    )


def test_summary_recipient_name_prefers_configured_name_over_userid(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the recipient was configured with a real name but resolve-by-userId
    only echoes back the userId, the summary should report the configured name."""
    user_id = "072007534524160438"
    monkeypatch.setattr(nodes, "get_notification_adapter", lambda **_: _UserIdOnlyAdapter())

    ctx = {
        "run_plan": {
            "plan_meta_json": {
                "summary_recipient": {
                    "channel_config_id": "channel-001",
                    "user_id": user_id,
                    "display_name": "周行",
                }
            }
        },
        "execution_run_record": {"id": "run-001"},
    }

    result = asyncio.run(
        nodes._send_run_summary_notification(
            ctx=ctx,
            auth_token="token",
            channel_config=_channel_config(),
            anomalies=[],
            threshold=0,
            explosion=False,
        )
    )

    assert result["status"] == "sent"
    assert result["summary_recipient"]["name"] == "周行"
    assert result["summary_recipient"]["identifier"] == user_id
