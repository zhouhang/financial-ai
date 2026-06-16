# Browser Profile-Aware Claim Design

## Context

Production Windows browser collection can run with `BROWSER_AGENT_MAX_CONCURRENCY=2`, but
recent scheduled Taobao jobs did not fully use two distinct login profiles. The observed
sequence was:

- `履冰旗舰店-店铺订单` was claimed and started.
- `履冰旗舰店-收支明细` was claimed immediately after, but waited on the local profile lock
  because it shared the same `runtime_profile_ref`.
- Those two claimed jobs filled the server-side `running` count, so `巴别时代旗舰店` could not
  be claimed until one 履冰 job completed.

The local browser-agent lock is correct: jobs sharing one Chrome profile must be serialized.
The inefficiency is that the server marks a same-profile pending job as `running` before the
local lock can actually run it.

## Goal

Change server-side browser job claim so formal collection jobs prefer executable work:

- Keep the existing per-agent running limit.
- Do not claim a formal collection job when the same agent already has a formal `running` job
  using the same effective browser profile.
- Continue allowing different profile jobs to run in parallel.
- Keep verification jobs out of scope so login repair and manual verification flows remain
  unblocked by this scheduling optimization.

## Non-Goals

- Do not change browser-agent local locking.
- Do not add a new profile lease table.
- Do not change job creation, retry policy, completion handling, or reaper behavior.
- Do not alter `runtime_profile_ref` generation logic.
- Do not make fairness or priority changes beyond avoiding same-profile formal claim.

## Profile Key Semantics

The server claim rule must use the same fallback semantics as the browser-agent runtime lock:

```text
effective_profile_key = runtime_profile_ref if non-empty else shop_id if non-empty else "unknown"
```

In SQL this should be expressed as:

```sql
COALESCE(NULLIF(srb.runtime_profile_ref, ''), srb.shop_id, 'unknown')
```

This matters for old bindings that still have empty `runtime_profile_ref`; they should not all
collapse into one global empty-profile bucket.

## Proposed Design

Update `auth.db.claim_next_browser_sync_job()` in the candidate selection query.

Keep the existing `running_for_agent.running_count < agent_max_concurrency` gate. Add a second
gate for non-verification jobs:

- If `sync_jobs.is_verification = TRUE`, preserve current behavior.
- If `sync_jobs.is_verification = FALSE`, exclude the candidate when an existing formal running
  browser job for the same agent has the same effective profile key.

Conceptually:

```sql
AND (
    sync_jobs.is_verification = TRUE
    OR NOT EXISTS (
        SELECT 1
        FROM sync_jobs running_jobs
        JOIN data_sources running_ds ON running_ds.id = running_jobs.data_source_id
        JOIN shop_runtime_bindings running_srb
          ON running_srb.company_id = running_jobs.company_id
         AND running_srb.data_source_id = running_jobs.data_source_id
        WHERE running_jobs.job_status = 'running'
          AND running_jobs.is_verification = FALSE
          AND running_ds.source_kind = 'browser_playbook'
          AND running_srb.agent_id = srb.agent_id
          AND COALESCE(NULLIF(running_srb.runtime_profile_ref, ''), running_srb.shop_id, 'unknown')
              = COALESCE(NULLIF(srb.runtime_profile_ref, ''), srb.shop_id, 'unknown')
    )
)
```

The final SQL may use a CTE if that reads cleaner, but the behavior should match the above.
Existing `ORDER BY sync_jobs.created_at ASC` should stay unchanged.

## Expected Behavior

When two jobs for the same profile are pending and one is running, the second job stays pending.
Another pending job for a different profile can be claimed if the agent still has capacity.

When the queue contains only same-profile pending jobs, the agent may return idle while waiting
for the running profile to finish. This is intentional; otherwise the job would be marked
`running` but only sit behind the local lock.

Verification jobs keep the current behavior. They may still be claimed while a same-profile
formal job is running, and local locking will serialize actual browser access. This avoids
blocking manual verification and login recovery behind the optimization.

## Risk Analysis

Potential risk: formal jobs may appear to claim more slowly when the queue is dominated by one
profile. This is expected and safer than occupying a running slot while blocked on the local
profile lock.

Potential risk: a stuck formal running job can block later formal jobs for that profile. This is
already true in practice because the local Chrome profile would be locked; the existing browser
job reaper remains responsible for clearing orphaned running jobs.

Potential risk: empty `runtime_profile_ref` could over-serialize old bindings. The explicit
`shop_id` fallback avoids that.

Potential risk: the extra anti-join adds work to claim. The relevant candidate set is small
because it is scoped to pending browser jobs for one agent and running browser jobs for the same
agent. No new index is proposed unless production query timing shows a problem.

## Tests

Add focused tests around `claim_next_browser_sync_job()`:

- SQL contains the formal-job profile exclusion and preserves the existing agent running-count
  gate.
- Same agent + same effective profile + formal running job blocks a formal candidate.
- Same agent + different effective profile does not block a formal candidate.
- Different agent + same effective profile does not block a formal candidate.
- Verification candidates are not blocked by same-profile formal running jobs.
- Empty `runtime_profile_ref` uses `shop_id` fallback.

Where possible, keep tests at the SQL-shape level already used by the current dispatcher tests.
If a lightweight fake cursor can model multiple candidate rows, add one behavioral unit test for
the same-profile/different-profile choice.

## Rollout And Verification

Deploy as a finance-mcp server change. No browser-agent restart is required for the server-side
claim rule itself, but active browser-agent processes will observe the behavior on their next
claim request.

After deploy, verify with a scheduled or manually triggered batch containing at least two shops
with different `runtime_profile_ref` values:

- Two different-profile jobs should become `running` close together.
- Same-profile order and bill jobs should not both become `running` before the first finishes.
- Win browser-agent logs should show two `browser runner starting` lines for different
  `profile_key` values when capacity is available.

