# Browser Handoff Remote Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete browser handoff stages 3a/3b/4: close the session lifecycle, route `/handoff?t=...` notifications to a mobile-first finance-web remote-control page, and let the owner view screenshots and send click/drag/text input back to the waiting browser-agent.

**Architecture:** finance-mcp remains the persistent owner of handoff sessions, tokens, audit metadata, and sync job status. data-agent owns the in-memory live relay between finance-web controller sockets and browser-agent sockets. browser-agent owns Chrome/Playwright and exposes a narrow remote-control backend that captures frames and applies input only while the runner is waiting on risk verification.

**Tech Stack:** Python 3.12, FastAPI WebSocket, PostgreSQL JSONB audit events, Playwright sync API inside browser-agent worker threads, React 19 + TypeScript + Vite, lucide-react icons, pytest, Vitest, Playwright screenshots for UI verification.

---

## Current State

- `browser_handoff_sessions` already exists in `finance-mcp/auth/migrations/033_browser_handoff_sessions.sql`.
- `browser_handoff_session_create` and `browser_handoff_session_describe` already exist in `finance-mcp/tools/data_sources.py`.
- data-agent already handles `risk_waiting` in `finance-agents/data-agent/services/browser_agent_gateway.py`, but it still sends `/p/handoff?t=...`.
- data-agent still has the old lightweight HTML route in `finance-agents/data-agent/graphs/platform/api.py`.
- browser-agent `DataAgentWsClient` currently ignores non-`result` event frames.
- browser-agent runner reports `risk_waiting`, then passively polls for the risk page to clear; it has no remote-control queue yet.
- finance-web has no `/handoff` page and no React router; route gating happens directly in `finance-web/src/App.tsx`.

## File Structure

### finance-mcp

- Create `finance-mcp/auth/migrations/034_browser_handoff_lifecycle.sql`
  - Adds indexes for `agent_id/status` and `expires_at`.
  - Keeps schema additive; do not rewrite migration `033`.
- Modify `finance-mcp/auth/db.py`
  - Add audit append helpers.
  - Add status transition helpers for `active`, `waiting_agent`, `resuming`, `completed`, `expired`, `failed`.
  - Add stale-expire helper that marks the sync job failed with `RISK_VERIFICATION`.
- Modify `finance-mcp/auth/handoff_token.py`
  - Rename docstring semantics from one-time token to 15-minute capability token.
  - Add `decode_handoff_token_unverified()` for expiry handling without exposing secret data.
- Modify `finance-mcp/tools/data_sources.py`
  - Add MCP tools for controller open, event/audit, completion/failure, and expire.
  - Update create/describe copy and return shape.
- Modify `finance-mcp/unified_mcp_server.py`
  - Register new MCP tool names.
- Test `finance-mcp/tests/test_handoff_session_db.py`
- Test `finance-mcp/tests/test_handoff_session_tools.py`
- Test `finance-mcp/tests/test_handoff_token.py`

### data-agent

- Create `finance-agents/data-agent/services/browser_handoff_gateway.py`
  - Owns live in-memory registries:
    - `agent_id -> BrowserAgentPeer`
    - `handoff_session_id -> HandoffController`
    - `handoff_session_id -> latest_frame`
  - Owns controller takeover, relay, expiry checks, and audit calls.
- Modify `finance-agents/data-agent/services/browser_agent_gateway.py`
  - Keep domain request/response mapping.
  - Update notification link to `/handoff?t=...`.
  - Let handoff frame/status messages bypass the normal MCP request/response path.
- Modify `finance-agents/data-agent/server.py`
  - Register/unregister browser-agent peers.
  - Add `/handoff/ws?t=...`.
  - Route browser-agent handoff frames/events into `browser_handoff_gateway`.
- Modify `finance-agents/data-agent/tools/mcp_client.py`
  - Add typed wrappers for new handoff MCP tools.
- Modify `finance-agents/data-agent/graphs/platform/api.py`
  - Remove `/p/handoff`.
- Delete `finance-agents/data-agent/tests/test_handoff_landing.py`
- Test `finance-agents/data-agent/tests/test_gateway_risk_waiting.py`
- Test `finance-agents/data-agent/tests/test_browser_agent_gateway.py`
- Test `finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py`
- Create `finance-agents/data-agent/tests/test_browser_handoff_gateway.py`
- Create `finance-agents/data-agent/tests/test_handoff_ws_endpoint.py`

### browser-agent

- Create `finance-agents/browser-agent/finance_browser_agent/remote_control.py`
  - Defines `RemoteControlBackend`, `PlaywrightControlBackend`, `RemoteControlCoordinator`, and event dataclasses.
  - Ensures Playwright page operations happen in the runner thread, not in the async WS reader thread.
- Modify `finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py`
  - Add async event handler for downlink `event` frames.
  - Add `send_event()` for frame/status messages that do not expect `result`.
- Modify `finance-agents/browser-agent/finance_browser_agent/tally_client.py`
  - Construct a shared `RemoteControlCoordinator`.
  - Wire WS downlink events to the coordinator.
  - Expose `handoff_coordinator` for dispatcher/runner.
- Modify `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
  - Inject `handoff_coordinator` into runner messages.
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
  - Set `BROWSER_AGENT_RISK_MANUAL_TIMEOUT_MS` default to 900000.
  - Register a `PlaywrightControlBackend` while waiting for risk verification.
  - During the wait loop, capture frames, drain input commands, handle resume checks, and keep automatic risk-clear detection.
- Test `finance-agents/browser-agent/tests/test_data_agent_ws.py`
- Test `finance-agents/browser-agent/tests/test_tally_client.py`
- Test `finance-agents/browser-agent/tests/test_dispatcher_loop.py`
- Create `finance-agents/browser-agent/tests/test_remote_control.py`
- Modify `finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py`

### finance-web

- Create `finance-web/src/handoff/types.ts`
- Create `finance-web/src/handoff/handoffWs.ts`
- Create `finance-web/src/handoff/useHandoffSession.ts`
- Create `finance-web/src/handoff/HandoffViewport.tsx`
- Create `finance-web/src/handoff/HandoffPage.tsx`
- Modify `finance-web/src/App.tsx`
  - If `window.location.pathname === '/handoff'`, render `HandoffPage` before the normal authenticated app.
- Create `finance-web/tests/components/handoff-page.spec.tsx`

---

## Task 1: finance-mcp lifecycle, audit, and expiry tools

**Files:**
- Create: `finance-mcp/auth/migrations/034_browser_handoff_lifecycle.sql`
- Modify: `finance-mcp/auth/db.py`
- Modify: `finance-mcp/auth/handoff_token.py`
- Modify: `finance-mcp/tools/data_sources.py`
- Modify: `finance-mcp/unified_mcp_server.py`
- Test: `finance-mcp/tests/test_handoff_session_db.py`
- Test: `finance-mcp/tests/test_handoff_session_tools.py`
- Test: `finance-mcp/tests/test_handoff_token.py`

- [ ] **Step 1: Write failing token capability test**

Add this test to `finance-mcp/tests/test_handoff_token.py`:

```python
def test_handoff_token_can_decode_expired_payload_for_expire_only(monkeypatch):
    from datetime import datetime, timedelta, timezone

    import jwt

    from auth.handoff_token import decode_handoff_token_unverified, verify_handoff_token

    secret = "unit-secret"
    monkeypatch.setenv("JWT_SECRET", secret)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "purpose": "browser_handoff",
            "handoff_session_id": "h-expired",
            "company_id": "c-1",
            "iat": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=5),
            "jti": "j-1",
        },
        secret,
        algorithm="HS256",
    )

    assert verify_handoff_token(token) is None
    decoded = decode_handoff_token_unverified(token)
    assert decoded["handoff_session_id"] == "h-expired"
    assert decoded["company_id"] == "c-1"
```

- [ ] **Step 2: Run token test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_token.py::test_handoff_token_can_decode_expired_payload_for_expire_only -v
```

Expected: FAIL with `ImportError` or `AttributeError` for `decode_handoff_token_unverified`.

- [ ] **Step 3: Implement token helper**

In `finance-mcp/auth/handoff_token.py`, replace the opening docstring and add the helper:

```python
"""浏览器风控 handoff 的 15 分钟 capability token。

token 是无状态 bearer 能力,只编码 handoff_session_id + company_id,供责任人链接打开时
换取 session 描述和临时控制能力。不编码任何凭证/profile 路径/CDP 端口。
"""
```

Add below `verify_handoff_token()`:

```python
def decode_handoff_token_unverified(token: str) -> Optional[dict]:
    """解码 handoff token 的非敏感 claims,仅用于过期落库。

    仍然校验签名和 purpose,但不校验 exp。调用方不得据此授予控制能力。
    """
    try:
        payload = jwt.decode(
            str(token or ""),
            _secret(),
            algorithms=[_ALG],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    if not payload.get("handoff_session_id") or not payload.get("company_id"):
        return None
    return payload
```

- [ ] **Step 4: Run token test and verify it passes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_token.py::test_handoff_token_can_decode_expired_payload_for_expire_only -v
```

Expected: PASS.

- [ ] **Step 5: Write failing DB lifecycle tests**

Append these tests to `finance-mcp/tests/test_handoff_session_db.py`:

```python
def test_handoff_status_transition_appends_metadata_only_audit():
    import auth.db as auth_db

    auth_db.ensure_browser_handoff_schema()
    row = auth_db.insert_handoff_session(
        company_id="00000000-0000-0000-0000-000000000001",
        sync_job_id="00000000-0000-0000-0000-000000000002",
        data_source_id=None,
        agent_id="agent-A",
        profile_key="店铺A",
        reason="RISK_VERIFICATION",
        channel_config_id=None,
        expires_in_seconds=900,
    )

    updated = auth_db.transition_handoff_session_status(
        handoff_session_id=str(row["id"]),
        status="active",
        event_type="page_opened",
        controller_id="ctrl-1",
        agent_id="agent-A",
        reason="opened from mobile",
    )

    assert updated["status"] == "active"
    audit = updated["audit_events"]
    assert audit[-1]["event_type"] == "page_opened"
    assert audit[-1]["controller_id"] == "ctrl-1"
    assert "base64" not in str(audit).lower()
    assert "验证码" not in str(audit)


def test_expire_handoff_session_marks_sync_job_failed(monkeypatch):
    import auth.db as auth_db

    calls = []
    monkeypatch.setattr(
        auth_db,
        "mark_browser_sync_job_failed",
        lambda **kwargs: calls.append(kwargs) or {"id": kwargs["sync_job_id"], "job_status": "failed"},
    )

    auth_db.ensure_browser_handoff_schema()
    row = auth_db.insert_handoff_session(
        company_id="00000000-0000-0000-0000-000000000001",
        sync_job_id="00000000-0000-0000-0000-000000000003",
        data_source_id=None,
        agent_id="agent-A",
        profile_key="店铺A",
        reason="RISK_VERIFICATION",
        channel_config_id=None,
        expires_in_seconds=-1,
    )

    expired = auth_db.expire_handoff_session(
        handoff_session_id=str(row["id"]),
        reason="unit expired",
    )

    assert expired["status"] == "expired"
    assert calls == [
        {
            "sync_job_id": "00000000-0000-0000-0000-000000000003",
            "error_message": "handoff expired: unit expired",
            "fail_reason": "RISK_VERIFICATION",
            "retryable": False,
            "max_attempts": 1,
            "retry_delay_seconds": 0,
        }
    ]
```

- [ ] **Step 6: Run DB lifecycle tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_session_db.py::test_handoff_status_transition_appends_metadata_only_audit finance-mcp/tests/test_handoff_session_db.py::test_expire_handoff_session_marks_sync_job_failed -v
```

Expected: FAIL because `transition_handoff_session_status` and `expire_handoff_session` do not exist.

- [ ] **Step 7: Add migration 034**

Create `finance-mcp/auth/migrations/034_browser_handoff_lifecycle.sql`:

```sql
CREATE INDEX IF NOT EXISTS idx_handoff_sessions_agent_status
    ON browser_handoff_sessions(agent_id, status);

CREATE INDEX IF NOT EXISTS idx_handoff_sessions_expires_at
    ON browser_handoff_sessions(expires_at);
```

- [ ] **Step 8: Implement DB lifecycle helpers**

In `finance-mcp/auth/db.py`, add imports if missing:

```python
from datetime import datetime, timezone
```

Add these helpers below `get_handoff_session()` and replace `mark_handoff_session_status()` only if keeping the old function would duplicate transition behavior:

```python
_HANDOFF_FINAL_STATUSES = {"completed", "expired", "failed", "cancelled"}


def _handoff_audit_event(
    *,
    event_type: str,
    controller_id: str = "",
    agent_id: str = "",
    reason: str = "",
    metadata: dict | None = None,
) -> dict:
    event = {
        "event_type": str(event_type or ""),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if controller_id:
        event["controller_id"] = str(controller_id)
    if agent_id:
        event["agent_id"] = str(agent_id)
    if reason:
        event["reason"] = str(reason)
    for key, value in (metadata or {}).items():
        if key not in {"data", "text", "input", "screenshot", "base64"}:
            event[str(key)] = value
    return event


def transition_handoff_session_status(
    *,
    handoff_session_id: str,
    status: str,
    event_type: str,
    controller_id: str = "",
    agent_id: str = "",
    reason: str = "",
    metadata: dict | None = None,
) -> dict | None:
    completed = str(status or "") in _HANDOFF_FINAL_STATUSES
    event = _handoff_audit_event(
        event_type=event_type,
        controller_id=controller_id,
        agent_id=agent_id,
        reason=reason,
        metadata=metadata,
    )
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE browser_handoff_sessions
                SET status = %s,
                    audit_events = audit_events || %s::jsonb,
                    completed_at = CASE WHEN %s THEN COALESCE(completed_at, now()) ELSE completed_at END,
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    str(status or ""),
                    psycopg2.extras.Json([event]),
                    completed,
                    handoff_session_id,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def append_handoff_audit_event(
    *,
    handoff_session_id: str,
    event_type: str,
    controller_id: str = "",
    agent_id: str = "",
    reason: str = "",
    metadata: dict | None = None,
) -> dict | None:
    row = get_handoff_session(handoff_session_id=handoff_session_id)
    if not row:
        return None
    return transition_handoff_session_status(
        handoff_session_id=handoff_session_id,
        status=str(row.get("status") or "pending"),
        event_type=event_type,
        controller_id=controller_id,
        agent_id=agent_id,
        reason=reason,
        metadata=metadata,
    )


def expire_handoff_session(*, handoff_session_id: str, reason: str = "expired") -> dict | None:
    row = transition_handoff_session_status(
        handoff_session_id=handoff_session_id,
        status="expired",
        event_type="expired",
        reason=reason,
    )
    if not row:
        return None
    sync_job_id = str(row.get("sync_job_id") or "")
    if sync_job_id:
        mark_browser_sync_job_failed(
            sync_job_id=sync_job_id,
            error_message=f"handoff expired: {reason}",
            fail_reason="RISK_VERIFICATION",
            retryable=False,
            max_attempts=1,
            retry_delay_seconds=0,
        )
    return row
```

- [ ] **Step 9: Run DB lifecycle tests and verify they pass**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_session_db.py::test_handoff_status_transition_appends_metadata_only_audit finance-mcp/tests/test_handoff_session_db.py::test_expire_handoff_session_marks_sync_job_failed -v
```

Expected: PASS.

- [ ] **Step 10: Write failing MCP tool tests**

Append these tests to `finance-mcp/tests/test_handoff_session_tools.py`:

```python
def test_open_marks_controller_and_active(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_control_open,
        _handle_browser_handoff_session_create,
    )

    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    opened = asyncio.run(_handle_browser_handoff_session_control_open({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "agent_online": True,
    }))

    assert opened["success"] is True
    assert opened["session"]["status"] == "active"
    assert opened["session"]["controller_id"] == "ctrl-1"


def test_resume_requested_records_resuming_and_sync_status(monkeypatch):
    import uuid as _uuid
    import auth.db as _db
    from tools.data_sources import (
        _handle_browser_handoff_session_create,
        _handle_browser_handoff_session_event,
    )

    statuses = []
    monkeypatch.setattr(_db, "get_sync_job", lambda *, sync_job_id: None)
    monkeypatch.setattr(_db, "set_browser_sync_job_status", lambda **kwargs: statuses.append(kwargs) or 1)

    created = asyncio.run(_handle_browser_handoff_session_create({
        "worker_token": _system_token(),
        "company_id": "00000000-0000-0000-0000-000000000001",
        "sync_job_id": str(_uuid.uuid4()),
        "agent_id": "agent-A",
        "profile_key": "店铺A",
        "reason": "RISK_VERIFICATION",
    }))

    event = asyncio.run(_handle_browser_handoff_session_event({
        "token": created["handoff_token"],
        "controller_id": "ctrl-1",
        "event_type": "resume_requested",
        "status": "resuming",
    }))

    assert event["success"] is True
    assert event["session"]["status"] == "resuming"
    assert statuses[-1]["status"] == "resuming"
```

- [ ] **Step 11: Run MCP tool tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_session_tools.py::test_open_marks_controller_and_active finance-mcp/tests/test_handoff_session_tools.py::test_resume_requested_records_resuming_and_sync_status -v
```

Expected: FAIL because the new tool handlers do not exist.

- [ ] **Step 12: Implement MCP tool handlers and registrations**

In `finance-mcp/tools/data_sources.py`, add tool schemas after `browser_handoff_session_describe`:

```python
Tool(
    name="browser_handoff_session_control_open",
    description="handoff 页面打开后登记当前 controller,更新 session 状态和审计。",
    inputSchema={
        "type": "object",
        "properties": {
            "token": {"type": "string"},
            "controller_id": {"type": "string"},
            "agent_online": {"type": "boolean"},
        },
        "required": ["token", "controller_id"],
    },
),
Tool(
    name="browser_handoff_session_event",
    description="记录 handoff 元数据事件,可携带允许的 session 状态迁移。",
    inputSchema={
        "type": "object",
        "properties": {
            "token": {"type": "string"},
            "handoff_session_id": {"type": "string"},
            "worker_token": {"type": "string"},
            "controller_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "event_type": {"type": "string"},
            "status": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["event_type"],
    },
),
Tool(
    name="browser_handoff_session_expire",
    description="将 handoff session 标记为 expired,并将 sync_job 以 RISK_VERIFICATION 失败。",
    inputSchema={
        "type": "object",
        "properties": {
            "token": {"type": "string"},
            "handoff_session_id": {"type": "string"},
            "worker_token": {"type": "string"},
            "reason": {"type": "string"},
        },
    },
),
```

Add these dispatch entries:

```python
if name == "browser_handoff_session_control_open":
    return await _handle_browser_handoff_session_control_open(arguments)
if name == "browser_handoff_session_event":
    return await _handle_browser_handoff_session_event(arguments)
if name == "browser_handoff_session_expire":
    return await _handle_browser_handoff_session_expire(arguments)
```

Add helper functions near the existing handoff handlers:

```python
def _handoff_row_for_token(token: str, *, allow_expired: bool = False) -> tuple[dict | None, str]:
    from auth.handoff_token import decode_handoff_token_unverified, verify_handoff_token

    payload = decode_handoff_token_unverified(token) if allow_expired else verify_handoff_token(token)
    if payload is None:
        return None, "链接无效或已过期"
    row = auth_db.get_handoff_session(handoff_session_id=str(payload["handoff_session_id"]))
    if not row:
        return None, "handoff session 不存在"
    if str(row.get("company_id") or "") != str(payload.get("company_id") or ""):
        return None, "handoff token 与 session 不匹配"
    return row, ""


def _handoff_public_session(row: dict[str, Any], *, controller_id: str = "") -> dict[str, Any]:
    view = _public_handoff_session_view(row)
    view.update({
        "sync_job_id": str(row.get("sync_job_id") or ""),
        "data_source_id": str(row.get("data_source_id") or ""),
        "controller_id": controller_id,
    })
    return view
```

Implement the handlers:

```python
async def _handle_browser_handoff_session_control_open(arguments: dict[str, Any]) -> dict[str, Any]:
    token = str(arguments.get("token") or "")
    controller_id = str(arguments.get("controller_id") or "").strip()
    if not controller_id:
        return {"success": False, "error": "missing controller_id"}
    row, error = _handoff_row_for_token(token)
    if not row:
        return {"success": False, "error": error}
    status = "active" if bool(arguments.get("agent_online", False)) else "waiting_agent"
    updated = auth_db.transition_handoff_session_status(
        handoff_session_id=str(row["id"]),
        status=status,
        event_type="page_opened",
        controller_id=controller_id,
        agent_id=str(row.get("agent_id") or ""),
    )
    auth_db.append_handoff_audit_event(
        handoff_session_id=str(row["id"]),
        event_type="controller_changed",
        controller_id=controller_id,
        agent_id=str(row.get("agent_id") or ""),
    )
    updated = auth_db.get_handoff_session(handoff_session_id=str(row["id"])) or updated
    return {"success": True, "session": _handoff_public_session(updated, controller_id=controller_id)}


async def _handle_browser_handoff_session_event(arguments: dict[str, Any]) -> dict[str, Any]:
    token = str(arguments.get("token") or "")
    handoff_session_id = str(arguments.get("handoff_session_id") or "").strip()
    worker_token = str(arguments.get("worker_token") or "")
    row: dict[str, Any] | None = None
    if token:
        row, error = _handoff_row_for_token(token)
        if not row:
            return {"success": False, "error": error}
    elif handoff_session_id and worker_token:
        try:
            _require_scheduler_user(worker_token)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        row = auth_db.get_handoff_session(handoff_session_id=handoff_session_id)
    if not row:
        return {"success": False, "error": "handoff session 不存在"}

    event_type = str(arguments.get("event_type") or "").strip()
    status = str(arguments.get("status") or row.get("status") or "pending").strip()
    controller_id = str(arguments.get("controller_id") or "").strip()
    agent_id = str(arguments.get("agent_id") or row.get("agent_id") or "").strip()
    updated = auth_db.transition_handoff_session_status(
        handoff_session_id=str(row["id"]),
        status=status,
        event_type=event_type,
        controller_id=controller_id,
        agent_id=agent_id,
        reason=str(arguments.get("reason") or ""),
    )
    if event_type == "resume_requested" or status == "resuming":
        auth_db.set_browser_sync_job_status(sync_job_id=str(row["sync_job_id"]), status="resuming")
    return {"success": True, "session": _handoff_public_session(updated or row, controller_id=controller_id)}


async def _handle_browser_handoff_session_expire(arguments: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] | None = None
    token = str(arguments.get("token") or "")
    if token:
        row, error = _handoff_row_for_token(token, allow_expired=True)
        if not row:
            return {"success": False, "error": error}
    elif arguments.get("worker_token") and arguments.get("handoff_session_id"):
        try:
            _require_scheduler_user(str(arguments.get("worker_token") or ""))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        row = auth_db.get_handoff_session(handoff_session_id=str(arguments.get("handoff_session_id")))
    if not row:
        return {"success": False, "error": "handoff session 不存在"}
    expired = auth_db.expire_handoff_session(
        handoff_session_id=str(row["id"]),
        reason=str(arguments.get("reason") or "expired"),
    )
    return {"success": True, "session": _handoff_public_session(expired or row)}
```

In `finance-mcp/unified_mcp_server.py`, add:

```python
"browser_handoff_session_control_open",
"browser_handoff_session_event",
"browser_handoff_session_expire",
```

- [ ] **Step 13: Run MCP handoff tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_token.py finance-mcp/tests/test_handoff_session_db.py finance-mcp/tests/test_handoff_session_tools.py -v
```

Expected: PASS.

- [ ] **Step 14: Commit finance-mcp lifecycle work**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-mcp/auth/migrations/034_browser_handoff_lifecycle.sql finance-mcp/auth/db.py finance-mcp/auth/handoff_token.py finance-mcp/tools/data_sources.py finance-mcp/unified_mcp_server.py finance-mcp/tests/test_handoff_token.py finance-mcp/tests/test_handoff_session_db.py finance-mcp/tests/test_handoff_session_tools.py
git commit -m "feat(handoff): add lifecycle audit and expiry tools"
```

---

## Task 2: data-agent live handoff relay and `/handoff/ws`

**Files:**
- Create: `finance-agents/data-agent/services/browser_handoff_gateway.py`
- Modify: `finance-agents/data-agent/services/browser_agent_gateway.py`
- Modify: `finance-agents/data-agent/server.py`
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
- Modify: `finance-agents/data-agent/graphs/platform/api.py`
- Delete: `finance-agents/data-agent/tests/test_handoff_landing.py`
- Test: `finance-agents/data-agent/tests/test_gateway_risk_waiting.py`
- Test: `finance-agents/data-agent/tests/test_browser_agent_gateway.py`
- Test: `finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py`
- Create: `finance-agents/data-agent/tests/test_browser_handoff_gateway.py`
- Create: `finance-agents/data-agent/tests/test_handoff_ws_endpoint.py`

- [ ] **Step 1: Write failing notification link test**

In `finance-agents/data-agent/tests/test_gateway_risk_waiting.py`, change:

```python
assert "/p/handoff?t=TKN" in calls["notify"][0]["content"]
```

to:

```python
assert "/handoff?t=TKN" in calls["notify"][0]["content"]
assert "/p/handoff" not in calls["notify"][0]["content"]
```

- [ ] **Step 2: Run link test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-agents/data-agent/tests/test_gateway_risk_waiting.py::test_risk_waiting_creates_session_and_notifies_owner -v
```

Expected: FAIL because the content still includes `/p/handoff`.

- [ ] **Step 3: Update notification link**

In `finance-agents/data-agent/services/browser_agent_gateway.py`, replace:

```python
link = f"{base}/p/handoff?t={token}" if base else f"/p/handoff?t={token}"
```

with:

```python
link = f"{base}/handoff?t={token}" if base else f"/handoff?t={token}"
```

Also change the message body from "请在采集机上完成验证,或查看详情" to:

```python
f"请打开链接远程完成验证:{link}"
```

- [ ] **Step 4: Run link test and verify it passes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-agents/data-agent/tests/test_gateway_risk_waiting.py::test_risk_waiting_creates_session_and_notifies_owner -v
```

Expected: PASS.

- [ ] **Step 5: Write failing handoff gateway unit tests**

Create `finance-agents/data-agent/tests/test_browser_handoff_gateway.py`:

```python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import browser_handoff_gateway as hg


class FakeAgent:
    def __init__(self, agent_id: str = "agent-A") -> None:
        self.agent_id = agent_id
        self.token = "worker-token"
        self.sent: list[dict] = []

    async def send_event(self, payload: dict) -> None:
        self.sent.append(payload)


class FakeController:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_controller_open_starts_online_agent_and_revokes_previous(monkeypatch):
    hg.reset_for_tests()
    calls: list[tuple[str, dict]] = []

    async def fake_call(tool: str, args: dict):
        calls.append((tool, args))
        if tool == "browser_handoff_session_describe":
            return {
                "success": True,
                "session": {
                    "handoff_session_id": "h1",
                    "sync_job_id": "j1",
                    "agent_id": "agent-A",
                    "profile_key": "店铺A",
                    "reason": "RISK_VERIFICATION",
                    "status": "pending",
                    "expires_at": "2026-05-25T12:00:00Z",
                },
            }
        if tool == "browser_handoff_session_control_open":
            return {
                "success": True,
                "session": {
                    "handoff_session_id": "h1",
                    "sync_job_id": "j1",
                    "agent_id": "agent-A",
                    "profile_key": "店铺A",
                    "reason": "RISK_VERIFICATION",
                    "status": "active",
                    "controller_id": args["controller_id"],
                    "expires_at": "2026-05-25T12:00:00Z",
                },
            }
        return {"success": True}

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    agent = FakeAgent()
    await hg.register_browser_agent(agent_id="agent-A", token="worker-token", send_event=agent.send_event)

    first = FakeController()
    first_controller = await hg.open_controller(token="TKN", send_json=first.send_json)
    second = FakeController()
    second_controller = await hg.open_controller(token="TKN", send_json=second.send_json)

    assert first_controller.controller_id != second_controller.controller_id
    assert any(msg["type"] == "controller_revoked" for msg in first.sent)
    assert agent.sent[-1]["type"] == "event"
    assert agent.sent[-1]["event"] == "handoff_start"
    assert agent.sent[-1]["handoff_session_id"] == "h1"


@pytest.mark.asyncio
async def test_frame_routes_only_to_current_controller(monkeypatch):
    hg.reset_for_tests()
    controller = FakeController()
    hg._controllers["h1"] = hg.HandoffController(
        handoff_session_id="h1",
        controller_id="ctrl-current",
        token="TKN",
        session={"handoff_session_id": "h1", "agent_id": "agent-A"},
        send_json=controller.send_json,
    )

    await hg.route_agent_message(
        agent_id="agent-A",
        token="worker-token",
        msg={
            "type": "handoff_frame",
            "handoff_session_id": "h1",
            "controller_id": "ctrl-current",
            "frame_id": 1,
            "mime": "image/jpeg",
            "width": 100,
            "height": 80,
            "data": "abc",
        },
    )

    assert controller.sent == [{
        "type": "frame",
        "handoff_session_id": "h1",
        "frame_id": 1,
        "mime": "image/jpeg",
        "width": 100,
        "height": 80,
        "data": "abc",
    }]
```

- [ ] **Step 6: Run gateway tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-agents/data-agent/tests/test_browser_handoff_gateway.py -v
```

Expected: FAIL because `browser_handoff_gateway` does not exist.

- [ ] **Step 7: Implement `browser_handoff_gateway.py`**

Create `finance-agents/data-agent/services/browser_handoff_gateway.py` with these public types and functions:

```python
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class BrowserAgentPeer:
    agent_id: str
    token: str
    send_event: SendJson


@dataclass
class HandoffController:
    handoff_session_id: str
    controller_id: str
    token: str
    session: dict[str, Any]
    send_json: SendJson


_agents: dict[str, BrowserAgentPeer] = {}
_controllers: dict[str, HandoffController] = {}
_latest_frames: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


def reset_for_tests() -> None:
    _agents.clear()
    _controllers.clear()
    _latest_frames.clear()


async def register_browser_agent(*, agent_id: str, token: str, send_event: SendJson) -> None:
    async with _lock:
        _agents[str(agent_id)] = BrowserAgentPeer(agent_id=str(agent_id), token=str(token), send_event=send_event)


async def unregister_browser_agent(agent_id: str) -> None:
    async with _lock:
        _agents.pop(str(agent_id), None)
        affected = [
            controller
            for controller in _controllers.values()
            if str(controller.session.get("agent_id") or "") == str(agent_id)
        ]
    for controller in affected:
        await controller.send_json({"type": "status", "status": "waiting_agent"})
        await call_mcp_tool("browser_handoff_session_event", {
            "token": controller.token,
            "controller_id": controller.controller_id,
            "event_type": "agent_offline",
            "status": "waiting_agent",
            "agent_id": str(agent_id),
        })


async def open_controller(*, token: str, send_json: SendJson) -> HandoffController:
    described = await call_mcp_tool("browser_handoff_session_describe", {"token": token})
    if not described.get("success"):
        await send_json({"type": "error", "status": "expired", "error": str(described.get("error") or "链接无效")})
        raise ValueError(str(described.get("error") or "链接无效"))

    session = dict(described.get("session") or {})
    handoff_session_id = str(session.get("handoff_session_id") or "")
    agent_id = str(session.get("agent_id") or "")
    controller_id = str(uuid.uuid4())
    async with _lock:
        old = _controllers.get(handoff_session_id)
        agent = _agents.get(agent_id)
        controller = HandoffController(
            handoff_session_id=handoff_session_id,
            controller_id=controller_id,
            token=token,
            session=session,
            send_json=send_json,
        )
        _controllers[handoff_session_id] = controller

    if old is not None:
        await old.send_json({"type": "controller_revoked", "handoff_session_id": handoff_session_id})

    opened = await call_mcp_tool("browser_handoff_session_control_open", {
        "token": token,
        "controller_id": controller_id,
        "agent_online": agent is not None,
    })
    if opened.get("success"):
        controller.session = dict(opened.get("session") or session)
    await send_json({
        "type": "session",
        "controller_id": controller_id,
        "session": controller.session,
        "status": controller.session.get("status") or ("active" if agent else "waiting_agent"),
    })
    latest = _latest_frames.get(handoff_session_id)
    if latest:
        await send_json({"type": "frame", **latest})
    if agent is None:
        await send_json({"type": "status", "status": "waiting_agent"})
        return controller

    await agent.send_event({
        "type": "event",
        "event": "handoff_start",
        "handoff_session_id": handoff_session_id,
        "controller_id": controller_id,
        "sync_job_id": str(controller.session.get("sync_job_id") or ""),
        "frame_profile": {"idle_fps": 1, "interactive_fps": 5},
    })
    return controller


async def close_controller(controller: HandoffController) -> None:
    async with _lock:
        current = _controllers.get(controller.handoff_session_id)
        if current and current.controller_id == controller.controller_id:
            _controllers.pop(controller.handoff_session_id, None)
            agent = _agents.get(str(controller.session.get("agent_id") or ""))
        else:
            agent = None
    if agent is not None:
        await agent.send_event({
            "type": "event",
            "event": "handoff_stop",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
        })


async def route_controller_message(controller: HandoffController, msg: dict[str, Any]) -> None:
    async with _lock:
        current = _controllers.get(controller.handoff_session_id)
        agent = _agents.get(str(controller.session.get("agent_id") or ""))
    if current is None or current.controller_id != controller.controller_id:
        await controller.send_json({"type": "controller_revoked", "handoff_session_id": controller.handoff_session_id})
        return
    if agent is None:
        await controller.send_json({"type": "status", "status": "waiting_agent"})
        return
    msg_type = str(msg.get("type") or "")
    if msg_type == "handoff_input":
        await agent.send_event({
            "type": "event",
            "event": "handoff_input",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
            "input": dict(msg.get("event") or {}),
        })
    elif msg_type == "resume_requested":
        await call_mcp_tool("browser_handoff_session_event", {
            "token": controller.token,
            "controller_id": controller.controller_id,
            "event_type": "resume_requested",
            "status": "resuming",
        })
        await controller.send_json({"type": "status", "status": "resuming"})
        await agent.send_event({
            "type": "event",
            "event": "handoff_resume_check",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
        })
    elif msg_type in {"client_hidden", "client_visible", "reconnect_stream"}:
        await agent.send_event({
            "type": "event",
            "event": "handoff_frame_rate",
            "handoff_session_id": controller.handoff_session_id,
            "controller_id": controller.controller_id,
            "profile": "idle" if msg_type == "client_hidden" else "interactive",
        })


async def route_agent_message(*, agent_id: str, token: str, msg: dict[str, Any]) -> bool:
    msg_type = str(msg.get("type") or "")
    handoff_session_id = str(msg.get("handoff_session_id") or "")
    if msg_type == "handoff_frame":
        frame = {
            "handoff_session_id": handoff_session_id,
            "frame_id": int(msg.get("frame_id") or 0),
            "mime": str(msg.get("mime") or "image/jpeg"),
            "width": int(msg.get("width") or 0),
            "height": int(msg.get("height") or 0),
            "data": str(msg.get("data") or ""),
        }
        _latest_frames[handoff_session_id] = frame
        controller = _controllers.get(handoff_session_id)
        if controller and controller.controller_id == str(msg.get("controller_id") or ""):
            await controller.send_json({"type": "frame", **frame})
        return True
    if msg_type in {"handoff_completed", "handoff_still_blocked", "handoff_failed"}:
        controller = _controllers.get(handoff_session_id)
        status = {
            "handoff_completed": "completed",
            "handoff_still_blocked": "still_blocked",
            "handoff_failed": "failed",
        }[msg_type]
        await call_mcp_tool("browser_handoff_session_event", {
            "worker_token": token,
            "handoff_session_id": handoff_session_id,
            "agent_id": agent_id,
            "event_type": status,
            "status": "completed" if status == "completed" else ("failed" if status == "failed" else "active"),
            "reason": str(msg.get("reason") or ""),
        })
        if controller:
            await controller.send_json({"type": "status", "status": status, "reason": str(msg.get("reason") or "")})
        return True
    return False
```

- [ ] **Step 8: Add MCP wrappers**

In `finance-agents/data-agent/tools/mcp_client.py`, add:

```python
async def browser_handoff_session_control_open(
    token: str,
    controller_id: str,
    agent_online: bool,
) -> dict[str, Any]:
    return await call_mcp_tool("browser_handoff_session_control_open", {
        "token": token,
        "controller_id": controller_id,
        "agent_online": agent_online,
    })


async def browser_handoff_session_event(payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("browser_handoff_session_event", payload)


async def browser_handoff_session_expire(payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("browser_handoff_session_expire", payload)
```

- [ ] **Step 9: Wire server endpoints**

In `finance-agents/data-agent/server.py`, import the new gateway:

```python
import asyncio

from services import browser_handoff_gateway
```

In `/browser-agent`, after `conn` is created, create a send lock and register:

```python
send_lock = asyncio.Lock()

async def _send_to_agent(payload: dict[str, Any]) -> None:
    async with send_lock:
        await ws.send_json(payload)

await browser_handoff_gateway.register_browser_agent(
    agent_id=conn.agent_id,
    token=conn.token,
    send_event=_send_to_agent,
)
```

Inside the browser-agent receive loop, before `handle_domain_message`:

```python
if await browser_handoff_gateway.route_agent_message(
    agent_id=conn.agent_id,
    token=conn.token,
    msg=msg,
):
    continue
```

Use `_send_to_agent(reply)` instead of `ws.send_json(reply)`.

In both disconnect/exception paths, call:

```python
if conn is not None:
    await browser_handoff_gateway.unregister_browser_agent(conn.agent_id)
```

Add the controller endpoint:

```python
@app.websocket("/handoff/ws")
async def websocket_handoff(ws: WebSocket, t: str = ""):
    await ws.accept()

    async def _send(payload: dict[str, Any]) -> None:
        await ws.send_json(payload)

    controller = None
    try:
        controller = await browser_handoff_gateway.open_controller(token=t, send_json=_send)
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "error": "无效的 JSON"})
                continue
            await browser_handoff_gateway.route_controller_message(controller, msg)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("handoff WS ended: %s", exc)
    finally:
        if controller is not None:
            await browser_handoff_gateway.close_controller(controller)
```

- [ ] **Step 10: Remove `/p/handoff` route and test**

Delete the `handoff_landing()` route from `finance-agents/data-agent/graphs/platform/api.py`.

Delete `finance-agents/data-agent/tests/test_handoff_landing.py`.

Create `finance-agents/data-agent/tests/test_handoff_ws_endpoint.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _mod in (
    "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio",
    "psycopg",
    "psycopg.conninfo",
    "psycopg.sql",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import server
from services import browser_handoff_gateway as hg


def test_p_handoff_removed():
    client = TestClient(server.app)
    response = client.get("/p/handoff?t=anything")
    assert response.status_code == 404


def test_handoff_ws_invalid_token_returns_error(monkeypatch):
    async def fake_call(tool, args):
        assert tool == "browser_handoff_session_describe"
        return {"success": False, "error": "链接无效或已过期"}

    monkeypatch.setattr(hg, "call_mcp_tool", fake_call)
    client = TestClient(server.app)
    with client.websocket_connect("/handoff/ws?t=bad") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["status"] == "expired"
```

- [ ] **Step 11: Run data-agent tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-agents/data-agent/tests/test_gateway_risk_waiting.py finance-agents/data-agent/tests/test_browser_agent_gateway.py finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py finance-agents/data-agent/tests/test_browser_handoff_gateway.py finance-agents/data-agent/tests/test_handoff_ws_endpoint.py -v
```

Expected: PASS.

- [ ] **Step 12: Commit data-agent relay work**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-agents/data-agent/services/browser_handoff_gateway.py finance-agents/data-agent/services/browser_agent_gateway.py finance-agents/data-agent/server.py finance-agents/data-agent/tools/mcp_client.py finance-agents/data-agent/graphs/platform/api.py finance-agents/data-agent/tests/test_gateway_risk_waiting.py finance-agents/data-agent/tests/test_browser_agent_gateway.py finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py finance-agents/data-agent/tests/test_browser_handoff_gateway.py finance-agents/data-agent/tests/test_handoff_ws_endpoint.py
git add -u finance-agents/data-agent/tests/test_handoff_landing.py
git commit -m "feat(handoff): relay controller and browser agent websocket traffic"
```

---

## Task 3: browser-agent Playwright remote-control backend

**Files:**
- Create: `finance-agents/browser-agent/finance_browser_agent/remote_control.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/tally_client.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Test: `finance-agents/browser-agent/tests/test_data_agent_ws.py`
- Test: `finance-agents/browser-agent/tests/test_tally_client.py`
- Test: `finance-agents/browser-agent/tests/test_dispatcher_loop.py`
- Create: `finance-agents/browser-agent/tests/test_remote_control.py`
- Modify: `finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py`

- [ ] **Step 1: Write failing WS event-handler test**

Add to `finance-agents/browser-agent/tests/test_data_agent_ws.py`:

```python
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
```

- [ ] **Step 2: Run WS event test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/browser-agent
pytest tests/test_data_agent_ws.py::test_reader_dispatches_event_frames_to_handler -v
```

Expected: FAIL because `DataAgentWsClient.__init__` has no `event_handler`.

- [ ] **Step 3: Implement WS downlink event handling**

In `finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py`:

```python
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
```

Add `event_handler: EventHandler | None = None` to `__init__`, store `self._event_handler`.

In `_reader()`, replace the "其它类型(event)本轮忽略" comment with:

```python
elif msg.get("type") == "event" and self._event_handler is not None:
    asyncio.create_task(self._event_handler(msg))
```

Add:

```python
async def send_event(self, payload: dict[str, Any]) -> dict[str, Any]:
    if self._ws is None or (self._reader_task and self._reader_task.done()):
        if not await self.connect():
            return {"success": False, "error": "无法建立 data-agent WS 连接"}
    try:
        await self._ws.send(json.dumps(payload, ensure_ascii=False))
        return {"success": True}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"data-agent WS 发送失败: {exc}"}
```

- [ ] **Step 4: Run WS event tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/browser-agent
pytest tests/test_data_agent_ws.py tests/test_risk_waiting_report.py -v
```

Expected: PASS.

- [ ] **Step 5: Write failing remote-control backend tests**

Create `finance-agents/browser-agent/tests/test_remote_control.py`:

```python
from __future__ import annotations

import base64
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.remote_control import PlaywrightControlBackend, RemoteControlCoordinator


class FakeMouse:
    def __init__(self) -> None:
        self.calls = []

    def click(self, x, y, button="left"):
        self.calls.append(("click", round(x), round(y), button))

    def down(self, button="left"):
        self.calls.append(("down", button))

    def move(self, x, y):
        self.calls.append(("move", round(x), round(y)))

    def up(self, button="left"):
        self.calls.append(("up", button))

    def wheel(self, dx, dy):
        self.calls.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self) -> None:
        self.calls = []

    def type(self, text):
        self.calls.append(("type", text))

    def down(self, key):
        self.calls.append(("down", key))

    def up(self, key):
        self.calls.append(("up", key))


class FakePage:
    viewport_size = {"width": 1000, "height": 800}

    def __init__(self) -> None:
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    def screenshot(self, **kwargs):
        return b"jpg-bytes"


def test_backend_maps_normalized_input_to_playwright_mouse_and_keyboard():
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])

    backend.apply_input_event({"kind": "click", "x": 0.25, "y": 0.5, "button": "left"})
    backend.apply_input_event({"kind": "text", "text": "123456"})
    backend.apply_input_event({"kind": "key_down", "key": "Enter"})
    backend.apply_input_event({"kind": "key_up", "key": "Enter"})

    assert page.mouse.calls == [("click", 250, 400, "left")]
    assert page.keyboard.calls == [("type", "123456"), ("down", "Enter"), ("up", "Enter")]


def test_backend_capture_frame_base64_encodes_screenshot():
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])

    frame = backend.capture_frame()

    assert frame["mime"] == "image/jpeg"
    assert frame["width"] == 1000
    assert frame["height"] == 800
    assert base64.b64decode(frame["data"]) == b"jpg-bytes"


def test_coordinator_queues_downlink_until_runner_thread_drains():
    sent = []

    async def emit(payload):
        sent.append(payload)

    coordinator = RemoteControlCoordinator(send_event=emit)
    page = FakePage()
    backend = PlaywrightControlBackend(page=page, risk_contexts=[page])
    coordinator.register_backend(sync_job_id="j1", backend=backend)

    asyncio.run(coordinator.handle_event({
        "type": "event",
        "event": "handoff_input",
        "sync_job_id": "j1",
        "handoff_session_id": "h1",
        "controller_id": "ctrl-1",
        "input": {"kind": "click", "x": 0.1, "y": 0.2},
    }))
    backend.drain_pending_input()

    assert page.mouse.calls == [("click", 100, 160, "left")]
```

- [ ] **Step 6: Run remote-control tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/browser-agent
pytest tests/test_remote_control.py -v
```

Expected: FAIL because `remote_control.py` does not exist.

- [ ] **Step 7: Implement `remote_control.py`**

Create `finance-agents/browser-agent/finance_browser_agent/remote_control.py` with:

```python
from __future__ import annotations

import asyncio
import base64
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)


class RemoteControlBackend(Protocol):
    handoff_session_id: str
    controller_id: str

    def start_stream(self, *, handoff_session_id: str, controller_id: str, idle_fps: float, interactive_fps: float) -> None: ...
    def stop_stream(self) -> None: ...
    def capture_frame(self) -> dict[str, Any]: ...
    def apply_input_event(self, event: dict[str, Any]) -> None: ...
    def queue_input_event(self, event: dict[str, Any]) -> None: ...
    def drain_pending_input(self) -> None: ...
    def should_capture_frame(self) -> bool: ...


@dataclass
class PlaywrightControlBackend:
    page: Any
    risk_contexts: list[Any]
    handoff_session_id: str = ""
    controller_id: str = ""
    idle_fps: float = 1.0
    interactive_fps: float = 5.0
    stream_active: bool = False
    _last_frame_at: float = 0.0
    _interactive_until: float = 0.0
    _input_queue: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)

    def start_stream(self, *, handoff_session_id: str, controller_id: str, idle_fps: float, interactive_fps: float) -> None:
        self.handoff_session_id = handoff_session_id
        self.controller_id = controller_id
        self.idle_fps = max(0.2, float(idle_fps or 1))
        self.interactive_fps = max(self.idle_fps, float(interactive_fps or 5))
        self.stream_active = True

    def stop_stream(self) -> None:
        self.stream_active = False

    def queue_input_event(self, event: dict[str, Any]) -> None:
        self._input_queue.put(dict(event or {}))

    def drain_pending_input(self) -> None:
        while True:
            try:
                event = self._input_queue.get_nowait()
            except queue.Empty:
                return
            self.apply_input_event(event)

    def capture_frame(self) -> dict[str, Any]:
        viewport = getattr(self.page, "viewport_size", None) or {}
        raw = self.page.screenshot(type="jpeg", quality=60, full_page=False)
        self._last_frame_at = time.monotonic()
        return {
            "mime": "image/jpeg",
            "width": int(viewport.get("width") or 0),
            "height": int(viewport.get("height") or 0),
            "data": base64.b64encode(raw).decode("ascii"),
        }

    def should_capture_frame(self) -> bool:
        if not self.stream_active:
            return False
        fps = self.interactive_fps if time.monotonic() <= self._interactive_until else self.idle_fps
        return time.monotonic() - self._last_frame_at >= 1.0 / max(0.2, fps)

    def _point(self, event: dict[str, Any]) -> tuple[float, float]:
        viewport = getattr(self.page, "viewport_size", None) or {"width": 0, "height": 0}
        width = float(viewport.get("width") or 0)
        height = float(viewport.get("height") or 0)
        return float(event.get("x") or 0) * width, float(event.get("y") or 0) * height

    def apply_input_event(self, event: dict[str, Any]) -> None:
        kind = str(event.get("kind") or "")
        self._interactive_until = time.monotonic() + 2.0
        if kind == "text":
            text = str(event.get("text") or "")
            if text:
                self.page.keyboard.type(text)
            return
        if kind in {"key_down", "key_up"}:
            key = str(event.get("key") or "")
            if key:
                (self.page.keyboard.down if kind == "key_down" else self.page.keyboard.up)(key)
            return
        if kind == "wheel":
            self.page.mouse.wheel(float(event.get("delta_x") or 0), float(event.get("delta_y") or 0))
            return
        x, y = self._point(event)
        button = str(event.get("button") or "left")
        if kind == "click":
            self.page.mouse.click(x, y, button=button)
        elif kind == "mouse_down":
            self.page.mouse.move(x, y)
            self.page.mouse.down(button=button)
        elif kind == "mouse_move":
            self.page.mouse.move(x, y)
        elif kind == "mouse_up":
            self.page.mouse.move(x, y)
            self.page.mouse.up(button=button)


class RemoteControlCoordinator:
    def __init__(self, *, send_event: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]) -> None:
        self._send_event = send_event
        self._backends_by_sync_job: dict[str, RemoteControlBackend] = {}
        self._pending_starts: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register_backend(self, *, sync_job_id: str, backend: RemoteControlBackend) -> None:
        with self._lock:
            self._backends_by_sync_job[str(sync_job_id)] = backend
            pending = self._pending_starts.pop(str(sync_job_id), None)
        if pending:
            self._start_backend(backend, pending)

    def unregister_backend(self, *, sync_job_id: str) -> None:
        with self._lock:
            self._backends_by_sync_job.pop(str(sync_job_id), None)

    async def handle_event(self, msg: dict[str, Any]) -> None:
        event = str(msg.get("event") or "")
        sync_job_id = str(msg.get("sync_job_id") or "")
        with self._lock:
            backend = self._backends_by_sync_job.get(sync_job_id)
            if backend is None and event == "handoff_start":
                self._pending_starts[sync_job_id] = dict(msg)
                return
        if backend is None:
            return
        if event == "handoff_start":
            self._start_backend(backend, msg)
        elif event == "handoff_stop":
            backend.stop_stream()
        elif event == "handoff_input":
            backend.queue_input_event(dict(msg.get("input") or {}))
        elif event == "handoff_frame_rate":
            backend.start_stream(
                handoff_session_id=backend.handoff_session_id,
                controller_id=backend.controller_id,
                idle_fps=1,
                interactive_fps=5,
            )
        elif event == "handoff_resume_check":
            backend.queue_input_event({"kind": "__resume_check__"})

    def _start_backend(self, backend: RemoteControlBackend, msg: dict[str, Any]) -> None:
        frame_profile = dict(msg.get("frame_profile") or {})
        backend.start_stream(
            handoff_session_id=str(msg.get("handoff_session_id") or ""),
            controller_id=str(msg.get("controller_id") or ""),
            idle_fps=float(frame_profile.get("idle_fps") or 1),
            interactive_fps=float(frame_profile.get("interactive_fps") or 5),
        )

    async def emit_frame(self, *, sync_job_id: str, backend: RemoteControlBackend, frame: dict[str, Any]) -> None:
        await self._send_event({
            "type": "handoff_frame",
            "sync_job_id": sync_job_id,
            "handoff_session_id": backend.handoff_session_id,
            "controller_id": backend.controller_id,
            **frame,
        })

    async def emit_status(self, payload: dict[str, Any]) -> None:
        await self._send_event(payload)
```

- [ ] **Step 8: Wire Tally client and dispatcher**

In `finance-agents/browser-agent/finance_browser_agent/tally_client.py`, import:

```python
from finance_browser_agent.remote_control import RemoteControlCoordinator
```

In `BrowserAgentTallyClient.__init__`, build the client and coordinator in this order:

```python
self.handoff_coordinator = RemoteControlCoordinator(
    send_event=lambda payload: self._client.send_event(payload)
)
self._client = ws_client or DataAgentWsClient(
    ws_url=config.data_agent_ws_url,
    agent_id=config.agent_id,
    max_concurrency=config.max_concurrency,
    token_provider=lambda: self.worker_token,
    event_handler=self.handoff_coordinator.handle_event,
)
```

If `ws_client` is injected in tests and does not have `send_event`, create a small async fallback that returns `{"success": False, "error": "handoff unavailable"}`.

In `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`, in `_message_from_job()` add:

```python
"handoff_coordinator": getattr(self.client, "handoff_coordinator", None),
```

Add a test to `tests/test_dispatcher_loop.py`:

```python
def test_dispatcher_message_includes_handoff_coordinator_when_available():
    client = FakeClient([], {})
    client.handoff_coordinator = object()
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: message, max_concurrency=1)
    message = loop._message_from_job({"id": "j1", "shop_id": "s1", "playbook_body": {}}, {})
    assert message["handoff_coordinator"] is client.handoff_coordinator
```

- [ ] **Step 9: Run dispatcher/tally tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/browser-agent
pytest tests/test_data_agent_ws.py tests/test_tally_client.py tests/test_dispatcher_loop.py tests/test_remote_control.py -v
```

Expected: PASS.

- [ ] **Step 10: Integrate backend into Playwright risk wait**

In `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`:

Change default config:

```python
risk_manual_timeout_ms=_env_int("BROWSER_AGENT_RISK_MANUAL_TIMEOUT_MS", 900000),
```

Import:

```python
import asyncio
from finance_browser_agent.remote_control import PlaywrightControlBackend, RemoteControlCoordinator
```

Add helper:

```python
def _run_async_safely(coro: Any) -> None:
    try:
        asyncio.run(coro)
    except Exception:
        logger.exception("handoff async callback failed")
```

Add this wait helper near `_wait_for_risk_to_clear()`:

```python
def _wait_for_risk_to_clear_with_handoff(
    page: Any,
    contexts: list[Any],
    *,
    timeout_ms: int,
    poll_interval_ms: int,
    sync_job_id: str,
    coordinator: RemoteControlCoordinator | None,
) -> bool:
    if coordinator is None:
        return _wait_for_risk_to_clear(contexts, timeout_ms=timeout_ms, poll_interval_ms=poll_interval_ms)
    backend = PlaywrightControlBackend(page=page, risk_contexts=contexts)
    coordinator.register_backend(sync_job_id=sync_job_id, backend=backend)
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    try:
        while time.monotonic() <= deadline:
            backend.drain_pending_input()
            if backend.should_capture_frame():
                _run_async_safely(coordinator.emit_frame(
                    sync_job_id=sync_job_id,
                    backend=backend,
                    frame=backend.capture_frame(),
                ))
            if not any(_detect_auth_or_risk(context) == "RISK_VERIFICATION" for context in contexts):
                _run_async_safely(coordinator.emit_status({
                    "type": "handoff_completed",
                    "sync_job_id": sync_job_id,
                    "handoff_session_id": backend.handoff_session_id,
                    "controller_id": backend.controller_id,
                }))
                return True
            wait_ms = min(max(1, poll_interval_ms), int(max(1, (deadline - time.monotonic()) * 1000)))
            _wait_for_timeout(page, wait_ms)
        return not any(_detect_auth_or_risk(context) == "RISK_VERIFICATION" for context in contexts)
    finally:
        backend.stop_stream()
        coordinator.unregister_backend(sync_job_id=sync_job_id)
```

In `_run_playbook_with_playwright_inner()`, set:

```python
handoff_coordinator = message.get("handoff_coordinator")
```

Pass `handoff_coordinator` and `job_id` to each risk wait path:

- `_login_if_needed(...)`
- `_await_navigate_risk_clearance(...)`
- `_wait_for_post_login_selector(...)`

Where those functions currently call `_wait_for_risk_to_clear(...)`, replace with `_wait_for_risk_to_clear_with_handoff(...)`.

- [ ] **Step 11: Update Playwright risk wait tests**

In `finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py`, add this test. It calls the wait helper directly with a fake page and fake coordinator, so it does not start Chrome:

```python
def test_navigate_risk_wait_registers_handoff_backend(monkeypatch):
    class FakeRiskPage:
        url = "https://example.com/identity_verify"
        frames = []
        viewport_size = {"width": 100, "height": 80}

        def wait_for_timeout(self, delay_ms):
            return None

        def screenshot(self, **kwargs):
            return b"fake-jpeg"

    registered = []
    unregistered = []
    emitted_frames = []

    class FakeCoordinator:
        def register_backend(self, *, sync_job_id, backend):
            registered.append((sync_job_id, backend))
            backend.start_stream(
                handoff_session_id="h1",
                controller_id="ctrl-1",
                idle_fps=1000,
                interactive_fps=1000,
            )

        def unregister_backend(self, *, sync_job_id):
            unregistered.append(sync_job_id)

        async def emit_frame(self, **kwargs):
            emitted_frames.append(kwargs)

        async def emit_status(self, payload):
            return None

    from finance_browser_agent import playwright_runner as pr

    page = FakeRiskPage()
    monkeypatch.setattr(pr, "_detect_auth_or_risk", lambda context: "RISK_VERIFICATION")

    cleared = pr._wait_for_risk_to_clear_with_handoff(
        page,
        [page],
        timeout_ms=10,
        poll_interval_ms=1,
        sync_job_id="j1",
        coordinator=FakeCoordinator(),
    )

    assert cleared is False
    assert registered[0][0] == "j1"
    assert unregistered == ["j1"]
    assert emitted_frames[0]["sync_job_id"] == "j1"
    assert emitted_frames[0]["frame"]["mime"] == "image/jpeg"
```

- [ ] **Step 12: Run browser-agent tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/browser-agent
pytest tests/test_data_agent_ws.py tests/test_tally_client.py tests/test_dispatcher_loop.py tests/test_remote_control.py tests/test_playwright_navigate_risk_wait.py tests/test_risk_waiting_report.py -v
```

Expected: PASS.

- [ ] **Step 13: Commit browser-agent work**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-agents/browser-agent/finance_browser_agent/remote_control.py finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/tests/test_data_agent_ws.py finance-agents/browser-agent/tests/test_tally_client.py finance-agents/browser-agent/tests/test_dispatcher_loop.py finance-agents/browser-agent/tests/test_remote_control.py finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py
git commit -m "feat(handoff): add playwright remote control backend"
```

---

## Task 4: finance-web mobile-first `/handoff?t=...` page

**Files:**
- Create: `finance-web/src/handoff/types.ts`
- Create: `finance-web/src/handoff/handoffWs.ts`
- Create: `finance-web/src/handoff/useHandoffSession.ts`
- Create: `finance-web/src/handoff/HandoffViewport.tsx`
- Create: `finance-web/src/handoff/HandoffPage.tsx`
- Modify: `finance-web/src/App.tsx`
- Create: `finance-web/tests/components/handoff-page.spec.tsx`

- [ ] **Step 1: Write failing component tests**

Create `finance-web/tests/components/handoff-page.spec.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import HandoffPage from '../../src/handoff/HandoffPage';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  readyState = FakeWebSocket.OPEN;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
    setTimeout(() => this.onopen?.(), 0);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.onclose?.();
  }

  feed(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe('HandoffPage', () => {
  const originalWebSocket = globalThis.WebSocket;

  afterEach(() => {
    vi.restoreAllMocks();
    FakeWebSocket.instances = [];
    globalThis.WebSocket = originalWebSocket;
    window.history.replaceState({}, '', '/');
  });

  it('connects to /api/handoff/ws with token and renders session metadata', async () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    window.history.replaceState({}, '', '/handoff?t=TKN');

    render(<HandoffPage />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(FakeWebSocket.instances[0].url).toContain('/api/handoff/ws?t=TKN');

    FakeWebSocket.instances[0].feed({
      type: 'session',
      controller_id: 'ctrl-1',
      status: 'active',
      session: {
        profile_key: '单枪旗舰店',
        reason: 'RISK_VERIFICATION',
        agent_id: 'browser-agent-win',
        expires_at: '2026-05-25T12:00:00Z',
      },
    });

    expect(await screen.findByText('单枪旗舰店')).toBeInTheDocument();
    expect(screen.getByText(/browser-agent-win/)).toBeInTheDocument();
  });

  it('renders frames and sends normalized pointer input', async () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    window.history.replaceState({}, '', '/handoff?t=TKN');

    render(<HandoffPage />);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const ws = FakeWebSocket.instances[0];
    ws.feed({
      type: 'frame',
      mime: 'image/jpeg',
      width: 100,
      height: 80,
      frame_id: 1,
      data: 'YWJj',
    });

    const viewport = await screen.findByTestId('handoff-viewport');
    vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({
      left: 10,
      top: 20,
      width: 200,
      height: 100,
      right: 210,
      bottom: 120,
      x: 10,
      y: 20,
      toJSON: () => ({}),
    } as DOMRect);

    fireEvent.pointerDown(viewport, { clientX: 110, clientY: 70, pointerId: 1, button: 0 });
    fireEvent.pointerUp(viewport, { clientX: 110, clientY: 70, pointerId: 1, button: 0 });

    const sent = ws.sent.map((item) => JSON.parse(item));
    expect(sent.some((msg) => msg.type === 'handoff_input' && msg.event.kind === 'mouse_down')).toBe(true);
    expect(sent.some((msg) => msg.type === 'handoff_input' && msg.event.x === 0.5 && msg.event.y === 0.5)).toBe(true);
  });
});
```

- [ ] **Step 2: Run component tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- handoff-page.spec.tsx
```

Expected: FAIL because `src/handoff/HandoffPage` does not exist.

- [ ] **Step 3: Add handoff types**

Create `finance-web/src/handoff/types.ts`:

```typescript
export type HandoffStatus =
  | 'connecting'
  | 'active'
  | 'waiting_agent'
  | 'revoked'
  | 'resuming'
  | 'still_blocked'
  | 'completed'
  | 'expired'
  | 'error';

export interface HandoffSession {
  handoff_session_id?: string;
  sync_job_id?: string;
  profile_key?: string;
  reason?: string;
  agent_id?: string;
  status?: string;
  expires_at?: string;
  controller_id?: string;
}

export interface HandoffFrame {
  frame_id: number;
  mime: string;
  width: number;
  height: number;
  data: string;
}

export interface HandoffInputEvent {
  kind: 'mouse_down' | 'mouse_move' | 'mouse_up' | 'click' | 'wheel' | 'key_down' | 'key_up' | 'text';
  x?: number;
  y?: number;
  button?: 'left' | 'middle' | 'right';
  delta_x?: number;
  delta_y?: number;
  key?: string;
  text?: string;
}
```

- [ ] **Step 4: Add WS URL helper**

Create `finance-web/src/handoff/handoffWs.ts`:

```typescript
export function buildHandoffWsUrl(token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const encoded = encodeURIComponent(token);
  return `${protocol}//${window.location.host}/api/handoff/ws?t=${encoded}`;
}

export function parseHandoffToken(): string {
  return new URLSearchParams(window.location.search).get('t') || '';
}
```

- [ ] **Step 5: Add session hook**

Create `finance-web/src/handoff/useHandoffSession.ts`:

```typescript
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildHandoffWsUrl } from './handoffWs';
import type { HandoffFrame, HandoffInputEvent, HandoffSession, HandoffStatus } from './types';

interface HandoffMessage {
  type: string;
  status?: HandoffStatus;
  session?: HandoffSession;
  controller_id?: string;
  error?: string;
  reason?: string;
  frame_id?: number;
  mime?: string;
  width?: number;
  height?: number;
  data?: string;
}

export function useHandoffSession(token: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<HandoffStatus>(token ? 'connecting' : 'expired');
  const [session, setSession] = useState<HandoffSession | null>(null);
  const [frame, setFrame] = useState<HandoffFrame | null>(null);
  const [error, setError] = useState('');
  const wsUrl = useMemo(() => (token ? buildHandoffWsUrl(token) : ''), [token]);

  const send = useCallback((payload: unknown) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(payload));
    return true;
  }, []);

  const sendInput = useCallback((event: HandoffInputEvent) => {
    send({ type: 'handoff_input', event });
  }, [send]);

  const resume = useCallback(() => {
    setStatus('resuming');
    send({ type: 'resume_requested' });
  }, [send]);

  const reconnect = useCallback(() => {
    send({ type: 'reconnect_stream' });
  }, [send]);

  useEffect(() => {
    if (!token) {
      setStatus('expired');
      return undefined;
    }
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => setStatus((current) => (current === 'connecting' ? 'active' : current));
    ws.onmessage = (event) => {
      const msg = JSON.parse(String(event.data || '{}')) as HandoffMessage;
      if (msg.type === 'session') {
        setSession({ ...(msg.session || {}), controller_id: msg.controller_id });
        setStatus(msg.status || 'active');
      } else if (msg.type === 'frame') {
        setFrame({
          frame_id: Number(msg.frame_id || 0),
          mime: msg.mime || 'image/jpeg',
          width: Number(msg.width || 0),
          height: Number(msg.height || 0),
          data: msg.data || '',
        });
        setStatus((current) => current === 'connecting' ? 'active' : current);
      } else if (msg.type === 'status') {
        setStatus(msg.status || 'active');
        if (msg.reason) setError(msg.reason);
      } else if (msg.type === 'controller_revoked') {
        setStatus('revoked');
      } else if (msg.type === 'error') {
        setStatus(msg.status || 'error');
        setError(msg.error || '链接不可用');
      }
    };
    ws.onclose = () => {
      setStatus((current) => current === 'completed' || current === 'expired' ? current : 'waiting_agent');
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [token, wsUrl]);

  return { status, session, frame, error, sendInput, resume, reconnect };
}
```

- [ ] **Step 6: Add viewport component**

Create `finance-web/src/handoff/HandoffViewport.tsx`:

```tsx
import type { HandoffFrame, HandoffInputEvent } from './types';

interface HandoffViewportProps {
  frame: HandoffFrame | null;
  disabled?: boolean;
  onInput: (event: HandoffInputEvent) => void;
}

function pointFromEvent(target: HTMLElement, event: { clientX: number; clientY: number }) {
  const rect = target.getBoundingClientRect();
  const x = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
  const y = rect.height > 0 ? (event.clientY - rect.top) / rect.height : 0;
  return {
    x: Math.max(0, Math.min(1, Number(x.toFixed(4)))),
    y: Math.max(0, Math.min(1, Number(y.toFixed(4)))),
  };
}

export default function HandoffViewport({ frame, disabled = false, onInput }: HandoffViewportProps) {
  const src = frame ? `data:${frame.mime};base64,${frame.data}` : '';

  return (
    <div
      data-testid="handoff-viewport"
      className="relative flex min-h-[42vh] w-full touch-none select-none items-center justify-center overflow-hidden bg-slate-950"
      onPointerDown={(event) => {
        if (disabled) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        onInput({ kind: 'mouse_down', ...pointFromEvent(event.currentTarget, event), button: 'left' });
      }}
      onPointerMove={(event) => {
        if (disabled || event.buttons !== 1) return;
        onInput({ kind: 'mouse_move', ...pointFromEvent(event.currentTarget, event), button: 'left' });
      }}
      onPointerUp={(event) => {
        if (disabled) return;
        onInput({ kind: 'mouse_up', ...pointFromEvent(event.currentTarget, event), button: 'left' });
      }}
      onWheel={(event) => {
        if (disabled) return;
        onInput({ kind: 'wheel', delta_x: event.deltaX, delta_y: event.deltaY });
      }}
    >
      {src ? (
        <img
          alt=""
          src={src}
          className="h-full max-h-[62vh] w-full object-contain"
          draggable={false}
        />
      ) : (
        <div className="h-[42vh] w-full animate-pulse bg-slate-900" />
      )}
    </div>
  );
}
```

- [ ] **Step 7: Add mobile-first page**

Create `finance-web/src/handoff/HandoffPage.tsx`:

```tsx
import { CheckCircle2, Keyboard, RefreshCw, ShieldAlert, WifiOff } from 'lucide-react';
import { useMemo, useState } from 'react';
import HandoffViewport from './HandoffViewport';
import { parseHandoffToken } from './handoffWs';
import { useHandoffSession } from './useHandoffSession';

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    connecting: '连接中',
    active: '可操作',
    waiting_agent: '等待采集机',
    revoked: '已被接管',
    resuming: '复检中',
    still_blocked: '仍需验证',
    completed: '已通过',
    expired: '已失效',
    error: '不可用',
  };
  return labels[status] || status;
}

export default function HandoffPage() {
  const token = useMemo(() => parseHandoffToken(), []);
  const { status, session, frame, error, sendInput, resume, reconnect } = useHandoffSession(token);
  const [text, setText] = useState('');
  const disabled = status === 'revoked' || status === 'completed' || status === 'expired' || status === 'error';

  return (
    <main className="min-h-dvh bg-slate-100 text-slate-950">
      <section className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs font-medium text-orange-600">
              <ShieldAlert size={16} />
              <span>{statusLabel(status)}</span>
            </div>
            <h1 className="mt-1 truncate text-lg font-semibold text-slate-950">
              {session?.profile_key || '人工验证'}
            </h1>
            <p className="mt-1 truncate text-xs text-slate-500">
              {session?.reason || 'RISK_VERIFICATION'} · {session?.agent_id || '采集机'}
            </p>
          </div>
          <button
            type="button"
            onClick={reconnect}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-slate-200 bg-white text-slate-700"
            aria-label="重连画面"
          >
            <RefreshCw size={18} />
          </button>
        </header>

        <div className="flex-1 bg-slate-950">
          <HandoffViewport frame={frame} disabled={disabled} onInput={sendInput} />
        </div>

        <footer className="space-y-3 border-t border-slate-200 bg-white px-4 py-3 pb-[calc(env(safe-area-inset-bottom)+12px)]">
          {status === 'waiting_agent' ? (
            <div className="flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <WifiOff size={16} />
              <span>采集机暂未连接</span>
            </div>
          ) : null}
          {status === 'revoked' ? (
            <div className="rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-600">新的页面已接管</div>
          ) : null}
          {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

          <div className="flex gap-2">
            <label className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-slate-200 px-3 py-2">
              <Keyboard size={17} className="shrink-0 text-slate-500" />
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
                disabled={disabled}
                className="min-w-0 flex-1 bg-transparent text-base outline-none"
                placeholder="短信验证码或文本"
                inputMode="text"
              />
            </label>
            <button
              type="button"
              disabled={disabled || !text}
              onClick={() => {
                sendInput({ kind: 'text', text });
                setText('');
              }}
              className="rounded-md bg-slate-900 px-4 text-sm font-semibold text-white disabled:opacity-40"
            >
              发送
            </button>
          </div>

          <button
            type="button"
            disabled={disabled || status === 'resuming'}
            onClick={resume}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-md bg-orange-600 text-base font-semibold text-white disabled:opacity-50"
          >
            <CheckCircle2 size={20} />
            <span>我已完成验证</span>
          </button>
        </footer>
      </section>
    </main>
  );
}
```

- [ ] **Step 8: Route `/handoff` before the main app**

In `finance-web/src/App.tsx`, add import:

```typescript
import HandoffPage from './handoff/HandoffPage';
```

At the start of `App()` before auth/app state work that is not needed for public pages, add:

```typescript
if (window.location.pathname.toLowerCase() === '/handoff') {
  return <HandoffPage />;
}
```

Keep the existing public recon exceptions route intact.

- [ ] **Step 9: Run component tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- handoff-page.spec.tsx
```

Expected: PASS.

- [ ] **Step 10: Run TypeScript build**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run build
```

Expected: PASS.

- [ ] **Step 11: Start dev server and capture mobile screenshot**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

In a second terminal, capture the mobile screenshot:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx playwright screenshot --viewport-size=390,844 http://127.0.0.1:5173/handoff?t=demo /tmp/handoff-mobile.png
```

Open `/tmp/handoff-mobile.png` or inspect the screenshot artifact. Mocking the WS in a static page is not available, so this visual check verifies the invalid/connecting mobile shell does not overflow.

Expected: mobile viewport shows header, browser frame area, text input, and completed button without horizontal overflow or overlapping controls.

- [ ] **Step 12: Commit finance-web work**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/handoff/types.ts finance-web/src/handoff/handoffWs.ts finance-web/src/handoff/useHandoffSession.ts finance-web/src/handoff/HandoffViewport.tsx finance-web/src/handoff/HandoffPage.tsx finance-web/src/App.tsx finance-web/tests/components/handoff-page.spec.tsx
git commit -m "feat(handoff): add mobile remote control page"
```

---

## Task 5: End-to-end validation and service restart

**Files:**
- Modify only if validation finds defects in files touched by Tasks 1-4.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-mcp/tests/test_handoff_token.py finance-mcp/tests/test_handoff_session_db.py finance-mcp/tests/test_handoff_session_tools.py -v
pytest finance-agents/data-agent/tests/test_gateway_risk_waiting.py finance-agents/data-agent/tests/test_browser_agent_gateway.py finance-agents/data-agent/tests/test_browser_agent_ws_endpoint.py finance-agents/data-agent/tests/test_browser_handoff_gateway.py finance-agents/data-agent/tests/test_handoff_ws_endpoint.py -v
cd finance-agents/browser-agent
pytest tests/test_data_agent_ws.py tests/test_tally_client.py tests/test_dispatcher_loop.py tests/test_remote_control.py tests/test_playwright_navigate_risk_wait.py tests/test_risk_waiting_report.py -v
```

Expected: all focused Python tests PASS.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- handoff-page.spec.tsx
npm run build
```

Expected: Vitest and build PASS.

- [ ] **Step 3: Restart services**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected:

- finance-web starts on `http://localhost:5173`
- data-agent health responds on `http://localhost:8100/health`
- finance-mcp health responds on `http://localhost:3335/health`

- [ ] **Step 4: Smoke-test removed `/p/handoff` and new `/handoff` route**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
curl -I http://127.0.0.1:8100/p/handoff?t=demo
curl -I http://127.0.0.1:5173/handoff?t=demo
```

Expected:

- data-agent `/p/handoff` returns `404`.
- finance-web `/handoff?t=demo` returns the Vite app shell.

- [ ] **Step 5: In-memory relay smoke with two controllers**

Run the focused relay test that Task 2 added:

```bash
cd /Users/kevin/workspace/financial-ai
pytest finance-agents/data-agent/tests/test_browser_handoff_gateway.py::test_controller_open_starts_online_agent_and_revokes_previous finance-agents/data-agent/tests/test_browser_handoff_gateway.py::test_frame_routes_only_to_current_controller -v
```

These tests cover:

1. browser-agent WS with valid system token and `agent_id=agent-A`;
2. first `/handoff/ws?t=<valid token>` controller;
3. second `/handoff/ws?t=<same token>` controller.

Expected:

- first controller receives `controller_revoked`;
- second controller receives `session`;
- browser-agent receives `handoff_start` for the second controller;
- a `handoff_frame` from browser-agent routes only to the second controller.

- [ ] **Step 6: Manual mobile in-app browser checklist**

Run after services are reachable through the public/local domain used in notifications:

- DingTalk mobile opens `/handoff?t=<token>` and page fits in portrait.
- WeCom mobile opens `/handoff?t=<token>` and page fits in portrait.
- Feishu mobile opens `/handoff?t=<token>` and page fits in portrait.
- Text input sends a `text` event and can fill an SMS code field.
- Touch drag sends `mouse_down` / `mouse_move` / `mouse_up` with normalized coordinates.
- “我已完成验证” sends `resume_requested` and page enters `resuming`.

- [ ] **Step 7: Commit validation fixes if any**

If validation required fixes:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-mcp/auth/db.py finance-mcp/auth/handoff_token.py finance-mcp/tools/data_sources.py finance-mcp/unified_mcp_server.py
git add finance-agents/data-agent/services/browser_handoff_gateway.py finance-agents/data-agent/services/browser_agent_gateway.py finance-agents/data-agent/server.py finance-agents/data-agent/tools/mcp_client.py finance-agents/data-agent/graphs/platform/api.py
git add finance-agents/browser-agent/finance_browser_agent/remote_control.py finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/finance_browser_agent/playwright_runner.py
git add finance-web/src/handoff/types.ts finance-web/src/handoff/handoffWs.ts finance-web/src/handoff/useHandoffSession.ts finance-web/src/handoff/HandoffViewport.tsx finance-web/src/handoff/HandoffPage.tsx finance-web/src/App.tsx
git commit -m "fix(handoff): stabilize remote control validation"
```

If no fixes were needed, do not create an empty commit.

---

## Windows OS Backend Follow-Up Scope

Do not implement this in the current plan. If Playwright dragging cannot pass the real slider, add a new plan for a Windows-only backend with this work:

- Add `WindowsOsControlBackend` implementing the same `RemoteControlBackend` protocol.
- Locate the Chrome window for the active profile/job using Windows APIs.
- Capture the Chrome window or content area without including unrelated desktop content.
- Convert normalized browser-frame coordinates to screen coordinates with DPI scaling.
- Use Windows `SendInput` for mouse down/move/up, click, wheel, and keyboard input.
- Add startup self-check for OS, Chrome window, screenshot, and input injection.
- Select backend via `HANDOFF_CONTROL_BACKEND=playwright|windows_os`.
- Keep finance-mcp, data-agent, and finance-web protocols unchanged.

---

## Self-Review Checklist

- [ ] Spec coverage: stage 3a lifecycle, token semantics, audit metadata, expiry, `/p/handoff` removal, stage 3b duplex channel, browser-agent Playwright backend, stage 4 mobile-first finance-web page, and Windows OS fallback scope are covered.
- [ ] Placeholder scan: no `TBD`, no “write tests for this” without concrete test code, no unresolved file paths.
- [ ] Type consistency: `handoff_session_id`, `controller_id`, `sync_job_id`, `handoff_input`, `handoff_frame`, and status names match across finance-mcp, data-agent, browser-agent, and finance-web.
- [ ] Security constraints: token-only page does not expose credentials, profile paths, CDP ports, downloads, screenshot persistence, or input text audit.
- [ ] Verification commands: each task has focused tests and commit points; final task restarts services per repo instructions.
