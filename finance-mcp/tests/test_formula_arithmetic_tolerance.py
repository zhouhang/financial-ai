"""公式算术对脏数据行的容错:单行非数值应得 None,不应整批 raise 崩 proc。

线上回填消化曾因某行 动账金额=date(1015-01-01) 让 `{动账金额}-{平台服务费}` 整 run 崩。
"""
import datetime

import pytest

from proc.mcp_server.steps_runtime import _evaluate_formula_expression


def _eval(expr: str, vars_: dict) -> object:
    # env 本身即变量字典(__vars__ 标识符在引擎里解析为整个 env)
    return _evaluate_formula_expression(expr, dict(vars_))


def test_subtract_with_garbage_date_operand_returns_none_not_raise() -> None:
    # 一行脏数据:动账金额 是日期,平台服务费 是数字字符串 → 该行结果 None,不抛错
    result = _eval(
        "({动账金额} - {平台服务费})",
        {"动账金额": datetime.date(1015, 1, 1), "平台服务费": "-6.13"},
    )
    assert result is None


def test_subtract_with_both_non_numeric_returns_none() -> None:
    result = _eval("({a} - {b})", {"a": "abc", "b": datetime.date(2026, 1, 1)})
    assert result is None


def test_normal_numeric_subtraction_still_works() -> None:
    # 正常数值/数字字符串照常计算(回归)
    result = _eval("({动账金额} - {平台服务费})", {"动账金额": "200.50", "平台服务费": "6.13"})
    assert result == pytest.approx(194.37)


def test_mult_div_with_garbage_returns_none() -> None:
    assert _eval("({a} * {b})", {"a": datetime.date(2026, 1, 1), "b": "2"}) is None
    assert _eval("({a} / {b})", {"a": "10", "b": datetime.date(2026, 1, 1)}) is None
