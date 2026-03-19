"""统一规则加载与校验层。"""
from __future__ import annotations

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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class FileCountConfig(StrictModel):
    min: int = 1
    max: int = 0
    allow_multiple: bool = True


class ValidationConfig(StrictModel):
    ignore_whitespace: bool = True
    case_sensitive: bool = False
    allow_multi_rule_match: bool = True
    file_count: FileCountConfig = Field(default_factory=FileCountConfig)


class TableSchema(StrictModel):
    table_id: str
    table_name: str
    all_columns: list[str] = Field(default_factory=list)
    column_aliases: dict[str, list[str]] = Field(default_factory=dict)
    is_ness: bool = False
    max_file_match_count: int = 0
    enabled: bool = True


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


class CrossFileMappingModel(StrictModel):
    source_column: str
    target_column: str


class CompareColumnModel(StrictModel):
    column: str
    source_column: str | None = None
    target_column: str | None = None
    tolerance: float | int = 0
    tolerance_type: Literal["absolute", "relative"] = "absolute"


class AggregationItemModel(StrictModel):
    column: str
    function: Literal["sum", "count", "mean", "min", "max", "first", "last"] = "sum"


class AggregationConfigModel(StrictModel):
    enabled: bool = False
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[AggregationItemModel] = Field(default_factory=list)


class KeyColumnsConfigModel(StrictModel):
    columns: list[str] = Field(default_factory=list)
    cross_file_mapping: CrossFileMappingModel | None = None
    cross_file_mappings: list[CrossFileMappingModel] = Field(default_factory=list)
    transformations: dict[str, Any] = Field(default_factory=dict)


class CompareColumnsConfigModel(StrictModel):
    columns: list[CompareColumnModel] = Field(default_factory=list)


class ReconciliationConfigModel(StrictModel):
    key_columns: KeyColumnsConfigModel
    compare_columns: CompareColumnsConfigModel = Field(default_factory=CompareColumnsConfigModel)
    aggregation: AggregationConfigModel = Field(default_factory=AggregationConfigModel)


class ReconRuleModel(StrictModel):
    rule_id: str
    rule_name: str
    enabled: bool = True
    source_file: ReconFileConfigModel
    target_file: ReconFileConfigModel
    reconciliation_config: ReconciliationConfigModel
    output: dict[str, Any] = Field(default_factory=dict)
    diff_analysis: dict[str, Any] = Field(default_factory=dict)


class ReconRuleSetModel(StrictModel):
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
        if not item.get("all_columns"):
            errors.append(
                {"path": f"table_schemas.{idx}.all_columns", "message": "all_columns 不能为空", "type": "missing"}
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


def _semantic_errors_for_merge(rule: dict[str, Any]) -> list[dict[str, str]]:
    table_names = [item.get("table_name") for item in rule.get("merge_rules", []) if item.get("enabled", True)]
    if len(table_names) != len(set(table_names)):
        return [{"path": "merge_rules", "message": "启用的 table_name 必须唯一", "type": "duplicate"}]
    return []


def _semantic_errors_for_recon(rule: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    rule_ids = [item["rule_id"] for item in rule.get("rules", [])]
    if len(rule_ids) != len(set(rule_ids)):
        errors.append({"path": "rules", "message": "rule_id 必须唯一", "type": "duplicate"})
    for idx, item in enumerate(rule.get("rules", [])):
        recon_config = item.get("reconciliation_config", {})
        key_columns = recon_config.get("key_columns", {}).get("columns", [])
        if not key_columns and not recon_config.get("key_columns", {}).get("cross_file_mapping"):
            errors.append(
                {
                    "path": f"rules.{idx}.reconciliation_config.key_columns",
                    "message": "至少需要配置 key_columns.columns 或 cross_file_mapping",
                    "type": "missing",
                }
            )
        for compare_idx, compare_item in enumerate(recon_config.get("compare_columns", {}).get("columns", [])):
            if not compare_item.get("column"):
                errors.append(
                    {
                        "path": f"rules.{idx}.reconciliation_config.compare_columns.columns.{compare_idx}",
                        "message": "compare_columns 缺少 column",
                        "type": "missing",
                    }
                )
        for agg_idx, aggregation in enumerate(recon_config.get("aggregation", {}).get("aggregations", [])):
            if aggregation.get("function") not in VALID_AGG_FUNCTIONS:
                errors.append(
                    {
                        "path": f"rules.{idx}.reconciliation_config.aggregation.aggregations.{agg_idx}.function",
                        "message": "聚合函数不在白名单内",
                        "type": "constraint",
                    }
                )
        transformations = recon_config.get("key_columns", {}).get("transformations", {})
        for file_side in ("source", "target"):
            side_config = transformations.get(file_side, {})
            pattern = side_config.get("regex_extract")
            if pattern:
                if len(pattern) > 256:
                    errors.append(
                        {
                            "path": f"rules.{idx}.reconciliation_config.key_columns.transformations.{file_side}.regex_extract",
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
                                "path": f"rules.{idx}.reconciliation_config.key_columns.transformations.{file_side}.regex_extract",
                                "message": f"正则表达式无效: {exc}",
                                "type": "regex",
                            }
                        )
            replace_pattern = side_config.get("regex_replace", {}).get("pattern")
            if replace_pattern:
                if len(replace_pattern) > 256:
                    errors.append(
                        {
                            "path": f"rules.{idx}.reconciliation_config.key_columns.transformations.{file_side}.regex_replace.pattern",
                            "message": "正则表达式过长",
                            "type": "constraint",
                        }
                    )
                else:
                    try:
                        re.compile(replace_pattern)
                    except re.error as exc:
                        errors.append(
                            {
                                "path": f"rules.{idx}.reconciliation_config.key_columns.transformations.{file_side}.regex_replace.pattern",
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
    elif expected_kind == "merge":
        normalized_payload = rule_payload
        model = ProcMergeRuleSetModel
        semantic_check = _semantic_errors_for_merge
    elif expected_kind == "proc_entry":
        normalized_payload = rule_payload
        if normalized_payload.get("rules"):
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
                [{"path": "$", "message": "规则中未定义 rules 或 merge_rules", "type": "missing"}],
            )
    elif expected_kind == "recon":
        normalized_payload = rule_payload
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
