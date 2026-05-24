from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.data_agent_ws import DataAgentWsClient


class FakeWs:
    def __init__(self, scripted):
        self.sent=[]; self._q=asyncio.Queue()
        for s in scripted: self._q.put_nowait(s)
    async def send(self, raw): self.sent.append(json.loads(raw))
    async def recv(self): return await self._q.get()
    def feed(self,obj): self._q.put_nowait(json.dumps(obj))
    def __aiter__(self): return self
    async def __anext__(self): return await self._q.get()
    async def close(self): pass


def _client(fake):
    async def connector(url): return fake
    return DataAgentWsClient(ws_url="ws://t/browser-agent", agent_id="A", max_concurrency=1,
                             token_provider=lambda:"tok", connector=connector)


def test_report_risk_waiting_sends_domain_frame():
    fake=FakeWs([json.dumps({"type":"hello_ack","ok":True})])
    client=_client(fake)
    async def run():
        task=asyncio.create_task(client.report_risk_waiting(
            sync_job_id="j1", reason="RISK_VERIFICATION", company_id="c1",
            shop_id="s1", data_source_id="ds1"))
        await asyncio.sleep(0.05)
        sent=fake.sent[-1]
        fake.feed({"type":"result","id":sent["id"],"ok":True,"data":{"handoff_session_id":"h1"}})
        return await task
    res=asyncio.run(run())
    sent=fake.sent[-1]
    assert sent["type"]=="risk_waiting" and sent["sync_job_id"]=="j1" and sent["reason"]=="RISK_VERIFICATION"
    assert res.get("handoff_session_id")=="h1"
