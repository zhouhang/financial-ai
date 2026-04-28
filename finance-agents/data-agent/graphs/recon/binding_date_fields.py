"""Resolve run-plan date fields from scheme output-field metadata."""

from __future__ import annotations

from typing import Any


def safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str):
            candidate = value.strip()
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            candidate = str(value).strip()
        else:
            candidate = ""
        if candidate:
            return candidate
    return ""


def infer_binding_side(binding: dict[str, Any]) -> str:
    side = text(binding.get("side"), safe_dict(binding.get("mapping_config")).get("side")).lower()
    if side in {"left", "right"}:
        return side
    role_code = text(binding.get("role_code")).lower()
    if role_code.startswith("right"):
        return "right"
    if role_code.startswith("left"):
        return "left"
    return ""


def extract_source_items_from_scheme_meta(
    *,
    scheme_meta: dict[str, Any],
    side: str,
) -> list[dict[str, Any]]:
    dataset_bindings = safe_dict(scheme_meta.get("dataset_bindings"))
    source_items = dataset_bindings.get(side)
    if not isinstance(source_items, list):
        source_items = scheme_meta.get(f"{side}_sources")
    return [dict(item) for item in safe_list(source_items) if isinstance(item, dict)]


def normalize_output_field(raw: Any) -> dict[str, str]:
    item = safe_dict(raw)
    return {
        "output_name": text(item.get("output_name"), item.get("outputName")),
        "source_field": text(item.get("source_field"), item.get("sourceField")),
        "source_dataset_id": text(item.get("source_dataset_id"), item.get("sourceDatasetId")),
        "semantic_role": text(item.get("semantic_role"), item.get("semanticRole")).lower(),
    }


def source_matches_binding(source_item: dict[str, Any], binding: dict[str, Any]) -> bool:
    binding_query = safe_dict(binding.get("query"))
    binding_mapping = safe_dict(binding.get("mapping_config"))
    binding_source_id = text(binding.get("data_source_id"), binding.get("source_id"))
    binding_keys = {
        text(binding.get("resource_key")),
        text(binding.get("table_name")),
        text(binding.get("dataset_code")),
        text(binding_query.get("resource_key")),
        text(binding_mapping.get("resource_key")),
        text(binding_mapping.get("table_name")),
        text(binding_mapping.get("dataset_code")),
    }
    binding_keys.discard("")

    source_id = text(source_item.get("data_source_id"), source_item.get("source_id"))
    source_keys = {
        text(source_item.get("resource_key")),
        text(source_item.get("table_name")),
        text(source_item.get("technical_name")),
        text(source_item.get("dataset_name")),
        text(source_item.get("dataset_code")),
    }
    source_keys.discard("")
    if binding_source_id and source_id and binding_source_id != source_id:
        return False
    return bool(binding_keys & source_keys)


def resolve_scheme_source_date_field(
    *,
    scheme_meta: dict[str, Any],
    side: str,
    binding: dict[str, Any],
    display_date_field: str = "",
) -> str:
    if side not in {"left", "right"}:
        return ""

    output_fields = [
        normalize_output_field(item)
        for item in safe_list(scheme_meta.get(f"{side}_output_fields"))
    ]
    output_fields = [item for item in output_fields if item.get("source_field")]
    if not output_fields:
        return ""

    source_items = extract_source_items_from_scheme_meta(scheme_meta=scheme_meta, side=side)
    matched_dataset_ids = {
        text(item.get("dataset_id"), item.get("id"))
        for item in source_items
        if source_matches_binding(item, binding)
    }
    matched_dataset_ids.discard("")

    def source_matches(field: dict[str, str]) -> bool:
        source_dataset_id = field.get("source_dataset_id", "")
        return not matched_dataset_ids or not source_dataset_id or source_dataset_id in matched_dataset_ids

    normalized_display = display_date_field.strip()
    time_candidates = [
        field
        for field in output_fields
        if source_matches(field) and field.get("semantic_role") == "time_field"
    ]
    if normalized_display:
        for field in time_candidates:
            if normalized_display in {field.get("output_name", ""), field.get("source_field", "")}:
                return field.get("source_field", "")
        for field in output_fields:
            if source_matches(field) and normalized_display in {
                field.get("output_name", ""),
                field.get("source_field", ""),
            }:
                return field.get("source_field", "")
    if len(time_candidates) == 1:
        return time_candidates[0].get("source_field", "")
    return ""


def normalize_binding_query_date_field(
    *,
    scheme_meta: dict[str, Any],
    binding: dict[str, Any],
    query: dict[str, Any],
    side: str = "",
    left_time_semantic: str = "",
    right_time_semantic: str = "",
) -> dict[str, Any]:
    resolved_side = side or infer_binding_side(binding)
    if resolved_side not in {"left", "right"}:
        return dict(query)

    normalized_query = dict(query)
    display_date_field = text(
        normalized_query.get("display_date_field"),
        right_time_semantic if resolved_side == "right" else left_time_semantic,
        scheme_meta.get(f"{resolved_side}_time_semantic"),
    )
    source_date_field = resolve_scheme_source_date_field(
        scheme_meta=scheme_meta,
        side=resolved_side,
        binding=binding,
        display_date_field=display_date_field,
    )
    current_date_field = text(normalized_query.get("date_field"))
    if source_date_field and (not current_date_field or current_date_field == display_date_field):
        normalized_query["date_field"] = source_date_field
    if display_date_field:
        normalized_query["display_date_field"] = display_date_field
    return normalized_query
