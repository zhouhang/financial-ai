# Browser-Job Reaper Resilience (Tier 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop browser sync_jobs (and the recon runs they block) from silently hanging in `running` — via source-side self-heal plus an independent finance-cron reaper net.

**Architecture:** Two defense lines. (1) Source self-heal: the browser-agent dispatcher checks the completion write result and re-fails+retries instead of falsely logging success; capture-file writes are made idempotent so retries are safe. (2) Independent net: the queue reapers move from the browser-agent into finance-cron, plus a new heartbeat-stale reaper marks orphaned `running` jobs of dead agents as failed so the recon run fails visibly + alerts.

**Tech Stack:** Python 3.12, PostgreSQL (psycopg2), MCP (SSE) tools in finance-mcp, APScheduler in finance-cron, pytest (DB-free fake-cursor unit tests + asyncio dispatcher tests).

**Spec:** `docs/superpowers/specs/2026-06-02-browser-job-reaper-resilience-design.md`

---

## File Structure

- `finance-mcp/auth/migrations/038_browser_capture_files_idempotent.sql` — **create**: unique index for idempotent capture-file upsert.
- `finance-mcp/auth/db.py` — **modify**: `insert_browser_capture_files` (ON CONFLICT); **add** `reap_stale_agent_running_jobs`.
- `finance-mcp/tools/data_sources.py` — **modify**: register tool `browser_sync_job_reap_stale_agents`, add dispatch + handler.
- `finance-mcp/tests/test_browser_capture_files.py` — **modify**: idempotent-write assertion.
- `finance-mcp/tests/test_reap_stale_agents.py` — **create**: SQL-shape unit test for the new reaper.
- `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py` — **modify**: check completion result.
- `finance-agents/browser-agent/tests/test_dispatcher_loop.py` — **modify**: completion-write-failure test.
- `finance-agents/browser-agent/service.py` — **modify**: remove `_waiting_reconciler`.
- `finance-agents/browser-agent/tests/test_service_wiring.py` — **create**: assert reconciler no longer wired.
- `finance-cron/mcp_client.py` — **modify**: add 4 reaper tool wrappers.
- `finance-cron/scheduler_service.py` — **modify**: add reaper interval job + config fields.
- `finance-cron/tests/test_reaper_cycle.py` — **create**: assert cron calls the right tools in order.

---

## Task 1: Idempotent capture-file writes (#1 slice)

**Files:**
- Create: `finance-mcp/auth/migrations/038_browser_capture_files_idempotent.sql`
- Modify: `finance-mcp/auth/db.py:8167-8181` (the `execute_values` INSERT inside `insert_browser_capture_files`)
- Test: `finance-mcp/tests/test_browser_capture_files.py`

- [ ] **Step 1: Write the migration**

Create `finance-mcp/auth/migrations/038_browser_capture_files_idempotent.sql`:

```sql
-- 038: make browser_capture_files writes idempotent so completion retries don't duplicate audit rows.
-- A retried sync_job re-reports the same (sync_job_id, storage_path); upsert instead of insert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_browser_capture_files_sync_job_storage_path
    ON public.browser_capture_files (sync_job_id, storage_path)
    WHERE sync_job_id IS NOT NULL;
```

- [ ] **Step 2: Apply the migration to the dev DB**

Run:
```bash
PGPASSWORD=123456 psql -h localhost -p 5432 -U tally_user -d tally \
  -v ON_ERROR_STOP=1 -f finance-mcp/auth/migrations/038_browser_capture_files_idempotent.sql
```
Expected: `CREATE INDEX` (re-running prints nothing new and still exits 0).

- [ ] **Step 3: Write the failing test**

Add to `finance-mcp/tests/test_browser_capture_files.py` (reuse the file's existing `FakeCursor`/`FakeConn`/`FakeConnManager` + `monkeypatch.setattr(auth_db, "get_conn", ...)` pattern; if that file has no fake-cursor harness, copy the one from `finance-mcp/tests/test_browser_waiting_data_queue.py`):

```python
def test_insert_browser_capture_files_upserts_on_conflict(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    # execute_values writes via cur.execute under the hood for our FakeCursor; capture the SQL.
    monkeypatch.setattr(
        auth_db.psycopg2.extras,
        "execute_values",
        lambda cur, sql, rows, template=None, **kw: cur.execute(sql, tuple(rows)),
    )

    auth_db.insert_browser_capture_files(
        company_id="c1", data_source_id="d1", dataset_id="ds1", sync_job_id="j1",
        resource_key="rk", shop_id="s1", playbook_id="p1", biz_date="2026-05-31",
        capture_files=[{"storage_path": "/tmp/a.csv", "checksum": "x", "row_count": 1}],
    )

    sql = "\n".join(cursor.sql)
    assert "ON CONFLICT (sync_job_id, storage_path)" in sql
    assert "DO UPDATE" in sql
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd finance-mcp && python -m pytest tests/test_browser_capture_files.py::test_insert_browser_capture_files_upserts_on_conflict -v`
Expected: FAIL — assertion error, current SQL has no `ON CONFLICT`.

- [ ] **Step 5: Add ON CONFLICT to the INSERT**

In `finance-mcp/auth/db.py`, change the `execute_values` SQL inside `insert_browser_capture_files` (currently ends with `) VALUES %s`) to:

```python
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO browser_capture_files (
                        company_id, data_source_id, dataset_id, sync_job_id, resource_key,
                        shop_id, playbook_id, biz_date, storage_path, encoding, checksum, row_count,
                        storage_provider, storage_bucket, storage_key, storage_uri, content_type, size_bytes
                    ) VALUES %s
                    ON CONFLICT (sync_job_id, storage_path) DO UPDATE SET
                        encoding = EXCLUDED.encoding,
                        checksum = EXCLUDED.checksum,
                        row_count = EXCLUDED.row_count,
                        storage_provider = EXCLUDED.storage_provider,
                        storage_bucket = EXCLUDED.storage_bucket,
                        storage_key = EXCLUDED.storage_key,
                        storage_uri = EXCLUDED.storage_uri,
                        content_type = EXCLUDED.content_type,
                        size_bytes = EXCLUDED.size_bytes,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    rows,
                    template=(
                        "(%s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, "
                        "%s, %s, %s, %s, %s, %s)"
                    ),
                )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd finance-mcp && python -m pytest tests/test_browser_capture_files.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 7: Commit**

```bash
git add finance-mcp/auth/migrations/038_browser_capture_files_idempotent.sql finance-mcp/auth/db.py finance-mcp/tests/test_browser_capture_files.py
git commit -m "feat: make browser_capture_files writes idempotent (ON CONFLICT)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Dispatcher checks completion write result (#2)

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py:105-123`
- Test: `finance-agents/browser-agent/tests/test_dispatcher_loop.py`

- [ ] **Step 1: Write the failing test**

Add to `finance-agents/browser-agent/tests/test_dispatcher_loop.py`. First extend the existing `FakeClient` so success-marking can be made to fail:

```python
class FailingCompleteClient(FakeClient):
    async def mark_browser_job_success(self, payload: dict) -> dict:
        self.completed.append(payload)
        return {"success": False, "error": "column \"storage_provider\" does not exist"}


@pytest.mark.asyncio
async def test_dispatcher_retries_when_completion_write_fails() -> None:
    job = {
        "id": "sync-001", "shop_id": "shop-001",
        "playbook_body": {"steps": [], "output": {"columns": [], "item_key_fields": []}, "quality_gate": {}},
        "request_payload": {"biz_date": "2026-05-31"},
    }
    client = FailingCompleteClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    # Must NOT report success when the server rejected the completion write.
    assert result["status"] != "success"
    assert client.failed, "expected a retryable failure to be recorded"
    assert client.failed[0]["retryable"] is True
    assert client.failed[0]["fail_reason"] == "COMPLETE_PERSIST_FAILED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd finance-agents/browser-agent && python -m pytest tests/test_dispatcher_loop.py::test_dispatcher_retries_when_completion_write_fails -v`
Expected: FAIL — current code logs success and returns `{"status": "success"}` regardless of the result.

- [ ] **Step 3: Make the success branch check the result**

In `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`, replace the success branch (lines 105-123, the `if isinstance(result, dict) and result.get("status") == "success":` block) with:

```python
        if isinstance(result, dict) and result.get("status") == "success":
            ack = await self.client.mark_browser_job_success(
                {
                    "sync_job_id": sync_job_id,
                    "summary": {
                        "record_count": len(result.get("records") or []),
                        "quality_summary": result.get("quality_summary") or {},
                    },
                    "records": list(result.get("records") or []),
                    "capture_files": list(result.get("capture_files") or []),
                }
            )
            if not (isinstance(ack, dict) and ack.get("success", True) is not False):
                # Runner succeeded but the server could not persist the result. Do NOT claim
                # success — re-fail as retryable so the job re-collects and re-completes.
                error_message = str((ack or {}).get("error") or "completion persist failed")
                await self.client.mark_browser_job_failed(
                    {
                        "sync_job_id": sync_job_id,
                        "fail_reason": "COMPLETE_PERSIST_FAILED",
                        "error_message": error_message,
                        "retryable": True,
                        "max_attempts": 3,
                        "retry_delay_seconds": 60,
                    }
                )
                logger.warning(
                    "browser completion persist failed, re-failing as retryable: sync_job_id=%s error=%s",
                    sync_job_id,
                    error_message,
                )
                return {"status": "failed", "sync_job_id": sync_job_id, "retryable": True}
            logger.info(
                "browser runner succeeded: sync_job_id=%s record_count=%s capture_file_count=%s",
                sync_job_id,
                len(result.get("records") or []),
                len(result.get("capture_files") or []),
            )
            return {"status": "success", "sync_job_id": sync_job_id}
```

Note: `ack.get("success", True) is not False` treats a missing `success` key as success (back-compat with clients/tests that return bare `{}`), and only an explicit `False` triggers the retry path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd finance-agents/browser-agent && python -m pytest tests/test_dispatcher_loop.py -v`
Expected: PASS — new test passes and `test_dispatcher_completes_successful_job` still passes (FakeClient returns `{"success": True}`).

- [ ] **Step 5: Commit**

```bash
git add finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/tests/test_dispatcher_loop.py
git commit -m "fix: dispatcher re-fails retryable when completion write is rejected

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Heartbeat-stale reaper (#4 server side)

**Files:**
- Modify: `finance-mcp/auth/db.py` (add `reap_stale_agent_running_jobs` next to `fail_running_browser_sync_jobs_for_agent`, ~line 6554)
- Modify: `finance-mcp/tools/data_sources.py` (tool registration after the `browser_sync_job_startup_cleanup` Tool block ~line 5977; dispatch after line 6165; handler after `_handle_browser_sync_job_startup_cleanup` ~line 9704)
- Test: `finance-mcp/tests/test_reap_stale_agents.py`

- [ ] **Step 1: Write the failing DB-shape test**

Create `finance-mcp/tests/test_reap_stale_agents.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


class FakeCursor:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.rowcount = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.sql.append(sql)
        self.params.append(params or ())

    def fetchall(self) -> list[dict]:
        return [{"id": "sync-stale-1"}]


class FakeConn:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self, *args, **kwargs) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        return None


class FakeConnManager:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    def __enter__(self) -> FakeConn:
        return FakeConn(self.cursor)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_reap_stale_agent_running_jobs_filters_and_threshold(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    result = auth_db.reap_stale_agent_running_jobs(stale_after_seconds=180)

    sql = "\n".join(cursor.sql)
    assert "job_status = 'running'" in sql
    assert "source_kind = 'browser_playbook'" in sql
    assert "AGENT_HEARTBEAT_LOST" in sql
    assert "last_heartbeat_at" in sql
    # threshold passed as a parameter
    assert cursor.params[0][0] == 180
    assert result["failed_count"] == 1
    assert result["sync_job_ids"] == ["sync-stale-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd finance-mcp && python -m pytest tests/test_reap_stale_agents.py -v`
Expected: FAIL — `AttributeError: module 'auth.db' has no attribute 'reap_stale_agent_running_jobs'`.

- [ ] **Step 3: Implement `reap_stale_agent_running_jobs`**

In `finance-mcp/auth/db.py`, add immediately after `fail_running_browser_sync_jobs_for_agent` (after its `return` at ~line 6553):

```python
def reap_stale_agent_running_jobs(*, stale_after_seconds: int = 180) -> dict[str, Any]:
    """Fail browser_playbook sync_jobs left 'running' by agents whose heartbeat has gone stale.

    This is the independent (finance-cron-driven) safety net for the case where the whole
    browser-agent process dies mid/after a job: its heartbeat stops, so after
    ``stale_after_seconds`` we presume the agent dead and mark its in-flight running jobs
    failed (AGENT_HEARTBEAT_LOST). The recon-queue 'fail_failed' reaper then cascades the
    failure to the blocked execution_run. Healthy agents (fresh heartbeat) are never touched.
    """
    threshold = max(1, int(stale_after_seconds))
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET job_status = 'failed',
                        browser_fail_reason = 'AGENT_HEARTBEAT_LOST',
                        error_message = 'AGENT_HEARTBEAT_LOST: browser-agent heartbeat stale, job presumed orphaned',
                        next_retry_at = NULL,
                        completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE sync_jobs.job_status = 'running'
                      AND EXISTS (
                          SELECT 1
                          FROM data_sources ds
                          JOIN shop_runtime_bindings srb
                            ON srb.company_id = sync_jobs.company_id
                           AND srb.data_source_id = sync_jobs.data_source_id
                          JOIN agents a
                            ON a.company_id = srb.company_id
                           AND a.agent_id = srb.agent_id
                          WHERE ds.id = sync_jobs.data_source_id
                            AND ds.source_kind = 'browser_playbook'
                            AND (
                                a.last_heartbeat_at IS NULL
                                OR a.last_heartbeat_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                            )
                      )
                    RETURNING sync_jobs.id
                    """,
                    (threshold,),
                )
                rows = cur.fetchall() or []
                conn.commit()
    except Exception as e:
        logger.error(f"reap_stale_agent_running_jobs 失败 (stale_after_seconds={threshold}): {e}")
        return {"failed_count": 0, "sync_job_ids": [], "error": str(e)}
    sync_job_ids = [str(row.get("id") or "") for row in rows if row.get("id")]
    return {"failed_count": len(sync_job_ids), "sync_job_ids": sync_job_ids}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd finance-mcp && python -m pytest tests/test_reap_stale_agents.py -v`
Expected: PASS.

- [ ] **Step 5: Register the MCP tool**

In `finance-mcp/tools/data_sources.py`, add a new `Tool(...)` right after the `browser_sync_job_startup_cleanup` Tool block (after line 5977):

```python
        Tool(
            name="browser_sync_job_reap_stale_agents",
            description="调度器专用：将心跳过期 agent 名下仍 running 的 browser_playbook sync_job 标记失败（孤立作业兜底）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "worker_token": {"type": "string"},
                    "stale_after_seconds": {"type": "integer"},
                },
                "required": ["worker_token"],
            },
        ),
```

- [ ] **Step 6: Add dispatch + handler**

In `finance-mcp/tools/data_sources.py`, add the dispatch line right after line 6165 (`return await _handle_browser_sync_job_startup_cleanup(arguments)`):

```python
        if name == "browser_sync_job_reap_stale_agents":
            return await _handle_browser_sync_job_reap_stale_agents(arguments)
```

And add the handler right after `_handle_browser_sync_job_startup_cleanup` ends (after line 9703):

```python
async def _handle_browser_sync_job_reap_stale_agents(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        _require_scheduler_user(str(arguments.get("worker_token") or ""))
    except ValueError as e:
        return {"success": False, "error": str(e)}
    raw = arguments.get("stale_after_seconds")
    stale_after_seconds = int(raw) if isinstance(raw, (int, float)) and int(raw) > 0 else 180
    result = auth_db.reap_stale_agent_running_jobs(stale_after_seconds=stale_after_seconds)
    if result.get("error"):
        return {"success": False, **result}
    return {"success": True, **result}
```

- [ ] **Step 7: Run the focused tests + a smoke import**

Run:
```bash
cd finance-mcp && python -m pytest tests/test_reap_stale_agents.py -v
python -c "import tools.data_sources"   # ensure no syntax/name errors in the edited module
```
Expected: PASS, and the import prints nothing (exit 0).

- [ ] **Step 8: Commit**

```bash
git add finance-mcp/auth/db.py finance-mcp/tools/data_sources.py finance-mcp/tests/test_reap_stale_agents.py
git commit -m "feat: add heartbeat-stale browser sync_job reaper + MCP tool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Relocate reapers to finance-cron + remove agent reconciler (#3)

**Files:**
- Modify: `finance-cron/mcp_client.py` (append 4 wrappers after `data_source_trigger_dataset_collection`)
- Modify: `finance-cron/scheduler_service.py` (config fields + reaper job + method + imports)
- Modify: `finance-agents/browser-agent/service.py` (remove `_waiting_reconciler`)
- Create: `finance-agents/browser-agent/tests/test_service_wiring.py`
- Create: `finance-cron/tests/test_reaper_cycle.py`

- [ ] **Step 1: Add finance-cron MCP wrappers**

Append to `finance-cron/mcp_client.py`:

```python
async def recon_queue_fail_failed_collection_waiting(worker_token: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_queue_fail_failed_collection_waiting", {"worker_token": worker_token}
    )


async def recon_queue_requeue_ready_waiting(worker_token: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_queue_requeue_ready_waiting", {"worker_token": worker_token}
    )


async def recon_queue_fail_expired_waiting(worker_token: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_queue_fail_expired_waiting", {"worker_token": worker_token}
    )


async def browser_sync_job_reap_stale_agents(
    worker_token: str, *, stale_after_seconds: int = 180
) -> dict[str, Any]:
    return await call_mcp_tool(
        "browser_sync_job_reap_stale_agents",
        {"worker_token": worker_token, "stale_after_seconds": stale_after_seconds},
    )
```

- [ ] **Step 2: Write the failing reaper-cycle test**

Create `finance-cron/tests/test_reaper_cycle.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CRON_ROOT = Path(__file__).resolve().parents[1]
if str(CRON_ROOT) not in sys.path:
    sys.path.insert(0, str(CRON_ROOT))

import scheduler_service
from scheduler_service import FinanceCronSchedulerService, load_cron_config


@pytest.mark.asyncio
async def test_run_reaper_cycle_calls_tools_in_order(monkeypatch) -> None:
    calls: list[str] = []

    async def _reap(token, *, stale_after_seconds=180):
        calls.append("reap_stale_agents")
        return {"success": True, "failed_count": 0}

    async def _fail_failed(token):
        calls.append("fail_failed")
        return {"success": True}

    async def _requeue(token):
        calls.append("requeue_ready")
        return {"success": True}

    async def _fail_expired(token):
        calls.append("fail_expired")
        return {"success": True}

    monkeypatch.setattr(scheduler_service, "browser_sync_job_reap_stale_agents", _reap)
    monkeypatch.setattr(scheduler_service, "recon_queue_fail_failed_collection_waiting", _fail_failed)
    monkeypatch.setattr(scheduler_service, "recon_queue_requeue_ready_waiting", _requeue)
    monkeypatch.setattr(scheduler_service, "recon_queue_fail_expired_waiting", _fail_expired)

    service = FinanceCronSchedulerService(load_cron_config(None))
    await service.run_reaper_cycle()

    assert calls == ["reap_stale_agents", "fail_failed", "requeue_ready", "fail_expired"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd finance-cron && python -m pytest tests/test_reaper_cycle.py -v`
Expected: FAIL — `AttributeError` (no `run_reaper_cycle`) and/or import error for the new wrapper names.

- [ ] **Step 4: Add config fields**

In `finance-cron/scheduler_service.py`, in the `FinanceCronConfig` dataclass (near `todo_sync_interval_seconds: int = 300`, ~line 46) add:

```python
    reaper_interval_seconds: int = 30
    reaper_stale_after_seconds: int = 180
```

And in `load_cron_config` (where other scheduler fields are parsed, after `todo_sync_interval_seconds=...`), add:

```python
        reaper_interval_seconds=max(
            5,
            int(
                scheduler.get("reaper_interval_seconds")
                or 30
            ),
        ),
        reaper_stale_after_seconds=max(
            30,
            int(
                scheduler.get("reaper_stale_after_seconds")
                or 180
            ),
        ),
```

- [ ] **Step 5: Import the wrappers**

In `finance-cron/scheduler_service.py`, extend the existing `from mcp_client import (...)` block (starts ~line 19) with:

```python
    browser_sync_job_reap_stale_agents,
    recon_queue_fail_expired_waiting,
    recon_queue_fail_failed_collection_waiting,
    recon_queue_requeue_ready_waiting,
```

- [ ] **Step 6: Add `run_reaper_cycle` method**

In `finance-cron/scheduler_service.py`, add a method on `FinanceCronSchedulerService` (e.g. after `sync_pending_todo_exceptions_job`):

```python
    async def run_reaper_cycle(self) -> None:
        """Independent recon/browser reaper net (relocated from the browser-agent).

        Order matters: reap stale-agent running jobs first so the just-failed jobs are
        cascaded by fail_failed in the same cycle.
        """
        token = create_scheduler_auth_token()
        steps = (
            ("reap_stale_agents", lambda: browser_sync_job_reap_stale_agents(
                token, stale_after_seconds=self.config.reaper_stale_after_seconds)),
            ("fail_failed", lambda: recon_queue_fail_failed_collection_waiting(token)),
            ("requeue_ready", lambda: recon_queue_requeue_ready_waiting(token)),
            ("fail_expired", lambda: recon_queue_fail_expired_waiting(token)),
        )
        for label, call in steps:
            try:
                await call()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[finance-cron] reaper 步骤失败: step=%s error=%s", label, exc)
```

- [ ] **Step 7: Register the interval job**

In `finance-cron/scheduler_service.py` `start()`, add another `add_job` (after the `sync-pending-todo-exceptions` job, before `self.scheduler.start()`):

```python
        self.scheduler.add_job(
            self.run_reaper_cycle,
            trigger="interval",
            seconds=self.config.reaper_interval_seconds,
            id="recon-browser-reaper",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=self.config.misfire_grace_seconds,
        )
```

- [ ] **Step 8: Run reaper-cycle test to verify it passes**

Run: `cd finance-cron && python -m pytest tests/test_reaper_cycle.py -v`
Expected: PASS.

- [ ] **Step 9: Remove `_waiting_reconciler` from the browser-agent**

In `finance-agents/browser-agent/service.py`:
- Delete the `_waiting_reconciler` coroutine (lines 44-52).
- In `main()` (line 114-118 `asyncio.gather(...)`), remove the `_waiting_reconciler(client, config.waiting_poll_interval_seconds),` line so it reads:

```python
    await asyncio.gather(
        _heartbeat(client, config),
        _dispatcher(client, config),
    )
```

Update the module docstring (lines 6-14): delete the `_waiting_reconciler` bullet, since reapers now live in finance-cron.

- [ ] **Step 10: Write the service-wiring test**

Create `finance-agents/browser-agent/tests/test_service_wiring.py`:

```python
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import service


def test_waiting_reconciler_removed_from_browser_agent() -> None:
    # Reapers now live in finance-cron; the agent must not run them.
    assert not hasattr(service, "_waiting_reconciler")
    src = inspect.getsource(service.main)
    assert "_waiting_reconciler" not in src
```

- [ ] **Step 11: Run the wiring test**

Run: `cd finance-agents/browser-agent && python -m pytest tests/test_service_wiring.py -v`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add finance-cron/mcp_client.py finance-cron/scheduler_service.py finance-cron/tests/test_reaper_cycle.py \
        finance-agents/browser-agent/service.py finance-agents/browser-agent/tests/test_service_wiring.py
git commit -m "refactor: move recon/browser reapers from browser-agent to finance-cron

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: End-to-end regression

**Files:**
- Modify: `finance-mcp/tests/test_reap_stale_agents.py` (created in Task 3 — extend it; it already has the dict-returning `FakeCursor`/`FakeConn`/`FakeConnManager`)

The agent-death scenario chains two helpers with **different cursor shapes**:
`reap_stale_agent_running_jobs` uses a `RealDictCursor` (fetchall → dicts, already handled by Task 3's `FakeCursor`), while `fail_waiting_recon_runs_with_failed_collection_jobs` iterates 3-tuples (`for queue_id, company_id, failed_error in rows`). So this test defines a small tuple-returning cursor for the cascade half.

- [ ] **Step 1: Write the agent-death regression test**

Append to `finance-mcp/tests/test_reap_stale_agents.py`:

```python
class TupleCursor(FakeCursor):
    def fetchall(self):  # fail_waiting iterates (queue_id, company_id, failed_error)
        return [("queue-001", "company-001", "AGENT_HEARTBEAT_LOST: stale")]


class TupleConnManager(FakeConnManager):
    def __enter__(self) -> FakeConn:
        return FakeConn(self.cursor)


def test_stale_agent_running_job_is_reaped_then_cascaded(monkeypatch) -> None:
    # 1) reap marks the stale agent's running job failed (dict cursor from Task 3)
    reap_cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(reap_cursor))
    reaped = auth_db.reap_stale_agent_running_jobs(stale_after_seconds=180)
    assert reaped["failed_count"] >= 1

    # 2) the fail_failed reaper targets waiting_data queue rows whose sync_job is now failed
    fail_cursor = TupleCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: TupleConnManager(fail_cursor))
    auth_db.fail_waiting_recon_runs_with_failed_collection_jobs()
    sql = "\n".join(fail_cursor.sql)
    assert "status = 'waiting_data'" in sql
    assert "job_status IN ('failed', 'cancelled')" in sql
```

- [ ] **Step 2: Run it to verify it passes**

Run: `cd finance-mcp && python -m pytest tests/test_reap_stale_agents.py -v`
Expected: PASS (the assertions describe behavior implemented in Task 3 + the existing `fail_waiting_recon_runs_with_failed_collection_jobs`).

> Note: the source-side self-heal path (completion-write-failure → retryable re-fail → re-collect → idempotent re-complete) is already covered end-to-end by Task 2's dispatcher test plus Task 1's idempotency test; no additional integration harness is added for it in v1.

- [ ] **Step 3: Run the full affected suites**

Run:
```bash
cd finance-mcp && python -m pytest tests/test_browser_capture_files.py tests/test_reap_stale_agents.py tests/test_browser_waiting_data_queue.py tests/test_browser_first_store_e2e.py -v
cd ../finance-agents/browser-agent && python -m pytest tests/test_dispatcher_loop.py tests/test_service_wiring.py -v
cd ../../finance-cron && python -m pytest tests/test_reaper_cycle.py -v
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add finance-mcp/tests/test_reap_stale_agents.py
git commit -m "test: regression for stale-agent reap + cascade

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Manual verification (post-implementation)

1. Apply migration 038 to any environment running the storage-metadata code (dev confirmed in Task 1; **production ECS must also run it** — see `project_migration037_capture_drift` memory).
2. Restart finance-cron; confirm log line `已启动 APScheduler` and that the `recon-browser-reaper` job is registered (APScheduler logs the job, or add a one-time debug log).
3. Confirm the browser-agent no longer logs `_waiting_reconciler` activity (it shouldn't, the coroutine is gone) and still heartbeats + claims.
