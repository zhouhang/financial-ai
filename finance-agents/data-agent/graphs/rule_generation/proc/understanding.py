"""Understanding schema helpers for proc rule generation."""

from __future__ import annotations

import re
from typing import Any


SOURCE_REFERENCE_USAGES: set[str] = {
    "match_key",
    "compare_field",
    "time_field",
    "filter_field",
    "group_field",
    "lookup_key",
    "source_value",
}

OUTPUT_SPEC_KINDS: set[str] = {
    "passthrough",
    "rename",
    "formula",
    "aggregate",
    "lookup",
    "join_derived",
    "constant",
    "unknown",
}

OUTPUT_MODES: set[str] = {
    "explicit",
    "source_passthrough",
    "unspecified",
}

BUSINESS_RULE_TYPES: set[str] = {
    "filter",
    "join",
    "aggregate",
    "derive",
    "validation",
    "sort",
    "dedupe",
    "other",
}

EXPRESSION_OPERATORS: set[str] = {
    "ref",
    "constant",
    "add",
    "subtract",
    "multiply",
    "divide",
    "concat",
    "function",
    "conditional",
}

PREDICATE_OPERATORS: set[str] = {
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "contains",
    "and",
    "or",
    "not",
    "exists",
}


def normalize_understanding(
    understanding: Any,
    *,
    rule_text: str = "",
    target_table: str = "",
) -> dict[str, Any]:
    """Normalize understanding payload into a stable three-layer structure."""
    raw = understanding if isinstance(understanding, dict) else {}
    normalized = {
        "rule_summary": _to_text(
            raw.get("rule_summary")
            or raw.get("summary")
            or raw.get("description")
            or raw.get("rule_text")
            or rule_text,
        ),
        "target_table": _to_text(raw.get("target_table") or target_table),
        "output_mode": normalize_output_mode(raw.get("output_mode") or raw.get("projection_mode")),
        "source_references": [],
        "output_specs": [],
        "business_rules": [],
    }

    source_references = _safe_list(raw.get("source_references"))
    if not source_references:
        source_references = _legacy_field_intents_to_source_references(raw.get("field_intents"))
    normalized_source_references: list[dict[str, Any]] = []
    for index, source_reference in enumerate(source_references, start=1):
        normalized_item = _normalize_source_reference(source_reference, index=index)
        if normalized_item:
            normalized_source_references.append(normalized_item)
    normalized["source_references"] = normalized_source_references

    output_specs = _safe_list(raw.get("output_specs"))
    if not output_specs:
        output_specs = _legacy_field_intents_to_output_specs(raw.get("field_intents"))
    normalized_output_specs: list[dict[str, Any]] = []
    for index, output_spec in enumerate(output_specs, start=1):
        normalized_item = _normalize_output_spec(output_spec, index=index)
        if normalized_item:
            normalized_output_specs.append(normalized_item)
    normalized["output_specs"] = normalized_output_specs

    normalized_business_rules: list[dict[str, Any]] = []
    for index, business_rule in enumerate(_safe_list(raw.get("business_rules")), start=1):
        normalized_item = _normalize_business_rule(business_rule, index=index)
        if normalized_item:
            normalized_business_rules.append(normalized_item)
    normalized["business_rules"] = normalized_business_rules
    _recover_long_numeric_identifiers(normalized, rule_text=rule_text)
    return normalized


def _normalize_source_reference(item: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    semantic_name = _to_text(
        item.get("semantic_name")
        or item.get("mention")
        or item.get("field")
        or item.get("name"),
    )
    usage = normalize_source_reference_usage(item.get("usage") or item.get("role") or item.get("type"))
    if not semantic_name and not usage:
        return None
    return {
        "ref_id": _to_text(item.get("ref_id") or item.get("id") or f"src_ref_{index}"),
        "semantic_name": semantic_name,
        "usage": usage or "source_value",
        "must_bind": _to_bool(item.get("must_bind"), default=True),
        "table_scope": _normalize_text_list(
            item.get("table_scope")
            or item.get("tables")
            or item.get("source_tables"),
        ),
        "candidate_fields": _normalize_candidate_fields(item.get("candidate_fields") or item.get("candidates")),
        "description": _to_text(item.get("description") or item.get("reason")),
        "operator": _to_text(item.get("operator")),
        "value": item.get("value"),
    }


def _normalize_output_spec(item: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = _to_text(item.get("name") or item.get("output_name") or item.get("field"))
    kind = normalize_output_spec_kind(item.get("kind") or item.get("type") or item.get("mode"))
    if not name and not kind:
        return None
    return {
        "output_id": _to_text(item.get("output_id") or item.get("id") or f"out_{index}"),
        "name": name,
        "kind": kind or "unknown",
        "source_ref_ids": _normalize_text_list(
            item.get("source_ref_ids")
            or item.get("depends_on_refs")
            or item.get("refs"),
        ),
        "rule_ids": _normalize_text_list(
            item.get("rule_ids")
            or item.get("lineage_rule_ids")
            or item.get("business_rule_ids")
            or item.get("depends_on_rules"),
        ),
        "expression": _normalize_expression(
            item.get("expression")
            or item.get("expression_ir")
            or item.get("formula_ir"),
        ),
        "expression_hint": _to_text(item.get("expression_hint") or item.get("formula") or item.get("expression")),
        "description": _to_text(item.get("description") or item.get("reason")),
    }


def _normalize_business_rule(item: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    description = _to_text(item.get("description") or item.get("text") or item.get("rule"))
    rule_type = normalize_business_rule_type(item.get("type") or item.get("category"))
    if not description and not rule_type:
        return None
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    return {
        "rule_id": _to_text(item.get("rule_id") or item.get("id") or f"rule_{index}"),
        "type": rule_type or "other",
        "description": description,
        "related_ref_ids": _normalize_text_list(
            item.get("related_ref_ids")
            or item.get("source_ref_ids")
            or item.get("refs"),
        ),
        "output_ids": _normalize_text_list(
            item.get("output_ids")
            or item.get("applies_to_output_ids")
            or item.get("target_output_ids")
            or item.get("output_spec_ids"),
        ),
        "predicate": _normalize_predicate(
            item.get("predicate")
            or item.get("predicate_ir")
            or item.get("condition")
            or item.get("where"),
        ),
        "params": params,
    }


def normalize_source_reference_usage(value: Any) -> str:
    usage = _to_text(value).lower()
    aliases = {
        "join_key": "match_key",
        "key_field": "match_key",
        "date_field": "time_field",
        "filter": "filter_field",
        "field": "source_value",
    }
    usage = aliases.get(usage, usage)
    return usage if usage in SOURCE_REFERENCE_USAGES else ""


def normalize_output_spec_kind(value: Any) -> str:
    kind = _to_text(value).lower()
    aliases = {
        "derived": "join_derived",
        "expression": "formula",
        "calc": "formula",
        "calculated": "formula",
        "agg": "aggregate",
        "lookup_value": "lookup",
        "source": "passthrough",
    }
    kind = aliases.get(kind, kind)
    return kind if kind in OUTPUT_SPEC_KINDS else ""


def normalize_output_mode(value: Any) -> str:
    mode = _to_text(value).lower()
    aliases = {
        "passthrough": "source_passthrough",
        "pass_through": "source_passthrough",
        "passthrough_all": "source_passthrough",
        "preserve_source_fields": "source_passthrough",
        "keep_source_fields": "source_passthrough",
        "original_fields": "source_passthrough",
        "all_source_fields": "source_passthrough",
        "projection": "explicit",
        "explicit_outputs": "explicit",
    }
    mode = aliases.get(mode, mode)
    return mode if mode in OUTPUT_MODES else "unspecified"


def normalize_business_rule_type(value: Any) -> str:
    rule_type = _to_text(value).lower()
    aliases = {
        "calculation": "derive",
        "derive_rule": "derive",
        "filter_rule": "filter",
        "join_rule": "join",
        "group": "aggregate",
        "check": "validation",
    }
    rule_type = aliases.get(rule_type, rule_type)
    return rule_type if rule_type in BUSINESS_RULE_TYPES else ""


def normalize_expression_operator(value: Any) -> str:
    operator = _to_text(value).lower()
    aliases = {
        "+": "add",
        "plus": "add",
        "sum": "add",
        "-": "subtract",
        "minus": "subtract",
        "*": "multiply",
        "x": "multiply",
        "mul": "multiply",
        "/": "divide",
        "div": "divide",
        "||": "concat",
        "append": "concat",
        "field": "ref",
        "field_ref": "ref",
        "source_ref": "ref",
        "reference": "ref",
        "literal": "constant",
        "const": "constant",
        "value": "constant",
        "call": "function",
        "if": "conditional",
        "case": "conditional",
    }
    operator = aliases.get(operator, operator)
    return operator if operator in EXPRESSION_OPERATORS else ""


def normalize_predicate_operator(value: Any) -> str:
    operator = _to_text(value).lower()
    aliases = {
        "=": "eq",
        "==": "eq",
        "equals": "eq",
        "equal": "eq",
        "!=": "neq",
        "<>": "neq",
        "not_equals": "neq",
        ">": "gt",
        ">=": "gte",
        "<": "lt",
        "<=": "lte",
        "include": "contains",
        "has": "contains",
        "all": "and",
        "any": "or",
        "!": "not",
        "not_empty": "exists",
        "not_blank": "exists",
        "non_empty": "exists",
        "non_blank": "exists",
        "is_not_empty": "exists",
        "is_not_blank": "exists",
        "not_null": "exists",
        "non_null": "exists",
        "is_not_null": "exists",
        "present": "exists",
    }
    operator = aliases.get(operator, operator)
    return operator if operator in PREDICATE_OPERATORS else ""


def _legacy_field_intents_to_source_references(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(_safe_list(value), start=1):
        if not isinstance(item, dict):
            continue
        usage = normalize_source_reference_usage(item.get("role") or item.get("usage"))
        if usage == "":
            continue
        items.append({
            "ref_id": _to_text(item.get("intent_id") or item.get("id") or f"src_ref_{index}"),
            "semantic_name": _to_text(item.get("mention") or item.get("field") or item.get("name")),
            "usage": usage,
            "must_bind": usage != "source_value" or bool(item.get("mention") or item.get("field")),
            "candidate_fields": item.get("candidate_fields") or item.get("candidates") or [],
            "operator": _to_text(item.get("operator")),
            "value": item.get("value"),
        })
    return items


def _legacy_field_intents_to_output_specs(value: Any) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index, item in enumerate(_safe_list(value), start=1):
        if not isinstance(item, dict):
            continue
        role = _to_text(item.get("role") or item.get("usage")).lower()
        if role != "output_field":
            continue
        specs.append({
            "output_id": _to_text(item.get("intent_id") or item.get("id") or f"out_{index}"),
            "name": _to_text(item.get("mention") or item.get("field") or item.get("name")),
            "kind": "unknown",
        })
    return specs


def _normalize_candidate_fields(value: Any) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for item in _safe_list(value):
        if isinstance(item, dict):
            raw_name = _to_text(
                item.get("raw_name")
                or item.get("name")
                or item.get("field")
                or item.get("field_name"),
            )
            display_name = _to_text(
                item.get("display_name")
                or item.get("label")
                or item.get("business_name")
                or raw_name,
            )
            source_table = _to_text(
                item.get("source_table")
                or item.get("table_name")
                or item.get("table"),
            )
            reason = _to_text(item.get("reason") or item.get("evidence"))
        else:
            raw_name = _to_text(item)
            display_name = raw_name
            source_table = ""
            reason = ""
        if not raw_name and not display_name:
            continue
        candidates.append({
            "raw_name": raw_name,
            "display_name": display_name or raw_name,
            "source_table": source_table,
            "reason": reason,
        })
    return candidates


def _normalize_expression(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        inferred_op = normalize_expression_operator(
            value.get("op")
            or value.get("operator")
            or value.get("type")
            or value.get("kind"),
        )
        if not inferred_op:
            if _to_text(value.get("ref_id") or value.get("source_ref_id")):
                inferred_op = "ref"
            elif "value" in value and len([key for key in value.keys() if key not in {"description", "reason"}]) == 1:
                inferred_op = "constant"
        if inferred_op == "ref":
            ref_id = _to_text(value.get("ref_id") or value.get("source_ref_id") or value.get("reference_id"))
            if not ref_id:
                return None
            return {"op": "ref", "ref_id": ref_id}
        if inferred_op == "constant":
            return {"op": "constant", "value": _normalize_constant_value(value.get("value"))}
        if inferred_op in {"add", "subtract", "multiply", "divide", "concat"}:
            operands = _safe_list(value.get("operands"))
            if not operands and ("left" in value or "right" in value):
                operands = [value.get("left"), value.get("right")]
            normalized_operands = [
                normalized_operand
                for operand in operands
                if (normalized_operand := _normalize_expression_operand(operand)) is not None
            ]
            if not normalized_operands:
                return None
            return {
                "op": inferred_op,
                "operands": normalized_operands,
            }
        if inferred_op == "function":
            function_name = _to_text(value.get("function") or value.get("name"))
            args = _safe_list(value.get("args") or value.get("arguments"))
            normalized_args = [
                normalized_arg
                for arg in args
                if (normalized_arg := _normalize_expression_operand(arg)) is not None
            ]
            if not function_name:
                return None
            return {
                "op": "function",
                "name": function_name,
                "args": normalized_args,
            }
        if inferred_op == "conditional":
            when = _normalize_predicate(value.get("when") or value.get("predicate") or value.get("condition"))
            then_value = _normalize_expression_operand(value.get("then"))
            else_value = _normalize_expression_operand(value.get("else") or value.get("otherwise"))
            if not when or then_value is None:
                return None
            normalized = {
                "op": "conditional",
                "when": when,
                "then": then_value,
            }
            if else_value is not None:
                normalized["else"] = else_value
            return normalized
    if value in {None, ""}:
        return None
    return {"op": "constant", "value": _normalize_constant_value(value)}


def _normalize_expression_operand(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return _normalize_expression(value)
    if value in {None, ""}:
        return None
    return {"op": "constant", "value": _normalize_constant_value(value)}


def _normalize_predicate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    inferred_op = normalize_predicate_operator(
        value.get("op")
        or value.get("operator")
        or value.get("type")
        or value.get("kind"),
    )
    if not inferred_op:
        if _to_text(value.get("ref_id") or value.get("source_ref_id")) and "value" in value:
            inferred_op = "eq"
        elif isinstance(value.get("conditions") or value.get("clauses") or value.get("predicates"), list):
            inferred_op = "and"
    if inferred_op in {"eq", "neq", "gt", "gte", "lt", "lte", "contains"}:
        left = _normalize_expression_operand(value.get("left"))
        right = _normalize_expression_operand(value.get("right"))
        if left is None and _to_text(value.get("ref_id") or value.get("source_ref_id")):
            left = {
                "op": "ref",
                "ref_id": _to_text(value.get("ref_id") or value.get("source_ref_id")),
            }
        if right is None and "value" in value:
            right = {"op": "constant", "value": _normalize_constant_value(value.get("value"))}
        if left is None or right is None:
            return None
        return {"op": inferred_op, "left": left, "right": right}
    if inferred_op == "in":
        left = _normalize_expression_operand(value.get("left"))
        if left is None and _to_text(value.get("ref_id") or value.get("source_ref_id")):
            left = {
                "op": "ref",
                "ref_id": _to_text(value.get("ref_id") or value.get("source_ref_id")),
            }
        raw_values = value.get("values")
        if not isinstance(raw_values, list) and "right" in value:
            right_value = value.get("right")
            raw_values = right_value if isinstance(right_value, list) else [right_value]
        if not isinstance(raw_values, list) and "value" in value:
            raw_values = [value.get("value")]
        normalized_values = [
            normalized_operand
            for item in _safe_list(raw_values)
            if (normalized_operand := _normalize_expression_operand(item)) is not None
        ]
        if left is None or not normalized_values:
            return None
        return {"op": "in", "left": left, "right": normalized_values}
    if inferred_op in {"and", "or"}:
        predicates = _safe_list(
            value.get("operands")
            or value.get("conditions")
            or value.get("clauses")
            or value.get("predicates"),
        )
        normalized_predicates = [
            normalized_predicate
            for item in predicates
            if (normalized_predicate := _normalize_predicate(item)) is not None
        ]
        if not normalized_predicates:
            return None
        return {"op": inferred_op, "operands": normalized_predicates}
    if inferred_op == "not":
        operand = _normalize_predicate(value.get("operand") or value.get("predicate") or value.get("condition"))
        if operand is None:
            return None
        return {"op": "not", "operand": operand}
    if inferred_op == "exists":
        operand = _normalize_expression_operand(value.get("operand") or value.get("left") or value.get("field"))
        if operand is None and _to_text(value.get("ref_id") or value.get("source_ref_id")):
            operand = {
                "op": "ref",
                "ref_id": _to_text(value.get("ref_id") or value.get("source_ref_id")),
            }
        if operand is None and _to_text(value.get("field_ref_id")):
            operand = {
                "op": "ref",
                "ref_id": _to_text(value.get("field_ref_id")),
            }
        if (
            isinstance(operand, dict)
            and operand.get("op") == "constant"
            and _to_text(operand.get("value")).startswith("ref_")
        ):
            operand = {"op": "ref", "ref_id": _to_text(operand.get("value"))}
        if operand is None:
            return None
        return {"op": "exists", "operand": operand}
    return None


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    results: list[str] = []
    for item in _safe_list(value):
        text = _to_text(item)
        if text:
            results.append(text)
    return results


def _normalize_constant_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int) and len(str(abs(value))) >= 15:
        return str(value)
    if isinstance(value, float) and abs(value) >= 10**14:
        return format(value, ".0f")
    return value


def _recover_long_numeric_identifiers(understanding: dict[str, Any], *, rule_text: str) -> None:
    tokens = re.findall(r"(?<!\d)\d{15,}(?!\d)", str(rule_text or ""))
    if not tokens:
        return

    def recover(value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("op") == "constant" and "value" in value:
                recovered = _match_original_long_numeric_token(value.get("value"), tokens)
                if recovered:
                    value["value"] = recovered
            else:
                for key, child in list(value.items()):
                    value[key] = recover(child)
            return value
        if isinstance(value, list):
            return [recover(item) for item in value]
        return value

    recover(understanding)
    for reference in _safe_list(understanding.get("source_references")):
        if not isinstance(reference, dict):
            continue
        recovered = _match_original_long_numeric_token(reference.get("value"), tokens)
        if recovered:
            reference["value"] = recovered


def _match_original_long_numeric_token(value: Any, tokens: list[str]) -> str:
    text = _constant_token_text(value)
    if len(text) < 12 or not text.isdigit():
        return ""
    if text in tokens:
        return text
    ranked = sorted(tokens, key=lambda token: _common_prefix_length(text, token), reverse=True)
    if ranked and _common_prefix_length(text, ranked[0]) >= min(12, len(text), len(ranked[0])):
        return ranked[0]
    return tokens[0] if len(tokens) == 1 else ""


def _constant_token_text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int):
        return str(abs(value))
    if isinstance(value, float):
        return format(abs(value), ".0f")
    return str(value or "").strip()


def _common_prefix_length(left: str, right: str) -> int:
    count = 0
    for left_char, right_char in zip(left, right, strict=False):
        if left_char != right_char:
            break
        count += 1
    return count


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _to_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = _to_text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return default
