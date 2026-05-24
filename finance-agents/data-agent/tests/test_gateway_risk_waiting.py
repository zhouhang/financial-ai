from __future__ import annotations
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import browser_agent_gateway as gw


def _conn():
    return gw.BrowserAgentConnection(token="tok", agent_id="A", max_concurrency=1)


def test_risk_waiting_creates_session_and_notifies(monkeypatch):
    calls={"create":0,"notify":[]}
    async def fake_call(tool,args):
        if tool=="browser_handoff_session_create":
            calls["create"]+=1
            return {"success":True,"handoff_session_id":"h1","handoff_token":"TKN","status":"pending"}
        return {"success":True}
    monkeypatch.setattr(gw,"call_mcp_tool",fake_call)

    class FakeAdapter:
        def send_bot_message(self,*,content,to_user_id="",**k):
            calls["notify"].append(content)
            class R: success=True; message="ok"
            return R()
    monkeypatch.setattr(gw,"get_notification_adapter",lambda **k: FakeAdapter())
    monkeypatch.setattr(gw,"load_company_channel_config",lambda **k: type("C",(),{"id":"chan1","provider":"feishu"})())
    monkeypatch.setenv("TALLY_PUBLIC_BASE_URL","https://dev.tallyai.cn/api")

    conn=_conn()
    r1=asyncio.run(gw.handle_domain_message(conn, {"type":"risk_waiting","id":"e1",
        "sync_job_id":"j1","reason":"RISK_VERIFICATION","company_id":"c1","shop_id":"s1"}))
    assert r1["ok"] is True and calls["create"]==1
    assert len(calls["notify"])==1 and "/p/handoff?t=TKN" in calls["notify"][0]

    r2=asyncio.run(gw.handle_domain_message(conn, {"type":"risk_waiting","id":"e2",
        "sync_job_id":"j1","reason":"RISK_VERIFICATION","company_id":"c1","shop_id":"s1"}))
    assert r2["ok"] is True and calls["create"]==1 and len(calls["notify"])==1  # idempotent


def test_risk_waiting_missing_company_errors(monkeypatch):
    r=asyncio.run(gw.handle_domain_message(_conn(), {"type":"risk_waiting","id":"e","sync_job_id":"j2"}))
    assert r["ok"] is False
