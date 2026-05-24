from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import finance_browser_agent.playwright_runner as playwright_runner
from finance_browser_agent.dispatcher_loop import BrowserDispatcherLoop
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


def test_build_user_data_dir_prefers_runtime_profile_ref_and_sanitizes(tmp_path) -> None:
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
    )

    user_data_dir = build_user_data_dir(
        config=config,
        shop_id="shop-a",
        runtime_profile_ref="../bank/profile-01",
    )

    assert user_data_dir == str(tmp_path / "profiles" / "bankprofile-01")


def test_should_skip_login_action_only_skips_login_steps_when_authenticated() -> None:
    assert should_skip_login_action({"action": "login"}, authenticated=True) is True
    assert should_skip_login_action({"action": "login_if_needed"}, authenticated=True) is True
    assert should_skip_login_action({"action": "login"}, authenticated=False) is False
    assert should_skip_login_action({"action": "click"}, authenticated=True) is False


class FakePage:
    def __init__(
        self,
        *,
        url: str = "about:blank",
        selectors: set[str] | None = None,
        content_text: str = "",
    ) -> None:
        self.url = url
        self.selectors = selectors or set()
        self.content_text = content_text
        self.gotos: list[tuple[str, str, int]] = []
        self.fills: list[tuple[str, str, int]] = []
        self.clicks: list[tuple[str, int]] = []
        self.waits: list[tuple[str, int]] = []
        self.timeouts: list[int] = []

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.gotos.append((url, wait_until, timeout))
        self.url = url

    def content(self) -> str:
        return self.content_text

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.waits.append((selector, timeout))
        if selector not in self.selectors:
            raise TimeoutError(selector)

    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        self.fills.append((selector, value, timeout))

    def click(self, selector: str, *, timeout: int) -> None:
        self.clicks.append((selector, timeout))

    def wait_for_timeout(self, timeout: int) -> None:
        self.timeouts.append(timeout)


class FailingFillPage(FakePage):
    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        raise TimeoutError(selector)

    def click(self, selector: str, *, timeout: int) -> None:
        raise TimeoutError(selector)

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        raise TimeoutError(selector)


class RecordingFailingFillPage(FailingFillPage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example")
        self.fill_timeouts: list[int] = []

    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        self.fill_timeouts.append(timeout)
        raise TimeoutError(selector)


class FakePageWithFrames(FailingFillPage):
    def __init__(self, *, frames: list[FakePage]) -> None:
        super().__init__(url="https://login.example")
        self.frames = frames


class PasswordModePage(FakePage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example", selectors={".dashboard"})
        self.password_mode = False

    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        if not self.password_mode:
            raise TimeoutError(selector)
        super().fill(selector, value, timeout=timeout)

    def click(self, selector: str, *, timeout: int) -> None:
        if selector == "text=密码登录":
            self.password_mode = True
        super().click(selector, timeout=timeout)


class PasswordModeCreatesFramePage(FailingFillPage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example")
        self.frames: list[FakePage] = []
        self.password_mode_clicks = 0

    def click(self, selector: str, *, timeout: int) -> None:
        if selector == "text=密码登录":
            self.password_mode_clicks += 1
            self.frames = [FakePage(url="https://login.example/password-frame", selectors={".dashboard"})]
            return
        raise TimeoutError(selector)


class DelayedFramePage(FailingFillPage):
    def __init__(self, *, frame_after_calls: int) -> None:
        super().__init__(url="https://login.example")
        self.frame_after_calls = frame_after_calls
        self.frame_calls = 0
        self.login_frame = FakePage(url="https://login.example/iframe", selectors={".dashboard"})
        self.timeouts: list[int] = []

    @property
    def frames(self) -> list[FakePage]:
        self.frame_calls += 1
        if self.frame_calls >= self.frame_after_calls:
            return [self.login_frame]
        return []

    def wait_for_timeout(self, timeout: int) -> None:
        self.timeouts.append(timeout)


class LocatorBackedPage(FakePage):
    def __init__(
        self,
        *,
        visible_text: str,
        content_text: str,
        selectors: set[str] | None = None,
    ) -> None:
        super().__init__(url="https://login.example", selectors=selectors, content_text=content_text)
        self.visible_text = visible_text

    def locator(self, selector: str):
        if selector != "body":
            raise TimeoutError(selector)
        page = self

        class _BodyLocator:
            @property
            def first(self):
                return self

            def inner_text(self, *, timeout: int) -> str:
                return page.visible_text

        return _BodyLocator()


class RiskThenFramePage(FailingFillPage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example")
        self.timeouts: list[int] = []
        self.risk_checks = 0
        self.login_frame = FakePage(url="https://login.example/iframe", selectors={".dashboard"})

    @property
    def frames(self) -> list[FakePage]:
        if self.risk_checks >= 2:
            return [self.login_frame]
        return []

    def wait_for_timeout(self, timeout: int) -> None:
        self.timeouts.append(timeout)

    def locator(self, selector: str):
        if selector != "body":
            raise TimeoutError(selector)
        page = self

        class _BodyLocator:
            @property
            def first(self):
                return self

            def inner_text(self, *, timeout: int) -> str:
                page.risk_checks += 1
                if page.risk_checks == 1:
                    return "向右滑动验证"
                return "密码登录"

        return _BodyLocator()


class ReappearingRiskThenFramePage(FailingFillPage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example")
        self.risk_checks = 0
        self.login_frame = FakePage(url="https://login.example/iframe", selectors={".dashboard"})

    @property
    def frames(self) -> list[FakePage]:
        if self.risk_checks >= 4:
            return [self.login_frame]
        return []

    def locator(self, selector: str):
        if selector != "body":
            raise TimeoutError(selector)
        page = self

        class _BodyLocator:
            @property
            def first(self):
                return self

            def inner_text(self, *, timeout: int) -> str:
                page.risk_checks += 1
                if page.risk_checks in {1, 3}:
                    return "向右滑动验证"
                return "密码登录"

        return _BodyLocator()


class FakePageWithFramesAndPostLogin(FailingFillPage):
    def __init__(self, *, frames: list[FakePage], selectors: set[str]) -> None:
        super().__init__(url="https://login.example")
        self.frames = frames
        self.selectors = selectors
        self.waits: list[tuple[str, int]] = []

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.waits.append((selector, timeout))
        if selector not in self.selectors:
            raise TimeoutError(selector)


class RetryLoginWithExistingUsernamePage(FakePage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example", selectors={".dashboard"})
        self.values: dict[str, str] = {}
        self.username_type_count = 0
        self.password_attempts = 0

    def locator(self, selector: str):
        page = self

        class _Locator:
            @property
            def first(self):
                return self

            def inner_text(self, *, timeout: int) -> str:
                return ""

            def input_value(self, *, timeout: int) -> str:
                return page.values.get(selector, "")

            def click(self, *, timeout: int) -> None:
                return None

            def fill(self, value: str, *, timeout: int) -> None:
                page.values[selector] = value

            def type(self, value: str, *, delay: int, timeout: int) -> None:
                if selector == "#username":
                    page.username_type_count += 1
                if selector == "#password":
                    page.password_attempts += 1
                    if page.password_attempts == 1:
                        raise TimeoutError(selector)
                page.values[selector] = page.values.get(selector, "") + value

        return _Locator()


class MissingPasswordControlPage(FakePage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example")
        self.values: dict[str, str] = {}
        self.waited_selectors: list[str] = []

    def locator(self, selector: str):
        page = self

        class _Locator:
            @property
            def first(self):
                return self

            def inner_text(self, *, timeout: int) -> str:
                return ""

            def wait_for(self, *, timeout: int) -> None:
                page.waited_selectors.append(selector)
                if selector == "#password":
                    raise TimeoutError(selector)

            def click(self, *, timeout: int) -> None:
                return None

            def fill(self, value: str, *, timeout: int) -> None:
                page.values[selector] = value

            def type(self, value: str, *, delay: int, timeout: int) -> None:
                page.values[selector] = page.values.get(selector, "") + value

        return _Locator()


class SlowTypeLongUsernamePage(FakePage):
    def __init__(self) -> None:
        super().__init__(url="https://login.example", selectors={".dashboard"})
        self.values: dict[str, str] = {}
        self.username_type_timeouts: list[int] = []

    def locator(self, selector: str):
        page = self

        class _Locator:
            @property
            def first(self):
                return self

            def inner_text(self, *, timeout: int) -> str:
                return ""

            def wait_for(self, *, timeout: int) -> None:
                return None

            def input_value(self, *, timeout: int) -> str:
                return page.values.get(selector, "")

            def click(self, *, timeout: int) -> None:
                return None

            def fill(self, value: str, *, timeout: int) -> None:
                page.values[selector] = value

            def type(self, value: str, *, delay: int, timeout: int) -> None:
                if selector == "#username":
                    page.username_type_timeouts.append(timeout)
                required_timeout = len(value) * delay
                if timeout < required_timeout:
                    partial_len = max(1, timeout // max(1, delay))
                    page.values[selector] = page.values.get(selector, "") + value[:partial_len]
                    raise TimeoutError(selector)
                page.values[selector] = page.values.get(selector, "") + value

        return _Locator()


def test_login_if_needed_without_logged_in_selector_is_not_skipped_on_about_blank() -> None:
    page = FakePage(url="about:blank")

    authenticated = _profile_is_authenticated(page, {"auth_check": {}})

    assert authenticated is False
    assert should_skip_login_action({"action": "login_if_needed"}, authenticated=authenticated) is False


def test_profile_with_logged_in_selector_authenticates_when_selector_exists() -> None:
    page = FakePage(url="https://seller.example/home", selectors={".account-menu"})

    assert (
        _profile_is_authenticated(
            page,
            {"auth_check": {"logged_in_selector": ".account-menu", "timeout_ms": 1234}},
        )
        is True
    )
    assert page.waits == [(".account-menu", 1234)]
    assert should_skip_login_action({"action": "login_if_needed"}, authenticated=True) is True


def test_login_action_fills_credentials_clicks_submit_and_waits(tmp_path) -> None:
    page = FakePage(url="https://login.example", selectors={".dashboard"})

    _execute_action(
        page,
        {
            "action": "login",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert page.fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]
    assert page.clicks == [("button[type='submit']", 1000)]
    assert page.waits == [(".dashboard", 2000)]


def test_login_action_falls_back_to_child_frame_when_main_page_has_no_fields(tmp_path) -> None:
    login_frame = FakePage(url="https://login.example/iframe", selectors={".dashboard"})
    page = FakePageWithFrames(frames=[login_frame])

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert login_frame.fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]
    assert login_frame.clicks == [("button[type='submit']", 1000)]
    assert login_frame.waits == [(".dashboard", 2000)]


def test_login_action_uses_bounded_selector_timeout_before_child_frame(tmp_path) -> None:
    login_frame = FakePage(url="https://login.example/iframe", selectors={".dashboard"})
    main_page = RecordingFailingFillPage()
    main_page.frames = [login_frame]

    _execute_action(
        main_page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 120000,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert main_page.fill_timeouts
    assert max(main_page.fill_timeouts) <= 1000
    assert login_frame.fills[0] == ("#username", "alice", 1000)


def test_login_action_clicks_common_password_login_mode_before_fill(tmp_path) -> None:
    page = PasswordModePage()

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert ("text=密码登录", 1000) in page.clicks
    assert ("#username", "alice", 1000) in page.fills
    assert ("#password", "secret", 1000) in page.fills
    assert page.clicks[-1] == ("button[type='submit']", 1000)


def test_login_action_refreshes_frames_after_password_login_mode_click(tmp_path) -> None:
    page = PasswordModeCreatesFramePage()

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert page.password_mode_clicks == 1
    assert page.frames[0].fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]
    assert page.frames[0].clicks == [("button[type='submit']", 1000)]


def test_login_action_waits_for_delayed_login_iframe_before_failing(tmp_path) -> None:
    page = DelayedFramePage(frame_after_calls=4)

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert page.frame_calls >= 4
    assert page.login_frame.fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]
    assert page.timeouts


def test_login_action_waits_on_main_page_when_frame_post_login_selector_is_missing(tmp_path) -> None:
    login_frame = FakePage(url="https://login.example/iframe")
    page = FakePageWithFramesAndPostLogin(frames=[login_frame], selectors={".dashboard"})

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert login_frame.clicks == [("button[type='submit']", 1000)]
    assert login_frame.waits == [(".dashboard", 2000)]
    assert page.waits == [(".dashboard", 2000)]


def test_login_action_maps_post_login_risk_verification_to_risk_failure(tmp_path) -> None:
    page = FakePage(url="https://login.example", content_text="请拖动滑块完成安全验证")

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "action": "login_if_needed",
                "username_selector": "#username",
                "password_selector": "#password",
                "submit_selector": "button[type='submit']",
                "username_value_from": "params.login_username",
                "password_value_from": "params.login_password",
                "post_login_wait_selector": ".dashboard",
                "timeout_ms": 4321,
            },
            params={"login_username": "alice", "login_password": "secret"},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
        )

    assert exc.value.fail_reason == "RISK_VERIFICATION"


def test_login_action_waits_for_manual_risk_in_login_form_before_retrying(tmp_path) -> None:
    page = RiskThenFramePage()
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        risk_manual_timeout_ms=3210,
    )

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        run_config=config,
    )

    assert page.risk_checks >= 2
    assert 3210 not in page.timeouts
    assert all(timeout < 3210 for timeout in page.timeouts)
    assert page.login_frame.fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]


def test_login_action_keeps_waiting_when_form_risk_reappears_before_manual_clear(tmp_path) -> None:
    page = ReappearingRiskThenFramePage()
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        risk_manual_timeout_ms=3000,
    )

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        run_config=config,
    )

    assert page.risk_checks >= 4
    assert page.login_frame.fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]


def test_login_action_does_not_retype_existing_username_during_retry(tmp_path) -> None:
    page = RetryLoginWithExistingUsernamePage()
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        type_delay_ms=160,
    )

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        run_config=config,
    )

    assert page.username_type_count == 1
    assert page.values["#username"] == "alice"
    assert page.password_attempts == 2


def test_login_action_allows_long_username_to_finish_human_typing(tmp_path) -> None:
    page = SlowTypeLongUsernamePage()
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        type_delay_ms=160,
    )

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "单枪旗舰店:yang", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        run_config=config,
    )

    assert page.values["#username"] == "单枪旗舰店:yang"
    assert page.username_type_timeouts == [4321]


def test_login_action_does_not_mutate_username_before_all_controls_are_ready(tmp_path) -> None:
    page = MissingPasswordControlPage()
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        type_delay_ms=160,
    )

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "action": "login_if_needed",
                "username_selector": "#username",
                "password_selector": "#password",
                "submit_selector": "button[type='submit']",
                "username_value_from": "params.login_username",
                "password_value_from": "params.login_password",
                "post_login_wait_selector": ".dashboard",
                "timeout_ms": 1,
            },
            params={"login_username": "alice", "login_password": "secret"},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
            run_config=config,
        )

    assert exc.value.fail_reason == "PAGE_CHANGED"
    assert "#password" in page.waited_selectors
    assert page.values == {}


def test_login_action_maps_uncleared_form_risk_to_risk_failure(monkeypatch, tmp_path) -> None:
    page = FailingFillPage(url="https://login.example", content_text="向右滑动验证")
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
        risk_manual_timeout_ms=3000,
    )
    monotonic_values = iter([0.0, 0.0, 0.0, 10.0])
    monkeypatch.setattr(
        playwright_runner.time,
        "monotonic",
        lambda: next(monotonic_values, 10.0),
    )
    monkeypatch.setattr(
        playwright_runner,
        "_wait_for_risk_to_clear",
        lambda contexts, *, timeout_ms, poll_interval_ms=1000: False,
    )

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "action": "login_if_needed",
                "username_selector": "#username",
                "password_selector": "#password",
                "submit_selector": "button[type='submit']",
                "username_value_from": "params.login_username",
                "password_value_from": "params.login_password",
                "post_login_wait_selector": ".dashboard",
                "timeout_ms": 1,
            },
            params={"login_username": "alice", "login_password": "secret"},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
            run_config=config,
        )

    assert exc.value.fail_reason == "RISK_VERIFICATION"


def test_login_risk_detection_ignores_hidden_slider_text_when_visible_body_is_normal(tmp_path) -> None:
    page = LocatorBackedPage(
        visible_text="密码登录 短信登录 登录",
        content_text="<div style='display:none'>请按住滑块，拖动到最右边</div>",
        selectors={".dashboard"},
    )

    _execute_action(
        page,
        {
            "action": "login_if_needed",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type='submit']",
            "username_value_from": "params.login_username",
            "password_value_from": "params.login_password",
            "post_login_wait_selector": ".dashboard",
            "timeout_ms": 4321,
        },
        params={"login_username": "alice", "login_password": "secret"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
    )

    assert page.fills == [
        ("#username", "alice", 1000),
        ("#password", "secret", 1000),
    ]


def test_login_action_rejects_missing_resolved_credentials(tmp_path) -> None:
    page = FakePage(url="https://login.example", selectors={".dashboard"})

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "action": "login",
                "username_selector": "#username",
                "password_selector": "#password",
                "submit_selector": "button[type='submit']",
                "username_value_from": "params.login_username",
                "password_value_from": "params.login_password",
                "timeout_ms": 4321,
            },
            params={},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
        )

    assert exc.value.fail_reason == "AUTH_EXPIRED"
    assert page.fills == []


def test_parse_downloaded_csv_uses_gb18030_and_preserves_long_ids(tmp_path) -> None:
    path = tmp_path / "交易货款_20260521_20260521.csv"
    path.write_bytes(
        (
            "账期,业务流水号,订单号,订单实际金额（元）,打款时间\n"
            "20260521,2026052123001193261450560998,3302219424181023654,19.83,2026-05-21 22:32:44\t\n"
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


def test_navigate_allows_auth_redirect_when_login_step_follows(tmp_path) -> None:
    page = FakePage(url="about:blank")

    result = _execute_action(
        page,
        {
            "action": "navigate",
            "url": "https://login.taobao.com/member/login.htm",
            "timeout_ms": 1234,
        },
        params={},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        allow_auth_redirect=True,
    )

    assert result == {"auth_required": True}
    assert page.gotos == [("https://login.taobao.com/member/login.htm", "load", 1234)]


def test_navigate_still_fails_auth_redirect_without_login_step(tmp_path) -> None:
    page = FakePage(url="about:blank")

    with pytest.raises(BrowserActionError) as exc:
        _execute_action(
            page,
            {
                "action": "navigate",
                "url": "https://login.taobao.com/member/login.htm",
                "timeout_ms": 1234,
            },
            params={},
            extracted={},
            capture_files=[],
            download_dir=tmp_path,
        )

    assert exc.value.fail_reason == "AUTH_EXPIRED"


def test_sanitize_profile_key_matches_runner_profile_dir() -> None:
    assert sanitize_profile_key("bank/profile-01") == "bankprofile-01"


class FakeClient:
    def __init__(self, job: dict[str, object]) -> None:
        self.jobs = [job]
        self.completed: list[dict] = []
        self.failed: list[dict] = []

    async def claim_browser_job(self) -> dict:
        if not self.jobs:
            return {"success": True, "job": None}
        return {"success": True, "job": self.jobs.pop(0)}

    async def mark_browser_job_success(self, payload: dict) -> dict:
        self.completed.append(payload)
        return {"success": True}

    async def mark_browser_job_failed(self, payload: dict) -> dict:
        self.failed.append(payload)
        return {"success": True}


class FakeProfileLocks:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def lock_for_shop(self, shop_id: str):
        self.keys.append(shop_id)
        return _FakeAsyncLock()


class _FakeAsyncLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_dispatcher_profile_lock_prefers_runtime_profile_ref() -> None:
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "runtime_profile_ref": "bank/profile-01",
        "playbook_body": {"steps": []},
        "request_payload": {},
    }
    client = FakeClient(job)
    profile_locks = FakeProfileLocks()
    loop = BrowserDispatcherLoop(
        client=client,
        runner=lambda message: {
            "job_id": "sync-001",
            "status": "success",
            "records": [],
            "capture_files": [],
        },
        max_concurrency=1,
        profile_locks=profile_locks,
    )

    await loop.run_once()

    assert profile_locks.keys == ["bankprofile-01"]


@pytest.mark.asyncio
async def test_dispatcher_profile_lock_falls_back_to_shop_id() -> None:
    job = {
        "id": "sync-001",
        "shop_id": "shop-001",
        "runtime_profile_ref": "",
        "playbook_body": {"steps": []},
        "request_payload": {},
    }
    client = FakeClient(job)
    profile_locks = FakeProfileLocks()
    loop = BrowserDispatcherLoop(
        client=client,
        runner=lambda message: {
            "job_id": "sync-001",
            "status": "success",
            "records": [],
            "capture_files": [],
        },
        max_concurrency=1,
        profile_locks=profile_locks,
    )

    await loop.run_once()

    assert profile_locks.keys == ["shop-001"]


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
