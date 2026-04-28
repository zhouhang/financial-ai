from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

auto_run_api = importlib.import_module("graphs.recon.auto_run_api")
binding_date_fields = importlib.import_module("graphs.recon.binding_date_fields")


def _scheme_meta() -> dict[str, object]:
    return {
        "right_time_semantic": "订单更新时间",
        "dataset_bindings": {
            "right": [
                {
                    "dataset_id": "dataset-right",
                    "data_source_id": "source-001",
                    "resource_key": "public.ods_yxst_fp_orders_di_o",
                }
            ]
        },
        "right_output_fields": [
            {
                "id": "parsed_right_2_订单更新时间",
                "outputName": "订单更新时间",
                "sourceField": "updated_at",
                "semanticRole": "time_field",
                "sourceDatasetId": "dataset-right",
            }
        ],
    }


def test_resolve_scheme_source_date_field_uses_raw_source_field_from_camel_meta() -> None:
    source_field = binding_date_fields.resolve_scheme_source_date_field(
        scheme_meta=_scheme_meta(),
        side="right",
        binding={
            "side": "right",
            "data_source_id": "source-001",
            "resource_key": "public.ods_yxst_fp_orders_di_o",
        },
        display_date_field="订单更新时间",
    )

    assert source_field == "updated_at"


def test_normalize_binding_query_date_field_does_not_save_display_name_as_date_field() -> None:
    normalized = binding_date_fields.normalize_binding_query_date_field(
        scheme_meta=_scheme_meta(),
        binding={
            "side": "right",
            "data_source_id": "source-001",
            "resource_key": "public.ods_yxst_fp_orders_di_o",
        },
        query={"resource_key": "public.ods_yxst_fp_orders_di_o", "display_date_field": "订单更新时间"},
        side="right",
    )

    assert normalized["date_field"] == "updated_at"
    assert normalized["display_date_field"] == "订单更新时间"


def test_normalize_run_plan_payload_date_fields_patches_input_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execution_scheme_get(
        auth_token: str,
        *,
        scheme_id: str = "",
        scheme_code: str = "",
    ) -> dict[str, object]:
        return {
            "success": True,
            "scheme": {
                "scheme_code": scheme_code,
                "scheme_meta_json": _scheme_meta(),
            },
        }

    monkeypatch.setattr(auto_run_api, "execution_scheme_get", fake_execution_scheme_get)
    payload = {
        "scheme_code": "scheme_001",
        "input_bindings_json": [
            {
                "side": "right",
                "data_source_id": "source-001",
                "resource_key": "public.ods_yxst_fp_orders_di_o",
                "query": {
                    "resource_key": "public.ods_yxst_fp_orders_di_o",
                    "display_date_field": "订单更新时间",
                },
            }
        ],
        "plan_meta_json": {"input_bindings": []},
    }

    normalized = asyncio.run(
        auto_run_api._normalize_run_plan_payload_date_fields("token", payload)
    )

    query = normalized["input_bindings_json"][0]["query"]
    assert query["date_field"] == "updated_at"
    assert query["display_date_field"] == "订单更新时间"
    assert normalized["plan_meta_json"]["input_bindings"][0]["query"]["date_field"] == "updated_at"
