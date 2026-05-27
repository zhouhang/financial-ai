from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import execution_runs


def test_hydrate_execution_scheme_dataset_snapshots_uses_current_dataset_schema(monkeypatch) -> None:
    scheme = {
        "id": "scheme-001",
        "scheme_meta_json": {
            "dataset_bindings": {
                "right": [
                    {
                        "dataset_id": "dataset-browser",
                        "dataset_name": "tb0131100248-已卖出宝贝订单",
                        "data_source_id": "source-browser",
                        "source_kind": "browser_playbook",
                        "resource_key": "browser-collection-tb0131100248-sold-orders@1",
                        "schema_summary": {},
                    }
                ]
            }
        },
    }
    dataset_row = {
        "id": "dataset-browser",
        "dataset_name": "tb0131100248-已卖出宝贝订单",
        "data_source_id": "source-browser",
        "dataset_code": "browser-collection-tb0131100248-sold-orders",
        "resource_key": "browser-collection-tb0131100248-sold-orders@1",
        "dataset_kind": "browser_playbook",
        "schema_summary": {
            "columns": [
                {"name": "订单编号", "data_type": "string"},
                {"name": "订单付款时间", "data_type": "datetime"},
            ],
            "storage": "browser_collection_records",
            "source_type": "browser_collection_records",
        },
        "extract_config": {
            "storage": "browser_collection_records",
            "source_type": "browser_collection_records",
        },
        "meta": {
            "semantic_profile": {
                "field_label_map": {
                    "订单付款时间": "订单付款时间",
                },
                "key_fields": ["订单编号"],
            }
        },
    }

    monkeypatch.setattr(
        execution_runs.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda **kwargs: dataset_row,
    )

    hydrated = execution_runs._hydrate_execution_scheme_dataset_snapshots("company-001", scheme)
    binding = hydrated["scheme_meta_json"]["dataset_bindings"]["right"][0]

    assert binding["schema_summary"]["columns"][1]["name"] == "订单付款时间"
    assert binding["extract_config"]["storage"] == "browser_collection_records"
    assert binding["field_label_map"]["订单付款时间"] == "订单付款时间"
    assert binding["key_fields"] == ["订单编号"]
    assert scheme["scheme_meta_json"]["dataset_bindings"]["right"][0]["schema_summary"] == {}
