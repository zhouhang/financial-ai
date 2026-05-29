from __future__ import annotations

import pandas as pd

from proc.mcp_server.steps_runtime import SOURCE_RECORD_METADATA_COLUMN
from recon.mcp_server.recon_tool import _build_anomaly_rows, _execute_comparison


def test_recon_anomaly_rows_include_proc_source_records() -> None:
    source_df = pd.DataFrame(
        [
            {
                "订单号": "A001",
                "金额": 100,
                SOURCE_RECORD_METADATA_COLUMN: {
                    "订单编号": "A001",
                    "实付金额": 100,
                    "买家昵称": "alice",
                },
            }
        ]
    )
    target_df = pd.DataFrame(
        [
            {
                "订单号": "A001",
                "金额": 80,
                SOURCE_RECORD_METADATA_COLUMN: {
                    "商户订单号": "A001",
                    "入账金额": 80,
                    "账务备注": "支付宝入账",
                },
            }
        ]
    )

    diff_result = _execute_comparison(
        df_source=source_df,
        df_target=target_df,
        key_mappings=[{"source_field": "订单号", "target_field": "订单号"}],
        compare_columns_config=[
            {
                "name": "金额",
                "source_column": "金额",
                "target_column": "金额",
                "tolerance": 0,
            }
        ],
        rule_id="source_record_detail",
    )
    anomaly_rows = _build_anomaly_rows(
        diff_result,
        key_mappings=[{"source_field": "订单号", "target_field": "订单号"}],
        compare_columns_config=[
            {
                "name": "金额",
                "source_column": "金额",
                "target_column": "金额",
                "tolerance": 0,
            }
        ],
    )

    assert anomaly_rows[0]["source_record"]["买家昵称"] == "alice"
    assert anomaly_rows[0]["target_record"]["账务备注"] == "支付宝入账"
    assert anomaly_rows[0]["compare_values"][0]["source_value"] == 100
    assert anomaly_rows[0]["compare_values"][0]["target_value"] == 80
