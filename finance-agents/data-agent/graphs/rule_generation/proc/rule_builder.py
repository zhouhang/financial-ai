"""Deterministic proc rule builders for rule generation workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_proc_rule_skeleton_from_ir(
    *,
    side: str,
    target_table: str,
    target_tables: list[str] | None = None,
    rule_text: str,
    sources: list[dict[str, Any]],
    understanding: dict[str, Any],
    field_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal proc DSL skeleton; IR compiler fills executable semantics."""
    targets = [
        str(item).strip()
        for item in list(target_tables or [])
        if str(item).strip()
    ]
    if not targets and target_table:
        targets = [target_table]
    if not targets:
        targets = ["proc_output"]

    output_specs = [
        item
        for item in list((understanding or {}).get("output_specs") or [])
        if isinstance(item, dict)
    ]
    output_mode = str((understanding or {}).get("output_mode") or "").strip()
    passthrough = output_mode == "source_passthrough" and not output_specs
    passthrough_source = (
        _select_passthrough_source(sources, understanding, field_bindings=field_bindings or [])
        if passthrough
        else {}
    )
    source_specs = _source_specs(
        sources,
        primary_source=passthrough_source if passthrough else None,
    )
    source_columns = _passthrough_columns(passthrough_source) if passthrough else []
    columns = _schema_columns_from_output_specs(output_specs) if output_specs else source_columns
    if not columns:
        columns = [{"name": "result", "data_type": "string"}]

    steps: list[dict[str, Any]] = []
    for target in targets:
        create_step_id = f"create_{target}"
        steps.append({
            "step_id": create_step_id,
            "action": "create_schema",
            "target_table": target,
            "schema": {
                "primary_key": [],
                "columns": columns,
            },
        })
        mappings = (
            _passthrough_mappings(
                _alias_for_source(source_specs, passthrough_source) or source_specs[0]["alias"],
                source_columns,
            )
            if passthrough and source_specs
            else []
        )
        steps.append({
            "step_id": f"write_{target}",
            "action": "write_dataset",
            "target_table": target,
            "depends_on": [create_step_id],
            "row_write_mode": "upsert",
            "sources": source_specs,
            "mappings": mappings,
        })

    return {
        "role_desc": rule_text.strip() or "AI生成数据整理规则",
        "version": "1.0",
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "author": "rule_generation",
            "generation_mode": "ir_compiler",
            "side": side,
        },
        "global_config": {
            "default_round_precision": 2,
            "date_format": "YYYY-MM-DD",
            "null_value_handling": "keep",
            "error_handling": "stop",
        },
        "file_rule_code": "",
        "dsl_constraints": _dsl_constraints(),
        "steps": steps,
    }


def build_fallback_proc_rule(
    *,
    side: str,
    target_table: str,
    rule_text: str,
    sources: list[dict[str, Any]],
    field_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a conservative single-side proc rule from available source metadata."""
    primary_source = sources[0] if sources else {}
    table_name = _table_name(primary_source)
    alias = f"{side}_source_1"
    key_field = _bound_field_for_role(field_bindings or [], "match_key", table_name)
    amount_field = _bound_field_for_role(field_bindings or [], "compare_field", table_name)
    date_field = _bound_field_for_role(field_bindings or [], "time_field", table_name)
    filter_bindings = [
        item
        for item in list(field_bindings or [])
        if isinstance(item, dict)
        and item.get("status") == "bound"
        and str(item.get("role") or "") == "filter_field"
        and item.get("value") not in {None, ""}
        and _binding_matches_table(item, table_name)
    ]
    source_name = str(
        primary_source.get("business_name")
        or primary_source.get("dataset_name")
        or primary_source.get("name")
        or table_name
        or side
    ).strip()

    columns = [
        {"name": "biz_key", "data_type": "string", "nullable": False},
        {"name": "amount", "data_type": "decimal", "precision": 18, "scale": 2, "default": 0},
        {"name": "biz_date", "data_type": "date", "nullable": True},
        {"name": "source_name", "data_type": "string", "nullable": True},
    ]
    mappings: list[dict[str, Any]] = []
    if key_field:
        mappings.append(_source_mapping("biz_key", alias, key_field))
    else:
        mappings.append(_formula_mapping("biz_key", "'样例业务主键'"))
    if amount_field:
        mappings.append(_source_mapping("amount", alias, amount_field))
    else:
        mappings.append(_formula_mapping("amount", "0"))
    if date_field:
        mappings.append(_source_mapping("biz_date", alias, date_field))
    else:
        mappings.append(_formula_mapping("biz_date", "''"))
    mappings.append(_formula_mapping("source_name", repr(source_name)))

    return {
        "role_desc": rule_text.strip() or "AI生成数据整理规则",
        "version": "1.0",
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "author": "rule_generation",
            "generation_mode": "fallback",
        },
        "global_config": {
            "default_round_precision": 2,
            "date_format": "YYYY-MM-DD",
            "null_value_handling": "keep",
            "error_handling": "stop",
        },
        "file_rule_code": "",
        "dsl_constraints": _dsl_constraints(),
        "steps": [
            {
                "step_id": f"create_{target_table}",
                "action": "create_schema",
                "target_table": target_table,
                "schema": {"primary_key": ["biz_key"], "columns": columns},
            },
            {
                "step_id": f"{side}_write_recon_ready",
                "action": "write_dataset",
                "target_table": target_table,
                "depends_on": [f"create_{target_table}"],
                "row_write_mode": "upsert",
                "sources": [{"table": table_name, "alias": alias}] if table_name else [],
                **_filter_step_payload(filter_bindings, alias),
                "mappings": mappings,
            },
        ],
    }


def _bound_field_for_role(field_bindings: list[dict[str, Any]], role: str, table_name: str) -> str:
    for binding in field_bindings:
        if not isinstance(binding, dict):
            continue
        if binding.get("status") != "bound" or str(binding.get("role") or "") != role:
            continue
        if not _binding_matches_table(binding, table_name):
            continue
        selected_field = binding.get("selected_field")
        if isinstance(selected_field, dict):
            field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
            if field_name:
                return field_name
    return ""


def _dsl_constraints() -> dict[str, Any]:
    return {
        "actions": ["create_schema", "write_dataset"],
        "builtin_functions": ["current_date", "month_of", "add_months"],
        "aggregate_operators": ["sum", "min"],
        "field_write_modes": ["overwrite", "increment"],
        "row_write_modes": ["insert_if_missing", "update_only", "upsert"],
        "column_data_types": ["string", "date", "decimal"],
        "value_node_types": ["source", "formula", "template_source", "function", "context", "lookup"],
        "merge_strategies": ["union_distinct"],
        "loop_context_vars": [],
    }


def _source_specs(
    sources: list[dict[str, Any]],
    *,
    primary_source: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    ordered_sources = _sources_with_primary_first(sources, primary_source or {})
    for index, source in enumerate(ordered_sources, start=1):
        table_name = _table_name(source)
        if not table_name:
            continue
        specs.append({"table": table_name, "alias": f"source_{index}"})
    return specs


def _sources_with_primary_first(
    sources: list[dict[str, Any]],
    primary_source: dict[str, Any],
) -> list[dict[str, Any]]:
    primary_table = _table_name(primary_source)
    if not primary_table:
        return list(sources)
    primary_items: list[dict[str, Any]] = []
    other_items: list[dict[str, Any]] = []
    for source in sources:
        if _table_name(source) == primary_table:
            primary_items.append(source)
        else:
            other_items.append(source)
    return primary_items + other_items if primary_items else list(sources)


def _select_passthrough_source(
    sources: list[dict[str, Any]],
    understanding: dict[str, Any],
    *,
    field_bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not sources:
        return {}
    if len(sources) == 1:
        return sources[0]
    scored: list[tuple[int, int, dict[str, Any]]] = []
    reference_scopes = _understanding_reference_scopes(understanding)
    binding_scopes = _field_binding_reference_scopes(field_bindings)
    for index, source in enumerate(sources):
        aliases = _source_scope_aliases(source)
        score = (
            sum(1 for scope in reference_scopes if scope in aliases)
            + sum(3 for scope in binding_scopes if scope in aliases)
        )
        scored.append((score, -index, source))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not scored or scored[0][0] <= 0:
        raise ValueError("source_passthrough 多数据集场景无法根据本轮 IR 判断基础表")
    return scored[0][2]


def _understanding_reference_scopes(understanding: dict[str, Any]) -> set[str]:
    scopes: set[str] = set()
    for reference in list((understanding or {}).get("source_references") or []):
        if not isinstance(reference, dict):
            continue
        scopes.update(_text_set(reference.get("table_scope")))
        for candidate in list(reference.get("candidate_fields") or []):
            if not isinstance(candidate, dict):
                continue
            scopes.update(_text_set([
                candidate.get("source_table"),
                candidate.get("table_name"),
                candidate.get("dataset_name"),
            ]))
    return scopes


def _field_binding_reference_scopes(field_bindings: list[dict[str, Any]]) -> set[str]:
    scopes: set[str] = set()
    for binding in list(field_bindings or []):
        if not isinstance(binding, dict) or binding.get("status") != "bound":
            continue
        scopes.update(_text_set(binding.get("table_scope")))
        selected = binding.get("selected_field") if isinstance(binding.get("selected_field"), dict) else {}
        scopes.update(_text_set([
            selected.get("source_table"),
            selected.get("table_name"),
            selected.get("dataset_name"),
        ]))
        for candidate in list(binding.get("candidates") or []):
            if not isinstance(candidate, dict):
                continue
            scopes.update(_text_set([
                candidate.get("source_table"),
                candidate.get("table_name"),
                candidate.get("dataset_name"),
            ]))
    return scopes


def _source_scope_aliases(source: dict[str, Any]) -> set[str]:
    return _text_set([
        _table_name(source),
        source.get("business_name"),
        source.get("dataset_name"),
        source.get("name"),
        source.get("resource_key"),
        source.get("dataset_id"),
        source.get("id"),
    ])


def _text_set(values: Any) -> set[str]:
    if isinstance(values, (str, int, float)):
        values = [values]
    return {
        str(item).strip()
        for item in list(values or [])
        if str(item).strip()
    }


def _alias_for_source(source_specs: list[dict[str, str]], source: dict[str, Any]) -> str:
    table_name = _table_name(source)
    for spec in source_specs:
        if str(spec.get("table") or "").strip() == table_name:
            return str(spec.get("alias") or "").strip()
    return ""


def _schema_columns_from_output_specs(output_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in output_specs:
        name = str(spec.get("name") or spec.get("output_id") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        columns.append({"name": name, "data_type": _output_spec_data_type(spec)})
    return columns


def _passthrough_columns(source: dict[str, Any]) -> list[dict[str, Any]]:
    fields = source.get("fields")
    if not isinstance(fields, list) or not fields:
        fields = (source.get("schema_summary") or {}).get("columns") if isinstance(source.get("schema_summary"), dict) else []
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in list(fields or []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or field.get("raw_name") or field.get("field_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        columns.append({
            "name": name,
            "data_type": _normalize_column_type(field.get("data_type") or field.get("schema_type")),
        })
    if columns:
        return columns
    for row in list(source.get("sample_rows") or []):
        if not isinstance(row, dict):
            continue
        for name in row.keys():
            field_name = str(name).strip()
            if field_name and field_name not in seen:
                seen.add(field_name)
                columns.append({"name": field_name, "data_type": "string"})
    return columns


def _passthrough_mappings(alias: str, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _source_mapping(str(column.get("name") or ""), alias, str(column.get("name") or ""))
        for column in columns
        if str(column.get("name") or "").strip()
    ]


def _output_spec_data_type(spec: dict[str, Any]) -> str:
    kind = str(spec.get("kind") or "").strip().lower()
    if kind in {"aggregate"}:
        return "decimal"
    expression = spec.get("expression") if isinstance(spec.get("expression"), dict) else {}
    return _expression_data_type(expression) if expression else "string"


def _expression_data_type(expression: dict[str, Any]) -> str:
    op = str(expression.get("op") or "").strip().lower()
    if op in {"add", "subtract", "multiply", "divide"}:
        return "decimal"
    if op == "function" and str(expression.get("name") or "").strip() in {"current_date", "add_months"}:
        return "date"
    value = expression.get("value") if op == "constant" else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "decimal"
    return "string"


def _normalize_column_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if any(token in text for token in ("decimal", "numeric", "number", "int", "float", "double")):
        return "decimal"
    if any(token in text for token in ("date", "time", "timestamp")):
        return "date"
    return "string"


def _binding_matches_table(binding: dict[str, Any], table_name: str) -> bool:
    selected_field = binding.get("selected_field")
    if not isinstance(selected_field, dict):
        return False
    selected_table = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
    return not selected_table or not table_name or selected_table == table_name


def _filter_step_payload(filter_bindings: list[dict[str, Any]], alias: str) -> dict[str, Any]:
    if not filter_bindings:
        return {}
    clauses: list[str] = []
    bindings: dict[str, Any] = {}
    for index, binding in enumerate(filter_bindings, start=1):
        selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
        if not isinstance(selected_field, dict):
            continue
        field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
        if not field_name:
            continue
        field_token = f"filter_field_{index}"
        value_token = f"filter_value_{index}"
        clauses.append(f"{{{field_token}}} == {{{value_token}}}")
        bindings[field_token] = {"type": "source", "source": {"alias": alias, "field": field_name}}
        bindings[value_token] = {"type": "formula", "expr": repr(str(binding.get("value") or ""))}
    if not clauses:
        return {}
    return {
        "filter": {
            "type": "formula",
            "expr": " and ".join(clauses),
            "bindings": bindings,
        }
    }


def _source_mapping(target_field: str, alias: str, field: str) -> dict[str, Any]:
    return {
        "target_field": target_field,
        "value": {"type": "source", "source": {"alias": alias, "field": field}},
        "field_write_mode": "overwrite",
    }


def _formula_mapping(target_field: str, expr: str) -> dict[str, Any]:
    return {
        "target_field": target_field,
        "value": {"type": "formula", "expr": expr},
        "field_write_mode": "overwrite",
    }


def _table_name(source: dict[str, Any]) -> str:
    return str(
        source.get("table_name")
        or source.get("resource_key")
        or source.get("dataset_code")
        or source.get("dataset_name")
        or source.get("source_id")
        or ""
    ).strip()
