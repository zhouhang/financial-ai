from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from proc.mcp_server.steps_runtime import ProcRuleConfigError, StepsProcRuntime
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


def test_steps_runtime_filter_not_is_null_excludes_blank_strings(tmp_path: Path) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "订单.csv"
    _write_csv(
        source_path,
        [
            {"客户订单号": "O-001", "含税销售金额": 100},
            {"客户订单号": "", "含税销售金额": 200},
            {"客户订单号": "   ", "含税销售金额": 300},
            {"客户订单号": None, "含税销售金额": 400},
        ],
    )

    rule = {
        "steps": [
            {
                "step_id": "create_output",
                "action": "create_schema",
                "target_table": "输出",
                "schema": {
                    "primary_key": ["客户订单号"],
                    "columns": [
                        {"name": "客户订单号", "data_type": "string"},
                        {"name": "含税销售金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "write_output",
                "depends_on": ["create_output"],
                "action": "write_dataset",
                "target_table": "输出",
                "sources": [{"table": "订单", "alias": "orders"}],
                "filter": {
                    "type": "formula",
                    "expr": "not is_null({order_no})",
                    "bindings": {
                        "order_no": {
                            "type": "source",
                            "source": {"alias": "orders", "field": "客户订单号"},
                        }
                    },
                },
                "mappings": [
                    {
                        "target_field": "客户订单号",
                        "value": {"type": "source", "source": {"alias": "orders", "field": "客户订单号"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "含税销售金额",
                        "value": {"type": "source", "source": {"alias": "orders", "field": "含税销售金额"}},
                        "field_write_mode": "overwrite",
                    },
                ],
                "row_write_mode": "upsert",
            },
        ]
    }

    runtime = StepsProcRuntime(
        "runtime_filter_non_empty_rule",
        rule,
        [{"table_name": "订单", "file_path": str(source_path)}],
        str(tmp_path / "output"),
    )

    runtime.execute()

    output = runtime.tables["输出"]
    assert output["客户订单号"].tolist() == ["O-001"]


def test_steps_runtime_allows_missing_source_column_for_nullable_target_field(
    tmp_path: Path,
) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "科目期初.csv"
    _write_csv(source_path, [{"编号": "O-001", "金额": 100}])

    rule = {
        "steps": [
            {
                "step_id": "create_output",
                "action": "create_schema",
                "target_table": "统计使用-7月余额",
                "schema": {
                    "primary_key": ["编号"],
                    "columns": [
                        {"name": "编号", "data_type": "string", "nullable": False},
                        {"name": "金额", "data_type": "decimal", "default": 0},
                        {"name": "逾期时间", "data_type": "date", "nullable": True},
                    ],
                },
            },
            {
                "step_id": "write_output",
                "depends_on": ["create_output"],
                "action": "write_dataset",
                "target_table": "统计使用-7月余额",
                "sources": [{"table": "科目期初", "alias": "opening_balance_source"}],
                "mappings": [
                    {
                        "target_field": "编号",
                        "value": {
                            "type": "source",
                            "source": {"alias": "opening_balance_source", "field": "编号"},
                        },
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "金额",
                        "value": {
                            "type": "source",
                            "source": {"alias": "opening_balance_source", "field": "金额"},
                        },
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "逾期时间",
                        "value": {
                            "type": "source",
                            "source": {"alias": "opening_balance_source", "field": "逾期时间"},
                        },
                        "field_write_mode": "overwrite",
                    },
                ],
                "row_write_mode": "upsert",
            },
        ]
    }

    runtime = StepsProcRuntime(
        "nullable_source_compat_rule",
        rule,
        [{"table_name": "科目期初", "file_path": str(source_path)}],
        str(tmp_path / "output"),
    )

    runtime.execute()

    output = runtime.tables["统计使用-7月余额"]
    assert output.iloc[0]["编号"] == "O-001"
    assert pd.isna(output.iloc[0]["逾期时间"])


def _risk_asset_overdue_rule() -> dict[str, object]:
    return {
        "steps": [
            {
                "step_id": "create_result",
                "action": "create_schema",
                "target_table": "风险资产结果",
                "schema": {
                    "primary_key": ["编号"],
                    "columns": [
                        {"name": "编号", "data_type": "string"},
                        {"name": "其他信息", "data_type": "date"},
                        {"name": "期末余额", "data_type": "decimal"},
                        {"name": "逾期计算说明", "data_type": "string"},
                        {"name": "逾期金额", "data_type": "decimal"},
                    ],
                },
            },
            {
                "step_id": "seed_result",
                "depends_on": ["create_result"],
                "action": "write_dataset",
                "target_table": "风险资产结果",
                "sources": [{"table": "风险资产原始", "alias": "risk"}],
                "mappings": [
                    {
                        "target_field": "编号",
                        "value": {"type": "source", "source": {"alias": "risk", "field": "编号"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "其他信息",
                        "value": {"type": "source", "source": {"alias": "risk", "field": "其他信息"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "期末余额",
                        "value": {"type": "source", "source": {"alias": "risk", "field": "期末余额"}},
                        "field_write_mode": "overwrite",
                    },
                    {
                        "target_field": "逾期计算说明",
                        "value": {"type": "source", "source": {"alias": "risk", "field": "逾期计算说明"}},
                        "field_write_mode": "overwrite",
                    },
                ],
                "row_write_mode": "upsert",
            },
            {
                "step_id": "calculate_overdue",
                "description": "按有效期计算逾期金额",
                "depends_on": ["seed_result"],
                "action": "write_dataset",
                "target_table": "风险资产结果",
                "sources": [{"table": "风险资产结果", "alias": "result"}],
                "match": {
                    "sources": [
                        {
                            "alias": "result",
                            "keys": [{"field": "编号", "target_field": "编号"}],
                        }
                    ]
                },
                "mappings": [
                    {
                        "target_field": "逾期金额",
                        "value": {
                            "type": "formula",
                            "expr": (
                                "{ending} <= 0 ? 0 : "
                                "{rule} == '有效期＞2个月' ? "
                                "(is_null({other_info}) or {other_info} >= {today} ? 0 : {ending}) : 0"
                            ),
                            "bindings": {
                                "ending": {
                                    "type": "source",
                                    "source": {"alias": "result", "field": "期末余额"},
                                },
                                "rule": {
                                    "type": "source",
                                    "source": {"alias": "result", "field": "逾期计算说明"},
                                },
                                "other_info": {
                                    "type": "source",
                                    "source": {"alias": "result", "field": "其他信息"},
                                },
                                "today": {"type": "function", "function": "current_date", "args": {}},
                            },
                        },
                        "field_write_mode": "overwrite",
                    }
                ],
                "row_write_mode": "update_only",
            },
        ]
    }


def test_steps_runtime_treats_export_null_marker_as_empty_in_date_formula(tmp_path: Path) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "风险资产原始.csv"
    _write_csv(
        source_path,
        [
            {
                "编号": "R-001",
                "其他信息": r"\N",
                "期末余额": 100,
                "逾期计算说明": "有效期＞2个月",
            }
        ],
    )

    runtime = StepsProcRuntime(
        "runtime_risk_asset_null_date_rule",
        _risk_asset_overdue_rule(),
        [{"table_name": "风险资产原始", "file_path": str(source_path)}],
        str(tmp_path / "output"),
    )

    runtime.execute()

    output = runtime.tables["风险资产结果"]
    assert output.iloc[0]["逾期金额"] == 0


def test_steps_runtime_reports_field_context_for_unparseable_date_compare(tmp_path: Path) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "风险资产原始.csv"
    _write_csv(
        source_path,
        [
            {
                "编号": "R-001",
                "其他信息": "待确认",
                "期末余额": 100,
                "逾期计算说明": "有效期＞2个月",
            }
        ],
    )

    runtime = StepsProcRuntime(
        "runtime_risk_asset_bad_date_rule",
        _risk_asset_overdue_rule(),
        [{"table_name": "风险资产原始", "file_path": str(source_path)}],
        str(tmp_path / "output"),
    )

    with pytest.raises(ProcRuleConfigError) as exc_info:
        runtime.execute()

    message = str(exc_info.value)
    assert "公式比较失败" in message
    assert "calculate_overdue" in message
    assert "风险资产结果.逾期金额" in message
    assert "其他信息" in message
    assert "待确认" in message
    assert "风险资产原始.其他信息" in message


def test_steps_runtime_renames_alias_columns_to_canonical_on_load(tmp_path: Path) -> None:
    """上传文件用别名列名时，加载源表应改名为规则使用的规范列名。

    复现：proc 规则按 核算项目 分组聚合，但文件该列名为 客商名称，
    未规范化会导致 pandas.groupby 抛 KeyError('核算项目')。
    """
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "科目期初.csv"
    _write_csv(
        source_path,
        [{"科目名称": "应收账款", "公司": "测试公司", "客商名称": "客户A", "期末余额": 100}],
    )

    runtime = StepsProcRuntime(
        "alias_normalize_rule",
        {"steps": []},
        [{"table_name": "科目期初", "file_path": str(source_path)}],
        str(tmp_path / "output"),
        column_aliases={"科目期初": {"客商名称": "核算项目"}},
    )

    df = runtime._ensure_table_loaded("科目期初")

    assert "核算项目" in df.columns
    assert "客商名称" not in df.columns
    # 规范化后按规范列名分组不再抛 KeyError
    df.groupby(["科目名称", "公司", "核算项目"], dropna=False, sort=False)


def test_steps_runtime_skips_alias_rename_when_canonical_present(tmp_path: Path) -> None:
    """文件已含规范列名时不重命名，避免产生重复列。"""
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/runtime_steps_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    source_path = uploads_root / "科目期初2.csv"
    _write_csv(
        source_path,
        [{"科目名称": "应收账款", "核算项目": "客户A", "客商名称": "客户A"}],
    )

    runtime = StepsProcRuntime(
        "alias_normalize_rule",
        {"steps": []},
        [{"table_name": "科目期初", "file_path": str(source_path)}],
        str(tmp_path / "output"),
        column_aliases={"科目期初": {"客商名称": "核算项目"}},
    )

    df = runtime._ensure_table_loaded("科目期初")

    assert list(df.columns).count("核算项目") == 1
    assert "客商名称" in df.columns


def test_collect_table_field_references_attributes_fields_per_source_table() -> None:
    """规则按 source alias 引用列名时，应归属到对应输入表。

    覆盖规则用别名而非规范名、且不同表写法不一的情况。
    """
    from proc.mcp_server.proc_rule import _collect_table_field_references

    rule = {
        "steps": [
            {
                "step_id": "s1",
                "action": "write_dataset",
                "target_table": "金蝶期末余额-检核",
                "sources": [
                    {"alias": "debit_src", "table": "借方-计提单明细"},
                    {"alias": "credit_src", "table": "贷方-收款单明细"},
                ],
                "aggregate": [
                    {
                        "source_alias": "debit_src",
                        "output_alias": "debit_agg",
                        "group_fields": ["对应科目", "公司", "客商名称"],
                        "aggregations": [{"field": "含税金额", "operator": "sum", "alias": "a"}],
                    },
                    {
                        "source_alias": "credit_src",
                        "output_alias": "credit_agg",
                        "group_fields": ["科目名称", "公司", "客商名称"],
                        "aggregations": [{"field": "金额", "operator": "sum", "alias": "b"}],
                    },
                ],
                "match": {"sources": [{"alias": "debit_agg", "keys": [
                    {"field": "对应科目", "target_field": "核算项目1"},
                ]}]},
                "mappings": [{"target_field": "期初", "value": {
                    "type": "source", "source": {"alias": "credit_src", "field": "费用项目"}}}],
            }
        ]
    }

    refs = _collect_table_field_references(rule)

    # 借方按 对应科目/公司 引用，贷方按 科目名称/公司 引用 —— 同物理列不同写法各归各表
    assert refs["借方-计提单明细"] == {"对应科目", "公司", "客商名称", "含税金额"}
    assert refs["贷方-收款单明细"] == {"科目名称", "公司", "客商名称", "金额", "费用项目"}
    # match.keys[].target_field 归属到目标表
    assert "核算项目1" in refs["金蝶期末余额-检核"]
    # aggregate 输出别名（debit_agg）的字段不应被当作输入表列
    assert "金蝶期末余额-检核" in refs and "debit_agg" not in refs
