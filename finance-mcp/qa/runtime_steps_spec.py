from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from proc.mcp_server.steps_runtime import StepsProcRuntime
from tools.rule_schema import validate_rule_record


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def test_example_overdue_rule_validates_as_proc_steps() -> None:
    rule_path = Path(__file__).resolve().parents[1] / "examples/proc/overdue_requirement_v1.json"
    rule = json.loads(rule_path.read_text(encoding="utf-8"))

    result = validate_rule_record(
        {
            "rule_code": "overdue_statistics",
            "rule": rule,
        },
        "proc_entry",
    )

    assert result["success"] is True


def test_steps_runtime_supports_add_months_and_lookup(tmp_path: Path) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    debit_path = uploads_root / "借方-计提单明细.csv"
    credit_path = uploads_root / "贷方-收款单明细.csv"

    _write_csv(
        debit_path,
        [
            {
                "对应科目编码": "1001",
                "对应科目": "应收账款",
                "日期": "2026-01-15",
                "公司名称": "测试公司",
                "中心": "华东中心",
                "周期": 2,
                "客商名称": "客户A",
                "含税金额": 100,
                "不含税金额": 90,
                "税额": 10,
                "单号整理": "JT001",
                "期数": "1",
            }
        ],
    )
    _write_csv(
        credit_path,
        [
            {
                "对应科目编码": "1001",
                "对应科目": "应收账款",
                "日期": "2026-02-01",
                "公司名称": "测试公司",
                "客商名称": "客户A",
                "金额": 60,
                "单号": "SK001",
                "费用项目": "测试费用",
                "商户": "测试商户",
                "填单人": "张三",
            }
        ],
    )

    rule = {
        "steps": [
            {
                "step_id": "create_debit_usage",
                "action": "create_schema",
                "target_table": "统计使用-借方",
                "schema": {
                    "primary_key": ["单号", "对应科目编码", "公司名称", "客商名称", "周期", "中心"],
                    "columns": [
                        {"name": "对应科目编码", "data_type": "string", "nullable": False},
                        {"name": "对应科目", "data_type": "string", "nullable": False},
                        {"name": "日期", "data_type": "date", "nullable": False},
                        {"name": "公司名称", "data_type": "string", "nullable": False},
                        {"name": "中心", "data_type": "string", "nullable": False},
                        {"name": "周期", "data_type": "string", "nullable": False},
                        {"name": "客商名称", "data_type": "string", "nullable": False},
                        {"name": "含税金额", "data_type": "decimal", "precision": 18, "scale": 2, "default": 0},
                        {"name": "不含税金额", "data_type": "decimal", "precision": 18, "scale": 2, "default": 0},
                        {"name": "税额", "data_type": "decimal", "precision": 18, "scale": 2, "default": 0},
                        {"name": "单号", "data_type": "string", "nullable": False},
                        {"name": "期数", "data_type": "string", "nullable": True},
                        {"name": "逾期时间", "data_type": "date", "nullable": True},
                    ],
                },
            },
            {
                "step_id": "write_debit_usage",
                "depends_on": ["create_debit_usage"],
                "action": "write_dataset",
                "target_table": "统计使用-借方",
                "sources": [{"table": "借方-计提单明细", "alias": "debit_detail_source"}],
                "mappings": [
                    {
                        "target_field": "对应科目编码",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "对应科目编码"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "对应科目",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "对应科目"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "日期",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "日期"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "公司名称",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "公司名称"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "中心",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "中心"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "周期",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "周期"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "客商名称",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "客商名称"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "含税金额",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "含税金额"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "不含税金额",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "不含税金额"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "税额",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "税额"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "单号",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "单号整理"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "期数",
                        "value": {"type": "source", "source": {"alias": "debit_detail_source", "field": "期数"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "逾期时间",
                        "value": {
                            "type": "function",
                            "function": "add_months",
                            "args": {
                                "date": {"type": "source", "source": {"alias": "debit_detail_source", "field": "日期"}},
                                "months": {"type": "source", "source": {"alias": "debit_detail_source", "field": "周期"}},
                            },
                        },
                        "field_write_mode": "overwrite",
                    },
                ],
                "row_write_mode": "upsert",
            },
            {
                "step_id": "create_credit_usage",
                "depends_on": ["write_debit_usage"],
                "action": "create_schema",
                "target_table": "统计使用-贷方",
                "schema": {
                    "primary_key": ["单号", "对应科目编码", "公司名称", "客商名称", "周期", "中心"],
                    "columns": [
                        {"name": "对应科目编码", "data_type": "string", "nullable": False},
                        {"name": "对应科目", "data_type": "string", "nullable": False},
                        {"name": "日期", "data_type": "date", "nullable": False},
                        {"name": "公司名称", "data_type": "string", "nullable": False},
                        {"name": "客商名称", "data_type": "string", "nullable": False},
                        {"name": "中心", "data_type": "string", "nullable": False},
                        {"name": "周期", "data_type": "string", "nullable": False},
                        {"name": "金额", "data_type": "decimal", "precision": 18, "scale": 2, "default": 0},
                        {"name": "单号", "data_type": "string", "nullable": False},
                        {"name": "费用项目", "data_type": "string", "nullable": True},
                        {"name": "商户", "data_type": "string", "nullable": True},
                        {"name": "填单人", "data_type": "string", "nullable": True},
                    ],
                },
            },
            {
                "step_id": "write_credit_usage",
                "depends_on": ["create_credit_usage"],
                "action": "write_dataset",
                "target_table": "统计使用-贷方",
                "sources": [
                    {"table": "贷方-收款单明细", "alias": "credit_detail_source"},
                    {"table": "统计使用-借方", "alias": "debit_usage_lookup"},
                ],
                "filter": {
                    "type": "formula",
                    "expr": "not is_null({lookup_center}) and not is_null({lookup_period})",
                    "bindings": {
                        "lookup_center": {
                            "type": "lookup",
                            "source_alias": "debit_usage_lookup",
                            "value_field": "中心",
                            "keys": [
                                {"lookup_field": "对应科目编码", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目编码"}}},
                                {"lookup_field": "对应科目", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目"}}},
                                {"lookup_field": "公司名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "公司名称"}}},
                                {"lookup_field": "客商名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "客商名称"}}},
                            ],
                        },
                        "lookup_period": {
                            "type": "lookup",
                            "source_alias": "debit_usage_lookup",
                            "value_field": "周期",
                            "keys": [
                                {"lookup_field": "对应科目编码", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目编码"}}},
                                {"lookup_field": "对应科目", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目"}}},
                                {"lookup_field": "公司名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "公司名称"}}},
                                {"lookup_field": "客商名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "客商名称"}}},
                            ],
                        },
                    },
                },
                "mappings": [
                    {
                        "target_field": "对应科目编码",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目编码"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "对应科目",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "日期",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "日期"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "公司名称",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "公司名称"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "客商名称",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "客商名称"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "中心",
                        "value": {
                            "type": "lookup",
                            "source_alias": "debit_usage_lookup",
                            "value_field": "中心",
                            "keys": [
                                {"lookup_field": "对应科目编码", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目编码"}}},
                                {"lookup_field": "对应科目", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目"}}},
                                {"lookup_field": "公司名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "公司名称"}}},
                                {"lookup_field": "客商名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "客商名称"}}},
                            ],
                        },
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "周期",
                        "value": {
                            "type": "lookup",
                            "source_alias": "debit_usage_lookup",
                            "value_field": "周期",
                            "keys": [
                                {"lookup_field": "对应科目编码", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目编码"}}},
                                {"lookup_field": "对应科目", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "对应科目"}}},
                                {"lookup_field": "公司名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "公司名称"}}},
                                {"lookup_field": "客商名称", "input": {"type": "source", "source": {"alias": "credit_detail_source", "field": "客商名称"}}},
                            ],
                        },
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "金额",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "金额"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "单号",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "单号"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "费用项目",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "费用项目"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "商户",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "商户"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "填单人",
                        "value": {"type": "source", "source": {"alias": "credit_detail_source", "field": "填单人"}},
                        "field_write_mode": "overwrite",
                    },
                ],
                "row_write_mode": "upsert",
            },
        ]
    }

    runtime = StepsProcRuntime(
        "runtime_test_rule",
        rule,
        [
            {"table_name": "借方-计提单明细", "file_path": str(debit_path)},
            {"table_name": "贷方-收款单明细", "file_path": str(credit_path)},
        ],
        str(tmp_path / "output"),
    )

    runtime.execute()

    debit_usage = runtime.tables["统计使用-借方"]
    credit_usage = runtime.tables["统计使用-贷方"]

    assert len(debit_usage) == 1
    assert str(debit_usage.iloc[0]["逾期时间"]) == "2026-03-15"

    assert len(credit_usage) == 1
    assert credit_usage.iloc[0]["中心"] == "华东中心"
    assert str(credit_usage.iloc[0]["周期"]) == "2"


def test_steps_runtime_supports_to_decimal_function_in_formula_binding(tmp_path: Path) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "订单.csv"
    _write_csv(source_path, [{"订单号": "O-001", "金额": "80.60"}])

    rule = {
        "steps": [
            {
                "step_id": "create_output",
                "action": "create_schema",
                "target_table": "输出",
                "schema": {
                    "primary_key": ["订单号"],
                    "columns": [
                        {"name": "订单号", "data_type": "string"},
                        {"name": "输出金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "write_output",
                "depends_on": ["create_output"],
                "action": "write_dataset",
                "target_table": "输出",
                "sources": [{"table": "订单", "alias": "orders"}],
                "mappings": [
                    {
                        "target_field": "订单号",
                        "value": {"type": "source", "source": {"alias": "orders", "field": "订单号"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "输出金额",
                        "value": {
                            "type": "formula",
                            "expr": "{amount} + 10",
                            "bindings": {
                                "amount": {
                                    "type": "function",
                                    "function": "to_decimal",
                                    "args": {
                                        "value": {
                                            "type": "source",
                                            "source": {"alias": "orders", "field": "金额"},
                                        }
                                    },
                                }
                            },
                        },
                        "field_write_mode": "overwrite",
                    },
                ],
                "row_write_mode": "upsert",
            },
        ]
    }

    runtime = StepsProcRuntime(
        "runtime_to_decimal_rule",
        rule,
        [{"table_name": "订单", "file_path": str(source_path)}],
        str(tmp_path / "output"),
    )

    runtime.execute()

    output = runtime.tables["输出"]
    assert len(output) == 1
    assert output.iloc[0]["输出金额"] == 90.6
