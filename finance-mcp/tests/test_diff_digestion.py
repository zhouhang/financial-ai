from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server.diff_digestion import load_side_rows_for_keys


class TestLoadSideRowsForKeys:
    def test_filters_rows_matching_keys(self) -> None:
        full_df = pd.DataFrame(
            {
                "订单编号": ["A", "B", "C"],
                "金额": ["1.0", "2.0", "3.0"],
            }
        )
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"A", "C"})
        assert len(result) == 2
        assert sorted(result["订单编号"].tolist()) == ["A", "C"]
        assert list(result.columns) == ["订单编号", "金额"]

    def test_key_matching_is_string_based(self) -> None:
        full_df = pd.DataFrame({"订单编号": [1001, 1002], "金额": [1, 2]})
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"1001"})
        assert len(result) == 1
        assert result.iloc[0]["金额"] == 1

    def test_empty_df_returns_empty(self) -> None:
        full_df = pd.DataFrame(columns=["订单编号", "金额"])
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"A"})
        assert result.empty

    def test_missing_key_column_returns_empty(self) -> None:
        full_df = pd.DataFrame({"其他列": ["A", "B"]})
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"A"})
        assert result.empty

    def test_empty_keys_returns_empty(self) -> None:
        full_df = pd.DataFrame({"订单编号": ["A", "B"]})
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys=set())
        assert result.empty
