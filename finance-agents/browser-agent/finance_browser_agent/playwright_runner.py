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
- newly requested export report not yet downloadable → EXPORT_REPORT_NOT_READY
- anything else → OTHER (retryable)

Exact-match Layer 2 quality gate is delegated to ``finance_browser_agent.quality_gate``.
"""

from __future__ import annotations

import asyncio
import contextvars
import contextlib
import json
import logging
import os
import random
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from finance_browser_agent.chrome_launcher import launch_chrome
from finance_browser_agent.playbook_interpreter import validate_step_actions
from finance_browser_agent.quality_gate import validate_rows
from finance_browser_agent.remote_control import PlaywrightControlBackend, RemoteControlCoordinator
from finance_browser_agent.storage_client import upload_capture_file_if_configured
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

_risk_waiting_cb: contextvars.ContextVar = contextvars.ContextVar("risk_waiting_cb", default=None)


def _notify_risk_waiting(reason: str = "RISK_VERIFICATION") -> None:
    cb = _risk_waiting_cb.get()
    if cb:
        try:
            cb(str(reason or "RISK_VERIFICATION"))
        except Exception:
            logger.exception("on_risk_waiting callback failed")


_AUTH_REDIRECT_MARKERS = (
    "请先登录",
    "登录后继续",
)
_RISK_MARKERS = (
    "验证码",
    "请完成下列验证",
    "滑块",
    "拖动滑块",
    "拖动完成",
    "拖动完成上方拼图",
    "完成拼图",
    "滑动验证",
    "向右滑动验证",
    "安全校验",
    "安全验证",
    "身份验证",
    "手机验证",
    "verify",
    "captcha",
    "risk",
)
_STRONG_RISK_MARKERS = (
    "请完成下列验证",
    "滑块",
    "拖动滑块",
    "拖动完成",
    "拖动完成上方拼图",
    "完成拼图",
    "滑动验证",
    "向右滑动验证",
    "安全校验",
    "安全验证",
    "身份验证",
    "手机验证",
    "captcha",
)
_DEFAULT_PASSWORD_LOGIN_SELECTORS = (
    "text=密码登录",
    "text=账号密码登录",
    "text=账户密码登录",
    "text=使用密码登录",
    "text=账号登录",
    ".password-login",
    ".login-switch",
)
_LOGIN_SELECTOR_ATTEMPT_TIMEOUT_MS = 1000


@dataclass(frozen=True)
class PlaywrightRunConfig:
    profile_root: str
    download_root: str
    headless: bool
    timezone_id: str
    browser_channel: str
    window_width: int = 1600
    window_height: int = 1000
    window_x: int = 0
    window_y: int = 0
    step_delay_min_ms: int = 1000
    step_delay_max_ms: int = 3000
    click_delay_min_ms: int = 800
    click_delay_max_ms: int = 1800
    type_delay_ms: int = 160
    risk_manual_timeout_ms: int = 900000

    @classmethod
    def from_env(cls) -> "PlaywrightRunConfig":
        default_root = Path.home() / "tally-browser-agent"
        return cls(
            profile_root=os.getenv("BROWSER_AGENT_PROFILE_ROOT", str(default_root / "profiles")),
            download_root=os.getenv("BROWSER_AGENT_DOWNLOAD_ROOT", str(default_root / "downloads")),
            headless=os.getenv("BROWSER_AGENT_HEADLESS", "0") == "1",
            timezone_id=os.getenv("BROWSER_AGENT_TIMEZONE", "Asia/Shanghai"),
            browser_channel=os.getenv("BROWSER_AGENT_BROWSER_CHANNEL", "chrome").strip() or "chrome",
            window_width=_env_int("BROWSER_AGENT_CHROME_WINDOW_WIDTH", 1600),
            window_height=_env_int("BROWSER_AGENT_CHROME_WINDOW_HEIGHT", 1000),
            window_x=_env_int("BROWSER_AGENT_CHROME_WINDOW_X", 0),
            window_y=_env_int("BROWSER_AGENT_CHROME_WINDOW_Y", 0),
            step_delay_min_ms=_env_int("BROWSER_AGENT_STEP_DELAY_MIN_MS", 1000),
            step_delay_max_ms=_env_int("BROWSER_AGENT_STEP_DELAY_MAX_MS", 3000),
            click_delay_min_ms=_env_int("BROWSER_AGENT_CLICK_DELAY_MIN_MS", 800),
            click_delay_max_ms=_env_int("BROWSER_AGENT_CLICK_DELAY_MAX_MS", 1800),
            type_delay_ms=_env_int("BROWSER_AGENT_TYPE_DELAY_MS", 160),
            risk_manual_timeout_ms=_env_int("BROWSER_AGENT_RISK_MANUAL_TIMEOUT_MS", 900000),
        )


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _set_browser_window_bounds(page: Any, config: PlaywrightRunConfig) -> None:
    if config.headless or config.window_width <= 0 or config.window_height <= 0:
        return
    try:
        session = page.context.new_cdp_session(page)
        window_info = session.send("Browser.getWindowForTarget")
        window_id = int(window_info.get("windowId"))
        session.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "left": max(0, int(config.window_x)),
                    "top": max(0, int(config.window_y)),
                    "width": int(config.window_width),
                    "height": int(config.window_height),
                    "windowState": "normal",
                },
            },
        )
        logger.info(
            "browser window bounds applied: window_id=%s width=%s height=%s x=%s y=%s",
            window_id,
            config.window_width,
            config.window_height,
            config.window_x,
            config.window_y,
        )
    except Exception:
        logger.exception("browser window bounds update failed")


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


@contextlib.contextmanager
def _profile_file_lock(user_data_dir: str):
    """Serialize access to one Chrome user-data-dir across browser-agent processes."""
    profile_path = Path(user_data_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    lock_path = profile_path.with_suffix(profile_path.suffix + ".lock")
    with lock_path.open("a+") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def sanitize_profile_key(value: str) -> str:
    """Return the shared browser profile key used for profile paths and locks."""
    safe = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in {"-", "_"})
    return safe or "unknown"


def should_skip_login_action(action: dict[str, Any], *, authenticated: bool) -> bool:
    return authenticated and str(action.get("action") or "").strip() in {"login", "login_if_needed"}


def _detect_auth_or_risk(page: Any) -> str | None:
    """Inspect the current page for login redirect or risk verification markers.

    Risk is judged from the user-VISIBLE text only. Scanning the full page HTML produced false
    positives: vendor risk-control SDKs embed words like ``risk``/``captcha``/``verify`` in
    scripts and markup on perfectly normal pages (JD's daily-bill page tripped on a bare
    ``risk`` substring every navigate), wrongly flagging RISK_VERIFICATION when no challenge was
    shown. We give inner_text a generous timeout so visible text is reliably available, and never
    fall back to raw HTML for risk markers.
    """
    risk_text = ""
    try:
        locator_factory = getattr(page, "locator", None)
        if callable(locator_factory):
            risk_text = locator_factory("body").first.inner_text(timeout=2000) or ""
    except Exception:
        risk_text = ""
    lowered_risk_text = risk_text.lower()
    matched = next((marker for marker in _STRONG_RISK_MARKERS if marker in risk_text), None)
    if matched:
        logger.info("browser risk verification detected (visible marker=%r)", matched)
        return "RISK_VERIFICATION"
    if "验证码" in risk_text and any(marker in risk_text for marker in ("请输入", "获取", "发送", "手机")):
        logger.info("browser risk verification detected (visible 验证码 prompt)")
        return "RISK_VERIFICATION"
    if "captcha" in lowered_risk_text:
        logger.info("browser risk verification detected (visible captcha)")
        return "RISK_VERIFICATION"
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if any(marker in url for marker in ("login.taobao.com", "passport")):
        return "AUTH_EXPIRED"
    if any(marker in risk_text for marker in _AUTH_REDIRECT_MARKERS):
        return "AUTH_EXPIRED"
    return None


def _page_url(page: Any) -> str:
    try:
        return str(page.url or "")
    except Exception:
        return ""


def _wait_for_transient_auth_redirect_to_clear(
    page: Any,
    *,
    timeout_ms: int,
    poll_interval_ms: int = 500,
) -> str | None:
    """QianNiu may briefly route through login/havana URLs even with a valid session."""
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    last_url = _page_url(page)
    while time.monotonic() <= deadline:
        detected = _detect_auth_or_risk(page)
        if detected != "AUTH_EXPIRED":
            if last_url:
                logger.info(
                    "browser transient auth redirect cleared: final_url=%s detected=%s",
                    _page_url(page),
                    detected or "none",
                )
            return detected
        last_url = _page_url(page)
        remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
        _wait_for_timeout(page, min(max(1, poll_interval_ms), remaining_ms))
    logger.info("browser transient auth redirect did not clear: final_url=%s", last_url)
    return "AUTH_EXPIRED"


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


def _profile_auth_check_diagnostics(page: Any, *, user_data_dir: str) -> dict[str, str]:
    return {
        "url": _page_url(page),
        "user_data_dir": str(user_data_dir or ""),
    }


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
    return _render_template(str(action.get("value") or ""), params=params, extracted=extracted)


def _resolve_action_url(
    action: dict[str, Any],
    *,
    key: str,
    params: dict[str, Any],
    extracted: dict[str, Any],
) -> str:
    value = action.get(key)
    if value is None:
        return ""
    return _render_template(str(value or ""), params=params, extracted=extracted).strip()


def _string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _page_text(page: Any) -> str:
    try:
        locator_factory = getattr(page, "locator", None)
        if callable(locator_factory):
            return str(locator_factory("body").first.inner_text(timeout=500) or "")
    except Exception:
        pass
    try:
        return str(page.content() or "")
    except Exception:
        return ""


def _contains_any_marker(value: str, markers: list[str]) -> bool:
    lowered = value.lower()
    return any(marker in value or marker.lower() in lowered for marker in markers)


def _page_has_configured_auth_markers(page: Any, action: dict[str, Any]) -> bool:
    url_markers = _string_items(action.get("auth_url_contains"))
    text_markers = _string_items(action.get("auth_text_contains"))
    if url_markers and _contains_any_marker(_page_url(page), url_markers):
        return True
    if text_markers and _contains_any_marker(_page_text(page), text_markers):
        return True
    return False


def _page_has_configured_error_markers(page: Any, action: dict[str, Any]) -> bool:
    return _contains_any_marker(_page_url(page), _string_items(action.get("error_url_contains")))


def _ready_selectors(action: dict[str, Any]) -> list[str]:
    selectors = _string_items(action.get("ready_selectors"))
    primary = str(action.get("ready_selector") or "").strip()
    if primary:
        selectors.insert(0, primary)
    deduped: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        if selector and selector not in seen:
            deduped.append(selector)
            seen.add(selector)
    return deduped


def _page_has_ready_selector(page: Any, selectors: list[str], *, timeout_ms: int) -> bool:
    for selector in selectors:
        candidates = _selector_candidates(selector)
        per_selector_timeout_ms = max(1, int(timeout_ms / max(1, len(candidates))))
        for candidate_selector in candidates:
            try:
                page.wait_for_selector(candidate_selector, timeout=per_selector_timeout_ms)
                return True
            except Exception:
                locator = _safe_first_locator(page, candidate_selector)
                if locator is not None and _locator_visible(locator, timeout_ms=per_selector_timeout_ms):
                    return True
    return False


def _selector_candidates(selector: str) -> list[str]:
    raw = str(selector or "").strip()
    if not raw:
        return []
    candidates = [raw]
    candidates.extend(part.strip() for part in raw.split(",") if part.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _configured_page_state(page: Any, action: dict[str, Any]) -> str | None:
    detected = _detect_auth_or_risk(page)
    if detected:
        return detected
    if _page_has_configured_auth_markers(page, action):
        return "AUTH_EXPIRED"
    if _page_has_configured_error_markers(page, action):
        return "PAGE_ERROR"
    return None


def _reload_page(page: Any, *, timeout_ms: int) -> None:
    reload_method = getattr(page, "reload", None)
    if callable(reload_method):
        reload_method(wait_until="load", timeout=timeout_ms)


def _ensure_page_ready(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None = None,
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    handoff_event_loop: Any = None,
    chrome: Any = None,
) -> dict[str, Any]:
    target_url = _resolve_action_url(action, key="target_url", params=params, extracted=extracted)
    selectors = _ready_selectors(action)
    if not target_url or not selectors:
        raise BrowserActionError(
            "PAGE_CHANGED",
            "ensure_page_ready requires target_url and ready_selector/ready_selectors",
        )

    check_timeout_ms = int(action.get("ready_check_timeout_ms") or 1000)
    if _page_has_ready_selector(page, selectors, timeout_ms=check_timeout_ms):
        return {}

    attempts = max(1, int(action.get("recover_attempts") or 1))
    wait_after_navigation_ms = max(0, int(action.get("wait_after_navigation_ms") or 0))
    reload_first = action.get("reload_first")
    allow_auth = bool(action.get("allow_auth_redirect"))
    last_state: str | None = _configured_page_state(page, action)
    last_error: Exception | None = None

    for attempt in range(attempts):
        current_state = _configured_page_state(page, action)
        if current_state == "RISK_VERIFICATION":
            current_state = _await_navigate_risk_clearance(
                page,
                run_config=run_config,
                sync_job_id=sync_job_id,
                handoff_coordinator=handoff_coordinator,
                backend_factory=backend_factory,
                handoff_event_loop=handoff_event_loop,
                chrome=chrome,
            )
        last_state = current_state or last_state
        should_reload = reload_first is True or (
            reload_first is not False and current_state in {"PAGE_ERROR", "AUTH_EXPIRED"}
        )
        if should_reload:
            try:
                _reload_page(page, timeout_ms=timeout_ms)
                if wait_after_navigation_ms:
                    _wait_for_timeout(page, wait_after_navigation_ms)
                if _page_has_ready_selector(page, selectors, timeout_ms=check_timeout_ms):
                    return {}
            except Exception as exc:
                last_error = exc

        try:
            page.goto(target_url, wait_until="load", timeout=timeout_ms)
            if wait_after_navigation_ms:
                _wait_for_timeout(page, wait_after_navigation_ms)
            if _page_has_ready_selector(page, selectors, timeout_ms=check_timeout_ms):
                return {}
        except Exception as exc:
            last_error = exc

        last_state = _configured_page_state(page, action) or last_state
        logger.info(
            "browser ensure_page_ready retry: step_id=%s attempt=%s/%s state=%s url=%s",
            action.get("id") or "",
            attempt + 1,
            attempts,
            last_state or "not_ready",
            _page_url(page),
        )

    if last_state == "AUTH_EXPIRED" and allow_auth:
        return {"auth_required": True}
    if last_state in {"AUTH_EXPIRED", "RISK_VERIFICATION"}:
        raise BrowserActionError(last_state, f"ensure_page_ready detected {last_state}: url={_page_url(page)}")
    raise BrowserActionError(
        "PAGE_CHANGED",
        f"ensure_page_ready selector not found after recovery: url={_page_url(page)} error={last_error}",
    )


def _render_template(value: str, *, params: dict[str, Any], extracted: dict[str, Any]) -> str:
    text = str(value or "")
    if "{{" not in text:
        return text

    def repl(match: re.Match[str]) -> str:
        raw_key = match.group(1).strip()
        if "." not in raw_key:
            return ""
        scope, key = raw_key.split(".", 1)
        if scope == "params":
            return str(params.get(key.strip()) or "")
        if scope == "extracted":
            return str(extracted.get(key.strip()) or "")
        return ""

    return re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", repl, text)


def _int_from_summary_text(value: Any) -> int | None:
    text = str(value or "").strip().replace(",", "")
    empty_markers = (
        "暂无数据",
        "暂无记录",
        "无数据",
        "没有数据",
        "未查询到",
        "查询不到",
        "无符合条件",
        "no data",
    )
    if not text:
        return 0
    if text in {"-", "--", "---", "—", "——", "–", "－"}:
        return 0
    lowered = text.lower()
    if any(marker in lowered for marker in empty_markers):
        return 0
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _execute_action(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    capture_files: list[dict[str, Any]],
    download_dir: Path,
    allow_auth_redirect: bool = False,
    run_config: PlaywrightRunConfig | None = None,
    sync_job_id: str = "",
    storage_context: dict[str, str] | None = None,
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    handoff_event_loop: Any = None,
    chrome: Any = None,
    overlays: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute one step. Returns a dict with ``rows`` (when parse_table) or empty dict.

    Raises a ``BrowserActionError`` with a ``fail_reason`` attribute on selector/auth/risk
    failure so the outer loop maps it to the right TASK_RESULT shape.
    """
    name = str(action.get("action") or "").strip()
    step_id = str(action.get("id") or "").strip()
    selector = str(action.get("selector") or "").strip()
    timeout_ms = int(action.get("timeout_ms") or 30000)
    logger.info("browser step starting: step_id=%s action=%s", step_id or "<unnamed>", name)

    if name == "navigate":
        page.goto(str(action.get("url") or ""), wait_until="load", timeout=timeout_ms)
        detected = _detect_auth_or_risk(page)
        if detected in {"AUTH_EXPIRED", "RISK_VERIFICATION"} and allow_auth_redirect:
            return {"auth_required": True}
        if detected == "AUTH_EXPIRED":
            auth_redirect_grace_ms = int(action.get("auth_redirect_grace_ms") or 15000)
            detected = _wait_for_transient_auth_redirect_to_clear(
                page,
                timeout_ms=auth_redirect_grace_ms,
            )
        if detected == "RISK_VERIFICATION":
            detected = _await_navigate_risk_clearance(
                page,
                run_config=run_config,
                sync_job_id=sync_job_id,
                handoff_coordinator=handoff_coordinator,
                backend_factory=backend_factory,
                handoff_event_loop=handoff_event_loop,
                chrome=chrome,
            )
        if detected:
            raise BrowserActionError(detected, f"navigate detected {detected}: url={_page_url(page)}")
        return {}
    if name == "click":
        record_time_as = str(action.get("record_time_as") or "").strip()
        if record_time_as:
            extracted[record_time_as] = _now_local_iso()
        _click_like_human(
            page,
            selector,
            timeout_ms=timeout_ms,
            run_config=run_config,
            overlays=overlays,
        )
        return {}
    if name == "click_if_present":
        visible_timeout_ms = int(action.get("visible_timeout_ms") or min(timeout_ms, 1000))
        selected_selector = ""
        for candidate_selector in _selector_candidates(selector):
            locator = _safe_first_locator(page, candidate_selector)
            if locator is not None and _locator_visible(locator, timeout_ms=visible_timeout_ms):
                selected_selector = candidate_selector
                break
        if not selected_selector:
            logger.info(
                "browser optional click skipped: step_id=%s selector=%s",
                step_id or "<unnamed>",
                selector,
            )
            return {"skipped": True}
        _click_like_human(
            page,
            selected_selector,
            timeout_ms=timeout_ms,
            run_config=run_config,
            overlays=overlays,
        )
        return {}
    if name == "fill":
        page.fill(selector, _resolve_value(action, params, extracted), timeout=timeout_ms)
        return {}
    if name == "ensure_page_ready":
        return _ensure_page_ready(
            page,
            action,
            params=params,
            extracted=extracted,
            timeout_ms=timeout_ms,
            run_config=run_config,
            sync_job_id=sync_job_id,
            handoff_coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            handoff_event_loop=handoff_event_loop,
            chrome=chrome,
        )
    if name == "set_date":
        _set_date_value(
            page,
            selector,
            _resolve_value(action, params, extracted),
            timeout_ms=timeout_ms,
            overlays=overlays,
        )
        return {}
    if name == "set_range_calendar_day":
        _set_range_calendar_day(
            page,
            action,
            value=_resolve_value(action, params, extracted),
            timeout_ms=timeout_ms,
            overlays=overlays,
        )
        return {}
    if name == "wait_for":
        page.wait_for_selector(selector, timeout=timeout_ms)
        return {}
    if name == "wait_ms":
        duration_ms = int(action.get("duration_ms") or action.get("value") or 0)
        if duration_ms <= 0:
            raise BrowserActionError("PAGE_CHANGED", "wait_ms requires positive duration_ms")
        page.wait_for_timeout(duration_ms)
        return {}
    if name in {"login", "login_if_needed"}:
        post_login_selector = str(action.get("post_login_wait_selector") or "").strip()
        if name == "login_if_needed" and post_login_selector:
            check_timeout_ms = min(timeout_ms, int(action.get("already_logged_in_timeout_ms") or 2000))
            if _page_has_ready_selector(
                page,
                _string_items(post_login_selector),
                timeout_ms=check_timeout_ms,
            ):
                logger.info(
                    "browser login_if_needed skipped because post-login selector is already ready: "
                    "step_id=%s url=%s",
                    step_id or "<unnamed>",
                    _page_url(page),
                )
                return {}
        _execute_login_action(
            page,
            action,
            params=params,
            extracted=extracted,
            timeout_ms=timeout_ms,
            run_config=run_config,
            sync_job_id=sync_job_id,
            handoff_coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            handoff_event_loop=handoff_event_loop,
            chrome=chrome,
        )
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
    if name == "stop_if_summary_zero":
        summary_field = str(action.get("summary_field") or "row_count").strip()
        count = _int_from_summary_text(extracted.get(summary_field))
        if count == 0:
            extracted[str(action.get("record_as") or "empty_result")] = True
            return {"stop_playbook": True}
        return {}
    if name == "select_checkboxes":
        return _select_checkboxes(
            page,
            action,
            params=params,
            extracted=extracted,
            timeout_ms=timeout_ms,
            overlays=overlays,
        )
    if name == "download":
        with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
            _click_like_human(
                page,
                selector,
                timeout_ms=timeout_ms,
                run_config=run_config,
                overlays=overlays,
            )
        return _save_download(
            info.value,
            download_dir=download_dir,
            capture_files=capture_files,
            storage_context=storage_context,
        )
    if name == "download_history_file":
        return _download_history_file(
            page,
            action,
            params=params,
            extracted=extracted,
            capture_files=capture_files,
            download_dir=download_dir,
            timeout_ms=timeout_ms,
            storage_context=storage_context,
            overlays=overlays,
        )
    if name == "download_qianniu_export_report":
        return _download_qianniu_export_report(
            page,
            action,
            params=params,
            extracted=extracted,
            capture_files=capture_files,
            download_dir=download_dir,
            timeout_ms=timeout_ms,
            storage_context=storage_context,
            overlays=overlays,
        )
    if name == "parse_table":
        source = str(action.get("source") or "last_download")
        fmt = str(action.get("format") or "csv").lower()
        skip_rows = int(action.get("skip_rows") or 0)
        archive = str(action.get("archive") or "").strip().lower()
        drop_row_prefix = str(action.get("drop_row_prefix") or "")
        path = Path(str(extracted.get(source) or capture_files[-1].get("local_path") or capture_files[-1]["storage_path"]))
        # Some platforms (e.g. PDD 货款明细) deliver the report wrapped in a (non-encrypted) zip
        # containing a single csv/xlsx. Extract the inner table before parsing.
        if archive == "zip" or path.suffix.lower() == ".zip":
            path = _extract_single_table_from_zip(path)
        rows, encoding = _parse_downloaded_table_with_metadata(path, fmt=fmt, skip_rows=skip_rows)
        if drop_row_prefix:
            # Drop trailing summary lines whose first column starts with the marker
            # (e.g. PDD bill footer rows "#收入合计：...", "#导出时间：...").
            rows = [
                row for row in rows
                if not str(next(iter(row.values()), "")).startswith(drop_row_prefix)
            ]
        if capture_files:
            capture_files[-1]["encoding"] = encoding
            capture_files[-1]["row_count"] = len(rows)
        return {"rows": rows}
    if name == "paginate_capture_json":
        rows = _paginate_capture_json(page, action, timeout_ms=timeout_ms, overlays=overlays)
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
    run_config: PlaywrightRunConfig | None = None,
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    handoff_event_loop: Any = None,
    chrome: Any = None,
) -> None:
    username_selector = str(action.get("username_selector") or "").strip()
    password_selector = str(action.get("password_selector") or "").strip()
    submit_selector = str(action.get("submit_selector") or "").strip()
    if not username_selector or not password_selector or not submit_selector:
        raise BrowserActionError(
            "PAGE_CHANGED",
            "login action requires username/password/submit selectors",
        )
    username = _login_value(action, field="username_value", params=params, extracted=extracted)
    password = _login_value(action, field="password_value", params=params, extracted=extracted)
    if not username or not password:
        raise BrowserActionError(
            "AUTH_EXPIRED",
            "login action missing resolved username or password",
        )

    post_login_wait_selector = str(action.get("post_login_wait_selector") or "").strip()
    login_context = _find_login_context(
        page,
        username_selector=username_selector,
        password_selector=password_selector,
        submit_selector=submit_selector,
        post_login_wait_selector=post_login_wait_selector,
        login_mode_selectors=_string_items(action.get("login_mode_selectors")),
        pre_submit_click_selectors=_string_items(action.get("pre_submit_click_selectors")),
        username=username,
        password=password,
        timeout_ms=timeout_ms,
        run_config=run_config,
        sync_job_id=sync_job_id,
        handoff_coordinator=handoff_coordinator,
        backend_factory=backend_factory,
        handoff_event_loop=handoff_event_loop,
        chrome=chrome,
    )
    wait_for_post_login_selector = action.get("wait_for_post_login_selector")
    if wait_for_post_login_selector is None:
        wait_for_post_login_selector = True
    if post_login_wait_selector and bool(wait_for_post_login_selector):
        _wait_for_post_login_selector(
            page,
            login_context=login_context,
            selector=post_login_wait_selector,
            timeout_ms=timeout_ms,
            run_config=run_config,
            sync_job_id=sync_job_id,
            handoff_coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            handoff_event_loop=handoff_event_loop,
            chrome=chrome,
        )


def _find_login_context(
    page: Any,
    *,
    username_selector: str,
    password_selector: str,
    submit_selector: str,
    post_login_wait_selector: str = "",
    login_mode_selectors: list[str] | None = None,
    pre_submit_click_selectors: list[str] | None = None,
    username: str,
    password: str,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None = None,
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    handoff_event_loop: Any = None,
    chrome: Any = None,
) -> Any:
    attempt_timeout_ms = min(timeout_ms, _LOGIN_SELECTOR_ATTEMPT_TIMEOUT_MS)
    last_error: Exception | None = None
    password_mode_clicked = False
    risk_deadline: float | None = None
    deadline = time.monotonic() + (max(timeout_ms, attempt_timeout_ms) / 1000)
    while time.monotonic() <= deadline:
        if post_login_wait_selector and _page_has_ready_selector(
            page,
            _string_items(post_login_wait_selector),
            timeout_ms=attempt_timeout_ms,
        ):
            logger.info(
                "browser login fields skipped because post-login selector is ready: selector=%s url=%s",
                post_login_wait_selector,
                _page_url(page),
            )
            return page
        candidates = _login_candidates(page)
        if login_mode_selectors and not password_mode_clicked:
            password_mode_clicked = _try_click_password_login_mode(
                candidates,
                timeout_ms=attempt_timeout_ms,
                login_mode_selectors=login_mode_selectors,
                include_builtin_selectors=False,
            )
            if password_mode_clicked:
                _wait_for_timeout(page, min(1000, attempt_timeout_ms))
                continue
        risk_deadline, handled_risk = _handle_login_risk_verification(
            page,
            candidates,
            run_config=run_config,
            sync_job_id=sync_job_id,
            handoff_coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            handoff_event_loop=handoff_event_loop,
            chrome=chrome,
            risk_deadline=risk_deadline,
            overall_deadline=deadline,
        )
        if risk_deadline is not None:
            deadline = max(deadline, risk_deadline)
        if handled_risk:
            continue
        for candidate in candidates:
            try:
                controls_ready = _ensure_login_controls_ready(
                    candidate,
                    username_selector=username_selector,
                    password_selector=password_selector,
                    submit_selector=submit_selector,
                    timeout_ms=attempt_timeout_ms,
                )
                interaction_timeout_ms = timeout_ms if controls_ready else attempt_timeout_ms
                _type_like_human(
                    candidate,
                    username_selector,
                    username,
                    timeout_ms=interaction_timeout_ms,
                    run_config=run_config,
                )
                _type_like_human(
                    candidate,
                    password_selector,
                    password,
                    timeout_ms=interaction_timeout_ms,
                    run_config=run_config,
                )
                if not _login_inputs_are_complete(
                    candidate,
                    username_selector=username_selector,
                    password_selector=password_selector,
                    expected_username=username,
                    expected_password=password,
                    timeout_ms=interaction_timeout_ms,
                ):
                    raise BrowserActionError(
                        "AUTH_EXPIRED",
                        "login input did not finish before submit",
                    )
                _click_pre_submit_controls(
                    candidate,
                    pre_submit_click_selectors,
                    timeout_ms=interaction_timeout_ms,
                    run_config=run_config,
                )
                _click_like_human(
                    candidate,
                    submit_selector,
                    timeout_ms=interaction_timeout_ms,
                    run_config=run_config,
                )
                return candidate
            except Exception as exc:
                if isinstance(exc, BrowserActionError) and "input did not finish" in str(exc):
                    raise exc
                last_error = exc
                risk_deadline, handled_risk = _handle_login_risk_verification(
                    page,
                    _login_candidates(page),
                    run_config=run_config,
                    sync_job_id=sync_job_id,
                    handoff_coordinator=handoff_coordinator,
                    backend_factory=backend_factory,
                    handoff_event_loop=handoff_event_loop,
                    chrome=chrome,
                    risk_deadline=risk_deadline,
                    overall_deadline=deadline,
                )
                if risk_deadline is not None:
                    deadline = max(deadline, risk_deadline)
                if handled_risk:
                    break
                if post_login_wait_selector and _page_has_ready_selector(
                    page,
                    _string_items(post_login_wait_selector),
                    timeout_ms=attempt_timeout_ms,
                ):
                    logger.info(
                        "browser login fields skipped after failed input lookup because "
                        "post-login selector is ready: selector=%s url=%s",
                        post_login_wait_selector,
                        _page_url(page),
                    )
                    return page
        if handled_risk:
            continue
        risk_deadline, handled_risk = _handle_login_risk_verification(
            page,
            _login_candidates(page),
            run_config=run_config,
            sync_job_id=sync_job_id,
            handoff_coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            handoff_event_loop=handoff_event_loop,
            chrome=chrome,
            risk_deadline=risk_deadline,
            overall_deadline=deadline,
        )
        if risk_deadline is not None:
            deadline = max(deadline, risk_deadline)
        if handled_risk:
            continue
        if not password_mode_clicked:
            password_mode_clicked = _try_click_password_login_mode(
                candidates,
                timeout_ms=attempt_timeout_ms,
                login_mode_selectors=login_mode_selectors,
            )
        _wait_for_timeout(page, min(1000, attempt_timeout_ms))
    raise BrowserActionError(
        "PAGE_CHANGED",
        f"login fields not found in page or child frames: {last_error}",
    )


def _handle_login_risk_verification(
    page: Any,
    candidates: list[Any],
    *,
    run_config: PlaywrightRunConfig | None,
    sync_job_id: str,
    handoff_coordinator: RemoteControlCoordinator | None,
    backend_factory: Any,
    handoff_event_loop: Any,
    chrome: Any,
    risk_deadline: float | None,
    overall_deadline: float,
) -> tuple[float | None, bool]:
    detected_states = [_detect_auth_or_risk(candidate) for candidate in candidates]
    if "RISK_VERIFICATION" not in detected_states:
        return risk_deadline, False

    manual_timeout_ms = int(run_config.risk_manual_timeout_ms if run_config else 0)
    if manual_timeout_ms <= 0:
        raise BrowserActionError("RISK_VERIFICATION", "login page requires risk verification")
    now = time.monotonic()
    if risk_deadline is None:
        risk_deadline = max(overall_deadline, now + manual_timeout_ms / 1000)
        logger.warning(
            "browser login risk verification waiting for manual completion: timeout_ms=%s",
            manual_timeout_ms,
        )
        _notify_risk_waiting()
    if now <= risk_deadline:
        risk_cleared = _wait_for_risk_to_clear_with_handoff(
            page,
            candidates,
            timeout_ms=int(max(1, (risk_deadline - now) * 1000)),
            poll_interval_ms=1000,
            sync_job_id=sync_job_id,
            coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            handoff_event_loop=handoff_event_loop,
            chrome=chrome,
        )
        if risk_cleared:
            return risk_deadline, True
    raise BrowserActionError(
        "RISK_VERIFICATION",
        "login page risk verification was not completed",
    )


def _login_candidates(page: Any) -> list[Any]:
    return [page, *list(getattr(page, "frames", []) or [])]


def _try_click_password_login_mode(
    candidates: list[Any],
    *,
    timeout_ms: int,
    login_mode_selectors: list[str] | None = None,
    include_builtin_selectors: bool = True,
) -> bool:
    builtin_selectors = _DEFAULT_PASSWORD_LOGIN_SELECTORS if include_builtin_selectors else ()
    selectors = [
        selector.strip()
        for selector in [*(login_mode_selectors or []), *builtin_selectors]
        if str(selector or "").strip()
    ]
    for candidate in candidates:
        for selector in selectors:
            try:
                candidate.click(selector, timeout=timeout_ms)
                return True
            except Exception:
                continue
    return False


def _click_pre_submit_controls(
    context: Any,
    selectors: list[str] | None,
    *,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None,
) -> None:
    for selector in selectors or []:
        try:
            _click_like_human(
                context,
                selector,
                timeout_ms=timeout_ms,
                run_config=run_config,
            )
        except Exception as exc:
            logger.info("browser login pre-submit click skipped: selector=%s error=%s", selector, exc)


def _ensure_login_controls_ready(
    context: Any,
    *,
    username_selector: str,
    password_selector: str,
    submit_selector: str,
    timeout_ms: int,
) -> bool:
    locator_factory = getattr(context, "locator", None)
    if not callable(locator_factory):
        return False
    for selector in (username_selector, password_selector, submit_selector):
        try:
            locator = locator_factory(selector).first
        except Exception:
            return False
        wait_for = getattr(locator, "wait_for", None)
        if callable(wait_for):
            wait_for(timeout=timeout_ms)
    return True


def _input_value(context: Any, selector: str, *, timeout_ms: int) -> str | None:
    locator_factory = getattr(context, "locator", None)
    if callable(locator_factory):
        try:
            return str(locator_factory(selector).first.input_value(timeout=timeout_ms) or "")
        except Exception:
            return None
    return None


def _login_inputs_are_complete(
    context: Any,
    *,
    username_selector: str,
    password_selector: str,
    expected_username: str,
    expected_password: str,
    timeout_ms: int,
) -> bool:
    username_value = _input_value(context, username_selector, timeout_ms=min(timeout_ms, 2000))
    password_value = _input_value(context, password_selector, timeout_ms=min(timeout_ms, 2000))
    if username_value is None or password_value is None:
        return True
    complete = username_value == expected_username and password_value == expected_password
    if not complete:
        logger.warning(
            "browser login input incomplete before submit: username_len=%s/%s password_len=%s/%s",
            len(username_value),
            len(expected_username),
            len(password_value),
            len(expected_password),
        )
    return complete


def _wait_for_risk_to_clear(
    contexts: list[Any],
    *,
    timeout_ms: int,
    poll_interval_ms: int = 1000,
) -> bool:
    return _wait_for_blocking_states_to_clear(
        contexts,
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
        blocking_states={"RISK_VERIFICATION"},
    )


def _wait_for_blocking_states_to_clear(
    contexts: list[Any],
    *,
    timeout_ms: int,
    poll_interval_ms: int = 1000,
    blocking_states: set[str] | None = None,
) -> bool:
    blocking = set(blocking_states or {"RISK_VERIFICATION"})
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    last_context = contexts[0] if contexts else None
    while time.monotonic() <= deadline:
        if _blocking_states_cleared(contexts, blocking):
            return True
        remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
        wait_ms = min(max(1, poll_interval_ms), remaining_ms)
        _wait_for_timeout(last_context, wait_ms)
    return _blocking_states_cleared(contexts, blocking)


def _run_async_safely(coro: Any, *, event_loop: Any = None) -> None:
    try:
        if event_loop is not None:
            future = asyncio.run_coroutine_threadsafe(coro, event_loop)

            def _log_future_error(done: Any) -> None:
                try:
                    done.result()
                except Exception:
                    logger.exception("handoff async callback failed")

            future.add_done_callback(_log_future_error)
            return
        asyncio.run(coro)
    except Exception:
        logger.exception("handoff async callback failed")


def _risk_cleared(contexts: list[Any]) -> bool:
    return _blocking_states_cleared(contexts, {"RISK_VERIFICATION"})


def _blocking_states_cleared(contexts: list[Any], blocking_states: set[str]) -> bool:
    return not any((_detect_auth_or_risk(context) or "") in blocking_states for context in contexts)


def _wait_for_risk_to_clear_with_handoff(
    page: Any,
    contexts: list[Any],
    *,
    timeout_ms: int,
    poll_interval_ms: int,
    sync_job_id: str,
    coordinator: RemoteControlCoordinator | None,
    backend_factory: Any = None,
    chrome: Any = None,
    blocking_states: set[str] | None = None,
    still_blocked_reason: str = "risk verification still blocked",
    handoff_event_loop: Any = None,
) -> bool:
    blocking = set(blocking_states or {"RISK_VERIFICATION"})
    if coordinator is None:
        return _wait_for_blocking_states_to_clear(
            contexts,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            blocking_states=blocking,
        )
    if backend_factory is not None:
        backend = backend_factory.create_backend(page=page, chrome=chrome, risk_contexts=contexts)
    else:
        backend = PlaywrightControlBackend(page=page, risk_contexts=contexts)
    try:
        backend.bind_window()
    except Exception:
        logger.exception("OS 后端窗口绑定失败,降级为不可控等待")
        try:
            backend.teardown()
        except Exception:
            pass
        return _wait_for_risk_to_clear(
            contexts,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )
    coordinator.register_backend(sync_job_id=sync_job_id, backend=backend)
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    try:
        while time.monotonic() <= deadline:
            backend.drain_pending_input()
            if backend.should_capture_frame():
                _run_async_safely(coordinator.emit_frame(
                    sync_job_id=sync_job_id,
                    backend=backend,
                    frame=backend.capture_frame(),
                ), event_loop=handoff_event_loop)
            if _blocking_states_cleared(contexts, blocking):
                _run_async_safely(coordinator.emit_status({
                    "type": "handoff_completed",
                    "sync_job_id": sync_job_id,
                    "handoff_session_id": backend.handoff_session_id,
                    "controller_id": backend.controller_id,
                }), event_loop=handoff_event_loop)
                return True
            if backend.pop_resume_check_requested() and not _blocking_states_cleared(contexts, blocking):
                _run_async_safely(coordinator.emit_status({
                    "type": "handoff_still_blocked",
                    "sync_job_id": sync_job_id,
                    "handoff_session_id": backend.handoff_session_id,
                    "controller_id": backend.controller_id,
                    "reason": still_blocked_reason,
                }), event_loop=handoff_event_loop)
            remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
            wait_ms = min(max(1, poll_interval_ms), remaining_ms)
            _wait_for_timeout(page, wait_ms)
        return _blocking_states_cleared(contexts, blocking)
    finally:
        backend.stop_stream()
        coordinator.unregister_backend(sync_job_id=sync_job_id)
        try:
            backend.teardown()
        except Exception:
            pass


def _await_navigate_risk_clearance(
    page: Any,
    *,
    run_config: "PlaywrightRunConfig | None",
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    handoff_event_loop: Any = None,
    chrome: Any = None,
) -> str | None:
    """navigate 落到风控页时,不立即失败:保持页面打开,轮询等待人工清除,
    上限 risk_manual_timeout_ms。清除返回 None(继续 playbook);超时或未配置超时返回
    'RISK_VERIFICATION'(由调用方抛出)。"""
    manual_timeout_ms = int(run_config.risk_manual_timeout_ms if run_config else 0)
    if manual_timeout_ms <= 0:
        return "RISK_VERIFICATION"
    logger.warning(
        "browser navigate risk verification waiting for manual completion: timeout_ms=%s",
        manual_timeout_ms,
    )
    _notify_risk_waiting()
    cleared = _wait_for_risk_to_clear_with_handoff(
        page,
        _login_candidates(page),
        timeout_ms=manual_timeout_ms,
        poll_interval_ms=1000,
        sync_job_id=sync_job_id,
        coordinator=handoff_coordinator,
        backend_factory=backend_factory,
        handoff_event_loop=handoff_event_loop,
        chrome=chrome,
    )
    return None if cleared else "RISK_VERIFICATION"


def _random_delay_ms(min_ms: int, max_ms: int) -> int:
    lower = max(0, int(min_ms or 0))
    upper = max(0, int(max_ms or 0))
    if upper < lower:
        upper = lower
    if upper <= 0:
        return 0
    return random.randint(lower, upper)


def _wait_for_timeout(context: Any, delay_ms: int) -> None:
    if delay_ms <= 0:
        return
    wait_for_timeout = getattr(context, "wait_for_timeout", None)
    if callable(wait_for_timeout):
        wait_for_timeout(delay_ms)
        return
    time.sleep(delay_ms / 1000)


def _pause_before_step(
    page: Any,
    *,
    run_config: PlaywrightRunConfig,
    step_id: str,
    action_name: str,
) -> None:
    delay_ms = _random_delay_ms(run_config.step_delay_min_ms, run_config.step_delay_max_ms)
    if delay_ms <= 0:
        return
    logger.info(
        "browser human pacing before step: step_id=%s action=%s delay_ms=%s",
        step_id or "<unnamed>",
        action_name or "<unknown>",
        delay_ms,
    )
    _wait_for_timeout(page, delay_ms)


def _pause_before_click(context: Any, *, run_config: PlaywrightRunConfig | None) -> None:
    if not run_config:
        return
    delay_ms = _random_delay_ms(run_config.click_delay_min_ms, run_config.click_delay_max_ms)
    _wait_for_timeout(context, delay_ms)


def _safe_first_locator(context: Any, selector: str) -> Any | None:
    locator_factory = getattr(context, "locator", None)
    if not callable(locator_factory):
        return None
    try:
        locator = locator_factory(selector)
    except Exception:
        return None
    first = getattr(locator, "first", None)
    return first if first is not None else locator


def _locator_visible(locator: Any, *, timeout_ms: int = 300) -> bool:
    try:
        return bool(locator.is_visible(timeout=timeout_ms))
    except Exception:
        return False


def _normalize_overlay_configs(raw_overlays: Any) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    if not isinstance(raw_overlays, list):
        return overlays
    for index, raw_overlay in enumerate(raw_overlays):
        if not isinstance(raw_overlay, dict):
            continue
        overlay_id = str(raw_overlay.get("id") or f"overlay_{index + 1}").strip()
        markers = [
            str(selector or "").strip()
            for selector in list(raw_overlay.get("markers") or [])
            if str(selector or "").strip()
        ]
        close_selectors = [
            str(selector or "").strip()
            for selector in list(raw_overlay.get("close_selectors") or [])
            if str(selector or "").strip()
        ]
        if overlay_id and markers and close_selectors:
            overlays.append(
                {
                    "id": overlay_id,
                    "markers": markers,
                    "close_selectors": close_selectors,
                }
            )
    return overlays


def _dismiss_configured_overlays(context: Any, overlays: list[dict[str, Any]] | None) -> bool:
    dismissed_any = False
    for overlay in overlays or []:
        overlay_id = str(overlay.get("id") or "overlay").strip()
        markers = list(overlay.get("markers") or [])
        close_selectors = list(overlay.get("close_selectors") or [])
        has_overlay = False
        for marker in markers:
            locator = _safe_first_locator(context, str(marker))
            if locator is not None and _locator_visible(locator, timeout_ms=300):
                has_overlay = True
                break
        if not has_overlay:
            continue
        clicked = False
        for selector in close_selectors:
            locator = _safe_first_locator(context, str(selector))
            if locator is None:
                continue
            try:
                locator.click(timeout=1000)
                _wait_for_timeout(context, 300)
                clicked = True
                dismissed_any = True
                logger.info(
                    "browser configured overlay dismissed: overlay_id=%s selector=%s",
                    overlay_id,
                    selector,
                )
                break
            except Exception as exc:
                logger.info(
                    "browser configured overlay close skipped: overlay_id=%s selector=%s error=%s",
                    overlay_id,
                    selector,
                    exc,
                )
        if not clicked:
            logger.info("browser configured overlay detected but not dismissed: overlay_id=%s", overlay_id)
    return dismissed_any


def _dismiss_overlays_and_retry_once(
    context: Any,
    overlays: list[dict[str, Any]] | None,
    operation: Any,
) -> Any:
    try:
        return operation()
    except Exception:
        if not _dismiss_configured_overlays(context, overlays):
            raise
    return operation()


def _click_like_human(
    context: Any,
    selector: str,
    *,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None,
    overlays: list[dict[str, Any]] | None = None,
) -> None:
    def _click_once() -> None:
        _pause_before_click(context, run_config=run_config)
        context.click(selector, timeout=timeout_ms)

    _dismiss_overlays_and_retry_once(context, overlays, _click_once)


def _type_like_human(
    context: Any,
    selector: str,
    value: str,
    *,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None,
) -> None:
    type_delay_ms = int(run_config.type_delay_ms if run_config else 0)
    locator_factory = getattr(context, "locator", None)
    if not callable(locator_factory) or type_delay_ms <= 0:
        context.fill(selector, value, timeout=timeout_ms)
        return
    locator = locator_factory(selector).first
    max_attempts = 3
    for attempt in range(max_attempts):
        locator.click(timeout=timeout_ms)
        try:
            if locator.input_value(timeout=timeout_ms) == value:
                return
        except Exception:
            pass
        locator.fill("", timeout=timeout_ms)
        locator.type(value, delay=type_delay_ms, timeout=timeout_ms)
        try:
            if locator.input_value(timeout=min(timeout_ms, 2000)) == value:
                return
        except Exception:
            return
        if attempt < max_attempts - 1:
            logger.warning(
                "browser input incomplete after type; retrying: selector=%s attempt=%s/%s",
                selector,
                attempt + 1,
                max_attempts,
            )
    raise BrowserActionError("AUTH_EXPIRED", f"input did not finish before submit: selector={selector}")


def _close_open_datepicker_overlay(page: Any) -> None:
    """Close a previous date-picker popup before targeting the next readonly input."""
    overlay = _safe_first_locator(page, ".next-overlay-wrapper.opened")
    if overlay is None or not _locator_visible(overlay, timeout_ms=200):
        return
    keyboard = getattr(page, "keyboard", None)
    press = getattr(keyboard, "press", None)
    if not callable(press):
        return
    try:
        press("Escape")
        _wait_for_timeout(page, 200)
    except Exception:
        return


def _set_date_value(
    page: Any,
    selector: str,
    value: str,
    *,
    timeout_ms: int,
    overlays: list[dict[str, Any]] | None = None,
) -> None:
    if not selector or not value:
        raise BrowserActionError("PAGE_CHANGED", "set_date requires selector and value")
    _dismiss_configured_overlays(page, overlays)
    _close_open_datepicker_overlay(page)
    locator = page.locator(selector).first
    _dismiss_overlays_and_retry_once(page, overlays, lambda: locator.click(timeout=timeout_ms))
    try:
        readonly = bool(
            locator.evaluate(
                """
                el => Boolean(
                  el.readOnly ||
                  el.hasAttribute('readonly') ||
                  el.getAttribute('aria-readonly') === 'true'
                )
                """
            )
        )
    except Exception:
        readonly = False
    if not readonly:
        try:
            locator.fill(value, timeout=timeout_ms)
        except Exception as exc:
            logger.info("browser date input fill failed; falling back to DOM value setter: %s", exc)
    locator.evaluate(
        """
        (el, value) => {
          const proto = el instanceof HTMLTextAreaElement
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
          const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
          if (setter) {
            setter.call(el, value);
          } else {
            el.value = value;
          }
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        value,
    )
    keyboard = getattr(page, "keyboard", None)
    press = getattr(keyboard, "press", None)
    if callable(press):
        try:
            press("Enter")
            press("Tab")
        except Exception:
            pass
    locator.evaluate(
        """
        el => {
          el.blur();
          el.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        """
    )
    page.wait_for_timeout(300)
    try:
        actual_value = locator.input_value(timeout=min(timeout_ms, 2000))
    except Exception:
        actual_value = value
    if str(actual_value or "").strip() != str(value or "").strip():
        raise BrowserActionError(
            "PAGE_CHANGED",
            f"set_date value not committed: selector={selector} expected={value} actual={actual_value}",
        )
    logger.info("browser date input committed: selector=%s value=%s", selector, value)


_CALENDAR_PICK_JS = """
(args) => {
  const {headerSel, cellSel, oom, targetHeader, day} = args;
  const visible = (el) => {
    if (!el) return false;
    const cls = (el.className || '').toString().toLowerCase();
    if (cls.includes('hidden')) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && rect.width > 0
      && rect.height > 0;
  };
  const panelSelectors = [
    "[class*='RPR_outerPickerWrapper']",
    "[class*='PP_dropdownMain']",
    ".auxo-picker-dropdown",
    ".ant-picker-dropdown",
    "[class*='auxo-picker-dropdown']",
    "[class*='ant-picker-dropdown']"
  ].join(',');
  let panels = Array.from(document.querySelectorAll(panelSelectors)).filter(visible);
  if (!panels.length) panels = [document];
  const panelReports = [];
  document.querySelectorAll('[data-tally-calendar-target]').forEach(el => {
    el.removeAttribute('data-tally-calendar-target');
  });
  for (const panel of panels.reverse()) {
    const headers = Array.from(panel.querySelectorAll(headerSel)).filter(visible);
    panelReports.push(headers.map(h => (h.textContent || '').trim()));
    const target = headers.find(h => (h.textContent || '').trim() === targetHeader);
    if (!target) continue;
    const hr = target.getBoundingClientRect();
    const hx = hr.left + hr.width / 2;
    const cells = Array.from(panel.querySelectorAll(cellSel)).filter(c =>
      (c.textContent || '').trim() === String(day) &&
      !(c.className || '').toString().includes(oom) &&
      visible(c)
    );
    if (!cells.length) return {ok: false, reason: 'no_day_cell', headers: headers.map(h => (h.textContent || '').trim())};
    // The picker shows two month panels side by side; pick the day cell whose horizontal
    // center is closest to the target month's header — i.e. the cell in that month's panel.
    cells.sort((a, b) => {
      const ax = a.getBoundingClientRect(); const bx = b.getBoundingClientRect();
      return Math.abs(ax.left + ax.width / 2 - hx) - Math.abs(bx.left + bx.width / 2 - hx);
    });
    const targetCell = cells[0];
    const clickable = targetCell.querySelector(
      ".auxo-picker-cell-inner,.ant-picker-cell-inner,[class*='picker-cell-inner']"
    ) || targetCell;
    const rect = clickable.getBoundingClientRect();
    clickable.setAttribute('data-tally-calendar-target', '1');
    return {
      ok: true,
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      marker: "[data-tally-calendar-target='1']",
      headers: headers.map(h => (h.textContent || '').trim()),
      cellText: (targetCell.textContent || '').trim(),
      panelClass: (panel.className || '').toString(),
    };
  }
  return {ok: false, reason: 'header_not_found', panels: panelReports};
}
"""

_CALENDAR_VISIBLE_MONTHS_JS = """
(headerSel) => {
  const visible = (el) => {
    if (!el) return false;
    const cls = (el.className || '').toString().toLowerCase();
    if (cls.includes('hidden')) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && rect.width > 0
      && rect.height > 0;
  };
  const panelSelectors = [
    "[class*='RPR_outerPickerWrapper']",
    "[class*='PP_dropdownMain']",
    ".auxo-picker-dropdown",
    ".ant-picker-dropdown",
    "[class*='auxo-picker-dropdown']",
    "[class*='ant-picker-dropdown']"
  ].join(',');
  let roots = Array.from(document.querySelectorAll(panelSelectors)).filter(visible);
  if (!roots.length) roots = [document];
  return roots.flatMap(root =>
    Array.from(root.querySelectorAll(headerSel))
      .filter(visible)
      .map(h => (h.textContent || '').trim())
  );
}
"""

# Opens the Nth (0=start, 1=end) time input inside the open RangePicker dropdown so the
# hh/mm/ss option lists render.
_CALENDAR_OPEN_TIME_JS = """
(index) => {
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && (el.offsetParent !== null || rect.width > 0 || rect.height > 0);
  };
  const panels = Array.from(document.querySelectorAll(
    "[class*='RPR_outerPickerWrapper'],[class*='PP_dropdownMain'],"
      + ".auxo-picker-dropdown,.ant-picker-dropdown,"
      + "[class*='auxo-picker-dropdown'],[class*='ant-picker-dropdown']"
  )).filter(panel => {
    const cls = (panel.className || '').toString();
    return !cls.includes('hidden') && visible(panel);
  });
  const panel = panels[panels.length - 1];
  if (!panel) return {ok: false, reason: 'no_picker_panel'};
  const inputs = Array.from(panel.querySelectorAll('input'))
    .filter(i => (i.getAttribute('placeholder') || '').includes('时间')
      || (i.className || '').toString().includes('time')
      || Boolean(i.closest("[class*='time'],[class*='Time']")));
  const input = inputs[index];
  if (input) {
    ['mousedown', 'mouseup', 'click'].forEach(t =>
      input.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window})));
    return {ok: true};
  }
  const columns = Array.from(panel.querySelectorAll(
    ".auxo-picker-time-panel-column,.ant-picker-time-panel-column,[class*='picker-time-panel-column']"
  )).filter(visible);
  if (columns.length >= 3) return {ok: true, via: 'visible_time_columns'};
  const hasDatePanel = Boolean(panel.querySelector(
    ".auxo-picker-panel,.ant-picker-panel,[class*='picker-panel'],[class*='PickerPanel']"
  ));
  if (hasDatePanel) return {ok: true, via: 'date_only_panel'};
  return {ok: false, reason: 'no_time_input_' + index, columns: columns.length};
}
"""

# Clicks hh/mm/ss options in the currently-visible time-picker lists, then returns the value
# of the time input at `index`.
_CALENDAR_PICK_TIME_JS = """
(args) => {
  const {index, hh, mm, ss} = args;
  const fire = (el) => ['mousedown', 'mouseup', 'click'].forEach(t =>
    el.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window})));
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && (el.offsetParent !== null || rect.width > 0 || rect.height > 0);
  };
  const panels = Array.from(document.querySelectorAll(
    "[class*='RPR_outerPickerWrapper'],[class*='PP_dropdownMain'],"
      + ".auxo-picker-dropdown,.ant-picker-dropdown,"
      + "[class*='auxo-picker-dropdown'],[class*='ant-picker-dropdown']"
  )).filter(panel => {
    const cls = (panel.className || '').toString();
    return !cls.includes('hidden') && visible(panel);
  });
  const panel = panels[panels.length - 1];
  const pick = (listTestid, val) => {
    const uls = Array.from(document.querySelectorAll("[data-testid='" + listTestid + "']"))
      .filter(u => u.offsetWidth > 0 && u.offsetHeight > 0);
    const ul = uls[uls.length - 1];
    if (!ul) return false;
    const li = Array.from(ul.querySelectorAll('li')).find(e => (e.textContent || '').trim() === val);
    if (!li) return false;
    li.scrollIntoView({block: 'center'});
    fire(li);
    return true;
  };
  const okh = pick('beast-core-timePicker-list-hh', hh);
  const okm = pick('beast-core-timePicker-list-mm', mm);
  const oks = pick('beast-core-timePicker-list-ss', ss);
  const inputs = panel ? Array.from(panel.querySelectorAll('input'))
    .filter(i => (i.getAttribute('placeholder') || '').includes('时间')
      || (i.className || '').toString().includes('time')
      || Boolean(i.closest("[class*='time'],[class*='Time']"))) : [];
  // Read the applied time from the dedicated range time inputs first (PDD beast-core exposes
  // data-testid'd begin/end time inputs); fall back to the heuristic panel input. The old
  // heuristic-only readback returned null on PDD's current DOM, raising a false "not applied"
  // even though the hh/mm/ss pick had succeeded.
  const readBack = () => {
    const ded = document.querySelector(
      "[data-testid='beast-core-rangePicker-timePicker-htmlInput-" + (index === 0 ? 'begin' : 'end') + "']"
    );
    if (ded && ded.value) return ded.value;
    return inputs[index] ? inputs[index].value : null;
  };
  if (okh && okm && oks) {
    return {ok: true, okh, okm, oks, value: readBack()};
  }

  const columns = panel ? Array.from(panel.querySelectorAll(
    ".auxo-picker-time-panel-column,.ant-picker-time-panel-column,[class*='picker-time-panel-column']"
  )).filter(visible) : [];
  const base = columns.length >= 6 ? index * 3 : 0;
  const pickColumn = (columnIndex, val) => {
    const column = columns[columnIndex];
    if (!column) return false;
    const item = Array.from(column.querySelectorAll(
      "li,[role='option'],[class*='time-panel-cell-inner'],[class*='TimePanelCell']"
    )).find(e => (e.textContent || '').trim() === val);
    if (!item) return false;
    item.scrollIntoView({block: 'center'});
    fire(item);
    return true;
  };
  const auxOkh = pickColumn(base, hh);
  const auxOkm = pickColumn(base + 1, mm);
  const auxOks = pickColumn(base + 2, ss);
  const value = readBack() || `${hh}:${mm}:${ss}`;
  return {
    ok: auxOkh && auxOkm && auxOks,
    okh: auxOkh,
    okm: auxOkm,
    oks: auxOks,
    value,
    columns: columns.length,
  };
}
"""


def _set_calendar_range_times(
    page: Any,
    *,
    start_time: str,
    end_time: str,
    timeout_ms: int,
) -> None:
    """Set start/end times in an open date-time RangePicker (readonly time inputs + hh/mm/ss lists).

    The day-cell click leaves both times at the current clock time, yielding a zero-width range
    that filters out the whole day's rows. Selecting e.g. 00:00:00 ~ 23:59:59 captures the full day.
    """
    for index, value in ((0, start_time), (1, end_time)):
        value = str(value or "").strip()
        if not value:
            continue
        match = re.match(r"^(\d{1,2}):(\d{1,2}):(\d{1,2})$", value)
        if not match:
            raise BrowserActionError("PAGE_CHANGED", f"calendar time value invalid: {value}")
        hh, mm, ss = (f"{int(group):02d}" for group in match.groups())
        opened = page.evaluate(_CALENDAR_OPEN_TIME_JS, index)
        if not isinstance(opened, dict) or not opened.get("ok"):
            raise BrowserActionError("PAGE_CHANGED", f"calendar time input open failed ({value}): {opened}")
        if opened.get("via") == "date_only_panel":
            logger.info("browser calendar time skipped for date-only picker: value=%s", value)
            continue
        page.wait_for_timeout(400)
        result = page.evaluate(_CALENDAR_PICK_TIME_JS, {"index": index, "hh": hh, "mm": mm, "ss": ss})
        if not isinstance(result, dict) or not result.get("ok"):
            raise BrowserActionError("PAGE_CHANGED", f"calendar time pick failed ({value}): {result}")
        if str(result.get("value") or "") != value:
            raise BrowserActionError(
                "PAGE_CHANGED", f"calendar time not applied ({value}): got {result.get('value')}"
            )
        page.wait_for_timeout(250)


def _calendar_visible_year_months(page: Any, header_selector: str) -> list[tuple[int, int]]:
    """Return the (year, month) of each visible calendar panel header, e.g. '2026年6月'."""
    texts = page.evaluate(_CALENDAR_VISIBLE_MONTHS_JS, header_selector)
    months: list[tuple[int, int]] = []
    for text in texts or []:
        m = re.search(r"(\d{4})\D+(\d{1,2})", str(text))
        if m:
            months.append((int(m.group(1)), int(m.group(2))))
    return months


def _calendar_input_contains_date(input_value: str, *, year: int, month: int, day: int) -> bool:
    """Return true when a picker input contains the target date in common web formats."""
    normalized = re.sub(r"\D+", "-", str(input_value or "")).strip("-")
    expected = f"{year:04d}-{month:02d}-{day:02d}"
    return normalized == expected or normalized.startswith(f"{expected}-")


def _set_range_calendar_day(
    page: Any,
    action: dict[str, Any],
    *,
    value: str,
    timeout_ms: int,
    overlays: list[dict[str, Any]] | None = None,
) -> None:
    """Select a single-day range (start==end==biz_date) in a click-only calendar RangePicker.

    For pickers whose input is readonly (calendar-only, no text entry, no quick presets), so
    ``set_date`` cannot type a value. Opens the picker, navigates month panels until biz_date's
    month is visible (so an arbitrary past biz_date can be back-filled, not just T-1), then clicks
    that day cell in its month's panel twice (range start then end).
    """
    selector = str(action.get("selector") or "").strip()
    if not selector or not value:
        raise BrowserActionError("PAGE_CHANGED", "set_range_calendar_day requires selector and value")
    match = re.match(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})", str(value))
    if not match:
        raise BrowserActionError("PAGE_CHANGED", f"set_range_calendar_day value is not a date: {value}")
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    target_header = str(action.get("panel_header_format") or "{year}年{month}月").format(
        year=year, month=month, day=day
    )
    header_selector = str(action.get("header_selector") or '[class*="RPR_panelHeader"]')
    day_cell_selector = str(action.get("day_cell_selector") or '[class*="RPR_cell_"]')
    out_of_month_marker = str(action.get("out_of_month_marker") or "outOfMonth")
    prev_month_selector = str(
        action.get("prev_month_selector") or '[class*="RPR_iconPrevNext"][class*="ICN_type-left"]'
    )
    next_month_selector = str(
        action.get("next_month_selector") or '[class*="RPR_iconPrevNext"][class*="RPR_right"]'
    )
    end_selector = str(action.get("end_selector") or "").strip()
    confirm_selector = str(action.get("confirm_selector") or "").strip()
    start_time = str(action.get("start_time") or "").strip()
    end_time = str(action.get("end_time") or "").strip()

    target_index = year * 12 + month

    def open_calendar(open_selector: str) -> None:
        # A stray popup can intercept the click and the panel may render slowly, so dismiss
        # overlays, click, then poll for month-panel headers.
        for _ in range(5):
            _dismiss_configured_overlays(page, overlays)
            try:
                _dismiss_overlays_and_retry_once(
                    page, overlays, lambda: page.locator(open_selector).first.click(timeout=timeout_ms)
                )
            except Exception as exc:
                logger.info("browser calendar open click retry: %s", exc)
            for _ in range(10):
                page.wait_for_timeout(300)
                if _calendar_visible_year_months(page, header_selector):
                    return
        raise BrowserActionError(
            "PAGE_CHANGED", f"calendar did not open for {value}: selector={open_selector}"
        )

    def navigate_to_target_month() -> None:
        # The picker may show two adjacent months; click prev/next until biz_date's month is visible.
        for _ in range(60):
            visible = _calendar_visible_year_months(page, header_selector)
            if not visible:
                break
            indices = [y * 12 + m for (y, m) in visible]
            if target_index in indices:
                return
            nav_selector = prev_month_selector if target_index < min(indices) else next_month_selector
            try:
                page.locator(nav_selector).first.click(timeout=timeout_ms)
            except Exception as exc:
                raise BrowserActionError(
                    "PAGE_CHANGED",
                    f"calendar month navigation failed for {value} (visible={visible}): {exc}",
                )
            page.wait_for_timeout(250)
        raise BrowserActionError(
            "PAGE_CHANGED", f"calendar could not navigate to month of {value}"
        )

    open_calendar(selector)
    navigate_to_target_month()

    js_args = {
        "headerSel": header_selector,
        "cellSel": day_cell_selector,
        "oom": out_of_month_marker,
        "targetHeader": target_header,
        "day": day,
    }
    for position in ("start", "end"):
        if position == "end" and end_selector:
            visible_indices = [
                visible_year * 12 + visible_month
                for visible_year, visible_month in _calendar_visible_year_months(
                    page, header_selector
                )
            ]
            if target_index not in visible_indices:
                open_calendar(end_selector)
                navigate_to_target_month()
        result = page.evaluate(_CALENDAR_PICK_JS, js_args)
        if not isinstance(result, dict) or not result.get("ok"):
            raise BrowserActionError(
                "PAGE_CHANGED",
                f"calendar {position} day not found for {value}: {result}",
            )
        x = result.get("x")
        y = result.get("y")
        if x is None or y is None:
            raise BrowserActionError(
                "PAGE_CHANGED",
                f"calendar {position} day click point missing for {value}: {result}",
            )
        marker_selector = str(result.get("marker") or "").strip()
        if marker_selector:
            page.locator(marker_selector).first.click(timeout=min(timeout_ms, 5000))
        else:
            page.mouse.click(float(x), float(y))
        page.wait_for_timeout(250)
        try:
            debug_start_value = str(
                page.locator(selector).first.input_value(timeout=min(timeout_ms, 1000)) or ""
            )
        except Exception:
            debug_start_value = ""
        debug_end_value = debug_start_value
        if end_selector:
            try:
                debug_end_value = str(
                    page.locator(end_selector).first.input_value(timeout=min(timeout_ms, 1000))
                    or ""
                )
            except Exception:
                debug_end_value = ""
        logger.debug(
            "browser calendar %s day clicked: result=%s start=%r end=%r",
            position,
            result,
            debug_start_value,
            debug_end_value,
        )

    if start_time or end_time:
        _set_calendar_range_times(
            page, start_time=start_time, end_time=end_time, timeout_ms=timeout_ms
        )

    if confirm_selector:
        try:
            page.locator(confirm_selector).first.click(timeout=min(timeout_ms, 3000))
        except Exception as exc:
            logger.info("browser calendar confirm click skipped: %s", exc)
    page.wait_for_timeout(300)
    try:
        start_value = str(page.locator(selector).first.input_value(timeout=min(timeout_ms, 2000)) or "")
    except Exception:
        start_value = ""
    end_value = start_value
    if end_selector:
        try:
            end_value = str(page.locator(end_selector).first.input_value(timeout=min(timeout_ms, 2000)) or "")
        except Exception:
            end_value = ""
    expected_date = f"{year:04d}-{month:02d}-{day:02d}"
    if not _calendar_input_contains_date(
        start_value, year=year, month=month, day=day
    ) or not _calendar_input_contains_date(end_value, year=year, month=month, day=day):
        raise BrowserActionError(
            "PAGE_CHANGED",
            "calendar range value not committed: "
            f"expected={expected_date} start={start_value!r} end={end_value!r}",
        )
    logger.info("browser calendar range set: selector=%s value=%s", selector, value)


def _select_checkboxes(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    timeout_ms: int,
    overlays: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selector = str(action.get("selector") or "").strip()
    if not selector:
        raise BrowserActionError("PAGE_CHANGED", "select_checkboxes requires selector")
    _dismiss_configured_overlays(page, overlays)
    root = page.locator(selector).last
    root.wait_for(state="visible", timeout=timeout_ms)
    label_selector = str(action.get("label_selector") or "label.next-checkbox-wrapper").strip()
    raw_labels = action.get("checked_labels")
    if raw_labels is None:
        raw_labels = action.get("allowed_labels")
    checked_labels = {
        _render_template(str(item), params=params, extracted=extracted).strip()
        for item in list(raw_labels or [])
        if str(item or "").strip()
    }
    if not checked_labels:
        raise BrowserActionError("PAGE_CHANGED", "select_checkboxes requires checked labels")
    if len(checked_labels) != len(list(raw_labels or [])):
        raise BrowserActionError("PAGE_CHANGED", "select_checkboxes contains empty labels")

    max_passes = max(1, int(action.get("max_passes") or 5))
    for _ in range(max_passes):
        state = _read_checkbox_state(root, label_selector=label_selector)
        known_labels = {str(item.get("text") or "") for item in state if item.get("text")}
        missing = sorted(checked_labels - known_labels)
        if missing:
            raise BrowserActionError("PAGE_CHANGED", f"select_checkboxes missing labels: {missing}")
        extra = [
            str(item.get("text") or "")
            for item in state
            if item.get("text")
            and item.get("text") != "全选"
            and bool(item.get("checked"))
            and str(item.get("text") or "") not in checked_labels
        ]
        missing_checked = [
            label
            for label in sorted(checked_labels)
            if not any(str(item.get("text") or "") == label and bool(item.get("checked")) for item in state)
        ]
        if not extra and not missing_checked:
            selected = sorted(
                str(item.get("text") or "")
                for item in state
                if item.get("text") and item.get("text") != "全选" and bool(item.get("checked"))
            )
            return {"selected_labels": selected}
        for label in [*extra, *missing_checked]:
            _dismiss_configured_overlays(page, overlays)
            clicked = _dismiss_overlays_and_retry_once(
                page,
                overlays,
                lambda: _click_exact_checkbox_label(root, label_selector=label_selector, label=label),
            )
            if not clicked:
                raise BrowserActionError("PAGE_CHANGED", f"select_checkboxes label not clickable: {label}")
            page.wait_for_timeout(120)

    final_state = _read_checkbox_state(root, label_selector=label_selector)
    selected = sorted(
        str(item.get("text") or "")
        for item in final_state
        if item.get("text") and item.get("text") != "全选" and bool(item.get("checked"))
    )
    extra = sorted(set(selected) - checked_labels)
    missing_checked = sorted(checked_labels - set(selected))
    if extra or missing_checked:
        raise BrowserActionError(
            "PAGE_CHANGED",
            f"select_checkboxes failed: extra={extra} missing={missing_checked}",
        )
    return {"selected_labels": selected}


def _read_checkbox_state(root: Any, *, label_selector: str) -> list[dict[str, Any]]:
    return list(
        root.locator(label_selector).evaluate_all(
            """
            els => els.map((label) => {
              const input = label.querySelector('input[type="checkbox"]');
              return {
                text: (label.innerText || label.textContent || '').trim(),
                checked: !!input?.checked,
                disabled: !!input?.disabled,
              };
            })
            """
        )
        or []
    )


def _click_exact_checkbox_label(root: Any, *, label_selector: str, label: str) -> bool:
    return bool(
        root.evaluate(
            """
            (root, arg) => {
              const labels = Array.from(root.querySelectorAll(arg.selector));
              const label = labels.find((item) => (
                (item.innerText || item.textContent || '').trim() === arg.label
              ));
              if (!label) return false;
              const input = label.querySelector('input[type="checkbox"]');
              if (input && input.disabled) return false;
              label.click();
              return true;
            }
            """,
            {"selector": label_selector, "label": label},
        )
    )


def _wait_for_post_login_selector(
    page: Any,
    *,
    login_context: Any,
    selector: str,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None = None,
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    handoff_event_loop: Any = None,
    chrome: Any = None,
) -> None:
    contexts = [login_context]
    if page is not login_context:
        contexts.append(page)
    selectors = _selector_candidates(selector)
    last_error: Exception | None = None
    last_detected: str | None = None
    risk_detected = False
    auth_handoff_detected = False
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    while time.monotonic() <= deadline:
        for context in contexts:
            remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
            per_selector_timeout_ms = min(remaining_ms, max(1, int(2000 / max(1, len(selectors)))))
            for candidate_selector in selectors:
                try:
                    context.wait_for_selector(candidate_selector, timeout=per_selector_timeout_ms)
                    return
                except Exception as exc:
                    last_error = exc
                    locator = _safe_first_locator(context, candidate_selector)
                    if locator is not None and _locator_visible(locator, timeout_ms=per_selector_timeout_ms):
                        return
        for context in contexts:
            detected = _detect_auth_or_risk(context)
            if detected:
                last_detected = detected
                logger.warning(
                    "browser post-login state detected: state=%s url=%s",
                    detected,
                    _page_url(context),
                )
                if detected == "RISK_VERIFICATION" and not risk_detected:
                    risk_detected = True
                    manual_timeout_ms = int(run_config.risk_manual_timeout_ms if run_config else 0)
                    if manual_timeout_ms > 0:
                        deadline = max(deadline, time.monotonic() + manual_timeout_ms / 1000)
                        logger.warning(
                            "browser risk verification waiting for manual completion: timeout_ms=%s",
                            manual_timeout_ms,
                        )
                        _notify_risk_waiting()
                        _wait_for_risk_to_clear_with_handoff(
                            page,
                            contexts,
                            timeout_ms=manual_timeout_ms,
                            poll_interval_ms=1000,
                            sync_job_id=sync_job_id,
                            coordinator=handoff_coordinator,
                            backend_factory=backend_factory,
                            handoff_event_loop=handoff_event_loop,
                            chrome=chrome,
                        )
                elif detected == "AUTH_EXPIRED" and not auth_handoff_detected:
                    auth_handoff_detected = True
                    manual_timeout_ms = int(run_config.risk_manual_timeout_ms if run_config else 0)
                    if manual_timeout_ms > 0:
                        deadline = max(deadline, time.monotonic() + manual_timeout_ms / 1000)
                        logger.warning(
                            "browser auth expired waiting for manual completion: timeout_ms=%s",
                            manual_timeout_ms,
                        )
                        _notify_risk_waiting("AUTH_EXPIRED")
                        _wait_for_risk_to_clear_with_handoff(
                            page,
                            contexts,
                            timeout_ms=manual_timeout_ms,
                            poll_interval_ms=1000,
                            sync_job_id=sync_job_id,
                            coordinator=handoff_coordinator,
                            backend_factory=backend_factory,
                            handoff_event_loop=handoff_event_loop,
                            chrome=chrome,
                            blocking_states={"AUTH_EXPIRED", "RISK_VERIFICATION"},
                            still_blocked_reason="auth expired or verification still blocked",
                        )
    if risk_detected:
        raise BrowserActionError("RISK_VERIFICATION", f"post-login risk verification not completed: {last_error}")
    if auth_handoff_detected:
        raise BrowserActionError("AUTH_EXPIRED", f"post-login auth expired not completed: {last_error}")
    if last_detected:
        raise BrowserActionError(last_detected, f"post-login detected {last_detected}: {last_error}")
    raise BrowserActionError("PAGE_CHANGED", f"post-login selector not found after login: {last_error}")


def _date_tokens(value: str) -> set[str]:
    text = str(value or "").strip()
    tokens = {text} if text else set()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        tokens.add(text.replace("-", ""))
    if len(text) == 8 and text.isdigit():
        tokens.add(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
    return {token for token in tokens if token}


def _canonical_date_token(value: str) -> str:
    text = str(value or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text.replace("-", "")
    if len(text) == 8 and text.isdigit():
        return text
    return ""


def _canonical_history_date_token(value: str, *, target_year: str) -> str:
    text = str(value or "").strip()
    token = _canonical_date_token(text)
    if token:
        return token
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", text)
    if match and target_year:
        month = int(match.group(1))
        day = int(match.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{target_year}{month:02d}{day:02d}"
    return ""


def _history_row_matches_target_date(row_text: str, target_date: str) -> bool:
    target_token = _canonical_date_token(target_date)
    if not target_token:
        return False
    target_year = target_token[:4]

    compact_text = " ".join(str(row_text or "").split())
    file_names = re.findall(r"\S+\.(?:csv|xlsx|xls)\b", compact_text, flags=re.IGNORECASE)
    for file_name in file_names:
        file_date_tokens = [
            _canonical_history_date_token(match, target_year=target_year)
            for match in re.findall(
                r"(?<!\d)(?:20\d{6}|20\d{2}[-/.]\d{2}[-/.]\d{2}|\d{1,2}[-/.]\d{1,2})(?!\d)",
                file_name,
            )
        ]
        if file_date_tokens and all(token == target_token for token in file_date_tokens):
            return True
    if file_names:
        return False

    business_text = re.split(
        r"(?:生成时间|创建时间|更新时间|申请时间|提交时间|完成时间|下载时间)",
        compact_text,
        maxsplit=1,
    )[0]
    # The date may be followed by a clock time before the range separator, e.g.
    # "2026-06-14 00:00:00 ~ 2026-06-14 23:59:59" — allow an optional " HH:MM(:SS)" after each date.
    date_range_matches = re.findall(
        r"(?<!\d)(20\d{2}[-/.]\d{2}[-/.]\d{2}|20\d{6}|\d{1,2}[-/.]\d{1,2})(?!\d)"
        r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?\s*"
        r"(?:~|至|到|_|—|–|\s-\s)\s*"
        r"(?<!\d)(20\d{2}[-/.]\d{2}[-/.]\d{2}|20\d{6}|\d{1,2}[-/.]\d{1,2})(?!\d)"
        r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?",
        business_text,
    )
    for start, end in date_range_matches:
        if (
            _canonical_history_date_token(start, target_year=target_year) == target_token
            and _canonical_history_date_token(end, target_year=target_year) == target_token
        ):
            return True
    return False


def _now_local_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_local_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("/", "-").replace(".", "-")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    match = re.search(
        r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})日?\s+"
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
        normalized,
    )
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second or "0"),
        )
    except ValueError:
        return None


def _extract_export_row_requested_time(row_text: str, requested_after: datetime | None) -> datetime | None:
    parsed = _extract_export_report_request_times(row_text)
    if not parsed:
        return None
    if requested_after is None:
        return parsed[0]
    return min(parsed, key=lambda item: abs((item - requested_after).total_seconds()))


def _extract_export_report_request_times(row_text: str) -> list[datetime]:
    compact_text = " ".join(str(row_text or "").split())
    matches = re.findall(
        r"报表申请时间[:：]?\s*"
        r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s+\d{1,2}:\d{2}(?::\d{2})?)",
        compact_text,
    )
    return [item for item in (_parse_local_datetime(match) for match in matches) if item is not None]


def _playwright_text_arg(value: str) -> str:
    text = str(value or "")
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    return f"/{re.escape(text)}/"


def _save_download(
    download: Any,
    *,
    download_dir: Path,
    capture_files: list[dict[str, Any]],
    storage_context: dict[str, str] | None = None,
) -> dict[str, str]:
    target = download_dir / (download.suggested_filename or "download.bin")
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        index = 1
        while target.exists():
            target = download_dir / f"{stem}-{index}{suffix}"
            index += 1
    download.save_as(str(target))
    _append_capture_file(target, capture_files=capture_files, storage_context=storage_context)
    return {"last_download": str(target)}


def _append_capture_file(
    target: Path,
    *,
    capture_files: list[dict[str, Any]],
    storage_context: dict[str, str] | None = None,
) -> None:
    context = dict(storage_context or {})
    storage_meta = upload_capture_file_if_configured(
        target,
        company_id=str(context.get("company_id") or ""),
        shop_id=str(context.get("shop_id") or ""),
        biz_date=str(context.get("biz_date") or ""),
        sync_job_id=str(context.get("sync_job_id") or ""),
    )
    capture_files.append({**storage_meta, "encoding": "", "checksum": "", "row_count": 0})


def _configured_selectors(action: dict[str, Any], list_key: str, single_key: str = "") -> list[str]:
    raw_items = action.get(list_key)
    selectors: list[str] = []
    if isinstance(raw_items, list):
        selectors.extend(str(item or "").strip() for item in raw_items)
    elif isinstance(raw_items, str):
        selectors.append(raw_items.strip())
    if single_key:
        single = str(action.get(single_key) or "").strip()
        if single:
            selectors.insert(0, single)
    deduped: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        if selector and selector not in seen:
            deduped.append(selector)
            seen.add(selector)
    return deduped


def _configured_selectors_with_primary(
    primary_selector: str,
    action: dict[str, Any],
    list_key: str,
    single_key: str = "",
) -> list[str]:
    selectors = [primary_selector.strip()] if primary_selector.strip() else []
    selectors.extend(_configured_selectors(action, list_key, single_key))
    deduped: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        if selector and selector not in seen:
            deduped.append(selector)
            seen.add(selector)
    return deduped


def _selector_has_matches(page: Any, selector: str) -> bool | None:
    try:
        return page.locator(selector).count() > 0
    except Exception:
        return None


def _click_first_available_selector(
    page: Any,
    selectors: list[str],
    *,
    timeout_ms: int,
    force: bool = True,
) -> bool:
    last_error: Exception | None = None
    for selector in selectors:
        has_matches = _selector_has_matches(page, selector)
        if has_matches is False:
            continue
        try:
            page.click(selector, timeout=timeout_ms, force=force)
            return True
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return False


def _locator_text_rows(locator: Any, *, timeout_ms: int) -> list[tuple[int, str]]:
    try:
        rows = locator.evaluate_all(
            """
            els => els
              .map((el, index) => {
                const style = window.getComputedStyle(el);
                const visible = style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && el.getClientRects().length > 0;
                return {
                  index,
                  visible,
                  text: (el.innerText || el.textContent || '').trim(),
                };
              })
              .filter(item => item.visible && item.text)
            """
        )
    except Exception as exc:
        logger.info("browser history batch row text read failed; falling back to row reads: %s", exc)
        rows = []
        try:
            row_count = locator.count()
        except Exception:
            return []
        for index in range(row_count):
            try:
                text = locator.nth(index).inner_text(timeout=min(timeout_ms, 1000))
            except Exception:
                continue
            rows.append({"index": index, "text": text})

    normalized: list[tuple[int, str]] = []
    for index, item in enumerate(list(rows or [])):
        if isinstance(item, dict):
            raw_index = item.get("index", index)
            raw_text = item.get("text", "")
        else:
            raw_index = index
            raw_text = item
        try:
            row_index = int(raw_index)
        except (TypeError, ValueError):
            row_index = index
        text = " ".join(str(raw_text or "").split())
        if text:
            normalized.append((row_index, text))
    return normalized


def _download_qianniu_export_report(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    capture_files: list[dict[str, Any]],
    download_dir: Path,
    timeout_ms: int,
    storage_context: dict[str, str] | None = None,
    overlays: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row_selector = str(action.get("selector") or "").strip()
    requested_after_value = _resolve_value(
        {"value_from": action.get("requested_after_from")},
        params,
        extracted,
    )
    requested_after = _parse_local_datetime(requested_after_value)
    report_type = str(action.get("report_type") or "").strip()
    download_button_text = str(action.get("download_button_text") or "").strip()
    refresh_selector = str(action.get("refresh_selector") or "").strip()
    refresh_interval_ms = max(1000, int(action.get("refresh_interval_ms") or 15000))
    requested_tolerance_seconds = int(action.get("request_time_tolerance_seconds") or 5)
    request_time_tolerance_seconds = max(requested_tolerance_seconds, 60)
    if not row_selector or not requested_after or not download_button_text:
        raise BrowserActionError(
            "PAGE_CHANGED",
            "download_qianniu_export_report requires selector, requested_after_from, and download_button_text",
        )

    button_selector = (
        f"button:has-text({_playwright_text_arg(download_button_text)}), "
        f"[role='button']:has-text({_playwright_text_arg(download_button_text)})"
    )
    fallback_row_selector = (
        "[class*='order-export_order-block'], "
        "tr.next-table-row, "
        ".next-table-row, "
        "[role='row']"
    )
    detail_selector = str(action.get("detail_selector") or "").strip()
    earliest_allowed = requested_after - timedelta(seconds=max(0, request_time_tolerance_seconds))

    def _find_download_button() -> tuple[Any | None, str]:
        row_sources: list[tuple[str, Any]] = []
        for selector in [row_selector, fallback_row_selector, detail_selector]:
            if not selector:
                continue
            try:
                row_sources.append((selector, page.locator(selector)))
            except Exception as exc:
                logger.info("qianniu export row selector failed: selector=%s error=%s", selector, exc)
        nearest_skipped_time = ""
        checked_any_row = False
        for source_selector, rows in row_sources:
            try:
                row_count = rows.count()
            except Exception as exc:
                logger.info(
                    "qianniu export row count failed: selector=%s error=%s",
                    source_selector,
                    exc,
                )
                continue
            for index in range(row_count):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=300):
                        continue
                except Exception:
                    pass
                try:
                    text = row.inner_text(timeout=min(timeout_ms, 5000))
                except Exception:
                    continue
                compact_text = " ".join(str(text or "").split())
                if "报表申请时间" not in compact_text and download_button_text not in compact_text:
                    continue
                checked_any_row = True
                if report_type and report_type not in compact_text:
                    continue
                row_requested_times = _extract_export_report_request_times(compact_text)
                if len(row_requested_times) > 1:
                    logger.info(
                        "qianniu export row skipped because it contains multiple request times: "
                        "selector=%s row=%s requested_after=%s text=%s",
                        source_selector,
                        index,
                        requested_after.isoformat(sep=" ", timespec="seconds"),
                        compact_text[:500],
                    )
                    continue
                row_requested_at = _extract_export_row_requested_time(compact_text, requested_after)
                if row_requested_at is None:
                    logger.info(
                        "qianniu export row skipped because request time was not found: "
                        "selector=%s row=%s text=%s",
                        source_selector,
                        index,
                        compact_text[:300],
                    )
                    continue
                if row_requested_at < earliest_allowed:
                    nearest_skipped_time = row_requested_at.isoformat(sep=" ", timespec="seconds")
                    continue
                button = row.locator(button_selector).first
                try:
                    if button.count() <= 0:
                        continue
                except Exception:
                    continue
                try:
                    if not button.is_visible(timeout=500):
                        continue
                except Exception:
                    continue
                try:
                    if button.is_disabled(timeout=500):
                        continue
                except Exception:
                    pass
                logger.info(
                    "qianniu export report matched for download: requested_after=%s row_requested_at=%s "
                    "report_type=%s selector=%s row=%s text=%s",
                    requested_after.isoformat(sep=" ", timespec="seconds"),
                    row_requested_at.isoformat(sep=" ", timespec="seconds"),
                    report_type,
                    source_selector,
                    index,
                    compact_text[:500],
                )
                return button, ""
        try:
            buttons = page.locator(button_selector)
            button_count = buttons.count()
        except Exception as exc:
            logger.info("qianniu export button selector failed: selector=%s error=%s", button_selector, exc)
            button_count = 0
            buttons = None
        for index in range(button_count):
            button = buttons.nth(index)
            try:
                if not button.is_visible(timeout=500):
                    continue
            except Exception:
                continue
            try:
                if button.is_disabled(timeout=500):
                    continue
            except Exception:
                pass
            try:
                row = button.locator("xpath=ancestor::*[contains(., '报表申请时间')][1]").first
                text = row.inner_text(timeout=min(timeout_ms, 5000))
            except Exception as exc:
                logger.info(
                    "qianniu export button ancestor lookup failed: button=%s error=%s",
                    index,
                    exc,
                )
                continue
            compact_text = " ".join(str(text or "").split())
            if "报表申请时间" not in compact_text:
                continue
            checked_any_row = True
            if report_type and report_type not in compact_text:
                continue
            row_requested_times = _extract_export_report_request_times(compact_text)
            if len(row_requested_times) > 1:
                logger.info(
                    "qianniu export button ancestor skipped because it contains multiple request times: "
                    "button=%s requested_after=%s text=%s",
                    index,
                    requested_after.isoformat(sep=" ", timespec="seconds"),
                    compact_text[:500],
                )
                continue
            row_requested_at = _extract_export_row_requested_time(compact_text, requested_after)
            if row_requested_at is None:
                logger.info(
                    "qianniu export button ancestor skipped because request time was not found: "
                    "button=%s text=%s",
                    index,
                    compact_text[:300],
                )
                continue
            if row_requested_at < earliest_allowed:
                nearest_skipped_time = row_requested_at.isoformat(sep=" ", timespec="seconds")
                continue
            logger.info(
                "qianniu export report matched by button ancestor for download: "
                "requested_after=%s row_requested_at=%s report_type=%s button=%s text=%s",
                requested_after.isoformat(sep=" ", timespec="seconds"),
                row_requested_at.isoformat(sep=" ", timespec="seconds"),
                report_type,
                index,
                compact_text[:500],
            )
            return button, ""
        if not checked_any_row:
            return None, "no_export_rows"
        return None, nearest_skipped_time

    def _refresh_export_list() -> None:
        if refresh_selector:
            try:
                _dismiss_configured_overlays(page, overlays)
                _dismiss_overlays_and_retry_once(
                    page,
                    overlays,
                    lambda: page.click(refresh_selector, timeout=min(10000, timeout_ms), force=True),
                )
                return
            except Exception as exc:
                logger.info("qianniu export list refresh click failed, reloading page: %s", exc)
        page.reload(wait_until="domcontentloaded", timeout=min(30000, timeout_ms))

    def _wait_for_export_candidates_after_refresh() -> None:
        wait_timeout = min(5000, timeout_ms)
        for selector in [row_selector, button_selector, fallback_row_selector, detail_selector]:
            if not selector:
                continue
            try:
                page.wait_for_selector(selector, timeout=wait_timeout)
                logger.info("qianniu export list hydrated after refresh: selector=%s", selector)
                return
            except Exception:
                continue

    try:
        page.wait_for_selector(row_selector, timeout=min(timeout_ms, 5000))
    except Exception:
        logger.info("qianniu export rows not visible yet; will continue polling")

    deadline = time.monotonic() + (timeout_ms / 1000)
    last_skipped_time = ""
    while time.monotonic() <= deadline:
        detected = _detect_auth_or_risk(page)
        if detected:
            raise BrowserActionError(detected, f"download_qianniu_export_report detected {detected}")
        button, skipped_time = _find_download_button()
        if skipped_time:
            last_skipped_time = skipped_time
        if button is not None:
            with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
                _dismiss_configured_overlays(page, overlays)
                _dismiss_overlays_and_retry_once(
                    page,
                    overlays,
                    lambda: button.click(timeout=min(30000, timeout_ms)),
                )
            return _save_download(
                info.value,
                download_dir=download_dir,
                capture_files=capture_files,
                storage_context=storage_context,
            )
        remaining_ms = int(max(0, (deadline - time.monotonic()) * 1000))
        if remaining_ms <= 0:
            break
        wait_ms = min(refresh_interval_ms, remaining_ms)
        logger.info(
            "qianniu export report not ready; waiting before refresh: requested_after=%s "
            "report_type=%s wait_ms=%s last_skipped_time=%s",
            requested_after.isoformat(sep=" ", timespec="seconds"),
            report_type,
            wait_ms,
            last_skipped_time,
        )
        page.wait_for_timeout(wait_ms)
        if time.monotonic() <= deadline:
            _refresh_export_list()
            _wait_for_export_candidates_after_refresh()

    raise BrowserActionError(
        "EXPORT_REPORT_NOT_READY",
        "download_qianniu_export_report timed out waiting for a newly generated report "
        f"after {requested_after.isoformat(sep=' ', timespec='seconds')}",
    )


def _download_history_file(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    capture_files: list[dict[str, Any]],
    download_dir: Path,
    timeout_ms: int,
    storage_context: dict[str, str] | None = None,
    overlays: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selector = str(action.get("selector") or "").strip()
    history_row_selectors = _configured_selectors_with_primary(
        selector,
        action,
        "history_row_selectors",
        "history_row_selector",
    )
    status_text = str(action.get("history_completed_status_text") or "已完成").strip()
    download_selector = str(action.get("history_download_selector") or "button:has-text('下载')").strip()
    history_open_selectors = _configured_selectors(
        action,
        "history_open_selectors",
        "history_open_selector",
    )
    history_close_selectors = _configured_selectors(
        action,
        "history_close_selectors",
        "history_close_selector",
    )
    history_open_timeout_ms = int(action.get("history_open_timeout_ms") or 30000)
    history_refresh_close_timeout_ms = int(
        action.get("history_refresh_close_timeout_ms")
        or min(max(1000, history_open_timeout_ms), 3000)
    )
    history_refresh_interval_ms = max(0, int(action.get("history_refresh_interval_ms") or 5000))
    target_date = _resolve_value(action, params, extracted)
    # match_mode "latest_today": these export tasks have no concurrency, so instead of strictly
    # matching the order-time-range date (brittle: ranges carry HH:MM(:SS) and vary by page),
    # just grab the newest completed task generated today. The freshly generated report is the
    # newest row whose text carries today's date.
    match_mode = str(action.get("history_match_mode") or "").strip()
    today_tokens = {
        datetime.now().strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y/%m/%d"),
    }
    tokens = _date_tokens(target_date)
    if not history_row_selectors or (match_mode != "latest_today" and not tokens):
        raise BrowserActionError("PAGE_CHANGED", "download_history_file requires selector and target date")
    if not status_text or not download_selector:
        raise BrowserActionError(
            "PAGE_CHANGED",
            "download_history_file requires history_completed_status_text and history_download_selector",
        )

    def _history_has_visible_rows() -> bool:
        if not selector:
            return False
        try:
            return bool(_locator_text_rows(page.locator(selector), timeout_ms=history_open_timeout_ms))
        except Exception:
            return False

    def _open_history() -> None:
        if _history_has_visible_rows():
            return
        if not history_open_selectors:
            return
        _dismiss_configured_overlays(page, overlays)
        _dismiss_overlays_and_retry_once(
            page,
            overlays,
            lambda: _click_first_available_selector(
                page,
                history_open_selectors,
                timeout_ms=history_open_timeout_ms,
                force=True,
            ),
        )

    def _find_completed_row() -> Any | None:
        for row_selector in history_row_selectors:
            rows = page.locator(row_selector)
            for index, compact_text in _locator_text_rows(rows, timeout_ms=timeout_ms):
                matches_status = status_text in compact_text
                if match_mode == "latest_today":
                    # Rows are listed newest-first, so the first completed row carrying today's
                    # date is the report we just generated (no concurrency).
                    if matches_status and any(tok in compact_text for tok in today_tokens):
                        logger.info(
                            "browser history latest-today row matched: selector=%s row=%s text=%s",
                            row_selector,
                            index,
                            compact_text[:500],
                        )
                        return rows.nth(index)
                    continue
                matches_date = _history_row_matches_target_date(compact_text, str(target_date))
                if matches_date and matches_status:
                    logger.info(
                        "browser history row matched for download: target_date=%s selector=%s row=%s "
                        "status_text=%s text=%s",
                        target_date,
                        row_selector,
                        index,
                        status_text,
                        compact_text[:500],
                    )
                    return rows.nth(index)
        return None

    def _refresh_history() -> None:
        if not history_open_selectors:
            return
        try:
            _dismiss_configured_overlays(page, overlays)
            closed = _dismiss_overlays_and_retry_once(
                page,
                overlays,
                lambda: _click_first_available_selector(
                    page,
                    history_close_selectors,
                    timeout_ms=history_refresh_close_timeout_ms,
                    force=True,
                ),
            )
        except Exception as exc:
            closed = False
            logger.info("browser history drawer close skipped before refresh: %s", exc)
        if closed:
            page.wait_for_timeout(min(1000, max(0, history_refresh_interval_ms)))
        try:
            _dismiss_configured_overlays(page, overlays)
            _open_history()
        except Exception as exc:
            logger.info("browser history reopen skipped; keeping current history list: %s", exc)

    try:
        _open_history()
    except Exception as exc:
        logger.info("browser history open skipped; checking current history list: %s", exc)
    # When a bill simply does not exist for the target day, the daily-bill grid just omits that
    # row (it is not generated late), so there is nothing to wait for: with missing_row_ok we cap
    # the search short and, if still unmatched, treat it as an empty (no-bill) success below
    # instead of polling to timeout and failing.
    missing_row_ok = bool(action.get("missing_row_ok"))
    search_timeout_ms = min(timeout_ms, 8000) if missing_row_ok else timeout_ms
    deadline = time.monotonic() + (search_timeout_ms / 1000)
    row = None
    while time.monotonic() <= deadline:
        row = _find_completed_row()
        if row is not None:
            break
        wait_ms = min(2000, max(0, int((deadline - time.monotonic()) * 1000)))
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        row = _find_completed_row()
        if row is not None:
            break
        if time.monotonic() <= deadline:
            _refresh_history()

    if row is None:
        if missing_row_ok:
            logger.info(
                "download_history_file: no matching bill row for %s; treating as empty success "
                "(missing_row_ok=true — no bill generated for this day)",
                target_date,
            )
            return {"stop_playbook": True, "rows": []}
        raise BrowserActionError("PAGE_CHANGED", f"history download row not completed for {target_date}")

    # The 新消息 (ImportantList) popup can cover the download button and even re-appear after a
    # dismiss. With a long action timeout a covered click would hang waiting for actionability, so
    # dismiss overlays and click with a short per-attempt timeout, retrying so a re-shown popup is
    # cleared before the next attempt.
    click_timeout_ms = min(timeout_ms, int(action.get("history_download_click_timeout_ms") or 8000))
    # In latest_today mode the matched "row" may be a container holding several reports' download
    # buttons (the row markup uses unstable styled-component classes), so click the page's first
    # (newest, top-listed) download button instead of scoping to the matched container.
    download_target = (
        page.locator(download_selector).first
        if match_mode == "latest_today"
        else row.locator(download_selector)
    )
    last_exc: Exception | None = None
    with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
        clicked = False
        for _ in range(6):
            _dismiss_configured_overlays(page, overlays)
            try:
                download_target.click(timeout=click_timeout_ms)
                clicked = True
                break
            except Exception as exc:
                last_exc = exc
                page.wait_for_timeout(500)
        if not clicked:
            raise BrowserActionError(
                "PAGE_CHANGED", f"history download click blocked (overlay covering button?): {last_exc}"
            )
    return _save_download(
        info.value,
        download_dir=download_dir,
        capture_files=capture_files,
        storage_context=storage_context,
    )


class BrowserActionError(Exception):
    def __init__(self, fail_reason: str, message: str) -> None:
        super().__init__(message)
        self.fail_reason = fail_reason


def _read_csv_with_fallback(path: Path, *, skip_rows: int = 0) -> tuple[Any, str]:
    import pandas as pd

    skiprows = skip_rows or None
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return pd.read_csv(
                path, encoding=encoding, dtype=str, keep_default_na=False, skiprows=skiprows
            ), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(path, dtype=str, keep_default_na=False, skiprows=skiprows), ""


def _extract_single_table_from_zip(zip_path: Path) -> Path:
    """Extract the single csv/xlsx member from a (non-encrypted) downloaded zip.

    PDD 货款明细导出 delivers ``*.zip`` wrapping one csv. We extract it next to the zip and
    return the extracted path so the normal csv/xlsx parser can read it. Raises PAGE_CHANGED
    if the archive is encrypted or does not contain exactly one table file.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = [
                info for info in zf.infolist()
                if not info.is_dir() and info.filename.lower().rsplit(".", 1)[-1] in {"csv", "xlsx"}
            ]
            if len(members) != 1:
                raise BrowserActionError(
                    "PAGE_CHANGED",
                    f"expected exactly one csv/xlsx in zip, found {len(members)}",
                )
            member = members[0]
            if member.flag_bits & 0x1:
                raise BrowserActionError("PAGE_CHANGED", "zip member is password-encrypted")
            target = zip_path.with_name(f"{zip_path.stem}__{Path(member.filename).name}")
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            return target
    except zipfile.BadZipFile as exc:
        raise BrowserActionError("PAGE_CHANGED", f"downloaded file is not a valid zip: {exc}")


def _unwrap_excel_text_guard(value: Any) -> Any:
    """Strip the Excel text guard some exports wrap long ids in, e.g. ``="349693386401"``.

    JD daily-bill csv wraps id columns (订单编号/单据编号/商品编号/商户订单号) as ``="value"`` so
    Excel keeps them as text instead of mangling long numbers. Stored verbatim those ids would
    not join with the order playbook's plain ids, breaking reconciliation, so unwrap to ``value``
    (``=""`` -> empty). Only the exact ``="..."`` shape is touched; ordinary values pass through.
    """
    if isinstance(value, str) and len(value) >= 3 and value.startswith('="') and value.endswith('"'):
        return value[2:-1]
    return value


def _parse_downloaded_table_with_metadata(
    path: Path, *, fmt: str, skip_rows: int = 0
) -> tuple[list[dict[str, Any]], str]:
    """Parse a downloaded CSV/XLSX file and return rows plus detected encoding.

    ``skip_rows`` skips that many leading lines before the header row, for reports whose real
    column header is not the first line (e.g. PDD bill csv has title/time-range/separator lines
    above the header).
    """
    import pandas as pd

    if fmt == "xlsx":
        df = pd.read_excel(path, dtype=str, keep_default_na=False, skiprows=skip_rows or None)
        encoding = ""
    else:
        df, encoding = _read_csv_with_fallback(path, skip_rows=skip_rows)
    rows = [
        {str(k): ("" if pd.isna(v) else _unwrap_excel_text_guard(v)) for k, v in row.items()}
        for row in df.to_dict("records")
    ]
    return rows, encoding


def _parse_downloaded_table(path: Path, *, fmt: str) -> list[dict[str, Any]]:
    """Parse a downloaded CSV/XLSX file into a list of row dicts.

    pandas is lazy-imported because the synthetic test runner never needs it.
    """
    rows, _encoding = _parse_downloaded_table_with_metadata(path, fmt=fmt)
    return rows


def _json_get(obj: Any, path: str) -> Any:
    """Resolve a dotted JSON path with numeric list indices, e.g. 'data.results' or 'a.0.b'."""
    cur = obj
    for seg in str(path).split("."):
        if cur is None or seg == "":
            return cur if seg == "" else None
        if isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError, TypeError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def _apply_json_transform(value: Any, transform: str) -> Any:
    """Optional value transform for captured JSON fields (path suffix after '|')."""
    if value is None:
        return ""
    if transform == "epoch_ms":  # JD orderCreateTime etc. are epoch milliseconds
        try:
            dt = datetime.fromtimestamp(int(value) / 1000, tz=timezone(timedelta(hours=8)))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return value
    if transform in {"cent_to_yuan", "fen_to_yuan"}:
        try:
            yuan = (Decimal(str(value)) / Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            return f"{yuan:.2f}"
        except (InvalidOperation, ValueError):
            return value
    return value


def _extract_json_field(item: Any, spec: str) -> Any:
    """Extract one column value from a JSON row.

    ``spec`` is ``path`` or ``path|transform``. A ``[]`` segment maps over a list and joins the
    leaf values with ' | ' (e.g. 'orderItems[].skuName' -> all item names of a multi-item order).
    """
    path, _, transform = str(spec).partition("|")
    if "[]" in path:
        before, _, after = path.partition("[]")
        after = after.lstrip(".")
        before = before.rstrip(".")
        lst = _json_get(item, before) if before else item
        if not isinstance(lst, list):
            return ""
        vals = [(_json_get(el, after) if after else el) for el in lst]
        return " | ".join("" if v is None else str(v) for v in vals)
    return _apply_json_transform(_json_get(item, path), transform)


def _wait_for_predicate(page: Any, predicate, timeout_ms: int) -> bool:
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        page.wait_for_timeout(200)
    return bool(predicate())


def _is_enabled_clickable(locator: Any) -> bool:
    try:
        if locator.count() == 0 or not locator.is_visible():
            return False
        cls = (locator.get_attribute("class") or "").lower()
        if "disabl" in cls:
            return False
        if (locator.get_attribute("aria-disabled") or "") == "true":
            return False
        return bool(locator.is_enabled())
    except Exception:
        return False


def _paginate_capture_json(
    page: Any,
    action: dict[str, Any],
    *,
    timeout_ms: int,
    overlays: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect rows from a paginated table by capturing the JSON the page already fetches.

    For platforms whose export is encrypted but whose on-page table is XHR/JSON-backed: drive the
    UI (click the query trigger, then the next-page control) like a human, and harvest the JSON
    responses the page receives — no crafted/replayed API calls. Each captured body's
    ``results_path`` array is mapped to columns via ``field_map`` (col -> 'json.path' or
    'json.path|transform'). Pagination stops when collected rows reach ``total_path`` or the
    next-page control is gone/disabled.
    """
    capture_contains = str(action.get("capture_url_contains") or "").strip()
    field_map = dict(action.get("field_map") or {})
    if not capture_contains or not field_map:
        raise BrowserActionError(
            "PAGE_CHANGED", "paginate_capture_json requires capture_url_contains and field_map"
        )
    results_path = str(action.get("results_path") or "data.results")
    total_path = str(action.get("total_path") or "")
    next_selector = str(action.get("next_selector") or "")
    trigger_selector = str(action.get("trigger_selector") or "")
    max_pages = int(action.get("max_pages") or 500)
    page_wait_ms = int(action.get("page_wait_ms") or 10000)

    captured: list[Any] = []

    def _on_response(resp: Any) -> None:
        try:
            if capture_contains in resp.url:
                captured.append(resp.json())
        except Exception:
            pass

    page.on("response", _on_response)
    try:
        if trigger_selector:
            _dismiss_configured_overlays(page, overlays)
            page.locator(trigger_selector).first.click(timeout=timeout_ms)
        if not _wait_for_predicate(page, lambda: len(captured) >= 1, page_wait_ms):
            raise BrowserActionError("PAGE_CHANGED", "paginate_capture_json captured no data response")

        rows: list[dict[str, Any]] = []
        processed = 0
        total: int | None = None
        pages = 0
        while pages < max_pages:
            while processed < len(captured):
                body = captured[processed]
                processed += 1
                pages += 1
                results = _json_get(body, results_path)
                if isinstance(results, list):
                    for elem in results:
                        # Some APIs (e.g. Douyin 资金流水 query_item) return each row as a
                        # JSON-encoded string inside the array; decode it before field extraction.
                        if isinstance(elem, str):
                            try:
                                elem = json.loads(elem)
                            except Exception:
                                continue
                        rows.append({col: _extract_json_field(elem, spec) for col, spec in field_map.items()})
                if total is None and total_path:
                    raw_total = _json_get(body, total_path)
                    if raw_total is not None:
                        try:
                            total = int(raw_total)
                        except (TypeError, ValueError):
                            total = None
            if total is not None and len(rows) >= total:
                break
            if not next_selector:
                break
            nxt = page.locator(next_selector).first
            if not _is_enabled_clickable(nxt):
                break
            before = len(captured)
            try:
                _dismiss_configured_overlays(page, overlays)
                nxt.click(timeout=timeout_ms)
            except Exception as exc:
                logger.info("paginate_capture_json next-page click stopped: %s", exc)
                break
            if not _wait_for_predicate(page, lambda: len(captured) > before, page_wait_ms):
                break
        logger.info(
            "paginate_capture_json done: rows=%s pages=%s total=%s", len(rows), pages, total
        )
        return rows
    finally:
        try:
            page.remove_listener("response", _on_response)
        except Exception:
            pass


def run_playbook_with_playwright(
    message: dict[str, Any],
    *,
    config: PlaywrightRunConfig | None = None,
) -> dict[str, Any]:
    """Execute a v1 browser playbook against real pages via persistent-context Chrome.

    Returns the same TASK_RESULT shape as ``runner.run_message``: success → records + capture
    files + quality_summary; failure → fail_reason + error_info.
    """
    _risk_token = _risk_waiting_cb.set(message.get("on_risk_waiting"))
    try:
        return _run_playbook_with_playwright_inner(message, config=config)
    finally:
        _risk_waiting_cb.reset(_risk_token)


def _run_playbook_with_playwright_inner(
    message: dict[str, Any],
    *,
    config: PlaywrightRunConfig | None = None,
) -> dict[str, Any]:
    config = config or PlaywrightRunConfig.from_env()
    playbook = dict(message.get("playbook_body") or {})
    params = dict(message.get("params") or {})
    company_id = str(message.get("company_id") or params.get("company_id") or "")
    shop_id = str(message.get("shop_id") or params.get("shop_id") or "unknown")
    runtime_profile_ref = str(message.get("runtime_profile_ref") or "")
    job_id = str(message.get("job_id") or "unknown")
    handoff_coordinator = message.get("handoff_coordinator")
    backend_factory = message.get("handoff_backend_factory")
    handoff_event_loop = message.get("handoff_event_loop")

    user_data_dir = build_user_data_dir(
        config=config,
        shop_id=shop_id,
        runtime_profile_ref=runtime_profile_ref,
    )
    download_dir = Path(config.download_root) / shop_id / job_id
    download_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    capture_files: list[dict[str, Any]] = []
    storage_context = {
        "company_id": company_id,
        "shop_id": shop_id,
        "biz_date": str(params.get("biz_date") or ""),
        "sync_job_id": job_id,
    }
    extracted: dict[str, Any] = {}
    steps = [dict(step) for step in playbook.get("steps") or []]
    overlays = _normalize_overlay_configs(playbook.get("overlays"))
    try:
        validate_step_actions(steps)
    except ValueError as exc:
        logger.warning(
            "playwright browser run rejected invalid playbook: job_id=%s error=%s",
            job_id,
            str(exc),
        )
        return {
            "job_id": job_id,
            "status": "failed",
            "fail_reason": "OTHER",
            "error_info": {"message": str(exc)},
        }
    logger.info(
        "playwright browser run starting: job_id=%s shop_id=%s playbook_id=%s "
        "user_data_dir=%s download_dir=%s headless=%s browser_channel=%s window=%sx%s+%s+%s",
        job_id,
        shop_id,
        message.get("playbook_id") or playbook.get("playbook_id") or "",
        user_data_dir,
        str(download_dir),
        config.headless,
        config.browser_channel,
        config.window_width,
        config.window_height,
        config.window_x,
        config.window_y,
    )

    try:
        profile_lock = _profile_file_lock(user_data_dir)
        with profile_lock:
            chrome = launch_chrome(
                user_data_dir=user_data_dir,
                headless=config.headless,
                channel=config.browser_channel,
                timezone_id=config.timezone_id,
                window_width=config.window_width,
                window_height=config.window_height,
                window_x=config.window_x,
                window_y=config.window_y,
            )
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.connect_over_cdp(chrome.cdp_url)
                    context = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
                    page = context.pages[0] if context.pages else context.new_page()
                    _set_browser_window_bounds(page, config)
                    try:
                        for index, step_dict in enumerate(steps):
                            step_action = str(step_dict.get("action") or "").strip()
                            step_id = str(step_dict.get("id") or "").strip()
                            if step_action in {"login", "login_if_needed"}:
                                authenticated = _profile_is_authenticated(page, playbook)
                                if should_skip_login_action(step_dict, authenticated=authenticated):
                                    logger.info(
                                        "browser login skipped because profile is authenticated: "
                                        "job_id=%s step_id=%s",
                                        job_id,
                                        step_dict.get("id") or "",
                                    )
                                    continue
                                logger.info(
                                    "browser login required for profile: job_id=%s step_id=%s diagnostics=%s",
                                    job_id,
                                    step_id,
                                    _profile_auth_check_diagnostics(page, user_data_dir=user_data_dir),
                                )
                            _pause_before_step(
                                page,
                                run_config=config,
                                step_id=step_id,
                                action_name=step_action,
                            )
                            allow_auth_redirect = step_action == "navigate" and any(
                                str(next_step.get("action") or "").strip() in {"login", "login_if_needed"}
                                for next_step in steps[index + 1 :]
                            )
                            result = _execute_action(
                                page,
                                step_dict,
                                params=params,
                                extracted=extracted,
                                capture_files=capture_files,
                                download_dir=download_dir,
                                allow_auth_redirect=allow_auth_redirect,
                                run_config=config,
                                sync_job_id=job_id,
                                storage_context=storage_context,
                                handoff_coordinator=handoff_coordinator,
                                backend_factory=backend_factory,
                                handoff_event_loop=handoff_event_loop,
                                chrome=chrome,
                                overlays=overlays,
                            )
                            if result.get("rows"):
                                rows.extend(result["rows"])
                            if result.get("stop_playbook"):
                                logger.info(
                                    "browser playbook stopped early: job_id=%s step_id=%s",
                                    job_id,
                                    step_id,
                                )
                                break
                    finally:
                        try:
                            browser.close()
                        except Exception:
                            pass
            finally:
                chrome.terminate()
    except BrowserActionError as exc:
        logger.warning(
            "playwright browser run failed: job_id=%s fail_reason=%s error=%s",
            job_id,
            exc.fail_reason,
            str(exc),
        )
        return {
            "job_id": job_id,
            "status": "failed",
            "fail_reason": exc.fail_reason,
            "error_info": {"message": str(exc)},
        }
    except PlaywrightTimeoutError as exc:
        logger.warning(
            "playwright browser run timeout: job_id=%s fail_reason=PAGE_CHANGED error=%s",
            job_id,
            str(exc),
        )
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
        enforce_date=bool(quality_gate.get("enforce_date", True)),
        expected_row_count=summary_row_count if summary_step_id else params.get("expected_row_count"),
        expected_amount_total=summary_amount_total if summary_step_id else params.get("expected_amount_total"),
    )
    if not quality.get("success"):
        logger.warning(
            "playwright browser quality gate failed: job_id=%s fail_reason=%s error=%s",
            job_id,
            quality.get("fail_reason") or "DATA_MISMATCH",
            quality.get("error") or "quality gate failed",
        )
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
