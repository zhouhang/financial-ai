from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest


DATA_AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))
else:
    sys.path.remove(str(DATA_AGENT_ROOT))
    sys.path.insert(0, str(DATA_AGENT_ROOT))


nodes = importlib.import_module("graphs.recon.scheme_execution.nodes")
routers = importlib.import_module("graphs.recon.scheme_execution.routers")


@pytest.mark.anyio
async def test_execute_proc_preserves_dataset_source_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    preparation_metrics = [
        {
            "side": "right",
            "target_table": "right_recon_ready",
            "row_count": 1,
            "duration_seconds": 0.42,
        }
    ]

    async def fake_execute_proc_rule(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "success": True,
            "memory_outputs": [
                {
                    "target_table": "right_recon_ready",
                    "memory_ref": "memory:right",
                    "row_count": 1,
                }
            ],
            "generated_files": [],
            "runtime_metrics": {"preparation": preparation_metrics},
        }

    monkeypatch.setattr(nodes, "execute_proc_rule", fake_execute_proc_rule)

    result = await nodes.execute_proc_node(
        {
            "auth_token": "token",
            "recon_ctx": {
                "biz_date": "2026-05-11",
                "proc_rule_code": "dataset_proc_test",
                "scheme": {"scheme_meta_json": {}},
                "recon_inputs": [
                    {
                        "table_name": "alipay_bill_lines",
                        "input_type": "dataset",
                        "payload": {
                            "dataset_ref": {
                                "source_type": "platform_alipay_bill_lines",
                                "source_key": "source-alipay-1",
                                "query": {
                                    "dataset_id": "dataset-alipay-1",
                                    "resource_key": "signcustomer:merchant-1",
                                    "biz_date": "2026-05-11",
                                    "date_field": "bill_date",
                                    "filters": {"业务类型": "交易付款"},
                                },
                            }
                        },
                    }
                ],
            },
        }
    )

    dataset_ref = captured["dataset_inputs"][0]["dataset_ref"]
    assert dataset_ref["source_type"] == "platform_alipay_bill_lines"
    assert dataset_ref["source_key"] == "source-alipay-1"
    assert dataset_ref["query"]["dataset_id"] == "dataset-alipay-1"
    assert dataset_ref["query"]["biz_date"] == "2026-05-11"
    assert dataset_ref["query"]["date_field"] == "bill_date"
    assert dataset_ref["query"]["filters"] == {"业务类型": "交易付款"}
    assert result["recon_ctx"]["prepare_status"] == "success"
    assert result["recon_ctx"]["recon_inputs"][0]["input_type"] == "memory"
    assert result["recon_ctx"]["runtime_metrics"]["preparation"] == preparation_metrics


def test_route_after_execute_proc_stops_on_prepare_error() -> None:
    route = routers.route_after_execute_proc(
        {
            "recon_ctx": {
                "exec_status": "error",
                "failed_stage": "prepare",
            }
        }
    )

    assert route == "build_recon_observation_node"


def test_route_after_execute_proc_continues_on_prepare_success() -> None:
    route = routers.route_after_execute_proc(
        {
            "recon_ctx": {
                "prepare_status": "success",
                "exec_status": "",
            }
        }
    )

    assert route == "build_recon_inputs_node"
