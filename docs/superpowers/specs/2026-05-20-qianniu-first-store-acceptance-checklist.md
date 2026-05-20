# QianNiu First-Store Acceptance Checklist

> Companion to:
> - `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`
> - `docs/superpowers/specs/2026-05-20-browser-agent-first-login-sop.md`

First-store is **not** production-ready until every check below passes for one real QianNiu
shop. Treat this as the v1 sign-off gate — unit tests verify wiring, this checklist verifies
that wiring actually drives a real merchant browser session against the real fund-bill page.

## Prerequisites

- [ ] Collection machine passes `scripts/check_environment.py` (all four boolean fields true,
      `font_probe="ok"`, `timezone_id="Asia/Shanghai"`).
- [ ] `START_ALL_SERVICES.sh` starts browser-agent without errors.
- [ ] One `browser_playbook` data source row exists for the test shop.
- [ ] One **published** `data_source_datasets` row exists for that source with
      `source_type='browser_collection_records'`.
- [ ] **Playbook registration + first-time verification flow completed for the test shop** —
      see `2026-05-20-browser-agent-first-login-sop.md`. Operator submitted playbook +
      merchant credentials via finance-web 数据连接 → 浏览器抓取 (`BrowserPlaybookPanel`,
      which replaces the legacy `source_kind='browser'` reserved card); the asynchronous
      verification dry-run returned success and the operator clicked "激活" so both rows are now active:
  - [ ] `playbooks.status='active'` (set by the verification flow, not by hand)
  - [ ] `shop_runtime_bindings.profile_status='active'`, `playbook_status='ok'`,
        `credential_ref` populated (set by the verification flow, not by hand)
  - [ ] `shop_runtime_bindings.agent_id` matches the collection machine running browser-agent
  - [ ] The persistent profile under `/var/lib/tally-agent/profiles/<shop_id>/` was created
        as a byproduct of the verification dry-run (operator did NOT SSH the box manually)

## Live-Run Evidence

For three **real** QianNiu business dates (recommend 2 past T-1 plus the most recent T-1),
trigger one collection per date and capture the following evidence:

### Per-date evidence (×3)

- [ ] `biz_date` chosen: ________________
- [ ] `sync_job_id` created: ________________
- [ ] Browser-agent claim happened within ≤ poll interval after trigger.
- [ ] Playwright opens the real QianNiu fund-bill page using the persistent profile (no
      AUTH_EXPIRED, no RISK_VERIFICATION).
- [ ] One file downloaded into `BROWSER_AGENT_DOWNLOAD_ROOT/<shop_id>/<sync_job_id>/`.
- [ ] `browser_collection_records` row count > 0 for this `(shop_id, biz_date)`.
- [ ] `browser_capture_files` has exactly one row referencing the downloaded file path with
      non-empty `checksum` and `row_count` matching the parsed detail row count.

### Layer 2 exact-match (per date, no tolerance)

- [ ] Parsed detail row count **==** the value extracted from the page's `extract_summary`
      step (`row_count` mapping).
- [ ] `sum(parsed amount) == amount_total` from the same summary step, **after** normalizing
      both sides to `Decimal` with 2 fractional digits — no float comparison.

If any date fails Layer 2: the playbook's selectors or its `accounting_policy` are wrong, not
the runner. Re-author the playbook before re-running.

### Recon waiting-data path

- [ ] Trigger a reconciliation that depends on `browser_collection_records` **before** the
      browser collection finishes. Confirm `recon_execution_queue.status='waiting_data'` and
      `collection_job_ids` is non-empty.
- [ ] After collection success, confirm `data_wait_resume_count` incremented and the recon
      job moved back to `queued`, then to `done`.
- [ ] Manually flip a test binding to `risk_blocked`, trigger collection, confirm:
      - `data_source_trigger_dataset_collection` returns `failure_type=browser_binding_unavailable`
      - no `sync_jobs` row is created
      - any `recon_execution_queue` row referencing that source surfaces the binding failure,
        not a 90-min `waiting_data` timeout.

## Evidence To Save

Attach to the sign-off ticket:

- Three `sync_job` IDs.
- Three `recon_execution_queue` job IDs (if recon was exercised).
- The three `biz_date` values used.
- Row counts and amount totals (parsed and summary) for each date — must show exact equality.
- Capture file storage paths and checksums.
- Screenshots or logs of the real QianNiu export flow for at least one date (proof that
  Playwright really drove a real page, not a synthetic stand-in).
- `browser-agent.log` excerpt for the three runs.

## Sign-off

- Operator: ________________  Date: ________________
- Engineering: ________________  Date: ________________

Sign-off means: first-store v1 is allowed to run unattended for the test shop. Onboarding a
second shop or moving from T-1 to multiple-daily collection requires its own follow-up plan
(see Deferred Work Register in the production hardening plan).
