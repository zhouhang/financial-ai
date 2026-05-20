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

## First-Store Launch Readiness Boundary

First-store launch means one real customer shop runs real T-1 reconciliation under internal
operator supervision. It is not yet customer self-service, but it still handles real merchant
credentials and real financial data. The launch gate is therefore:

1. Credentials are not stored in plaintext, never logged, and are never returned by normal
   read APIs. The current sealed/encrypted credential path is acceptable for first-store only
   if this invariant holds end to end. Formal KMS envelope encryption and key rotation are
   deferred to the next rollout gate.
2. Minimal operator alerting is implemented through the existing Tally collaboration channel
   stack. Do not add a standalone DingTalk webhook. Browser collection alerts reuse
   `services.notifications.get_notification_adapter(...)` and the existing
   `DingTalkDwsAdapter` used by reconciliation exception reminders.
3. First-store browser alerts are internal operator alerts sent to 周行 through DingTalk DWS.
   The default delivery is `send_reminder`: bot message + DingTalk todo + best-effort DING
   strong notification. Pure summary messages may use `send_bot_message`, but blocking
   collection failures should create a todo so they are not missed.
4. Alert events required before first-store launch:
   - browser-agent down or offline beyond the configured grace window
   - browser sync job terminal failure
   - `RISK_VERIFICATION` / `risk_blocked`
   - consecutive missed successful collections for the first-store shop
   - reconciliation failed or stayed unavailable because browser data was not ready
5. The collection machine, installed Google Chrome Stable, headed mode, profile root, and
   download root are fixed for the first-store trial.
6. SOPs exist for first login, risk verification, re-verification, page change, re-collection,
   and re-reconciliation.
7. Real QianNiu validation passes for three business dates and one real reconciliation loop.

Customer authorization / operation-confirmation trail is not a first-store blocker because
the first shop is run under internal operator supervision. It becomes mandatory before
second/third customer expansion and is tracked in Deferred.

## Playbook Registration And First-Time Verification (v1)

First login is **not** an operator action on the collection machine. It is part of Playbook
Registration in **finance-web's 数据连接 → 浏览器 page** (`BrowserPlaybookPanel`):

1. Operator generates the playbook JSON with Claude Code or codex (v1) — local AI coding tool flow, not a production component.
2. Operator opens the **浏览器** tab in 数据连接 (this card reuses the slot previously occupied by the
   legacy `source_kind='browser'` reserved placeholder; v1 replaces the placeholder with real UI).
   The panel form takes:
   - `playbook_body` (paste the JSON)
   - merchant-issued sub-account `username` / `password` for the shop (具备订单和资金数据下载权限)
   - `biz_date` for the verification dry-run (default = most recent T-1)
   - a pre-published browser dataset to land into (dropdown);
     `egress_group` is optional.
   - **`shop_id` / `agent_id` are not asked**:
     - `shop_id` is derived server-side from `data_source.code` (one data source = one shop in this design).
     - `agent_id` is picked server-side from the registered collection agents pool;
       v1 has a single node, so the env default `BROWSER_AGENT_DEFAULT_AGENT_ID`
       (fallback `browser-agent-local`) is used. Tally drops the verification +
       production sync_jobs into the queue and whichever agent services that
       `agent_id` picks them up.
3. Submitting calls `POST /api/data-sources/{source_id}/browser-playbook/register`, which proxies to the
   MCP tool `data_source_register_browser_playbook`. Tally Cloud writes `playbooks`
   (`status='draft'`) and `shop_runtime_bindings` (`profile_status='verifying'`,
   `credential_ref=<KMS-encrypted>`), then creates one async browser sync_job marked
   `is_verification=true`. browser-agent claims it, logs in with the supplied credentials,
   runs the playbook, returns the result.
4. The panel polls `GET /api/sync-jobs/{verification_sync_job_id}` every 5s (bounded ~20min).
5. On `job_status='success'` → panel shows an "激活" button which calls
   `POST /api/data-sources/browser-playbook/finalize` →
   `playbooks.status='active'` and `shop_runtime_bindings.profile_status='active'`
   atomically. The persistent profile is now on the collection machine and production cron
   can claim subsequent jobs for this shop.
6. On `job_status='failed'` → the panel surfaces `browser_fail_reason` + `error_message`
   (`AUTH_EXPIRED` / `PAGE_CHANGED` / `DATA_MISMATCH` / `RISK_VERIFICATION`). The operator
   revises the form and re-submits. The failed sync_job stays as an audit record;
   production claim never picks it up (claim SQL filters by `is_verification=true ⇒
   profile_status IN ('verifying','active')` and on the binding side the failed verification
   doesn't move the binding to active).

The collection machine therefore needs **no SSH access** and **no operator-driven local
login** during normal onboarding. The only time someone touches the machine directly is the
RISK_VERIFICATION fallback path (noVNC deferred for v1; operator goes to the box to clear a
slider once).

The 「Playbooks / Authoring Jobs / Agents / Shops」 4 standalone operator pages described in
the main spec stay v2 scope — v1 ships only the single `BrowserPlaybookPanel` route, which
covers the full first-store onboarding loop.

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
- Formal KMS envelope encryption, key rotation, and credential access audit export.
- Customer authorization / operation-confirmation trail before second/third customer expansion.
- Full alerting center and customer-facing notification preferences. First-store uses the
  existing DWS collaboration channel with 周行 as the internal operator recipient.
- Multi-node browser-agent failover and capacity dashboard.

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
