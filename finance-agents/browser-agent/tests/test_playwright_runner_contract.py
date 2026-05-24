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
    assert config.step_delay_min_ms == 1000
    assert config.step_delay_max_ms == 3000
    assert config.click_delay_min_ms == 800
    assert config.click_delay_max_ms == 1800
    assert config.type_delay_ms == 160
    assert config.risk_manual_timeout_ms == 300000


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
