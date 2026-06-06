# Browser Agent Assignment Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe browser-agent listing, binding listing, and explicit binding reassignment so browser playbook work can move from `collector-mac-1` to `collector-win-1` and later be assigned to additional collectors.

**Architecture:** Keep exact `agent_id` claim semantics unchanged. Add a focused `finance-mcp/browser_playbook/assignment.py` repository/service for agent status, binding listing, and reassignment transaction logic, then expose thin MCP handlers from `finance-mcp/tools/data_sources.py`.

**Tech Stack:** Python 3.12, finance-mcp MCP tools, PostgreSQL via `psycopg2`, pytest with existing fake connection/cursor tests.

---

## File Structure

- Create: `finance-mcp/browser_playbook/assignment.py`
  - Owns browser-agent assignment queries and reassignment transaction logic.
  - Keeps new control-plane logic out of the already-large `finance-mcp/auth/db.py` and `finance-mcp/tools/data_sources.py`.
- Modify: `finance-mcp/tools/data_sources.py`
  - Import assignment helpers.
  - Register MCP Tool schemas.
  - Add handler branches and thin auth/argument adapters.
- Modify: `finance-mcp/unified_mcp_server.py`
  - Add new tool names to `_DATA_SOURCE_TOOL_NAMES`.
- Modify: `finance-mcp/tests/test_browser_dispatcher.py`
  - Add focused tests for the new assignment helper module and MCP handlers.
  - Keep existing claim/default-agent tests intact.

---

### Task 1: Add Assignment Helper Tests

**Files:**
- Modify: `finance-mcp/tests/test_browser_dispatcher.py`
- Create later: `finance-mcp/browser_playbook/assignment.py`

- [ ] **Step 1: Add imports used by new tests**

At the top of `finance-mcp/tests/test_browser_dispatcher.py`, change:

```python
from pathlib import Path
from typing import Any
```

to:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
```

- [ ] **Step 2: Add fake DB primitives and assignment helper tests**

Append this block near the browser-agent tests, immediately after
`test_upsert_browser_agent_heartbeat_marks_online`:

```python
def test_list_browser_agents_computes_online_status(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    rows = [
        {
            "agent_id": "collector-win-1",
            "hostname": "win-host",
            "version": "v1",
            "status": "online",
            "capabilities": {"max_concurrency": 2},
            "last_heartbeat_at": now - timedelta(seconds=30),
        },
        {
            "agent_id": "collector-mac-1",
            "hostname": "mac-host",
            "version": "v1",
            "status": "online",
            "capabilities": {},
            "last_heartbeat_at": now - timedelta(seconds=240),
        },
    ]
    captured: dict[str, object] = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.list_browser_agents(
        company_id="company-001",
        online_threshold_seconds=180,
    )

    assert result["success"] is True
    assert result["count"] == 2
    assert result["agents"][0]["agent_id"] == "collector-win-1"
    assert result["agents"][0]["is_online"] is True
    assert result["agents"][1]["agent_id"] == "collector-mac-1"
    assert result["agents"][1]["is_online"] is False
    assert "FROM agents" in captured["sql"]
    assert captured["params"] == ("company-001",)


def test_list_browser_bindings_includes_running_job_flags(monkeypatch) -> None:
    from browser_playbook import assignment

    rows = [
        {
            "data_source_id": "source-001",
            "data_source_code": "shop-code-001",
            "data_source_name": "Shop 001",
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily",
            "agent_id": "collector-mac-1",
            "profile_status": "active",
            "playbook_status": "ok",
            "running_sync_job_ids": ["sync-001"],
            "has_running_job": True,
        }
    ]
    captured: dict[str, object] = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())

    result = assignment.list_browser_bindings(
        company_id="company-001",
        agent_id="collector-mac-1",
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["bindings"][0]["data_source_id"] == "source-001"
    assert result["bindings"][0]["has_running_job"] is True
    assert result["bindings"][0]["running_sync_job_ids"] == ["sync-001"]
    assert "JOIN data_sources ds" in captured["sql"]
    assert "srb.agent_id = %s" in captured["sql"]
    assert captured["params"] == ("company-001", "collector-mac-1")


def test_reassign_browser_bindings_dry_run_does_not_update(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    calls: list[str] = []

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            calls.append(sql)
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {"agent_id": "collector-win-1", "last_heartbeat_at": now, "status": "online"}
            return None

        def fetchall(self):
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": [],
                    "has_running_job": False,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            calls.append("commit")

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=True,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["matched_count"] == 1
    assert result["updated_count"] == 0
    assert "blocked_reason" not in result
    assert not any("UPDATE shop_runtime_bindings" in sql for sql in calls)


def test_reassign_browser_bindings_dry_run_reports_offline_target(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {
                    "agent_id": "collector-win-1",
                    "last_heartbeat_at": now - timedelta(minutes=10),
                    "status": "online",
                }
            return None

        def fetchall(self):
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": [],
                    "has_running_job": False,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=True,
        require_online=True,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["matched_count"] == 1
    assert result["updated_count"] == 0
    assert result["would_block"] is True
    assert result["blocked_reason"] == "target_agent_offline"


def test_reassign_browser_bindings_updates_when_safe(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    captured: dict[str, object] = {"commit_count": 0}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql
            captured["last_sql"] = sql
            captured["last_params"] = params

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {"agent_id": "collector-win-1", "last_heartbeat_at": now, "status": "online"}
            return None

        def fetchall(self):
            if "RETURNING" in self.sql and "UPDATE shop_runtime_bindings" in self.sql:
                return [{"data_source_id": "source-001", "agent_id": "collector-win-1"}]
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": [],
                    "has_running_job": False,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

        def commit(self):
            captured["commit_count"] = int(captured["commit_count"]) + 1

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=False,
    )

    assert result["success"] is True
    assert result["dry_run"] is False
    assert result["matched_count"] == 1
    assert result["updated_count"] == 1
    assert captured["commit_count"] == 1
    assert "UPDATE shop_runtime_bindings" in str(captured["last_sql"])


def test_reassign_browser_bindings_rejects_same_agent() -> None:
    from browser_playbook import assignment

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-win-1",
        to_agent_id="collector-win-1",
        dry_run=False,
    )

    assert result["success"] is False
    assert result["error"] == "source and target agent are the same"
    assert result["error_code"] == "same_agent"


def test_reassign_browser_bindings_rejects_offline_target_unless_forced(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {
                    "agent_id": "collector-win-1",
                    "last_heartbeat_at": now - timedelta(minutes=10),
                    "status": "online",
                }
            return None

        def fetchall(self):
            return []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=False,
        require_online=True,
        force_offline_target=False,
    )

    assert result["success"] is False
    assert result["error_code"] == "target_agent_offline"


def test_reassign_browser_bindings_blocks_running_jobs(monkeypatch) -> None:
    from browser_playbook import assignment

    now = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchone(self):
            if "FROM agents" in self.sql:
                return {"agent_id": "collector-win-1", "last_heartbeat_at": now, "status": "online"}
            return None

        def fetchall(self):
            return [
                {
                    "data_source_id": "source-001",
                    "data_source_code": "shop-code-001",
                    "data_source_name": "Shop 001",
                    "shop_id": "shop-001",
                    "playbook_id": "qianniu-daily",
                    "agent_id": "collector-mac-1",
                    "profile_status": "active",
                    "playbook_status": "ok",
                    "running_sync_job_ids": ["sync-running-001"],
                    "has_running_job": True,
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return _Cursor()

    class _ConnManager:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(assignment, "get_conn", lambda: _ConnManager())
    monkeypatch.setattr(assignment, "_now_utc", lambda: now)

    result = assignment.reassign_browser_bindings(
        company_id="company-001",
        from_agent_id="collector-mac-1",
        to_agent_id="collector-win-1",
        dry_run=False,
    )

    assert result["success"] is False
    assert result["error_code"] == "running_jobs_present"
    assert result["running_sync_job_ids"] == ["sync-running-001"]
```

- [ ] **Step 3: Run tests and confirm missing module failure**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest finance-mcp/tests/test_browser_dispatcher.py::test_list_browser_agents_computes_online_status -q
```

Expected: FAIL with `ImportError` or `cannot import name 'assignment'` because `finance-mcp/browser_playbook/assignment.py` does not exist yet.

---

### Task 2: Implement Assignment Helper Module

**Files:**
- Create: `finance-mcp/browser_playbook/assignment.py`
- Test: `finance-mcp/tests/test_browser_dispatcher.py`

- [ ] **Step 1: Create assignment helper module**

Create `finance-mcp/browser_playbook/assignment.py` with:

```python
"""Browser-agent assignment and migration helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2.extras

from auth.db import get_conn

logger = logging.getLogger(__name__)

DEFAULT_ONLINE_THRESHOLD_SECONDS = 180


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = value
    return normalized


def _is_online(row: dict[str, Any], *, online_threshold_seconds: int) -> bool:
    heartbeat = row.get("last_heartbeat_at")
    if not isinstance(heartbeat, datetime):
        return False
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    elapsed = (_now_utc() - heartbeat.astimezone(timezone.utc)).total_seconds()
    return str(row.get("status") or "") == "online" and elapsed <= online_threshold_seconds


def _target_agent_status(
    cur: Any,
    *,
    company_id: str,
    agent_id: str,
    online_threshold_seconds: int,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT agent_id, hostname, version, status, capabilities, last_heartbeat_at
        FROM agents
        WHERE company_id = %s
          AND agent_id = %s
        LIMIT 1
        """,
        (company_id, agent_id),
    )
    row = cur.fetchone()
    if not row:
        return {"agent_id": agent_id, "is_online": False, "exists": False}
    normalized = _normalize_row(dict(row))
    normalized["exists"] = True
    normalized["is_online"] = _is_online(dict(row), online_threshold_seconds=online_threshold_seconds)
    return normalized


def list_browser_agents(
    *,
    company_id: str,
    online_threshold_seconds: int = DEFAULT_ONLINE_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    threshold = max(1, int(online_threshold_seconds or DEFAULT_ONLINE_THRESHOLD_SECONDS))
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT agent_id, hostname, version, status, capabilities, last_heartbeat_at
                    FROM agents
                    WHERE company_id = %s
                    ORDER BY last_heartbeat_at DESC NULLS LAST, agent_id ASC
                    """,
                    (company_id,),
                )
                agents: list[dict[str, Any]] = []
                for row in cur.fetchall() or []:
                    raw = dict(row)
                    normalized = _normalize_row(raw)
                    normalized["is_online"] = _is_online(
                        raw,
                        online_threshold_seconds=threshold,
                    )
                    agents.append(normalized)
                return {"success": True, "count": len(agents), "agents": agents}
    except Exception as exc:  # noqa: BLE001
        logger.error("list_browser_agents failed (company_id=%s): %s", company_id, exc)
        return {"success": False, "error": str(exc), "count": 0, "agents": []}


def _binding_filters_sql(
    *,
    agent_id: str = "",
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if agent_id:
        clauses.append("srb.agent_id = %s")
        params.append(agent_id)
    if data_source_id:
        clauses.append("srb.data_source_id = %s")
        params.append(data_source_id)
    if shop_id:
        clauses.append("srb.shop_id = %s")
        params.append(shop_id)
    if playbook_id:
        clauses.append("srb.playbook_id = %s")
        params.append(playbook_id)
    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


def _list_browser_bindings_in_cursor(
    cur: Any,
    *,
    company_id: str,
    agent_id: str = "",
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
    lock_rows: bool = False,
) -> list[dict[str, Any]]:
    filters_sql, filter_params = _binding_filters_sql(
        agent_id=agent_id,
        data_source_id=data_source_id,
        shop_id=shop_id,
        playbook_id=playbook_id,
    )
    lock_sql = " FOR UPDATE OF srb" if lock_rows else ""
    cur.execute(
        f"""
        SELECT
            srb.data_source_id,
            ds.code AS data_source_code,
            ds.name AS data_source_name,
            srb.shop_id,
            srb.playbook_id,
            srb.agent_id,
            srb.profile_status,
            srb.playbook_status,
            COALESCE(running.running_sync_job_ids, ARRAY[]::uuid[]) AS running_sync_job_ids,
            COALESCE(array_length(running.running_sync_job_ids, 1), 0) > 0 AS has_running_job
        FROM shop_runtime_bindings srb
        JOIN data_sources ds
          ON ds.company_id = srb.company_id
         AND ds.id = srb.data_source_id
         AND ds.source_kind = 'browser_playbook'
        LEFT JOIN LATERAL (
            SELECT array_agg(sj.id ORDER BY sj.created_at ASC) AS running_sync_job_ids
            FROM sync_jobs sj
            WHERE sj.company_id = srb.company_id
              AND sj.data_source_id = srb.data_source_id
              AND sj.job_status = 'running'
        ) running ON TRUE
        WHERE srb.company_id = %s
        {filters_sql}
        ORDER BY ds.name ASC, srb.shop_id ASC, srb.data_source_id ASC
        {lock_sql}
        """,
        tuple([company_id, *filter_params]),
    )
    bindings: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        normalized = _normalize_row(dict(row))
        normalized["data_source_id"] = str(normalized.get("data_source_id") or "")
        normalized["running_sync_job_ids"] = [
            str(sync_job_id) for sync_job_id in normalized.get("running_sync_job_ids") or []
        ]
        normalized["has_running_job"] = bool(normalized.get("has_running_job"))
        bindings.append(normalized)
    return bindings


def list_browser_bindings(
    *,
    company_id: str,
    agent_id: str = "",
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
) -> dict[str, Any]:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                bindings = _list_browser_bindings_in_cursor(
                    cur,
                    company_id=company_id,
                    agent_id=agent_id,
                    data_source_id=data_source_id,
                    shop_id=shop_id,
                    playbook_id=playbook_id,
                )
                return {"success": True, "count": len(bindings), "bindings": bindings}
    except Exception as exc:  # noqa: BLE001
        logger.error("list_browser_bindings failed (company_id=%s): %s", company_id, exc)
        return {"success": False, "error": str(exc), "count": 0, "bindings": []}


def reassign_browser_bindings(
    *,
    company_id: str,
    from_agent_id: str,
    to_agent_id: str,
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
    dry_run: bool = True,
    require_online: bool = True,
    force_offline_target: bool = False,
    online_threshold_seconds: int = DEFAULT_ONLINE_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    source_agent = str(from_agent_id or "").strip()
    target_agent = str(to_agent_id or "").strip()
    if not source_agent:
        return {"success": False, "error": "missing from_agent_id", "error_code": "missing_from_agent_id"}
    if not target_agent:
        return {"success": False, "error": "missing to_agent_id", "error_code": "missing_to_agent_id"}
    if source_agent == target_agent:
        return {
            "success": False,
            "error": "source and target agent are the same",
            "error_code": "same_agent",
        }

    threshold = max(1, int(online_threshold_seconds or DEFAULT_ONLINE_THRESHOLD_SECONDS))
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                target_status = _target_agent_status(
                    cur,
                    company_id=company_id,
                    agent_id=target_agent,
                    online_threshold_seconds=threshold,
                )
                target_offline_block = (
                    require_online
                    and not force_offline_target
                    and not target_status.get("is_online")
                )
                if target_offline_block and not dry_run:
                    return {
                        "success": False,
                        "error": f"target agent is not online: {target_agent}",
                        "error_code": "target_agent_offline",
                        "target_agent": target_status,
                    }

                bindings = _list_browser_bindings_in_cursor(
                    cur,
                    company_id=company_id,
                    agent_id=source_agent,
                    data_source_id=data_source_id,
                    shop_id=shop_id,
                    playbook_id=playbook_id,
                    lock_rows=not dry_run,
                )
                running_sync_job_ids = [
                    sync_job_id
                    for binding in bindings
                    for sync_job_id in binding.get("running_sync_job_ids", [])
                ]
                if running_sync_job_ids:
                    return {
                        "success": False,
                        "error": "matched bindings have running browser sync jobs",
                        "error_code": "running_jobs_present",
                        "dry_run": dry_run,
                        "matched_count": len(bindings),
                        "bindings": bindings,
                        "running_sync_job_ids": running_sync_job_ids,
                    }

                if dry_run:
                    return {
                        "success": True,
                        "dry_run": True,
                        "matched_count": len(bindings),
                        "updated_count": 0,
                        "bindings": bindings,
                        "target_agent": target_status,
                        "would_block": bool(target_offline_block),
                        "blocked_reason": "target_agent_offline" if target_offline_block else "",
                    }

                if not bindings:
                    conn.commit()
                    return {
                        "success": True,
                        "dry_run": False,
                        "matched_count": 0,
                        "updated_count": 0,
                        "bindings": [],
                        "target_agent": target_status,
                    }

                data_source_ids = [binding["data_source_id"] for binding in bindings]
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings
                    SET agent_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND agent_id = %s
                      AND data_source_id = ANY(%s::uuid[])
                    RETURNING data_source_id, agent_id
                    """,
                    (target_agent, company_id, source_agent, data_source_ids),
                )
                updated_rows = cur.fetchall() or []
                conn.commit()
                return {
                    "success": True,
                    "dry_run": False,
                    "matched_count": len(bindings),
                    "updated_count": len(updated_rows),
                    "bindings": bindings,
                    "target_agent": target_status,
                }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "reassign_browser_bindings failed (company_id=%s, from=%s, to=%s): %s",
            company_id,
            source_agent,
            target_agent,
            exc,
        )
        return {"success": False, "error": str(exc), "error_code": "database_error"}
```

- [ ] **Step 2: Run helper tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest \
  finance-mcp/tests/test_browser_dispatcher.py::test_list_browser_agents_computes_online_status \
  finance-mcp/tests/test_browser_dispatcher.py::test_list_browser_bindings_includes_running_job_flags \
  finance-mcp/tests/test_browser_dispatcher.py::test_reassign_browser_bindings_dry_run_does_not_update \
  finance-mcp/tests/test_browser_dispatcher.py::test_reassign_browser_bindings_dry_run_reports_offline_target \
  finance-mcp/tests/test_browser_dispatcher.py::test_reassign_browser_bindings_updates_when_safe \
  finance-mcp/tests/test_browser_dispatcher.py::test_reassign_browser_bindings_rejects_same_agent \
  finance-mcp/tests/test_browser_dispatcher.py::test_reassign_browser_bindings_rejects_offline_target_unless_forced \
  finance-mcp/tests/test_browser_dispatcher.py::test_reassign_browser_bindings_blocks_running_jobs \
  -q
```

Expected: PASS for all seven helper tests.

- [ ] **Step 3: Commit helper module and tests**

Run:

```bash
git add finance-mcp/browser_playbook/assignment.py finance-mcp/tests/test_browser_dispatcher.py
git commit -m "feat: add browser agent assignment helpers"
```

Expected: commit succeeds with only those two paths staged.

---

### Task 3: Add MCP Tool Schemas And Handlers

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Modify: `finance-mcp/unified_mcp_server.py`
- Modify: `finance-mcp/tests/test_browser_dispatcher.py`

- [ ] **Step 1: Write MCP handler tests**

Append these tests after `test_browser_agent_heartbeat_tool_calls_helper`:

```python
def test_browser_agent_list_tool_calls_assignment(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()
    captured: dict[str, object] = {}

    def fake_list_browser_agents(**kwargs):
        captured.update(kwargs)
        return {"success": True, "count": 1, "agents": [{"agent_id": "collector-win-1"}]}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001"},
    )
    monkeypatch.setattr(data_sources.browser_assignment, "list_browser_agents", fake_list_browser_agents)

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_agent_list",
            {"auth_token": "user-token", "online_threshold_seconds": 180},
        )
    )

    assert result["success"] is True
    assert result["agents"][0]["agent_id"] == "collector-win-1"
    assert captured == {"company_id": "company-001", "online_threshold_seconds": 180}


def test_browser_binding_list_tool_calls_assignment(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()
    captured: dict[str, object] = {}

    def fake_list_browser_bindings(**kwargs):
        captured.update(kwargs)
        return {"success": True, "count": 1, "bindings": [{"agent_id": "collector-mac-1"}]}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001"},
    )
    monkeypatch.setattr(data_sources.browser_assignment, "list_browser_bindings", fake_list_browser_bindings)

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_binding_list",
            {
                "auth_token": "user-token",
                "agent_id": "collector-mac-1",
                "source_id": "source-001",
                "shop_id": "shop-001",
                "playbook_id": "qianniu-daily",
            },
        )
    )

    assert result["success"] is True
    assert captured == {
        "company_id": "company-001",
        "agent_id": "collector-mac-1",
        "data_source_id": "source-001",
        "shop_id": "shop-001",
        "playbook_id": "qianniu-daily",
    }


def test_browser_binding_reassign_tool_defaults_to_dry_run(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()
    captured: dict[str, object] = {}

    def fake_reassign_browser_bindings(**kwargs):
        captured.update(kwargs)
        return {"success": True, "dry_run": True, "matched_count": 2, "updated_count": 0}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001"},
    )
    monkeypatch.setattr(
        data_sources.browser_assignment,
        "reassign_browser_bindings",
        fake_reassign_browser_bindings,
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_binding_reassign",
            {
                "auth_token": "user-token",
                "from_agent_id": "collector-mac-1",
                "to_agent_id": "collector-win-1",
            },
        )
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert captured["company_id"] == "company-001"
    assert captured["from_agent_id"] == "collector-mac-1"
    assert captured["to_agent_id"] == "collector-win-1"
    assert captured["dry_run"] is True
    assert captured["require_online"] is True
    assert captured["force_offline_target"] is False


def test_browser_binding_reassign_tool_parses_false_boolean_strings(monkeypatch) -> None:
    import asyncio

    data_sources = _import_mcp_data_sources()
    captured: dict[str, object] = {}

    def fake_reassign_browser_bindings(**kwargs):
        captured.update(kwargs)
        return {"success": True, "dry_run": False, "matched_count": 0, "updated_count": 0}

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-001"},
    )
    monkeypatch.setattr(
        data_sources.browser_assignment,
        "reassign_browser_bindings",
        fake_reassign_browser_bindings,
    )

    result = asyncio.run(
        data_sources.handle_tool_call(
            "browser_binding_reassign",
            {
                "auth_token": "user-token",
                "from_agent_id": "collector-mac-1",
                "to_agent_id": "collector-win-1",
                "dry_run": "false",
                "require_online": "false",
                "force_offline_target": "true",
            },
        )
    )

    assert result["success"] is True
    assert captured["dry_run"] is False
    assert captured["require_online"] is False
    assert captured["force_offline_target"] is True
```

- [ ] **Step 2: Run handler test and confirm missing handler failure**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest finance-mcp/tests/test_browser_dispatcher.py::test_browser_agent_list_tool_calls_assignment -q
```

Expected: FAIL because `tools.data_sources` has no `browser_assignment` import or `browser_agent_list` handler yet.

- [ ] **Step 3: Import assignment module in data_sources**

In `finance-mcp/tools/data_sources.py`, add this import near the other `browser_playbook` imports:

```python
from browser_playbook import assignment as browser_assignment
```

- [ ] **Step 4: Add Tool definitions**

In `finance-mcp/tools/data_sources.py`, insert these `Tool(...)` blocks after the existing
`browser_agent_heartbeat` Tool block:

```python
        Tool(
            name="browser_agent_list",
            description="运维专用：列出当前公司的 browser-agent 采集节点及在线状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "online_threshold_seconds": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="browser_binding_list",
            description="运维专用：列出 browser_playbook 运行绑定及当前分配的采集机。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "agent_id": {"type": "string"},
                    **source_id_schema,
                    "shop_id": {"type": "string"},
                    "playbook_id": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="browser_binding_reassign",
            description="运维专用：将 browser_playbook 绑定从一个采集机迁移到另一个采集机。默认 dry_run=true，只预览不更新。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "from_agent_id": {"type": "string"},
                    "to_agent_id": {"type": "string"},
                    **source_id_schema,
                    "shop_id": {"type": "string"},
                    "playbook_id": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                    "require_online": {"type": "boolean"},
                    "force_offline_target": {"type": "boolean"},
                    "online_threshold_seconds": {"type": "integer"},
                },
                "required": ["auth_token", "from_agent_id", "to_agent_id"],
            },
        ),
```

- [ ] **Step 5: Add handle_tool_call branches**

In `finance-mcp/tools/data_sources.py`, add these branches after the existing
`browser_agent_heartbeat` branch:

```python
        if name == "browser_agent_list":
            return await _handle_browser_agent_list(arguments)
        if name == "browser_binding_list":
            return await _handle_browser_binding_list(arguments)
        if name == "browser_binding_reassign":
            return await _handle_browser_binding_reassign(arguments)
```

- [ ] **Step 6: Add thin handlers**

In `finance-mcp/tools/data_sources.py`, add these handlers immediately after
`_handle_browser_agent_heartbeat`:

```python
async def _handle_browser_agent_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(str(arguments.get("auth_token") or ""))
    threshold = max(1, int(arguments.get("online_threshold_seconds") or 180))
    return browser_assignment.list_browser_agents(
        company_id=str(user["company_id"]),
        online_threshold_seconds=threshold,
    )


async def _handle_browser_binding_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(str(arguments.get("auth_token") or ""))
    return browser_assignment.list_browser_bindings(
        company_id=str(user["company_id"]),
        agent_id=str(arguments.get("agent_id") or "").strip(),
        data_source_id=_source_id_from_args(arguments),
        shop_id=str(arguments.get("shop_id") or "").strip(),
        playbook_id=str(arguments.get("playbook_id") or "").strip(),
    )


async def _handle_browser_binding_reassign(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(str(arguments.get("auth_token") or ""))
    return browser_assignment.reassign_browser_bindings(
        company_id=str(user["company_id"]),
        from_agent_id=str(arguments.get("from_agent_id") or "").strip(),
        to_agent_id=str(arguments.get("to_agent_id") or "").strip(),
        data_source_id=_source_id_from_args(arguments),
        shop_id=str(arguments.get("shop_id") or "").strip(),
        playbook_id=str(arguments.get("playbook_id") or "").strip(),
        dry_run=_normalize_bool(arguments.get("dry_run"), default=True),
        require_online=_normalize_bool(arguments.get("require_online"), default=True),
        force_offline_target=_normalize_bool(arguments.get("force_offline_target"), default=False),
        online_threshold_seconds=max(1, int(arguments.get("online_threshold_seconds") or 180)),
    )
```

- [ ] **Step 7: Register tool names in unified_mcp_server**

In `finance-mcp/unified_mcp_server.py`, add these names to `_DATA_SOURCE_TOOL_NAMES` near
`browser_agent_heartbeat`:

```python
    "browser_agent_list",
    "browser_binding_list",
    "browser_binding_reassign",
```

- [ ] **Step 8: Run MCP handler tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest \
  finance-mcp/tests/test_browser_dispatcher.py::test_browser_agent_list_tool_calls_assignment \
  finance-mcp/tests/test_browser_dispatcher.py::test_browser_binding_list_tool_calls_assignment \
  finance-mcp/tests/test_browser_dispatcher.py::test_browser_binding_reassign_tool_defaults_to_dry_run \
  finance-mcp/tests/test_browser_dispatcher.py::test_browser_binding_reassign_tool_parses_false_boolean_strings \
  -q
```

Expected: PASS for all four handler tests.

- [ ] **Step 9: Commit MCP tool wiring**

Run:

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/unified_mcp_server.py finance-mcp/tests/test_browser_dispatcher.py
git commit -m "feat: expose browser agent assignment tools"
```

Expected: commit succeeds with only those three paths staged.

---

### Task 4: Regression Verification

**Files:**
- Verify: `finance-mcp/auth/db.py`
- Verify: `finance-mcp/tools/data_sources.py`
- Verify: `finance-mcp/tests/test_browser_dispatcher.py`
- Verify: `finance-mcp/tests/test_browser_playbook_connector.py`

- [ ] **Step 1: Run focused browser dispatcher tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest finance-mcp/tests/test_browser_dispatcher.py -q
```

Expected: PASS. This verifies heartbeat, claim exact `agent_id` filtering, startup cleanup, stale reaper, and the new assignment helpers/tools.

- [ ] **Step 2: Run browser playbook registration default-agent regression**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest \
  finance-mcp/tests/test_browser_playbook_connector.py::test_register_browser_playbook_respects_env_default_agent_id \
  -q
```

Expected: PASS. This confirms new playbook registration still honors `BROWSER_AGENT_DEFAULT_AGENT_ID`.

- [ ] **Step 3: Run finance-mcp browser-related tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
.venv/bin/python -m pytest finance-mcp/tests/test_browser_*.py -q
```

Expected: PASS. If unrelated existing tests fail, record the failing test names and error messages before deciding whether they are in scope.

- [ ] **Step 4: Verify no accidental claim routing change**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
grep -n "srb.agent_id = %s" finance-mcp/auth/db.py
```

Expected: output still includes the `claim_next_browser_sync_job` filter line, proving jobs remain bound to exact collector id.

- [ ] **Step 5: Check git status**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git status --short
```

Expected: only intentional changes remain. If unrelated pre-existing working tree changes are present, leave them untouched and mention them in the final implementation summary.

- [ ] **Step 6: Commit verification note only if needed**

If Task 4 required a small code/test fix, commit it:

```bash
git add <only-files-fixed-in-task-4>
git commit -m "test: verify browser agent assignment routing"
```

Expected: commit succeeds. If no fixes were needed, do not create an empty commit.

---

## Manual Production Use After Implementation

After Windows is configured and heartbeat is visible:

1. Call `browser_agent_list` to confirm `collector-win-1` is online.
2. Call `browser_binding_list` with `agent_id=collector-mac-1` to inspect current bindings.
3. Call `browser_binding_reassign` with:
   - `from_agent_id=collector-mac-1`
   - `to_agent_id=collector-win-1`
   - `dry_run=true`
4. If no running jobs are reported, call the same tool with `dry_run=false`.
5. Set ECS `BROWSER_AGENT_DEFAULT_AGENT_ID=collector-win-1` so future registrations default to Windows.

Do not restart local services as part of implementing these code changes unless explicitly requested.
