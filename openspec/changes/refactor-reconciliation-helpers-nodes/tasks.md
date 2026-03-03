## 1. Helpers 拆分

- [ ] 1.1 创建 field_mapping_helpers.py
  - 移动: _apply_field_mapping_operations, _format_field_mappings, _guess_field_mappings, _build_field_mapping_text, _format_edit_field_mappings
- [ ] 1.2 创建 rule_config_helpers.py
  - 移动: _rule_template_to_mappings, _rule_template_to_config_items, _build_rule_config_text, _analyze_config_target, _format_rule_config_items
- [ ] 1.3 创建 schema_helpers.py
  - 移动: _rewrite_schema_transforms_to_mapped_fields, _preview_schema, _merge_json_snippets, _validate_and_deduplicate_rules, _build_dummy_analyses_from_mappings
- [ ] 1.4 创建 matching_helpers.py
  - 移动: match_rules_by_field_names, calculate_match_percentage, get_match_reason, _find_matching_items, _compute_keyword_overlap, _calculate_fuzzy_match_score, _is_field_match
- [ ] 1.5 创建 error_helpers.py
  - 移动: build_validation_error_message, build_single_file_error_message, build_format_error_message
- [ ] 1.6 创建 conversion_helpers.py
  - 移动: _format_operations_summary, _translate_rule_name_to_english, _extract_keywords, _expand_file_patterns, _get_file_names_from_rule_template, _adjust_field_mappings_with_llm, quick_complexity_check, _fallback_classify_sheets_by_name, extract_sample_rows

## 2. Nodes 拆分

- [ ] 2.1 创建 analysis_nodes.py
  - 移动: file_analysis_node
- [ ] 2.2 创建 mapping_nodes.py
  - 移动: field_mapping_node
- [ ] 2.3 创建 recommendation_nodes.py
  - 移动: rule_recommendation_node
- [ ] 2.4 创建 config_nodes.py
  - 移动: rule_config_node
- [ ] 2.5 创建 preview_nodes.py
  - 移动: validation_preview_node
- [ ] 2.6 创建 save_nodes.py
  - 移动: save_rule_node, edit_save_node, result_evaluation_node
- [ ] 2.7 创建 edit_nodes.py
  - 移动: edit_field_mapping_node, edit_rule_config_node, edit_validation_preview_node
- [ ] 2.8 创建 router_nodes.py
  - 移动: entry_router_node, _generate_friendly_response_for_other_intent

## 3. 更新 __init__.py

- [ ] 3.1 更新 helpers 导入来源指向新模块
- [ ] 3.2 更新 nodes 导入来源指向新模块

## 4. 更新外部引用

- [ ] 4.1 检查并更新 server.py 中的导入
- [ ] 4.2 检查并更新 workflow_intent.py 中的导入
- [ ] 4.3 检查并更新 main_graph/nodes.py 中的导入

## 5. 验证

- [ ] 5.1 运行 ruff check 确保无导入错误
- [ ] 5.2 运行 pytest 确保功能测试通过
- [ ] 5.3 手动测试对账流程确保工作正常

## 6. 清理

- [ ] 6.1 (可选) 删除原始 helpers.py 和 nodes.py 中的函数定义
- [ ] 6.2 (可选) 在原文件中保留重定向提示
