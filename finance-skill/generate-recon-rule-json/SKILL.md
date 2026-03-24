---
name: generate-recon-rule-json
description: 当用户根据分步的数据对账逻辑生成 recon 规则 JSON 时使用。输出符合当前 finance-mcp source_file/target_file/recon/output 风格的 JSON。
---

# 生成 Recon 规则 JSON

当用户描述一套对账流程，并希望生成 recon 规则 JSON 时，使用这个 skill。

典型请求：
- “根据这 1 2 3 4 5 步对账逻辑生成 recon json”
- “把这个对账场景配置成当前 recon 规则”
- “按现有 recon 样例写一个新的规则”

## 目标

把用户的对账逻辑转成当前 `recon_execute` 使用的 recon JSON 格式。

除非用户明确要求解释，否则默认只输出 JSON。

## 当前顶层结构

使用下面这个结构：

```json
{
  "rule_id": "RULE_ID",
  "rule_name": "规则名称",
  "description": "规则描述",
  "file_rule_code": "关联文件检查规则编码",
  "schema_version": "1.6",
  "rules": [
    {
      "enabled": true,
      "source_file": {},
      "target_file": {},
      "recon": {},
      "output": {}
    }
  ]
}
```

## 当前支持的主要区块

每个 `rules[]` 项里可以使用：
- `source_file.identification`
- `target_file.identification`
- `source_file.filter`
- `target_file.filter`
- `source_file.column_mapping`
- `target_file.column_mapping`
- `recon.key_columns`
- `recon.compare_columns`
- `recon.aggregation`
- `output`

## 文件识别写法

默认使用按表名识别：

```json
{
  "identification": {
    "match_by": "table_name",
    "match_value": "源表名称",
    "match_strategy": "exact"
  }
}
```

当前常见 `match_strategy`：
- `exact`
- `contains`
- `startswith`

## 业务键匹配写法

一个或多个业务键的写法：

```json
{
  "key_columns": {
    "mappings": [
      {
        "source_field": "订单号",
        "target_field": "外部订单号"
      }
    ],
    "match_type": "exact"
  }
}
```

## 当前支持的字段清洗类型

只使用当前支持的 transformation 类型：
- `regex_extract`
- `regex_replace`
- `strip_prefix`
- `strip_suffix`
- `strip_whitespace`
- `lowercase`

示例：

```json
{
  "transformations": {
    "source": {
      "订单号": [
        {
          "type": "strip_prefix",
          "value": "'"
        }
      ]
    },
    "target": {
      "外部订单号": [
        {
          "type": "regex_replace",
          "pattern": "_\\\\d+$",
          "replacement": ""
        }
      ]
    }
  }
}
```

## 比对字段写法

```json
{
  "compare_columns": {
    "columns": [
      {
        "name": "金额差异",
        "compare_type": "numeric",
        "source_column": "发生金额",
        "target_column": "平台金额",
        "tolerance": 0.01
      }
    ]
  }
}
```

## 聚合写法

只有用户明确要求“先汇总再比对”时，才加 `aggregation`。

```json
{
  "aggregation": {
    "enabled": true,
    "group_by": [
      {
        "source_field": "订单号",
        "target_field": "外部订单号"
      }
    ],
    "aggregations": [
      {
        "alias": "金额汇总",
        "function": "sum",
        "source_field": "发生金额",
        "target_field": "平台金额"
      }
    ]
  }
}
```

## 输出写法

默认输出 xlsx，并保留标准结果 sheet：

```json
{
  "output": {
    "format": "xlsx",
    "file_name_template": "{rule_name}_核对结果_{timestamp}",
    "sheets": {
      "summary": { "name": "核对汇总", "enabled": true },
      "source_only": { "name": "源表独有", "enabled": true },
      "target_only": { "name": "目标独有", "enabled": true },
      "matched_with_diff": { "name": "差异记录", "enabled": true }
    }
  }
}
```

## 工作流

1. 从用户描述中识别源文件和目标文件。
2. 明确文件在 file validation 阶段如何被识别。
3. 提取用于关联记录的业务键。
4. 如果用户提到清洗单号、去前缀、归一化值或正则处理，就补 `transformations`。
5. 补齐 compare columns 和 tolerance。
6. 只有用户明确要求“先汇总再比对”时，才加 aggregation。
7. 如果用户描述了多个独立的源目标对账场景，就在顶层 `rules` 里生成多个 item。
8. 返回一个完整 JSON 对象。

## 输出规则

- 默认只输出 JSON。
- 保持当前 recon 规则风格。
- 优先写清楚 `source_field` / `target_field` 映射。
- 业务展示名称保留用户原始语言。

## 边界

不要静默发明当前 recon engine 不支持的能力。遇到以下需求要先指出缺口：
- 三方或多方对账
- 对第三张参考表做 lookup
- 一对多核销或区间匹配
- 不是“列对列”而是公式派生值的比对
- 当前不支持的 transformation 类型
