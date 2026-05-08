# 支付宝渠道专表纠偏设计

## 背景

当前 `recon` 分支已经完成淘宝/天猫订单采集和支付宝账单采集的基础接入，但两者的物理存储不一致：

- 淘宝/天猫订单明细写入 `platform_order_lines`。
- 支付宝资金账单和交易账单解析后写入 `dataset_collection_records`。

这偏离了已确认的产品偏好：电商平台授权采集数据在数据量较大时优先采用渠道专用物理表，避免把不同渠道长期堆在同一张通用采集资产表里。已讨论确定的方案后续不得擅自调整；如需改变，必须先获得用户确认。

## 目标

将支付宝授权采集后的账单行从 `dataset_collection_records` 纠偏到支付宝渠道专表。

首版不做历史迁移，只影响后续新采集数据。当前已经写入 `dataset_collection_records` 的测试数据或本地旧数据不兼容、不回迁。

## 非目标

- 不为所有未来平台一次性建表。
- 不把支付宝账单硬塞进淘宝/天猫现有的 `platform_order_lines`。
- 不把支付宝账单所有原始字段都提升为物理列。
- 不保留 `dataset_collection_records` 作为支付宝账单的主存储兜底路径。

## 数据模型

新增物理表 `platform_alipay_bill_lines`，业务对象是支付宝账单行。账单行里包含可用于订单匹配和金额核对的字段。

首版提升字段：

- `company_id`
- `data_source_id`
- `dataset_id`
- `shop_connection_id`
- `external_shop_id`
- `bill_type`
- `bill_date`
- `source_file_name`
- `source_row_number`
- `source_row_key`
- `alipay_trade_no`
- `merchant_order_no`
- `business_order_no`
- `amount`
- `income_amount`
- `expense_amount`
- `trade_time`
- `payload`

其他支付宝账单模板字段保留在 `payload` 中，后续规则高频使用时再加列。

唯一键：

`company_id + shop_connection_id + bill_type + bill_date + source_row_key`

建议索引：

- `company_id, dataset_id, bill_date, updated_at DESC`
- `company_id, data_source_id, dataset_id, bill_date DESC`
- `company_id, shop_connection_id, bill_type, bill_date DESC`
- `company_id, alipay_trade_no`
- `company_id, merchant_order_no`
- `company_id, business_order_no`

## 数据集元数据

支付宝授权成功后仍生成两个数据集：

- `支付宝资金账单 - {商户名}`
- `支付宝交易账单 - {商户名}`

数据集目录继续存放在 `data_source_datasets`，但元数据改为指向支付宝渠道专表：

- `extract_config.storage = "platform_alipay_bill_lines"`
- `schema_summary.storage = "platform_alipay_bill_lines"`
- `schema_summary.source = "alipay_bill_lines"`
- `resource_key = "alipay_bill:<bill_type>:<shop_connection_id>"`

其中 `bill_type` 保持：

- `signcustomer`：资金账单
- `trade`：交易账单

## 采集流程

支付宝授权和调度策略保持不变：

- 授权成功后只初始化 T-1。
- 每天 `10:30` 采集 T-1。
- 不采 T 日。

采集执行改为：

1. 根据数据集识别支付宝账单 driver。
2. 下载支付宝账单 ZIP/CSV。
3. 解析账单行。
4. 提升首版对账字段。
5. upsert 到 `platform_alipay_bill_lines`。
6. 事件和指标标记 `collection_driver = "alipay_bill_download_import"`，`storage = "platform_alipay_bill_lines"`。

支付宝采集不再调用 `upsert_dataset_collection_records`。

## Recon Loader

新增 recon dataset loader：

- 主 source type：`platform_alipay_bill_lines`
- 兼容别名：`alipay_bill_lines`

loader 根据 `dataset_ref` 查询 `platform_alipay_bill_lines`：

```json
{
  "source_type": "platform_alipay_bill_lines",
  "source_key": "<data_source_id>",
  "query": {
    "dataset_id": "<dataset_id>",
    "resource_key": "alipay_bill:<bill_type>:<shop_connection_id>",
    "biz_date": "YYYY-MM-DD",
    "bill_type": "trade"
  }
}
```

查询约束：

- `source_key` 对应 `data_source_id`。
- `dataset_id` 必须可用于过滤。
- `resource_key` 解析出 `bill_type` 和 `shop_connection_id`。
- `biz_date` 对应 `bill_date`。
- `filters` 只支持标量和标量数组。
- 返回 `payload` 展平后的 DataFrame，提升字段也可作为过滤和排序字段。

## 接口与展示

数据源详情、样例、采集记录读取逻辑需要识别 `platform_alipay_bill_lines`：

- 支付宝数据集样例读取专表。
- 支付宝采集详情读取专表。
- 淘宝仍读取 `platform_order_lines`。
- 其他通用采集仍读取 `dataset_collection_records`。

## 测试要求

需要更新或新增测试：

- 支付宝数据集 payload 生成 `storage = platform_alipay_bill_lines`。
- 支付宝同步任务不再写 `dataset_collection_records`。
- 支付宝同步任务写入 `platform_alipay_bill_lines`。
- token 刷新和账单未生成错误处理保持现有行为。
- `test_alipay_dataset_loader_contract` 不再 skip，验证 `platform_alipay_bill_lines` 和 `alipay_bill_lines` loader 已注册。
- recon loader 可按 `dataset_id/resource_key/biz_date/bill_type` 读取支付宝账单行。
- 相关前端授权文案不变。

## 验收标准

- 新授权支付宝商户生成的两个数据集均指向 `platform_alipay_bill_lines`。
- 每天 `10:30` 的 T-1 采集写入 `platform_alipay_bill_lines`。
- 支付宝采集路径不再写入 `dataset_collection_records`。
- 自动对账和重新对账通过 `platform_alipay_bill_lines` loader 读取支付宝账单行。
- 聚焦后端和 data-agent 测试通过。

