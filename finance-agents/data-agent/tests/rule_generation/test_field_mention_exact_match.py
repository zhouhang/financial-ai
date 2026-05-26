from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
REPO_ROOT = Path(__file__).resolve().parents[4]
MCP_ROOT = REPO_ROOT / "finance-mcp"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from graphs.rule_generation.service import _match_field_mention


def _fields(*names: str) -> list[dict[str, str]]:
    return [{"name": name, "raw_name": name, "display_name": name} for name in names]


def test_exact_field_name_binds_even_with_superstring_fields() -> None:
    """A mention that exactly matches a field name must bind to that field,
    even when other fields contain it as a substring.

    Regression: dataset has 订单号 + 子订单号 + 商户订单号; the bare mention
    "订单号" is the complete name of a real field and must bind, not be flagged
    ambiguous against the more-specific 子订单号/商户订单号.
    """
    candidates = _fields("订单号", "子订单号", "商户订单号", "业务流水号", "订单实际金额（元）")
    result = _match_field_mention("订单号", candidates)
    assert result["status"] == "bound"
    assert (result.get("selected_field") or {}).get("name") == "订单号"


def test_no_exact_match_still_ambiguous_when_only_partial() -> None:
    """Guard: when the mention is NOT a complete field name and only partially
    matches several fields, it should still be reported ambiguous (this branch
    must not be broken by the exact-match fix)."""
    candidates = _fields("退款单号", "商户订单号", "子订单号")
    result = _match_field_mention("单号", candidates)
    assert result["status"] == "ambiguous"
