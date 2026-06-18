from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import pandas as pd
from recon.mcp_server import diff_digestion


def _diff_result():
    return {
        "matched_exact": pd.DataFrame(),
        "matched_with_diff": pd.DataFrame([{"source_订单编号": "D1"}]),
        "source_only": pd.DataFrame([{"source_订单编号": "S1"}, {"source_订单编号": "S2"}]),
        "target_only": pd.DataFrame([{"target_订单编号": "T1"}]),
    }


def _tokens(df, col):
    return set() if df is None or df.empty else set(df[col].astype(str)) if col in df else set()


def test_resolved_moves_to_matched_exact_and_reclassified_moves_bucket():
    dr = _diff_result()
    results = [
        {"key": {"订单编号": "S1"}, "outcome": "resolved"},
        {"key": {"订单编号": "D1"}, "outcome": "reclassified", "resolved_to": "source_only"},
        {"key": {"订单编号": "T1"}, "outcome": "kept"},
        {"key": {"订单编号": "S2"}, "outcome": "kept"},
    ]
    tally = diff_digestion.apply_outcomes_to_diff_result(
        dr, results, source_key_field="订单编号", target_key_field="订单编号"
    )
    # S1 resolved -> matched_exact
    assert _tokens(dr["matched_exact"], "source_订单编号") == {"S1"}
    # D1 reclassified diff -> source_only; S1 gone, S2 kept
    assert _tokens(dr["source_only"], "source_订单编号") == {"S2", "D1"}
    # matched_with_diff emptied (D1 moved out)
    assert dr["matched_with_diff"].empty
    # T1 untouched
    assert _tokens(dr["target_only"], "target_订单编号") == {"T1"}
    assert tally == {"matched_exact": 1, "source_only": 1}


def test_no_outcomes_is_noop():
    dr = _diff_result()
    tally = diff_digestion.apply_outcomes_to_diff_result(
        dr, [{"key": {"订单编号": "S1"}, "outcome": "kept"}],
        source_key_field="订单编号", target_key_field="订单编号",
    )
    assert tally == {}
    assert _tokens(dr["source_only"], "source_订单编号") == {"S1", "S2"}
    assert dr["matched_exact"].empty
