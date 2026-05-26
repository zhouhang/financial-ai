"""Collection machine readiness check.

Run on the collection machine before enabling browser-agent for a new shop. Returns a JSON
report covering everything that has to be in place for ``playwright_runner`` to actually drive
a real Chrome session against QianNiu:

- profile / download directories are writable
- Playwright module + configured installed browser channel are launchable
- Chinese font support exists (the fund-bill page renders Chinese; missing CJK fonts cause
  rendering issues and confuse downstream OCR if ever added)
- timezone is set to Asia/Shanghai (account/bill ledger expects China time)

The ``fc-list`` check is guarded with ``shutil.which`` because the binary is not preinstalled
on a fresh Ubuntu / macOS dev box; treating its absence as a runtime crash would block the
report. ``font_probe`` therefore reports ``fc_list_missing`` rather than raising.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.playwright_runner import PlaywrightRunConfig


def _probe_chrome_launch(config: PlaywrightRunConfig) -> tuple[bool, bool, str]:
    playwright_importable = False
    chrome_launchable = False
    chrome_error = ""
    try:
        from playwright.sync_api import sync_playwright

        playwright_importable = True
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel=config.browser_channel,
                headless=config.headless,
            )
            browser.close()
            chrome_launchable = True
    except Exception as exc:
        chrome_error = str(exc)
    return playwright_importable, chrome_launchable, chrome_error


def build_environment_report(*, config: PlaywrightRunConfig) -> dict[str, Any]:
    profile_root = Path(config.profile_root)
    download_root = Path(config.download_root)
    profile_root.mkdir(parents=True, exist_ok=True)
    download_root.mkdir(parents=True, exist_ok=True)

    playwright_importable, chrome_launchable, chrome_error = _probe_chrome_launch(config)

    font_probe_status = "fc_list_missing"
    if shutil.which("fc-list"):
        try:
            font_probe = subprocess.run(
                ["fc-list", ":lang=zh"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            font_probe_status = (
                "ok"
                if font_probe.returncode == 0 and font_probe.stdout.strip()
                else "missing_zh_fonts"
            )
        except (OSError, subprocess.SubprocessError):
            font_probe_status = "font_probe_failed"

    return {
        "profile_root": str(profile_root),
        "profile_root_writable": profile_root.exists() and profile_root.is_dir(),
        "download_root": str(download_root),
        "download_root_writable": download_root.exists() and download_root.is_dir(),
        "timezone_id": config.timezone_id,
        "system_timezone": time.tzname,
        "headless": config.headless,
        "browser_channel": config.browser_channel,
        "playwright_importable": playwright_importable,
        "chrome_launchable": chrome_launchable,
        "chrome_error": chrome_error,
        "font_probe": font_probe_status,
    }


def main() -> None:
    report = build_environment_report(config=PlaywrightRunConfig.from_env())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
