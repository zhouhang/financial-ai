"""对账辅助函数模块（向后兼容）

此文件已重构为多个子模块。所有功能已移动到：
- field_mapping_helpers.py: 字段映射
- rule_config_helpers.py: 规则配置
- schema_helpers.py: Schema处理
- matching_helpers.py: 规则匹配
- error_helpers.py: 错误消息
- conversion_helpers.py: 转换函数

此文件保留用于向后兼容，新代码请从子模块导入。
"""

# 从子模块重新导出所有函数
from graphs.reconciliation.field_mapping_helpers import (
    _apply_field_mapping_operations,
    _format_field_mappings,
    _guess_field_mappings,
    _format_edit_field_mappings,
    _build_field_mapping_text,
    _format_operations_summary,
)
from graphs.reconciliation.rule_config_helpers import (
    _rule_template_to_mappings,
    _get_file_names_from_rule_template,
    _rule_template_to_config_items,
    _build_rule_config_text,
    _analyze_config_target,
    _format_rule_config_items,
)
from graphs.reconciliation.schema_helpers import (
    _rewrite_schema_transforms_to_mapped_fields,
    _preview_schema,
    _merge_json_snippets,
    _validate_and_deduplicate_rules,
    _build_dummy_analyses_from_mappings,
)
from graphs.reconciliation.matching_helpers import (
    _extract_keywords,
    _compute_keyword_overlap,
    _calculate_fuzzy_match_score,
    _find_matching_items,
    match_rules_by_field_names,
    calculate_match_percentage,
    get_match_reason,
    KEY_FIELD_ALIASES,
    EXACT_MATCH_FIELDS,
    _is_field_match,
)
from graphs.reconciliation.error_helpers import (
    build_validation_error_message,
    build_single_file_error_message,
    build_format_error_message,
)
from graphs.reconciliation.conversion_helpers import (
    FILE_PATTERN_EXTENSIONS,
    _expand_file_patterns,
    _translate_rule_name_to_english,
    quick_complexity_check,
    _fallback_classify_sheets_by_name,
    extract_sample_rows,
    delete_uploaded_files,
    _adjust_field_mappings_with_llm,
    invoke_intelligent_analyzer,
)

__all__ = [
    "FILE_PATTERN_EXTENSIONS",
    "_expand_file_patterns",
    "_rewrite_schema_transforms_to_mapped_fields",
    "_extract_keywords",
    "_compute_keyword_overlap",
    "_calculate_fuzzy_match_score",
    "_find_matching_items",
    "_apply_field_mapping_operations",
    "_format_operations_summary",
    "_adjust_field_mappings_with_llm",
    "_format_field_mappings",
    "_rule_template_to_mappings",
    "_get_file_names_from_rule_template",
    "_rule_template_to_config_items",
    "_format_edit_field_mappings",
    "_build_field_mapping_text",
    "_build_rule_config_text",
    "_guess_field_mappings",
    "_analyze_config_target",
    "_format_rule_config_items",
    "_validate_and_deduplicate_rules",
    "_merge_json_snippets",
    "_translate_rule_name_to_english",
    "_preview_schema",
    "_build_dummy_analyses_from_mappings",
    "match_rules_by_field_names",
    "calculate_match_percentage",
    "get_match_reason",
    "build_validation_error_message",
    "build_single_file_error_message",
    "build_format_error_message",
    "quick_complexity_check",
    "_fallback_classify_sheets_by_name",
    "extract_sample_rows",
    "delete_uploaded_files",
    "KEY_FIELD_ALIASES",
    "EXACT_MATCH_FIELDS",
    "_is_field_match",
]
