"""Deterministic consistency checks between rule IR and generated proc DSL."""

from __future__ import annotations

import re
from typing import Any


def check_ir_dsl_consistency(
    rule_json: dict[str, Any],
    *,
    understanding: dict[str, Any],
    field_bindings: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
    target_table: str = "",
    target_tables: list[str] | None = None,
    rule_text: str = "",
) -> dict[str, Any]:
    """Check that proc DSL does not add, drop, or remap business semantics from IR."""
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    output_specs = _safe_dicts((understanding or {}).get("output_specs"))
    business_rules = _safe_dicts((understanding or {}).get("business_rules"))
    output_by_name = {
        str(item.get("name") or "").strip(): item
        for item in output_specs
        if str(item.get("name") or "").strip()
    }
    binding_by_ref_id = {
        str(item.get("intent_id") or "").strip(): item
        for item in field_bindings
        if isinstance(item, dict) and str(item.get("intent_id") or "").strip()
    }
    known_source_fields = _known_source_fields(sources or [])
    source_passthrough_mode = _is_source_passthrough_mode(
        understanding,
        output_specs=output_specs,
        business_rules=business_rules,
        rule_text=rule_text,
    )
    expected_targets = {
        str(item).strip()
        for item in list(target_tables or [])
        if str(item).strip()
    }
    if target_table:
        expected_targets.add(str(target_table).strip())

    write_steps = [
        step
        for step in _safe_dicts((rule_json or {}).get("steps"))
        if str(step.get("action") or "").strip() == "write_dataset"
        and (not expected_targets or str(step.get("target_table") or "").strip() in expected_targets)
    ]
    schema_steps = [
        step
        for step in _safe_dicts((rule_json or {}).get("steps"))
        if str(step.get("action") or "").strip() == "create_schema"
        and (not expected_targets or str(step.get("target_table") or "").strip() in expected_targets)
    ]
    passthrough_target_fields = _collect_direct_passthrough_target_fields(
        write_steps,
        known_source_fields=known_source_fields,
    ) if source_passthrough_mode else set()

    _check_output_mappings(
        write_steps,
        output_by_name=output_by_name,
        business_rules=business_rules,
        binding_by_ref_id=binding_by_ref_id,
        known_source_fields=known_source_fields,
        source_passthrough_mode=source_passthrough_mode,
        passthrough_target_fields=passthrough_target_fields,
        errors=errors,
    )
    _check_schema_columns(
        schema_steps,
        output_by_name=output_by_name,
        source_passthrough_mode=source_passthrough_mode,
        passthrough_target_fields=passthrough_target_fields,
        errors=errors,
    )
    _check_filter_rules(
        write_steps,
        business_rules=business_rules,
        binding_by_ref_id=binding_by_ref_id,
        errors=errors,
    )
    _check_aggregate_rules(
        write_steps,
        business_rules=business_rules,
        binding_by_ref_id=binding_by_ref_id,
        errors=errors,
    )

    return {
        "success": not errors,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "write_step_count": len(write_steps),
            "output_spec_count": len(output_by_name),
            "output_mode": "source_passthrough" if source_passthrough_mode else "explicit",
            "filter_rule_count": len([rule for rule in business_rules if str(rule.get("type") or "") == "filter"]),
        },
    }


def _is_source_passthrough_mode(
    understanding: dict[str, Any],
    *,
    output_specs: list[dict[str, Any]],
    business_rules: list[dict[str, Any]],
    rule_text: str,
) -> bool:
    output_mode = str(
        (understanding or {}).get("output_mode")
        or (understanding or {}).get("projection_mode")
        or ""
    ).strip().lower()
    if output_mode in {
        "source_passthrough",
        "passthrough",
        "pass_through",
        "passthrough_all",
        "preserve_source_fields",
        "keep_source_fields",
        "all_source_fields",
    }:
        return True
    if output_mode in {"explicit", "explicit_outputs", "projection"}:
        return False
    if not _business_rules_are_row_passthrough_only(business_rules):
        return False
    if _rule_text_has_explicit_output_projection(rule_text):
        return False
    return _output_specs_are_passthrough_like(output_specs)


def _business_rules_are_row_passthrough_only(business_rules: list[dict[str, Any]]) -> bool:
    if not business_rules:
        return False
    row_level_rule_types = {"filter", "sort", "dedupe"}
    return all(str(rule.get("type") or "").strip() in row_level_rule_types for rule in business_rules)


def _output_specs_are_passthrough_like(output_specs: list[dict[str, Any]]) -> bool:
    if not output_specs:
        return True
    for spec in output_specs:
        kind = str(spec.get("kind") or "").strip()
        if kind not in {"", "unknown", "passthrough", "rename"}:
            return False
        if isinstance(spec.get("expression"), dict):
            return False
        if [item for item in list(spec.get("rule_ids") or []) if str(item).strip()]:
            return False
    return True


def _rule_text_has_explicit_output_projection(rule_text: str) -> bool:
    text = str(rule_text or "").strip()
    if not text:
        return False
    if re.search(r"(输出字段|输出列|生成字段|生成列|新增字段|新增列|派生字段|计算字段)", text):
        return True
    for segment in re.split(r"[\n\r,，;；。]+", text):
        item = segment.strip()
        if not item:
            continue
        if re.search(r"(只保留|仅保留|只取|仅取|筛选|过滤).{0,40}(数据|记录|行)?$", item):
            continue
        if re.match(r"^.{1,30}?(?:=|＝|:=|:|：|等于|为).+", item):
            return True
    return False


def _collect_direct_passthrough_target_fields(
    write_steps: list[dict[str, Any]],
    *,
    known_source_fields: set[tuple[str, str]],
) -> set[str]:
    fields: set[str] = set()
    for step in write_steps:
        alias_by_name = _alias_by_name(step)
        for mapping in _safe_dicts(step.get("mappings")):
            target_field = str(mapping.get("target_field") or "").strip()
            source_field = _direct_source_field(mapping.get("value"))
            if not target_field or not source_field:
                continue
            source_table, field_name = source_field
            source_table = alias_by_name.get(source_table, source_table)
            if target_field != field_name:
                continue
            if known_source_fields and (source_table, field_name) not in known_source_fields:
                continue
            fields.add(target_field)
    return fields


def _direct_source_field(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, dict) or str(value.get("type") or "").strip() != "source":
        return None
    source = value.get("source") if isinstance(value.get("source"), dict) else {}
    alias = str(source.get("alias") or "").strip()
    field = str(source.get("field") or "").strip()
    if not field:
        return None
    return alias, field


def _check_output_mappings(
    write_steps: list[dict[str, Any]],
    *,
    output_by_name: dict[str, dict[str, Any]],
    business_rules: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
    known_source_fields: set[tuple[str, str]],
    source_passthrough_mode: bool,
    passthrough_target_fields: set[str],
    errors: list[dict[str, Any]],
) -> None:
    if not output_by_name and not source_passthrough_mode:
        return
    mapped_fields: set[str] = set()
    for step in write_steps:
        step_id = str(step.get("step_id") or "")
        alias_by_name = _alias_by_name(step)
        aggregate_aliases = _aggregate_alias_index(step, alias_by_name=alias_by_name)
        for mapping in _safe_dicts(step.get("mappings")):
            target_field = str(mapping.get("target_field") or "").strip()
            if not target_field:
                continue
            mapped_fields.add(target_field)
            spec = output_by_name.get(target_field)
            if not spec:
                if source_passthrough_mode and target_field in passthrough_target_fields:
                    continue
                errors.append({
                    "step_id": step_id,
                    "target_field": target_field,
                    "reason": "dsl_extra_output_mapping",
                    "message": f"JSON 输出字段“{target_field}”不在 IR output_specs 中。",
                })
                continue
            lineage_ref_ids = _collect_ref_ids_from_output_lineage(
                spec,
                business_rules=business_rules,
            )
            allowed_sources = _allowed_sources_for_ref_ids(
                lineage_ref_ids,
                binding_by_ref_id=binding_by_ref_id,
            )
            used_sources = _collect_source_fields(
                mapping.get("value"),
                alias_by_name=alias_by_name,
                aggregate_aliases=aggregate_aliases,
            )
            unexpected = sorted(used_sources - allowed_sources)
            if unexpected:
                related_ir_sources = _allowed_sources_for_ref_ids(
                    _collect_ref_ids_from_related_business_rules(
                        spec,
                        business_rules=business_rules,
                    ),
                    binding_by_ref_id=binding_by_ref_id,
                )
                all_ir_sources = _allowed_sources_for_ref_ids(
                    set(binding_by_ref_id.keys()),
                    binding_by_ref_id=binding_by_ref_id,
                )
                reason = "dsl_output_mapping_uses_unexpected_source_field"
                if any(
                    source in related_ir_sources
                    or source in all_ir_sources
                    or source in known_source_fields
                    for source in unexpected
                ):
                    reason = "ir_lineage_missing_for_output"
                errors.append({
                    "step_id": step_id,
                    "target_field": target_field,
                    "reason": reason,
                    "message": f"JSON 输出字段“{target_field}”引用了 IR 未声明的源字段。",
                    "missing_source_references": [
                        {"table": table, "field": field}
                        for table, field in unexpected
                        if (table, field) in known_source_fields
                    ],
                    "unexpected_sources": [
                        {"table": table, "field": field}
                        for table, field in unexpected
                    ],
                })
    if source_passthrough_mode:
        return
    for output_name in output_by_name:
        if output_name not in mapped_fields:
            errors.append({
                "target_field": output_name,
                "reason": "dsl_missing_output_mapping",
                "message": f"IR 输出字段“{output_name}”没有对应的 JSON mapping。",
            })


def _check_schema_columns(
    schema_steps: list[dict[str, Any]],
    *,
    output_by_name: dict[str, dict[str, Any]],
    source_passthrough_mode: bool,
    passthrough_target_fields: set[str],
    errors: list[dict[str, Any]],
) -> None:
    if not output_by_name and not source_passthrough_mode:
        return
    schema_columns: set[str] = set()
    for step in schema_steps:
        schema = step.get("schema") if isinstance(step.get("schema"), dict) else {}
        for column in _safe_dicts(schema.get("columns")):
            name = str(column.get("name") or "").strip()
            if name:
                schema_columns.add(name)
                if name not in output_by_name:
                    if source_passthrough_mode and name in passthrough_target_fields:
                        continue
                    errors.append({
                        "step_id": str(step.get("step_id") or ""),
                        "target_field": name,
                        "reason": "dsl_extra_schema_column",
                        "message": f"JSON schema 字段“{name}”不在 IR output_specs 中。",
                    })
    if source_passthrough_mode:
        return
    for output_name in output_by_name:
        if schema_columns and output_name not in schema_columns:
            errors.append({
                "target_field": output_name,
                "reason": "dsl_missing_schema_column",
                "message": f"IR 输出字段“{output_name}”没有对应的 JSON schema 字段。",
            })


def _check_filter_rules(
    write_steps: list[dict[str, Any]],
    *,
    business_rules: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    filter_rules = [
        rule
        for rule in business_rules
        if str(rule.get("type") or "").strip() == "filter"
    ]
    for step in write_steps:
        step_id = str(step.get("step_id") or "")
        filter_node = step.get("filter")
        alias_by_name = _alias_by_name(step)
        aggregate_aliases = _aggregate_alias_index(step, alias_by_name=alias_by_name)
        applicable_filter_rules = [
            rule
            for rule in filter_rules
            if _filter_rule_applies_to_step(
                rule,
                alias_by_name=alias_by_name,
                binding_by_ref_id=binding_by_ref_id,
            )
        ]
        if filter_node is not None and not applicable_filter_rules:
            errors.append({
                "step_id": step_id,
                "reason": "dsl_filter_without_ir_rule",
                "message": "JSON 包含 filter，但 IR 没有过滤业务规则。",
            })
            continue
        if applicable_filter_rules and filter_node is None:
            errors.append({
                "step_id": step_id,
                "reason": "dsl_missing_filter_for_ir_rule",
                "message": "IR 包含过滤业务规则，但 JSON 没有 filter。",
            })
            continue
        if filter_node is None:
            continue
        allowed_sources: set[tuple[str, str]] = set()
        for rule in applicable_filter_rules:
            allowed_sources.update(
                _allowed_sources_for_ref_ids(
                    _collect_ref_ids_from_business_rule(rule),
                    binding_by_ref_id=binding_by_ref_id,
                )
            )
        used_sources = _collect_source_fields(
            filter_node,
            alias_by_name=alias_by_name,
            aggregate_aliases=aggregate_aliases,
        )
        unexpected = sorted(used_sources - allowed_sources)
        if allowed_sources and unexpected:
            errors.append({
                "step_id": step_id,
                "reason": "dsl_filter_uses_unexpected_source_field",
                "message": "JSON filter 引用了 IR 过滤规则未声明的源字段。",
                "unexpected_sources": [
                    {"table": table, "field": field}
                    for table, field in unexpected
                ],
            })


def _check_aggregate_rules(
    write_steps: list[dict[str, Any]],
    *,
    business_rules: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    aggregate_rules = [
        rule
        for rule in business_rules
        if str(rule.get("type") or "").strip() == "aggregate"
    ]
    for step in write_steps:
        step_id = str(step.get("step_id") or "")
        alias_by_name = _alias_by_name(step)
        for aggregate in _safe_dicts(step.get("aggregate")):
            used_sources = _collect_aggregate_source_fields(aggregate, alias_by_name=alias_by_name)
            if not used_sources:
                continue
            if not aggregate_rules:
                errors.append({
                    "step_id": step_id,
                    "reason": "dsl_aggregate_without_ir_rule",
                    "message": "JSON 包含 aggregate，但 IR 没有聚合业务规则。",
                    "unexpected_sources": [
                        {"table": table, "field": field}
                        for table, field in sorted(used_sources)
                    ],
                })
                continue
            matched = False
            for rule in aggregate_rules:
                allowed_sources = _allowed_sources_for_ref_ids(
                    _collect_ref_ids_from_business_rule(rule),
                    binding_by_ref_id=binding_by_ref_id,
                )
                if used_sources <= allowed_sources:
                    matched = True
                    break
            if not matched:
                errors.append({
                    "step_id": step_id,
                    "reason": "dsl_aggregate_uses_unexpected_source_field",
                    "message": "JSON aggregate 引用了 IR 聚合规则未声明的源字段。",
                    "unexpected_sources": [
                        {"table": table, "field": field}
                        for table, field in sorted(used_sources)
                    ],
                })


def _filter_rule_applies_to_step(
    rule: dict[str, Any],
    *,
    alias_by_name: dict[str, str],
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> bool:
    ref_ids = _collect_ref_ids_from_business_rule(rule)
    if not ref_ids:
        return True
    step_tables = {table for table in alias_by_name.values() if table}
    allowed_sources = _allowed_sources_for_ref_ids(ref_ids, binding_by_ref_id=binding_by_ref_id)
    if not allowed_sources:
        return False
    return any(not table or table in step_tables for table, _field in allowed_sources)


def _alias_by_name(step: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for source in _safe_dicts(step.get("sources")):
        alias = str(source.get("alias") or source.get("table") or "").strip()
        table = str(source.get("table") or "").strip()
        if alias:
            aliases[alias] = table
    return aliases


def _allowed_sources_for_ref_ids(
    ref_ids: set[str],
    *,
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> set[tuple[str, str]]:
    sources: set[tuple[str, str]] = set()
    for ref_id in ref_ids:
        binding = binding_by_ref_id.get(ref_id)
        selected = binding.get("selected_field") if isinstance(binding, dict) else None
        if not isinstance(selected, dict):
            continue
        table = str(selected.get("table_name") or selected.get("source_table") or "").strip()
        field = str(selected.get("name") or selected.get("raw_name") or "").strip()
        if field:
            sources.add((table, field))
    return sources


def _known_source_fields(sources: list[dict[str, Any]]) -> set[tuple[str, str]]:
    fields: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        table_name = _source_table_name(source)
        if not table_name:
            continue
        for field_name in _source_field_names(source):
            fields.add((table_name, field_name))
    return fields


def _source_table_name(source: dict[str, Any]) -> str:
    return str(
        source.get("table_name")
        or source.get("resource_key")
        or source.get("dataset_code")
        or source.get("dataset_name")
        or source.get("source_id")
        or ""
    ).strip()


def _source_field_names(source: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    raw_map = source.get("field_label_map")
    if isinstance(raw_map, dict):
        fields.update(str(key).strip() for key in raw_map.keys() if str(key).strip())
    for field in list(source.get("fields") or []):
        if not isinstance(field, dict):
            continue
        field_name = str(
            field.get("name")
            or field.get("raw_name")
            or field.get("field_name")
            or field.get("key")
            or ""
        ).strip()
        if field_name:
            fields.add(field_name)
    for row in list(source.get("sample_rows") or []):
        if isinstance(row, dict):
            fields.update(str(key).strip() for key in row.keys() if str(key).strip())
    return fields


def _collect_ref_ids_from_output_spec(spec: dict[str, Any]) -> set[str]:
    ref_ids = {
        str(item).strip()
        for item in list(spec.get("source_ref_ids") or [])
        if str(item).strip()
    }
    _collect_ref_ids_from_node(spec.get("expression"), ref_ids)
    return ref_ids


def _collect_ref_ids_from_output_lineage(
    spec: dict[str, Any],
    *,
    business_rules: list[dict[str, Any]],
) -> set[str]:
    ref_ids = _collect_ref_ids_from_output_spec(spec)
    for rule in _business_rules_for_output(spec, business_rules=business_rules):
        ref_ids.update(_collect_ref_ids_from_business_rule(rule))
    return ref_ids


def _collect_ref_ids_from_related_business_rules(
    spec: dict[str, Any],
    *,
    business_rules: list[dict[str, Any]],
) -> set[str]:
    ref_ids: set[str] = set()
    output_refs = _collect_ref_ids_from_output_spec(spec)
    output_ids = _output_identity_set(spec)
    explicit_rule_ids = {
        str(item).strip()
        for item in list(spec.get("rule_ids") or [])
        if str(item).strip()
    }
    for rule in business_rules:
        rule_refs = _collect_ref_ids_from_business_rule(rule)
        if not rule_refs:
            continue
        rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
        rule_output_ids = {
            str(item).strip()
            for item in list(rule.get("output_ids") or [])
            if str(item).strip()
        }
        if rule_id in explicit_rule_ids or bool(output_ids & rule_output_ids):
            ref_ids.update(rule_refs)
            continue
        if rule_output_ids:
            continue
        if output_refs & rule_refs:
            ref_ids.update(rule_refs)
    return ref_ids


def _collect_ref_ids_from_business_rule(rule: dict[str, Any]) -> set[str]:
    ref_ids = {
        str(item).strip()
        for item in list(rule.get("related_ref_ids") or [])
        if str(item).strip()
    }
    _collect_ref_ids_from_node(rule.get("predicate"), ref_ids)
    _collect_param_ref_ids(rule.get("params"), ref_ids)
    return ref_ids


def _business_rules_for_output(
    spec: dict[str, Any],
    *,
    business_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output_refs = _collect_ref_ids_from_output_spec(spec)
    output_ids = _output_identity_set(spec)
    explicit_rule_ids = {
        str(item).strip()
        for item in list(spec.get("rule_ids") or [])
        if str(item).strip()
    }
    linked_rules: list[dict[str, Any]] = []
    for rule in business_rules:
        rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
        rule_output_ids = {
            str(item).strip()
            for item in list(rule.get("output_ids") or [])
            if str(item).strip()
        }
        rule_refs = _collect_ref_ids_from_business_rule(rule)
        if rule_id and rule_id in explicit_rule_ids:
            linked_rules.append(rule)
            continue
        if output_ids and rule_output_ids and output_ids & rule_output_ids:
            linked_rules.append(rule)
            continue
        if rule_output_ids:
            continue
        if _is_lineage_rule(rule) and output_refs and rule_refs and output_refs & rule_refs:
            linked_rules.append(rule)
    return linked_rules


def _output_identity_set(spec: dict[str, Any]) -> set[str]:
    return {
        text
        for text in (
            str(spec.get("output_id") or spec.get("id") or "").strip(),
            str(spec.get("name") or "").strip(),
        )
        if text
    }


def _is_lineage_rule(rule: dict[str, Any]) -> bool:
    return str(rule.get("type") or "").strip() in {
        "join",
        "aggregate",
        "derive",
        "filter",
        "validation",
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


def _collect_source_fields(
    value: Any,
    *,
    alias_by_name: dict[str, str],
    aggregate_aliases: dict[str, dict[str, Any]] | None = None,
) -> set[tuple[str, str]]:
    aggregate_aliases = aggregate_aliases or {}
    fields: set[tuple[str, str]] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if str(node.get("type") or "").strip() == "source":
                source = node.get("source") if isinstance(node.get("source"), dict) else {}
                alias = str(source.get("alias") or "").strip()
                field = str(source.get("field") or "").strip()
                if field:
                    fields.add(_source_field_identity(alias, field, alias_by_name, aggregate_aliases))
            if str(node.get("type") or "").strip() == "lookup":
                alias = str(node.get("source_alias") or "").strip()
                value_field = str(node.get("value_field") or "").strip()
                if value_field:
                    fields.add(_source_field_identity(alias, value_field, alias_by_name, aggregate_aliases))
                for key in _safe_dicts(node.get("keys")):
                    lookup_field = str(key.get("lookup_field") or "").strip()
                    if lookup_field:
                        fields.add(_source_field_identity(alias, lookup_field, alias_by_name, aggregate_aliases))
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return fields


def _source_field_identity(
    alias: str,
    field: str,
    alias_by_name: dict[str, str],
    aggregate_aliases: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    aggregate = aggregate_aliases.get(alias)
    if aggregate:
        source_table = str(aggregate.get("source_table") or alias).strip()
        aggregation_fields = aggregate.get("aggregation_fields") if isinstance(aggregate.get("aggregation_fields"), dict) else {}
        group_fields = set(aggregate.get("group_fields") or [])
        if field in aggregation_fields:
            return source_table, str(aggregation_fields[field])
        if field in group_fields:
            return source_table, field
    return alias_by_name.get(alias, alias), field


def _aggregate_alias_index(
    step: dict[str, Any],
    *,
    alias_by_name: dict[str, str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for aggregate in _safe_dicts(step.get("aggregate")):
        source_alias = str(aggregate.get("source_alias") or "").strip()
        output_alias = str(aggregate.get("output_alias") or "").strip()
        if not output_alias:
            continue
        source_table = alias_by_name.get(source_alias, source_alias)
        aggregation_fields = {
            str(item.get("alias") or "").strip(): str(item.get("field") or "").strip()
            for item in _safe_dicts(aggregate.get("aggregations"))
            if str(item.get("alias") or "").strip() and str(item.get("field") or "").strip()
        }
        index[output_alias] = {
            "source_table": source_table,
            "group_fields": {
                str(item).strip()
                for item in list(aggregate.get("group_fields") or [])
                if str(item).strip()
            },
            "aggregation_fields": aggregation_fields,
        }
    return index


def _collect_aggregate_source_fields(
    aggregate: dict[str, Any],
    *,
    alias_by_name: dict[str, str],
) -> set[tuple[str, str]]:
    source_alias = str(aggregate.get("source_alias") or "").strip()
    source_table = alias_by_name.get(source_alias, source_alias)
    fields = {
        (source_table, str(item).strip())
        for item in list(aggregate.get("group_fields") or [])
        if str(item).strip()
    }
    for item in _safe_dicts(aggregate.get("aggregations")):
        field = str(item.get("field") or "").strip()
        if field:
            fields.add((source_table, field))
    return fields


def _collect_param_ref_ids(value: Any, ref_ids: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("ref_id") or key in {"ref_id", "source_ref_id", "value_ref_id", "field_ref_id"}:
                text = str(item or "").strip()
                if text:
                    ref_ids.add(text)
            elif key.endswith("ref_ids") and isinstance(item, list):
                ref_ids.update(str(ref).strip() for ref in item if str(ref).strip())
            _collect_param_ref_ids(item, ref_ids)
    elif isinstance(value, list):
        for item in value:
            _collect_param_ref_ids(item, ref_ids)


def _safe_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in list(value or []) if isinstance(item, dict)]
