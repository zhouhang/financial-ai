from __future__ import annotations

import importlib
import sys
from pathlib import Path


DATA_AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))


execution_service = importlib.import_module("graphs.recon.execution_service")


def test_build_recon_observation_uses_direct_anomaly_source_records() -> None:
    observation = execution_service.build_recon_observation(
        rule_code="recon_direct_records",
        rule_name="直接异常明细",
        rule={
            "rules": [
                {
                    "source_file": {"table_name": "left_recon_ready"},
                    "target_file": {"table_name": "right_recon_ready"},
                    "recon": {
                        "key_columns": {
                            "mappings": [{"source_field": "订单号", "target_field": "订单号"}]
                        },
                        "compare_columns": {
                            "columns": [
                                {
                                    "name": "金额",
                                    "source_column": "金额",
                                    "target_column": "金额",
                                }
                            ]
                        },
                    },
                }
            ]
        },
        trigger_type="schedule",
        entry_mode="dataset",
        recon_inputs=[],
        recon_result={
            "success": True,
            "results": [
                {
                    "status": "succeeded",
                    "matched_exact": 0,
                    "matched_with_diff": 1,
                    "source_only": 0,
                    "target_only": 0,
                    "anomaly_rows": [
                        {
                            "anomaly_type": "matched_with_diff",
                            "join_key": [
                                {
                                    "source_field": "订单号",
                                    "target_field": "订单号",
                                    "source_value": "A001",
                                    "target_value": "A001",
                                }
                            ],
                            "compare_values": [
                                {
                                    "name": "金额",
                                    "source_field": "金额",
                                    "target_field": "金额",
                                    "source_value": 100,
                                    "target_value": 80,
                                    "diff_value": 20,
                                }
                            ],
                            "source_record": {
                                "订单编号": "A001",
                                "实付金额": 100,
                                "买家昵称": "alice",
                            },
                            "target_record": {
                                "商户订单号": "A001",
                                "入账金额": 80,
                                "账务备注": "支付宝入账",
                            },
                        }
                    ],
                }
            ],
        },
        run_context={"run_id": "run-001"},
        run_id="run-001",
    )

    item = observation["anomaly_items"][0]
    assert item["source_record"]["买家昵称"] == "alice"
    assert item["target_record"]["账务备注"] == "支付宝入账"
    assert item["detail_unavailable"] is False
