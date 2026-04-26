"""Fallback proc rule builder for rule generation workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        "dsl_constraints": {
            "actions": ["create_schema", "write_dataset"],
            "builtin_functions": ["current_date", "month_of", "add_months"],
            "aggregate_operators": ["sum", "min"],
            "field_write_modes": ["overwrite", "increment"],
            "row_write_modes": ["insert_if_missing", "update_only", "upsert"],
            "column_data_types": ["string", "date", "decimal"],
            "value_node_types": ["source", "formula", "template_source", "function", "context", "lookup"],
            "merge_strategies": ["union_distinct"],
            "loop_context_vars": [],
        },
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
