# Alipay Immediate Initial Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Alipay authorization immediately start T-1 bill collection in the background instead of only creating deferred sync job records.

**Architecture:** Reuse the existing unified collection entrypoint `trigger_dataset_collection_for_company()` so Alipay initialization gets normal sync job, attempt, event, health, checkpoint, and idempotency behavior. Match the Taobao/Tmall callback pattern: create datasets during callback, then `asyncio.create_task()` a serial runner that triggers the two Alipay T-1 collection jobs. The Alipay collection driver continues to write `platform_alipay_bill_lines`; no `dataset_collection_records` fallback is introduced.

**Tech Stack:** Python async functions in `finance-mcp`, PostgreSQL-backed auth/sync job records, pytest/anyio, existing Alipay platform connector and data source collection driver.

---

## Decision Lock

These decisions are confirmed and must not be changed during implementation without explicit user approval:

- **MUST** trigger Alipay T-1 initialization immediately after authorization succeeds.
- **MUST** run the initialization asynchronously so the callback response is not blocked by bill download.
- **MUST** use `trigger_dataset_collection_for_company()` for initialization execution.
- **MUST** write actual Alipay bill rows to `platform_alipay_bill_lines`.
- **MUST NOT** implement initialization as only `create_unified_sync_job()` with `deferred_until = "alipay_bill_collector"`.
- **MUST NOT** write Alipay bills to `dataset_collection_records`.
- **MUST NOT** change the initialization range from T-1 only.
- **MUST NOT** change the daily 10:30 T-1 scheduled collection.

If implementation pressure suggests any of these should change, stop and ask the user first.

## File Structure

- Modify `finance-mcp/tools/platform_connections.py`
  - Add `_run_alipay_initial_collection_jobs()` next to the Taobao runner.
  - Replace `_schedule_alipay_initial_collection_jobs()` usage in the Alipay callback with `asyncio.create_task(_run_alipay_initial_collection_jobs(...))`.
  - Remove `_schedule_alipay_initial_collection_jobs()` if no longer used.
- Modify `finance-mcp/tests/test_platform_connections_alipay.py`
  - Update callback behavior test so it asserts immediate runner scheduling, not deferred job creation.
  - Add direct runner test to prove each T-1 Alipay payload calls `trigger_dataset_collection_for_company()` with the correct parameters.

No frontend changes are required for this fix. Existing user work in `finance-web/` must not be touched.

---

### Task 1: Lock Authorization Callback Behavior

**Files:**
- Modify: `finance-mcp/tests/test_platform_connections_alipay.py`

- [ ] **Step 1: Replace deferred-job assertions with immediate-runner assertions**

In `finance-mcp/tests/test_platform_connections_alipay.py`, inside `test_alipay_callback_creates_merchant_and_two_datasets`, change the call tracking shape from:

```python
    calls: dict[str, list[Any]] = {
        "shop_connections": [],
        "authorizations": [],
        "sync_sources": [],
        "data_sources": [],
        "datasets": [],
        "callbacks": [],
        "scheduled": [],
    }
```

to:

```python
    calls: dict[str, list[Any]] = {
        "shop_connections": [],
        "authorizations": [],
        "sync_sources": [],
        "data_sources": [],
        "datasets": [],
        "callbacks": [],
        "initial_collection_tasks": [],
    }
```

- [ ] **Step 2: Make deferred-job creation fail in the callback test**

In the same test, replace `fake_create_unified_sync_job` and its monkeypatch with a guard that fails if the callback tries to create a deferred-only sync job:

```python
    def forbidden_create_unified_sync_job(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Alipay authorization callback must trigger initial collection, not create deferred sync jobs")
```

Monkeypatch it:

```python
    monkeypatch.setattr(
        platform_connections.auth_db,
        "create_unified_sync_job",
        forbidden_create_unified_sync_job,
    )
```

- [ ] **Step 3: Capture `asyncio.create_task()` and the Alipay runner call**

Still inside `test_alipay_callback_creates_merchant_and_two_datasets`, add before calling `_handle_auth_callback`:

```python
    created_tasks: list[CompletedTask] = []

    class CompletedTask:
        def __init__(self, coroutine: Any):
            self.coroutine = coroutine

    async def fake_run_alipay_initial_collection_jobs(**kwargs: Any) -> None:
        calls["initial_collection_tasks"].append(kwargs)

    def fake_create_task(coroutine: Any) -> CompletedTask:
        task = CompletedTask(coroutine)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(
        platform_connections,
        "_run_alipay_initial_collection_jobs",
        fake_run_alipay_initial_collection_jobs,
        raising=False,
    )
    monkeypatch.setattr(platform_connections.asyncio, "create_task", fake_create_task)
```

Then immediately after `_handle_auth_callback(...)` returns, execute the captured coroutine so the test can inspect the runner arguments. Do not use `result`; `_handle_auth_callback()` should not expose the task.

```python
    assert len(created_tasks) == 1
    await created_tasks[0].coroutine
```

- [ ] **Step 4: Replace scheduled-job assertions**

Remove the assertions that expect `calls["scheduled"]`, `window_start`, `window_end`, and `request_payload["deferred_until"]`.

Add assertions for the runner call:

```python
    assert len(calls["initial_collection_tasks"]) == 1
    initial_task = calls["initial_collection_tasks"][0]
    assert initial_task["company_id"] == "company-1"
    jobs = initial_task["jobs"]
    assert len(jobs) == 2
    expected_bill_date = (datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=1)).isoformat()
    assert {job["source_id"] for job in jobs} == {"source-alipay-1"}
    assert {job["dataset_id"] for job in jobs} == {"dataset-0", "dataset-1"}
    assert {job["resource_key"] for job in jobs} == {
        "alipay_bill:signcustomer:shop-alipay-1",
        "alipay_bill:trade:shop-alipay-1",
    }
    assert all(job["trigger_mode"] == "initial" for job in jobs)
    assert all("alipay-initial:" in job["idempotency_key"] for job in jobs)
    assert all(job["params"]["bill_date"] == expected_bill_date for job in jobs)
    assert all(job["params"]["biz_date"] == expected_bill_date for job in jobs)
    assert {job["params"]["bill_type"] for job in jobs} == {"signcustomer", "trade"}
    assert all("deferred_until" not in job for job in jobs)
    assert all("deferred_until" not in job.get("params", {}) for job in jobs)
```

- [ ] **Step 5: Run the callback test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest finance-mcp/tests/test_platform_connections_alipay.py::test_alipay_callback_creates_merchant_and_two_datasets -q
```

Expected: FAIL because `_run_alipay_initial_collection_jobs` does not exist or because the current callback still calls `create_unified_sync_job()`.

- [ ] **Step 6: Commit the failing test**

Do not commit a failing test alone. Continue to Task 2 for implementation before committing.

---

### Task 2: Implement Immediate Alipay Initial Collection Runner

**Files:**
- Modify: `finance-mcp/tools/platform_connections.py`
- Modify: `finance-mcp/tests/test_platform_connections_alipay.py`

- [ ] **Step 1: Add a direct runner test**

Append this test to `finance-mcp/tests/test_platform_connections_alipay.py`:

```python
@pytest.mark.anyio
async def test_run_alipay_initial_collection_jobs_triggers_dataset_collection(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_trigger_dataset_collection_for_company(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"success": True, "job": {"id": f"job-{len(calls)}"}}

    class FakeDataSources:
        trigger_dataset_collection_for_company = staticmethod(fake_trigger_dataset_collection_for_company)

    original_import = __import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "tools" and "data_sources" in fromlist:
            return type("ToolsModule", (), {"data_sources": FakeDataSources})()
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    await platform_connections._run_alipay_initial_collection_jobs(
        company_id="company-1",
        jobs=[
            {
                "source_id": "source-alipay-1",
                "dataset_id": "dataset-fund",
                "resource_key": "alipay_bill:signcustomer:shop-alipay-1",
                "trigger_mode": "initial",
                "idempotency_key": "alipay-initial:dataset-fund:signcustomer:2026-05-08",
                "background": True,
                "params": {
                    "dataset_id": "dataset-fund",
                    "resource_key": "alipay_bill:signcustomer:shop-alipay-1",
                    "bill_type": "signcustomer",
                    "bill_date": "2026-05-08",
                    "biz_date": "2026-05-08",
                    "force_mode": "initial",
                },
            },
            {
                "source_id": "source-alipay-1",
                "dataset_id": "dataset-trade",
                "resource_key": "alipay_bill:trade:shop-alipay-1",
                "trigger_mode": "initial",
                "idempotency_key": "alipay-initial:dataset-trade:trade:2026-05-08",
                "background": True,
                "params": {
                    "dataset_id": "dataset-trade",
                    "resource_key": "alipay_bill:trade:shop-alipay-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-08",
                    "biz_date": "2026-05-08",
                    "force_mode": "initial",
                },
            },
        ],
    )

    assert [call["dataset_id"] for call in calls] == ["dataset-fund", "dataset-trade"]
    assert all(call["company_id"] == "company-1" for call in calls)
    assert all(call["source_id"] == "source-alipay-1" for call in calls)
    assert all(call["trigger_mode"] == "initial" for call in calls)
    assert all(call["background"] is False for call in calls)
    assert [call["resource_key"] for call in calls] == [
        "alipay_bill:signcustomer:shop-alipay-1",
        "alipay_bill:trade:shop-alipay-1",
    ]
    assert [call["params"]["bill_date"] for call in calls] == ["2026-05-08", "2026-05-08"]
    assert [call["params"]["biz_date"] for call in calls] == ["2026-05-08", "2026-05-08"]
    assert all("alipay-initial:" in call["idempotency_key"] for call in calls)
```

- [ ] **Step 2: Run the direct runner test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest finance-mcp/tests/test_platform_connections_alipay.py::test_run_alipay_initial_collection_jobs_triggers_dataset_collection -q
```

Expected: FAIL because `_run_alipay_initial_collection_jobs` does not exist.

- [ ] **Step 3: Add `_run_alipay_initial_collection_jobs()`**

In `finance-mcp/tools/platform_connections.py`, after `_run_taobao_initial_collection_jobs()`, add:

```python
async def _run_alipay_initial_collection_jobs(
    *,
    company_id: str,
    jobs: list[dict[str, Any]],
) -> None:
    """按账单类型串行执行支付宝 T-1 初始化采集任务。"""
    from tools import data_sources

    for job_payload in jobs:
        try:
            await data_sources.trigger_dataset_collection_for_company(
                company_id=company_id,
                source_id=str(job_payload.get("source_id") or ""),
                dataset_id=str(job_payload.get("dataset_id") or ""),
                resource_key=str(job_payload.get("resource_key") or ""),
                trigger_mode=str(job_payload.get("trigger_mode") or "initial"),
                idempotency_key=str(job_payload.get("idempotency_key") or ""),
                background=False,
                params=dict(job_payload.get("params") or {}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "支付宝初始化采集任务执行失败: company_id=%s dataset_id=%s resource_key=%s error=%s",
                company_id,
                job_payload.get("dataset_id"),
                job_payload.get("resource_key"),
                exc,
                exc_info=True,
            )
```

- [ ] **Step 4: Replace callback scheduling**

In `finance-mcp/tools/platform_connections.py`, inside the Alipay branch of `_handle_auth_callback()`, replace:

```python
                if alipay_jobs:
                    _schedule_alipay_initial_collection_jobs(
                        company_id=company_id,
                        jobs=alipay_jobs,
                    )
```

with:

```python
                if alipay_jobs:
                    asyncio.create_task(
                        _run_alipay_initial_collection_jobs(
                            company_id=company_id,
                            jobs=alipay_jobs,
                        )
                    )
```

- [ ] **Step 5: Remove the deferred scheduler function**

Delete `_schedule_alipay_initial_collection_jobs()` from `finance-mcp/tools/platform_connections.py`.

Then run:

```bash
rg -n "_schedule_alipay_initial_collection_jobs|deferred_until.*alipay_bill_collector|alipay_bill_collector" finance-mcp/tools/platform_connections.py finance-mcp/tests/test_platform_connections_alipay.py
```

Expected: no matches.

- [ ] **Step 6: Run Alipay platform connection tests**

Run:

```bash
.venv/bin/python -m pytest finance-mcp/tests/test_platform_connections_alipay.py -q
```

Expected: PASS.

- [ ] **Step 7: Compile changed module**

Run:

```bash
.venv/bin/python -m py_compile finance-mcp/tools/platform_connections.py
```

Expected: no output and exit 0.

- [ ] **Step 8: Commit immediate initialization fix**

```bash
git add finance-mcp/tools/platform_connections.py finance-mcp/tests/test_platform_connections_alipay.py
git commit -m "fix: trigger alipay initial collection after auth"
```

---

### Task 3: Integration Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused platform authorization tests**

Run:

```bash
.venv/bin/python -m pytest \
  finance-mcp/tests/test_platform_connections_alipay.py \
  finance-mcp/tests/test_platform_order_collection.py \
  finance-mcp/tests/test_scheduler_collection_plans.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full MCP backend tests**

Run:

```bash
.venv/bin/python -m pytest finance-mcp/tests -q
```

Expected: PASS.

- [ ] **Step 3: Confirm no deferred-only Alipay initialization remains**

Run:

```bash
rg -n "deferred_until.*alipay_bill_collector|alipay_bill_collector|_schedule_alipay_initial_collection_jobs" finance-mcp
```

Expected: no matches.

- [ ] **Step 4: Restart services**

Run:

```bash
./START_ALL_SERVICES.sh
```

Expected: all services report healthy.

- [ ] **Step 5: Health checks**

Run:

```bash
curl -s http://127.0.0.1:3335/health
curl -s http://127.0.0.1:8100/health
curl -I http://127.0.0.1:5173
```

Expected:

- MCP returns `status=healthy`.
- data-agent returns `status=ok`.
- finance-web returns HTTP 200.

- [ ] **Step 6: Git status check**

Run:

```bash
git status --short
```

Expected:

- Implementation files are clean after commits.
- Existing unrelated `finance-web/` modifications and recon output files may still be present; do not stage or revert them.

---

## Self-Review

- Spec coverage:
  - Immediate background initialization: Tasks 1 and 2.
  - Unified collection entrypoint: Task 2 direct runner test and implementation.
  - T-1 only payload: callback and runner assertions.
  - No deferred-only job: callback guard and grep verification.
  - Dedicated table preservation: existing platform collection tests included in Task 3.
  - Daily 10:30 unchanged: no scheduler code changes; scheduler tests included.
- Placeholder scan:
  - No placeholder implementation instructions remain.
- Type consistency:
  - Runner name is consistently `_run_alipay_initial_collection_jobs`.
  - Job payload keys match `_build_alipay_initial_collection_jobs`.
  - Collection entrypoint is consistently `data_sources.trigger_dataset_collection_for_company`.
