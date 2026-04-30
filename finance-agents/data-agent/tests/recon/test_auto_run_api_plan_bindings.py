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


def _aggregate_time_scheme_meta() -> dict[str, object]:
    return {
        "left_time_semantic": "时间",
        "dataset_bindings": {
            "left": [
                {
                    "dataset_id": "dataset-left",
                    "data_source_id": "source-agg",
                    "resource_key": "public.fp_orders",
                    "business_name": "fp订单表",
                }
            ]
        },
        "left_output_fields": [
            {
                "outputName": "时间",
                "sourceField": "agg_时间",
                "semanticRole": "time_field",
                "sourceDatasetId": "dataset-left",
            }
        ],
        "proc_rule_json": {
            "steps": [
                {
                    "action": "create_schema",
                    "target_table": "left_recon_ready",
                    "schema": {"columns": [{"name": "时间", "data_type": "date"}]},
                },
                {
                    "action": "write_dataset",
                    "target_table": "left_recon_ready",
                    "sources": [{"table": "public.fp_orders", "alias": "source_1"}],
                    "aggregate": [
                        {
                            "source_alias": "source_1",
                            "output_alias": "agg_rule_agg_time",
                            "group_fields": ["merchant_code"],
                            "aggregations": [
                                {"field": "created_at", "operator": "min", "alias": "agg_时间"},
                            ],
                        }
                    ],
                    "mappings": [
                        {
                            "target_field": "时间",
                            "value": {
                                "type": "source",
                                "source": {"alias": "agg_rule_agg_time", "field": "agg_时间"},
                            },
                        }
                    ],
                },
            ]
        },
    }


def _lookup_time_scheme_meta() -> dict[str, object]:
    return {
        "right_time_semantic": "时间",
        "dataset_bindings": {
            "right": [
                {
                    "dataset_id": "dataset-alipay",
                    "data_source_id": "source-alipay",
                    "resource_key": "public.alipay_orders",
                    "business_name": "支付宝订单数据",
                },
                {
                    "dataset_id": "dataset-fp",
                    "data_source_id": "source-fp",
                    "resource_key": "public.fp_orders",
                    "business_name": "fp订单表",
                },
            ]
        },
        "right_output_fields": [
            {
                "outputName": "时间",
                "sourceField": "",
                "semanticRole": "time_field",
                "sourceDatasetId": "",
                "valueMode": "formula",
            }
        ],
        "proc_rule_json": {
            "steps": [
                {
                    "action": "create_schema",
                    "target_table": "right_recon_ready",
                    "schema": {"columns": [{"name": "时间", "data_type": "date"}]},
                },
                {
                    "action": "write_dataset",
                    "target_table": "right_recon_ready",
                    "sources": [
                        {"table": "public.alipay_orders", "alias": "source_1"},
                        {"table": "public.fp_orders", "alias": "source_2"},
                    ],
                    "mappings": [
                        {
                            "target_field": "时间",
                            "value": {
                                "type": "lookup",
                                "source_alias": "source_1",
                                "value_field": "paid_time",
                                "keys": [
                                    {
                                        "lookup_field": "merchant_order_no",
                                        "input": {
                                            "type": "source",
                                            "source": {"alias": "source_2", "field": "customer_order_no"},
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
            ]
        },
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


def test_resolve_scheme_source_date_field_uses_proc_rule_lineage_for_aggregate_time() -> None:
    source_field = binding_date_fields.resolve_scheme_source_date_field(
        scheme_meta=_aggregate_time_scheme_meta(),
        side="left",
        binding={
            "side": "left",
            "data_source_id": "source-agg",
            "resource_key": "public.fp_orders",
        },
        display_date_field="时间",
    )

    assert source_field == "created_at"


def test_resolve_scheme_source_date_field_uses_lookup_value_field_for_matching_binding() -> None:
    source_field = binding_date_fields.resolve_scheme_source_date_field(
        scheme_meta=_lookup_time_scheme_meta(),
        side="right",
        binding={
            "side": "right",
            "data_source_id": "source-alipay",
            "resource_key": "public.alipay_orders",
        },
        display_date_field="时间",
    )

    assert source_field == "paid_time"


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


def test_normalize_binding_query_date_field_strict_mode_rejects_untraceable_time_binding() -> None:
    with pytest.raises(ValueError, match="fp订单表.*无法追溯到该数据集的原始日期字段"):
        binding_date_fields.normalize_binding_query_date_field(
            scheme_meta=_lookup_time_scheme_meta(),
            binding={
                "side": "right",
                "data_source_id": "source-fp",
                "resource_key": "public.fp_orders",
            },
            query={"resource_key": "public.fp_orders", "display_date_field": "时间"},
            side="right",
            strict=True,
        )


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


def test_normalize_run_plan_payload_date_fields_rejects_untraceable_time_binding(
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
                "scheme_meta_json": _lookup_time_scheme_meta(),
            },
        }

    monkeypatch.setattr(auto_run_api, "execution_scheme_get", fake_execution_scheme_get)
    payload = {
        "scheme_code": "scheme_lookup",
        "input_bindings_json": [
            {
                "side": "right",
                "data_source_id": "source-fp",
                "resource_key": "public.fp_orders",
                "query": {
                    "resource_key": "public.fp_orders",
                    "display_date_field": "时间",
                },
            }
        ],
    }

    with pytest.raises(auto_run_api.HTTPException, match="fp订单表.*无法追溯到该数据集的原始日期字段"):
        asyncio.run(auto_run_api._normalize_run_plan_payload_date_fields("token", payload))


def test_normalize_run_plan_payload_date_fields_skips_non_base_input_plan_binding(
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
                "scheme_meta_json": _lookup_time_scheme_meta(),
            },
        }

    monkeypatch.setattr(auto_run_api, "execution_scheme_get", fake_execution_scheme_get)
    payload = {
        "scheme_code": "scheme_lookup",
        "input_bindings_json": [
            {
                "side": "right",
                "data_source_id": "source-alipay",
                "resource_key": "public.alipay_orders",
                "input_plan_read_mode": "by_key_set",
                "input_plan_apply_biz_date_filter": False,
                "query": {"resource_key": "public.alipay_orders"},
            }
        ],
    }

    normalized = asyncio.run(auto_run_api._normalize_run_plan_payload_date_fields("token", payload))

    query = normalized["input_bindings_json"][0]["query"]
    assert "date_field" not in query
    assert "biz_date_field" not in query
