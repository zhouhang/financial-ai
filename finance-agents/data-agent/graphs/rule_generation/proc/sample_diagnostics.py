"""Deterministic diagnostics for proc sample trial results."""

from __future__ import annotations

import ast
import re
from typing import Any


class UnsupportedDiagnosticExpression(ValueError):
    """Raised when a diagnostic expression cannot be evaluated deterministically."""


def diagnose_proc_sample(
    *,
    rule_json: dict[str, Any],
    sample_result: dict[str, Any],
    sample_inputs: list[dict[str, Any]],
    expected_target: str = "",
    expected_targets: list[str] | None = None,
    assert_result: dict[str, Any] | None = None,
    rule_text: str = "",
) -> dict[str, Any]:
    """Diagnose why a proc sample run did not produce usable output.

    The diagnosis is intentionally deterministic. It observes the generated DSL,
    source sample rows, and runtime output, then produces evidence for whether
    an LLM repair attempt is useful.
    """
    targets = _expected_targets(
        sample_result=sample_result,
        expected_target=expected_target,
        expected_targets=expected_targets,
    )
    diagnostics: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not sample_result.get("success"):
        diagnostics.append({
            "reason": "sample_execution_error",
            "message": str(sample_result.get("error") or sample_result.get("message") or "样例执行失败"),
            "repair_recommended": True,
            "terminal": False,
            "errors": _result_messages(sample_result),
        })

    for target in targets:
        output_sample = _find_output_sample(sample_result, target)
        if not output_sample:
            diagnostics.append({
                "reason": "target_missing",
                "target_table": target,
                "message": f"样例执行没有生成目标表 {target}。",
                "repair_recommended": True,
                "terminal": False,
            })
            continue

        rows = [row for row in list(output_sample.get("rows") or []) if isinstance(row, dict)]
        row_count = _as_int(output_sample.get("row_count"), default=len(rows))
        if row_count <= 0:
            diagnostics.extend(
                _diagnose_empty_target(
                    rule_json=rule_json,
                    sample_inputs=sample_inputs,
                    target_table=target,
                    rule_text=rule_text,
                )
            )
        elif not rows:
            diagnostics.append({
                "reason": "target_preview_empty",
                "target_table": target,
                "row_count": row_count,
                "message": f"目标表 {target} 已生成 {row_count} 行，但没有可展示预览行。",
                "repair_recommended": False,
                "terminal": True,
            })

    if assert_result and not assert_result.get("success"):
        diagnostics.extend(
            _diagnose_assertion_failure(
                rule_json=rule_json,
                sample_result=sample_result,
                assert_result=assert_result,
                targets=targets,
            )
        )

    if not diagnostics and not sample_result.get("ready_for_confirm", True):
        diagnostics.append({
            "reason": "not_ready_without_specific_diagnosis",
            "message": str(sample_result.get("message") or "样例执行完成，但输出还不能确认。"),
            "repair_recommended": True,
            "terminal": False,
            "warnings": [str(item) for item in list(sample_result.get("warnings") or []) if str(item).strip()],
        })

    repair_recommended = any(bool(item.get("repair_recommended")) for item in diagnostics)
    terminal = bool(diagnostics) and not repair_recommended
    errors = _diagnostic_errors(diagnostics)
    message = _diagnosis_message(
        diagnostics=diagnostics,
        repair_recommended=repair_recommended,
        terminal=terminal,
    )

    return {
        "success": not terminal,
        "status": "repair_recommended" if repair_recommended else "terminal" if terminal else "passed",
        "repair_recommended": repair_recommended,
        "terminal": terminal,
        "message": message,
        "summary": {
            "diagnostic_count": len(diagnostics),
            "repair_recommended": repair_recommended,
            "terminal": terminal,
        },
        "diagnostics": diagnostics,
        "errors": errors,
        "warnings": warnings,
    }


def _diagnose_empty_target(
    *,
    rule_json: dict[str, Any],
    sample_inputs: list[dict[str, Any]],
    target_table: str,
    rule_text: str,
) -> list[dict[str, Any]]:
    steps = [
        step
        for step in list(rule_json.get("steps") or [])
        if isinstance(step, dict)
        and str(step.get("action") or "").strip() == "write_dataset"
        and str(step.get("target_table") or "").strip() == target_table
    ]
    if not steps:
        return [{
            "reason": "target_write_step_missing",
            "target_table": target_table,
            "message": f"目标表 {target_table} 没有对应 write_dataset step。",
            "repair_recommended": True,
            "terminal": False,
        }]

    diagnostics: list[dict[str, Any]] = []
    for step in steps:
        step_id = str(step.get("step_id") or "").strip()
        rows_by_alias = _rows_by_alias(step, sample_inputs)
        base_alias = _base_alias(step)
        base_rows = rows_by_alias.get(base_alias) or []
        row_write_mode = str(step.get("row_write_mode") or "").strip() or "upsert"

        if not base_rows:
            diagnostics.append({
                "reason": "source_sample_empty",
                "step_id": step_id,
                "target_table": target_table,
                "base_alias": base_alias,
                "message": f"{step_id or target_table} 的基础源样例行数为 0，无法生成输出样例。",
                "repair_recommended": False,
                "terminal": True,
            })
            continue

        if row_write_mode == "update_only":
            diagnostics.append({
                "reason": "update_only_on_empty_target",
                "step_id": step_id,
                "target_table": target_table,
                "row_write_mode": row_write_mode,
                "base_alias": base_alias,
                "base_row_count": len(base_rows),
                "message": (
                    f"{step_id or target_table} 使用 update_only，但样例目标表初始为空，"
                    "不会新增输出行。"
                ),
                "repair_recommended": True,
                "terminal": False,
            })
            continue

        filter_def = step.get("filter") if isinstance(step.get("filter"), dict) else None
        if filter_def:
            filter_diag = _diagnose_filter(
                step=step,
                rows_by_alias=rows_by_alias,
                base_alias=base_alias,
                rule_text=rule_text,
            )
            diagnostics.append(filter_diag)
            continue

        diagnostics.append({
            "reason": "target_empty_after_non_empty_source",
            "step_id": step_id,
            "target_table": target_table,
            "base_alias": base_alias,
            "base_row_count": len(base_rows),
            "mapping_count": len([item for item in list(step.get("mappings") or []) if isinstance(item, dict)]),
            "message": (
                f"{step_id or target_table} 有 {len(base_rows)} 行基础源样例，"
                "但目标表输出 0 行。"
            ),
            "repair_recommended": True,
            "terminal": False,
        })

    if diagnostics and all(item.get("terminal") for item in diagnostics):
        return diagnostics
    return diagnostics or [{
        "reason": "target_empty_unknown",
        "target_table": target_table,
        "message": f"目标表 {target_table} 输出 0 行，未能定位到更具体原因。",
        "repair_recommended": True,
        "terminal": False,
    }]


def _diagnose_filter(
    *,
    step: dict[str, Any],
    rows_by_alias: dict[str, list[dict[str, Any]]],
    base_alias: str,
    rule_text: str,
) -> dict[str, Any]:
    step_id = str(step.get("step_id") or "").strip()
    filter_def = step.get("filter") or {}
    expr = str(filter_def.get("expr") or "").strip()
    bindings = filter_def.get("bindings") if isinstance(filter_def.get("bindings"), dict) else {}
    base_rows = rows_by_alias.get(base_alias) or []

    matched = 0
    eval_errors: list[str] = []
    for row in base_rows:
        try:
            env = {
                name: _evaluate_value_node(
                    spec,
                    row_contexts={base_alias: row},
                    rows_by_alias=rows_by_alias,
                )
                for name, spec in bindings.items()
            }
            if bool(_evaluate_formula(expr, env)):
                matched += 1
        except Exception as exc:  # noqa: BLE001
            eval_errors.append(str(exc))

    if eval_errors and len(eval_errors) == len(base_rows):
        return {
            "reason": "filter_not_diagnosable",
            "step_id": step_id,
            "expr": expr,
            "base_alias": base_alias,
            "base_row_count": len(base_rows),
            "message": f"{step_id or 'write_dataset'} 的过滤公式无法用样例确定性诊断。",
            "repair_recommended": True,
            "terminal": False,
            "errors": list(dict.fromkeys(eval_errors))[:3],
        }

    if matched > 0:
        return {
            "reason": "target_empty_after_filter_matched_rows",
            "step_id": step_id,
            "expr": expr,
            "base_alias": base_alias,
            "base_row_count": len(base_rows),
            "filter_matched_count": matched,
            "message": (
                f"{step_id or 'write_dataset'} 的过滤条件命中 {matched} 行样例，"
                "但目标表仍输出 0 行。"
            ),
            "repair_recommended": True,
            "terminal": False,
        }

    comparison_diag = _diagnose_zero_match_comparisons(
        expr=expr,
        bindings=bindings,
        rows_by_alias=rows_by_alias,
        base_alias=base_alias,
        rule_text=rule_text,
    )
    if comparison_diag.get("repair_recommended"):
        return {
            "reason": "filter_zero_rows_repairable",
            "step_id": step_id,
            "expr": expr,
            "base_alias": base_alias,
            "base_row_count": len(base_rows),
            "filter_matched_count": 0,
            "message": "过滤条件将样例行全部排除，且诊断发现可能是 JSON 表达方式问题。",
            "repair_recommended": True,
            "terminal": False,
            "evidence": comparison_diag.get("evidence") or [],
        }

    return {
        "reason": "filter_zero_rows_no_matching_sample",
        "step_id": step_id,
        "expr": expr,
        "base_alias": base_alias,
        "base_row_count": len(base_rows),
        "filter_matched_count": 0,
        "message": "过滤条件将样例行全部排除，样例数据未证明 JSON 写法有误。",
        "repair_recommended": False,
        "terminal": True,
        "evidence": comparison_diag.get("evidence") or [],
    }


def _diagnose_zero_match_comparisons(
    *,
    expr: str,
    bindings: dict[str, Any],
    rows_by_alias: dict[str, list[dict[str, Any]]],
    base_alias: str,
    rule_text: str,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    repair_recommended = False
    comparisons = _extract_comparisons(expr)
    equality_comparisons = 0
    resolved_pairs = 0
    for comparison in comparisons:
        if comparison.get("operator") != "==":
            continue
        equality_comparisons += 1
        pair = _resolve_source_constant_pair(comparison, bindings)
        if not pair:
            continue
        resolved_pairs += 1
        source_token, constant_value = pair
        source_info = _source_binding_info(bindings.get(source_token))
        if not source_info:
            continue
        alias = source_info["alias"] or base_alias
        field = source_info["field"]
        source_rows = rows_by_alias.get(alias) or []
        source_values = [row.get(field) for row in source_rows if isinstance(row, dict)]
        loose_same_field = any(_loose_equal(value, constant_value) for value in source_values)
        strict_same_field = any(value == constant_value for value in source_values)
        if strict_same_field:
            continue
        if loose_same_field and not strict_same_field:
            repair_recommended = True
            evidence.append({
                "reason": "filter_value_type_or_literal_mismatch",
                "alias": alias,
                "field": field,
                "constant_value": constant_value,
                "sample_values": _preview_values(source_values),
                "message": "过滤值在同一字段样例中存在，但严格比较未命中，可能是常量类型或字面量写法不兼容。",
            })
            continue

        other_field_hits = _find_value_in_sample_fields(
            constant_value,
            rows_by_alias=rows_by_alias,
            exclude=(alias, field),
        )
        if other_field_hits:
            repair_recommended = True
            evidence.append({
                "reason": "filter_value_found_in_other_fields",
                "alias": alias,
                "field": field,
                "constant_value": constant_value,
                "other_field_hits": other_field_hits[:5],
                "message": "过滤值没有命中当前字段，但出现在其他样例字段中，可能是过滤字段绑定错误。",
            })
            continue

        if constant_value not in {None, ""} and not _rule_text_mentions_value(rule_text, constant_value):
            repair_recommended = True
            evidence.append({
                "reason": "filter_value_not_mentioned_by_user",
                "alias": alias,
                "field": field,
                "constant_value": constant_value,
                "message": "过滤常量未出现在用户描述中，可能是 JSON 幻觉出的过滤条件。",
            })
            continue

        evidence.append({
            "reason": "filter_value_not_found_in_samples",
            "alias": alias,
            "field": field,
            "constant_value": constant_value,
            "sample_values": _preview_values(source_values),
            "message": "过滤常量没有出现在当前样例字段中。",
        })

    if not comparisons:
        repair_recommended = True
        evidence.append({
            "reason": "filter_expression_not_comparable",
            "message": "过滤公式无法拆出可诊断的比较条件。",
        })
    elif equality_comparisons and not resolved_pairs:
        repair_recommended = True
        evidence.append({
            "reason": "filter_comparison_not_resolved",
            "message": "过滤比较条件无法解析为源字段与常量的比较。",
        })
    return {"repair_recommended": repair_recommended, "evidence": evidence}


def _diagnose_assertion_failure(
    *,
    rule_json: dict[str, Any],
    sample_result: dict[str, Any],
    assert_result: dict[str, Any],
    targets: list[str],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for target in targets:
        output_sample = _find_output_sample(sample_result, target)
        rows = [row for row in list((output_sample or {}).get("rows") or []) if isinstance(row, dict)]
        schema_fields = _schema_fields(rule_json, target)
        mapping_fields = _mapping_fields(rule_json, target)
        if rows and not mapping_fields:
            diagnostics.append({
                "reason": "assertion_failed_without_mappings",
                "target_table": target,
                "schema_fields": schema_fields,
                "message": f"目标表 {target} 有输出行，但 write_dataset 没有普通 mappings。",
                "repair_recommended": True,
                "terminal": False,
            })
        elif assert_result.get("errors"):
            diagnostics.append({
                "reason": "assertion_failed",
                "target_table": target,
                "schema_fields": schema_fields,
                "mapping_fields": mapping_fields,
                "message": "输出断言失败，需要根据断言错误修复 JSON 输出结构。",
                "repair_recommended": True,
                "terminal": False,
                "errors": assert_result.get("errors") or [],
            })
    return diagnostics


def _expected_targets(
    *,
    sample_result: dict[str, Any],
    expected_target: str,
    expected_targets: list[str] | None,
) -> list[str]:
    targets = [str(item).strip() for item in list(expected_targets or []) if str(item).strip()]
    if not targets and expected_target:
        targets = [expected_target]
    if not targets:
        for item in list(sample_result.get("output_samples") or []):
            if not isinstance(item, dict):
                continue
            target = str(item.get("target_table") or "").strip()
            if target and target not in targets:
                targets.append(target)
    return targets


def _find_output_sample(sample_result: dict[str, Any], target_table: str) -> dict[str, Any]:
    for item in list(sample_result.get("output_samples") or []):
        if isinstance(item, dict) and str(item.get("target_table") or "").strip() == target_table:
            return item
    return {}


def _rows_by_alias(step: dict[str, Any], sample_inputs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows_by_table = {_table_name(source): _sample_rows(source) for source in sample_inputs}
    result: dict[str, list[dict[str, Any]]] = {}
    for source in list(step.get("sources") or []):
        if not isinstance(source, dict):
            continue
        table = str(source.get("table") or "").strip()
        alias = str(source.get("alias") or table).strip()
        if alias:
            result[alias] = rows_by_table.get(table) or []
    return result


def _table_name(source: dict[str, Any]) -> str:
    return str(
        source.get("table_name")
        or source.get("resource_key")
        or source.get("dataset_code")
        or source.get("dataset_name")
        or source.get("source_id")
        or source.get("id")
        or ""
    ).strip()


def _sample_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = source.get("sample_rows")
    if not isinstance(rows, list):
        rows = source.get("rows")
    return [row for row in list(rows or []) if isinstance(row, dict)]


def _base_alias(step: dict[str, Any]) -> str:
    sources = [source for source in list(step.get("sources") or []) if isinstance(source, dict)]
    if sources:
        first = sources[0]
        return str(first.get("alias") or first.get("table") or "").strip()
    return ""


def _evaluate_value_node(
    node: Any,
    *,
    row_contexts: dict[str, dict[str, Any]],
    rows_by_alias: dict[str, list[dict[str, Any]]],
) -> Any:
    if not isinstance(node, dict):
        return node
    node_type = str(node.get("type") or "").strip()
    if node_type == "source" or isinstance(node.get("source"), dict):
        source = node.get("source") if isinstance(node.get("source"), dict) else {}
        alias = str(source.get("alias") or "").strip()
        field = str(source.get("field") or "").strip()
        if alias not in row_contexts:
            if len(row_contexts) == 1 and len(rows_by_alias) <= 1:
                # Diagnostic-only tolerance: single-source filters may carry an
                # equivalent alias after compiler normalization.
                return next(iter(row_contexts.values())).get(field)
            raise UnsupportedDiagnosticExpression(f"source alias 不在当前行上下文中: {alias}")
        return row_contexts[alias].get(field)
    if node_type == "formula":
        bindings = node.get("bindings") if isinstance(node.get("bindings"), dict) else {}
        env = {
            name: _evaluate_value_node(
                spec,
                row_contexts=row_contexts,
                rows_by_alias=rows_by_alias,
            )
            for name, spec in bindings.items()
        }
        return _evaluate_formula(str(node.get("expr") or ""), env)
    if node_type == "lookup":
        return _evaluate_lookup(node, row_contexts=row_contexts, rows_by_alias=rows_by_alias)
    if node_type == "function":
        return _evaluate_function_node(node, row_contexts=row_contexts, rows_by_alias=rows_by_alias)
    raise UnsupportedDiagnosticExpression(f"不支持诊断的 value.type: {node_type or '<empty>'}")


def _evaluate_function_node(
    node: dict[str, Any],
    *,
    row_contexts: dict[str, dict[str, Any]],
    rows_by_alias: dict[str, list[dict[str, Any]]],
) -> Any:
    function_name = str(node.get("function") or node.get("name") or "").strip()
    args = node.get("args") if isinstance(node.get("args"), dict) else {}
    if function_name == "to_decimal":
        return _to_decimal(
            _evaluate_value_node(
                args.get("value") or args.get("text"),
                row_contexts=row_contexts,
                rows_by_alias=rows_by_alias,
            )
        )
    if function_name == "coalesce":
        values = args.get("values") if isinstance(args.get("values"), list) else list(args.values())
        return _coalesce(*[
            _evaluate_value_node(value, row_contexts=row_contexts, rows_by_alias=rows_by_alias)
            for value in values
        ])
    if function_name == "is_null":
        return _is_null(
            _evaluate_value_node(
                args.get("value") or args.get("text"),
                row_contexts=row_contexts,
                rows_by_alias=rows_by_alias,
            )
        )
    raise UnsupportedDiagnosticExpression(f"不支持诊断的 function: {function_name or '<empty>'}")


def _evaluate_lookup(
    node: dict[str, Any],
    *,
    row_contexts: dict[str, dict[str, Any]],
    rows_by_alias: dict[str, list[dict[str, Any]]],
) -> Any:
    source_alias = str(node.get("source_alias") or "").strip()
    value_field = str(node.get("value_field") or "").strip()
    lookup_rows = rows_by_alias.get(source_alias) or []
    if not source_alias or not value_field:
        raise UnsupportedDiagnosticExpression("lookup 缺少 source_alias/value_field")
    expected_key_values: list[tuple[str, Any]] = []
    for key in list(node.get("keys") or []):
        if not isinstance(key, dict):
            continue
        lookup_field = str(key.get("lookup_field") or "").strip()
        input_value = _evaluate_value_node(
            key.get("input"),
            row_contexts=row_contexts,
            rows_by_alias=rows_by_alias,
        )
        expected_key_values.append((lookup_field, input_value))
    for row in lookup_rows:
        if all(_loose_equal(row.get(field), expected) for field, expected in expected_key_values):
            return row.get(value_field)
    return None


def _evaluate_formula(expr: str, env: dict[str, Any]) -> Any:
    translated = re.sub(r"\{([^{}]+)\}", lambda match: f"__vars__[{match.group(1)!r}]", expr.strip())
    tree = ast.parse(translated, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise UnsupportedDiagnosticExpression(f"公式包含不支持的语法: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in {"__vars__", "coalesce", "is_null", "to_decimal"}:
            raise UnsupportedDiagnosticExpression(f"公式包含不支持的标识符: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
                function_name = node.func.id if isinstance(node.func, ast.Name) else type(node.func).__name__
                raise UnsupportedDiagnosticExpression(f"公式包含不支持的函数: {function_name}")
    return eval(compile(tree, "<diagnose_formula>", "eval"), {"__builtins__": {}}, {  # noqa: S307
        "__vars__": env,
        **_SAFE_FUNCTIONS,
    })


_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Subscript,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _is_null(value: Any) -> bool:
    return value is None or value == ""


def _to_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(str(value).replace(",", ""))


_SAFE_FUNCTIONS = {
    "coalesce": _coalesce,
    "is_null": _is_null,
    "to_decimal": _to_decimal,
}


def _extract_comparisons(expr: str) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    operand = (
        r"(?:to_decimal\(\s*\{[^{}]+\}\s*\)|"
        r"\{[^{}]+\}|"
        r"'[^']*'|"
        r"\"[^\"]*\"|"
        r"[-+]?\d+(?:\.\d+)?)"
    )
    pattern = re.compile(
        rf"(?P<left>{operand})\s*"
        r"(?P<operator>==|!=|>=|<=|>|<)\s*"
        rf"(?P<right>{operand})"
    )
    for match in pattern.finditer(expr or ""):
        comparisons.append({
            "left": _parse_comparison_operand(match.group("left")),
            "operator": match.group("operator"),
            "right": _parse_comparison_operand(match.group("right")),
        })
    return comparisons


def _parse_comparison_operand(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    function_match = re.fullmatch(r"to_decimal\(\s*(\{[^{}]+\})\s*\)", text)
    if function_match:
        return _parse_comparison_operand(function_match.group(1))
    if text.startswith("{") and text.endswith("}"):
        return {"kind": "token", "token": text[1:-1]}
    try:
        return {"kind": "constant", "value": ast.literal_eval(text)}
    except Exception:  # noqa: BLE001
        return {"kind": "constant", "value": text}


def _resolve_source_constant_pair(
    comparison: dict[str, Any],
    bindings: dict[str, Any],
) -> tuple[str, Any] | None:
    left = comparison.get("left") if isinstance(comparison.get("left"), dict) else {}
    right = comparison.get("right") if isinstance(comparison.get("right"), dict) else {}
    left_token = str(left.get("token") or "").strip() if left.get("kind") == "token" else ""
    right_token = str(right.get("token") or "").strip() if right.get("kind") == "token" else ""

    left_is_source = bool(left_token and _source_binding_info(bindings.get(left_token)))
    right_is_source = bool(right_token and _source_binding_info(bindings.get(right_token)))
    if left_is_source:
        constant = _operand_constant(right, bindings)
        return (left_token, constant) if constant is not _NO_VALUE else None
    if right_is_source:
        constant = _operand_constant(left, bindings)
        return (right_token, constant) if constant is not _NO_VALUE else None
    return None


_NO_VALUE = object()


def _operand_constant(operand: dict[str, Any], bindings: dict[str, Any]) -> Any:
    if operand.get("kind") == "constant":
        return operand.get("value")
    token = str(operand.get("token") or "").strip()
    if not token:
        return _NO_VALUE
    return _constant_binding_value(bindings.get(token))


def _source_binding_info(node: Any) -> dict[str, str] | None:
    if not isinstance(node, dict):
        return None
    if str(node.get("type") or "").strip() == "function":
        args = node.get("args") if isinstance(node.get("args"), dict) else {}
        return _source_binding_info(args.get("value") or args.get("text"))
    if str(node.get("type") or "").strip() != "source" and not isinstance(node.get("source"), dict):
        return None
    source = node.get("source") if isinstance(node.get("source"), dict) else {}
    alias = str(source.get("alias") or "").strip()
    field = str(source.get("field") or "").strip()
    if not field:
        return None
    return {"alias": alias, "field": field}


def _constant_binding_value(node: Any) -> Any:
    if not isinstance(node, dict) or str(node.get("type") or "").strip() != "formula":
        return _NO_VALUE
    bindings = node.get("bindings")
    expr = str(node.get("expr") or "").strip()
    if bindings:
        return _NO_VALUE
    try:
        return _evaluate_formula(expr, {})
    except Exception:  # noqa: BLE001
        return _NO_VALUE


def _find_value_in_sample_fields(
    value: Any,
    *,
    rows_by_alias: dict[str, list[dict[str, Any]]],
    exclude: tuple[str, str],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for alias, rows in rows_by_alias.items():
        values_by_field: dict[str, list[Any]] = {}
        for row in rows:
            for field, field_value in row.items():
                if (alias, str(field)) == exclude:
                    continue
                if _loose_equal(field_value, value):
                    values_by_field.setdefault(str(field), []).append(field_value)
        for field, values in values_by_field.items():
            hits.append({
                "alias": alias,
                "field": field,
                "sample_values": _preview_values(values),
            })
    return hits


def _schema_fields(rule_json: dict[str, Any], target_table: str) -> list[str]:
    fields: list[str] = []
    for step in list(rule_json.get("steps") or []):
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip() != "create_schema":
            continue
        if str(step.get("target_table") or "").strip() != target_table:
            continue
        schema = step.get("schema") if isinstance(step.get("schema"), dict) else {}
        for column in list(schema.get("columns") or []):
            if isinstance(column, dict) and str(column.get("name") or "").strip():
                fields.append(str(column.get("name")).strip())
    return list(dict.fromkeys(fields))


def _mapping_fields(rule_json: dict[str, Any], target_table: str) -> list[str]:
    fields: list[str] = []
    for step in list(rule_json.get("steps") or []):
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip() != "write_dataset":
            continue
        if str(step.get("target_table") or "").strip() != target_table:
            continue
        for mapping in list(step.get("mappings") or []):
            if isinstance(mapping, dict) and str(mapping.get("target_field") or "").strip():
                fields.append(str(mapping.get("target_field")).strip())
    return list(dict.fromkeys(fields))


def _result_messages(result: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in list(result.get("errors") or []):
        if isinstance(item, dict):
            messages.append(item)
        elif str(item).strip():
            messages.append({"message": str(item).strip()})
    for key in ("error", "message", "summary"):
        text = str(result.get(key) or "").strip()
        if text:
            messages.append({"message": text})
    return messages


def _diagnostic_errors(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for item in diagnostics:
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        nested_errors = [
            str(error).strip()
            for error in list(item.get("errors") or [])
            if str(error).strip()
        ][:2]
        detail = f"：{'；'.join(nested_errors)}" if nested_errors else ""
        errors.append({
            "message": f"{message}{detail}",
            "reason": item.get("reason"),
            "repair_recommended": bool(item.get("repair_recommended")),
            "terminal": bool(item.get("terminal")),
        })
    return errors


def _diagnosis_message(
    *,
    diagnostics: list[dict[str, Any]],
    repair_recommended: bool,
    terminal: bool,
) -> str:
    if not diagnostics:
        return "样例诊断未发现问题。"
    if repair_recommended:
        return "样例诊断发现可修复问题，准备修复规则 JSON。"
    if terminal:
        return "样例诊断认为当前样例数据无法产出结果，已停止自动修复。"
    return "样例诊断完成。"


def _rule_text_mentions_value(rule_text: str, value: Any) -> bool:
    text = _normalize_for_compare(rule_text)
    value_text = _normalize_for_compare(value)
    return bool(value_text and value_text in text)


def _loose_equal(left: Any, right: Any) -> bool:
    return _normalize_for_compare(left) == _normalize_for_compare(right)


def _normalize_for_compare(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and re.fullmatch(r"[-+]?\d+\.0", text):
        text = text[:-2]
    return text.replace(",", "")


def _preview_values(values: list[Any]) -> list[Any]:
    preview: list[Any] = []
    for value in values:
        if value not in preview:
            preview.append(value)
        if len(preview) >= 5:
            break
    return preview


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
