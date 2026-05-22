from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    def __init__(self, *, url: str = "about:blank", selectors: set[str] | None = None) -> None:
        self.url = url
        self.selectors = selectors or set()
        self.gotos: list[tuple[str, str, int]] = []
        self.fills: list[tuple[str, str, int]] = []
        self.clicks: list[tuple[str, int]] = []
        self.waits: list[tuple[str, int]] = []

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.gotos.append((url, wait_until, timeout))
        self.url = url

    def content(self) -> str:
        return ""

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.waits.append((selector, timeout))
        if selector not in self.selectors:
            raise TimeoutError(selector)

    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        self.fills.append((selector, value, timeout))

    def click(self, selector: str, *, timeout: int) -> None:
        self.clicks.append((selector, timeout))


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
        ("#username", "alice", 4321),
        ("#password", "secret", 4321),
    ]
    assert page.clicks == [("button[type='submit']", 4321)]
    assert page.waits == [(".dashboard", 4321)]


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
