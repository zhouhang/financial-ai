"""Deterministic linting for generated proc steps DSL."""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from typing import Any


VALID_ACTIONS = {"create_schema", "write_dataset"}
VALID_ROW_WRITE_MODES = {"upsert", "insert_if_missing", "update_only"}
VALID_VALUE_TYPES = {"source", "formula", "template_source", "function", "context", "lookup"}
VALID_AGGREGATE_OPERATORS = {"sum", "min"}
SUPPORTED_FUNCTION_NODES = {
    "current_date",
    "add_months",
    "month_of",
    "fraction_numerator",
    "earliest_date",
    "to_decimal",
}
SUPPORTED_FORMULA_CALLS = {"coalesce", "is_null"}
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


def lint_proc_rule(
    rule: dict[str, Any],
    *,
    side: str,
    target_table: str,
    target_tables: list[str] | None = None,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Lint a generated proc rule against the selected side context."""
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    expected_targets = {
        str(item).strip()
        for item in list(target_tables or [])
        if str(item).strip()
    }
    if not expected_targets and target_table:
        expected_targets = {target_table}
    allowed_tables = {_table_name(source) for source in sources if _table_name(source)}
    fields_by_table = {
        _table_name(source): _source_fields(source)
        for source in sources
        if _table_name(source)
    }

    if not isinstance(rule, dict):
        return _result(False, [{"message": "proc_rule_json 必须是对象"}], warnings)
    steps = rule.get("steps")
    if not isinstance(steps, list) or not steps:
        return _result(False, [{"message": "proc_rule_json.steps 必须是非空数组"}], warnings)

    step_ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    generated_targets: set[str] = set()

    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict):
            errors.append({"step_index": index, "message": "step 必须是对象"})
            continue
        step_id = str(raw_step.get("step_id") or "").strip()
        if not step_id:
            errors.append({"step_index": index, "message": "step 缺少 step_id"})
        elif step_id in step_ids:
            errors.append({"step_id": step_id, "message": "step_id 重复"})
        else:
            step_ids.add(step_id)

        action = str(raw_step.get("action") or "").strip()
        if action not in VALID_ACTIONS:
            errors.append({"step_id": step_id, "message": f"不支持的 action: {action}"})

        step_target = str(raw_step.get("target_table") or "").strip()
        if expected_targets and step_target not in expected_targets:
            target_label = "、".join(sorted(expected_targets))
            scope_label = f"当前 {side} 侧" if side else "当前规则"
            errors.append({
                "step_id": step_id,
                "message": f"{scope_label}只能输出 {target_label}，不能输出 {step_target or '<empty>'}",
            })
        if step_target:
            generated_targets.add(step_target)

        dependencies[step_id or f"<step_{index}>"] = [
            str(item).strip()
            for item in list(raw_step.get("depends_on") or [])
            if str(item).strip()
        ]

        if action == "create_schema":
            _lint_schema_step(raw_step, step_id, errors)
        elif action == "write_dataset":
            _lint_write_step(
                raw_step,
                step_id,
                errors,
                warnings,
                allowed_tables=allowed_tables,
                fields_by_table=fields_by_table,
            )

    for step_id, deps in dependencies.items():
        for dep in deps:
            if dep not in step_ids:
                errors.append({"step_id": step_id, "message": f"depends_on 引用了不存在的 step: {dep}"})
    _lint_dependency_cycles(dependencies, errors)

    missing_targets = expected_targets - generated_targets
    if missing_targets:
        errors.append({"message": f"规则未生成目标表 {'、'.join(sorted(missing_targets))}"})

    return _result(not errors, errors, warnings)


def _lint_schema_step(step: dict[str, Any], step_id: str, errors: list[dict[str, Any]]) -> None:
    schema = step.get("schema")
    if not isinstance(schema, dict):
        errors.append({"step_id": step_id, "message": "create_schema 缺少 schema 对象"})
        return
    columns = schema.get("columns")
    if not isinstance(columns, list) or not columns:
        errors.append({"step_id": step_id, "message": "create_schema.schema.columns 必须是非空数组"})
        return
    names: set[str] = set()
    for column in columns:
        if not isinstance(column, dict):
            errors.append({"step_id": step_id, "message": "schema.columns 每一项必须是对象"})
            continue
        name = str(column.get("name") or "").strip()
        if not name:
            errors.append({"step_id": step_id, "message": "schema column 缺少 name"})
        elif name in names:
            errors.append({"step_id": step_id, "message": f"schema column 重复: {name}"})
        names.add(name)


def _lint_write_step(
    step: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    warnings: list[str],
    *,
    allowed_tables: set[str],
    fields_by_table: dict[str, set[str]],
) -> None:
    row_write_mode = str(step.get("row_write_mode") or "").strip() or "upsert"
    if row_write_mode not in VALID_ROW_WRITE_MODES:
        errors.append({"step_id": step_id, "message": f"不支持的 row_write_mode: {row_write_mode}"})

    sources = [source for source in list(step.get("sources") or []) if isinstance(source, dict)]
    if not sources:
        errors.append({"step_id": step_id, "message": "write_dataset 缺少 sources"})
        return

    alias_to_table: dict[str, str] = {}
    for source in sources:
        table_name = str(source.get("table") or "").strip()
        alias = str(source.get("alias") or table_name).strip()
        if not table_name:
            errors.append({"step_id": step_id, "message": "sources[].table 不能为空"})
            continue
        if allowed_tables and table_name not in allowed_tables:
            errors.append({"step_id": step_id, "message": f"source table 不属于当前侧数据集: {table_name}"})
        if not alias:
            errors.append({"step_id": step_id, "message": f"source {table_name} 缺少 alias"})
            continue
        alias_to_table[alias] = table_name

    effective_fields_by_table = dict(fields_by_table)
    _lint_reference_filter(
        step,
        step_id,
        errors,
        alias_to_table=alias_to_table,
        fields_by_table=effective_fields_by_table,
    )
    _lint_aggregates(
        step,
        step_id,
        errors,
        alias_to_table=alias_to_table,
        fields_by_table=effective_fields_by_table,
    )
    _lint_match_sources(
        step,
        step_id,
        errors,
        alias_to_table=alias_to_table,
        fields_by_table=effective_fields_by_table,
    )

    mappings = [item for item in list(step.get("mappings") or []) if isinstance(item, dict)]
    dynamic_mappings = step.get("dynamic_mappings")
    if not mappings and not dynamic_mappings:
        errors.append({"step_id": step_id, "message": "write_dataset 缺少 mappings"})
    if dynamic_mappings is not None:
        _lint_dynamic_mappings(
            dynamic_mappings,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=effective_fields_by_table,
            has_match_sources=bool(((step.get("match") or {}).get("sources") or [])),
        )
    _lint_base_alias_compatibility(
        step,
        step_id,
        errors,
        sources=sources,
        mappings=mappings,
    )
    for mapping in mappings:
        if not str(mapping.get("target_field") or "").strip() and not mapping.get("target_field_template"):
            errors.append({"step_id": step_id, "message": "mapping 缺少 target_field 或 target_field_template"})
        value = mapping.get("value")
        if not isinstance(value, dict):
            errors.append({"step_id": step_id, "message": "mapping.value 必须是对象"})
            continue
        _lint_value_node(
            value,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=effective_fields_by_table,
            context_label="mapping.value",
        )

    filter_def = step.get("filter")
    if filter_def is not None:
        if not isinstance(filter_def, dict):
            errors.append({"step_id": step_id, "message": "step.filter 必须是对象"})
        else:
            _lint_value_node(
                filter_def,
                step_id,
                errors,
                alias_to_table=alias_to_table,
                fields_by_table=effective_fields_by_table,
                context_label="step.filter",
            )

    if not mappings:
        warnings.append(f"{step_id} 没有普通 mappings，可能依赖 dynamic_mappings")


def _lint_base_alias_compatibility(
    step: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    sources: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> None:
    match = step.get("match") if isinstance(step.get("match"), dict) else {}
    if match.get("keys") and not match.get("sources"):
        errors.append({
            "step_id": step_id,
            "message": (
                "当前 steps DSL 不支持 match.keys；多源关联取值请保留一个基础 alias，"
                "并使用 lookup 从另一张表取数，或改为 match.sources 格式。"
            ),
            "reason": "match_keys_not_supported",
        })
    match_sources = list(match.get("sources") or [])
    if match_sources:
        return
    aliases = _infer_base_aliases_for_lint(step, sources=sources, mappings=mappings)
    if len(aliases) != 1:
        errors.append({
            "step_id": step_id,
            "message": (
                "无 match 的 write_dataset 仅支持单一基础 alias；"
                "多源关联请生成 match，或使用 lookup 将非基础表作为查找表。"
            ),
            "reason": "write_dataset_without_match_requires_single_base_alias",
            "aliases": aliases,
        })


def _lint_reference_filter(
    step: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
) -> None:
    reference_filter = step.get("reference_filter")
    if reference_filter is None:
        return
    if not isinstance(reference_filter, dict):
        errors.append({"step_id": step_id, "message": "reference_filter 必须是对象"})
        return
    source_alias = str(reference_filter.get("source_alias") or "").strip()
    if not source_alias:
        errors.append({"step_id": step_id, "message": "reference_filter 缺少 source_alias"})
    elif source_alias not in alias_to_table:
        errors.append({"step_id": step_id, "message": f"reference_filter source_alias 未定义: {source_alias}"})
    if not str(reference_filter.get("reference_table") or "").strip():
        errors.append({"step_id": step_id, "message": "reference_filter 缺少 reference_table"})
    keys = [item for item in list(reference_filter.get("keys") or []) if isinstance(item, dict)]
    if not keys:
        errors.append({"step_id": step_id, "message": "reference_filter.keys 不能为空"})
        return
    source_table = alias_to_table.get(source_alias, "")
    known_fields = fields_by_table.get(source_table) or set()
    for index, key in enumerate(keys):
        source_field = str(key.get("source_field") or "").strip()
        reference_field = str(key.get("reference_field") or "").strip()
        if not source_field or not reference_field:
            errors.append({
                "step_id": step_id,
                "message": f"reference_filter.keys[{index}] 缺少 source_field/reference_field",
            })
            continue
        if known_fields and source_field not in known_fields:
            errors.append({"step_id": step_id, "message": f"reference_filter source_field 不存在: {source_table}.{source_field}"})


def _lint_aggregates(
    step: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
) -> None:
    aggregates = step.get("aggregate")
    if aggregates is None:
        return
    if not isinstance(aggregates, list):
        errors.append({"step_id": step_id, "message": "aggregate 必须是数组"})
        return
    for index, aggregate in enumerate(aggregates):
        if not isinstance(aggregate, dict):
            errors.append({"step_id": step_id, "message": f"aggregate[{index}] 必须是对象"})
            continue
        source_alias = str(aggregate.get("source_alias") or "").strip()
        output_alias = str(aggregate.get("output_alias") or "").strip()
        if not source_alias:
            errors.append({"step_id": step_id, "message": f"aggregate[{index}] 缺少 source_alias"})
            continue
        if source_alias not in alias_to_table:
            errors.append({"step_id": step_id, "message": f"aggregate[{index}] source_alias 未定义: {source_alias}"})
            continue
        if not output_alias:
            errors.append({"step_id": step_id, "message": f"aggregate[{index}] 缺少 output_alias"})
            continue
        source_table = alias_to_table.get(source_alias, "")
        known_fields = fields_by_table.get(source_table) or set()
        aggregate_fields: set[str] = set()
        group_fields = [str(item).strip() for item in list(aggregate.get("group_fields") or []) if str(item).strip()]
        for field in group_fields:
            aggregate_fields.add(field)
            if known_fields and field not in known_fields:
                errors.append({"step_id": step_id, "message": f"aggregate[{index}].group_fields 字段不存在: {source_table}.{field}"})
        aggregations = [item for item in list(aggregate.get("aggregations") or []) if isinstance(item, dict)]
        if not aggregations:
            errors.append({"step_id": step_id, "message": f"aggregate[{index}].aggregations 不能为空"})
        for agg_index, item in enumerate(aggregations):
            field = str(item.get("field") or "").strip()
            operator = str(item.get("operator") or item.get("function") or "").strip()
            alias = str(item.get("alias") or "").strip()
            if not field:
                errors.append({"step_id": step_id, "message": f"aggregate[{index}].aggregations[{agg_index}] 缺少 field"})
            elif known_fields and field not in known_fields:
                errors.append({"step_id": step_id, "message": f"aggregate[{index}].aggregations[{agg_index}] 字段不存在: {source_table}.{field}"})
            if operator not in VALID_AGGREGATE_OPERATORS:
                errors.append({
                    "step_id": step_id,
                    "message": f"aggregate[{index}].aggregations[{agg_index}] 不支持的 operator: {operator or '<empty>'}",
                })
            if not alias:
                errors.append({"step_id": step_id, "message": f"aggregate[{index}].aggregations[{agg_index}] 缺少 alias"})
            else:
                aggregate_fields.add(alias)
        if output_alias:
            pseudo_table = f"__aggregate__:{output_alias}"
            alias_to_table[output_alias] = pseudo_table
            fields_by_table[pseudo_table] = aggregate_fields


def _lint_match_sources(
    step: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
) -> None:
    match = step.get("match")
    if match is None:
        return
    if not isinstance(match, dict):
        errors.append({"step_id": step_id, "message": "match 必须是对象"})
        return
    if match.get("keys") and not match.get("sources"):
        return
    for source_index, source in enumerate([item for item in list(match.get("sources") or []) if isinstance(item, dict)]):
        alias = str(source.get("alias") or "").strip()
        if not alias:
            errors.append({"step_id": step_id, "message": f"match.sources[{source_index}] 缺少 alias"})
            continue
        if alias not in alias_to_table:
            errors.append({"step_id": step_id, "message": f"match.sources[{source_index}] alias 未定义: {alias}"})
            continue
        keys = [item for item in list(source.get("keys") or []) if isinstance(item, dict)]
        if not keys:
            errors.append({"step_id": step_id, "message": f"match.sources[{source_index}].keys 不能为空"})
            continue
        table_name = alias_to_table.get(alias, "")
        known_fields = fields_by_table.get(table_name) or set()
        for key_index, key in enumerate(keys):
            field = str(key.get("field") or "").strip()
            target_field = str(key.get("target_field") or "").strip()
            if not field or not target_field:
                errors.append({
                    "step_id": step_id,
                    "message": f"match.sources[{source_index}].keys[{key_index}] 缺少 field/target_field",
                })
                continue
            if known_fields and field not in known_fields:
                errors.append({"step_id": step_id, "message": f"match.sources[{source_index}].keys[{key_index}] 字段不存在: {table_name}.{field}"})


def _lint_dynamic_mappings(
    dynamic_mappings: Any,
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
    has_match_sources: bool,
) -> None:
    if not isinstance(dynamic_mappings, dict):
        errors.append({"step_id": step_id, "message": "dynamic_mappings 必须是对象"})
        return
    if not has_match_sources:
        errors.append({
            "step_id": step_id,
            "message": "dynamic_mappings 需要同时配置 match.sources",
            "reason": "dynamic_mappings_requires_match_sources",
        })
    mappings = [item for item in list(dynamic_mappings.get("mappings") or []) if isinstance(item, dict)]
    if not mappings:
        errors.append({"step_id": step_id, "message": "dynamic_mappings.mappings 不能为空"})
        return
    for index, mapping in enumerate(mappings):
        if not str(mapping.get("target_field") or "").strip() and not mapping.get("target_field_template"):
            errors.append({"step_id": step_id, "message": f"dynamic_mappings.mappings[{index}] 缺少 target_field 或 target_field_template"})
        value = mapping.get("value")
        if isinstance(value, dict):
            _lint_value_node(
                value,
                step_id,
                errors,
                alias_to_table=alias_to_table,
                fields_by_table=fields_by_table,
                context_label=f"dynamic_mappings.mappings[{index}].value",
            )


def _infer_base_aliases_for_lint(
    step: dict[str, Any],
    *,
    sources: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> list[str]:
    source_aliases = [
        str(source.get("alias") or source.get("table") or "").strip()
        for source in sources
        if str(source.get("alias") or source.get("table") or "").strip()
    ]
    source_aliases.extend(
        str(aggregate.get("output_alias") or "").strip()
        for aggregate in list(step.get("aggregate") or [])
        if isinstance(aggregate, dict) and str(aggregate.get("output_alias") or "").strip()
    )
    referenced_aliases: list[str] = []
    for mapping in mappings:
        referenced_aliases.extend(sorted(_collect_base_aliases(mapping)))
    if referenced_aliases:
        return list(dict.fromkeys(alias for alias in referenced_aliases if alias in source_aliases))
    return source_aliases


def _collect_base_aliases(node: Any) -> set[str]:
    aliases: set[str] = set()
    if isinstance(node, dict):
        node_type = str(node.get("type") or "").strip()
        if node_type in {"source", "template_source"}:
            source = node.get("source") if isinstance(node.get("source"), dict) else {}
            alias = str(source.get("alias") or "").strip()
            if alias:
                aliases.add(alias)
        for value in node.values():
            aliases |= _collect_base_aliases(value)
    elif isinstance(node, list):
        for item in node:
            aliases |= _collect_base_aliases(item)
    return aliases


def _lint_value_node(
    value: Any,
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
    context_label: str,
) -> None:
    if isinstance(value, list):
        for item in value:
            _lint_value_node(
                item,
                step_id,
                errors,
                alias_to_table=alias_to_table,
                fields_by_table=fields_by_table,
                context_label=context_label,
            )
        return
    if not isinstance(value, dict):
        return

    value_type = str(value.get("type") or "").strip()
    if value_type and value_type not in VALID_VALUE_TYPES:
        errors.append({"step_id": step_id, "message": f"{context_label} 不支持的 value.type: {value_type}"})

    if value_type == "source" or isinstance(value.get("source"), dict):
        _lint_source_node(
            value,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=context_label,
        )

    if value_type == "formula":
        _lint_formula_node(
            value,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=context_label,
        )
        return

    if value_type == "function":
        _lint_function_node(
            value,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=context_label,
        )
        return

    if value_type == "lookup":
        _lint_lookup_node(
            value,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=context_label,
        )
        return

    for key, nested in value.items():
        if key in {"source", "bindings"}:
            continue
        nested_label = f"{context_label}.{key}"
        _lint_value_node(
            nested,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=nested_label,
        )


def _lint_source_node(
    value: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
    context_label: str,
) -> None:
    source = value.get("source") or {}
    alias = str(source.get("alias") or "").strip()
    field = str(source.get("field") or "").strip()
    if not alias:
        errors.append({"step_id": step_id, "message": f"{context_label} 缺少 source.alias"})
    elif alias not in alias_to_table:
        errors.append({"step_id": step_id, "message": f"{context_label} source alias 未定义: {alias}"})
    table_name = alias_to_table.get(alias, "")
    known_fields = fields_by_table.get(table_name) or set()
    if field and known_fields and field not in known_fields:
        errors.append({"step_id": step_id, "message": f"{context_label} 字段不存在: {table_name}.{field}"})
    if not field:
        errors.append({"step_id": step_id, "message": f"{context_label} 缺少 source.field"})


def _lint_formula_node(
    value: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
    context_label: str,
) -> None:
    expr = str(value.get("expr") or value.get("formula") or "").strip()
    if not expr:
        errors.append({"step_id": step_id, "message": f"{context_label} 缺少 expr"})
        return
    bindings = value.get("bindings") or {}
    if not isinstance(bindings, dict):
        errors.append({"step_id": step_id, "message": f"{context_label}.bindings 必须是对象"})
        bindings = {}
    for token in _formula_tokens(expr):
        if token not in bindings:
            errors.append({"step_id": step_id, "message": f"{context_label} 引用变量缺少 binding: {token}"})
    formula_error = _validate_formula_expression(expr)
    if formula_error:
        errors.append({"step_id": step_id, "message": f"{context_label} {formula_error}"})
    for name, nested in bindings.items():
        _lint_value_node(
            nested,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=f"{context_label}.bindings.{name}",
        )


def _lint_function_node(
    value: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
    context_label: str,
) -> None:
    function_name = str(value.get("function") or "").strip()
    if not function_name:
        errors.append({"step_id": step_id, "message": f"{context_label} 缺少 function"})
    elif function_name not in SUPPORTED_FUNCTION_NODES:
        errors.append({"step_id": step_id, "message": f"{context_label} 不支持的 function: {function_name}"})
    args = value.get("args") or {}
    if not isinstance(args, dict):
        errors.append({"step_id": step_id, "message": f"{context_label}.args 必须是对象"})
        return
    for key, nested in args.items():
        _lint_value_node(
            nested,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=f"{context_label}.args.{key}",
        )


def _lint_lookup_node(
    value: dict[str, Any],
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
    context_label: str,
) -> None:
    source_alias = str(value.get("source_alias") or "").strip()
    value_field = str(value.get("value_field") or "").strip()
    if not source_alias:
        errors.append({"step_id": step_id, "message": f"{context_label} 缺少 source_alias"})
    elif source_alias not in alias_to_table:
        errors.append({"step_id": step_id, "message": f"{context_label} source_alias 未定义: {source_alias}"})
    source_table = alias_to_table.get(source_alias, "")
    known_fields = fields_by_table.get(source_table) or set()
    if not value_field:
        errors.append({"step_id": step_id, "message": f"{context_label} 缺少 value_field"})
    elif known_fields and value_field not in known_fields:
        errors.append({"step_id": step_id, "message": f"{context_label} value_field 不存在: {source_table}.{value_field}"})
    keys = [item for item in list(value.get("keys") or []) if isinstance(item, dict)]
    if not keys:
        errors.append({"step_id": step_id, "message": f"{context_label}.keys 不能为空"})
        return
    for index, key in enumerate(keys):
        lookup_field = str(key.get("lookup_field") or "").strip()
        if not lookup_field:
            errors.append({"step_id": step_id, "message": f"{context_label}.keys[{index}] 缺少 lookup_field"})
        elif known_fields and lookup_field not in known_fields:
            errors.append({"step_id": step_id, "message": f"{context_label}.keys[{index}] lookup_field 不存在: {source_table}.{lookup_field}"})
        input_spec = key.get("input")
        if not isinstance(input_spec, dict):
            errors.append({"step_id": step_id, "message": f"{context_label}.keys[{index}] 缺少 input"})
            continue
        _lint_value_node(
            input_spec,
            step_id,
            errors,
            alias_to_table=alias_to_table,
            fields_by_table=fields_by_table,
            context_label=f"{context_label}.keys[{index}].input",
        )


def _lint_dependency_cycles(dependencies: dict[str, list[str]], errors: list[dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            errors.append({"step_id": step_id, "message": "depends_on 存在循环依赖"})
            return
        visiting.add(step_id)
        for dep in dependencies.get(step_id, []):
            if dep in dependencies:
                visit(dep)
        visiting.discard(step_id)
        visited.add(step_id)

    for step_id in dependencies:
        visit(step_id)


def _formula_tokens(expr: str) -> set[str]:
    return set(re.findall(r"\{([^{}]+)\}", expr or ""))


def _validate_formula_expression(expr: str) -> str | None:
    try:
        _compile_formula_expression(expr)
    except SyntaxError as exc:
        return f"公式语法错误: {exc.msg}"
    except ValueError as exc:
        return str(exc)
    return None


@lru_cache(maxsize=256)
def _compile_formula_expression(expr: str) -> ast.Expression:
    translated = _translate_formula(expr)
    tree = ast.parse(translated, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ValueError(f"公式包含不支持的语法: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SUPPORTED_FORMULA_CALLS:
                function_name = node.func.id if isinstance(node.func, ast.Name) else type(node.func).__name__
                raise ValueError(f"公式包含不支持的函数: {function_name}")
        if isinstance(node, ast.Name) and node.id not in {"__vars__", *SUPPORTED_FORMULA_CALLS}:
            raise ValueError(f"公式包含不支持的标识符: {node.id}")
    return tree


def _translate_formula(expr: str) -> str:
    expr = _convert_ternary(expr.strip())
    return re.sub(r"\{([^{}]+)\}", lambda match: f"__vars__[{match.group(1)!r}]", expr)


def _convert_ternary(expr: str) -> str:
    expr = expr.strip()
    if not expr:
        return expr
    if _is_wrapped_by_outer_parentheses(expr):
        return f"({_convert_ternary(expr[1:-1])})"

    rebuilt: list[str] = []
    idx = 0
    while idx < len(expr):
        char = expr[idx]
        if char != "(":
            rebuilt.append(char)
            idx += 1
            continue
        end = _find_matching_parenthesis(expr, idx)
        inner = expr[idx + 1 : end]
        rebuilt.append(f"({_convert_ternary(inner)})")
        idx = end + 1

    return _convert_top_level_ternary("".join(rebuilt))


def _convert_top_level_ternary(expr: str) -> str:
    qmark = _find_top_level_qmark(expr)
    if qmark == -1:
        return expr
    colon = _find_matching_colon(expr, qmark)
    if colon == -1:
        raise ValueError(f"三元表达式缺少冒号: {expr}")
    condition = expr[:qmark].strip()
    when_true = expr[qmark + 1 : colon].strip()
    when_false = expr[colon + 1 :].strip()
    return (
        f"({_convert_ternary(when_true)} if {_convert_ternary(condition)} "
        f"else {_convert_ternary(when_false)})"
    )


def _find_top_level_qmark(expr: str) -> int:
    depth = 0
    for idx, char in enumerate(expr):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "?" and depth == 0:
            return idx
    return -1


def _find_matching_colon(expr: str, qmark: int) -> int:
    depth = 0
    nested = 0
    for idx in range(qmark + 1, len(expr)):
        char = expr[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and char == "?":
            nested += 1
        elif depth == 0 and char == ":":
            if nested == 0:
                return idx
            nested -= 1
    return -1


def _find_matching_parenthesis(expr: str, start: int) -> int:
    depth = 0
    for idx in range(start, len(expr)):
        char = expr[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
    raise ValueError(f"括号未闭合: {expr}")


def _is_wrapped_by_outer_parentheses(expr: str) -> bool:
    if len(expr) < 2 or expr[0] != "(" or expr[-1] != ")":
        return False
    try:
        return _find_matching_parenthesis(expr, 0) == len(expr) - 1
    except ValueError:
        return False


def _source_fields(source: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    field_label_map = source.get("field_label_map")
    if isinstance(field_label_map, dict):
        fields.update(str(key).strip() for key in field_label_map.keys() if str(key).strip())
    for field in list(source.get("fields") or []):
        if not isinstance(field, dict):
            continue
        name = str(
            field.get("name")
            or field.get("raw_name")
            or field.get("field_name")
            or field.get("key")
            or ""
        ).strip()
        if name:
            fields.add(name)
    for row in list(source.get("sample_rows") or []):
        if isinstance(row, dict):
            fields.update(str(key).strip() for key in row.keys() if str(key).strip())
    return fields


def _table_name(source: dict[str, Any]) -> str:
    return str(
        source.get("table_name")
        or source.get("resource_key")
        or source.get("dataset_code")
        or source.get("dataset_name")
        or source.get("source_id")
        or ""
    ).strip()


def _result(success: bool, errors: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    return {
        "success": success,
        "status": "passed" if success else "failed",
        "errors": errors,
        "warnings": warnings,
    }
