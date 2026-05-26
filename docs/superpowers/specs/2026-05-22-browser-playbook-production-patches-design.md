# Browser Playbook Production Patches Design

Date: 2026-05-22

## Context

The first real browser playbook targets QianNiu / Tmall Seller Center:

- Page: `https://myseller.taobao.com/home.htm/whale-accountant/bill/summary?billType=day&billDirection=income`
- Dataset: income bill daily summary detail, business category `交易货款`
- Real UI flow: set `biz_date` as start/end date, search summary, click `下载明细`, open `历史下载记录`, wait for the matching row to become `已完成`, then click `下载`.
- Real downloaded file: CSV, encoded as GB18030, with Chinese headers and long numeric identifiers such as `订单号`, `子订单号`, and `业务流水号`.

The UI must keep credentials separate from playbook JSON. Operators paste the playbook body into the playbook JSON field and enter login account/password in separate UI fields. The playbook references credentials through `params.login_username` and `params.login_password`; it must not contain plaintext credentials.

## Goals

1. Parse QianNiu CSV files reliably without corrupting long IDs.
2. Make saved browser credentials available to `login_if_needed` at runtime without putting secrets in playbooks or logs.
3. Add a dedicated runner action for QianNiu-style asynchronous history downloads, so the runner downloads the file for the requested `biz_date` instead of accidentally clicking an old completed record.

## Non-Goals

- Do not expose credential fields inside the playbook JSON editor.
- Do not implement a general browser scripting DSL.
- Do not bypass or weaken the existing login-state rule: every browser run checks profile login state first; if authenticated, skip login, otherwise login and continue.
- Do not change finance-web registration UX in this patch unless tests reveal a mismatch with the existing API contract.

## Design

### 1. CSV Parsing

Update `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`.

For `parse_table` with `format="csv"`:

- Try encodings in order: `utf-8-sig`, `gb18030`, `gbk`.
- Read CSV with `dtype=str` so long numeric IDs remain exact strings.
- Keep empty values as `""`.
- Do not convert amounts at parse time. Quality gates already convert amount fields through Decimal logic.
- Save detected encoding into the latest `capture_files` entry when available.

This preserves fields such as `业务流水号` and `订单号` for item key generation.

### 2. Credential Injection

Keep playbook JSON clean:

```json
{
  "action": "login_if_needed",
  "username_value_from": "params.login_username",
  "password_value_from": "params.login_password"
}
```

At runtime:

- Browser registration continues to save UI-provided login account/password into `credential_ref`.
- Before executing a playbook, browser-agent resolves `credential_ref` and injects:
  - `params.login_username`
  - `params.login_password`
- If those keys already exist in `params`, do not overwrite them. This keeps tests and manual runner use flexible.
- Do not log plaintext credentials.
- If credential resolution fails and login is required, return `AUTH_EXPIRED`.

Preferred implementation boundary: add a small helper in browser-agent, used by `dispatcher_loop._message_from_job` or immediately before `run_message`, so credential injection is local to the browser execution path.

### 3. Dedicated Async History Download Action

Add action type `download_history_file`.

Playbook step shape:

```json
{
  "id": "download_completed_file",
  "action": "download_history_file",
  "selector": ".HistoryDataLists--drawer-conent--3FJMg52 tr.next-table-row",
  "value_from": "params.biz_date",
  "download_timeout_ms": 600000,
  "timeout_ms": 900000
}
```

Runner behavior:

1. Resolve `target_date` from `value_from`.
2. Build accepted date tokens:
   - `YYYY-MM-DD`, for example `2026-05-21`
   - compact `YYYYMMDD`, for example `20260521`
3. Poll rows matched by `selector` until one row:
   - contains any accepted date token,
   - contains `已完成`,
   - contains a button with text `下载`.
4. Use `page.expect_download()` around the row-scoped `下载` button click.
5. Save the downloaded file into the existing job download directory and set `last_download`.
6. If no matching row completes before `timeout_ms`, fail with `PAGE_CHANGED`.

This keeps playbook JSON declarative while modeling the actual QianNiu async-download UI.

## Data Flow

1. Operator registers browser collection in UI:
   - title
   - login account
   - password
   - playbook JSON
2. Server stores credentials as `credential_ref`.
3. Browser-agent claims a job and receives `credential_ref`.
4. Browser-agent injects credentials into local execution params only.
5. Runner opens persistent Chrome profile.
6. Runner checks `auth_check.logged_in_selector`.
7. If already authenticated, skip `login_if_needed`.
8. If unauthenticated, execute login using injected credentials.
9. Runner executes date search, summary extraction, async history download, parse, and quality gate.

## Error Handling

- CSV cannot be decoded with all supported encodings: fail as `PAGE_CHANGED`.
- Missing required output columns: existing quality gate returns `PAGE_CHANGED`.
- Missing credentials when login is needed: `AUTH_EXPIRED`.
- Auth redirect or risk verification markers: existing `AUTH_EXPIRED` / `RISK_VERIFICATION`.
- History row for target date never reaches `已完成`: `PAGE_CHANGED`.
- Row count or amount mismatch: `DATA_MISMATCH`.

## Tests

Add or update tests in browser-agent and finance-mcp:

- CSV parser reads GB18030 CSV and preserves long IDs as strings.
- CSV parser falls back from UTF-8 to GB18030.
- Credential injection maps sealed `credential_ref` to `params.login_username/login_password` and does not overwrite explicit params.
- Plaintext credentials are not included in task result or logs tested at helper boundary.
- `download_history_file` selects the row matching `biz_date`, not an older completed row.
- `download_history_file` times out with `PAGE_CHANGED` when no matching completed row exists.
- Playbook schema accepts `download_history_file`.

## Production Validation

After implementation:

1. Register the QianNiu playbook in UI with login account/password in separate fields.
2. Run verification for a recent T-1 `biz_date`.
3. Confirm browser-agent:
   - skips login when profile is already authenticated,
   - logs in only when profile is unauthenticated,
   - downloads the matching history file,
   - parses GB18030 CSV,
   - preserves item keys,
   - passes exact row count and amount quality gates.
