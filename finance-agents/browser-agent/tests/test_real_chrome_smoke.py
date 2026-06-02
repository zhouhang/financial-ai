from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.playwright_runner import PlaywrightRunConfig


@pytest.mark.skipif(
    os.getenv("BROWSER_AGENT_RUN_REAL_CHROME_TEST") != "1",
    reason="set BROWSER_AGENT_RUN_REAL_CHROME_TEST=1 in a real GUI session to launch Chrome",
)
def test_real_google_chrome_launches_in_headed_persistent_context() -> None:
    """Production smoke: installed Google Chrome Stable can be driven by Playwright.

    This test intentionally launches a real headed Chrome, so it is opt-in and must be run
    from the collection machine's normal GUI session, not from the default sandboxed unit-test
    path.
    """
    from playwright.sync_api import sync_playwright

    config = PlaywrightRunConfig.from_env()
    profile_dir = tempfile.mkdtemp(prefix="tally-real-chrome-smoke-")
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            profile_dir,
            channel=config.browser_channel,
            headless=config.headless,
            accept_downloads=True,
            timezone_id=config.timezone_id,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("about:blank")
            assert "about:blank" in page.url
        finally:
            context.close()
