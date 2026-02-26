"""对账子图模块 — 第2层：规则生成工作流

节点流程：
  file_analysis → field_mapping (HITL) → rule_config (HITL) → validation_preview (HITL) → save_rule

每个 HITL 节点通过 interrupt 暂停，等待用户确认后继续。

字段映射逻辑（以用户纠正结果为准）：
  1. 文件解析表头 → LLM 自动猜测（仅 order_id/amount/date，不含 status）
  2. 显示给用户 → 用户可确认或输入自然语言纠正（如「删除status」）
  3. LLM 解析纠正意见 → 更新底层 JSON
  4. 最终以 confirmed_mappings 为准 → 保存到 rule_template.field_roles
  5. field_mapping_text、rule_config_text 一并存入 rule_template，供编辑规则时展示

本模块是原 reconciliation.py (2535行) 重构后的模块化版本，
保持向后兼容，所有原有导入仍然可用。
"""

# Re-export all public interfaces from submodules

# ── 辅助函数 ─────────────────────────────────────────────────────────────────
from .helpers import (
    # 常量
    FILE_PATTERN_EXTENSIONS,
    # 文件模式处理
    _expand_file_patterns,
    _rewrite_schema_transforms_to_mapped_fields,
    # 文本匹配
    _extract_keywords,
    _compute_keyword_overlap,
    _calculate_fuzzy_match_score,
    _find_matching_items,
    # 字段映射操作
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
    # 配置处理
    _analyze_config_target,
    _format_rule_config_items,
    _validate_and_deduplicate_rules,
    _merge_json_snippets,
    _translate_rule_name_to_english,
    # 预览和分析
    _preview_schema,
    _build_dummy_analyses_from_mappings,
)

# ── 解析函数 ─────────────────────────────────────────────────────────────────
from .parsers import (
    _parse_rule_config_json_snippet,
    _parse_rule_config_with_llm,
)

# ── 节点函数 ─────────────────────────────────────────────────────────────────
from .nodes import (
    # 创建规则流程节点
    file_analysis_node,
    field_mapping_node,
    rule_recommendation_node,
    rule_config_node,
    validation_preview_node,
    save_rule_node,
    result_evaluation_node,
    # 编辑规则流程节点
    edit_field_mapping_node,
    edit_rule_config_node,
    edit_validation_preview_node,
    edit_save_node,
    # 入口路由节点
    entry_router_node,
)

# ── 路由函数 ─────────────────────────────────────────────────────────────────
from .routers import (
    route_after_file_analysis,
    route_after_field_mapping,
    route_after_rule_recommendation,
    route_after_rule_config,
    route_after_preview,
    route_after_save_rule,
    route_from_entry,
    build_reconciliation_subgraph,
)

# 定义 __all__ 以明确公开接口
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
