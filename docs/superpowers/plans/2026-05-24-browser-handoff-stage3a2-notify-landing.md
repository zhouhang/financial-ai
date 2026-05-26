# 阶段3a-2:风控上报 → 通知责任人 → 落地页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通"风控→通知责任人→就地处理"的闭环:browser-agent 进入风控等待时经 WS 上报 `risk_waiting`;data-agent 据此(经 finance-mcp)创建 handoff session,经**公司默认通知通道(钉钉/飞书/企微)**给责任人发含一次性链接的消息;责任人打开链接看到最小落地页(店铺/验证原因/采集机/状态),用自己对采集机的权限就地完成验证(阶段2 已让该机 Chrome 保持打开等待)。

**Architecture:** 复用阶段0 的 WS 领域消息(请求/响应)新增 `risk_waiting` 类型(agent→data-agent,不映射 MCP 工具,由 gateway 编排:调 3a-1 的 `browser_handoff_session_create` 拿一次性 token → 解析默认通道 → `get_notification_adapter` + `send_bot_message` 发链接;按 sync_job_id 进程内幂等)。runner 在风控等待入口经线程安全回调(`run_coroutine_threadsafe`)触发 agent 上报。落地页 `/p/handoff` 照搬已建的 `/p/alipay-auth`(`_invite_html`/`_logo_data_uri`),调 `browser_handoff_session_describe` 渲染。**不含实时远程接管(截图/输入)——那是阶段3b/4。**

**Tech Stack:** Python 3.12;asyncio(跨线程 `run_coroutine_threadsafe`);WebSocket;FastAPI HTMLResponse;复用已建的钉钉/飞书/企微通知适配器 + 3a-1 的 handoff 工具/token。

---

## 依赖与复用(已就位)
- 3a-1:MCP 工具 `browser_handoff_session_create`(返回 `handoff_token`)/ `browser_handoff_session_describe`(按 token 返回脱敏 session);一次性 token。
- 阶段0:`DataAgentWsClient`(`request(type,payload)` 请求/响应)、data-agent `services/browser_agent_gateway.py`(`handle_domain_message`)、`/browser-agent` WS 端点。
- 阶段2:runner 三处风控等待入口(login ~445-469 / post-login / navigate `_await_navigate_risk_clearance`),都打了 `... risk verification waiting for manual completion ...` 日志。
- 通知:data-agent `services/notifications` 的 `get_notification_adapter` + `load_company_channel_config(company_id=..., is_default 优先)` + 适配器 `send_bot_message`。
- 落地页范式:`graphs/platform/api.py` 的 `_invite_html`(751)/`_logo_data_uri`(731)/`@router.get("/p/alipay-auth")`(805);链接前缀 env `TALLY_PUBLIC_BASE_URL`。

## 决定的设计点
- **agent→cloud 信号**:WS 领域消息 `risk_waiting`(不是心跳搭车),由 runner 在风控等待入口经回调触发。
- **通道解析**:公司默认通道(`load_company_channel_config` is_default 优先)。按对账任务精确选通道留作后续(MVP 单公司默认通道即责任人)。
- **幂等**:gateway 进程内维护已通知的 `sync_job_id` 集合,重复 `risk_waiting` 不重复建会话/通知。
- **链接**:`{TALLY_PUBLIC_BASE_URL}/p/handoff?t=<handoff_token>`。

## 文件结构
- Modify `finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py` — `report_risk_waiting(...)`。
- Modify `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py` — 捕获 loop + 构造线程安全回调,传入 runner。
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py` — `run_playbook_with_playwright` 接 `on_risk_waiting` 回调,在三处等待入口调用。
- Modify `finance-agents/data-agent/services/browser_agent_gateway.py` — `risk_waiting` 分支:建 session + 通知责任人 + 幂等。
- Modify `finance-agents/data-agent/graphs/platform/api.py` — `GET /p/handoff` 落地页。
- Tests:browser-agent + data-agent 各自测试文件。

---

## Task 1: agent 上报 risk_waiting(WS + runner 回调)

**Files:**
- Modify: `finance_browser_agent/data_agent_ws.py`、`dispatcher_loop.py`、`playwright_runner.py`
- Test: `finance-agents/browser-agent/tests/test_risk_waiting_report.py`

- [ ] **Step 1: 写失败测试**(`DataAgentWsClient.report_risk_waiting` 发出 `risk_waiting` 帧;runner 在等待入口回调):
```python
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
    assert res.get("handoff_session_id")=="h1" or res.get("success") is not False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_risk_waiting_report.py -v`

- [ ] **Step 3: 实现**
(a) `data_agent_ws.py` 加方法:
```python
    async def report_risk_waiting(self, *, sync_job_id: str, reason: str, company_id: str = "",
                                  shop_id: str = "", data_source_id: str = "") -> dict:
        return await self.request("risk_waiting", {
            "sync_job_id": sync_job_id, "reason": reason, "company_id": company_id,
            "shop_id": shop_id, "data_source_id": data_source_id,
        })
```
(b) `dispatcher_loop.py`:在 `_process_job` 里、调用 runner 之前,捕获事件循环并构造**闭包了 `job` 的**线程安全回调(company_id/data_source_id/sync_job_id/shop_id 由 dispatcher 从 enriched job 填,runner 只需传 reason),注入 message:
```python
        loop = asyncio.get_running_loop()
        def _on_risk_waiting(reason: str = "RISK_VERIFICATION") -> None:
            # runner 在工作线程里调用;dispatcher 闭包 job 拿齐归属字段,调度回事件循环发 WS
            try:
                asyncio.run_coroutine_threadsafe(
                    self.client.report_risk_waiting(
                        sync_job_id=str(job.get("id") or ""),
                        reason=str(reason or "RISK_VERIFICATION"),
                        company_id=str(job.get("company_id") or ""),
                        shop_id=str(job.get("shop_id") or ""),
                        data_source_id=str(job.get("data_source_id") or ""),
                    ),
                    loop,
                )
            except Exception:
                logger.exception("report_risk_waiting 调度失败")
        message = self._message_from_job(job, payload)
        message["on_risk_waiting"] = _on_risk_waiting
```
说明:① 给 `BrowserAgentTallyClient` 加透传 `async def report_risk_waiting(self, **kw): return await self._client.report_risk_waiting(**kw)`(回调调的是 `self.client`,即 TallyClient)。② **实现前确认 enriched claim job 带 `company_id`/`data_source_id`**(claim 的 binding JOIN 应已带;若没有,在 `_message_from_job`/claim 补,或 gateway 侧按 sync_job 兜底)。
(c) `playwright_runner.py`:三处风控等待入口在不同的**模块级函数**里(`_await_navigate_risk_clearance`、login/post-login 等待),回调无法用局部变量传到位。用一个 **ContextVar** 在单次 run 内传递(runner 单线程,ContextVar 跨调用栈安全):
```python
import contextvars
_risk_waiting_cb: contextvars.ContextVar = contextvars.ContextVar("risk_waiting_cb", default=None)


def _notify_risk_waiting() -> None:
    cb = _risk_waiting_cb.get()
    if cb:
        try:
            cb("RISK_VERIFICATION")
        except Exception:
            logger.exception("on_risk_waiting 回调失败")
```
- `run_playbook_with_playwright` 开头:`token = _risk_waiting_cb.set(message.get("on_risk_waiting")); try: ... finally: _risk_waiting_cb.reset(token)`(包住整个执行体)。
- 在**三处** `... risk verification waiting for manual completion ...` 日志旁各加一行 `_notify_risk_waiting()`。
(回调失败不影响等待;三处都调,gateway 按 sync_job_id 幂等去重,只通知一次。)

- [ ] **Step 4: 运行确认通过;Step 5: 全量 browser-agent 回归**(`pytest tests/ -q`,确认 dispatcher/runner 现有测试无回归)。
- [ ] **Step 6: Commit**
```bash
git add finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-agents/browser-agent/finance_browser_agent/playwright_runner.py
git add -f finance-agents/browser-agent/tests/test_risk_waiting_report.py
git commit -m "feat(handoff): agent reports risk_waiting over WS at risk-wait entry"
```

---

## Task 2: data-agent 处理 risk_waiting → 建 session + 通知责任人

**Files:**
- Modify: `finance-agents/data-agent/services/browser_agent_gateway.py`
- Test: `finance-agents/data-agent/tests/test_gateway_risk_waiting.py`

- [ ] **Step 1: 写失败测试**(mock `call_mcp_tool` + 通知适配器,断言:建 session、解析默认通道、发含链接消息、幂等):
```python
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
            calls["notify"].append(content); 
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

    # 幂等:同一 sync_job 再来一次,不重复建/通知
    r2=asyncio.run(gw.handle_domain_message(conn, {"type":"risk_waiting","id":"e2",
        "sync_job_id":"j1","reason":"RISK_VERIFICATION","company_id":"c1","shop_id":"s1"}))
    assert r2["ok"] is True and calls["create"]==1 and len(calls["notify"])==1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_gateway_risk_waiting.py -v`

- [ ] **Step 3: 实现**(`services/browser_agent_gateway.py`):
顶部加 import:
```python
import os
from services.notifications import get_notification_adapter, load_company_channel_config
```
模块级幂等集合(进程内):
```python
_NOTIFIED_RISK_JOBS: set[str] = set()
```
在 `handle_domain_message` 开头(`_DOMAIN_TOOL_MAP` 查表之前)加 `risk_waiting` 特例分支:
```python
    if msg_type == "risk_waiting":
        return await _handle_risk_waiting(conn, msg)
```
新增编排函数:
```python
async def _handle_risk_waiting(conn: "BrowserAgentConnection", msg: dict) -> dict:
    req_id = str(msg.get("id") or "")
    sync_job_id = str(msg.get("sync_job_id") or "")
    company_id = str(msg.get("company_id") or "")
    if not sync_job_id or not company_id:
        return {"type": "result", "id": req_id, "ok": False, "error": "risk_waiting 缺 sync_job_id/company_id"}
    if sync_job_id in _NOTIFIED_RISK_JOBS:
        return {"type": "result", "id": req_id, "ok": True, "data": {"deduped": True}}
    # 解析公司默认通道
    channel = load_company_channel_config(company_id=company_id)  # is_default 优先
    channel_id = getattr(channel, "id", None) if channel else None
    created = await call_mcp_tool("browser_handoff_session_create", {
        "worker_token": conn.token, "company_id": company_id, "sync_job_id": sync_job_id,
        "agent_id": conn.agent_id, "profile_key": str(msg.get("shop_id") or ""),
        "reason": str(msg.get("reason") or "RISK_VERIFICATION"),
        "data_source_id": (msg.get("data_source_id") or None),
        "channel_config_id": channel_id,
    })
    if not created.get("success"):
        return {"type": "result", "id": req_id, "ok": False, "error": str(created.get("error") or "create session failed")}
    token = created.get("handoff_token") or ""
    base = os.getenv("TALLY_PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base}/p/handoff?t={token}" if base else f"/p/handoff?t={token}"
    if channel is not None:
        try:
            adapter = get_notification_adapter(provider=getattr(channel, "provider", ""), channel_config=channel)
            adapter.send_bot_message(
                content=f"采集店铺需要人工验证({msg.get('reason') or 'RISK_VERIFICATION'})。请在采集机上完成验证,或查看详情:{link}",
                to_user_id="",
            )
        except Exception:
            logger.exception("handoff 通知发送失败 sync_job_id=%s", sync_job_id)
    _NOTIFIED_RISK_JOBS.add(sync_job_id)
    return {"type": "result", "id": req_id, "ok": True,
            "data": {"handoff_session_id": created.get("handoff_session_id"), "notified": channel is not None}}
```
(`logger` 在 gateway 文件已 import;若没有则 `import logging; logger=logging.getLogger(__name__)`。)

- [ ] **Step 4: 运行确认通过(含幂等用例);Step 5: Commit**
```bash
git add finance-agents/data-agent/services/browser_agent_gateway.py
git add -f finance-agents/data-agent/tests/test_gateway_risk_waiting.py
git commit -m "feat(handoff): data-agent risk_waiting -> create session + notify responsible person"
```

---

## Task 3: /p/handoff 落地页

**Files:**
- Modify: `finance-agents/data-agent/graphs/platform/api.py`(照搬 `/p/alipay-auth` 结构)
- Test: `finance-agents/data-agent/tests/test_handoff_landing.py`

- [ ] **Step 1: 写失败测试**(TestClient GET /p/handoff;mock describe):
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# 与现有 endpoint 测试一致:import server 前 mock 缺失重依赖(见 test_browser_agent_ws_endpoint.py 的写法)
import importlib, types
for _m in ["langgraph.checkpoint.postgres","langgraph.checkpoint.postgres.aio","psycopg","psycopg.conninfo","psycopg.sql"]:
    sys.modules.setdefault(_m, types.ModuleType(_m))
from unittest.mock import MagicMock
for _m in ["langgraph.checkpoint.postgres","langgraph.checkpoint.postgres.aio","psycopg","psycopg.conninfo","psycopg.sql"]:
    sys.modules[_m]=MagicMock()
from fastapi.testclient import TestClient
import server
from graphs.platform import api as platform_api


def test_handoff_landing_renders(monkeypatch):
    async def fake_describe(token):
        return {"success": True, "session": {"status":"pending","reason":"RISK_VERIFICATION",
                "agent_id":"browser-agent-local","profile_key":"单枪旗舰店","expires_at":"2026-05-24 22:00:00"}}
    monkeypatch.setattr(platform_api, "browser_handoff_session_describe", fake_describe, raising=False)
    client=TestClient(server.app)
    r=client.get("/p/handoff?t=sometoken")
    assert r.status_code==200
    assert "单枪旗舰店" in r.text and "人工验证" in r.text


def test_handoff_landing_invalid_token(monkeypatch):
    async def fake_describe(token):
        return {"success": False, "error": "链接无效或已过期"}
    monkeypatch.setattr(platform_api, "browser_handoff_session_describe", fake_describe, raising=False)
    client=TestClient(server.app)
    r=client.get("/p/handoff?t=bad")
    assert r.status_code in (200,400) and ("失效" in r.text or "无效" in r.text)
```

- [ ] **Step 2: 运行确认失败**(无 /p/handoff 路由)

Run: `cd finance-agents/data-agent && ./.venv/bin/python -m pytest tests/test_handoff_landing.py -v`

- [ ] **Step 3: 实现**:
(a) data-agent 的 mcp_client 加 wrapper(若无):`async def browser_handoff_session_describe(token): return await call_mcp_tool("browser_handoff_session_describe", {"token": token})`;在 `graphs/platform/api.py` 从 mcp_client 导入它。
(b) 在 `api.py` `/p/alipay-auth` 路由之后,加:
```python
@router.get("/p/handoff", response_class=HTMLResponse)
async def handoff_landing(t: str = Query("", description="handoff token")):
    import html as _html
    info = await browser_handoff_session_describe(t)
    if not info.get("success"):
        inner = ("<div class='status err'><div class='ic'>!</div><div class='t'>链接无效或已过期</div></div>"
                 "<p class='desc'>该验证链接无法使用,可能已过期或被改动。请联系对接人重新触发。</p>")
        return HTMLResponse(_invite_html(title="链接已失效", inner=inner), status_code=400)
    s = info.get("session") or {}
    shop = _html.escape(str(s.get("profile_key") or ""))
    reason = _html.escape(str(s.get("reason") or ""))
    agent = _html.escape(str(s.get("agent_id") or ""))
    status = _html.escape(str(s.get("status") or ""))
    inner = (
        "<p class='eyebrow'>该采集店铺需要人工验证</p>"
        f"<p class='shop'>{shop}</p>"
        f"<div class='hint'>验证类型: <b>{reason}</b> · 采集机: {agent} · 状态: {status}</div>"
        "<p class='desc'>请在该采集机上打开的浏览器窗口中完成验证(滑块/手机验证码等);"
        "采集任务正保持会话等待,完成后会自动继续并下载数据。本页暂不支持远程操作。</p>"
    )
    return HTMLResponse(_invite_html(title="人工验证", inner=inner))
```

- [ ] **Step 4: 运行确认通过;Step 5: Commit**
```bash
git add finance-agents/data-agent/graphs/platform/api.py finance-agents/data-agent/tools/mcp_client.py
git add -f finance-agents/data-agent/tests/test_handoff_landing.py
git commit -m "feat(handoff): /p/handoff landing page (describe by token, Tally-styled)"
```

---

## Task 4: 联调验证(真机/本地)
- [ ] 重启 finance-mcp + data-agent(+ browser-agent 自动用新代码)。
- [ ] 触发一次会进风控的采集(或用 3a-1 探针式手段):确认链路 runner 上报 `risk_waiting` → data-agent 建 session → 默认通道收到含 `/p/handoff?t=` 的消息 → 打开链接看到店铺/验证类型/采集机/状态;责任人就地完成验证后,阶段2 的等待循环检测到登录态恢复 → 续跑。
- [ ] 确认幂等:同一风控等待期间不重复轰炸通知。

## 收尾(完成后)
- 3a-2 交付"风控→通知责任人→就地处理→续跑"闭环(责任人用对采集机的访问权就地处理)。
- 远程实时接管(责任人在链接里直接看画面+操作)= 阶段3b(WS 截图/输入双工)+ 阶段4(finance-web 接管页),其中滑块输入 Playwright-vs-OS 分叉待真机定。
- 通道精确化(按对账任务而非公司默认)留作后续小迭代。
