"""Per-company CLI 配置隔离。

文件型配置的 CLI(如 lark-cli)凭证落盘,无法像 dws 那样 per-call env 注入凭证。
改为给每家公司分配独立配置目录,并通过子进程 env(HOME / XDG_CONFIG_HOME)指向它,
使不同公司的 CLI 凭证互不串扰。

lark-cli 实测:凭证密文存 $HOME/Library/Application Support/lark-cli/*.enc 与
$HOME/.lark-cli/config.json(文件级加密,非系统钥匙串),故设置 HOME 即可按公司隔离。
"""
from __future__ import annotations

import os
from pathlib import Path


def company_state_dir(base_dir: str, provider: str, company_id: str) -> Path:
    """返回 <base_dir>/<provider>/<company_id> 目录(不存在则创建,权限 0700)。"""
    safe_company = (str(company_id or "").strip() or "default")
    path = Path(os.path.expanduser(base_dir)) / provider / safe_company
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def company_cli_env(base_dir: str, provider: str, company_id: str) -> dict[str, str]:
    """返回该公司隔离配置目录对应的子进程 env(HOME + XDG_CONFIG_HOME)。"""
    home = company_state_dir(base_dir, provider, company_id)
    config_home = home / ".config"
    config_home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home), "XDG_CONFIG_HOME": str(config_home)}
