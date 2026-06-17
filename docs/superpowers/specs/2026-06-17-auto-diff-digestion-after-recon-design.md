# Auto Diff Digestion After Recon Design

## Context

Daily reconciliation currently executes a run plan, records the reconciliation result, and then
finalizes the daily digest. Diff digestion already exists as a separate capability:

- `finance-agents/data-agent/graphs/recon/diff_digestion_service.py` calls the MCP
  `recon_diff_digestion` tool.
- `finance-agents/data-agent/recon_worker.py` already supports a manual/queued
  `trigger_mode=resolve` branch for diff digestion.
- `finance-mcp/tools/execution_runs.py` implements `recon_diff_digestion`, which reloads the
  run, rebuilds full reconciliation frames, rejudges open exceptions, and writes the resulting
  open counts back to the existing run.

The new behavior is to automatically run one diff digestion pass after a successful regular
reconciliation task, including successful retries. Finance users only need the final actionable
result, so the automatic pass should update the same run's open differences instead of creating a
separate result surface.

## Goals

- Automatically execute diff digestion after every successful non-`resolve` reconciliation run.
- Keep a successful reconciliation task successful even if automatic digestion fails.
- Run daily digest finalization after automatic digestion so reports use the latest open
  differences.
- Record automatic digestion status and duration in run artifacts for troubleshooting and timeout
  analysis.
- Verify locally with both unit tests and a large run, especially a Bokuan reconciliation, to check
  runtime against the current MCP timeout.

## Non-Goals

- Do not change the MCP diff digestion algorithm.
- Do not add a database table.
- Do not add a frontend screen, button, or run-plan setting.
- Do not change the current 600 second MCP timeout for `recon_diff_digestion` in the first
  implementation.
- Do not make automatic digestion failure fail the reconciliation task.
- Do not change the manual `trigger_mode=resolve` branch semantics.

## Proposed Approach

Implement the feature in the regular success path of
`finance-agents/data-agent/recon_worker.py`.

The worker should run automatic digestion only when:

- `execute_run_plan_run` returns success,
- the returned run has `execution_status == "success"`,
- the run has a non-empty `id`,
- the job is not `trigger_mode=resolve`.

The regular successful path should become:

1. Execute the run plan.
2. If the result is `data_waiting`, keep the existing waiting-data behavior and skip digestion.
3. If the run succeeded, call `run_diff_digestion(auth_token, run_id, biz_date)`.
4. Record an `auto_diff_digestion` summary in `artifacts_json.runtime_summary`.
5. Complete the queue job.
6. Record queue completion timing in `artifacts_json.runtime_summary.queue`.
7. Run `finalize_and_deliver_daily_digest`.

The ordering is important: daily digest finalization must run after automatic digestion so the
delivered result reflects the final open differences.

## Failure Semantics

Automatic digestion is a post-processing step. If it fails, the reconciliation task remains
successful.

Cases:

- Reconciliation fails: keep the existing failure path; do not run automatic digestion.
- Reconciliation enters `data_waiting`: keep the existing waiting-data path; do not run automatic
  digestion.
- Reconciliation succeeds and automatic digestion succeeds: complete the queue job and finalize the
  digest with digested open counts.
- Reconciliation succeeds and automatic digestion fails or times out: log a warning, write failure
  details into run artifacts, complete the queue job, and finalize the digest with the current run
  counts.
- Run ID is missing: skip automatic digestion, record that it was not attempted, and keep the
  reconciliation successful.

## Run Artifact Summary

The worker should write automatic digestion metadata into:

```json
artifacts_json.runtime_summary.auto_diff_digestion
```

Successful example:

```json
{
  "enabled": true,
  "attempted": true,
  "ok": true,
  "error": "",
  "started_at": "2026-06-17T10:00:00+08:00",
  "finished_at": "2026-06-17T10:00:12+08:00",
  "duration_seconds": 12.345,
  "summary": {
    "resolved": 10,
    "reclassified": 2,
    "kept": 3,
    "open_counts": {}
  }
}
```

Failure example:

```json
{
  "enabled": true,
  "attempted": true,
  "ok": false,
  "error": "等待 MCP 响应超时（600秒）",
  "started_at": "2026-06-17T10:00:00+08:00",
  "finished_at": "2026-06-17T10:10:00+08:00",
  "duration_seconds": 600.123,
  "summary": {}
}
```

Skipped example:

```json
{
  "enabled": true,
  "attempted": false,
  "ok": false,
  "error": "run_id 为空，跳过自动差异消化",
  "summary": {}
}
```

## Logging

Add structured worker logs around the automatic digestion step:

- `INFO` when automatic digestion starts.
- `INFO` when automatic digestion succeeds, including resolved, reclassified, kept, open counts,
  and duration.
- `WARNING` when automatic digestion fails but the reconciliation task remains successful.

The existing manual `resolve` logs should remain unchanged.

## Timeout Strategy

`recon_diff_digestion` currently uses a 600 second MCP result wait timeout. The first
implementation should not raise this timeout. Instead, it should measure real duration in the run
artifact summary and verify a large local run.

If large runs approach or exceed 600 seconds, handle that as a follow-up design. Likely follow-up
options are:

- Increase the specific `recon_diff_digestion` timeout.
- Move automatic digestion to an asynchronous `resolve` job and make digest finalization wait for
  it.
- Optimize diff digestion loading or key pushdown for the affected rules.

## Testing

Unit tests should cover:

- A successful regular schedule job calls `run_diff_digestion`.
- Daily digest finalization runs after automatic digestion.
- Automatic digestion success records an artifact summary.
- Automatic digestion failure still completes the queue job and does not call `recon_queue_fail`.
- `data_waiting` does not run automatic digestion.
- Reconciliation failure does not run automatic digestion.
- Missing run ID skips automatic digestion without failing the queue job.
- `trigger_mode=resolve` keeps the existing behavior and does not call the daily digest finalizer.

Update the existing test that currently asserts regular schedule jobs do not call digestion.

Manual/local verification should include:

1. Run the focused unit tests for diff digestion service and recon worker behavior.
2. Run a small local reconciliation task and confirm the artifact summary is written.
3. Run a larger Bokuan reconciliation task and record:
   - reconciliation duration,
   - automatic digestion duration,
   - total worker duration,
   - whether the 600 second MCP timeout is approached,
   - final open difference counts after digestion.

## Rollout Notes

This change should apply to all successful regular reconciliation tasks by default. It does not
need a per-plan switch in the first version because automatic digestion failure is non-blocking and
because finance users want the final actionable result.

After deployment, monitor worker logs for automatic digestion warnings and review large-task
duration in `runtime_summary.auto_diff_digestion.duration_seconds`.
