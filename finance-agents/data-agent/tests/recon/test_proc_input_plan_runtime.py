from __future__ import annotations

from pathlib import Path
import importlib.util
import sys

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_AGENT_ROOT = REPO_ROOT / "finance-agents" / "data-agent"
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))
MCP_ROOT = REPO_ROOT / "finance-mcp"
if str(MCP_ROOT) not in sys.path:
    sys.path.append(str(MCP_ROOT))

from proc.mcp_server.steps_runtime import StepsProcRuntime


def _load_dataset_loader_module():
    module_path = MCP_ROOT / "recon" / "mcp_server" / "dataset_loader.py"
    spec = importlib.util.spec_from_file_location("mcp_dataset_loader_for_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dataset_loader = _load_dataset_loader_module()


def test_steps_runtime_keeps_input_plan_alias_frames_isolated_for_same_table(tmp_path: Path) -> None:
    runtime = StepsProcRuntime(
        "test_rule",
        {"steps": []},
        [],
        str(tmp_path),
        preloaded_frames={
            "__input_plan__::ready::base::public.orders": pd.DataFrame([{"id": "base-only"}]),
            "__input_plan__::ready::lookup::public.orders": pd.DataFrame([{"id": "lookup-only"}]),
        },
    )

    alias_frames, _ = runtime._load_alias_frames(
        {
            "target_table": "ready",
            "sources": [
                {"table": "public.orders", "alias": "base"},
                {"table": "public.orders", "alias": "lookup"},
            ],
        }
    )

    assert alias_frames["base"].iloc[0]["id"] == "base-only"
    assert alias_frames["lookup"].iloc[0]["id"] == "lookup-only"


def test_steps_runtime_fails_when_input_plan_alias_frame_missing(tmp_path: Path) -> None:
    runtime = StepsProcRuntime(
        "test_rule",
        {"steps": []},
        [],
        str(tmp_path),
        preloaded_frames={
            "__input_plan__::ready::base::public.orders": pd.DataFrame([{"id": "base-only"}]),
        },
    )

    with pytest.raises(ValueError, match="input_plan 未加载到当前 source 数据"):
        runtime._load_alias_frames(
            {
                "target_table": "ready",
                "sources": [
                    {"table": "public.orders", "alias": "lookup"},
                ],
                "mappings": [
                    {
                        "target_field": "订单号",
                        "value": {
                            "type": "source",
                            "source": {"alias": "lookup", "field": "id"},
                        },
                    }
                ],
            }
        )


def test_steps_runtime_skips_unreferenced_source_missing_from_input_plan(tmp_path: Path) -> None:
    runtime = StepsProcRuntime(
        "test_rule",
        {"steps": []},
        [],
        str(tmp_path),
        preloaded_frames={
            "__input_plan__::ready::fp::public.fp_orders": pd.DataFrame([{"id": "base-only"}]),
        },
    )

    alias_frames, _ = runtime._load_alias_frames(
        {
            "target_table": "ready",
            "sources": [
                {"table": "public.alipay_orders", "alias": "alipay"},
                {"table": "public.fp_orders", "alias": "fp"},
            ],
            "mappings": [
                {
                    "target_field": "订单号",
                    "value": {
                        "type": "source",
                        "source": {"alias": "fp", "field": "id"},
                    },
                }
            ],
        }
    )

    assert list(alias_frames.keys()) == ["fp"]
    assert alias_frames["fp"].iloc[0]["id"] == "base-only"


def test_collection_record_filter_normalizes_common_external_field_types() -> None:
    df = pd.DataFrame({"order_id": [1, 2.0, "003", "A-004"]})

    filtered = dataset_loader._apply_collection_record_scalar_filter(df, "order_id", ["1", "2", "003"])

    assert filtered["order_id"].tolist() == [1, 2.0, "003"]


def test_db_query_builder_supports_keyset_list_filters_with_text_fallback() -> None:
    sql, params = dataset_loader._build_db_query_from_conditions(
        "orders",
        {"filters": {"order_id": ["1", "2"]}},
        {"table": "public.orders"},
        coerce_filters_to_text=True,
    )

    assert '"order_id"::text = ANY(%s)' in sql
    assert params == [["1", "2"]]
