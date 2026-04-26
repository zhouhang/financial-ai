"""Output assertions for generated proc sample runs."""

from __future__ import annotations

import re
from typing import Any


def assert_proc_output(
    sample_result: dict[str, Any],
    *,
    expected_target: str = "",
    expected_targets: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate that a sample run produced recon-ready output for one side."""
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    targets = [str(item).strip() for item in list(expected_targets or []) if str(item).strip()]
    if not targets and expected_target:
        targets = [expected_target]
    if not targets:
        targets = _sample_output_targets(sample_result)
    primary_target = targets[0] if targets else ""
    output_sample = _find_output_sample(sample_result, primary_target) if primary_target else _first_output_sample(sample_result)
    rows = list(output_sample.get("rows") or []) if output_sample else []
    output_fields = _extract_output_fields(rows, sample_result, primary_target, sources=sources or [])

    for target in targets:
        if not _find_output_sample(sample_result, target):
            errors.append({"message": f"未生成目标表 {target}"})
    if not rows:
        errors.append({"message": f"{primary_target or '输出结果'} 没有可展示样例行"})
    if not output_fields:
        errors.append({"message": f"{primary_target or '输出结果'} 无法推断输出字段"})

    key_fields = [field for field in output_fields if _is_key_field(str(field.get("name") or ""))]
    amount_fields = [field for field in output_fields if _is_amount_field(str(field.get("name") or ""))]
    if not key_fields and output_fields:
        warnings.append("未识别到明显的匹配主键字段，第三步可能需要手动选择。")
    if not amount_fields and output_fields:
        warnings.append("未识别到明显的金额字段，第三步可能需要手动选择。")

    return {
        "success": not errors,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "output_fields": output_fields,
        "output_preview_rows": rows[:5],
    }


def _sample_output_targets(sample_result: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for item in list(sample_result.get("output_samples") or []):
        if not isinstance(item, dict):
            continue
        target = str(item.get("target_table") or "").strip()
        if target and target not in targets:
            targets.append(target)
    return targets


def _first_output_sample(sample_result: dict[str, Any]) -> dict[str, Any]:
    for item in list(sample_result.get("output_samples") or []):
        if isinstance(item, dict):
            return item
    return {}


def _find_output_sample(sample_result: dict[str, Any], expected_target: str) -> dict[str, Any]:
    for item in list(sample_result.get("output_samples") or []):
        if isinstance(item, dict) and str(item.get("target_table") or "").strip() == expected_target:
            return item
    return {}


def _extract_output_fields(
    rows: list[dict[str, Any]],
    sample_result: dict[str, Any],
    expected_target: str,
    *,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row.keys():
                key_text = str(key).strip()
                if key_text and key_text not in names:
                    names.append(key_text)
    if not names:
        normalized_rule = sample_result.get("normalized_rule") or {}
        for step in list(normalized_rule.get("steps") or []):
            if not isinstance(step, dict) or str(step.get("target_table") or "").strip() != expected_target:
                continue
            schema = step.get("schema") or {}
            for column in list(schema.get("columns") or []):
                if isinstance(column, dict):
                    name = str(column.get("name") or "").strip()
                    if name and name not in names:
                        names.append(name)
    label_map = _build_output_field_label_map(sample_result, expected_target, sources)
    return [
        {
            "name": name,
            "label": label_map.get(name) or name,
            "data_type": _infer_data_type(name, rows),
        }
        for name in names
    ]


def _build_output_field_label_map(
    sample_result: dict[str, Any],
    expected_target: str,
    sources: list[dict[str, Any]],
) -> dict[str, str]:
    label_map: dict[str, str] = {}
    source_label_map = _build_source_field_label_map(sources)
    normalized_rule = sample_result.get("normalized_rule") or {}
    for step in list(normalized_rule.get("steps") or []):
        if not isinstance(step, dict) or str(step.get("target_table") or "").strip() != expected_target:
            continue
        schema = step.get("schema") or {}
        for column in list(schema.get("columns") or []):
            if not isinstance(column, dict):
                continue
            name = str(column.get("name") or "").strip()
            label = str(column.get("label") or column.get("display_name") or "").strip()
            if name and label:
                label_map[name] = label
        for mapping in list(step.get("mappings") or []):
            if not isinstance(mapping, dict):
                continue
            target_field = str(mapping.get("target_field") or "").strip()
            if not target_field or target_field in label_map:
                continue
            source_field = _extract_mapping_source_field(mapping.get("value"))
            source_label = source_label_map.get(source_field)
            if source_label:
                label_map[target_field] = source_label
    return label_map


def _build_source_field_label_map(sources: list[dict[str, Any]]) -> dict[str, str]:
    label_map: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        raw_map = source.get("field_label_map")
        if isinstance(raw_map, dict):
            for raw_name, display_name in raw_map.items():
                raw_text = str(raw_name or "").strip()
                display_text = str(display_name or "").strip()
                if raw_text and display_text:
                    label_map.setdefault(raw_text, display_text)
        for field in list(source.get("fields") or []):
            if not isinstance(field, dict):
                continue
            raw_name = str(field.get("name") or field.get("raw_name") or field.get("field_name") or "").strip()
            display_name = str(field.get("label") or field.get("display_name") or "").strip()
            if raw_name and display_name:
                label_map.setdefault(raw_name, display_name)
    return label_map


def _extract_mapping_source_field(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    if value.get("type") != "source":
        return ""
    source = value.get("source")
    if isinstance(source, dict):
        return str(source.get("field") or value.get("field") or "").strip()
    return str(value.get("field") or "").strip()


def _infer_data_type(name: str, rows: list[dict[str, Any]]) -> str:
    if _is_amount_field(name):
        return "decimal"
    if re.search(r"日期|时间|date|time", name, re.IGNORECASE):
        return "date"
    values = [row.get(name) for row in rows if isinstance(row, dict) and row.get(name) is not None]
    if values and all(isinstance(value, int | float) for value in values):
        return "decimal"
    return "string"


def _is_key_field(name: str) -> bool:
    return bool(re.search(r"单号|编号|编码|主键|key|id|code|no", name, re.IGNORECASE))


def _is_amount_field(name: str) -> bool:
    return bool(re.search(r"金额|余额|价|费|款|amount|amt|money|fee|price|balance", name, re.IGNORECASE))
