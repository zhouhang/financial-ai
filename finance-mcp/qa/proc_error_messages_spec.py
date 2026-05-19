from __future__ import annotations

import pytest

from proc.mcp_server.steps_runtime import (
    ProcRuntimeError,
    ProcRuleConfigError,
    ProcUserDataError,
)


def test_proc_error_subclasses() -> None:
    assert issubclass(ProcUserDataError, ProcRuntimeError)
    assert issubclass(ProcRuleConfigError, ProcRuntimeError)


def test_proc_error_format_detail_has_three_parts() -> None:
    err = ProcUserDataError(
        summary="规则「逾期统计数据整理」无法处理文件「借方-计提单明细」",
        cause="缺少列「公司」。",
        suggestion="请补充该列。",
    )
    detail = err.format_detail()
    assert "数据整理失败：规则「逾期统计数据整理」无法处理文件「借方-计提单明细」" in detail
    assert "原因：缺少列「公司」。" in detail
    assert "建议：请补充该列。" in detail
    assert str(err) == detail


import pandas as pd

from proc.mcp_server.steps_runtime import StepsProcRuntime


def _make_runtime(tmp_path, rule_data=None, validated_files=None) -> StepsProcRuntime:
    return StepsProcRuntime(
        rule_code="r_test",
        rule_data=rule_data if rule_data is not None else {"name": "逾期统计数据整理", "steps": []},
        validated_files=validated_files
        if validated_files is not None
        else [{"table_name": "借方-计提单明细", "file_path": "/uploads/借方-计提单明细.xlsx"}],
        output_dir=str(tmp_path),
    )


def test_rule_display_name_prefers_name(tmp_path) -> None:
    assert _make_runtime(tmp_path)._rule_display_name() == "逾期统计数据整理"


def test_rule_display_name_falls_back_to_code(tmp_path) -> None:
    rt = _make_runtime(tmp_path, rule_data={"steps": []})
    assert rt._rule_display_name() == "r_test"


def test_describe_table_distinguishes_file_and_intermediate(tmp_path) -> None:
    rt = _make_runtime(tmp_path)
    assert rt._describe_table("借方-计提单明细") == "文件「借方-计提单明细」"
    assert rt._describe_table("统计使用-借方") == "中间结果「统计使用-借方」"


def test_require_columns_raises_user_data_error_on_missing(tmp_path) -> None:
    rt = _make_runtime(tmp_path)
    df = pd.DataFrame({"对应科目编码": ["1001"]})
    with pytest.raises(ProcUserDataError) as exc_info:
        rt._require_columns(df, ["公司"], "借方-计提单明细")
    msg = str(exc_info.value)
    assert "逾期统计数据整理" in msg
    assert "借方-计提单明细" in msg
    assert "公司" in msg


def test_require_columns_passes_when_all_present(tmp_path) -> None:
    rt = _make_runtime(tmp_path)
    df = pd.DataFrame({"公司": ["A"], "金额": [1]})
    rt._require_columns(df, ["公司", "金额"], "借方-计提单明细")  # 不抛异常


import json
from pathlib import Path


def _write_csv_helper(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def test_missing_source_column_raises_user_data_error(tmp_path: Path) -> None:
    uploads_root = Path(__file__).resolve().parents[1] / "uploads/proc_error_messages_spec" / tmp_path.name
    uploads_root.mkdir(parents=True, exist_ok=True)

    debit_path = uploads_root / "借方-计提单明细.csv"
    credit_path = uploads_root / "贷方-收款单明细.csv"

    _write_csv_helper(
        debit_path,
        [
            {
                "对应科目编码": "1001",
                "对应科目": "应收账款",
                "日期": "2026-01-15",
                # "公司名称" intentionally omitted — missing column under test
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
    _write_csv_helper(
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

    with pytest.raises(ProcUserDataError) as exc_info:
        runtime.execute()
    msg = str(exc_info.value)
    assert "公司名称" in msg
    assert "借方-计提单明细" in msg


def test_render_proc_failure_passes_through_structured_error() -> None:
    from proc.mcp_server.proc_rule import render_proc_failure

    exc = ProcUserDataError(summary="规则「X」无法处理文件「Y」", cause="缺列「公司」。", suggestion="补上。")
    assert render_proc_failure(exc) == exc.format_detail()


def test_render_proc_failure_translates_bare_keyerror() -> None:
    from proc.mcp_server.proc_rule import render_proc_failure

    detail = render_proc_failure(KeyError("公司"))
    assert "公司" in detail
    assert "原因：" in detail
    assert "建议：" in detail


def test_render_proc_failure_wraps_unknown_exception() -> None:
    from proc.mcp_server.proc_rule import render_proc_failure

    detail = render_proc_failure(RuntimeError("some internal boom"))
    assert "系统执行出错" in detail
    assert "管理员" in detail
    assert "some internal boom" not in detail
