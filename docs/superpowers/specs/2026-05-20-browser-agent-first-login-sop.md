# Playbook Registration And First-Time Verification SOP

> Companion to:
> - `docs/superpowers/specs/2026-05-15-tally-collection-agent-architecture-design.md` (see "Playbook 注册时的首次验证流程")
> - `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md` (see "Playbook Registration And First-Time Verification (v1)")
>
> **Supersedes**: an earlier version of this file documented a "manual first login on the
> collection machine" flow. That model was wrong. First login happens server-side as part of
> playbook registration; operators never SSH the collection box for normal onboarding.

## Purpose

Bring one new merchant shop online. The collection machine requires no per-shop human action;
all binding state is established through Tally Cloud.

## Pre-flight (one-time per collection machine)

Run the environment readiness check on the collection machine:
```bash
cd finance-agents/browser-agent
BROWSER_AGENT_PROFILE_ROOT=/var/lib/tally-agent/profiles \
BROWSER_AGENT_DOWNLOAD_ROOT=/var/lib/tally-agent/downloads \
python scripts/check_environment.py
```

Confirm the JSON report has:
- `profile_root_writable: true`
- `download_root_writable: true`
- `playwright_importable: true`
- `chromium_launchable: true`
- `timezone_id: "Asia/Shanghai"`
- `font_probe: "ok"` (else `apt install fonts-noto-cjk fonts-wqy-zenhei`)

If any of the above is false, fix the host before onboarding any shop.

## Per-Shop Onboarding (Tally backend only)

### Step 1 — Generate the playbook (v1: AI-assisted local flow)

Use Claude Code or codex on your laptop with the v1 schema (see main spec "Playbook JSON v1 Contract")
to produce a `playbook_body` JSON for the target site (QianNiu fund bill, etc.). The
playbook must:
- accept `params.biz_date`
- declare `output.item_key_fields`, `output.columns`, `quality_gate`, `accounting_policy`, `failure_mapping`
- include an `extract_summary` step for Layer 2 cross-check
- use only v1 action set (`navigate / click / fill / set_date / wait_for / extract_text / extract_summary / download / parse_table / assert`)

> v2 (Authoring Worker) will replace this manual step with an in-product natural-language UI
> backed by Claude Agent SDK + DeepSeek-V4 Pro. Not in scope for first-store.

### Step 2 — Publish the browser dataset

In Tally backend, for the merchant's `browser_playbook` data source, publish one
`data_source_datasets` row with `source_type='browser_collection_records'`. This is the
landing dataset for collected rows; without it, registration is rejected.

### Step 3 — Register playbook + credentials + run synchronous verification

Submit `data_source_register_browser_playbook` (via Operator UI or MCP tool) with:
- `source_id` (the merchant's browser_playbook data source)
- `playbook_id`, `version`, `title`, `playbook_body` (from Step 1)
- `shop_id`, `agent_id` (the collection machine that owns this shop)
- `credential_username` + `credential_password` (merchant-issued sub-account with order/fund
  download permissions). These are stored KMS-encrypted; only `credential_ref` is exposed in
  any read path.
- `verification_biz_date` (default: most recent T-1)

Tally then **atomically**:
1. Writes `playbooks` (`status='draft'`) and `shop_runtime_bindings`
   (`profile_status='verifying'`, `playbook_status='ok'`, `credential_ref=<encrypted>`).
2. Triggers one synchronous browser sync_job with `verification=true`. browser-agent claims
   it, logs in on the collection machine using the supplied credentials, runs the playbook
   end-to-end against the real site, and returns the result.
3. On success → both rows atomically flip to active (`playbooks.status='active'`,
   `shop_runtime_bindings.profile_status='active'`) and the persistent profile is now on
   the collection machine for cron to reuse.
4. On failure → returns one of:
   - `AUTH_EXPIRED` — credentials wrong; operator re-submits with corrected credentials.
   - `PAGE_CHANGED` / `DATA_MISMATCH` — playbook is wrong; operator revises and re-submits.
   - `RISK_VERIFICATION` — see fallback below.

### Step 4 — Sanity check

After verification passes, confirm:
- `sync_jobs` has one `job_status='success'` row for the verification (look for `verification=true`).
- `browser_collection_records` has rows for the chosen `verification_biz_date`.
- `browser_capture_files` records the downloaded file with non-empty `checksum`.
- `shop_runtime_bindings.profile_status='active'` and `cron_pause_reason IS NULL`.

The shop is now in cron rotation.

## RISK_VERIFICATION Fallback (noVNC deferred for v1)

If verification (Step 3) or any later production collection returns `RISK_VERIFICATION`, the
binding transitions to `profile_status='risk_blocked'` and `cron_pause_reason='risk_verification'`.
Future scheduled collection is paused for that shop (claim SQL filters by
`profile_status='active'`).

The v1 fallback (until noVNC ships) requires one operator visit to the collection machine:
1. SSH to the collection box.
2. Open the shop's persistent profile in a non-headless browser:
   ```bash
   cd finance-agents/browser-agent
   BROWSER_AGENT_HEADLESS=0 python -c "
   from playwright.sync_api import sync_playwright
   p = sync_playwright().start()
   ctx = p.chromium.launch_persistent_context('/var/lib/tally-agent/profiles/<shop_id>', headless=False)
   input('Clear the verification then press enter to close.')
   ctx.close(); p.stop()
   "
   ```
3. Complete the slider / SMS code / safety check manually.
4. In Tally Cloud, trigger a **re-verify** through the same registration endpoint (it can
   accept "re-verify only" without changing playbook or credentials). On success the binding
   flips back to `profile_status='active'`.

Do **not** keep retrying scheduled collection automatically while the binding is `risk_blocked`
— platform-side counter-measures escalate against repeated failed verifications.

## What This SOP Does NOT Cover

- One-off creation of a new persistent profile by hand. There is no such flow in v1; the
  profile is created server-side as a byproduct of the verification dry-run.
- Operator selection of a specific collection agent. The Tally backend resolves this via
  `shop_runtime_bindings.agent_id` configured at registration time.
- Credential rotation. See the main spec's "凭证轮换与回收" section; rotation reuses the
  registration endpoint to re-verify with the new credentials before activating.
