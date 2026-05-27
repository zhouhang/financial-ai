# Browser Sync Job Manual Clear Design

## Context

Browser collection development often leaves a sync job partially failed while the UI still shows
the task as waiting, running, waiting for human verification, or resuming. These non-terminal
states can block new work because the system continues to treat the current browser collection as
in flight.

The existing `BrowserPlaybookPanel` already has a delete button, but that deletes or disables the
browser collection data source. This change must not duplicate that behavior. It only clears the
current stuck execution job for development-stage recovery.

## Goals

- Add a manual "clear task" action for stuck browser sync jobs.
- Keep the browser collection data source, dataset, playbook, and credentials intact.
- Represent manual clearing as `sync_jobs.job_status = 'cancelled'` with a clear reason.
- Make downstream `waiting_data` reconciliation jobs stop waiting when their collection job is
  manually cleared.
- Prevent late browser-agent callbacks from overwriting a manually cancelled job.

## Non-Goals

- No automatic timeout cleanup or scheduler-based fallback.
- No batch cleanup.
- No reset of `shop_runtime_bindings` health state.
- No deletion of browser collection configuration.
- No attempt to forcibly terminate an already-running local Playwright thread.

## Backend Design

Add a user-authenticated clear path:

`finance-web -> data-agent REST -> data-agent mcp_client -> finance-mcp tool -> auth.db`

The finance-mcp tool should be named `data_source_clear_browser_sync_job`.

Inputs:

- `auth_token`
- `sync_job_id`
- optional `reason`

Validation:

- Resolve the current user from `auth_token`.
- Load the sync job and require `job.company_id == user.company_id`.
- Require the job to belong to a `data_sources.source_kind = 'browser_playbook'` data source.
- Allow clearing only these statuses:
  - `pending`
  - `queued`
  - `running`
  - `waiting_human_verification`
  - `resuming`
- Reject terminal jobs such as `success`, `failed`, and `cancelled`.

State update:

- `sync_jobs.job_status = 'cancelled'`
- `sync_jobs.browser_fail_reason = 'MANUAL_CLEARED'`
- `sync_jobs.error_message = 'MANUAL_CLEARED: operator cleared stuck browser task'`
- `sync_jobs.completed_at = now()`
- `sync_jobs.next_retry_at = NULL`
- `sync_jobs.updated_at = now()`

If the sync job has a non-final browser handoff session, mark that handoff session `cancelled` and
append an audit event with `event_type = 'manual_clear'`.

The clear operation should be idempotent for already-cleared jobs only if the caller gets a clear
"already cancelled" response. It should not silently report success for unrelated terminal states.

## Late Callback Protection

Manual clearing changes cloud-side state only. A local browser-agent thread may still be running and
may later report success or failure. The worker callback handlers must not overwrite a cancelled
job.

Update the browser worker completion/failure path so `browser_sync_job_complete` and
`browser_sync_job_fail` only transition jobs that are still in an active browser execution state:

- `running`
- `waiting_human_verification`
- `resuming`

If the current job status is `cancelled`, the handler should return success with the unchanged job
or a clear no-op response. It must not change the status back to `success` or `failed`.

## Reconciliation Waiting-Data Link

The current waiting-data reconciler fast-fails only when referenced collection jobs are `failed`.
Manual clearing uses `cancelled`, so the reconciler must treat both `failed` and `cancelled` as
terminal collection failures.

Update the waiting-data failure query so any waiting reconciliation job whose
`collection_job_ids` include a sync job with `job_status IN ('failed', 'cancelled')` is marked
failed immediately. The error should use the sync job error message, so a manually cleared
collection surfaces as:

`MANUAL_CLEARED: operator cleared stuck browser task`

This is not an automatic browser cleanup policy. It only makes the explicit manual clear action
release downstream waiting jobs.

## Data-Agent API

Add a REST endpoint:

`POST /api/sync-jobs/{sync_job_id}/clear`

Request body:

```json
{
  "reason": "optional operator note"
}
```

Response:

```json
{
  "success": true,
  "job": {},
  "message": "当前浏览器任务已清除，可重新下发或等待后续任务执行"
}
```

The endpoint uses the current `Authorization` bearer token and calls
`data_source_clear_browser_sync_job` through `tools.mcp_client`.

## Frontend Design

In `BrowserPlaybookPanel`, add a "清除任务" action beside "详情 / 重试 / 删除".

Show the button only when:

- `source.browser_verification.sync_job_id` exists, and
- `job_status` is one of:
  - `pending`
  - `queued`
  - `running`
  - `waiting_human_verification`
  - `resuming`

Do not show the button for:

- `success`
- `failed`
- `cancelled`
- missing `sync_job_id`

Before calling the API, show a confirmation dialog that states:

`确认清除当前执行任务？这只会清除卡住的浏览器执行任务，不会删除浏览器采集配置。`

On success:

- Refresh the browser task list via `onRegistered`.
- Show:
  `当前浏览器任务已清除，可重新下发或等待后续任务执行`
- Display `cancelled + MANUAL_CLEARED` as `已清除` in the task status badge.
- Keep the existing delete button as the data-source deletion action.

The button should use the existing `actionBusy` guard so it cannot race with retry or delete.

## Testing

Finance-mcp tests:

- Clears a stuck browser-playbook sync job for the current company.
- Rejects a sync job from another company.
- Rejects non-browser-playbook sync jobs.
- Rejects terminal jobs.
- Marks a related non-final handoff session `cancelled`.
- Prevents complete/fail worker callbacks from overwriting `cancelled`.
- Waiting-data reconciliation fails when a referenced collection job is `cancelled`.

Data-agent tests:

- `POST /api/sync-jobs/{id}/clear` forwards the auth token and sync job id to mcp_client.
- API returns a success message on clear success.
- API returns a user-facing error when finance-mcp rejects the clear.

Frontend tests:

- Stuck statuses show "清除任务".
- Terminal statuses do not show "清除任务".
- Clicking clear confirms, calls `/api/sync-jobs/{id}/clear`, refreshes the list, and shows the
  success notice.
- `cancelled + MANUAL_CLEARED` displays as `已清除`.

## Rollout

This is a development-stage manual recovery feature. It should ship without enabling any automatic
cleanup policy. If stuck browser jobs continue to be common after the browser task system
stabilizes, a separate design should consider automatic timeout handling with stricter safeguards.
