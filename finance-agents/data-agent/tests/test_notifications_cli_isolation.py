from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications.cli_isolation import company_cli_env, company_state_dir


def test_company_state_dir_is_isolated_per_company(tmp_path):
    d1 = company_state_dir(str(tmp_path), "feishu", "company-A")
    d2 = company_state_dir(str(tmp_path), "feishu", "company-B")
    assert d1 != d2
    assert d1.exists() and d2.exists()
    assert "company-A" in str(d1) and "feishu" in str(d1)


def test_company_cli_env_points_home_and_xdg_under_company_dir(tmp_path):
    env = company_cli_env(str(tmp_path), "feishu", "company-A")
    assert env["HOME"].startswith(str(tmp_path))
    assert "company-A" in env["HOME"]
    assert env["XDG_CONFIG_HOME"].startswith(env["HOME"])


def test_company_cli_env_blank_company_falls_back_to_default(tmp_path):
    env = company_cli_env(str(tmp_path), "feishu", "")
    assert "default" in env["HOME"]
