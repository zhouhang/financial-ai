from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.playwright_runner import _dismiss_configured_overlays


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str, *, visible: bool = False) -> None:
        self.page = page
        self.selector = selector
        self._visible = visible
        self.first = self

    def is_visible(self, timeout: int = 0) -> bool:
        self.page.visibility_checks.append((self.selector, timeout))
        return self._visible

    def click(self, timeout: int = 0) -> None:
        self.page.click_attempts.append((self.selector, timeout))
        if self.selector in self.page.failing_click_selectors:
            raise RuntimeError("not clickable")
        if self.selector not in self.page.visible_selectors:
            raise RuntimeError("not found")
        self.page.clicks.append((self.selector, timeout))


class FakePage:
    def __init__(
        self,
        visible_selectors: set[str],
        *,
        failing_click_selectors: set[str] | None = None,
    ) -> None:
        self.visible_selectors = visible_selectors
        self.failing_click_selectors = failing_click_selectors or set()
        self.visibility_checks: list[tuple[str, int]] = []
        self.click_attempts: list[tuple[str, int]] = []
        self.clicks: list[tuple[str, int]] = []
        self.waits: list[int] = []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector, visible=selector in self.visible_selectors)

    def wait_for_timeout(self, delay_ms: int) -> None:
        self.waits.append(delay_ms)


def test_dismiss_configured_overlays_skips_when_marker_is_missing() -> None:
    page = FakePage({".close"})
    overlays = [
        {
            "id": "finance_survey",
            "markers": [".survey"],
            "close_selectors": [".close"],
        }
    ]

    dismissed = _dismiss_configured_overlays(page, overlays)

    assert dismissed is False
    assert page.click_attempts == []


def test_dismiss_configured_overlays_clicks_first_available_close_selector() -> None:
    page = FakePage({".survey", ".close"})
    overlays = [
        {
            "id": "finance_survey",
            "markers": [".survey"],
            "close_selectors": [".missing", ".close"],
        }
    ]

    dismissed = _dismiss_configured_overlays(page, overlays)

    assert dismissed is True
    assert page.click_attempts == [(".missing", 1000), (".close", 1000)]
    assert page.clicks == [(".close", 1000)]
    assert page.waits == [300]


def test_dismiss_configured_overlays_continues_when_close_clicks_fail() -> None:
    page = FakePage(
        {".survey", ".close-a", ".close-b"},
        failing_click_selectors={".close-a", ".close-b"},
    )
    overlays = [
        {
            "id": "finance_survey",
            "markers": [".survey"],
            "close_selectors": [".close-a", ".close-b"],
        }
    ]

    dismissed = _dismiss_configured_overlays(page, overlays)

    assert dismissed is False
    assert page.click_attempts == [(".close-a", 1000), (".close-b", 1000)]
    assert page.clicks == []
