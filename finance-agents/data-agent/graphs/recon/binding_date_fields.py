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
        "value_mode": text(item.get("value_mode"), item.get("valueMode")).lower(),
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


def _side_target_table(side: str) -> str:
    if side == "left":
        return "left_recon_ready"
    if side == "right":
        return "right_recon_ready"
    return ""


def _build_source_item_keys(source_item: dict[str, Any]) -> set[str]:
    keys = {
        text(source_item.get("resource_key")),
        text(source_item.get("table_name")),
        text(source_item.get("technical_name")),
        text(source_item.get("dataset_name")),
        text(source_item.get("dataset_code")),
    }
    keys.discard("")
    return keys


def _build_binding_keys(binding: dict[str, Any]) -> set[str]:
    binding_query = safe_dict(binding.get("query"))
    binding_mapping = safe_dict(binding.get("mapping_config"))
    keys = {
        text(binding.get("resource_key")),
        text(binding.get("table_name")),
        text(binding.get("dataset_code")),
        text(binding_query.get("resource_key")),
        text(binding_mapping.get("resource_key")),
        text(binding_mapping.get("table_name")),
        text(binding_mapping.get("dataset_code")),
    }
    keys.discard("")
    return keys


def _resolve_matched_source_items(
    *,
    scheme_meta: dict[str, Any],
    side: str,
    binding: dict[str, Any],
) -> list[dict[str, Any]]:
    source_items = extract_source_items_from_scheme_meta(scheme_meta=scheme_meta, side=side)
    matched = [item for item in source_items if source_matches_binding(item, binding)]
    if matched:
        return matched

    binding_keys = _build_binding_keys(binding)
    if not binding_keys:
        return []
    return [
        item
        for item in source_items
        if _build_source_item_keys(item) & binding_keys
    ]


def _describe_binding_label(
    *,
    scheme_meta: dict[str, Any],
    side: str,
    binding: dict[str, Any],
    matched_source_items: list[dict[str, Any]],
) -> str:
    candidates = matched_source_items or extract_source_items_from_scheme_meta(
        scheme_meta=scheme_meta,
        side=side,
    )
    for item in candidates:
        for key in ("business_name", "dataset_name", "name", "resource_key", "table_name"):
            label = text(item.get(key))
            if label:
                return label
    return text(
        binding.get("binding_name"),
        binding.get("dataset_name"),
        binding.get("display_name"),
        binding.get("resource_key"),
        binding.get("table_name"),
    ) or f"{side} 侧数据集"


def _find_proc_write_step(proc_rule_json: dict[str, Any], target_table: str) -> dict[str, Any]:
    for step in safe_list(proc_rule_json.get("steps")):
        item = safe_dict(step)
        if text(item.get("action")).lower() != "write_dataset":
            continue
        if text(item.get("target_table")) == target_table:
            return item
    return {}


def _build_alias_to_table(write_step: dict[str, Any]) -> dict[str, str]:
    alias_to_table: dict[str, str] = {}
    for raw_source in safe_list(write_step.get("sources")):
        source = safe_dict(raw_source)
        alias = text(source.get("alias"), source.get("table"))
        table = text(source.get("table"), source.get("alias"))
        if alias and table:
            alias_to_table[alias] = table
    return alias_to_table


def _build_aggregate_map(write_step: dict[str, Any]) -> dict[str, dict[str, Any]]:
    aggregate_map: dict[str, dict[str, Any]] = {}
    for raw_aggregate in safe_list(write_step.get("aggregate")):
        aggregate = safe_dict(raw_aggregate)
        output_alias = text(aggregate.get("output_alias"), aggregate.get("alias"))
        if output_alias:
            aggregate_map[output_alias] = aggregate
    return aggregate_map


def _resolve_alias_field_refs(
    *,
    alias: str,
    field: str,
    alias_to_table: dict[str, str],
    aggregate_map: dict[str, dict[str, Any]],
    visiting: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    normalized_alias = alias.strip()
    normalized_field = field.strip()
    if not normalized_alias or not normalized_field:
        return []

    visit_key = (normalized_alias, normalized_field)
    if visit_key in visiting:
        return []

    aggregate = aggregate_map.get(normalized_alias)
    if aggregate:
        next_visiting = set(visiting)
        next_visiting.add(visit_key)
        source_alias = text(aggregate.get("source_alias"))
        group_fields = {text(item) for item in safe_list(aggregate.get("group_fields"))}
        group_fields.discard("")
        if normalized_field in group_fields:
            return _resolve_alias_field_refs(
                alias=source_alias,
                field=normalized_field,
                alias_to_table=alias_to_table,
                aggregate_map=aggregate_map,
                visiting=next_visiting,
            )
        for raw_item in safe_list(aggregate.get("aggregations")):
            aggregation = safe_dict(raw_item)
            if text(aggregation.get("alias")) != normalized_field:
                continue
            source_field = text(aggregation.get("field"))
            return _resolve_alias_field_refs(
                alias=source_alias,
                field=source_field,
                alias_to_table=alias_to_table,
                aggregate_map=aggregate_map,
                visiting=next_visiting,
            )
        return []

    table = text(alias_to_table.get(normalized_alias), normalized_alias)
    if not table:
        return []
    return [(table, normalized_field)]


def _collect_value_provider_refs(
    value: Any,
    *,
    alias_to_table: dict[str, str],
    aggregate_map: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []

    def add_many(items: list[tuple[str, str]]) -> None:
        for item in items:
            if item not in refs:
                refs.append(item)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node_type = text(node.get("type")).lower()
            if node_type == "source":
                source = safe_dict(node.get("source"))
                add_many(
                    _resolve_alias_field_refs(
                        alias=text(source.get("alias"), node.get("alias")),
                        field=text(source.get("field"), node.get("field")),
                        alias_to_table=alias_to_table,
                        aggregate_map=aggregate_map,
                        visiting=set(),
                    )
                )
                return
            if node_type == "lookup":
                add_many(
                    _resolve_alias_field_refs(
                        alias=text(node.get("source_alias")),
                        field=text(node.get("value_field")),
                        alias_to_table=alias_to_table,
                        aggregate_map=aggregate_map,
                        visiting=set(),
                    )
                )
                return
            for key, nested in node.items():
                if key == "keys":
                    continue
                visit(nested)
            return
        if isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return refs


def _resolve_proc_rule_output_refs(
    *,
    proc_rule_json: dict[str, Any],
    side: str,
    output_name: str,
) -> list[tuple[str, str]]:
    target_table = _side_target_table(side)
    if not target_table or not output_name.strip():
        return []

    write_step = _find_proc_write_step(proc_rule_json, target_table)
    if not write_step:
        return []

    alias_to_table = _build_alias_to_table(write_step)
    aggregate_map = _build_aggregate_map(write_step)
    for raw_mapping in safe_list(write_step.get("mappings")):
        mapping = safe_dict(raw_mapping)
        if text(mapping.get("target_field")) != output_name.strip():
            continue
        return _collect_value_provider_refs(
            mapping.get("value"),
            alias_to_table=alias_to_table,
            aggregate_map=aggregate_map,
        )
    return []


def _filter_refs_for_binding(
    refs: list[tuple[str, str]],
    *,
    matched_source_items: list[dict[str, Any]],
    binding: dict[str, Any],
) -> list[tuple[str, str]]:
    if not refs:
        return []

    candidate_tables: set[str] = set()
    for item in matched_source_items:
        candidate_tables.update(_build_source_item_keys(item))
    if not candidate_tables:
        candidate_tables.update(_build_binding_keys(binding))

    if not candidate_tables:
        return refs

    return [
        ref
        for ref in refs
        if ref[0] in candidate_tables
    ]


def _build_output_field_candidates(
    *,
    output_fields: list[dict[str, str]],
    matched_dataset_ids: set[str],
    display_date_field: str,
) -> list[dict[str, str]]:
    def source_matches(field: dict[str, str]) -> bool:
        source_dataset_id = field.get("source_dataset_id", "")
        return not matched_dataset_ids or not source_dataset_id or source_dataset_id in matched_dataset_ids

    matched_fields = [field for field in output_fields if source_matches(field)]
    normalized_display = display_date_field.strip()
    time_candidates = [
        field
        for field in matched_fields
        if field.get("semantic_role") == "time_field"
    ]
    if normalized_display:
        exact = [
            field
            for field in matched_fields
            if normalized_display in {field.get("output_name", ""), field.get("source_field", "")}
        ]
        if exact:
            return exact
    if time_candidates:
        return time_candidates
    return matched_fields


def resolve_scheme_source_date_field_resolution(
    *,
    scheme_meta: dict[str, Any],
    side: str,
    binding: dict[str, Any],
    display_date_field: str = "",
) -> dict[str, Any]:
    if side not in {"left", "right"}:
        return {"field": "", "status": "missing", "error": ""}

    output_fields = [
        normalize_output_field(item)
        for item in safe_list(scheme_meta.get(f"{side}_output_fields"))
    ]
    if not output_fields:
        return {"field": "", "status": "missing", "error": ""}

    matched_source_items = _resolve_matched_source_items(
        scheme_meta=scheme_meta,
        side=side,
        binding=binding,
    )
    matched_dataset_ids = {
        text(item.get("dataset_id"), item.get("id"))
        for item in matched_source_items
    }
    matched_dataset_ids.discard("")

    candidate_fields = _build_output_field_candidates(
        output_fields=output_fields,
        matched_dataset_ids=matched_dataset_ids,
        display_date_field=display_date_field,
    )
    if not candidate_fields:
        return {"field": "", "status": "missing", "error": ""}

    proc_rule_json = safe_dict(scheme_meta.get("proc_rule_json"))
    binding_label = _describe_binding_label(
        scheme_meta=scheme_meta,
        side=side,
        binding=binding,
        matched_source_items=matched_source_items,
    )
    if proc_rule_json:
        for field in candidate_fields:
            output_name = field.get("output_name", "")
            refs = _resolve_proc_rule_output_refs(
                proc_rule_json=proc_rule_json,
                side=side,
                output_name=output_name,
            )
            filtered_refs = _filter_refs_for_binding(
                refs,
                matched_source_items=matched_source_items,
                binding=binding,
            )
            unique_fields = list(dict.fromkeys(field_name for _table, field_name in filtered_refs if field_name))
            if len(unique_fields) == 1:
                return {"field": unique_fields[0], "status": "resolved", "error": ""}
            if len(unique_fields) > 1:
                return {
                    "field": "",
                    "status": "ambiguous",
                    "error": (
                        f"{binding_label} 的时间字段“{display_date_field or output_name}”"
                        f"可追溯到多个原始字段（{'、'.join(unique_fields)}），无法确定按哪个字段做 T-1 取数。"
                        "请在第二步把时间字段改成直接映射到唯一源时间字段后再保存运行计划。"
                    ),
                }

    for field in candidate_fields:
        source_field = field.get("source_field", "")
        if source_field:
            return {"field": source_field, "status": "resolved", "error": ""}

    output_name = candidate_fields[0].get("output_name", "") or display_date_field
    return {
        "field": "",
        "status": "missing",
        "error": (
            f"{binding_label} 的时间字段“{display_date_field or output_name}”"
            "无法追溯到该数据集的原始日期字段。请在第二步把时间字段改成直接映射到源时间字段，"
            "或改成能唯一追溯到原始时间字段的聚合/关联结果后再保存运行计划。"
        ),
    }


def resolve_scheme_source_date_field(
    *,
    scheme_meta: dict[str, Any],
    side: str,
    binding: dict[str, Any],
    display_date_field: str = "",
) -> str:
    resolution = resolve_scheme_source_date_field_resolution(
        scheme_meta=scheme_meta,
        side=side,
        binding=binding,
        display_date_field=display_date_field,
    )
    return text(resolution.get("field"))


def normalize_binding_query_date_field(
    *,
    scheme_meta: dict[str, Any],
    binding: dict[str, Any],
    query: dict[str, Any],
    side: str = "",
    left_time_semantic: str = "",
    right_time_semantic: str = "",
    strict: bool = False,
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
    resolution = resolve_scheme_source_date_field_resolution(
        scheme_meta=scheme_meta,
        side=resolved_side,
        binding=binding,
        display_date_field=display_date_field,
    )
    source_date_field = text(resolution.get("field"))
    current_date_field = text(normalized_query.get("date_field"))
    if source_date_field and (not current_date_field or current_date_field == display_date_field):
        normalized_query["date_field"] = source_date_field
    elif strict and display_date_field and (not current_date_field or current_date_field == display_date_field):
        error = text(resolution.get("error"))
        if error:
            raise ValueError(error)
    if display_date_field:
        normalized_query["display_date_field"] = display_date_field
    return normalized_query
