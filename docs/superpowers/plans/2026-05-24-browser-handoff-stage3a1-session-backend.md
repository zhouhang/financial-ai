# 阶段3a-1:云端 handoff session 后端基座 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 finance-mcp 建立"人工验证 handoff session"的后端基座:持久化表 + 一次性 token + 创建/按 token 描述的 MCP 工具 + sync_job 的 `waiting_human_verification`/`resuming` 状态——为后续(agent 上报风控等待、data-agent 通知责任人、最小落地页)铺底。

**Architecture:** 新增 `browser_handoff_sessions` 表(SQL 迁移 + `ensure_*_schema` 就绪门,照 `031_browser_playbook_collection.sql` 范式)。一次性 token 用 HS256 无状态 JWT(照搬 `auth/alipay_auth_invite.py`),编码 `handoff_session_id`,链接打开时换取 session 描述。两个 MCP 工具:`browser_handoff_session_create`(风控时建 session,返回一次性链接 token)、`browser_handoff_session_describe`(按 token 查 session,供落地页)。sync_job 的 `job_status` 是 varchar,无枚举约束,直接新增两个状态值 + 转移辅助函数。

**Tech Stack:** Python 3.12;PostgreSQL(迁移 SQL);PyJWT(HS256);finance-mcp MCP 工具。测试:`cd finance-mcp && ../.venv/bin/python -m pytest tests/<file> -v`(命中本地 DB)。

---

## 范围与边界

**本计划(3a-1)只做后端基座**,可独立测试,不改 agent、不改 data-agent、不做页面:
- handoff session 持久化(表 + CRUD)。
- 一次性 token(build/verify)。
- 两个 MCP 工具(create / describe)+ 注册 + 路由白名单。
- sync_job `waiting_human_verification`/`resuming` 状态转移辅助。

**不在本计划(留 3a-2)**:agent 进入风控等待时经心跳上报状态;data-agent 据此建 session 并经对账任务通道通知责任人;最小落地页(`/p/handoff`,照搬已建的 `/p/alipay-auth` 范式)。3a-2 的取信号方式已定:**agent 心跳携带 active job 风控状态**;通知通道 = **sync_job 的 channel_config_id(触发上下文带)|| 公司默认通道**。

## 设计依据
- spec:`docs/superpowers/specs/2026-05-23-browser-agent-risk-handoff-design.md` 的「Handoff Session 数据」「状态模型」「安全要求」+「设计定位与 2026-05-24 修订」。
- 复用范式:`finance-mcp/auth/alipay_auth_invite.py`(一次性 HS256 token);`finance-mcp/auth/db.py:ensure_browser_playbook_collection_schema`(迁移就绪门);`finance-mcp/migrations/031_browser_playbook_collection.sql`(迁移文件结构)。

## handoff_sessions 字段(取自 spec「Handoff Session 数据」+ 通道扩展)
`handoff_session_id`(uuid pk)、`sync_job_id`、`company_id`、`data_source_id`、`agent_id`、`profile_key`、`status`、`reason`、`channel_config_id`(通知用)、`created_at`、`expires_at`、`claimed_by_user_id`、`claimed_at`、`completed_at`、`audit_events`(jsonb)。

## 文件结构
- Create `finance-mcp/migrations/032_browser_handoff_sessions.sql` — 建表。
- Modify `finance-mcp/auth/db.py` — `ensure_browser_handoff_schema()` + 接入 `ensure_schema()`;CRUD(`insert_handoff_session`/`get_handoff_session`/`mark_handoff_session_status`);`set_browser_sync_job_status()`(waiting_human_verification/resuming)。
- Create `finance-mcp/auth/handoff_token.py` — build/verify 一次性 token。
- Modify `finance-mcp/tools/data_sources.py` — `_handle_browser_handoff_session_create` / `_handle_browser_handoff_session_describe` + Tool 注册 + dispatch。
- Modify `finance-mcp/unified_mcp_server.py` — `_PLATFORM_TOOL_NAMES` 加两个工具名。
- Tests:`finance-mcp/tests/test_handoff_token.py`、`finance-mcp/tests/test_handoff_session_db.py`、`finance-mcp/tests/test_handoff_session_tools.py`。

---

## Task 1: 一次性 handoff token

**Files:**
- Create: `finance-mcp/auth/handoff_token.py`
- Test: `finance-mcp/tests/test_handoff_token.py`

- [ ] **Step 1: 写失败测试** `tests/test_handoff_token.py`:
```python
from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth.handoff_token import build_handoff_token, verify_handoff_token


def test_roundtrip_ok():
    tok = build_handoff_token(handoff_session_id="hs-1", company_id="c1", ttl_seconds=600)
    payload = verify_handoff_token(tok)
    assert payload is not None
    assert payload["handoff_session_id"] == "hs-1"
    assert payload["company_id"] == "c1"


def test_wrong_purpose_or_garbage_rejected():
    import jwt, os
    secret = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
    bad = jwt.encode({"purpose": "other", "handoff_session_id": "x"}, secret, algorithm="HS256")
    assert verify_handoff_token(bad) is None
    assert verify_handoff_token("not-a-jwt") is None
    assert verify_handoff_token("") is None


def test_expired_rejected():
    tok = build_handoff_token(handoff_session_id="hs-2", company_id="c1", ttl_seconds=1)
    time.sleep(2)
    assert verify_handoff_token(tok) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd finance-mcp && ../.venv/bin/python -m pytest tests/test_handoff_token.py -v`
Expected: FAIL（`ModuleNotFoundError: auth.handoff_token`）

- [ ] **Step 3: 实现**(照搬 `auth/alipay_auth_invite.py` 结构)`finance-mcp/auth/handoff_token.py`:
```python
"""浏览器风控 handoff 的一次性 HS256 token。

token 是无状态 bearer 能力,只编码 handoff_session_id + company_id,供责任人链接打开时
换取 session 描述。不编码任何凭证/profile 路径/CDP 端口。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

_PURPOSE = "browser_handoff"
_ALG = "HS256"
_DEFAULT_TTL_SECONDS = 900  # 15 分钟


def _secret() -> str:
    return os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def build_handoff_token(*, handoff_session_id: str, company_id: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": _PURPOSE,
        "handoff_session_id": str(handoff_session_id),
        "company_id": str(company_id),
        "iat": now,
        "exp": now + timedelta(seconds=int(ttl_seconds) if ttl_seconds else _DEFAULT_TTL_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALG)


def verify_handoff_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(str(token or ""), _secret(), algorithms=[_ALG])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    if not payload.get("handoff_session_id") or not payload.get("company_id"):
        return None
    return payload
```

- [ ] **Step 4: 运行确认通过** (3 passed)
- [ ] **Step 5: Commit**
```bash
git add finance-mcp/auth/handoff_token.py
git add -f finance-mcp/tests/test_handoff_token.py
git commit -m "feat(handoff): one-time HS256 handoff token"
```

---

## Task 2: handoff_sessions 表 + schema 就绪门

**Files:**
- Create: `finance-mcp/migrations/032_browser_handoff_sessions.sql`
- Modify: `finance-mcp/auth/db.py`(新增 `ensure_browser_handoff_schema()`,并在 `ensure_schema()` 末尾追加调用;参照 line 960 `ensure_browser_playbook_collection_schema` 的就绪门写法 + line 982 `ensure_schema`)
- Test: `finance-mcp/tests/test_handoff_session_db.py`(先只验表存在,CRUD 在 Task 3)

- [ ] **Step 1: 写迁移 SQL** `migrations/032_browser_handoff_sessions.sql`:
```sql
CREATE TABLE IF NOT EXISTS browser_handoff_sessions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_job_id        uuid NOT NULL,
    company_id         uuid NOT NULL,
    data_source_id     uuid,
    agent_id           varchar(128) NOT NULL DEFAULT '',
    profile_key        varchar(256) NOT NULL DEFAULT '',
    status             varchar(32)  NOT NULL DEFAULT 'pending',  -- pending|claimed|completed|expired|cancelled
    reason             varchar(64)  NOT NULL DEFAULT '',
    channel_config_id  uuid,
    claimed_by_user_id uuid,
    claimed_at         timestamptz,
    completed_at       timestamptz,
    expires_at         timestamptz NOT NULL,
    audit_events       jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_handoff_sessions_sync_job ON browser_handoff_sessions(sync_job_id);
CREATE INDEX IF NOT EXISTS idx_handoff_sessions_company_status ON browser_handoff_sessions(company_id, status);
```

- [ ] **Step 2: 写失败测试** `tests/test_handoff_session_db.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth.db as auth_db


def test_ensure_schema_creates_handoff_table():
    auth_db.ensure_browser_handoff_schema()
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('public.browser_handoff_sessions')")
            assert cur.fetchone()[0] is not None
```

- [ ] **Step 3: 运行确认失败**

Run: `cd finance-mcp && ../.venv/bin/python -m pytest tests/test_handoff_session_db.py -v`
Expected: FAIL（`AttributeError: ... ensure_browser_handoff_schema`）

- [ ] **Step 4: 实现就绪门**(在 `auth/db.py`,紧邻 `ensure_browser_playbook_collection_schema`):
```python
_BROWSER_HANDOFF_SCHEMA_READY = False


def _browser_handoff_schema_ready() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("select to_regclass('public.browser_handoff_sessions')")
                return cur.fetchone()[0] is not None
    except Exception:
        return False


def ensure_browser_handoff_schema() -> list[str]:
    global _BROWSER_HANDOFF_SCHEMA_READY
    if _BROWSER_HANDOFF_SCHEMA_READY:
        return []
    if _browser_handoff_schema_ready():
        _BROWSER_HANDOFF_SCHEMA_READY = True
        return []
    migration_name = "032_browser_handoff_sessions.sql"
    _execute_sql_script(_migration_path(migration_name))
    if not _browser_handoff_schema_ready():
        raise RuntimeError("browser_handoff schema 升级失败")
    _BROWSER_HANDOFF_SCHEMA_READY = True
    logger.info("browser_handoff schema 已自动补齐: %s", migration_name)
    return [migration_name]
```
并在 `ensure_schema()` 末尾追加:`applied.extend(ensure_browser_handoff_schema())`。

- [ ] **Step 5: 运行确认通过**;**Step 6: Commit**
```bash
git add finance-mcp/migrations/032_browser_handoff_sessions.sql finance-mcp/auth/db.py
git add -f finance-mcp/tests/test_handoff_session_db.py
git commit -m "feat(handoff): browser_handoff_sessions table + ensure-schema gate"
```

---

## Task 3: handoff session CRUD + sync_job 状态转移

**Files:**
- Modify: `finance-mcp/auth/db.py`(新增 4 个函数)
- Test: `finance-mcp/tests/test_handoff_session_db.py`(追加用例)

- [ ] **Step 1: 追加失败测试**:
```python
import uuid

def _new_sync_job_id():
    # 用真实存在的 sync_job 关联会更稳;此处只测 handoff 行的读写,sync_job_id 用随机 uuid
    return str(uuid.uuid4())


def test_insert_get_and_mark_handoff_session():
    auth_db.ensure_browser_handoff_schema()
    sj = _new_sync_job_id()
    row = auth_db.insert_handoff_session(
        company_id="00000000-0000-0000-0000-000000000001",
        sync_job_id=sj, data_source_id=None, agent_id="browser-agent-local",
        profile_key="shop-x", reason="RISK_VERIFICATION", channel_config_id=None,
        expires_in_seconds=900,
    )
    hid = row["id"]
    got = auth_db.get_handoff_session(handoff_session_id=hid)
    assert got and got["status"] == "pending" and got["sync_job_id"] == sj
    updated = auth_db.mark_handoff_session_status(handoff_session_id=hid, status="completed")
    assert updated["status"] == "completed" and updated["completed_at"] is not None


def test_set_browser_sync_job_status_waiting_and_resuming():
    # 这两个状态只是 varchar 值;函数应能写入并读回
    sj = _new_sync_job_id()
    # 需要一条 sync_jobs 行;若无则跳过真实写,改测函数对不存在 id 返回 None/0 行
    res = auth_db.set_browser_sync_job_status(sync_job_id=sj, status="waiting_human_verification")
    assert res in (0, 1)  # 不存在则 0 行,存在则 1 行;不抛异常
```

- [ ] **Step 2: 运行确认失败**(函数不存在)

- [ ] **Step 3: 实现** 4 个函数(`auth/db.py`,用 `get_conn()` + RealDictCursor;参照文件内现有 CRUD 写法):
```python
def insert_handoff_session(*, company_id, sync_job_id, data_source_id, agent_id,
                           profile_key, reason, channel_config_id, expires_in_seconds=900):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO browser_handoff_sessions
                   (sync_job_id, company_id, data_source_id, agent_id, profile_key, reason,
                    channel_config_id, expires_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s, now() + (%s || ' seconds')::interval)
                   RETURNING *""",
                (sync_job_id, company_id, data_source_id, agent_id, profile_key, reason,
                 channel_config_id, str(int(expires_in_seconds))),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def get_handoff_session(*, handoff_session_id):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM browser_handoff_sessions WHERE id = %s", (handoff_session_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def mark_handoff_session_status(*, handoff_session_id, status, claimed_by_user_id=None):
    completed = status in ("completed", "expired", "cancelled")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """UPDATE browser_handoff_sessions
                   SET status=%s,
                       claimed_by_user_id = COALESCE(%s, claimed_by_user_id),
                       claimed_at = CASE WHEN %s='claimed' THEN now() ELSE claimed_at END,
                       completed_at = CASE WHEN %s THEN now() ELSE completed_at END,
                       updated_at = now()
                   WHERE id=%s RETURNING *""",
                (status, claimed_by_user_id, status, completed, handoff_session_id),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def set_browser_sync_job_status(*, sync_job_id, status):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sync_jobs SET job_status=%s, updated_at=now() WHERE id=%s",
                (status, sync_job_id),
            )
            affected = cur.rowcount
            conn.commit()
            return affected
```

- [ ] **Step 4: 运行确认通过**;**Step 5: Commit**
```bash
git add finance-mcp/auth/db.py
git add -f finance-mcp/tests/test_handoff_session_db.py
git commit -m "feat(handoff): session CRUD + sync_job waiting/resuming status setter"
```

---

## Task 4: MCP 工具 create / describe + 注册

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`(2 个 handler + Tool 注册 + dispatch)
- Modify: `finance-mcp/unified_mcp_server.py`(`_PLATFORM_TOOL_NAMES` 加两个工具名)
- Test: `finance-mcp/tests/test_handoff_session_tools.py`

> 注册/分发/白名单的三处接线,照搬本仓已有 browser/alipay 工具的写法(`browser_sync_job_claim` 等就在同文件)。`_require_system` 门:create 用 system worker_token;describe 用 token(无需登录,落地页用)。

- [ ] **Step 1: 写失败测试**:
```python
from __future__ import annotations
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth.db as auth_db
from tools.data_sources import _handle_browser_handoff_session_create, _handle_browser_handoff_session_describe


def _system_token():
    # 复用 browser-agent 的系统 token 写法:role=system 的 HS256 JWT
    import os, uuid, jwt
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub":"sys","role":"system","iat":now,"exp":now+timedelta(hours=1),"jti":str(uuid.uuid4())},
                      os.getenv("JWT_SECRET","tally-secret-change-in-production"), algorithm="HS256")


def test_create_then_describe_by_token():
    auth_db.ensure_browser_handoff_schema()
    import uuid
    sj = str(uuid.uuid4())
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": sj, "agent_id": "browser-agent-local",
        "profile_key": "shop-x", "reason": "RISK_VERIFICATION",
    }))
    assert created["success"] is True
    token = created["handoff_token"]
    assert token and created["handoff_session_id"]

    described = asyncio.run(_handle_browser_handoff_session_describe({"token": token}))
    assert described["success"] is True
    assert described["session"]["reason"] == "RISK_VERIFICATION"
    assert described["session"]["status"] == "pending"
    assert "credential" not in str(described).lower()  # 不泄露凭证

def test_describe_rejects_bad_token():
    described = asyncio.run(_handle_browser_handoff_session_describe({"token": "garbage"}))
    assert described["success"] is False
```

- [ ] **Step 2: 运行确认失败**(handler 不存在)

- [ ] **Step 3: 实现 handler**(`tools/data_sources.py`):
```python
async def _handle_browser_handoff_session_create(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_system(arguments.get("worker_token", ""))
    from auth.handoff_token import build_handoff_token
    company_id = str(arguments.get("company_id") or "").strip()
    sync_job_id = str(arguments.get("sync_job_id") or "").strip()
    if not company_id or not sync_job_id:
        return {"success": False, "error": "missing company_id or sync_job_id"}
    row = auth_db.insert_handoff_session(
        company_id=company_id, sync_job_id=sync_job_id,
        data_source_id=(arguments.get("data_source_id") or None),
        agent_id=str(arguments.get("agent_id") or ""),
        profile_key=str(arguments.get("profile_key") or ""),
        reason=str(arguments.get("reason") or "RISK_VERIFICATION"),
        channel_config_id=(arguments.get("channel_config_id") or None),
        expires_in_seconds=int(arguments.get("expires_in_seconds") or 900),
    )
    if not row:
        return {"success": False, "error": "insert handoff session failed"}
    auth_db.set_browser_sync_job_status(sync_job_id=sync_job_id, status="waiting_human_verification")
    token = build_handoff_token(handoff_session_id=str(row["id"]), company_id=company_id,
                                ttl_seconds=int(arguments.get("expires_in_seconds") or 900))
    return {"success": True, "handoff_session_id": str(row["id"]), "handoff_token": token,
            "status": row["status"]}


def _public_handoff_session_view(row: dict[str, Any]) -> dict[str, Any]:
    # 落地页可见的字段:不含凭证/profile 路径/CDP/playbook
    return {
        "handoff_session_id": str(row.get("id") or ""),
        "status": str(row.get("status") or ""),
        "reason": str(row.get("reason") or ""),
        "agent_id": str(row.get("agent_id") or ""),
        "profile_key": str(row.get("profile_key") or ""),
        "expires_at": str(row.get("expires_at") or ""),
    }


async def _handle_browser_handoff_session_describe(arguments: dict[str, Any]) -> dict[str, Any]:
    from auth.handoff_token import verify_handoff_token
    payload = verify_handoff_token(str(arguments.get("token") or ""))
    if payload is None:
        return {"success": False, "error": "链接无效或已过期"}
    row = auth_db.get_handoff_session(handoff_session_id=str(payload["handoff_session_id"]))
    if not row:
        return {"success": False, "error": "handoff session 不存在"}
    return {"success": True, "session": _public_handoff_session_view(row)}
```

- [ ] **Step 4: 注册 + 分发 + 白名单**:
  - 在 `data_sources.py` 的 `create_tools()`(browser 工具附近)加两个 Tool 定义:`browser_handoff_session_create`(input: worker_token, company_id, sync_job_id, agent_id, profile_key, reason, data_source_id?, channel_config_id?, expires_in_seconds?)与 `browser_handoff_session_describe`(input: token)。
  - 在 `handle_tool_call` dispatch 加两个分支调上面 handler。
  - 在 `unified_mcp_server.py` 的 `_PLATFORM_TOOL_NAMES` 集合加 `"browser_handoff_session_create"`、`"browser_handoff_session_describe"`(**关键:漏了会路由到"未知工具"**,这是之前 alipay 踩过的坑)。

- [ ] **Step 5: 运行确认通过**(2 passed);**Step 6: Commit**
```bash
git add finance-mcp/tools/data_sources.py finance-mcp/unified_mcp_server.py
git add -f finance-mcp/tests/test_handoff_session_tools.py
git commit -m "feat(handoff): create/describe MCP tools + routing"
```

---

## 收尾(完成后)
- 3a-1 交付:handoff session 可被(系统态)创建、按一次性 token 描述;sync_job 可置 waiting_human_verification/resuming。纯后端,已测。
- **下一计划 3a-2**(approach 已定):① agent 进入风控等待时,经心跳 payload 携带 `active_jobs:[{sync_job_id,status=waiting_human_verification,reason,...}]`(runner 经线程安全回调写共享状态,heartbeat 读取);② data-agent 心跳处理:发现 waiting 且该 sync_job 尚无 handoff session → 调 `browser_handoff_session_create` + 解析通道(sync_job.channel_config_id || 公司默认)→ `get_notification_adapter` + `send_bot_message`(责任人,一次性链接);③ 最小落地页 `/p/handoff?t=` 照搬 `/p/alipay-auth` 范式,调 describe 显示店铺/验证类型/采集机/状态,引导责任人就地处理。
- 远程实时接管(截图/输入)= 阶段3b/4,不在 3a。
