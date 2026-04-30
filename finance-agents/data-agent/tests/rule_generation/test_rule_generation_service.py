from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
REPO_ROOT = Path(__file__).resolve().parents[4]
MCP_ROOT = REPO_ROOT / "finance-mcp"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from graphs.rule_generation.proc.ir_compiler import compile_understanding_into_rule
from graphs.rule_generation.proc.ir_dsl_consistency import check_ir_dsl_consistency
from graphs.rule_generation.proc.ir_linter import lint_rule_generation_ir
from graphs.rule_generation.proc.linter import lint_proc_rule
from graphs.rule_generation.proc.prompts import build_ir_repair_prompt, build_understanding_prompt
from graphs.rule_generation.proc.rule_builder import build_proc_rule_skeleton_from_ir
from graphs.rule_generation.proc.sample_diagnostics import diagnose_proc_sample
from graphs.rule_generation.proc.understanding import normalize_understanding
from graphs.rule_generation.input_plan import (
    execute_input_plan_preview,
    generate_input_plan_from_proc,
    validate_input_plan,
)
from graphs.rule_generation.service import (
    RuleGenerationService,
    _normalize_generated_proc_rule,
    _source_profile,
    _validate_understanding,
)


async def _collect_events(stream) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    async for event in stream:
        events.append(event)
    return events


def _contains_value_type(value: object, expected_type: str) -> bool:
    if isinstance(value, dict):
        if str(value.get("type") or "") == expected_type:
            return True
        return any(_contains_value_type(item, expected_type) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value_type(item, expected_type) for item in value)
    return False


def _source_payload() -> dict[str, object]:
    return {
        "id": "dataset_1",
        "table_name": "public.trade_orders",
        "business_name": "交易订单明细表",
        "field_label_map": {
            "customer_order_no": "客户订单号",
            "tax_sale_amount": "含税销售金额",
            "customer_member_code": "客户会员编码",
            "order_finish_time": "订单完成时间",
            "overdue_amount": "逾期金额",
        },
        "fields": [
            {"name": "customer_order_no", "label": "客户订单号", "data_type": "string"},
            {"name": "tax_sale_amount", "label": "含税销售金额", "data_type": "decimal"},
            {"name": "customer_member_code", "label": "客户会员编码", "data_type": "string"},
            {"name": "order_finish_time", "label": "订单完成时间", "data_type": "date"},
            {"name": "overdue_amount", "label": "逾期金额", "data_type": "decimal"},
        ],
        "sample_rows": [
            {
                "customer_order_no": "ORD-001",
                "tax_sale_amount": 100.23,
                "customer_member_code": "CUST_MEMBER_001",
                "order_finish_time": "2026-04-18",
                "overdue_amount": 80.0,
            }
        ],
    }


def _trade_order_source_with_member_aliases_payload() -> dict[str, object]:
    return {
        "id": "trade_orders",
        "table_name": "public.ods_yxst_trd_order_di_o",
        "business_name": "交易订单明细表",
        "field_label_map": {
            "root_order_id": "根订单号",
            "tax_sale_amount": "含税销售金额",
            "order_finish_time": "订单完成时间",
            "cust_memer_code": "客户会员编码",
            "member_code": "会员编码",
        },
        "fields": [
            {"name": "root_order_id", "label": "根订单号", "data_type": "string"},
            {"name": "tax_sale_amount", "label": "含税销售金额", "data_type": "decimal"},
            {"name": "order_finish_time", "label": "订单完成时间", "data_type": "date"},
            {"name": "cust_memer_code", "label": "客户会员编码", "data_type": "string"},
            {"name": "member_code", "label": "会员编码", "data_type": "string"},
        ],
        "sample_rows": [
            {
                "root_order_id": "ROOT-001",
                "tax_sale_amount": 100.0,
                "order_finish_time": "2026-04-18",
                "cust_memer_code": "6965404",
                "member_code": "MEM-001",
            }
        ],
    }


def _fp_order_source_payload() -> dict[str, object]:
    return {
        "id": "fp_orders",
        "table_name": "public.fp_orders",
        "business_name": "fp订单表",
        "field_label_map": {
            "purchase_order_id": "采购订单ID",
            "customer_order_no": "客户订单号",
            "order_create_time": "订单创建时间",
        },
        "fields": [
            {"name": "purchase_order_id", "label": "采购订单ID", "data_type": "string"},
            {"name": "customer_order_no", "label": "客户订单号", "data_type": "string"},
            {"name": "order_create_time", "label": "订单创建时间", "data_type": "date"},
        ],
        "sample_rows": [
            {
                "purchase_order_id": "PO-001",
                "customer_order_no": "M-001",
                "order_create_time": "2026-04-16 09:10:00",
            }
        ],
    }


def _fp_sales_source_payload() -> dict[str, object]:
    source = _fp_order_source_payload()
    source["field_label_map"] = {
        **source["field_label_map"],
        "total_sale_amount": "销售总金额",
    }
    source["fields"] = [
        *source["fields"],
        {"name": "total_sale_amount", "label": "销售总金额", "data_type": "decimal"},
    ]
    source["sample_rows"] = [
        {
            **source["sample_rows"][0],
            "total_sale_amount": 100.0,
        }
    ]
    return source


def _fp_projection_source_payload() -> dict[str, object]:
    return {
        "id": "fp_orders",
        "table_name": "public.fp_orders",
        "business_name": "fp订单表",
        "field_label_map": {
            "sales_merchant_code": "销售商户编码",
            "charge_account": "充值账号",
            "purchase_total_amount": "采购总金额",
            "order_create_time": "订单创建时间",
            "remark": "订单备注",
        },
        "fields": [
            {"name": "sales_merchant_code", "label": "销售商户编码", "data_type": "string"},
            {"name": "charge_account", "label": "充值账号", "data_type": "string"},
            {"name": "purchase_total_amount", "label": "采购总金额", "data_type": "decimal"},
            {"name": "order_create_time", "label": "订单创建时间", "data_type": "date"},
            {"name": "remark", "label": "订单备注", "data_type": "string"},
        ],
        "sample_rows": [
            {
                "sales_merchant_code": "merchant_001",
                "charge_account": "charge_001",
                "purchase_total_amount": 120.5,
                "order_create_time": "2026-04-16 09:10:00",
                "remark": "seed",
            }
        ],
    }


def _alipay_order_source_payload() -> dict[str, object]:
    return {
        "id": "alipay_orders",
        "table_name": "public.alipay_orders",
        "business_name": "支付宝订单数据",
        "field_label_map": {
            "merchant_order_no": "商户订单号",
            "order_amount": "订单金额(元)",
            "buyer_info": "买家信息",
        },
        "fields": [
            {"name": "merchant_order_no", "label": "商户订单号", "data_type": "string"},
            {"name": "order_amount", "label": "订单金额(元)", "data_type": "decimal"},
            {"name": "buyer_info", "label": "买家信息", "data_type": "string"},
        ],
        "sample_rows": [
            {
                "merchant_order_no": "M-001",
                "order_amount": 88.12,
                "buyer_info": "buyer_1",
            }
        ],
    }


def test_input_plan_infers_lookup_table_keyset_read() -> None:
    rule = {
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {"columns": [{"name": "订单号", "data_type": "string"}]},
            },
            {
                "step_id": "write_left_recon_ready",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "mappings": [
                    {
                        "target_field": "订单号",
                        "value": {"type": "source", "source": {"alias": "fp", "field": "customer_order_no"}},
                    },
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "lookup",
                            "source_alias": "alipay",
                            "value_field": "order_amount",
                            "keys": [
                                {
                                    "lookup_field": "merchant_order_no",
                                    "input": {
                                        "type": "source",
                                        "source": {"alias": "fp", "field": "customer_order_no"},
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
        ],
    }

    plan = generate_input_plan_from_proc(
        rule_json=rule,
        sources=[_fp_order_source_payload(), _alipay_order_source_payload()],
        target_table="left_recon_ready",
    )
    validation = validate_input_plan(
        plan,
        rule_json=rule,
        sources=[_fp_order_source_payload(), _alipay_order_source_payload()],
        target_table="left_recon_ready",
    )
    preview = execute_input_plan_preview(
        plan,
        sources=[_fp_order_source_payload(), _alipay_order_source_payload()],
    )

    alipay_plan = next(item for item in plan["datasets"] if item["alias"] == "alipay")
    assert alipay_plan["read_mode"] == "by_key_set"
    assert alipay_plan["depends_on_alias"] == "fp"
    assert alipay_plan["key_from_field"] == "customer_order_no"
    assert alipay_plan["key_to_field"] == "merchant_order_no"
    assert validation["success"] is True
    assert preview["success"] is True


def test_input_plan_prunes_selected_but_unreferenced_source() -> None:
    rule = {
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {"columns": [{"name": "商户编码", "data_type": "string"}]},
            },
            {
                "step_id": "write_left_recon_ready",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.alipay_orders", "alias": "alipay"},
                    {"table": "public.fp_orders", "alias": "fp"},
                ],
                "mappings": [
                    {
                        "target_field": "商户编码",
                        "value": {
                            "type": "source",
                            "source": {"alias": "fp", "field": "customer_order_no"},
                        },
                    },
                ],
            },
        ],
    }

    plan = generate_input_plan_from_proc(
        rule_json=rule,
        sources=[_alipay_order_source_payload(), _fp_order_source_payload()],
        target_table="left_recon_ready",
    )
    validation = validate_input_plan(
        plan,
        rule_json=rule,
        sources=[_alipay_order_source_payload(), _fp_order_source_payload()],
        target_table="left_recon_ready",
    )

    assert [item["alias"] for item in plan["datasets"]] == ["fp"]
    assert plan["datasets"][0]["read_mode"] == "base"
    assert validation["success"] is True


def _simple_rule() -> dict[str, object]:
    return {
        "role_desc": "测试规则",
        "version": "1.0",
        "metadata": {"author": "test"},
        "global_config": {
            "default_round_precision": 2,
            "date_format": "YYYY-MM-DD",
            "null_value_handling": "keep",
            "error_handling": "stop",
        },
        "file_rule_code": "test_rule",
        "dsl_constraints": {
            "actions": ["create_schema", "write_dataset"],
            "builtin_functions": ["current_date", "month_of", "add_months"],
            "aggregate_operators": ["sum", "min"],
            "field_write_modes": ["overwrite", "increment"],
            "row_write_modes": ["insert_if_missing", "update_only", "upsert"],
            "column_data_types": ["string", "date", "decimal"],
            "value_node_types": ["source", "formula", "template_source", "function", "context", "lookup"],
            "merge_strategies": ["union_distinct"],
            "loop_context_vars": [],
        },
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "primary_key": ["biz_key"],
                    "columns": [
                        {"name": "biz_key", "data_type": "string", "nullable": False},
                        {"name": "amount", "data_type": "decimal", "precision": 18, "scale": 2},
                        {"name": "biz_date", "data_type": "date", "nullable": True},
                    ],
                },
            },
            {
                "step_id": "write_left_recon_ready",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "depends_on": ["create_left_recon_ready"],
                "row_write_mode": "upsert",
                "sources": [{"table": "public.trade_orders", "alias": "orders"}],
                "mappings": [
                    {
                        "target_field": "biz_key",
                        "value": {"type": "source", "source": {"alias": "orders", "field": "customer_order_no"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "amount",
                        "value": {"type": "source", "source": {"alias": "orders", "field": "tax_sale_amount"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "biz_date",
                        "value": {"type": "source", "source": {"alias": "orders", "field": "order_finish_time"}},
                        "field_write_mode": "overwrite",
                    },
                ],
            },
        ],
    }


def test_clause_like_filter_reference_is_repaired_before_user_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuleGenerationService()
    source = _source_payload()
    generated_rule = _simple_rule()

    llm_responses = iter([
        {
            "understanding": {
                "rule_summary": "只保留指定会员编码并生成对账准备数据",
                "source_references": [
                    {
                        "ref_id": "ref_filter",
                        "semantic_name": "客户会员编码只保留CUST_MEMBER_001的数据",
                        "usage": "filter_field",
                        "must_bind": True,
                        "candidate_fields": [
                            {
                                "raw_name": "customer_member_code",
                                "display_name": "客户会员编码",
                                "source_table": "public.trade_orders",
                            }
                        ],
                    },
                    {
                        "ref_id": "ref_key",
                        "semantic_name": "客户订单号",
                        "usage": "match_key",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "含税销售金额",
                        "usage": "compare_field",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_time",
                        "semantic_name": "订单完成时间",
                        "usage": "time_field",
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {"output_id": "out_1", "name": "biz_key", "kind": "rename", "source_ref_ids": ["ref_key"]},
                    {"output_id": "out_2", "name": "amount", "kind": "rename", "source_ref_ids": ["ref_amount"]},
                    {"output_id": "out_3", "name": "biz_date", "kind": "rename", "source_ref_ids": ["ref_time"]},
                ],
                "business_rules": [],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        {
            "understanding": {
                "rule_summary": "只保留指定会员编码并生成对账准备数据",
                "source_references": [
                    {
                        "ref_id": "ref_filter",
                        "semantic_name": "客户会员编码",
                        "usage": "filter_field",
                        "must_bind": True,
                        "candidate_fields": [
                            {
                                "raw_name": "customer_member_code",
                                "display_name": "客户会员编码",
                                "source_table": "public.trade_orders",
                            }
                        ],
                    },
                    {
                        "ref_id": "ref_key",
                        "semantic_name": "客户订单号",
                        "usage": "match_key",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "含税销售金额",
                        "usage": "compare_field",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_time",
                        "semantic_name": "订单完成时间",
                        "usage": "time_field",
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {"output_id": "out_1", "name": "biz_key", "kind": "rename", "source_ref_ids": ["ref_key"]},
                    {"output_id": "out_2", "name": "amount", "kind": "rename", "source_ref_ids": ["ref_amount"]},
                    {"output_id": "out_3", "name": "biz_date", "kind": "rename", "source_ref_ids": ["ref_time"]},
                ],
                "business_rules": [
                    {
                        "rule_id": "rule_filter",
                        "type": "filter",
                        "description": "只保留客户会员编码等于 CUST_MEMBER_001 的数据",
                        "related_ref_ids": ["ref_filter"],
                        "predicate": {
                            "op": "eq",
                            "left": {"op": "ref", "ref_id": "ref_filter"},
                            "right": {"op": "constant", "value": "CUST_MEMBER_001"},
                        },
                    }
                ],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        generated_rule,
    ])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "normalized_rule": generated_rule,
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [
                        {"biz_key": "ORD-001", "amount": 100.23, "biz_date": "2026-04-18"},
                    ],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    result = asyncio.run(
        service.run_proc_side(
            auth_token="token",
            payload={
                "side": "left",
                "target_table": "left_recon_ready",
                "rule_text": "客户订单号作为匹配字段，含税销售金额作为对比字段，客户会员编码只保留CUST_MEMBER_001的数据，订单完成时间作为时间字段",
                "sources": [source],
            },
        )
    )

    assert result["event"] == "graph_completed"
    assert result["status"] == "succeeded"
    assert result["output_preview_rows"] == [{"biz_key": "ORD-001", "amount": 100.23, "biz_date": "2026-04-18"}]
    assert result["understanding"]["source_references"][0]["semantic_name"] == "客户会员编码"
    write_step = result["proc_rule_json"]["steps"][1]
    assert write_step["filter"]["expr"] == "(({ref_filter_1} == 'CUST_MEMBER_001'))"
    assert write_step["filter"]["bindings"]["ref_filter_1"]["source"]["field"] == "customer_member_code"


def test_ambiguous_time_field_requires_user_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuleGenerationService()
    source = _source_payload()

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return {
            "understanding": {
                "rule_summary": "时间字段存在歧义",
                "source_references": [
                    {
                        "ref_id": "ref_time",
                        "semantic_name": "订单时间",
                        "usage": "time_field",
                        "must_bind": True,
                        "candidate_fields": [
                            {
                                "raw_name": "order_finish_time",
                                "display_name": "订单完成时间",
                                "source_table": "public.trade_orders",
                            },
                            {
                                "raw_name": "customer_order_no",
                                "display_name": "客户订单号",
                                "source_table": "public.trade_orders",
                            },
                        ],
                    }
                ],
                "output_specs": [],
                "business_rules": [],
            },
            "assumptions": [],
            "ambiguities": [],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)

    result = asyncio.run(
        service.run_proc_side(
            auth_token="token",
            payload={
                "side": "left",
                "target_table": "left_recon_ready",
                "rule_text": "订单时间作为时间字段",
                "sources": [source],
            },
        )
    )

    assert result["event"] == "needs_user_input"
    assert result["status"] == "needs_user_input"
    assert result["questions"]
    assert "订单时间" in result["questions"][0]["question"]


def test_missing_short_source_field_prompts_user_before_ir_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuleGenerationService()
    source = _alipay_order_source_payload()
    source["field_label_map"] = {
        **source["field_label_map"],
        "refund_amount": "退款金额(元)",
        "fee_rate": "费率",
    }
    source["fields"] = [
        *source["fields"],
        {"name": "refund_amount", "label": "退款金额(元)", "data_type": "decimal"},
        {"name": "fee_rate", "label": "费率", "data_type": "decimal"},
    ]

    llm_calls = 0

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        nonlocal llm_calls
        llm_calls += 1
        return {
            "understanding": {
                "rule_summary": "选择支付宝订单数据但描述了不存在的销售金额字段",
                "source_references": [
                    {
                        "ref_id": "ref_key",
                        "semantic_name": "客户订单号",
                        "usage": "match_key",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "含税销售金额",
                        "usage": "compare_field",
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {"output_id": "out_key", "name": "订单号", "kind": "rename", "source_ref_ids": ["ref_key"]},
                    {"output_id": "out_amount", "name": "金额", "kind": "rename", "source_ref_ids": ["ref_amount"]},
                ],
                "business_rules": [],
            },
            "assumptions": [],
            "ambiguities": [],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)

    result = asyncio.run(
        service.run_proc_side(
            auth_token="token",
            payload={
                "side": "left",
                "target_table": "left_recon_ready",
                "rule_text": "客户订单号作为匹配字段\n含税销售金额作为对比字段",
                "sources": [source],
            },
        )
    )

    assert result["event"] == "needs_user_input"
    assert result["status"] == "needs_user_input"
    assert result["phase"] == "validate_ir_structure"
    assert llm_calls == 1
    amount_question = next(
        question for question in result["questions"] if question["mention"] == "含税销售金额"
    )
    candidate_labels = [candidate["display_name"] for candidate in amount_question["candidates"]]
    assert "订单金额(元)" in candidate_labels
    assert amount_question["role"] == "compare_field"


def test_derived_output_specs_are_not_treated_as_source_field_ambiguities() -> None:
    source_profiles = [_source_profile(_source_payload())]
    understanding = normalize_understanding(
        {
            "rule_summary": "基于逾期金额计算坏账金额",
            "source_references": [
                {
                    "ref_id": "ref_overdue",
                    "semantic_name": "逾期金额",
                    "usage": "source_value",
                    "must_bind": True,
                }
            ],
            "output_specs": [
                {
                    "output_id": "out_bad_debt",
                    "name": "坏账金额",
                    "kind": "formula",
                    "source_ref_ids": ["ref_overdue"],
                    "expression": {
                        "op": "multiply",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_overdue"},
                            {"op": "constant", "value": 1.15},
                        ],
                    },
                    "expression_hint": "逾期金额 * 1.15",
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_bad_debt",
                    "type": "derive",
                    "description": "坏账金额按逾期金额的 1.15 倍计算",
                    "related_ref_ids": ["ref_overdue"],
                }
            ],
        },
        rule_text="根据逾期金额计算坏账金额",
        target_table="risk_asset_ready",
    )

    issues = _validate_understanding(understanding, source_profiles=source_profiles)

    assert issues == []


def test_validate_ir_structure_accepts_business_name_table_scope() -> None:
    source_profiles = [
        _source_profile(_fp_order_source_payload()),
        _source_profile(_alipay_order_source_payload()),
    ]
    understanding = normalize_understanding(
        {
            "rule_summary": "按业务数据集名称限定字段来源",
            "source_references": [
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["fp订单表"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["支付宝订单数据"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_order_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["支付宝订单数据"],
                    "must_bind": True,
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "join_derived",
                    "source_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_order_amount",
                    ],
                }
            ],
            "business_rules": [],
        },
        rule_text="金额为fp订单表的客户订单号与支付宝订单数据的商户订单号关联，取出订单金额",
        target_table="left_recon_ready",
    )

    issues = _validate_understanding(understanding, source_profiles=source_profiles)

    assert issues == []


def test_assignment_left_side_output_aliases_trigger_understanding_repair_not_user_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RuleGenerationService()
    fp_source = _fp_order_source_payload()
    alipay_source = _alipay_order_source_payload()
    generated_rule = {
        "role_desc": "测试规则",
        "version": "1.0",
        "metadata": {"author": "test"},
        "global_config": {},
        "file_rule_code": "test_rule",
        "dsl_constraints": {"actions": ["create_schema", "write_dataset"]},
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                        {"name": "订单时间", "data_type": "date"},
                    ],
                },
            },
            {
                "step_id": "write_left_recon_ready",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "row_write_mode": "upsert",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "mappings": [
                    {
                        "target_field": "订单号",
                        "value": {"type": "source", "source": {"alias": "fp", "field": "purchase_order_id"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "lookup",
                            "source_alias": "alipay",
                            "value_field": "order_amount",
                            "keys": [
                                {
                                    "lookup_field": "merchant_order_no",
                                    "input": {
                                        "type": "source",
                                        "source": {"alias": "fp", "field": "customer_order_no"},
                                    },
                                }
                            ],
                        },
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "订单时间",
                        "value": {"type": "source", "source": {"alias": "fp", "field": "order_create_time"}},
                        "field_write_mode": "overwrite",
                    },
                ],
            },
        ],
    }

    llm_responses = iter([
        {
            "understanding": {
                "rule_summary": "根据两张表生成派生输出字段",
                "source_references": [
                    {"ref_id": "ref_order_no", "semantic_name": "订单号", "usage": "match_key", "must_bind": True},
                    {"ref_id": "ref_amount", "semantic_name": "金额", "usage": "compare_field", "must_bind": True},
                    {"ref_id": "ref_time", "semantic_name": "订单时间", "usage": "time_field", "must_bind": True},
                ],
                "output_specs": [
                    {"output_id": "out_order_no", "name": "订单号", "kind": "rename", "source_ref_ids": ["ref_order_no"], "description": "fp订单表的采购订单ID"},
                    {"output_id": "out_amount", "name": "金额", "kind": "join_derived", "source_ref_ids": ["ref_amount"], "description": "fp订单表的客户订单号关联支付宝订单数据的商户订单号，获取订单金额"},
                    {"output_id": "out_time", "name": "订单时间", "kind": "rename", "source_ref_ids": ["ref_time"], "description": "fp订单表订单创建时间"},
                ],
                "business_rules": [],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        {
            "understanding": {
                "rule_summary": "根据两张表生成派生输出字段",
                "source_references": [
                    {
                        "ref_id": "ref_purchase_order_id",
                        "semantic_name": "采购订单ID",
                        "usage": "source_value",
                        "table_scope": ["public.fp_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_fp_customer_order_no",
                        "semantic_name": "客户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.fp_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_alipay_merchant_order_no",
                        "semantic_name": "商户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_order_amount",
                        "semantic_name": "订单金额",
                        "usage": "source_value",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_order_create_time",
                        "semantic_name": "订单创建时间",
                        "usage": "time_field",
                        "table_scope": ["public.fp_orders"],
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {"output_id": "out_order_no", "name": "订单号", "kind": "rename", "source_ref_ids": ["ref_purchase_order_id"]},
                    {
                        "output_id": "out_amount",
                        "name": "金额",
                        "kind": "join_derived",
                        "source_ref_ids": ["ref_fp_customer_order_no", "ref_alipay_merchant_order_no", "ref_order_amount"],
                        "description": "fp订单表的客户订单号关联支付宝订单数据的商户订单号，获取订单金额",
                    },
                    {"output_id": "out_time", "name": "订单时间", "kind": "rename", "source_ref_ids": ["ref_order_create_time"]},
                ],
                "business_rules": [
                    {
                        "rule_id": "join_alipay_amount",
                        "type": "join",
                        "description": "fp客户订单号关联支付宝商户订单号取订单金额",
                        "related_ref_ids": ["ref_fp_customer_order_no", "ref_alipay_merchant_order_no", "ref_order_amount"],
                    }
                ],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        generated_rule,
    ])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "normalized_rule": generated_rule,
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"订单号": "PO-001", "金额": 88.12, "订单时间": "2026-04-16 09:10:00"}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    result = asyncio.run(
        service.run_proc_side(
            auth_token="token",
            payload={
                "side": "left",
                "target_table": "left_recon_ready",
                "rule_text": (
                    "订单号=fp订单表的采购订单ID\n"
                    "金额=fp订单表的客户订单号关联支付宝订单数据的商户订单号，获取订单金额\n"
                    "订单时间为fp订单表订单创建时间"
                ),
                "sources": [fp_source, alipay_source],
            },
        )
    )

    assert result["event"] == "graph_completed"
    assert result["status"] == "succeeded"
    semantic_names = {item["semantic_name"] for item in result["understanding"]["source_references"]}
    assert "订单号" not in semantic_names
    assert "金额" not in semantic_names
    assert "订单时间" not in semantic_names
    assert {"采购订单ID", "客户订单号", "商户订单号", "订单金额", "订单创建时间"}.issubset(semantic_names)


def test_rule_generation_returns_input_plan_and_uses_preview_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RuleGenerationService()
    fp_source = _fp_order_source_payload()
    alipay_source = _alipay_order_source_payload()
    alipay_source["sample_rows"] = [
        {"merchant_order_no": "M-001", "order_amount": 88.12, "buyer_info": "buyer_1"},
        {"merchant_order_no": "M-999", "order_amount": 1.23, "buyer_info": "buyer_2"},
    ]

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return {
            "understanding": {
                "rule_summary": "fp订单关联支付宝订单金额",
                "source_references": [
                    {
                        "ref_id": "ref_fp_order_no",
                        "semantic_name": "客户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.fp_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_alipay_order_no",
                        "semantic_name": "商户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "订单金额",
                        "usage": "source_value",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {
                        "output_id": "out_amount",
                        "name": "金额",
                        "kind": "join_derived",
                        "source_ref_ids": ["ref_fp_order_no", "ref_alipay_order_no", "ref_amount"],
                    },
                ],
                "business_rules": [
                    {
                        "rule_id": "join_amount",
                        "type": "join",
                        "description": "fp客户订单号关联支付宝商户订单号取订单金额",
                        "related_ref_ids": ["ref_fp_order_no", "ref_alipay_order_no", "ref_amount"],
                    }
                ],
            },
            "assumptions": [],
            "ambiguities": [],
        }

    captured_sources: list[dict[str, object]] = []

    async def fake_run_proc_sample(**kwargs: object) -> dict[str, object]:
        captured_sources.extend(kwargs.get("sources") or [])
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"金额": 88.12}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    result = asyncio.run(
        service.run_proc_side(
            auth_token="token",
            payload={
                "side": "left",
                "target_table": "left_recon_ready",
                "rule_text": "金额=fp订单表的客户订单号关联支付宝订单数据的商户订单号，获取订单金额",
                "sources": [fp_source, alipay_source],
            },
        )
    )

    assert result["event"] == "graph_completed"
    assert result["input_plan_json"]["datasets"]
    alipay_plan = next(item for item in result["input_plan_json"]["datasets"] if item["alias"] == "source_2")
    assert alipay_plan["read_mode"] == "by_key_set"
    alipay_sample = next(item for item in captured_sources if item["table_name"] == "public.alipay_orders")
    assert alipay_sample["sample_rows"] == [
        {"merchant_order_no": "M-001", "order_amount": 88.12, "buyer_info": "buyer_1"}
    ]


def test_normalize_understanding_builds_structured_expression_and_predicate() -> None:
    understanding = normalize_understanding(
        {
            "rule_summary": "订单金额加 10，只保留指定买家",
            "source_references": [
                {"ref_id": "ref_amount", "semantic_name": "订单金额", "usage": "source_value"},
                {"ref_id": "ref_buyer", "semantic_name": "买家信息", "usage": "filter_field"},
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "输出金额",
                    "kind": "formula",
                    "expression": {
                        "operator": "+",
                        "left": {"ref_id": "ref_amount"},
                        "right": {"value": 10},
                    },
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_filter",
                    "type": "filter",
                    "condition": {
                        "operator": "=",
                        "ref_id": "ref_buyer",
                        "value": "buyer_1",
                    },
                }
            ],
        },
        rule_text="输出金额字段=订单金额+10，买家信息只取buyer_1的数据",
        target_table="left_recon_ready",
    )

    assert understanding["output_specs"][0]["expression"] == {
        "op": "add",
        "operands": [
            {"op": "ref", "ref_id": "ref_amount"},
            {"op": "constant", "value": 10},
        ],
    }
    assert understanding["business_rules"][0]["predicate"] == {
        "op": "eq",
        "left": {"op": "ref", "ref_id": "ref_buyer"},
        "right": {"op": "constant", "value": "buyer_1"},
    }


def test_normalize_understanding_accepts_common_not_empty_predicate_aliases() -> None:
    understanding = normalize_understanding(
        {
            "rule_summary": "只保留客户订单号不为空的数据",
            "source_references": [
                {"ref_id": "ref_order_no", "semantic_name": "客户订单号", "usage": "filter_field"},
            ],
            "business_rules": [
                {
                    "rule_id": "rule_filter",
                    "type": "filter",
                    "predicate": {
                        "op": "is_not_empty",
                        "field_ref_id": "ref_order_no",
                    },
                }
            ],
        },
        rule_text="取客户订单号不为空的数据",
        target_table="left_recon_ready",
    )

    assert understanding["business_rules"][0]["predicate"] == {
        "op": "exists",
        "operand": {"op": "ref", "ref_id": "ref_order_no"},
    }
    result = lint_rule_generation_ir(understanding, field_bindings=[])
    reasons = {item.get("reason") for item in result.get("errors") or []}
    assert "business_rule_missing_filter_predicate" not in reasons


def test_ir_repair_prompt_turns_missing_filter_predicate_into_required_repair() -> None:
    prompt = build_ir_repair_prompt(
        {
            "rule_text": "取客户订单号不为空的数据",
            "understanding": {
                "business_rules": [
                    {
                        "rule_id": "rule_filter_1",
                        "type": "filter",
                        "description": "过滤出客户订单号不为空的数据。",
                    }
                ]
            },
        },
        failures=[
            {
                "stage": "lint_ir",
                "reason": "business_rule_missing_filter_predicate",
                "rule_id": "rule_filter_1",
                "message": "business_rule 缺少结构化 predicate。",
            }
        ],
    )

    assert "complete_filter_predicate" in prompt
    assert "rule_filter_1" in prompt


def test_lint_rule_generation_ir_requires_structured_filter_predicate_and_formula_expression() -> None:
    understanding = normalize_understanding(
        {
            "rule_summary": "订单金额加 10，只保留指定买家",
            "source_references": [
                {"ref_id": "ref_amount", "semantic_name": "含税销售金额", "usage": "source_value"},
                {"ref_id": "ref_buyer", "semantic_name": "客户会员编码", "usage": "filter_field"},
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "输出金额",
                    "kind": "formula",
                    "expression_hint": "含税销售金额 + 10",
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_filter",
                    "type": "filter",
                    "description": "只保留客户会员编码等于 CUST_MEMBER_001 的数据",
                    "related_ref_ids": ["ref_buyer"],
                }
            ],
        },
        rule_text="输出金额字段=含税销售金额+10，客户会员编码只保留CUST_MEMBER_001的数据",
        target_table="left_recon_ready",
    )

    result = lint_rule_generation_ir(understanding, field_bindings=[])
    reasons = {item.get("reason") for item in result["errors"]}

    assert result["success"] is False
    assert "output_spec_missing_expression" in reasons
    assert "business_rule_missing_filter_predicate" in reasons


def test_lint_rule_generation_ir_rejects_unknown_output_ref_and_missing_filter_predicate() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {"ref_id": "ref_amount", "semantic_name": "含税销售金额", "usage": "source_value"},
                {"ref_id": "ref_member", "semantic_name": "客户会员编码", "usage": "filter_field"},
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "输出金额",
                    "kind": "rename",
                    "source_ref_ids": ["ref_missing"],
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_filter",
                    "type": "filter",
                    "description": "只保留指定客户会员编码",
                    "related_ref_ids": ["ref_member"],
                }
            ],
        },
        rule_text="输出金额取含税销售金额，只保留指定客户会员编码",
        target_table="left_recon_ready",
    )

    result = lint_rule_generation_ir(understanding, field_bindings=[])

    assert result["success"] is False
    reasons = {item.get("reason") for item in result["errors"]}
    assert "output_spec_unknown_source_ref_id" in reasons
    assert "business_rule_missing_filter_predicate" in reasons


def test_ir_lint_failure_is_repaired_before_dsl_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuleGenerationService()
    source = _source_payload()
    generated_rule = _simple_rule()
    generated_rule["steps"][0]["schema"]["primary_key"] = []
    generated_rule["steps"][0]["schema"]["columns"] = [
        {"name": "amount", "data_type": "decimal", "precision": 18, "scale": 2}
    ]
    generated_rule["steps"][1]["mappings"] = [
        {
            "target_field": "amount",
            "value": {"type": "source", "source": {"alias": "orders", "field": "tax_sale_amount"}},
            "field_write_mode": "overwrite",
        }
    ]

    llm_responses = iter([
        {
            "understanding": {
                "rule_summary": "输出金额取含税销售金额",
                "source_references": [
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "含税销售金额",
                        "usage": "source_value",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_member",
                        "semantic_name": "客户会员编码",
                        "usage": "filter_field",
                        "must_bind": True,
                    }
                ],
                "output_specs": [
                    {
                        "output_id": "out_amount",
                        "name": "amount",
                        "kind": "rename",
                        "source_ref_ids": ["ref_missing"],
                    }
                ],
                "business_rules": [
                    {
                        "rule_id": "rule_filter",
                        "type": "filter",
                        "description": "只保留客户会员编码等于 CUST_MEMBER_001 的数据",
                        "related_ref_ids": ["ref_member"],
                    }
                ],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        {
            "understanding": {
                "rule_summary": "输出金额取含税销售金额",
                "source_references": [
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "含税销售金额",
                        "usage": "source_value",
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_member",
                        "semantic_name": "客户会员编码",
                        "usage": "filter_field",
                        "must_bind": True,
                    }
                ],
                "output_specs": [
                    {
                        "output_id": "out_amount",
                        "name": "amount",
                        "kind": "rename",
                        "source_ref_ids": ["ref_amount"],
                    }
                ],
                "business_rules": [
                    {
                        "rule_id": "rule_filter",
                        "type": "filter",
                        "description": "只保留客户会员编码等于 CUST_MEMBER_001 的数据",
                        "related_ref_ids": ["ref_member"],
                        "predicate": {
                            "op": "eq",
                            "left": {"op": "ref", "ref_id": "ref_member"},
                            "right": {"op": "constant", "value": "CUST_MEMBER_001"},
                        },
                    }
                ],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        generated_rule,
    ])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "normalized_rule": generated_rule,
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"amount": 100.23}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    events = asyncio.run(
        _collect_events(
            service.stream_proc_side(
                auth_token="token",
                payload={
                    "side": "left",
                    "target_table": "left_recon_ready",
                    "rule_text": "输出金额取含税销售金额",
                    "sources": [source],
                },
            )
        )
    )
    result = events[-1]

    assert result["event"] == "graph_completed"
    assert result["status"] == "succeeded"
    assert result["understanding"]["output_specs"][0]["source_ref_ids"] == ["ref_amount"]
    assert result["proc_rule_json"]["steps"][1]["filter"]["bindings"]["ref_member_1"]["source"]["field"] == "customer_member_code"
    completed_nodes = [
        event["node"]["code"]
        for event in events
        if event.get("event") == "node_completed" and isinstance(event.get("node"), dict)
    ]
    assert "lint_ir" in completed_nodes
    assert "repair_ir" in completed_nodes


def test_ir_dsl_consistency_does_not_use_json_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    service = RuleGenerationService()
    source = _source_payload()
    bad_rule = _simple_rule()
    bad_rule["steps"][0]["schema"]["primary_key"] = []
    bad_rule["steps"][0]["schema"]["columns"] = [
        {"name": "amount", "data_type": "decimal", "precision": 18, "scale": 2}
    ]
    bad_rule["steps"][1]["mappings"] = [
        {
            "target_field": "amount",
            "value": {"type": "source", "source": {"alias": "orders", "field": "tax_sale_amount"}},
            "field_write_mode": "overwrite",
        }
    ]
    bad_rule["steps"][1]["filter"] = {"type": "formula", "expr": "true", "bindings": {}}
    repaired_rule = _simple_rule()
    repaired_rule["steps"][0]["schema"]["primary_key"] = []
    repaired_rule["steps"][0]["schema"]["columns"] = [
        {"name": "amount", "data_type": "decimal", "precision": 18, "scale": 2}
    ]
    repaired_rule["steps"][1]["mappings"] = [
        {
            "target_field": "amount",
            "value": {"type": "source", "source": {"alias": "orders", "field": "tax_sale_amount"}},
            "field_write_mode": "overwrite",
        }
    ]
    repaired_rule["steps"][1].pop("filter", None)

    llm_responses = iter([
        {
            "understanding": {
                "rule_summary": "输出金额取含税销售金额",
                "source_references": [
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "含税销售金额",
                        "usage": "source_value",
                        "must_bind": True,
                    }
                ],
                "output_specs": [
                    {
                        "output_id": "out_amount",
                        "name": "amount",
                        "kind": "rename",
                        "source_ref_ids": ["ref_amount"],
                    }
                ],
                "business_rules": [],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        bad_rule,
        repaired_rule,
    ])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "normalized_rule": repaired_rule,
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"amount": 100.23}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    events = asyncio.run(
        _collect_events(
            service.stream_proc_side(
                auth_token="token",
                payload={
                    "side": "left",
                    "target_table": "left_recon_ready",
                    "rule_text": "输出金额取含税销售金额",
                    "sources": [source],
                },
            )
        )
    )
    result = events[-1]

    assert result["event"] == "graph_completed"
    assert "filter" not in result["proc_rule_json"]["steps"][1]
    completed_nodes = [
        event["node"]["code"]
        for event in events
        if event.get("event") == "node_completed" and isinstance(event.get("node"), dict)
    ]
    checked_nodes = [
        event["node"]["code"]
        for event in events
        if event.get("event") in {"node_completed", "node_failed"} and isinstance(event.get("node"), dict)
    ]
    assert checked_nodes.count("check_ir_dsl_consistency") >= 1
    assert "repair_proc_json_runtime" not in completed_nodes
    assert "repair_ir_dsl_consistency" not in completed_nodes
    assert "lint_proc_json" in completed_nodes


def test_unmatched_source_reference_is_marked_for_reclassification_not_user_field_pick() -> None:
    source_profiles = [_source_profile(_source_payload())]
    understanding = normalize_understanding(
        {
            "rule_summary": "坏账金额由逾期金额计算得出",
            "source_references": [
                {
                    "ref_id": "ref_bad_debt",
                    "semantic_name": "坏账金额",
                    "usage": "source_value",
                    "must_bind": True,
                }
            ],
            "output_specs": [],
            "business_rules": [],
        },
        rule_text="坏账金额由逾期金额计算得出",
        target_table="risk_asset_ready",
    )

    issues = _validate_understanding(understanding, source_profiles=source_profiles)

    assert any(issue.get("reason") == "source_reference_unmatched_needs_reclassification" for issue in issues)


def test_normalize_generated_rule_flattens_nested_formula_and_filters() -> None:
    normalized = _normalize_generated_proc_rule(
        {
            "steps": [
                {
                    "action": "write_dataset",
                    "target_table": "left_recon_ready",
                    "sources": [{"table": "public.alipay_order_detail_20260416", "alias": "alipay"}],
                    "row_write_mode": "upsert",
                    "filters": [
                        {
                            "field": "buyer_info",
                            "operator": "=",
                            "value": "buyer_20260416_1",
                        }
                    ],
                    "mappings": [
                        {
                            "target_field": "output_amount",
                            "value": {
                                "type": "formula",
                                "expr": {
                                    "expr": "{order_amount} + 10",
                                    "bindings": {
                                        "order_amount": {
                                            "type": "source",
                                            "source": {
                                                "alias": "alipay",
                                                "field": "order_amount",
                                            },
                                        }
                                    },
                                },
                            },
                        }
                    ],
                }
            ]
        }
    )

    step = normalized["steps"][0]
    mapping_value = step["mappings"][0]["value"]

    assert mapping_value["expr"] == "{order_amount} + 10"
    assert mapping_value["bindings"]["order_amount"]["source"]["field"] == "order_amount"
    assert step["filter"]["expr"] == "{filter_field_1} == {filter_value_1}"
    assert step["filter"]["bindings"]["filter_field_1"]["source"]["field"] == "buyer_info"


def test_compile_understanding_into_rule_builds_filter_and_formula_from_ir() -> None:
    normalized_rule = _normalize_generated_proc_rule(_simple_rule())
    understanding = normalize_understanding(
        {
            "rule_summary": "输出金额=含税销售金额+10，只保留指定会员编码",
            "source_references": [
                {"ref_id": "ref_key", "semantic_name": "客户订单号", "usage": "match_key"},
                {"ref_id": "ref_amount", "semantic_name": "含税销售金额", "usage": "compare_field"},
                {"ref_id": "ref_time", "semantic_name": "订单完成时间", "usage": "time_field"},
                {"ref_id": "ref_filter", "semantic_name": "客户会员编码", "usage": "filter_field"},
            ],
            "output_specs": [
                {"output_id": "out_key", "name": "biz_key", "kind": "rename", "source_ref_ids": ["ref_key"]},
                {
                    "output_id": "out_amount",
                    "name": "amount",
                    "kind": "formula",
                    "source_ref_ids": ["ref_amount"],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_amount"},
                            {"op": "constant", "value": "10"},
                        ],
                    },
                },
                {"output_id": "out_time", "name": "biz_date", "kind": "rename", "source_ref_ids": ["ref_time"]},
            ],
            "business_rules": [
                {
                    "rule_id": "rule_filter",
                    "type": "filter",
                    "description": "只保留客户会员编码等于 CUST_MEMBER_001 的数据",
                    "related_ref_ids": ["ref_filter"],
                    "predicate": {
                        "op": "eq",
                        "left": {"op": "ref", "ref_id": "ref_filter"},
                        "right": {"op": "constant", "value": "CUST_MEMBER_001"},
                    },
                }
            ],
        },
        rule_text="客户订单号，输出金额=含税销售金额+10，客户会员编码只保留CUST_MEMBER_001，订单完成时间",
        target_table="left_recon_ready",
    )
    source_references = understanding["source_references"]
    field_bindings = []
    for reference in source_references:
        field_bindings.append(
            {
                "intent_id": reference["ref_id"],
                "role": reference["usage"],
                "usage": reference["usage"],
                "mention": reference["semantic_name"],
                "must_bind": True,
                "status": "bound",
                "selected_field": {
                    "name": {
                        "ref_key": "customer_order_no",
                        "ref_amount": "tax_sale_amount",
                        "ref_time": "order_finish_time",
                        "ref_filter": "customer_member_code",
                    }[reference["ref_id"]],
                    "label": {
                        "ref_key": "客户订单号",
                        "ref_amount": "含税销售金额",
                        "ref_time": "订单完成时间",
                        "ref_filter": "客户会员编码",
                    }[reference["ref_id"]],
                    "table_name": "public.trade_orders",
                },
            }
        )

    compiled_rule = compile_understanding_into_rule(
        normalized_rule,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_source_payload()],
        target_table="left_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    amount_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "amount")
    assert amount_mapping["value"]["expr"] == "({ref_amount_2} + 10)"
    assert amount_mapping["value"]["bindings"]["ref_amount_2"]["type"] == "function"
    assert amount_mapping["value"]["bindings"]["ref_amount_2"]["function"] == "to_decimal"
    assert write_step["filter"]["expr"] == "(({ref_filter_1} == 'CUST_MEMBER_001'))"
    assert write_step["filter"]["bindings"]["ref_filter_1"]["source"]["field"] == "customer_member_code"


def test_source_passthrough_skeleton_uses_referenced_source_not_source_order() -> None:
    understanding = normalize_understanding(
        {
            "output_mode": "source_passthrough",
            "source_references": [
                {
                    "ref_id": "ref_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "match_key",
                    "table_scope": ["public.fp_orders"],
                    "candidate_fields": [
                        {
                            "raw_name": "customer_order_no",
                            "display_name": "客户订单号",
                            "source_table": "public.fp_orders",
                        }
                    ],
                },
                {
                    "ref_id": "ref_filter",
                    "semantic_name": "充值账号",
                    "usage": "filter_field",
                    "table_scope": ["public.fp_orders"],
                    "candidate_fields": [
                        {
                            "raw_name": "charge_account",
                            "display_name": "充值账号",
                            "source_table": "public.fp_orders",
                        }
                    ],
                },
            ],
            "output_specs": [],
            "business_rules": [],
        },
        rule_text="fp订单表的客户订单号作为匹配字段\n只取充值账号为charge_001的数据",
        target_table="right_recon_ready",
    )

    rule = build_proc_rule_skeleton_from_ir(
        side="right",
        target_table="right_recon_ready",
        target_tables=[],
        rule_text="fp订单表的客户订单号作为匹配字段\n只取充值账号为charge_001的数据",
        sources=[_alipay_order_source_payload(), _fp_order_source_payload()],
        understanding=understanding,
    )

    create_step = rule["steps"][0]
    write_step = rule["steps"][1]
    schema_fields = {column["name"] for column in create_step["schema"]["columns"]}
    mapping_aliases = {
        mapping["value"]["source"]["alias"]
        for mapping in write_step["mappings"]
        if mapping.get("value", {}).get("type") == "source"
    }
    assert "purchase_order_id" in schema_fields
    assert "order_amount" not in schema_fields
    assert write_step["sources"][0]["table"] == "public.fp_orders"
    assert mapping_aliases == {"source_1"}


def test_source_passthrough_skeleton_uses_bound_field_source_when_ir_scope_missing() -> None:
    understanding = normalize_understanding(
        {
            "output_mode": "source_passthrough",
            "source_references": [
                {
                    "ref_id": "ref_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "match_key",
                    "candidate_fields": [],
                },
            ],
            "output_specs": [],
            "business_rules": [],
        },
        rule_text="客户订单号作为匹配字段",
        target_table="right_recon_ready",
    )

    rule = build_proc_rule_skeleton_from_ir(
        side="right",
        target_table="right_recon_ready",
        target_tables=[],
        rule_text="客户订单号作为匹配字段",
        sources=[_alipay_order_source_payload(), _fp_order_source_payload()],
        understanding=understanding,
        field_bindings=[
            {
                "intent_id": "ref_order_no",
                "status": "bound",
                "selected_field": {
                    "raw_name": "customer_order_no",
                    "display_name": "客户订单号",
                    "source_table": "public.fp_orders",
                },
            }
        ],
    )

    create_step = rule["steps"][0]
    write_step = rule["steps"][1]
    schema_fields = {column["name"] for column in create_step["schema"]["columns"]}
    assert "customer_order_no" in schema_fields
    assert "merchant_order_no" not in schema_fields
    assert write_step["sources"][0]["table"] == "public.fp_orders"


def test_ir_dsl_consistency_rejects_llm_filter_when_ir_has_no_filter_rule() -> None:
    normalized_rule = _normalize_generated_proc_rule(_simple_rule())
    write_step = normalized_rule["steps"][1]
    write_step["filter"] = {"type": "formula", "expr": "true", "bindings": {}}
    understanding = normalize_understanding(
        {
            "rule_summary": "输出订单号和含税销售金额",
            "source_references": [
                {"ref_id": "ref_key", "semantic_name": "客户订单号", "usage": "match_key"},
                {"ref_id": "ref_amount", "semantic_name": "含税销售金额", "usage": "compare_field"},
            ],
            "output_specs": [
                {"output_id": "out_key", "name": "biz_key", "kind": "rename", "source_ref_ids": ["ref_key"]},
                {"output_id": "out_amount", "name": "amount", "kind": "rename", "source_ref_ids": ["ref_amount"]},
            ],
            "business_rules": [],
        },
        rule_text="订单号=客户订单号，金额=含税销售金额",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_key",
            "role": "match_key",
            "usage": "match_key",
            "mention": "客户订单号",
            "must_bind": True,
            "status": "bound",
            "selected_field": {
                "name": "customer_order_no",
                "label": "客户订单号",
                "table_name": "public.trade_orders",
            },
        },
        {
            "intent_id": "ref_amount",
            "role": "compare_field",
            "usage": "compare_field",
            "mention": "含税销售金额",
            "must_bind": True,
            "status": "bound",
            "selected_field": {
                "name": "tax_sale_amount",
                "label": "含税销售金额",
                "table_name": "public.trade_orders",
            },
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        normalized_rule,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_source_payload()],
        target_table="left_recon_ready",
        target_tables=[],
    )
    result = check_ir_dsl_consistency(
        compiled_rule,
        understanding=understanding,
        field_bindings=field_bindings,
        target_table="left_recon_ready",
        target_tables=[],
    )

    assert result["success"] is False
    assert any(error.get("reason") == "dsl_filter_without_ir_rule" for error in result["errors"])


def test_ir_dsl_consistency_allows_output_lineage_from_join_rule() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "step_2_write_dataset",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "mappings": [
                    {
                        "target_field": "订单号",
                        "value": {
                            "type": "source",
                            "source": {"alias": "fp", "field": "customer_order_no"},
                        },
                    },
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "formula",
                            "expr": "({amount} + 10)",
                            "bindings": {
                                "amount": {
                                    "type": "lookup",
                                    "source_alias": "alipay",
                                    "value_field": "order_amount",
                                    "keys": [
                                        {
                                            "lookup_field": "merchant_order_no",
                                            "input": {
                                                "type": "source",
                                                "source": {"alias": "fp", "field": "customer_order_no"},
                                            },
                                        }
                                    ],
                                }
                            },
                        },
                    },
                ],
            },
        ]
    }
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_fp_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_alipay_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_orders"],
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "rename",
                    "source_ref_ids": ["ref_fp_order_no"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": ["ref_amount"],
                    "rule_ids": ["rule_join_amount"],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_join_amount",
                    "type": "join",
                    "description": "fp 客户订单号关联支付宝商户订单号取订单金额",
                    "related_ref_ids": [
                        "ref_fp_order_no",
                        "ref_alipay_order_no",
                        "ref_amount",
                    ],
                    "output_ids": ["out_amount"],
                }
            ],
        },
        rule_text="金额是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的订单金额+10",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_fp_order_no",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_alipay_order_no",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_amount",
            "status": "bound",
            "selected_field": {"name": "order_amount", "table_name": "public.alipay_orders"},
        },
    ]

    result = check_ir_dsl_consistency(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        target_table="left_recon_ready",
        target_tables=[],
    )

    assert result["success"] is True


def test_ir_dsl_consistency_routes_known_unbound_source_fields_to_ir_repair() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "columns": [
                        {"name": "金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "step_2_write_dataset",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "mappings": [
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "formula",
                            "expr": "({amount} + 10)",
                            "bindings": {
                                "amount": {
                                    "type": "lookup",
                                    "source_alias": "alipay",
                                    "value_field": "order_amount",
                                    "keys": [
                                        {
                                            "lookup_field": "merchant_order_no",
                                            "input": {
                                                "type": "source",
                                                "source": {"alias": "fp", "field": "customer_order_no"},
                                            },
                                        }
                                    ],
                                }
                            },
                        },
                    },
                ],
            },
        ]
    }
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": ["ref_amount"],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                },
            ],
            "business_rules": [],
        },
        rule_text="金额是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的订单金额+10",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_amount",
            "status": "bound",
            "selected_field": {"name": "order_amount", "table_name": "public.alipay_orders"},
        },
    ]

    result = check_ir_dsl_consistency(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_fp_order_source_payload(), _alipay_order_source_payload()],
        target_table="left_recon_ready",
        target_tables=[],
    )

    assert result["success"] is False
    error = result["errors"][0]
    assert error["reason"] == "ir_lineage_missing_for_output"
    assert {"table": "public.fp_orders", "field": "customer_order_no"} in error["missing_source_references"]
    assert {"table": "public.alipay_orders", "field": "merchant_order_no"} in error["missing_source_references"]


def test_missing_join_lineage_routes_through_ir_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RuleGenerationService()
    generated_rule = {
        "role_desc": "测试规则",
        "version": "1.0",
        "metadata": {"author": "test"},
        "global_config": {},
        "file_rule_code": "test_rule",
        "dsl_constraints": {"actions": ["create_schema", "write_dataset"]},
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "primary_key": [],
                    "columns": [{"name": "金额", "data_type": "decimal"}],
                },
            },
            {
                "step_id": "step_2_write_dataset",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "mappings": [
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "formula",
                            "expr": "({amount} + 10)",
                            "bindings": {
                                "amount": {
                                    "type": "lookup",
                                    "source_alias": "alipay",
                                    "value_field": "order_amount",
                                    "keys": [
                                        {
                                            "lookup_field": "merchant_order_no",
                                            "input": {
                                                "type": "source",
                                                "source": {"alias": "fp", "field": "customer_order_no"},
                                            },
                                        }
                                    ],
                                }
                            },
                        },
                    }
                ],
            },
        ],
    }
    repaired_understanding = {
        "understanding": {
            "rule_summary": "fp 客户订单号关联支付宝商户订单号取订单金额并加 10",
            "source_references": [
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                    "must_bind": True,
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_amount",
                    ],
                    "rule_ids": ["rule_join_amount"],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_join_amount",
                    "type": "join",
                    "description": "fp 客户订单号关联支付宝商户订单号取订单金额",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_amount",
                    ],
                    "output_ids": ["out_amount"],
                }
            ],
        },
        "assumptions": [],
        "ambiguities": [],
    }
    llm_responses = iter([
        {
            "understanding": {
                "rule_summary": "取关联出的订单金额并加 10",
                "source_references": [
                    {
                        "ref_id": "ref_fp_customer_order_no",
                        "semantic_name": "客户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.fp_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_alipay_merchant_order_no",
                        "semantic_name": "商户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "订单金额",
                        "usage": "source_value",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {
                        "output_id": "out_amount",
                        "name": "金额",
                        "kind": "formula",
                        "source_ref_ids": [
                            "ref_fp_customer_order_no",
                            "ref_alipay_merchant_order_no",
                            "ref_amount",
                        ],
                        "expression": {
                            "op": "add",
                            "operands": [
                                {"op": "ref", "ref_id": "ref_amount"},
                                {"op": "constant", "value": 10},
                            ],
                        },
                    }
                ],
                "business_rules": [],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        repaired_understanding,
    ])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "normalized_rule": generated_rule,
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"金额": 98.12}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    events = asyncio.run(
        _collect_events(
            service.stream_proc_side(
                auth_token="token",
                payload={
                    "side": "left",
                    "target_table": "left_recon_ready",
                    "rule_text": (
                        "金额是fp订单表的客户订单号与支付宝订单数据的商户订单号"
                        "关联出的订单金额+10"
                    ),
                    "sources": [_fp_order_source_payload(), _alipay_order_source_payload()],
                },
            )
        )
    )
    result = events[-1]

    assert result["event"] == "graph_completed"
    write_step = result["proc_rule_json"]["steps"][1]
    amount_mapping = write_step["mappings"][0]
    assert _contains_value_type(amount_mapping["value"], "lookup") or bool(
        (write_step.get("match") or {}).get("sources")
    )
    semantic_names = {item["semantic_name"] for item in result["understanding"]["source_references"]}
    assert {"客户订单号", "商户订单号", "订单金额"} <= semantic_names
    checked_nodes = [
        event["node"]["code"]
        for event in events
        if event.get("event") in {"node_completed", "node_failed"} and isinstance(event.get("node"), dict)
    ]
    assert checked_nodes.count("check_ir_dsl_consistency") == 1
    assert "repair_ir" in checked_nodes
    assert "generate_proc_json" in checked_nodes[checked_nodes.index("repair_ir") + 1:]


def test_ir_repair_prompt_includes_stage_failures_and_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RuleGenerationService()
    wrong_understanding = {
        "understanding": {
            "rule_summary": "取关联出的订单金额并加 10",
            "source_references": [
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                    "must_bind": True,
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_amount",
                    ],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                }
            ],
            "business_rules": [],
        },
        "assumptions": [],
        "ambiguities": [],
    }
    repaired_understanding = {
        "understanding": {
            **wrong_understanding["understanding"],
            "business_rules": [
                {
                    "rule_id": "rule_join_amount",
                    "type": "join",
                    "description": "fp 客户订单号关联支付宝商户订单号取订单金额",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_amount",
                    ],
                    "output_ids": ["out_amount"],
                }
            ],
        },
        "assumptions": [],
        "ambiguities": [],
    }
    llm_responses = [wrong_understanding, wrong_understanding, repaired_understanding]
    prompts: list[str] = []

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        prompts.append(prompt)
        return llm_responses.pop(0)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"金额": 98.12}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    events = asyncio.run(
        _collect_events(
            service.stream_proc_side(
                auth_token="token",
                payload={
                    "side": "left",
                    "target_table": "left_recon_ready",
                    "rule_text": (
                        "订单号为fp订单表的客户订单号\n"
                        "金额是fp订单表的客户订单号与支付宝订单数据的商户订单号"
                        "关联出的订单金额+10"
                    ),
                    "sources": [_fp_order_source_payload(), _alipay_order_source_payload()],
                },
            )
        )
    )

    assert events[-1]["event"] == "graph_completed"
    repair_prompts = prompts[1:]
    assert len(repair_prompts) == 2
    assert '"repair_stage": "lint_ir"' in repair_prompts[0]
    assert '"repair_failures"' in repair_prompts[0]
    assert "cross_table_outputs_missing_relation_rule" in repair_prompts[0]
    assert '"changed_understanding": false' in repair_prompts[1]
    assert "previous_repair_no_change" in repair_prompts[1]


def test_ir_repair_prompt_requires_missing_source_field_repairs() -> None:
    prompt = build_ir_repair_prompt(
        {
            "rule_text": (
                "销售商户编码作为匹配字段\n"
                "fp订单表的相同销售商户编码按销售总金额累加合并得到金额\n"
                "fp订单表客户的订单创建时间作为时间字段"
            ),
            "understanding": {
                "rule_summary": "按销售商户编码聚合金额",
                "source_references": [
                    {"ref_id": "ref_merchant", "semantic_name": "销售商户编码", "usage": "group_field"},
                    {"ref_id": "ref_amount", "semantic_name": "销售总金额", "usage": "source_value"},
                ],
                "output_specs": [
                    {"output_id": "out_key", "name": "销售商户编码", "kind": "rename", "source_ref_ids": ["ref_merchant"]},
                    {"output_id": "out_amount", "name": "金额", "kind": "aggregate", "source_ref_ids": ["ref_amount"]},
                ],
                "business_rules": [],
            },
            "sources": [_fp_order_source_payload()],
            "current_repair_stage": "lint_ir",
        },
        failures=[
            {
                "stage": "lint_ir",
                "reason": "rule_text_field_mentions_missing_ir_refs",
                "message": "规则描述中提到的数据集字段没有进入 IR。",
                "missing_source_fields": [
                    {
                        "table_name": "public.fp_orders",
                        "name": "order_create_time",
                        "label": "订单创建时间",
                    }
                ],
            }
        ],
    )

    assert '"required_repairs"' in prompt
    assert '"type": "add_missing_source_field_to_ir"' in prompt
    assert '"raw_name": "order_create_time"' in prompt
    assert "禁止原样返回 current_understanding" in prompt


def test_lint_rule_generation_ir_requires_business_rule_output_lineage() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {"ref_id": "ref_left_key", "semantic_name": "左表字段", "usage": "lookup_key"},
                {"ref_id": "ref_right_key", "semantic_name": "右表字段", "usage": "lookup_key"},
                {"ref_id": "ref_value", "semantic_name": "取数字段", "usage": "source_value"},
            ],
            "output_specs": [
                {
                    "output_id": "out_unrelated",
                    "name": "输出字段",
                    "kind": "rename",
                    "source_ref_ids": ["ref_value"],
                }
            ],
            "business_rules": [
                {
                    "rule_id": "join_unbound",
                    "type": "join",
                    "description": "一个未绑定到输出字段的关联规则",
                    "related_ref_ids": ["ref_left_key", "ref_right_key"],
                }
            ],
        },
        rule_text="一个未绑定到输出字段的关联规则",
        target_table="left_recon_ready",
    )

    result = lint_rule_generation_ir(understanding, field_bindings=[])

    assert result["success"] is False
    assert any(
        error.get("reason") == "business_rule_missing_output_lineage"
        for error in result["errors"]
    )


def test_lint_rule_generation_ir_allows_join_derived_lineage_from_business_rule() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_orders"],
                },
                {
                    "ref_id": "ref_alipay_create_time",
                    "semantic_name": "创建时间",
                    "usage": "time_field",
                    "table_scope": ["public.alipay_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "join_derived",
                    "source_ref_ids": ["ref_alipay_create_time"],
                    "rule_ids": ["rule_join_time"],
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_join_time",
                    "type": "join",
                    "description": "fp 客户订单号匹配支付宝商户订单号取创建时间",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_alipay_create_time",
                    ],
                    "output_ids": ["out_time"],
                }
            ],
        },
        rule_text="时间为用fp订单表客户订单号和支付宝订单数据商户订单号做匹配取出支付宝订单数据的创建时间",
        target_table="left_recon_ready",
    )

    result = lint_rule_generation_ir(understanding, field_bindings=[])

    assert result["success"] is True


def test_lint_rule_generation_ir_rejects_lookup_without_value_ref_before_compile() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {"ref_id": "ref_fp_customer_order_no", "semantic_name": "客户订单号", "usage": "lookup_key"},
                {"ref_id": "ref_alipay_merchant_order_no", "semantic_name": "商户订单号", "usage": "lookup_key"},
            ],
            "output_specs": [
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "lookup",
                    "source_ref_ids": ["ref_fp_customer_order_no", "ref_alipay_merchant_order_no"],
                    "rule_ids": ["rule_join_time"],
                }
            ],
            "business_rules": [
                {
                    "rule_id": "rule_join_time",
                    "type": "join",
                    "description": "fp 客户订单号匹配支付宝商户订单号取创建时间",
                    "related_ref_ids": ["ref_fp_customer_order_no", "ref_alipay_merchant_order_no"],
                    "output_ids": ["out_time"],
                }
            ],
        },
        rule_text="时间为fp订单表客户订单号和支付宝订单数据商户订单号做匹配取出支付宝订单数据的创建时间",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_fp_customer_order_no",
            "usage": "lookup_key",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_alipay_merchant_order_no",
            "usage": "lookup_key",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
    ]

    result = lint_rule_generation_ir(understanding, field_bindings=field_bindings)

    assert result["success"] is False
    assert any(
        error.get("reason") == "output_spec_missing_lookup_value_ref"
        for error in result["errors"]
    )


def test_lint_rule_generation_ir_rejects_lookup_key_not_available_after_aggregate() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {"ref_id": "ref_merchant_code", "semantic_name": "销售商户编码", "usage": "group_field"},
                {"ref_id": "ref_total_sale_amount", "semantic_name": "销售总金额", "usage": "source_value"},
                {"ref_id": "ref_fp_customer_order_no", "semantic_name": "客户订单号", "usage": "lookup_key"},
                {"ref_id": "ref_alipay_merchant_order_no", "semantic_name": "商户订单号", "usage": "lookup_key"},
                {"ref_id": "ref_created_time", "semantic_name": "创建时间", "usage": "source_value"},
            ],
            "output_specs": [
                {
                    "output_id": "out_merchant_code",
                    "name": "销售商户编码",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_merchant_code"],
                    "rule_ids": ["rule_agg"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "aggregate",
                    "source_ref_ids": ["ref_total_sale_amount"],
                    "rule_ids": ["rule_agg"],
                },
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "lookup",
                    "source_ref_ids": ["ref_created_time"],
                    "rule_ids": ["rule_join_time"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_agg",
                    "type": "aggregate",
                    "related_ref_ids": ["ref_merchant_code", "ref_total_sale_amount"],
                    "output_ids": ["out_merchant_code", "out_amount"],
                    "params": {
                        "operator": "sum",
                        "value_ref_id": "ref_total_sale_amount",
                        "group_ref_ids": ["ref_merchant_code"],
                    },
                },
                {
                    "rule_id": "rule_join_time",
                    "type": "join",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_created_time",
                    ],
                    "output_ids": ["out_time"],
                },
            ],
        },
        rule_text=(
            "销售商户编码作为匹配字段\n"
            "fp订单表的相同销售商户编码按销售总金额累加合并得到金额\n"
            "时间为fp订单表客户订单号和支付宝订单数据商户订单号做匹配取出支付宝订单数据的创建时间"
        ),
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_merchant_code",
            "usage": "group_field",
            "status": "bound",
            "selected_field": {"name": "merchant_code", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_total_sale_amount",
            "usage": "source_value",
            "status": "bound",
            "selected_field": {"name": "total_sale_amount", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_fp_customer_order_no",
            "usage": "lookup_key",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_alipay_merchant_order_no",
            "usage": "lookup_key",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_created_time",
            "usage": "source_value",
            "status": "bound",
            "selected_field": {"name": "created_time", "table_name": "public.alipay_orders"},
        },
    ]

    result = lint_rule_generation_ir(understanding, field_bindings=field_bindings)

    assert result["success"] is False
    assert any(
        error.get("reason") == "lookup_key_not_in_aggregate_grain"
        for error in result["errors"]
    )


def test_lint_rule_generation_ir_rejects_cross_table_outputs_without_relation_rule() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "rename",
                    "source_ref_ids": ["ref_fp_customer_order_no"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_amount",
                    ],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                },
            ],
            "business_rules": [],
        },
        rule_text="订单号为fp订单表的客户订单号，金额是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的订单金额+10",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_fp_customer_order_no",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_alipay_merchant_order_no",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_amount",
            "status": "bound",
            "selected_field": {"name": "order_amount", "table_name": "public.alipay_orders"},
        },
    ]

    result = lint_rule_generation_ir(understanding, field_bindings=field_bindings)
    reasons = {item.get("reason") for item in result["errors"]}

    assert result["success"] is False
    assert "cross_table_outputs_missing_relation_rule" in reasons
    assert "output_spec_cross_table_lineage_missing_rule" in reasons


def test_lint_proc_rule_rejects_runtime_incompatible_formula_and_filter() -> None:
    result = lint_proc_rule(
        {
            "steps": [
                {
                    "step_id": "create_left_recon_ready",
                    "action": "create_schema",
                    "target_table": "left_recon_ready",
                    "schema": {
                        "primary_key": ["biz_key"],
                        "columns": [
                            {"name": "biz_key", "data_type": "string"},
                            {"name": "amount", "data_type": "decimal"},
                        ],
                    },
                },
                {
                    "step_id": "write_left_recon_ready",
                    "action": "write_dataset",
                    "target_table": "left_recon_ready",
                    "sources": [{"table": "public.trade_orders", "alias": "orders"}],
                    "row_write_mode": "upsert",
                    "filter": {
                        "type": "formula",
                        "expr": "{member_code} = 'CUST_MEMBER_001'",
                        "bindings": {
                            "member_code": {
                                "type": "source",
                                "source": {"alias": "orders", "field": "customer_member_code"},
                            }
                        },
                    },
                    "mappings": [
                        {
                            "target_field": "amount",
                            "value": {
                                "type": "formula",
                                "expr": "to_decimal({order_amount}) + 10",
                                "bindings": {
                                    "order_amount": {
                                        "type": "source",
                                        "source": {"alias": "orders", "field": "tax_sale_amount"},
                                    }
                                },
                            },
                        }
                    ],
                },
            ]
        },
        side="left",
        target_table="left_recon_ready",
        target_tables=[],
        sources=[_source_payload()],
    )

    assert result["success"] is False
    messages = [item["message"] for item in result["errors"]]
    assert any("step.filter 公式语法错误" in message for message in messages)
    assert any("mapping.value 公式包含不支持的函数: to_decimal" in message for message in messages)


def test_sample_diagnostics_evaluates_function_wrapped_filter() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_right_recon_ready",
                "action": "create_schema",
                "target_table": "right_recon_ready",
                "schema": {"columns": [{"name": "标识", "data_type": "string"}]},
            },
            {
                "step_id": "write_right_recon_ready",
                "action": "write_dataset",
                "target_table": "right_recon_ready",
                "sources": [{"table": "public.fp_orders", "alias": "source_1"}],
                "filter": {
                    "type": "formula",
                    "expr": "{id_filter_1} == 880000000091",
                    "bindings": {
                        "id_filter_1": {
                            "type": "function",
                            "function": "to_decimal",
                            "args": {
                                "value": {
                                    "type": "source",
                                    "source": {"alias": "source_1", "field": "id"},
                                }
                            },
                        }
                    },
                },
                "mappings": [
                    {
                        "target_field": "标识",
                        "value": {"type": "source", "source": {"alias": "source_1", "field": "id"}},
                    }
                ],
            },
        ]
    }

    result = diagnose_proc_sample(
        rule_json=rule_json,
        sample_result={
            "success": True,
            "ready_for_confirm": False,
            "output_samples": [{"target_table": "right_recon_ready", "row_count": 0, "rows": []}],
        },
        sample_inputs=[
            {
                "table_name": "public.fp_orders",
                "sample_rows": [{"id": "880000000091"}],
            }
        ],
        expected_target="right_recon_ready",
        rule_text="只取fp订单表的标识为880000000091的数据",
    )

    reasons = {item.get("reason") for item in result["diagnostics"]}
    assert "filter_not_diagnosable" not in reasons
    assert "target_empty_after_filter_matched_rows" in reasons


def test_sample_diagnostics_tolerates_single_source_alias_mismatch() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "write_right_recon_ready",
                "action": "write_dataset",
                "target_table": "right_recon_ready",
                "sources": [{"table": "public.fp_orders", "alias": "source_1"}],
                "filter": {
                    "type": "formula",
                    "expr": "{id_filter_1} == '880000000091'",
                    "bindings": {
                        "id_filter_1": {
                            "type": "source",
                            "source": {"alias": "fp", "field": "id"},
                        }
                    },
                },
            },
        ]
    }

    result = diagnose_proc_sample(
        rule_json=rule_json,
        sample_result={
            "success": True,
            "ready_for_confirm": False,
            "output_samples": [{"target_table": "right_recon_ready", "row_count": 0, "rows": []}],
        },
        sample_inputs=[
            {
                "table_name": "public.fp_orders",
                "sample_rows": [{"id": "880000000091"}],
            }
        ],
        expected_target="right_recon_ready",
        rule_text="只取fp订单表的标识为880000000091的数据",
    )

    reasons = {item.get("reason") for item in result["diagnostics"]}
    assert "filter_not_diagnosable" not in reasons
    assert "target_empty_after_filter_matched_rows" in reasons


def test_understanding_prompt_includes_twenty_sample_rows() -> None:
    source = _source_payload()
    source["sample_rows"] = [
        {
            "customer_order_no": f"ORD-{index:03}",
            "tax_sale_amount": index,
        }
        for index in range(25)
    ]

    prompt = build_understanding_prompt({
        "side": "left",
        "target_table": "left_recon_ready",
        "rule_text": "保留样例数据",
        "sources": [source],
    })
    payload_json = prompt.split("输入上下文：\n", 1)[1]
    payload = json.loads(payload_json)
    sample_rows = payload["source_profiles"][0]["sample_rows"]

    assert len(sample_rows) == 20
    assert sample_rows[-1]["customer_order_no"] == "ORD-019"


def test_compile_understanding_into_rule_builds_step_aggregate_from_ir() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "primary_key": ["订单号"],
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "step_2_write_dataset",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [{"table": "public.fp_orders", "alias": "fp"}],
                "row_write_mode": "upsert",
                "mappings": [],
            },
        ]
    }
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "group_field",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_total_sale_amount",
                    "semantic_name": "销售总金额",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "rename",
                    "source_ref_ids": ["ref_customer_order_no"],
                    "rule_ids": ["rule_sum_amount"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "aggregate",
                    "source_ref_ids": ["ref_total_sale_amount"],
                    "rule_ids": ["rule_sum_amount"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_sum_amount",
                    "type": "aggregate",
                    "description": "按客户订单号累加销售总金额",
                    "related_ref_ids": ["ref_customer_order_no", "ref_total_sale_amount"],
                    "output_ids": ["out_order_no", "out_amount"],
                    "params": {
                        "operator": "sum",
                        "value_ref_id": "ref_total_sale_amount",
                        "group_ref_ids": ["ref_customer_order_no"],
                    },
                }
            ],
        },
        rule_text="订单号和金额为fp订单表的相同客户订单号按销售总金额累加合并得到订单号和金额",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_customer_order_no",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_total_sale_amount",
            "status": "bound",
            "selected_field": {"name": "total_sale_amount", "table_name": "public.fp_orders"},
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_fp_sales_source_payload()],
        target_table="left_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    assert write_step["aggregate"] == [
        {
            "source_alias": "fp",
            "output_alias": "agg_rule_sum_amount",
            "group_fields": ["customer_order_no"],
            "aggregations": [
                {"field": "total_sale_amount", "operator": "sum", "alias": "agg_金额"},
            ],
        }
    ]
    assert write_step["match"]["sources"][0]["keys"] == [
        {"field": "customer_order_no", "target_field": "订单号"},
    ]
    amount_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "金额")
    assert amount_mapping["value"]["source"] == {"alias": "agg_rule_sum_amount", "field": "agg_金额"}
    lint_result = lint_proc_rule(
        compiled_rule,
        side="left",
        target_table="left_recon_ready",
        target_tables=[],
        sources=[_fp_sales_source_payload()],
    )
    assert lint_result["success"] is True
    consistency_result = check_ir_dsl_consistency(
        compiled_rule,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_fp_sales_source_payload()],
        target_table="left_recon_ready",
        target_tables=[],
    )
    assert consistency_result["success"] is True


def test_validate_understanding_reports_invalid_table_scope_before_field_missing() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_merchant_code",
                    "semantic_name": "销售商户编码",
                    "usage": "group_field",
                    "table_scope": ["fp订单表的相同销售商户编码按销售总金额累加合并得到金额"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "aggregate",
                    "source_ref_ids": ["ref_merchant_code"],
                },
            ],
        },
        rule_text="fp订单表的相同销售商户编码按销售总金额累加合并得到金额",
        target_table="left_recon_ready",
    )

    issues = _validate_understanding(
        understanding,
        source_profiles=[_source_profile(_fp_sales_source_payload())],
        rule_text="fp订单表的相同销售商户编码按销售总金额累加合并得到金额",
    )

    assert issues[0]["reason"] == "invalid_table_scope"
    assert not any(
        issue.get("reason") == "source_reference_unmatched_needs_reclassification"
        for issue in issues
    )


def test_compile_understanding_into_rule_builds_global_aggregate_from_ir() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "primary_key": [],
                    "columns": [{"name": "金额", "data_type": "decimal"}],
                },
            },
            {
                "step_id": "step_2_write_dataset",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [{"table": "public.fp_orders", "alias": "fp"}],
                "row_write_mode": "upsert",
                "mappings": [],
            },
        ]
    }
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_total_sale_amount",
                    "semantic_name": "销售总金额",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "aggregate",
                    "source_ref_ids": ["ref_total_sale_amount"],
                    "rule_ids": ["rule_sum_amount"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_sum_amount",
                    "type": "aggregate",
                    "description": "销售总金额整体累加",
                    "related_ref_ids": ["ref_total_sale_amount"],
                    "output_ids": ["out_amount"],
                    "params": {
                        "operator": "sum",
                        "value_ref_id": "ref_total_sale_amount",
                    },
                }
            ],
        },
        rule_text="按销售总金额累加得到金额",
        target_table="left_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_total_sale_amount",
            "status": "bound",
            "selected_field": {"name": "total_sale_amount", "table_name": "public.fp_orders"},
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_fp_sales_source_payload()],
        target_table="left_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    assert write_step["aggregate"][0]["group_fields"] == []
    assert "match" not in write_step
    lint_result = lint_proc_rule(
        compiled_rule,
        side="left",
        target_table="left_recon_ready",
        target_tables=[],
        sources=[_fp_sales_source_payload()],
    )
    assert lint_result["success"] is True

    from proc.mcp_server.steps_runtime import StepsProcRuntime

    fp_rows = [
        {"total_sale_amount": "100.50"},
        {"total_sale_amount": "25.25"},
    ]
    with tempfile.TemporaryDirectory() as output_dir:
        runtime = StepsProcRuntime(
            "test_global_aggregate",
            compiled_rule,
            [],
            output_dir,
            preloaded_frames={"public.fp_orders": pd.DataFrame(fp_rows)},
        )
        runtime.execute()

    rows = runtime.tables["left_recon_ready"].to_dict("records")
    assert rows == [{"金额": 125.75}]


def test_compile_understanding_prunes_stale_aggregate_match_and_runs_join_lookup() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "step_1_create_schema",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                        {"name": "时间", "data_type": "string"},
                    ],
                },
            },
            {
                "step_id": "step_2_write_dataset",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "aggregate": [
                    {
                        "source_alias": "fp",
                        "output_alias": "agg_fp",
                        "group_fields": ["customer_order_no"],
                        "aggregations": [
                            {"field": "total_sale_amount", "operator": "sum", "alias": "agg_total"},
                        ],
                    }
                ],
                "match": {
                    "sources": [
                        {
                            "alias": "agg_fp",
                            "keys": [{"field": "customer_order_no", "target_field": "customer_order_no"}],
                        }
                    ]
                },
                "mappings": [
                    {
                        "target_field": "时间",
                        "value": {
                            "type": "lookup",
                            "source_alias": "alipay",
                            "value_field": "created_time",
                            "keys": [
                                {
                                    "lookup_field": "merchant_order_no",
                                    "input": {
                                        "type": "source",
                                        "source": {"alias": "agg_fp", "field": "customer_order_no"},
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        ]
    }
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_group_order",
                    "semantic_name": "客户订单号",
                    "usage": "group_field",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "销售总金额",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_join_order",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_merchant_order",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_created_time",
                    "semantic_name": "创建时间",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                    "must_bind": True,
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_group_order"],
                    "rule_ids": ["rule_agg"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "aggregate",
                    "source_ref_ids": ["ref_amount"],
                    "rule_ids": ["rule_agg"],
                },
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "lookup",
                    "source_ref_ids": ["ref_created_time"],
                    "rule_ids": ["rule_join"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_agg",
                    "type": "aggregate",
                    "related_ref_ids": ["ref_group_order", "ref_amount"],
                    "output_ids": ["out_order_no", "out_amount"],
                    "params": {
                        "operator": "sum",
                        "value_ref_id": "ref_amount",
                        "group_ref_ids": ["ref_group_order"],
                    },
                },
                {
                    "rule_id": "rule_join",
                    "type": "join",
                    "related_ref_ids": ["ref_join_order", "ref_merchant_order"],
                    "output_ids": ["out_time"],
                    "params": {
                        "left_ref_id": "ref_join_order",
                        "right_ref_id": "ref_merchant_order",
                    },
                },
            ],
        },
        rule_text="按客户订单号聚合销售总金额，再关联支付宝商户订单号取创建时间",
        target_table="left_recon_ready",
    )
    fp_source = _fp_sales_source_payload()
    alipay_source = _alipay_order_source_payload()
    alipay_source["field_label_map"] = {
        **alipay_source["field_label_map"],
        "created_time": "创建时间",
    }
    alipay_source["fields"] = [
        *alipay_source["fields"],
        {"name": "created_time", "label": "创建时间", "data_type": "date"},
    ]
    field_bindings = [
        {
            "intent_id": "ref_group_order",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_amount",
            "status": "bound",
            "selected_field": {"name": "total_sale_amount", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_join_order",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_merchant_order",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_created_time",
            "status": "bound",
            "selected_field": {"name": "created_time", "table_name": "public.alipay_orders"},
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[fp_source, alipay_source],
        target_table="left_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    assert [item["output_alias"] for item in write_step["aggregate"]] == ["agg_rule_agg"]
    assert write_step["match"]["sources"] == [
        {
            "alias": "agg_rule_agg",
            "keys": [{"field": "customer_order_no", "target_field": "订单号"}],
        }
    ]
    time_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "时间")
    assert time_mapping["value"]["keys"][0]["input"]["source"]["alias"] == "agg_rule_agg"

    from proc.mcp_server.steps_runtime import StepsProcRuntime

    fp_rows = [
        {"customer_order_no": "M-001", "total_sale_amount": "100"},
        {"customer_order_no": "M-001", "total_sale_amount": "25"},
        {"customer_order_no": "M-002", "total_sale_amount": "80"},
    ]
    alipay_rows = [
        {"merchant_order_no": "M-001", "created_time": "2026-04-16 10:11:21"},
        {"merchant_order_no": "M-002", "created_time": "2026-04-16 11:12:22"},
    ]
    with tempfile.TemporaryDirectory() as output_dir:
        runtime = StepsProcRuntime(
            "test_aggregate_join",
            compiled_rule,
            [],
            output_dir,
            preloaded_frames={
                "public.fp_orders": pd.DataFrame(fp_rows),
                "public.alipay_orders": pd.DataFrame(alipay_rows),
            },
        )
        runtime.execute()

    rows = runtime.tables["left_recon_ready"].to_dict("records")
    assert rows == [
        {"订单号": "M-001", "金额": 125, "时间": "2026-04-16 10:11:21"},
        {"订单号": "M-002", "金额": 80, "时间": "2026-04-16 11:12:22"},
    ]


def test_lint_proc_rule_rejects_multi_source_write_without_match_before_sample() -> None:
    result = lint_proc_rule(
        {
            "steps": [
                {
                    "step_id": "create_left_recon_ready",
                    "action": "create_schema",
                    "target_table": "left_recon_ready",
                    "schema": {
                        "primary_key": [],
                        "columns": [
                            {"name": "订单号", "data_type": "string"},
                            {"name": "金额", "data_type": "decimal"},
                        ],
                    },
                },
                {
                    "step_id": "write_left_recon_ready",
                    "action": "write_dataset",
                    "target_table": "left_recon_ready",
                    "sources": [
                        {"table": "public.fp_orders", "alias": "fp"},
                        {"table": "public.alipay_orders", "alias": "alipay"},
                    ],
                    "row_write_mode": "upsert",
                    "mappings": [
                        {
                            "target_field": "订单号",
                            "value": {
                                "type": "source",
                                "source": {"alias": "fp", "field": "purchase_order_id"},
                            },
                        },
                        {
                            "target_field": "金额",
                            "value": {
                                "type": "formula",
                                "expr": "({amount} + 10)",
                                "bindings": {
                                    "amount": {
                                        "type": "source",
                                        "source": {"alias": "alipay", "field": "order_amount"},
                                    }
                                },
                            },
                        },
                    ],
                },
            ]
        },
        side="left",
        target_table="left_recon_ready",
        target_tables=[],
        sources=[_fp_order_source_payload(), _alipay_order_source_payload()],
    )

    assert result["success"] is False
    assert any(
        error.get("reason") == "write_dataset_without_match_requires_single_base_alias"
        for error in result["errors"]
    )


def test_lint_proc_rule_allows_single_base_alias_with_lookup_source() -> None:
    result = lint_proc_rule(
        {
            "steps": [
                {
                    "step_id": "create_left_recon_ready",
                    "action": "create_schema",
                    "target_table": "left_recon_ready",
                    "schema": {
                        "primary_key": [],
                        "columns": [
                            {"name": "订单号", "data_type": "string"},
                            {"name": "金额", "data_type": "decimal"},
                        ],
                    },
                },
                {
                    "step_id": "write_left_recon_ready",
                    "action": "write_dataset",
                    "target_table": "left_recon_ready",
                    "sources": [
                        {"table": "public.fp_orders", "alias": "fp"},
                        {"table": "public.alipay_orders", "alias": "alipay"},
                    ],
                    "row_write_mode": "upsert",
                    "mappings": [
                        {
                            "target_field": "订单号",
                            "value": {
                                "type": "source",
                                "source": {"alias": "fp", "field": "purchase_order_id"},
                            },
                        },
                        {
                            "target_field": "金额",
                            "value": {
                                "type": "formula",
                                "expr": "({amount} + 10)",
                                "bindings": {
                                    "amount": {
                                        "type": "lookup",
                                        "source_alias": "alipay",
                                        "value_field": "order_amount",
                                        "keys": [
                                            {
                                                "lookup_field": "merchant_order_no",
                                                "input": {
                                                    "type": "source",
                                                    "source": {"alias": "fp", "field": "customer_order_no"},
                                                },
                                            }
                                        ],
                                    }
                                },
                            },
                        },
                    ],
                },
            ]
        },
        side="left",
        target_table="left_recon_ready",
        target_tables=[],
        sources=[_fp_order_source_payload(), _alipay_order_source_payload()],
    )

    assert result["success"] is True


def test_compile_formula_and_time_outputs_linked_by_lookup_rule() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_right_recon_ready",
                "action": "create_schema",
                "target_table": "right_recon_ready",
                "schema": {
                    "primary_key": [],
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                        {"name": "时间", "data_type": "date"},
                    ],
                },
            },
            {
                "step_id": "write_right_recon_ready",
                "action": "write_dataset",
                "target_table": "right_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "mappings": [],
            },
        ]
    }
    alipay_source = _alipay_order_source_payload()
    alipay_source["field_label_map"] = {
        **alipay_source["field_label_map"],
        "paid_time": "支付时间",
    }
    alipay_source["fields"] = [
        *alipay_source["fields"],
        {"name": "paid_time", "label": "支付时间", "data_type": "date"},
    ]
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_orders"],
                },
                {
                    "ref_id": "ref_order_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                },
                {
                    "ref_id": "ref_paid_time",
                    "semantic_name": "支付时间",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "rename",
                    "source_ref_ids": ["ref_order_no"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_order_amount",
                    ],
                    "rule_ids": ["rule_lookup_alipay"],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_order_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                },
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "lookup",
                    "source_ref_ids": ["ref_paid_time"],
                    "rule_ids": ["rule_lookup_alipay"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_lookup_alipay",
                    "type": "lookup",
                    "description": "fp 客户订单号关联支付宝商户订单号取订单金额和支付时间",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                        "ref_order_amount",
                        "ref_paid_time",
                    ],
                    "output_ids": ["out_amount", "out_time"],
                }
            ],
        },
        rule_text=(
            "订单号为fp订单表的客户订单号\n"
            "金额是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的订单金额+10\n"
            "时间是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的支付时间"
        ),
        target_table="right_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_order_no",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_fp_customer_order_no",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_alipay_merchant_order_no",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_order_amount",
            "status": "bound",
            "selected_field": {"name": "order_amount", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_paid_time",
            "status": "bound",
            "selected_field": {"name": "paid_time", "table_name": "public.alipay_orders"},
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_fp_order_source_payload(), alipay_source],
        target_table="right_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    amount_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "金额")
    time_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "时间")
    assert _contains_value_type(amount_mapping["value"], "lookup")
    assert _contains_value_type(time_mapping["value"], "lookup")
    lint_result = lint_proc_rule(
        compiled_rule,
        side="right",
        target_table="right_recon_ready",
        target_tables=[],
        sources=[_fp_order_source_payload(), alipay_source],
    )
    assert lint_result["success"] is True


def test_compile_inferred_lookup_with_real_table_order_alipay_first() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_right_recon_ready",
                "action": "create_schema",
                "target_table": "right_recon_ready",
                "schema": {
                    "primary_key": [],
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                        {"name": "时间", "data_type": "date"},
                    ],
                },
            },
            {
                "step_id": "write_right_recon_ready",
                "action": "write_dataset",
                "target_table": "right_recon_ready",
                "sources": [
                    {"table": "public.alipay_order_detail_20260416", "alias": "source_1"},
                    {"table": "public.ods_yxst_fp_orders_di_o", "alias": "source_2"},
                ],
                "row_write_mode": "upsert",
                "mappings": [],
            },
        ]
    }
    alipay_source = {
        "id": "alipay_order_detail",
        "table_name": "public.alipay_order_detail_20260416",
        "business_name": "支付宝订单数据",
        "field_label_map": {
            "merchant_order_no": "商户订单号",
            "order_amount": "订单金额",
            "paid_time": "支付时间",
        },
        "fields": [
            {"name": "merchant_order_no", "label": "商户订单号", "data_type": "string"},
            {"name": "order_amount", "label": "订单金额", "data_type": "decimal"},
            {"name": "paid_time", "label": "支付时间", "data_type": "date"},
        ],
    }
    fp_source = {
        "id": "fp_orders",
        "table_name": "public.ods_yxst_fp_orders_di_o",
        "business_name": "fp订单表",
        "field_label_map": {
            "customer_order_no": "客户订单号",
        },
        "fields": [
            {"name": "customer_order_no", "label": "客户订单号", "data_type": "string"},
        ],
    }
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "source_value",
                    "table_scope": ["public.ods_yxst_fp_orders_di_o"],
                },
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.ods_yxst_fp_orders_di_o"],
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "lookup_key",
                    "table_scope": ["public.alipay_order_detail_20260416"],
                },
                {
                    "ref_id": "ref_order_amount",
                    "semantic_name": "订单金额",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_order_detail_20260416"],
                },
                {
                    "ref_id": "ref_paid_time",
                    "semantic_name": "支付时间",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_order_detail_20260416"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "rename",
                    "source_ref_ids": ["ref_order_no"],
                },
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": ["ref_order_amount"],
                    "expression": {
                        "op": "add",
                        "operands": [
                            {"op": "ref", "ref_id": "ref_order_amount"},
                            {"op": "constant", "value": 10},
                        ],
                    },
                },
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "lookup",
                    "source_ref_ids": ["ref_paid_time"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_lookup_alipay",
                    "type": "lookup",
                    "description": "fp 客户订单号关联支付宝商户订单号取订单金额和支付时间",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                    ],
                }
            ],
        },
        rule_text=(
            "订单号为fp订单表的客户订单号\n"
            "金额是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的订单金额+10\n"
            "时间是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的支付时间"
        ),
        target_table="right_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_order_no",
            "status": "bound",
            "selected_field": {
                "name": "customer_order_no",
                "table_name": "public.ods_yxst_fp_orders_di_o",
            },
        },
        {
            "intent_id": "ref_fp_customer_order_no",
            "status": "bound",
            "selected_field": {
                "name": "customer_order_no",
                "table_name": "public.ods_yxst_fp_orders_di_o",
            },
        },
        {
            "intent_id": "ref_alipay_merchant_order_no",
            "status": "bound",
            "selected_field": {
                "name": "merchant_order_no",
                "table_name": "public.alipay_order_detail_20260416",
            },
        },
        {
            "intent_id": "ref_order_amount",
            "status": "bound",
            "selected_field": {
                "name": "order_amount",
                "table_name": "public.alipay_order_detail_20260416",
            },
        },
        {
            "intent_id": "ref_paid_time",
            "status": "bound",
            "selected_field": {
                "name": "paid_time",
                "table_name": "public.alipay_order_detail_20260416",
            },
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[alipay_source, fp_source],
        target_table="right_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    order_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "订单号")
    amount_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "金额")
    time_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "时间")
    assert order_mapping["value"] == {
        "type": "source",
        "source": {"alias": "source_2", "field": "customer_order_no"},
    }
    assert _contains_value_type(amount_mapping["value"], "lookup")
    assert _contains_value_type(time_mapping["value"], "lookup")
    lint_result = lint_proc_rule(
        compiled_rule,
        side="right",
        target_table="right_recon_ready",
        target_tables=[],
        sources=[alipay_source, fp_source],
    )
    assert lint_result["success"] is True


def test_compile_passthrough_output_linked_by_join_rule_as_lookup() -> None:
    rule_json = {
        "steps": [
            {
                "step_id": "create_right_recon_ready",
                "action": "create_schema",
                "target_table": "right_recon_ready",
                "schema": {
                    "primary_key": [],
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "时间", "data_type": "date"},
                    ],
                },
            },
            {
                "step_id": "write_right_recon_ready",
                "action": "write_dataset",
                "target_table": "right_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "mappings": [],
            },
        ]
    }
    alipay_source = _alipay_order_source_payload()
    alipay_source["field_label_map"] = {
        **alipay_source["field_label_map"],
        "paid_time": "支付时间",
    }
    alipay_source["fields"] = [
        *alipay_source["fields"],
        {"name": "paid_time", "label": "支付时间", "data_type": "date"},
    ]
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_fp_customer_order_no",
                    "semantic_name": "客户订单号",
                    "usage": "match_key",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_alipay_merchant_order_no",
                    "semantic_name": "商户订单号",
                    "usage": "match_key",
                    "table_scope": ["public.alipay_orders"],
                },
                {
                    "ref_id": "ref_paid_time",
                    "semantic_name": "支付时间",
                    "usage": "source_value",
                    "table_scope": ["public.alipay_orders"],
                },
            ],
            "output_specs": [
                {
                    "output_id": "out_order_no",
                    "name": "订单号",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_fp_customer_order_no"],
                },
                {
                    "output_id": "out_time",
                    "name": "时间",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_paid_time"],
                },
            ],
            "business_rules": [
                {
                    "rule_id": "rule_join",
                    "type": "join",
                    "description": "fp 客户订单号关联支付宝商户订单号取支付时间",
                    "related_ref_ids": [
                        "ref_fp_customer_order_no",
                        "ref_alipay_merchant_order_no",
                    ],
                    "output_ids": ["out_time"],
                    "params": {
                        "left_ref_id": "ref_fp_customer_order_no",
                        "right_ref_id": "ref_alipay_merchant_order_no",
                    },
                }
            ],
        },
        rule_text="时间是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的支付时间",
        target_table="right_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_fp_customer_order_no",
            "status": "bound",
            "selected_field": {"name": "customer_order_no", "table_name": "public.fp_orders"},
        },
        {
            "intent_id": "ref_alipay_merchant_order_no",
            "status": "bound",
            "selected_field": {"name": "merchant_order_no", "table_name": "public.alipay_orders"},
        },
        {
            "intent_id": "ref_paid_time",
            "status": "bound",
            "selected_field": {"name": "paid_time", "table_name": "public.alipay_orders"},
        },
    ]

    compiled_rule = compile_understanding_into_rule(
        rule_json,
        understanding=understanding,
        field_bindings=field_bindings,
        sources=[_fp_order_source_payload(), alipay_source],
        target_table="right_recon_ready",
        target_tables=[],
    )

    write_step = compiled_rule["steps"][1]
    order_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "订单号")
    time_mapping = next(item for item in write_step["mappings"] if item["target_field"] == "时间")
    assert order_mapping["value"] == {
        "type": "source",
        "source": {"alias": "fp", "field": "customer_order_no"},
    }
    assert _contains_value_type(time_mapping["value"], "lookup")
    lint_result = lint_proc_rule(
        compiled_rule,
        side="right",
        target_table="right_recon_ready",
        target_tables=[],
        sources=[_fp_order_source_payload(), alipay_source],
    )
    assert lint_result["success"] is True


def test_join_formula_is_compiled_without_json_runtime_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RuleGenerationService()
    bad_rule = {
        "role_desc": "测试规则",
        "version": "1.0",
        "metadata": {"author": "test"},
        "global_config": {},
        "file_rule_code": "test_rule",
        "dsl_constraints": {"actions": ["create_schema", "write_dataset"]},
        "steps": [
            {
                "step_id": "create_left_recon_ready",
                "action": "create_schema",
                "target_table": "left_recon_ready",
                "schema": {
                    "primary_key": [],
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "write_left_recon_ready",
                "action": "write_dataset",
                "target_table": "left_recon_ready",
                "sources": [
                    {"table": "public.fp_orders", "alias": "fp"},
                    {"table": "public.alipay_orders", "alias": "alipay"},
                ],
                "row_write_mode": "upsert",
                "mappings": [
                    {
                        "target_field": "订单号",
                        "value": {
                            "type": "source",
                            "source": {"alias": "fp", "field": "customer_order_no"},
                        },
                    },
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "formula",
                            "expr": "({ref_amount} + 10)",
                            "bindings": {
                                "ref_amount": {
                                    "type": "source",
                                    "source": {"alias": "alipay", "field": "order_amount"},
                                }
                            },
                        },
                    },
                ],
            },
        ],
    }
    repaired_rule = {
        **bad_rule,
        "steps": [
            bad_rule["steps"][0],
            {
                **bad_rule["steps"][1],
                "mappings": [
                    bad_rule["steps"][1]["mappings"][0],
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "formula",
                            "expr": "({ref_amount} + 10)",
                            "bindings": {
                                "ref_amount": {
                                    "type": "lookup",
                                    "source_alias": "alipay",
                                    "value_field": "order_amount",
                                    "keys": [
                                        {
                                            "lookup_field": "merchant_order_no",
                                            "input": {
                                                "type": "source",
                                                "source": {"alias": "fp", "field": "customer_order_no"},
                                            },
                                        }
                                    ],
                                }
                            },
                        },
                    },
                ],
            },
        ],
    }
    llm_responses = iter([
        {
            "understanding": {
                "rule_summary": "fp 客户订单号关联支付宝商户订单号取订单金额并加 10",
                "source_references": [
                    {
                        "ref_id": "ref_fp_order_no",
                        "semantic_name": "客户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.fp_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_alipay_order_no",
                        "semantic_name": "商户订单号",
                        "usage": "lookup_key",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                    {
                        "ref_id": "ref_amount",
                        "semantic_name": "订单金额",
                        "usage": "source_value",
                        "table_scope": ["public.alipay_orders"],
                        "must_bind": True,
                    },
                ],
                "output_specs": [
                    {
                        "output_id": "out_order_no",
                        "name": "订单号",
                        "kind": "rename",
                        "source_ref_ids": ["ref_fp_order_no"],
                    },
                    {
                        "output_id": "out_amount",
                        "name": "金额",
                        "kind": "formula",
                        "source_ref_ids": [
                            "ref_fp_order_no",
                            "ref_alipay_order_no",
                            "ref_amount",
                        ],
                        "expression": {
                            "op": "add",
                            "operands": [
                                {"op": "ref", "ref_id": "ref_amount"},
                                {"op": "constant", "value": 10},
                            ],
                        },
                    },
                ],
                "business_rules": [
                    {
                        "rule_id": "join_amount",
                        "type": "join",
                        "description": "fp 客户订单号关联支付宝商户订单号取订单金额",
                        "related_ref_ids": [
                            "ref_fp_order_no",
                            "ref_alipay_order_no",
                            "ref_amount",
                        ],
                    }
                ],
            },
            "assumptions": [],
            "ambiguities": [],
        },
        bad_rule,
        repaired_rule,
    ])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "normalized_rule": repaired_rule,
            "output_samples": [
                {
                    "target_table": "left_recon_ready",
                    "rows": [{"订单号": "M-001", "金额": 98.12}],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    events = asyncio.run(
        _collect_events(
            service.stream_proc_side(
                auth_token="token",
                payload={
                    "side": "left",
                    "target_table": "left_recon_ready",
                    "rule_text": (
                        "订单号为fp订单表的客户订单号\n"
                        "金额是fp订单表的客户订单号与支付宝订单数据的商户订单号关联出的订单金额+10"
                    ),
                    "sources": [_fp_order_source_payload(), _alipay_order_source_payload()],
                },
            )
        )
    )
    result = events[-1]

    assert result["event"] == "graph_completed"
    amount_mapping = next(
        item
        for item in result["proc_rule_json"]["steps"][1]["mappings"]
        if item["target_field"] == "金额"
    )
    assert _contains_value_type(amount_mapping["value"], "lookup")
    checked_nodes = [
        event["node"]["code"]
        for event in events
        if event.get("event") in {"node_completed", "node_failed"} and isinstance(event.get("node"), dict)
    ]
    assert checked_nodes.count("lint_proc_json") == 1
    assert "repair_proc_json_runtime" not in checked_nodes


def test_source_passthrough_with_result_refs_requires_explicit_outputs() -> None:
    understanding = normalize_understanding(
        {
            "output_mode": "source_passthrough",
            "source_references": [
                {
                    "ref_id": "ref_merchant",
                    "semantic_name": "销售商户编码",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_charge",
                    "semantic_name": "充值账号",
                    "usage": "filter_field",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "采购总金额",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                },
                {
                    "ref_id": "ref_time",
                    "semantic_name": "订单创建时间",
                    "usage": "time_field",
                    "table_scope": ["public.fp_orders"],
                },
            ],
            "output_specs": [],
            "business_rules": [
                {
                    "rule_id": "filter_charge",
                    "type": "filter",
                    "related_ref_ids": ["ref_charge"],
                    "predicate": {
                        "op": "eq",
                        "left": {"op": "ref", "ref_id": "ref_charge"},
                        "right": {"op": "constant", "value": "charge_001"},
                    },
                }
            ],
        },
        rule_text=(
            "保留销售商户编码\n"
            "只取充值账号为charge_001的数据\n"
            "保留采购总金额\n"
            "保留订单创建时间"
        ),
        target_table="right_recon_ready",
    )
    source_profile = _source_profile(_fp_projection_source_payload())
    field_bindings = [
        {
            "intent_id": "ref_merchant",
            "usage": "source_value",
            "status": "bound",
            "selected_field": {
                "name": "sales_merchant_code",
                "label": "销售商户编码",
                "table_name": "public.fp_orders",
            },
        },
        {
            "intent_id": "ref_charge",
            "usage": "filter_field",
            "status": "bound",
            "selected_field": {
                "name": "charge_account",
                "label": "充值账号",
                "table_name": "public.fp_orders",
            },
        },
        {
            "intent_id": "ref_amount",
            "usage": "source_value",
            "status": "bound",
            "selected_field": {
                "name": "purchase_total_amount",
                "label": "采购总金额",
                "table_name": "public.fp_orders",
            },
        },
        {
            "intent_id": "ref_time",
            "usage": "time_field",
            "status": "bound",
            "selected_field": {
                "name": "order_create_time",
                "label": "订单创建时间",
                "table_name": "public.fp_orders",
            },
        },
    ]

    result = lint_rule_generation_ir(
        understanding,
        field_bindings=field_bindings,
        rule_text=(
            "保留销售商户编码\n"
            "只取充值账号为charge_001的数据\n"
            "保留采购总金额\n"
            "保留订单创建时间"
        ),
        source_profiles=[source_profile],
    )

    assert result["success"] is False
    assert any(
        error.get("reason") == "source_passthrough_has_unprojected_source_refs"
        for error in result["errors"]
    )


def test_lint_rejects_contains_predicate_before_compile() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_filter",
                    "semantic_name": "客户会员编码",
                    "usage": "filter_field",
                    "table_scope": ["public.trade_orders"],
                }
            ],
            "business_rules": [
                {
                    "rule_id": "filter_member",
                    "type": "filter",
                    "related_ref_ids": ["ref_filter"],
                    "predicate": {
                        "op": "contains",
                        "left": {"op": "ref", "ref_id": "ref_filter"},
                        "right": {"op": "constant", "value": "CUST_MEMBER"},
                    },
                }
            ],
        },
        rule_text="客户会员编码包含 CUST_MEMBER",
        target_table="right_recon_ready",
    )

    result = lint_rule_generation_ir(
        understanding,
        field_bindings=[
            {
                "intent_id": "ref_filter",
                "usage": "filter_field",
                "status": "bound",
                "selected_field": {
                    "name": "customer_member_code",
                    "label": "客户会员编码",
                    "table_name": "public.trade_orders",
                },
            }
        ],
        rule_text="客户会员编码包含 CUST_MEMBER",
        source_profiles=[_source_profile(_source_payload())],
    )

    assert result["success"] is False
    assert any(
        error.get("reason") == "business_rule_predicate_unsupported_contains"
        for error in result["errors"]
    )


def test_lint_rejects_unknown_runtime_function_before_compile() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "含税销售金额",
                    "usage": "source_value",
                    "table_scope": ["public.trade_orders"],
                }
            ],
            "output_specs": [
                {
                    "output_id": "out_amount",
                    "name": "金额",
                    "kind": "formula",
                    "source_ref_ids": ["ref_amount"],
                    "expression": {
                        "op": "function",
                        "name": "unsupported_func",
                        "args": [{"op": "ref", "ref_id": "ref_amount"}],
                    },
                }
            ],
        },
        rule_text="金额使用未知函数计算",
        target_table="right_recon_ready",
    )

    result = lint_rule_generation_ir(
        understanding,
        field_bindings=[
            {
                "intent_id": "ref_amount",
                "usage": "source_value",
                "status": "bound",
                "selected_field": {
                    "name": "tax_sale_amount",
                    "label": "含税销售金额",
                    "table_name": "public.trade_orders",
                },
            }
        ],
        rule_text="金额使用未知函数计算",
        source_profiles=[_source_profile(_source_payload())],
    )

    assert result["success"] is False
    assert any(
        error.get("reason") == "output_expression_unsupported_function"
        for error in result["errors"]
    )


def test_normalize_in_predicate_accepts_right_list() -> None:
    understanding = normalize_understanding(
        {
            "source_references": [
                {
                    "ref_id": "ref_filter",
                    "semantic_name": "客户会员编码",
                    "usage": "filter_field",
                }
            ],
            "business_rules": [
                {
                    "rule_id": "filter_member",
                    "type": "filter",
                    "predicate": {
                        "op": "in",
                        "left": {"op": "ref", "ref_id": "ref_filter"},
                        "right": ["CUST_MEMBER_001", "CUST_MEMBER_002"],
                    },
                }
            ],
        },
        rule_text="客户会员编码在两个会员中",
        target_table="right_recon_ready",
    )

    predicate = understanding["business_rules"][0]["predicate"]
    assert predicate == {
        "op": "in",
        "left": {"op": "ref", "ref_id": "ref_filter"},
        "right": [
            {"op": "constant", "value": "CUST_MEMBER_001"},
            {"op": "constant", "value": "CUST_MEMBER_002"},
        ],
    }


def test_rule_text_field_coverage_does_not_count_shadowed_short_field() -> None:
    source = _trade_order_source_with_member_aliases_payload()
    understanding = normalize_understanding(
        {
            "output_mode": "explicit",
            "source_references": [
                {
                    "ref_id": "ref_key",
                    "semantic_name": "根订单号",
                    "usage": "match_key",
                    "table_scope": ["public.ods_yxst_trd_order_di_o"],
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "含税销售金额",
                    "usage": "compare_field",
                    "table_scope": ["public.ods_yxst_trd_order_di_o"],
                },
                {
                    "ref_id": "ref_time",
                    "semantic_name": "订单完成时间",
                    "usage": "time_field",
                    "table_scope": ["public.ods_yxst_trd_order_di_o"],
                },
                {
                    "ref_id": "ref_filter",
                    "semantic_name": "客户会员编码",
                    "usage": "filter_field",
                    "table_scope": ["public.ods_yxst_trd_order_di_o"],
                },
            ],
            "output_specs": [
                {"output_id": "out_key", "name": "根订单号", "kind": "passthrough", "source_ref_ids": ["ref_key"]},
                {"output_id": "out_amount", "name": "含税销售金额", "kind": "passthrough", "source_ref_ids": ["ref_amount"]},
                {"output_id": "out_time", "name": "订单完成时间", "kind": "passthrough", "source_ref_ids": ["ref_time"]},
            ],
            "business_rules": [
                {
                    "rule_id": "filter_member",
                    "type": "filter",
                    "related_ref_ids": ["ref_filter"],
                    "predicate": {
                        "op": "eq",
                        "left": {"op": "ref", "ref_id": "ref_filter"},
                        "right": {"op": "constant", "value": "6965404"},
                    },
                }
            ],
        },
        rule_text=(
            "根订单号作为匹配字段\n"
            "含税销售金额作为对比字段\n"
            "订单完成时间作为时间字段\n"
            "只取客户会员编码为6965404的数据"
        ),
        target_table="right_recon_ready",
    )
    field_bindings = [
        {
            "intent_id": "ref_key",
            "usage": "match_key",
            "status": "bound",
            "selected_field": {"name": "root_order_id", "label": "根订单号", "table_name": "public.ods_yxst_trd_order_di_o"},
        },
        {
            "intent_id": "ref_amount",
            "usage": "compare_field",
            "status": "bound",
            "selected_field": {"name": "tax_sale_amount", "label": "含税销售金额", "table_name": "public.ods_yxst_trd_order_di_o"},
        },
        {
            "intent_id": "ref_time",
            "usage": "time_field",
            "status": "bound",
            "selected_field": {"name": "order_finish_time", "label": "订单完成时间", "table_name": "public.ods_yxst_trd_order_di_o"},
        },
        {
            "intent_id": "ref_filter",
            "usage": "filter_field",
            "status": "bound",
            "selected_field": {"name": "cust_memer_code", "label": "客户会员编码", "table_name": "public.ods_yxst_trd_order_di_o"},
        },
    ]

    result = lint_rule_generation_ir(
        understanding,
        field_bindings=field_bindings,
        rule_text=(
            "根订单号作为匹配字段\n"
            "含税销售金额作为对比字段\n"
            "订单完成时间作为时间字段\n"
            "只取客户会员编码为6965404的数据"
        ),
        source_profiles=[_source_profile(source)],
    )

    assert result["success"] is True


def test_projection_passthrough_ir_is_repaired_to_three_output_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RuleGenerationService()
    wrong_understanding = {
        "understanding": {
            "rule_summary": "过滤充值账号并输出部分字段",
            "output_mode": "source_passthrough",
            "source_references": [
                {
                    "ref_id": "ref_merchant",
                    "semantic_name": "销售商户编码",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_charge",
                    "semantic_name": "充值账号",
                    "usage": "filter_field",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_amount",
                    "semantic_name": "采购总金额",
                    "usage": "source_value",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
                {
                    "ref_id": "ref_time",
                    "semantic_name": "订单创建时间",
                    "usage": "time_field",
                    "table_scope": ["public.fp_orders"],
                    "must_bind": True,
                },
            ],
            "output_specs": [],
            "business_rules": [
                {
                    "rule_id": "filter_charge",
                    "type": "filter",
                    "related_ref_ids": ["ref_charge"],
                    "predicate": {
                        "op": "eq",
                        "left": {"op": "ref", "ref_id": "ref_charge"},
                        "right": {"op": "constant", "value": "charge_001"},
                    },
                }
            ],
        },
        "assumptions": [],
        "ambiguities": [],
    }
    repaired_understanding = {
        "understanding": {
            **wrong_understanding["understanding"],
            "output_mode": "explicit",
            "output_specs": [
                {
                    "output_id": "out_merchant",
                    "name": "销售商户编码",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_merchant"],
                },
                {
                    "output_id": "out_amount",
                    "name": "采购总金额",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_amount"],
                },
                {
                    "output_id": "out_time",
                    "name": "订单创建时间",
                    "kind": "passthrough",
                    "source_ref_ids": ["ref_time"],
                },
            ],
        },
        "assumptions": [],
        "ambiguities": [],
    }
    llm_responses = iter([wrong_understanding, repaired_understanding])

    async def fake_invoke_llm_json(prompt: str, **_: object) -> dict[str, object]:
        return next(llm_responses)

    async def fake_run_proc_sample(**_: object) -> dict[str, object]:
        return {
            "success": True,
            "ready_for_confirm": True,
            "backend": "mock",
            "output_samples": [
                {
                    "target_table": "right_recon_ready",
                    "rows": [
                        {
                            "销售商户编码": "merchant_001",
                            "采购总金额": 120.5,
                            "订单创建时间": "2026-04-16 09:10:00",
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr("graphs.rule_generation.service.invoke_llm_json", fake_invoke_llm_json)
    monkeypatch.setattr("graphs.rule_generation.service.run_proc_sample", fake_run_proc_sample)

    events = asyncio.run(
        _collect_events(
            service.stream_proc_side(
                auth_token="token",
                payload={
                    "side": "right",
                    "target_table": "right_recon_ready",
                    "rule_text": (
                        "保留销售商户编码\n"
                        "只取充值账号为charge_001的数据\n"
                        "保留采购总金额\n"
                        "保留订单创建时间"
                    ),
                    "sources": [_fp_projection_source_payload()],
                },
            )
        )
    )
    result = events[-1]

    assert result["event"] == "graph_completed"
    assert [field["name"] for field in result["output_fields"]] == [
        "销售商户编码",
        "采购总金额",
        "订单创建时间",
    ]
    schema_columns = result["proc_rule_json"]["steps"][0]["schema"]["columns"]
    assert [column["name"] for column in schema_columns] == [
        "销售商户编码",
        "采购总金额",
        "订单创建时间",
    ]
