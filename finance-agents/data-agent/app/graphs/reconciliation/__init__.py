"""对账子图模块

包含对账工作流的节点和辅助函数。

文件结构：
- nodes.py: 节点函数
- helpers.py: 辅助函数（已拆分为子模块）
"""

# ── 辅助函数（从拆分子模块导入）──────────────────────────────
from app.graphs.reconciliation.helpers import (
    FILE_PATTERN_EXTENSIONS,
    _expand_file_patterns,
    _rewrite_schema_transforms_to_mapped_fields,
    _extract_keywords,
    _compute_keyword_overlap,
    _calculate_fuzzy_match_score,
    _find_matching_items,
    _apply_field_mapping_operations,
    _format_operations_summary,
    _adjust_field_mappings_with_llm,
    _format_field_mappings,
    _rule_template_to_mappings,
    _get_file_names_from_rule_template,
    _rule_template_to_config_items,
    _format_edit_field_mappings,
    _build_field_mapping_text,
    _build_rule_config_text,
    _guess_field_mappings,
    _analyze_config_target,
    _format_rule_config_items,
    _validate_and_deduplicate_rules,
    _merge_json_snippets,
    _translate_rule_name_to_english,
    _preview_schema,
    _build_dummy_analyses_from_mappings,
    match_rules_by_field_names,
    calculate_match_percentage,
    get_match_reason,
    build_validation_error_message,
    build_single_file_error_message,
    build_format_error_message,
    quick_complexity_check,
    _fallback_classify_sheets_by_name,
    extract_sample_rows,
    delete_uploaded_files,
    invoke_intelligent_analyzer,
)

# ── 解析函数 ─────────────────────────────────────────────
from app.graphs.reconciliation.parsers import (
    _parse_rule_config_json_snippet,
    _parse_rule_config_with_llm,
)

# ── 节点函数 ─────────────────────────────────────────────
from app.graphs.reconciliation.nodes import (
    file_analysis_node,
    field_mapping_node,
    rule_recommendation_node,
    rule_config_node,
    validation_preview_node,
    save_rule_node,
    result_evaluation_node,
    edit_field_mapping_node,
    edit_rule_config_node,
    edit_validation_preview_node,
    edit_save_node,
    entry_router_node,
    _generate_friendly_response_for_other_intent,
)

# ── 路由函数 ─────────────────────────────────────────────
from app.graphs.reconciliation.routers import (
    route_after_file_analysis,
    route_after_field_mapping,
    route_after_rule_recommendation,
    route_after_rule_config,
    route_after_preview,
    route_after_save_rule,
    route_from_entry,
    build_reconciliation_subgraph,
)

__all__ = [
    # 常量
    "FILE_PATTERN_EXTENSIONS",
    # 辅助函数
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
    # 解析函数
    "_parse_rule_config_json_snippet",
    "_parse_rule_config_with_llm",
    # 节点函数
    "file_analysis_node",
    "field_mapping_node",
    "rule_config_node",
    "validation_preview_node",
    "save_rule_node",
    "edit_field_mapping_node",
    "edit_rule_config_node",
    "edit_validation_preview_node",
    "edit_save_node",
    "entry_router_node",
    # 路由函数
    "route_after_file_analysis",
    "route_after_field_mapping",
    "route_after_rule_config",
    "route_after_preview",
    "route_from_entry",
    "build_reconciliation_subgraph",
]
