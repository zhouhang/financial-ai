from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.playwright_runner import (
    PlaywrightRunConfig,
    _save_download,
    build_user_data_dir,
)


class FakeDownload:
    def __init__(self, suggested_filename: str) -> None:
        self.suggested_filename = suggested_filename

    def save_as(self, path: str) -> None:
        Path(path).write_bytes(b"a,b\n1,2\n")


def test_build_user_data_dir_uses_shop_id_under_profile_root(tmp_path) -> None:
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
    )
    assert build_user_data_dir(config=config, shop_id="shop-001") == str(tmp_path / "shop-001")


def test_build_user_data_dir_sanitizes_unsafe_chars(tmp_path) -> None:
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path),
        download_root=str(tmp_path / "downloads"),
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
    )
    # Path separators / null bytes / spaces must not escape the profile_root.
    assert build_user_data_dir(config=config, shop_id="../etc/passwd") == str(tmp_path / "etcpasswd")
    assert build_user_data_dir(config=config, shop_id="") == str(tmp_path / "unknown")


def test_playwright_config_defaults_to_persistent_profile(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/tmp/tally-home")
    monkeypatch.delenv("BROWSER_AGENT_PROFILE_ROOT", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_DOWNLOAD_ROOT", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_HEADLESS", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_TIMEZONE", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_BROWSER_CHANNEL", raising=False)
    config = PlaywrightRunConfig.from_env()
    assert config.profile_root == "/tmp/tally-home/tally-browser-agent/profiles"
    assert config.download_root == "/tmp/tally-home/tally-browser-agent/downloads"
    assert config.timezone_id == "Asia/Shanghai"
    assert config.headless is False
    assert config.browser_channel == "chrome"
    assert config.step_delay_min_ms == 1000
    assert config.step_delay_max_ms == 3000
    assert config.click_delay_min_ms == 800
    assert config.click_delay_max_ms == 1800
    assert config.type_delay_ms == 160
    assert config.risk_manual_timeout_ms == 900000


def test_playwright_config_env_overrides(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_AGENT_PROFILE_ROOT", str(tmp_path / "profiles"))
    monkeypatch.setenv("BROWSER_AGENT_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    monkeypatch.setenv("BROWSER_AGENT_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_AGENT_TIMEZONE", "UTC")
    monkeypatch.setenv("BROWSER_AGENT_BROWSER_CHANNEL", "msedge")
    monkeypatch.setenv("BROWSER_AGENT_STEP_DELAY_MIN_MS", "1200")
    monkeypatch.setenv("BROWSER_AGENT_STEP_DELAY_MAX_MS", "2400")
    monkeypatch.setenv("BROWSER_AGENT_CLICK_DELAY_MIN_MS", "400")
    monkeypatch.setenv("BROWSER_AGENT_CLICK_DELAY_MAX_MS", "800")
    monkeypatch.setenv("BROWSER_AGENT_TYPE_DELAY_MS", "120")
    monkeypatch.setenv("BROWSER_AGENT_RISK_MANUAL_TIMEOUT_MS", "600000")
    config = PlaywrightRunConfig.from_env()
    assert config.profile_root == str(tmp_path / "profiles")
    assert config.download_root == str(tmp_path / "downloads")
    assert config.headless is True
    assert config.timezone_id == "UTC"
    assert config.browser_channel == "msedge"
    assert config.step_delay_min_ms == 1200
    assert config.step_delay_max_ms == 2400
    assert config.click_delay_min_ms == 400
    assert config.click_delay_max_ms == 800
    assert config.type_delay_ms == 120
    assert config.risk_manual_timeout_ms == 600000


def test_save_download_appends_uploaded_capture_metadata(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, str]] = []

    def fake_upload(path, **kwargs):
        calls.append({"path": str(path), **kwargs})
        return {
            "storage_path": "oss://bucket-a/prefix/browser-captures/company-001/shop-001/file.csv",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "prefix/browser-captures/company-001/shop-001/file.csv",
            "storage_uri": "oss://bucket-a/prefix/browser-captures/company-001/shop-001/file.csv",
            "local_path": str(path),
            "content_type": "text/csv",
            "size_bytes": Path(path).stat().st_size,
        }

    monkeypatch.setattr(
        "finance_browser_agent.playwright_runner.upload_capture_file_if_configured",
        fake_upload,
    )
    capture_files: list[dict[str, object]] = []

    result = _save_download(
        FakeDownload("file.csv"),
        download_dir=tmp_path,
        capture_files=capture_files,
        storage_context={
            "company_id": "company-001",
            "shop_id": "shop-001",
            "biz_date": "2026-05-18",
            "sync_job_id": "job-001",
        },
    )

    assert Path(result["last_download"]).read_bytes() == b"a,b\n1,2\n"
    assert calls == [
        {
            "path": result["last_download"],
            "company_id": "company-001",
            "shop_id": "shop-001",
            "biz_date": "2026-05-18",
            "sync_job_id": "job-001",
        }
    ]
    assert capture_files == [
        {
            "storage_path": "oss://bucket-a/prefix/browser-captures/company-001/shop-001/file.csv",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "prefix/browser-captures/company-001/shop-001/file.csv",
            "storage_uri": "oss://bucket-a/prefix/browser-captures/company-001/shop-001/file.csv",
            "local_path": result["last_download"],
            "content_type": "text/csv",
            "size_bytes": 8,
            "encoding": "",
            "checksum": "",
            "row_count": 0,
        }
    ]
