"""Real Playwright runner for v1 browser playbook actions against QianNiu.

Replaces the synthetic-row runner when ``BROWSER_AGENT_RUNNER_MODE=playwright`` is set. Uses
``playwright.sync_api.sync_playwright`` because the rest of the dispatcher loop already wraps
the call in ``asyncio.to_thread`` (see ``dispatcher_loop.py``); going async-Playwright would
add no benefit and complicate persistent-context handling.

Persistent profile: each shop binds to a directory under ``profile_root``. First-store QianNiu
collection should use the locally installed Google Chrome Stable channel in headed mode, not
Playwright's bundled Chromium, to stay close to a normal merchant browser session.

Fail-reason mapping:
- selector timeout / not found → PAGE_CHANGED
- login redirect or auth-required body → AUTH_EXPIRED
- risk-verification keywords visible (验证 / 滑块 / 安全校验) → RISK_VERIFICATION
- quality gate mismatch → DATA_MISMATCH
- anything else → OTHER (retryable)

Exact-match Layer 2 quality gate is delegated to ``finance_browser_agent.quality_gate``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_browser_agent.quality_gate import validate_rows

logger = logging.getLogger(__name__)


_AUTH_REDIRECT_MARKERS = (
    "login.taobao.com",
    "passport",
    "请先登录",
    "登录后继续",
)
_RISK_MARKERS = (
    "验证",
    "滑块",
    "安全校验",
    "verify",
    "captcha",
)


@dataclass(frozen=True)
class PlaywrightRunConfig:
    profile_root: str
    download_root: str
    headless: bool
    timezone_id: str
    browser_channel: str

    @classmethod
    def from_env(cls) -> "PlaywrightRunConfig":
        default_root = Path.home() / "tally-browser-agent"
        return cls(
            profile_root=os.getenv("BROWSER_AGENT_PROFILE_ROOT", str(default_root / "profiles")),
            download_root=os.getenv("BROWSER_AGENT_DOWNLOAD_ROOT", str(default_root / "downloads")),
            headless=os.getenv("BROWSER_AGENT_HEADLESS", "0") == "1",
            timezone_id=os.getenv("BROWSER_AGENT_TIMEZONE", "Asia/Shanghai"),
            browser_channel=os.getenv("BROWSER_AGENT_BROWSER_CHANNEL", "chrome").strip() or "chrome",
        )


def build_user_data_dir(
    *,
    config: PlaywrightRunConfig,
    shop_id: str,
    runtime_profile_ref: str = "",
) -> str:
    """Compose the persistent Chrome user-data-dir for one browser profile.

    Sanitizes the profile key to alphanumerics and ``- _`` so a malicious or malformed key can't
    escape the profile_root (no ../ traversal, no path separators).
    """
    raw_key = str(runtime_profile_ref or shop_id or "unknown")
    return str(Path(config.profile_root) / sanitize_profile_key(raw_key))


def sanitize_profile_key(value: str) -> str:
    """Return the shared browser profile key used for profile paths and locks."""
    safe = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in {"-", "_"})
    return safe or "unknown"


def should_skip_login_action(action: dict[str, Any], *, authenticated: bool) -> bool:
    return authenticated and str(action.get("action") or "").strip() in {"login", "login_if_needed"}


def _detect_auth_or_risk(page: Any) -> str | None:
    """Inspect the current page for login redirect or risk verification markers."""
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if any(marker in url for marker in ("login.taobao.com", "passport")):
        return "AUTH_EXPIRED"
    try:
        body = page.content() or ""
    except Exception:
        body = ""
    lowered = body.lower()
    if any(marker in body or marker in lowered for marker in _AUTH_REDIRECT_MARKERS):
        return "AUTH_EXPIRED"
    if any(marker in body or marker in lowered for marker in _RISK_MARKERS):
        return "RISK_VERIFICATION"
    return None


def _profile_is_authenticated(page: Any, playbook: dict[str, Any]) -> bool:
    """Detect whether the opened persistent profile already has a valid login state."""
    auth_check = dict(playbook.get("auth_check") or {})
    logged_in_selector = str(auth_check.get("logged_in_selector") or "").strip()
    timeout_ms = int(auth_check.get("timeout_ms") or 5000)
    if logged_in_selector:
        try:
            page.wait_for_selector(logged_in_selector, timeout=timeout_ms)
            return True
        except Exception:
            return False
    return False


def _resolve_value(action: dict[str, Any], params: dict[str, Any], extracted: dict[str, Any]) -> str:
    """Resolve ``value`` from a step:

    - ``value_from='params.biz_date'`` → params["biz_date"]
    - ``value_from='extracted.row_count'`` → extracted["row_count"]
    - ``value=<literal>`` → literal
    """
    value_from = str(action.get("value_from") or "").strip()
    if value_from:
        if "." not in value_from:
            return ""
        scope, key = value_from.split(".", 1)
        if scope == "params":
            return str(params.get(key.strip()) or "")
        if scope == "extracted":
            return str(extracted.get(key.strip()) or "")
        return ""
    return str(action.get("value") or "")


def _execute_action(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    capture_files: list[dict[str, Any]],
    download_dir: Path,
) -> dict[str, Any]:
    """Execute one step. Returns a dict with ``rows`` (when parse_table) or empty dict.

    Raises a ``BrowserActionError`` with a ``fail_reason`` attribute on selector/auth/risk
    failure so the outer loop maps it to the right TASK_RESULT shape.
    """
    name = str(action.get("action") or "").strip()
    selector = str(action.get("selector") or "").strip()
    timeout_ms = int(action.get("timeout_ms") or 30000)

    if name == "navigate":
        page.goto(str(action.get("url") or ""), wait_until="load", timeout=timeout_ms)
        detected = _detect_auth_or_risk(page)
        if detected:
            raise BrowserActionError(detected, f"navigate detected {detected}")
        return {}
    if name == "click":
        page.click(selector, timeout=timeout_ms)
        return {}
    if name == "fill":
        page.fill(selector, _resolve_value(action, params, extracted), timeout=timeout_ms)
        return {}
    if name == "set_date":
        page.fill(selector, _resolve_value(action, params, extracted), timeout=timeout_ms)
        return {}
    if name == "wait_for":
        page.wait_for_selector(selector, timeout=timeout_ms)
        return {}
    if name in {"login", "login_if_needed"}:
        _execute_login_action(page, action, params=params, extracted=extracted, timeout_ms=timeout_ms)
        return {}
    if name == "extract_text":
        text = page.locator(selector).first.inner_text(timeout=timeout_ms)
        extracted[str(action.get("id") or selector)] = text.strip()
        return {}
    if name == "extract_summary":
        mapping = dict(action.get("mapping") or {})
        for key, css in mapping.items():
            text = page.locator(str(css)).first.inner_text(timeout=timeout_ms)
            extracted[str(key)] = text.strip()
        return {}
    if name == "download":
        with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
            page.click(selector, timeout=timeout_ms)
        download = info.value
        target = download_dir / (download.suggested_filename or "download.bin")
        download.save_as(str(target))
        capture_files.append(
            {
                "storage_path": str(target),
                "encoding": "",
                "checksum": "",
                "row_count": 0,
            }
        )
        return {"last_download": str(target)}
    if name == "parse_table":
        source = str(action.get("source") or "last_download")
        fmt = str(action.get("format") or "csv").lower()
        path = extracted.get(source) or capture_files[-1]["storage_path"]
        rows = _parse_downloaded_table(Path(str(path)), fmt=fmt)
        return {"rows": rows}
    if name == "assert":
        target = _resolve_value(action, params, extracted)
        expected = str(action.get("equals") or "")
        if expected and target != expected:
            raise BrowserActionError("DATA_MISMATCH", f"assert failed: {target} != {expected}")
        return {}
    raise BrowserActionError("OTHER", f"unsupported action: {name}")


def _login_value(
    action: dict[str, Any],
    *,
    field: str,
    params: dict[str, Any],
    extracted: dict[str, Any],
) -> str:
    value_from_key = f"{field}_from"
    if value_from_key in action:
        return _resolve_value(
            {"value_from": action.get(value_from_key)},
            params,
            extracted,
        )
    return _resolve_value(
        {"value": action.get(field)},
        params,
        extracted,
    )


def _execute_login_action(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    timeout_ms: int,
) -> None:
    username_selector = str(action.get("username_selector") or "").strip()
    password_selector = str(action.get("password_selector") or "").strip()
    submit_selector = str(action.get("submit_selector") or "").strip()
    if not username_selector or not password_selector or not submit_selector:
        raise BrowserActionError(
            "PAGE_CHANGED",
            "login action requires username/password/submit selectors",
        )

    page.fill(
        username_selector,
        _login_value(action, field="username_value", params=params, extracted=extracted),
        timeout=timeout_ms,
    )
    page.fill(
        password_selector,
        _login_value(action, field="password_value", params=params, extracted=extracted),
        timeout=timeout_ms,
    )
    page.click(submit_selector, timeout=timeout_ms)
    post_login_wait_selector = str(action.get("post_login_wait_selector") or "").strip()
    if post_login_wait_selector:
        page.wait_for_selector(post_login_wait_selector, timeout=timeout_ms)


class BrowserActionError(Exception):
    def __init__(self, fail_reason: str, message: str) -> None:
        super().__init__(message)
        self.fail_reason = fail_reason


def _parse_downloaded_table(path: Path, *, fmt: str) -> list[dict[str, Any]]:
    """Parse a downloaded CSV/XLSX file into a list of row dicts.

    pandas is lazy-imported because the synthetic test runner never needs it.
    """
    import pandas as pd

    if fmt == "xlsx":
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    return [
        {str(k): ("" if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict("records")
    ]


def run_playbook_with_playwright(
    message: dict[str, Any],
    *,
    config: PlaywrightRunConfig | None = None,
) -> dict[str, Any]:
    """Execute a v1 browser playbook against real pages via persistent-context Chrome.

    Returns the same TASK_RESULT shape as ``runner.run_message``: success → records + capture
    files + quality_summary; failure → fail_reason + error_info.
    """
    config = config or PlaywrightRunConfig.from_env()
    playbook = dict(message.get("playbook_body") or {})
    params = dict(message.get("params") or {})
    shop_id = str(message.get("shop_id") or params.get("shop_id") or "unknown")
    runtime_profile_ref = str(message.get("runtime_profile_ref") or "")
    job_id = str(message.get("job_id") or "unknown")

    user_data_dir = build_user_data_dir(
        config=config,
        shop_id=shop_id,
        runtime_profile_ref=runtime_profile_ref,
    )
    download_dir = Path(config.download_root) / shop_id / job_id
    download_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    rows: list[dict[str, Any]] = []
    capture_files: list[dict[str, Any]] = []
    extracted: dict[str, Any] = {}

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=config.headless,
                channel=config.browser_channel,
                accept_downloads=True,
                timezone_id=config.timezone_id,
                downloads_path=str(download_dir),
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                for step in playbook.get("steps") or []:
                    step_dict = dict(step)
                    step_action = str(step_dict.get("action") or "").strip()
                    if step_action in {"login", "login_if_needed"}:
                        authenticated = _profile_is_authenticated(page, playbook)
                        if should_skip_login_action(step_dict, authenticated=authenticated):
                            continue
                    result = _execute_action(
                        page,
                        step_dict,
                        params=params,
                        extracted=extracted,
                        capture_files=capture_files,
                        download_dir=download_dir,
                    )
                    if result.get("rows"):
                        rows.extend(result["rows"])
            finally:
                context.close()
    except BrowserActionError as exc:
        return {
            "job_id": job_id,
            "status": "failed",
            "fail_reason": exc.fail_reason,
            "error_info": {"message": str(exc)},
        }
    except PlaywrightTimeoutError as exc:
        return {
            "job_id": job_id,
            "status": "failed",
            "fail_reason": "PAGE_CHANGED",
            "error_info": {"message": str(exc)},
        }
    except Exception as exc:
        logger.exception("playwright runner crashed")
        return {
            "job_id": job_id,
            "status": "failed",
            "fail_reason": "OTHER",
            "error_info": {"message": str(exc)},
        }

    output = dict(playbook.get("output") or {})
    quality_gate = dict(playbook.get("quality_gate") or {})
    summary_step_id = str(quality_gate.get("summary_step_id") or "")
    summary_row_count = extracted.get(str(quality_gate.get("row_count_field") or "row_count"))
    summary_amount_total = extracted.get(str(quality_gate.get("amount_total_field") or "amount_total"))
    quality = validate_rows(
        rows=rows,
        columns=list(output.get("columns") or []),
        item_key_fields=list(output.get("item_key_fields") or []),
        amount_field=str(quality_gate.get("amount_field") or "amount"),
        date_field=str(quality_gate.get("date_field") or "biz_date"),
        biz_date=str(params.get("biz_date") or ""),
        expected_row_count=summary_row_count if summary_step_id else params.get("expected_row_count"),
        expected_amount_total=summary_amount_total if summary_step_id else params.get("expected_amount_total"),
    )
    if not quality.get("success"):
        return {
            "job_id": job_id,
            "status": "failed",
            "fail_reason": quality.get("fail_reason") or "DATA_MISMATCH",
            "error_info": {"message": quality.get("error") or "quality gate failed"},
        }

    item_key_fields = list(output.get("item_key_fields") or [])
    records = []
    for row in rows:
        item_key_values = {field: row.get(field) for field in item_key_fields}
        records.append(
            {
                "item_key": "|".join(str(item_key_values.get(field) or "") for field in item_key_fields),
                "item_key_values": item_key_values,
                "payload": row,
            }
        )
    return {
        "job_id": job_id,
        "status": "success",
        "records": records,
        "capture_files": capture_files,
        "quality_summary": quality["summary"],
    }
