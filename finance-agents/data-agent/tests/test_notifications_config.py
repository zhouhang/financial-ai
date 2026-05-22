from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


def test_feishu_config_defaults():
    assert config.FEISHU_LARK_BIN == "lark-cli"
    assert config.FEISHU_LARK_ENABLED is True
    assert config.NOTIFY_CLI_STATE_DIR  # 非空字符串
