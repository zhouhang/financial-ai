# Playbook Registration And First-Time Verification SOP

> Companion to:
> - `docs/superpowers/specs/2026-05-15-tally-collection-agent-architecture-design.md` (see "Playbook 注册时的首次验证流程")
> - `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md` (see "Playbook Registration And First-Time Verification (v1)")
>
> **First-store default**: run the collection agent on the local Mac/Windows collection
> machine with installed Google Chrome Stable, headed mode, and a persistent per-shop profile.
> Playwright's bundled Chromium is a development fallback only and is not the recommended
> QianNiu production path.

## Purpose

Bring one new merchant shop online. The collection machine can be macOS, Windows, or Linux;
for first-store validation we use the local machine that has already logged into QianNiu with
the merchant sub-account and confirmed no captcha appears.

## Pre-flight (one-time per collection machine)

Run the environment readiness check on the collection machine:
```bash
cd finance-agents/browser-agent
BROWSER_AGENT_BROWSER_CHANNEL=chrome \
BROWSER_AGENT_HEADLESS=0 \
BROWSER_AGENT_PROFILE_ROOT="$HOME/tally-browser-agent/profiles" \
BROWSER_AGENT_DOWNLOAD_ROOT="$HOME/tally-browser-agent/downloads" \
python scripts/check_environment.py
```

Confirm the JSON report has:
- `profile_root_writable: true`
- `download_root_writable: true`
- `playwright_importable: true`
- `chrome_launchable: true`
- `browser_channel: "chrome"`
- `headless: false`
- `timezone_id: "Asia/Shanghai"`
- `font_probe: "ok"` when `fc-list` exists. On macOS, `font_probe="fc_list_missing"` is acceptable if Chrome renders the QianNiu Chinese pages normally.

If `chrome_launchable` is false, install Google Chrome Stable and re-run the check. If profile
or download roots are not writable, fix the directory/env configuration before onboarding any
shop.

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

Open finance-web → **数据连接 → 浏览器**(`BrowserPlaybookPanel`). This card reuses the slot previously occupied by the legacy `source_kind='browser'` placeholder; in v1 it is the actual registration UI.

In the form, submit:
- `source_id` (the merchant's browser_playbook data source — picked from the dropdown)
- `playbook_id`, `version`, `title`, `playbook_body` (from Step 1)
- `credential_username` + `credential_password` (merchant-issued sub-account with order/fund
  download permissions). These are stored KMS-encrypted; only `credential_ref` is exposed in
  any read path.
- `verification_biz_date` (default: most recent T-1)
- a published browser dataset to land into (dropdown).
- `egress_group` (optional).

> `shop_id` and `agent_id` are **not** in the form. `shop_id` is derived from
> `data_source.code` server-side; `agent_id` defaults to env `BROWSER_AGENT_DEFAULT_AGENT_ID`
> (fallback `browser-agent-local`). The single-node v1 doesn't need operator-driven agent
> picking; Tally queues the sync_job and the registered agent claims it.

Submitting the form calls `POST /api/data-sources/{source_id}/browser-playbook/register`,
which:
1. Writes `playbooks` (`status='draft'`) and `shop_runtime_bindings`
   (`profile_status='verifying'`, `playbook_status='ok'`, `credential_ref=<encrypted>`).
2. Creates one async browser sync_job with `is_verification=true`. browser-agent claims it and
   runs the playbook end-to-end against the real site using installed Chrome Stable in headed
   mode with the persistent profile under `BROWSER_AGENT_PROFILE_ROOT/<shop_id>`.
3. The panel polls `/api/sync-jobs/{verification_sync_job_id}` every 5s (max 20min).
4. On `job_status='success'` → the panel surfaces an **激活** button; clicking it calls
   `POST /api/data-sources/browser-playbook/finalize` which atomically flips both rows to
   active (`playbooks.status='active'`, `shop_runtime_bindings.profile_status='active'`).
   The persistent profile is now on the collection machine for cron to reuse.
5. On `job_status='failed'` → the panel shows `browser_fail_reason` + `error_message`:
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

The v1 fallback (until noVNC ships) requires one operator visit to the collection machine. On
the local Mac/Windows first-store machine, do this directly on that machine:
1. Open the shop's persistent profile in a non-headless Chrome session:
   ```bash
   cd finance-agents/browser-agent
   BROWSER_AGENT_BROWSER_CHANNEL=chrome \
   BROWSER_AGENT_HEADLESS=0 python -c "
   from playwright.sync_api import sync_playwright
   p = sync_playwright().start()
   import os, pathlib
   profile_root = pathlib.Path(os.environ.get('BROWSER_AGENT_PROFILE_ROOT', pathlib.Path.home() / 'tally-browser-agent' / 'profiles'))
   ctx = p.chromium.launch_persistent_context(
       str(profile_root / '<shop_id>'),
       channel='chrome',
       headless=False,
   )
   input('Clear the verification then press enter to close.')
   ctx.close(); p.stop()
   "
   ```
2. Complete the slider / SMS code / safety check manually.
3. In Tally Cloud, trigger a **re-verify** through the same registration endpoint (it can
   accept "re-verify only" without changing playbook or credentials). On success the binding
   flips back to `profile_status='active'`.

Do **not** keep retrying scheduled collection automatically while the binding is `risk_blocked`
— platform-side counter-measures escalate against repeated failed verifications.

## What This SOP Does NOT Cover

- One-off creation of a new persistent profile by hand. There is no such flow in v1; the
  profile is created server-side as a byproduct of the verification dry-run.
- Operator selection of a specific collection agent. The Tally backend resolves this via
  `shop_runtime_bindings.agent_id`, defaulted server-side from env
  `BROWSER_AGENT_DEFAULT_AGENT_ID` at registration time. v1 is single-node; multi-node
  agent-assignment is a v2 concern.
- Credential rotation. See the main spec's "凭证轮换与回收" section; rotation reuses the
  registration endpoint to re-verify with the new credentials before activating.
