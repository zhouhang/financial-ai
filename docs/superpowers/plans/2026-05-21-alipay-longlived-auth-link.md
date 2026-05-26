# 支付宝长效专属授权链接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把"生成专属授权链接"的 alipay 分支从 30 分钟直连支付宝链接,改成 30 天长效 Tally 落地链接 `/p/alipay-auth?t=<jwt>`;点开时(免登录)当场建一条 30 分钟 `auth_session` 再跳支付宝,从而解决链接发出去后过期的问题。

**Architecture:** 无状态 JWT(HS256,复用 `JWT_SECRET`)编码 `company_id`/operator/店铺名;finance-mcp 出 3 个 MCP 工具(签发在现有 create-auth-session、`alipay_auth_invite_describe`、`alipay_auth_invite_continue`);data-agent 加两个公开免登录 HTTP 路由(GET 渲染确认页 / POST continue 建 session 后 302 跳支付宝);支付宝回调逻辑不变。Excel 批量生成 20 条链接不在本计划范围。

**Tech Stack:** Python 3.11, PyJWT(已用), finance-mcp MCP tools, data-agent FastAPI(Starlette `HTMLResponse`/`RedirectResponse`), psycopg2, pytest。

---

## File Structure

- Create `finance-mcp/auth/alipay_auth_invite.py` — token 签发/校验纯函数(无请求上下文,供 MCP 工具与后续离线 Excel 脚本共用)。
- Modify `finance-mcp/tools/platform_connections.py` — alipay 分支改返回长效落地 URL;新增 `alipay_auth_invite_describe` / `alipay_auth_invite_continue` 两个工具 + 免登录建 session 内部函数。
- Modify `finance-mcp/auth/db.py` — 新增 `get_active_alipay_connection_for_shop`(幂等查询)。
- Modify `finance-agents/data-agent/tools/mcp_client.py` — `alipay_auth_invite_describe` / `alipay_auth_invite_continue` 包装器。
- Modify `finance-agents/data-agent/graphs/platform/api.py` — 公开路由 `GET /p/alipay-auth` + `POST /p/alipay-auth/continue`(HTML)。
- Tests: `finance-mcp/tests/test_alipay_auth_invite.py`, 扩展 `finance-mcp/tests/test_platform_connections*`(或新建)。

---

## Task 1: Token 签发与校验

**Files:**
- Create: `finance-mcp/auth/alipay_auth_invite.py`
- Test: `finance-mcp/tests/test_alipay_auth_invite.py`

- [ ] **Step 1: 写失败测试**

Create `finance-mcp/tests/test_alipay_auth_invite.py`:

```python
from __future__ import annotations
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import alipay_auth_invite as inv


def test_sign_then_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    tok = inv.build_alipay_auth_invite_token(
        company_id="c1", operator_user_id="u1",
        merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司",
        expected_alipay_account="s4k4net@163.com", external_shop_id="SK001",
    )
    p = inv.verify_alipay_auth_invite_token(tok)
    assert p is not None
    assert p["purpose"] == "alipay_auth_invite"
    assert p["company_id"] == "c1"
    assert p["operator_user_id"] == "u1"
    assert p["merchant_display_name"].startswith("搜卡手游专营店")
    assert p["expected_alipay_account"] == "s4k4net@163.com"


def test_verify_rejects_tampered(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    tok = inv.build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1", merchant_display_name="x")
    assert inv.verify_alipay_auth_invite_token(tok + "tamper") is None


def test_verify_rejects_wrong_purpose(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    import jwt
    from datetime import datetime, timezone, timedelta
    bad = jwt.encode({"purpose": "other", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, "test-secret", algorithm="HS256")
    assert inv.verify_alipay_auth_invite_token(bad) is None


def test_verify_rejects_expired(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    tok = inv.build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1", merchant_display_name="x", ttl_days=0)
    time.sleep(1)
    assert inv.verify_alipay_auth_invite_token(tok) is None
```

- [ ] **Step 2: 运行,确认失败**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_alipay_auth_invite.py -q`
Expected: FAIL (`No module named 'auth.alipay_auth_invite'`)

- [ ] **Step 3: 实现 token 模块**

Create `finance-mcp/auth/alipay_auth_invite.py`:

```python
"""支付宝长效专属授权链接的无状态 token 签发/校验。

token 是 HS256 JWT,编码授权要绑到哪个 Tally 企业 + 店铺显示名。它是一个 bearer 能力,
只能用于发起一次新的支付宝授权会话(换不到 app_auth_token)。供 MCP 工具与后续离线
Excel 批量脚本共用,不依赖任何请求上下文。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

_PURPOSE = "alipay_auth_invite"
_ALG = "HS256"


def _secret() -> str:
    return os.getenv("JWT_SECRET", "tally-secret-change-in-production")


def _ttl_days() -> int:
    try:
        return int(os.getenv("ALIPAY_AUTH_INVITE_TTL_DAYS", "30"))
    except ValueError:
        return 30


def build_alipay_auth_invite_token(
    *,
    company_id: str,
    operator_user_id: str,
    merchant_display_name: str,
    expected_alipay_account: str = "",
    external_shop_id: str = "",
    ttl_days: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    days = _ttl_days() if ttl_days is None else int(ttl_days)
    payload = {
        "purpose": _PURPOSE,
        "company_id": str(company_id),
        "operator_user_id": str(operator_user_id),
        "merchant_display_name": str(merchant_display_name),
        "expected_alipay_account": str(expected_alipay_account or ""),
        "external_shop_id": str(external_shop_id or ""),
        "iat": now,
        "exp": now + timedelta(days=days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALG)


def verify_alipay_auth_invite_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(str(token or ""), _secret(), algorithms=[_ALG])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    if not payload.get("company_id") or not payload.get("merchant_display_name"):
        return None
    return payload
```

- [ ] **Step 4: 运行,确认通过**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_alipay_auth_invite.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 提交**

```bash
git add -f finance-mcp/auth/alipay_auth_invite.py finance-mcp/tests/test_alipay_auth_invite.py
git commit -m "feat: alipay auth invite token sign/verify"
```

---

## Task 2: 幂等查询(该店是否已有有效支付宝连接)

**Files:**
- Modify: `finance-mcp/auth/db.py`
- Test: `finance-mcp/tests/test_alipay_auth_invite.py`

- [ ] **Step 1: 加失败测试(SQL 形态)**

Append to `finance-mcp/tests/test_alipay_auth_invite.py`:

```python
from auth import db as auth_db


class _Cur:
    def __init__(self, row): self._row=row; self.sql=""
    def __enter__(self): return self
    def __exit__(self,*a): return None
    def execute(self, sql, params=None): self.sql=sql
    def fetchone(self): return self._row

class _Conn:
    def __init__(self,row): self._c=_Cur(row)
    def __enter__(self): return self
    def __exit__(self,*a): return None
    def cursor(self,*a,**k): return self._c
    def commit(self): pass

class _CM:
    def __init__(self,row): self.row=row
    def __enter__(self): return _Conn(self.row)
    def __exit__(self,*a): return None


def test_get_active_alipay_connection_for_shop_filters(monkeypatch):
    cur_holder = {}
    cm = _CM({"id": "conn-1"})
    monkeypatch.setattr(auth_db, "get_conn", lambda: cm)
    out = auth_db.get_active_alipay_connection_for_shop(
        company_id="c1", merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司", external_shop_id="SK001")
    assert out == {"id": "conn-1"}
```

- [ ] **Step 2: 运行,确认失败**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_alipay_auth_invite.py::test_get_active_alipay_connection_for_shop_filters -q`
Expected: FAIL (`AttributeError: ... get_active_alipay_connection_for_shop`)

- [ ] **Step 3: 实现幂等查询**

In `finance-mcp/auth/db.py` 末尾附近(平台连接相关 helper 同区)新增:

```python
def get_active_alipay_connection_for_shop(
    *, company_id: str, merchant_display_name: str, external_shop_id: str = ""
) -> dict | None:
    """查该企业下是否已有匹配该店的有效(active)支付宝连接,用于落地页幂等。

    匹配规则:同 company + platform='alipay' + status='active',且
    external_shop_name == merchant_display_name 或(external_shop_id 非空且相等)。
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, external_shop_id, external_shop_name, status
                    FROM shop_connections
                    WHERE company_id = %s
                      AND platform_code = 'alipay'
                      AND status = 'active'
                      AND (
                          external_shop_name = %s
                          OR (%s <> '' AND external_shop_id = %s)
                      )
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (company_id, merchant_display_name, external_shop_id, external_shop_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"get_active_alipay_connection_for_shop 失败: {e}")
        return None
```

> 已核实:连接表为 `shop_connections`,含列 `company_id` / `platform_code` / `external_shop_id` / `external_shop_name` / `status`(default 'active',`update_shop_connection_status` 维护)。SQL 已按真实表名写好,无需再改。

- [ ] **Step 4: 运行,确认通过**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_alipay_auth_invite.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -f finance-mcp/auth/db.py finance-mcp/tests/test_alipay_auth_invite.py
git commit -m "feat: idempotency lookup for existing alipay shop connection"
```

---

## Task 3: 生成入口改返回长效落地链接

**Files:**
- Modify: `finance-mcp/tools/platform_connections.py`(`_handle_create_auth_session` alipay 分支)
- Test: `finance-mcp/tests/test_platform_alipay_invite.py`

- [ ] **Step 1: 写失败测试**

Create `finance-mcp/tests/test_platform_alipay_invite.py`:

```python
from __future__ import annotations
import asyncio, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import platform_connections as pc


def test_alipay_create_auth_session_returns_longlived_landing_url(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("TALLY_PUBLIC_BASE_URL", "https://tally.example.com")
    monkeypatch.setattr(pc, "_require_user", lambda t: {"user_id": "u1", "company_id": "c1"})

    result = asyncio.run(pc._handle_create_auth_session({
        "auth_token": "tok", "platform_code": "alipay",
        "merchant_display_name": "搜卡手游专营店武汉搜卡科技有限公司",
        "return_path": "/data-connections", "mode": "real",
    }))

    assert result["success"] is True
    url = result["auth_url"]
    assert url.startswith("https://tally.example.com/p/alipay-auth?t=")
    # token 解出来要带 company / 店铺名
    from auth.alipay_auth_invite import verify_alipay_auth_invite_token
    tok = url.split("t=", 1)[1]
    p = verify_alipay_auth_invite_token(tok)
    assert p["company_id"] == "c1" and p["merchant_display_name"].startswith("搜卡手游专营店")
```

- [ ] **Step 2: 运行,确认失败**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_platform_alipay_invite.py -q`
Expected: FAIL(返回的是 openauth.alipay.com 直连链接,不是落地 URL)

- [ ] **Step 3: 改 alipay 分支**

In `finance-mcp/tools/platform_connections.py` `_handle_create_auth_session`,在 alipay 校验 `merchant_display_name` 之后、创建 30min session/`build_auth_url` 之前,**短路返回长效落地链接**:

```python
    if platform_code == "alipay":
        if not merchant_display_name:
            return {"success": False, "platform_code": platform_code, "mode": mode,
                    "error": "支付宝授权需要填写商户显示名称"}
        base = os.getenv("TALLY_PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not base:
            return {"success": False, "platform_code": platform_code, "mode": mode,
                    "error": "未配置 TALLY_PUBLIC_BASE_URL，无法生成长效授权链接"}
        from auth.alipay_auth_invite import build_alipay_auth_invite_token
        invite = build_alipay_auth_invite_token(
            company_id=company_id,
            operator_user_id=str(user.get("user_id") or ""),
            merchant_display_name=merchant_display_name,
            expected_alipay_account=str(arguments.get("expected_alipay_account") or ""),
            external_shop_id=str(arguments.get("external_shop_id") or ""),
        )
        return {
            "success": True,
            "platform_code": "alipay",
            "auth_mode": "longlived_invite",
            "auth_url": f"{base}/p/alipay-auth?t={invite}",
            "mode": mode,
            "message": "已生成长效专属授权链接(30 天有效)",
        }
```

> 确认 `import os` 已在文件顶部(line ~17 已 import)。`company_id`/`user` 在该函数上方已由 `_require_user` 解析(`company_id = str(user["company_id"])`)。原 30min 直连分支代码保留给非 alipay 平台,不动。

- [ ] **Step 4: 运行,确认通过**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_platform_alipay_invite.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -f finance-mcp/tools/platform_connections.py finance-mcp/tests/test_platform_alipay_invite.py
git commit -m "feat: alipay 生成专属链接 returns 30-day landing url"
```

---

## Task 4: describe + continue 两个 MCP 工具(含免登录建 session)

**Files:**
- Modify: `finance-mcp/tools/platform_connections.py`(新工具 + dispatch)
- Test: `finance-mcp/tests/test_platform_alipay_invite.py`

- [ ] **Step 1: 写失败测试**

Append to `finance-mcp/tests/test_platform_alipay_invite.py`:

```python
def test_invite_describe_valid_and_idempotent(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from auth.alipay_auth_invite import build_alipay_auth_invite_token
    tok = build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1",
        merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司", expected_alipay_account="s4k4net@163.com")
    # 未授权
    monkeypatch.setattr(pc.auth_db, "get_active_alipay_connection_for_shop", lambda **k: None)
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": tok}))
    assert r["success"] and r["valid"] and r["already_authorized"] is False
    assert r["merchant_display_name"].startswith("搜卡手游专营店")
    assert r["expected_alipay_account"] == "s4k4net@163.com"
    # 已授权
    monkeypatch.setattr(pc.auth_db, "get_active_alipay_connection_for_shop", lambda **k: {"id": "conn-1"})
    r2 = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": tok}))
    assert r2["already_authorized"] is True


def test_invite_describe_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": "garbage"}))
    assert r["success"] is True and r["valid"] is False


def test_invite_continue_creates_session_without_login(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    from auth.alipay_auth_invite import build_alipay_auth_invite_token
    tok = build_alipay_auth_invite_token(company_id="c1", operator_user_id="u1",
        merchant_display_name="搜卡手游专营店武汉搜卡科技有限公司")
    captured = {}
    monkeypatch.setattr(pc, "_create_alipay_session_for_invite",
        lambda **k: captured.update(k) or {"success": True, "auth_url": "https://openauth.alipay.com/x?state=s1", "state": "s1"})
    r = asyncio.run(pc.handle_tool_call("alipay_auth_invite_continue", {"token": tok}))
    assert r["success"] is True
    assert r["auth_url"].startswith("https://openauth.alipay.com/")
    assert captured["company_id"] == "c1" and captured["operator_user_id"] == "u1"
```

- [ ] **Step 2: 运行,确认失败**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_platform_alipay_invite.py -q`
Expected: FAIL(未知工具 / 函数不存在)

- [ ] **Step 3: 加免登录建 session 内部函数 + 两个工具 + dispatch**

In `finance-mcp/tools/platform_connections.py`:

(a) 抽出免登录建 session 函数(复用现有 30min session + `build_auth_url` 逻辑,company/operator 由参数传入):

```python
def _create_alipay_session_for_invite(
    *, company_id: str, operator_user_id: str, merchant_display_name: str, return_path: str = "/"
) -> dict[str, Any]:
    """免登录:用显式 company/operator 建一条 30min alipay auth_session 并返回支付宝授权 url。"""
    try:
        app_config = _load_app_config(company_id, "alipay", mode="real")
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    connector = build_connector(app_config)
    state_token = str(uuid.uuid4())
    session = auth_db.create_auth_session(
        company_id=company_id,
        platform_code="alipay",
        operator_user_id=operator_user_id or None,
        state_token=state_token,
        return_path=return_path,
        redirect_uri=app_config.redirect_uri,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        extra={"merchant_display_name": merchant_display_name,
               "connection_label": merchant_display_name,
               "subject_type": "alipay_merchant"},
    )
    if session is None:
        return {"success": False, "error": "创建授权会话失败"}
    return {"success": True,
            "auth_url": connector.build_auth_url(state=str(session.get("state_token") or "")),
            "state": str(session.get("state_token") or ""),
            "session_id": str(session.get("id") or "")}


async def _handle_alipay_invite_describe(arguments: dict[str, Any]) -> dict[str, Any]:
    from auth.alipay_auth_invite import verify_alipay_auth_invite_token
    payload = verify_alipay_auth_invite_token(str(arguments.get("token") or ""))
    if not payload:
        return {"success": True, "valid": False, "error": "链接已失效或无效"}
    existing = auth_db.get_active_alipay_connection_for_shop(
        company_id=str(payload["company_id"]),
        merchant_display_name=str(payload["merchant_display_name"]),
        external_shop_id=str(payload.get("external_shop_id") or ""),
    )
    return {
        "success": True, "valid": True,
        "already_authorized": bool(existing),
        "merchant_display_name": str(payload["merchant_display_name"]),
        "expected_alipay_account": str(payload.get("expected_alipay_account") or ""),
    }


async def _handle_alipay_invite_continue(arguments: dict[str, Any]) -> dict[str, Any]:
    from auth.alipay_auth_invite import verify_alipay_auth_invite_token
    payload = verify_alipay_auth_invite_token(str(arguments.get("token") or ""))
    if not payload:
        return {"success": False, "error": "链接已失效或无效"}
    return _create_alipay_session_for_invite(
        company_id=str(payload["company_id"]),
        operator_user_id=str(payload.get("operator_user_id") or ""),
        merchant_display_name=str(payload["merchant_display_name"]),
        return_path=str(payload.get("return_path") or "/data-connections?mode=platform&platform=alipay"),
    )
```

(b) 在 `handle_tool_call` dispatch 里加:

```python
    if name == "alipay_auth_invite_describe":
        return await _handle_alipay_invite_describe(arguments)
    if name == "alipay_auth_invite_continue":
        return await _handle_alipay_invite_continue(arguments)
```

(c) 在工具列表(`name="platform_create_auth_session"` 同一 Tool 列表)追加两个 Tool 定义,`inputSchema` 均为 `{"token": {"type":"string"}}`,`required:["token"]`。

> 确认 `uuid` / `datetime,timedelta,timezone` / `build_connector` / `_load_app_config` / `auth_db` 已在文件顶部 import(现有 `_handle_create_auth_session` 已用到全部,故都在)。

- [ ] **Step 4: 运行,确认通过**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_platform_alipay_invite.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -f finance-mcp/tools/platform_connections.py finance-mcp/tests/test_platform_alipay_invite.py
git commit -m "feat: alipay auth invite describe + login-free continue MCP tools"
```

---

## Task 5: data-agent 公开落地路由 + MCP 客户端包装

**Files:**
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
- Modify: `finance-agents/data-agent/graphs/platform/api.py`

- [ ] **Step 1: 加 MCP 客户端包装器**

In `finance-agents/data-agent/tools/mcp_client.py` 追加:

```python
async def alipay_auth_invite_describe(token: str) -> dict[str, Any]:
    return await call_mcp_tool("alipay_auth_invite_describe", {"token": token})


async def alipay_auth_invite_continue(token: str) -> dict[str, Any]:
    return await call_mcp_tool("alipay_auth_invite_continue", {"token": token})
```

- [ ] **Step 2: 加公开路由**

In `finance-agents/data-agent/graphs/platform/api.py`:
顶部 import 处加 `from fastapi.responses import HTMLResponse, RedirectResponse`(若已存在 RedirectResponse 则只补 HTMLResponse),并 `from tools.mcp_client import alipay_auth_invite_describe, alipay_auth_invite_continue`。然后加:

```python
def _invite_html(*, title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title></head>"
        "<body style='font-family:system-ui;max-width:560px;margin:48px auto;padding:0 16px'>"
        f"{body}</body></html>"
    )


@router.get("/p/alipay-auth", response_class=HTMLResponse)
async def alipay_invite_landing(t: str = Query("", description="invite token")):
    info = await alipay_auth_invite_describe(t)
    if not info.get("valid"):
        return HTMLResponse(_invite_html(title="链接已失效",
            body="<h3>链接已失效或无效</h3><p>请联系对接人重新生成专属授权链接。</p>"), status_code=400)
    if info.get("already_authorized"):
        return HTMLResponse(_invite_html(title="已授权",
            body=f"<h3>该店铺已完成支付宝授权</h3><p>{info.get('merchant_display_name','')}</p><p>无需重复操作。</p>"))
    shop = info.get("merchant_display_name", "")
    acct = info.get("expected_alipay_account", "")
    acct_hint = (f"<p style='color:#b45309'><b>请务必使用账号 {acct} 登录支付宝</b>，登错账号会绑错主体。</p>" if acct else "")
    body = (
        f"<h3>支付宝授权</h3><p>店铺：<b>{shop}</b></p>{acct_hint}"
        "<form method='post' action='/p/alipay-auth/continue'>"
        f"<input type='hidden' name='t' value='{t}'/>"
        "<button type='submit' style='padding:10px 18px;font-size:15px'>继续去支付宝授权</button>"
        "</form>"
    )
    return HTMLResponse(_invite_html(title="支付宝授权", body=body))


@router.post("/p/alipay-auth/continue")
async def alipay_invite_continue(t: str = Form("")):
    result = await alipay_auth_invite_continue(t)
    if not result.get("success") or not result.get("auth_url"):
        return HTMLResponse(_invite_html(title="无法继续",
            body=f"<h3>无法发起授权</h3><p>{result.get('error','请稍后重试')}</p>"), status_code=400)
    return RedirectResponse(url=str(result["auth_url"]), status_code=303)
```

> 确认顶部已 `from fastapi import Query, Form`(Query 已用;Form 需补 import)。这两个路由是公开的(不取 `Authorization` header),与现有 `GET /data-sources/auth/callback/{source_id}` 同为免登录回调/落地层。

- [ ] **Step 3: 冒烟校验(import 不报错)**

Run: `cd finance-agents/data-agent && source .venv/bin/activate && python -c "import graphs.platform.api"`
Expected: 无报错

- [ ] **Step 4: 提交**

```bash
git add -f finance-agents/data-agent/tools/mcp_client.py finance-agents/data-agent/graphs/platform/api.py
git commit -m "feat: public alipay auth invite landing routes (no login)"
```

---

## Task 6: 端到端(mock)+ 前端确认

**Files:**
- Test: `finance-mcp/tests/test_platform_alipay_invite.py`

- [ ] **Step 1: 加端到端测试(token→describe→continue 串起来)**

Append to `finance-mcp/tests/test_platform_alipay_invite.py`:

```python
def test_invite_end_to_end_token_describe_continue(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("TALLY_PUBLIC_BASE_URL", "https://tally.example.com")
    monkeypatch.setattr(pc, "_require_user", lambda t: {"user_id": "u1", "company_id": "c1"})
    # 1. 生成专属链接
    gen = asyncio.run(pc._handle_create_auth_session({
        "auth_token": "tok", "platform_code": "alipay",
        "merchant_display_name": "博宽服务专营店深圳市博宽网络科技有限公司", "mode": "real"}))
    tok = gen["auth_url"].split("t=", 1)[1]
    # 2. describe(未授权)
    monkeypatch.setattr(pc.auth_db, "get_active_alipay_connection_for_shop", lambda **k: None)
    desc = asyncio.run(pc.handle_tool_call("alipay_auth_invite_describe", {"token": tok}))
    assert desc["valid"] and not desc["already_authorized"]
    # 3. continue(免登录建 session)
    monkeypatch.setattr(pc, "_create_alipay_session_for_invite",
        lambda **k: {"success": True, "auth_url": "https://openauth.alipay.com/oauth2/appToAppAuth.htm?state=zz", "state": "zz"})
    cont = asyncio.run(pc.handle_tool_call("alipay_auth_invite_continue", {"token": tok}))
    assert cont["auth_url"].endswith("state=zz")
```

- [ ] **Step 2: 运行全部 invite 测试**

Run: `source .venv/bin/activate && python -m pytest finance-mcp/tests/test_alipay_auth_invite.py finance-mcp/tests/test_platform_alipay_invite.py -q`
Expected: PASS(全部)

- [ ] **Step 3: 前端确认(无需改动)**

现有支付宝授权弹窗已展示 `auth_url`(`DataConnectionsPanel.tsx:3986`),后端现在返回的是长效落地 URL,弹窗"已生成企业专属授权链接"文案照旧。

Run: `cd finance-web && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0(无前端类型改动)

若希望弹窗文案体现"长效(30 天)",可把 `notice` 文案改成"已生成 30 天有效的专属授权链接,可复制发给商户/财务,任意时间点击完成授权。"(可选,非必须)。

- [ ] **Step 4: 本地真连冒烟(手动,记录在 PR)**

1. 配 `TALLY_PUBLIC_BASE_URL`(本机用 `http://127.0.0.1:8100` 或隧道域名)+ 真 `JWT_SECRET`,`./START_ALL_SERVICES.sh`。
2. UI 生成一条 alipay 专属链接,确认是 `/p/alipay-auth?t=...`。
3. 浏览器打开该链接 → 确认页显示店铺名 →「继续」→ 跳到支付宝 → 用目标账号授权 → 回调成功、连接出现在列表。
4. 再点同一链接 → 应显示"已授权,无需重复"。

- [ ] **Step 5: 提交**

```bash
git add -f finance-mcp/tests/test_platform_alipay_invite.py
git commit -m "test: alipay auth invite end-to-end (mock)"
```

---

## Self-Review

- **Spec coverage**:目标1-2(长效链接 + 点击当场建 session)= Task 3+4;目标3(免登录)= Task 4 `_create_alipay_session_for_invite` + Task 5 公开路由;目标4(回调不改)= 未改回调,沿用 state 命中;目标5(互不影响)= 每 token 独立 + 各自 session;幂等 = Task 2;错误页 = Task 5;token = Task 1。Excel = 明确范围外,未建任务 ✅。
- **Placeholder scan**:无 TBD;每个 code step 给了完整代码;Task 2 的表名/字段有"实现前确认"指令(因为我未逐列核实 `platform_shop_connections` 的真实列名,这是唯一需要 implementer 用一条 grep 落实的点)。
- **Type/名一致**:`build_alipay_auth_invite_token`/`verify_alipay_auth_invite_token`/`get_active_alipay_connection_for_shop`/`_create_alipay_session_for_invite`/`alipay_auth_invite_describe`/`alipay_auth_invite_continue` 在各 Task 间名字一致。
