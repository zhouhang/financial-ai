"""统一规则加载与校验层。"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


VALID_FILTER_OPERATORS = {
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_null",
    "is_not_null",
    "regex_match",
}
VALID_PROC_RULE_TYPES = {
    "direct_mapping",
    "constant",
    "extract",
    "formula",
    "parse_from_field",
    "regex_extract",
    "conditional_value",
    "conditional_extract",
    "conditional_formula",
    "lookup",
}
VALID_AGG_FUNCTIONS = {"sum", "count", "mean", "min", "max", "first", "last"}
VALID_PROC_STEP_ACTIONS = {"create_schema", "write_dataset"}
VALID_PROC_STEP_ROW_WRITE_MODES = {"upsert", "insert_if_missing", "update_only"}
VALID_PROC_STEP_FIELD_WRITE_MODES = {"overwrite", "increment"}
VALID_PROC_STEP_VALUE_TYPES = {"source", "formula", "template_source", "function", "context", "lookup"}
PROC_STEP_CONTEXT_NAMES = {"month", "prev_month", "is_first_month"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ValidationConfig(StrictModel):
    ignore_whitespace: bool = True
    case_sensitive: bool = False


class TableSchema(StrictModel):
    table_id: str
    table_name: str
    file_type: list[str] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)
    column_aliases: dict[str, list[str]] = Field(default_factory=dict)


class FileValidationRuleModel(StrictModel):
    validation_config: ValidationConfig = Field(default_factory=ValidationConfig)
    table_schemas: list[TableSchema]


class ProcFieldMappingModel(StrictModel):
    target_field: str
    rule_type: str
    source_field: str | None = None
    value: Any = None
    formula: str | None = None
    pattern: str | None = None
    lookup_table: str | None = None
    lookup_key: str | None = None
    lookup_value: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ProcFieldMappingModel":
        if self.rule_type not in VALID_PROC_RULE_TYPES:
            raise ValueError(f"不支持的 rule_type: {self.rule_type}")
        if self.rule_type == "direct_mapping" and not self.source_field:
            raise ValueError("direct_mapping 缺少 source_field")
        if self.rule_type == "constant" and self.value is None:
            raise ValueError("constant 缺少 value")
        if self.rule_type in {"formula", "conditional_formula"} and not self.formula:
            raise ValueError(f"{self.rule_type} 缺少 formula")
        if self.rule_type == "regex_extract" and (not self.source_field or not self.pattern):
            raise ValueError("regex_extract 缺少 source_field 或 pattern")
        if self.rule_type == "lookup" and (
            not self.lookup_table or not self.lookup_key or not self.lookup_value
        ):
            raise ValueError("lookup 缺少 lookup_table / lookup_key / lookup_value")
        return self


class ProcLookupTableModel(StrictModel):
    table_name: str


class ProcGlobalFilterModel(StrictModel):
    source_column: str
    operator: Literal["in", "starts_with"]
    values: list[Any] = Field(default_factory=list)
    exclude_values: list[Any] = Field(default_factory=list)


class ProcRuleModel(StrictModel):
    rule_id: str
    target_table: str
    source_tables: list[str] | None = None
    source_table: str | None = None
    field_mappings: list[ProcFieldMappingModel] = Field(default_factory=list)
    global_filter: ProcGlobalFilterModel | None = None
    lookup_tables: list[ProcLookupTableModel] = Field(default_factory=list)
    merge: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_proc_rule(self) -> "ProcRuleModel":
        source_tables = self.source_tables or ([] if not self.source_table else [self.source_table])
        if not source_tables:
            raise ValueError("proc 规则缺少 source_table/source_tables")
        if not self.field_mappings:
            raise ValueError("proc 规则缺少 field_mappings")
        return self


class ProcRuleSetModel(StrictModel):
    rules: list[ProcRuleModel]


class ProcStepsRuleSetModel(StrictModel):
    role_desc: str | None = None
    file_rule_code: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)


class MergeRuleModel(StrictModel):
    rule_id: str
    table_name: str
    merge_type: Literal["append_rows", "aggregate_by_key"] = "append_rows"
    enabled: bool = True
    merge_config: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class ProcMergeRuleSetModel(StrictModel):
    merge_rules: list[MergeRuleModel]


class FilterConditionModel(StrictModel):
    column: str
    operator: str
    value: Any = None
    values: list[Any] | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> "FilterConditionModel":
        if self.operator not in VALID_FILTER_OPERATORS:
            raise ValueError(f"不支持的过滤操作符: {self.operator}")
        if self.operator not in {"is_null", "is_not_null"} and self.value is None and self.values is None:
            raise ValueError("过滤条件缺少 value 或 values")
        return self


class FilterConfigModel(StrictModel):
    enabled: bool = False
    conditions: list[FilterConditionModel] = Field(default_factory=list)
    logic: Literal["and", "or"] = "and"


class ColumnMappingModel(StrictModel):
    mappings: dict[str, str] = Field(default_factory=dict)


class FileIdentificationModel(StrictModel):
    match_by: Literal["table_name"] = "table_name"
    match_value: str
    match_strategy: Literal["exact", "contains", "startswith"] = "exact"


class ReconFileConfigModel(StrictModel):
    identification: FileIdentificationModel
    filter: FilterConfigModel | None = None
    column_mapping: ColumnMappingModel | None = None


class CompareColumnModel(StrictModel):
    name: str | None = None
    column: str | None = None
    source_column: str | None = None
    target_column: str | None = None
    tolerance: float | int = 0


class AggregationGroupByModel(StrictModel):
    source_field: str
    target_field: str


class AggregationItemModel(StrictModel):
    alias: str | None = None
    source_field: str | None = None
    target_field: str | None = None
    column: str | None = None
    source_column: str | None = None
    target_column: str | None = None
    function: Literal["sum", "count", "mean", "min", "max", "first", "last"] = "sum"


class AggregationConfigModel(StrictModel):
    enabled: bool = False
    group_by: list[AggregationGroupByModel] = Field(default_factory=list)
    aggregations: list[AggregationItemModel] = Field(default_factory=list)


class KeyFieldMappingModel(StrictModel):
    source_field: str
    target_field: str


class KeyColumnsConfigModel(StrictModel):
    source_field: str | None = None
    target_field: str | None = None
    mappings: list[KeyFieldMappingModel] = Field(default_factory=list)
    transformations: dict[str, dict[str, list[dict[str, Any]]]] = Field(default_factory=dict)


class CompareColumnsConfigModel(StrictModel):
    columns: list[CompareColumnModel] = Field(default_factory=list)


class ReconConfigModel(StrictModel):
    key_columns: KeyColumnsConfigModel
    compare_columns: CompareColumnsConfigModel = Field(default_factory=CompareColumnsConfigModel)
    aggregation: AggregationConfigModel = Field(default_factory=AggregationConfigModel)


class ReconRuleModel(StrictModel):
    enabled: bool = True
    source_file: ReconFileConfigModel
    target_file: ReconFileConfigModel
    recon: ReconConfigModel
    output: dict[str, Any] = Field(default_factory=dict)


class ReconRuleSetModel(StrictModel):
    rule_id: str
    rule_name: str
    description: str | None = None
    file_rule_code: str | None = None
    schema_version: str | None = None
    rules: list[ReconRuleModel]


def _format_validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    result = []
    for error in exc.errors():
        loc = ".".join(str(item) for item in error.get("loc", []))
        result.append(
            {
                "path": loc or "$",
                "message": error.get("msg", "规则校验失败"),
                "type": error.get("type", "validation_error"),
            }
        )
    return result


def _normalize_rule_payload(raw_rule: Any) -> dict[str, Any]:
    if isinstance(raw_rule, str):
        raw_rule = json.loads(raw_rule)
    if not isinstance(raw_rule, dict):
        raise ValueError("规则内容必须是 JSON 对象")
    return raw_rule


def _normalize_proc_step_value_spec(spec: Any) -> Any:
    if not isinstance(spec, dict):
        return spec

    normalized = copy.deepcopy(spec)
    spec_type = str(normalized.get("type") or "").strip()

    if spec_type == "formula":
        expr = normalized.get("expr")
        if not isinstance(expr, str) or not expr.strip():
            formula = normalized.get("formula")
            if isinstance(formula, str) and formula.strip():
                normalized["expr"] = formula.strip()
        normalized.pop("formula", None)

    if spec_type == "context":
        name = normalized.get("name")
        context_name = normalized.get("context")
        if (not isinstance(name, str) or not name.strip()) and isinstance(context_name, str):
            stripped = context_name.strip()
            if stripped in PROC_STEP_CONTEXT_NAMES:
                normalized["name"] = stripped
            elif stripped:
                return {
                    "type": "formula",
                    "expr": json.dumps(stripped, ensure_ascii=False),
                }
        normalized.pop("context", None)

    bindings = normalized.get("bindings")
    if isinstance(bindings, dict):
        normalized["bindings"] = {
            key: _normalize_proc_step_value_spec(value)
            for key, value in bindings.items()
        }

    variables = normalized.get("variables")
    if isinstance(variables, dict):
        normalized["variables"] = {
            key: _normalize_proc_step_value_spec(value)
            for key, value in variables.items()
        }

    args = normalized.get("args")
    if isinstance(args, dict):
        normalized["args"] = {
            key: _normalize_proc_step_value_spec(value)
            for key, value in args.items()
        }

    keys = normalized.get("keys")
    if isinstance(keys, list):
        rebuilt_keys: list[Any] = []
        for item in keys:
            if not isinstance(item, dict):
                rebuilt_keys.append(item)
                continue
            rebuilt = copy.deepcopy(item)
            if "input" in rebuilt:
                rebuilt["input"] = _normalize_proc_step_value_spec(rebuilt.get("input"))
            rebuilt_keys.append(rebuilt)
        normalized["keys"] = rebuilt_keys

    return normalized


def _normalize_proc_steps_payload(rule_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(rule_payload)
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return normalized

    for step in steps:
        if not isinstance(step, dict):
            continue

        filter_def = step.get("filter")
        if isinstance(filter_def, dict):
            if not isinstance(filter_def.get("expr"), str) or not str(filter_def.get("expr") or "").strip():
                formula = filter_def.get("formula")
                if isinstance(formula, str) and formula.strip():
                    filter_def["expr"] = formula.strip()
            filter_def.pop("formula", None)
            bindings = filter_def.get("bindings")
            if isinstance(bindings, dict):
                filter_def["bindings"] = {
                    key: _normalize_proc_step_value_spec(value)
                    for key, value in bindings.items()
                }

        mappings = step.get("mappings")
        if isinstance(mappings, list):
            normalized_mappings: list[Any] = []
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    normalized_mappings.append(mapping)
                    continue
                rebuilt = copy.deepcopy(mapping)
                if "value" in rebuilt:
                    rebuilt["value"] = _normalize_proc_step_value_spec(rebuilt.get("value"))
                bindings = rebuilt.get("bindings")
                if isinstance(bindings, dict):
                    rebuilt["bindings"] = {
                        key: _normalize_proc_step_value_spec(value)
                        for key, value in bindings.items()
                    }
                normalized_mappings.append(rebuilt)
            step["mappings"] = normalized_mappings

        dynamic_mappings = step.get("dynamic_mappings")
        if isinstance(dynamic_mappings, dict) and isinstance(dynamic_mappings.get("mappings"), list):
            rebuilt_dynamic_mappings: list[Any] = []
            for mapping in dynamic_mappings.get("mappings") or []:
                if not isinstance(mapping, dict):
                    rebuilt_dynamic_mappings.append(mapping)
                    continue
                rebuilt = copy.deepcopy(mapping)
                if "value" in rebuilt:
                    rebuilt["value"] = _normalize_proc_step_value_spec(rebuilt.get("value"))
                bindings = rebuilt.get("bindings")
                if isinstance(bindings, dict):
                    rebuilt["bindings"] = {
                        key: _normalize_proc_step_value_spec(value)
                        for key, value in bindings.items()
                    }
                rebuilt_dynamic_mappings.append(rebuilt)
            dynamic_mappings["mappings"] = rebuilt_dynamic_mappings

    return normalized


def _validation_failure(rule_code: str, rule_type: str, validation_errors: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "success": False,
        "error": "规则校验失败",
        "error_code": "RULE_SCHEMA_INVALID",
        "rule_code": rule_code,
        "rule_type": rule_type,
        "validation_errors": validation_errors,
    }


def _semantic_errors_for_file_validation(rule: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    table_ids = [item["table_id"] for item in rule.get("table_schemas", [])]
    if len(table_ids) != len(set(table_ids)):
        errors.append({"path": "table_schemas", "message": "table_id 必须唯一", "type": "duplicate"})
    for idx, item in enumerate(rule.get("table_schemas", [])):
        if not item.get("required_columns"):
            errors.append(
                {"path": f"table_schemas.{idx}.required_columns", "message": "required_columns 不能为空", "type": "missing"}
            )
    return errors


def _semantic_errors_for_proc(rule: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    for rule_idx, item in enumerate(rule.get("rules", [])):
        targets = [mapping.get("target_field") for mapping in item.get("field_mappings", []) if mapping.get("target_field")]
        if len(targets) != len(set(targets)):
            errors.append(
                {"path": f"rules.{rule_idx}.field_mappings", "message": "target_field 必须唯一", "type": "duplicate"}
            )
        target_set = set(targets)
        lookup_tables = {lookup.get("table_name") for lookup in item.get("lookup_tables", [])}
        for mapping_idx, mapping in enumerate(item.get("field_mappings", [])):
            for dep in mapping.get("depends_on", []) or []:
                if dep not in target_set:
                    errors.append(
                        {
                            "path": f"rules.{rule_idx}.field_mappings.{mapping_idx}.depends_on",
                            "message": f"depends_on 引用了未定义字段: {dep}",
                            "type": "reference",
                        }
                    )
            if mapping.get("rule_type") == "lookup" and mapping.get("lookup_table") not in lookup_tables:
                errors.append(
                    {
                        "path": f"rules.{rule_idx}.field_mappings.{mapping_idx}.lookup_table",
                        "message": "lookup_table 未在 lookup_tables 中声明",
                        "type": "reference",
                    }
                )
            pattern = mapping.get("pattern")
            if pattern and len(pattern) > 256:
                errors.append(
                    {
                        "path": f"rules.{rule_idx}.field_mappings.{mapping_idx}.pattern",
                        "message": "正则表达式过长",
                        "type": "constraint",
                    }
                )
    return errors


def _semantic_errors_for_proc_steps(rule: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    steps = rule.get("steps", [])
    if not steps:
        return [{"path": "steps", "message": "steps 不能为空", "type": "missing"}]

    step_ids = [item.get("step_id") for item in steps if item.get("step_id")]
    if len(step_ids) != len(set(step_ids)):
        errors.append({"path": "steps", "message": "step_id 必须唯一", "type": "duplicate"})

    for idx, step in enumerate(steps):
        if not step.get("action"):
            errors.append(
                {"path": f"steps.{idx}.action", "message": "缺少 action", "type": "missing"}
            )
        elif step.get("action") not in VALID_PROC_STEP_ACTIONS:
            errors.append(
                {
                    "path": f"steps.{idx}.action",
                    "message": f"不支持的 action: {step.get('action')}",
                    "type": "invalid",
                }
            )
        if not step.get("target_table"):
            errors.append(
                {
                    "path": f"steps.{idx}.target_table",
                    "message": "缺少 target_table",
                    "type": "missing",
                }
            )
        row_write_mode = step.get("row_write_mode")
        if row_write_mode and row_write_mode not in VALID_PROC_STEP_ROW_WRITE_MODES:
            errors.append(
                {
                    "path": f"steps.{idx}.row_write_mode",
                    "message": f"不支持的 row_write_mode: {row_write_mode}",
                    "type": "invalid",
                }
            )

        reference_filter = step.get("reference_filter") or {}
        if reference_filter:
            if not reference_filter.get("source_alias"):
                errors.append(
                    {
                        "path": f"steps.{idx}.reference_filter.source_alias",
                        "message": "reference_filter 缺少 source_alias",
                        "type": "missing",
                    }
                )
            if not reference_filter.get("reference_table"):
                errors.append(
                    {
                        "path": f"steps.{idx}.reference_filter.reference_table",
                        "message": "reference_filter 缺少 reference_table",
                        "type": "missing",
                    }
                )
            keys = reference_filter.get("keys") or []
            if not keys:
                errors.append(
                    {
                        "path": f"steps.{idx}.reference_filter.keys",
                        "message": "reference_filter.keys 不能为空",
                        "type": "missing",
                    }
                )
            for key_idx, key in enumerate(keys):
                if not key.get("source_field") or not key.get("reference_field"):
                    errors.append(
                        {
                            "path": f"steps.{idx}.reference_filter.keys.{key_idx}",
                            "message": "reference_filter.keys 每项都需要 source_field/reference_field",
                            "type": "missing",
                        }
                    )

        for agg_idx, aggregate in enumerate(step.get("aggregate", []) or []):
            if not aggregate.get("source_alias"):
                errors.append(
                    {
                        "path": f"steps.{idx}.aggregate.{agg_idx}.source_alias",
                        "message": "aggregate 缺少 source_alias",
                        "type": "missing",
                    }
                )
            if not aggregate.get("output_alias"):
                errors.append(
                    {
                        "path": f"steps.{idx}.aggregate.{agg_idx}.output_alias",
                        "message": "aggregate 缺少 output_alias",
                        "type": "missing",
                    }
                )

        dynamic_mappings = step.get("dynamic_mappings") or {}
        if dynamic_mappings and not ((step.get("match") or {}).get("sources") or []):
            errors.append(
                {
                    "path": f"steps.{idx}.dynamic_mappings",
                    "message": "dynamic_mappings 需要同时配置 match.sources",
                    "type": "missing",
                }
            )

        for mapping_idx, mapping in enumerate(step.get("mappings", []) or []):
            if not mapping.get("target_field") and not mapping.get("target_field_template"):
                errors.append(
                    {
                        "path": f"steps.{idx}.mappings.{mapping_idx}",
                        "message": "mapping 需要配置 target_field 或 target_field_template",
                        "type": "missing",
                    }
                )
            value = mapping.get("value") or {}
            if value:
                value_type = value.get("type")
                if value_type not in VALID_PROC_STEP_VALUE_TYPES:
                    errors.append(
                        {
                            "path": f"steps.{idx}.mappings.{mapping_idx}.value.type",
                            "message": f"不支持的 value.type: {value_type}",
                            "type": "invalid",
                        }
                    )
                if value_type == "formula" and not str(value.get("expr") or "").strip():
                    errors.append(
                        {
                            "path": f"steps.{idx}.mappings.{mapping_idx}.value.expr",
                            "message": "formula 缺少 expr",
                            "type": "missing",
                        }
                    )
                if value_type == "context" and not str(value.get("name") or "").strip():
                    errors.append(
                        {
                            "path": f"steps.{idx}.mappings.{mapping_idx}.value.name",
                            "message": "context 缺少 name",
                            "type": "missing",
                        }
                    )
                if value_type == "lookup":
                    if not value.get("source_alias"):
                        errors.append(
                            {
                                "path": f"steps.{idx}.mappings.{mapping_idx}.value.source_alias",
                                "message": "lookup 缺少 source_alias",
                                "type": "missing",
                            }
                        )
                    if not value.get("value_field"):
                        errors.append(
                            {
                                "path": f"steps.{idx}.mappings.{mapping_idx}.value.value_field",
                                "message": "lookup 缺少 value_field",
                                "type": "missing",
                            }
                        )
                    keys = value.get("keys") or []
                    if not keys:
                        errors.append(
                            {
                                "path": f"steps.{idx}.mappings.{mapping_idx}.value.keys",
                                "message": "lookup.keys 不能为空",
                                "type": "missing",
                            }
                        )
                    for key_idx, key in enumerate(keys):
                        if not key.get("lookup_field") or not key.get("input"):
                            errors.append(
                                {
                                    "path": f"steps.{idx}.mappings.{mapping_idx}.value.keys.{key_idx}",
                                    "message": "lookup.keys 每项都需要 lookup_field 和 input",
                                    "type": "missing",
                                }
                            )
            field_write_mode = mapping.get("field_write_mode")
            if field_write_mode and field_write_mode not in VALID_PROC_STEP_FIELD_WRITE_MODES:
                errors.append(
                    {
                        "path": f"steps.{idx}.mappings.{mapping_idx}.field_write_mode",
                        "message": f"不支持的 field_write_mode: {field_write_mode}",
                        "type": "invalid",
                    }
                )
    return errors


def _semantic_errors_for_merge(rule: dict[str, Any]) -> list[dict[str, str]]:
    table_names = [item.get("table_name") for item in rule.get("merge_rules", []) if item.get("enabled", True)]
    if len(table_names) != len(set(table_names)):
        return [{"path": "merge_rules", "message": "启用的 table_name 必须唯一", "type": "duplicate"}]
    return []


def _semantic_errors_for_recon(rule: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    if not rule.get("rule_id"):
        errors.append({"path": "rule_id", "message": "缺少顶层 rule_id", "type": "missing"})
    if not rule.get("rule_name"):
        errors.append({"path": "rule_name", "message": "缺少顶层 rule_name", "type": "missing"})
    for idx, item in enumerate(rule.get("rules", [])):
        recon_config = item.get("recon") or item.get("reconciliation_config", {})
        key_config = recon_config.get("key_columns", {})
        mappings = key_config.get("mappings") or []
        if not mappings:
            source_field = key_config.get("source_field")
            target_field = key_config.get("target_field")
            if source_field and target_field:
                mappings = [{"source_field": source_field, "target_field": target_field}]
        if not mappings:
            errors.append(
                {
                    "path": f"rules.{idx}.recon.key_columns",
                    "message": "需要配置 key_columns.mappings，或同时配置 source_field 和 target_field",
                    "type": "missing",
                }
            )
        else:
            pair_set: set[tuple[str, str]] = set()
            for mapping_idx, mapping in enumerate(mappings):
                source_field = mapping.get("source_field")
                target_field = mapping.get("target_field")
                if not source_field or not target_field:
                    errors.append(
                        {
                            "path": f"rules.{idx}.recon.key_columns.mappings.{mapping_idx}",
                            "message": "每个 key mapping 都需要 source_field 和 target_field",
                            "type": "missing",
                        }
                    )
                    continue
                pair = (source_field, target_field)
                if pair in pair_set:
                    errors.append(
                        {
                            "path": f"rules.{idx}.recon.key_columns.mappings.{mapping_idx}",
                            "message": "key mapping 不能重复",
                            "type": "duplicate",
                        }
                    )
                pair_set.add(pair)
        for compare_idx, compare_item in enumerate(recon_config.get("compare_columns", {}).get("columns", [])):
            if not compare_item.get("name"):
                errors.append(
                    {
                        "path": f"rules.{idx}.recon.compare_columns.columns.{compare_idx}",
                        "message": "compare_columns 缺少 name",
                        "type": "missing",
                    }
                )
            if not compare_item.get("source_column") or not compare_item.get("target_column"):
                errors.append(
                    {
                        "path": f"rules.{idx}.recon.compare_columns.columns.{compare_idx}",
                        "message": "compare_columns 需要同时配置 source_column 和 target_column",
                        "type": "missing",
                    }
                )
        group_by = recon_config.get("aggregation", {}).get("group_by", [])
        if isinstance(group_by, dict):
            group_by = [group_by]
        for group_idx, group_item in enumerate(group_by):
            if not group_item.get("source_field") or not group_item.get("target_field"):
                errors.append(
                    {
                        "path": f"rules.{idx}.recon.aggregation.group_by.{group_idx}",
                        "message": "group_by 每项都需要 source_field 和 target_field",
                        "type": "missing",
                    }
                )
        aggregations = recon_config.get("aggregation", {}).get("aggregations", [])
        if isinstance(aggregations, dict):
            aggregations = [aggregations]
        for agg_idx, aggregation in enumerate(aggregations):
            if aggregation.get("function") not in VALID_AGG_FUNCTIONS:
                errors.append(
                    {
                        "path": f"rules.{idx}.recon.aggregation.aggregations.{agg_idx}.function",
                        "message": "聚合函数不在白名单内",
                        "type": "constraint",
                    }
                )
            if not aggregation.get("source_field") or not aggregation.get("target_field"):
                errors.append(
                    {
                        "path": f"rules.{idx}.recon.aggregation.aggregations.{agg_idx}",
                        "message": "aggregations 每项都需要 source_field 和 target_field",
                        "type": "missing",
                    }
                )
        transformations = recon_config.get("key_columns", {}).get("transformations", {})
        for file_side in ("source", "target"):
            side_config = transformations.get(file_side, {})
            if not isinstance(side_config, dict):
                errors.append(
                    {
                        "path": f"rules.{idx}.recon.key_columns.transformations.{file_side}",
                        "message": "transformations 的 source/target 必须是对象，键为字段名，值为操作数组",
                        "type": "type",
                    }
                )
                continue
            for field_name, operations in side_config.items():
                if not isinstance(operations, list):
                    errors.append(
                        {
                            "path": f"rules.{idx}.recon.key_columns.transformations.{file_side}.{field_name}",
                            "message": "字段转换配置必须是数组",
                            "type": "type",
                        }
                    )
                    continue
                for op_idx, op in enumerate(operations):
                    if not isinstance(op, dict):
                        errors.append(
                            {
                                "path": f"rules.{idx}.recon.key_columns.transformations.{file_side}.{field_name}.{op_idx}",
                                "message": "转换操作必须是对象",
                                "type": "type",
                            }
                        )
                        continue
                    op_type = op.get("type")
                    path_prefix = f"rules.{idx}.recon.key_columns.transformations.{file_side}.{field_name}.{op_idx}"
                    if op_type not in {"regex_extract", "regex_replace", "strip_prefix", "strip_suffix", "strip_whitespace", "lowercase"}:
                        errors.append(
                            {
                                "path": f"{path_prefix}.type",
                                "message": "不支持的转换类型",
                                "type": "constraint",
                            }
                        )
                    pattern = op.get("pattern") if op_type in {"regex_extract", "regex_replace"} else None
                    if op_type == "regex_extract":
                        pattern = op.get("pattern") or op.get("regex_extract")
                    if pattern:
                        if len(pattern) > 256:
                            errors.append(
                                {
                                    "path": f"{path_prefix}.pattern",
                                    "message": "正则表达式过长",
                                    "type": "constraint",
                                }
                            )
                        else:
                            try:
                                re.compile(pattern)
                            except re.error as exc:
                                errors.append(
                                    {
                                        "path": f"{path_prefix}.pattern",
                                        "message": f"正则表达式无效: {exc}",
                                        "type": "regex",
                                    }
                                )
    return errors


def validate_rule_record(rule_record: dict[str, Any], expected_kind: str) -> dict[str, Any]:
    rule_code = str(rule_record.get("rule_code") or "")
    try:
        rule_payload = _normalize_rule_payload(rule_record.get("rule") or {})
    except (ValueError, json.JSONDecodeError) as exc:
        return _validation_failure(
            rule_code,
            expected_kind,
            [{"path": "$", "message": f"规则 JSON 无效: {exc}", "type": "json"}],
        )

    if expected_kind == "file_validation":
        normalized_payload = rule_payload.get("file_validation_rules", rule_payload)
        model = FileValidationRuleModel
        semantic_check = _semantic_errors_for_file_validation
    elif expected_kind == "proc":
        normalized_payload = rule_payload
        model = ProcRuleSetModel
        semantic_check = _semantic_errors_for_proc
    elif expected_kind == "proc_steps":
        normalized_payload = _normalize_proc_steps_payload(rule_payload)
        model = ProcStepsRuleSetModel
        semantic_check = _semantic_errors_for_proc_steps
    elif expected_kind == "merge":
        normalized_payload = rule_payload
        model = ProcMergeRuleSetModel
        semantic_check = _semantic_errors_for_merge
    elif expected_kind == "proc_entry":
        normalized_payload = copy.deepcopy(rule_payload)
        if normalized_payload.get("steps"):
            normalized_payload = _normalize_proc_steps_payload(normalized_payload)
            model = ProcStepsRuleSetModel
            semantic_check = _semantic_errors_for_proc_steps
            expected_kind = "proc_steps"
        elif normalized_payload.get("rules"):
            model = ProcRuleSetModel
            semantic_check = _semantic_errors_for_proc
            expected_kind = "proc"
        elif normalized_payload.get("merge_rules"):
            model = ProcMergeRuleSetModel
            semantic_check = _semantic_errors_for_merge
            expected_kind = "merge"
        else:
            return _validation_failure(
                rule_code,
                expected_kind,
                [
                    {
                        "path": "$",
                        "message": "规则中未定义 steps、rules 或 merge_rules",
                        "type": "missing",
                    }
                ],
            )
    elif expected_kind == "recon":
        normalized_payload = rule_payload
        rules = normalized_payload.get("rules", [])
        first_rule = rules[0] if rules else {}
        normalized_payload["rule_id"] = normalized_payload.get("rule_id") or first_rule.get("rule_id")
        normalized_payload["rule_name"] = normalized_payload.get("rule_name") or first_rule.get("rule_name")
        normalized_payload["description"] = normalized_payload.get("description") or first_rule.get("description")
        for item in normalized_payload.get("rules", []):
            if "recon" not in item and "reconciliation_config" in item:
                item["recon"] = item.pop("reconciliation_config")
            item.pop("rule_id", None)
            item.pop("rule_name", None)
            item.pop("description", None)
            item.pop("diff_analysis", None)
            recon = item.get("recon") or {}
            compare_columns = (recon.get("compare_columns") or {}).get("columns") or []
            for compare_item in compare_columns:
                if "name" not in compare_item and "column" in compare_item:
                    compare_item["name"] = compare_item.get("column")
            key_config = recon.get("key_columns") or {}
            cross_mapping = key_config.pop("cross_file_mapping", None) or {}
            columns = key_config.pop("columns", None) or []
            mappings = key_config.get("mappings") or []
            if not mappings:
                source_field = key_config.get("source_field") or cross_mapping.get("source_column") or (columns[0] if columns else None)
                target_field = key_config.get("target_field") or cross_mapping.get("target_column") or (columns[-1] if columns else None)
                if source_field and target_field:
                    mappings = [{"source_field": source_field, "target_field": target_field}]
            key_config["mappings"] = mappings
            if mappings:
                key_config["source_field"] = key_config.get("source_field") or mappings[0].get("source_field")
                key_config["target_field"] = key_config.get("target_field") or mappings[0].get("target_field")
            key_config.pop("cross_file_mappings", None)
            recon["key_columns"] = key_config

            aggregation = recon.get("aggregation") or {}
            group_by = aggregation.get("group_by")
            if isinstance(group_by, dict):
                aggregation["group_by"] = [group_by]
            elif isinstance(group_by, list) and group_by and isinstance(group_by[0], str):
                aggregation["group_by"] = [
                    {
                        "source_field": group_by[0] if len(group_by) > 0 else None,
                        "target_field": group_by[-1] if len(group_by) > 1 else (group_by[0] if group_by else None),
                    }
                ]
            if "aggregations" not in aggregation and "aggre_fields" in aggregation:
                aggregation["aggregations"] = aggregation.pop("aggre_fields")
            aggregations = aggregation.get("aggregations")
            if isinstance(aggregations, dict):
                aggregation["aggregations"] = [aggregations]
            recon["aggregation"] = aggregation
        model = ReconRuleSetModel
        semantic_check = _semantic_errors_for_recon
    else:
        return _validation_failure(
            rule_code,
            expected_kind,
            [{"path": "$", "message": f"未知的规则类型: {expected_kind}", "type": "type"}],
        )

    try:
        validated = model.model_validate(normalized_payload)
    except ValidationError as exc:
        return _validation_failure(rule_code, expected_kind, _format_validation_errors(exc))

    normalized_rule = validated.model_dump(exclude_none=True)
    semantic_errors = semantic_check(normalized_rule)
    if semantic_errors:
        return _validation_failure(rule_code, expected_kind, semantic_errors)

    return {
        "success": True,
        "rule_code": rule_code,
        "rule_type": expected_kind,
        "record": rule_record,
        "rule": normalized_rule,
        "raw_rule": rule_payload,
    }


def load_and_validate_rule(rule_code: str, expected_kind: str, user_id: str | None = None) -> dict[str, Any]:
    from tools.rules import get_rule

    rule_record = get_rule(rule_code, user_id=user_id)
    if rule_record is None:
        return {
            "success": False,
            "error": f"未找到 rule_code='{rule_code}' 的规则",
            "error_code": "RULE_NOT_FOUND",
            "rule_code": rule_code,
            "rule_type": expected_kind,
        }
    return validate_rule_record(rule_record, expected_kind)
