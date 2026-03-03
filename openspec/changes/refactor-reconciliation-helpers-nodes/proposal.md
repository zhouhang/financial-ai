## Why

`reconciliation/helpers.py` (1992行) 和 `nodes.py` (2048行) 文件过大,难以维护和理解。需要拆分为更小的、职责单一的文件模块,同时保持现有功能完全不变。

## What Changes

- **helpers.py** 拆分 (预计1992行 → 6个文件):
  - `field_mapping_helpers.py`: 字段映射相关 (`_apply_field_mapping_operations`, `_format_field_mappings`, `_guess_field_mappings`, `_build_field_mapping_text` 等)
  - `rule_config_helpers.py`: 规则配置相关 (`_rule_template_to_mappings`, `_rule_template_to_config_items`, `_build_rule_config_text`, `_analyze_config_target` 等)
  - `schema_helpers.py`: Schema转换相关 (`_rewrite_schema_transforms_to_mapped_fields`, `_preview_schema`, `_merge_json_snippets`, `_validate_and_deduplicate_rules` 等)
  - `matching_helpers.py`: 规则匹配相关 (`match_rules_by_field_names`, `calculate_match_percentage`, `_find_matching_items`, `_calculate_fuzzy_match_score` 等)
  - `error_helpers.py`: 错误消息构建 (`build_validation_error_message`, `build_single_file_error_message`, `build_format_error_message` 等)
  - `conversion_helpers.py`: 格式转换 (`_format_operations_summary`, `_translate_rule_name_to_english`, `_extract_keywords` 等)

- **nodes.py** 拆分 (预计2048行 → 8个文件):
  - `analysis_nodes.py`: 文件分析节点 (`file_analysis_node`)
  - `mapping_nodes.py`: 字段映射节点 (`field_mapping_node`)
  - `recommendation_nodes.py`: 规则推荐节点 (`rule_recommendation_node`)
  - `config_nodes.py`: 规则配置节点 (`rule_config_node`)
  - `preview_nodes.py`: 验证预览节点 (`validation_preview_node`)
  - `save_nodes.py`: 保存规则节点 (`save_rule_node`, `edit_save_node`, `result_evaluation_node`)
  - `edit_nodes.py`: 编辑模式节点 (`edit_field_mapping_node`, `edit_rule_config_node`, `edit_validation_preview_node`)
  - `router_nodes.py`: 路由节点 (`entry_router_node`, `_generate_friendly_response_for_other_intent`)

- **更新导入**: 修改所有引用这些函数的地方,使用新的模块路径

## Capabilities

### New Capabilities
- (无新功能)

### Modified Capabilities
- (无需求变更,仅重构)

## Impact

- **重构影响**:
  - 所有现有的 helpers.py 和 nodes.py 函数需要更新导入路径
  - 需要确保 `routers.py` 和 `__init__.py` 中的导入正确
  - 需要更新任何外部引用这些函数的模块
- **测试**: 需要运行现有测试确保功能不变
- **风险**: 这是高风险重构,需要确保所有导入正确
