# Browser Agent First-Login SOP

> Companion to the production hardening design at
> `docs/superpowers/specs/2026-05-20-browser-first-store-production-hardening-design.md`.

## Purpose

Before enabling scheduled browser collection for a shop, an operator must create and verify a
persistent Chrome profile for that shop on the collection machine. The runner trusts the
profile already contains a logged-in session — it does **not** automate first login, because
first login may hit risk verification (滑块/短信/安全校验) that an automated session cannot
solve safely.

## Pre-flight

1. Run the environment readiness check:
   ```bash
   cd finance-agents/browser-agent
   BROWSER_AGENT_PROFILE_ROOT=/var/lib/tally-agent/profiles \
   BROWSER_AGENT_DOWNLOAD_ROOT=/var/lib/tally-agent/downloads \
   python scripts/check_environment.py
   ```
2. Confirm the JSON report has:
   - `profile_root_writable: true`
   - `download_root_writable: true`
   - `playwright_importable: true`
   - `chromium_launchable: true`
   - `timezone_id: "Asia/Shanghai"`
   - `font_probe: "ok"` (or fix CJK fonts: `apt install fonts-noto-cjk fonts-wqy-zenhei`)

If any of the above is false, fix the host before proceeding.

## First-Login Steps

1. Set `BROWSER_AGENT_PROFILE_ROOT=/var/lib/tally-agent/profiles` and ensure the directory
   exists and is writable by the user that runs `service.py`.
2. Launch a non-headless Chrome/Playwright persistent context for the shop id:
   ```bash
   cd finance-agents/browser-agent
   BROWSER_AGENT_HEADLESS=0 BROWSER_AGENT_RUNNER_MODE=playwright \
   python -c "from playwright.sync_api import sync_playwright; \
              import os; \
              p = sync_playwright().start(); \
              ctx = p.chromium.launch_persistent_context('/var/lib/tally-agent/profiles/<shop_id>', headless=False); \
              input('Log in then press enter to close.'); ctx.close(); p.stop()"
   ```
3. Log in with the merchant-provided collection sub-account.
4. Navigate to the target QianNiu fund bill page that the playbook will open.
5. Confirm no risk verification is blocking the account; if a slider / SMS code is shown,
   complete it manually now.
6. Close the browser cleanly (no force-kill — the persistent context flushes state on close).
7. In Tally Cloud (via Operator UI / MCP), upsert the shop binding:
   - `shop_runtime_bindings.profile_status = 'active'`
   - `shop_runtime_bindings.playbook_status = 'ok'`
   - `shop_runtime_bindings.runtime_profile_ref = 'profiles/<shop_id>'`
   - `shop_runtime_bindings.agent_id = '<the agent_id this machine runs as>'`

## Risk Verification Fallback (noVNC deferred for v1)

`noVNC` UI integration is deferred. For v1, when QianNiu shows risk verification during
production collection, the dispatcher loop classifies the result as `RISK_VERIFICATION` and
cloud-side `mark_browser_sync_job_failed` flips the binding to:

- `profile_status = 'risk_blocked'`
- `cron_pause_reason = 'RISK_VERIFICATION'`

Scheduled collection then pauses for that shop (the claim SQL filters by
`profile_status='active'`). An operator must:

1. SSH or physically log in to the collection machine.
2. Open the shop's persistent profile in a non-headless browser.
3. Complete the verification manually (same flow as first login).
4. Reset the binding via Operator UI / MCP back to `profile_status='active'` and clear
   `cron_pause_reason`.

Do **not** keep retrying scheduled collection until the verification is cleared — retries
against an active risk challenge tend to escalate platform-side counter-measures.

## Sanity Check

After binding is `active`, trigger a one-shot collection via the data source UI and verify:

- A `sync_jobs` row appears with `job_status='pending'` and `browser_fail_reason=''`.
- Within a few seconds the browser-agent claims it (`job_status='running'`).
- On success the row reaches `job_status='success'`, `browser_collection_records` has rows
  for the requested `biz_date`, and `browser_capture_files` records the downloaded file.
- If the test fails with `AUTH_EXPIRED`, the profile is already stale — repeat first login.
