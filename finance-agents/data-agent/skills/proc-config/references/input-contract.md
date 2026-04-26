# Proc 输入 Contract

输入载荷包含四部分：

1. `request_type`
   - `generate_proc_draft`
   - `regenerate_proc_draft`
2. `session_context`
   - `session_id`
   - `scheme_name`
   - `biz_goal`
3. `target_context`
   - `left_sources`
   - `right_sources`
   - `left_description`
   - `right_description`
   - `sample_datasets`
4. `rule_context`
   - `user_instruction_text`
   - `previous_effective_rule_json`
   - `previous_trial_feedback`
   - `previous_validation_errors`

重点理解：

1. `left_sources` / `right_sources` 是当前用户已经选定的数据集，字段里会带 `source_table_identifier`（源表执行标识）、`dataset_name`、`schema_summary`、`sample_rows`。
   - 还会带 `business_name`、`field_label_map`、`fields`、`field_display_pairs`、`sample_rows_with_display_fields`。
   - **重要**：`source_table_identifier` 是整张表的执行层标识符（如 `alipay_orders`），不是表中的数据列，禁止在 `source.field` 中使用它。
2. `sample_datasets` 是左右两侧样本数据的合集，通常与 `left_sources` / `right_sources` 对应。
3. 若上一轮有试跑失败，优先阅读 `previous_trial_feedback` 和 `previous_validation_errors`，再修订草稿。

字段使用约束：

1. `business_name` 和 `display_with_raw` 只用于帮助理解业务语义。
2. `effective_rule_json` 中字段引用必须使用原始字段名 `raw_name`（来自 `schema_summary` 或 `sample_rows` 的列名）。
3. 禁止把中文显示名写入 `mappings/match/filter/aggregate` 的字段路径。
4. `biz_key`、`amount`、`biz_date`、`source_name` 是标准输出字段，只能作为 `target_field`，禁止作为 `source.field`。

生成说明时必须覆盖：

1. 左侧用了哪些数据集。
2. 右侧用了哪些数据集。
3. 每一步的整理动作。
4. 左右最终输出的核心字段。

禁止出现这类模糊表述：

1. `处理左侧整理结果表`
2. `处理右侧整理结果表`
3. `执行数据整理`
