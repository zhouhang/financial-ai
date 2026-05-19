# 数据整理报错提示友好化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让数据整理(proc)失败时给出"摘要 / 原因 / 建议"三段式、能定位到规则+文件+列的友好报错,替代当前只显示一个字段名的现象。

**Architecture:** 在 proc 后端引入两类领域异常(`ProcUserDataError` 用户可修 / `ProcRuleConfigError` 配置 bug),用列访问守卫和归类后的 `raise` 让 `steps_runtime.py` 抛出带结构化原因的异常;`proc_rule.py` 顶层 catch 把这些异常渲染成成品文本,裸 `KeyError` 兜底翻译。展示层(LLM)不改。

**Tech Stack:** Python、pandas、pytest。

**设计文档:** `docs/superpowers/specs/2026-05-19-proc-error-messages-design.md`

---

## 文件结构

- `finance-mcp/proc/mcp_server/steps_runtime.py` — 修改。新增领域异常类、上下文 helper、列访问守卫;归类改造所有 `raise`。
- `finance-mcp/proc/mcp_server/proc_rule.py` — 修改。两处顶层 catch 渲染结构化错误 + 裸 `KeyError` 兜底。
- `finance-mcp/proc/mcp_server/merge_rule.py` — 修改。2 处面向用户的 `raise` 归类改造。
- `finance-mcp/qa/proc_error_messages_spec.py` — 新建。异常类、helper、运行时集成、顶层兜底的测试。

## 测试运行约定

qa 测试需 `finance-mcp` 在 `PYTHONPATH`,且用项目 venv 的 pytest。所有测试命令形如:

```bash
cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py -v
```

---

## Task 1: 领域异常类

**Files:**
- Modify: `finance-mcp/proc/mcp_server/steps_runtime.py`(在文件顶部 `FormulaEvaluationError` 类附近新增)
- Test: `finance-mcp/qa/proc_error_messages_spec.py`(新建)

- [ ] **Step 1: 写失败测试**

创建 `finance-mcp/qa/proc_error_messages_spec.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py -v`
Expected: FAIL — `ImportError: cannot import name 'ProcRuntimeError'`。

- [ ] **Step 3: 实现异常类**

在 `finance-mcp/proc/mcp_server/steps_runtime.py` 中,`class FormulaEvaluationError` 定义之后新增:

```python
class ProcRuntimeError(Exception):
    """数据整理运行期错误基类,携带结构化的摘要/原因/建议。"""

    def __init__(self, *, summary: str, cause: str, suggestion: str) -> None:
        self.summary = summary
        self.cause = cause
        self.suggestion = suggestion
        super().__init__(self.format_detail())

    def format_detail(self) -> str:
        return (
            f"数据整理失败：{self.summary}\n\n"
            f"原因：{self.cause}\n"
            f"建议：{self.suggestion}"
        )


class ProcUserDataError(ProcRuntimeError):
    """类①:用户可自行修复的数据问题(文件缺列、日期格式错等)。"""


class ProcRuleConfigError(ProcRuntimeError):
    """类②:规则配置本身的问题,需规则作者/管理员修复。"""
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py -v`
Expected: PASS(2 个测试通过)。

- [ ] **Step 5: 提交**

```bash
git add finance-mcp/proc/mcp_server/steps_runtime.py finance-mcp/qa/proc_error_messages_spec.py
git commit -m "feat: add structured proc runtime error classes"
```

---

## Task 2: 上下文 helper 与列访问守卫

**Files:**
- Modify: `finance-mcp/proc/mcp_server/steps_runtime.py`(`StepsProcRuntime` 类内新增方法)
- Test: `finance-mcp/qa/proc_error_messages_spec.py`

**背景:** `StepsProcRuntime.__init__` 接受 `rule_code, rule_data, validated_files, output_dir` 等参数,内部已构建 `self.table_file_map`(`table_name` → 文件路径)与 `self.rule_data`。

- [ ] **Step 1: 写失败测试**

在 `finance-mcp/qa/proc_error_messages_spec.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py -v`
Expected: FAIL — `AttributeError: 'StepsProcRuntime' object has no attribute '_rule_display_name'`。

- [ ] **Step 3: 实现 helper**

在 `finance-mcp/proc/mcp_server/steps_runtime.py` 的 `StepsProcRuntime` 类内新增三个方法(放在 `__init__` 之后、`execute` 之前)。注意:`Path` 已在该文件顶部 import。

```python
    def _rule_display_name(self) -> str:
        name = str(self.rule_data.get("name") or "").strip()
        return name or self.rule_code

    def _describe_table(self, table_name: str) -> str:
        if table_name in self.table_file_map:
            return f"文件「{table_name}」"
        return f"中间结果「{table_name}」"

    def _require_columns(
        self, df: pd.DataFrame, columns: list[str], table_name: str
    ) -> None:
        missing = [str(c) for c in columns if str(c) and str(c) not in df.columns]
        if not missing:
            return
        table_desc = self._describe_table(table_name)
        column_list = "「" + "」「".join(missing) + "」"
        plural = "这些列" if len(missing) > 1 else "这一列"
        raise ProcUserDataError(
            summary=f"规则「{self._rule_display_name()}」无法处理{table_desc}",
            cause=f"该规则需要{table_desc}包含列{column_list}，但其中没有{plural}。",
            suggestion="请确认上传的文件含有上述列；若列名相近，检查是否有多余空格或命名不一致。",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py -v`
Expected: PASS(全部 7 个测试通过)。

- [ ] **Step 5: 提交**

```bash
git add finance-mcp/proc/mcp_server/steps_runtime.py finance-mcp/qa/proc_error_messages_spec.py
git commit -m "feat: add proc runtime context helpers and column guard"
```

---

## Task 3: steps_runtime 列守卫与 raise 归类改造

**Files:**
- Modify: `finance-mcp/proc/mcp_server/steps_runtime.py`
- Test: `finance-mcp/qa/proc_error_messages_spec.py`

**背景:** 此任务把 `steps_runtime.py` 里所有面向用户的 `raise` 改成领域异常,并在 `_apply_aggregations` 的列访问处加守卫。改造后,引用了不存在列的规则会抛 `ProcUserDataError`,配置错误抛 `ProcRuleConfigError`。

- [ ] **Step 1: 写失败的集成测试**

打开 `finance-mcp/qa/runtime_steps_spec.py`,找到测试函数 `test_steps_runtime_supports_add_months_and_lookup`。把它的 CSV 写入、规则构造、运行时调用逻辑**原样复制**为一个新函数 `test_missing_source_column_raises_user_data_error`,加进 `finance-mcp/qa/proc_error_messages_spec.py` 末尾(所需的 `import` 一并补齐:`json`、`Path`、以及该测试用到的运行入口)。然后做两处改动:

1. 在写借方明细 CSV 的那一行 `dict` 中,**删除 `"公司名称": ...` 这个键值对**(让源文件缺这一列)。
2. 把原测试结尾的成功断言替换为:

```python
    with pytest.raises(ProcUserDataError) as exc_info:
        # 这里保留原测试中"运行规则"的那行调用
        ...
    msg = str(exc_info.value)
    assert "公司名称" in msg
    assert "借方-计提单明细" in msg
```

(把 `...` 换成原测试里实际执行规则的那一行,例如 `StepsProcRuntime(...).execute()` 或 `execute_steps_rule_with_frames(...)`,与原测试保持一致。)

- [ ] **Step 2: 运行测试确认失败**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py::test_missing_source_column_raises_user_data_error -v`
Expected: FAIL — 当前缺列会抛裸 `KeyError` 或普通 `ValueError`,不是 `ProcUserDataError`。

- [ ] **Step 3a: 在 `_apply_aggregations` 加列守卫**

`steps_runtime.py` 中 aggregate 处理处(`source_df = alias_frames[source_alias]` 之后,当前约在第 545 行)。在该行之后插入守卫,一次性校验分组字段和聚合字段:

```python
            source_df = alias_frames[source_alias]
            _agg_fields = [
                str(item.get("field"))
                for item in aggregations
                if item.get("field")
            ]
            self._require_columns(
                source_df,
                [str(f) for f in group_fields] + _agg_fields,
                alias_tables.get(source_alias, source_alias),
            )
```

- [ ] **Step 3b: 归类改造所有 `raise`**

对 `steps_runtime.py` 中每一处 `raise`,按下表替换。**统一改造方式:**

- 类② → `raise ProcRuleConfigError(summary=f"规则「{self._rule_display_name()}」配置有误", cause=<原消息文本>, suggestion="这是规则配置问题，请联系管理员核对规则后重试。")`
- 类① → `raise ProcUserDataError(summary=..., cause=..., suggestion=...)`,文案见各条说明。
- 不在类内的模块级函数(无 `self`)中的 `raise`:见下方"模块级函数"说明。

**类②(规则配置 bug)** — 原消息整段作为 `cause`,summary/suggestion 用上面的统一模板。涉及的原消息(按其文本定位,行号会随改动漂移):

- `step '...' 依赖未定义: ...`
- `steps 依赖无法解析，可能存在循环依赖: ...`
- `不支持的 step action: ...`
- `不支持的 row_write_mode: ...`
- `reference_filter source_alias 不存在: ...`
- `reference_filter 缺少 reference_table`
- `reference_filter.keys 不能为空`
- `reference_filter.keys[...] 缺少 source_field/reference_field`
- `filter source alias 不存在: ...`
- `不支持的 filter.type: ...`
- `aggregate source_alias 不存在: ...`
- `aggregate 缺少 output_alias`
- `aggregate.aggregations 不能为空`
- `不支持的 aggregate operator: ...`(类内与模块级各一处,均为类②)
- `match source alias 不存在: ...`
- `无 match 的 write_dataset 仅支持单一基础 alias`
- `dynamic_mappings 需要同时配置 match.sources`
- `dynamic match source alias 不存在: ...`
- `不支持的 value.type: ...`
- `不支持的 function: ...`
- `lookup 缺少 source_alias` / `lookup source_alias 不存在: ...` / `lookup 缺少 value_field` / `lookup.keys 不能为空` / `lookup.keys[...] 缺少 lookup_field` / `lookup.keys[...] 缺少 input`
- `input_plan 未加载到当前 source 数据：...`
- `不支持的 field_write_mode: ...`
- `导出列配置无效: ...`
- `导出列缺少 source_field/source_template`
- `不支持的导出动态维度: ...`
- `月份范围无效: ...` / `导出月份范围无效: ...`
- `无法解析月份偏移量: ...`
- `公式包含不支持的语法: ...` / `公式包含不支持的函数: ...` / `公式包含不支持的标识符: ...`
- `三元表达式缺少冒号: ...`
- `括号未闭合: ...`
- `proc 内存结果不存在或已过期` / `proc 内存结果已过期` / `proc 内存结果格式无效`(这三处是 `KeyError`/`TypeError`,改为 `ProcRuleConfigError`,cause 用原文本)

**类①(用户数据问题)** — 用下列文案:

- `表 '...' 未在上传文件或中间结果中找到` → `ProcUserDataError(summary=f"规则「{self._rule_display_name()}」找不到所需的数据表", cause=f"规则引用的表「{table_name}」既不在上传文件中，也不是前序步骤的结果。", suggestion="请确认相关文件已上传，且文件名与规则要求一致。")`
- `earliest_date 字段不存在: {source_table}.{date_field}` → `ProcUserDataError(summary=f"规则「{self._rule_display_name()}」无法计算日期", cause=f"{self._describe_table(source_table)}中没有列「{date_field}」。", suggestion="请确认该文件包含上述日期列。")`
- `earliest_date 无可用日期: {source_table}.{date_field}` → `ProcUserDataError(summary=f"规则「{self._rule_display_name()}」无法计算日期", cause=f"{self._describe_table(source_table)}的列「{date_field}」中没有有效日期。", suggestion="请检查该列的日期是否填写完整、格式是否规范。")`

**模块级函数中的类①**(这些函数没有 `self`,无法用 `_rule_display_name`/`_describe_table`,因此 summary 用固定文案,把已知的列/值信息放进 cause):

- `无法解析日期值: {value}`(两处) / `无法解析月份结束日期: {value}` / `无法解析月份值: {value}` →
  `ProcUserDataError(summary="数据整理无法解析日期", cause=f"值「{value}」不是有效的日期。", suggestion="请检查相关列的日期格式是否规范。")`
- `月份超出范围: {month}` →
  `ProcUserDataError(summary="数据整理遇到无效月份", cause=f"月份值「{month}」超出有效范围。", suggestion="请检查相关列的月份数据。")`
- `无法解析 decimal 值: {value}` →
  `ProcUserDataError(summary="数据整理无法解析金额", cause=f"值「{value}」不是有效的数字。", suggestion="请检查相关列是否含有非数字字符。")`
- `文件不存在: {file_path}`(`FileNotFoundError`) →
  `ProcUserDataError(summary="数据整理找不到文件", cause=f"文件「{file_path}」不存在。", suggestion="请重新上传该文件。")`
- `不支持的文件格式: {suffix}` →
  `ProcUserDataError(summary="数据整理遇到不支持的文件格式", cause=f"文件格式「{suffix}」不受支持。", suggestion="请上传 Excel 或 CSV 文件。")`

**保持原样,不要改:**

- 所有 `_FastPathNotSupported(...)`(内部控制流,快路径降级,不是错误)。
- `步骤 {step_id}（...）执行失败：{exc}` 这处 `raise ValueError` 包裹的是 `FormulaEvaluationError`。改为:`raise ProcRuleConfigError(summary=f"规则「{self._rule_display_name()}」的步骤执行失败", cause=f"步骤「{step_id}」（{step.get('description') or action}）：{exc}", suggestion="若提示缺少列，请检查上传文件；否则请联系管理员核对规则。") from exc`
- `FormulaEvaluationError` 类本身及 `_build_formula_context_error` 的逻辑不动。

> 提示:执行前先 `grep -n "raise " proc/mcp_server/steps_runtime.py` 列出全部 `raise`,逐一对照上表归类;每个 `raise` 都必须落到"类① / 类② / 保持原样"三者之一。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py qa/runtime_steps_spec.py -v`
Expected: PASS — 新增的 `test_missing_source_column_raises_user_data_error` 通过;`runtime_steps_spec.py` 原有测试全部通过(无回归)。

- [ ] **Step 5: 提交**

```bash
git add finance-mcp/proc/mcp_server/steps_runtime.py finance-mcp/qa/proc_error_messages_spec.py
git commit -m "feat: raise structured errors throughout proc steps runtime"
```

---

## Task 4: proc_rule 与 merge_rule 的报错出口

**Files:**
- Modify: `finance-mcp/proc/mcp_server/proc_rule.py`
- Modify: `finance-mcp/proc/mcp_server/merge_rule.py`
- Test: `finance-mcp/qa/proc_error_messages_spec.py`

**背景:** `proc_rule.py` 有两处顶层 `except`:steps 路径(`except Exception as e:` 后返回 `errors=[str(e)]`、`message=f"steps 规则执行失败: {e}"`)和旧式 `rules` 循环(`msg = f"规则 {rule.get('rule_id')!r} 执行失败: {e}"`)。`merge_rule.py` 有 2 处面向用户的 `raise`。

- [ ] **Step 1: 写失败测试**

在 `finance-mcp/qa/proc_error_messages_spec.py` 末尾追加。被测函数:在 `proc_rule.py` 中新增一个纯函数 `render_proc_failure(exc: BaseException) -> str`,把任意异常翻译成成品三段文本。

```python
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
    # 内部技术细节不直接外泄给用户
    assert "some internal boom" not in detail
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_proc_failure'`。

- [ ] **Step 3a: 实现 `render_proc_failure`**

在 `finance-mcp/proc/mcp_server/proc_rule.py` 顶部的 import 区加入:

```python
from proc.mcp_server.steps_runtime import (
    ProcRuntimeError,
    ProcRuleConfigError,
    ProcUserDataError,
)
```

在该文件模块级(任意顶层位置,建议紧跟 import 之后)新增:

```python
def render_proc_failure(exc: BaseException) -> str:
    """把数据整理执行抛出的异常翻译成面向用户的三段式成品文本。"""
    if isinstance(exc, ProcRuntimeError):
        return exc.format_detail()
    if isinstance(exc, KeyError):
        key = exc.args[0] if exc.args else str(exc)
        return ProcUserDataError(
            summary="数据整理找不到所需的列",
            cause=f"执行过程中找不到列「{key}」。",
            suggestion="请确认上传的文件包含该列，并检查列名是否一致。",
        ).format_detail()
    return ProcRuleConfigError(
        summary="系统执行出错",
        cause="数据整理过程中发生未预期的错误。",
        suggestion="请联系管理员排查。",
    ).format_detail()
```

- [ ] **Step 3b: 在 steps 路径顶层 catch 使用它**

`proc_rule.py` steps 路径的 `except Exception as e:` 块(当前约 565-576 行),把返回 dict 改为:

```python
        except Exception as e:
            logger.error(f"[proc_rule] steps 规则执行失败: {e}", exc_info=True)
            detail = render_proc_failure(e)
            return {
                "success": False,
                "rule_code": rule_code,
                "generated_files": [],
                "memory_outputs": [],
                "generated_count": 0,
                "errors": [detail],
                "message": detail,
                "merged_files": [],
            }
```

- [ ] **Step 3c: 在旧式 `rules` 循环 catch 使用它**

`proc_rule.py` 旧式 `rules` 循环的 `except Exception as e:` 块(当前约 726-729 行),把 `msg` 的构造改为:

```python
        except Exception as e:
            detail = render_proc_failure(e)
            logger.error(
                f"[proc_rule] 规则 {rule.get('rule_id')!r} 执行失败: {e}", exc_info=True
            )
            errors.append(detail)
```

(注意:原代码里 `errors.append(msg)`,现改为 append `detail`;删除原 `msg = ...` 行。)

- [ ] **Step 3d: 改造 merge_rule.py 的 raise**

`finance-mcp/proc/mcp_server/merge_rule.py` 顶部 import 区加入:

```python
from proc.mcp_server.steps_runtime import ProcUserDataError
```

把 `raise FileNotFoundError(f"文件不存在: {file_path}")` 改为:

```python
        raise ProcUserDataError(
            summary="数据整理找不到文件",
            cause=f"文件「{file_path}」不存在。",
            suggestion="请重新上传该文件。",
        )
```

把 `raise ValueError(f"不支持的文件格式: {ext}")` 改为:

```python
        raise ProcUserDataError(
            summary="数据整理遇到不支持的文件格式",
            cause=f"文件格式「{ext}」不受支持。",
            suggestion="请上传 Excel 或 CSV 文件。",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd finance-mcp && PYTHONPATH=. /Users/kevin/workspace/financial-ai/.venv/bin/pytest qa/proc_error_messages_spec.py qa/runtime_steps_spec.py -v`
Expected: PASS(全部测试通过,无回归)。

- [ ] **Step 5: 提交**

```bash
git add finance-mcp/proc/mcp_server/proc_rule.py finance-mcp/proc/mcp_server/merge_rule.py finance-mcp/qa/proc_error_messages_spec.py
git commit -m "feat: render structured proc failure messages at proc_rule funnel"
```

---

## Self-Review

- **Spec 覆盖:**
  - 「领域异常 `ProcRuntimeError`/`ProcUserDataError`/`ProcRuleConfigError` + summary/cause/suggestion」→ Task 1。
  - 「上下文 helper `_rule_display_name`/`_describe_table`/`_require_columns`」→ Task 2。
  - 「列访问守卫落点」→ Task 3 Step 3a(`_apply_aggregations`);其余已有 `if not in columns` 检查的访问点(earliest_date 等)在 Task 3 Step 3b 归类时一并改为 `ProcUserDataError`。
  - 「~60 处 raise 归类改造 + `_FastPathNotSupported` 不动 + 公式错误处理」→ Task 3 Step 3b。
  - 「proc_rule 顶层兜底:结构化渲染 / 裸 KeyError 翻译 / 未知异常归类②」→ Task 4(`render_proc_failure` + 两处 catch)。
  - 「merge_rule 面向用户的 raise 归类」→ Task 4 Step 3d。
  - 「测试三场景」→ Task 2(缺列单测)、Task 3(缺列集成测试)、Task 4(裸 KeyError 兜底测试);类②由 Task 3 的归类改造覆盖,`render_proc_failure` 的未知异常测试覆盖兜底。
  - 「仅改 proc/,不动 agent/前端」→ 计划只涉及 `proc/` 三个文件,符合。
- **占位符扫描:** Task 3 Step 1 中的 `...` 是明确指向"原测试中执行规则那一行"的复制指令,并给了 `StepsProcRuntime(...).execute()` 等具体形态,非空泛占位。其余步骤均含完整代码。
- **类型一致性:** 异常构造一律用关键字参数 `summary=/cause=/suggestion=`;`format_detail()` 在 Task 1 定义、Task 4 引用,签名一致;`render_proc_failure(exc)` 在 Task 4 定义与引用一致。
