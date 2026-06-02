# 浏览器采集作业卡死 — 兜底与自愈设计 (Tier 1)

- 日期: 2026-06-02
- 状态: 待实现 (spec 已评审)
- 范围: Tier 1（进 v1）。Tier 2（completion 完整原子化）明确推迟。

## 背景

2026-06-01 排查 `tb0131100248 资金对账` 5-31 运行记录"一直运行中",根因是迁移 037 未执行
导致 `browser_sync_job_complete` 在写 `browser_capture_files` 时崩溃,作业被孤立在 `running`,
下游对账运行记录无限期卡"运行中"。排查中确认了一组健壮性缺陷(已逐行核对代码):

1. **completion 非原子** — `_handle_browser_sync_job_complete`(data_sources.py)先写 records(自带 commit),
   再写 capture_files,最后翻转状态;中途崩溃即孤立作业在 `running`。
2. **dispatcher 谎报成功** — `dispatcher_loop.py:105-123` 调 `mark_browser_job_success` 后**无条件**打
   "succeeded",不检查回写结果,agent 永不重试/失败。
3. **reaper 与会死的进程同生共死** — `requeue/fail_failed/fail_expired` 全跑在 browser-agent 的
   `_waiting_reconciler`(service.py:44);agent 死 → 连 90min deadline 兜底都不触发。
4. **无心跳回收** — `agents.last_heartbeat_at` 只被 `browser_alerts.py` 用于告警,没有任何地方
   据此回收孤立的 `running` 作业。唯一会回收 running 的 `fail_running_browser_sync_jobs_for_agent`
   (db.py:6514)仅在 agent 重启经 `startup_cleanup` 触发。

事故同时命中 #1/#2(回写崩溃孤立作业)和 #3/#4(agent 进程随后死亡,兜底也死),故卡 ~18 小时。

## 目标与非目标

**目标**:让"采集作业卡 running"既能从源头自愈,又有一张跑在独立进程里的兜底网,保证任何成因
都不会让对账运行记录静默卡死——最差也是"可见失败 + 告警 + 可重跑"。

**非目标(Tier 2,本次不做)**:
- completion 的完整原子化(records + capture_files + 状态翻转收进单事务/可重放单元)。
- "作业 running 超过 X 分钟强制回收"的时长兜底(心跳 + runner `timeout_ms` 已覆盖已知路径)。
- 自动重采重试 #4 回收的作业(本次明确:标失败 + 告警,不自动重试)。

## 关键决策(已与 owner 确认)

- 范围:Tier 1 进 v1;Tier 2 推迟。
- #4 孤立作业处置:**标失败 + 告警,不自动重试**,复用现有 AGENT_INTERRUPTED 语义。
- reaper 归属:**单一归属 finance-cron**,从 browser-agent 移走 `_waiting_reconciler`。
- #4 落地结构:**方案 A** — finance-mcp 出一个服务端工具,cron 只负责定时触发。
- 心跳过期阈值 `stale_after_seconds` 默认 **180s**(≫30s 心跳间隔以容忍网络抖动),与
  `browser_alerts` 的离线阈值对齐成同一"死亡"定义。
- **180s 是 agent 心跳静默时长,不是作业运行时长**;健康 agent 上的长采集绝不被回收。

## 架构与职责(改动后)

| 进程 | 职责 | 变化 |
|---|---|---|
| browser-agent | 只管采集:claim → run → report + 心跳 | 移除 `_waiting_reconciler`;dispatcher 检查回写结果 |
| finance-mcp | 真值源 + 所有 reaper 的 SQL 原语(幂等) | 新增 1 个心跳回收工具;capture_files 写入幂等 |
| finance-cron | 唯一 reaper 驱动者(APScheduler interval → MCP 工具) | 新增周期任务:队列三件套 + 心跳回收 |

**两道防线**:
- 第一道(源头自愈)= #2 + #1薄片:回写崩 → 标可重试失败 → 重采 → 幂等重放 → 成功。秒级,不依赖 cron。
- 第二道(独立兜底)= #3 + #4:agent 死 → cron 按心跳过期回收 running 作业 → 级联失败对账记录 + 告警。

**不变量**:reaper 只跑在 finance-cron;browser-agent 不做任何看门动作;finance-mcp 只提供幂等 SQL 原语,不自己定时。

## 组件级改动

### #2 dispatcher 检查回写结果
- `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py:105-123`:接收
  `mark_browser_job_success` 返回值并判定 `success`(并捕获异常)。失败 → 调
  `mark_browser_job_failed(retryable=True, fail_reason="COMPLETE_PERSIST_FAILED")`,作业回 `pending` 等重采;成功才打 success。
- `tally_client.py:145`:确认把服务端 `job_complete` 工具返回的 `{success, ...}` 透传上来,不吞错。

### #1 薄片 — capture_files 写入幂等
- 新迁移 `038_browser_capture_files_idempotent.sql`:
  `CREATE UNIQUE INDEX IF NOT EXISTS … ON public.browser_capture_files (sync_job_id, storage_path)`(幂等)。
- `finance-mcp/auth/db.py` `insert_browser_capture_files`:INSERT 加 `ON CONFLICT (sync_job_id, storage_path) DO UPDATE`(刷新 checksum/size/storage_* 等元数据)。

### #3 reaper 迁移到 finance-cron
- 删:`finance-agents/browser-agent/service.py:44-52` 的 `_waiting_reconciler` 及其 task 装配;
  `tally_client.py:151-158` 的 `*_waiting` 包装不再被 service 调用(可移除或留作内部 API)。
- 加:`finance-cron/mcp_client.py` 三个薄包装,调已存在工具 `queue_fail_failed` / `queue_requeue_ready` /
  `queue_fail_expired`(`finance-mcp/tools/recon_auto_runs.py:1021/1029/1039`)。
- 加:`finance-cron/scheduler_service.py` 注册**一个统一的 reaper interval job**(默认 30s),
  每轮按序跑四步:`reap_stale_agents → queue_fail_failed → queue_requeue_ready → queue_fail_expired`
  (前三件套与原 `_waiting_reconciler` 同序,reap_stale 见 #4),`max_instances=1` + `coalesce=true`。
  单一 job 保证当轮回收的失败作业当轮即被级联。

### #4 心跳过期回收(方案 A)
- finance-mcp 新增 `auth_db.reap_stale_agent_running_jobs(stale_after_seconds)`:一条 SQL,把
  `agents.last_heartbeat_at` 过期/NULL 的 agent 名下、`source_kind='browser_playbook'` 且 `job_status='running'`
  的 sync_job 标 `failed` + `browser_fail_reason='AGENT_HEARTBEAT_LOST'`(由现有 `fail_running_browser_sync_jobs_for_agent`
  db.py:6514 泛化:从"按 agent_id"改为"按心跳过期"筛选)。返回 `failed_count` / `sync_job_ids`。
- finance-mcp 新增 MCP 工具 `browser_sync_job_reap_stale_agents`(scheduler-token 鉴权,与 `startup_cleanup` 同款)。
- 由 #3 的统一 reaper interval job 在每轮第一步调它(不另起独立 job);阈值 `stale_after_seconds`
  默认 180s,可配置(env/cron config),与 `browser_alerts` 离线阈值对齐。
- 级联与告警:被标 failed 后,同轮的 `queue_fail_failed` 级联失败对账运行记录;告警复用现有
  `data-agent/services/browser_alerts.py`(已按心跳过期发离线告警),不新增告警通道。

## 数据流

**A — 回写崩溃,agent 还活着(自愈)**
```
runner 成功 → mark_browser_job_success → 服务端写 capture_files 失败 → 工具返回 {success:false}
→ dispatcher 检查到失败(#2) → mark_browser_job_failed(retryable=true) → 作业回 pending
→ agent 重新 claim → 重采(records 幂等 upsert) → 再次 complete(capture_files ON CONFLICT 幂等) → success
→ queue_requeue_ready → 对账正常跑完
```

**B — agent 整个死掉(兜底)**
```
agent 进程没了 → 心跳停 → (180s 后) cron 调 reap_stale_agents
→ 该 agent 名下 running 作业标 failed(AGENT_HEARTBEAT_LOST)
→ 同轮 queue_fail_failed 级联 → 对账运行记录标失败 → browser_alerts 告警 → 人工/重新对账重跑
```

## 错误处理 / 边界

| 边界 | 处理 |
|---|---|
| 网络分区误判(agent 活着但 >180s 送不出心跳)被 #4 标失败 | agent 恢复后补发 complete 撞 `guard_browser_sync_job_worker_active`(db.py:5738)状态守卫 → 忽略,无副作用;最坏该次对账标失败走重跑。180s≫30s 降低概率 |
| 竞态:#4 回收与正常 complete 同时 | 两路均带 `allowed_current_statuses` 守卫,先提交者赢,另一个忽略,幂等 |
| 重采重复写 | records 走 key_fields upsert;capture_files 走 ON CONFLICT;均幂等 |
| #4 误伤健康 agent / 非浏览器作业 | SQL 双过滤:`source_kind='browser_playbook'` + 仅心跳过期/NULL 的 agent |
| cron 任务重叠/慢 | APScheduler `max_instances=1` + `coalesce=true`;reaper SQL 幂等 |
| cron 触发时 finance-mcp 不可用 | `mcp_client` 连接失败仅记日志,下一 interval 再跑,不抛 |

## 测试策略(优先 TDD 先红灯)

- **#2**(扩 `test_dispatcher_loop.py`):回写返回 `{success:false}`/抛异常 → 断言调 `mark_browser_job_failed(retryable=True)`、不报成功;返回成功 → happy path 回归。
- **#1 薄片**(扩 `test_browser_capture_files.py`):同 `(sync_job_id, storage_path)` 连插两次 → 一行+更新不报错;迁移 038 重复执行幂等。
- **#4**(新 `test_reap_stale_agents.py`):stale + fresh agent 各挂 running 浏览器作业 + 一个非浏览器作业 → 调函数 → 只有 stale agent 浏览器作业变 failed/`AGENT_HEARTBEAT_LOST`,其余不动;工具层鉴权 + 返回值。
- **#3**:断言 `service.py` 启动不再装配 `_waiting_reconciler`;finance-cron 注册了新 interval job 且 `mcp_client` 调用工具名正确。
- **端到端两条**(扩 `test_browser_first_store_e2e.py` / `test_browser_waiting_data_queue.py`):
  1. 自愈:capture_files 首次抛错 → #2 标可重试失败 → 重采重放 → success → 对账跑完。
  2. agent 死:running 作业 + 心跳置过期 → `reap_stale → queue_fail_failed` → 断言作业 failed、对账记录 failed(非永远 running)。

## 实现顺序建议

1. 迁移 038 + capture_files 幂等(#1 薄片) — 解除本类崩溃,且是重试安全的前提。
2. #2 dispatcher 检查回写 — 源头自愈。
3. #4 finance-mcp 工具 + auth_db 函数。
4. #3 finance-cron 注册 reaper interval job + mcp_client 包装;移除 browser-agent `_waiting_reconciler`。
5. 端到端回归。
