# Proc 输出示例

好的中文说明示例：

1. 步骤1：定义左侧整理结果表 `left_recon_ready`，保留业务单号、业务日期、净收入金额、来源数据集名称。
2. 步骤2：将 `mall_orders` 与 `mall_refunds` 按订单号汇总，退款金额取负后计算左侧净收入，写入 `left_recon_ready`。
3. 步骤3：定义右侧整理结果表 `right_recon_ready`，保留入账单号、入账日期、入账金额、来源数据集名称。
4. 步骤4：将 `erp_receipts` 中的入账流水直接映射到 `right_recon_ready`，输出对账所需金额和日期字段。

不好的中文说明示例：

1. 步骤1：处理左侧整理结果表。
2. 步骤2：处理右侧整理结果表。

JSON 片段示例：

```json
{
  "step_id": "left_write_recon_ready",
  "action": "write_dataset",
  "target_table": "left_recon_ready",
  "row_write_mode": "upsert",
  "sources": [
    { "alias": "orders", "table": "mall_orders" },
    { "alias": "refunds", "table": "mall_refunds" }
  ],
  "mappings": [
    {
      "target_field": "biz_key",
      "value": {
        "type": "source",
        "source": { "alias": "orders", "field": "order_id" }
      },
      "field_write_mode": "overwrite"
    }
  ]
}
```
