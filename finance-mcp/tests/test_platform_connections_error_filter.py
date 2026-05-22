from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools.platform_connections import _is_non_actionable_dataset_error


def test_type_not_supported_is_non_actionable():
    # 支付宝 sub_code TYPE_NOT_SUPPORTED:该账单类型不支持下载,商家无法处理,不算异常
    assert _is_non_actionable_dataset_error("此账单类型不支持下载（TYPE_NOT_SUPPORTED）") is True
    assert _is_non_actionable_dataset_error("TYPE_NOT_SUPPORTED") is True
    assert _is_non_actionable_dataset_error("某账单不支持下载") is True


def test_real_errors_are_actionable():
    # 真实可处理的错误(网络/鉴权/同步失败)仍应计入异常
    assert _is_non_actionable_dataset_error("网络超时，请重试") is False
    assert _is_non_actionable_dataset_error("授权已过期，请重新授权") is False
    assert _is_non_actionable_dataset_error("") is False
    assert _is_non_actionable_dataset_error(None) is False
