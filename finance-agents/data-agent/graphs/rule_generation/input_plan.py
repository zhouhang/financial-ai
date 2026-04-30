"""Input planning for AI-generated proc rules.

The input plan is intentionally separate from proc DSL. Proc remains the data
transformation contract; input_plan only decides how to load/crop source
datasets before proc runs.
"""

from __future__ import annotations

import copy
from collections import OrderedDict
from typing import Any


VALID_READ_MODES = {"base", "by_key_set", "all"}


def generate_input_plan_from_proc(
    *,
    rule_json: dict[str, Any],
    sources: list[dict[str, Any]],
    target_table: str,
    target_tables: list[str] | None = None,
) -> dict[str, Any]:
    """Infer a deterministic input plan from proc JSON source/lookup lineage."""
    expected_targets = {str(item).strip() for item in list(target_tables or []) if str(item).strip()}
    if target_table:
        expected_targets.add(str(target_table).strip())

    source_by_table = {_source_table(source): source for source in sources if _source_table(source)}
    entries: "OrderedDict[tuple[str, str, str], dict[str, Any]]" = OrderedDict()

    for step in _write_steps(rule_json, expected_targets=expected_targets):
        all_step_sources = [_normalize_step_source(source) for source in list(step.get("sources") or [])]
        all_step_sources = [source for source in all_step_sources if source.get("table") and source.get("alias")]
        used_aliases = _collect_step_used_source_aliases(step)
        step_sources = [
            source
            for source in all_step_sources
            if not used_aliases or str(source.get("alias") or "") in used_aliases
        ]
        source_by_alias = {str(source["alias"]): source for source in step_sources}
        dependency_by_alias = _collect_step_keyset_dependencies(step, source_by_alias=source_by_alias)
        for source in step_sources:
            alias = str(source["alias"])
            table = str(source["table"])
            meta = source_by_table.get(table, {})
            dependency = dependency_by_alias.get(alias)
            read_mode = "by_key_set" if dependency else "base"
            key_pairs = list((dependency or {}).get("key_pairs") or [])
            entry = {
                "target_table": str(step.get("target_table") or ""),
                "step_id": str(step.get("step_id") or ""),
                "alias": alias,
                "table": table,
                "dataset_id": str(meta.get("dataset_id") or meta.get("id") or ""),
                "source_id": str(meta.get("source_id") or meta.get("data_source_id") or ""),
                "resource_key": str(meta.get("resource_key") or meta.get("dataset_code") or table),
                "read_mode": read_mode,
                "apply_biz_date_filter": read_mode == "base",
                "reason": (
                    "作为基础输入，沿用运行计划的对账日期过滤。"
                    if read_mode == "base"
                    else "作为关联/查找输入，按基础输入的关联键裁剪，避免读取全量关联表。"
                ),
            }
            if key_pairs:
                entry["depends_on_alias"] = str(dependency.get("depends_on_alias") or "")
                entry["key_from_field"] = str(key_pairs[0].get("from_field") or "")
                entry["key_to_field"] = str(key_pairs[0].get("to_field") or "")
                entry["key_pairs"] = key_pairs
            entries[(entry["target_table"], alias, table)] = entry

    return {
        "version": "1.0",
        "kind": "proc_input_plan",
        "target_table": target_table,
        "datasets": list(entries.values()),
        "summary": _summarize_plan_entries(list(entries.values())),
    }


def validate_input_plan(
    plan: dict[str, Any],
    *,
    rule_json: dict[str, Any],
    sources: list[dict[str, Any]],
    target_table: str,
    target_tables: list[str] | None = None,
) -> dict[str, Any]:
    """Validate plan structure and references against proc JSON and source schema."""
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return _validation_result(False, [{"message": "input_plan 必须是对象"}], warnings)

    datasets = [item for item in list(plan.get("datasets") or []) if isinstance(item, dict)]
    if not datasets:
        return _validation_result(False, [{"message": "input_plan.datasets 不能为空"}], warnings)

    expected_targets = {str(item).strip() for item in list(target_tables or []) if str(item).strip()}
    if target_table:
        expected_targets.add(str(target_table).strip())
    proc_sources = _proc_sources(rule_json, expected_targets=expected_targets, referenced_only=True)
    proc_source_keys = {
        (str(item.get("target_table") or ""), str(item.get("alias") or ""), str(item.get("table") or ""))
        for item in proc_sources
    }
    proc_alias_keys = {
        (str(item.get("target_table") or ""), str(item.get("alias") or ""))
        for item in proc_sources
    }
    plan_source_keys = {
        (str(item.get("target_table") or ""), str(item.get("alias") or ""), str(item.get("table") or ""))
        for item in datasets
    }

    missing_sources = sorted(proc_source_keys - plan_source_keys)
    for target, alias, table in missing_sources:
        errors.append({
            "reason": "input_plan_missing_proc_source",
            "message": f"input_plan 缺少 proc source: {target}.{alias}({table})",
            "target_table": target,
            "alias": alias,
            "table": table,
        })

    source_fields_by_table = {_source_table(source): set(_source_fields(source)) for source in sources if _source_table(source)}
    aliases = {(str(item.get("target_table") or ""), str(item.get("alias") or "")) for item in datasets}
    for index, item in enumerate(datasets):
        target = str(item.get("target_table") or "").strip()
        alias = str(item.get("alias") or "").strip()
        table = str(item.get("table") or "").strip()
        read_mode = str(item.get("read_mode") or "").strip()
        if (target, alias) not in proc_alias_keys:
            errors.append({
                "reason": "input_plan_unknown_alias",
                "message": f"input_plan.datasets[{index}] alias 不在 proc sources 中: {target}.{alias}",
                "target_table": target,
                "alias": alias,
            })
        if (target, alias, table) not in proc_source_keys:
            errors.append({
                "reason": "input_plan_table_mismatch",
                "message": f"input_plan.datasets[{index}] table 与 proc source 不一致: {target}.{alias}({table})",
                "target_table": target,
                "alias": alias,
                "table": table,
            })
        if read_mode not in VALID_READ_MODES:
            errors.append({
                "reason": "input_plan_invalid_read_mode",
                "message": f"input_plan.datasets[{index}] read_mode 不支持: {read_mode or '<empty>'}",
            })
            continue
        if read_mode == "by_key_set":
            depends_on_alias = str(item.get("depends_on_alias") or "").strip()
            if (target, depends_on_alias) not in aliases:
                errors.append({
                    "reason": "input_plan_missing_dependency",
                    "message": f"input_plan.datasets[{index}] depends_on_alias 不存在: {depends_on_alias}",
                    "target_table": target,
                    "alias": alias,
                })
            key_pairs = _normalize_key_pairs(item)
            if not key_pairs:
                errors.append({
                    "reason": "input_plan_missing_key_pairs",
                    "message": f"input_plan.datasets[{index}] by_key_set 缺少 key_pairs",
                    "target_table": target,
                    "alias": alias,
                })
                continue
            for pair_index, pair in enumerate(key_pairs):
                from_field = str(pair.get("from_field") or "").strip()
                to_field = str(pair.get("to_field") or "").strip()
                depends_table = _table_for_alias(datasets, target=target, alias=depends_on_alias)
                if depends_table and from_field and from_field not in source_fields_by_table.get(depends_table, set()):
                    errors.append({
                        "reason": "input_plan_key_from_field_missing",
                        "message": (
                            f"input_plan.datasets[{index}].key_pairs[{pair_index}] "
                            f"from_field 不存在: {depends_table}.{from_field}"
                        ),
                    })
                if table and to_field and to_field not in source_fields_by_table.get(table, set()):
                    errors.append({
                        "reason": "input_plan_key_to_field_missing",
                        "message": (
                            f"input_plan.datasets[{index}].key_pairs[{pair_index}] "
                            f"to_field 不存在: {table}.{to_field}"
                        ),
                    })
        if read_mode == "all":
            warnings.append(f"{target}.{alias} 将读取全量数据，可能影响大表性能。")

    return _validation_result(not errors, errors, warnings)


def execute_input_plan_preview(
    plan: dict[str, Any],
    *,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply input plan to source sample_rows for proc trial preview."""
    datasets = [item for item in list(plan.get("datasets") or []) if isinstance(item, dict)]
    source_by_table = {_source_table(source): source for source in sources if _source_table(source)}
    rows_by_target_alias: dict[tuple[str, str], list[dict[str, Any]]] = {}
    warnings: list[str] = []
    pending = list(datasets)

    while pending:
        progressed = False
        next_pending: list[dict[str, Any]] = []
        for item in pending:
            target = str(item.get("target_table") or "").strip()
            alias = str(item.get("alias") or "").strip()
            table = str(item.get("table") or "").strip()
            read_mode = str(item.get("read_mode") or "base").strip()
            source = source_by_table.get(table, {})
            sample_rows = [dict(row) for row in list(source.get("sample_rows") or []) if isinstance(row, dict)]
            if read_mode != "by_key_set":
                rows_by_target_alias[(target, alias)] = sample_rows
                progressed = True
                continue

            depends_on_alias = str(item.get("depends_on_alias") or "").strip()
            dependency_key = (target, depends_on_alias)
            if dependency_key not in rows_by_target_alias:
                next_pending.append(item)
                continue
            dependency_rows = rows_by_target_alias.get(dependency_key) or []
            filtered_rows = _filter_rows_by_key_pairs(
                rows=sample_rows,
                dependency_rows=dependency_rows,
                key_pairs=_normalize_key_pairs(item),
            )
            if sample_rows and dependency_rows and not filtered_rows:
                warnings.append(
                    f"{target}.{alias} 样例数据未匹配到 {depends_on_alias} 的关联键，正式执行会按关联键裁剪。"
                )
            rows_by_target_alias[(target, alias)] = filtered_rows
            progressed = True
        if not progressed:
            unresolved = ", ".join(
                f"{item.get('target_table')}.{item.get('alias')}" for item in next_pending
            )
            return {
                "success": False,
                "message": "input_plan 预览失败，存在无法解析的依赖关系。",
                "errors": [{"reason": "input_plan_preview_dependency_cycle", "message": unresolved}],
                "warnings": warnings,
            }
        pending = next_pending

    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    for item in datasets:
        target = str(item.get("target_table") or "").strip()
        alias = str(item.get("alias") or "").strip()
        table = str(item.get("table") or "").strip()
        rows = rows_by_target_alias.get((target, alias), [])
        rows_by_table.setdefault(table, rows)

    preview_sources: list[dict[str, Any]] = []
    for source in sources:
        table = _source_table(source)
        preview_sources.append({
            **source,
            "sample_rows": rows_by_table.get(table, list(source.get("sample_rows") or [])),
            "sample_origin": "input_plan_preview",
        })

    return {
        "success": True,
        "message": "已按取数计划生成样例输入。",
        "preview_sources": preview_sources,
        "warnings": warnings,
        "summary": {
            "dataset_count": len(datasets),
            "keyset_dataset_count": len([
                item for item in datasets if str(item.get("read_mode") or "") == "by_key_set"
            ]),
        },
    }


def build_input_plan_questions(plan: dict[str, Any], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build finance-friendly confirmation questions for unresolved input plans."""
    datasets = [item for item in list(plan.get("datasets") or []) if isinstance(item, dict)]
    candidates = []
    for item in datasets:
        label = str(item.get("alias") or item.get("table") or "").strip()
        table = str(item.get("table") or "").strip()
        if label or table:
            candidates.append(f"{label}({table})" if label and table else label or table)
    return [
        {
            "id": "input_plan_confirmation",
            "type": "input_plan_confirmation",
            "role": "input_plan",
            "question": (
                "整理规则已生成，但系统无法确定部分数据集正式运行时如何取数。"
                "请补充说明每个数据集是按对账日期取数、按另一张表的关联字段取数，还是读取全部。"
            ),
            "candidates": candidates[:8],
            "evidence": [str(error.get("message") or "") for error in errors[:5] if error.get("message")],
        }
    ]


def _write_steps(rule_json: dict[str, Any], *, expected_targets: set[str]) -> list[dict[str, Any]]:
    steps = []
    for step in list(rule_json.get("steps") or []):
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip() != "write_dataset":
            continue
        target = str(step.get("target_table") or "").strip()
        if expected_targets and target not in expected_targets:
            continue
        steps.append(step)
    return steps


def _proc_sources(
    rule_json: dict[str, Any],
    *,
    expected_targets: set[str],
    referenced_only: bool = False,
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for step in _write_steps(rule_json, expected_targets=expected_targets):
        target = str(step.get("target_table") or "").strip()
        used_aliases = _collect_step_used_source_aliases(step) if referenced_only else set()
        for source in list(step.get("sources") or []):
            normalized = _normalize_step_source(source)
            if used_aliases and normalized.get("alias") not in used_aliases:
                continue
            if normalized.get("alias") and normalized.get("table"):
                sources.append({"target_table": target, **normalized})
    return sources


def _normalize_step_source(source: Any) -> dict[str, str]:
    if not isinstance(source, dict):
        return {}
    table = str(source.get("table") or "").strip()
    alias = str(source.get("alias") or table).strip()
    return {"table": table, "alias": alias}


def _collect_step_keyset_dependencies(
    step: dict[str, Any],
    *,
    source_by_alias: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    aggregate_by_output_alias = {
        str(item.get("output_alias") or "").strip(): item
        for item in list(step.get("aggregate") or [])
        if isinstance(item, dict) and str(item.get("output_alias") or "").strip()
    }
    dependencies: dict[str, dict[str, Any]] = {}
    for lookup in _iter_lookup_nodes(step):
        lookup_alias = str(lookup.get("source_alias") or "").strip()
        target_alias = lookup_alias
        key_to_fields = [str(item.get("lookup_field") or "").strip() for item in list(lookup.get("keys") or []) if isinstance(item, dict)]
        if lookup_alias in aggregate_by_output_alias:
            aggregate = aggregate_by_output_alias[lookup_alias]
            target_alias = str(aggregate.get("source_alias") or "").strip()
            group_fields = [str(item).strip() for item in list(aggregate.get("group_fields") or []) if str(item).strip()]
            key_to_fields = group_fields or key_to_fields
        if target_alias not in source_by_alias:
            continue
        key_pairs: list[dict[str, str]] = []
        for index, key in enumerate([item for item in list(lookup.get("keys") or []) if isinstance(item, dict)]):
            input_source = _first_source_node(key.get("input"))
            if not input_source:
                continue
            depends_on_alias = str(input_source.get("alias") or "").strip()
            from_field = str(input_source.get("field") or "").strip()
            to_field = key_to_fields[index] if index < len(key_to_fields) else str(key.get("lookup_field") or "").strip()
            if not depends_on_alias or not from_field or not to_field:
                continue
            key_pairs.append({"from_field": from_field, "to_field": to_field})
            dependency = dependencies.setdefault(
                target_alias,
                {
                    "depends_on_alias": depends_on_alias,
                    "key_pairs": [],
                },
            )
            if dependency.get("depends_on_alias") != depends_on_alias:
                continue
            if {"from_field": from_field, "to_field": to_field} not in dependency["key_pairs"]:
                dependency["key_pairs"].append({"from_field": from_field, "to_field": to_field})
    return dependencies


def _collect_step_used_source_aliases(step: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    aliases |= _collect_source_aliases(step.get("mappings") or [])
    aliases |= _collect_source_aliases(step.get("filter") or {})
    aliases |= _collect_source_aliases(step.get("reference_filter") or {})
    for aggregate in list(step.get("aggregate") or []):
        if not isinstance(aggregate, dict):
            continue
        source_alias = str(aggregate.get("source_alias") or "").strip()
        if source_alias:
            aliases.add(source_alias)
    for source_spec in list((step.get("match") or {}).get("sources") or []):
        if not isinstance(source_spec, dict):
            continue
        alias = str(source_spec.get("alias") or "").strip()
        if alias:
            aliases.add(alias)
    return aliases


def _collect_source_aliases(value: Any) -> set[str]:
    aliases: set[str] = set()
    if isinstance(value, dict):
        node_type = str(value.get("type") or "").strip()
        if node_type in {"source", "template_source"}:
            source = value.get("source") if isinstance(value.get("source"), dict) else {}
            alias = str(source.get("alias") or "").strip()
            if alias:
                aliases.add(alias)
        lookup_alias = str(value.get("source_alias") or "").strip()
        if node_type == "lookup" and lookup_alias:
            aliases.add(lookup_alias)
        for child in value.values():
            aliases |= _collect_source_aliases(child)
    elif isinstance(value, list):
        for item in value:
            aliases |= _collect_source_aliases(item)
    return aliases


def _iter_lookup_nodes(value: Any):
    if isinstance(value, dict):
        if str(value.get("type") or "") == "lookup":
            yield value
        for child in value.values():
            yield from _iter_lookup_nodes(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_lookup_nodes(item)


def _first_source_node(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        if str(value.get("type") or "") == "source":
            source = value.get("source") if isinstance(value.get("source"), dict) else {}
            alias = str(source.get("alias") or "").strip()
            field = str(source.get("field") or "").strip()
            return {"alias": alias, "field": field} if alias and field else {}
        for child in value.values():
            found = _first_source_node(child)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _first_source_node(item)
            if found:
                return found
    return {}


def _normalize_key_pairs(item: dict[str, Any]) -> list[dict[str, str]]:
    pairs = [
        {
            "from_field": str(pair.get("from_field") or "").strip(),
            "to_field": str(pair.get("to_field") or "").strip(),
        }
        for pair in list(item.get("key_pairs") or [])
        if isinstance(pair, dict)
    ]
    if not pairs:
        from_field = str(item.get("key_from_field") or "").strip()
        to_field = str(item.get("key_to_field") or "").strip()
        if from_field and to_field:
            pairs.append({"from_field": from_field, "to_field": to_field})
    return [pair for pair in pairs if pair.get("from_field") and pair.get("to_field")]


def _filter_rows_by_key_pairs(
    *,
    rows: list[dict[str, Any]],
    dependency_rows: list[dict[str, Any]],
    key_pairs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not rows or not dependency_rows or not key_pairs:
        return []
    key_set = {
        tuple(_normalize_key(row.get(pair["from_field"])) for pair in key_pairs)
        for row in dependency_rows
    }
    return [
        row
        for row in rows
        if tuple(_normalize_key(row.get(pair["to_field"])) for pair in key_pairs) in key_set
    ]


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _table_for_alias(datasets: list[dict[str, Any]], *, target: str, alias: str) -> str:
    for item in datasets:
        if str(item.get("target_table") or "").strip() == target and str(item.get("alias") or "").strip() == alias:
            return str(item.get("table") or "").strip()
    return ""


def _source_table(source: dict[str, Any]) -> str:
    return str(
        source.get("table_name")
        or source.get("resource_key")
        or source.get("dataset_code")
        or source.get("name")
        or ""
    ).strip()


def _source_fields(source: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for field in list(source.get("fields") or []):
        if isinstance(field, dict):
            name = str(field.get("name") or field.get("raw_name") or field.get("field_name") or "").strip()
            if name and name not in fields:
                fields.append(name)
    labels = source.get("field_label_map") if isinstance(source.get("field_label_map"), dict) else {}
    for name in labels.keys():
        text = str(name or "").strip()
        if text and text not in fields:
            fields.append(text)
    for row in list(source.get("sample_rows") or []):
        if isinstance(row, dict):
            for name in row.keys():
                text = str(name or "").strip()
                if text and text not in fields:
                    fields.append(text)
    return fields


def _summarize_plan_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dataset_count": len(entries),
        "base_count": len([item for item in entries if str(item.get("read_mode") or "") == "base"]),
        "keyset_count": len([item for item in entries if str(item.get("read_mode") or "") == "by_key_set"]),
        "full_scan_count": len([item for item in entries if str(item.get("read_mode") or "") == "all"]),
    }


def _validation_result(success: bool, errors: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    return {
        "success": success,
        "message": "取数计划校验通过。" if success else "取数计划校验失败。",
        "summary": {
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
        "errors": copy.deepcopy(errors),
        "warnings": list(warnings),
    }
