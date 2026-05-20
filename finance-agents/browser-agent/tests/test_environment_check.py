from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.playwright_runner import PlaywrightRunConfig
from scripts.check_environment import build_environment_report


def test_environment_report_contains_required_paths(tmp_path) -> None:
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=True,
        timezone_id="Asia/Shanghai",
    )
    report = build_environment_report(config=config)
    assert "profile_root" in report
    assert "download_root" in report
    assert report["timezone_id"] == "Asia/Shanghai"
    assert "playwright_importable" in report
    assert "chromium_launchable" in report
    assert "font_probe" in report


def test_environment_report_creates_missing_directories(tmp_path) -> None:
    profile_root = tmp_path / "new_profiles"
    download_root = tmp_path / "new_downloads"
    assert not profile_root.exists()
    assert not download_root.exists()
    config = PlaywrightRunConfig(
        profile_root=str(profile_root),
        download_root=str(download_root),
        headless=True,
        timezone_id="Asia/Shanghai",
    )
    report = build_environment_report(config=config)
    assert report["profile_root_writable"] is True
    assert report["download_root_writable"] is True


def test_environment_report_handles_missing_fc_list(tmp_path, monkeypatch) -> None:
    """fc-list isn't preinstalled on fresh macOS / Ubuntu; report must not crash."""
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "fc-list" else shutil.which(name))
    config = PlaywrightRunConfig(
        profile_root=str(tmp_path / "profiles"),
        download_root=str(tmp_path / "downloads"),
        headless=True,
        timezone_id="Asia/Shanghai",
    )
    report = build_environment_report(config=config)
    assert report["font_probe"] == "fc_list_missing"
