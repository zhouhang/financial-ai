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

import contextvars
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_browser_agent.chrome_launcher import launch_chrome
from finance_browser_agent.quality_gate import validate_rows
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_risk_waiting_cb: contextvars.ContextVar = contextvars.ContextVar("risk_waiting_cb", default=None)


def _notify_risk_waiting() -> None:
    cb = _risk_waiting_cb.get()
    if cb:
        try:
            cb("RISK_VERIFICATION")
        except Exception:
            logger.exception("on_risk_waiting callback failed")


_AUTH_REDIRECT_MARKERS = (
    "login.taobao.com",
    "passport",
    "请先登录",
    "登录后继续",
)
_RISK_MARKERS = (
    "验证码",
    "滑块",
    "拖动滑块",
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
    "滑块",
    "拖动滑块",
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
    step_delay_min_ms: int = 1000
    step_delay_max_ms: int = 3000
    click_delay_min_ms: int = 800
    click_delay_max_ms: int = 1800
    type_delay_ms: int = 160
    risk_manual_timeout_ms: int = 300000

    @classmethod
    def from_env(cls) -> "PlaywrightRunConfig":
        default_root = Path.home() / "tally-browser-agent"
        return cls(
            profile_root=os.getenv("BROWSER_AGENT_PROFILE_ROOT", str(default_root / "profiles")),
            download_root=os.getenv("BROWSER_AGENT_DOWNLOAD_ROOT", str(default_root / "downloads")),
            headless=os.getenv("BROWSER_AGENT_HEADLESS", "0") == "1",
            timezone_id=os.getenv("BROWSER_AGENT_TIMEZONE", "Asia/Shanghai"),
            browser_channel=os.getenv("BROWSER_AGENT_BROWSER_CHANNEL", "chrome").strip() or "chrome",
            step_delay_min_ms=_env_int("BROWSER_AGENT_STEP_DELAY_MIN_MS", 1000),
            step_delay_max_ms=_env_int("BROWSER_AGENT_STEP_DELAY_MAX_MS", 3000),
            click_delay_min_ms=_env_int("BROWSER_AGENT_CLICK_DELAY_MIN_MS", 800),
            click_delay_max_ms=_env_int("BROWSER_AGENT_CLICK_DELAY_MAX_MS", 1800),
            type_delay_ms=_env_int("BROWSER_AGENT_TYPE_DELAY_MS", 160),
            risk_manual_timeout_ms=_env_int("BROWSER_AGENT_RISK_MANUAL_TIMEOUT_MS", 300000),
        )


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


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
    visible_text = ""
    try:
        locator_factory = getattr(page, "locator", None)
        if callable(locator_factory):
            visible_text = locator_factory("body").first.inner_text(timeout=500) or ""
    except Exception:
        visible_text = ""
    try:
        body = page.content() or ""
    except Exception:
        body = ""
    risk_text = visible_text or body
    lowered = body.lower()
    lowered_risk_text = risk_text.lower()
    # Risk pages often live under login/passport URLs. Prefer strong in-page risk signals
    # so operators see the actionable cause instead of a generic auth-expired result.
    if any(marker in risk_text or marker in lowered_risk_text for marker in _STRONG_RISK_MARKERS):
        return "RISK_VERIFICATION"
    if ("验证码" in risk_text and any(marker in risk_text for marker in ("请输入", "获取", "发送", "手机"))) or any(
        marker in lowered_risk_text for marker in ("captcha", "risk")
    ):
        return "RISK_VERIFICATION"
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if any(marker in url for marker in ("login.taobao.com", "passport")):
        return "AUTH_EXPIRED"
    if any(marker in body or marker in lowered for marker in _AUTH_REDIRECT_MARKERS):
        return "AUTH_EXPIRED"
    return None


def _page_url(page: Any) -> str:
    try:
        return str(page.url or "")
    except Exception:
        return ""


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
    allow_auth_redirect: bool = False,
    run_config: PlaywrightRunConfig | None = None,
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
        if detected == "AUTH_EXPIRED" and allow_auth_redirect:
            return {"auth_required": True}
        if detected == "RISK_VERIFICATION":
            detected = _await_navigate_risk_clearance(page, run_config=run_config)
        if detected:
            raise BrowserActionError(detected, f"navigate detected {detected}")
        return {}
    if name == "click":
        _click_like_human(page, selector, timeout_ms=timeout_ms, run_config=run_config)
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
        _execute_login_action(
            page,
            action,
            params=params,
            extracted=extracted,
            timeout_ms=timeout_ms,
            run_config=run_config,
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
    if name == "download":
        with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
            _click_like_human(page, selector, timeout_ms=timeout_ms, run_config=run_config)
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
    if name == "parse_table":
        source = str(action.get("source") or "last_download")
        fmt = str(action.get("format") or "csv").lower()
        path = extracted.get(source) or capture_files[-1]["storage_path"]
        rows, encoding = _parse_downloaded_table_with_metadata(Path(str(path)), fmt=fmt)
        if capture_files:
            capture_files[-1]["encoding"] = encoding
            capture_files[-1]["row_count"] = len(rows)
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

    login_context = _find_login_context(
        page,
        username_selector=username_selector,
        password_selector=password_selector,
        submit_selector=submit_selector,
        username=username,
        password=password,
        timeout_ms=timeout_ms,
        run_config=run_config,
    )
    post_login_wait_selector = str(action.get("post_login_wait_selector") or "").strip()
    if post_login_wait_selector:
        _wait_for_post_login_selector(
            page,
            login_context=login_context,
            selector=post_login_wait_selector,
            timeout_ms=timeout_ms,
            run_config=run_config,
        )


def _find_login_context(
    page: Any,
    *,
    username_selector: str,
    password_selector: str,
    submit_selector: str,
    username: str,
    password: str,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None = None,
) -> Any:
    attempt_timeout_ms = min(timeout_ms, _LOGIN_SELECTOR_ATTEMPT_TIMEOUT_MS)
    last_error: Exception | None = None
    password_mode_clicked = False
    risk_deadline: float | None = None
    deadline = time.monotonic() + (max(timeout_ms, attempt_timeout_ms) / 1000)
    while time.monotonic() <= deadline:
        candidates = _login_candidates(page)
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
                _click_like_human(
                    candidate,
                    submit_selector,
                    timeout_ms=interaction_timeout_ms,
                    run_config=run_config,
                )
                return candidate
            except Exception as exc:
                last_error = exc
        detected_states = [_detect_auth_or_risk(candidate) for candidate in candidates]
        if "RISK_VERIFICATION" in detected_states:
            manual_timeout_ms = int(run_config.risk_manual_timeout_ms if run_config else 0)
            if manual_timeout_ms <= 0:
                raise BrowserActionError("RISK_VERIFICATION", "login page requires risk verification")
            now = time.monotonic()
            if risk_deadline is None:
                risk_deadline = now + manual_timeout_ms / 1000
                deadline = max(deadline, risk_deadline)
                logger.warning(
                    "browser login risk verification waiting for manual completion: timeout_ms=%s",
                    manual_timeout_ms,
                )
                _notify_risk_waiting()
            if now <= risk_deadline:
                risk_cleared = _wait_for_risk_to_clear(
                    candidates,
                    timeout_ms=int(max(1, (risk_deadline - now) * 1000)),
                    poll_interval_ms=1000,
                )
                if risk_cleared:
                    continue
            raise BrowserActionError(
                "RISK_VERIFICATION",
                "login page risk verification was not completed",
            )
        if not password_mode_clicked:
            password_mode_clicked = _try_click_password_login_mode(
                candidates,
                timeout_ms=attempt_timeout_ms,
            )
        _wait_for_timeout(page, min(1000, attempt_timeout_ms))
    raise BrowserActionError(
        "PAGE_CHANGED",
        f"login fields not found in page or child frames: {last_error}",
    )


def _login_candidates(page: Any) -> list[Any]:
    return [page, *list(getattr(page, "frames", []) or [])]


def _try_click_password_login_mode(candidates: list[Any], *, timeout_ms: int) -> bool:
    for candidate in candidates:
        for selector in _DEFAULT_PASSWORD_LOGIN_SELECTORS:
            try:
                candidate.click(selector, timeout=timeout_ms)
                return True
            except Exception:
                continue
    return False


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


def _wait_for_risk_to_clear(
    contexts: list[Any],
    *,
    timeout_ms: int,
    poll_interval_ms: int = 1000,
) -> bool:
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    last_context = contexts[0] if contexts else None
    while time.monotonic() <= deadline:
        if not any(_detect_auth_or_risk(context) == "RISK_VERIFICATION" for context in contexts):
            return True
        remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
        wait_ms = min(max(1, poll_interval_ms), remaining_ms)
        _wait_for_timeout(last_context, wait_ms)
    return not any(_detect_auth_or_risk(context) == "RISK_VERIFICATION" for context in contexts)


def _await_navigate_risk_clearance(page: Any, *, run_config: "PlaywrightRunConfig | None") -> str | None:
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
    cleared = _wait_for_risk_to_clear(
        _login_candidates(page),
        timeout_ms=manual_timeout_ms,
        poll_interval_ms=1000,
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


def _click_like_human(
    context: Any,
    selector: str,
    *,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None,
) -> None:
    _pause_before_click(context, run_config=run_config)
    context.click(selector, timeout=timeout_ms)


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
    locator.click(timeout=timeout_ms)
    try:
        if locator.input_value(timeout=timeout_ms) == value:
            return
    except Exception:
        pass
    locator.fill("", timeout=timeout_ms)
    locator.type(value, delay=type_delay_ms, timeout=timeout_ms)


def _wait_for_post_login_selector(
    page: Any,
    *,
    login_context: Any,
    selector: str,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None = None,
) -> None:
    contexts = [login_context]
    if page is not login_context:
        contexts.append(page)
    last_error: Exception | None = None
    last_detected: str | None = None
    risk_detected = False
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000)
    while time.monotonic() <= deadline:
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
                        _wait_for_risk_to_clear(
                            contexts,
                            timeout_ms=manual_timeout_ms,
                            poll_interval_ms=1000,
                        )
        for context in contexts:
            remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
            try:
                context.wait_for_selector(selector, timeout=min(remaining_ms, 2000))
                return
            except Exception as exc:
                last_error = exc
    if risk_detected:
        raise BrowserActionError("RISK_VERIFICATION", f"post-login risk verification not completed: {last_error}")
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

    deadline = time.monotonic() + (timeout_ms / 1000)
    row = None
    while time.monotonic() <= deadline:
        rows = page.locator(selector)
        for index in range(rows.count()):
            candidate = rows.nth(index)
            text = candidate.inner_text(timeout=min(timeout_ms, 5000))
            compact_text = " ".join(str(text or "").split())
            if (
                any(token in compact_text for token in tokens)
                and "已完成" in compact_text
                and "下载" in compact_text
            ):
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


class BrowserActionError(Exception):
    def __init__(self, fail_reason: str, message: str) -> None:
        super().__init__(message)
        self.fail_reason = fail_reason


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


def _parse_downloaded_table_with_metadata(path: Path, *, fmt: str) -> tuple[list[dict[str, Any]], str]:
    """Parse a downloaded CSV/XLSX file and return rows plus detected encoding."""
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
    """Parse a downloaded CSV/XLSX file into a list of row dicts.

    pandas is lazy-imported because the synthetic test runner never needs it.
    """
    rows, _encoding = _parse_downloaded_table_with_metadata(path, fmt=fmt)
    return rows


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

    rows: list[dict[str, Any]] = []
    capture_files: list[dict[str, Any]] = []
    extracted: dict[str, Any] = {}
    steps = [dict(step) for step in playbook.get("steps") or []]
    logger.info(
        "playwright browser run starting: job_id=%s shop_id=%s playbook_id=%s "
        "user_data_dir=%s download_dir=%s headless=%s browser_channel=%s",
        job_id,
        shop_id,
        message.get("playbook_id") or playbook.get("playbook_id") or "",
        user_data_dir,
        str(download_dir),
        config.headless,
        config.browser_channel,
    )

    try:
        chrome = launch_chrome(
            user_data_dir=user_data_dir,
            headless=config.headless,
            channel=config.browser_channel,
            timezone_id=config.timezone_id,
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(chrome.cdp_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
                page = context.pages[0] if context.pages else context.new_page()
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
                                "browser login required for profile: job_id=%s step_id=%s",
                                job_id,
                                step_id,
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
                        )
                        if result.get("rows"):
                            rows.extend(result["rows"])
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
