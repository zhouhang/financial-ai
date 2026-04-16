# Recon DSL Guardrails

顶层字段至少包含：

1. `rule_id`
2. `rule_name`
3. `description`
4. `file_rule_code`
5. `schema_version`
6. `rules`

硬约束：

1. `source_file.table_name` 必须是 `left_recon_ready`。
2. `target_file.table_name` 必须是 `right_recon_ready`。
3. `source_file.identification.match_value` 与 `target_file.identification.match_value` 也要与上述表名一致。
4. `recon.key_columns.mappings` 必须完整。
5. `recon.compare_columns.columns` 必须完整。
6. `compare_columns.columns[].compare_type` 只使用 `numeric`。
7. `compare_columns.columns[].tolerance` 必须是数字。
8. `output.sheets` 需要包含：
   - `summary`
   - `source_only`
   - `target_only`
   - `matched_with_diff`

禁止：

1. 三方或多方对账。
2. 第三张参考表 lookup。
3. 区间匹配。
4. recon 引擎未支持的 transformation 类型。

如果需求超出能力，不要自造字段，直接写入 `unsupported_points`。
