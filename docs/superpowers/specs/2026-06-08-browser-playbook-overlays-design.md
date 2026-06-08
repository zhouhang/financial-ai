# Browser Playbook Overlays Design

## Goal

Make browser collection resilient to site-specific popups without adding new site-specific
selectors to Python code. Page changes, new popup blockers, and new customer sites should be
handled by editing or adding browser playbooks whenever the runner already has the required
generic capability.

The immediate production issue is the QianNiu finance survey popup blocking bill-detail downloads.
The longer-term requirement is to keep the browser runner generic across e-commerce and
non-e-commerce customers.

## Non-Goals

- Do not create a broad playbook scripting language.
- Do not keep QianNiu-specific popup selector lists in the runner as a compatibility layer.
- Do not rerun all shops during verification.
- Do not restart services until the operator chooses the deployment/restart point.

## Playbook Contract

Add an optional top-level `overlays` field to `playbook_body`:

```json
{
  "schema_version": "1.0",
  "overlays": [
    {
      "id": "finance_survey",
      "markers": [".aes-survey-hanging", "text=财务管理工具"],
      "close_selectors": [
        ".aes-survey-hanging--close",
        "[class*='aes-survey-hanging--close']"
      ]
    }
  ],
  "steps": []
}
```

Overlay fields:

- `id`: required stable identifier for logging and tests.
- `markers`: required non-empty selector list. The overlay is considered present only when at
  least one marker is visible.
- `close_selectors`: required non-empty selector list. Selectors are tried in order using optional
  click semantics: missing selectors are skipped, click failures are logged and the next selector is
  tried.

This field is optional. A playbook without `overlays` keeps normal step behavior but gets no
site-specific popup handling.

## Runner Behavior

Replace the site-specific `_KNOWN_OVERLAY_*` mechanism with a generic configured overlay dismiss
engine:

- Parse `playbook_body.overlays` once for the run.
- Before relevant interaction actions, call `dismiss_configured_overlays(page, overlays)`.
- For each overlay, check visible markers first.
- If a marker is visible, try configured close selectors in order.
- If one close selector clicks successfully, wait briefly and continue.
- If no close selector works, log the overlay id and continue to the main action. The main action
  remains responsible for failing if the page is still blocked.

Interaction actions that should dismiss overlays:

- `click`
- `download`
- `set_date`
- `select_checkboxes`
- `download_history_file` before opening history, refreshing/reopening history, and clicking the
  final download button
- `download_qianniu_export_report` before refresh clicks and final download clicks

`wait_for` should not dismiss overlays because it is an observation step, not an interaction step.

## Migration

Remove runner hardcoding for QianNiu popups, including warning notices, driver/newbie guidance, and
the finance survey popup.

Migrate existing active browser playbooks by adding top-level overlays:

- Store-order playbooks should include QianNiu warning and guide overlays that previously lived in
  code.
- Bill-detail playbooks should include the same QianNiu overlays plus the finance survey overlay:
  `.aes-survey-hanging`, `[class*='aes-survey-hanging']`,
  `.aes-survey-hanging--close`, and `[class*='aes-survey-hanging--close']`.

Update both local PostgreSQL and ECS/RDS playbooks. Remove any obsolete step-level
`overlay_close_selectors` fields if present.

## Project Memory

Add a browser collection preference to `AGENTS.md`:

When browser collection pages change or a new page collection is added, prefer modifying or adding
playbooks. Change Python only when a reusable runner capability is missing. Site-specific selectors
belong in playbooks, not in the runner.

## Tests

Add focused automated coverage:

- `finance-mcp` schema accepts top-level `overlays`.
- Browser-agent action contract accepts playbooks with top-level `overlays`.
- Configured overlay dismissal skips missing markers.
- Configured overlay dismissal clicks the first available close selector when a marker is visible.
- Configured overlay dismissal logs and continues when close selectors fail.
- Existing click retry behavior calls configured overlay dismissal before retrying.
- `download_history_file` uses configured overlay dismissal before its internal open/refresh/final
  download clicks.
- Regression fixtures prove QianNiu warning, guide, and finance survey popups are represented by
  playbook overlays rather than runner constants.

## Production Verification

After code and playbook migration are complete, make the browser-agent use the new code by the
operator-approved restart or deployment path. Do not restart automatically.

Then rerun only the two failed funding reconciliation tasks from today:

- `abgame旗舰店资金对账`
- `履冰旗舰店资金对账`

Success criteria:

- Browser collection reaches the bill-detail download stage.
- Popups configured in playbook overlays are dismissed when present.
- Bill-detail files download successfully.
- The two funding reconciliation tasks no longer fail because a popup blocked detail download.

