"""IR linting for proc rule generation."""

from __future__ import annotations

from typing import Any

from graphs.rule_generation.proc.ir_compiler import RUNTIME_FUNCTIONS
from graphs.rule_generation.proc.understanding import (
    EXPRESSION_OPERATORS,
    OUTPUT_SPEC_KINDS,
    PREDICATE_OPERATORS,
    normalize_output_spec_kind,
)


AGGREGATE_OPERATORS = {"sum", "min"}


def lint_rule_generation_ir(
    understanding: dict[str, Any],
    *,
    field_bindings: list[dict[str, Any]],
    rule_text: str = "",
    source_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate that structured understanding is complete enough to drive DSL generation."""
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    source_references = _safe_dicts((understanding or {}).get("source_references"))
    output_specs = _safe_dicts((understanding or {}).get("output_specs"))
    business_rules = _safe_dicts((understanding or {}).get("business_rules"))
    ref_ids = _source_ref_ids(source_references, errors)
    output_ids = _output_ids(output_specs, errors)
    rule_ids = _business_rule_ids(business_rules, errors)
    binding_by_ref_id = {
        str(item.get("intent_id") or "").strip(): item
        for item in field_bindings
        if isinstance(item, dict) and str(item.get("intent_id") or "").strip()
    }

    if not source_references and not output_specs and not business_rules:
        errors.append({
            "message": "规则 IR 为空，未包含源字段引用、输出字段或业务规则。",
            "reason": "ir_empty",
        })

    for spec in output_specs:
        _lint_output_spec(
            spec,
            ref_ids=ref_ids,
            rule_ids=rule_ids,
            business_rules=business_rules,
            binding_by_ref_id=binding_by_ref_id,
            errors=errors,
        )

    for rule in business_rules:
        _lint_business_rule(
            rule,
            ref_ids=ref_ids,
            output_ids=output_ids,
            binding_by_ref_id=binding_by_ref_id,
            errors=errors,
        )

    _lint_output_rule_lineage(output_specs, business_rules, errors=errors)
    _lint_cross_table_output_lineage(
        output_specs,
        business_rules,
        binding_by_ref_id=binding_by_ref_id,
        errors=errors,
    )
    _lint_lookup_outputs_are_compilable(
        output_specs,
        business_rules,
        binding_by_ref_id=binding_by_ref_id,
        errors=errors,
    )
    _lint_source_passthrough_ir_consistency(
        understanding or {},
        source_references=source_references,
        output_specs=output_specs,
        business_rules=business_rules,
        errors=errors,
    )
    _lint_rule_text_mentioned_field_coverage(
        rule_text,
        source_profiles=source_profiles or [],
        binding_by_ref_id=binding_by_ref_id,
        errors=errors,
    )

    return {
        "success": not errors,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "source_reference_count": len(source_references),
            "output_spec_count": len(output_specs),
            "business_rule_count": len(business_rules),
        },
    }


def _source_ref_ids(source_references: list[dict[str, Any]], errors: list[dict[str, Any]]) -> set[str]:
    ref_ids: set[str] = set()
    for reference in source_references:
        ref_id = str(reference.get("ref_id") or "").strip()
        semantic_name = str(reference.get("semantic_name") or "").strip()
        if not ref_id:
            errors.append({
                "message": f"source_reference“{semantic_name or 'unknown'}”缺少 ref_id。",
                "reason": "source_reference_missing_ref_id",
            })
            continue
        if ref_id in ref_ids:
            errors.append({
                "message": f"source_reference.ref_id 重复: {ref_id}",
                "reason": "source_reference_duplicate_ref_id",
                "ref_id": ref_id,
            })
            continue
        ref_ids.add(ref_id)
    return ref_ids


def _output_ids(output_specs: list[dict[str, Any]], errors: list[dict[str, Any]]) -> set[str]:
    output_ids: set[str] = set()
    for spec in output_specs:
        output_id = str(spec.get("output_id") or spec.get("id") or "").strip()
        name = str(spec.get("name") or "").strip()
        if not output_id:
            continue
        if output_id in output_ids:
            errors.append({
                "message": f"output_spec.output_id 重复: {output_id}",
                "reason": "output_spec_duplicate_output_id",
                "output_id": output_id,
            })
            continue
        output_ids.add(output_id)
        if name:
            output_ids.add(name)
    return output_ids


def _business_rule_ids(business_rules: list[dict[str, Any]], errors: list[dict[str, Any]]) -> set[str]:
    rule_ids: set[str] = set()
    for rule in business_rules:
        rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
        if not rule_id:
            continue
        if rule_id in rule_ids:
            errors.append({
                "message": f"business_rule.rule_id 重复: {rule_id}",
                "reason": "business_rule_duplicate_rule_id",
                "rule_id": rule_id,
            })
            continue
        rule_ids.add(rule_id)
    return rule_ids


def _lint_output_spec(
    spec: dict[str, Any],
    *,
    ref_ids: set[str],
    rule_ids: set[str],
    business_rules: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    name = str(spec.get("name") or "").strip()
    output_id = str(spec.get("output_id") or spec.get("id") or name or "unknown").strip()
    kind = normalize_output_spec_kind(spec.get("kind"))
    source_ref_ids = _text_list(spec.get("source_ref_ids"))
    linked_rule_ids = _text_list(spec.get("rule_ids"))
    expression = spec.get("expression") if isinstance(spec.get("expression"), dict) else None

    if not name:
        errors.append({
            "message": f"output_spec“{output_id}”缺少 name。",
            "reason": "output_spec_missing_name",
            "output_id": output_id,
        })
    if kind not in OUTPUT_SPEC_KINDS:
        errors.append({
            "message": f"output_spec“{name or output_id}”的 kind 不合法。",
            "reason": "output_spec_invalid_kind",
            "output_id": output_id,
        })
        return

    unknown_ref_ids = [ref_id for ref_id in source_ref_ids if ref_id not in ref_ids]
    if unknown_ref_ids:
        errors.append({
            "message": f"output_spec“{name or output_id}”引用了不存在的 source_ref_ids。",
            "reason": "output_spec_unknown_source_ref_id",
            "output_id": output_id,
            "ref_ids": unknown_ref_ids,
        })
    unknown_rule_ids = [rule_id for rule_id in linked_rule_ids if rule_id not in rule_ids]
    if unknown_rule_ids:
        errors.append({
            "message": f"output_spec“{name or output_id}”引用了不存在的 rule_ids。",
            "reason": "output_spec_unknown_rule_id",
            "output_id": output_id,
            "rule_ids": unknown_rule_ids,
        })

    if kind in {"passthrough", "rename"} and len(source_ref_ids) != 1:
        errors.append({
            "message": f"output_spec“{name or output_id}”是直接取数字段，但未明确唯一来源字段。",
            "reason": "output_spec_missing_single_source_ref",
            "output_id": output_id,
        })

    if kind in {"formula", "constant"} and not expression:
        errors.append({
            "message": f"output_spec“{name or output_id}”缺少结构化 expression。",
            "reason": "output_spec_missing_expression",
            "output_id": output_id,
        })

    if kind in {"lookup", "join_derived"} and not expression:
        join_lineage_ref_ids = _lineage_ref_ids_for_output(
            spec,
            business_rules,
            rule_types={"join", "derive", "other"},
        )
        if len(join_lineage_ref_ids) < 2:
            errors.append({
                "message": f"output_spec“{name or output_id}”是关联/查找派生字段，但缺少关联字段或取数字段引用。",
                "reason": "output_spec_insufficient_join_lineage",
                "output_id": output_id,
            })

    linked_aggregate_rules = _aggregate_rules_for_output(spec, business_rules)
    if kind == "aggregate" and not linked_aggregate_rules:
        errors.append({
            "message": f"output_spec“{name or output_id}”是聚合字段，但没有绑定 aggregate business_rule。",
            "reason": "output_spec_missing_aggregate_rule",
            "output_id": output_id,
        })

    if kind == "unknown" and not expression and not source_ref_ids:
        errors.append({
            "message": f"output_spec“{name or output_id}”缺少来源 lineage，无法稳定生成 DSL。",
            "reason": "output_spec_missing_lineage",
            "output_id": output_id,
        })

    if expression:
        _lint_expression(
            expression,
            ref_ids=ref_ids,
            errors=errors,
            context={
                "message_prefix": f"output_spec“{name or output_id}”",
                "reason_prefix": "output_expression",
                "output_id": output_id,
            },
        )

    for ref_id in source_ref_ids:
        binding = binding_by_ref_id.get(ref_id)
        if not binding:
            continue
        if binding.get("must_bind", True) and binding.get("status") == "bound" and not isinstance(binding.get("selected_field"), dict):
            errors.append({
                "message": f"output_spec“{name or output_id}”引用的 ref_id“{ref_id}”缺少绑定字段。",
                "reason": "output_spec_bound_ref_missing_selected_field",
                "output_id": output_id,
                "ref_id": ref_id,
            })


def _lint_business_rule(
    rule: dict[str, Any],
    *,
    ref_ids: set[str],
    output_ids: set[str],
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    rule_id = str(rule.get("rule_id") or rule.get("id") or "unknown").strip()
    rule_type = str(rule.get("type") or "").strip()
    description = str(rule.get("description") or rule_id).strip()
    related_ref_ids = _text_list(rule.get("related_ref_ids"))
    param_ref_ids = _collect_param_ref_ids(rule.get("params"))
    all_rule_ref_ids = sorted(set(related_ref_ids) | param_ref_ids)
    linked_output_ids = _text_list(rule.get("output_ids"))
    unknown_ref_ids = [ref_id for ref_id in all_rule_ref_ids if ref_id not in ref_ids]
    if unknown_ref_ids:
        errors.append({
            "message": f"business_rule“{description}”引用了不存在的 related_ref_ids。",
            "reason": "business_rule_unknown_related_ref_id",
            "rule_id": rule_id,
            "ref_ids": unknown_ref_ids,
        })
    for ref_id in all_rule_ref_ids:
        binding = binding_by_ref_id.get(ref_id)
        if not binding:
            continue
        if binding.get("must_bind", True) and binding.get("status") == "bound" and not isinstance(binding.get("selected_field"), dict):
            errors.append({
                "message": f"business_rule“{description}”引用的 ref_id“{ref_id}”缺少绑定字段。",
                "reason": "business_rule_bound_ref_missing_selected_field",
                "rule_id": rule_id,
                "ref_id": ref_id,
            })
    unknown_output_ids = [output_id for output_id in linked_output_ids if output_id not in output_ids]
    if unknown_output_ids:
        errors.append({
            "message": f"business_rule“{description}”引用了不存在的 output_ids。",
            "reason": "business_rule_unknown_output_id",
            "rule_id": rule_id,
            "output_ids": unknown_output_ids,
        })

    predicate = rule.get("predicate") if isinstance(rule.get("predicate"), dict) else None
    if rule_type == "filter" and not predicate:
        errors.append({
            "message": f"business_rule“{description}”缺少结构化 predicate。",
            "reason": "business_rule_missing_filter_predicate",
            "rule_id": rule_id,
        })
    if rule_type == "aggregate":
        _lint_aggregate_business_rule(
            rule,
            description=description,
            rule_id=rule_id,
            ref_ids=ref_ids,
            errors=errors,
        )
    if rule_type == "join":
        _lint_join_business_rule(
            rule,
            description=description,
            rule_id=rule_id,
            binding_by_ref_id=binding_by_ref_id,
            errors=errors,
        )
    if predicate:
        _lint_predicate(
            predicate,
            ref_ids=ref_ids,
            errors=errors,
            context={
                "message_prefix": f"business_rule“{description}”",
                "reason_prefix": "business_rule_predicate",
                "rule_id": rule_id,
            },
        )


def _lint_output_rule_lineage(
    output_specs: list[dict[str, Any]],
    business_rules: list[dict[str, Any]],
    *,
    errors: list[dict[str, Any]],
) -> None:
    output_refs_by_id: dict[str, set[str]] = {}
    output_identity_by_id: dict[str, set[str]] = {}
    output_rule_ids_by_id: dict[str, set[str]] = {}
    for spec in output_specs:
        output_id = str(spec.get("output_id") or spec.get("id") or "").strip()
        name = str(spec.get("name") or "").strip()
        if not output_id:
            continue
        refs = _collect_ref_ids_from_output_spec(spec)
        output_refs_by_id[output_id] = refs
        output_identity_by_id[output_id] = {item for item in (output_id, name) if item}
        output_rule_ids_by_id[output_id] = set(_text_list(spec.get("rule_ids")))

    for rule in business_rules:
        rule_type = str(rule.get("type") or "").strip()
        if rule_type not in {"join", "aggregate", "derive"}:
            continue
        related_ref_ids = set(_text_list(rule.get("related_ref_ids")))
        if not related_ref_ids:
            continue
        if _rule_has_output_lineage(
            rule,
            output_refs_by_id,
            output_identity_by_id,
            output_rule_ids_by_id,
        ):
            continue
        description = str(rule.get("description") or rule.get("rule_id") or "unknown").strip()
        errors.append({
            "message": f"business_rule“{description}”会影响输出，但没有绑定到具体 output_spec。",
            "reason": "business_rule_missing_output_lineage",
            "rule_id": rule.get("rule_id"),
        })


def _rule_has_output_lineage(
    rule: dict[str, Any],
    output_refs_by_id: dict[str, set[str]],
    output_identity_by_id: dict[str, set[str]],
    output_rule_ids_by_id: dict[str, set[str]],
) -> bool:
    rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
    related_ref_ids = set(_text_list(rule.get("related_ref_ids")))
    linked_output_ids = set(_text_list(rule.get("output_ids")))
    for output_id, output_refs in output_refs_by_id.items():
        if rule_id and rule_id in output_rule_ids_by_id.get(output_id, set()):
            return True
        if linked_output_ids and linked_output_ids & output_identity_by_id.get(output_id, set()):
            return True
        if linked_output_ids:
            continue
        if output_refs and related_ref_ids and output_refs & related_ref_ids:
            return True
    return False


def _lint_cross_table_output_lineage(
    output_specs: list[dict[str, Any]],
    business_rules: list[dict[str, Any]],
    *,
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    output_refs_by_id = {
        str(spec.get("output_id") or spec.get("id") or spec.get("name") or "").strip(): _collect_ref_ids_from_output_spec(spec)
        for spec in output_specs
        if isinstance(spec, dict)
    }
    all_output_refs: set[str] = set()
    for refs in output_refs_by_id.values():
        all_output_refs.update(refs)
    all_output_tables = _tables_for_ref_ids(all_output_refs, binding_by_ref_id)
    if len(all_output_tables) > 1 and not _has_cross_table_rule_for_refs(
        all_output_refs,
        business_rules,
        binding_by_ref_id,
    ):
        errors.append({
            "message": "输出字段引用了多个数据集字段，但 IR 未声明表间关联、查找或聚合关系。",
            "reason": "cross_table_outputs_missing_relation_rule",
            "tables": sorted(all_output_tables),
        })

    for spec in output_specs:
        output_id = str(spec.get("output_id") or spec.get("id") or spec.get("name") or "unknown").strip()
        refs = output_refs_by_id.get(output_id) or set()
        tables = _tables_for_ref_ids(refs, binding_by_ref_id)
        if len(tables) <= 1:
            continue
        if _output_has_cross_table_rule(spec, business_rules, binding_by_ref_id):
            continue
        errors.append({
            "message": f"output_spec“{spec.get('name') or output_id}”跨数据集取数，但缺少绑定到该输出的关联、查找或聚合规则。",
            "reason": "output_spec_cross_table_lineage_missing_rule",
            "output_id": output_id,
            "tables": sorted(tables),
        })


def _lint_lookup_outputs_are_compilable(
    output_specs: list[dict[str, Any]],
    business_rules: list[dict[str, Any]],
    *,
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    aggregate_grains_by_table = _aggregate_grains_by_table(
        business_rules,
        binding_by_ref_id=binding_by_ref_id,
    )
    for spec in output_specs:
        kind = normalize_output_spec_kind(spec.get("kind"))
        linked_rules = _business_rules_for_output(
            spec,
            business_rules,
            rule_types={"join", "lookup", "derive", "other"},
        )
        if kind not in {"lookup", "join_derived", "formula"} or not linked_rules:
            continue
        output_id = str(spec.get("output_id") or spec.get("id") or spec.get("name") or "unknown").strip()
        output_name = str(spec.get("name") or output_id).strip()
        value_ref_ids = _lookup_value_ref_ids(
            spec,
            linked_rules,
            binding_by_ref_id=binding_by_ref_id,
        )
        if kind in {"lookup", "join_derived"} and not value_ref_ids:
            errors.append({
                "message": f"output_spec“{output_name}”是关联/查找派生字段，但缺少明确的取数字段。",
                "reason": "output_spec_missing_lookup_value_ref",
                "output_id": output_id,
            })
            continue
        for rule in linked_rules:
            explicit_join_key_ref_ids = _explicit_join_key_ref_ids(rule)
            join_key_ref_ids = explicit_join_key_ref_ids or [
                ref_id
                for ref_id in _text_list(rule.get("related_ref_ids"))
                if ref_id and ref_id not in value_ref_ids
            ]
            value_tables = _tables_for_ref_ids(value_ref_ids, binding_by_ref_id)
            for key_ref_id in join_key_ref_ids:
                key_table = _table_for_ref_id(key_ref_id, binding_by_ref_id)
                if not key_table or key_table in value_tables:
                    continue
                for grain_ref_ids in aggregate_grains_by_table.get(key_table, []):
                    if key_ref_id in grain_ref_ids:
                        continue
                    errors.append({
                        "message": (
                            f"output_spec“{output_name}”需要用聚合前字段做关联取数，"
                            "但该字段不在聚合后的分组粒度中。"
                        ),
                        "reason": "lookup_key_not_in_aggregate_grain",
                        "output_id": output_id,
                        "ref_id": key_ref_id,
                        "group_ref_ids": sorted(grain_ref_ids),
                    })
                    break


def _aggregate_grains_by_table(
    business_rules: list[dict[str, Any]],
    *,
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> dict[str, list[set[str]]]:
    grains: dict[str, list[set[str]]] = {}
    for rule in business_rules:
        if str(rule.get("type") or "").strip() != "aggregate":
            continue
        params = rule.get("params") if isinstance(rule.get("params"), dict) else {}
        value_ref_id = _first_text_param(
            params,
            ("value_ref_id", "source_ref_id", "field_ref_id", "aggregate_ref_id", "measure_ref_id"),
        )
        group_ref_ids = set(_text_list(
            params.get("group_ref_ids")
            or params.get("group_by_ref_ids")
            or params.get("group_ids")
            or params.get("group_refs")
            or params.get("key_ref_ids")
        ))
        if not value_ref_id or not group_ref_ids:
            continue
        value_table = _table_for_ref_id(value_ref_id, binding_by_ref_id)
        if not value_table:
            continue
        grains.setdefault(value_table, []).append(group_ref_ids)
    return grains


def _lookup_value_ref_ids(
    spec: dict[str, Any],
    linked_rules: list[dict[str, Any]],
    *,
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> set[str]:
    value_ref_ids: set[str] = set()
    explicit_join_key_ref_ids: set[str] = set()
    for rule in linked_rules:
        explicit_join_key_ref_ids.update(_explicit_join_key_ref_ids(rule))
    for ref_id in _collect_ref_ids_from_output_spec(spec):
        if ref_id in explicit_join_key_ref_ids:
            continue
        if _ref_usage(ref_id, binding_by_ref_id) != "lookup_key":
            value_ref_ids.add(ref_id)
    if value_ref_ids:
        return value_ref_ids
    for rule in linked_rules:
        for ref_id in _text_list(rule.get("related_ref_ids")):
            if ref_id in explicit_join_key_ref_ids:
                continue
            if _ref_usage(ref_id, binding_by_ref_id) != "lookup_key":
                value_ref_ids.add(ref_id)
    return value_ref_ids


def _explicit_join_key_ref_ids(rule: dict[str, Any]) -> set[str]:
    params = rule.get("params") if isinstance(rule.get("params"), dict) else {}
    keys = (
        "left_ref_id",
        "right_ref_id",
        "source_ref_id",
        "lookup_ref_id",
        "source_key_ref_id",
        "lookup_key_ref_id",
    )
    ref_ids = {
        str(params.get(key) or "").strip()
        for key in keys
        if str(params.get(key) or "").strip()
    }
    for key in ("key_ref_ids", "join_key_ref_ids", "lookup_key_ref_ids"):
        ref_ids.update(_text_list(params.get(key)))
    return ref_ids


def _table_for_ref_id(
    ref_id: str,
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> str:
    binding = binding_by_ref_id.get(ref_id)
    selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
    if not isinstance(selected_field, dict):
        return ""
    return str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()


def _ref_usage(ref_id: str, binding_by_ref_id: dict[str, dict[str, Any]]) -> str:
    binding = binding_by_ref_id.get(ref_id)
    if not isinstance(binding, dict):
        return ""
    return str(binding.get("usage") or binding.get("role") or "").strip()


def _tables_for_ref_ids(
    ref_ids: set[str],
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> set[str]:
    tables: set[str] = set()
    for ref_id in ref_ids:
        binding = binding_by_ref_id.get(ref_id)
        selected_field = binding.get("selected_field") if isinstance(binding, dict) else None
        if not isinstance(selected_field, dict):
            continue
        table_name = str(selected_field.get("table_name") or selected_field.get("source_table") or "").strip()
        if table_name:
            tables.add(table_name)
    return tables


def _has_cross_table_rule_for_refs(
    ref_ids: set[str],
    business_rules: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> bool:
    for rule in business_rules:
        if str(rule.get("type") or "").strip() not in {"join", "lookup", "derive", "aggregate", "other"}:
            continue
        rule_refs = set(_text_list(rule.get("related_ref_ids"))) | _collect_param_ref_ids(rule.get("params"))
        if len(_tables_for_ref_ids(rule_refs, binding_by_ref_id)) > 1 and (not ref_ids or rule_refs & ref_ids):
            return True
    return False


def _output_has_cross_table_rule(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> bool:
    for rule in _business_rules_for_output(spec, business_rules, rule_types={"join", "lookup", "derive", "aggregate", "other"}):
        rule_refs = set(_text_list(rule.get("related_ref_ids"))) | _collect_param_ref_ids(rule.get("params"))
        if len(_tables_for_ref_ids(rule_refs, binding_by_ref_id)) > 1:
            return True
    return False


def _lint_rule_text_mentioned_field_coverage(
    rule_text: str,
    *,
    source_profiles: list[dict[str, Any]],
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    mentioned_fields = _mentioned_source_fields(rule_text, source_profiles)
    if not mentioned_fields:
        return
    represented_fields = _represented_source_fields(binding_by_ref_id)
    missing_fields = [
        field
        for field in mentioned_fields
        if (field["table_name"], field["name"]) not in represented_fields
    ]
    if not missing_fields:
        return
    errors.append({
        "message": "规则描述中提到的数据集字段没有进入 IR，可能漏掉了过滤、关联、聚合或取数 lineage。",
        "reason": "rule_text_field_mentions_missing_ir_refs",
        "missing_source_fields": missing_fields[:12],
    })


def _lint_source_passthrough_ir_consistency(
    understanding: dict[str, Any],
    *,
    source_references: list[dict[str, Any]],
    output_specs: list[dict[str, Any]],
    business_rules: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    output_mode = str((understanding or {}).get("output_mode") or "").strip()
    if output_mode != "source_passthrough" or output_specs:
        return

    operational_ref_ids = _operational_ref_ids(business_rules)
    unprojected_refs: list[dict[str, Any]] = []
    for reference in source_references:
        ref_id = str(reference.get("ref_id") or "").strip()
        usage = str(reference.get("usage") or "").strip()
        if not ref_id or usage in {"filter_field", "lookup_key", "group_field"}:
            continue
        if ref_id in operational_ref_ids:
            continue
        unprojected_refs.append({
            "ref_id": ref_id,
            "semantic_name": str(reference.get("semantic_name") or "").strip(),
            "usage": usage,
        })

    if not unprojected_refs:
        return
    errors.append({
        "message": "IR 声明了应进入结果语义的源字段，但 output_mode 仍是 source_passthrough 且没有 output_specs。",
        "reason": "source_passthrough_has_unprojected_source_refs",
        "unprojected_source_refs": unprojected_refs[:12],
    })


def _operational_ref_ids(business_rules: list[dict[str, Any]]) -> set[str]:
    ref_ids: set[str] = set()
    for rule in business_rules:
        if not isinstance(rule, dict):
            continue
        ref_ids.update(_text_list(rule.get("related_ref_ids")))
        _collect_ref_ids_from_node(rule.get("predicate"), ref_ids)
        ref_ids.update(_collect_param_ref_ids(rule.get("params")))
    return ref_ids


def _mentioned_source_fields(
    rule_text: str,
    source_profiles: list[dict[str, Any]],
) -> list[dict[str, str]]:
    normalized_rule_text = _normalize_match_text(rule_text)
    if not normalized_rule_text:
        return []
    mentioned: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for profile in source_profiles:
        table_name = str(profile.get("table_name") or "").strip()
        scope_aliases = [
            str(item).strip()
            for item in list(profile.get("scope_aliases") or [])
            if str(item).strip()
        ]
        for candidate in _safe_dicts(profile.get("field_candidates")):
            field_name = str(candidate.get("name") or "").strip()
            if not field_name:
                continue
            field_label = str(candidate.get("label") or field_name).strip() or field_name
            terms = _candidate_match_terms(field_name, field_label)
            match_spans = [
                span
                for term in terms
                for span in _term_spans(normalized_rule_text, term)
            ]
            if not match_spans:
                continue
            key = (table_name, field_name)
            if key in seen:
                continue
            seen.add(key)
            mentioned.append({
                "table_name": table_name,
                "source_aliases": scope_aliases,
                "name": field_name,
                "label": field_label,
                "_match_spans": match_spans,
            })
    return [
        {
            "table_name": item["table_name"],
            "source_aliases": item["source_aliases"],
            "name": item["name"],
            "label": item["label"],
        }
        for item in mentioned
        if not _mentioned_field_is_shadowed(item, mentioned)
    ]


def _term_spans(text: str, term: str) -> list[dict[str, Any]]:
    if not text or not term:
        return []
    spans: list[dict[str, Any]] = []
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return spans
        spans.append({"start": index, "end": index + len(term), "term": term})
        start = index + 1


def _mentioned_field_is_shadowed(
    item: dict[str, Any],
    mentioned: list[dict[str, Any]],
) -> bool:
    spans = [
        span
        for span in list(item.get("_match_spans") or [])
        if isinstance(span, dict)
    ]
    if not spans:
        return False
    other_spans = [
        span
        for other in mentioned
        if other is not item
        for span in list(other.get("_match_spans") or [])
        if isinstance(span, dict)
    ]
    if not other_spans:
        return False
    return all(_span_is_covered_by_longer_span(span, other_spans) for span in spans)


def _span_is_covered_by_longer_span(
    span: dict[str, Any],
    other_spans: list[dict[str, Any]],
) -> bool:
    start = int(span.get("start") or 0)
    end = int(span.get("end") or 0)
    term = str(span.get("term") or "")
    for other in other_spans:
        other_start = int(other.get("start") or 0)
        other_end = int(other.get("end") or 0)
        other_term = str(other.get("term") or "")
        if len(other_term) <= len(term):
            continue
        if other_start <= start and other_end >= end:
            return True
    return False


def _represented_source_fields(
    binding_by_ref_id: dict[str, dict[str, Any]],
) -> set[tuple[str, str]]:
    represented: set[tuple[str, str]] = set()
    for binding in binding_by_ref_id.values():
        if not isinstance(binding, dict):
            continue
        for field in _binding_source_field_candidates(binding):
            table_name = str(field.get("table_name") or field.get("source_table") or "").strip()
            field_name = str(field.get("name") or field.get("raw_name") or "").strip()
            if table_name and field_name:
                represented.add((table_name, field_name))
    return represented


def _binding_source_field_candidates(binding: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    selected_field = binding.get("selected_field")
    if isinstance(selected_field, dict):
        fields.append(selected_field)
    for candidate in _safe_dicts(binding.get("candidates")):
        fields.append(candidate)
    return fields


def _candidate_match_terms(field_name: str, field_label: str) -> set[str]:
    terms: set[str] = set()
    for value in (field_name, field_label):
        normalized = _normalize_match_text(value)
        if _is_specific_match_term(normalized):
            terms.add(normalized)
    return terms


def _is_specific_match_term(value: str) -> bool:
    if not value:
        return False
    if _has_ascii_identifier_char(value):
        return len(value) >= 3
    return len(value) >= 4


def _has_ascii_identifier_char(value: str) -> bool:
    return any(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value)


def _normalize_match_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(char for char in text if char.isalnum() or char == "_")


def _collect_ref_ids_from_output_spec(spec: dict[str, Any]) -> set[str]:
    ref_ids = set(_text_list(spec.get("source_ref_ids")))
    _collect_ref_ids_from_node(spec.get("expression"), ref_ids)
    return ref_ids


def _lineage_ref_ids_for_output(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
    *,
    rule_types: set[str],
) -> set[str]:
    ref_ids = _collect_ref_ids_from_output_spec(spec)
    for rule in _business_rules_for_output(spec, business_rules, rule_types=rule_types):
        ref_ids.update(_text_list(rule.get("related_ref_ids")))
        ref_ids.update(_collect_param_ref_ids(rule.get("params")))
    return ref_ids


def _business_rules_for_output(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
    *,
    rule_types: set[str],
) -> list[dict[str, Any]]:
    output_id = str(spec.get("output_id") or spec.get("id") or "").strip()
    output_name = str(spec.get("name") or "").strip()
    output_keys = {item for item in (output_id, output_name) if item}
    linked_rule_ids = set(_text_list(spec.get("rule_ids")))
    source_ref_ids = _collect_ref_ids_from_output_spec(spec)
    result: list[dict[str, Any]] = []
    for rule in business_rules:
        if str(rule.get("type") or "").strip() not in rule_types:
            continue
        rule_id = str(rule.get("rule_id") or rule.get("id") or "").strip()
        rule_output_ids = set(_text_list(rule.get("output_ids")))
        rule_refs = set(_text_list(rule.get("related_ref_ids"))) | _collect_param_ref_ids(rule.get("params"))
        if rule_id and rule_id in linked_rule_ids:
            result.append(rule)
            continue
        if output_keys and rule_output_ids and output_keys & rule_output_ids:
            result.append(rule)
            continue
        if source_ref_ids and rule_refs and source_ref_ids & rule_refs and not rule_output_ids:
            result.append(rule)
    return result


def _aggregate_rules_for_output(
    spec: dict[str, Any],
    business_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _business_rules_for_output(spec, business_rules, rule_types={"aggregate"})


def _lint_aggregate_business_rule(
    rule: dict[str, Any],
    *,
    description: str,
    rule_id: str,
    ref_ids: set[str],
    errors: list[dict[str, Any]],
) -> None:
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
    if not operator:
        errors.append({
            "message": f"business_rule“{description}”是聚合规则，但缺少合法 operator，必须是 sum/min。",
            "reason": "aggregate_rule_missing_operator",
            "rule_id": rule_id,
        })
    if not value_ref_id:
        errors.append({
            "message": f"business_rule“{description}”是聚合规则，但缺少 value_ref_id。",
            "reason": "aggregate_rule_missing_value_ref",
            "rule_id": rule_id,
        })
    elif value_ref_id not in ref_ids:
        errors.append({
            "message": f"business_rule“{description}”的 value_ref_id 不存在。",
            "reason": "aggregate_rule_unknown_value_ref",
            "rule_id": rule_id,
            "ref_id": value_ref_id,
        })
    if not group_ref_ids:
        errors.append({
            "message": f"business_rule“{description}”是聚合规则，但缺少 group_ref_ids。",
            "reason": "aggregate_rule_missing_group_refs",
            "rule_id": rule_id,
        })
    unknown_group_refs = [ref_id for ref_id in group_ref_ids if ref_id not in ref_ids]
    if unknown_group_refs:
        errors.append({
            "message": f"business_rule“{description}”的 group_ref_ids 引用了不存在的 ref_id。",
            "reason": "aggregate_rule_unknown_group_ref",
            "rule_id": rule_id,
            "ref_ids": unknown_group_refs,
        })


def _lint_join_business_rule(
    rule: dict[str, Any],
    *,
    description: str,
    rule_id: str,
    binding_by_ref_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    related_ref_ids = _text_list(rule.get("related_ref_ids"))
    if len(related_ref_ids) < 2:
        errors.append({
            "message": f"business_rule“{description}”是关联规则，但缺少关联字段或取数字段引用。",
            "reason": "join_rule_insufficient_related_refs",
            "rule_id": rule_id,
        })
        return
    tables = {
        str((binding.get("selected_field") or {}).get("table_name") or "").strip()
        for ref_id in related_ref_ids
        for binding in [binding_by_ref_id.get(ref_id) or {}]
        if isinstance(binding.get("selected_field"), dict)
    }
    if tables and len(tables) < 2:
        errors.append({
            "message": f"business_rule“{description}”是关联规则，但相关字段未覆盖至少两个数据集。",
            "reason": "join_rule_related_refs_not_cross_table",
            "rule_id": rule_id,
        })


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


def _collect_param_ref_ids(value: Any) -> set[str]:
    refs: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key.endswith("ref_id") or key in {"ref_id", "source_ref_id", "value_ref_id", "field_ref_id"}:
                    text = str(item or "").strip()
                    if text:
                        refs.add(text)
                elif key.endswith("ref_ids") and isinstance(item, list):
                    refs.update(_text_list(item))
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return refs


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


def _lint_expression(
    node: dict[str, Any],
    *,
    ref_ids: set[str],
    errors: list[dict[str, Any]],
    context: dict[str, Any],
) -> None:
    op = str(node.get("op") or "").strip()
    if op not in EXPRESSION_OPERATORS:
        errors.append({
            **context,
            "message": f"{context['message_prefix']} 的 expression.op 不合法。",
            "reason": f"{context['reason_prefix']}_invalid_op",
        })
        return
    if op == "ref":
        ref_id = str(node.get("ref_id") or "").strip()
        if not ref_id:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 expression.ref 缺少 ref_id。",
                "reason": f"{context['reason_prefix']}_missing_ref_id",
            })
        elif ref_id not in ref_ids:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 引用了不存在的 ref_id“{ref_id}”。",
                "reason": f"{context['reason_prefix']}_unknown_ref_id",
                "ref_id": ref_id,
            })
        return
    if op == "constant":
        if "value" not in node:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 constant expression 缺少 value。",
                "reason": f"{context['reason_prefix']}_missing_constant_value",
            })
        return
    if op in {"add", "subtract", "multiply", "divide", "concat"}:
        operands = [item for item in list(node.get("operands") or []) if isinstance(item, dict)]
        if len(operands) < 2:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 {op} expression 至少需要两个 operands。",
                "reason": f"{context['reason_prefix']}_insufficient_operands",
            })
            return
        for operand in operands:
            _lint_expression(operand, ref_ids=ref_ids, errors=errors, context=context)
        return
    if op == "function":
        function_name = str(node.get("name") or "").strip()
        if not function_name:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 function expression 缺少 name。",
                "reason": f"{context['reason_prefix']}_missing_function_name",
            })
        elif function_name not in RUNTIME_FUNCTIONS:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 使用了当前执行器不支持的函数“{function_name}”。",
                "reason": f"{context['reason_prefix']}_unsupported_function",
                "function_name": function_name,
            })
        for arg in [item for item in list(node.get("args") or []) if isinstance(item, dict)]:
            _lint_expression(arg, ref_ids=ref_ids, errors=errors, context=context)
        return
    if op == "conditional":
        when = node.get("when") if isinstance(node.get("when"), dict) else None
        then_value = node.get("then") if isinstance(node.get("then"), dict) else None
        else_value = node.get("else") if isinstance(node.get("else"), dict) else None
        if not when or not then_value:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 conditional expression 缺少 when/then。",
                "reason": f"{context['reason_prefix']}_missing_conditional_branch",
            })
            return
        _lint_predicate(when, ref_ids=ref_ids, errors=errors, context=context)
        _lint_expression(then_value, ref_ids=ref_ids, errors=errors, context=context)
        if else_value:
            _lint_expression(else_value, ref_ids=ref_ids, errors=errors, context=context)


def _lint_predicate(
    node: dict[str, Any],
    *,
    ref_ids: set[str],
    errors: list[dict[str, Any]],
    context: dict[str, Any],
) -> None:
    op = str(node.get("op") or "").strip()
    if op not in PREDICATE_OPERATORS:
        errors.append({
            **context,
            "message": f"{context['message_prefix']} 的 predicate.op 不合法。",
            "reason": f"{context['reason_prefix']}_invalid_op",
        })
        return
    if op == "contains":
        errors.append({
            **context,
            "message": f"{context['message_prefix']} 使用了当前执行器不支持的 contains 谓词。",
            "reason": f"{context['reason_prefix']}_unsupported_contains",
        })
        return
    if op in {"eq", "neq", "gt", "gte", "lt", "lte"}:
        left = node.get("left") if isinstance(node.get("left"), dict) else None
        right = node.get("right") if isinstance(node.get("right"), dict) else None
        if not left or not right:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 {op} predicate 缺少 left/right。",
                "reason": f"{context['reason_prefix']}_missing_binary_side",
            })
            return
        _lint_expression(left, ref_ids=ref_ids, errors=errors, context=context)
        _lint_expression(right, ref_ids=ref_ids, errors=errors, context=context)
        return
    if op == "in":
        left = node.get("left") if isinstance(node.get("left"), dict) else None
        right = [item for item in list(node.get("right") or []) if isinstance(item, dict)]
        if not left or not right:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 in predicate 缺少 left/right。",
                "reason": f"{context['reason_prefix']}_missing_in_side",
            })
            return
        _lint_expression(left, ref_ids=ref_ids, errors=errors, context=context)
        for item in right:
            _lint_expression(item, ref_ids=ref_ids, errors=errors, context=context)
        return
    if op in {"and", "or"}:
        operands = [item for item in list(node.get("operands") or []) if isinstance(item, dict)]
        if len(operands) < 2:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 {op} predicate 至少需要两个 operands。",
                "reason": f"{context['reason_prefix']}_insufficient_operands",
            })
            return
        for operand in operands:
            _lint_predicate(operand, ref_ids=ref_ids, errors=errors, context=context)
        return
    if op == "not":
        operand = node.get("operand") if isinstance(node.get("operand"), dict) else None
        if not operand:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 not predicate 缺少 operand。",
                "reason": f"{context['reason_prefix']}_missing_not_operand",
            })
            return
        _lint_predicate(operand, ref_ids=ref_ids, errors=errors, context=context)
        return
    if op == "exists":
        operand = node.get("operand") if isinstance(node.get("operand"), dict) else None
        if not operand:
            errors.append({
                **context,
                "message": f"{context['message_prefix']} 的 exists predicate 缺少 operand。",
                "reason": f"{context['reason_prefix']}_missing_exists_operand",
            })
            return
        _lint_expression(operand, ref_ids=ref_ids, errors=errors, context=context)


def _safe_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in list(value or []) if isinstance(item, dict)]


def _text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in list(value or []) if str(item).strip()]
