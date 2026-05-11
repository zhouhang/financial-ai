# 支付宝账单 raw 字段去重设计

## 背景

泰斯和蓝迪两个支付宝资金账单数据集的实际存储结构如下：

- `platform_alipay_bill_lines.payload` 外层保存标准化和系统字段，例如 `bill_date`、`bill_type`、`source_row_key`、`alipay_trade_no`、`merchant_order_no`、`business_order_no`、`trade_time`、`dataset_id`、`data_source_id`、`shop_connection_id`。
- `platform_alipay_bill_lines.payload.raw` 保存支付宝原始账单行的中文字段，例如 `账务流水号`、`业务流水号`、`商户订单号`、`商品名称`、`发生时间`、`对方账号`、`收入金额（+元）`、`支出金额（-元）`、`账户余额（元）`、`交易渠道`、`业务类型`、`备注`。

问题不在存储层重复。当前重复来自语义生成和展示层：系统把 `payload.raw` 同时展开成无前缀中文字段和 `raw.xxx` 字段，导致语义 profile 里同时存在 `账务流水号` 和 `raw.账务流水号`，财务人员看到两套含义相同的字段。

## 目标

- 保留完整原始账单数据，方便审计和排查。
- 语义数据集只暴露一套财务可读字段。
- 已发布或已生成过语义的数据集，在刷新语义或保存发布信息时自动清理历史 `raw.xxx` 字段。
- 店铺详情、发布抽屉、对账方案选择中不再出现重复的 `raw` / `raw.xxx` 字段。

## 非目标

- 不改变 `platform_alipay_bill_lines` 表结构。
- 不删除 `payload.raw` 原始数据。
- 不重新设计支付宝账单采集流程。
- 不引入人工字段映射页面。

## 设计

### 存储层

保持现有存储结构不变：

- 外层 `payload` 继续保存标准化字段和系统字段。
- `payload.raw` 继续保存支付宝原始账单行 JSON。

`raw` 的职责是原始证据和排查依据，不作为语义字段命名空间暴露给财务用户。

### 语义生成层

支付宝账单语义生成时采用以下规则：

- 跳过 `raw` 容器字段。
- 不生成 `raw.xxx` 字段。
- 从 `payload.raw` 展开的中文字段只生成无前缀字段，例如 `账务流水号`、`业务流水号`、`商户订单号`。
- 外层标准字段继续生成中文语义，例如：
  - `bill_date` -> `账单日期`
  - `bill_type` -> `账单类型`
  - `source_row_key` -> `账单行唯一键`
  - `alipay_trade_no` -> `支付宝交易号`
  - `merchant_order_no` -> `商户订单号`
  - `business_order_no` -> `业务订单号`
  - `trade_time` -> `交易时间`

语义 profile 中的 `fields`、`field_label_map`、`key_fields`、`low_confidence_fields` 都必须排除 `raw` 和 `raw.xxx`。

### 历史语义清理

发布或更新语义时，后端需要清理历史 profile 中的 `raw.xxx`：

- `field_label_map` 删除所有 key 为 `raw` 或以 `raw.` 开头的项。
- `fields` 删除 `raw_name` 为 `raw` 或以 `raw.` 开头的项。
- `key_fields` 删除 `raw` 或以 `raw.` 开头的项。
- `low_confidence_fields` 删除 `raw` 或以 `raw.` 开头的项。

刷新语义时生成的新 profile 也必须满足同样规则。

### 展示层

店铺详情、发布抽屉、数据预览、对账方案数据集选择只使用去重后的语义字段：

- 不展示 `raw`。
- 不展示 `raw.xxx`。
- 默认展示无前缀中文字段和外层标准字段中文名。

采集详情保留原始数据查看能力，但 `raw` 只作为折叠 JSON 或行详情展示，不作为默认表格列。

### 数据流

1. 支付宝账单采集写入 `platform_alipay_bill_lines.payload` 和 `payload.raw`。
2. 语义样本加载时可以读取 `payload.raw`，但输出候选字段时只保留无前缀中文字段。
3. 语义 profile 写入前执行 raw 字段清理。
4. 发布接口保存语义和发布状态前再次执行 raw 字段清理。
5. 前端渲染字段列表时继续兜底过滤 `raw` / `raw.xxx`。

### 错误处理

- 如果清理后字段为空，发布接口返回明确错误：`缺少可发布的语义字段`。
- 如果请求中包含不存在字段，继续返回现有校验错误，但 `raw` / `raw.xxx` 不应触发不存在字段错误，而是被过滤。
- 采集详情读取 `raw` 失败时不影响主表格展示。

## 测试计划

- 后端语义生成测试：支付宝账单样本包含 `payload.raw` 时，profile 不包含 `raw.xxx`，但包含无前缀中文字段。
- 后端发布测试：历史 profile 已有 `raw.xxx` 时，发布后返回的 dataset 不再包含 `raw.xxx`。
- 后端校验测试：请求 payload 中包含 `raw` / `raw.xxx` 时不会导致发布失败。
- 前端展示测试：店铺详情数据预览和发布字段列表不出现 `raw` / `raw.xxx`。
- 回归测试：支付宝资金账单仍能正常发布，`bill_date` 等外层标准字段仍可保留并发布。

## 验收标准

- 泰斯和蓝迪的支付宝资金账单刷新语义或保存发布信息后，语义字段中不再出现 `raw.xxx`。
- 财务人员在店铺详情和发布抽屉只看到一套中文业务字段。
- 对账方案选择中不出现 `raw` / `raw.xxx`。
- 采集详情仍能查看原始 `raw` JSON。
- 现有支付宝账单发布流程不再因 `raw` / `raw.xxx` 字段失败。
