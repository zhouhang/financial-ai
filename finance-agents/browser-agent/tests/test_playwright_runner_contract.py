from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.playwright_runner import (
    PlaywrightRunConfig,
    build_user_data_dir,
)


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


def test_playwright_config_env_overrides(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BROWSER_AGENT_PROFILE_ROOT", str(tmp_path / "profiles"))
    monkeypatch.setenv("BROWSER_AGENT_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    monkeypatch.setenv("BROWSER_AGENT_HEADLESS", "1")
    monkeypatch.setenv("BROWSER_AGENT_TIMEZONE", "UTC")
    monkeypatch.setenv("BROWSER_AGENT_BROWSER_CHANNEL", "msedge")
    config = PlaywrightRunConfig.from_env()
    assert config.profile_root == str(tmp_path / "profiles")
    assert config.download_root == str(tmp_path / "downloads")
    assert config.headless is True
    assert config.timezone_id == "UTC"
    assert config.browser_channel == "msedge"
