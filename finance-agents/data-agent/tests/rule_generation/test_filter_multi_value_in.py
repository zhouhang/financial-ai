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

from graphs.rule_generation.proc.understanding import _normalize_predicate


def test_eq_with_list_value_becomes_in_predicate() -> None:
    """A scalar eq carrying a list value (订单状态取A和B) must normalize to an `in`
    predicate, not eq against the list's repr (which compiles to col == "['A','B']" and
    matches nothing).

    Regression: PDD order recon, 订单状态只取 已发货，待收货 / 已收货 -> 0 rows.
    """
    predicate = _normalize_predicate(
        {"op": "eq", "ref_id": "ref_order_status_1", "value": ["已收货", "已发货，待收货"]}
    )
    assert predicate is not None
    assert predicate["op"] == "in"
    assert predicate["left"] == {"op": "ref", "ref_id": "ref_order_status_1"}
    assert [item["value"] for item in predicate["right"]] == ["已收货", "已发货，待收货"]


def test_eq_with_scalar_value_stays_eq() -> None:
    predicate = _normalize_predicate(
        {"op": "eq", "ref_id": "ref_order_status_1", "value": "已收货"}
    )
    assert predicate is not None
    assert predicate["op"] == "eq"
    assert predicate["right"] == {"op": "constant", "value": "已收货"}


def test_explicit_in_with_single_list_value_keeps_all_values() -> None:
    """An explicit `in` whose values live under the singular `value` key as a list must keep
    every member (previously a list under `value` was wrapped into a single nested list)."""
    predicate = _normalize_predicate(
        {"op": "in", "ref_id": "ref_status", "value": ["A", "B", "C"]}
    )
    assert predicate is not None
    assert predicate["op"] == "in"
    assert [item["value"] for item in predicate["right"]] == ["A", "B", "C"]


def test_eq_with_stringified_list_repr_becomes_in_predicate() -> None:
    """Upstream/LLM sometimes delivers the multi-value filter as a Python list *repr string*
    ("['A','B']") rather than a real list. That must also normalize to `in`.

    Regression: PDD 博宽游戏 order recon kept failing with
    `订单状态 == "['已收货', '已发货，待收货']"` even after the list-only fix, because the value
    arrived as a repr string.
    """
    predicate = _normalize_predicate(
        {"op": "eq", "ref_id": "ref_order_status_1", "value": "['已收货', '已发货，待收货']"}
    )
    assert predicate is not None
    assert predicate["op"] == "in"
    assert [item["value"] for item in predicate["right"]] == ["已收货", "已发货，待收货"]


def test_eq_with_bracketed_non_list_scalar_stays_eq() -> None:
    """A scalar string that merely starts with '[' but is not a valid list literal must NOT be
    misread as a membership list."""
    predicate = _normalize_predicate(
        {"op": "eq", "ref_id": "ref_x", "value": "[特殊]商品"}
    )
    assert predicate is not None
    assert predicate["op"] == "eq"
    assert predicate["right"] == {"op": "constant", "value": "[特殊]商品"}
