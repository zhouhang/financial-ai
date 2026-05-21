# 异常看板真实运行概览设计

日期: 2026-05-21

## 背景

“泰斯支付宝对账”最近两天在异常看板里显示 1 秒完成。排查后确认真实执行没有这么短:

- 2026-05-21 调度运行在 `recon_execution_queue` 中耗时约 73.854 秒。
- 2026-05-21 手动重跑在 `recon_execution_queue` 中耗时约 91.614 秒。
- 汇总消息已通过 DWS 发送给汇总接收人张小毅，但页面没有展示这类运行事实。

当前异常看板主区展示的是 `execution_runs.started_at/finished_at`。这两个字段写入发生在持久化运行记录时，不能代表从采集、整理、对账到通知的真实全过程。用户需要在异常看板直接看到本次运行各步骤是否真的走完、每一步处理了多少数据、耗时多少，以及汇总消息是否成功推送。

## 目标

- 异常看板主区不再展示“所属方案、运行状态、开始时间、结束时间”。
- 顶部第一行改成真实运行概览:
  - `对账数据日期`
  - 左侧业务数据采集行数和耗时
  - 右侧业务数据采集行数和耗时
  - 整理后左表行数和耗时
  - 整理后右表行数和耗时
  - 对账耗时
- 所有数据源/步骤名称优先使用业务名，避免在页面露出技术表名。
- 异常数从主区卡片移到下方差异列表顶部。
- 保留运行状态、起止时间、所属方案、失败原因等排查信息，但下沉到默认折叠的“运行详情”区域。
- 运行详情中展示汇总接收人和汇总消息推送结果。
- 内部异常看板弹窗与公开异常页面使用同一套运行概览口径。

## 非目标

- 不改变对账规则、整理规则、差异生成逻辑。
- 不改变异常责任人催办逻辑。
- 不用日志作为页面数据源；日志只用于排查，不作为前端展示依赖。
- 不重新定义差异数口径。
- 不要求历史运行补齐完整耗时。历史数据缺字段时显示 `--`。

## 页面结构

### 顶部标题

保留任务名和刷新/重新验证等现有操作。任务名旁可保留成功/失败标签，但不再把“运行状态”作为主指标卡展示。

### 第一行运行概览

主区用一行或响应式换行的紧凑指标条展示:

```text
对账数据日期 2026-05-20
交易订单明细表采集 205 行 耗时 38.42 秒
支付宝资金账单采集 136 行 耗时 31.06 秒
整理后交易订单明细表 205 行 耗时 4.18 秒
整理后支付宝资金账单 136 行 耗时 3.77 秒
对账耗时 2.24 秒
```

响应式规则:

- 桌面端优先一行扫描，空间不足时自然换行。
- 移动端按步骤顺序纵向排列。
- 每个指标固定包含“名称 + 行数 + 耗时”，缺少行数或耗时时只把该部分显示为 `--`。

业务名优先级:

1. `business_name`
2. `dataset_name`
3. `display_name`
4. `name`
5. 非技术化的 `dataset_code`
6. 兜底为“左侧数据源 / 右侧数据源”

`resource_key`、`table_name`、`left_recon_ready`、`right_recon_ready` 只允许作为内部匹配依据，不直接展示。

### 差异列表顶部

差异列表 section 顶部新增标题行:

```text
差异列表  待处理差异 69 条
```

筛选、搜索、分页和异常详情保持现有行为。内部弹窗当前的“异常摘要”列表也在列表顶部显示异常数，不再在上方主区显示“异常数”卡片。

### 运行详情

主区下方新增默认折叠的“运行详情”。用户展开后看到:

- 所属方案
- 运行状态
- 开始时间
- 结束时间
- 队列开始时间
- 队列结束时间
- 失败阶段
- 失败原因
- 汇总接收人
- 汇总消息推送状态
- 汇总消息 ID 或失败原因

显示原则:

- `execution_runs.started_at/finished_at` 标注为“记录写入时间”，不再暗示为真实执行耗时。
- 如果能关联到 `recon_execution_queue.started_at/finished_at`，显示为“队列运行时间”。
- 汇总推送状态来自运行记录持久化的通知结果，不从本地 DWS 日志读取。

## 后端运行摘要

前端不应拼装真实阶段耗时。后端需要在公开 bundle 和内部运行列表都返回统一的运行摘要对象，建议放在:

```text
run.raw.artifacts_json.runtime_summary
```

结构:

```json
{
  "biz_date": "2026-05-20",
  "queue": {
    "started_at": "2026-05-21T04:00:01+08:00",
    "finished_at": "2026-05-21T04:01:15+08:00",
    "duration_seconds": 73.854
  },
  "collections": [
    {
      "side": "left",
      "business_name": "交易订单明细表",
      "row_count": 205,
      "duration_seconds": 38.42
    },
    {
      "side": "right",
      "business_name": "支付宝资金账单",
      "row_count": 136,
      "duration_seconds": 31.06
    }
  ],
  "preparation": [
    {
      "side": "left",
      "business_name": "交易订单明细表",
      "row_count": 205,
      "duration_seconds": 4.18
    },
    {
      "side": "right",
      "business_name": "支付宝资金账单",
      "row_count": 136,
      "duration_seconds": 3.77
    }
  ],
  "reconciliation": {
    "duration_seconds": 2.24
  },
  "summary_notification": {
    "status": "sent",
    "recipient_name": "张小毅",
    "recipient_identifier": "072007534524160438",
    "message_id": "msg_20260521_001",
    "error": ""
  }
}
```

### 字段来源

- `biz_date`: 优先 `run_context_json.biz_date`，再退到 `execution_runs.biz_date/business_date/data_date`。
- 采集行数: 优先本次采集 job metrics 的 `row_count` 或 collection summary 的 `record_count`。
- 采集耗时: `source_snapshot_json.collections[].job.metrics.collection_timing.total_seconds`。
- 整理后左/右行数: 优先持久化的 proc 输出统计；缺失时可使用对账汇总推导:
  - 左侧 = `matched_exact + matched_with_diff + source_only`
  - 右侧 = `matched_exact + matched_with_diff + target_only`
- 整理耗时: 需要在自动运行图中补采 `proc` 阶段耗时并持久化。
- 对账耗时: 需要在自动运行图中补采 `recon` 阶段耗时并持久化。
- 汇总推送结果: `auto_notify_result.summary_notification` 需要在通知节点结束后写回 `execution_runs.artifacts_json.runtime_summary.summary_notification`。
- 队列耗时: 可通过运行上下文关联 `recon_execution_queue` 记录，或在创建/消费队列时把 queue job id 放入 `run_context_json.queue_job_id` 后查询。

## 数据流

1. 自动对账执行时记录阶段级 runtime metrics。
2. 持久化 `execution_runs` 时写入 `artifacts_json.runtime_summary`。
3. 自动汇总通知结束后，再轻量更新一次运行记录，把 `summary_notification` 合并进 `runtime_summary`。
4. `get_public_execution_run_exception_bundle()` 返回现有 run/scheme/plan/exceptions，同时包含 `artifacts_json.runtime_summary`。
5. 前端将 bundle 映射成 `RunRuntimeSummaryViewModel`，内部异常看板和公开异常页共用格式化逻辑。
6. 页面渲染顶部运行概览、差异列表 badge 和折叠运行详情。

## 兼容策略

- 历史运行没有 `runtime_summary` 时，页面仍正常展示异常列表。
- 缺采集耗时时显示 `耗时 --`，不回退到 `started_at/finished_at`。
- 缺整理耗时时显示 `耗时 --`，行数可用对账汇总推导。
- 缺汇总通知结果时显示“汇总推送状态 --”。
- 如果运行失败，顶部只展示已完成步骤；失败原因在“运行详情”中展示。
- 如果业务名缺失，展示“左侧数据源 / 右侧数据源”，不展示技术表名。

## 测试要求

### 前端组件测试

- 异常看板主区不再出现“所属方案、运行状态、开始时间、结束时间”四张卡片。
- `数据日期` 文案改为 `对账数据日期`。
- 采集、整理、对账指标按业务名、行数、耗时展示。
- 异常数显示在差异列表顶部。
- 运行详情默认折叠，展开后能看到方案、状态、起止时间、汇总接收人和推送状态。
- 缺少 `runtime_summary` 时不崩溃，关键字段显示 `--`，异常列表仍可用。

### 后端/服务测试

- 自动运行持久化时写入 `artifacts_json.runtime_summary`。
- 通知节点结束后写回 `summary_notification`。
- 公开 bundle 返回 `runtime_summary`。
- 采集耗时优先读取 `collection_timing.total_seconds`。
- 整理/对账耗时缺失时不伪造数值。

### 手工验收

使用“泰斯支付宝对账”最近两次运行检查:

- 看板不再显示 1 秒完成。
- 顶部能看到对账数据日期、两侧采集行数和耗时、整理后行数、对账耗时。
- 差异数位于差异列表顶部。
- 展开运行详情能看到汇总接收人张小毅，以及汇总消息发送成功状态。
