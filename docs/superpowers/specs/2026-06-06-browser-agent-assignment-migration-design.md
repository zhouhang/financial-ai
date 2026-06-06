# Browser Agent Assignment And Migration Design

Date: 2026-06-06

## Context

The browser-agent service runs on local collection machines and connects outbound to the
cloud data-agent WebSocket. A connected agent is not enough to receive work. Browser
playbook jobs are claimed only when the runtime binding's `agent_id` matches the connected
collector's `agent_id`.

Current behavior is intentionally strict:

- Agent heartbeat writes online status into `agents`.
- Browser playbook registration writes `shop_runtime_bindings.agent_id`.
- Job claim filters pending browser jobs by `shop_runtime_bindings.agent_id = current agent_id`.
- The default agent for new browser playbook registrations comes from
  `BROWSER_AGENT_DEFAULT_AGENT_ID`, falling back to `browser-agent-local`.

This works for a single early collector, but it does not support an operator smoothly
migrating all jobs from a temporary Mac collector to a permanent Windows collector, or
later adding a second Windows/Mac collector and assigning only some shops to it.

## Goals

- Keep short-term migration explicit: move existing browser playbook bindings from
  `collector-mac-1` to `collector-win-1`.
- Support future dynamic expansion: add `collector-win-2`, `collector-mac-2`, or similar
  and assign selected shops/data sources to them.
- Preserve deterministic ownership. A job should not move to a different collector just
  because that collector is online.
- Avoid moving a running browser job in a way that makes failure handling ambiguous.
- Reuse existing `agents` heartbeat and `shop_runtime_bindings.agent_id` tables where possible.

## Non-Goals

- No automatic "whoever is online claims the job" routing.
- No cross-machine Chrome profile synchronization.
- No collector pool load balancing in this first change.
- No UI-heavy admin workflow in the first implementation unless a later task asks for it.
- No change to CAPTCHA handoff routing semantics.

## Recommended Approach

Keep explicit `agent_id` ownership and add operator-facing assignment tools.

This makes the migration safe and predictable. `collector-win-1` receives work only after
bindings are moved to it. Future collectors receive only the bindings explicitly assigned
to them. This matches the fact that browser collection depends on machine-local Chrome
profiles, cookies, OS-level handoff support, and network environment.

## Rejected Alternatives

### Online Agent Auto-Claim

Let any online collector claim any pending browser playbook job.

This is rejected because browser jobs are not stateless. A collector may lack the shop's
Chrome profile, cookies, local files, OS-level handoff readiness, or expected network path.
It also makes production failures harder to explain because job ownership changes silently.

### Collector Group Load Balancing

Bind a shop to a group such as `windows-prod`, then let any collector in that group claim.

This can be useful later, but it needs sticky assignment or profile synchronization. Without
that, it has the same practical risk as online auto-claim. The first implementation should
solve migration and manual expansion before adding group routing.

## Components

### Agent Status Listing

Add a finance-mcp tool to list browser agents for the current company, reading `agents`.
The result should include:

- `agent_id`
- `hostname`
- `version`
- `status`
- `last_heartbeat_at`
- `is_online` computed from a stale threshold
- `capabilities`, including `max_concurrency` and handoff diagnostics when present

The default online threshold should be conservative, for example 90 seconds or 180 seconds.

### Browser Binding Listing

Add a finance-mcp tool to list browser playbook runtime bindings, reading
`shop_runtime_bindings` joined with `data_sources`.

The result should include:

- `data_source_id`
- `data_source_code`
- `data_source_name`
- `shop_id`
- `playbook_id`
- `agent_id`
- `profile_status`
- `playbook_status`
- whether there is a currently running browser sync job for that binding

Optional filters:

- `agent_id`
- `data_source_id`
- `shop_id`
- `playbook_id`

### Binding Reassignment

Add a finance-mcp tool to reassign browser playbook bindings from one collector to another.

Inputs:

- `from_agent_id`
- `to_agent_id`
- optional filters: `data_source_id`, `shop_id`, `playbook_id`
- `dry_run`, default `true`
- `require_online`, default `true` for execution
- `force_offline_target`, default `false`

Rules:

- Require an authenticated user scoped to the company.
- Reject empty `from_agent_id` or `to_agent_id`.
- Reject no-op reassignment where both ids are equal.
- By default, reject execution when the target agent has no fresh heartbeat.
- Allow pre-assignment to a not-yet-online collector only when `force_offline_target=true`.
- Always return the matching bindings before changing anything.
- Block execution when any matched binding has a running browser sync job.
- Update only `shop_runtime_bindings.agent_id`.
- Do not rewrite sync job history.

The dry-run response should show the exact bindings that would move and whether execution
would be blocked.

## Migration Flow

1. Configure the Windows collector `.env` with:
   - `BROWSER_AGENT_ID=collector-win-1`
   - `DATA_AGENT_WS_URL=wss://www.tallyai.cn/api/browser-agent`
   - `BROWSER_AGENT_MAX_CONCURRENCY=2`
   - the production company id and JWT secret
2. Start the Windows browser-agent in a logged-in interactive desktop session.
3. Verify cloud heartbeat shows `collector-win-1` online.
4. Run reassignment dry-run:
   - `from_agent_id=collector-mac-1`
   - `to_agent_id=collector-win-1`
5. Execute reassignment only when no matched binding has a running browser job.
6. Set ECS `BROWSER_AGENT_DEFAULT_AGENT_ID=collector-win-1` so future browser playbook
   registrations default to the Windows collector.
7. Confirm new browser jobs are claimed by `collector-win-1`.
8. Stop the Mac browser-agent after there are no running browser jobs for `collector-mac-1`.

If Windows is not online yet but the operator wants to pre-stage the assignment, run the
execute step with `force_offline_target=true`. Jobs will stay pending until the target
collector comes online and claims them.

## Future Expansion Flow

For a second collector:

1. Give the machine a stable unique id such as `collector-win-2`.
2. Start it and verify heartbeat.
3. Use binding listing to choose a subset of shops/data sources.
4. Run dry-run reassignment for that subset.
5. Execute reassignment after confirming no matched binding has a running browser job.

This supports controlled scaling without introducing cross-machine profile ambiguity.

## Error Handling

- Missing target heartbeat: return a clear `target_agent_offline` error unless forced.
- Running jobs found: return `running_jobs_present` with affected `sync_job_id` values.
- No matching bindings: return success with `matched_count=0` and no update.
- Database errors: return the original error text through the existing finance-mcp tool
  response pattern and log server-side details.
- Race protection: reassignment SQL should check for running jobs in the same transaction
  before updating bindings.

## Testing

Add focused tests for:

- Agent listing computes online/stale status.
- Binding listing returns agent ids and running-job flags.
- Dry-run reassignment does not update rows.
- Execution updates matching bindings.
- Execution rejects same source and target agent.
- Execution rejects stale or missing target agent unless forced.
- Execution rejects bindings with running browser jobs.
- Existing job claim still filters by exact `agent_id`.
- Browser playbook registration still defaults from `BROWSER_AGENT_DEFAULT_AGENT_ID`.

## Risk And Cost

Implementation risk is low because the browser execution path does not change. The main
change is operational metadata management around `shop_runtime_bindings.agent_id`.

The highest risk is changing a binding while a job is running. The design avoids this by
blocking reassignment when matched bindings have running browser jobs.

Cost is modest:

- A few finance-mcp database helper functions.
- Two or three finance-mcp tools.
- Tests around listing, reassignment, and existing claim behavior.
- Optional CLI/UI exposure later.

No schema migration is required for the first version because `agents` and
`shop_runtime_bindings.agent_id` already exist.

