---
name: generate-proc-rule-json
description: 当用户根据分步的数据整理逻辑生成 proc 规则 JSON 时使用。输出符合当前 finance-mcp create_schema/write_dataset steps DSL 风格的 JSON。
---

# 生成 Proc 规则 JSON

当用户描述一套数据整理流程，并希望生成 proc JSON 时，使用这个 skill。

典型请求：
- “根据这 1 2 3 4 5 步整理逻辑生成 proc json”
- “把这个数据整理需求配置成新的 proc 规则”
- “按当前 proc DSL 样例写一个可执行 json”

## 目标

把用户的分步业务逻辑转成当前 `proc_execute` 使用的 `steps` DSL。

除非用户明确要求解释，否则默认只输出 JSON。

## 当前顶层结构

使用下面这个结构：

```json
{
  "role_desc": "规则说明",
  "version": "4.5",
  "metadata": {
    "created_at": "2026-03-24T10:30:00+08:00",
    "author": "codex",
    "tags": ["数据整理"]
  },
  "global_config": {
    "default_round_precision": 2,
    "date_format": "YYYY-MM-DD",
    "null_value_handling": "keep",
    "error_handling": "stop"
  },
  "file_rule_code": "关联文件检查规则编码",
  "dsl_constraints": {
    "actions": ["create_schema", "write_dataset"],
    "builtin_functions": ["earliest_date", "current_date", "month_of"],
    "aggregate_operators": ["sum", "min"],
    "field_write_modes": ["overwrite", "increment"],
    "row_write_modes": ["insert_if_missing", "update_only", "upsert"],
    "column_data_types": ["string", "date", "decimal"],
    "value_node_types": ["source", "formula", "template_source", "function", "context"],
    "merge_strategies": ["union_distinct"],
    "loop_context_vars": ["month", "prev_month", "is_first_month"]
  },
  "steps": []
}
```

## Step 约定

只使用当前支持的 action：
- `create_schema`
- `write_dataset`

统一遵循这些约定：
- 不要再写 `enabled`
- 每个 step 都要有稳定的英文 `step_id`
- `target_table` 尽量放在 step 前部，便于阅读
- source `alias` 用英文，不用拼音
- 只要后续 step 依赖前面 step 的表或结果，就显式写 `depends_on`

## 当前 DSL 组件

按需使用这些节点：
- `schema.columns`
- `schema.primary_key`
- `schema.dynamic_columns`
- `sources`
- `match.sources[].keys`
- `reference_filter`
- `filter`
- `aggregate`
- `mappings`
- `dynamic_mappings`
- `row_write_mode`
- `field_write_mode`

`value.type` 只使用：
- `source`
- `formula`
- `template_source`
- `function`
- `context`

聚合算子写在 `aggregate[].aggregations[].operator`，不要写成 `function`。

## Mapping 写法

普通字段复制写法：

```json
{
  "target_field": "公司名称",
  "value": {
    "type": "source",
    "source": {
      "alias": "opening_balance_source",
      "field": "公司"
    }
  },
  "field_write_mode": "overwrite"
}
```

公式写法：

```json
{
  "target_field": "计算余额",
  "value": {
    "type": "formula",
    "expr": "{balance} + {debit} - {credit}"
  },
  "bindings": {
    "balance": {
      "type": "source",
      "source": {
        "alias": "merged_statistics",
        "field": "期初余额"
      }
    },
    "debit": {
      "type": "source",
      "source": {
        "alias": "merged_statistics",
        "field": "累计借方"
      }
    },
    "credit": {
      "type": "source",
      "source": {
        "alias": "merged_statistics",
        "field": "累计贷方"
      }
    }
  },
  "field_write_mode": "overwrite"
}
```

## 工作流

1. 先读用户的编号步骤，列出所有源表、目标表和中间表。
2. 判断哪些 step 是 `create_schema`，哪些是 `write_dataset`。
3. 对每个写入 step，明确：
- 用哪些源表
- 按什么 key 匹配
- 是否需要 `reference_filter`
- 是否需要 `aggregate`
- 是固定 mappings 还是动态 mappings
4. 任何新表第一次写入前，都先创建 schema。
5. 显式补齐 `depends_on`。
6. 如果用户描述的是按月滚动逻辑，就使用：
- `schema.dynamic_columns`
- `dynamic_mappings`
- `month`、`prev_month`、`is_first_month` 这类 `context` 变量
7. 返回一个完整 JSON 对象。

## 输出规则

- 优先遵循当前 v4.5 风格。
- `alias` 和 `step_id` 保持英文。
- 业务表名、字段名保留用户原始语言。
- 默认只输出 JSON。

## 边界

如果用户要求当前 DSL 不支持的语义，不要静默发明新节点，先指出缺口。常见风险包括：
- 对外部参考数据做 lookup，但这些参考数据并没有作为 source table 出现
- 用户要求按 `YYYY-MM` 区分多年的动态列，而不是当前的“月号列”
- 自定义当前 builtin list 之外的 function 名称

## 常见模式选择

- “只保留能在参考表匹配到的源数据”时，优先用 `reference_filter`
- 先分组求和或求最小时，用 `aggregate`
- 写月度列或循环回填时，用 `dynamic_mappings`
- 目标表可能需要新建行时，用 `row_write_mode = upsert`
- 目标表行必须先存在时，用 `row_write_mode = update_only`
