# Browser First-Store Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the browser first-store loop so one real QianNiu/Taobao shop can automatically collect data on a collection machine, persist records/files, unblock T-1 reconciliation, and fail fast with actionable reasons.

**Architecture:** Keep Tally Cloud as the source of truth for `sync_jobs`, `browser_collection_records`, `browser_capture_files`, published datasets, and `recon_execution_queue`. Move browser execution into a long-running `finance-agents/browser-agent` service deployed on the collection machine; this service contains both dispatcher and runner responsibilities: claim browser jobs, enforce local Chrome/profile concurrency, run the deterministic playbook runner, upload results, and reconcile waiting-data jobs. Recon workers only consume `queued` reconciliation jobs and no longer poll browser waiting-data state.

**Tech Stack:** Python 3.11, FastAPI/MCP SSE client, PostgreSQL, psycopg2, Playwright-ready browser-agent structure, pytest, shell service scripts.

---

## Scope

This plan fixes the gaps found after the first browser implementation pass:

1. Add a real long-running `finance-agents/browser-agent` service that consumes `browser_playbook` `sync_jobs`.
2. Package dispatcher and runner together on the collection machine.
3. Make browser job claiming source-of-truth based (`data_sources.source_kind='browser_playbook'`), not JSON-field based.
4. Enforce per-agent and per-shop concurrency in the browser-agent service.
5. Persist `capture_files` metadata.
6. Retry transient browser failures and fail deterministic browser failures immediately.
7. Resume or fail `waiting_data` reconciliation jobs from a centralized browser-agent/cloud helper path.
8. Tighten `waiting_datasets`, `collection_job_ids`, and attempt semantics.
9. Explicitly document first-store v1 dataset publication and deferred WS/soft-delete behavior.
10. Implement real retry scheduling, not only retry classification.
11. Validate the real QianNiu Playwright runner, collection-machine environment, profile login, and layer-2 sample checks before calling first-store production-ready.

Out of scope for this plan:

- Full WebSocket runner protocol (`HELLO`, `HEARTBEAT`, ack lease) unless explicitly added later.
- noVNC or live browser UI.
- AI authoring worker.
- Customer-facing browser onboarding UI.
- Multi-machine fleet assignment beyond safe DB claiming and agent concurrency.

Capacity note: `BROWSER_AGENT_MAX_CONCURRENCY=2` means two different shop profiles can run at the same time. It does not make one shop run two browser sessions concurrently, because `ProfileLockRegistry` serializes work per `shop_id` to protect the persistent Chrome profile. Throughput verification for concurrency must use at least two different shops or two different profile roots.

## Mandatory Corrections From Review

These corrections override any conflicting task text later in this plan.

| Area | Required correction |
| --- | --- |
| Retry | `retryable=True` must create a real retry path: the browser sync job is not terminally failed until retry attempts are exhausted. It must be rescheduled with `next_retry_at`, respect a max-attempt limit of 3, and be skipped by claim SQL until due. |
| Concurrency | `BROWSER_AGENT_MAX_CONCURRENCY=2` must run two concurrent dispatcher workers or equivalent concurrent claim/process tasks. A semaphore inside a serial loop is not sufficient. |
| Agent routing | Browser job claim must join `shop_runtime_bindings` and filter by `shop_runtime_bindings.agent_id = :agent_id`. A browser-agent may only claim shops bound to itself. |
| Claim enrichment | `browser_sync_job_claim` must return the runnable message inputs: shop binding, active playbook body, playbook version, profile ref, egress group, credential ref, and normalized params. The browser-agent must not rely on raw `sync_jobs.request_payload` containing `shop_id` or `playbook_body`. |
| Health gate | Browser job claim must require `profile_status='active'` and `playbook_status='ok'`. Browser trigger/claim must not dispatch stale, risk-blocked, or reauth-required shops into Chrome. |
| Async runner isolation | The browser-agent event loop must not run sync Playwright directly. If the runner uses `playwright.sync_api`, dispatcher workers must call it through `asyncio.to_thread(...)`; otherwise max concurrency is fake. |
| Binding state transitions | `AUTH_EXPIRED` updates `profile_status='needs_reauth'`; `RISK_VERIFICATION` updates `profile_status='risk_blocked'`; `PAGE_CHANGED` updates `playbook_status='stale'`; all set `cron_pause_reason` so future scheduled collection pauses until operator action. |
| Token refresh | Browser-agent system tokens must be refreshed automatically. A token minted once at process start is invalid after 2 hours and is not acceptable. |
| Error clarity | Waiting-data fast-fail errors must include the browser `fail_reason` prefix, for example `AUTH_EXPIRED: 登录过期`. |
| Production runner | First-store is not production-ready until the QianNiu playbook runs with real Playwright actions against real pages and validates 2-3 real business dates. The skeleton runner alone is not enough. |
| Collection machine | The plan must verify Chrome/Playwright dependencies, persistent profile directory, timezone, fonts, download directory, and first-login SOP. |
| Risk verification | Because noVNC is deferred, v1 must document and test the operational fallback: mark `risk_blocked`, pause cron, and require manual profile intervention before re-enable. |

## Architecture Decisions

### Browser-Agent Owns Dispatcher + Runner

Do not create a cloud-only dispatcher that pushes work to runners. The first-store production-trial architecture is:

```text
Tally Cloud
  finance-mcp
    - creates browser sync_jobs.pending
    - stores records/files
    - owns recon_execution_queue

Collection Machine
  finance-agents/browser-agent/service.py
    - polls/claims browser sync_jobs from finance-mcp
    - enforces local concurrency and per-shop profile lock
    - calls local runner.run_message()
    - uploads records/capture_files and marks sync job success/failed
    - periodically resumes/fails waiting_data recon jobs
```

This keeps Chrome/profile/download handling close to the machine that owns those resources and avoids blocking `finance-mcp` or `recon-worker`.

### Recon Waiting-Data Recovery

Recon workers do not need direct notification. They keep polling `recon_execution_queue` for `queued` jobs. Browser-agent or a cloud queue helper changes `waiting_data` back to `queued` after browser data is ready:

```text
browser sync_job success -> waiting_data recon job queued
browser sync_job deterministic failed -> waiting_data recon job failed
waiting_data deadline expired -> failed
```

The MVP implementation centralizes this recovery in browser-agent calling MCP queue tools. A DB-level guard prevents empty `collection_job_ids` from being requeued.

### Dataset Publication

First-store v1 uses manual bootstrap:

- The operator creates a `browser_playbook` data source.
- The operator publishes one `data_source_datasets` row with `source_type='browser_collection_records'`.
- The operator registers the playbook and shop binding.
- Collection writes rows into `browser_collection_records` for that published dataset.

This plan does not auto-create or auto-publish datasets after collection. It adds explicit validation and documentation so first-store setup cannot be mistaken for automatic publication.

### Frontend (v1 mandatory)

The first-store onboarding flow needs a real UI — operator cannot persist merchant credentials
through MCP / CLI tools alone. v1 ships **`finance-web/src/components/BrowserPlaybookPanel.tsx`**,
mounted on the `数据连接 → 浏览器` card. This card **reuses the slot previously held by
the legacy `source_kind='browser'` placeholder**: the placeholder card text is gone, the slot
now renders the real `browser_playbook` registration / verification / activation form.

The 「Playbooks / Authoring Jobs / Agents / Shops」 standalone operator pages described in the
main spec are **v2 scope** — v1 only ships the single `BrowserPlaybookPanel`, which is enough
to drive registration → first-time verification dry-run → finalize activation end-to-end.

### Deferred Behaviors

Full WS protocol and browser-record soft delete remain deferred for first-store v1:

- The first-store service uses MCP polling/claim APIs plus local runner calls, not WS push.
- Missing records on recapture are not marked `deleted` in v1. This is documented and tested as a known limitation, not silently implied as complete.
- Canary playbook version routing is deferred. First-store v1 claims only `p.status='active'`; future canary rollout must route `shop_id IN canary_shop_ids` to the canary version before broad rollout.
- Pending browser sync-job cleanup is deferred. If a binding becomes `stale`, `risk_blocked`, or `needs_reauth` after trigger but before claim, the pending job may remain unclaimable until manual cleanup.
- Standalone Playbooks / Authoring Jobs / Agents / Shops operator pages are deferred; v1 covers everything through `BrowserPlaybookPanel`.
- Authoring Worker v2 (Claude Agent SDK + DeepSeek-V4 Pro in-product natural-language playbook generation) is deferred; v1 operators use Claude Code or codex locally and paste JSON into the panel.

---

## File Structure

Create:

- `finance-agents/browser-agent/service.py`
  - Long-running browser-agent process entrypoint.
  - Creates system token, initializes MCP client, runs dispatcher loop and waiting-data reconciler loop.
- `finance-agents/browser-agent/finance_browser_agent/tally_client.py`
  - Async MCP client wrappers used by browser-agent.
  - Calls browser sync-job tools and recon waiting-data tools.
  - Refreshes the system token before expiry for long-running service operation.
- `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
  - Claims jobs, starts concurrent workers, enforces local concurrency, calls runner, uploads results, handles retries/failures.
- `finance-agents/browser-agent/finance_browser_agent/failure_policy.py`
  - Classifies browser result failures as transient or deterministic.
- `finance-agents/browser-agent/finance_browser_agent/profile_locks.py`
  - Per-shop `asyncio.Lock` registry for Chrome profile serialization.
- `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
  - Real Playwright interpreter for the v1 action set against QianNiu pages.
- `finance-agents/browser-agent/scripts/check_environment.py`
  - Collection-machine dependency and profile path checks.
- `finance-agents/browser-agent/tests/test_dispatcher_loop.py`
  - Unit tests for claim/execute/upload/retry/fail behavior.
- `finance-agents/browser-agent/tests/test_failure_policy.py`
  - Unit tests for transient vs deterministic classification.
- `finance-mcp/tests/test_browser_waiting_data_queue.py`
  - DB helper tests for empty job IDs, failed job propagation, and ready requeue.
- `finance-mcp/tests/test_browser_capture_files.py`
  - DB helper tests for capture file insertion.
- `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`
  - Short design addendum that freezes the dispatcher+runner packaging and deferred items.

Modify:

- `finance-mcp/auth/migrations/031_browser_playbook_collection.sql`
  - Add any missing capture-file columns and indexes required by helper queries.
  - Add browser retry scheduling columns to `sync_jobs` if not already available.
- `finance-mcp/auth/db.py`
  - Browser job claim by joining `data_sources` and `shop_runtime_bindings`.
  - Filter claims by `agent_id`, `profile_status='active'`, and `playbook_status='ok'`.
  - Insert capture files.
  - Mark waiting-data jobs ready/failed with safe guards.
  - Add real browser job retry scheduling helper.
  - Add browser binding state transition helper.
- `finance-mcp/tools/data_sources.py`
  - Add worker-only MCP tools for browser sync job claim, success, failure, and capture result upload.
  - Validate manual browser bootstrap has an existing published dataset.
  - Reject browser dataset collection before creating a sync job when the shop binding is not runnable.
  - Lock browser short-circuit tests around dataset collection path.
- `finance-mcp/tools/recon_auto_runs.py`
  - Replace generic waiting-data helpers with guarded ready/fail behavior, or add browser-specific helpers that call new DB functions.
- `finance-agents/data-agent/recon_worker.py`
  - Remove per-worker ready/expired waiting-data polling once browser-agent owns it.
  - Keep only `data_waiting -> recon_queue_waiting_data`.
- `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
  - Ensure `waiting_datasets` contains only actually waiting browser datasets.
- `finance-agents/data-agent/graphs/recon/auto_run_service.py`
  - Ensure service-level waiting responses also include only browser queued datasets.
- `finance-agents/data-agent/tools/mcp_client.py`
  - Remove browser waiting-data recovery wrappers if no remaining recon-worker code calls them.
  - Keep `recon_queue_waiting_data` because recon-worker still needs to park a job when browser data is not ready.
- `START_ALL_SERVICES.sh`
  - Start one `browser-agent` process by default for local/dev.
  - Stop stale browser-agent processes and verify it is alive.
- `STOP_ALL_SERVICES.sh`
  - Stop browser-agent pid if present.
- `docs/superpowers/plans/2026-05-20-browser-first-store-hardening-notes.md`
  - Mark superseded by this formal plan.

---

## Task 1: Design Addendum And Plan Supersession

**Files:**

- Create: `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`
- Modify: `docs/superpowers/plans/2026-05-20-browser-first-store-hardening-notes.md`

- [ ] **Step 1: Write the design addendum**

Create `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md` with these sections:

```markdown
# Browser First-Store Production Hardening Design

## Decision

First-store browser collection is not complete until a real shop can automatically create a browser collection job, have it consumed by a long-running collection-machine service, persist browser records and capture files, and resume or fail reconciliation without manual process calls.

The collection-machine process is `finance-agents/browser-agent/service.py`. It packages dispatcher and runner together. Tally Cloud remains the queue and data source of truth.

## Runtime Flow

1. `data_source_trigger_dataset_collection` creates `sync_jobs.pending` for a published browser dataset.
2. `finance-agents/browser-agent/service.py` claims pending browser jobs from finance-mcp.
3. The browser-agent enforces per-shop profile lock and local concurrency.
4. The browser-agent calls local `runner.run_message()`.
5. On success it uploads records and `capture_files`, then marks the sync job success.
6. On deterministic failure it marks the sync job failed and fails any waiting recon job immediately.
7. On transient failure it retries according to the browser retry policy.
8. `recon_execution_queue.waiting_data` jobs are restored to `queued` only when their non-empty `collection_job_ids` all point to successful sync jobs.

## Compatibility

Database, platform OAuth, and API collection remain unchanged. They may continue to execute inside finance-mcp because they are deterministic programmatic collectors. Browser collection uses browser-agent because it owns Chrome, profiles, downloads, and local concurrency.

## First-Store Dataset Publication

First-store v1 requires manual data-source dataset publication before collection. The browser-agent writes into the existing dataset id supplied by the queued sync job. Automatic dataset publication is deferred.

## Deferred

- Full WS runner protocol with HELLO/HEARTBEAT/ack lease.
- noVNC live browser UI.
- Browser-record soft delete for rows missing from a later recapture.
- Canary playbook version routing.
- Stale pending browser sync-job cleanup.
- Multi-machine fleet assignment UI.
```

- [ ] **Step 2: Mark the hardening notes as superseded**

At the top of `docs/superpowers/plans/2026-05-20-browser-first-store-hardening-notes.md`, change the status line to:

```markdown
> Status: superseded by `docs/superpowers/plans/2026-05-20-browser-first-store-production-hardening.md`.
```

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md docs/superpowers/plans/2026-05-20-browser-first-store-hardening-notes.md
git commit -m "docs: define browser first-store hardening design"
```

---

## Task 2: Browser Waiting-Data Queue Guards

**Files:**

- Modify: `finance-mcp/auth/db.py`
- Modify: `finance-mcp/tools/recon_auto_runs.py`
- Test: `finance-mcp/tests/test_browser_waiting_data_queue.py`

- [ ] **Step 1: Add failing tests**

Create `finance-mcp/tests/test_browser_waiting_data_queue.py`:

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


def test_requeue_ready_waiting_requires_non_empty_collection_jobs(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.requeue_ready_waiting_recon_runs()

    sql = "\n".join(cursor.sql)
    assert "jsonb_array_length(collection_job_ids) > 0" in sql
    assert "status = 'waiting_data'" in sql


def test_fail_waiting_recon_runs_with_failed_browser_jobs_uses_collection_job_ids(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))

    auth_db.fail_waiting_recon_runs_with_failed_collection_jobs()

    sql = "\n".join(cursor.sql)
    assert "status = 'waiting_data'" in sql
    assert "jsonb_array_elements_text(collection_job_ids)" in sql
    assert "s.job_status = 'failed'" in sql
    assert "s.error_message" in sql
    assert "s.browser_fail_reason" in sql
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_waiting_data_queue.py -q
```

Expected: FAIL because `fail_waiting_recon_runs_with_failed_collection_jobs` does not exist and the requeue guard is missing.

- [ ] **Step 3: Add guarded ready requeue**

In `finance-mcp/auth/db.py`, update `requeue_ready_waiting_recon_runs()` SQL so the `WHERE` block includes:

```sql
AND jsonb_typeof(collection_job_ids) = 'array'
AND jsonb_array_length(collection_job_ids) > 0
AND NOT EXISTS (
    SELECT 1
    FROM jsonb_array_elements_text(collection_job_ids) job_id
    JOIN sync_jobs s ON s.id::text = job_id
    WHERE s.job_status <> 'success'
)
```

- [ ] **Step 4: Add fast-fail helper**

Add this function to `finance-mcp/auth/db.py` near the waiting-data helpers:

```python
def fail_waiting_recon_runs_with_failed_collection_jobs() -> int:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue q
                    SET status = 'failed',
                        finished_at = CURRENT_TIMESTAMP,
                        error = COALESCE(NULLIF(f.failed_error, ''), q.waiting_reason, '浏览器采集失败'),
                        updated_at = CURRENT_TIMESTAMP
                    FROM (
                        SELECT q0.id AS queue_id,
                               string_agg(
                                   DISTINCT CONCAT(
                                       COALESCE(NULLIF(s.browser_fail_reason, ''), NULLIF(s.checkpoint_after ->> 'fail_reason', ''), 'BROWSER_COLLECTION_FAILED'),
                                       ': ',
                                       COALESCE(NULLIF(REGEXP_REPLACE(s.error_message, '^[A-Z_]+: ', ''), ''), '浏览器采集失败')
                                   ),
                                   ' / '
                               ) AS failed_error
                        FROM recon_execution_queue q0
                        JOIN LATERAL jsonb_array_elements_text(q0.collection_job_ids) job_id ON TRUE
                        JOIN sync_jobs s ON s.id::text = job_id
                        WHERE q0.status = 'waiting_data'
                          AND s.job_status = 'failed'
                        GROUP BY q0.id
                    ) f
                    WHERE q.id = f.queue_id
                      AND q.status = 'waiting_data'
                    """
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"fail_waiting_recon_runs_with_failed_collection_jobs 失败: {e}")
        return 0
```

- [ ] **Step 5: Expose fast-fail through recon queue MCP tool**

In `finance-mcp/tools/recon_auto_runs.py`, add a tool named `recon_queue_fail_failed_collection_waiting` with required `worker_token`, route it in `handle_tool_call`, and implement:

```python
def _queue_fail_failed_collection_waiting(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        _require_system(str(arguments.get("worker_token") or ""))
    except ValueError as e:
        return {"success": False, "error": str(e)}
    return {
        "success": True,
        "failed": auth_db.fail_waiting_recon_runs_with_failed_collection_jobs(),
    }
```

- [ ] **Step 6: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_waiting_data_queue.py finance-mcp/tests/test_recon_execution_waiting_data.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add finance-mcp/auth/db.py finance-mcp/tools/recon_auto_runs.py finance-mcp/tests/test_browser_waiting_data_queue.py
git commit -m "fix: guard browser waiting data queue transitions"
```

---

## Task 3: Browser Capture File Persistence

**Files:**

- Modify: `finance-mcp/auth/db.py`
- Modify: `finance-mcp/browser_playbook/dispatcher.py`
- Test: `finance-mcp/tests/test_browser_capture_files.py`
- Test: `finance-mcp/tests/test_browser_dispatcher.py`

- [ ] **Step 1: Add failing DB helper tests**

Create `finance-mcp/tests/test_browser_capture_files.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


def test_insert_browser_capture_files_uses_execute_values(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            captured["committed"] = True

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_execute_values(cur, sql, values, template=None, page_size=1000, fetch=False):
        captured["sql"] = sql
        captured["values"] = values
        return []

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())
    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.insert_browser_capture_files(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        resource_key="qianniu-daily-bill-export@1.0.0",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-18",
        capture_files=[
            {
                "storage_path": "/tmp/export.csv",
                "encoding": "utf-8",
                "checksum": "sha256:abc",
                "row_count": 10,
            }
        ],
    )

    assert result["inserted_count"] == 1
    assert "INSERT INTO browser_capture_files" in str(captured["sql"])
    assert captured["committed"] is True
```

- [ ] **Step 2: Add failing dispatcher test**

Append to `finance-mcp/tests/test_browser_dispatcher.py` a case that registers a fake runner result with one `capture_files` entry and asserts the fake DB received it:

```python
def test_dispatcher_persists_capture_files() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "sync-001",
            "status": "success",
            "records": [],
            "capture_files": [{"storage_path": "/tmp/qn.csv", "encoding": "utf-8", "checksum": "abc", "row_count": 0}],
        },
    )
    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)

    dispatcher.run_once()

    assert fake_db.capture_files[0]["capture_files"][0]["storage_path"] == "/tmp/qn.csv"
```

Update the test `FakeDb` with:

```python
self.capture_files: list[dict[str, Any]] = []

def insert_browser_capture_files(self, **kwargs: Any) -> dict[str, Any]:
    self.capture_files.append(kwargs)
    return {"inserted_count": len(kwargs.get("capture_files") or [])}
```

- [ ] **Step 3: Implement DB helper**

Add `insert_browser_capture_files()` to `finance-mcp/auth/db.py` near browser record helpers. It must:

- Return `{"inserted_count": 0}` for empty input.
- Insert into `browser_capture_files`.
- Accept `storage_path`, `encoding`, `checksum`, `row_count`.
- Carry `company_id`, `data_source_id`, `dataset_id`, `sync_job_id`, `resource_key`, `shop_id`, `playbook_id`, `biz_date`.

- [ ] **Step 4: Call helper from dispatcher**

In `finance-mcp/browser_playbook/dispatcher.py`, after `upsert_browser_collection_records()` and before `mark_browser_sync_job_success()`, call:

```python
file_summary = self.db.insert_browser_capture_files(
    company_id=company_id,
    data_source_id=data_source_id,
    dataset_id=str(payload.get("dataset_id") or ""),
    sync_job_id=str(job["id"]),
    resource_key=str(job.get("resource_key") or ""),
    shop_id=str(binding["shop_id"]),
    playbook_id=str(playbook["playbook_id"]),
    biz_date=str(payload.get("biz_date") or ""),
    capture_files=list(result.get("capture_files") or []),
)
summary["capture_file_count"] = int(file_summary.get("inserted_count") or 0)
```

- [ ] **Step 5: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_capture_files.py finance-mcp/tests/test_browser_dispatcher.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add finance-mcp/auth/db.py finance-mcp/browser_playbook/dispatcher.py finance-mcp/tests/test_browser_capture_files.py finance-mcp/tests/test_browser_dispatcher.py
git commit -m "feat: persist browser capture files"
```

---

## Task 4: Source-Truth Browser Job Claiming And Enrichment

**Files:**

- Modify: `finance-mcp/auth/db.py`
- Test: `finance-mcp/tests/test_browser_dispatcher.py`

- [ ] **Step 1: Add failing SQL-shape test**

Add to `finance-mcp/tests/test_browser_dispatcher.py`:

```python
def test_claim_next_browser_sync_job_filters_by_source_kind_agent_and_binding_health(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql: str, params=None):
            captured["sql"] = sql

        def fetchone(self):
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    auth_db.claim_next_browser_sync_job(agent_id="agent-001")

    assert "JOIN data_sources ds ON ds.id = sync_jobs.data_source_id" in captured["sql"]
    assert "JOIN shop_runtime_bindings srb" in captured["sql"]
    assert "JOIN playbooks p" in captured["sql"]
    assert "ds.source_kind = 'browser_playbook'" in captured["sql"]
    assert "srb.agent_id = %s" in captured["sql"]
    assert "srb.profile_status = 'active'" in captured["sql"]
    assert "srb.playbook_status = 'ok'" in captured["sql"]
    assert "running_for_agent.running_count < %s" in captured["sql"]
    assert "claimed.playbook_body" in captured["sql"]
    assert "claimed.browser_binding" in captured["sql"]
    assert "request_payload ->" not in captured["sql"]


def test_claim_next_browser_sync_job_returns_enriched_fields(monkeypatch) -> None:
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql: str, params=None):
            return None

        def fetchone(self):
            return {
                "id": "sync-001",
                "company_id": "company-001",
                "data_source_id": "source-001",
                "job_status": "running",
                "request_payload": {"biz_date": "2026-05-18"},
                "shop_id": "shop-001",
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
                "playbook_body": {"steps": [{"id": "open", "action": "navigate", "url": "https://example.com"}]},
                "runtime_profile_ref": "profile-001",
                "egress_group": "wan-1",
                "credential_ref": "cred-001",
                "browser_binding": {"shop_id": "shop-001", "profile_status": "active", "playbook_status": "ok"},
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    row = auth_db.claim_next_browser_sync_job(agent_id="agent-001")

    assert row["shop_id"] == "shop-001"
    assert row["playbook_body"]["steps"][0]["action"] == "navigate"
    assert row["runtime_profile_ref"] == "profile-001"
    assert row["browser_binding"]["playbook_status"] == "ok"
```

- [ ] **Step 2: Update function signature**

Change `claim_next_browser_sync_job` signature in `finance-mcp/auth/db.py` to:

```python
def claim_next_browser_sync_job(*, agent_id: str = "", agent_max_concurrency: int = 2) -> dict | None:
```

- [ ] **Step 3: Replace JSON routing with enriched data-source claim**

Replace the browser claim SQL with a CTE that claims the job and returns all fields needed by the collection-machine browser-agent:

```sql
WITH claimed AS (
    SELECT sync_jobs.id,
           jsonb_build_object(
               'shop_id', srb.shop_id,
               'agent_id', srb.agent_id,
               'playbook_id', srb.playbook_id,
               'runtime_profile_ref', COALESCE(srb.runtime_profile_ref, ''),
               'egress_group', COALESCE(srb.egress_group, ''),
               'credential_ref', COALESCE(srb.credential_ref, ''),
               'profile_status', srb.profile_status,
               'playbook_status', srb.playbook_status
           ) AS browser_binding,
           srb.shop_id,
           srb.playbook_id,
           COALESCE(srb.runtime_profile_ref, '') AS runtime_profile_ref,
           COALESCE(srb.egress_group, '') AS egress_group,
           COALESCE(srb.credential_ref, '') AS credential_ref,
           p.version AS playbook_version,
           p.playbook_body
    FROM sync_jobs
    JOIN data_sources ds ON ds.id = sync_jobs.data_source_id
    JOIN shop_runtime_bindings srb
      ON srb.company_id = sync_jobs.company_id
     AND srb.data_source_id = sync_jobs.data_source_id
    JOIN playbooks p
      ON p.company_id = sync_jobs.company_id
     AND p.playbook_id = srb.playbook_id
     AND p.status = 'active'
    JOIN LATERAL (
        SELECT COUNT(*) AS running_count
        FROM sync_jobs running_jobs
        JOIN data_sources running_ds ON running_ds.id = running_jobs.data_source_id
        JOIN shop_runtime_bindings running_srb
          ON running_srb.company_id = running_jobs.company_id
         AND running_srb.data_source_id = running_jobs.data_source_id
        WHERE running_jobs.job_status = 'running'
          AND running_ds.source_kind = 'browser_playbook'
          AND running_srb.agent_id = %s
    ) running_for_agent ON TRUE
    WHERE sync_jobs.job_status = 'pending'
      AND ds.source_kind = 'browser_playbook'
      AND ds.status = 'active'
      AND ds.is_enabled = TRUE
      AND srb.agent_id = %s
      AND srb.profile_status = 'active'
      AND srb.playbook_status = 'ok'
      AND running_for_agent.running_count < %s
      AND (sync_jobs.next_retry_at IS NULL OR sync_jobs.next_retry_at <= CURRENT_TIMESTAMP)
    ORDER BY sync_jobs.created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE sync_jobs
SET job_status = 'running',
    started_at = CURRENT_TIMESTAMP,
    current_attempt = COALESCE(current_attempt, 0) + 1,
    updated_at = CURRENT_TIMESTAMP
FROM claimed
WHERE sync_jobs.id = claimed.id
RETURNING sync_jobs.id, sync_jobs.company_id, sync_jobs.data_source_id,
          sync_jobs.trigger_mode, sync_jobs.resource_key,
          sync_jobs.window_start, sync_jobs.window_end,
          sync_jobs.idempotency_key, sync_jobs.job_status,
          sync_jobs.request_payload, sync_jobs.checkpoint_before,
          sync_jobs.checkpoint_after, sync_jobs.active_snapshot_id,
          sync_jobs.published_snapshot_id, sync_jobs.current_attempt,
          sync_jobs.error_message, sync_jobs.started_at,
          sync_jobs.completed_at, sync_jobs.created_at, sync_jobs.updated_at,
          claimed.browser_binding, claimed.shop_id, claimed.playbook_id,
          claimed.playbook_version, claimed.playbook_body,
          claimed.runtime_profile_ref, claimed.egress_group, claimed.credential_ref
```

The claim result must be normalized so `browser_sync_job_claim` returns these top-level keys: `shop_id`, `playbook_id`, `playbook_version`, `playbook_body`, `runtime_profile_ref`, `egress_group`, `credential_ref`, and `browser_binding`. The running-count guard is DB-level protection for accidental duplicate browser-agent processes using the same `agent_id`; the browser-agent service semaphore remains the normal local concurrency control.

Implementation note: current `_normalize_record()` passes through unknown keys, which is required for the enriched return columns above. If `_normalize_record()` is changed later to use a whitelist, this test must fail until the whitelist includes the enriched browser keys or `claim_next_browser_sync_job()` returns `dict(row)` with UUID/date normalization applied.

- [ ] **Step 4: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_dispatcher.py finance-mcp/tests/test_browser_playbook_connector.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add finance-mcp/auth/db.py finance-mcp/tests/test_browser_dispatcher.py
git commit -m "fix: claim browser jobs by data source kind"
```

---

## Task 5: Browser-Agent Failure Policy

**Files:**

- Create: `finance-agents/browser-agent/finance_browser_agent/failure_policy.py`
- Test: `finance-agents/browser-agent/tests/test_failure_policy.py`

- [ ] **Step 1: Add tests**

Create `finance-agents/browser-agent/tests/test_failure_policy.py`:

```python
from __future__ import annotations

from finance_browser_agent.failure_policy import classify_failure


def test_deterministic_failures_are_not_retried() -> None:
    for reason in ["PAGE_CHANGED", "AUTH_EXPIRED", "RISK_VERIFICATION", "DATA_MISMATCH"]:
        policy = classify_failure(reason)
        assert policy.retryable is False
        assert policy.normalized_reason == reason


def test_transient_failures_are_retried() -> None:
    for reason in ["AGENT_OFFLINE", "TIMEOUT", "CHROME_CRASH", "NETWORK_ERROR", "OTHER"]:
        policy = classify_failure(reason)
        assert policy.retryable is True


def test_max_attempts_defaults_to_three() -> None:
    assert classify_failure("TIMEOUT").max_attempts == 3
```

- [ ] **Step 2: Implement failure policy**

Create `finance-agents/browser-agent/finance_browser_agent/failure_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


DETERMINISTIC_FAILURES = {
    "PAGE_CHANGED",
    "AUTH_EXPIRED",
    "RISK_VERIFICATION",
    "DATA_MISMATCH",
    "UNHEALTHY_BINDING",
}

TRANSIENT_FAILURES = {
    "AGENT_OFFLINE",
    "TIMEOUT",
    "CHROME_CRASH",
    "NETWORK_ERROR",
    "OTHER",
}


@dataclass(frozen=True)
class FailurePolicy:
    normalized_reason: str
    retryable: bool
    max_attempts: int = 3
    retry_delay_seconds: int = 1800


def classify_failure(reason: str | None) -> FailurePolicy:
    normalized = str(reason or "OTHER").strip().upper() or "OTHER"
    if normalized in DETERMINISTIC_FAILURES:
        return FailurePolicy(normalized_reason=normalized, retryable=False)
    if normalized not in TRANSIENT_FAILURES:
        normalized = "OTHER"
    return FailurePolicy(normalized_reason=normalized, retryable=True)
```

- [ ] **Step 3: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_failure_policy.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/failure_policy.py finance-agents/browser-agent/tests/test_failure_policy.py
git commit -m "feat: classify browser collection failures"
```

---

## Task 5.5: Browser Sync Job Retry Scheduling And Binding State Transitions

**Files:**

- Modify: `finance-mcp/auth/migrations/031_browser_playbook_collection.sql`
- Modify: `finance-mcp/auth/db.py`
- Test: `finance-mcp/tests/test_browser_dispatcher.py`

- [ ] **Step 1: Add retry and binding transition SQL tests**

Extend `finance-mcp/tests/test_browser_dispatcher.py` with tests that inspect SQL for retry scheduling and binding state transitions:

```python
def test_mark_browser_sync_job_failed_retryable_reschedules_pending(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql: str, params=None):
            captured["sql"] = sql

        def fetchone(self):
            return {"id": "sync-001", "job_status": "pending"}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    auth_db.mark_browser_sync_job_failed(
        sync_job_id="sync-001",
        error_message="timeout",
        fail_reason="TIMEOUT",
        retryable=True,
        max_attempts=3,
        retry_delay_seconds=1800,
    )

    sql = captured["sql"]
    assert "job_status = CASE" in sql
    assert "next_retry_at = CASE" in sql
    assert "browser_fail_reason" in sql


def test_apply_browser_binding_failure_transition_maps_reasons(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql: str, params=None):
            captured["sql"] = sql

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            return None

    class FakeConnManager:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager())

    auth_db.apply_browser_binding_failure_transition(sync_job_id="sync-001", fail_reason="AUTH_EXPIRED")

    sql = captured["sql"]
    assert "profile_status = CASE" in sql
    assert "playbook_status = CASE" in sql
    assert "cron_pause_reason" in sql
```

- [ ] **Step 2: Add retry scheduling columns**

In `finance-mcp/auth/migrations/031_browser_playbook_collection.sql`, add:

```sql
ALTER TABLE public.sync_jobs
    ADD COLUMN IF NOT EXISTS next_retry_at timestamptz,
    ADD COLUMN IF NOT EXISTS browser_fail_reason character varying(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3;

CREATE INDEX IF NOT EXISTS idx_sync_jobs_browser_pending_retry
    ON public.sync_jobs (next_retry_at ASC, created_at ASC)
    WHERE job_status = 'pending';
```

- [ ] **Step 3: Update schema readiness**

In `finance-mcp/auth/db.py`, include `next_retry_at`, `browser_fail_reason`, and `max_attempts` in the browser schema readiness checks for `sync_jobs`.

- [ ] **Step 4: Implement real retry scheduling**

Update `mark_browser_sync_job_failed` in `finance-mcp/auth/db.py` to accept:

```python
def mark_browser_sync_job_failed(
    *,
    sync_job_id: str,
    error_message: str,
    fail_reason: str,
    retryable: bool = False,
    max_attempts: int = 3,
    retry_delay_seconds: int = 1800,
) -> dict | None:
```

Behavior:

- Always write `browser_fail_reason`.
- Normalize `error_message` before storage so final failed jobs include the reason prefix exactly once: `"{fail_reason}: {message_without_existing_prefix}"`.
- If `retryable=True` and `current_attempt < max_attempts`, set `job_status='pending'`, `next_retry_at=CURRENT_TIMESTAMP + retry_delay_seconds`, `completed_at=NULL`, and keep `checkpoint_after.fail_reason`.
- Otherwise set `job_status='failed'`, `completed_at=CURRENT_TIMESTAMP`, and keep `checkpoint_after.fail_reason`.

The SQL must include:

```sql
job_status = CASE
    WHEN %s = TRUE AND COALESCE(current_attempt, 0) < %s THEN 'pending'
    ELSE 'failed'
END
```

The returned row for a final failed job must expose both `browser_fail_reason` and prefixed `error_message`. Waiting-data fast-fail can then surface `AUTH_EXPIRED: 登录过期` without requiring an operator to open the underlying sync job.

- [ ] **Step 5: Implement binding failure state transition**

Add `apply_browser_binding_failure_transition(sync_job_id: str, fail_reason: str) -> int` to `finance-mcp/auth/db.py`:

```sql
UPDATE shop_runtime_bindings b
SET profile_status = CASE
        WHEN %s = 'AUTH_EXPIRED' THEN 'needs_reauth'
        WHEN %s = 'RISK_VERIFICATION' THEN 'risk_blocked'
        ELSE profile_status
    END,
    playbook_status = CASE
        WHEN %s = 'PAGE_CHANGED' THEN 'stale'
        ELSE playbook_status
    END,
    cron_pause_reason = CASE
        WHEN %s IN ('AUTH_EXPIRED', 'RISK_VERIFICATION', 'PAGE_CHANGED') THEN %s
        ELSE cron_pause_reason
    END,
    updated_at = CURRENT_TIMESTAMP
FROM sync_jobs s
WHERE s.id = %s
  AND b.company_id = s.company_id
  AND b.data_source_id = s.data_source_id
```

Call this from `mark_browser_sync_job_failed` only after reading the `UPDATE ... RETURNING` row and only when `row["job_status"] == "failed"`. Do not call it when `row["job_status"] == "pending"` because that means a transient retry was rescheduled and the shop binding should remain runnable.

Use this control flow:

```python
row = cur.fetchone()
normalized = _normalize_record(dict(row)) if row else None
if normalized and str(normalized.get("job_status") or "") == "failed":
    apply_browser_binding_failure_transition(
        sync_job_id=sync_job_id,
        fail_reason=fail_reason,
    )
return normalized
```

- [ ] **Step 6: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_dispatcher.py finance-mcp/tests/test_browser_playbook_records.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add finance-mcp/auth/migrations/031_browser_playbook_collection.sql finance-mcp/auth/db.py finance-mcp/tests/test_browser_dispatcher.py finance-mcp/tests/test_browser_playbook_records.py
git commit -m "fix: schedule browser retries and pause unhealthy bindings"
```

---

## Task 6: Browser-Agent MCP Client

**Files:**

- Create: `finance-agents/browser-agent/finance_browser_agent/tally_client.py`
- Test: `finance-agents/browser-agent/tests/test_tally_client.py`

- [ ] **Step 1: Add client-shape tests**

Create `finance-agents/browser-agent/tests/test_tally_client.py`:

```python
from __future__ import annotations

import jwt

from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient, create_system_token


def test_create_system_token_has_system_role(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    token = create_system_token(agent_id="browser-agent-local")
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert payload["role"] == "system"
    assert payload["username"] == "browser-agent"
    assert payload["sub"] == "browser-agent:browser-agent-local"


def test_browser_agent_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_AGENT_ID", raising=False)
    config = BrowserAgentConfig.from_env()
    assert config.agent_id
    assert config.poll_interval_seconds >= 1
    assert config.max_concurrency >= 1


def test_browser_agent_client_refreshes_token_before_expiry(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    config = BrowserAgentConfig.from_env()
    client = BrowserAgentTallyClient(config=config)
    first = client.worker_token
    client._token_expires_at = 0
    second = client.worker_token
    assert first != second
```

- [ ] **Step 2: Implement client config and token helper**

Create `finance-agents/browser-agent/finance_browser_agent/tally_client.py` with:

```python
from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt


JWT_ALGORITHM = "HS256"


@dataclass(frozen=True)
class BrowserAgentConfig:
    agent_id: str
    mcp_base_url: str
    poll_interval_seconds: float
    max_concurrency: int
    waiting_poll_interval_seconds: float

    @classmethod
    def from_env(cls) -> "BrowserAgentConfig":
        hostname = socket.gethostname() or "local"
        return cls(
            agent_id=os.getenv("BROWSER_AGENT_ID", f"browser-agent-{hostname}"),
            mcp_base_url=os.getenv("FINANCE_MCP_BASE_URL", "http://127.0.0.1:3335"),
            poll_interval_seconds=float(os.getenv("BROWSER_AGENT_POLL_INTERVAL_SECONDS", "2")),
            max_concurrency=max(1, int(os.getenv("BROWSER_AGENT_MAX_CONCURRENCY", "2"))),
            waiting_poll_interval_seconds=float(os.getenv("BROWSER_AGENT_WAITING_POLL_INTERVAL_SECONDS", "30")),
        )


def create_system_token(*, agent_id: str) -> str:
    jwt_secret = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"browser-agent:{agent_id}",
        "username": "browser-agent",
        "role": "system",
        "company_id": None,
        "department_id": None,
        "iat": now,
        "exp": now + timedelta(hours=2),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)


class BrowserAgentTallyClient:
    def __init__(self, *, config: BrowserAgentConfig) -> None:
        self.config = config
        self._token = ""
        self._token_expires_at = 0.0

    @property
    def worker_token(self) -> str:
        now_ts = datetime.now(timezone.utc).timestamp()
        if not self._token or now_ts >= self._token_expires_at - 300:
            self._token = create_system_token(agent_id=self.config.agent_id)
            self._token_expires_at = (datetime.now(timezone.utc) + timedelta(hours=2)).timestamp()
        return self._token
```

- [ ] **Step 3: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_tally_client.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-agents/browser-agent/tests/test_tally_client.py
git commit -m "feat: add browser agent tally client shell"
```

Deployment note: on a separate collection machine, `FINANCE_MCP_BASE_URL` must point to the reachable Tally Cloud finance-mcp endpoint. The `http://127.0.0.1:3335` default is for local all-in-one development only.

---

## Task 7: Browser Sync Job MCP Tools

**Files:**

- Modify: `finance-mcp/tools/data_sources.py`
- Modify: `finance-mcp/auth/db.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/tally_client.py`
- Test: `finance-mcp/tests/test_browser_dispatcher.py`
- Test: `finance-agents/browser-agent/tests/test_tally_client.py`

- [ ] **Step 1: Add MCP tool names**

In `finance-mcp/tools/data_sources.py`, add tools:

- `browser_sync_job_claim`
- `browser_sync_job_complete`
- `browser_sync_job_fail`

Inputs:

```python
browser_sync_job_claim:
  worker_token: string
  agent_id: string
  max_concurrency: integer

browser_sync_job_complete:
  worker_token: string
  sync_job_id: string
  summary: object
  capture_files: array

browser_sync_job_fail:
  worker_token: string
  sync_job_id: string
  fail_reason: string
  error_message: string
  retryable: boolean
  max_attempts: integer
  retry_delay_seconds: integer
```

- [ ] **Step 2: Add handler tests**

Extend `finance-mcp/tests/test_browser_dispatcher.py` with direct handler tests that monkeypatch `auth_db.claim_next_browser_sync_job`, `auth_db.mark_browser_sync_job_success`, and `auth_db.mark_browser_sync_job_failed`. Verify:

- `browser_sync_job_claim` returns `{"success": True, "job": ...}`.
- `browser_sync_job_complete` calls success helper.
- `browser_sync_job_fail` calls fail helper.

- [ ] **Step 3: Implement MCP handlers**

In `finance-mcp/tools/data_sources.py`:

- Reuse existing system-token validation style from data-source scheduler helpers or add `_require_system_or_scheduler`.
- `browser_sync_job_claim` calls `auth_db.claim_next_browser_sync_job(agent_id=agent_id, agent_max_concurrency=max_concurrency)`.
- `browser_sync_job_complete` calls `auth_db.mark_browser_sync_job_success(...)`.
- `browser_sync_job_fail` calls `auth_db.mark_browser_sync_job_failed(...)` with `retryable`, `max_attempts`, and `retry_delay_seconds`.
- If `mark_browser_sync_job_failed` returns a row with `job_status='pending'`, the handler returns `{"success": True, "rescheduled": True, "job": row}`.
- If it returns `job_status='failed'`, the handler returns `{"success": True, "rescheduled": False, "job": row}`.

- [ ] **Step 4: Implement MCP session and browser-agent client wrappers**

In `finance-agents/browser-agent/finance_browser_agent/tally_client.py`, copy the `_McpSession` structure from `finance-cron/mcp_client.py` and adapt it so the base URL comes from `BrowserAgentConfig.mcp_base_url`. Keep these behaviors:

- Use `httpx.AsyncClient(..., trust_env=False)`.
- Open `GET {mcp_base_url}/sse`.
- Send `initialize` and `notifications/initialized`.
- Send `tools/call` requests to `POST {mcp_base_url}/messages/?session_id=...`.
- Decode MCP content text as JSON when possible.
- Return `{"success": False, "error": ...}` instead of raising for network/tool failures.

Then add these methods to `BrowserAgentTallyClient`:

```python
async def claim_browser_job(self) -> dict[str, Any]:
    return await self.call_tool(
        "browser_sync_job_claim",
        {
            "worker_token": self.worker_token,
            "agent_id": self.config.agent_id,
            "max_concurrency": self.config.max_concurrency,
        },
    )
```

Also implement:

```python
async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return await self._session.call_tool(tool_name, arguments)

async def mark_browser_job_success(self, payload: dict[str, Any]) -> dict[str, Any]:
    return await self.call_tool(
        "browser_sync_job_complete",
        {"worker_token": self.worker_token, **payload},
    )

async def mark_browser_job_failed(self, payload: dict[str, Any]) -> dict[str, Any]:
    return await self.call_tool(
        "browser_sync_job_fail",
        {"worker_token": self.worker_token, **payload},
    )

async def requeue_ready_waiting(self) -> dict[str, Any]:
    return await self.call_tool(
        "recon_queue_requeue_ready_waiting",
        {"worker_token": self.worker_token},
    )

async def fail_failed_waiting(self) -> dict[str, Any]:
    return await self.call_tool(
        "recon_queue_fail_failed_collection_waiting",
        {"worker_token": self.worker_token},
    )

async def fail_expired_waiting(self) -> dict[str, Any]:
    return await self.call_tool(
        "recon_queue_fail_expired_waiting",
        {"worker_token": self.worker_token},
    )
```

All wrapper methods must use `self.worker_token`, not `self._token`, so long-running browser-agent processes refresh tokens before expiry.

- [ ] **Step 5: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_dispatcher.py finance-agents/browser-agent/tests/test_tally_client.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/auth/db.py finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-mcp/tests/test_browser_dispatcher.py finance-agents/browser-agent/tests/test_tally_client.py
git commit -m "feat: expose browser sync job worker tools"
```

---

## Task 8: Browser-Agent Dispatcher Loop

**Files:**

- Create: `finance-agents/browser-agent/finance_browser_agent/profile_locks.py`
- Create: `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
- Modify: `finance-agents/browser-agent/runner.py`
- Test: `finance-agents/browser-agent/tests/test_dispatcher_loop.py`

- [ ] **Step 1: Add dispatcher loop tests**

Create `finance-agents/browser-agent/tests/test_dispatcher_loop.py` with fakes:

```python
from __future__ import annotations

import pytest

from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop


class FakeClient:
    def __init__(self, jobs: list[dict], result: dict) -> None:
        self.jobs = jobs
        self.result = result
        self.completed: list[dict] = []
        self.failed: list[dict] = []

    async def claim_browser_job(self) -> dict:
        if not self.jobs:
            return {"success": True, "job": None}
        return {"success": True, "job": self.jobs.pop(0)}

    async def mark_browser_job_success(self, payload: dict) -> dict:
        self.completed.append(payload)
        return {"success": True}

    async def mark_browser_job_failed(self, payload: dict) -> dict:
        self.failed.append(payload)
        return {"success": True}


@pytest.mark.asyncio
async def test_dispatcher_completes_successful_job() -> None:
    job = {
        "id": "sync-001",
        "request_payload": {
            "rows": [],
            "biz_date": "2026-05-18",
        },
        "shop_id": "shop-001",
        "playbook_id": "qianniu-daily-bill-export",
        "playbook_version": "1.0.0",
        "playbook_body": {
            "steps": [],
            "output": {"columns": [], "item_key_fields": []},
            "quality_gate": {},
        },
        "runtime_profile_ref": "profile-001",
        "egress_group": "wan-1",
        "credential_ref": "cred-001",
    }
    client = FakeClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] == "success"
    assert client.completed[0]["sync_job_id"] == "sync-001"


@pytest.mark.asyncio
async def test_dispatcher_builds_message_from_claim_enrichment_not_raw_payload() -> None:
    captured: dict[str, dict] = {}
    job = {
        "id": "sync-001",
        "request_payload": {"biz_date": "2026-05-18"},
        "shop_id": "shop-001",
        "playbook_id": "qianniu-daily-bill-export",
        "playbook_version": "1.0.0",
        "playbook_body": {"steps": [], "output": {"columns": [], "item_key_fields": []}, "quality_gate": {}},
        "runtime_profile_ref": "profile-001",
        "egress_group": "wan-1",
        "credential_ref": "cred-001",
    }

    def runner(message: dict) -> dict:
        captured["message"] = message
        return {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []}

    client = FakeClient([job], {})
    loop = BrowserDispatcherLoop(client=client, runner=runner, max_concurrency=1)

    await loop.run_once()

    assert captured["message"]["shop_id"] == "shop-001"
    assert captured["message"]["playbook_body"] == job["playbook_body"]
    assert captured["message"]["runtime_profile_ref"] == "profile-001"


@pytest.mark.asyncio
async def test_dispatcher_runs_sync_runner_in_thread(monkeypatch) -> None:
    called: dict[str, bool] = {"to_thread": False}
    job = {
        "id": "sync-001",
        "request_payload": {"biz_date": "2026-05-18"},
        "shop_id": "shop-001",
        "playbook_body": {"steps": []},
    }
    client = FakeClient([job], {"job_id": "sync-001", "status": "success", "records": [], "capture_files": []})

    async def fake_to_thread(func, *args, **kwargs):
        called["to_thread"] = True
        return func(*args, **kwargs)

    monkeypatch.setattr("finance_browser_agent.dispatcher_loop.asyncio.to_thread", fake_to_thread)
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    await loop.run_once()

    assert called["to_thread"] is True


@pytest.mark.asyncio
async def test_dispatcher_fails_deterministic_error_without_retry() -> None:
    job = {"id": "sync-001", "request_payload": {"biz_date": "2026-05-18"}, "shop_id": "shop-001", "playbook_body": {"steps": []}}
    client = FakeClient([job], {"job_id": "sync-001", "status": "failed", "fail_reason": "AUTH_EXPIRED", "error_info": {"message": "login expired"}})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] == "failed"
    assert client.failed[0]["retryable"] is False
    assert client.failed[0]["fail_reason"] == "AUTH_EXPIRED"


@pytest.mark.asyncio
async def test_dispatcher_passes_retry_policy_for_transient_error() -> None:
    job = {"id": "sync-001", "request_payload": {"biz_date": "2026-05-18"}, "shop_id": "shop-001", "playbook_body": {"steps": []}}
    client = FakeClient([job], {"job_id": "sync-001", "status": "failed", "fail_reason": "TIMEOUT", "error_info": {"message": "timeout"}})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=1)

    result = await loop.run_once()

    assert result["status"] == "failed"
    assert client.failed[0]["retryable"] is True
    assert client.failed[0]["max_attempts"] == 3
    assert client.failed[0]["retry_delay_seconds"] == 1800


@pytest.mark.asyncio
async def test_dispatcher_run_forever_starts_concurrent_workers() -> None:
    client = FakeClient([], {"status": "success"})
    loop = BrowserDispatcherLoop(client=client, runner=lambda message: client.result, max_concurrency=2)
    workers = loop.create_worker_tasks()
    assert len(workers) == 2
    for task in workers:
        task.cancel()
```

- [ ] **Step 2: Implement profile lock registry**

Create `finance-agents/browser-agent/finance_browser_agent/profile_locks.py`:

```python
from __future__ import annotations

import asyncio


class ProfileLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for_shop(self, shop_id: str) -> asyncio.Lock:
        key = str(shop_id or "unknown").strip() or "unknown"
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
```

- [ ] **Step 3: Implement dispatcher loop**

Create `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`:

```python
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from finance_browser_agent.failure_policy import classify_failure
from finance_browser_agent.profile_locks import ProfileLockRegistry

logger = logging.getLogger(__name__)


class BrowserDispatcherLoop:
    def __init__(
        self,
        *,
        client: Any,
        runner: Callable[[dict[str, Any]], dict[str, Any]],
        max_concurrency: int,
        profile_locks: ProfileLockRegistry | None = None,
    ) -> None:
        self.client = client
        self.runner = runner
        self.max_concurrency = max(1, max_concurrency)
        self.semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self.profile_locks = profile_locks or ProfileLockRegistry()

    async def run_once(self) -> dict[str, Any]:
        claim = await self.client.claim_browser_job()
        job = claim.get("job") if isinstance(claim, dict) else None
        if not job:
            return {"status": "idle"}
        return await self._process_job(dict(job))

    async def _process_job(self, job: dict[str, Any]) -> dict[str, Any]:
        sync_job_id = str(job.get("id") or "")
        payload = dict(job.get("request_payload") or {})
        shop_id = str(job.get("shop_id") or "unknown")
        async with self.semaphore:
            async with self.profile_locks.lock_for_shop(shop_id):
                result = await asyncio.to_thread(self.runner, self._message_from_job(job, payload))
        if result.get("status") == "success":
            await self.client.mark_browser_job_success(
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
            return {"status": "success", "sync_job_id": sync_job_id}
        policy = classify_failure(str(result.get("fail_reason") or "OTHER"))
        await self.client.mark_browser_job_failed(
            {
                "sync_job_id": sync_job_id,
                "fail_reason": policy.normalized_reason,
                "error_message": str((result.get("error_info") or {}).get("message") or "browser task failed"),
                "retryable": policy.retryable,
                "max_attempts": policy.max_attempts,
                "retry_delay_seconds": policy.retry_delay_seconds,
            }
        )
        return {"status": "failed", "sync_job_id": sync_job_id, "retryable": policy.retryable}

    def create_worker_tasks(self) -> list[asyncio.Task]:
        return [
            asyncio.create_task(self.worker_loop(worker_index=index))
            for index in range(self.max_concurrency)
        ]

    async def worker_loop(self, *, worker_index: int) -> None:
        while True:
            try:
                result = await self.run_once()
                if result.get("status") == "idle":
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("browser dispatcher worker failed: worker_index=%s", worker_index)
                await asyncio.sleep(5)

    def _message_from_job(self, job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload.get("params") or payload)
        return {
            "job_id": str(job.get("id") or ""),
            "shop_id": str(job.get("shop_id") or ""),
            "playbook_id": str(job.get("playbook_id") or ""),
            "playbook_version": str(job.get("playbook_version") or ""),
            "playbook_body": dict(job.get("playbook_body") or {}),
            "params": params,
            "runtime_profile_ref": str(job.get("runtime_profile_ref") or ""),
            "egress_group": str(job.get("egress_group") or ""),
            "credential_ref": str(job.get("credential_ref") or ""),
            "timeout_ms": int(params.get("timeout_ms") or payload.get("timeout_ms") or 900000),
        }
```

- [ ] **Step 4: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_dispatcher_loop.py finance-agents/browser-agent/tests/test_failure_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/profile_locks.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/tests/test_dispatcher_loop.py
git commit -m "feat: add browser agent dispatcher loop"
```

---

## Task 9: Browser-Agent Service Entrypoint

**Files:**

- Create: `finance-agents/browser-agent/service.py`
- Modify: `START_ALL_SERVICES.sh`
- Modify: `STOP_ALL_SERVICES.sh`
- Test: `finance-agents/browser-agent/tests/test_service_config.py`

- [ ] **Step 1: Add service config test**

Create `finance-agents/browser-agent/tests/test_service_config.py`:

```python
from __future__ import annotations

from finance_browser_agent.tally_client import BrowserAgentConfig


def test_browser_agent_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_AGENT_ID", "agent-test")
    monkeypatch.setenv("BROWSER_AGENT_MAX_CONCURRENCY", "3")
    config = BrowserAgentConfig.from_env()
    assert config.agent_id == "agent-test"
    assert config.max_concurrency == 3
```

- [ ] **Step 2: Implement service entrypoint**

Create `finance-agents/browser-agent/service.py`:

```python
from __future__ import annotations

import asyncio
import logging
import signal

from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop
from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient
from runner import run_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("browser-agent")

_shutdown = False


def _handle_signal(signum, frame) -> None:
    global _shutdown
    _shutdown = True
    logger.info("收到停止信号: %s", signum)


async def _waiting_reconciler(client: BrowserAgentTallyClient, interval_seconds: float) -> None:
    while not _shutdown:
        await client.fail_failed_waiting()
        await client.requeue_ready_waiting()
        await client.fail_expired_waiting()
        await asyncio.sleep(interval_seconds)


async def _dispatcher(client: BrowserAgentTallyClient, config: BrowserAgentConfig) -> None:
    loop = BrowserDispatcherLoop(
        client=client,
        runner=run_message,
        max_concurrency=config.max_concurrency,
    )
    workers = loop.create_worker_tasks()
    try:
        while not _shutdown:
            await asyncio.sleep(config.poll_interval_seconds)
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


async def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    config = BrowserAgentConfig.from_env()
    client = BrowserAgentTallyClient(config=config)
    logger.info("browser-agent 启动: agent_id=%s max_concurrency=%s", config.agent_id, config.max_concurrency)
    await asyncio.gather(
        _dispatcher(client, config),
        _waiting_reconciler(client, config.waiting_poll_interval_seconds),
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Wire startup script**

In `START_ALL_SERVICES.sh`:

- Stop stale browser-agent processes near other cleanup:

```bash
[ -f /tmp/browser-agent.pid ] && kill -9 "$(cat /tmp/browser-agent.pid)" 2>/dev/null || true
rm -f /tmp/browser-agent.pid
pkill -f "finance-agents/browser-agent/service.py" 2>/dev/null || true
```

- Start it after finance-mcp is healthy and before recon-worker:

```bash
echo ""
echo "📌 步骤 4b: 启动 browser-agent..."
BROWSER_AGENT_PID="$(start_detached "$LOG_DIR/browser-agent.log" "$PROJECT_ROOT/finance-agents/browser-agent" python service.py)"
echo "$BROWSER_AGENT_PID" > /tmp/browser-agent.pid
echo "✅ browser-agent 已启动 (PID: $BROWSER_AGENT_PID)"
```

- Add health check:

```bash
if [ -f /tmp/browser-agent.pid ] && kill -0 "$(cat /tmp/browser-agent.pid)" 2>/dev/null; then
    echo "✅ browser-agent (collection) - 运行正常"
else
    echo "❌ browser-agent - 启动失败"
    SERVICES_OK=false
fi
```

- Add log line:

```bash
echo "   - browser-agent: tail -f $LOG_DIR/browser-agent.log"
```

- [ ] **Step 4: Wire stop script**

In `STOP_ALL_SERVICES.sh`, stop `/tmp/browser-agent.pid` and stale `finance-agents/browser-agent/service.py` processes.

- [ ] **Step 5: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_service_config.py finance-agents/browser-agent/tests/test_dispatcher_loop.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add finance-agents/browser-agent/service.py START_ALL_SERVICES.sh STOP_ALL_SERVICES.sh finance-agents/browser-agent/tests/test_service_config.py
git commit -m "feat: run browser agent as collection service"
```

---

## Task 10: Waiting Dataset Precision And Recon Worker Poller Cleanup

**Files:**

- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
- Modify: `finance-agents/data-agent/graphs/recon/auto_run_service.py`
- Modify: `finance-agents/data-agent/recon_worker.py`
- Test: `finance-agents/data-agent/tests/recon/test_browser_waiting_data_flow.py`

- [ ] **Step 1: Add precision assertions**

In `finance-agents/data-agent/tests/recon/test_browser_waiting_data_flow.py`, add a test with two bindings:

- one browser binding returning `queued=True`
- one non-browser binding ready

Assert `waiting_datasets` contains only the browser dataset id.

- [ ] **Step 2: Tighten `auto_scheme_run` waiting list**

In `nodes.py`, keep current waiting binding filtering but ensure `_waiting_dataset_from_binding()` is called only for bindings where:

```python
bool(b.get("waiting_data")) and str(b.get("collection_driver") or "") == "browser_playbook_remote"
```

- [ ] **Step 3: Tighten `auto_run_service` waiting list**

In `auto_run_service.py`, replace the broad `for binding in bindings` waiting list with only queued browser collection attempts:

```python
waiting_datasets = [
    {
        "data_source_id": str(attempt.get("binding", {}).get("data_source_id") or ""),
        "dataset_id": str(attempt.get("binding", {}).get("dataset_id") or ""),
        "biz_date": normalized_biz_date,
    }
    for attempt in collection_attempts
    if str(attempt.get("collection_driver") or "") == "browser_playbook_remote"
    and bool(attempt.get("queued"))
]
```

- [ ] **Step 4: Remove per-worker waiting-data poller**

In `finance-agents/data-agent/recon_worker.py`, remove these calls from the main loop:

```python
await recon_queue_requeue_ready_waiting(system_token)
await recon_queue_fail_expired_waiting(system_token)
```

Keep `recon_queue_waiting_data` handling in `_process_job`. Browser-agent now owns waiting-data recovery.

- [ ] **Step 5: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_browser_waiting_data_flow.py finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-agents/data-agent/graphs/recon/auto_run_service.py finance-agents/data-agent/recon_worker.py finance-agents/data-agent/tests/recon/test_browser_waiting_data_flow.py
git commit -m "fix: centralize browser waiting data recovery"
```

---

## Task 11: Dataset Bootstrap Validation

**Files:**

- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_browser_playbook_connector.py`

- [ ] **Step 1: Add registration validation test**

Add a test asserting `data_source_register_browser_playbook` returns an error when no published `data_source_datasets` row exists for the browser source.

Expected error message:

```text
请先发布 browser_collection_records 数据集后再注册 playbook
```

- [ ] **Step 2: Implement validation**

In `_handle_data_source_register_browser_playbook`, before `upsert_playbook`, call:

```python
datasets = auth_db.list_unified_data_source_datasets(
    company_id=company_id,
    data_source_id=source_id,
    only_published=True,
)
has_browser_dataset = any(
    _dataset_storage_value(row) == "browser_collection_records"
    for row in datasets
)
if not has_browser_dataset:
    return {
        "success": False,
        "error": "请先发布 browser_collection_records 数据集后再注册 playbook",
    }
```

Use the existing `_dataset_storage_value()` helper in `finance-mcp/tools/data_sources.py`; do not introduce a second ad-hoc source-type detector.

- [ ] **Step 3: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_playbook_connector.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_browser_playbook_connector.py
git commit -m "fix: require published browser dataset before playbook registration"
```

---

## Task 12: Attempt Semantics And Retry Metadata

**Files:**

- Modify: `finance-mcp/auth/migrations/031_browser_playbook_collection.sql`
- Modify: `finance-mcp/auth/db.py`
- Test: `finance-mcp/tests/test_browser_waiting_data_queue.py`

- [ ] **Step 1: Add migration fields**

Add fields to `recon_execution_queue` for waiting resume metadata:

```sql
ALTER TABLE public.recon_execution_queue
    ADD COLUMN IF NOT EXISTS data_wait_resume_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_data_wait_resumed_at timestamptz;
```

- [ ] **Step 2: Update schema readiness**

In `_browser_playbook_collection_schema_ready()`, require:

```python
"data_wait_resume_count",
"last_data_wait_resumed_at",
```

- [ ] **Step 3: Increment resume metadata when ready**

In `requeue_ready_waiting_recon_runs()`, update:

```sql
data_wait_resume_count = COALESCE(data_wait_resume_count, 0) + 1,
last_data_wait_resumed_at = CURRENT_TIMESTAMP
```

Document in function comment:

```python
"""Resume waiting-data recon jobs without consuming business retry budget."""
```

- [ ] **Step 4: Test SQL contains resume metadata**

Extend `test_requeue_ready_waiting_requires_non_empty_collection_jobs` to assert:

```python
assert "data_wait_resume_count" in sql
assert "last_data_wait_resumed_at" in sql
```

- [ ] **Step 5: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_waiting_data_queue.py finance-mcp/tests/test_browser_playbook_records.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add finance-mcp/auth/migrations/031_browser_playbook_collection.sql finance-mcp/auth/db.py finance-mcp/tests/test_browser_waiting_data_queue.py finance-mcp/tests/test_browser_playbook_records.py
git commit -m "feat: track browser waiting data resume metadata"
```

---

## Task 12.5: Browser Trigger Health Gate

**Files:**

- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_browser_playbook_connector.py`

- [ ] **Step 1: Add trigger health-gate tests**

In `finance-mcp/tests/test_browser_playbook_connector.py`, add a test that sets the shop binding to `profile_status='risk_blocked'` and verifies dataset collection returns a non-queued failure before creating a sync job:

```python
def test_browser_dataset_collection_rejects_unhealthy_binding_before_sync_job(monkeypatch) -> None:
    source = {
        "id": "source-001",
        "company_id": "company-001",
        "source_kind": "browser_playbook",
        "provider_code": "qianniu",
        "status": "active",
        "is_enabled": True,
        "auth_config": {},
        "connection_config": {},
        "extract_config": {},
        "mapping_config": {},
        "runtime_config": {},
    }
    dataset = {
        "id": "dataset-001",
        "dataset_code": "qianniu_daily_bill",
        "resource_key": "daily_bill",
        "source_kind": "browser_playbook",
        "provider_code": "qianniu",
        "sync_strategy": {},
    }
    created = {"called": False}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda *, company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda *, company_id, data_source_id: source,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_runtime_binding_for_source",
        lambda *, company_id, data_source_id: {
            "shop_id": "shop-001",
            "profile_status": "risk_blocked",
            "playbook_status": "ok",
            "cron_pause_reason": "RISK_VERIFICATION",
        },
    )
    monkeypatch.setattr(data_sources.auth_db, "get_latest_source_dataset_checkpoint", lambda **kwargs: {})

    def fail_if_created(**kwargs):
        created["called"] = True
        raise AssertionError("unhealthy browser binding must not create sync job")

    monkeypatch.setattr(data_sources.auth_db, "create_or_reuse_dataset_collection_sync_job", fail_if_created)

    result = asyncio.run(
        data_sources.trigger_dataset_collection_for_company(
            company_id="company-001",
            source_id="source-001",
            dataset_id="dataset-001",
            trigger_mode="manual",
            params={"biz_date": "2026-05-19"},
        )
    )

    assert result["success"] is False
    assert result["queued"] is False
    assert result["failure_type"] == "browser_binding_unavailable"
    assert result["error_code"] == "RISK_VERIFICATION"
    assert created["called"] is False
```

- [ ] **Step 2: Add browser binding health helper**

In `finance-mcp/tools/data_sources.py`, add:

```python
def _browser_binding_unavailable_result(binding: dict[str, Any]) -> dict[str, Any] | None:
    profile_status = _safe_text(binding.get("profile_status")) or "unknown"
    playbook_status = _safe_text(binding.get("playbook_status")) or "unknown"
    pause_reason = _safe_text(binding.get("cron_pause_reason"))
    if profile_status == "active" and playbook_status == "ok":
        return None
    error_code = pause_reason or profile_status or playbook_status or "UNHEALTHY_BINDING"
    return {
        "success": False,
        "queued": False,
        "failure_type": "browser_binding_unavailable",
        "error_code": error_code,
        "error": f"浏览器采集店铺状态不可用: profile_status={profile_status}, playbook_status={playbook_status}, pause_reason={pause_reason}",
    }
```

- [ ] **Step 3: Enforce health before sync-job creation**

In `_trigger_dataset_collection_resolved()`, after `uses_driver_managed_storage` is computed and before checkpoint/job creation, add:

```python
if collection_driver == COLLECTION_DRIVER_BROWSER_PLAYBOOK:
    binding = auth_db.get_shop_runtime_binding_for_source(
        company_id=company_id,
        data_source_id=source_id,
    )
    unavailable = _browser_binding_unavailable_result(binding)
    if unavailable:
        return {
            **unavailable,
            "dataset_id": _safe_text(dataset_row.get("id")),
            "dataset_code": _safe_text(dataset_row.get("dataset_code")),
            "resource_key": resource_key,
            "biz_date": biz_date,
            "collection_driver": collection_driver,
        }
```

This prevents known-bad browser sources from creating pending jobs that no agent can claim. Recon will receive a data-unavailable failure immediately instead of entering `waiting_data` and timing out.

- [ ] **Step 4: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_playbook_connector.py finance-agents/data-agent/tests/recon/test_browser_waiting_data_flow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_browser_playbook_connector.py
git commit -m "fix: block browser collection for unhealthy bindings"
```

---

## Task 13: Deferred Soft Delete Documentation And Test Lock

**Files:**

- Modify: `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`
- Modify: `finance-mcp/tests/test_browser_playbook_records.py`

- [ ] **Step 1: Add deferred soft-delete statement**

In the design addendum, expand the deferred section:

```markdown
## Soft Delete Limitation

First-store v1 does not mark browser records missing from a later successful recapture as `deleted`.
Repeated captures upsert seen rows and leave previously seen rows active. This is acceptable only
for the first real-shop trial because the first target is append-like daily fund bills. A later
hardening plan must add complete-success missing-key soft delete before using browser collection
for mutable same-day datasets.
```

- [ ] **Step 2: Add test that makes limitation explicit**

In `finance-mcp/tests/test_browser_playbook_records.py`, add or adjust a test name/assertion so the current helper explicitly returns `deleted_count == 0` and the test comment says soft delete is deferred.

- [ ] **Step 3: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_playbook_records.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md finance-mcp/tests/test_browser_playbook_records.py
git commit -m "docs: document browser soft delete limitation"
```

---

## Task 14: End-To-End Service Verification

**Files:**

- Modify: `finance-mcp/tests/test_browser_first_store_e2e.py`
- Modify implementation files from Tasks 2-12 if this e2e test exposes a mismatch.

- [ ] **Step 1: Extend first-store e2e expectations**

Update `finance-mcp/tests/test_browser_first_store_e2e.py` so it verifies:

- browser job can be claimed through the source-kind route
- capture files are persisted
- waiting-data job with empty `collection_job_ids` is not requeued
- waiting-data job with failed collection job is failed immediately
- waiting-data job with successful collection job is requeued

- [ ] **Step 2: Run all browser-related tests in split groups**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_playbook_records.py \
  finance-mcp/tests/test_browser_collection_loader.py \
  finance-mcp/tests/test_browser_playbook_schema.py \
  finance-mcp/tests/test_browser_playbook_connector.py \
  finance-mcp/tests/test_browser_dispatcher.py \
  finance-mcp/tests/test_browser_capture_files.py \
  finance-mcp/tests/test_browser_waiting_data_queue.py \
  finance-mcp/tests/test_recon_execution_waiting_data.py \
  finance-mcp/tests/test_browser_first_store_e2e.py -q
```

Expected: PASS.

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py \
  finance-agents/browser-agent/tests/test_quality_gate.py \
  finance-agents/browser-agent/tests/test_failure_policy.py \
  finance-agents/browser-agent/tests/test_tally_client.py \
  finance-agents/browser-agent/tests/test_dispatcher_loop.py \
  finance-agents/browser-agent/tests/test_service_config.py -q
```

Expected: PASS.

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_browser_waiting_data_flow.py \
  finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py -q
```

Expected: PASS.

- [ ] **Step 3: Restart services**

Run:

```bash
./START_ALL_SERVICES.sh
```

Expected:

- finance-mcp healthy
- data-agent healthy
- finance-cron alive
- browser-agent alive
- recon-worker alive
- finance-web alive

- [ ] **Step 4: Commit**

Run:

```bash
git add finance-mcp/tests/test_browser_first_store_e2e.py
git commit -m "test: cover browser first-store production hardening"
```

If only tests were changed and no test modifications were needed, skip this commit and record the verification output in the final response.

---

## Task 15: Real Playwright QianNiu Runner

**Files:**

- Create: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Modify: `finance-agents/browser-agent/runner.py`
- Test: `finance-agents/browser-agent/tests/test_playwright_runner_contract.py`

- [ ] **Step 1: Add Playwright runner contract tests**

Create `finance-agents/browser-agent/tests/test_playwright_runner_contract.py`:

```python
from __future__ import annotations

from finance_browser_agent.playwright_runner import PlaywrightRunConfig, build_user_data_dir


def test_build_user_data_dir_uses_shop_id_under_profile_root(tmp_path) -> None:
    config = PlaywrightRunConfig(profile_root=str(tmp_path), headless=True, timezone_id="Asia/Shanghai")
    assert build_user_data_dir(config=config, shop_id="shop-001") == str(tmp_path / "shop-001")


def test_playwright_config_defaults_to_persistent_profile(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_AGENT_PROFILE_ROOT", raising=False)
    config = PlaywrightRunConfig.from_env()
    assert config.profile_root.endswith("profiles")
    assert config.timezone_id == "Asia/Shanghai"
```

- [ ] **Step 2: Implement Playwright runner for v1 actions**

Create `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py` with:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlaywrightRunConfig:
    profile_root: str
    headless: bool
    timezone_id: str
    download_root: str = ""

    @classmethod
    def from_env(cls) -> "PlaywrightRunConfig":
        profile_root = os.getenv("BROWSER_AGENT_PROFILE_ROOT", "/var/lib/tally-agent/profiles")
        return cls(
            profile_root=profile_root,
            headless=os.getenv("BROWSER_AGENT_HEADLESS", "1") != "0",
            timezone_id=os.getenv("BROWSER_AGENT_TIMEZONE", "Asia/Shanghai"),
            download_root=os.getenv("BROWSER_AGENT_DOWNLOAD_ROOT", "/var/lib/tally-agent/downloads"),
        )


def build_user_data_dir(*, config: PlaywrightRunConfig, shop_id: str) -> str:
    safe_shop_id = "".join(ch for ch in str(shop_id or "unknown") if ch.isalnum() or ch in {"-", "_"})
    return str(Path(config.profile_root) / (safe_shop_id or "unknown"))


def run_playbook_with_playwright(message: dict[str, Any], *, config: PlaywrightRunConfig | None = None) -> dict[str, Any]:
    """Run a v1 browser playbook using Playwright persistent context.

    Executes real v1 actions and returns the same TASK_RESULT shape as runner.run_message().
    """
    config = config or PlaywrightRunConfig.from_env()
    playbook = dict(message.get("playbook_body") or {})
    params = dict(message.get("params") or {})
    shop_id = str(message.get("shop_id") or params.get("shop_id") or "unknown")
    job_id = str(message.get("job_id") or "unknown")
    download_dir = Path(config.download_root) / shop_id / job_id
    download_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=build_user_data_dir(config=config, shop_id=shop_id),
                headless=config.headless,
                accept_downloads=True,
                timezone_id=config.timezone_id,
                downloads_path=str(download_dir),
            )
            page = context.pages[0] if context.pages else context.new_page()
            rows: list[dict[str, Any]] = []
            capture_files: list[dict[str, Any]] = []
            extracted: dict[str, Any] = {}
            try:
                for step in playbook.get("steps") or []:
                    _execute_action(page, dict(step), params=params, extracted=extracted, rows=rows, capture_files=capture_files, download_dir=download_dir)
                quality = _validate_playwright_rows(playbook=playbook, params=params, rows=rows, extracted=extracted)
                if not quality.get("success"):
                    return {
                        "job_id": job_id,
                        "status": "failed",
                        "fail_reason": quality.get("fail_reason") or "DATA_MISMATCH",
                        "error_info": {"message": quality.get("error") or "quality gate failed"},
                    }
                return {
                    "job_id": job_id,
                    "status": "success",
                    "records": _records_from_rows(playbook=playbook, rows=rows),
                    "capture_files": capture_files,
                    "quality_summary": quality["summary"],
                }
            finally:
                context.close()
    except PlaywrightTimeoutError as exc:
        return {"job_id": job_id, "status": "failed", "fail_reason": "PAGE_CHANGED", "error_info": {"message": str(exc)}}
    except Exception as exc:
        return {"job_id": job_id, "status": "failed", "fail_reason": "OTHER", "error_info": {"message": str(exc)}}
```

Add helper functions in the same file:

- `_execute_action(page, action, params, extracted, rows, capture_files, download_dir)` supports `navigate`, `click`, `fill`, `set_date`, `wait_for`, `extract_text`, `extract_summary`, `download`, `parse_table`, and `assert`.
- `_detect_auth_or_risk(page)` returns `AUTH_EXPIRED` when the current URL/title/body indicates login is required and `RISK_VERIFICATION` when it contains common risk-verification text such as `验证`, `滑块`, `安全校验`.
- `_parse_downloaded_table(path)` reads CSV/XLSX with pandas and returns list of dictionaries.
- `_validate_playwright_rows(...)` calls existing `validate_rows()`.
- `_records_from_rows(...)` mirrors `runner.run_message()` item-key construction.
- Selector timeout or missing selector returns `PAGE_CHANGED`; auth/risk detection returns its deterministic reason before marking a selector failure.

- [ ] **Step 3: Wire runner selection**

Modify `finance-agents/browser-agent/runner.py`:

- If `BROWSER_AGENT_RUNNER_MODE=playwright`, call `run_playbook_with_playwright()`.
- Otherwise keep existing synthetic row mode for tests.

- [ ] **Step 4: Run unit tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_playwright_runner_contract.py \
  finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py \
  finance-agents/browser-agent/tests/test_quality_gate.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/runner.py finance-agents/browser-agent/tests/test_playwright_runner_contract.py
git commit -m "feat: add real playwright browser runner"
```

---

## Task 16: Collection Machine Environment And First-Login SOP

**Files:**

- Create: `finance-agents/browser-agent/scripts/check_environment.py`
- Create: `docs/superpowers/specs/2026-05-20-browser-agent-first-login-sop.md`
- Test: `finance-agents/browser-agent/tests/test_environment_check.py`

- [ ] **Step 1: Add environment check tests**

Create `finance-agents/browser-agent/tests/test_environment_check.py`:

```python
from __future__ import annotations

from finance_browser_agent.playwright_runner import PlaywrightRunConfig
from scripts.check_environment import build_environment_report


def test_environment_report_contains_required_paths(tmp_path) -> None:
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=True,
        timezone_id="Asia/Shanghai",
    )
    report = build_environment_report(config=config)
    assert "profile_root" in report
    assert "download_root" in report
    assert report["timezone_id"] == "Asia/Shanghai"
    assert "playwright_importable" in report
    assert "chromium_launchable" in report
    assert "font_probe" in report
```

- [ ] **Step 2: Implement environment checker**

Create `finance-agents/browser-agent/scripts/check_environment.py`:

```python
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from finance_browser_agent.playwright_runner import PlaywrightRunConfig


def build_environment_report(*, config: PlaywrightRunConfig) -> dict[str, object]:
    profile_root = Path(config.profile_root)
    download_root = Path(config.download_root)
    profile_root.mkdir(parents=True, exist_ok=True)
    download_root.mkdir(parents=True, exist_ok=True)
    playwright_importable = False
    chromium_launchable = False
    chromium_error = ""
    try:
        from playwright.sync_api import sync_playwright

        playwright_importable = True
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
            chromium_launchable = True
    except Exception as exc:
        chromium_error = str(exc)
    font_probe_status = "fc_list_missing"
    if shutil.which("fc-list"):
        try:
            font_probe = subprocess.run(
                ["fc-list", ":lang=zh"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            font_probe_status = (
                "ok"
                if font_probe.returncode == 0 and font_probe.stdout.strip()
                else "missing_zh_fonts"
            )
        except (OSError, subprocess.SubprocessError):
            font_probe_status = "font_probe_failed"
    return {
        "profile_root": str(profile_root),
        "profile_root_writable": profile_root.exists() and profile_root.is_dir(),
        "download_root": str(download_root),
        "download_root_writable": download_root.exists() and download_root.is_dir(),
        "timezone_id": config.timezone_id,
        "system_timezone": time.tzname,
        "headless": config.headless,
        "playwright_importable": playwright_importable,
        "chromium_launchable": chromium_launchable,
        "chromium_error": chromium_error,
        "font_probe": font_probe_status,
    }


def main() -> None:
    report = build_environment_report(config=PlaywrightRunConfig.from_env())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write first-login SOP**

Create `docs/superpowers/specs/2026-05-20-browser-agent-first-login-sop.md`:

```markdown
# Browser Agent First-Login SOP

## Purpose

Before enabling scheduled browser collection for a shop, an operator must create and verify a persistent Chrome profile for that shop on the collection machine.

## Steps

1. Set `BROWSER_AGENT_PROFILE_ROOT=/var/lib/tally-agent/profiles`.
2. Open Chrome/Playwright persistent context for the shop id under `/var/lib/tally-agent/profiles/<shop_id>`.
3. Log in with the merchant-provided collection sub-account.
4. Open the target QianNiu fund bill page.
5. Confirm no risk verification is blocking the account.
6. Close the browser cleanly.
7. In Tally, set `shop_runtime_bindings.profile_status='active'` and `playbook_status='ok'`.

## Risk Verification

If QianNiu shows risk verification, set `profile_status='risk_blocked'` and `cron_pause_reason='RISK_VERIFICATION'`. Do not keep retrying scheduled collection until an operator clears the verification on the collection machine.
```

- [ ] **Step 4: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/browser-agent/tests/test_environment_check.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add finance-agents/browser-agent/scripts/check_environment.py finance-agents/browser-agent/tests/test_environment_check.py docs/superpowers/specs/2026-05-20-browser-agent-first-login-sop.md
git commit -m "docs: add browser agent environment and login sop"
```

---

## Task 17: Real QianNiu Sample Acceptance

**Files:**

- Create: `docs/superpowers/specs/2026-05-20-qianniu-first-store-acceptance-checklist.md`
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py` when real QianNiu execution exposes runner defects.
- Modify: active QianNiu playbook JSON in the configured data source when selectors or summary mappings are wrong.

- [ ] **Step 1: Write acceptance checklist**

Create `docs/superpowers/specs/2026-05-20-qianniu-first-store-acceptance-checklist.md`:

```markdown
# QianNiu First-Store Acceptance Checklist

First-store is not production-ready until all checks pass for one real shop.

## Required Evidence

- Browser-agent service is running on the collection machine.
- `check_environment.py` report shows writable profile and download roots.
- Persistent profile for the shop is logged in and `profile_status=active`.
- One published `browser_collection_records` dataset exists for the shop.
- The active playbook opens the real QianNiu fund bill page.
- The playbook exports and parses three real business dates.
- For each date, parsed detail row count equals page/download summary count.
- For each date, parsed amount sum equals page/download summary amount with zero tolerance.
- `browser_capture_files` contains one file record per downloaded original file.
- A reconciliation job started before data readiness enters `waiting_data`.
- After collection success, the reconciliation job is restored to `queued` and completes.
- If a test profile is forced into auth-expired or risk-blocked state, binding status is updated and scheduled retry pauses.

## Evidence To Save

- sync_job ids
- recon_execution_queue job ids
- three business dates
- row counts and amount totals
- capture file storage paths
- screenshots or logs of the real QianNiu export flow
```

- [ ] **Step 2: Run real-shop smoke command**

After the operator has completed first login and registered the playbook, run a real collection for one known business date:

```bash
source .venv/bin/activate
BROWSER_AGENT_RUNNER_MODE=playwright python finance-agents/browser-agent/service.py
```

Expected:

- Browser-agent claims the pending browser job.
- Playwright opens the real QianNiu page using the persistent shop profile.
- A file downloads into `BROWSER_AGENT_DOWNLOAD_ROOT`.
- `browser_collection_records` row count is greater than 0.
- `browser_capture_files` has at least one row.

- [ ] **Step 3: Run three-date layer-2 validation**

For three real dates, compare:

```text
parsed detail row count == page/download summary row count
sum(parsed amount) == page/download summary amount
```

Expected: exact match for all dates.

- [ ] **Step 4: Commit checklist**

Run:

```bash
git add docs/superpowers/specs/2026-05-20-qianniu-first-store-acceptance-checklist.md
git commit -m "docs: add qianniu first-store acceptance checklist"
```

---

## Rollback Plan

If browser-agent causes instability:

1. Stop browser-agent:

```bash
[ -f /tmp/browser-agent.pid ] && kill -9 "$(cat /tmp/browser-agent.pid)"
```

2. Disable browser data sources:

```sql
UPDATE data_sources
SET status='disabled', is_enabled=false
WHERE source_kind='browser_playbook';
```

3. Existing database/API/platform OAuth collection and recon workers continue unchanged.

## Completion Criteria

- `START_ALL_SERVICES.sh` starts browser-agent as a normal service.
- Triggering a browser dataset collection creates a pending `sync_jobs` row and browser-agent consumes it.
- Successful browser-agent execution writes `browser_collection_records` and `browser_capture_files`.
- Recon jobs enter `waiting_data` only with non-empty `collection_job_ids`.
- Browser collection success restores waiting recon jobs to `queued`.
- Browser collection deterministic failure fails waiting recon jobs immediately with reason.
- Empty `collection_job_ids` never requeues a waiting recon job.
- Existing database/API/platform OAuth collection tests still pass.
- Browser-agent refreshes system tokens before expiry.
- `BROWSER_AGENT_MAX_CONCURRENCY=2` starts two concurrent dispatcher workers.
- Browser jobs are claimed only by the bound `shop_runtime_bindings.agent_id`.
- `AUTH_EXPIRED`, `RISK_VERIFICATION`, and `PAGE_CHANGED` update shop binding status and pause future scheduled collection.
- A real Playwright QianNiu run succeeds for one shop and three business dates.
- Collection-machine environment and first-login SOP are completed.
