from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import browser_agent_gateway as gw


def _conn() -> gw.BrowserAgentConnection:
    return gw.BrowserAgentConnection(token="tok", agent_id="A", max_concurrency=1)


def test_risk_waiting_creates_session_and_notifies_owner(monkeypatch):
    gw._NOTIFIED_RISK_JOBS.clear()
    calls = {"create": 0, "load_channel": [], "resolve": [], "notify": []}

    async def fake_call(tool, args):
        if tool == "browser_handoff_session_create":
            calls["create"] += 1
            assert "channel_config_id" not in args
            return {
                "success": True,
                "handoff_session_id": "h1",
                "handoff_token": "TKN",
                "status": "pending",
                "channel_config_id": "chan1",
                "owner": {"identifier": "u1", "name": "周行"},
            }
        return {"success": True}

    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    class FakeResolved:
        success = True
        resolved_user = type("U", (), {"user_id": "ding-u1"})()

    class FakeAdapter:
        def resolve_user(self, *, user_id="", mobile="", keyword=""):
            calls["resolve"].append({"user_id": user_id, "mobile": mobile, "keyword": keyword})
            return FakeResolved()

        def send_bot_message(self, *, content, to_user_id="", **kwargs):
            calls["notify"].append({"content": content, "to_user_id": to_user_id, **kwargs})
            return type("R", (), {"success": True, "message": "ok"})()

    monkeypatch.setattr(gw, "get_notification_adapter", lambda **kwargs: FakeAdapter())
    monkeypatch.setattr(
        gw,
        "load_company_channel_config_by_id",
        lambda **kwargs: calls["load_channel"].append(kwargs) or type("C", (), {"id": "chan1", "provider": "feishu"})(),
    )
    monkeypatch.setenv("TALLY_PUBLIC_BASE_URL", "https://dev.tallyai.cn/api")

    result = asyncio.run(
        gw.handle_domain_message(
            _conn(),
            {
                "type": "risk_waiting",
                "id": "e1",
                "sync_job_id": "j-owner",
                "reason": "RISK_VERIFICATION",
                "company_id": "c1",
                "shop_id": "s1",
            },
        )
    )

    assert result["ok"] is True
    assert calls["create"] == 1
    assert calls["load_channel"] == [{"channel_id": "chan1"}]
    assert calls["resolve"] == [{"user_id": "u1", "mobile": "", "keyword": "周行"}]
    assert len(calls["notify"]) == 1
    assert calls["notify"][0]["to_user_id"] == "ding-u1"
    assert calls["notify"][0]["content_type"] == "markdown"
    assert calls["notify"][0]["title"] == "Tally 浏览器人工验证"
    assert "[打开验证链接](https://dev.tallyai.cn/handoff?t=TKN)" in calls["notify"][0]["content"]
    assert "https://dev.tallyai.cn/api/handoff" not in calls["notify"][0]["content"]
    assert "/p/handoff" not in calls["notify"][0]["content"]

    deduped = asyncio.run(
        gw.handle_domain_message(
            _conn(),
            {
                "type": "risk_waiting",
                "id": "e2",
                "sync_job_id": "j-owner",
                "reason": "RISK_VERIFICATION",
                "company_id": "c1",
                "shop_id": "s1",
            },
        )
    )
    assert deduped["ok"] is True
    assert calls["create"] == 1 and len(calls["notify"]) == 1


def test_risk_waiting_without_owner_falls_back_to_alert_recipient(monkeypatch):
    gw._NOTIFIED_RISK_JOBS.clear()
    calls = {"adapter": 0, "load_channel": 0, "fallback": []}

    async def fake_call(tool, args):
        if tool == "browser_handoff_session_create":
            return {
                "success": True,
                "handoff_session_id": "h2",
                "handoff_token": "TKN2",
                "status": "pending",
                "channel_config_id": "chan1",
                "owner": {},
            }
        return {"success": True}

    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    def unexpected_adapter(**kwargs):
        calls["adapter"] += 1
        raise AssertionError("owner-less handoff must not use the per-company channel adapter")

    def unexpected_load_channel(**kwargs):
        calls["load_channel"] += 1
        raise AssertionError("owner-less handoff must not load the per-company channel")

    monkeypatch.setattr(gw, "get_notification_adapter", unexpected_adapter)
    monkeypatch.setattr(gw, "load_company_channel_config_by_id", unexpected_load_channel)

    def fake_fallback(*, company_id, sync_job_id, shop_id, reason, link):
        calls["fallback"].append(
            {"company_id": company_id, "sync_job_id": sync_job_id,
             "shop_id": shop_id, "reason": reason, "link": link}
        )
        return True

    monkeypatch.setattr(gw, "_notify_handoff_fallback", fake_fallback)
    monkeypatch.setenv("TALLY_PUBLIC_BASE_URL", "https://dev.tallyai.cn/api")

    result = asyncio.run(
        gw.handle_domain_message(
            _conn(),
            {
                "type": "risk_waiting",
                "id": "e1",
                "sync_job_id": "j-no-owner",
                "reason": "RISK_VERIFICATION",
                "company_id": "c1",
                "shop_id": "s9",
            },
        )
    )

    assert result["ok"] is True
    assert result["data"]["notified"] is True
    # 主通道(per-company channel)未被使用,确认是走兜底
    assert calls["adapter"] == 0 and calls["load_channel"] == 0
    assert len(calls["fallback"]) == 1
    assert calls["fallback"][0]["company_id"] == "c1"
    assert calls["fallback"][0]["sync_job_id"] == "j-no-owner"
    assert calls["fallback"][0]["shop_id"] == "s9"
    assert calls["fallback"][0]["link"] == "https://dev.tallyai.cn/handoff?t=TKN2"


def test_handoff_fallback_reuses_browser_alert_service(monkeypatch):
    import services.browser_alerts as ba

    captured = {}

    class FakeService:
        def send_alert(self, event):
            captured["event"] = event
            return {"status": "sent"}

    monkeypatch.setattr(ba, "BrowserAlertService", FakeService)

    ok = gw._notify_handoff_fallback(
        company_id="c1",
        sync_job_id="j1",
        shop_id="s1",
        reason="RISK_VERIFICATION",
        link="https://dev.tallyai.cn/handoff?t=TKN",
    )

    assert ok is True
    event = captured["event"]
    assert event.event_type == "risk_blocked"
    assert event.company_id == "c1"
    assert event.sync_job_id == "j1"
    assert event.shop_id == "s1"
    assert "https://dev.tallyai.cn/handoff?t=TKN" in event.message


def test_risk_waiting_missing_company_errors(monkeypatch):
    result = asyncio.run(
        gw.handle_domain_message(_conn(), {"type": "risk_waiting", "id": "e", "sync_job_id": "j2"})
    )
    assert result["ok"] is False
