from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from auth import db as auth_db

logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _first_source_value_node(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if _as_text(value.get("type")) == "source":
        return _safe_dict(value.get("source"))
    for child in value.values():
        if isinstance(child, dict):
            found = _first_source_value_node(child)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                found = _first_source_value_node(item)
                if found:
                    return found
    return {}


def _build_proc_source_field_map(scheme: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scheme_meta = _safe_dict(scheme.get("scheme_meta_json"))
    proc_rule = _safe_dict(scheme_meta.get("proc_rule_json"))
    output: dict[str, dict[str, Any]] = {}
    for step in _safe_list(proc_rule.get("steps")):
        if not isinstance(step, dict) or _as_text(step.get("action")) != "write_dataset":
            continue
        target_table = _as_text(step.get("target_table"))
        if not target_table:
            continue
        source_tables_by_alias = {
            _as_text(item.get("alias")): _as_text(item.get("table"))
            for item in _safe_list(step.get("sources"))
            if isinstance(item, dict) and _as_text(item.get("alias"))
        }
        field_sources: dict[str, dict[str, str]] = {}
        source_tables: list[str] = []
        for source_table in source_tables_by_alias.values():
            if source_table and source_table not in source_tables:
                source_tables.append(source_table)
        for mapping in _safe_list(step.get("mappings")):
            if not isinstance(mapping, dict):
                continue
            target_field = _as_text(mapping.get("target_field"))
            source_node = _first_source_value_node(mapping.get("value"))
            source_field = _as_text(source_node.get("field"))
            source_alias = _as_text(source_node.get("alias"))
            source_table = source_tables_by_alias.get(source_alias, "")
            if target_field and source_field:
                field_sources[target_field] = {
                    "field": source_field,
                    "table": source_table,
                }
        output[target_table] = {
            "field_sources": field_sources,
            "source_tables": source_tables,
        }
    return output


def _build_collection_lookup(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    snapshot = _safe_dict(run.get("source_snapshot_json"))
    default_biz_date = _as_text(snapshot.get("biz_date")) or _as_text(
        _safe_dict(run.get("run_context_json")).get("biz_date")
    )
    lookup: dict[str, dict[str, Any]] = {}
    for item in _safe_list(snapshot.get("collections")):
        if not isinstance(item, dict):
            continue
        binding = _safe_dict(item.get("binding"))
        if not binding:
            continue
        entry = {
            "binding": binding,
            "biz_date": _as_text(item.get("biz_date")) or default_biz_date,
        }
        keys = [
            binding.get("input_plan_target_table"),
            binding.get("target_table"),
            binding.get("table_name"),
            binding.get("resource_key"),
            binding.get("dataset_code"),
            binding.get("dataset_name"),
        ]
        for raw_key in keys:
            key = _as_text(raw_key)
            if key and key not in lookup:
                lookup[key] = entry
    return lookup


def _has_lookup_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    try:
        if bool(pd.isna(value)):
            return False
    except Exception:
        pass
    return True


def _side_record_key(side: str) -> str:
    return "source_record" if side == "source" else "target_record"


def _has_meaningful_record(record: Any) -> bool:
    return any(_has_lookup_value(value) for value in _safe_dict(record).values())


def _lookup_collection_entry(
    *,
    target_table: str,
    source_table: str,
    collection_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for key in (target_table, source_table):
        entry = collection_lookup.get(_as_text(key))
        if entry:
            return entry
    return {}


def _lookup_candidates_for_side(
    *,
    detail_json: dict[str, Any],
    side: str,
    target_table: str,
    proc_source_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    table_map = _safe_dict(proc_source_map.get(target_table))
    field_sources = _safe_dict(table_map.get("field_sources"))
    raw_record = _safe_dict(detail_json.get("raw_record"))
    candidates: list[dict[str, Any]] = []
    for item in _safe_list(detail_json.get("join_key")):
        if not isinstance(item, dict):
            continue
        processed_field = _as_text(
            item.get("source_field") if side == "source" else item.get("target_field")
        ) or _as_text(item.get("field"))
        if not processed_field:
            continue
        value = item.get("source_value") if side == "source" else item.get("target_value")
        if not _has_lookup_value(value):
            value = item.get("value")
        if not _has_lookup_value(value):
            value = item.get("target_value") if side == "source" else item.get("source_value")
        if not _has_lookup_value(value):
            value = raw_record.get(processed_field)
        if not _has_lookup_value(value):
            continue
        source_config = _safe_dict(field_sources.get(processed_field))
        candidates.append(
            {
                "processed_field": processed_field,
                "source_field": _as_text(source_config.get("field")) or processed_field,
                "source_table": _as_text(source_config.get("table")),
                "value": value,
            }
        )
    return candidates


def _is_browser_collection(binding: dict[str, Any]) -> bool:
    source_type = _as_text(binding.get("dataset_source_type")).lower()
    source_kind = _as_text(binding.get("source_kind")).lower()
    resource_key = _as_text(binding.get("resource_key")).lower()
    return (
        source_type == "browser_collection_records"
        or source_kind == "browser_playbook"
        or resource_key.startswith("browser-collection")
    )


def _query_source_payload(
    *,
    company_id: str,
    collection_entry: dict[str, Any],
    source_field: str,
    value: Any,
) -> dict[str, Any]:
    binding = _safe_dict(collection_entry.get("binding"))
    if not binding or not source_field:
        return {}
    common_kwargs = {
        "company_id": company_id,
        "data_source_id": _as_text(binding.get("data_source_id")) or None,
        "dataset_id": _as_text(binding.get("dataset_id")) or None,
        "dataset_code": _as_text(binding.get("dataset_code")) or None,
        "resource_key": _as_text(binding.get("resource_key")) or None,
        "biz_date": _as_text(collection_entry.get("biz_date")) or None,
        "filters": {source_field: value},
        "limit": 1,
    }
    try:
        list_records = (
            auth_db.list_browser_collection_records
            if _is_browser_collection(binding)
            else auth_db.list_dataset_collection_records
        )
        rows = list_records(**common_kwargs)
        if not rows and common_kwargs.get("biz_date"):
            rows = list_records(**{**common_kwargs, "biz_date": None})
        if not rows and common_kwargs.get("dataset_code"):
            rows = list_records(**{**common_kwargs, "biz_date": None, "dataset_code": None})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[execution] 回查异常原始记录失败: field={source_field}, error={exc}")
        return {}
    for row in rows or []:
        payload = _safe_dict(row.get("payload") if isinstance(row, dict) else {})
        if payload:
            return payload
    return {}


def _hydrate_exception_side_record(
    *,
    company_id: str,
    detail_json: dict[str, Any],
    side: str,
    proc_source_map: dict[str, dict[str, Any]],
    collection_lookup: dict[str, dict[str, Any]],
    record_cache: dict[tuple[str, str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    target_table = _as_text(detail_json.get("source_ref" if side == "source" else "target_ref"))
    if not target_table:
        return {}
    for candidate in _lookup_candidates_for_side(
        detail_json=detail_json,
        side=side,
        target_table=target_table,
        proc_source_map=proc_source_map,
    ):
        collection_entry = _lookup_collection_entry(
            target_table=target_table,
            source_table=_as_text(candidate.get("source_table")),
            collection_lookup=collection_lookup,
        )
        binding = _safe_dict(collection_entry.get("binding"))
        if not binding:
            continue
        source_field = _as_text(candidate.get("source_field"))
        value = candidate.get("value")
        cache_key = (
            _as_text(binding.get("dataset_id")) or _as_text(binding.get("resource_key")),
            _as_text(collection_entry.get("biz_date")),
            source_field,
            _as_text(value),
        )
        if cache_key not in record_cache:
            record_cache[cache_key] = _query_source_payload(
                company_id=company_id,
                collection_entry=collection_entry,
                source_field=source_field,
                value=value,
            )
        if record_cache[cache_key]:
            return record_cache[cache_key]
    return {}


def hydrate_execution_exception_details(
    *,
    run: dict[str, Any],
    scheme: dict[str, Any],
    exceptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Backfill source_record/target_record for legacy exception details."""
    if not exceptions:
        return exceptions
    company_id = _as_text(run.get("company_id"))
    if not company_id:
        return exceptions
    proc_source_map = _build_proc_source_field_map(scheme)
    collection_lookup = _build_collection_lookup(run)
    if not proc_source_map or not collection_lookup:
        return exceptions
    record_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    hydrated: list[dict[str, Any]] = []
    for raw_item in exceptions:
        item = dict(raw_item)
        detail_json = _safe_dict(item.get("detail_json"))
        if not detail_json:
            hydrated.append(item)
            continue
        changed = False
        for side in ("source", "target"):
            record_key = _side_record_key(side)
            if _has_meaningful_record(detail_json.get(record_key)):
                continue
            record = _hydrate_exception_side_record(
                company_id=company_id,
                detail_json=detail_json,
                side=side,
                proc_source_map=proc_source_map,
                collection_lookup=collection_lookup,
                record_cache=record_cache,
            )
            if record:
                detail_json[record_key] = record
                changed = True
        if changed:
            item["detail_json"] = detail_json
        hydrated.append(item)
    return hydrated
