# helpers.py 重构前后代码差异报告

> **迁移状态**：✅ 已完成迁移（以原版 helpers.py commit 935c4c1 为准，已迁移至各 `*_helpers.py`）

---

## 1. field_mapping_helpers.py

### 1.1 _format_edit_field_mappings
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 格式 | 业务列名↔财务列名，每行 bullet `•` | ✅ 已恢复 |
| 空值返回 | `"（无映射）"` | ✅ 已恢复 |

### 1.2 _build_field_mapping_text
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 格式 | `{label}: {role}->{col_str}, ...`，label 为「业务」/「财务」，col 用 `" / ".join` | ✅ 已恢复 |

### 1.3 _format_field_mappings
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 空时 | `"（未找到匹配字段）"` | ✅ 已恢复 |
| bullet_style=False | `"\n\n".join(lines)` | ✅ 已恢复 |

### 1.4 _guess_field_mappings
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 文件名 | `a.get("original_filename") or a.get("filename", "")` | ✅ 已使用 |

---

## 2. rule_config_helpers.py

### 2.1 _format_rule_config_items
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 行格式 | `  {idx}. {target} {desc}` 带编号 | ✅ 已恢复 |
| 两文件拆分 | 当 target 含 `" + "` 时拆成两行，每行带 `📁` | ✅ 已恢复 |
| desc 来源 | `item.get("description") or item.get("content") or item.get("name", "")` | ✅ 已恢复 |

---

## 3. conversion_helpers.py

### 3.1 delete_uploaded_files
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| MCP 工具名 | `"file_delete"` | ✅ 已恢复 |
| 参数 | `{auth_token, file_paths}` | ✅ 已恢复 |

### 3.2 _adjust_field_mappings_with_llm
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 完整 prompt | json_examples、规则 1–10、delete_column 说明等 | ✅ 已恢复 |
| 文件名 | `a.get("original_filename") or a.get("filename", "")` | ✅ 已使用 |

### 3.3 quick_complexity_check
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| file_count > 2 | 返回 `"complex"` | ✅ 已恢复 |
| file_count == 1 | 返回 `"medium"` | ✅ 已恢复 |

### 3.4 _fallback_classify_sheets_by_name
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 输入 | `sheets`: 每项含 `sheet_name` 等（dict 列表） | ✅ 已适配 |
| 返回值 | `{sheet_name: {type, confidence, reason}}` | ✅ 已恢复 |

### 3.5 extract_sample_rows
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| CSV | 使用 chardet 检测编码 | ✅ 已恢复 |
| 返回 | `df.fillna("").to_dict(orient="records")` | ✅ 已恢复 |

### 3.6 _translate_rule_name_to_english
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 实现 | pypinyin 转拼音再生成 type_key | ✅ 已恢复 |

---

## 4. matching_helpers.py

### 4.1 _extract_keywords
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 中文 | 按字符双重循环提取所有中文字串 | ✅ 已恢复 |

### 4.2 _compute_keyword_overlap
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 逻辑 | 长串精确匹配→0.9；否则按字符重叠度 | ✅ 已恢复 |

### 4.3 _calculate_fuzzy_match_score
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 逻辑 | keyword_score*0.6 + sequence_score*0.4 | ✅ 已恢复 |

### 4.4 _find_matching_items
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 参数 | `(target, items, threshold=0.5, max_matches, strict_substring_only)` | ✅ 已恢复，并保留 `key="description"` 可选 |

---

## 5. schema_helpers.py

### 5.1 _rewrite_schema_transforms_to_mapped_fields
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 逻辑 | 将 transform/expression 中 row.get('orig_col') 替换为 row.get('role') | ✅ 已恢复 |

### 5.2 _validate_and_deduplicate_rules
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 逻辑 | 订单号去重、row_filters 业务侧删除等 | ✅ 已恢复 |

### 5.3 _merge_json_snippets
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 逻辑 | 支持 json_snippet 包装，深度合并，排除 custom_validations | ✅ 已恢复 |

---

## 6. error_helpers.py

### 6.1 build_validation_error_message
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 签名 | `(validation_result, file_paths)` | ✅ 已恢复 |

### 6.2 build_single_file_error_message
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 格式 | HTML 表格样例 | ✅ 已恢复 |

### 6.3 build_format_error_message
| 维度 | 原版 | 迁移后 |
|------|------|--------|
| 签名 | `(validation_result, file_paths, original_filenames_map)` | ✅ 已恢复 |
