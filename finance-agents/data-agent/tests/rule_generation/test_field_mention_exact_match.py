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


from graphs.rule_generation.service import _clean_field_mention


def test_user_prefixed_field_binds_after_aggressive_clean_strips_用() -> None:
    """_clean_field_mention strips a leading 用 (meant for verb '用X作为...'), which mangles
    fields that legitimately start with 用户 (用户实付金额(元) -> 户实付金额(元)). The matcher
    must still bind such a mangled mention to its real field via symmetric cleaning of candidates.

    Regression: PDD order dataset, '用户实付金额(元)作为对比字段' -> mention '户实付金额(元)'.
    """
    mangled = _clean_field_mention("用户实付金额(元)")
    assert mangled == "户实付金额(元)"  # documents the aggressive-clean behavior

    candidates = _fields("订单号", "订单状态", "用户实付金额(元)", "商家实收金额(元)", "邮费(元)")
    result = _match_field_mention(mangled, candidates)
    assert result["status"] == "bound", result
    assert result["selected_field"]["name"] == "用户实付金额(元)"


def test_verb_phrase_用订单号_still_binds_to_订单号() -> None:
    """The aggressive leading-用 strip exists to rescue verb phrases like '用订单号作为匹配字段'.
    After the fix that path must still work: cleaned mention '订单号' binds to field 订单号.
    """
    assert _clean_field_mention("用订单号") == "订单号"
    result = _match_field_mention("订单号", _fields("订单号", "用户实付金额(元)"))
    assert result["status"] == "bound"
    assert result["selected_field"]["name"] == "订单号"
