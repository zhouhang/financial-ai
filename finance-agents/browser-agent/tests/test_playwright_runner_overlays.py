from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.playwright_runner import _dismiss_known_overlays


class FakeLocator:
    def __init__(
        self,
        page: "FakePage",
        selector: str,
        *,
        visible: bool = False,
        box: dict[str, float] | None = None,
    ) -> None:
        self.page = page
        self.selector = selector
        self._visible = visible
        self._box = box
        self.first = self

    def is_visible(self, timeout: int = 0) -> bool:
        self.page.visibility_checks.append((self.selector, timeout))
        return self._visible

    def click(self, timeout: int = 0) -> None:
        if self.selector in self.page.failing_click_selectors or self.selector not in self.page.visible_selectors:
            raise RuntimeError("not clickable")
        self.page.events.append(("click", self.selector, timeout))
        self.page.clicks.append((self.selector, timeout))

    def locator(self, selector: str) -> "FakeLocator":
        return FakeLocator(self.page, f"{self.selector} >> {selector}", visible=True)

    def bounding_box(self, timeout: int = 0) -> dict[str, float] | None:
        self.page.bounding_box_checks.append((self.selector, timeout))
        return self._box


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page
        self.pressed: list[str] = []

    def press(self, key: str) -> None:
        self.page.events.append(("press", key))
        self.pressed.append(key)


class FakeMouse:
    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


class FakePage:
    def __init__(
        self,
        visible_selectors: set[str],
        *,
        boxes: dict[str, dict[str, float]] | None = None,
        failing_click_selectors: set[str] | None = None,
        evaluate_result: dict[str, float | str] | None = None,
    ) -> None:
        self.visible_selectors = visible_selectors
        self.boxes = boxes or {}
        self.failing_click_selectors = failing_click_selectors or set()
        self.evaluate_result = evaluate_result
        self.evaluate_calls: list[str] = []
        self.visibility_checks: list[tuple[str, int]] = []
        self.bounding_box_checks: list[tuple[str, int]] = []
        self.clicks: list[tuple[str, int]] = []
        self.events: list[tuple] = []
        self.keyboard = FakeKeyboard(self)
        self.mouse = FakeMouse()

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(
            self,
            selector,
            visible=selector in self.visible_selectors,
            box=self.boxes.get(selector),
        )

    def wait_for_timeout(self, delay_ms: int) -> None:
        return None

    def evaluate(self, script: str) -> dict[str, float | str] | None:
        self.evaluate_calls.append(script)
        return self.evaluate_result


def test_dismiss_known_overlays_closes_qianniu_warning_notice() -> None:
    page = FakePage({"text=预警通知", ".notify_headRight__XdjnE .next-icon-close_blod"})

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.keyboard.pressed == ["Escape"]
    assert page.clicks == [(".notify_headRight__XdjnE .next-icon-close_blod", 1000)]


def test_dismiss_known_overlays_uses_qianniu_notify_head_close_icon() -> None:
    page = FakePage({"text=预警通知", ".notify_headRight__XdjnE .next-icon-close_blod"})

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.clicks[0] == (".notify_headRight__XdjnE .next-icon-close_blod", 1000)


def test_dismiss_known_overlays_clicks_newbie_guide_finish_button() -> None:
    page = FakePage({"text=新手引导", ".next-dialog button:has-text('完成')"})

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.clicks == [(".next-dialog button:has-text('完成')", 1000)]


def test_dismiss_known_overlays_clicks_driver_popover_finish_button() -> None:
    page = FakePage({"text=新手引导", "button.driver-popover-next-btn:has-text('完成')"})

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.clicks == [("button.driver-popover-next-btn:has-text('完成')", 1000)]


def test_dismiss_known_overlays_uses_driver_popover_marker_without_title_text() -> None:
    page = FakePage({".driver-popover", "button.driver-popover-next-btn:has-text('完成')"})

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.clicks == [("button.driver-popover-next-btn:has-text('完成')", 1000)]


def test_dismiss_known_overlays_clicks_driver_popover_finish_before_escape() -> None:
    page = FakePage({".driver-popover", "button.driver-popover-next-btn:has-text('完成')"})

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.events[0] == ("click", "button.driver-popover-next-btn:has-text('完成')", 1000)
    assert page.keyboard.pressed == []


def test_dismiss_known_overlays_clicks_top_right_x_when_selector_close_fails() -> None:
    page = FakePage(
        {"text=预警通知", ".normal_container__13Xbj"},
        boxes={".normal_container__13Xbj": {"x": 100, "y": 80, "width": 360, "height": 180}},
        failing_click_selectors={
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
        },
    )

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.mouse.clicks == [(444, 96)]


def test_dismiss_known_overlays_prefers_message_panel_header_x() -> None:
    page = FakePage(
        {"text=预警通知", "text=重要消息", ".normal_container__13Xbj"},
        boxes={
            "text=重要消息": {"x": 791, "y": 475, "width": 96, "height": 22},
            ".normal_container__13Xbj": {"x": 796, "y": 481, "width": 334, "height": 146},
        },
        failing_click_selectors={
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
        },
    )

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.mouse.clicks == [(1118, 486)]


def test_dismiss_known_overlays_clicks_dom_detected_close_point() -> None:
    page = FakePage(
        {"text=预警通知"},
        failing_click_selectors={
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
        },
        evaluate_result={"x": 923.5, "y": 252.0, "source": "candidate"},
    )

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.mouse.clicks == [(923.5, 252.0)]


def test_dismiss_known_overlays_rejects_dom_close_outside_notice_panel() -> None:
    page = FakePage(
        {"text=预警通知", "text=重要消息", ".normal_container__13Xbj"},
        boxes={
            "text=重要消息": {"x": 791, "y": 475, "width": 96, "height": 22},
            ".normal_container__13Xbj": {"x": 796, "y": 481, "width": 334, "height": 146},
        },
        failing_click_selectors={
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
        },
        evaluate_result={
            "x": 1219,
            "y": 22.5,
            "source": "caret-down  tbdicon tbdicon-caret-down ",
            "panel_left": 774,
            "panel_top": 456,
            "panel_right": 1145,
            "panel_bottom": 676,
        },
    )

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.mouse.clicks == [(1118, 486)]


def test_dismiss_known_overlays_skips_page_header_container_for_top_right_x() -> None:
    page = FakePage(
        {"text=预警通知", ".normal_container__13Xbj", ".container--SMNuCb74"},
        boxes={
            ".normal_container__13Xbj": {"x": 140, "y": 120, "width": 320, "height": 160},
            ".container--SMNuCb74": {"x": 0, "y": 0, "width": 1280, "height": 65},
        },
        failing_click_selectors={
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
        },
    )

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is True
    assert page.mouse.clicks == [(444, 136)]


def test_dismiss_known_overlays_is_noop_without_known_overlay() -> None:
    page = FakePage(set())

    dismissed = _dismiss_known_overlays(page)

    assert dismissed is False
    assert page.keyboard.pressed == []
    assert page.clicks == []
    assert page.evaluate_calls == []
