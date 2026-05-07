from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"
AUTO_SCHEME_DIR = RECON_DIR / "auto_scheme_run"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)
auto_scheme_package = _ensure_package("graphs.recon.auto_scheme_run", AUTO_SCHEME_DIR)


async def _unused_run_auto_scheme_run_graph(*args: object, **kwargs: object) -> dict[str, object]:
    raise AssertionError("run_auto_scheme_run_graph should not be called in this test module")


auto_scheme_package.run_auto_scheme_run_graph = _unused_run_auto_scheme_run_graph

nodes = importlib.import_module("graphs.recon.auto_scheme_run.nodes")


def test_dataset_binding_preserves_platform_order_lines_source_type_and_biz_date() -> None:
    binding = {
        "role_code": "left_1",
        "data_source_id": "taobao-source-001",
        "resource_key": "tmall_orders",
        "filter_config": {
            "dataset_source_type": "platform_order_lines",
            "query": {"display_date_field": "业务日期"},
        },
        "mapping_config": {
            "table_name": "tmall_orders",
            "dataset_code": "tmall_orders",
            "dataset_id": "dataset-taobao-orders",
        },
    }
    scheme_meta = {
        "dataset_bindings": {
            "left": [
                {
                    "dataset_id": "dataset-taobao-orders",
                    "data_source_id": "taobao-source-001",
                    "resource_key": "tmall_orders",
                }
            ]
        },
        "left_output_fields": [
            {
                "outputName": "业务日期",
                "sourceField": "biz_date",
                "semanticRole": "time_field",
                "sourceDatasetId": "dataset-taobao-orders",
            }
        ],
    }

    normalized = nodes._build_plan_binding_from_dataset_binding(
        binding=binding,
        left_time_semantic="业务日期",
        right_time_semantic="",
        scheme_meta=scheme_meta,
    )

    assert normalized is not None
    assert normalized["dataset_source_type"] == "platform_order_lines"
    assert normalized["query"]["date_field"] == "biz_date"
    assert normalized["dataset_ref"] == {
        "source_type": "platform_order_lines",
        "source_key": "taobao-source-001",
        "query": normalized["query"],
    }
