# Browser Playbook Production Patches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the first QianNiu browser playbook production-runnable by adding safe CSV parsing, runtime credential injection, and a dedicated asynchronous history download action.

**Architecture:** Keep browser playbook JSON free of plaintext credentials. Extend the existing finance-mcp schema and browser-agent action whitelist for one new action, then implement runtime behavior inside the browser-agent runner and dispatcher. Keep changes scoped to browser playbook execution; do not change the finance-web registration UI.

**Tech Stack:** Python 3.12, Pydantic, pytest, pandas, Playwright sync API, existing `auth.crypto` secret format.

---

## File Structure

- Modify `finance-mcp/browser_playbook/models.py`
  - Add `download_history_file` to the validated action type.
  - Reuse existing `selector`, `value_from`, `timeout_ms`, and `download_timeout_ms` fields.
- Modify `finance-mcp/tests/test_browser_playbook_schema.py`
  - Add schema coverage for `download_history_file`.
- Modify `finance-agents/browser-agent/finance_browser_agent/playbook_interpreter.py`
  - Add `download_history_file` to runtime action validation.
- Modify `finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py`
  - Add whitelist coverage for `download_history_file`.
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
  - Add robust CSV parsing.
  - Add row-scoped `download_history_file` behavior.
  - Save detected encoding to the latest capture file.
- Modify `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`
  - Add unit tests for CSV parsing and `download_history_file` behavior using fakes.
- Create `finance-agents/browser-agent/finance_browser_agent/credentials.py`
  - Decode sealed `credential_ref` into runtime params.
  - Avoid logging or returning plaintext credentials.
- Create `finance-agents/browser-agent/tests/test_credentials.py`
  - Unit tests for credential injection.
- Modify `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
  - Apply credential injection before passing the message to the sync runner.
- Modify `finance-agents/browser-agent/tests/test_dispatcher_loop.py`
  - Verify dispatcher injects credentials and does not overwrite explicit params.

---

### Task 1: Schema And Action Whitelist

**Files:**
- Modify: `finance-mcp/browser_playbook/models.py`
- Modify: `finance-mcp/tests/test_browser_playbook_schema.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/playbook_interpreter.py`
- Modify: `finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py`

- [ ] **Step 1: Add failing schema test**

Append this test to `finance-mcp/tests/test_browser_playbook_schema.py`:

```python
def test_playbook_accepts_download_history_file_action() -> None:
    playbook = _valid_playbook_body()
    steps = playbook["steps"]  # type: ignore[index]
    assert isinstance(steps, list)
    steps[6] = {
        "id": "download_completed_file",
        "action": "download_history_file",
        "selector": ".HistoryDataLists--drawer-conent--3FJMg52 tr.next-table-row",
        "value_from": "params.biz_date",
        "download_timeout_ms": 600000,
        "timeout_ms": 900000,
    }

    msg = RunPlaybookMessage.model_validate(
        {
            "job_id": "job-001",
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily-bill-export",
            "playbook_version": "1.0.0",
            "playbook_body": playbook,
            "params": {"biz_date": "2026-05-18"},
            "runtime_profile_ref": "profiles/shop-001",
        }
    )

    assert msg.playbook_body.steps[6].action == "download_history_file"
```

- [ ] **Step 2: Run schema test and verify failure**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_schema.py::test_playbook_accepts_download_history_file_action -v
```

Expected: fail with validation error because `download_history_file` is not in `ActionType`.

- [ ] **Step 3: Update Pydantic action type**

In `finance-mcp/browser_playbook/models.py`, add `"download_history_file"` to `ActionType`:

```python
ActionType = Literal[
    "login",
    "login_if_needed",
    "navigate",
    "click",
    "fill",
    "set_date",
    "wait_for",
    "extract_text",
    "extract_summary",
    "download",
    "download_history_file",
    "parse_table",
    "assert",
]
```

Then update `PlaybookStep.validate_action_contract` so `download_history_file` requires a selector and a date source:

```python
        if self.action in {"click", "fill", "set_date", "wait_for", "extract_text", "download", "download_history_file"}:
            if not str(self.selector or "").strip():
                raise ValueError(f"{self.action} requires selector")
        if self.action == "download_history_file" and self.value_from != "params.biz_date":
            raise ValueError("download_history_file must use value_from=params.biz_date")
```

- [ ] **Step 4: Add failing interpreter whitelist test**

Append this to `finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py`:

```python
def test_playbook_interpreter_accepts_download_history_file_action() -> None:
    validate_step_actions([{"action": "download_history_file"}])
```

- [ ] **Step 5: Run interpreter test and verify failure**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py::test_playbook_interpreter_accepts_download_history_file_action -v
```

Expected: fail with `unsupported action: download_history_file`.

- [ ] **Step 6: Update browser-agent action whitelist**

In `finance-agents/browser-agent/finance_browser_agent/playbook_interpreter.py`, add the action:

```python
VALID_ACTIONS = {
    "login",
    "login_if_needed",
    "navigate",
    "click",
    "fill",
    "set_date",
    "wait_for",
    "extract_text",
    "extract_summary",
    "download",
    "download_history_file",
    "parse_table",
    "assert",
}
```

- [ ] **Step 7: Run Task 1 tests**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_schema.py::test_playbook_accepts_download_history_file_action finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py::test_playbook_interpreter_accepts_download_history_file_action -v
```

Expected: both tests pass.

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add finance-mcp/browser_playbook/models.py finance-mcp/tests/test_browser_playbook_schema.py finance-agents/browser-agent/finance_browser_agent/playbook_interpreter.py finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py
git commit -m "feat: allow browser history download action"
```

---

### Task 2: Robust CSV Parsing

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Modify: `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`

- [ ] **Step 1: Add failing GB18030 parser test**

Update the import block in `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py` to include `_parse_downloaded_table`:

```python
from finance_browser_agent.playwright_runner import (
    BrowserActionError,
    PlaywrightRunConfig,
    _execute_action,
    _parse_downloaded_table,
    _profile_is_authenticated,
    build_user_data_dir,
    sanitize_profile_key,
    should_skip_login_action,
)
```

Append this test:

```python
def test_parse_downloaded_csv_uses_gb18030_and_preserves_long_ids(tmp_path) -> None:
    path = tmp_path / "交易货款_20260521_20260521.csv"
    path.write_bytes(
        (
            "账期,业务流水号,订单号,订单实际金额（元）,打款时间\n"
            "20260521,2026052123001193261450560998,3302219424181023654,19.83,2026-05-21 22:32:44\\t\n"
        ).encode("gb18030")
    )

    rows = _parse_downloaded_table(path, fmt="csv")

    assert rows == [
        {
            "账期": "20260521",
            "业务流水号": "2026052123001193261450560998",
            "订单号": "3302219424181023654",
            "订单实际金额（元）": "19.83",
            "打款时间": "2026-05-21 22:32:44\t",
        }
    ]
```

- [ ] **Step 2: Run parser test and verify failure**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_parse_downloaded_csv_uses_gb18030_and_preserves_long_ids -v
```

Expected: fail because current parser uses default UTF-8 and default dtype.

- [ ] **Step 3: Implement encoding fallback helper**

In `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`, add this helper above `_parse_downloaded_table`:

```python
def _read_csv_with_fallback(path: Path) -> tuple[Any, str]:
    import pandas as pd

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(path, dtype=str, keep_default_na=False), ""
```

Update `_parse_downloaded_table`:

```python
def _parse_downloaded_table(path: Path, *, fmt: str) -> list[dict[str, Any]]:
    """Parse a downloaded CSV/XLSX file into a list of row dicts.

    pandas is lazy-imported because the synthetic test runner never needs it.
    """
    import pandas as pd

    if fmt == "xlsx":
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    else:
        df, _encoding = _read_csv_with_fallback(path)
    return [
        {str(k): ("" if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict("records")
    ]
```

- [ ] **Step 4: Add capture encoding test**

Append this test to `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`:

```python
def test_parse_table_records_detected_csv_encoding_in_capture_file(tmp_path) -> None:
    path = tmp_path / "交易货款_20260521_20260521.csv"
    path.write_bytes("账期,业务流水号\n20260521,2026052123001193261450560998\n".encode("gb18030"))
    capture_files = [{"storage_path": str(path), "encoding": "", "checksum": "", "row_count": 0}]

    result = _execute_action(
        FakePage(),
        {
            "id": "parse_detail_file",
            "action": "parse_table",
            "source": "last_download",
            "format": "csv",
        },
        params={},
        extracted={"last_download": str(path)},
        capture_files=capture_files,
        download_dir=tmp_path,
    )

    assert result["rows"][0]["业务流水号"] == "2026052123001193261450560998"
    assert capture_files[0]["encoding"] == "gb18030"
    assert capture_files[0]["row_count"] == 1
```

- [ ] **Step 5: Run capture encoding test and verify failure**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_parse_table_records_detected_csv_encoding_in_capture_file -v
```

Expected: fail because `_execute_action(parse_table)` does not update capture file encoding or row count yet.

- [ ] **Step 6: Update parse_table action to record encoding and row count**

Change `_parse_downloaded_table` to return rows plus encoding:

```python
def _parse_downloaded_table_with_metadata(path: Path, *, fmt: str) -> tuple[list[dict[str, Any]], str]:
    import pandas as pd

    if fmt == "xlsx":
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
        encoding = ""
    else:
        df, encoding = _read_csv_with_fallback(path)
    rows = [
        {str(k): ("" if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict("records")
    ]
    return rows, encoding


def _parse_downloaded_table(path: Path, *, fmt: str) -> list[dict[str, Any]]:
    rows, _encoding = _parse_downloaded_table_with_metadata(path, fmt=fmt)
    return rows
```

Update the `parse_table` branch:

```python
    if name == "parse_table":
        source = str(action.get("source") or "last_download")
        fmt = str(action.get("format") or "csv").lower()
        path = extracted.get(source) or capture_files[-1]["storage_path"]
        rows, encoding = _parse_downloaded_table_with_metadata(Path(str(path)), fmt=fmt)
        if capture_files:
            capture_files[-1]["encoding"] = encoding
            capture_files[-1]["row_count"] = len(rows)
        return {"rows": rows}
```

- [ ] **Step 7: Run Task 2 tests**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_parse_downloaded_csv_uses_gb18030_and_preserves_long_ids finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_parse_table_records_detected_csv_encoding_in_capture_file -v
```

Expected: both tests pass.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/tests/test_playwright_profile_login_state.py
git commit -m "fix: parse qianniu csv files safely"
```

---

### Task 3: Runtime Credential Injection

**Files:**
- Create: `finance-agents/browser-agent/finance_browser_agent/credentials.py`
- Create: `finance-agents/browser-agent/tests/test_credentials.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
- Modify: `finance-agents/browser-agent/tests/test_dispatcher_loop.py`

- [ ] **Step 1: Add credential helper tests**

Create `finance-agents/browser-agent/tests/test_credentials.py`:

```python
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.credentials import inject_credentials_into_params, open_credential_ref


def _fallback_ref(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "enc:fallback:v1:" + base64.urlsafe_b64encode(raw).decode("ascii")


def test_open_credential_ref_reads_sealed_json_payload() -> None:
    credential_ref = _fallback_ref({"username": "finance_ops", "password": "secret"})

    assert open_credential_ref(credential_ref) == {"username": "finance_ops", "password": "secret"}


def test_inject_credentials_into_params_adds_login_keys_without_overwriting() -> None:
    credential_ref = _fallback_ref({"username": "finance_ops", "password": "secret"})
    params = {"biz_date": "2026-05-21", "login_username": "manual"}

    result = inject_credentials_into_params(params, credential_ref)

    assert result == {
        "biz_date": "2026-05-21",
        "login_username": "manual",
        "login_password": "secret",
    }
    assert params == {"biz_date": "2026-05-21", "login_username": "manual"}


def test_inject_credentials_ignores_empty_ref() -> None:
    assert inject_credentials_into_params({"biz_date": "2026-05-21"}, "") == {
        "biz_date": "2026-05-21"
    }
```

- [ ] **Step 2: Run credential tests and verify failure**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_credentials.py -v
```

Expected: fail because `finance_browser_agent.credentials` does not exist.

- [ ] **Step 3: Implement credential helper**

Create `finance-agents/browser-agent/finance_browser_agent/credentials.py`:

```python
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PREFIX_V1 = "enc:v1:"
_PREFIX_FALLBACK = "enc:fallback:v1:"
_ENV_SECRET_KEY = "FINANCE_MCP_SECRET_KEY"


def _build_keystream(secret_key: str, length: int) -> bytes:
    seed = hashlib.sha256(secret_key.encode("utf-8")).digest()
    stream = bytearray()
    current = seed
    while len(stream) < length:
        current = hashlib.sha256(current + seed).digest()
        stream.extend(current)
    return bytes(stream[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _open_secret(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX_V1):
        payload = value[len(_PREFIX_V1):]
        secret_key = (os.getenv(_ENV_SECRET_KEY) or "").strip()
        if not secret_key:
            logger.error("credential_ref uses %s encryption but %s is not configured", _PREFIX_V1, _ENV_SECRET_KEY)
            return ""
        encrypted = base64.urlsafe_b64decode(payload.encode("ascii"))
        keystream = _build_keystream(secret_key, len(encrypted))
        return _xor_bytes(encrypted, keystream).decode("utf-8")
    if value.startswith(_PREFIX_FALLBACK):
        payload = value[len(_PREFIX_FALLBACK):]
        return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
    return value


def open_credential_ref(credential_ref: str) -> dict[str, Any]:
    raw = _open_secret(credential_ref).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.error("credential_ref is not valid JSON")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def inject_credentials_into_params(params: dict[str, Any], credential_ref: str) -> dict[str, Any]:
    merged = dict(params)
    credentials = open_credential_ref(credential_ref)
    username = str(credentials.get("username") or "")
    password = str(credentials.get("password") or "")
    if username and not str(merged.get("login_username") or ""):
        merged["login_username"] = username
    if password and not str(merged.get("login_password") or ""):
        merged["login_password"] = password
    return merged
```

- [ ] **Step 4: Add dispatcher injection test**

Append this test to `finance-agents/browser-agent/tests/test_dispatcher_loop.py`:

```python
def test_dispatcher_message_injects_credentials_without_overwriting() -> None:
    loop = BrowserDispatcherLoop(client=FakeClient([], {}), runner=lambda message: message, max_concurrency=1)
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "playbook_id": "qianniu-income-daily-goods-bill-detail",
        "playbook_version": "1.0.0",
        "playbook_body": {"steps": []},
        "runtime_profile_ref": "profile-001",
        "egress_group": "",
        "credential_ref": (
            "enc:fallback:v1:"
            "eyJwYXNzd29yZCI6ICJzZWNyZXQiLCAidXNlcm5hbWUiOiAiZmluYW5jZV9vcHMifQ=="
        ),
    }
    payload = {
        "params": {
            "biz_date": "2026-05-21",
            "login_username": "manual_user",
        }
    }

    message = loop._message_from_job(job, payload)

    assert message["params"]["login_username"] == "manual_user"
    assert message["params"]["login_password"] == "secret"
```

- [ ] **Step 5: Run dispatcher injection test and verify failure**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_dispatcher_loop.py::test_dispatcher_message_injects_credentials_without_overwriting -v
```

Expected: fail because dispatcher does not inject credentials.

- [ ] **Step 6: Wire credential injection into dispatcher**

In `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`, add import:

```python
from finance_browser_agent.credentials import inject_credentials_into_params
```

Update `_message_from_job`:

```python
    def _message_from_job(self, job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload.get("params") or payload)
        credential_ref = str(job.get("credential_ref") or "")
        params = inject_credentials_into_params(params, credential_ref)
        return {
            "job_id": str(job.get("id") or ""),
            "shop_id": str(job.get("shop_id") or ""),
            "playbook_id": str(job.get("playbook_id") or ""),
            "playbook_version": str(job.get("playbook_version") or ""),
            "playbook_body": dict(job.get("playbook_body") or {}),
            "params": params,
            "runtime_profile_ref": str(job.get("runtime_profile_ref") or ""),
            "egress_group": str(job.get("egress_group") or ""),
            "credential_ref": credential_ref,
            "timeout_ms": int(params.get("timeout_ms") or payload.get("timeout_ms") or 900000),
        }
```

- [ ] **Step 7: Run Task 3 tests**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_credentials.py finance-agents/browser-agent/tests/test_dispatcher_loop.py::test_dispatcher_message_injects_credentials_without_overwriting -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/credentials.py finance-agents/browser-agent/tests/test_credentials.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/tests/test_dispatcher_loop.py
git commit -m "fix: inject browser credentials at runtime"
```

---

### Task 4: Dedicated History Download Action

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Modify: `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`

- [ ] **Step 1: Add fake classes for history download**

Append these helpers to `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`:

```python
class FakeDownload:
    suggested_filename = "交易货款_20260521_20260521.csv"

    def __init__(self) -> None:
        self.saved_as = ""

    def save_as(self, path: str) -> None:
        self.saved_as = path
        Path(path).write_text("账期,业务流水号\n20260521,2026052123001193261450560998\n", encoding="utf-8")


class FakeDownloadInfo:
    def __init__(self, download: FakeDownload) -> None:
        self.value = download

    def __enter__(self) -> "FakeDownloadInfo":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeHistoryButton:
    def __init__(self, row: "FakeHistoryRow") -> None:
        self.row = row

    def click(self, *, timeout: int) -> None:
        self.row.clicked_timeout = timeout


class FakeHistoryRow:
    def __init__(self, text: str) -> None:
        self.text = text
        self.clicked_timeout: int | None = None

    def inner_text(self, *, timeout: int) -> str:
        return self.text

    def locator(self, selector: str) -> FakeHistoryButton:
        assert selector == "button:has-text('下载')"
        return FakeHistoryButton(self)


class FakeHistoryLocator:
    def __init__(self, rows: list[FakeHistoryRow]) -> None:
        self.rows = rows

    def count(self) -> int:
        return len(self.rows)

    def nth(self, index: int) -> FakeHistoryRow:
        return self.rows[index]


class FakeHistoryPage(FakePage):
    def __init__(self, rows: list[FakeHistoryRow]) -> None:
        super().__init__()
        self.rows = rows
        self.download = FakeDownload()

    def locator(self, selector: str) -> FakeHistoryLocator:
        assert selector == ".history tr"
        return FakeHistoryLocator(self.rows)

    def wait_for_timeout(self, timeout: int) -> None:
        return None

    def expect_download(self, *, timeout: int) -> FakeDownloadInfo:
        return FakeDownloadInfo(self.download)
```

- [ ] **Step 2: Add failing successful history download test**

Append this test:

```python
def test_download_history_file_picks_matching_biz_date_row(tmp_path) -> None:
    old_row = FakeHistoryRow("2026-05-20 ~ 2026-05-20 交易货款 已完成 下载")
    target_row = FakeHistoryRow("2026-05-21 ~ 2026-05-21 交易货款 已完成 下载")
    page = FakeHistoryPage([old_row, target_row])
    capture_files: list[dict[str, object]] = []

    result = _execute_action(
        page,
        {
            "id": "download_completed_file",
            "action": "download_history_file",
            "selector": ".history tr",
            "value_from": "params.biz_date",
            "download_timeout_ms": 600000,
            "timeout_ms": 900000,
        },
        params={"biz_date": "2026-05-21"},
        extracted={},
        capture_files=capture_files,
        download_dir=tmp_path,
    )

    assert result["last_download"].endswith("交易货款_20260521_20260521.csv")
    assert old_row.clicked_timeout is None
    assert target_row.clicked_timeout == 900000
    assert capture_files[0]["storage_path"] == result["last_download"]
```

- [ ] **Step 3: Run history download success test and verify failure**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_download_history_file_picks_matching_biz_date_row -v
```

Expected: fail with unsupported action.

- [ ] **Step 4: Implement date token and history download helpers**

In `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`, add these helpers above `_execute_action`:

```python
def _date_tokens(value: str) -> set[str]:
    text = str(value or "").strip()
    tokens = {text} if text else set()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        tokens.add(text.replace("-", ""))
    if len(text) == 8 and text.isdigit():
        tokens.add(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
    return {token for token in tokens if token}


def _download_history_file(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    capture_files: list[dict[str, Any]],
    download_dir: Path,
    timeout_ms: int,
) -> dict[str, Any]:
    selector = str(action.get("selector") or "").strip()
    target_date = _resolve_value(action, params, extracted)
    tokens = _date_tokens(target_date)
    if not selector or not tokens:
        raise BrowserActionError("PAGE_CHANGED", "download_history_file requires selector and target date")

    deadline = __import__("time").monotonic() + (timeout_ms / 1000)
    row = None
    while __import__("time").monotonic() <= deadline:
        rows = page.locator(selector)
        for index in range(rows.count()):
            candidate = rows.nth(index)
            text = candidate.inner_text(timeout=min(timeout_ms, 5000))
            compact_text = " ".join(str(text or "").split())
            if any(token in compact_text for token in tokens) and "已完成" in compact_text and "下载" in compact_text:
                row = candidate
                break
        if row is not None:
            break
        page.wait_for_timeout(2000)

    if row is None:
        raise BrowserActionError("PAGE_CHANGED", f"history download row not completed for {target_date}")

    with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
        row.locator("button:has-text('下载')").click(timeout=timeout_ms)
    download = info.value
    target = download_dir / (download.suggested_filename or "download.bin")
    download.save_as(str(target))
    capture_files.append({"storage_path": str(target), "encoding": "", "checksum": "", "row_count": 0})
    return {"last_download": str(target)}
```

Add this branch in `_execute_action` immediately after the existing `download` branch:

```python
    if name == "download_history_file":
        return _download_history_file(
            page,
            action,
            params=params,
            extracted=extracted,
            capture_files=capture_files,
            download_dir=download_dir,
            timeout_ms=timeout_ms,
        )
```

- [ ] **Step 5: Add failing timeout test**

Append this test:

```python
def test_download_history_file_times_out_without_matching_completed_row(tmp_path) -> None:
    page = FakeHistoryPage([FakeHistoryRow("2026-05-20 ~ 2026-05-20 交易货款 已完成 下载")])

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "id": "download_completed_file",
                "action": "download_history_file",
                "selector": ".history tr",
                "value_from": "params.biz_date",
                "timeout_ms": 1,
            },
            params={"biz_date": "2026-05-21"},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
        )

    assert exc.value.fail_reason == "PAGE_CHANGED"
```

- [ ] **Step 6: Run Task 4 tests**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_download_history_file_picks_matching_biz_date_row finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_download_history_file_times_out_without_matching_completed_row -v
```

Expected: both tests pass.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/tests/test_playwright_profile_login_state.py
git commit -m "feat: download completed browser history files"
```

---

### Task 5: Integration Verification

**Files:**
- No new files.

- [ ] **Step 1: Run browser-agent targeted tests**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py finance-agents/browser-agent/tests/test_dispatcher_loop.py finance-agents/browser-agent/tests/test_credentials.py -v
```

Expected: all selected browser-agent tests pass.

- [ ] **Step 2: Run finance-mcp browser schema tests**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_schema.py -v
```

Expected: all schema tests pass.

- [ ] **Step 3: Run full browser-related Python tests**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_schema.py finance-mcp/tests/test_browser_playbook_connector.py finance-mcp/tests/test_browser_dispatcher.py finance-mcp/tests/test_browser_first_store_e2e.py finance-mcp/tests/test_browser_playbook_source_less_registration.py finance-agents/browser-agent/tests -v
```

Expected: all tests pass or any environment-only skips remain skips.

- [ ] **Step 4: Restart services**

Run:

```bash
./START_ALL_SERVICES.sh
```

Expected: services restart successfully.

- [ ] **Step 5: Health check**

Run:

```bash
curl -s http://127.0.0.1:3335/health
curl -s http://127.0.0.1:8100/health
curl -I http://127.0.0.1:5173
```

Expected: finance-mcp and data-agent return healthy JSON; finance-web returns HTTP 200 or 3xx.

- [ ] **Step 6: Final commit if verification required changes**

If Task 5 required fixes, commit them:

```bash
git add finance-mcp/browser_playbook/models.py finance-mcp/tests/test_browser_playbook_schema.py finance-agents/browser-agent/finance_browser_agent/playbook_interpreter.py finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/tests/test_playwright_profile_login_state.py finance-agents/browser-agent/finance_browser_agent/credentials.py finance-agents/browser-agent/tests/test_credentials.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/tests/test_dispatcher_loop.py
git commit -m "fix: stabilize browser playbook production flow"
```

If Task 5 required no fixes, do not create an empty commit.

---

## Self-Review

- Spec coverage:
  - CSV GB18030 + long IDs: Task 2.
  - Credential injection: Task 3.
  - Dedicated async history download action: Tasks 1 and 4.
  - Production validation: Task 5.
- Red-flag scan: no unresolved markers remain.
- Type consistency:
  - `download_history_file` is added to finance-mcp schema and browser-agent whitelist.
  - Runtime step uses existing `selector`, `value_from`, `timeout_ms`, and `download_timeout_ms`.
  - Credential helper exposes `open_credential_ref` and `inject_credentials_into_params`; dispatcher uses only the injection helper.
