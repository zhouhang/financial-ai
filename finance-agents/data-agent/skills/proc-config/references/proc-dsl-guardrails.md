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

标准输出字段约束（极重要）：

1. `biz_key`、`amount`、`biz_date`、`source_name` 是 proc 步骤的标准输出字段，只能出现在 `target_field`，永远不能作为 `source.field`（源字段）。
2. `biz_key` 必须从源表的实际主键字段（如 `order_id`、`ledger_id`）映射而来，形如 `{"target_field": "biz_key", "value": {"type": "source", "source": {"alias": "...", "field": "actual_key_field"}}}`。
3. `source_name` 必须使用 `formula` 类型输出数据来源的业务名称字符串（中文固定值），禁止映射到源表任何数据库字段。

数据集元数据约束（极重要）：

1. 输入 payload 中的 `source_table_identifier` 是本数据集的执行层标识符（即源表名），不是表里的数据列。
2. 禁止把 `source_table_identifier` 的值或 `table_name` 这个字符串作为 `source.field` 使用。
3. `sources[].table` 应引用 `source_table_identifier` 的值（如 `alipay_orders`），而非字面量 `"table_name"` 或 `"source_table_identifier"`。

如果需求超出能力，不要自造 DSL，直接写入 `unsupported_points`。
