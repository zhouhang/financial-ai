# 爆量异常抽样处理设计

日期: 2026-06-03

## 背景

自动对账在异常数量很大时会把所有差异逐条创建为 `execution_run_exceptions`，再让后续催办节点处理这些异常。最近一次订单对账中，旧匹配键导致单个运行出现 35665 条异常，系统花了很长时间逐条落库、逐条更新催办状态。

当前 `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py` 已经计算 `explosion_threshold` 和 `explosion` 标记，但 `create_exception_tasks_node` 仍遍历全量 `anomaly_items` 并逐条调用 `execution_run_exception_create`。这意味着“爆量”只影响通知文案，不保护异常任务落库和催办链路。

## 目标

1. 超过阈值时不再为全量异常逐条创建 `execution_run_exceptions`。
2. 爆量模式下只创建按异常类型和责任人分层抽样出的样本异常，默认最多 200 条。
3. `execution_runs.anomaly_count` 和 `recon_result_summary_json` 继续保留全量异常数和全量类型分布。
4. 样本异常继续走现有催办流程，不新增特殊催办机制。
5. 页面和运行记录能明确表达“全量差异 X 条，当前抽样展示 Y 条”，避免把样本数误认为全量。
6. 第一版不新增数据库表、不新增 MCP 批量创建接口、不实现全量差异导出。

## 非目标

1. 不改变对账计算逻辑。
2. 不改变差异类型、差异摘要、责任人解析规则。
3. 不新增全量差异 Excel 导出或异步归档能力。
4. 不新增单独的爆量催办流程。
5. 不重构 `finance-mcp/auth/db.py` 的异常 CRUD。
6. 不修复历史已生成的爆量异常记录。

## 推荐方案

采用“执行节点限流采样”方案。采样逻辑放在 `auto_scheme_run/nodes.py` 的 `create_exception_tasks_node` 内，位于对账结果产生之后、调用 `execution_run_exception_create` 之前。

流程保持为:

1. 对账执行产生全量 `ctx["anomaly_items"]`。
2. `create_exception_tasks_node` 读取全量异常数量和运行计划通知策略。
3. 如果未超过阈值，沿用现有逻辑，全部创建异常。
4. 如果超过阈值，只对分层抽样出的异常创建 `execution_run_exceptions`。
5. `maybe_auto_notify_node` 继续读取已创建的异常并走现有催办逻辑。

这样能直接切断爆量场景下的逐条落库和逐条催办状态更新，同时保持现有 MCP 接口和催办代码不变。

## 配置

配置优先读取运行计划的 `plan_meta_json.notify_policy`。为了兼容现有代码和历史计划，也继续读取 `plan_meta_json.reminder_policy_json` / `plan_meta_json.reminder_policy`。

```json
{
  "notify_policy": {
    "explosion_threshold": 1000,
    "sample_exception_limit": 200
  }
}
```

默认值:

- `explosion_threshold = 1000`
- `sample_exception_limit = 200`

兼容规则:

- 旧位置 `reminder_policy_json` / `reminder_policy` 继续可用。
- 旧字段 `explosion_threshold` 继续可用。
- 新字段 `sample_exception_limit` 优先于旧字段 `explosion_sample_limit`。
- 如果 `sample_exception_limit` 缺失，再读取 `explosion_sample_limit`。
- 如果阈值非法、小于 1 或无法转为整数，回退默认值。

## 采样规则

爆量判断:

```python
total_anomaly_count = len(anomalies)
explosion = total_anomaly_count > explosion_threshold
```

分层 key:

```text
(anomaly_type, owner_identifier)
```

其中:

- `anomaly_type` 来自异常项的 `anomaly_type`，缺失时使用 `unknown`。
- `owner_identifier` 使用异常创建阶段现有的责任人解析结果。当前新执行流主要使用运行计划默认责任人；如果没有逐异常责任人，则所有异常会自然落到默认责任人分层，采样仍至少按 `anomaly_type` 覆盖。

抽样算法:

1. 按 `(anomaly_type, owner_identifier)` 分组。
2. 每个分层优先取 1 条，尽量覆盖所有异常类型和责任人。
3. 如果分层数超过 `sample_exception_limit`，按原始出现顺序取前 `sample_exception_limit` 个分层的第一条。
4. 如果还有剩余额度，按各分层原始数量占比分配额外样本。
5. 每个分层内部保持原始顺序取样，便于排查时和对账结果顺序对应。
6. 最终样本数量不超过 `sample_exception_limit`。

采样失败时回退为原始顺序前 `sample_exception_limit` 条，并在采样元数据中记录 fallback。

## 运行上下文

爆量模式下写入:

```json
{
  "exception_total_count": 35665,
  "exception_created_count": 200,
  "exception_created_sample_count": 200,
  "exception_creation_limited": true,
  "exception_sampling": {
    "enabled": true,
    "reason": "explosion_threshold_exceeded",
    "threshold": 1000,
    "sample_limit": 200,
    "total_count": 35665,
    "sample_count": 200,
    "created_count": 200,
    "create_failed_count": 0,
    "strategy": "stratified_by_anomaly_type_owner",
    "fallback_used": false
  }
}
```

非爆量模式下:

```json
{
  "exception_creation_limited": false,
  "exception_total_count": 110,
  "exception_created_sample_count": 110
}
```

`ctx["anomaly_items"]` 不截断，避免影响后续全量统计口径。只截断传入异常创建循环的 `sampled_anomalies`。

## 持久化表示

运行记录继续使用现有字段:

- `execution_runs.anomaly_count`: 全量异常数量。
- `execution_runs.recon_result_summary_json`: 全量对账汇总，例如 `source_only`、`target_only`、`matched_exact`、`matched_with_diff`。
- `execution_run_exceptions`: 样本异常，爆量模式下最多 `sample_exception_limit` 条。

采样元数据写入:

```text
execution_runs.artifacts_json.runtime_summary.exception_sampling
```

示例:

```json
{
  "enabled": true,
  "reason": "explosion_threshold_exceeded",
  "threshold": 1000,
  "sample_limit": 200,
  "total_count": 35665,
  "sample_count": 200,
  "created_count": 200,
  "strategy": "stratified_by_anomaly_type_owner"
}
```

如果运行过程中已经有 `runtime_summary`，只合并 `exception_sampling`，不覆盖已有的采集、整理、对账耗时和汇总通知结果。

## 页面/API 表示

第一版不新增 API。现有内部异常页和公开异常页继续通过 run bundle 读取:

- run 的 `anomaly_count`
- run 的 `recon_result_summary_json`
- run 的 `artifacts_json.runtime_summary.exception_sampling`
- `execution_run_exceptions` 样本列表

前端展示规则:

1. 如果没有 `exception_sampling.enabled=true`，保持现有差异列表展示。
2. 如果存在 `exception_sampling.enabled=true`，在差异列表顶部显示:

```text
全量差异 35665 条，当前抽样展示 200 条
```

3. 列表分页、详情、处理状态、催办状态仍基于样本异常。
4. 不提供“查看全量明细”入口。

## 催办行为

不新增爆量催办分支。

爆量模式下只创建样本异常，因此 `maybe_auto_notify_node` 自然只处理样本异常。责任人收到的仍是现有催办内容和流程，只是催办对象数量从全量异常变为样本异常。

这意味着:

- 全量异常不会逐条创建待办。
- 样本异常仍可催办、处理、关闭、重跑验证。
- run 上的全量异常数仍用于判断本次对账质量。

## 错误处理

1. 阈值配置非法时使用默认值，不中断运行。
2. 采样逻辑异常时退回前 N 条样本，不中断运行。
3. 单条样本异常创建失败时继续下一条，沿用现有容错。
4. `exception_created_count` 记录实际创建成功数量。
5. `exception_sampling.create_failed_count` 记录样本创建失败数量。
6. 如果运行没有异常或缺少 `run_id` / `scheme_code`，保持现有早退行为。

## 测试策略

### 单元测试

覆盖 `auto_scheme_run/nodes.py` 中的策略解析和采样函数:

1. `total <= 1000` 时不采样，全部异常进入创建流程。
2. `total > 1000` 时最多创建 200 条。
3. 样本覆盖多个 `anomaly_type`。
4. 样本覆盖多个 `owner_identifier`。
5. 分层数超过样本上限时，不超过上限并保持确定性顺序。
6. `sample_exception_limit` 优先于 `explosion_sample_limit`。
7. 非法阈值回退默认 `1000/200`。
8. 采样异常时 fallback 到前 200 条。

### 节点测试

用 monkeypatch 替换 MCP 调用，直接执行 `create_exception_tasks_node`:

1. 35665 条模拟异常时，`execution_run_exception_create` 调用不超过 200 次。
2. `exception_total_count` 仍为 35665。
3. `exception_creation_limited` 为 `true`。
4. `created_exceptions` 只包含样本异常。
5. `auto_notify_policy.explosion` 为 `true`，并记录采样元数据。

### 前端测试

1. 有 `runtime_summary.exception_sampling.enabled=true` 时显示“全量差异 X 条，当前抽样展示 Y 条”。
2. 没有采样元数据时保持旧展示。
3. 异常列表仍只渲染 API 返回的异常样本。

## 验收标准

1. 类似博宽旧规则 35665 条差异的场景，不再创建 35665 条 `execution_run_exceptions`。
2. 爆量 run 的 `execution_run_exceptions` 不超过 200 条。
3. run 的 `anomaly_count` 仍显示全量异常数。
4. `recon_result_summary_json` 仍显示全量类型分布。
5. 页面明确提示当前为抽样展示。
6. 样本异常仍走现有催办流程。
7. 没有配置 `notify_policy` 的运行计划使用默认 `1000/200`。
8. 非爆量小规模异常保持现有行为。

## 后续可选优化

1. 新增 MCP 批量创建接口，把最多 200 条样本异常一次性 upsert。
2. 新增全量差异异步归档或导出能力。
3. 新增爆量摘要表，保存更完整的责任人、类型和字段分布。
4. 在运行计划 UI 中暴露 `explosion_threshold` 和 `sample_exception_limit` 配置。
