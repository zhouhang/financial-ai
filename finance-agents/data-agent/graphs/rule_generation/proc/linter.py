"""Deterministic linting for generated proc steps DSL."""

from __future__ import annotations

import re
from typing import Any


VALID_ACTIONS = {"create_schema", "write_dataset"}
VALID_ROW_WRITE_MODES = {"upsert", "insert_if_missing", "update_only"}
VALID_VALUE_TYPES = {"source", "formula", "template_source", "function", "context", "lookup"}


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

    mappings = [item for item in list(step.get("mappings") or []) if isinstance(item, dict)]
    dynamic_mappings = step.get("dynamic_mappings")
    if not mappings and not dynamic_mappings:
        errors.append({"step_id": step_id, "message": "write_dataset 缺少 mappings"})
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
            fields_by_table=fields_by_table,
        )

    if not mappings:
        warnings.append(f"{step_id} 没有普通 mappings，可能依赖 dynamic_mappings")


def _lint_value_node(
    value: Any,
    step_id: str,
    errors: list[dict[str, Any]],
    *,
    alias_to_table: dict[str, str],
    fields_by_table: dict[str, set[str]],
) -> None:
    if isinstance(value, list):
        for item in value:
            _lint_value_node(item, step_id, errors, alias_to_table=alias_to_table, fields_by_table=fields_by_table)
        return
    if not isinstance(value, dict):
        return

    value_type = str(value.get("type") or "").strip()
    if value_type and value_type not in VALID_VALUE_TYPES:
        errors.append({"step_id": step_id, "message": f"不支持的 value.type: {value_type}"})

    if value_type == "source" or isinstance(value.get("source"), dict):
        source = value.get("source") or {}
        alias = str(source.get("alias") or "").strip()
        field = str(source.get("field") or "").strip()
        if not alias:
            errors.append({"step_id": step_id, "message": "source value 缺少 alias"})
        elif alias not in alias_to_table:
            errors.append({"step_id": step_id, "message": f"source alias 未定义: {alias}"})
        table_name = alias_to_table.get(alias, "")
        known_fields = fields_by_table.get(table_name) or set()
        if field and known_fields and field not in known_fields:
            errors.append({"step_id": step_id, "message": f"字段不存在: {table_name}.{field}"})
        if not field:
            errors.append({"step_id": step_id, "message": "source value 缺少 field"})

    if value_type == "formula":
        expr = str(value.get("expr") or value.get("formula") or "").strip()
        if not expr:
            errors.append({"step_id": step_id, "message": "formula value 缺少 expr"})
        bindings = value.get("bindings") or {}
        if not isinstance(bindings, dict):
            errors.append({"step_id": step_id, "message": "formula.bindings 必须是对象"})
            bindings = {}
        for token in _formula_tokens(expr):
            if token not in bindings:
                errors.append({"step_id": step_id, "message": f"formula 引用变量缺少 binding: {token}"})
        for nested in bindings.values():
            _lint_value_node(nested, step_id, errors, alias_to_table=alias_to_table, fields_by_table=fields_by_table)
        return

    for key, nested in value.items():
        if key in {"source", "bindings"}:
            continue
        _lint_value_node(nested, step_id, errors, alias_to_table=alias_to_table, fields_by_table=fields_by_table)


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
