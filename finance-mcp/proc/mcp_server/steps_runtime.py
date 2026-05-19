from __future__ import annotations

import ast
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from security_utils import resolve_upload_file_path

logger = logging.getLogger(__name__)

VALID_ROW_WRITE_MODES = {"upsert", "insert_if_missing", "update_only"}
VALID_FIELD_WRITE_MODES = {"overwrite", "increment"}
MEMORY_FRAME_TTL_SECONDS = 30 * 60
MEMORY_FRAME_MAX_ENTRIES = 64

_MEMORY_FRAME_REGISTRY: dict[str, dict[str, Any]] = {}


class _FastPathNotSupported(RuntimeError):
    """Raised when a step cannot be executed by the vectorized fast path."""


class FormulaEvaluationError(ValueError):
    """Raised when a formula cannot be evaluated with user-facing context."""

    def __init__(self, message: str, *, binding_names: list[str] | None = None) -> None:
        super().__init__(message)
        self.binding_names = binding_names or []


class ProcRuntimeError(ValueError):
    """数据整理运行期错误基类,携带结构化的摘要/原因/建议。"""

    def __init__(self, *, summary: str, cause: str, suggestion: str) -> None:
        self.summary = summary
        self.cause = cause
        self.suggestion = suggestion
        super().__init__(self.format_detail())

    def format_detail(self) -> str:
        return (
            f"数据整理失败：{self.summary}\n\n"
            f"原因：{self.cause}\n"
            f"建议：{self.suggestion}"
        )


class ProcUserDataError(ProcRuntimeError):
    """类①:用户可自行修复的数据问题(文件缺列、日期格式错等)。"""


class ProcRuleConfigError(ProcRuntimeError):
    """类②:规则配置本身的问题,需规则作者/管理员修复。"""


@dataclass
class TableSchemaState:
    name: str
    primary_key: list[str] = field(default_factory=list)
    column_order: list[str] = field(default_factory=list)
    nullable_fields: set[str] = field(default_factory=set)
    defaults: dict[str, Any] = field(default_factory=dict)
    data_types: dict[str, str] = field(default_factory=dict)
    export_layout: dict[str, Any] = field(default_factory=dict)
    export_enabled: bool = True


def execute_steps_rule(
    rule_code: str,
    rule_data: dict[str, Any],
    validated_files: list[dict[str, Any]],
    output_dir: str,
    preloaded_frames: dict[str, pd.DataFrame] | None = None,
    column_aliases: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    runtime = StepsProcRuntime(
        rule_code, rule_data, validated_files, output_dir,
        preloaded_frames=preloaded_frames, column_aliases=column_aliases,
    )
    return runtime.execute()


def execute_steps_rule_to_frames(
    rule_code: str,
    rule_data: dict[str, Any],
    validated_files: list[dict[str, Any]],
    output_dir: str,
    preloaded_frames: dict[str, pd.DataFrame] | None = None,
    column_aliases: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    runtime = StepsProcRuntime(
        rule_code, rule_data, validated_files, output_dir,
        preloaded_frames=preloaded_frames, column_aliases=column_aliases,
    )
    runtime.execute_to_frames()
    return runtime.export_frame_outputs()


def execute_steps_rule_with_frames(
    rule_code: str,
    rule_data: dict[str, Any],
    validated_files: list[dict[str, Any]],
    output_dir: str,
    preloaded_frames: dict[str, pd.DataFrame] | None = None,
    column_aliases: dict[str, dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runtime = StepsProcRuntime(
        rule_code, rule_data, validated_files, output_dir,
        preloaded_frames=preloaded_frames, column_aliases=column_aliases,
    )
    runtime.execute_to_frames()
    frame_outputs = runtime.export_frame_outputs()
    generated_files = runtime.export_tables()
    return generated_files, frame_outputs


def register_proc_frame_outputs(
    *,
    rule_code: str,
    frame_outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now = time.time()
    _cleanup_memory_frame_registry(now)
    memory_outputs: list[dict[str, Any]] = []
    for item in frame_outputs:
        df = item.get("dataframe")
        if not isinstance(df, pd.DataFrame):
            continue
        target_table = str(item.get("target_table") or "").strip()
        if not target_table:
            continue
        memory_ref = f"proc_frame:{rule_code}:{target_table}:{uuid.uuid4().hex}"
        row_count = int(item.get("row_count") or len(df))
        _MEMORY_FRAME_REGISTRY[memory_ref] = {
            "created_at": now,
            "expires_at": now + MEMORY_FRAME_TTL_SECONDS,
            "rule_code": rule_code,
            "target_table": target_table,
            "row_count": row_count,
            "dataframe": df.copy(),
        }
        memory_outputs.append(
            {
                "target_table": target_table,
                "input_type": "memory",
                "memory_ref": memory_ref,
                "row_count": row_count,
                "expires_in_seconds": MEMORY_FRAME_TTL_SECONDS,
            }
        )
    _cleanup_memory_frame_registry(now)
    return memory_outputs


def resolve_proc_memory_frame(memory_ref: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    now = time.time()
    _cleanup_memory_frame_registry(now)
    ref = str(memory_ref or "").strip()
    item = _MEMORY_FRAME_REGISTRY.get(ref)
    if not item:
        raise KeyError("proc 内存结果不存在或已过期")
    if float(item.get("expires_at") or 0) < now:
        _MEMORY_FRAME_REGISTRY.pop(ref, None)
        raise KeyError("proc 内存结果已过期")
    df = item.get("dataframe")
    if not isinstance(df, pd.DataFrame):
        raise TypeError("proc 内存结果格式无效")
    meta = {key: value for key, value in item.items() if key != "dataframe"}
    return df.copy(), meta


def _cleanup_memory_frame_registry(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired_refs = [
        ref
        for ref, item in _MEMORY_FRAME_REGISTRY.items()
        if float(item.get("expires_at") or 0) < current
    ]
    for ref in expired_refs:
        _MEMORY_FRAME_REGISTRY.pop(ref, None)
    if len(_MEMORY_FRAME_REGISTRY) <= MEMORY_FRAME_MAX_ENTRIES:
        return
    ordered_refs = sorted(
        _MEMORY_FRAME_REGISTRY,
        key=lambda ref: float(_MEMORY_FRAME_REGISTRY[ref].get("created_at") or 0),
    )
    for ref in ordered_refs[: max(0, len(_MEMORY_FRAME_REGISTRY) - MEMORY_FRAME_MAX_ENTRIES)]:
        _MEMORY_FRAME_REGISTRY.pop(ref, None)


class StepsProcRuntime:
    def __init__(
        self,
        rule_code: str,
        rule_data: dict[str, Any],
        validated_files: list[dict[str, Any]],
        output_dir: str,
        preloaded_frames: dict[str, pd.DataFrame] | None = None,
        column_aliases: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.rule_code = rule_code
        self.rule_data = rule_data
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.validated_files = validated_files
        self.preloaded_frames: dict[str, pd.DataFrame] = preloaded_frames or {}
        self.column_aliases: dict[str, dict[str, str]] = column_aliases or {}
        self.table_file_map = {
            str(item.get("table_name") or "").strip(): str(
                item.get("file_path") or item.get("file_name") or ""
            ).strip()
            for item in validated_files
            if str(item.get("table_name") or "").strip()
        }
        self.tables: dict[str, pd.DataFrame] = {}
        self.schemas: dict[str, TableSchemaState] = {}
        self.materialized_targets: list[str] = []
        self._active_alias_frames: dict[str, pd.DataFrame] = {}
        self._lookup_cache: dict[tuple[str, tuple[str, ...]], dict[tuple[Any, ...], dict[str, Any]]] = {}
        self._row_index_cache: dict[str, dict[tuple[Any, ...], int]] = {}
        self._column_lineage: dict[tuple[str, str], dict[str, Any]] = {}
        self._input_plan_frame_keys = {
            key for key in self.preloaded_frames.keys() if str(key).startswith("__input_plan__::")
        }

    def _rule_display_name(self) -> str:
        name = str(self.rule_data.get("name") or "").strip()
        return name or self.rule_code

    def _describe_table(self, table_name: str) -> str:
        if table_name in self.table_file_map:
            return f"文件「{table_name}」"
        return f"中间结果「{table_name}」"

    def _require_columns(
        self, df: pd.DataFrame, columns: list[str], table_name: str
    ) -> None:
        missing = [str(c) for c in columns if str(c) and str(c) not in df.columns]
        if not missing:
            return
        table_desc = self._describe_table(table_name)
        column_list = "「" + "」「".join(missing) + "」"
        plural = "这些列" if len(missing) > 1 else "这一列"
        raise ProcUserDataError(
            summary=f"规则「{self._rule_display_name()}」无法处理{table_desc}",
            cause=f"该规则需要{table_desc}包含列{column_list}，但其中没有{plural}。",
            suggestion="请确认上传的文件含有上述列；若列名相近，检查是否有多余空格或命名不一致。",
        )

    def execute(self) -> list[dict[str, Any]]:
        self.execute_to_frames()
        exports = self.export_tables()
        logger.info(
            "[steps_runtime] steps 规则执行完成: rule_code=%s, exported=%s",
            self.rule_code,
            [(item.get("target_table"), item.get("row_count")) for item in exports],
        )
        return exports

    def execute_to_frames(self) -> None:
        steps = list(self.rule_data.get("steps", []) or [])
        logger.info(
            "[steps_runtime] 开始执行 steps 规则: rule_code=%s, step_count=%s, input_tables=%s",
            self.rule_code,
            len(steps),
            sorted(self.table_file_map.keys()),
        )
        known_step_ids = {
            str(step.get("step_id") or "").strip()
            for step in steps
            if str(step.get("step_id") or "").strip()
        }
        executed_step_ids: set[str] = set()
        pending_steps = list(steps)

        while pending_steps:
            progressed = False
            next_pending: list[dict[str, Any]] = []
            for step in pending_steps:
                step_id = str(step.get("step_id") or "").strip()
                dependencies = [
                    str(item).strip()
                    for item in (step.get("depends_on") or [])
                    if str(item).strip()
                ]
                missing_dependencies = [item for item in dependencies if item not in known_step_ids]
                if missing_dependencies:
                    raise ProcRuleConfigError(
                        summary=f"规则「{self._rule_display_name()}」配置有误",
                        cause=f"step '{step_id or '<anonymous>'}' 依赖未定义: {', '.join(missing_dependencies)}",
                        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                    )
                if not all(item in executed_step_ids for item in dependencies):
                    next_pending.append(step)
                    continue

                self._execute_step(step)
                if step_id:
                    executed_step_ids.add(step_id)
                progressed = True

            if not progressed:
                unresolved = [
                    str(step.get("step_id") or "<anonymous>")
                    for step in next_pending
                ]
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause=f"steps 依赖无法解析，可能存在循环依赖: {', '.join(unresolved)}",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            pending_steps = next_pending
        logger.info(
            "[steps_runtime] steps 规则内存执行完成: rule_code=%s, materialized=%s",
            self.rule_code,
            [(name, len(self.tables[name])) for name in self.materialized_targets if name in self.tables],
        )

    def _execute_step(self, step: dict[str, Any]) -> None:
        action = str(step.get("action") or "").strip()
        target_table = str(step.get("target_table") or "").strip()
        step_id = str(step.get("step_id") or "<anonymous>").strip() or "<anonymous>"
        start_time = time.perf_counter()
        logger.info(
            "[steps_runtime] step start: rule_code=%s step_id=%s action=%s target=%s",
            self.rule_code,
            step_id,
            action,
            target_table,
        )
        if action == "create_schema":
            self._create_schema(step)
        elif action == "write_dataset":
            try:
                self._write_dataset(step)
            except FormulaEvaluationError as exc:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」的步骤执行失败",
                    cause=f"步骤「{step_id}」（{step.get('description') or action}）：{exc}",
                    suggestion="若提示缺少列，请检查上传文件；否则请联系管理员核对规则。",
                ) from exc
        else:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"不支持的 step action: {action}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if target_table and target_table not in self.materialized_targets:
            self.materialized_targets.append(target_table)
        target_df = self.tables.get(target_table)
        logger.info(
            "[steps_runtime] step done: rule_code=%s step_id=%s elapsed=%.3fs rows=%s cols=%s",
            self.rule_code,
            step_id,
            time.perf_counter() - start_time,
            len(target_df) if target_df is not None else "NA",
            len(target_df.columns) if target_df is not None else "NA",
        )

    def _create_schema(self, step: dict[str, Any]) -> None:
        target_table = str(step.get("target_table") or "").strip()
        schema_def = step.get("schema") or {}
        columns = list(schema_def.get("columns") or [])
        dynamic_columns = schema_def.get("dynamic_columns") or {}

        if dynamic_columns:
            months = self._resolve_month_range(dynamic_columns)
            for month in months:
                month_context = {
                    "month": month,
                    "prev_month": _previous_month(month),
                    "is_first_month": month == months[0],
                }
                for pattern in dynamic_columns.get("columns_pattern", []):
                    columns.append(
                        {
                            **pattern,
                            "name": self._render_template_definition(
                                pattern.get("name", ""),
                                pattern.get("variables") or {},
                                month_context,
                            ),
                        }
                    )

        column_order: list[str] = []
        nullable_fields: set[str] = set()
        defaults: dict[str, Any] = {}
        data_types: dict[str, str] = {}
        for column in columns:
            name = str(column.get("name") or "").strip()
            if not name or name in column_order:
                continue
            column_order.append(name)
            if column.get("nullable") is True:
                nullable_fields.add(name)
            defaults[name] = column.get("default")
            data_types[name] = str(column.get("data_type") or "").strip().lower()

        self.schemas[target_table] = TableSchemaState(
            name=target_table,
            primary_key=list(schema_def.get("primary_key") or []),
            column_order=column_order,
            nullable_fields=nullable_fields,
            defaults=defaults,
            data_types=data_types,
            export_layout=dict(schema_def.get("export_layout") or {}),
            export_enabled=bool(schema_def.get("export_enabled", True)),
        )
        self.tables[target_table] = pd.DataFrame(columns=column_order)

    def _write_dataset(self, step: dict[str, Any]) -> None:
        target_table = str(step.get("target_table") or "").strip()
        row_write_mode = str(step.get("row_write_mode") or "").strip() or "upsert"
        if row_write_mode not in VALID_ROW_WRITE_MODES:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"不支持的 row_write_mode: {row_write_mode}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        alias_frames, alias_tables = self._load_alias_frames(step)
        self._active_alias_frames = alias_frames
        self._lookup_cache = {}
        self._check_source_columns(step, alias_frames, alias_tables)
        self._apply_reference_filter(step, alias_frames)
        self._apply_filter(step, alias_frames, alias_tables, target_table)
        self._apply_aggregates(step, alias_frames, alias_tables)

        try:
            self._ensure_table_loaded(target_table)
            target_df = self.tables[target_table]

            if step.get("dynamic_mappings"):
                updated_df = self._apply_dynamic_mappings(
                    step,
                    target_df,
                    alias_frames,
                    alias_tables,
                    target_table,
                    row_write_mode,
                )
            else:
                updated_df = self._apply_standard_mappings(
                    step,
                    target_df,
                    alias_frames,
                    alias_tables,
                    target_table,
                    row_write_mode,
                )

            self.tables[target_table] = self._align_columns(target_table, updated_df)
        finally:
            self._active_alias_frames = {}
            self._lookup_cache = {}

    def _load_alias_frames(
        self, step: dict[str, Any]
    ) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
        alias_frames: dict[str, pd.DataFrame] = {}
        alias_tables: dict[str, str] = {}
        target_table = str(step.get("target_table") or "").strip()
        for source in step.get("sources", []) or []:
            table_name = str(source.get("table") or "").strip()
            alias = str(source.get("alias") or table_name).strip()
            if self._should_skip_unplanned_source(target_table, alias, table_name, step):
                logger.info(
                    "[steps_runtime] input_plan skip unused source: target=%s alias=%s table=%s",
                    target_table,
                    alias,
                    table_name,
                )
                continue
            df = self._ensure_alias_frame_loaded(target_table, alias, table_name).copy()
            alias_frames[alias] = df
            alias_tables[alias] = table_name
        return alias_frames, alias_tables

    def _check_source_columns(
        self,
        step: dict[str, Any],
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
    ) -> None:
        """Check fields that must exist before a step can run correctly.

        Plain source-to-nullable-target mappings intentionally keep the historical runtime behavior:
        a missing source column evaluates to null. Structural references such as filter, aggregate,
        lookup, match, and non-null target writes still fail early with a user-facing message.
        """
        alias_required: dict[str, set[str]] = {}
        target_table = str(step.get("target_table") or "").strip()

        def _add_required(alias: str, field: Any) -> None:
            alias = str(alias or "").strip()
            field = str(field or "").strip()
            if alias and field and alias in alias_frames:
                alias_required.setdefault(alias, set()).add(field)

        def _is_nullable_target_field(field: Any) -> bool:
            target_field = str(field or "").strip()
            if not target_field:
                return False
            schema = self.schemas.get(target_table)
            if not schema:
                return False
            return target_field in schema.nullable_fields and target_field not in schema.primary_key

        def _is_optional_direct_source_mapping(mapping: dict[str, Any]) -> bool:
            value = mapping.get("value") or {}
            if not isinstance(value, dict) or value.get("type") != "source":
                return False
            if "default" in value:
                return True
            return _is_nullable_target_field(mapping.get("target_field"))

        def _collect_source_refs(node: Any) -> None:
            if not isinstance(node, dict):
                return
            if node.get("type") in {"source", "template_source"}:
                source = node.get("source") or {}
                alias = str(source.get("alias") or "").strip()
                field = str(source.get("field") or "").strip()
                if "default" not in node:
                    _add_required(alias, field)
            if node.get("type") == "lookup":
                source_alias = str(node.get("source_alias") or "").strip()
                _add_required(source_alias, node.get("value_field"))
                for key in node.get("keys") or []:
                    if isinstance(key, dict):
                        _add_required(source_alias, key.get("lookup_field"))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    _collect_source_refs(value)

        for mapping in step.get("mappings") or []:
            if not isinstance(mapping, dict) or _is_optional_direct_source_mapping(mapping):
                continue
            _collect_source_refs(mapping.get("value") or {})
            _collect_source_refs(mapping.get("bindings") or {})
        _collect_source_refs(step.get("filter") or {})

        reference_filter = step.get("reference_filter") or {}
        if isinstance(reference_filter, dict) and reference_filter:
            source_alias = str(reference_filter.get("source_alias") or "").strip()
            reference_table = str(reference_filter.get("reference_table") or "").strip()
            reference_df = self._ensure_table_loaded(reference_table) if reference_table else None
            for key in reference_filter.get("keys") or []:
                if isinstance(key, dict):
                    _add_required(source_alias, key.get("source_field"))
                    if reference_df is not None:
                        self._require_columns(
                            reference_df,
                            [str(key.get("reference_field") or "").strip()],
                            reference_table,
                        )

        for source_spec in (step.get("match") or {}).get("sources") or []:
            if not isinstance(source_spec, dict):
                continue
            alias = str(source_spec.get("alias") or "").strip()
            for key in source_spec.get("keys") or []:
                if isinstance(key, dict):
                    _add_required(alias, key.get("field"))

        for agg in step.get("aggregate", []) or []:
            source_alias = str(agg.get("source_alias") or "").strip()
            for field in agg.get("group_fields") or []:
                _add_required(source_alias, field)
            for field_item in agg.get("aggregations") or []:
                field = str(field_item.get("field") or "").strip()
                _add_required(source_alias, field)

        for alias, required_fields in alias_required.items():
            df = alias_frames[alias]
            table_name = alias_tables.get(alias, alias)
            self._require_columns(df, sorted(required_fields), table_name)

    def _should_skip_unplanned_source(
        self,
        target_table: str,
        alias: str,
        table_name: str,
        step: dict[str, Any],
    ) -> bool:
        if not self._input_plan_frame_keys:
            return False
        target_prefix = f"__input_plan__::{target_table}::"
        if not any(key.startswith(target_prefix) for key in self._input_plan_frame_keys):
            return False
        if self._input_plan_frame_key(target_table, alias, table_name) in self._input_plan_frame_keys:
            return False
        return alias not in _collect_step_used_source_aliases(step)

    def _apply_reference_filter(
        self,
        step: dict[str, Any],
        alias_frames: dict[str, pd.DataFrame],
    ) -> None:
        filter_def = step.get("reference_filter") or {}
        if not filter_def:
            return

        source_alias = str(filter_def.get("source_alias") or "").strip()
        reference_table = str(filter_def.get("reference_table") or "").strip()
        keys = list(filter_def.get("keys") or [])

        if source_alias not in alias_frames:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"reference_filter source_alias 不存在: {source_alias}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if not reference_table:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="reference_filter 缺少 reference_table",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if not keys:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="reference_filter.keys 不能为空",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        for idx, item in enumerate(keys):
            if not item.get("source_field") or not item.get("reference_field"):
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause=f"reference_filter.keys[{idx}] 缺少 source_field/reference_field",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )

        source_df = alias_frames[source_alias]
        reference_df = self._ensure_table_loaded(reference_table)
        reference_key_set = {
            tuple(_normalize_key(row.get(item["reference_field"])) for item in keys)
            for _, row in reference_df.iterrows()
        }

        mask = []
        for _, row in source_df.iterrows():
            source_key = tuple(_normalize_key(row.get(item["source_field"])) for item in keys)
            mask.append(source_key in reference_key_set)
        alias_frames[source_alias] = source_df[mask].reset_index(drop=True)

    def _apply_filter(
        self,
        step: dict[str, Any],
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
    ) -> None:
        filter_def = step.get("filter") or {}
        if not filter_def:
            return
        source_defs = list(step.get("sources") or [])
        if not source_defs:
            return
        primary_alias = str(source_defs[0].get("alias") or source_defs[0].get("table") or "").strip()
        if primary_alias not in alias_frames:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"filter source alias 不存在: {primary_alias}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )

        filter_type = str(filter_def.get("type") or "").strip()
        if filter_type != "formula":
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"不支持的 filter.type: {filter_type}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )

        bindings = filter_def.get("bindings") or {}
        expr = str(filter_def.get("expr") or "").strip()
        source_df = alias_frames[primary_alias]

        fast_mask = self._try_build_filter_mask_fast(
            expr=expr,
            bindings=bindings,
            base_alias=primary_alias,
            base_df=source_df,
            alias_frames=alias_frames,
            alias_tables=alias_tables,
            target_table=target_table,
        )
        if fast_mask is not None:
            alias_frames[primary_alias] = source_df[fast_mask].reset_index(drop=True)
            return

        mask = []
        for _, row in source_df.iterrows():
            row_contexts = {primary_alias: row.to_dict()}
            env = {
                name: _normalize_formula_value(
                    self._evaluate_value_spec(
                        value,
                        row_contexts,
                        alias_tables,
                        target_table,
                        {},
                        {},
                    )
                )
                for name, value in bindings.items()
            }
            mask.append(bool(_evaluate_formula_expression(expr, env)))
        alias_frames[primary_alias] = source_df[mask].reset_index(drop=True)

    def _apply_aggregates(
        self,
        step: dict[str, Any],
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
    ) -> None:
        for aggregate in step.get("aggregate", []) or []:
            source_alias = str(aggregate.get("source_alias") or "").strip()
            output_alias = str(aggregate.get("output_alias") or "").strip()
            group_fields = list(aggregate.get("group_fields") or [])
            aggregations = list(aggregate.get("aggregations") or [])

            if source_alias not in alias_frames:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause=f"aggregate source_alias 不存在: {source_alias}",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            if not output_alias:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause="aggregate 缺少 output_alias",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            if not aggregations:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause="aggregate.aggregations 不能为空",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )

            source_df = alias_frames[source_alias]
            _agg_fields = [
                str(item.get("field"))
                for item in aggregations
                if item.get("field")
            ]
            self._require_columns(
                source_df,
                [str(f) for f in group_fields] + _agg_fields,
                alias_tables.get(source_alias, source_alias),
            )
            if not group_fields:
                result_df = pd.DataFrame(
                    [
                        {
                            str(item.get("alias") or item.get("field") or ""): _evaluate_aggregate_series(
                                source_df[item.get("field")],
                                str(item.get("operator") or item.get("function") or "").strip(),
                            )
                            for item in aggregations
                            if str(item.get("alias") or item.get("field") or "").strip()
                        }
                    ]
                )
                alias_frames[output_alias] = result_df
                alias_tables[output_alias] = alias_tables.get(source_alias, source_alias)
                continue

            grouped = source_df.groupby(group_fields, dropna=False, sort=False)
            agg_frames = []
            for item in aggregations:
                field = item.get("field")
                operator = str(item.get("operator") or item.get("function") or "").strip()
                alias = item.get("alias")
                if operator == "sum":
                    series = grouped[field].agg(_series_sum)
                elif operator == "min":
                    series = grouped[field].agg(_series_min)
                else:
                    raise ProcRuleConfigError(
                        summary=f"规则「{self._rule_display_name()}」配置有误",
                        cause=f"不支持的 aggregate operator: {operator}",
                        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                    )
                agg_frames.append(series.rename(alias))
            result_df = pd.concat(agg_frames, axis=1).reset_index()
            alias_frames[output_alias] = result_df
            alias_tables[output_alias] = alias_tables.get(source_alias, source_alias)

    def _apply_standard_mappings(
        self,
        step: dict[str, Any],
        target_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
        row_write_mode: str,
    ) -> pd.DataFrame:
        match_sources = list((step.get("match") or {}).get("sources") or [])
        mappings = list(step.get("mappings") or [])

        if match_sources:
            for source_spec in match_sources:
                alias = str(source_spec.get("alias") or "").strip()
                source_df = alias_frames.get(alias)
                if source_df is None:
                    raise ProcRuleConfigError(
                        summary=f"规则「{self._rule_display_name()}」配置有误",
                        cause=f"match source alias 不存在: {alias}",
                        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                    )
                relevant_mappings = self._select_relevant_mappings(mappings, alias, len(match_sources))
                for _, source_row in source_df.iterrows():
                    key_map = {
                        item["target_field"]: source_row.get(item["field"])
                        for item in source_spec.get("keys", []) or []
                    }
                    row_index = self._locate_or_create_target_row(
                        target_table,
                        target_df,
                        key_map,
                        row_write_mode,
                    )
                    if row_index is None:
                        continue
                    target_row = target_df.loc[row_index].to_dict()
                    row_contexts = {alias: source_row.to_dict()}
                    target_row = self._apply_mapping_group(
                        relevant_mappings,
                        target_df,
                        row_index,
                        row_contexts,
                        alias_tables,
                        target_row,
                        target_table,
                        {},
                    )
            return target_df

        base_aliases = self._infer_base_aliases(step, alias_frames)
        if len(base_aliases) != 1:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="无 match 的 write_dataset 仅支持单一基础 alias",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        base_alias = base_aliases[0]

        fast_df = self._try_apply_standard_mappings_fast(
            mappings=mappings,
            base_alias=base_alias,
            target_df=target_df,
            alias_frames=alias_frames,
            alias_tables=alias_tables,
            target_table=target_table,
            row_write_mode=row_write_mode,
        )
        if fast_df is not None:
            return fast_df

        for _, source_row in alias_frames[base_alias].iterrows():
            row_contexts = {base_alias: source_row.to_dict()}
            row_values = self._evaluate_mappings_to_dict(
                mappings,
                row_contexts,
                alias_tables,
                target_table,
                {},
                current_target_row={},
            )
            key_map = self._resolve_row_key_map(target_table, row_values)
            row_index = self._locate_or_create_target_row(
                target_table,
                target_df,
                key_map,
                row_write_mode,
            )
            if row_index is None:
                continue
            target_row = target_df.loc[row_index].to_dict()
            self._apply_row_values(
                mappings,
                row_values,
                target_df,
                row_index,
                target_row,
                target_table,
                alias_tables,
            )
        return target_df

    def _try_build_filter_mask_fast(
        self,
        *,
        expr: str,
        bindings: dict[str, Any],
        base_alias: str,
        base_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
    ) -> pd.Series | None:
        if base_df.empty:
            return pd.Series(dtype=bool)
        try:
            env = {
                name: self._ensure_series(
                    self._evaluate_value_spec_series(
                        spec,
                        base_alias=base_alias,
                        base_df=base_df,
                        alias_frames=alias_frames,
                        alias_tables=alias_tables,
                        target_table=target_table,
                        contexts={},
                    ),
                    index=base_df.index,
                )
                for name, spec in bindings.items()
            }
        except _FastPathNotSupported:
            return None
        return self._evaluate_formula_to_mask(expr, env, index=base_df.index)

    def _try_apply_standard_mappings_fast(
        self,
        *,
        mappings: list[dict[str, Any]],
        base_alias: str,
        target_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
        row_write_mode: str,
    ) -> pd.DataFrame | None:
        if not target_df.empty:
            return None
        if row_write_mode not in {"upsert", "insert_if_missing"}:
            return None
        if any(str(mapping.get("field_write_mode") or "overwrite") != "overwrite" for mapping in mappings):
            return None

        base_df = alias_frames.get(base_alias)
        if base_df is None:
            return None
        if base_df.empty:
            return target_df

        try:
            result_df = self._build_result_frame_fast(
                mappings=mappings,
                base_alias=base_alias,
                base_df=base_df,
                alias_frames=alias_frames,
                alias_tables=alias_tables,
                target_table=target_table,
            )
        except _FastPathNotSupported:
            return None

        primary_key = list(self.schemas.get(target_table, TableSchemaState(target_table)).primary_key)
        if primary_key and all(field in result_df.columns for field in primary_key):
            result_df = result_df.drop_duplicates(subset=primary_key, keep="last").reset_index(drop=True)
        self._invalidate_row_index_cache(target_table)
        return result_df

    def _build_result_frame_fast(
        self,
        *,
        mappings: list[dict[str, Any]],
        base_alias: str,
        base_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
    ) -> pd.DataFrame:
        schema = self.schemas.get(target_table)
        if schema and schema.column_order:
            result_df = pd.DataFrame(
                {
                    column: [schema.defaults.get(column)] * len(base_df)
                    for column in schema.column_order
                },
                index=base_df.index,
            )
        else:
            result_df = pd.DataFrame(index=base_df.index)

        for mapping in mappings:
            target_field = mapping.get("target_field")
            if not target_field:
                raise _FastPathNotSupported("fast path 暂不支持 target_field_template")
            self._record_column_lineage(target_table, str(target_field), mapping, alias_tables)
            values = self._evaluate_mapping_series(
                mapping,
                base_alias=base_alias,
                base_df=base_df,
                alias_frames=alias_frames,
                alias_tables=alias_tables,
                target_table=target_table,
                contexts={},
            )
            result_df[str(target_field)] = values

        result_df = result_df.reset_index(drop=True)
        return self._align_columns(target_table, result_df)

    def _evaluate_mapping_series(
        self,
        mapping: dict[str, Any],
        *,
        base_alias: str,
        base_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
        contexts: dict[str, Any],
    ) -> pd.Series:
        values = self._evaluate_value_spec_series(
            mapping.get("value") or {},
            base_alias=base_alias,
            base_df=base_df,
            alias_frames=alias_frames,
            alias_tables=alias_tables,
            target_table=target_table,
            contexts=contexts,
            bindings_override=mapping.get("bindings") or {},
        )
        return self._ensure_series(values, index=base_df.index)

    def _evaluate_value_spec_series(
        self,
        spec: dict[str, Any],
        *,
        base_alias: str,
        base_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
        contexts: dict[str, Any],
        bindings_override: dict[str, Any] | None = None,
    ) -> pd.Series | Any:
        spec_type = str(spec.get("type") or "").strip()
        if not spec_type:
            return spec

        if spec_type == "source":
            source = spec.get("source") or {}
            alias = str(source.get("alias") or "").strip()
            field = str(source.get("field") or "").strip()
            if alias != base_alias or alias_tables.get(alias) == target_table:
                raise _FastPathNotSupported(f"fast path 暂不支持直接读取 alias={alias}")
            if field not in base_df.columns:
                series = pd.Series([None] * len(base_df), index=base_df.index)
            else:
                series = base_df[field].reset_index(drop=True)
                series.index = base_df.index
            if "default" in spec:
                default = spec.get("default")
                return series.where(~series.apply(_is_nullish), default)
            return series

        if spec_type == "context":
            return contexts.get(spec.get("name"))

        if spec_type == "lookup":
            return self._evaluate_lookup_series(
                spec,
                base_alias=base_alias,
                base_df=base_df,
                alias_frames=alias_frames,
                alias_tables=alias_tables,
                target_table=target_table,
                contexts=contexts,
            )

        if spec_type == "formula":
            bindings = bindings_override or spec.get("bindings") or {}
            env = {
                name: self._ensure_series(
                    self._evaluate_value_spec_series(
                        value,
                        base_alias=base_alias,
                        base_df=base_df,
                        alias_frames=alias_frames,
                        alias_tables=alias_tables,
                        target_table=target_table,
                        contexts=contexts,
                    ),
                    index=base_df.index,
                )
                for name, value in bindings.items()
            }
            expr = str(spec.get("expr") or spec.get("formula") or "").strip()
            return self._evaluate_formula_to_series(expr, env, index=base_df.index)

        raise _FastPathNotSupported(f"fast path 暂不支持 value.type={spec_type}")

    def _evaluate_lookup_series(
        self,
        node: dict[str, Any],
        *,
        base_alias: str,
        base_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
        contexts: dict[str, Any],
    ) -> pd.Series:
        source_alias = str(node.get("source_alias") or "").strip()
        keys = list(node.get("keys") or [])
        value_field = str(node.get("value_field") or "").strip()
        default = node.get("default")

        if source_alias not in alias_frames or not value_field or not keys:
            raise _FastPathNotSupported("lookup 配置不完整")

        lookup_fields: list[str] = []
        key_series_list: list[pd.Series] = []
        for idx, item in enumerate(keys):
            lookup_field = str(item.get("lookup_field") or "").strip()
            input_spec = item.get("input")
            if not lookup_field or not isinstance(input_spec, dict) or not input_spec:
                raise _FastPathNotSupported(f"lookup.keys[{idx}] 配置不完整")
            lookup_fields.append(lookup_field)
            key_series_list.append(
                self._ensure_series(
                    self._evaluate_value_spec_series(
                        input_spec,
                        base_alias=base_alias,
                        base_df=base_df,
                        alias_frames=alias_frames,
                        alias_tables=alias_tables,
                        target_table=target_table,
                        contexts=contexts,
                    ),
                    index=base_df.index,
                )
            )

        index = self._get_lookup_index(source_alias, tuple(lookup_fields))
        values: list[Any] = []
        for row_idx in range(len(base_df)):
            key = tuple(_normalize_key(series.iat[row_idx]) for series in key_series_list)
            matched_row = index.get(key)
            if matched_row is None:
                values.append(default if "default" in node else None)
                continue
            value = matched_row.get(value_field)
            if _is_nullish(value) and "default" in node:
                value = default
            values.append(value)
        return pd.Series(values, index=base_df.index)

    def _evaluate_formula_to_series(
        self,
        expr: str,
        env: dict[str, pd.Series],
        *,
        index: pd.Index,
    ) -> pd.Series:
        values: list[Any] = []
        for row_idx in range(len(index)):
            row_env = {
                name: _normalize_formula_value(series.iat[row_idx])
                for name, series in env.items()
            }
            values.append(_evaluate_formula_expression(expr, row_env))
        return pd.Series(values, index=index)

    def _evaluate_formula_to_mask(
        self,
        expr: str,
        env: dict[str, pd.Series],
        *,
        index: pd.Index,
    ) -> pd.Series:
        values: list[bool] = []
        for row_idx in range(len(index)):
            row_env = {
                name: _normalize_formula_value(series.iat[row_idx])
                for name, series in env.items()
            }
            values.append(bool(_evaluate_formula_expression(expr, row_env)))
        return pd.Series(values, index=index, dtype=bool)

    def _ensure_series(
        self,
        value: pd.Series | Any,
        *,
        index: pd.Index,
    ) -> pd.Series:
        if isinstance(value, pd.Series):
            series = value.reset_index(drop=True)
            series.index = index
            return series
        return pd.Series([value] * len(index), index=index)

    def _apply_dynamic_mappings(
        self,
        step: dict[str, Any],
        target_df: pd.DataFrame,
        alias_frames: dict[str, pd.DataFrame],
        alias_tables: dict[str, str],
        target_table: str,
        row_write_mode: str,
    ) -> pd.DataFrame:
        dynamic_def = step.get("dynamic_mappings") or {}
        mappings = list(dynamic_def.get("mappings") or [])
        match_sources = list((step.get("match") or {}).get("sources") or [])
        months = self._resolve_month_range(dynamic_def)

        if not match_sources:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="dynamic_mappings 需要同时配置 match.sources",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )

        for idx, month in enumerate(months):
            contexts = {
                "month": month,
                "prev_month": _previous_month(month),
                "is_first_month": idx == 0,
            }
            for source_spec in match_sources:
                alias = str(source_spec.get("alias") or "").strip()
                source_df = alias_frames.get(alias)
                if source_df is None:
                    raise ProcRuleConfigError(
                        summary=f"规则「{self._rule_display_name()}」配置有误",
                        cause=f"dynamic match source alias 不存在: {alias}",
                        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                    )
                for _, source_row in source_df.iterrows():
                    key_map = {
                        item["target_field"]: source_row.get(item["field"])
                        for item in source_spec.get("keys", []) or []
                    }
                    row_index = self._locate_or_create_target_row(
                        target_table,
                        target_df,
                        key_map,
                        row_write_mode,
                    )
                    if row_index is None:
                        continue
                    target_row = target_df.loc[row_index].to_dict()
                    row_contexts = {alias: source_row.to_dict()}
                    if alias_tables.get(alias) == target_table:
                        row_contexts[alias] = dict(target_row)
                    target_row = self._apply_mapping_group(
                        mappings,
                        target_df,
                        row_index,
                        row_contexts,
                        alias_tables,
                        target_row,
                        target_table,
                        contexts,
                    )
            target_df = self._align_columns(target_table, target_df)
        return target_df

    def _evaluate_mappings_to_dict(
        self,
        mappings: list[dict[str, Any]],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        contexts: dict[str, Any],
        current_target_row: dict[str, Any],
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for mapping in mappings:
            target_field = self._resolve_target_field(mapping, row_contexts, alias_tables, contexts)
            if not target_field:
                continue
            values[target_field] = self._evaluate_mapping_value(
                mapping,
                row_contexts,
                alias_tables,
                target_table,
                contexts,
                current_target_row,
            )
        return values

    def _apply_mapping_group(
        self,
        mappings: list[dict[str, Any]],
        target_df: pd.DataFrame,
        row_index: int,
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        current_target_row: dict[str, Any],
        target_table: str,
        contexts: dict[str, Any],
    ) -> dict[str, Any]:
        for mapping in mappings:
            target_field = self._resolve_target_field(mapping, row_contexts, alias_tables, contexts)
            if not target_field:
                continue
            try:
                value = self._evaluate_mapping_value(
                    mapping,
                    row_contexts,
                    alias_tables,
                    target_table,
                    contexts,
                    current_target_row,
                )
            except FormulaEvaluationError as exc:
                raise self._build_formula_context_error(
                    exc,
                    mapping,
                    target_table,
                    target_field,
                    row_contexts,
                    alias_tables,
                    current_target_row,
                    contexts,
                ) from exc
            self._ensure_column_exists(target_table, target_df, target_field)
            self._record_column_lineage(target_table, target_field, mapping, alias_tables)
            current_value = current_target_row.get(target_field)
            field_write_mode = str(mapping.get("field_write_mode") or "overwrite")
            new_value = self._apply_field_write_mode(field_write_mode, current_value, value)
            new_value = self._normalize_value_for_column(target_table, target_field, new_value)
            target_df.at[row_index, target_field] = new_value
            current_target_row[target_field] = new_value
            if (
                target_field in self.schemas.get(target_table, TableSchemaState(target_table)).primary_key
                and new_value != current_value
            ):
                self._invalidate_row_index_cache(target_table)
            for alias, origin_table in alias_tables.items():
                if origin_table == target_table and alias in row_contexts:
                    row_contexts[alias][target_field] = new_value
        return current_target_row

    def _apply_row_values(
        self,
        mappings: list[dict[str, Any]],
        row_values: dict[str, Any],
        target_df: pd.DataFrame,
        row_index: int,
        current_target_row: dict[str, Any],
        target_table: str,
        alias_tables: dict[str, str],
    ) -> None:
        for mapping in mappings:
            target_field = mapping.get("target_field")
            if not target_field:
                continue
            value = row_values.get(target_field)
            current_value = current_target_row.get(target_field)
            field_write_mode = str(mapping.get("field_write_mode") or "overwrite")
            new_value = self._apply_field_write_mode(field_write_mode, current_value, value)
            new_value = self._normalize_value_for_column(target_table, target_field, new_value)
            self._ensure_column_exists(target_table, target_df, target_field)
            self._record_column_lineage(target_table, str(target_field), mapping, alias_tables)
            target_df.at[row_index, target_field] = new_value
            current_target_row[target_field] = new_value
            if (
                target_field in self.schemas.get(target_table, TableSchemaState(target_table)).primary_key
                and new_value != current_value
            ):
                self._invalidate_row_index_cache(target_table)

    def _evaluate_mapping_value(
        self,
        mapping: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        contexts: dict[str, Any],
        current_target_row: dict[str, Any],
    ) -> Any:
        value_node = mapping.get("value") or {}
        node_type = value_node.get("type")

        if node_type == "source":
            return self._evaluate_source_node(
                value_node,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
            )
        if node_type == "template_source":
            return self._evaluate_template_source_node(
                value_node,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
        if node_type == "context":
            return contexts.get(value_node.get("name"))
        if node_type == "function":
            return self._evaluate_function_node(value_node, row_contexts, alias_tables, target_table, current_target_row, contexts)
        if node_type == "lookup":
            return self._evaluate_lookup_node(
                value_node,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
        if node_type == "formula":
            bindings = mapping.get("bindings") or value_node.get("bindings") or {}
            env = self._evaluate_formula_bindings(
                bindings,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            expr = value_node.get("expr", "")
            if not expr and isinstance(value_node.get("formula"), str):
                expr = value_node.get("formula", "")
            return _evaluate_formula_expression(expr, env)
        raise ProcRuleConfigError(
            summary=f"规则「{self._rule_display_name()}」配置有误",
            cause=f"不支持的 value.type: {node_type}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    def _evaluate_value_spec(
        self,
        spec: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        current_target_row: dict[str, Any],
        contexts: dict[str, Any],
    ) -> Any:
        spec_type = spec.get("type")
        if spec_type == "source":
            return self._evaluate_source_node(spec, row_contexts, alias_tables, target_table, current_target_row)
        if spec_type == "template_source":
            return self._evaluate_template_source_node(
                spec,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
        if spec_type == "context":
            return contexts.get(spec.get("name"))
        if spec_type == "function":
            return self._evaluate_function_node(spec, row_contexts, alias_tables, target_table, current_target_row, contexts)
        if spec_type == "lookup":
            return self._evaluate_lookup_node(
                spec,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
        if spec_type == "formula":
            env = self._evaluate_formula_bindings(
                spec.get("bindings") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            expr = spec.get("expr", "")
            if not expr and isinstance(spec.get("formula"), str):
                expr = spec.get("formula", "")
            return _evaluate_formula_expression(expr, env)
        return spec

    def _evaluate_formula_bindings(
        self,
        bindings: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        current_target_row: dict[str, Any],
        contexts: dict[str, Any],
    ) -> dict[str, Any]:
        env: dict[str, Any] = {}
        metadata: dict[str, dict[str, Any]] = {}
        for name, spec in bindings.items():
            raw_value = self._evaluate_value_spec(
                spec,
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            env[name] = _normalize_formula_value(raw_value)
            metadata[name] = self._describe_formula_binding_source(
                spec,
                raw_value,
                row_contexts,
                alias_tables,
            )
        env["__metadata__"] = metadata
        return env

    def _describe_formula_binding_source(
        self,
        spec: Any,
        raw_value: Any,
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
    ) -> dict[str, Any]:
        if not isinstance(spec, dict):
            return {"value": raw_value, "type": type(raw_value).__name__}
        spec_type = spec.get("type")
        if spec_type == "source":
            source = spec.get("source") or {}
            alias = str(source.get("alias") or "").strip()
            field = str(source.get("field") or "").strip()
            table = alias_tables.get(alias, alias)
            return {
                "table": table,
                "alias": alias,
                "field": field,
                "lineage": self._column_lineage.get((table, field)),
                "value": raw_value,
                "type": type(raw_value).__name__,
            }
        if spec_type == "function":
            return {
                "function": str(spec.get("function") or "").strip(),
                "value": raw_value,
                "type": type(raw_value).__name__,
            }
        if spec_type == "lookup":
            source_alias = str(spec.get("source_alias") or "").strip()
            return {
                "table": alias_tables.get(source_alias, source_alias),
                "alias": source_alias,
                "field": str(spec.get("value_field") or "").strip(),
                "value": raw_value,
                "type": type(raw_value).__name__,
            }
        if spec_type == "formula":
            return {"formula": str(spec.get("expr") or spec.get("formula") or ""), "value": raw_value, "type": type(raw_value).__name__}
        return {"value": raw_value, "type": type(raw_value).__name__}

    def _record_column_lineage(
        self,
        target_table: str,
        target_field: str,
        mapping: dict[str, Any],
        alias_tables: dict[str, str],
    ) -> None:
        lineage = self._lineage_from_value_spec(mapping.get("value") or {}, alias_tables)
        if not lineage:
            return
        self._column_lineage[(target_table, target_field)] = lineage

    def _lineage_from_value_spec(
        self,
        spec: Any,
        alias_tables: dict[str, str],
    ) -> dict[str, Any] | None:
        if not isinstance(spec, dict):
            return None
        spec_type = spec.get("type")
        if spec_type == "source":
            source = spec.get("source") or {}
            alias = str(source.get("alias") or "").strip()
            field = str(source.get("field") or "").strip()
            if not alias or not field:
                return None
            return {
                "table": alias_tables.get(alias, alias),
                "alias": alias,
                "field": field,
            }
        if spec_type == "lookup":
            source_alias = str(spec.get("source_alias") or "").strip()
            value_field = str(spec.get("value_field") or "").strip()
            if not source_alias or not value_field:
                return None
            return {
                "table": alias_tables.get(source_alias, source_alias),
                "alias": source_alias,
                "field": value_field,
            }
        if spec_type == "formula":
            bindings = spec.get("bindings") or {}
            if len(bindings) == 1:
                return self._lineage_from_value_spec(next(iter(bindings.values())), alias_tables)
        return None

    def _build_formula_context_error(
        self,
        error: FormulaEvaluationError,
        mapping: dict[str, Any],
        target_table: str,
        target_field: str,
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        current_target_row: dict[str, Any],
        contexts: dict[str, Any],
    ) -> FormulaEvaluationError:
        value_node = mapping.get("value") or {}
        expr = str(value_node.get("expr") or value_node.get("formula") or "")
        bindings = mapping.get("bindings") or value_node.get("bindings") or {}
        details = [str(error)]
        if target_table or target_field:
            details.append(f"目标字段：{target_table}.{target_field}".strip("."))
        if expr:
            details.append(f"公式：{expr}")

        related_names = list(error.binding_names or [])
        if not related_names:
            related_names = list(bindings.keys())
        binding_lines: list[str] = []
        for name in related_names:
            if name not in bindings:
                continue
            raw_value = self._evaluate_value_spec(
                bindings[name],
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            source = self._describe_formula_binding_source(
                bindings[name],
                raw_value,
                row_contexts,
                alias_tables,
            )
            binding_lines.append(f"{name}={_format_binding_source_for_error(source)}")
        if binding_lines:
            details.append("相关变量：" + "；".join(binding_lines))

        details.append("请检查上述字段是否为日期格式，空值请留空，不要使用 \\N、待确认 等文本。")
        return FormulaEvaluationError("；".join(details), binding_names=error.binding_names)

    def _evaluate_source_node(
        self,
        node: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        current_target_row: dict[str, Any],
    ) -> Any:
        source = node.get("source") or {}
        alias = str(source.get("alias") or "").strip()
        field = str(source.get("field") or "").strip()
        default = node.get("default")
        if alias_tables.get(alias) == target_table and field in current_target_row:
            value = current_target_row.get(field)
        else:
            value = (row_contexts.get(alias) or {}).get(field)
        return default if _is_nullish(value) and "default" in node else value

    def _evaluate_template_source_node(
        self,
        node: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        current_target_row: dict[str, Any],
        contexts: dict[str, Any],
    ) -> Any:
        source = node.get("source") or {}
        alias = str(source.get("alias") or "").strip()
        field_name = self._render_template_definition(
            node.get("template", ""),
            node.get("variables") or {},
            contexts,
            row_contexts=row_contexts,
            alias_tables=alias_tables,
            target_table=target_table,
            current_target_row=current_target_row,
        )
        default = node.get("default")
        if alias_tables.get(alias) == target_table and field_name in current_target_row:
            value = current_target_row.get(field_name)
        else:
            value = (row_contexts.get(alias) or {}).get(field_name)
        return default if _is_nullish(value) and "default" in node else value

    def _evaluate_function_node(
        self,
        node: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        current_target_row: dict[str, Any],
        contexts: dict[str, Any],
    ) -> Any:
        function_name = str(node.get("function") or "").strip()
        args = node.get("args") or {}

        if function_name == "current_date":
            return _current_date()
        if function_name == "add_months":
            date_value = self._evaluate_value_spec(
                args.get("date") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            months_value = self._evaluate_value_spec(
                args.get("months") or args.get("offset") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            return _add_months(date_value, months_value)
        if function_name == "month_of":
            value = self._evaluate_value_spec(
                args.get("date") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            return _as_month(value)
        if function_name == "fraction_numerator":
            value = self._evaluate_value_spec(
                args.get("value") or args.get("text") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            return _extract_fraction_numerator(value)
        if function_name == "to_decimal":
            value = self._evaluate_value_spec(
                args.get("value") or args.get("text") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            return _to_decimal(value)
        if function_name == "strip_prefix":
            value = self._evaluate_value_spec(
                args.get("value") or args.get("text") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            prefix = self._evaluate_value_spec(
                args.get("prefix") or {},
                row_contexts,
                alias_tables,
                target_table,
                current_target_row,
                contexts,
            )
            return _strip_prefix(value, prefix)
        if function_name == "earliest_date":
            source_table = str(args.get("source") or "").strip()
            date_field = str(args.get("date_field") or "").strip()
            output_format = str(args.get("output_format") or "").strip()
            offset = int(args.get("offset") or 0)
            df = self._ensure_table_loaded(source_table)
            if date_field not in df.columns:
                raise ProcUserDataError(
                    summary=f"规则「{self._rule_display_name()}」无法计算日期",
                    cause=f"{self._describe_table(source_table)}中没有列「{date_field}」。",
                    suggestion="请确认该文件包含上述日期列。",
                )
            series = pd.to_datetime(df[date_field], errors="coerce").dropna()
            if series.empty:
                raise ProcUserDataError(
                    summary=f"规则「{self._rule_display_name()}」无法计算日期",
                    cause=f"{self._describe_table(source_table)}的列「{date_field}」中没有有效日期。",
                    suggestion="请检查该列的日期是否填写完整、格式是否规范。",
                )
            earliest = series.min()
            if output_format == "month":
                return _offset_month(int(earliest.month), offset)
            if offset:
                earliest = earliest + pd.DateOffset(months=offset)
            return earliest.date()
        raise ProcRuleConfigError(
            summary=f"规则「{self._rule_display_name()}」配置有误",
            cause=f"不支持的 function: {function_name}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    def _evaluate_lookup_node(
        self,
        node: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        target_table: str,
        current_target_row: dict[str, Any],
        contexts: dict[str, Any],
    ) -> Any:
        source_alias = str(node.get("source_alias") or "").strip()
        keys = list(node.get("keys") or [])
        value_field = str(node.get("value_field") or "").strip()
        default = node.get("default")

        if not source_alias:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="lookup 缺少 source_alias",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if source_alias not in self._active_alias_frames:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"lookup source_alias 不存在: {source_alias}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if not value_field:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="lookup 缺少 value_field",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if not keys:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause="lookup.keys 不能为空",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )

        lookup_fields: list[str] = []
        lookup_key: list[Any] = []
        for idx, item in enumerate(keys):
            lookup_field = str(item.get("lookup_field") or "").strip()
            input_spec = item.get("input")
            if not lookup_field:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause=f"lookup.keys[{idx}] 缺少 lookup_field",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            if not isinstance(input_spec, dict) or not input_spec:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause=f"lookup.keys[{idx}] 缺少 input",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            lookup_fields.append(lookup_field)
            lookup_key.append(
                _normalize_key(
                    self._evaluate_value_spec(
                        input_spec,
                        row_contexts,
                        alias_tables,
                        target_table,
                        current_target_row,
                        contexts,
                    )
                )
            )

        index = self._get_lookup_index(source_alias, tuple(lookup_fields))
        matched_row = index.get(tuple(lookup_key))
        if matched_row is None:
            return default if "default" in node else None
        value = matched_row.get(value_field)
        return default if _is_nullish(value) and "default" in node else value

    def _get_lookup_index(
        self,
        source_alias: str,
        lookup_fields: tuple[str, ...],
    ) -> dict[tuple[Any, ...], dict[str, Any]]:
        cache_key = (source_alias, lookup_fields)
        cached = self._lookup_cache.get(cache_key)
        if cached is not None:
            return cached

        lookup_df = self._active_alias_frames[source_alias]
        index: dict[tuple[Any, ...], dict[str, Any]] = {}
        for _, row in lookup_df.iterrows():
            row_dict = row.to_dict()
            key = tuple(_normalize_key(row_dict.get(field)) for field in lookup_fields)
            index.setdefault(key, row_dict)
        self._lookup_cache[cache_key] = index
        return index

    def _resolve_target_field(
        self,
        mapping: dict[str, Any],
        row_contexts: dict[str, dict[str, Any]],
        alias_tables: dict[str, str],
        contexts: dict[str, Any],
    ) -> str:
        target_field = mapping.get("target_field")
        if target_field:
            return str(target_field)
        template = mapping.get("target_field_template") or {}
        return self._render_template_definition(
            template.get("template", ""),
            template.get("variables") or {},
            contexts,
            row_contexts=row_contexts,
            alias_tables=alias_tables,
            current_target_row={},
        )

    def _render_template_definition(
        self,
        template: str,
        variables: dict[str, Any],
        contexts: dict[str, Any],
        row_contexts: Optional[dict[str, dict[str, Any]]] = None,
        alias_tables: Optional[dict[str, str]] = None,
        target_table: str = "",
        current_target_row: Optional[dict[str, Any]] = None,
    ) -> str:
        rendered = str(template)
        for name, spec in variables.items():
            value = self._evaluate_value_spec(
                spec,
                row_contexts or {},
                alias_tables or {},
                target_table,
                current_target_row or {},
                contexts,
            )
            rendered = rendered.replace(f"{{{name}}}", "" if value is None else str(value))
        return rendered

    def _infer_base_aliases(
        self,
        step: dict[str, Any],
        alias_frames: dict[str, pd.DataFrame],
    ) -> list[str]:
        referenced_aliases = []
        for mapping in step.get("mappings", []) or []:
            referenced_aliases.extend(sorted(_collect_aliases(mapping)))
        if referenced_aliases:
            return list(dict.fromkeys(alias for alias in referenced_aliases if alias in alias_frames))
        return list(alias_frames.keys())

    def _select_relevant_mappings(
        self,
        mappings: list[dict[str, Any]],
        alias: str,
        match_source_count: int,
    ) -> list[dict[str, Any]]:
        selected = []
        for mapping in mappings:
            aliases = _collect_aliases(mapping)
            if alias in aliases:
                selected.append(mapping)
            elif not aliases and match_source_count == 1:
                selected.append(mapping)
        return selected

    def _resolve_row_key_map(
        self,
        target_table: str,
        row_values: dict[str, Any],
    ) -> dict[str, Any]:
        primary_key = self.schemas.get(target_table, TableSchemaState(target_table)).primary_key
        if not primary_key:
            return {}
        return {field: row_values.get(field) for field in primary_key}

    def _locate_or_create_target_row(
        self,
        target_table: str,
        target_df: pd.DataFrame,
        key_map: dict[str, Any],
        row_write_mode: str,
    ) -> Optional[int]:
        row_index = self._find_row_index(target_table, target_df, key_map)
        if row_index is not None:
            return row_index
        if row_write_mode not in {"upsert", "insert_if_missing"}:
            return None
        new_row = self._build_default_row(target_table)
        for field, value in key_map.items():
            new_row[field] = value
            self._ensure_column_exists(target_table, target_df, field)
        target_df.loc[len(target_df)] = new_row
        row_index = int(len(target_df) - 1)
        self._update_row_index_cache(target_table, key_map, row_index)
        return row_index

    def _find_row_index(
        self,
        target_table: str,
        df: pd.DataFrame,
        key_map: dict[str, Any],
    ) -> Optional[int]:
        if df.empty:
            return None
        if not key_map:
            return None
        cache_key = self._normalize_row_key(target_table, key_map)
        if cache_key is not None:
            cached = self._get_row_index_cache(target_table, df).get(cache_key)
            if cached is not None:
                return cached
        mask = pd.Series([True] * len(df), index=df.index)
        for field, value in key_map.items():
            if field not in df.columns:
                return None
            mask = mask & (df[field].apply(_normalize_key) == _normalize_key(value))
        matches = df.index[mask]
        if not len(matches):
            return None
        row_index = int(matches[0])
        self._update_row_index_cache(target_table, key_map, row_index)
        return row_index

    def _normalize_row_key(
        self,
        target_table: str,
        key_map: dict[str, Any],
    ) -> Optional[tuple[Any, ...]]:
        schema = self.schemas.get(target_table)
        primary_key = list(schema.primary_key) if schema else []
        if not primary_key:
            return None
        if any(field not in key_map for field in primary_key):
            return None
        return tuple(_normalize_key(key_map.get(field)) for field in primary_key)

    def _get_row_index_cache(
        self,
        target_table: str,
        df: pd.DataFrame,
    ) -> dict[tuple[Any, ...], int]:
        cached = self._row_index_cache.get(target_table)
        if cached is not None:
            return cached

        schema = self.schemas.get(target_table)
        primary_key = list(schema.primary_key) if schema else []
        if not primary_key or any(field not in df.columns for field in primary_key):
            cached = {}
            self._row_index_cache[target_table] = cached
            return cached

        cached = {}
        for row_index, row in df.iterrows():
            key = tuple(_normalize_key(row.get(field)) for field in primary_key)
            cached.setdefault(key, int(row_index))
        self._row_index_cache[target_table] = cached
        return cached

    def _update_row_index_cache(
        self,
        target_table: str,
        key_map: dict[str, Any],
        row_index: int,
    ) -> None:
        key = self._normalize_row_key(target_table, key_map)
        if key is None:
            return
        cached = self._row_index_cache.setdefault(target_table, {})
        cached[key] = row_index

    def _invalidate_row_index_cache(self, target_table: str) -> None:
        self._row_index_cache.pop(target_table, None)

    def _build_default_row(self, table_name: str) -> dict[str, Any]:
        schema = self.schemas.get(table_name)
        if not schema:
            df = self.tables.get(table_name)
            if df is None:
                return {}
            return {column: None for column in df.columns}
        return {column: schema.defaults.get(column) for column in schema.column_order}

    def _ensure_column_exists(
        self,
        table_name: str,
        df: pd.DataFrame,
        column_name: str,
    ) -> None:
        if column_name not in df.columns:
            df[column_name] = None
        else:
            df[column_name] = df[column_name].astype("object")
        schema = self.schemas.get(table_name)
        if schema and column_name not in schema.column_order:
            schema.column_order.append(column_name)
            schema.defaults.setdefault(column_name, None)
            schema.data_types.setdefault(column_name, "")

    def _align_columns(self, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
        schema = self.schemas.get(table_name)
        if not schema:
            return df
        df = self._normalize_dataframe_for_schema(schema, df)
        ordered = [column for column in schema.column_order if column in df.columns]
        extras = [column for column in df.columns if column not in ordered]
        return df[ordered + extras]

    def _normalize_dataframe_for_schema(self, schema: TableSchemaState, df: pd.DataFrame) -> pd.DataFrame:
        for column_name, data_type in schema.data_types.items():
            if data_type != "decimal" or column_name not in df.columns:
                continue
            df[column_name] = df[column_name].map(_normalize_decimal_cell)
        return df

    def _normalize_value_for_column(self, table_name: str, column_name: str, value: Any) -> Any:
        schema = self.schemas.get(table_name)
        if not schema or schema.data_types.get(column_name) != "decimal":
            return value
        return _normalize_decimal_cell(value)

    def _ensure_alias_frame_loaded(
        self,
        target_table: str,
        alias: str,
        table_name: str,
    ) -> pd.DataFrame:
        input_plan_key = self._input_plan_frame_key(target_table, alias, table_name)
        if input_plan_key in self.preloaded_frames:
            return self.preloaded_frames[input_plan_key]
        target_prefix = f"__input_plan__::{target_table}::"
        if any(key.startswith(target_prefix) for key in self._input_plan_frame_keys):
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=(
                    "input_plan 未加载到当前 source 数据："
                    f"{target_table}.{alias}({table_name})。请重新生成数据整理规则或检查运行计划数据绑定。"
                ),
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        return self._ensure_table_loaded(table_name)

    @staticmethod
    def _input_plan_frame_key(target_table: str, alias: str, table_name: str) -> str:
        return f"__input_plan__::{target_table}::{alias}::{table_name}"

    def _apply_column_aliases(self, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
        """将上传文件的别名列重命名为规则使用的规范列名。

        文件校验规则用 column_aliases 接受不同店铺的列名写法，但校验仅做匹配，
        不改数据。proc 规则引用的是规范列名，因此在加载源表时统一改名，
        否则 groupby/字段访问会因列名不一致抛 KeyError。
        """
        alias_map = self.column_aliases.get(table_name)
        if not alias_map:
            return df
        existing = set(df.columns)
        rename: dict[str, str] = {}
        for col in df.columns:
            canonical = alias_map.get(_normalize_alias_key(col))
            if not canonical or canonical == col or canonical in existing:
                continue
            if canonical in rename.values():
                continue
            rename[col] = canonical
        if rename:
            df = df.rename(columns=rename)
            logger.info(
                "[steps_runtime] 表 '%s' 列名别名规范化: %s", table_name, rename
            )
        return df

    def _ensure_table_loaded(self, table_name: str) -> pd.DataFrame:
        if table_name in self.tables:
            return self.tables[table_name]
        if table_name in self.preloaded_frames:
            df = self.preloaded_frames[table_name].copy()
            df = self._apply_column_aliases(table_name, df)
            self.tables[table_name] = df
            if table_name not in self.schemas:
                self.schemas[table_name] = TableSchemaState(
                    name=table_name,
                    primary_key=[],
                    column_order=list(df.columns),
                    defaults={column: None for column in df.columns},
                    export_enabled=True,
                )
            self._invalidate_row_index_cache(table_name)
            return df
        file_path = self.table_file_map.get(table_name)
        if not file_path:
            raise ProcUserDataError(
                summary=f"规则「{self._rule_display_name()}」找不到所需的数据表",
                cause=f"规则引用的表「{table_name}」既不在上传文件中，也不是前序步骤的结果。",
                suggestion="请确认相关文件已上传，且文件名与规则要求一致。",
            )
        df = _read_file_as_df(file_path)
        df = self._apply_column_aliases(table_name, df)
        self.tables[table_name] = df
        if table_name not in self.schemas:
            self.schemas[table_name] = TableSchemaState(
                name=table_name,
                primary_key=[],
                column_order=list(df.columns),
                defaults={column: None for column in df.columns},
                export_enabled=True,
            )
        self._invalidate_row_index_cache(table_name)
        return df

    def _resolve_month_range(self, definition: dict[str, Any]) -> list[int]:
        start_value = self._evaluate_boundary_definition(definition.get("start") or {})
        end_value = self._evaluate_boundary_definition(definition.get("end") or {})
        start_month = _as_month(start_value)
        end_month = _as_month(end_value)
        months = [start_month]
        for _ in range(23):
            if months[-1] == end_month:
                return months
            months.append(_next_month(months[-1]))
        raise ProcRuleConfigError(
            summary=f"规则「{self._rule_display_name()}」配置有误",
            cause=f"月份范围无效: start={start_month}, end={end_month}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    def _evaluate_boundary_definition(self, definition: dict[str, Any]) -> Any:
        function_name = str(definition.get("function") or "").strip()
        if not function_name:
            return definition
        return self._evaluate_function_node(
            {"type": "function", "function": function_name, "args": definition.get("args") or {}},
            {},
            {},
            "",
            {},
            {},
        )

    def _apply_field_write_mode(
        self,
        field_write_mode: str,
        current_value: Any,
        new_value: Any,
    ) -> Any:
        if field_write_mode not in VALID_FIELD_WRITE_MODES:
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"不支持的 field_write_mode: {field_write_mode}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if field_write_mode == "increment":
            return (_coerce_number(current_value) or 0) + (_coerce_number(new_value) or 0)
        return new_value

    def export_tables(self) -> list[dict[str, Any]]:
        exports: list[dict[str, Any]] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        for table_name in self.materialized_targets:
            df = self.tables.get(table_name)
            if df is None:
                continue
            schema = self.schemas.get(table_name)
            if schema and not schema.export_enabled:
                continue
            output_name = f"{_safe_table_name(table_name)}_{timestamp}.xlsx"
            output_path = self.output_dir / output_name
            export_df = self._build_export_dataframe(table_name, df)
            _write_excel(export_df, output_path)
            exports.append(
                {
                    "rule_id": table_name,
                    "target_table": table_name,
                    "output_file": str(output_path),
                    "row_count": int(len(df)),
                }
            )
        return exports

    def export_frame_outputs(self) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for table_name in self.materialized_targets:
            df = self.tables.get(table_name)
            if df is None:
                continue
            schema = self.schemas.get(table_name)
            if schema and not schema.export_enabled:
                continue
            export_df = _normalize_excel_text_dataframe(self._build_export_dataframe(table_name, df))
            outputs.append(
                {
                    "rule_id": table_name,
                    "target_table": table_name,
                    "row_count": int(len(df)),
                    "dataframe": export_df.copy(),
                }
            )
        return outputs

    def _build_export_dataframe(self, table_name: str, df: pd.DataFrame) -> pd.DataFrame:
        schema = self.schemas.get(table_name)
        export_layout = dict(schema.export_layout or {}) if schema else {}
        if not export_layout:
            return df

        export_columns: list[pd.Series] = []
        export_headers: list[Any] = []

        for column_spec in export_layout.get("fixed_columns") or []:
            source_field, header = self._resolve_export_column(column_spec, {})
            export_columns.append(self._get_export_series(df, source_field))
            export_headers.append(header)

        for group in export_layout.get("dynamic_groups") or []:
            for context in self._resolve_export_month_contexts(group):
                for column_spec in group.get("columns") or []:
                    source_field, header = self._resolve_export_column(column_spec, context)
                    export_columns.append(self._get_export_series(df, source_field))
                    export_headers.append(header)

        if not export_columns:
            return df

        export_df = pd.concat(export_columns, axis=1)
        export_df.columns = export_headers
        return export_df

    def _resolve_export_column(
        self,
        column_spec: Any,
        context: dict[str, Any],
    ) -> tuple[str, Any]:
        if isinstance(column_spec, str):
            return column_spec, column_spec

        if not isinstance(column_spec, dict):
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"导出列配置无效: {column_spec}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )

        source_field = str(column_spec.get("source_field") or "").strip()
        if not source_field:
            source_template = str(column_spec.get("source_template") or "").strip()
            if not source_template:
                raise ProcRuleConfigError(
                    summary=f"规则「{self._rule_display_name()}」配置有误",
                    cause="导出列缺少 source_field/source_template",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            source_field = _render_context_template(source_template, context, coerce_to_string=True)

        if "header" in column_spec:
            header = column_spec.get("header")
        else:
            header_template = column_spec.get("header_template")
            if header_template is None:
                header = source_field
            else:
                header = _render_context_template(str(header_template), context, coerce_to_string=False)

        return source_field, header

    def _get_export_series(self, df: pd.DataFrame, column_name: str) -> pd.Series:
        if column_name in df.columns:
            return df[column_name].reset_index(drop=True)
        return pd.Series([None] * len(df))

    def _resolve_export_month_contexts(self, definition: dict[str, Any]) -> list[dict[str, Any]]:
        dimension = str(definition.get("dimension") or "month").strip()
        if dimension != "month":
            raise ProcRuleConfigError(
                summary=f"规则「{self._rule_display_name()}」配置有误",
                cause=f"不支持的导出动态维度: {dimension}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )

        start_value = self._evaluate_boundary_definition(definition.get("start") or {})
        end_value = self._evaluate_boundary_definition(definition.get("end") or {})
        start_date = _coerce_date_value(start_value)
        end_date = _coerce_date_value(end_value)

        current = _month_end(start_date)
        end_month = _month_end(end_date)
        contexts: list[dict[str, Any]] = []
        for _ in range(24):
            if current > end_month:
                return contexts
            contexts.append(
                {
                    "month": current.month,
                    "prev_month": _previous_month(current.month),
                    "month_end": current.isoformat(),
                    "month_end_date": current,
                }
            )
            next_month = _add_months(current, 1)
            if next_month is None:
                break
            current = _month_end(next_month)
        raise ProcRuleConfigError(
            summary=f"规则「{self._rule_display_name()}」配置有误",
            cause=f"导出月份范围无效: start={start_date}, end={end_date}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )


def _normalize_alias_key(name: Any) -> str:
    """列名别名归一化：去空白、去制表符、转小写，与文件校验保持一致。"""
    return str(name or "").strip().replace(" ", "").replace("\t", "").lower()


def _read_file_as_df(file_path: str) -> pd.DataFrame:
    path = resolve_upload_file_path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            import chardet

            with open(path, "rb") as file:
                encoding = chardet.detect(file.read()).get("encoding", "gbk")
            return pd.read_csv(path, encoding=encoding)
    if suffix in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
        return pd.read_excel(path, dtype=object)
    raise ProcUserDataError(
        summary="数据整理遇到不支持的文件格式",
        cause=f"文件格式「{suffix}」不受支持。",
        suggestion="请上传 Excel 或 CSV 文件。",
    )


def _normalize_excel_text_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(_normalize_excel_text_value)


def _write_excel(df: pd.DataFrame, output_path: Path) -> None:
    export_df = _normalize_excel_text_dataframe(df)
    formula_text_cells = _formula_like_text_cell_positions(export_df)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Sheet1")
        if formula_text_cells:
            worksheet = writer.sheets["Sheet1"]
            for row_index, column_index in formula_text_cells:
                cell = worksheet.cell(row=row_index + 2, column=column_index + 1)
                cell.data_type = "s"


_EXCEL_QUOTED_TEXT_RE = re.compile(r'^=\s*(?:"(?P<quoted>.*)"|\\"(?P<escaped>.*)\\")\s*$')


def _normalize_excel_text_value(value: Any) -> Any:
    """Preserve external-system text identifiers that arrive as Excel formulas."""
    if not isinstance(value, str):
        return value
    match = _EXCEL_QUOTED_TEXT_RE.fullmatch(value.strip())
    if not match:
        return value
    return match.group("quoted") if match.group("quoted") is not None else match.group("escaped")


def _formula_like_text_cell_positions(df: pd.DataFrame) -> set[tuple[int, int]]:
    positions: set[tuple[int, int]] = set()
    for row_index, row in enumerate(df.itertuples(index=False, name=None)):
        for column_index, value in enumerate(row):
            if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
                positions.add((row_index, column_index))
    return positions


def _normalize_key(value: Any) -> Any:
    if _is_nullish(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    return value


def _is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if _is_export_null_marker(value):
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False


def _series_min(series: pd.Series) -> Any:
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return cleaned.min()


def _series_sum(series: pd.Series) -> Any:
    numeric_values: list[float] = []
    for value in series:
        if _is_nullish(value):
            continue
        numeric_value = _to_decimal(value)
        if numeric_value is not None:
            numeric_values.append(numeric_value)
    if not numeric_values:
        return None
    total = sum(numeric_values)
    return int(total) if float(total).is_integer() else total


def _evaluate_aggregate_series(series: pd.Series, operator: str) -> Any:
    if operator == "sum":
        return _series_sum(series)
    if operator == "min":
        return _series_min(series)
    raise ProcRuleConfigError(
        summary="规则配置有误",
        cause=f"不支持的 aggregate operator: {operator}",
        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
    )


def _coerce_number(value: Any) -> Optional[float]:
    if _is_nullish(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            item_value = value.item()
            if isinstance(item_value, (int, float)):
                return float(item_value)
        except Exception:
            pass
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _normalize_formula_value(value: Any) -> Any:
    if _is_export_null_marker(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and _looks_like_date_text(value):
        try:
            return _coerce_date_value(value)
        except ValueError:
            return value
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _coerce_date_value(value: Any) -> date:
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        raise ProcUserDataError(
            summary="数据整理无法解析日期",
            cause=f"值「{value}」不是有效的日期。",
            suggestion="请检查相关列的日期格式是否规范。",
        )
    return ts.date()


def _month_end(value: Any) -> date:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        raise ProcUserDataError(
            summary="数据整理无法解析日期",
            cause=f"值「{value}」不是有效的月份。",
            suggestion="请检查相关列的日期格式是否规范。",
        )
    return (ts + pd.offsets.MonthEnd(0)).date()


def _render_context_template(
    template: str,
    context: dict[str, Any],
    *,
    coerce_to_string: bool,
) -> Any:
    placeholder_only = re.fullmatch(r"\{([^{}]+)\}", template.strip())
    if placeholder_only:
        value = context.get(placeholder_only.group(1))
        return "" if value is None and coerce_to_string else value

    rendered = str(template)
    for name, value in context.items():
        rendered = rendered.replace(f"{{{name}}}", "" if value is None else str(value))
    return rendered


def _safe_table_name(table_name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", table_name)


def _current_date() -> date:
    return date.today()


def _coerce_month_offset(value: Any) -> int:
    if _is_nullish(value):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        match = re.search(r"[-+]?\d+", text)
        if match:
            return int(match.group())
    raise ProcRuleConfigError(
        summary="规则配置有误",
        cause=f"无法解析月份偏移量: {value}",
        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
    )


def _add_months(value: Any, months: Any) -> Optional[date]:
    if _is_nullish(value):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        raise ProcUserDataError(
            summary="数据整理无法解析日期",
            cause=f"值「{value}」不是有效的日期。",
            suggestion="请检查相关列的日期格式是否规范。",
        )
    return (ts + pd.DateOffset(months=_coerce_month_offset(months))).date()


def _extract_fraction_numerator(value: Any) -> int:
    if _is_nullish(value):
        return 0
    text = str(value).strip()
    if not text:
        return 0
    if "/" in text:
        numerator, _, _ = text.partition("/")
        return _coerce_month_offset(numerator)
    return _coerce_month_offset(text)


def _as_month(value: Any) -> int:
    if isinstance(value, int):
        month = value
    elif isinstance(value, pd.Timestamp):
        month = int(value.month)
    elif isinstance(value, datetime):
        month = int(value.month)
    elif isinstance(value, date):
        month = int(value.month)
    else:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            raise ProcUserDataError(
                summary="数据整理无法解析日期",
                cause=f"值「{value}」不是有效的月份。",
                suggestion="请检查相关列的日期格式是否规范。",
            )
        month = int(ts.month)
    if month < 1 or month > 12:
        raise ProcUserDataError(
            summary="数据整理遇到无效月份",
            cause=f"月份值「{month}」超出有效范围。",
            suggestion="请检查相关列的月份数据。",
        )
    return month


def _to_decimal(value: Any) -> Optional[float]:
    if _is_nullish(value):
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            item_value = value.item()
            if isinstance(item_value, (int, float)):
                return float(item_value)
            value = item_value
        except Exception:
            pass
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise ProcUserDataError(
            summary="数据整理无法解析金额",
            cause=f"值「{value}」不是有效的数字。",
            suggestion="请检查相关列是否含有非数字字符。",
        ) from exc


def _normalize_decimal_cell(value: Any) -> Any:
    if _is_nullish(value):
        return None
    try:
        return _to_decimal(value)
    except ValueError:
        return value


def _strip_prefix(value: Any, prefix: Any) -> Optional[str]:
    if _is_nullish(value):
        return None
    text = str(value)
    prefix_text = "" if _is_nullish(prefix) else str(prefix)
    if prefix_text and text.startswith(prefix_text):
        return text[len(prefix_text):]
    return text


def _offset_month(month: int, offset: int) -> int:
    return ((month - 1 + offset) % 12) + 1


def _previous_month(month: int) -> int:
    return 12 if month == 1 else month - 1


def _next_month(month: int) -> int:
    return 1 if month == 12 else month + 1


def _collect_aliases(node: Any) -> set[str]:
    aliases: set[str] = set()
    if isinstance(node, dict):
        node_type = node.get("type")
        if node_type in {"source", "template_source"}:
            source = node.get("source") or {}
            alias = source.get("alias")
            if alias:
                aliases.add(str(alias))
        for value in node.values():
            aliases |= _collect_aliases(value)
    elif isinstance(node, list):
        for item in node:
            aliases |= _collect_aliases(item)
    return aliases


def _collect_step_used_source_aliases(step: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    aliases |= _collect_aliases(step.get("mappings") or [])
    aliases |= _collect_aliases(step.get("filter") or {})
    aliases |= _collect_aliases(step.get("reference_filter") or {})
    for aggregate in step.get("aggregate", []) or []:
        if not isinstance(aggregate, dict):
            continue
        source_alias = str(aggregate.get("source_alias") or "").strip()
        if source_alias:
            aliases.add(source_alias)
    for source_spec in (step.get("match") or {}).get("sources", []) or []:
        if not isinstance(source_spec, dict):
            continue
        alias = str(source_spec.get("alias") or "").strip()
        if alias:
            aliases.add(alias)
    return aliases


_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.IfExp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Subscript,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
)


@lru_cache(maxsize=256)
def _compile_formula_expression(expr: str) -> ast.Expression:
    translated = _translate_formula(expr)
    tree = ast.parse(translated, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ProcRuleConfigError(
                summary="规则配置有误",
                cause=f"公式包含不支持的语法: {type(node).__name__}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in {"coalesce", "is_null"}:
                function_name = node.func.id if isinstance(node.func, ast.Name) else type(node.func).__name__
                raise ProcRuleConfigError(
                    summary="规则配置有误",
                    cause=f"公式包含不支持的函数: {function_name}",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
        if isinstance(node, ast.Name) and node.id not in {"__vars__", "coalesce", "is_null"}:
            raise ProcRuleConfigError(
                summary="规则配置有误",
                cause=f"公式包含不支持的标识符: {node.id}",
                suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
            )
    return tree


def _evaluate_formula_expression(expr: str, env: dict[str, Any]) -> Any:
    tree = _compile_formula_expression(expr)
    return _evaluate_formula_ast(tree.body, env)


def _translate_formula(expr: str) -> str:
    expr = _convert_ternary(expr.strip())
    return re.sub(r"\{([^{}]+)\}", lambda match: f"__vars__[{match.group(1)!r}]", expr)


def _convert_ternary(expr: str) -> str:
    expr = expr.strip()
    if not expr:
        return expr
    if _is_wrapped_by_outer_parentheses(expr):
        return f"({_convert_ternary(expr[1:-1])})"

    rebuilt: list[str] = []
    idx = 0
    while idx < len(expr):
        char = expr[idx]
        if char != "(":
            rebuilt.append(char)
            idx += 1
            continue
        end = _find_matching_parenthesis(expr, idx)
        inner = expr[idx + 1 : end]
        rebuilt.append(f"({_convert_ternary(inner)})")
        idx = end + 1

    return _convert_top_level_ternary("".join(rebuilt))


def _convert_top_level_ternary(expr: str) -> str:
    qmark = _find_top_level_qmark(expr)
    if qmark == -1:
        return expr
    colon = _find_matching_colon(expr, qmark)
    if colon == -1:
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause=f"三元表达式缺少冒号: {expr}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )
    condition = expr[:qmark].strip()
    when_true = expr[qmark + 1 : colon].strip()
    when_false = expr[colon + 1 :].strip()
    return (
        f"({_convert_ternary(when_true)} if {_convert_ternary(condition)} "
        f"else {_convert_ternary(when_false)})"
    )


def _find_top_level_qmark(expr: str) -> int:
    depth = 0
    for idx, char in enumerate(expr):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "?" and depth == 0:
            return idx
    return -1


def _find_matching_colon(expr: str, qmark: int) -> int:
    depth = 0
    nested = 0
    for idx in range(qmark + 1, len(expr)):
        char = expr[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and char == "?":
            nested += 1
        elif depth == 0 and char == ":":
            if nested == 0:
                return idx
            nested -= 1
    return -1


def _find_matching_parenthesis(expr: str, start: int) -> int:
    depth = 0
    for idx in range(start, len(expr)):
        char = expr[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
    raise ProcRuleConfigError(
        summary="规则配置有误",
        cause=f"括号未闭合: {expr}",
        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
    )


def _is_wrapped_by_outer_parentheses(expr: str) -> bool:
    if len(expr) < 2 or expr[0] != "(" or expr[-1] != ")":
        return False
    try:
        return _find_matching_parenthesis(expr, 0) == len(expr) - 1
    except ValueError:
        return False


def _coalesce(*values: Any) -> Any:
    for value in values:
        if not _is_null(value):
            return value
    return None


def _is_null(value: Any) -> bool:
    return _is_nullish(value)


def _evaluate_formula_ast(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id == "__vars__":
            return env
        if node.id == "coalesce":
            return _coalesce
        if node.id == "is_null":
            return _is_null
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause=f"不支持的公式标识符: {node.id}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    if isinstance(node, ast.Subscript):
        container = _evaluate_formula_ast(node.value, env)
        slice_node = node.slice
        if isinstance(slice_node, ast.Index):  # pragma: no cover
            slice_node = slice_node.value
        key = _evaluate_formula_ast(slice_node, env)
        return container.get(key) if isinstance(container, dict) else container[key]

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value_node in node.values:
                if not bool(_evaluate_formula_ast(value_node, env)):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for value_node in node.values:
                if bool(_evaluate_formula_ast(value_node, env)):
                    return True
            return False
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause=f"不支持的逻辑运算: {type(node.op).__name__}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    if isinstance(node, ast.BinOp):
        left = _evaluate_formula_ast(node.left, env)
        right = _evaluate_formula_ast(node.right, env)
        if _is_nullish(left) or _is_nullish(right):
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            left_num, right_num = _require_formula_numeric_operands(left, right, "-")
            return left_num - right_num
        if isinstance(node.op, ast.Mult):
            left_num, right_num = _require_formula_numeric_operands(left, right, "*")
            return left_num * right_num
        if isinstance(node.op, ast.Div):
            left_num, right_num = _require_formula_numeric_operands(left, right, "/")
            return left_num / right_num
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause=f"不支持的算术运算: {type(node.op).__name__}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_formula_ast(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not bool(operand)
        if _is_nullish(operand):
            return None
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause=f"不支持的单目运算: {type(node.op).__name__}",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    if isinstance(node, ast.IfExp):
        condition = _evaluate_formula_ast(node.test, env)
        branch = node.body if bool(condition) else node.orelse
        return _evaluate_formula_ast(branch, env)

    if isinstance(node, ast.Compare):
        left = _evaluate_formula_ast(node.left, env)
        for operator, comparator_node in zip(node.ops, node.comparators):
            right = _evaluate_formula_ast(comparator_node, env)
            left_name = _formula_binding_name_for_node(node.left)
            right_name = _formula_binding_name_for_node(comparator_node)
            if _comparison_involves_blank_string(left, right):
                left_for_compare = _normalize_blank_compare_value(left)
                right_for_compare = _normalize_blank_compare_value(right)
            elif _is_nullish(left) or _is_nullish(right):
                return False
            else:
                left_for_compare = left
                right_for_compare = right
            if isinstance(operator, (ast.Gt, ast.GtE, ast.Lt, ast.LtE)):
                left_for_compare, right_for_compare = _coerce_relational_compare_values(
                    left_for_compare,
                    right_for_compare,
                    left_name=left_name,
                    right_name=right_name,
                )
            if not _apply_compare_operator(operator, left_for_compare, right_for_compare):
                return False
            left = right
        return True

    if isinstance(node, ast.Call):
        func = _evaluate_formula_ast(node.func, env)
        args = [_evaluate_formula_ast(arg, env) for arg in node.args]
        if func is _coalesce:
            return _coalesce(*args)
        if func is _is_null:
            if len(args) != 1:
                raise ProcRuleConfigError(
                    summary="规则配置有误",
                    cause="is_null 需要 1 个参数",
                    suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
                )
            return _is_null(args[0])
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause="公式包含不支持的函数调用",
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )

    raise ProcRuleConfigError(
        summary="规则配置有误",
        cause=f"公式包含不支持的节点: {type(node).__name__}",
        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
    )


def _coerce_formula_numeric_operands(left: Any, right: Any) -> Optional[tuple[float, float]]:
    left_num = _coerce_formula_number(left)
    right_num = _coerce_formula_number(right)
    if left_num is None or right_num is None:
        return None
    return left_num, right_num


def _require_formula_numeric_operands(left: Any, right: Any, operator: str) -> tuple[float, float]:
    operands = _coerce_formula_numeric_operands(left, right)
    if operands is None:
        raise ProcRuleConfigError(
            summary="规则配置有误",
            cause=(
                f"公式算术运算 {operator} 需要数值，实际为 "
                f"{type(left).__name__}({left!r}) 和 {type(right).__name__}({right!r})"
            ),
            suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
        )
    return operands


def _coerce_formula_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or _is_nullish(value):
        return None
    try:
        return _to_decimal(value)
    except ValueError:
        return None


def _formula_binding_name_for_node(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    value_node = node.value
    if not isinstance(value_node, ast.Name) or value_node.id != "__vars__":
        return None
    slice_node = node.slice
    if isinstance(slice_node, ast.Index):  # pragma: no cover
        slice_node = slice_node.value
    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
        return slice_node.value
    return None


def _apply_compare_operator(operator: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    raise ProcRuleConfigError(
        summary="规则配置有误",
        cause=f"不支持的比较运算: {type(operator).__name__}",
        suggestion="这是规则配置问题，请联系管理员核对规则后重试。",
    )


def _comparison_involves_blank_string(left: Any, right: Any) -> bool:
    return _is_blank_string(left) or _is_blank_string(right)


def _is_blank_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() == ""


def _normalize_blank_compare_value(value: Any) -> Any:
    if _is_nullish(value):
        return ""
    if isinstance(value, str):
        return value.strip()
    return value


def _is_export_null_marker(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() in {"\\N", "NULL", "N/A", "NA"}


def _looks_like_date_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(
        re.match(r"^\d{4}[-/.年]\d{1,2}([-/.月]\d{1,2}日?)?(\s+\d{1,2}:\d{2}(:\d{2})?)?$", text)
    )


def _coerce_relational_compare_values(
    left: Any,
    right: Any,
    *,
    left_name: str | None = None,
    right_name: str | None = None,
) -> tuple[Any, Any]:
    if not (_looks_date_like_value(left) or _looks_date_like_value(right)):
        return left, right
    return (
        _coerce_formula_compare_date(left, binding_name=left_name),
        _coerce_formula_compare_date(right, binding_name=right_name),
    )


def _looks_date_like_value(value: Any) -> bool:
    return isinstance(value, (pd.Timestamp, datetime, date)) or _looks_like_date_text(value)


def _coerce_formula_compare_date(value: Any, *, binding_name: str | None) -> date:
    if isinstance(value, str) and not _looks_like_date_text(value):
        raise FormulaEvaluationError(
            f"公式比较失败：需要日期值，但实际是文本 {value!r}",
            binding_names=[binding_name] if binding_name else [],
        )
    try:
        return _coerce_date_value(value)
    except ValueError as exc:
        raise FormulaEvaluationError(
            f"公式比较失败：无法将 {value!r} 解析为日期",
            binding_names=[binding_name] if binding_name else [],
        ) from exc


def _format_binding_source_for_error(source: dict[str, Any]) -> str:
    value = source.get("value")
    parts: list[str] = []
    table = str(source.get("table") or "").strip()
    field = str(source.get("field") or "").strip()
    alias = str(source.get("alias") or "").strip()
    function_name = str(source.get("function") or "").strip()
    if table and field:
        parts.append(f"{table}.{field}")
        lineage = source.get("lineage")
        if isinstance(lineage, dict):
            lineage_table = str(lineage.get("table") or "").strip()
            lineage_field = str(lineage.get("field") or "").strip()
            if lineage_table and lineage_field and (lineage_table != table or lineage_field != field):
                parts.append(f"来源={lineage_table}.{lineage_field}")
    elif alias and field:
        parts.append(f"{alias}.{field}")
    elif function_name:
        parts.append(f"{function_name}()")
    elif source.get("formula"):
        parts.append("嵌套公式")
    parts.append(f"值={value!r}")
    parts.append(f"类型={source.get('type')}")
    return "，".join(parts)
