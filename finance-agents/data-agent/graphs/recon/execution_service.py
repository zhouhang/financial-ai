"""recon 执行公共服务。

将 recon 执行核心逻辑下沉为可复用服务，供：
- 聊天子图节点（recon_task_execution_node）
- 内部 API（cron/程序触发）
共同调用。
"""

from __future__ import annotations

import logging
import uuid
import json
from typing import Any

from tools.mcp_client import execute_recon
from utils.file_intake import build_upload_name_maps as shared_build_upload_name_maps

logger = logging.getLogger(__name__)

def build_upload_name_maps(raw_files: list[Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Build filename <-> upload ref maps without depending on graph-private helpers."""
    return shared_build_upload_name_maps(raw_files)


def _to_int(value: Any) -> int:
    """Safe int conversion for numeric fields from MCP output."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_results(recon_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize MCP recon output to a list-like shape."""
    results = recon_result.get("results", [])
    if isinstance(results, list) and results:
        return [r for r in results if isinstance(r, dict)]
    if recon_result.get("success"):
        return [recon_result]
    return []


def _extract_recon_meta(rule: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, Any]], set[str], set[str]]:
    """Extract key mappings / compare config from rule json."""
    key_mappings: list[dict[str, str]] = []
    compare_fields: list[dict[str, Any]] = []
    source_tables: set[str] = set()
    target_tables: set[str] = set()

    rule_items = rule.get("rules")
    if not isinstance(rule_items, list):
        return key_mappings, compare_fields, source_tables, target_tables

    for item in rule_items:
        if not isinstance(item, dict):
            continue
        source_file = item.get("source_file")
        if not isinstance(source_file, dict):
            source_file = {}
        target_file = item.get("target_file")
        if not isinstance(target_file, dict):
            target_file = {}
        source_table = str(source_file.get("table_name") or "").strip()
        target_table = str(target_file.get("table_name") or "").strip()
        if source_table:
            source_tables.add(source_table)
        if target_table:
            target_tables.add(target_table)

        recon_cfg = item.get("recon")
        if not isinstance(recon_cfg, dict):
            recon_cfg = item.get("reconciliation_config") if isinstance(item.get("reconciliation_config"), dict) else {}

        key_cfg = recon_cfg.get("key_columns") if isinstance(recon_cfg.get("key_columns"), dict) else {}
        mappings = key_cfg.get("mappings")
        if isinstance(mappings, list):
            for m in mappings:
                if not isinstance(m, dict):
                    continue
                src = str(m.get("source_field") or "").strip()
                tgt = str(m.get("target_field") or "").strip()
                if src and tgt:
                    key_mappings.append({"source_field": src, "target_field": tgt})
        else:
            src = str(key_cfg.get("source_field") or "").strip()
            tgt = str(key_cfg.get("target_field") or "").strip()
            if src and tgt:
                key_mappings.append({"source_field": src, "target_field": tgt})

        compare_cfg = recon_cfg.get("compare_columns") if isinstance(recon_cfg.get("compare_columns"), dict) else {}
        columns = compare_cfg.get("columns")
        if isinstance(columns, list):
            for c in columns:
                if not isinstance(c, dict):
                    continue
                compare_fields.append(
                    {
                        "name": str(c.get("name") or c.get("alias") or c.get("column") or "").strip(),
                        "source_field": str(c.get("source_column") or "").strip(),
                        "target_field": str(c.get("target_column") or "").strip(),
                        "compare_type": str(c.get("compare_type") or "").strip(),
                        "tolerance": c.get("tolerance"),
                    }
                )

    # de-dup while preserving order
    deduped_mappings: list[dict[str, str]] = []
    seen_mapping: set[tuple[str, str]] = set()
    for m in key_mappings:
        key = (m["source_field"], m["target_field"])
        if key in seen_mapping:
            continue
        seen_mapping.add(key)
        deduped_mappings.append(m)

    deduped_compare: list[dict[str, Any]] = []
    seen_compare: set[tuple[str, str, str]] = set()
    for c in compare_fields:
        key = (str(c.get("name") or ""), str(c.get("source_field") or ""), str(c.get("target_field") or ""))
        if key in seen_compare:
            continue
        seen_compare.add(key)
        deduped_compare.append(c)

    return deduped_mappings, deduped_compare, source_tables, target_tables


def _dedupe_non_empty(items: list[str]) -> list[str]:
    """Remove empty values and duplicates while preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _build_mismatch_label(
    *,
    key_mappings: list[dict[str, str]],
    compare_fields: list[dict[str, Any]],
) -> str:
    """Build a business-oriented mismatch label from rule config."""
    key_text = "/".join(
        f"{m.get('source_field', '')}/{m.get('target_field', '')}".strip("/")
        for m in key_mappings[:2]
        if m.get("source_field") or m.get("target_field")
    )
    compare_text = "、".join(
        str(c.get("name") or c.get("source_field") or c.get("target_field") or "")
        for c in compare_fields[:2]
        if c.get("name") or c.get("source_field") or c.get("target_field")
    )

    if key_text and compare_text:
        return f"{key_text}匹配但{compare_text}不一致"
    if key_text:
        return f"{key_text}匹配但数值不一致"
    if compare_text:
        return f"{compare_text}不一致"
    return "关键列匹配但数值不一致"


def _normalize_json_value(value: Any) -> Any:
    """Normalize pandas/numpy values for JSON serialization."""
    try:
        # pandas Timestamp / datetime-like
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass
    try:
        import pandas as pd  # local import to avoid hard dependency at module import

        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        # numpy scalar
        if hasattr(value, "item"):
            return value.item()
    except Exception:
        pass
    return value


def _normalize_row_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize row dict values for safe JSON output."""
    return {str(k): _normalize_json_value(v) for k, v in row.items()}


def _extract_sheet_name_map(rule: dict[str, Any]) -> dict[str, list[str]]:
    """Extract anomaly sheet names from rule output config."""
    name_map: dict[str, list[str]] = {
        "matched_with_diff": ["差异记录", "matched_with_diff"],
        "source_only": ["源文件独有", "source_only", "合单独有"],
        "target_only": ["目标文件独有", "target_only", "官网独有"],
    }
    rules = rule.get("rules")
    if not isinstance(rules, list):
        return name_map
    for item in rules:
        if not isinstance(item, dict):
            continue
        output_cfg = item.get("output")
        if not isinstance(output_cfg, dict):
            continue
        sheets_cfg = output_cfg.get("sheets")
        if not isinstance(sheets_cfg, dict):
            continue
        for key in ("matched_with_diff", "source_only", "target_only"):
            sheet_cfg = sheets_cfg.get(key)
            if not isinstance(sheet_cfg, dict):
                continue
            name = str(sheet_cfg.get("name") or "").strip()
            if name and name not in name_map[key]:
                name_map[key].append(name)
    return name_map


def _resolve_row_value(row: dict[str, Any], candidates: list[str]) -> Any:
    """Resolve row value by candidate column names."""
    for name in candidates:
        key = str(name or "").strip()
        if key and key in row:
            return row[key]
    return None


def _candidate_columns_for_field(field: str, role: str) -> list[str]:
    """Build candidate column names for source/target field lookup."""
    field_name = str(field or "").strip()
    if not field_name:
        return []
    if role == "source":
        return [field_name, f"source_{field_name}", f"source.{field_name}", f"合单.{field_name}"]
    return [field_name, f"target_{field_name}", f"target.{field_name}", f"官网.{field_name}"]


def _candidate_side_only_columns(field: str, role: str) -> list[str]:
    """Build candidate names for source_only/target_only sheets after export renaming."""
    field_name = str(field or "").strip()
    if not field_name:
        return []
    if role == "source":
        return [field_name, f"source_{field_name}", f"source.{field_name}", f"合单.{field_name}"]
    return [field_name, f"target_{field_name}", f"target.{field_name}", f"官网.{field_name}"]


def _candidate_diff_columns(compare_name: str, source_field: str, target_field: str) -> list[str]:
    """Build candidate diff column names."""
    name = str(compare_name or "").strip()
    src = str(source_field or "").strip()
    tgt = str(target_field or "").strip()
    candidates = [
        f"{name}差异" if name and not name.endswith("差异") else name,
        f"diff_{name}" if name else "",
        f"diff_{src}" if src else "",
        f"diff_{tgt}" if tgt else "",
        f"{src}差异" if src else "",
        f"{tgt}差异" if tgt else "",
    ]
    return [c for c in candidates if c]


def _build_placeholder_anomaly_items(
    *,
    run_id: str,
    rule_code: str,
    rule_name: str,
    result_index: int,
    result: dict[str, Any],
    anomaly_type: str,
    count: int,
) -> list[dict[str, Any]]:
    """Build placeholder anomaly items when row-level details are unavailable."""
    items: list[dict[str, Any]] = []
    if count <= 0:
        return items
    for idx in range(count):
        items.append(
            {
                "item_id": f"{run_id}:{result_index}:{anomaly_type}:{idx + 1}",
                "run_id": run_id,
                "rule_code": rule_code,
                "rule_name": rule_name,
                "result_index": result_index,
                "anomaly_type": anomaly_type,
                "source_ref": str(result.get("source_file") or ""),
                "target_ref": str(result.get("target_file") or ""),
                "join_key": [],
                "compare_values": [],
                "detail_unavailable": True,
                "raw_record": {},
            }
        )
    return items


def _extract_anomaly_items_from_output(
    *,
    run_id: str,
    rule_code: str,
    rule_name: str,
    results: list[dict[str, Any]],
    key_mappings: list[dict[str, str]],
    compare_fields: list[dict[str, Any]],
    sheet_name_map: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Extract row-level anomaly items from recon output workbooks."""
    items: list[dict[str, Any]] = []
    for result_idx, result in enumerate(results, 1):
        output_file = str(result.get("output_file") or "").strip()
        type_counts = {
            "matched_with_diff": _to_int(result.get("matched_with_diff")),
            "source_only": _to_int(result.get("source_only")),
            "target_only": _to_int(result.get("target_only")),
        }
        extracted_count = {"matched_with_diff": 0, "source_only": 0, "target_only": 0}

        if output_file:
            try:
                import pandas as pd  # local import for optional dependency handling

                workbook = pd.read_excel(output_file, sheet_name=None, dtype=object)
                if isinstance(workbook, dict):
                    sheet_to_type: dict[str, str] = {}
                    for anomaly_type, names in sheet_name_map.items():
                        for sheet_name in names:
                            sheet_to_type[sheet_name] = anomaly_type

                    for sheet_name, df in workbook.items():
                        if not hasattr(df, "to_dict"):
                            continue
                        anomaly_type = sheet_to_type.get(str(sheet_name))
                        if not anomaly_type:
                            if "差异" in str(sheet_name):
                                anomaly_type = "matched_with_diff"
                            elif "源" in str(sheet_name) or "合单" in str(sheet_name):
                                anomaly_type = "source_only"
                            elif "目标" in str(sheet_name) or "官网" in str(sheet_name):
                                anomaly_type = "target_only"
                        if anomaly_type not in {"matched_with_diff", "source_only", "target_only"}:
                            continue

                        rows = df.to_dict(orient="records")
                        for row_idx, row in enumerate(rows, 1):
                            normalized_row = _normalize_row_dict(row if isinstance(row, dict) else {})

                            join_key: list[dict[str, Any]] = []
                            for mapping in key_mappings:
                                source_field = str(mapping.get("source_field") or "").strip()
                                target_field = str(mapping.get("target_field") or "").strip()
                                source_value = _resolve_row_value(
                                    normalized_row, _candidate_columns_for_field(source_field, "source")
                                )
                                target_value = _resolve_row_value(
                                    normalized_row, _candidate_columns_for_field(target_field, "target")
                                )
                                join_key.append(
                                    {
                                        "source_field": source_field,
                                        "target_field": target_field,
                                        "source_value": source_value,
                                        "target_value": target_value,
                                    }
                                )

                            compare_values: list[dict[str, Any]] = []
                            for compare_cfg in compare_fields:
                                compare_name = str(compare_cfg.get("name") or "").strip()
                                source_field = str(compare_cfg.get("source_field") or "").strip()
                                target_field = str(compare_cfg.get("target_field") or "").strip()
                                source_value = _resolve_row_value(
                                    normalized_row, _candidate_columns_for_field(source_field, "source")
                                )
                                target_value = _resolve_row_value(
                                    normalized_row, _candidate_columns_for_field(target_field, "target")
                                )
                                diff_value = _resolve_row_value(
                                    normalized_row,
                                    _candidate_diff_columns(compare_name, source_field, target_field),
                                )
                                if anomaly_type == "source_only" and source_value is None and source_field:
                                    source_value = _resolve_row_value(
                                        normalized_row,
                                        _candidate_side_only_columns(source_field, "source"),
                                    )
                                if anomaly_type == "target_only" and target_value is None and target_field:
                                    target_value = _resolve_row_value(
                                        normalized_row,
                                        _candidate_side_only_columns(target_field, "target"),
                                    )
                                compare_values.append(
                                    {
                                        "name": compare_name,
                                        "source_field": source_field,
                                        "target_field": target_field,
                                        "source_value": source_value,
                                        "target_value": target_value,
                                        "diff_value": diff_value,
                                    }
                                )

                            items.append(
                                {
                                    "item_id": f"{run_id}:{result_idx}:{anomaly_type}:{row_idx}",
                                    "run_id": run_id,
                                    "rule_code": rule_code,
                                    "rule_name": rule_name,
                                    "result_index": result_idx,
                                    "anomaly_type": anomaly_type,
                                    "source_ref": str(result.get("source_file") or ""),
                                    "target_ref": str(result.get("target_file") or ""),
                                    "join_key": join_key,
                                    "compare_values": compare_values,
                                    "detail_unavailable": False,
                                    "raw_record": normalized_row,
                                }
                            )
                            extracted_count[anomaly_type] += 1
            except Exception as exc:
                logger.warning(f"[recon] 读取 anomaly 明细失败: output_file={output_file}, error={exc}")

        # fallback: keep 1:1 anomaly item cardinality even if detail extraction failed
        for anomaly_type, count in type_counts.items():
            missing = max(count - extracted_count.get(anomaly_type, 0), 0)
            if missing > 0:
                items.extend(
                    _build_placeholder_anomaly_items(
                        run_id=run_id,
                        rule_code=rule_code,
                        rule_name=rule_name,
                        result_index=result_idx,
                        result=result,
                        anomaly_type=anomaly_type,
                        count=missing,
                    )
                )
    return items


def _build_stable_run_id(
    *,
    explicit_run_id: str,
    rule_code: str,
    trigger_type: str,
    entry_mode: str,
    run_context: dict[str, Any],
    recon_inputs: list[dict[str, Any]],
    succeeded_results: list[dict[str, Any]],
) -> str:
    """Build deterministic run_id when caller does not provide one."""
    explicit = str(explicit_run_id or "").strip()
    if explicit:
        return explicit

    context_candidates = [
        str(run_context.get("run_id") or "").strip(),
        str(run_context.get("request_id") or "").strip(),
        str(run_context.get("job_run_id") or "").strip(),
        str(run_context.get("job_id") or "").strip(),
        str(run_context.get("trace_id") or "").strip(),
    ]
    for candidate in context_candidates:
        if candidate:
            return f"recon:{rule_code}:{candidate}"

    input_seed: list[dict[str, Any]] = []
    for item in recon_inputs:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        input_seed.append(
            {
                "table_name": str(item.get("table_name") or ""),
                "input_type": str(item.get("input_type") or ""),
                "file_path": str(payload.get("file_path") or ""),
                "dataset_ref": payload.get("dataset_ref") if isinstance(payload.get("dataset_ref"), dict) else {},
            }
        )

    output_seed = [
        str(result.get("output_file") or "")
        for result in succeeded_results
        if isinstance(result, dict)
    ]
    payload_seed = {
        "rule_code": rule_code,
        "trigger_type": trigger_type or "chat",
        "entry_mode": entry_mode or "file",
        "run_context": {
            "job_name": str(run_context.get("job_name") or ""),
            "biz_date": str(run_context.get("biz_date") or ""),
        },
        "inputs": input_seed,
        "outputs": sorted(output_seed),
    }
    seed = json.dumps(payload_seed, ensure_ascii=False, sort_keys=True, default=str)
    return f"recon:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"


def build_recon_observation(
    *,
    rule_code: str,
    rule_name: str,
    rule: dict[str, Any],
    trigger_type: str,
    entry_mode: str,
    recon_inputs: list[dict[str, Any]],
    recon_result: dict[str, Any],
    run_context: dict[str, Any] | None = None,
    run_id: str | None = None,
    ref_to_display_name: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build structured observation object for downstream reasoning agents."""
    ref_to_display_name = ref_to_display_name or {}
    run_context = run_context or {}
    key_mappings, compare_fields, source_tables, target_tables = _extract_recon_meta(rule)
    results = _normalize_results(recon_result)
    succeeded_results = [r for r in results if str(r.get("status", "succeeded")) == "succeeded"]
    resolved_run_id = _build_stable_run_id(
        explicit_run_id=str(run_id or ""),
        rule_code=rule_code,
        trigger_type=trigger_type,
        entry_mode=entry_mode,
        run_context=run_context,
        recon_inputs=recon_inputs,
        succeeded_results=succeeded_results,
    )

    matched_exact = sum(_to_int(r.get("matched_exact")) for r in succeeded_results)
    matched_with_diff = sum(_to_int(r.get("matched_with_diff")) for r in succeeded_results)
    source_only = sum(_to_int(r.get("source_only")) for r in succeeded_results)
    target_only = sum(_to_int(r.get("target_only")) for r in succeeded_results)
    total_records = matched_exact + matched_with_diff + source_only + target_only

    status = str(recon_result.get("status") or "").strip()
    if not status:
        status = "success" if recon_result.get("success") else "failed"

    normalized_inputs: list[dict[str, Any]] = []
    for item in recon_inputs:
        if not isinstance(item, dict):
            continue
        table_name = str(item.get("table_name") or "").strip()
        if not table_name:
            continue
        input_type = str(item.get("input_type") or "").strip().lower() or "file"
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        role = "unknown"
        if table_name in source_tables:
            role = "source"
        elif table_name in target_tables:
            role = "target"

        display_name = table_name
        if input_type == "file":
            file_path = str(payload.get("file_path") or "").strip()
            file_name = str(payload.get("file_name") or "").strip()
            display_name = (
                ref_to_display_name.get(file_path)
                or ref_to_display_name.get(file_name)
                or file_name
                or (file_path.split("/")[-1] if file_path else table_name)
            )
        elif input_type == "dataset":
            dataset_ref = payload.get("dataset_ref") if isinstance(payload.get("dataset_ref"), dict) else payload
            source_key = str((dataset_ref or {}).get("source_key") or "").strip()
            if source_key:
                display_name = source_key

        normalized_inputs.append(
            {
                "role": role,
                "table_name": table_name,
                "display_name": display_name,
                "input_type": input_type,
            }
        )

    output_files: list[str] = []
    download_urls: list[str] = []
    for r in succeeded_results:
        output_file = str(r.get("output_file") or "").strip()
        download_url = str(r.get("download_url") or "").strip()
        if output_file and output_file not in output_files:
            output_files.append(output_file)
        if download_url and download_url not in download_urls:
            download_urls.append(download_url)

    mismatch_label = _build_mismatch_label(key_mappings=key_mappings, compare_fields=compare_fields)
    sheet_name_map = _extract_sheet_name_map(rule if isinstance(rule, dict) else {})
    anomaly_items = _extract_anomaly_items_from_output(
        run_id=resolved_run_id,
        rule_code=rule_code,
        rule_name=rule_name,
        results=succeeded_results,
        key_mappings=key_mappings,
        compare_fields=compare_fields,
        sheet_name_map=sheet_name_map,
    )
    mismatch_related_fields = _dedupe_non_empty(
        [
            *(f"{m.get('source_field', '')}/{m.get('target_field', '')}".strip("/") for m in key_mappings),
            *(str(c.get("name") or c.get("source_field") or c.get("target_field") or "").strip() for c in compare_fields),
        ]
    )
    anomaly_groups = [
        {
            "anomaly_type": "value_mismatch",
            "label": mismatch_label,
            "count": matched_with_diff,
            "related_fields": mismatch_related_fields,
        },
        {
            "anomaly_type": "source_only",
            "label": "仅源文件存在",
            "count": source_only,
            "related_fields": _dedupe_non_empty([str(m.get("source_field") or "") for m in key_mappings]),
        },
        {
            "anomaly_type": "target_only",
            "label": "仅目标文件存在",
            "count": target_only,
            "related_fields": _dedupe_non_empty([str(m.get("target_field") or "") for m in key_mappings]),
        },
    ]

    return {
        "version": "1.0",
        "observation_type": "recon",
        "run_id": resolved_run_id,
        "status": status,
        "rule": {
            "rule_code": rule_code,
            "rule_name": rule_name,
            "rule_type": "recon",
        },
        "context": {
            "trigger_type": trigger_type or "chat",
            "entry_mode": entry_mode or "file",
        },
        "inputs": normalized_inputs,
        "summary": {
            "matched_exact": matched_exact,
            "matched_with_diff": matched_with_diff,
            "source_only": source_only,
            "target_only": target_only,
            "total_records": total_records,
            "has_anomaly": (matched_with_diff + source_only + target_only) > 0,
        },
        "join_config": {
            "key_mappings": key_mappings,
        },
        "compare_config": compare_fields,
        "anomaly_groups": anomaly_groups,
        "anomaly_items": anomaly_items,
        "anomaly_item_count": len(anomaly_items),
        "artifacts": {
            "output_files": output_files,
            "download_urls": download_urls,
            "primary_output_file": output_files[0] if output_files else "",
            "primary_download_url": download_urls[0] if download_urls else "",
        },
    }


def _normalize_recon_input_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """归一化单条 recon 输入。"""
    if not isinstance(item, dict):
        return None

    table_name = str(item.get("table_name") or "").strip()
    if not table_name:
        return None

    payload = item.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    # 兼容平铺写法
    file_path = str(item.get("file_path") or "").strip()
    if file_path and "file_path" not in payload:
        payload["file_path"] = file_path

    dataset_ref = item.get("dataset_ref")
    if isinstance(dataset_ref, dict) and "dataset_ref" not in payload:
        payload["dataset_ref"] = dataset_ref

    memory_ref = str(item.get("memory_ref") or "").strip()
    if memory_ref and "memory_ref" not in payload:
        payload["memory_ref"] = memory_ref

    input_type = str(item.get("input_type") or "").strip().lower()
    if not input_type:
        if payload.get("file_path"):
            input_type = "file"
        elif payload.get("memory_ref"):
            input_type = "memory"
        else:
            input_type = "dataset"

    return {
        "table_name": table_name,
        "input_type": input_type,
        "payload": payload,
    }


def normalize_recon_inputs(raw_inputs: list[Any]) -> list[dict[str, Any]]:
    """归一化 recon_inputs 数组。"""
    result: list[dict[str, Any]] = []
    for item in raw_inputs:
        normalized = _normalize_recon_input_item(item if isinstance(item, dict) else {})
        if normalized is not None:
            result.append(normalized)
    return result


def build_recon_inputs_from_file_matches(
    *,
    file_match_results: list[dict[str, Any]],
    uploaded_files_raw: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
    """将文件校验结果转换为统一 recon_inputs。"""
    if not file_match_results:
        return [], {}, "未找到文件校验结果，请先完成文件校验步骤"

    file_path_map, ref_to_display_name = build_upload_name_maps(uploaded_files_raw)
    recon_inputs: list[dict[str, Any]] = []

    for match in file_match_results:
        file_name = str(match.get("file_name") or "").strip()
        table_name = str(match.get("table_name") or "").strip()
        if not file_name or not table_name:
            continue
        file_path = str(file_path_map.get(file_name) or "").strip()
        if not file_path:
            continue
        recon_inputs.append(
            {
                "table_name": table_name,
                "input_type": "file",
                "payload": {
                    "file_path": file_path,
                    "file_name": file_name,
                    "table_id": match.get("table_id"),
                },
            }
        )

    if not recon_inputs:
        return [], ref_to_display_name, "无法构建文件路径映射，请检查上传文件状态"
    return recon_inputs, ref_to_display_name, None


def resolve_recon_inputs(
    *,
    state: dict[str, Any],
    ctx: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
    """统一解析 recon 输入。

    优先读取 ctx.recon_inputs，缺失时回退到文件校验结果+上传文件的旧路径。
    """
    raw_inputs = list(ctx.get("recon_inputs") or [])
    recon_inputs = normalize_recon_inputs(raw_inputs)
    logical_uploaded_files = list(ctx.get("logical_uploaded_files") or state.get("uploaded_files") or [])
    if recon_inputs:
        # 仅用于展示文件名映射，dataset 模式通常为空。
        _, ref_to_display_name = build_upload_name_maps(logical_uploaded_files)
        return recon_inputs, ref_to_display_name, None

    return build_recon_inputs_from_file_matches(
        file_match_results=list(ctx.get("file_match_results") or []),
        uploaded_files_raw=logical_uploaded_files,
    )


def build_execution_request(
    *,
    rule_code: str,
    rule_id: str,
    auth_token: str,
    recon_inputs: list[dict[str, Any]],
    run_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """构建统一执行请求。"""
    validated_inputs: list[dict[str, Any]] = []
    validated_files: list[dict[str, str]] = []

    for item in recon_inputs:
        table_name = str(item.get("table_name") or "").strip()
        input_type = str(item.get("input_type") or "").strip().lower()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if not table_name:
            continue

        if input_type == "file":
            file_path = str(payload.get("file_path") or "").strip()
            if not file_path:
                continue
            validated_inputs.append(
                {
                    "table_name": table_name,
                    "input_type": "file",
                    "file_path": file_path,
                }
            )
            validated_files.append(
                {
                    "table_name": table_name,
                    "file_path": file_path,
                }
            )
            continue

        if input_type == "dataset":
            dataset_ref = payload.get("dataset_ref")
            if not isinstance(dataset_ref, dict) or not dataset_ref:
                dataset_ref = dict(payload)
            validated_inputs.append(
                {
                    "table_name": table_name,
                    "input_type": "dataset",
                    "dataset_ref": dataset_ref,
                }
            )
            continue

        if input_type == "memory":
            memory_ref = str(payload.get("memory_ref") or "").strip()
            if not memory_ref:
                continue
            fallback_file_path = str(payload.get("fallback_file_path") or "").strip()
            memory_input = {
                "table_name": table_name,
                "input_type": "memory",
                "memory_ref": memory_ref,
            }
            if fallback_file_path:
                memory_input["fallback_file_path"] = fallback_file_path
            validated_inputs.append(
                memory_input
            )
            continue

        logger.warning(f"[recon] 忽略未知 input_type: {input_type}, table_name={table_name}")

    if not validated_inputs:
        return {}, "recon_inputs 为空或无有效输入，无法执行对账"

    request: dict[str, Any] = {
        "rule_code": rule_code,
        "rule_id": rule_id,
        "validated_inputs": validated_inputs,
        # 兼容未升级的 MCP：仍保留文件模式参数
        "validated_files": validated_files,
        "run_context": run_context or {},
    }
    if auth_token:
        request["auth_token"] = auth_token
    return request, None


async def run_recon_execution(execution_request: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """执行 recon，返回 MCP 原始结果。"""
    try:
        recon_result = await execute_recon(
            validated_inputs=list(execution_request.get("validated_inputs") or []),
            validated_files=list(execution_request.get("validated_files") or []),
            rule_code=str(execution_request.get("rule_code") or ""),
            rule_id=str(execution_request.get("rule_id") or ""),
            auth_token=str(execution_request.get("auth_token") or ""),
        )
        return recon_result, None
    except Exception as exc:
        return {}, f"调用对账服务失败: {exc}"


def build_recon_ctx_update_from_execution(
    *,
    recon_result: dict[str, Any],
    recon_inputs: list[dict[str, Any]],
    execution_request: dict[str, Any],
    ref_to_display_name: dict[str, str],
    recon_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将 recon_execute 返回结果整理为 recon_ctx 可直接写入的字段。

    Returns:
        {
            "ok": bool,                    # 是否可进入结果展示阶段
            "execution_status": str,       # success/partial_success/skipped/error
            "exec_error": str,             # 失败时错误信息
            "ctx_update": dict[str, Any],  # 供节点写回 recon_ctx 的字段
        }
    """
    execution_status = recon_result.get("status")
    if execution_status is None and not recon_result.get("success"):
        execution_status = "failed"

    base_ctx_update: dict[str, Any] = {
        "recon_inputs": recon_inputs,
        "execution_result": recon_result,
        "recon_result": recon_result,
        "recon_observation": recon_observation or {},
        "run_id": str((recon_observation or {}).get("run_id") or ""),
        "anomaly_items": list((recon_observation or {}).get("anomaly_items") or []),
    }

    if execution_status in {"failed", "invalid_request"}:
        return {
            "ok": False,
            "execution_status": "error",
            "exec_error": str(recon_result.get("error") or "对账执行失败"),
            "ctx_update": base_ctx_update,
        }

    if execution_status is None:
        execution_status = "success"

    # 统一处理对账结果（支持单条或多条规则）
    results = list(recon_result.get("results") or [])
    if not results and recon_result.get("success"):
        results = [recon_result]

    succeeded_results = [r for r in results if r.get("status", "succeeded") == "succeeded"]
    skipped_results = [r for r in results if r.get("status") == "skipped"]
    failed_results = [r for r in results if r.get("status") == "failed"]

    total_diff = sum(int(r.get("matched_with_diff", 0) or 0) for r in succeeded_results)
    total_source_only = sum(int(r.get("source_only", 0) or 0) for r in succeeded_results)
    total_target_only = sum(int(r.get("target_only", 0) or 0) for r in succeeded_results)
    total_matched = sum(int(r.get("matched_exact", 0) or 0) for r in succeeded_results)

    file_info_list: list[dict[str, Any]] = []
    output_files: list[str] = []
    download_urls: list[str] = []
    filter_stats: dict[str, Any] = {}

    for result in succeeded_results:
        source_file = str(result.get("source_file") or "")
        target_file = str(result.get("target_file") or "")
        output_file = str(result.get("output_file") or "")
        download_url = str(result.get("download_url") or "")
        rule_name = str(result.get("rule_name") or "")

        if source_file and target_file:
            source_display = ref_to_display_name.get(
                source_file,
                source_file.split("/")[-1] if "/" in source_file else source_file,
            )
            target_display = ref_to_display_name.get(
                target_file,
                target_file.split("/")[-1] if "/" in target_file else target_file,
            )
            file_info_list.append(
                {
                    "rule_name": rule_name,
                    "source_file": source_display,
                    "target_file": target_display,
                }
            )

        if output_file:
            output_files.append(output_file)
        if download_url:
            download_urls.append(download_url)

        if result.get("source_filter_stats"):
            filter_stats["source"] = result.get("source_filter_stats")
        if result.get("target_filter_stats"):
            filter_stats["target"] = result.get("target_filter_stats")

    ctx_update = {
        **base_ctx_update,
        "file_info_list": file_info_list,
        "output_files": output_files,
        "download_urls": download_urls,
        "filter_stats": filter_stats,
        "skipped_results": skipped_results,
        "failed_results": failed_results,
        "differences": [
            {
                "type": "matched_with_diff",
                "description": f"匹配但有差异: {total_diff} 条",
                "count": total_diff,
            },
            {
                "type": "source_only",
                "description": f"源文件独有: {total_source_only} 条",
                "count": total_source_only,
            },
            {
                "type": "target_only",
                "description": f"目标文件独有: {total_target_only} 条",
                "count": total_target_only,
            },
        ],
        "matched_count": total_matched,
        "unmatched_count": total_diff + total_source_only + total_target_only,
    }

    return {
        "ok": True,
        "execution_status": execution_status,
        "exec_error": "",
        "ctx_update": ctx_update,
    }
