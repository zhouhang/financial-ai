"""Compile structured understanding IR into executable proc DSL fragments."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any


RUNTIME_FUNCTIONS = {
    "current_date",
    "add_months",
    "month_of",
    "fraction_numerator",
    "to_decimal",
}

INLINE_FORMULA_FUNCTIONS = {"coalesce", "is_null"}
AGGREGATE_OPERATORS = {"sum", "min"}
ROW_LOOKUP_RULE_TYPES = {"join", "lookup", "derive", "other"}
ARITHMETIC_OPERATORS = {
    "add": "+",
    "subtract": "-",
    "multiply": "*",
    "divide": "/",
    "concat": "+",
}
COMPARE_OPERATORS = {
    "eq": "==",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


@dataclass
class CompiledFormulaFragment:
    expr: str
    bindings: dict[str, Any] = field(default_factory=dict)
    data_type: str = "unknown"
    value_kind: str = "expression"


@dataclass
class StepCompileContext:
    target_table: str
    alias_by_table: dict[str, str]
    default_alias: str
    field_meta: dict[tuple[str, str], dict[str, str]]
    binding_map: dict[str, dict[str, Any]]
    token_counter: int = 0

    def allocate_token(self, base: str) -> str:
        self.token_counter += 1
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(base or "value")).strip("_").lower()
        normalized = normalized or "value"
        return f"{normalized}_{self.token_counter}"

    def alias_for_table(self, table_name: str) -> str:
        table = str(table_name or "").strip()
        if table and table in self.alias_by_table:
            return self.alias_by_table[table]
        return self.default_alias

    def meta_for_field(self, table_name: str, field_name: str) -> dict[str, str]:
        return self.field_meta.get((str(table_name or "").strip(), str(field_name or "").strip()), {})


@dataclass
class AggregateCompilePlan:
    rule_id: str
    output_alias: str
    source_alias: str
    source_table: str
    value_ref_id: str
    value_field: str
    operator: str
    aggregation_alias: str
    group_ref_ids: list[str]
    group_fields: list[str]
    group_target_fields: list[str]


def compile_understanding_into_rule(
    rule: dict[str, Any],
    *,
    understanding: dict[str, Any],
    field_bindings: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    target_table: str = "",
    target_tables: list[str] | None = None,
) -> dict[str, Any]:
    """Compile structured IR onto a generated proc rule.

    Proc JSON is generated deterministically from IR. LLM is only allowed to
    generate or repair the structured understanding consumed by this compiler.
    """
    if not isinstance(rule, dict):
        return {}
    normalized_rule = copy.deepcopy(rule)
    steps = [step for step in list(normalized_rule.get("steps") or []) if isinstance(step, dict)]
    if not steps:
        return normalized_rule

    source_refs = {
        str(item.get("ref_id") or "").strip(): item
        for item in list((understanding or {}).get("source_references") or [])
        if isinstance(item, dict) and str(item.get("ref_id") or "").strip()
    }
    output_specs = [
        item
        for item in list((understanding or {}).get("output_specs") or [])
        if isinstance(item, dict)
    ]
    business_rules = [
        item
        for item in list((understanding or {}).get("business_rules") or [])
        if isinstance(item, dict)
    ]
    binding_map = {
        str(item.get("intent_id") or "").strip(): item
        for item in list(field_bindings or [])
        if isinstance(item, dict) and str(item.get("intent_id") or "").strip()
    }
    field_meta = _build_field_meta(sources)

    expected_targets = {
        str(item).strip()
        for item in list(target_tables or [])
        if str(item).strip()
    }
    if target_table:
        expected_targets.add(str(target_table).strip())

    schema_steps_by_target: dict[str, dict[str, Any]] = {}
    write_steps: list[dict[str, Any]] = []
    for step in steps:
        action = str(step.get("action") or "").strip()
        current_target = str(step.get("target_table") or "").strip()
        if expected_targets and current_target not in expected_targets:
            continue
        if action == "create_schema":
            schema_steps_by_target[current_target] = step
        elif action == "write_dataset":
            write_steps.append(step)

    for write_step in write_steps:
        current_target = str(write_step.get("target_table") or "").strip()
        compile_context = StepCompileContext(
            target_table=current_target,
            alias_by_table=_alias_by_table(write_step),
            default_alias=_default_alias(write_step),
            field_meta=field_meta,
            binding_map=binding_map,
        )

        compiled_filter = _compile_filter_rules(
            business_rules,
            source_refs=source_refs,
            compile_context=compile_context,
        )
        if compiled_filter:
            write_step["filter"] = compiled_filter

        schema_step = schema_steps_by_target.get(current_target)
        mappings = [item for item in list(write_step.get("mappings") or []) if isinstance(item, dict)]
        write_step["mappings"] = mappings
        aggregate_compiled_outputs = _compile_aggregate_rules(
            write_step,
            mappings,
            output_specs,
            business_rules,
            source_refs=source_refs,
            compile_context=compile_context,
            schema_step=schema_step,
        )
        for spec in output_specs:
            target_field = str(spec.get("name") or "").strip()
            if not target_field:
                continue
            if _output_spec_identity(spec) & aggregate_compiled_outputs:
                continue
            if not _should_compile_output_spec(spec):
                continue
            compiled_value, data_type = _compile_output_spec_value(
                spec,
                source_refs=source_refs,
                compile_context=compile_context,
                business_rules=business_rules,
                write_step=write_step,
                output_specs=output_specs,
            )
            if not compiled_value:
                raise ValueError(f"output_spec 无法编译为可执行 DSL: {target_field}")
            mapping = _find_mapping(mappings, target_field)
            if mapping is None:
                mapping = {"target_field": target_field}
                mappings.append(mapping)
            elif not _should_replace_existing_mapping(
                mapping.get("value"),
                replacement_value=compiled_value,
                spec=spec,
                alias_by_table=compile_context.alias_by_table,
                allowed_sources=_allowed_sources_for_output_spec(spec, compile_context),
            ):
                if schema_step:
                    _ensure_schema_column(schema_step, target_field=target_field, data_type=data_type)
                continue
            mapping["target_field"] = target_field
            mapping["value"] = compiled_value
            mapping["field_write_mode"] = str(mapping.get("field_write_mode") or "overwrite")
            if schema_step:
                _ensure_schema_column(schema_step, target_field=target_field, data_type=data_type)
        _prune_unused_match_sources(write_step, schema_step=schema_step)
        _prune_unused_aggregates(write_step)

    normalized_rule["steps"] = steps
    return normalized_rule


def _compile_output_spec_value(
    spec: dict[str, Any],
    *,
    source_refs: dict[str, dict[str, Any]],
    compile_context: StepCompileContext,
    business_rules: list[dict[str, Any]],
    write_step: dict[str, Any],
    output_specs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    kind = str(spec.get("kind") or "").strip().lower()
    expression = spec.get("expression") if isinstance(spec.get("expression"), dict) else None
    source_ref_ids = [
        str(item).strip()
        for item in list(spec.get("source_ref_ids") or [])
        if str(item).strip()
    ]
    if kind in {"passthrough", "rename", "unknown"} and len(source_ref_ids) == 1:
        if _output_linked_business_rules(spec, business_rules, rule_types=ROW_LOOKUP_RULE_TYPES):
            linked_value, linked_data_type = _compile_join_derived_value(
                spec,
                business_rules,
                compile_context=compile_context,
                write_step=write_step,
                output_specs=output_specs,
            )
            if linked_value:
                return linked_value, linked_data_type
        source_node, data_type = _binding_source_node(source_ref_ids[0], compile_context)
        return (source_node, data_type) if source_node else (None, "string")

    if kind in {"constant", "formula"} and expression:
        return _compile_formula_output_value(
            spec,
            expression,
            business_rules,
            compile_context=compile_context,
            write_step=write_step,
            output_specs=output_specs,
        )

    if kind in {"lookup", "join_derived"}:
        if expression:
            return _compile_expression_value(expression, compile_context)
        return _compile_join_derived_value(
            spec,
            business_rules,
            compile_context=compile_context,
            write_step=write_step,
            output_specs=output_specs,
        )

    return None, "string"


def _compile_formula_output_value(
    spec: dict[str, Any],
    expression: dict[str, Any],
    business_rules: list[dict[str, Any]],
    *,
    compile_context: StepCompileContext,
    write_step: dict[str, Any],
    output_specs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    linked_join_rules = _candidate_row_lookup_rules_for_output_spec(
        spec,
        business_rules,
        compile_context=compile_context,
        write_step=write_step,
        output_specs=output_specs,
        rule_types=ROW_LOOKUP_RULE_TYPES,
    )
    if not linked_join_rules:
        return _compile_expression_value(expression, compile_context)
    return _compile_expression_value(
        expression,
        compile_context,
        ref_resolver=lambda ref_id, numeric_context: _compile_join_lookup_ref_fragment(
            ref_id,
            spec,
            linked_join_rules,
            compile_context=compile_context,
            write_step=write_step,
            output_specs=output_specs,
            numeric_context=numeric_context,
        ),
    )


def _compile_join_derived_value(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
    *,
    compile_context: StepCompileContext,
    write_step: dict[str, Any],
    output_specs: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    linked_rules = [
        rule
        for rule in _candidate_row_lookup_rules_for_output_spec(
            spec,
            business_rules,
            compile_context=compile_context,
            write_step=write_step,
            output_specs=output_specs,
            rule_types=ROW_LOOKUP_RULE_TYPES,
        )
        if isinstance(rule, dict)
    ]
    source_ref_ids = _text_list(spec.get("source_ref_ids"))
    target_field = str(spec.get("name") or "").strip()
    current_alias_candidates = _current_row_alias_candidates(
        write_step,
        compile_context,
        output_specs=output_specs,
        current_target_field=target_field,
    )
    value_ref_id = _select_join_value_ref_id(source_ref_ids, linked_rules, compile_context)
    value_source = _bound_source_for_ref_id(value_ref_id, compile_context) if value_ref_id else None
    if not value_source:
        return None, "string"
    value_table, value_field, data_type = value_source
    lookup_alias = compile_context.alias_for_table(value_table)
    for rule in linked_rules:
        related_ref_ids = _text_list(rule.get("related_ref_ids"))
        left_ref_id = ""
        right_ref_id = ""
        for ref_id in related_ref_ids:
            source = _bound_source_for_ref_id(ref_id, compile_context)
            if not source:
                continue
            table_name, _field_name, _data_type = source
            if table_name == value_table and ref_id != value_ref_id:
                right_ref_id = right_ref_id or ref_id
            elif table_name != value_table:
                left_ref_id = left_ref_id or ref_id
        if not left_ref_id or not right_ref_id:
            continue
        left_source = _bound_source_for_ref_id(left_ref_id, compile_context)
        right_source = _bound_source_for_ref_id(right_ref_id, compile_context)
        if not left_source or not right_source:
            continue
        for current_alias in current_alias_candidates:
            current_table = _table_for_current_alias(current_alias, write_step, compile_context)
            if current_table and current_table != left_source[0]:
                continue
            input_field = _field_available_on_current_alias(left_source[1], current_alias, write_step)
            if not input_field:
                continue
            return {
                "type": "lookup",
                "source_alias": lookup_alias,
                "value_field": value_field,
                "keys": [
                    {
                        "lookup_field": right_source[1],
                        "input": {
                            "type": "source",
                            "source": {"alias": current_alias, "field": input_field},
                        },
                    }
                ],
            }, data_type or "string"
    return None, "string"


def _compile_join_lookup_ref_fragment(
    ref_id: str,
    spec: dict[str, Any],
    linked_rules: list[dict[str, Any]],
    *,
    compile_context: StepCompileContext,
    write_step: dict[str, Any],
    output_specs: list[dict[str, Any]],
    numeric_context: bool,
) -> CompiledFormulaFragment | None:
    value_source = _bound_source_for_ref_id(ref_id, compile_context)
    if not value_source:
        return None
    value_table, value_field, data_type = value_source
    target_field = str(spec.get("name") or "").strip()
    current_alias_candidates = _current_row_alias_candidates(
        write_step,
        compile_context,
        output_specs=output_specs,
        current_target_field=target_field,
    )
    for current_alias in current_alias_candidates:
        current_table = _table_for_current_alias(current_alias, write_step, compile_context)
        if current_table != value_table:
            lookup_fragment = _lookup_fragment_for_current_alias(
                ref_id,
                value_table=value_table,
                value_field=value_field,
                data_type=data_type,
                current_alias=current_alias,
                current_table=current_table,
                linked_rules=linked_rules,
                compile_context=compile_context,
                write_step=write_step,
                numeric_context=numeric_context,
            )
            if lookup_fragment:
                return lookup_fragment
            continue
        input_field = _field_available_on_current_alias(value_field, current_alias, write_step)
        if not input_field:
            continue
        return _value_node_fragment(
            ref_id=ref_id,
            field_name=input_field,
            value_node={
                "type": "source",
                "source": {"alias": current_alias, "field": input_field},
            },
            data_type=data_type,
            numeric_context=numeric_context,
            compile_context=compile_context,
            value_kind="source",
        )
    return _compile_ref_fragment(ref_id, compile_context, numeric_context=numeric_context)


def _lookup_fragment_for_current_alias(
    ref_id: str,
    *,
    value_table: str,
    value_field: str,
    data_type: str,
    current_alias: str,
    current_table: str,
    linked_rules: list[dict[str, Any]],
    compile_context: StepCompileContext,
    write_step: dict[str, Any],
    numeric_context: bool,
) -> CompiledFormulaFragment | None:
    if not current_table or current_table == value_table:
        return None
    lookup_alias = compile_context.alias_for_table(value_table)
    for rule in linked_rules:
        related_ref_ids = _row_lookup_rule_ref_ids(rule)
        left_ref_id = _first_ref_on_table(
            related_ref_ids,
            table_name=current_table,
            compile_context=compile_context,
            exclude_ref_ids={ref_id},
        )
        right_ref_id = _first_ref_on_table(
            related_ref_ids,
            table_name=value_table,
            compile_context=compile_context,
            exclude_ref_ids={ref_id},
        )
        if not left_ref_id or not right_ref_id:
            continue
        left_source = _bound_source_for_ref_id(left_ref_id, compile_context)
        right_source = _bound_source_for_ref_id(right_ref_id, compile_context)
        if not left_source or not right_source:
            continue
        input_field = _field_available_on_current_alias(left_source[1], current_alias, write_step)
        if not input_field:
            continue
        return _value_node_fragment(
            ref_id=ref_id,
            field_name=value_field,
            value_node={
                "type": "lookup",
                "source_alias": lookup_alias,
                "value_field": value_field,
                "keys": [
                    {
                        "lookup_field": right_source[1],
                        "input": {
                            "type": "source",
                            "source": {"alias": current_alias, "field": input_field},
                        },
                    }
                ],
            },
            data_type=data_type,
            numeric_context=numeric_context,
            compile_context=compile_context,
            value_kind="lookup",
        )
    return None


def _candidate_row_lookup_rules_for_output_spec(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
    *,
    compile_context: StepCompileContext,
    write_step: dict[str, Any],
    output_specs: list[dict[str, Any]],
    rule_types: set[str],
) -> list[dict[str, Any]]:
    linked = _output_linked_business_rules(spec, business_rules, rule_types=rule_types)
    linked_ids = {_rule_identity(rule) for rule in linked}
    spec_ref_ids = _output_spec_ref_ids(spec)
    spec_tables = {
        source[0]
        for ref_id in spec_ref_ids
        if (source := _bound_source_for_ref_id(ref_id, compile_context)) is not None
    }
    if not spec_tables:
        return linked

    current_alias_candidates = _current_row_alias_candidates(
        write_step,
        compile_context,
        output_specs=output_specs,
        current_target_field=str(spec.get("name") or "").strip(),
    )
    current_tables = {
        table
        for alias in current_alias_candidates
        if (table := _table_for_current_alias(alias, write_step, compile_context))
    }
    candidates = list(linked)
    for rule in business_rules:
        if str(rule.get("type") or "").strip() not in rule_types:
            continue
        rule_identity = _rule_identity(rule)
        if rule_identity in linked_ids:
            continue
        related_ref_ids = _row_lookup_rule_ref_ids(rule)
        rule_tables = {
            source[0]
            for ref_id in related_ref_ids
            if (source := _bound_source_for_ref_id(ref_id, compile_context)) is not None
        }
        if len(rule_tables) < 2:
            continue
        for value_table in spec_tables:
            if value_table not in rule_tables:
                continue
            if current_tables - {value_table} and rule_tables & (current_tables - {value_table}):
                candidates.append(rule)
                linked_ids.add(rule_identity)
                break
    return candidates


def _row_lookup_rule_ref_ids(rule: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for ref_id in _text_list(rule.get("related_ref_ids")):
        if ref_id not in seen:
            ordered.append(ref_id)
            seen.add(ref_id)
    for ref_id in _collect_ref_ids_from_node_to_set(rule.get("params")):
        if ref_id not in seen:
            ordered.append(ref_id)
            seen.add(ref_id)
    return ordered


def _output_spec_ref_ids(spec: dict[str, Any]) -> set[str]:
    ref_ids = set(_text_list(spec.get("source_ref_ids")))
    _collect_ref_ids_from_node(spec.get("expression"), ref_ids)
    return ref_ids


def _rule_identity(rule: dict[str, Any]) -> str:
    return str(rule.get("rule_id") or rule.get("id") or id(rule)).strip()


def _first_ref_on_table(
    ref_ids: list[str],
    *,
    table_name: str,
    compile_context: StepCompileContext,
    exclude_ref_ids: set[str],
) -> str:
    for ref_id in ref_ids:
        if ref_id in exclude_ref_ids:
            continue
        source = _bound_source_for_ref_id(ref_id, compile_context)
        if source and source[0] == table_name:
            return ref_id
    return ""


def _compile_aggregate_rules(
    write_step: dict[str, Any],
    mappings: list[dict[str, Any]],
    output_specs: list[dict[str, Any]],
    business_rules: list[dict[str, Any]],
    *,
    source_refs: dict[str, dict[str, Any]],
    compile_context: StepCompileContext,
    schema_step: dict[str, Any] | None,
) -> set[str]:
    compiled_outputs: set[str] = set()
    for rule in business_rules:
        if str(rule.get("type") or "").strip() != "aggregate":
            continue
        if not _rule_applies_to_step(rule, source_refs=source_refs, compile_context=compile_context):
            continue
        plan = _build_aggregate_plan(rule, output_specs, compile_context)
        if not plan:
            description = str(rule.get("description") or rule.get("rule_id") or "未命名聚合规则").strip()
            raise ValueError(f"aggregate 规则无法编译为可执行 DSL: {description}")
        _ensure_aggregate_entry(write_step, plan)
        linked_specs = _output_specs_for_rule(rule, output_specs)
        if not linked_specs:
            continue
        for spec in linked_specs:
            target_field = str(spec.get("name") or "").strip()
            if not target_field:
                continue
            source_ref_ids = set(_text_list(spec.get("source_ref_ids")))
            if source_ref_ids and source_ref_ids <= set(plan.group_ref_ids):
                group_ref_id = next((ref_id for ref_id in plan.group_ref_ids if ref_id in source_ref_ids), "")
                source_field = _group_field_for_ref_id(group_ref_id, plan)
                value_node = {
                    "type": "source",
                    "source": {"alias": plan.output_alias, "field": source_field},
                }
                data_type = _data_type_for_ref_id(group_ref_id, compile_context)
            else:
                value_node = {
                    "type": "source",
                    "source": {"alias": plan.output_alias, "field": plan.aggregation_alias},
                }
                data_type = "decimal"
            mapping = _find_mapping(mappings, target_field)
            if mapping is None:
                mapping = {"target_field": target_field}
                mappings.append(mapping)
            mapping["target_field"] = target_field
            mapping["value"] = value_node
            mapping["field_write_mode"] = str(mapping.get("field_write_mode") or "overwrite")
            if schema_step:
                _ensure_schema_column(schema_step, target_field=target_field, data_type=data_type)
            compiled_outputs.update(_output_spec_identity(spec))
    return compiled_outputs


def _build_aggregate_plan(
    rule: dict[str, Any],
    output_specs: list[dict[str, Any]],
    compile_context: StepCompileContext,
) -> AggregateCompilePlan | None:
    params = rule.get("params") if isinstance(rule.get("params"), dict) else {}
    operator = _normalize_aggregate_operator(
        params.get("operator")
        or params.get("function")
        or params.get("aggregate_operator")
    )
    value_ref_id = _first_text_param(
        params,
        ("value_ref_id", "source_ref_id", "field_ref_id", "aggregate_ref_id", "measure_ref_id"),
    )
    group_ref_ids = _text_list(
        params.get("group_ref_ids")
        or params.get("group_by_ref_ids")
        or params.get("group_ids")
        or params.get("group_refs")
        or params.get("key_ref_ids")
    )
    if not value_ref_id:
        value_ref_id = _infer_aggregate_value_ref_id(rule, output_specs)
    if not group_ref_ids:
        group_ref_ids = _infer_aggregate_group_ref_ids(rule, value_ref_id=value_ref_id)
    if not operator or not value_ref_id:
        return None
    value_source = _bound_source_for_ref_id(value_ref_id, compile_context)
    if not value_source:
        return None
    source_table, value_field, _data_type = value_source
    source_alias = compile_context.alias_for_table(source_table)
    group_fields: list[str] = []
    for ref_id in group_ref_ids:
        group_source = _bound_source_for_ref_id(ref_id, compile_context)
        if not group_source:
            return None
        group_table, group_field, _group_type = group_source
        if group_table != source_table:
            return None
        group_fields.append(group_field)
    rule_id = str(rule.get("rule_id") or rule.get("id") or "aggregate").strip() or "aggregate"
    target_name = _first_output_name_for_rule(rule, output_specs) or str(params.get("alias") or rule_id)
    output_alias = str(params.get("output_alias") or f"agg_{_safe_identifier(rule_id)}").strip()
    aggregation_alias = str(params.get("alias") or f"agg_{target_name}").strip()
    return AggregateCompilePlan(
        rule_id=rule_id,
        output_alias=output_alias,
        source_alias=source_alias,
        source_table=source_table,
        value_ref_id=value_ref_id,
        value_field=value_field,
        operator=operator,
        aggregation_alias=aggregation_alias,
        group_ref_ids=group_ref_ids,
        group_fields=group_fields,
        group_target_fields=[
            _target_field_for_group_ref(ref_id, output_specs, rule) or field
            for ref_id, field in zip(group_ref_ids, group_fields, strict=False)
        ],
    )


def _ensure_aggregate_entry(write_step: dict[str, Any], plan: AggregateCompilePlan) -> None:
    aggregates = [item for item in list(write_step.get("aggregate") or []) if isinstance(item, dict)]
    write_step["aggregate"] = aggregates
    aggregate = next(
        (
            item
            for item in aggregates
            if str(item.get("output_alias") or "").strip() == plan.output_alias
        ),
        None,
    )
    if aggregate is None:
        aggregate = {
            "source_alias": plan.source_alias,
            "output_alias": plan.output_alias,
            "group_fields": plan.group_fields,
            "aggregations": [],
        }
        aggregates.append(aggregate)
    aggregate["source_alias"] = plan.source_alias
    aggregate["output_alias"] = plan.output_alias
    aggregate["group_fields"] = plan.group_fields
    aggregations = [item for item in list(aggregate.get("aggregations") or []) if isinstance(item, dict)]
    aggregate["aggregations"] = aggregations
    existing = next(
        (
            item
            for item in aggregations
            if str(item.get("alias") or "").strip() == plan.aggregation_alias
        ),
        None,
    )
    aggregation_spec = {
        "field": plan.value_field,
        "operator": plan.operator,
        "alias": plan.aggregation_alias,
    }
    if existing is None:
        aggregations.append(aggregation_spec)
    else:
        existing.update(aggregation_spec)
    if not str(write_step.get("row_write_mode") or "").strip():
        write_step["row_write_mode"] = "upsert"

    match = write_step.get("match") if isinstance(write_step.get("match"), dict) else {}
    match_sources = [item for item in list(match.get("sources") or []) if isinstance(item, dict)]
    if not plan.group_fields:
        if match_sources:
            kept_sources = [
                item
                for item in match_sources
                if str(item.get("alias") or "").strip() != plan.output_alias
            ]
            if kept_sources:
                match["sources"] = kept_sources
                write_step["match"] = match
            else:
                write_step.pop("match", None)
        return

    write_step["match"] = match
    match["sources"] = match_sources
    match_source = next(
        (
            item
            for item in match_sources
            if str(item.get("alias") or "").strip() == plan.output_alias
        ),
        None,
    )
    if match_source is None:
        match_source = {"alias": plan.output_alias, "keys": []}
        match_sources.append(match_source)
    match_source["alias"] = plan.output_alias
    match_source["keys"] = [
        {"field": field, "target_field": target_field}
        for field, target_field in zip(plan.group_fields, plan.group_target_fields, strict=False)
    ]


def _output_specs_for_rule(
    rule: dict[str, Any],
    output_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
    output_ids = set(_text_list(rule.get("output_ids")))
    params = rule.get("params") if isinstance(rule.get("params"), dict) else {}
    group_ref_ids = set(_text_list(
        params.get("group_ref_ids")
        or params.get("group_by_ref_ids")
        or params.get("group_ids")
        or params.get("group_refs")
        or params.get("key_ref_ids")
    ))
    related_ref_ids = set(_text_list(rule.get("related_ref_ids"))) | _collect_ref_ids_from_node_to_set(params)
    result: list[dict[str, Any]] = []
    for spec in output_specs:
        spec_identity = _output_spec_identity(spec)
        spec_rule_ids = set(_text_list(spec.get("rule_ids")))
        spec_refs = set(_text_list(spec.get("source_ref_ids")))
        if rule_id and rule_id in spec_rule_ids:
            result.append(spec)
            continue
        if output_ids and output_ids & spec_identity:
            result.append(spec)
            continue
        if group_ref_ids and spec_refs and spec_refs <= group_ref_ids:
            result.append(spec)
            continue
        if not output_ids and related_ref_ids and spec_refs and related_ref_ids & spec_refs:
            result.append(spec)
    return result


def _output_linked_business_rules(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
    *,
    rule_types: set[str],
) -> list[dict[str, Any]]:
    spec_identity = _output_spec_identity(spec)
    spec_rule_ids = set(_text_list(spec.get("rule_ids")))
    spec_refs = set(_text_list(spec.get("source_ref_ids")))
    linked: list[dict[str, Any]] = []
    for rule in business_rules:
        if str(rule.get("type") or "").strip() not in rule_types:
            continue
        rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
        rule_output_ids = set(_text_list(rule.get("output_ids")))
        rule_refs = set(_text_list(rule.get("related_ref_ids"))) | _collect_ref_ids_from_node_to_set(rule.get("params"))
        if rule_id and rule_id in spec_rule_ids:
            linked.append(rule)
            continue
        if spec_identity and rule_output_ids and spec_identity & rule_output_ids:
            linked.append(rule)
            continue
        if not rule_output_ids and spec_refs and rule_refs and spec_refs & rule_refs:
            linked.append(rule)
    return linked


def _select_join_value_ref_id(
    source_ref_ids: list[str],
    linked_rules: list[dict[str, Any]],
    compile_context: StepCompileContext,
) -> str:
    for ref_id in source_ref_ids:
        source = _bound_source_for_ref_id(ref_id, compile_context)
        binding = compile_context.binding_map.get(ref_id) or {}
        usage = str(binding.get("usage") or binding.get("role") or "").strip()
        if source and usage != "lookup_key":
            return ref_id
    for ref_id in source_ref_ids:
        if _bound_source_for_ref_id(ref_id, compile_context):
            return ref_id
    for rule in linked_rules:
        for ref_id in _text_list(rule.get("related_ref_ids")):
            source = _bound_source_for_ref_id(ref_id, compile_context)
            binding = compile_context.binding_map.get(ref_id) or {}
            usage = str(binding.get("usage") or binding.get("role") or "").strip()
            if source and usage != "lookup_key":
                return ref_id
    for rule in linked_rules:
        for ref_id in _text_list(rule.get("related_ref_ids")):
            if _bound_source_for_ref_id(ref_id, compile_context):
                return ref_id
    return ""


def _current_row_alias_candidates(
    write_step: dict[str, Any],
    compile_context: StepCompileContext,
    *,
    output_specs: list[dict[str, Any]],
    current_target_field: str,
) -> list[str]:
    aliases: list[str] = []
    match_sources = [
        item
        for item in list((write_step.get("match") or {}).get("sources") or [])
        if isinstance(item, dict)
    ]
    for source in match_sources:
        alias = str(source.get("alias") or "").strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    for aggregate in [item for item in list(write_step.get("aggregate") or []) if isinstance(item, dict)]:
        alias = str(aggregate.get("output_alias") or "").strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    if compile_context.default_alias and compile_context.default_alias not in aliases:
        aliases.append(compile_context.default_alias)
    for source in [item for item in list(write_step.get("sources") or []) if isinstance(item, dict)]:
        alias = str(source.get("alias") or "").strip()
        if alias and alias not in aliases:
            aliases.append(alias)

    output_names = {
        str(spec.get("name") or "").strip()
        for spec in output_specs
        if isinstance(spec, dict) and str(spec.get("name") or "").strip()
    }
    mapping_aliases = _aliases_used_by_mappings_except(write_step, current_target_field)
    direct_output_aliases = _direct_output_aliases_except(
        output_specs,
        compile_context,
        current_target_field=current_target_field,
    )
    match_target_aliases = _match_aliases_targeting_output_fields(write_step, output_names)
    aggregate_aliases = {
        str(item.get("output_alias") or "").strip()
        for item in list(write_step.get("aggregate") or [])
        if isinstance(item, dict) and str(item.get("output_alias") or "").strip()
    }
    alias_order = {alias: index for index, alias in enumerate(aliases)}

    def score(alias: str) -> tuple[int, int]:
        value = 0
        if alias in mapping_aliases:
            value += 100
        if alias in direct_output_aliases:
            value += 70
        if alias in match_target_aliases:
            value += 50
        if alias in aggregate_aliases:
            value += 20
        return value, -alias_order.get(alias, 0)

    return sorted(aliases, key=score, reverse=True)


def _direct_output_aliases_except(
    output_specs: list[dict[str, Any]],
    compile_context: StepCompileContext,
    *,
    current_target_field: str,
) -> set[str]:
    aliases: set[str] = set()
    for spec in output_specs:
        if not isinstance(spec, dict):
            continue
        if str(spec.get("name") or "").strip() == current_target_field:
            continue
        kind = str(spec.get("kind") or "").strip().lower()
        source_ref_ids = _text_list(spec.get("source_ref_ids"))
        if kind not in {"passthrough", "rename", "unknown"} or len(source_ref_ids) != 1:
            continue
        source = _bound_source_for_ref_id(source_ref_ids[0], compile_context)
        if not source:
            continue
        aliases.add(compile_context.alias_for_table(source[0]))
    return aliases


def _aliases_used_by_mappings_except(write_step: dict[str, Any], target_field: str) -> set[str]:
    aliases: set[str] = set()
    for mapping in [item for item in list(write_step.get("mappings") or []) if isinstance(item, dict)]:
        if str(mapping.get("target_field") or "").strip() == target_field:
            continue
        aliases.update(_collect_value_source_aliases(mapping.get("value")))
        aliases.update(_collect_value_source_aliases(mapping.get("bindings")))
    return aliases


def _match_aliases_targeting_output_fields(write_step: dict[str, Any], output_names: set[str]) -> set[str]:
    aliases: set[str] = set()
    for source in [
        item
        for item in list((write_step.get("match") or {}).get("sources") or [])
        if isinstance(item, dict)
    ]:
        alias = str(source.get("alias") or "").strip()
        if not alias:
            continue
        target_fields = {
            str(key.get("target_field") or "").strip()
            for key in list(source.get("keys") or [])
            if isinstance(key, dict) and str(key.get("target_field") or "").strip()
        }
        if target_fields & output_names:
            aliases.add(alias)
    return aliases


def _table_for_current_alias(
    alias: str,
    write_step: dict[str, Any],
    compile_context: StepCompileContext,
) -> str:
    table_by_alias = {source_alias: table for table, source_alias in compile_context.alias_by_table.items()}
    if alias in table_by_alias:
        return table_by_alias[alias]
    for aggregate in [item for item in list(write_step.get("aggregate") or []) if isinstance(item, dict)]:
        output_alias = str(aggregate.get("output_alias") or "").strip()
        if output_alias != alias:
            continue
        source_alias = str(aggregate.get("source_alias") or "").strip()
        return table_by_alias.get(source_alias, source_alias)
    return table_by_alias.get(compile_context.default_alias, "")


def _field_available_on_current_alias(
    field_name: str,
    alias: str,
    write_step: dict[str, Any],
) -> str:
    for aggregate in [item for item in list(write_step.get("aggregate") or []) if isinstance(item, dict)]:
        output_alias = str(aggregate.get("output_alias") or "").strip()
        if output_alias != alias:
            continue
        group_fields = {
            str(item).strip()
            for item in list(aggregate.get("group_fields") or [])
            if str(item).strip()
        }
        return field_name if field_name in group_fields else ""
    return field_name


def _first_output_name_for_rule(rule: dict[str, Any], output_specs: list[dict[str, Any]]) -> str:
    for spec in _output_specs_for_rule(rule, output_specs):
        source_ref_ids = set(_text_list(spec.get("source_ref_ids")))
        params = rule.get("params") if isinstance(rule.get("params"), dict) else {}
        value_ref_id = _first_text_param(
            params,
            ("value_ref_id", "source_ref_id", "field_ref_id", "aggregate_ref_id", "measure_ref_id"),
        )
        if value_ref_id and value_ref_id in source_ref_ids:
            return str(spec.get("name") or "").strip()
    linked = _output_specs_for_rule(rule, output_specs)
    return str((linked[0] if linked else {}).get("name") or "").strip()


def _infer_aggregate_value_ref_id(rule: dict[str, Any], output_specs: list[dict[str, Any]]) -> str:
    linked_specs = _output_specs_for_rule(rule, output_specs)
    for spec in linked_specs:
        if str(spec.get("kind") or "").strip() != "aggregate":
            continue
        refs = _text_list(spec.get("source_ref_ids"))
        if len(refs) == 1:
            return refs[0]
    return ""


def _infer_aggregate_group_ref_ids(rule: dict[str, Any], *, value_ref_id: str) -> list[str]:
    return [
        ref_id
        for ref_id in _text_list(rule.get("related_ref_ids"))
        if ref_id and ref_id != value_ref_id
    ]


def _group_field_for_ref_id(ref_id: str, plan: AggregateCompilePlan) -> str:
    for index, group_ref_id in enumerate(plan.group_ref_ids):
        if group_ref_id == ref_id and index < len(plan.group_fields):
            return plan.group_fields[index]
    return plan.group_fields[0] if plan.group_fields else ""


def _target_field_for_group_ref(
    ref_id: str,
    output_specs: list[dict[str, Any]],
    rule: dict[str, Any],
) -> str:
    linked_specs = _output_specs_for_rule(rule, output_specs)
    for spec in linked_specs:
        refs = set(_text_list(spec.get("source_ref_ids")))
        if ref_id in refs:
            target_field = str(spec.get("name") or "").strip()
            if target_field:
                return target_field
    return ""


def _bound_source_for_ref_id(
    ref_id: str,
    compile_context: StepCompileContext,
) -> tuple[str, str, str] | None:
    binding = compile_context.binding_map.get(ref_id)
    selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
    if not isinstance(selected_field, dict):
        return None
    field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
    table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
    if not field_name:
        return None
    data_type = str(compile_context.meta_for_field(table_name, field_name).get("data_type") or "string")
    return table_name, field_name, data_type


def _data_type_for_ref_id(ref_id: str, compile_context: StepCompileContext) -> str:
    source = _bound_source_for_ref_id(ref_id, compile_context)
    return source[2] if source else "string"


def _output_spec_identity(spec: dict[str, Any]) -> set[str]:
    return {
        text
        for text in (
            str(spec.get("output_id") or spec.get("id") or "").strip(),
            str(spec.get("name") or "").strip(),
        )
        if text
    }


def _normalize_aggregate_operator(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "total": "sum",
        "summation": "sum",
        "minimum": "min",
    }
    text = aliases.get(text, text)
    return text if text in AGGREGATE_OPERATORS else ""


def _first_text_param(params: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in list(value or []) if str(item).strip()]


def _collect_ref_ids_from_node_to_set(value: Any) -> set[str]:
    ref_ids: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key.endswith("ref_id") or key in {"ref_id", "source_ref_id", "value_ref_id", "field_ref_id"}:
                    text = str(item or "").strip()
                    if text:
                        ref_ids.add(text)
                elif key.endswith("ref_ids") and isinstance(item, list):
                    ref_ids.update(_text_list(item))
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return ref_ids


def _safe_identifier(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "")).strip("_").lower()
    return text or "aggregate"


def _should_compile_output_spec(spec: dict[str, Any]) -> bool:
    kind = str(spec.get("kind") or "").strip().lower()
    source_ref_ids = [
        str(item).strip()
        for item in list(spec.get("source_ref_ids") or [])
        if str(item).strip()
    ]
    expression = spec.get("expression") if isinstance(spec.get("expression"), dict) else None
    if kind in {"passthrough", "rename", "unknown"}:
        return len(source_ref_ids) == 1
    if kind in {"formula", "constant"}:
        return expression is not None
    if kind in {"lookup", "join_derived"}:
        return expression is not None or bool(source_ref_ids) or bool(spec.get("rule_ids"))
    return False


def _compile_filter_rules(
    business_rules: list[dict[str, Any]],
    *,
    source_refs: dict[str, dict[str, Any]],
    compile_context: StepCompileContext,
) -> dict[str, Any] | None:
    compiled_fragments: list[CompiledFormulaFragment] = []
    for rule in business_rules:
        if str(rule.get("type") or "").strip() != "filter":
            continue
        predicate = rule.get("predicate") if isinstance(rule.get("predicate"), dict) else None
        if not predicate:
            continue
        if not _rule_applies_to_step(rule, source_refs=source_refs, compile_context=compile_context):
            continue
        compiled = _compile_predicate_fragment(predicate, compile_context)
        if not compiled:
            description = str(rule.get("description") or rule.get("rule_id") or "未命名过滤规则").strip()
            raise ValueError(f"filter 规则无法编译为可执行 DSL: {description}")
        compiled_fragments.append(compiled)

    if not compiled_fragments:
        return None

    expr = " and ".join(f"({item.expr})" for item in compiled_fragments if item.expr)
    bindings: dict[str, Any] = {}
    for item in compiled_fragments:
        bindings.update(item.bindings)
    return {
        "type": "formula",
        "expr": expr,
        "bindings": bindings,
    }


def _rule_applies_to_step(
    rule: dict[str, Any],
    *,
    source_refs: dict[str, dict[str, Any]],
    compile_context: StepCompileContext,
) -> bool:
    ref_ids = _collect_ref_ids_from_rule(rule)
    if not ref_ids:
        return True
    for ref_id in ref_ids:
        binding = compile_context.binding_map.get(ref_id)
        selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
        if not isinstance(selected_field, dict):
            return False
        table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
        if table_name and table_name not in compile_context.alias_by_table:
            return False
    return True


def _collect_ref_ids_from_rule(rule: dict[str, Any]) -> set[str]:
    collected: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            ref_id = str(value.get("ref_id") or "").strip()
            if ref_id:
                collected.add(ref_id)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(rule.get("predicate"))
    visit(rule.get("expression"))
    collected.update(_collect_ref_ids_from_node_to_set(rule.get("params")))
    for item in list(rule.get("related_ref_ids") or []):
        text = str(item).strip()
        if text:
            collected.add(text)
    return collected


def _compile_expression_value(
    expression: dict[str, Any],
    compile_context: StepCompileContext,
    *,
    ref_resolver: Any = None,
) -> tuple[dict[str, Any] | None, str]:
    op = str(expression.get("op") or "").strip()
    if op == "ref":
        ref_id = str(expression.get("ref_id") or "").strip()
        if ref_resolver:
            resolved = ref_resolver(ref_id, False)
            if resolved:
                return _formula_fragment_value_node(resolved), resolved.data_type
        source_node, data_type = _binding_source_node(ref_id, compile_context)
        return (source_node, data_type) if source_node else (None, "string")

    if op == "constant":
        return {
            "type": "formula",
            "expr": _literal_expr(expression.get("value")),
        }, _infer_constant_type(expression.get("value"))

    if op == "function":
        function_node, data_type = _compile_runtime_function_node(expression, compile_context)
        return function_node, data_type

    compiled = _compile_expression_fragment(
        expression,
        compile_context,
        numeric_context=False,
        ref_resolver=ref_resolver,
    )
    if not compiled:
        return None, "string"
    return {
        "type": "formula",
        "expr": compiled.expr,
        **({"bindings": compiled.bindings} if compiled.bindings else {}),
    }, compiled.data_type


def _compile_expression_fragment(
    expression: dict[str, Any],
    compile_context: StepCompileContext,
    *,
    numeric_context: bool,
    ref_resolver: Any = None,
) -> CompiledFormulaFragment | None:
    op = str(expression.get("op") or "").strip()
    if op == "ref":
        ref_id = str(expression.get("ref_id") or "").strip()
        if ref_resolver:
            resolved = ref_resolver(ref_id, numeric_context)
            if resolved:
                return resolved
        return _compile_ref_fragment(ref_id, compile_context, numeric_context=numeric_context)

    if op == "constant":
        value = expression.get("value")
        return CompiledFormulaFragment(
            expr=_literal_expr(value, numeric_context=numeric_context),
            bindings={},
            data_type="decimal" if numeric_context and _is_numeric_literal(value) else _infer_constant_type(value),
            value_kind="constant",
        )

    if op in ARITHMETIC_OPERATORS:
        operands = [
            item
            for item in list(expression.get("operands") or [])
            if isinstance(item, dict)
        ]
        compiled_operands = [
            compiled
            for operand in operands
            if (
                compiled := _compile_expression_fragment(
                    operand,
                    compile_context,
                    numeric_context=op != "concat",
                    ref_resolver=ref_resolver,
                )
            ) is not None
        ]
        if len(compiled_operands) < 2:
            return None
        expr = compiled_operands[0].expr
        bindings: dict[str, Any] = {}
        bindings.update(compiled_operands[0].bindings)
        for operand in compiled_operands[1:]:
            expr = f"({expr} {ARITHMETIC_OPERATORS[op]} {operand.expr})"
            bindings.update(operand.bindings)
        return CompiledFormulaFragment(
            expr=expr,
            bindings=bindings,
            data_type="decimal" if op != "concat" else "string",
            value_kind="expression",
        )

    if op == "function":
        function_name = str(expression.get("name") or "").strip()
        if function_name in INLINE_FORMULA_FUNCTIONS:
            args = [
                compiled
                for item in list(expression.get("args") or [])
                if isinstance(item, dict)
                if (
                    compiled := _compile_expression_fragment(
                        item,
                        compile_context,
                        numeric_context=False,
                        ref_resolver=ref_resolver,
                    )
                ) is not None
            ]
            if function_name == "is_null" and len(args) == 1:
                return CompiledFormulaFragment(
                    expr=f"is_null({args[0].expr})",
                    bindings=_merge_bindings(args),
                    data_type="boolean",
                    value_kind="expression",
                )
            if function_name == "coalesce" and args:
                return CompiledFormulaFragment(
                    expr=f"coalesce({', '.join(item.expr for item in args)})",
                    bindings=_merge_bindings(args),
                    data_type=args[0].data_type,
                    value_kind="expression",
                )
        function_node, data_type = _compile_runtime_function_node(expression, compile_context)
        if function_node:
            token = compile_context.allocate_token(function_name)
            return CompiledFormulaFragment(
                expr=f"{{{token}}}",
                bindings={token: function_node},
                data_type=data_type,
                value_kind="function",
            )
        return None

    if op == "conditional":
        when = expression.get("when") if isinstance(expression.get("when"), dict) else None
        then_value = expression.get("then") if isinstance(expression.get("then"), dict) else None
        else_value = expression.get("else") if isinstance(expression.get("else"), dict) else None
        compiled_when = _compile_predicate_fragment(when or {}, compile_context) if when else None
        compiled_then = (
            _compile_expression_fragment(
                then_value or {},
                compile_context,
                numeric_context=False,
                ref_resolver=ref_resolver,
            )
            if then_value
            else None
        )
        compiled_else = (
            _compile_expression_fragment(
                else_value or {},
                compile_context,
                numeric_context=False,
                ref_resolver=ref_resolver,
            )
            if else_value
            else None
        )
        if not compiled_when or not compiled_then:
            return None
        expr = f"({compiled_when.expr} ? {compiled_then.expr} : {(compiled_else.expr if compiled_else else 'None')})"
        bindings = {}
        bindings.update(compiled_when.bindings)
        bindings.update(compiled_then.bindings)
        if compiled_else:
            bindings.update(compiled_else.bindings)
        return CompiledFormulaFragment(
            expr=expr,
            bindings=bindings,
            data_type=compiled_then.data_type if compiled_then.data_type != "unknown" else (compiled_else.data_type if compiled_else else "unknown"),
            value_kind="expression",
        )

    return None


def _compile_predicate_fragment(
    predicate: dict[str, Any],
    compile_context: StepCompileContext,
) -> CompiledFormulaFragment | None:
    op = str(predicate.get("op") or "").strip()
    if op in COMPARE_OPERATORS:
        left = predicate.get("left") if isinstance(predicate.get("left"), dict) else None
        right = predicate.get("right") if isinstance(predicate.get("right"), dict) else None
        if not left or not right:
            return None
        left, right = _align_equality_constant_types(op, left, right, compile_context)
        numeric_context = _predicate_needs_numeric_context(op, left, right, compile_context)
        compiled_left = _compile_expression_fragment(left, compile_context, numeric_context=numeric_context)
        compiled_right = _compile_expression_fragment(right, compile_context, numeric_context=numeric_context)
        if not compiled_left or not compiled_right:
            return None
        return CompiledFormulaFragment(
            expr=f"({compiled_left.expr} {COMPARE_OPERATORS[op]} {compiled_right.expr})",
            bindings={**compiled_left.bindings, **compiled_right.bindings},
            data_type="boolean",
            value_kind="expression",
        )

    if op == "contains":
        raise ValueError("contains 谓词当前无法安全编译为 steps formula，请改为 eq/in 等显式条件")

    if op == "in":
        left = predicate.get("left") if isinstance(predicate.get("left"), dict) else None
        values = [item for item in list(predicate.get("right") or []) if isinstance(item, dict)]
        if not left or not values:
            return None
        compiled_left = _compile_expression_fragment(left, compile_context, numeric_context=False)
        compiled_values = [
            compiled
            for item in values
            if (compiled := _compile_expression_fragment(item, compile_context, numeric_context=False)) is not None
        ]
        if not compiled_left or not compiled_values:
            return None
        expr = " or ".join(f"({compiled_left.expr} == {item.expr})" for item in compiled_values)
        bindings = dict(compiled_left.bindings)
        for item in compiled_values:
            bindings.update(item.bindings)
        return CompiledFormulaFragment(expr=f"({expr})", bindings=bindings, data_type="boolean", value_kind="expression")

    if op in {"and", "or"}:
        operands = [
            item
            for item in list(predicate.get("operands") or [])
            if isinstance(item, dict)
        ]
        compiled_operands = [
            compiled
            for item in operands
            if (compiled := _compile_predicate_fragment(item, compile_context)) is not None
        ]
        if len(compiled_operands) < 2:
            return None
        joiner = " and " if op == "and" else " or "
        return CompiledFormulaFragment(
            expr=f"({joiner.join(item.expr for item in compiled_operands)})",
            bindings=_merge_bindings(compiled_operands),
            data_type="boolean",
            value_kind="expression",
        )

    if op == "not":
        operand = predicate.get("operand") if isinstance(predicate.get("operand"), dict) else None
        compiled_operand = _compile_predicate_fragment(operand or {}, compile_context) if operand else None
        if not compiled_operand:
            return None
        return CompiledFormulaFragment(
            expr=f"(not {compiled_operand.expr})",
            bindings=dict(compiled_operand.bindings),
            data_type="boolean",
            value_kind="expression",
        )

    if op == "exists":
        operand = predicate.get("operand") if isinstance(predicate.get("operand"), dict) else None
        compiled_operand = _compile_expression_fragment(operand or {}, compile_context, numeric_context=False) if operand else None
        if not compiled_operand:
            return None
        return CompiledFormulaFragment(
            expr=f"(not is_null({compiled_operand.expr}))",
            bindings=dict(compiled_operand.bindings),
            data_type="boolean",
            value_kind="expression",
        )

    return None


def _align_equality_constant_types(
    operator: str,
    left: dict[str, Any],
    right: dict[str, Any],
    compile_context: StepCompileContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if operator not in {"eq", "neq"}:
        return left, right
    left_type = _expression_data_type(left, compile_context)
    right_type = _expression_data_type(right, compile_context)
    if left_type in {"string", "date"} and _is_constant_expression(right):
        return left, _copy_constant_with_value(right, _constant_text_value(right.get("value")))
    if right_type in {"string", "date"} and _is_constant_expression(left):
        return _copy_constant_with_value(left, _constant_text_value(left.get("value"))), right
    return left, right


def _is_constant_expression(expression: dict[str, Any]) -> bool:
    return str(expression.get("op") or "").strip() == "constant"


def _copy_constant_with_value(expression: dict[str, Any], value: Any) -> dict[str, Any]:
    copied = dict(expression)
    copied["value"] = value
    return copied


def _constant_text_value(value: Any) -> str:
    return "" if value is None else str(value)


def _compile_ref_fragment(
    ref_id: str,
    compile_context: StepCompileContext,
    *,
    numeric_context: bool,
) -> CompiledFormulaFragment | None:
    binding = compile_context.binding_map.get(ref_id)
    selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
    if not isinstance(selected_field, dict):
        return None
    field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
    table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
    alias = compile_context.alias_for_table(table_name)
    source_node = {
        "type": "source",
        "source": {
            "alias": alias,
            "field": field_name,
        },
    }
    meta = compile_context.meta_for_field(table_name, field_name)
    data_type = str(meta.get("data_type") or "string")
    token = compile_context.allocate_token(ref_id or field_name)
    binding_spec: dict[str, Any] = source_node
    if numeric_context:
        binding_spec = {
            "type": "function",
            "function": "to_decimal",
            "args": {"value": source_node},
        }
        data_type = "decimal"
    return CompiledFormulaFragment(
        expr=f"{{{token}}}",
        bindings={token: binding_spec},
        data_type=data_type,
        value_kind="source",
    )


def _value_node_fragment(
    *,
    ref_id: str,
    field_name: str,
    value_node: dict[str, Any],
    data_type: str,
    numeric_context: bool,
    compile_context: StepCompileContext,
    value_kind: str,
) -> CompiledFormulaFragment:
    token = compile_context.allocate_token(ref_id or field_name)
    binding_spec: dict[str, Any] = value_node
    result_type = data_type or "string"
    if numeric_context:
        binding_spec = {
            "type": "function",
            "function": "to_decimal",
            "args": {"value": value_node},
        }
        result_type = "decimal"
    return CompiledFormulaFragment(
        expr=f"{{{token}}}",
        bindings={token: binding_spec},
        data_type=result_type,
        value_kind=value_kind,
    )


def _formula_fragment_value_node(fragment: CompiledFormulaFragment) -> dict[str, Any]:
    return {
        "type": "formula",
        "expr": fragment.expr,
        **({"bindings": fragment.bindings} if fragment.bindings else {}),
    }


def _compile_runtime_function_node(
    expression: dict[str, Any],
    compile_context: StepCompileContext,
) -> tuple[dict[str, Any] | None, str]:
    function_name = str(expression.get("name") or "").strip()
    if function_name not in RUNTIME_FUNCTIONS:
        return None, "unknown"
    args = [item for item in list(expression.get("args") or []) if isinstance(item, dict)]
    if function_name == "current_date":
        return {"type": "function", "function": "current_date", "args": {}}, "date"
    if function_name == "month_of" and len(args) == 1:
        value_spec, _ = _compile_expression_to_value_spec(args[0], compile_context, numeric_context=False)
        if value_spec:
            return {"type": "function", "function": "month_of", "args": {"date": value_spec}}, "decimal"
    if function_name == "add_months" and len(args) == 2:
        date_spec, _ = _compile_expression_to_value_spec(args[0], compile_context, numeric_context=False)
        months_spec, _ = _compile_expression_to_value_spec(args[1], compile_context, numeric_context=True)
        if date_spec and months_spec:
            return {
                "type": "function",
                "function": "add_months",
                "args": {"date": date_spec, "months": months_spec},
            }, "date"
    if function_name == "fraction_numerator" and len(args) == 1:
        value_spec, _ = _compile_expression_to_value_spec(args[0], compile_context, numeric_context=False)
        if value_spec:
            return {"type": "function", "function": "fraction_numerator", "args": {"value": value_spec}}, "decimal"
    if function_name == "to_decimal" and len(args) == 1:
        value_spec, _ = _compile_expression_to_value_spec(args[0], compile_context, numeric_context=False)
        if value_spec:
            return {"type": "function", "function": "to_decimal", "args": {"value": value_spec}}, "decimal"
    return None, "unknown"


def _compile_expression_to_value_spec(
    expression: dict[str, Any],
    compile_context: StepCompileContext,
    *,
    numeric_context: bool,
) -> tuple[dict[str, Any] | None, str]:
    op = str(expression.get("op") or "").strip()
    if op == "ref":
        ref_id = str(expression.get("ref_id") or "").strip()
        source_node, data_type = _binding_source_node(ref_id, compile_context)
        if not source_node:
            return None, "unknown"
        if numeric_context:
            return {
                "type": "function",
                "function": "to_decimal",
                "args": {"value": source_node},
            }, "decimal"
        return source_node, data_type
    if op == "constant":
        value = expression.get("value")
        return {
            "type": "formula",
            "expr": _literal_expr(value, numeric_context=numeric_context),
        }, "decimal" if numeric_context and _is_numeric_literal(value) else _infer_constant_type(value)
    if op == "function":
        return _compile_runtime_function_node(expression, compile_context)
    compiled = _compile_expression_fragment(expression, compile_context, numeric_context=numeric_context)
    if not compiled:
        return None, "unknown"
    return {
        "type": "formula",
        "expr": compiled.expr,
        **({"bindings": compiled.bindings} if compiled.bindings else {}),
    }, compiled.data_type


def _binding_source_node(ref_id: str, compile_context: StepCompileContext) -> tuple[dict[str, Any] | None, str]:
    binding = compile_context.binding_map.get(ref_id)
    selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
    if not isinstance(selected_field, dict):
        return None, "unknown"
    field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
    table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
    alias = compile_context.alias_for_table(table_name)
    meta = compile_context.meta_for_field(table_name, field_name)
    return {
        "type": "source",
        "source": {"alias": alias, "field": field_name},
    }, str(meta.get("data_type") or "string")


def _alias_by_table(step: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for source in list(step.get("sources") or []):
        if not isinstance(source, dict):
            continue
        table_name = str(source.get("table") or "").strip()
        alias = str(source.get("alias") or table_name).strip()
        if table_name and alias:
            mapping[table_name] = alias
    return mapping


def _default_alias(step: dict[str, Any]) -> str:
    for source in list(step.get("sources") or []):
        if not isinstance(source, dict):
            continue
        alias = str(source.get("alias") or source.get("table") or "").strip()
        if alias:
            return alias
    return ""


def _find_mapping(mappings: list[dict[str, Any]], target_field: str) -> dict[str, Any] | None:
    for mapping in mappings:
        if str(mapping.get("target_field") or "").strip() == target_field:
            return mapping
    return None


def _should_replace_existing_mapping(
    value: Any,
    *,
    replacement_value: Any,
    spec: dict[str, Any],
    alias_by_table: dict[str, str],
    allowed_sources: set[tuple[str, str]],
) -> bool:
    if not isinstance(value, dict):
        return True
    if _contains_value_type(value, "lookup"):
        kind = str(spec.get("kind") or "").strip().lower()
        return kind in {"lookup", "join_derived"} and _contains_value_type(replacement_value, "lookup")
    used_sources = _collect_value_source_fields(value, alias_by_table=alias_by_table)
    if used_sources and not used_sources <= allowed_sources:
        return False
    used_tables = {table for table, _field in used_sources}
    return len(used_tables) <= 1


def _allowed_sources_for_output_spec(
    spec: dict[str, Any],
    compile_context: StepCompileContext,
) -> set[tuple[str, str]]:
    ref_ids = {
        str(item).strip()
        for item in list(spec.get("source_ref_ids") or [])
        if str(item).strip()
    }
    _collect_ref_ids_from_node(spec.get("expression"), ref_ids)
    allowed: set[tuple[str, str]] = set()
    for ref_id in ref_ids:
        binding = compile_context.binding_map.get(ref_id)
        selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
        if not isinstance(selected_field, dict):
            continue
        table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
        field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
        if field_name:
            allowed.add((table_name, field_name))
    return allowed


def _contains_value_type(value: Any, expected_type: str) -> bool:
    if isinstance(value, dict):
        if str(value.get("type") or "").strip() == expected_type:
            return True
        return any(_contains_value_type(item, expected_type) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value_type(item, expected_type) for item in value)
    return False


def _collect_value_source_fields(
    value: Any,
    *,
    alias_by_table: dict[str, str],
) -> set[tuple[str, str]]:
    table_by_alias = {alias: table for table, alias in alias_by_table.items()}
    sources: set[tuple[str, str]] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node_type = str(node.get("type") or "").strip()
            if node_type == "source":
                source = node.get("source") if isinstance(node.get("source"), dict) else {}
                alias = str(source.get("alias") or "").strip()
                field = str(source.get("field") or "").strip()
                if field:
                    sources.add((table_by_alias.get(alias, alias), field))
            elif node_type == "lookup":
                alias = str(node.get("source_alias") or "").strip()
                table = table_by_alias.get(alias, alias)
                value_field = str(node.get("value_field") or "").strip()
                if value_field:
                    sources.add((table, value_field))
                for key in [item for item in list(node.get("keys") or []) if isinstance(item, dict)]:
                    lookup_field = str(key.get("lookup_field") or "").strip()
                    if lookup_field:
                        sources.add((table, lookup_field))
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return sources


def _collect_value_source_aliases(value: Any) -> set[str]:
    aliases: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node_type = str(node.get("type") or "").strip()
            if node_type in {"source", "template_source"}:
                source = node.get("source") if isinstance(node.get("source"), dict) else {}
                alias = str(source.get("alias") or "").strip()
                if alias:
                    aliases.add(alias)
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return aliases


def _prune_unused_match_sources(write_step: dict[str, Any], *, schema_step: dict[str, Any] | None) -> None:
    match = write_step.get("match")
    if not isinstance(match, dict):
        return
    match_sources = [item for item in list(match.get("sources") or []) if isinstance(item, dict)]
    if not match_sources:
        return
    schema_fields = _schema_field_names(schema_step)
    used_aliases = _aliases_used_by_mappings_except(write_step, target_field="")
    kept_sources: list[dict[str, Any]] = []
    for source in match_sources:
        alias = str(source.get("alias") or "").strip()
        if not alias:
            continue
        key_target_fields = {
            str(key.get("target_field") or "").strip()
            for key in list(source.get("keys") or [])
            if isinstance(key, dict) and str(key.get("target_field") or "").strip()
        }
        if alias in used_aliases or (key_target_fields and key_target_fields <= schema_fields):
            kept_sources.append(source)
    if kept_sources:
        match["sources"] = kept_sources
    else:
        write_step.pop("match", None)


def _prune_unused_aggregates(write_step: dict[str, Any]) -> None:
    aggregates = [item for item in list(write_step.get("aggregate") or []) if isinstance(item, dict)]
    if not aggregates:
        return
    match_aliases = {
        str(source.get("alias") or "").strip()
        for source in list((write_step.get("match") or {}).get("sources") or [])
        if isinstance(source, dict) and str(source.get("alias") or "").strip()
    }
    mapping_aliases = _aliases_used_by_mappings_except(write_step, target_field="")
    kept = [
        aggregate
        for aggregate in aggregates
        if str(aggregate.get("output_alias") or "").strip() in (match_aliases | mapping_aliases)
    ]
    if kept:
        write_step["aggregate"] = kept
    else:
        write_step.pop("aggregate", None)


def _schema_field_names(schema_step: dict[str, Any] | None) -> set[str]:
    if not isinstance(schema_step, dict):
        return set()
    schema = schema_step.get("schema")
    if not isinstance(schema, dict):
        return set()
    return {
        str(column.get("name") or "").strip()
        for column in list(schema.get("columns") or [])
        if isinstance(column, dict) and str(column.get("name") or "").strip()
    }


def _collect_ref_ids_from_node(value: Any, ref_ids: set[str]) -> None:
    if isinstance(value, dict):
        ref_id = str(value.get("ref_id") or "").strip()
        if ref_id:
            ref_ids.add(ref_id)
        for item in value.values():
            _collect_ref_ids_from_node(item, ref_ids)
    elif isinstance(value, list):
        for item in value:
            _collect_ref_ids_from_node(item, ref_ids)


def _ensure_schema_column(schema_step: dict[str, Any], *, target_field: str, data_type: str) -> None:
    schema = schema_step.get("schema")
    if not isinstance(schema, dict):
        schema = {}
        schema_step["schema"] = schema
    columns = [item for item in list(schema.get("columns") or []) if isinstance(item, dict)]
    schema["columns"] = columns
    for column in columns:
        if str(column.get("name") or "").strip() != target_field:
            continue
        if not str(column.get("data_type") or "").strip():
            column["data_type"] = data_type or "string"
        return
    columns.append({"name": target_field, "data_type": data_type or "string"})


def _build_field_meta(sources: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, str]]:
    meta: dict[tuple[str, str], dict[str, str]] = {}
    for source in list(sources or []):
        if not isinstance(source, dict):
            continue
        table_name = str(
            source.get("table_name")
            or source.get("resource_key")
            or source.get("dataset_code")
            or source.get("dataset_name")
            or source.get("source_id")
            or ""
        ).strip()
        for field in list(source.get("fields") or []):
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("name") or field.get("raw_name") or field.get("field_name") or "").strip()
            if not field_name:
                continue
            meta[(table_name, field_name)] = {
                "data_type": _normalize_data_type(field.get("data_type") or field.get("schema_type")),
                "label": str(field.get("label") or field.get("display_name") or field_name).strip() or field_name,
            }
    return meta


def _normalize_data_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"decimal", "numeric", "number", "float", "double", "real", "int", "integer", "bigint", "smallint"}:
        return "decimal"
    if text in {"date", "datetime", "timestamp", "timestamp with time zone"}:
        return "date"
    return "string"


def _literal_expr(value: Any, *, numeric_context: bool = False) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int | float):
        return str(value)
    if numeric_context and _is_numeric_literal(value):
        return str(value).strip().replace(",", "")
    return repr(str(value))


def _infer_constant_type(value: Any) -> str:
    if isinstance(value, bool):
        return "string"
    if isinstance(value, int | float):
        return "decimal"
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "date"
    if _is_numeric_literal(text):
        return "decimal"
    return "string"


def _is_numeric_literal(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int | float):
        return True
    text = str(value).strip().replace(",", "")
    return bool(re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text))


def _predicate_needs_numeric_context(
    operator: str,
    left: dict[str, Any],
    right: dict[str, Any],
    compile_context: StepCompileContext,
) -> bool:
    if operator in {"gt", "gte", "lt", "lte"}:
        return True
    left_type = _expression_data_type(left, compile_context)
    right_type = _expression_data_type(right, compile_context)
    return "decimal" in {left_type, right_type}


def _expression_data_type(expression: dict[str, Any], compile_context: StepCompileContext) -> str:
    op = str(expression.get("op") or "").strip()
    if op == "constant":
        return _infer_constant_type(expression.get("value"))
    if op == "ref":
        ref_id = str(expression.get("ref_id") or "").strip()
        binding = compile_context.binding_map.get(ref_id)
        selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
        if not isinstance(selected_field, dict):
            return "unknown"
        field_name = str(selected_field.get("name") or selected_field.get("raw_name") or "").strip()
        table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
        meta = compile_context.meta_for_field(table_name, field_name)
        return str(meta.get("data_type") or "unknown")
    if op in {"add", "subtract", "multiply", "divide"}:
        return "decimal"
    if op == "function":
        function_name = str(expression.get("name") or "").strip()
        if function_name in {"current_date", "add_months"}:
            return "date"
        if function_name in {"month_of", "fraction_numerator", "to_decimal"}:
            return "decimal"
    return "unknown"


def _merge_bindings(fragments: list[CompiledFormulaFragment]) -> dict[str, Any]:
    bindings: dict[str, Any] = {}
    for fragment in fragments:
        bindings.update(fragment.bindings)
    return bindings
