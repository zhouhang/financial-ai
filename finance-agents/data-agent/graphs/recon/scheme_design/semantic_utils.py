from __future__ import annotations

from typing import Any


def _extract_semantic_profile(dataset: dict[str, Any]) -> dict[str, Any]:
    direct_profile = dataset.get("semantic_profile")
    if isinstance(direct_profile, dict):
        return direct_profile
    for container_key in ("meta", "metadata", "dataset_meta"):
        container = dataset.get(container_key)
        if not isinstance(container, dict):
            continue
        profile = container.get("semantic_profile")
        if isinstance(profile, dict):
            return profile
    return {}


def _normalize_string_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = str(raw_value or "").strip()
        result[key] = value or key
    return result


def _field_names_from_schema(schema_summary: Any) -> list[str]:
    if not isinstance(schema_summary, dict):
        return []
    field_names: list[str] = []
    columns = schema_summary.get("columns")
    if isinstance(columns, list):
        for column in columns:
            if not isinstance(column, dict):
                continue
            name = str(column.get("name") or column.get("column_name") or "").strip()
            if name and name not in field_names:
                field_names.append(name)
        return field_names
    for key in schema_summary.keys():
        name = str(key or "").strip()
        if name and name != "columns" and name not in field_names:
            field_names.append(name)
    return field_names


def _field_names_from_rows(sample_rows: Any) -> list[str]:
    rows = [row for row in list(sample_rows or []) if isinstance(row, dict)]
    field_names: list[str] = []
    for row in rows[:3]:
        for key in row.keys():
            name = str(key or "").strip()
            if name and name not in field_names:
                field_names.append(name)
    return field_names


def infer_raw_field_names(dataset: dict[str, Any]) -> list[str]:
    from_schema = _field_names_from_schema(dataset.get("schema_summary"))
    from_rows = _field_names_from_rows(dataset.get("sample_rows"))
    names: list[str] = []
    for name in [*from_schema, *from_rows]:
        if name and name not in names:
            names.append(name)
    return names


def _normalize_fields_list(raw_fields: Any, fallback_map: dict[str, str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(raw_fields, list):
        for item in raw_fields:
            if not isinstance(item, dict):
                continue
            raw_name = str(
                item.get("raw_name")
                or item.get("field_name")
                or item.get("name")
                or item.get("key")
                or ""
            ).strip()
            if not raw_name or raw_name in seen:
                continue
            display_name = str(
                item.get("display_name")
                or item.get("display_name_zh")
                or item.get("label")
                or fallback_map.get(raw_name)
                or raw_name
            ).strip() or raw_name
            normalized.append(
                {
                    "raw_name": raw_name,
                    "display_name": display_name,
                    "semantic_type": str(item.get("semantic_type") or "").strip(),
                    "business_role": str(item.get("business_role") or "").strip(),
                    "confidence": item.get("confidence"),
                }
            )
            seen.add(raw_name)
    for raw_name, display_name in fallback_map.items():
        if raw_name in seen:
            continue
        normalized.append(
            {
                "raw_name": raw_name,
                "display_name": display_name,
                "semantic_type": "",
                "business_role": "",
                "confidence": None,
            }
        )
        seen.add(raw_name)
    return normalized


def ensure_dataset_semantic_context(
    dataset: dict[str, Any],
    *,
    default_business_name: str = "",
) -> dict[str, Any]:
    resolved = dict(dataset)
    profile = _extract_semantic_profile(resolved)

    top_map = _normalize_string_map(resolved.get("field_label_map"))
    profile_map = _normalize_string_map(profile.get("field_label_map"))
    merged_map: dict[str, str] = {}
    merged_map.update(profile_map)
    merged_map.update(top_map)

    raw_field_names = infer_raw_field_names(resolved)
    for raw_name in raw_field_names:
        merged_map.setdefault(raw_name, raw_name)

    raw_fields = resolved.get("fields")
    if not isinstance(raw_fields, list):
        raw_fields = resolved.get("semantic_fields")
    if not isinstance(raw_fields, list):
        raw_fields = profile.get("fields")
    fields = _normalize_fields_list(raw_fields, merged_map)
    for item in fields:
        raw_name = str(item.get("raw_name") or "").strip()
        display_name = str(item.get("display_name") or "").strip()
        if raw_name:
            merged_map[raw_name] = display_name or merged_map.get(raw_name, raw_name) or raw_name

    business_name = str(
        resolved.get("business_name")
        or profile.get("business_name")
        or resolved.get("display_name")
        or resolved.get("dataset_name")
        or resolved.get("table_name")
        or default_business_name
        or ""
    ).strip()
    if not business_name:
        business_name = str(resolved.get("dataset_name") or resolved.get("table_name") or "未命名数据集").strip()

    resolved["business_name"] = business_name
    resolved["field_label_map"] = merged_map
    resolved["fields"] = fields
    if profile:
        resolved["semantic_profile"] = profile
    return resolved


def format_field_display(raw_name: str, field_label_map: dict[str, str] | None) -> str:
    raw = str(raw_name or "").strip()
    if not raw:
        return ""
    label_map = field_label_map or {}
    label = str(label_map.get(raw) or "").strip()
    if label and label != raw:
        return f"{label}({raw})"
    return raw


def format_table_display(table_name: str, table_label_map: dict[str, str] | None) -> str:
    raw = str(table_name or "").strip()
    if not raw:
        return ""
    label_map = table_label_map or {}
    label = str(label_map.get(raw) or "").strip()
    if label and label != raw:
        return f"{label}({raw})"
    return raw


def format_table_label(table_name: str, table_label_map: dict[str, str] | None) -> str:
    """Return only the business label for prose/draft_text — never expose raw DB table name."""
    raw = str(table_name or "").strip()
    if not raw:
        return ""
    label = str((table_label_map or {}).get(raw) or "").strip()
    return label if (label and label != raw) else raw


def build_prompt_dataset_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    resolved = ensure_dataset_semantic_context(dataset)
    field_label_map = _normalize_string_map(resolved.get("field_label_map"))
    field_names = infer_raw_field_names(resolved)
    field_display_pairs = [
        {
            "raw_name": raw_name,
            "display_name": field_label_map.get(raw_name, raw_name),
            "display_with_raw": format_field_display(raw_name, field_label_map),
        }
        for raw_name in field_names
    ]
    sample_rows = [
        row
        for row in list(resolved.get("sample_rows") or [])
        if isinstance(row, dict)
    ][:3]
    sample_rows_with_display_fields: list[dict[str, Any]] = []
    for row in sample_rows:
        sample_rows_with_display_fields.append(
            {
                format_field_display(str(key), field_label_map): value
                for key, value in row.items()
            }
        )
    return {
        "side": str(resolved.get("side") or "").strip(),
        "business_name": str(resolved.get("business_name") or "").strip(),
        "dataset_name": str(resolved.get("dataset_name") or "").strip(),
        "table_name": str(resolved.get("table_name") or "").strip(),
        "resource_key": str(resolved.get("resource_key") or "").strip(),
        "description": str(resolved.get("description") or "").strip(),
        "schema_summary": resolved.get("schema_summary") if isinstance(resolved.get("schema_summary"), dict) else {},
        "sample_rows": sample_rows,
        "field_label_map": field_label_map,
        "fields": resolved.get("fields") if isinstance(resolved.get("fields"), list) else [],
        "field_display_pairs": field_display_pairs,
        "sample_rows_with_display_fields": sample_rows_with_display_fields,
    }
