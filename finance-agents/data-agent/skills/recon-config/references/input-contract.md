# Recon 输入 Contract

输入载荷包含四部分：

1. `request_type`
   - `generate_recon_draft`
   - `regenerate_recon_draft`
2. `session_context`
   - `session_id`
   - `scheme_name`
   - `biz_goal`
3. `target_context`
   - 这里的左右数据已经是经过第 2 步整理后的样本
   - `sample_datasets` 中会包含 `left_recon_ready` 和 `right_recon_ready` 的字段结构与抽样
4. `rule_context`
   - `user_instruction_text`
   - `previous_effective_rule_json`
   - `previous_trial_feedback`
   - `previous_validation_errors`

重点理解：

1. Recon 阶段不能再回到原始源表做处理，只能基于整理后的左右数据做匹配与比对。
2. 如果上一轮试跑失败，优先从 `previous_trial_feedback` 中定位是主键不对、金额字段不对还是容差不合适。
3. 输入中可能包含 `business_name`、`field_label_map`、`fields`、`field_display_pairs`、`sample_rows_with_display_fields`，用于语义理解。

字段使用约束：

1. `effective_rule_json` 中的匹配字段、金额字段必须使用 `raw_name`。
2. 中文显示名（例如 `订单金额`）不能直接写入 JSON 字段引用。
