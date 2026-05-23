# Browser-agent WS 传输层迁移(阶段 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 browser-agent 与云端的通信从"直连 finance-mcp 的 MCP SSE"改为"经 WebSocket 连 data-agent、由 data-agent 作为唯一 finance-mcp 调用方中转",并保持双工就绪(暂不实现 handoff)。

**Architecture:** browser-agent 用一条主动出站 WebSocket 连 data-agent;首帧 `hello` 提交 system JWT 鉴权;之后收发"领域消息"(带 `id` 配对),不出现 MCP 工具名。data-agent 校验 `role=system` 后把领域消息映射成 finance-mcp 工具调用、注入 `worker_token`/`agent_id`,经既有 `call_mcp_tool` 转发。finance-mcp 的 7 个工具与 dispatcher_loop 完全不动。

**Tech Stack:** Python 3.12;browser-agent 客户端用 `websockets`(root `.venv` 已装 16.0);data-agent 服务端用 FastAPI/starlette WebSocket(已有 `/chat` 先例);PyJWT 本地校验。

---

## 关键事实(实现前必读)

- **设计依据**:`docs/superpowers/specs/2026-05-23-browser-agent-risk-handoff-design.md` 的「通信架构」「阶段 0」。
- **browser-agent**(目录 `finance-agents/browser-agent/`,包名 `finance_browser_agent`):
  - `tally_client.py`:`BrowserAgentConfig`(env 配置)+ `BrowserAgentTallyClient`(7 个方法:`claim_browser_job` / `heartbeat` / `mark_browser_job_success` / `mark_browser_job_failed` / `requeue_ready_waiting` / `fail_failed_waiting` / `fail_expired_waiting`)。当前 `_call(tool, args)` → `self._session.call_tool(...)`(MCP SSE)。`create_system_token(agent_id)` 签 `role="system"` 的 JWT(`JWT_SECRET`,HS256,2h)。`worker_token` 属性按需重签。
  - `mcp_session.py`:`McpSession`(直连 finance-mcp 的 SSE 传输,本轮停用)。
  - `dispatcher_loop.py` / `service.py`:**不改**。`service.main()` 构造 `BrowserAgentTallyClient(config=config)` 并跑 heartbeat/dispatcher/reconciler。
- **data-agent**(目录 `finance-agents/data-agent/`):
  - `tools/mcp_client.py`:`call_mcp_tool(tool_name, arguments) -> dict`(全局 SSE 单例,唯一 finance-mcp 调用入口)。
  - `server.py`:FastAPI `app`,已有 `@app.websocket("/chat")`(首帧带 token、`auth_me` 校验的模式)。
- **finance-mcp 7 个工具(不改)** 及其参数:
  - `browser_sync_job_claim`(worker_token, agent_id, max_concurrency)
  - `browser_agent_heartbeat`(worker_token, company_id, agent_id, hostname, version, capabilities)
  - `browser_sync_job_complete`(worker_token, + 上报 payload)
  - `browser_sync_job_fail`(worker_token, + 上报 payload)
  - `recon_queue_requeue_ready_waiting` / `recon_queue_fail_failed_collection_waiting` / `recon_queue_fail_expired_waiting`(worker_token)
- **测试运行**:
  - data-agent:`cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/<file> -v`
  - browser-agent:`cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/<file> -v`
  - 异步测试沿用仓库现有约定(pytest-asyncio,STRICT 模式 → 用 `@pytest.mark.asyncio`;若某目录用 anyio 则改 `@pytest.mark.anyio`,以同目录现有测试为准)。
- **鉴权与 token 刷新**:`hello` 帧带 token 作为连接级鉴权门;data-agent 把该 token 存为连接的 `worker_token` 转发用;`heartbeat` 领域消息再带上当前 token,data-agent 据此刷新存储的 token(心跳 30s ≪ token 2h,避免长连接 token 过期)。其余领域消息不带 token,worker_token 由 data-agent 注入。

## 领域消息协议(本计划锚点)

- `hello`(agent→DA):`{"type":"hello","token":"<jwt>","agent_id":"<id>","max_concurrency":2}`
- `hello_ack`(DA→agent):`{"type":"hello_ack","ok":true}` 或 `{"ok":false,"error":"..."}`
- 请求(agent→DA):`{"type":"<domain>","id":"<uuid>", ...payload}`
- 响应(DA→agent):`{"type":"result","id":"<uuid>","ok":true,"data":{...}}` 或 `{"ok":false,"error":"..."}`
- 领域类型 → MCP 工具:`claim`→`browser_sync_job_claim`、`heartbeat`→`browser_agent_heartbeat`、`job_complete`→`browser_sync_job_complete`、`job_fail`→`browser_sync_job_fail`、`queue_requeue_ready`→`recon_queue_requeue_ready_waiting`、`queue_fail_failed`→`recon_queue_fail_failed_collection_waiting`、`queue_fail_expired`→`recon_queue_fail_expired_waiting`。
- (预留,本轮不实现)`event`(DA→agent)+ 上行截图帧,供 handoff 用;agent 收到 `event` 暂忽略。

---

## 文件结构

- Create `finance-agents/data-agent/services/browser_agent_gateway.py` — 纯逻辑:token 校验 + 领域↔MCP 映射 + 连接态(可单测,不依赖 WS)。
- Modify `finance-agents/data-agent/server.py` — 新增 `@app.websocket("/browser-agent")`,委托给 gateway。
- Create `finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py` — `DataAgentWsClient`(WS 传输,connector 可注入以便单测)。
- Modify `finance-agents/browser-agent/finance_browser_agent/tally_client.py` — `BrowserAgentConfig`(换 `data_agent_ws_url`)+ `BrowserAgentTallyClient` 改用 WS + 领域消息。
- Modify `finance-agents/browser-agent/tests/test_tally_client.py` — 适配新客户端。
- Tests:`data-agent/tests/test_browser_agent_gateway.py`、`data-agent/tests/test_browser_agent_ws_endpoint.py`、`browser-agent/tests/test_data_agent_ws.py`。

---

## Task 1: data-agent gateway 纯逻辑(token 校验 + 领域↔MCP 映射)

**Files:**
- Create: `finance-agents/data-agent/services/browser_agent_gateway.py`
- Test: `finance-agents/data-agent/tests/test_browser_agent_gateway.py`

- [ ] **Step 1: 写失败测试**

`tests/test_browser_agent_gateway.py`:
```python
from __future__ import annotations
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import browser_agent_gateway as gw

_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def _token(role: str = "system") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": "browser-agent:a1", "role": role, "iat": now, "exp": now + timedelta(hours=2)},
        _SECRET, algorithm="HS256",
    )


def test_verify_system_token_accepts_system_role():
    assert gw.verify_system_token(_token("system")) is not None


def test_verify_system_token_rejects_non_system_and_garbage():
    assert gw.verify_system_token(_token("member")) is None
    assert gw.verify_system_token("not-a-jwt") is None
    assert gw.verify_system_token("") is None


def _conn() -> "gw.BrowserAgentConnection":
    return gw.BrowserAgentConnection(token="tok-1", agent_id="agent-A", max_concurrency=3)


@pytest.mark.asyncio
async def test_claim_maps_to_tool_with_injected_args(monkeypatch):
    calls = []
    async def fake_call(tool, args):
        calls.append((tool, args))
        return {"job": None}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    rid = str(uuid.uuid4())
    reply = await gw.handle_domain_message(_conn(), {"type": "claim", "id": rid})
    assert reply == {"type": "result", "id": rid, "ok": True, "data": {"job": None}}
    tool, args = calls[0]
    assert tool == "browser_sync_job_claim"
    assert args == {"worker_token": "tok-1", "agent_id": "agent-A", "max_concurrency": 3}


@pytest.mark.asyncio
async def test_job_complete_passes_payload_and_injects_token(monkeypatch):
    calls = []
    async def fake_call(tool, args):
        calls.append((tool, args)); return {"success": True}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    reply = await gw.handle_domain_message(
        _conn(), {"type": "job_complete", "id": "x", "sync_job_id": "j1", "records": [], "capture_files": []},
    )
    assert reply["ok"] is True
    tool, args = calls[0]
    assert tool == "browser_sync_job_complete"
    assert args["worker_token"] == "tok-1"
    assert args["sync_job_id"] == "j1" and args["records"] == [] and args["capture_files"] == []
    assert "type" not in args and "id" not in args


@pytest.mark.asyncio
async def test_heartbeat_refreshes_token(monkeypatch):
    captured = {}
    async def fake_call(tool, args):
        captured["args"] = args; return {"success": True}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)
    conn = _conn()
    await gw.handle_domain_message(conn, {"type": "heartbeat", "id": "h", "token": "tok-2", "company_id": "c1"})
    assert conn.token == "tok-2"                       # 已刷新
    assert captured["args"]["worker_token"] == "tok-2"  # 用刷新后的 token
    assert captured["args"]["agent_id"] == "agent-A"
    assert captured["args"]["company_id"] == "c1"
    assert "token" not in captured["args"]              # token 不作为工具参数透传


@pytest.mark.asyncio
async def test_unknown_type_returns_error(monkeypatch):
    async def fake_call(tool, args):
        raise AssertionError("不应调用 MCP")
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)
    reply = await gw.handle_domain_message(_conn(), {"type": "nope", "id": "z"})
    assert reply["ok"] is False and "未知消息类型" in reply["error"]


@pytest.mark.asyncio
async def test_mcp_exception_becomes_error_result(monkeypatch):
    async def fake_call(tool, args):
        raise RuntimeError("boom")
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)
    reply = await gw.handle_domain_message(_conn(), {"type": "queue_requeue_ready", "id": "q"})
    assert reply["ok"] is False and "boom" in reply["error"]
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_browser_agent_gateway.py -v`
Expected: FAIL（`ModuleNotFoundError: services.browser_agent_gateway`）。若报缺少 `pytest-asyncio`,先 `./.venv/bin/pip install pytest-asyncio` 并在 `tests/` 确认 asyncio 模式可用(仓库已用 anyio/asyncio 插件,见现有通知测试)。

- [ ] **Step 3: 实现 gateway**

`services/browser_agent_gateway.py`:
```python
"""data-agent ↔ browser-agent WebSocket 网关(纯逻辑)。

校验采集机的 system JWT,把"领域消息"映射成 finance-mcp 工具调用并经 call_mcp_tool 转发,
注入 worker_token(连接级已校验 token)与 agent_id。data-agent 是唯一 finance-mcp 调用方。
"""
from __future__ import annotations

import os
from typing import Any

import jwt

from tools.mcp_client import call_mcp_tool

_JWT_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
_JWT_ALG = "HS256"

# 领域消息类型 → finance-mcp 工具(白名单:只有这些可被采集机触发)
_DOMAIN_TOOL_MAP: dict[str, str] = {
    "claim": "browser_sync_job_claim",
    "heartbeat": "browser_agent_heartbeat",
    "job_complete": "browser_sync_job_complete",
    "job_fail": "browser_sync_job_fail",
    "queue_requeue_ready": "recon_queue_requeue_ready_waiting",
    "queue_fail_failed": "recon_queue_fail_failed_collection_waiting",
    "queue_fail_expired": "recon_queue_fail_expired_waiting",
}


def verify_system_token(token: str) -> dict[str, Any] | None:
    """校验 JWT 且必须 role=system,否则返回 None。"""
    try:
        payload = jwt.decode(str(token or ""), _JWT_SECRET, algorithms=[_JWT_ALG])
    except jwt.InvalidTokenError:
        return None
    if payload.get("role") != "system":
        return None
    return payload


class BrowserAgentConnection:
    """单条 WS 连接的状态:已校验 token + agent_id + max_concurrency。"""

    def __init__(self, *, token: str, agent_id: str, max_concurrency: int) -> None:
        self.token = token
        self.agent_id = agent_id
        self.max_concurrency = max_concurrency

    def _maybe_refresh_token(self, msg_type: str, msg: dict[str, Any]) -> None:
        if msg_type == "heartbeat" and msg.get("token"):
            self.token = str(msg["token"])

    def _build_args(self, msg_type: str, msg: dict[str, Any]) -> dict[str, Any]:
        payload = {k: v for k, v in msg.items() if k not in ("type", "id", "token")}
        args: dict[str, Any] = {"worker_token": self.token}
        if msg_type == "claim":
            args["agent_id"] = self.agent_id
            args["max_concurrency"] = self.max_concurrency
        elif msg_type == "heartbeat":
            args["agent_id"] = self.agent_id
            args.update(payload)
        else:
            args.update(payload)
        return args


async def handle_domain_message(conn: BrowserAgentConnection, msg: dict[str, Any]) -> dict[str, Any]:
    msg_type = str(msg.get("type") or "")
    req_id = str(msg.get("id") or "")
    tool = _DOMAIN_TOOL_MAP.get(msg_type)
    if tool is None:
        return {"type": "result", "id": req_id, "ok": False, "error": f"未知消息类型: {msg_type}"}
    conn._maybe_refresh_token(msg_type, msg)
    args = conn._build_args(msg_type, msg)
    try:
        data = await call_mcp_tool(tool, args)
    except Exception as exc:  # noqa: BLE001 — 转成结果帧,避免拖垮 WS 循环
        return {"type": "result", "id": req_id, "ok": False, "error": str(exc)}
    return {"type": "result", "id": req_id, "ok": True, "data": data}
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_browser_agent_gateway.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add finance-agents/data-agent/services/browser_agent_gateway.py finance-agents/data-agent/tests/test_browser_agent_gateway.py
git commit -m "feat(data-agent): browser-agent WS gateway logic (domain->mcp relay)"
```

---

## Task 2: data-agent `/browser-agent` WebSocket 端点

**Files:**
- Modify: `finance-agents/data-agent/server.py`(在 `/chat` 端点之后新增)
- Test: `finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py`

- [ ] **Step 1: 写失败测试(FastAPI TestClient websocket)**

`tests/test_browser_agent_ws_endpoint.py`:
```python
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from services import browser_agent_gateway as gw

_SECRET = os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def _token(role="system"):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": "browser-agent:a1", "role": role, "iat": now, "exp": now + timedelta(hours=2)},
                      _SECRET, algorithm="HS256")


def test_rejects_non_system_token():
    client = TestClient(server.app)
    with client.websocket_connect("/browser-agent") as ws:
        ws.send_json({"type": "hello", "token": _token("member"), "agent_id": "a1"})
        ack = ws.receive_json()
        assert ack == {"type": "hello_ack", "ok": False, "error": ack["error"]}
        assert ack["ok"] is False


def test_hello_then_claim_relays_to_mcp(monkeypatch):
    async def fake_call(tool, args):
        assert tool == "browser_sync_job_claim"
        assert args["worker_token"] and args["agent_id"] == "a1" and args["max_concurrency"] == 2
        return {"job": {"id": "job-1"}}
    monkeypatch.setattr(gw, "call_mcp_tool", fake_call)

    client = TestClient(server.app)
    with client.websocket_connect("/browser-agent") as ws:
        ws.send_json({"type": "hello", "token": _token("system"), "agent_id": "a1", "max_concurrency": 2})
        assert ws.receive_json() == {"type": "hello_ack", "ok": True}
        ws.send_json({"type": "claim", "id": "r1"})
        reply = ws.receive_json()
        assert reply == {"type": "result", "id": "r1", "ok": True, "data": {"job": {"id": "job-1"}}}
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_browser_agent_ws_endpoint.py -v`
Expected: FAIL（无 `/browser-agent` 路由 → `WebSocketDisconnect`/连接被拒）

- [ ] **Step 3: 实现端点**

在 `server.py` 顶部 import 处补:
```python
from services.browser_agent_gateway import (
    BrowserAgentConnection,
    handle_domain_message,
    verify_system_token,
)
```
在 `websocket_chat` 函数之后新增:
```python
@app.websocket("/browser-agent")
async def websocket_browser_agent(ws: WebSocket):
    """采集机 WS 端点:首帧 hello 鉴权(role=system),之后中转领域消息到 finance-mcp。"""
    await ws.accept()
    conn: BrowserAgentConnection | None = None
    try:
        hello = json.loads(await ws.receive_text())
        payload = verify_system_token(str(hello.get("token") or "")) if hello.get("type") == "hello" else None
        if payload is None:
            await ws.send_json({"type": "hello_ack", "ok": False, "error": "鉴权失败:需要 role=system 的 token"})
            await ws.close()
            return
        conn = BrowserAgentConnection(
            token=str(hello.get("token")),
            agent_id=str(hello.get("agent_id") or ""),
            max_concurrency=int(hello.get("max_concurrency") or 1),
        )
        logger.info("browser-agent WS 已连接: agent_id=%s", conn.agent_id)
        await ws.send_json({"type": "hello_ack", "ok": True})
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "result", "id": "", "ok": False, "error": "无效的 JSON"})
                continue
            reply = await handle_domain_message(conn, msg)
            await ws.send_json(reply)
    except WebSocketDisconnect:
        logger.info("browser-agent WS 断开: agent_id=%s", conn.agent_id if conn else "?")
    except Exception:
        logger.exception("browser-agent WS 处理异常")
```
（`json`、`WebSocket`、`WebSocketDisconnect`、`logger` 在 server.py 已 import,沿用。）

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_browser_agent_ws_endpoint.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add finance-agents/data-agent/server.py finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py
git commit -m "feat(data-agent): /browser-agent WebSocket endpoint"
```

---

## Task 3: browser-agent `DataAgentWsClient`

**Files:**
- Create: `finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py`
- Test: `finance-agents/browser-agent/tests/test_data_agent_ws.py`

> 设计要点:`connector` 可注入(默认 `websockets.connect`),便于单测;`request(type, payload)` 用客户端生成的 `id` 配对 `result` 帧;后台 reader 解析响应、忽略 `event` 帧;断线时挂起请求以异常结束,下次 `request` 自动重连。

- [ ] **Step 1: 写失败测试(注入假 WS)**

`tests/test_data_agent_ws.py`:
```python
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
    # hello_ack 先入队供 connect 读取
    fake = FakeWs([json.dumps({"type": "hello_ack", "ok": True})])
    client = _client(fake)

    async def run():
        task = asyncio.create_task(client.request("claim", {}))
        await asyncio.sleep(0.05)
        # reader 通过 async-for 读到 result 帧
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
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_data_agent_ws.py -v`
Expected: FAIL（`ModuleNotFoundError: finance_browser_agent.data_agent_ws`）

- [ ] **Step 3: 实现 WS 客户端**

`finance_browser_agent/data_agent_ws.py`:
```python
"""Browser-agent → data-agent WebSocket 传输。

单条主动出站 WS:connect 时发 hello 帧(system JWT + agent_id)鉴权;之后发"领域消息"
(客户端生成 id),等待匹配的 result 帧。后台 reader 解析响应并兑现挂起的 future,event 帧
本轮忽略(handoff 用)。断线时挂起请求以异常结束,下次 request 自动重连。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable

import websockets

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 120.0
_CONNECT_TIMEOUT = 10.0


async def _default_connector(url: str):
    return await websockets.connect(url, max_size=None)


class DataAgentWsClient:
    def __init__(
        self,
        *,
        ws_url: str,
        agent_id: str,
        max_concurrency: int,
        token_provider: Callable[[], str],
        connector: Callable[[str], Awaitable[Any]] = _default_connector,
    ) -> None:
        self._ws_url = ws_url
        self._agent_id = agent_id
        self._max_concurrency = max_concurrency
        self._token_provider = token_provider
        self._connector = connector
        self._ws: Any = None
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self._ws is not None and self._reader_task and not self._reader_task.done():
                return True
            try:
                self._ws = await asyncio.wait_for(self._connector(self._ws_url), timeout=_CONNECT_TIMEOUT)
                await self._ws.send(json.dumps({
                    "type": "hello",
                    "token": self._token_provider(),
                    "agent_id": self._agent_id,
                    "max_concurrency": self._max_concurrency,
                }))
                ack = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=_CONNECT_TIMEOUT))
                if ack.get("type") != "hello_ack" or not ack.get("ok"):
                    logger.error("data-agent WS 鉴权失败: %s", ack)
                    await self._close()
                    return False
                self._reader_task = asyncio.create_task(self._reader())
                logger.info("data-agent WS 已连接: %s", self._ws_url)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.error("data-agent WS 连接失败: %s", exc)
                await self._close()
                return False

    async def _close(self) -> None:
        ws, self._ws = self._ws, None
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        self._reader_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("data-agent WS 已断开"))
        self._pending.clear()
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def _reader(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "result":
                    fut = self._pending.pop(str(msg.get("id") or ""), None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                # 其它类型(event)本轮忽略
        except Exception as exc:  # noqa: BLE001
            logger.warning("data-agent WS 读取中断: %s", exc)
        finally:
            await self._close()

    async def request(self, msg_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None or (self._reader_task and self._reader_task.done()):
            if not await self.connect():
                return {"success": False, "error": "无法建立 data-agent WS 连接"}
        req_id = str(uuid.uuid4())
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        try:
            await self._ws.send(json.dumps({"type": msg_type, "id": req_id, **payload}))
            result = await asyncio.wait_for(fut, timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            return {"success": False, "error": "等待 data-agent 响应超时"}
        except Exception as exc:  # noqa: BLE001
            self._pending.pop(req_id, None)
            return {"success": False, "error": f"data-agent WS 发送失败: {exc}"}
        if not result.get("ok"):
            return {"success": False, "error": str(result.get("error") or "data-agent 返回失败")}
        data = result.get("data")
        return data if isinstance(data, dict) else {"success": True, "data": data}
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_data_agent_ws.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py finance-agents/browser-agent/tests/test_data_agent_ws.py
git commit -m "feat(browser-agent): DataAgentWsClient WS transport"
```

---

## Task 4: browser-agent 配置 + TallyClient 改用 WS 领域消息

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/tally_client.py`
- Test: `finance-agents/browser-agent/tests/test_tally_client.py`(改写)

- [ ] **Step 1: 改写测试(注入假 WS 客户端,断言领域消息)**

把 `tests/test_tally_client.py` 改为:
```python
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient


class FakeWsClient:
    def __init__(self):
        self.calls = []
        self.next_result = {"ok_marker": True}

    async def request(self, msg_type, payload):
        self.calls.append((msg_type, dict(payload)))
        return self.next_result


def _config():
    return BrowserAgentConfig(
        agent_id="agent-A", company_id="c1", data_agent_ws_url="ws://test/browser-agent",
        poll_interval_seconds=2, max_concurrency=2, waiting_poll_interval_seconds=30,
        heartbeat_interval_seconds=30,
    )


def _client():
    ws = FakeWsClient()
    return BrowserAgentTallyClient(config=_config(), ws_client=ws), ws


@pytest.mark.asyncio
async def test_claim_sends_domain_claim_without_tool_name():
    client, ws = _client()
    await client.claim_browser_job()
    assert ws.calls[0][0] == "claim"
    # 领域消息里不出现 MCP 工具名,也不带 worker_token(由 data-agent 注入)
    assert "worker_token" not in ws.calls[0][1]
    assert "browser_sync_job_claim" not in str(ws.calls[0])


@pytest.mark.asyncio
async def test_heartbeat_carries_token_and_capabilities():
    client, ws = _client()
    await client.heartbeat()
    msg_type, payload = ws.calls[0]
    assert msg_type == "heartbeat"
    assert payload["token"]  # 心跳带当前 token 供 data-agent 刷新
    assert payload["company_id"] == "c1"
    assert "capabilities" in payload


@pytest.mark.asyncio
async def test_complete_and_fail_and_queue_map_to_domain_types():
    client, ws = _client()
    await client.mark_browser_job_success({"sync_job_id": "j1", "records": []})
    await client.mark_browser_job_failed({"sync_job_id": "j1", "fail_reason": "X"})
    await client.requeue_ready_waiting()
    await client.fail_failed_waiting()
    await client.fail_expired_waiting()
    types = [c[0] for c in ws.calls]
    assert types == ["job_complete", "job_fail", "queue_requeue_ready", "queue_fail_failed", "queue_fail_expired"]
    assert ws.calls[0][1]["sync_job_id"] == "j1"  # payload 透传


def test_config_from_env_uses_data_agent_ws_url(monkeypatch):
    monkeypatch.setenv("DATA_AGENT_WS_URL", "wss://cloud/browser-agent")
    cfg = BrowserAgentConfig.from_env()
    assert cfg.data_agent_ws_url == "wss://cloud/browser-agent"
    assert not hasattr(cfg, "mcp_base_url")
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_tally_client.py -v`
Expected: FAIL（`BrowserAgentConfig` 无 `data_agent_ws_url` / `BrowserAgentTallyClient` 无 `ws_client` 参数)

- [ ] **Step 3: 改 tally_client.py**

(1) `BrowserAgentConfig`:把 `mcp_base_url` 字段与 `from_env` 里对应行替换为 `data_agent_ws_url`:
```python
@dataclass(frozen=True)
class BrowserAgentConfig:
    agent_id: str
    company_id: str
    data_agent_ws_url: str
    poll_interval_seconds: float
    max_concurrency: int
    waiting_poll_interval_seconds: float
    heartbeat_interval_seconds: float

    @classmethod
    def from_env(cls) -> "BrowserAgentConfig":
        hostname = socket.gethostname() or "local"
        return cls(
            agent_id=os.getenv("BROWSER_AGENT_ID", f"browser-agent-{hostname}"),
            company_id=os.getenv("BROWSER_AGENT_COMPANY_ID", "").strip(),
            data_agent_ws_url=os.getenv("DATA_AGENT_WS_URL", "ws://127.0.0.1:8100/browser-agent"),
            poll_interval_seconds=max(1.0, float(os.getenv("BROWSER_AGENT_POLL_INTERVAL_SECONDS", "2"))),
            max_concurrency=max(1, int(os.getenv("BROWSER_AGENT_MAX_CONCURRENCY", "2"))),
            waiting_poll_interval_seconds=max(5.0, float(os.getenv("BROWSER_AGENT_WAITING_POLL_INTERVAL_SECONDS", "30"))),
            heartbeat_interval_seconds=max(10.0, float(os.getenv("BROWSER_AGENT_HEARTBEAT_INTERVAL_SECONDS", "30"))),
        )
```
(2) import:把 `from finance_browser_agent.mcp_session import McpSession` 换成
`from finance_browser_agent.data_agent_ws import DataAgentWsClient`。
(3) `BrowserAgentTallyClient`:构造 WS 客户端并把 7 个方法改成领域消息:
```python
class BrowserAgentTallyClient:
    def __init__(self, *, config: BrowserAgentConfig, ws_client: "DataAgentWsClient | None" = None) -> None:
        self.config = config
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._client = ws_client or DataAgentWsClient(
            ws_url=config.data_agent_ws_url,
            agent_id=config.agent_id,
            max_concurrency=config.max_concurrency,
            token_provider=lambda: self.worker_token,
        )

    @property
    def worker_token(self) -> str:
        now_ts = datetime.now(timezone.utc).timestamp()
        if not self._token or now_ts >= self._token_expires_at - _TOKEN_REFRESH_LEAD_SECONDS:
            self._token = create_system_token(agent_id=self.config.agent_id)
            self._token_expires_at = (datetime.now(timezone.utc) + _TOKEN_LIFETIME).timestamp()
        return self._token

    async def claim_browser_job(self) -> dict[str, Any]:
        return await self._client.request("claim", {})

    async def heartbeat(self, *, company_id: str | None = None) -> dict[str, Any]:
        resolved_company_id = (company_id or self.config.company_id or "").strip()
        return await self._client.request("heartbeat", {
            "token": self.worker_token,
            "company_id": resolved_company_id,
            "hostname": socket.gethostname() or "",
            "version": os.getenv("BROWSER_AGENT_VERSION", ""),
            "capabilities": {
                "runner": os.getenv("BROWSER_AGENT_RUNNER_MODE", "playwright"),
                "browser_channel": os.getenv("BROWSER_AGENT_BROWSER_CHANNEL", "chrome"),
                "headless": os.getenv("BROWSER_AGENT_HEADLESS", "0"),
                "max_concurrency": self.config.max_concurrency,
            },
        })

    async def mark_browser_job_success(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._client.request("job_complete", dict(payload))

    async def mark_browser_job_failed(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._client.request("job_fail", dict(payload))

    async def requeue_ready_waiting(self) -> dict[str, Any]:
        return await self._client.request("queue_requeue_ready", {})

    async def fail_failed_waiting(self) -> dict[str, Any]:
        return await self._client.request("queue_fail_failed", {})

    async def fail_expired_waiting(self) -> dict[str, Any]:
        return await self._client.request("queue_fail_expired", {})
```
删掉旧的 `_call` 方法。模块顶部 docstring 里"MCP client"措辞可一并更新为"data-agent WS client"。

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_tally_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-agents/browser-agent/tests/test_tally_client.py
git commit -m "feat(browser-agent): TallyClient uses data-agent WS domain messages"
```

---

## Task 5: 收尾 — 停用旧 SSE 传输、配置、回归

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/mcp_session.py`(标注停用,或删除并清理引用)
- Modify: `.env.example` / `START_ALL_SERVICES.sh`(如含 browser-agent 环境)
- Test: 整体回归

- [ ] **Step 1: 确认 dispatcher_loop / service.py 无需改动**

Run: `grep -n "mcp_base_url\|McpSession\|FINANCE_MCP_BASE_URL\|_session" finance-agents/browser-agent/finance_browser_agent/service.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
Expected: 无输出（这两个文件不引用旧传输;仅通过 `BrowserAgentTallyClient` 间接使用)。若有输出,据上下文修正(只应保留构造 `BrowserAgentTallyClient(config=config)`)。

- [ ] **Step 2: 停用 mcp_session.py**

确认 `mcp_session.py` 已无生产引用:
Run: `grep -rn "mcp_session\|McpSession" finance-agents/browser-agent --include=*.py | grep -v __pycache__ | grep -v "def \|class "`
若仅剩自身定义 → 在 `mcp_session.py` 顶部 docstring 标注 `已于 WS 迁移后停用,保留备查;生产路径见 data_agent_ws.py`。不删除文件以免影响潜在引用。

- [ ] **Step 3: 配置项**

在 `.env.example`(若存在 browser-agent 段)新增 `DATA_AGENT_WS_URL=ws://127.0.0.1:8100/browser-agent`,移除/标注弃用 `FINANCE_MCP_BASE_URL`(browser-agent 不再需要)。若 `START_ALL_SERVICES.sh` 给 browser-agent 注入了 `FINANCE_MCP_BASE_URL`,改为注入 `DATA_AGENT_WS_URL`。
Run: `grep -n "FINANCE_MCP_BASE_URL\|DATA_AGENT_WS_URL\|browser-agent\|BROWSER_AGENT" START_ALL_SERVICES.sh`
据输出做最小修改(仅 browser-agent 启动段;data-agent/finance-mcp 的 FINANCE_MCP_BASE_URL 不动)。

- [ ] **Step 4: 全量回归**

Run:
```bash
cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_browser_agent_gateway.py tests/test_browser_agent_ws_endpoint.py -v
cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -v
```
Expected: 全绿;尤其 `test_dispatcher_loop.py` 无回归(证明 dispatcher 与新 client 接口兼容)。

- [ ] **Step 5: 确认 finance-mcp 未改动**

Run: `git status --porcelain finance-mcp`
Expected: 无输出（本计划不触碰 finance-mcp;7 个工具保持原样,只是改由 data-agent 调用)。

- [ ] **Step 6: Commit**

```bash
git add finance-agents/browser-agent/finance_browser_agent/mcp_session.py .env.example START_ALL_SERVICES.sh
git commit -m "chore(browser-agent): retire direct MCP SSE transport; switch env to DATA_AGENT_WS_URL"
```

---

## 收尾(全部任务完成后)

- 真机/联调留待后续:本机起 finance-mcp + data-agent,设 `DATA_AGENT_WS_URL=ws://127.0.0.1:8100/browser-agent` 跑 browser-agent,确认 claim→执行→complete 全链路经 data-agent 中转;dev/生产入口需放行 WS Upgrade(WSS)。
- 不在本轮:handoff 的 `event`/截图双工帧(设计文档阶段 2 起);finance-mcp 工具改动;dispatcher_loop 行为改动。
- 部署收益:迁移后 finance-mcp(:3335)无需对外暴露,内网采集机只连 data-agent 的公网 WSS 入口。
