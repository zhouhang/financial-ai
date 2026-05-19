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
