# Recon 输出示例

好的中文说明示例：

1. 按 `biz_key` 做左侧与右侧的一对一精确匹配。
2. 比对左侧 `amount` 与右侧 `amount`，允许金额容差 `0.01`。
3. 输出核对汇总、左侧独有、右侧独有和差异记录四类结果。

不好的中文说明示例：

1. 进行数据对账。
2. 检查左右是否一致。

JSON 片段示例：

```json
{
  "source_file": {
    "table_name": "left_recon_ready",
    "identification": {
      "match_by": "table_name",
      "match_value": "left_recon_ready",
      "match_strategy": "exact"
    }
  },
  "target_file": {
    "table_name": "right_recon_ready",
    "identification": {
      "match_by": "table_name",
      "match_value": "right_recon_ready",
      "match_strategy": "exact"
    }
  },
  "recon": {
    "key_columns": {
      "mappings": [
        { "source_field": "biz_key", "target_field": "biz_key" }
      ],
      "match_type": "exact"
    },
    "compare_columns": {
      "columns": [
        {
          "name": "金额差异",
          "compare_type": "numeric",
          "source_column": "amount",
          "target_column": "amount",
          "tolerance": 0.01
        }
      ]
    }
  }
}
```
