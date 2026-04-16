# Proc DSL Guardrails

只允许使用当前 steps DSL：

1. 顶层字段：`role_desc` `version` `metadata` `global_config` `file_rule_code` `dsl_constraints` `steps`
2. `steps[].action` 只允许：
   - `create_schema`
   - `write_dataset`
3. `create_schema` 负责定义结果表结构。
4. `write_dataset` 负责把源数据写入结果表。

硬约束：

1. 必须显式创建并写入 `left_recon_ready`。
2. 必须显式创建并写入 `right_recon_ready`。
3. 每个 step 都必须有唯一 `step_id`。
4. 每个 `write_dataset` 都必须有：
   - `target_table`
   - `row_write_mode`
   - `sources`
   - `mappings`
5. 每个 `sources[]` 都必须写：
   - `alias`
   - `table`
6. `sources[].table` 必须来自输入数据集的真实 `table_name`。
7. 不能写空字符串，不能写 `unknown`，不能虚构不存在的表名。

`schema.columns[]` 只使用这些列定义字段：

1. `name`
2. `data_type`
3. `nullable`
4. `default`
5. `precision`
6. `scale`

`mappings[]` 只使用这些 value 类型：

1. `source`
2. `formula`
3. `template_source`
4. `function`
5. `context`

如果需求超出能力，不要自造 DSL，直接写入 `unsupported_points`。
