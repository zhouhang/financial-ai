# QianNiu First-Store Acceptance Checklist

> Companion to:
> - `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`
> - `docs/superpowers/specs/2026-05-20-browser-agent-first-login-sop.md`

First-store is **not** production-ready until every check below passes for one real QianNiu
shop. Treat this as the v1 sign-off gate — unit tests verify wiring, this checklist verifies
that wiring actually drives a real merchant browser session against the real fund-bill page.

## Prerequisites

- [ ] Collection machine is the local Mac/Windows/Linux host that will run browser-agent.
      For first-store validation, use the local Mac already verified with the merchant
      sub-account in Google Chrome.
- [ ] Collection machine uses installed Google Chrome Stable in headed mode:
      `BROWSER_AGENT_BROWSER_CHANNEL=chrome`, `BROWSER_AGENT_HEADLESS=0`.
- [ ] Runtime env exists in root `.env`:
      `BROWSER_AGENT_ID=browser-agent-local`,
      `BROWSER_AGENT_DEFAULT_AGENT_ID=browser-agent-local`,
      `BROWSER_AGENT_COMPANY_ID=00000000-0000-0000-0000-00000000dd01`,
      `BROWSER_AGENT_PROFILE_ROOT=/Users/kevin/tally-browser-agent/profiles`,
      `BROWSER_AGENT_DOWNLOAD_ROOT=/Users/kevin/tally-browser-agent/downloads`.
      `BROWSER_AGENT_COMPANY_ID` is the Tally service-provider node owner for heartbeat only;
      it is not the merchant company and not the DingTalk channel owner.
- [ ] Collection machine passes `finance-agents/browser-agent/scripts/check_environment.py`:
      `profile_root_writable=true`, `download_root_writable=true`,
      `playwright_importable=true`, `chrome_launchable=true`,
      `browser_channel="chrome"`, `headless=false`, `timezone_id="Asia/Shanghai"`.
      On macOS, `font_probe="fc_list_missing"` is acceptable if Chrome renders QianNiu
      Chinese pages normally; on Linux prefer `font_probe="ok"`.
- [ ] `START_ALL_SERVICES.sh` starts browser-agent without errors.
- [ ] One `browser_playbook` data source row exists for the test shop.
- [ ] One **published** `data_source_datasets` row exists for that source with
      `source_type='browser_collection_records'`.
- [ ] Credential safety verified:
  - [ ] merchant sub-account password is not stored as plaintext in PostgreSQL
  - [ ] normal data-source/read APIs return only `credential_ref`, never the plaintext password
  - [ ] browser-agent, finance-mcp, and data-agent logs do not print the plaintext password
- [ ] Minimal DingTalk alerting configured through the existing Tally DWS collaboration channel:
  - [ ] DWS CLI is `v1.0.30` or newer.
  - [ ] `dws cache refresh` was run after upgrade.
  - [ ] `dws schema --format json --jq '.products[] | select(.id=="bot") | [.tools[].name]'`
        includes `batch_send_robot_msg_to_users`; otherwise `send-by-bot` can fail with
        `endpoint not resolved for product "bot"`.
  - [ ] `BROWSER_COLLECTION_ALERTS_ENABLED=true` is set only on the first-store runtime
        after one real bot-message delivery to 周行 succeeds.
  - [ ] `DINGTALK_CLIENT_ID`, `DINGTALK_CLIENT_SECRET`, and `DINGTALK_ROBOT_CODE` are set
        to the Anhui Namai DingTalk DWS app/robot credentials. Do not configure a Tally
        internal `company_channel_configs.id` such as `c991...` in runtime env.
  - [ ] `BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD=周行`
  - [ ] recipient resolves to 周行's DingTalk user id
  - [ ] a test `send_bot_message` reaches 周行 as a DingTalk bot message
  - [ ] no DingTalk todo is created for browser collection technical alerts
  - [ ] no standalone DingTalk webhook is introduced for browser alerts
- [ ] Browser alert events are wired or verified for first-store:
  - [ ] browser-agent offline/down beyond grace window
  - [ ] terminal browser sync failure
  - [ ] `RISK_VERIFICATION` / `risk_blocked`
  - [ ] consecutive missed successful collections
  - [ ] reconciliation unavailable because browser data was not ready
- [ ] **Playbook registration + first-time verification flow completed for the test shop** —
      see `2026-05-20-browser-agent-first-login-sop.md`. Operator submitted playbook +
      merchant credentials via finance-web 数据连接 → 浏览器 (`BrowserPlaybookPanel`,
      which replaces the legacy `source_kind='browser'` reserved card); the asynchronous
      verification dry-run returned success and the operator clicked "激活" so both rows are now active:
  - [ ] `playbooks.status='active'` (set by the verification flow, not by hand)
  - [ ] `shop_runtime_bindings.profile_status='active'`, `playbook_status='ok'`,
        `credential_ref` populated (set by the verification flow, not by hand)
  - [ ] `shop_runtime_bindings.agent_id` matches the collection machine running browser-agent
  - [ ] The persistent profile under `BROWSER_AGENT_PROFILE_ROOT/<shop_id>/` was created or
        reused by the verification dry-run. For local Mac first-store testing, use
        `$HOME/tally-browser-agent/profiles/<shop_id>`.

## Live-Run Evidence

For three **real** QianNiu business dates (recommend 2 past T-1 plus the most recent T-1),
trigger one collection per date and capture the following evidence:

### Per-date evidence (×3)

- [ ] `biz_date` chosen: ________________
- [ ] `sync_job_id` created: ________________
- [ ] Browser-agent claim happened within ≤ poll interval after trigger.
- [ ] Playwright opens the real QianNiu fund-bill page in installed Chrome Stable using the
      persistent profile (no AUTH_EXPIRED, no RISK_VERIFICATION).
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
- DingTalk alert proof:
  - one successful bot-message-only test alert to 周行
  - one simulated or real browser failure alert to 周行
  - one simulated or real `risk_blocked` alert to 周行

## Sign-off

- Operator: ________________  Date: ________________
- Engineering: ________________  Date: ________________

Sign-off means: first-store v1 is allowed to run unattended for the test shop. Onboarding a
second shop or moving from T-1 to multiple-daily collection requires its own follow-up plan
(see Deferred Work Register in the production hardening plan).

## Deferred Before Second/Third Shop

- Customer authorization / operation-confirmation trail for merchant sub-account delegation.
- Formal KMS envelope encryption with key rotation and credential access audit export.
- noVNC or an equivalent controlled remote verification channel so `RISK_VERIFICATION`
  handling no longer depends on direct access to the collection machine.
- Full alert management UI, recipient preferences, and alert deduplication controls.
- Multi-node browser-agent capacity and failover validation.
