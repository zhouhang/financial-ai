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

import asyncio
import contextvars
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
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

_risk_waiting_cb: contextvars.ContextVar = contextvars.ContextVar("risk_waiting_cb", default=None)


def _notify_risk_waiting() -> None:
    cb = _risk_waiting_cb.get()
    if cb:
        try:
            cb("RISK_VERIFICATION")
        except Exception:
            logger.exception("on_risk_waiting callback failed")


_AUTH_REDIRECT_MARKERS = (
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

_KNOWN_OVERLAY_MARKERS = (
    "text=预警通知",
    "text=新手引导",
    "text=操作指引",
    "text=功能介绍",
    "text=下次再说",
    ".normal_headTitle__iJ44s:has-text('预警通知')",
    ".driver-popover",
    ".driver-overlay",
)
_KNOWN_OVERLAY_PANEL_TITLE_SELECTORS = (
    "text=重要消息",
    "text=新手引导",
    "text=操作指引",
    "text=功能介绍",
)
_KNOWN_OVERLAY_CONTAINER_SELECTORS = (
    ".normal_container__13Xbj",
    ".container--SMNuCb74",
    ".next-dialog",
    ".next-balloon",
    ".driver-popover",
    "[class*='guide']",
    "[class*='Guide']",
    "[class*='tour']",
    "[class*='Tour']",
)
_KNOWN_DRIVER_POPOVER_CLOSE_SELECTORS = (
    "button.driver-popover-next-btn:has-text('完成')",
    ".driver-popover button.driver-popover-next-btn:has-text('完成')",
    ".driver-popover .driver-popover-next-btn:has-text('完成')",
)
_KNOWN_OVERLAY_CLOSE_SELECTORS = (
    *_KNOWN_DRIVER_POPOVER_CLOSE_SELECTORS,
    ".notify_headRight__XdjnE .next-icon-close_blod",
    "[class*='notify_headRight'] .next-icon-close_blod",
    "[class*='notify_headRight'] [class*='next-icon-close']",
    ".normal_container__13Xbj button:has-text('知道了')",
    ".normal_container__13Xbj button:has-text('确定')",
    ".normal_container__13Xbj button:has-text('关闭')",
    ".normal_container__13Xbj button:has-text('我知道了')",
    ".normal_container__13Xbj [role='button']:has-text('知道了')",
    ".normal_container__13Xbj [role='button']:has-text('确定')",
    ".normal_container__13Xbj .next-dialog-close",
    ".normal_container__13Xbj .next-icon-close",
    ".container--SMNuCb74 button:has-text('知道了')",
    ".container--SMNuCb74 button:has-text('确定')",
    ".container--SMNuCb74 button:has-text('关闭')",
    ".container--SMNuCb74 [role='button']:has-text('知道了')",
    ".container--SMNuCb74 [role='button']:has-text('确定')",
    ".container--SMNuCb74 .next-dialog-close",
    ".container--SMNuCb74 .next-icon-close",
    ".next-dialog button:has-text('知道了')",
    ".next-dialog button:has-text('我知道了')",
    ".next-dialog button:has-text('完成')",
    ".next-dialog button:has-text('下次再说')",
    ".next-dialog button:has-text('跳过')",
    ".next-dialog button:has-text('关闭')",
    ".next-dialog [role='button']:has-text('知道了')",
    ".next-dialog [role='button']:has-text('我知道了')",
    ".next-dialog [role='button']:has-text('完成')",
    ".next-dialog [role='button']:has-text('下次再说')",
    ".next-dialog [role='button']:has-text('跳过')",
    ".next-dialog .next-dialog-close",
    ".next-dialog .next-icon-close",
    ".next-balloon button:has-text('知道了')",
    ".next-balloon button:has-text('我知道了')",
    ".next-balloon button:has-text('完成')",
    ".next-balloon button:has-text('下次再说')",
    ".next-balloon button:has-text('跳过')",
    ".next-balloon .next-balloon-close",
    "[class*='guide'] button:has-text('知道了')",
    "[class*='guide'] button:has-text('完成')",
    "[class*='guide'] button:has-text('跳过')",
    "[class*='Guide'] button:has-text('知道了')",
    "[class*='Guide'] button:has-text('完成')",
    "[class*='Guide'] button:has-text('跳过')",
)

_KNOWN_OVERLAY_CLOSE_POINT_SCRIPT = r"""
() => {
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0';
  };
  const textOf = (el) => (el && el.innerText ? el.innerText : '').trim();
  const all = Array.from(document.querySelectorAll('body *')).filter(visible);
  const warningCandidates = all
    .filter((el) => textOf(el).includes('预警通知'))
    .sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return (ar.width * ar.height) - (br.width * br.height);
    });
  const warning = warningCandidates[0];
  if (!warning) return { present: false };

  const importantCandidates = all
    .filter((el) => textOf(el).includes('重要消息'))
    .sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return (ar.width * ar.height) - (br.width * br.height);
    });
  const important = importantCandidates[0];
  const warningRect = warning.getBoundingClientRect();
  const importantRect = important ? important.getBoundingClientRect() : warningRect;
  const panelLeft = Math.min(importantRect.left, warningRect.left) - 24;
  const panelTop = Math.min(importantRect.top, warningRect.top) - 24;
  const panelRight = Math.max(importantRect.right, warningRect.right) + 260;
  const panelBottom = Math.max(importantRect.bottom, warningRect.bottom) + 160;
  const candidates = all
    .map((el) => {
      const rect = el.getBoundingClientRect();
      const text = textOf(el);
      const label = [
        el.getAttribute('aria-label') || '',
        el.getAttribute('title') || '',
        el.getAttribute('class') || '',
        text,
      ].join(' ');
      return { el, rect, text, label };
    })
    .filter(({ rect, label }) => {
      if (rect.left < panelLeft || rect.right > panelRight) return false;
      if (rect.top < panelTop || rect.bottom > panelBottom) return false;
      if (rect.top > warningRect.top + 45) return false;
      if (rect.width > 48 || rect.height > 48) return false;
      return /关闭|close|icon|×|✕|\bx\b/i.test(label);
    })
    .sort((a, b) => (b.rect.left - a.rect.left) || (a.rect.top - b.rect.top));
  const target = candidates[0];
  if (!target) return null;
  return {
    x: target.rect.left + target.rect.width / 2,
    y: target.rect.top + target.rect.height / 2,
    panel_left: panelLeft,
    panel_top: panelTop,
    panel_right: panelRight,
    panel_bottom: panelBottom,
    source: target.label.slice(0, 120),
  };
}
"""


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
    if any(marker in risk_text or marker in lowered_risk_text for marker in _AUTH_REDIRECT_MARKERS):
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
    chrome: Any = None,
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
                chrome=chrome,
            )
        if detected:
            raise BrowserActionError(detected, f"navigate detected {detected}: url={_page_url(page)}")
        return {}
    if name == "click":
        record_time_as = str(action.get("record_time_as") or "").strip()
        if record_time_as:
            extracted[record_time_as] = _now_local_iso()
        _click_like_human(page, selector, timeout_ms=timeout_ms, run_config=run_config)
        return {}
    if name == "fill":
        page.fill(selector, _resolve_value(action, params, extracted), timeout=timeout_ms)
        return {}
    if name == "set_date":
        _set_date_value(page, selector, _resolve_value(action, params, extracted), timeout_ms=timeout_ms)
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
        )
    if name == "download":
        with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
            _click_like_human(page, selector, timeout_ms=timeout_ms, run_config=run_config)
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
        )
    if name == "parse_table":
        source = str(action.get("source") or "last_download")
        fmt = str(action.get("format") or "csv").lower()
        path = extracted.get(source) or capture_files[-1].get("local_path") or capture_files[-1]["storage_path"]
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
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
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

    login_context = _find_login_context(
        page,
        username_selector=username_selector,
        password_selector=password_selector,
        submit_selector=submit_selector,
        username=username,
        password=password,
        timeout_ms=timeout_ms,
        run_config=run_config,
        sync_job_id=sync_job_id,
        handoff_coordinator=handoff_coordinator,
        backend_factory=backend_factory,
        chrome=chrome,
    )
    post_login_wait_selector = str(action.get("post_login_wait_selector") or "").strip()
    if post_login_wait_selector:
        _wait_for_post_login_selector(
            page,
            login_context=login_context,
            selector=post_login_wait_selector,
            timeout_ms=timeout_ms,
            run_config=run_config,
            sync_job_id=sync_job_id,
            handoff_coordinator=handoff_coordinator,
            backend_factory=backend_factory,
            chrome=chrome,
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
    sync_job_id: str = "",
    handoff_coordinator: RemoteControlCoordinator | None = None,
    backend_factory: Any = None,
    chrome: Any = None,
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
                risk_cleared = _wait_for_risk_to_clear_with_handoff(
                    page,
                    candidates,
                    timeout_ms=int(max(1, (risk_deadline - now) * 1000)),
                    poll_interval_ms=1000,
                    sync_job_id=sync_job_id,
                    coordinator=handoff_coordinator,
                    backend_factory=backend_factory,
                    chrome=chrome,
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


def _run_async_safely(coro: Any) -> None:
    try:
        asyncio.run(coro)
    except Exception:
        logger.exception("handoff async callback failed")


def _risk_cleared(contexts: list[Any]) -> bool:
    return not any(_detect_auth_or_risk(context) == "RISK_VERIFICATION" for context in contexts)


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
) -> bool:
    if coordinator is None:
        return _wait_for_risk_to_clear(
            contexts,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )
    if backend_factory is not None:
        backend = backend_factory.create_backend(page=page, chrome=chrome, risk_contexts=contexts)
    else:
        backend = PlaywrightControlBackend(page=page, risk_contexts=contexts)
    try:
        backend.bind_window()
    except Exception:
        logger.exception("OS 后端窗口绑定失败,降级为不可控等待")
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
                ))
            if _risk_cleared(contexts):
                _run_async_safely(coordinator.emit_status({
                    "type": "handoff_completed",
                    "sync_job_id": sync_job_id,
                    "handoff_session_id": backend.handoff_session_id,
                    "controller_id": backend.controller_id,
                }))
                return True
            if backend.pop_resume_check_requested() and not _risk_cleared(contexts):
                _run_async_safely(coordinator.emit_status({
                    "type": "handoff_still_blocked",
                    "sync_job_id": sync_job_id,
                    "handoff_session_id": backend.handoff_session_id,
                    "controller_id": backend.controller_id,
                    "reason": "risk verification still blocked",
                }))
            remaining_ms = int(max(1, (deadline - time.monotonic()) * 1000))
            wait_ms = min(max(1, poll_interval_ms), remaining_ms)
            _wait_for_timeout(page, wait_ms)
        return _risk_cleared(contexts)
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


def _locator_bounding_box(locator: Any, *, timeout_ms: int = 300) -> dict[str, float] | None:
    try:
        box = locator.bounding_box(timeout=timeout_ms)
    except TypeError:
        try:
            box = locator.bounding_box()
        except Exception:
            return None
    except Exception:
        return None
    if not isinstance(box, dict):
        return None
    try:
        x = float(box.get("x") or 0)
        y = float(box.get("y") or 0)
        width = float(box.get("width") or 0)
        height = float(box.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def _box_is_reasonable_overlay_card(box: dict[str, float]) -> bool:
    width = box["width"]
    height = box["height"]
    # QianNiu's outer .container--SMNuCb74 can be a page-wide top bar such as 1280x65.
    # Clicking its top-right hits the page chrome area, not the notice card close button.
    if width >= 900 and height <= 120:
        return False
    if height < 80:
        return False
    return True


def _click_dom_detected_overlay_close(context: Any) -> bool:
    evaluate = getattr(context, "evaluate", None)
    mouse = getattr(context, "mouse", None)
    mouse_click = getattr(mouse, "click", None)
    if not callable(evaluate) or not callable(mouse_click):
        return False
    try:
        point = evaluate(_KNOWN_OVERLAY_CLOSE_POINT_SCRIPT)
    except Exception:
        return False
    if not isinstance(point, dict):
        return False
    try:
        x = float(point.get("x"))
        y = float(point.get("y"))
    except (TypeError, ValueError):
        return False
    if x <= 0 or y <= 0:
        return False
    try:
        panel_left = float(point.get("panel_left"))
        panel_top = float(point.get("panel_top"))
        panel_right = float(point.get("panel_right"))
        panel_bottom = float(point.get("panel_bottom"))
    except (TypeError, ValueError):
        panel_left = panel_top = panel_right = panel_bottom = None
    if panel_left is not None and not (
        panel_left <= x <= panel_right and panel_top <= y <= panel_bottom
    ):
        logger.info("browser known overlay dom close rejected outside panel: point=%s", point)
        return False
    try:
        mouse_click(x, y)
        _wait_for_timeout(context, 300)
        logger.info(
            "browser known overlay dom close clicked: point=%s x=%s y=%s",
            point,
            x,
            y,
        )
        return True
    except Exception:
        return False


def _click_overlay_panel_header_close(context: Any) -> bool:
    mouse = getattr(context, "mouse", None)
    mouse_click = getattr(mouse, "click", None)
    if not callable(mouse_click):
        return False
    title_box = None
    title_selector = ""
    for selector in _KNOWN_OVERLAY_PANEL_TITLE_SELECTORS:
        locator = _safe_first_locator(context, selector)
        if locator is None or not _locator_visible(locator, timeout_ms=300):
            continue
        title_box = _locator_bounding_box(locator, timeout_ms=300)
        if title_box:
            title_selector = selector
            break
    if not title_box:
        return False

    for container_selector in _KNOWN_OVERLAY_CONTAINER_SELECTORS:
        container_locator = _safe_first_locator(context, container_selector)
        if container_locator is None:
            continue
        container_box = _locator_bounding_box(container_locator, timeout_ms=300)
        if not container_box or not _box_is_reasonable_overlay_card(container_box):
            continue
        if container_box["y"] < title_box["y"] - 10:
            continue
        x = container_box["x"] + container_box["width"] - 12
        y = title_box["y"] + min(12, max(6, title_box["height"] / 2))
        try:
            mouse_click(x, y)
            _wait_for_timeout(context, 300)
            logger.info(
                "browser known overlay panel header close clicked: "
                "title_selector=%s title_box=%s container_selector=%s container_box=%s x=%s y=%s",
                title_selector,
                title_box,
                container_selector,
                container_box,
                x,
                y,
            )
            return True
        except Exception:
            continue
    return False


def _click_overlay_top_right_close(context: Any) -> bool:
    mouse = getattr(context, "mouse", None)
    mouse_click = getattr(mouse, "click", None)
    if not callable(mouse_click):
        return False
    for selector in _KNOWN_OVERLAY_CONTAINER_SELECTORS:
        locator = _safe_first_locator(context, selector)
        if locator is None:
            continue
        box = _locator_bounding_box(locator, timeout_ms=300)
        if not box:
            continue
        if not _box_is_reasonable_overlay_card(box):
            logger.info(
                "browser known overlay top-right close skipped unsuitable container: "
                "selector=%s box=%s",
                selector,
                box,
            )
            continue
        x = box["x"] + max(8, box["width"] - 16)
        y = box["y"] + 16
        try:
            mouse_click(x, y)
            _wait_for_timeout(context, 300)
            logger.info(
                "browser known overlay top-right close clicked: selector=%s box=%s x=%s y=%s",
                selector,
                box,
                x,
                y,
            )
            return True
        except Exception:
            continue
    return False


def _dismiss_known_overlays(context: Any) -> bool:
    """Close known QianNiu non-risk overlays that can intercept ordinary clicks."""
    has_overlay = False
    for marker in _KNOWN_OVERLAY_MARKERS:
        locator = _safe_first_locator(context, marker)
        if locator is not None and _locator_visible(locator, timeout_ms=300):
            has_overlay = True
            break
    if not has_overlay:
        return False

    dismissed = False
    for selector in _KNOWN_DRIVER_POPOVER_CLOSE_SELECTORS:
        locator = _safe_first_locator(context, selector)
        if locator is None:
            continue
        try:
            locator.click(timeout=1000)
            dismissed = True
            _wait_for_timeout(context, 300)
            break
        except Exception:
            continue
    if dismissed:
        logger.info("browser known overlay dismissed: overlay=driver_popover clicked=True")
        return True

    keyboard = getattr(context, "keyboard", None)
    press = getattr(keyboard, "press", None)
    if callable(press):
        try:
            press("Escape")
        except Exception:
            pass
        _wait_for_timeout(context, 200)

    for selector in _KNOWN_OVERLAY_CLOSE_SELECTORS:
        locator = _safe_first_locator(context, selector)
        if locator is None:
            continue
        try:
            locator.click(timeout=1000)
            dismissed = True
            _wait_for_timeout(context, 300)
            break
        except Exception:
            continue
    if not dismissed:
        dismissed = _click_dom_detected_overlay_close(context)
    if not dismissed:
        dismissed = _click_overlay_panel_header_close(context)
    if not dismissed:
        dismissed = _click_overlay_top_right_close(context)
    logger.info("browser known overlay dismissed: overlay=qianniu_warning_notice clicked=%s", dismissed)
    return True


def _click_like_human(
    context: Any,
    selector: str,
    *,
    timeout_ms: int,
    run_config: PlaywrightRunConfig | None,
) -> None:
    _dismiss_known_overlays(context)
    _pause_before_click(context, run_config=run_config)
    try:
        context.click(selector, timeout=timeout_ms)
    except Exception as exc:
        if _dismiss_known_overlays(context):
            _pause_before_click(context, run_config=run_config)
            context.click(selector, timeout=timeout_ms)
            return
        raise exc


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


def _set_date_value(page: Any, selector: str, value: str, *, timeout_ms: int) -> None:
    if not selector or not value:
        raise BrowserActionError("PAGE_CHANGED", "set_date requires selector and value")
    _dismiss_known_overlays(page)
    _close_open_datepicker_overlay(page)
    locator = page.locator(selector).first
    locator.click(timeout=timeout_ms)
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


def _select_checkboxes(
    page: Any,
    action: dict[str, Any],
    *,
    params: dict[str, Any],
    extracted: dict[str, Any],
    timeout_ms: int,
) -> dict[str, Any]:
    selector = str(action.get("selector") or "").strip()
    if not selector:
        raise BrowserActionError("PAGE_CHANGED", "select_checkboxes requires selector")
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
            clicked = _click_exact_checkbox_label(root, label_selector=label_selector, label=label)
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
    chrome: Any = None,
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
                        _wait_for_risk_to_clear_with_handoff(
                            page,
                            contexts,
                            timeout_ms=manual_timeout_ms,
                            poll_interval_ms=1000,
                            sync_job_id=sync_job_id,
                            coordinator=handoff_coordinator,
                            backend_factory=backend_factory,
                            chrome=chrome,
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
    date_range_matches = re.findall(
        r"(?<!\d)(20\d{2}[-/.]\d{2}[-/.]\d{2}|20\d{6}|\d{1,2}[-/.]\d{1,2})(?!\d)\s*"
        r"(?:~|至|到|_|—|–|\s-\s)\s*"
        r"(?<!\d)(20\d{2}[-/.]\d{2}[-/.]\d{2}|20\d{6}|\d{1,2}[-/.]\d{1,2})(?!\d)",
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
    compact_text = " ".join(str(row_text or "").split())
    matches = re.findall(
        r"20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s+\d{1,2}:\d{2}(?::\d{2})?",
        compact_text,
    )
    parsed = [item for item in (_parse_local_datetime(match) for match in matches) if item is not None]
    if not parsed:
        return None
    if requested_after is None:
        return parsed[0]
    return min(parsed, key=lambda item: abs((item - requested_after).total_seconds()))


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
    detail_selector = str(
        action.get("detail_selector")
        or (
            "body"
            f":has-text({_playwright_text_arg('订单导出报表')})"
            f":has-text({_playwright_text_arg(download_button_text)})"
        )
    ).strip()
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
        if not checked_any_row:
            return None, "no_export_rows"
        return None, nearest_skipped_time

    def _refresh_export_list() -> None:
        if refresh_selector:
            try:
                page.click(refresh_selector, timeout=min(10000, timeout_ms), force=True)
                return
            except Exception as exc:
                logger.info("qianniu export list refresh click failed, reloading page: %s", exc)
        page.reload(wait_until="domcontentloaded", timeout=min(30000, timeout_ms))

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
                button.click(timeout=min(30000, timeout_ms))
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

    raise BrowserActionError(
        "PAGE_CHANGED",
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
    tokens = _date_tokens(target_date)
    if not history_row_selectors or not tokens:
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
        _click_first_available_selector(
            page,
            history_open_selectors,
            timeout_ms=history_open_timeout_ms,
            force=True,
        )

    def _find_completed_row() -> Any | None:
        for row_selector in history_row_selectors:
            rows = page.locator(row_selector)
            for index, compact_text in _locator_text_rows(rows, timeout_ms=timeout_ms):
                matches_date = _history_row_matches_target_date(compact_text, str(target_date))
                matches_status = status_text in compact_text
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
            closed = _click_first_available_selector(
                page,
                history_close_selectors,
                timeout_ms=history_refresh_close_timeout_ms,
                force=True,
            )
        except Exception as exc:
            closed = False
            logger.info("browser history drawer close skipped before refresh: %s", exc)
        if closed:
            page.wait_for_timeout(min(1000, max(0, history_refresh_interval_ms)))
        try:
            _open_history()
        except Exception as exc:
            logger.info("browser history reopen skipped; keeping current history list: %s", exc)

    try:
        _open_history()
    except Exception as exc:
        logger.info("browser history open skipped; checking current history list: %s", exc)
    deadline = time.monotonic() + (timeout_ms / 1000)
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
        raise BrowserActionError("PAGE_CHANGED", f"history download row not completed for {target_date}")

    with page.expect_download(timeout=int(action.get("download_timeout_ms") or 600000)) as info:
        row.locator(download_selector).click(timeout=timeout_ms)
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
    company_id = str(message.get("company_id") or params.get("company_id") or "")
    shop_id = str(message.get("shop_id") or params.get("shop_id") or "unknown")
    runtime_profile_ref = str(message.get("runtime_profile_ref") or "")
    job_id = str(message.get("job_id") or "unknown")
    handoff_coordinator = message.get("handoff_coordinator")
    backend_factory = message.get("handoff_backend_factory")

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
                            chrome=chrome,
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
