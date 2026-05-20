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

## Playbook Registration And First-Time Verification (v1)

First login is **not** an operator action on the collection machine. It is part of Playbook
Registration in the Tally backend:

1. Operator generates the playbook JSON with Claude Code or codex (v1) — local AI coding tool flow, not a production component.
2. Operator submits via the `data_source_register_browser_playbook` MCP tool with:
   - `playbook_body` (the JSON)
   - merchant-issued sub-account `username` / `password` for the shop (具备订单和资金数据下载权限)
   - `biz_date` for the verification dry-run (default = most recent T-1)
3. Tally Cloud writes `playbooks` row (`status='draft'`) and `shop_runtime_bindings`
   (`profile_status='verifying'`, `credential_ref=<KMS-encrypted>`) **first**, then triggers
   one synchronous browser sync_job marked `verification=true`. browser-agent claims it,
   logs in with the supplied credentials, runs the playbook, returns the result.
4. On success → `playbooks.status='active'` and `shop_runtime_bindings.profile_status='active'`
   atomically. The persistent profile is now on the collection machine and production cron
   can claim subsequent jobs for this shop.
5. On failure → the failure reason (`AUTH_EXPIRED` / `PAGE_CHANGED` / `DATA_MISMATCH` /
   `RISK_VERIFICATION`) is returned to the operator UI with actionable next steps. Binding
   stays `verifying` (or moves to `risk_blocked` for RISK_VERIFICATION) — playbook never goes
   active without a green dry-run.

The collection machine therefore needs **no SSH access** and **no operator-driven local
login** during normal onboarding. The only time someone touches the machine directly is the
RISK_VERIFICATION fallback path (noVNC deferred for v1; operator goes to the box to clear a
slider once).

Production collection ships the same `(playbook + credential_ref)` pair via the RUN_PLAYBOOK
message. browser-agent prefers the persistent profile (already logged in from the
verification dry-run) and only re-uses the plaintext credentials when the profile is missing
or stale.

## Authoring Worker v2 (Out Of Scope For First-Store)

After first-store stabilizes, `finance-authoring/` becomes a long-running worker that
**wraps Claude Agent SDK + DeepSeek-V4 Pro** to provide the same natural-language → playbook
experience as the v1 Claude-Code / codex flow, but inside the Tally web UI. Operators
no longer rely on a local AI IDE. The first-time verification path stays the same — Authoring
Worker hands the freshly-synthesized playbook to the existing registration endpoint, which
runs the same synchronous verification dry-run before activation.

## Deferred

- Full WS runner protocol with HELLO/HEARTBEAT/ack lease.
- noVNC live browser UI.
- Browser-record soft delete for rows missing from a later recapture (see "Soft Delete Limitation" below).
- Multi-machine fleet assignment UI.
- Canary version routing in browser job claim (currently `p.status = 'active'` only; `canary_shop_ids` not consulted).
- Automatic cleanup of stale pending browser sync_jobs whose binding turned unhealthy after creation.

## Soft Delete Limitation

First-store v1 does not mark browser records missing from a later successful recapture as
`deleted`. Repeated captures upsert seen rows and leave previously seen rows active. The
`upsert_browser_collection_records` helper therefore always returns `deleted_count = 0` and a
test pins this contract so the limitation cannot regress unnoticed.

This is acceptable only for the first real-shop trial because the first target —
`qianniu-daily-bill-export` — is an append-like daily fund bill: rows are added day by day,
historical rows do not change. Before browser collection is used for mutable same-day datasets
(where a row can vanish between two captures of the same `biz_date`), a later hardening plan
must add complete-success missing-key soft delete: after a fully-successful recapture, mark
rows present in storage but absent from the latest capture as `record_status = 'deleted'`, but
**only after** the recapture passes all quality gates — partial captures must never trigger
soft delete.
