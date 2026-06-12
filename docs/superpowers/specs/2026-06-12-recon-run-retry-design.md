# 失败运行记录原地重试设计

> 日期:2026-06-12  
> 状态:设计已确认,待写实现计划

## 1. 背景

对账运行记录现在有两类用户动作:

- 成功运行记录里的差异,通过"差异消化"复核并原地更新差异数。
- 失败运行记录需要"重试",重新执行同一个运行计划和业务日期。

历史代码里还有两套"重跑"遗留:

- `recon_auto_run_rerun`:旧 `recon_auto_runs` 模型,会新建旧模型 run/job,不适合当前 `execution_runs` 主界面。
- `POST /recon/runs/rerun`:新模型入口,已能读取原 `execution_run` 并入队 `trigger_mode='rerun'`,但旧语义偏"重新对账验证",且默认会走执行图创建新运行记录。

本设计只改新模型路径,不复活旧 `recon_auto_runs` 路径。

## 2. 目标

1. 只有终态失败的 `execution_runs` 展示"重试"按钮。
2. 成功运行记录只展示"差异消化"按钮。
3. 运行中、排队中、等待数据、其他非终态运行记录不展示"重试"和"差异消化"。
4. 重试不新建运行记录,而是原失败运行记录原地进入运行中,最终被最新执行结果覆盖。
5. 重试成功落新异常前,清理原运行记录下的旧异常,避免同一个 run 的异常重复污染。
6. 覆盖原失败信息前,把原失败状态、阶段、原因和触发人写入 `run_context_json.retry_history` 作为审计。

## 3. 非目标

- 不做自动重试策略、退避、次数上限。
- 不重构对账执行图。
- 不修改成功 run 的差异消化语义。
- 不支持对旧 `recon_auto_runs` 运行记录做本功能。

## 4. 状态语义

当前 `execution_runs` 工具层允许的 `execution_status` 为:

- `running`
- `success`
- `failed`

因此本期失败终态严格定义为:

- `execution_status == 'failed'`

成功终态定义为:

- `execution_status == 'success'`

非终态定义为:

- `execution_status == 'running'`
- 队列中或等待数据中的任务,即使 UI 能从队列上下文识别,也不展示"重试"或"差异消化"。

未来扩展 `execution_status` 取值时,必须集中扩展 helper 和测试,不要在组件或 API 中散落字符串判断。

## 5. 后端设计

### 5.1 API 入口

复用现有:

```text
POST /api/recon/runs/rerun
```

请求体仍使用:

```json
{
  "original_run_id": "execution-run-id",
  "exception_id": "",
  "reason": "用户填写或默认原因"
}
```

但语义调整为:

```text
retry failed execution run in place
```

接口必须:

1. 鉴权并读取原 `execution_run`。
2. 若原 run 不存在,返回 404。
3. 若 `execution_status != 'failed'`,返回 400,错误说明"只有执行失败的运行记录可以重试"。
4. 若缺少 `plan_code` 或业务日期,返回 400,沿用当前 `prepare_execution_run_rerun` 的错误信息。
5. 查询是否已存在同一 run 的活跃重试队列:
   - `trigger_mode='rerun'`
   - `run_context.target_run_id = original_run_id`
   - 队列状态为 `queued` 或 `running`
6. 若已存在,返回 409,错误说明"该运行记录正在重试,请稍后"。
7. 入队 `recon_execution_queue`,不直接同步执行。

### 5.2 队列上下文

入队时 `run_context` 必须包含:

```json
{
  "target_run_id": "<original_run_id>",
  "execution_run_id": "<original_run_id>",
  "retry_from_failed_run_id": "<original_run_id>",
  "retry_reason": "<reason>",
  "trigger_type": "rerun"
}
```

同时保留原 `run_context_json` 中仍有用的业务上下文,例如 `biz_date`、`run_plan_code`、`schedule_slot` 等。

关键点:

- `execution_run_id` 是执行图复用原 run 的信号。
- `target_run_id` 是队列幂等去重的信号,与差异消化的去重模式一致。
- `trigger_type='rerun'` 用于审计和 badge 展示。

### 5.3 原地更新

执行图已有 `_persist_execution_run()`:

- 当 `run_context.execution_run_id` 存在时,它会更新该 run。
- 当不存在时,它才会创建新 run。

重试路径必须保证 `execution_run_id` 始终传入执行图,从而不创建新运行记录。

重试入队成功后,API 立即追加 `retry_history` 并把原 run 更新为:

- `execution_status='running'`
- `failed_stage=''`
- `failed_reason=''`
- `started_at=now`
- `finished_at=null`

最终执行完成后,原 run 被本次结果覆盖:

- `execution_status`
- `failed_stage`
- `failed_reason`
- `run_context_json`
- `source_snapshot_json`
- `subtasks_json`
- `proc_result_json`
- `recon_result_summary_json`
- `artifacts_json`
- `anomaly_count`
- `finished_at`

### 5.4 retry_history 审计

在覆盖原失败信息前,追加一条审计记录到 `run_context_json.retry_history`:

```json
{
  "attempted_at": "2026-06-12T10:30:00+08:00",
  "reason": "用户触发重试",
  "trigger_user": {
    "user_id": "...",
    "username": "...",
    "role": "..."
  },
  "previous_status": "failed",
  "previous_failed_stage": "recon",
  "previous_failed_reason": "执行失败原因",
  "previous_finished_at": "..."
}
```

要求:

- 只追加,不覆盖历史。
- 最多保留最近 20 条即可,避免 JSON 无限制增长。
- UI 本期不必须展示 `retry_history`,但数据必须保留。

### 5.5 旧异常清理

重试不新建 run,所以必须处理旧异常。

规则:

1. 重试开始时不立即清理旧异常,避免本次执行失败后看板失去原失败上下文。
2. 本次核心对账执行成功后、进入"准备写入新异常"阶段前,清理该 run 下原有异常。
3. 再写入本次新异常;如果本次成功且无异常,清理后保持该 run 无 open 异常。
4. 如果本次重试失败,旧异常保持不变,run 失败原因更新为本次失败原因,`retry_history` 中仍保留上一次失败审计。

实现规定:

- 在创建异常任务节点前增加 run 级清理步骤。
- 清理范围为 `execution_run_exceptions.run_id = original_run_id`。
- 采用物理删除,因为这些异常属于被覆盖运行结果的旧派生数据;审计重点在 `retry_history` 和最终 run 状态。

## 6. 前端设计

### 6.1 按钮显示

运行记录列表和异常看板使用同一 helper:

```text
canRetryRun(run) = run.executionStatus == 'failed'
canDigestRun(run) = run.executionStatus == 'success'
```

展示规则:

- `failed`:显示"重试"。
- `success`:显示"差异消化"。
- 其他状态:不显示两个按钮。

异常看板顶部当前固定展示"差异消化",需要改为按状态渲染。

### 6.2 点击重试

点击"重试":

1. 调 `POST /api/recon/runs/rerun`。
2. 按钮进入 "重试中..."。
3. 返回 queued 后刷新运行记录列表和当前 run。
4. 原 run 行刷新后显示后端返回的最新状态。
5. 提示文案:

```text
已发起重试,当前运行记录将更新为最新执行结果。
```

不跳转到新 run,因为不会创建新 run。

### 6.3 错误展示

- 400 非失败状态:展示"只有执行失败的运行记录可以重试"。
- 409 已在重试:展示"该运行记录正在重试,请稍后"。
- 404 不存在:刷新列表并提示运行记录不存在。
- 其他错误:展示后端 message。

## 7. 与差异消化的关系

- 差异消化仍只用于成功运行记录。
- 差异消化仍走 `trigger_mode='resolve'` 和 `run_context.target_run_id`。
- 重试走 `trigger_mode='rerun'` 和同一个 `target_run_id` 去重模式。
- 两者不会在同一个 run 上同时展示,降低误操作。

## 8. 测试要求

### 8.1 finance-mcp / data-agent

- `prepare_execution_run_rerun` 拒绝非 failed run。
- failed run 可构造 `target_run_id` + `execution_run_id` 上下文。
- `/recon/runs/rerun` 对活跃 `rerun + target_run_id` 返回 409。
- worker 执行 rerun 时不创建新 run,而是更新原 run。
- retry 开始会追加 `retry_history`,最多保留 20 条。
- retry 成功写新异常前清理旧异常。
- retry 失败不清理旧异常。

### 8.2 finance-web

- failed run 显示"重试",不显示"差异消化"。
- success run 显示"差异消化",不显示"重试"。
- running / waiting_data / queued / scheduled / unknown 不显示两个按钮。
- 点击重试调用 `/api/recon/runs/rerun`,body 包含 `original_run_id`。
- queued 后刷新同一个 run,不尝试聚焦新 run。

### 8.3 端到端验收

构造或选择一条失败运行记录:

1. 页面只显示"重试"。
2. 点击后原 run 进入运行中。
3. 成功后同一 run id 状态变为 success 或 failed。
4. 不新增 `execution_runs` 记录。
5. 如果成功且产生异常,旧异常已被清理,只剩本次异常。
6. `run_context_json.retry_history` 有本次重试审计。

## 9. 实施影响面

- `finance-agents/data-agent/graphs/recon/auto_run_api.py`
  - 收紧 `/runs/rerun` 状态校验。
  - 增加 rerun 活跃队列去重。
  - 入队上下文补 `target_run_id`、`execution_run_id`、`retry_from_failed_run_id`。

- `finance-agents/data-agent/graphs/recon/auto_run_service.py`
  - `prepare_execution_run_rerun` 增加 failed-only 校验和 retry context。

- `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
  - 原地重试时更新同一 run。
  - 追加 `retry_history`。
  - 成功写新异常前清理旧异常。

- `finance-mcp/tools/execution_runs.py` / `auth/db.py`
  - 如现有工具缺少按 run 清理异常能力,补最小工具。
  - 如 `started_at`/`finished_at` 更新能力不足,补最小 update 字段。

- `finance-web/src/components/ReconWorkspace.tsx`
  - 运行记录动作和异常看板动作按状态切换。
  - 新增重试调用与轮询/刷新。

- `finance-web/src/components/recon/ReconAutoRunsPanel.tsx`
  - 当前未被主页面引用,本期不纳入主路径;后续重新接入时必须复用同一按钮 helper。
