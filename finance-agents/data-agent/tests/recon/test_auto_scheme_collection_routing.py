from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

DATA_AGENT_ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = DATA_AGENT_ROOT / "graphs" / "recon"
AUTO_SCHEME_DIR = RECON_DIR / "auto_scheme_run"

if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))


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


@pytest.mark.anyio
async def test_hydrate_binding_preserves_dataset_source_type_from_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_dataset(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "success": True,
            "dataset": {
                "id": "dataset-alipay-1",
                "dataset_code": "alipay_bill_lines",
                "business_name": "支付宝账单明细",
                "source_kind": "platform_oauth",
                "provider_code": "alipay",
                "extract_config": {
                    "collection_driver": "alipay_bill_download_import",
                    "dataset_source_type": "alipay_bill_lines",
                    "storage": "alipay_bill_lines",
                },
                "collection_config": {
                    "collection_driver": "alipay_bill_download_import",
                    "dataset_source_type": "alipay_bill_lines",
                },
            },
        }

    async def fake_get_source(*args: object, **kwargs: object) -> dict[str, object]:
        return {"success": False}

    monkeypatch.setattr(nodes, "data_source_get", fake_get_source)
    monkeypatch.setattr(nodes, "data_source_get_dataset", fake_get_dataset)

    hydrated = await nodes._hydrate_binding_source_meta(
        auth_token="token",
        binding={
            "data_source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "resource_key": "alipay_bill_lines:merchant-1",
            "table_name": "alipay_bill_lines",
            "dataset_source_type": "collection_records",
        },
    )

    assert hydrated["dataset_source_type"] == "alipay_bill_lines"
    assert hydrated["collection_driver"] == "alipay_bill_download_import"
    assert hydrated["source_kind"] == "platform_oauth"
    assert hydrated["provider_code"] == "alipay"


def test_build_recon_inputs_uses_hydrated_dataset_source_type() -> None:
    inputs = nodes._build_recon_inputs_from_ready_collections(
        [
            {
                "binding": {
                    "data_source_id": "source-alipay-1",
                    "dataset_id": "dataset-alipay-1",
                    "resource_key": "alipay_bill_lines:merchant-1",
                    "table_name": "alipay_bill_lines",
                    "dataset_source_type": "alipay_bill_lines",
                    "query": {"date_field": "bill_date"},
                },
                "collection_records": {
                    "dataset_id": "dataset-alipay-1",
                    "resource_key": "alipay_bill_lines:merchant-1",
                    "record_count": 1,
                },
            }
        ],
        biz_date="2026-05-06",
    )

    dataset_ref = inputs[0]["payload"]["dataset_ref"]
    assert dataset_ref["source_type"] == "alipay_bill_lines"
    assert dataset_ref["source_key"] == "source-alipay-1"
    assert dataset_ref["query"]["biz_date"] == "2026-05-06"
    assert dataset_ref["query"]["date_field"] == "bill_date"


def test_check_dataset_ready_collection_failure_keeps_collection_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_collect(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "success": False,
            "error": "upstream timeout",
            "collection_driver": "alipay_bill_download_import",
        }

    async def fake_list(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("collection failure should block stale collection record lookup")

    monkeypatch.setattr(nodes, "data_source_trigger_dataset_collection", fake_collect)
    monkeypatch.setattr(nodes, "data_source_list_collection_records", fake_list)

    state = {
        "auth_token": "token",
        "recon_ctx": {
            "biz_date": "2026-05-06",
            "run_context": {"trigger_type": "schedule"},
            "plan_input_bindings": [
                {
                    "data_source_id": "source-alipay-1",
                    "dataset_id": "dataset-alipay-1",
                    "resource_key": "alipay_bill_lines:merchant-1",
                    "table_name": "alipay_bill_lines",
                    "required": True,
                    "collection_driver": "alipay_bill_download_import",
                    "dataset_source_type": "alipay_bill_lines",
                }
            ],
        },
    }

    result = asyncio.run(nodes.check_dataset_ready_node(state))
    recon_ctx = result["recon_ctx"]

    missing_binding = recon_ctx["missing_bindings"][0]
    collection_attempt = recon_ctx["collection_attempts"][0]
    assert missing_binding["error"] == "先同步失败：upstream timeout"
    assert missing_binding["collection_driver"] == "alipay_bill_download_import"
    assert missing_binding["dataset_source_type"] == "alipay_bill_lines"
    assert collection_attempt["collection_driver"] == "alipay_bill_download_import"
    assert collection_attempt["dataset_source_type"] == "alipay_bill_lines"
