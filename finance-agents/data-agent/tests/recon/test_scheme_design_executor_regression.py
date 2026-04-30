from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"
SCHEME_DESIGN_DIR = RECON_DIR / "scheme_design"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)
_ensure_package("graphs.recon.scheme_design", SCHEME_DESIGN_DIR)

executor_module = importlib.import_module("graphs.recon.scheme_design.executor")
models_module = importlib.import_module("models")

FallbackSchemeDesignExecutor = executor_module.FallbackSchemeDesignExecutor
SchemeDesignSession = models_module.SchemeDesignSession
SchemeDesignTargetState = models_module.SchemeDesignTargetState


def _dataset(*, side: str, business_name: str, table_name: str, fields: list[str]) -> dict[str, object]:
    return {
        "side": side,
        "business_name": business_name,
        "dataset_name": table_name,
        "table_name": table_name,
        "resource_key": table_name,
        "field_label_map": {field: field for field in fields},
        "fields": [{"raw_name": field, "display_name": field} for field in fields],
    }


def _build_session() -> object:
    left_dataset = _dataset(
        side="left",
        business_name="交易订单明细表",
        table_name="public.ods_yxst_trd_order_di_o",
        fields=[
            "id",
            "goods_price",
            "pt",
            "root_order_id",
            "tax_sale_amount",
            "order_finish_time",
            "cust_memer_code",
        ],
    )
    right_dataset = _dataset(
        side="right",
        business_name="fp订单表",
        table_name="public.ods_yxst_fp_orders_di_o",
        fields=[
            "id",
            "price",
            "created_at",
            "customer_order_no",
            "total_price",
            "updated_at",
            "merchant_name",
        ],
    )
    return SchemeDesignSession(
        session_id="design_test_proc_fix",
        scheme_name="系统测试方案",
        biz_goal="系统测试：验证 AI 生成 proc json 是否与说明一致",
        target_step=SchemeDesignTargetState(
            left_datasets=[left_dataset],
            right_datasets=[right_dataset],
            left_description="左侧使用交易订单明细表。",
            right_description="右侧使用 fp订单表。",
        ),
        sample_datasets=[left_dataset, right_dataset],
    )


def test_prepare_proc_draft_for_validation_promotes_legacy_source_field_shape() -> None:
    executor = FallbackSchemeDesignExecutor()
    session = _build_session()
    broken_rule = {
        "role_desc": "legacy",
        "file_rule_code": "legacy_proc",
        "steps": [
            {"action": "create_schema", "target_table": "left_recon_ready", "schema": {"columns": []}},
            {
                "type": "write_dataset",
                "output": "left_recon_ready",
                "source": {
                    "table": "public.ods_yxst_trd_order_di_o",
                    "field": {
                        "biz_key": {"type": "source", "expr": "root_order_id"},
                        "amount": {"type": "source", "expr": "tax_sale_amount"},
                        "biz_date": {"type": "source", "expr": "order_finish_time"},
                        "source_name": {"type": "formula", "expr": "'交易订单明细表'"},
                    },
                    "filter": "cust_memer_code = '6974126'",
                },
                "row_write_mode": "upsert",
            },
            {"action": "create_schema", "target_table": "right_recon_ready", "schema": {"columns": []}},
            {
                "action": "write_dataset",
                "target_table": "right_recon_ready",
                "sources": [{"alias": "right_source_1", "table": "public.ods_yxst_fp_orders_di_o"}],
                "mappings": [
                    {
                        "target_field": "biz_key",
                        "value": {"type": "source", "source": {"alias": "right_source_1", "field": "customer_order_no"}},
                    },
                    {
                        "target_field": "amount",
                        "value": {"type": "source", "source": {"alias": "right_source_1", "field": "total_price"}},
                    },
                    {
                        "target_field": "biz_date",
                        "value": {"type": "source", "source": {"alias": "right_source_1", "field": "updated_at"}},
                    },
                ],
            },
        ],
    }

    normalized = executor._prepare_proc_draft_for_validation(session, broken_rule)
    left_write = normalized["steps"][1]

    assert left_write["target_table"] == "left_recon_ready"
    assert left_write["sources"][0]["table"] == "public.ods_yxst_trd_order_di_o"
    assert left_write["mappings"][0]["value"]["source"]["field"] == "root_order_id"
    assert left_write["mappings"][1]["value"]["source"]["field"] == "tax_sale_amount"
    assert left_write["mappings"][2]["value"]["source"]["field"] == "order_finish_time"
    assert left_write["filter"]["bindings"]["ref_filter_1"]["source"]["field"] == "cust_memer_code"
    assert "source" not in left_write
    assert "output" not in left_write


def test_prepare_proc_draft_for_validation_promotes_source_entry_fields_and_match_key() -> None:
    executor = FallbackSchemeDesignExecutor()
    session = _build_session()
    broken_rule = {
        "role_desc": "legacy",
        "file_rule_code": "legacy_proc",
        "steps": [
            {"type": "create_schema", "output": "left_recon_ready", "schema": {"biz_key": "string"}},
            {
                "type": "write_dataset",
                "output": "left_recon_ready",
                "row_write_mode": "upsert",
                "sources": [
                    {
                        "table": "public.ods_yxst_trd_order_di_o",
                        "side": "left",
                        "alias": "left_source_1",
                        "fields": [
                            {"name": "biz_key", "source": {"field": "root_order_id"}},
                            {"name": "amount", "source": {"field": "tax_sale_amount"}},
                            {"name": "biz_date", "source": {"field": "order_finish_time"}},
                            {"name": "source_name", "source": {"formula": {"expr": "'交易订单明细表'"}}},
                        ],
                    }
                ],
            },
            {"type": "create_schema", "output": "right_recon_ready", "schema": {"biz_key": "string"}},
            {
                "type": "write_dataset",
                "output": "right_recon_ready",
                "row_write_mode": "upsert",
                "sources": [
                    {
                        "table": "public.ods_yxst_fp_orders_di_o",
                        "side": "right",
                        "alias": "right_source_1",
                        "fields": [
                            {"name": "biz_key", "source": {"field": "customer_order_no"}},
                            {"name": "amount", "source": {"field": "total_price"}},
                            {"name": "biz_date", "source": {"field": "updated_at"}},
                            {"name": "source_name", "source": {"formula": {"expr": "'fp订单表'"}}},
                        ],
                    }
                ],
            },
        ],
    }

    normalized = executor._prepare_proc_draft_for_validation(session, broken_rule)
    left_write = normalized["steps"][1]
    right_write = normalized["steps"][3]

    assert left_write["mappings"][0]["value"]["source"]["field"] == "root_order_id"
    assert left_write["match"]["sources"][0]["keys"][0]["field"] == "root_order_id"
    assert right_write["mappings"][0]["value"]["source"]["field"] == "customer_order_no"
    assert right_write["match"]["sources"][0]["keys"][0]["field"] == "customer_order_no"
    assert right_write["mappings"][3]["value"]["expr"] == "'fp订单表'"
