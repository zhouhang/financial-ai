from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.data_agent_ws import DataAgentWsClient


class FakeWs:
    """假 WS:记录 sent;recv 按脚本返回;支持 async for(reader)。"""
    def __init__(self, scripted_incoming):
        self.sent: list[dict] = []
        self._incoming = asyncio.Queue()
        for item in scripted_incoming:
            self._incoming.put_nowait(item)
        self.closed = False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        return await self._incoming.get()

    def feed(self, obj):
        self._incoming.put_nowait(json.dumps(obj))

    def __aiter__(self):
        return self

    async def __anext__(self):
        raw = await self._incoming.get()
        if raw is None:
            raise StopAsyncIteration
        return raw

    async def close(self):
        self.closed = True


def _client(fake):
    async def connector(url):
        return fake
    return DataAgentWsClient(
        ws_url="ws://test/browser-agent", agent_id="agent-A", max_concurrency=2,
        token_provider=lambda: "tok-1", connector=connector,
    )


@pytest.mark.asyncio
async def test_hello_sent_on_connect_and_request_resolves_by_id():
    fake = FakeWs([json.dumps({"type": "hello_ack", "ok": True})])
    client = _client(fake)

    async def run():
        task = asyncio.create_task(client.request("claim", {}))
        await asyncio.sleep(0.05)
        sent_claim = fake.sent[-1]
        fake.feed({"type": "result", "id": sent_claim["id"], "ok": True, "data": {"job": None}})
        return await task

    result = await run()
    assert result == {"job": None}
    assert fake.sent[0]["type"] == "hello" and fake.sent[0]["token"] == "tok-1"
    assert fake.sent[0]["agent_id"] == "agent-A" and fake.sent[0]["max_concurrency"] == 2
    assert fake.sent[1]["type"] == "claim" and fake.sent[1]["id"]


@pytest.mark.asyncio
async def test_request_returns_error_on_not_ok():
    fake = FakeWs([json.dumps({"type": "hello_ack", "ok": True})])
    client = _client(fake)
    task = asyncio.create_task(client.request("queue_requeue_ready", {}))
    await asyncio.sleep(0.05)
    fake.feed({"type": "result", "id": fake.sent[-1]["id"], "ok": False, "error": "boom"})
    res = await task
    assert res["success"] is False and "boom" in res["error"]


@pytest.mark.asyncio
async def test_hello_ack_failure_blocks_request():
    fake = FakeWs([json.dumps({"type": "hello_ack", "ok": False, "error": "鉴权失败"})])
    client = _client(fake)
    res = await client.request("claim", {})
    assert res["success"] is False


@pytest.mark.asyncio
async def test_reader_dispatches_event_frames_to_handler():
    seen = []

    async def on_event(msg):
        seen.append(msg)

    fake = FakeWs([json.dumps({"type": "hello_ack", "ok": True})])

    async def connector(url):
        return fake

    client = DataAgentWsClient(
        ws_url="ws://test/browser-agent",
        agent_id="agent-A",
        max_concurrency=2,
        token_provider=lambda: "tok-1",
        connector=connector,
        event_handler=on_event,
    )
    assert await client.connect() is True
    fake.feed({"type": "event", "event": "handoff_start", "handoff_session_id": "h1"})
    await asyncio.sleep(0.05)

    assert seen == [{"type": "event", "event": "handoff_start", "handoff_session_id": "h1"}]


@pytest.mark.asyncio
async def test_send_event_sends_without_result_roundtrip():
    fake = FakeWs([json.dumps({"type": "hello_ack", "ok": True})])
    client = _client(fake)

    result = await client.send_event({"type": "handoff_frame", "handoff_session_id": "h1"})

    assert result == {"success": True}
    assert fake.sent[-1] == {"type": "handoff_frame", "handoff_session_id": "h1"}
