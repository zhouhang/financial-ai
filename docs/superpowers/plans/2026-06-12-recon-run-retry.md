# Failed Recon Run In-Place Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a retry action for terminal failed reconciliation execution runs that reruns the original run in place, while successful runs keep only the existing diff digestion action.

**Architecture:** The feature uses the current `POST /api/recon/runs/rerun` route and `trigger_mode="rerun"` queue path, but changes its contract from "create a rerun validation" to "retry the failed execution run in place." The API validates the source run, marks the same run as running, enqueues the job with `run_context.execution_run_id`, and the execution graph clears old exceptions only after the retry reaches the successful exception-writing phase. The React UI centralizes action visibility so `failed` maps to retry, `success` maps to diff digestion, and non-terminal statuses map to no action.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL-backed MCP tools, LangGraph data-agent execution graph, React 19, TypeScript, Vite, Vitest.

---

## File Structure

- Modify `finance-mcp/auth/db.py`
  - Extend `update_execution_run()` with `restart_started_at_now` and `reset_finished_at`.
  - Add `delete_execution_run_exceptions_by_run_id()` for retry success cleanup.
- Modify `finance-mcp/tools/execution_runs.py`
  - Expose the two new update flags through `execution_run_update`.
  - Add `execution_run_exception_clear_by_run`.
- Modify `finance-mcp/unified_mcp_server.py`
  - Register the new MCP tool name so data-agent can call it.
- Modify `finance-agents/data-agent/tools/mcp_client.py`
  - Add wrappers for `execution_run_update()` and `execution_run_exception_clear_by_run()`.
- Modify `finance-agents/data-agent/graphs/recon/auto_run_service.py`
  - Make `prepare_execution_run_rerun()` reject non-failed runs and build in-place retry context.
  - Add retry history helpers used by the API.
- Modify `finance-agents/data-agent/graphs/recon/auto_run_api.py`
  - Add duplicate active retry guard.
  - Append `retry_history`, mark original run running, and enqueue the in-place retry.
- Modify `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
  - Clear old exceptions for in-place retries before writing new exceptions, including the zero-anomaly success path.
- Modify `finance-web/src/components/recon/runActions.ts`
  - New frontend action visibility helper.
- Modify `finance-web/src/components/ReconWorkspace.tsx`
  - Use the helper in both the run list and exception board.
  - Add retry click handling and status refresh.
- Add `finance-web/src/components/recon/runActions.spec.ts`
  - Unit tests for action visibility.
- Add `finance-web/src/components/recon/ReconWorkspace.runRetry.spec.tsx`
  - Component tests for failed/success/running action display and retry request.
- Add or extend Python tests:
  - `finance-mcp/tests/test_execution_run_retry_tools.py`
  - `finance-agents/data-agent/tests/recon/test_execution_run_retry.py`
  - `finance-agents/data-agent/tests/recon/test_digest_endpoint.py`
  - `finance-agents/data-agent/tests/recon/test_diff_digestion_service.py`

## Task 1: MCP Run Update Flags And Exception Cleanup Tool

**Files:**
- Modify: `finance-mcp/auth/db.py`
- Modify: `finance-mcp/tools/execution_runs.py`
- Modify: `finance-mcp/unified_mcp_server.py`
- Test: `finance-mcp/tests/test_execution_run_retry_tools.py`

- [ ] **Step 1: Write failing tests for update flags and exception cleanup**

Create `finance-mcp/tests/test_execution_run_retry_tools.py`:

```python
from __future__ import annotations

from typing import Any

import pytest

from tools import execution_runs


def _fake_user() -> dict[str, str]:
    return {"company_id": "company-1", "user_id": "user-1"}


def test_run_update_passes_retry_time_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_require_user(auth_token: str) -> dict[str, str]:
        assert auth_token == "token"
        return _fake_user()

    def fake_update_execution_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"id": kwargs["run_id"], "execution_status": kwargs["execution_status"]}

    monkeypatch.setattr(execution_runs, "_require_user", fake_require_user)
    monkeypatch.setattr(execution_runs.auth_db, "update_execution_run", fake_update_execution_run)

    result = execution_runs._run_update(
        {
            "auth_token": "token",
            "run_id": "run-1",
            "execution_status": "running",
            "restart_started_at_now": True,
            "reset_finished_at": True,
        }
    )

    assert result == {"success": True, "run": {"id": "run-1", "execution_status": "running"}}
    assert captured["company_id"] == "company-1"
    assert captured["run_id"] == "run-1"
    assert captured["execution_status"] == "running"
    assert captured["restart_started_at_now"] is True
    assert captured["reset_finished_at"] is True


def test_exception_clear_by_run_delegates_to_auth_db(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_require_user(auth_token: str) -> dict[str, str]:
        assert auth_token == "token"
        return _fake_user()

    def fake_delete_execution_run_exceptions_by_run_id(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(execution_runs, "_require_user", fake_require_user)
    monkeypatch.setattr(
        execution_runs.auth_db,
        "delete_execution_run_exceptions_by_run_id",
        fake_delete_execution_run_exceptions_by_run_id,
    )

    result = execution_runs._run_exception_clear_by_run(
        {"auth_token": "token", "run_id": "run-1"}
    )

    assert result == {"success": True, "deleted_count": 7}
    assert captured == {"company_id": "company-1", "run_id": "run-1"}
```

- [ ] **Step 2: Run the MCP tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_execution_run_retry_tools.py -q
```

Expected: FAIL because `_run_update()` does not pass `restart_started_at_now` or `reset_finished_at`, and `_run_exception_clear_by_run` does not exist.

- [ ] **Step 3: Extend `auth_db.update_execution_run()`**

In `finance-mcp/auth/db.py`, change the function signature:

```python
def update_execution_run(
    *,
    company_id: str,
    run_id: str,
    execution_status: str | None = None,
    failed_stage: str | None = None,
    failed_reason: str | None = None,
    run_context_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    subtasks_json: list[dict] | None = None,
    proc_result_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    artifacts_json: dict | None = None,
    anomaly_count: int | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
    restart_started_at_now: bool = False,
    reset_finished_at: bool = False,
) -> dict | None:
```

Replace the `started_at` and `finished_at` assignments in its SQL with:

```sql
                        started_at = CASE
                            WHEN %s THEN CURRENT_TIMESTAMP
                            WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP)
                            ELSE started_at
                        END,
                        finished_at = CASE
                            WHEN %s THEN NULL
                            WHEN %s THEN CURRENT_TIMESTAMP
                            ELSE finished_at
                        END,
```

Replace the matching parameter block:

```python
                        anomaly_count,
                        restart_started_at_now,
                        started_at_now,
                        reset_finished_at,
                        finished_at_now,
                        run_id,
                        company_id,
```

- [ ] **Step 4: Add the run-level exception delete helper**

In `finance-mcp/auth/db.py`, after `list_open_execution_run_exceptions()`, add:

```python
def delete_execution_run_exceptions_by_run_id(*, company_id: str, run_id: str) -> int:
    """删除指定执行记录下的异常派生数据，返回删除行数。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM execution_run_exceptions
                    WHERE company_id = %s
                      AND run_id = %s
                    """,
                    (company_id, run_id),
                )
                deleted_count = int(cur.rowcount or 0)
                conn.commit()
                return deleted_count
    except Exception as e:
        logger.error(
            f"删除 execution_run_exceptions 失败 (company_id={company_id}, run_id={run_id}): {e}"
        )
        return 0
```

- [ ] **Step 5: Expose flags and cleanup through `execution_runs` MCP tool**

In `finance-mcp/tools/execution_runs.py`, extend the `execution_run_update` schema properties:

```python
                    "started_at_now": {"type": "boolean"},
                    "finished_at_now": {"type": "boolean"},
                    "restart_started_at_now": {"type": "boolean"},
                    "reset_finished_at": {"type": "boolean"},
```

Add this tool definition near the other exception tools:

```python
        Tool(
            name="execution_run_exception_clear_by_run",
            description="删除指定执行记录下的异常派生数据，用于原地重试成功后写入新异常前清理旧异常。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["auth_token", "run_id"],
            },
        ),
```

In `handle_tool_call()`, add the dispatch branch:

```python
        if name == "execution_run_exception_clear_by_run":
            return _run_exception_clear_by_run(arguments)
```

In `_run_update()`, pass the new booleans:

```python
        started_at_now=_as_bool(arguments.get("started_at_now"), False),
        finished_at_now=_as_bool(arguments.get("finished_at_now"), False),
        restart_started_at_now=_as_bool(arguments.get("restart_started_at_now"), False),
        reset_finished_at=_as_bool(arguments.get("reset_finished_at"), False),
```

Add the handler after `_run_exceptions()`:

```python
def _run_exception_clear_by_run(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user.get("company_id") or "")
    run_id = _as_text(arguments.get("run_id"))
    if not run_id:
        return {"success": False, "error": "run_id 不能为空"}
    deleted_count = auth_db.delete_execution_run_exceptions_by_run_id(
        company_id=company_id,
        run_id=run_id,
    )
    return {"success": True, "deleted_count": deleted_count}
```

- [ ] **Step 6: Register the new MCP tool name**

In `finance-mcp/unified_mcp_server.py`, add `"execution_run_exception_clear_by_run"` to the execution run tool registration list next to the existing exception tools:

```python
    "execution_run_exception_clear_by_run",
```

- [ ] **Step 7: Run tests and commit**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_execution_run_retry_tools.py -q
```

Expected: PASS.

Commit:

```bash
git add finance-mcp/auth/db.py finance-mcp/tools/execution_runs.py finance-mcp/unified_mcp_server.py finance-mcp/tests/test_execution_run_retry_tools.py
git commit -m "feat(recon): add execution run retry mcp tools"
```

## Task 2: Data-Agent Failed-Only Rerun API And Retry History

**Files:**
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
- Modify: `finance-agents/data-agent/graphs/recon/auto_run_service.py`
- Modify: `finance-agents/data-agent/graphs/recon/auto_run_api.py`
- Test: `finance-agents/data-agent/tests/recon/test_execution_run_retry.py`
- Test: `finance-agents/data-agent/tests/recon/test_digest_endpoint.py`

- [ ] **Step 1: Write failing service tests**

Create `finance-agents/data-agent/tests/recon/test_execution_run_retry.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from graphs.recon import auto_run_service


def _source_run(status: str = "failed", retry_history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": "run-1",
        "plan_code": "plan-1",
        "biz_date": "2026-06-10",
        "execution_status": status,
        "failed_stage": "recon",
        "failed_reason": "left dataset missing",
        "finished_at": "2026-06-10T09:00:00+08:00",
        "run_context_json": {
            "biz_date": "2026-06-10",
            "run_plan_code": "plan-1",
            "retry_history": retry_history or [],
        },
    }


@pytest.mark.asyncio
async def test_prepare_execution_run_rerun_rejects_non_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execution_run_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": _source_run(status="success")}

    monkeypatch.setattr(auto_run_service, "execution_run_get", fake_execution_run_get)

    result = await auto_run_service.prepare_execution_run_rerun(
        auth_token="token",
        original_run_id="run-1",
        reason="用户触发重试",
    )

    assert result["success"] is False
    assert result["status"] == "invalid_request"
    assert result["error"] == "只有执行失败的运行记录可以重试"


@pytest.mark.asyncio
async def test_prepare_execution_run_rerun_builds_in_place_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execution_run_get(auth_token: str, run_id: str) -> dict[str, Any]:
        return {"success": True, "run": _source_run(status="failed")}

    monkeypatch.setattr(auto_run_service, "execution_run_get", fake_execution_run_get)

    result = await auto_run_service.prepare_execution_run_rerun(
        auth_token="token",
        original_run_id="run-1",
        reason="用户触发重试",
    )

    assert result["success"] is True
    assert result["run_plan_code"] == "plan-1"
    assert result["biz_date"] == "2026-06-10"
    assert result["run_context"]["target_run_id"] == "run-1"
    assert result["run_context"]["execution_run_id"] == "run-1"
    assert result["run_context"]["retry_from_failed_run_id"] == "run-1"
    assert result["run_context"]["retry_reason"] == "用户触发重试"
    assert result["run_context"]["trigger_type"] == "rerun"


def test_append_retry_history_keeps_latest_20() -> None:
    source_run = _source_run(
        retry_history=[{"attempt": index} for index in range(25)],
    )
    run_context = dict(source_run["run_context_json"])

    result = auto_run_service.append_execution_run_retry_history(
        run_context,
        source_run=source_run,
        reason="用户触发重试",
        trigger_user={"user_id": "u1", "username": "张三", "role": "admin"},
        attempted_at=datetime(2026, 6, 12, 10, 30, tzinfo=timezone.utc),
    )

    history = result["retry_history"]
    assert len(history) == 20
    assert history[-1]["reason"] == "用户触发重试"
    assert history[-1]["previous_status"] == "failed"
    assert history[-1]["previous_failed_stage"] == "recon"
    assert history[-1]["previous_failed_reason"] == "left dataset missing"
    assert history[-1]["trigger_user"]["username"] == "张三"
    assert history[0] == {"attempt": 6}
```

- [ ] **Step 2: Write failing API tests**

Append these tests to `finance-agents/data-agent/tests/recon/test_digest_endpoint.py`:

```python
def _make_execution_run_for_rerun(status: str = "failed") -> dict[str, object]:
    return {
        "id": "run-failed-1",
        "plan_code": "plan-1",
        "biz_date": "2026-06-10",
        "execution_status": status,
        "failed_stage": "recon",
        "failed_reason": "原失败原因",
        "finished_at": "2026-06-10T09:00:00+08:00",
        "run_context_json": {
            "biz_date": "2026-06-10",
            "run_plan_code": "plan-1",
        },
    }


def test_rerun_execution_run_rejects_active_duplicate(client, monkeypatch):
    async def fake_prepare_execution_run_rerun(**kwargs):
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": _make_execution_run_for_rerun(),
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": {"id": "job-1", "status": "queued"}}

    async def fake_recon_queue_enqueue(**kwargs):
        raise AssertionError("duplicate active retry must not enqueue")

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)

    response = client.post(
        "/api/recon/runs/rerun",
        headers=_auth_header(),
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "该运行记录正在重试,请稍后"


def test_rerun_execution_run_marks_original_run_running(client, monkeypatch):
    captured_enqueue = {}
    captured_update = {}

    async def fake_prepare_execution_run_rerun(**kwargs):
        return {
            "success": True,
            "run_plan_code": "plan-1",
            "biz_date": "2026-06-10",
            "source_run": _make_execution_run_for_rerun(),
            "run_context": {
                "target_run_id": "run-failed-1",
                "execution_run_id": "run-failed-1",
                "retry_from_failed_run_id": "run-failed-1",
                "retry_reason": "用户触发重试",
                "trigger_type": "rerun",
            },
        }

    async def fake_recon_queue_find_active(**kwargs):
        return {"success": True, "job": None}

    async def fake_recon_queue_enqueue(**kwargs):
        captured_enqueue.update(kwargs)
        return {"success": True, "job": {"id": "job-1", "status": "queued"}}

    async def fake_execution_run_update(auth_token, run_id, payload):
        captured_update.update({"auth_token": auth_token, "run_id": run_id, "payload": payload})
        return {"success": True, "run": {"id": run_id, "execution_status": "running"}}

    monkeypatch.setattr(auto_run_api, "prepare_execution_run_rerun", fake_prepare_execution_run_rerun)
    monkeypatch.setattr(auto_run_api, "recon_queue_find_active", fake_recon_queue_find_active)
    monkeypatch.setattr(auto_run_api, "recon_queue_enqueue", fake_recon_queue_enqueue)
    monkeypatch.setattr(auto_run_api, "execution_run_update", fake_execution_run_update)

    response = client.post(
        "/api/recon/runs/rerun",
        headers=_auth_header(),
        json={"original_run_id": "run-failed-1", "reason": "用户触发重试"},
    )

    assert response.status_code == 200
    assert response.json()["queued"] is True
    assert captured_enqueue["trigger_mode"] == "rerun"
    assert captured_enqueue["run_context"]["target_run_id"] == "run-failed-1"
    assert captured_enqueue["run_context"]["execution_run_id"] == "run-failed-1"
    assert captured_update["run_id"] == "run-failed-1"
    assert captured_update["payload"]["execution_status"] == "running"
    assert captured_update["payload"]["failed_stage"] == ""
    assert captured_update["payload"]["failed_reason"] == ""
    assert captured_update["payload"]["restart_started_at_now"] is True
    assert captured_update["payload"]["reset_finished_at"] is True
    assert captured_update["payload"]["run_context_json"]["retry_history"][-1]["previous_status"] == "failed"
```

- [ ] **Step 3: Run data-agent tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_digest_endpoint.py -q
```

Expected: FAIL because the retry helpers and API behavior are not implemented.

- [ ] **Step 4: Add MCP client wrappers**

In `finance-agents/data-agent/tools/mcp_client.py`, add:

```python
async def execution_run_update(auth_token: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool(
        "execution_run_update",
        {
            "auth_token": auth_token,
            "run_id": run_id,
            **payload,
        },
    )


async def execution_run_exception_clear_by_run(auth_token: str, run_id: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "execution_run_exception_clear_by_run",
        {
            "auth_token": auth_token,
            "run_id": run_id,
        },
    )
```

If `execution_run_update()` already exists, replace its body with the payload-spreading form above and keep all existing callers working.

- [ ] **Step 5: Implement service helpers**

In `finance-agents/data-agent/graphs/recon/auto_run_service.py`, add these helpers near `prepare_execution_run_rerun()`:

```python
def append_execution_run_retry_history(
    run_context: dict[str, Any],
    *,
    source_run: dict[str, Any],
    reason: str,
    trigger_user: dict[str, Any],
    attempted_at: datetime | None = None,
) -> dict[str, Any]:
    attempted = attempted_at or datetime.now(timezone.utc)
    merged_context = _safe_dict(run_context)
    existing_history = [
        item for item in _safe_list(merged_context.get("retry_history")) if isinstance(item, dict)
    ]
    existing_history.append(
        {
            "attempted_at": attempted.isoformat(),
            "reason": str(reason or "用户触发重试").strip() or "用户触发重试",
            "trigger_user": _safe_dict(trigger_user),
            "previous_status": str(source_run.get("execution_status") or ""),
            "previous_failed_stage": str(source_run.get("failed_stage") or ""),
            "previous_failed_reason": str(source_run.get("failed_reason") or ""),
            "previous_finished_at": str(source_run.get("finished_at") or ""),
        }
    )
    merged_context["retry_history"] = existing_history[-20:]
    return merged_context
```

Ensure the module imports `timezone`:

```python
from datetime import date, datetime, timedelta, timezone
```

- [ ] **Step 6: Make `prepare_execution_run_rerun()` failed-only and in-place**

In `prepare_execution_run_rerun()`, after `source_run = _safe_dict(run_result.get("run"))`, insert:

```python
    source_status = str(source_run.get("execution_status") or "").strip().lower()
    if source_status != "failed":
        return {
            "success": False,
            "status": "invalid_request",
            "error": "只有执行失败的运行记录可以重试",
            "source_run": source_run,
        }
```

Replace the existing `rerun_context.update(...)` block with:

```python
    retry_reason = str(reason or "用户触发重试").strip() or "用户触发重试"
    rerun_context.update(
        {
            "target_run_id": source_run_id,
            "execution_run_id": source_run_id,
            "retry_from_failed_run_id": source_run_id,
            "rerun_from_run_id": source_run_id,
            "rerun_exception_id": exception_ref,
            "retry_reason": retry_reason,
            "rerun_reason": retry_reason,
            "trigger_type": "rerun",
        }
    )
```

Keep the existing return payload and include the source run:

```python
        "source_run": source_run,
```

- [ ] **Step 7: Update the rerun API**

In `finance-agents/data-agent/graphs/recon/auto_run_api.py`, add `execution_run_update` to the import list from `tools.mcp_client`:

```python
    execution_run_update,
```

Inside `rerun_execution_run_api()`, after a successful `prepare_result`, insert the active queue guard:

```python
    target_run_id = str(body.original_run_id or "").strip()
    active_result = await recon_queue_find_active(
        company_id=str(user["company_id"]),
        trigger_mode="rerun",
        target_run_id=target_run_id,
    )
    if active_result.get("success") and active_result.get("job"):
        raise HTTPException(
            status_code=409,
            detail={"status": "conflict", "message": "该运行记录正在重试,请稍后"},
        )
```

Replace the inline enqueue `run_context=` expression with:

```python
    trigger_user = _build_trigger_user_context(user)
    source_run = dict(prepare_result.get("source_run") or {})
    run_context = _merge_trigger_user_context(
        dict(prepare_result.get("run_context") or {}),
        user,
    )
    run_context = append_execution_run_retry_history(
        run_context,
        source_run=source_run,
        reason=body.reason or "用户触发重试",
        trigger_user=trigger_user,
    )
```

Use that context in `recon_queue_enqueue()`:

```python
        run_context=run_context,
```

After successful enqueue and before returning, mark the original run as running:

```python
    update_result = await execution_run_update(
        auth_token,
        target_run_id,
        {
            "execution_status": "running",
            "failed_stage": "",
            "failed_reason": "",
            "run_context_json": run_context,
            "started_at_now": True,
            "restart_started_at_now": True,
            "reset_finished_at": True,
        },
    )
    if not update_result.get("success"):
        raise HTTPException(status_code=500, detail=update_result.get("error", "更新运行记录失败"))
```

Update the API imports from `graphs.recon.auto_run_service`:

```python
    append_execution_run_retry_history,
```

- [ ] **Step 8: Run tests and commit**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_digest_endpoint.py -q
```

Expected: PASS.

Commit:

```bash
git add finance-agents/data-agent/tools/mcp_client.py finance-agents/data-agent/graphs/recon/auto_run_service.py finance-agents/data-agent/graphs/recon/auto_run_api.py finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_digest_endpoint.py
git commit -m "feat(recon): retry failed execution runs in place"
```

## Task 3: Execution Graph Clears Old Exceptions Only After Retry Success

**Files:**
- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
- Test: `finance-agents/data-agent/tests/recon/test_execution_run_retry.py`
- Test: `finance-agents/data-agent/tests/recon/test_diff_digestion_service.py`

- [ ] **Step 1: Add failing graph cleanup tests**

Append to `finance-agents/data-agent/tests/recon/test_execution_run_retry.py`:

```python
from graphs.recon.auto_scheme_run import nodes


@pytest.mark.asyncio
async def test_retry_success_clears_old_exceptions_even_when_no_new_anomalies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, payload))
        if name == "execution_run_exception_clear_by_run":
            return {"success": True, "deleted_count": 3}
        raise AssertionError(f"unexpected MCP call: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "scheme_code": "scheme-1",
            "execution_run_record": {"id": "run-1"},
            "run_context": {
                "trigger_type": "rerun",
                "target_run_id": "run-1",
                "execution_run_id": "run-1",
                "retry_from_failed_run_id": "run-1",
            },
            "anomaly_items": [],
        },
    }

    result = await nodes.create_exception_tasks_node(state)

    assert calls == [
        (
            "execution_run_exception_clear_by_run",
            {"auth_token": "token", "run_id": "run-1"},
        )
    ]
    assert result["recon_ctx"]["retry_previous_exceptions_cleared"] is True
    assert result["recon_ctx"]["retry_previous_exceptions_deleted_count"] == 3


@pytest.mark.asyncio
async def test_retry_success_clears_old_exceptions_before_bulk_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(name)
        if name == "execution_run_exception_clear_by_run":
            return {"success": True, "deleted_count": 1}
        if name == "execution_run_exception_bulk_create":
            return {"success": True, "created": [{"id": "exception-1"}], "count": 1}
        return {"success": True}

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(
        nodes,
        "_resolve_run_plan_default_owner",
        lambda run_plan: ("", "", {}, False),
    )

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "scheme_code": "scheme-1",
            "run_plan": {},
            "scheme": {},
            "execution_run_record": {"id": "run-1"},
            "run_context": {
                "trigger_type": "rerun",
                "target_run_id": "run-1",
                "execution_run_id": "run-1",
                "retry_from_failed_run_id": "run-1",
            },
            "anomaly_items": [{"item_id": "a1", "anomaly_type": "source_only"}],
        },
    }

    await nodes.create_exception_tasks_node(state)

    assert calls[0] == "execution_run_exception_clear_by_run"
    assert "execution_run_exception_bulk_create" in calls[1:]


@pytest.mark.asyncio
async def test_non_retry_success_does_not_clear_old_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call_mcp_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError(f"unexpected MCP call: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "scheme_code": "scheme-1",
            "execution_run_record": {"id": "run-1"},
            "run_context": {"trigger_type": "manual", "execution_run_id": "run-1"},
            "anomaly_items": [],
        },
    }

    result = await nodes.create_exception_tasks_node(state)

    assert "retry_previous_exceptions_cleared" not in result["recon_ctx"]
```

- [ ] **Step 2: Add failing worker propagation test**

Append to `finance-agents/data-agent/tests/recon/test_diff_digestion_service.py`:

```python
@pytest.mark.asyncio
async def test_worker_rerun_passes_execution_run_id_context(monkeypatch):
    from graphs.recon import recon_worker

    captured = {}

    async def fake_execute_run_plan_run(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(recon_worker, "execute_run_plan_run", fake_execute_run_plan_run)

    job = recon_worker.ReconQueueJob(
        id="job-1",
        company_id="company-1",
        run_plan_code="plan-1",
        biz_date="2026-06-10",
        trigger_mode="rerun",
        status="queued",
        run_context={
            "target_run_id": "run-1",
            "execution_run_id": "run-1",
            "retry_from_failed_run_id": "run-1",
        },
    )

    await recon_worker.process_recon_queue_job("token", job)

    assert captured["run_plan_code"] == "plan-1"
    assert captured["trigger_mode"] == "rerun"
    assert captured["run_context"]["target_run_id"] == "run-1"
    assert captured["run_context"]["execution_run_id"] == "run-1"
    assert captured["run_context"]["retry_from_failed_run_id"] == "run-1"
    assert captured["run_context"]["queue_job_id"] == "job-1"
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_diff_digestion_service.py -q
```

Expected: FAIL because `create_exception_tasks_node()` returns before clearing old exceptions.

- [ ] **Step 4: Add retry-context helper in `nodes.py`**

In `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`, add near the other small context helpers:

```python
def _is_in_place_retry_context(ctx: dict[str, Any], run_id: str) -> bool:
    run_context = _safe_dict(ctx.get("run_context"))
    if str(run_context.get("trigger_type") or "").strip() != "rerun":
        return False
    if str(run_context.get("execution_run_id") or "").strip() != run_id:
        return False
    target_run_id = str(run_context.get("target_run_id") or "").strip()
    retry_from_run_id = str(run_context.get("retry_from_failed_run_id") or "").strip()
    return target_run_id == run_id and retry_from_run_id == run_id
```

Add the async cleanup helper:

```python
async def _clear_previous_retry_exceptions_if_needed(
    *,
    auth_token: str,
    ctx: dict[str, Any],
    run_id: str,
) -> None:
    if not auth_token or not run_id:
        return
    if ctx.get("retry_previous_exceptions_cleared"):
        return
    if not _is_in_place_retry_context(ctx, run_id):
        return

    result = await call_mcp_tool(
        "execution_run_exception_clear_by_run",
        {"auth_token": auth_token, "run_id": run_id},
    )
    ctx["retry_previous_exceptions_cleared"] = bool(result.get("success"))
    ctx["retry_previous_exceptions_deleted_count"] = int(result.get("deleted_count") or 0)
    if not result.get("success"):
        ctx["retry_previous_exceptions_clear_error"] = str(result.get("error") or "清理旧异常失败")
```

- [ ] **Step 5: Call cleanup before the anomaly early return**

In `create_exception_tasks_node()`, replace:

```python
    anomalies = [v for v in _safe_list(ctx.get("anomaly_items")) if isinstance(v, dict)]
    if not run_id or not scheme_code or not anomalies:
        return {"recon_ctx": ctx}
```

with:

```python
    anomalies = [v for v in _safe_list(ctx.get("anomaly_items")) if isinstance(v, dict)]
    if run_id and scheme_code:
        await _clear_previous_retry_exceptions_if_needed(
            auth_token=auth_token,
            ctx=ctx,
            run_id=run_id,
        )
    if not run_id or not scheme_code or not anomalies:
        return {"recon_ctx": ctx}
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_diff_digestion_service.py -q
```

Expected: PASS.

Commit:

```bash
git add finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_diff_digestion_service.py
git commit -m "feat(recon): clear retry exceptions before rewriting results"
```

## Task 4: Frontend Action Helper And Retry UI

**Files:**
- Create: `finance-web/src/components/recon/runActions.ts`
- Create: `finance-web/src/components/recon/runActions.spec.ts`
- Create: `finance-web/src/components/recon/ReconWorkspace.runRetry.spec.tsx`
- Modify: `finance-web/src/components/ReconWorkspace.tsx`

- [ ] **Step 1: Write action helper tests**

Create `finance-web/src/components/recon/runActions.spec.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { canDigestRun, canRetryRun, runActionForStatus } from './runActions';

describe('runActions', () => {
  it('shows retry only for failed runs', () => {
    expect(canRetryRun({ executionStatus: 'failed' })).toBe(true);
    expect(canDigestRun({ executionStatus: 'failed' })).toBe(false);
    expect(runActionForStatus({ executionStatus: 'failed' })).toBe('retry');
  });

  it('shows diff digestion only for successful runs', () => {
    expect(canRetryRun({ executionStatus: 'success' })).toBe(false);
    expect(canDigestRun({ executionStatus: 'success' })).toBe(true);
    expect(runActionForStatus({ executionStatus: 'success' })).toBe('digest');
  });

  it.each(['running', 'waiting_data', 'queued', 'scheduled', 'unknown', ''])(
    'shows no action for %s',
    (executionStatus) => {
      expect(canRetryRun({ executionStatus })).toBe(false);
      expect(canDigestRun({ executionStatus })).toBe(false);
      expect(runActionForStatus({ executionStatus })).toBeNull();
    },
  );
});
```

- [ ] **Step 2: Write component behavior tests**

Create `finance-web/src/components/recon/ReconWorkspace.runRetry.spec.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ReconWorkspace from '../ReconWorkspace';

const originalFetch = globalThis.fetch;

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: init.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

function mockFetch() {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';

    if (url.endsWith('/api/recon/schemes')) {
      return jsonResponse({ success: true, schemes: [] });
    }
    if (url.endsWith('/api/recon/run-plans')) {
      return jsonResponse({ success: true, plans: [] });
    }
    if (url.endsWith('/api/recon/runs') || url.includes('/api/recon/runs?')) {
      return jsonResponse({
        success: true,
        runs: [
          {
            id: 'run-failed',
            run_code: 'run-failed-code',
            plan_code: 'plan-1',
            scheme_code: 'scheme-1',
            execution_status: 'failed',
            anomaly_count: 3,
            created_at: '2026-06-10T09:00:00+08:00',
          },
          {
            id: 'run-success',
            run_code: 'run-success-code',
            plan_code: 'plan-1',
            scheme_code: 'scheme-1',
            execution_status: 'success',
            anomaly_count: 2,
            created_at: '2026-06-10T10:00:00+08:00',
          },
          {
            id: 'run-running',
            run_code: 'run-running-code',
            plan_code: 'plan-1',
            scheme_code: 'scheme-1',
            execution_status: 'running',
            anomaly_count: 0,
            created_at: '2026-06-10T11:00:00+08:00',
          },
        ],
        total: 3,
      });
    }
    if (url.endsWith('/api/recon/runs/rerun') && method === 'POST') {
      return jsonResponse({ queued: true, status: 'queued', job: { id: 'job-1' } });
    }
    if (url.endsWith('/api/recon/runs/run-failed')) {
      return jsonResponse({
        success: true,
        run: {
          id: 'run-failed',
          run_code: 'run-failed-code',
          plan_code: 'plan-1',
          scheme_code: 'scheme-1',
          execution_status: 'running',
          anomaly_count: 3,
        },
      });
    }
    return jsonResponse({ success: true });
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe('ReconWorkspace retry actions', () => {
  beforeEach(() => {
    window.localStorage.setItem('auth_token', 'token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders retry for failed, digest for success, and no action for running', async () => {
    mockFetch();

    render(<ReconWorkspace />);
    fireEvent.click(await screen.findByRole('button', { name: '运行记录' }));

    const failedRow = await screen.findByTestId('execution-run-row-run-failed');
    const successRow = await screen.findByTestId('execution-run-row-run-success');
    const runningRow = await screen.findByTestId('execution-run-row-run-running');

    expect(within(failedRow).getByRole('button', { name: '重试' })).toBeInTheDocument();
    expect(within(failedRow).queryByRole('button', { name: '差异消化' })).not.toBeInTheDocument();
    expect(within(successRow).getByRole('button', { name: '差异消化' })).toBeInTheDocument();
    expect(within(successRow).queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
    expect(within(runningRow).queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
    expect(within(runningRow).queryByRole('button', { name: '差异消化' })).not.toBeInTheDocument();
  });

  it('posts original_run_id when retry is clicked', async () => {
    const fetchMock = mockFetch();

    render(<ReconWorkspace />);
    fireEvent.click(await screen.findByRole('button', { name: '运行记录' }));

    const failedRow = await screen.findByTestId('execution-run-row-run-failed');
    fireEvent.click(within(failedRow).getByRole('button', { name: '重试' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/recon/runs/rerun'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ original_run_id: 'run-failed', reason: '用户触发重试' }),
        }),
      );
    });
    expect(await screen.findByText('已发起重试,当前运行记录将更新为最新执行结果。')).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run frontend tests and verify they fail**

Run:

```bash
cd finance-web
npx vitest run src/components/recon/runActions.spec.ts src/components/recon/ReconWorkspace.runRetry.spec.tsx
```

Expected: FAIL because `runActions.ts`, retry button rendering, and `data-testid` values are missing.

- [ ] **Step 4: Create the action helper**

Create `finance-web/src/components/recon/runActions.ts`:

```typescript
type RunStatusInput = {
  executionStatus?: string | null;
};

export type ReconRunPrimaryAction = 'retry' | 'digest';

export function normalizedExecutionStatus(input: RunStatusInput | string | null | undefined): string {
  const value = typeof input === 'string' ? input : input?.executionStatus;
  return String(value ?? '').trim().toLowerCase();
}

export function canRetryRun(input: RunStatusInput | string | null | undefined): boolean {
  return normalizedExecutionStatus(input) === 'failed';
}

export function canDigestRun(input: RunStatusInput | string | null | undefined): boolean {
  return normalizedExecutionStatus(input) === 'success';
}

export function runActionForStatus(
  input: RunStatusInput | string | null | undefined,
): ReconRunPrimaryAction | null {
  if (canRetryRun(input)) {
    return 'retry';
  }
  if (canDigestRun(input)) {
    return 'digest';
  }
  return null;
}
```

- [ ] **Step 5: Add retry state and handler to `ReconWorkspace.tsx`**

In `finance-web/src/components/ReconWorkspace.tsx`, import the helper:

```typescript
import { canDigestRun, canRetryRun } from './recon/runActions';
```

Add state near `digestingRunId`:

```typescript
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null);
```

Add this handler near `handleDiffDigestion`:

```typescript
  const handleRetryRun = useCallback(
    async (runId: string) => {
      const token = getAuthToken();
      if (!token) {
        setModalError('请先登录后再重试运行记录。');
        return;
      }
      setRetryingRunId(runId);
      setModalError(null);
      try {
        const response = await fetch(`${API_BASE}/api/recon/runs/rerun`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ original_run_id: runId, reason: '用户触发重试' }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = data?.detail;
          const message =
            typeof detail === 'string'
              ? detail
              : detail?.message || data?.message || data?.error || '发起重试失败';
          throw new Error(message);
        }
        setCenterNotice('已发起重试,当前运行记录将更新为最新执行结果。');
        await Promise.all([refreshRunQuietly(runId), loadRunsPage(1)]);
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '发起重试失败');
      } finally {
        setRetryingRunId(null);
      }
    },
    [loadRunsPage, refreshRunQuietly],
  );
```

- [ ] **Step 6: Render a single primary action for each run**

In `ReconWorkspace.tsx`, add this render helper near the run row rendering helpers:

```typescript
  const renderRunPrimaryActionButton = (run: ReconCenterRunItem) => {
    if (canRetryRun(run)) {
      return (
        <button
          type="button"
          className="recon-btn recon-btn-primary"
          disabled={retryingRunId === run.id}
          onClick={() => handleRetryRun(run.id)}
        >
          {retryingRunId === run.id ? '重试中...' : '重试'}
        </button>
      );
    }
    if (canDigestRun(run)) {
      return (
        <button
          type="button"
          className="recon-btn recon-btn-primary"
          disabled={digestingRunId === run.id}
          onClick={() => handleDiffDigestion(run.id)}
        >
          {digestingRunId === run.id ? '复核中...' : '差异消化'}
        </button>
      );
    }
    return null;
  };
```

In `renderRunRows()`, add a stable row test id on the row wrapper:

```tsx
data-testid={`execution-run-row-${run.id}`}
```

Place `{renderRunPrimaryActionButton(run)}` in the row actions next to the existing "异常看板" button and before "删除".

In the exception board modal header, replace the fixed "差异消化" button with:

```tsx
{focusedRun ? renderRunPrimaryActionButton(focusedRun) : null}
```

- [ ] **Step 7: Run frontend tests and type check**

Run:

```bash
cd finance-web
npx vitest run src/components/recon/runActions.spec.ts src/components/recon/ReconWorkspace.runRetry.spec.tsx
npx tsc --noEmit
```

Expected: PASS.

Commit:

```bash
git add finance-web/src/components/recon/runActions.ts finance-web/src/components/recon/runActions.spec.ts finance-web/src/components/recon/ReconWorkspace.runRetry.spec.tsx finance-web/src/components/ReconWorkspace.tsx
git commit -m "feat(recon): show retry only for failed runs"
```

## Task 5: End-To-End Verification And Service Restart

**Files:**
- No new files.
- Verify all modified files from Tasks 1-4.

- [ ] **Step 1: Run focused Python verification**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_execution_run_retry_tools.py finance-agents/data-agent/tests/recon/test_execution_run_retry.py finance-agents/data-agent/tests/recon/test_digest_endpoint.py finance-agents/data-agent/tests/recon/test_diff_digestion_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run:

```bash
cd finance-web
npx vitest run src/components/recon/runActions.spec.ts src/components/recon/ReconWorkspace.runRetry.spec.tsx
npx tsc --noEmit
npm run build
```

Expected: PASS for Vitest and TypeScript, and Vite emits a production build without errors.

- [ ] **Step 3: Restart local services**

Run from repo root:

```bash
./START_ALL_SERVICES.sh
```

Expected: finance-mcp, data-agent, and finance-web restart. Confirm health:

```bash
curl -s http://localhost:3335/health
curl -s http://localhost:8100/health
```

Expected: each response indicates the service is healthy.

- [ ] **Step 4: Manual smoke test in the browser**

Open `http://localhost:5173`, then:

1. Navigate to the reconciliation workspace.
2. Open the "运行记录" tab.
3. Pick a run where `execution_status='failed'`.
4. Confirm the row shows "重试" and does not show "差异消化".
5. Click "重试".
6. Confirm the toast text is `已发起重试,当前运行记录将更新为最新执行结果。`.
7. Refresh the run list and confirm the same run id is now `running`; no new run id appears for this retry.
8. After completion, confirm the same run id becomes `success` or `failed`.
9. When the retry succeeds, query the run's exceptions and confirm old exceptions were removed before the latest exceptions were written.
10. Pick a successful run and confirm it shows "差异消化" and not "重试".
11. Pick a running or waiting run and confirm neither action is shown.

- [ ] **Step 5: Inspect git diff for accidental scope creep**

Run:

```bash
git status --short
git diff --stat HEAD
git diff -- finance-mcp/auth/db.py finance-mcp/tools/execution_runs.py finance-agents/data-agent/graphs/recon/auto_run_service.py finance-agents/data-agent/graphs/recon/auto_run_api.py finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-web/src/components/ReconWorkspace.tsx
```

Expected: only retry-related changes are present; no unrelated generated files or formatting churn.

- [ ] **Step 6: Final commit**

When the manual smoke test produces any small fixes, commit them:

```bash
git add finance-mcp finance-agents/data-agent finance-web
git commit -m "test(recon): verify failed run retry flow"
```

If no files changed after Task 4, do not create an empty commit.

## Self-Review

- Spec coverage:
  - Failed-only retry button is covered by Task 4 helper and component tests.
  - Successful runs showing only diff digestion is covered by Task 4 helper and component tests.
  - Non-terminal runs showing neither action is covered by Task 4 helper and component tests.
  - In-place retry without creating a new run is covered by Task 2 `execution_run_id` context and Task 3 worker propagation.
  - Old exceptions clear only after successful execution reaches the exception-writing phase is covered by Task 3.
  - Retry failure preserving old exceptions follows from Task 3 cleanup living only in `create_exception_tasks_node()`, which is not reached by failed execution persistence.
  - `retry_history` audit and 20-entry cap are covered by Task 2.
- Placeholder scan:
  - The plan contains no unresolved markers or vague "add tests" steps.
  - Each code-changing step includes exact snippets or exact replacement code.
- Type consistency:
  - Backend uses `execution_status == "failed"` and `"success"` consistently.
  - Queue context keys are consistently `target_run_id`, `execution_run_id`, and `retry_from_failed_run_id`.
  - Frontend helper uses `executionStatus`, matching `ReconCenterRunItem`.
