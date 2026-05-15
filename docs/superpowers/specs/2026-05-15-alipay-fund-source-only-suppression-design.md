# 支付宝资金对账 source_only 临时抑制设计

## 背景

当前部分资金对账任务使用“交易订单明细表”对“支付宝资金账单”。交易订单明细表本身无法区分支付宝支付、微信支付或其他支付渠道；只有在与支付宝资金账单对账后，出现在 `source_only` 的订单才可推定为“非支付宝支付订单”。

如果把这些 `source_only` 全部作为待处理差异，会让财务处理大量当前无法闭环的噪音。微信或其他支付资金账单接入前，需要一个临时补丁降低待处理差异数量。

## 目标

- 对所有使用“支付宝资金账单”的对账任务启用临时抑制。
- 只抑制 `source_only`。
- `target_only` 和 `matched_with_diff` 保持原样，继续作为待处理差异。
- 被抑制的 `source_only` 不创建 `execution_run_exceptions`。
- 钉钉汇总消息、责任人催办消息、待办、运行记录待处理数只展示待处理差异，不展示被抑制数量。
- 差异公开页面在左侧源数据行数旁展示说明，例如“其中 69 条为非支付宝支付订单”。
- 原始对账摘要仍保留 `source_only` 原始数量，便于审计和未来移除补丁后复查。

## 非目标

- 不尝试在交易订单明细表整理阶段提前识别支付渠道。
- 不隐藏 `target_only` 或 `matched_with_diff`。
- 不修改支付宝资金账单采集逻辑。
- 不引入后台配置页面。
- 不做微信支付接入。

## 触发条件

临时抑制规则在运行结果后处理阶段触发：

1. 当前对账任务任一侧数据集是“支付宝资金账单”。
2. 对账结果中存在 `source_only`。
3. 这些 `source_only` 来自非支付宝资金账单一侧。

第一版按数据集名称/语义信息识别“支付宝资金账单”，例如：

- `dataset_name` 包含 `支付宝资金账单`
- 或数据集来源标识为 `alipay_bill:signcustomer`

## 运行摘要口径

原始字段保持不变：

```json
{
  "source_only": 69,
  "target_only": 0,
  "matched_exact": 136,
  "matched_with_diff": 0,
  "total_records": 205
}
```

新增待处理口径和临时抑制 metadata：

```json
{
  "pending_source_only": 0,
  "pending_target_only": 0,
  "pending_matched_with_diff": 0,
  "pending_total": 0,
  "has_anomaly": false,
  "temporary_suppression": {
    "id": "alipay-fund-source-only-non-alipay-payment",
    "enabled": true,
    "suppressed_source_only": 69,
    "label": "非支付宝支付订单",
    "remove_when": "微信/其他支付资金账单接入后，重新纳入资金对账"
  }
}
```

`has_anomaly` 使用待处理口径，即 `pending_total > 0`。

## 异常落库

被抑制的 `source_only` 不写入 `execution_run_exceptions`。

原因：

- 用户不希望这些差异进入钉钉汇总、责任人催办或待办。
- 如果仍落库为异常任务，后续所有页面和通知都需要额外过滤，容易出现数字不一致。
- 原始 `source_only` 数量已经保留在 `execution_runs.recon_result_summary_json`，审计信息足够。

`target_only` 和 `matched_with_diff` 继续按现有逻辑创建 `execution_run_exceptions`。

## 钉钉消息

钉钉汇总消息只显示待处理差异，不显示被抑制 source_only 的说明。

如果一次运行只有 `source_only` 且全部被抑制：

```text
任务：泰斯支付宝对账
业务日期：2026-04-30
待处理差异：0 条
差异分布：
无待处理差异
查看全量差异
```

责任人催办消息只在存在待处理差异时发送。若 `pending_total = 0`，不发送责任人催办，不创建待办。

## 运行记录

运行记录面向用户展示待处理口径：

```text
匹配成功：136 条
待处理差异：0 条
```

不展示“原始差异”或“已忽略”指标。

内部仍通过 `recon_result_summary_json.source_only` 和 `temporary_suppression` 保留原始信息。

## 差异公开页面

源数据行数保持原始进入对账口径：

```text
交易订单明细表：数据 205 条（其中 69 条为非支付宝支付订单）
支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺：数据 136 条

匹配成功：136 条
待处理差异：0 条
```

页面列表只展示 `execution_run_exceptions` 中的待处理异常。被抑制的 `source_only` 因不落库，不在列表中展示。

## 防遗忘机制

规则 ID 固定为：

```text
alipay-fund-source-only-non-alipay-payment
```

代码常量、测试名、运行摘要 metadata 都必须使用这个 ID。未来接入微信或其他支付资金账单后，全局搜索该 ID 即可定位并移除补丁。

## 测试要求

- 当对账任务使用支付宝资金账单且结果只有 `source_only` 时：
  - `recon_result_summary_json.source_only` 保留原始数量。
  - `pending_total = 0`。
  - `temporary_suppression.suppressed_source_only` 等于原始 `source_only`。
  - 不创建 `execution_run_exceptions`。
- 当存在 `target_only` 或 `matched_with_diff` 时：
  - 这些差异继续创建异常任务。
  - `pending_total = target_only + matched_with_diff`。
- 钉钉汇总和责任人催办使用 `pending_total`。
- 差异公开页面显示“其中 X 条为非支付宝支付订单”，并显示“待处理差异”而不是原始差异总数。
