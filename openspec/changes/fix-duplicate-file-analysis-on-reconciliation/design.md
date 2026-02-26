## Context

- **当前流程**：游客说「对账」→ `auth_handler` 解析为 `guest_reconciliation` → `route_after_router` 固定返回 `file_analysis` → 执行文件分析 → `route_after_file_analysis` → `rule_recommendation`。
- **问题根因**：每次用户发送新消息（非 resume），`server.py` 会将 `phase` 重置为 `""`，但 `file_analyses` 仍保留在 checkpoint 中。用户再次说「对账」时，`route_after_router` 仍返回 `file_analysis`，导致同一批文件被重复分析。
- **约束**：对账节点已展平到主图，`router` 的 conditional_edges 目前仅包含 `file_analysis`、`task_execution`、`edit_field_mapping`、`END`。

## Goals / Non-Goals

**Goals:**
- 当 `guest_reconciliation` 且已有 `file_analyses` 时，跳过 `file_analysis`，直接进入 `rule_recommendation`。
- 不改变 server 的 phase 重置逻辑（保持简单）。
- 仅修改路由逻辑，最小化改动范围。

**Non-Goals:**
- 不处理 `CREATE_NEW_RULE` 的类似场景（流程不同，需单独考虑）。
- 不修改 `rule_recommendation_node` 内部逻辑。
- 不改变文件变更时的清空逻辑（`files_changed` 时清空 `file_analyses` 已存在）。

## Decisions

### 1. 在 `route_after_router` 中根据 `file_analyses` 分支

**选择**：当 `intent == "guest_reconciliation"` 时，若 `state.get("file_analyses")` 非空，返回 `"rule_recommendation"`；否则返回 `"file_analysis"`。

**理由**：`file_analyses` 是判断「是否已分析过」的最直接依据；`phase` 已被 server 重置，不可靠。

**备选**：在 server 中不重置 phase——会增加分支逻辑，且需区分「新会话」与「对账流程中」，复杂度更高。

### 2. 在 router 的 conditional_edges 中增加 `rule_recommendation` 目标

**选择**：在 `build_main_graph` 的 `route_after_router` 映射中加入 `"rule_recommendation": "rule_recommendation"`。

**理由**：`rule_recommendation` 节点已存在，只需增加一条边；`rule_recommendation_node` 依赖 `file_analyses`，state 中已有，无需额外准备。

### 3. 不修改 server 的 phase 重置逻辑

**选择**：保持 `server.py` 中 `update_state(config, {"phase": ""})` 不变。

**理由**：phase 重置用于避免旧任务结果影响新任务；本修复仅依赖 `file_analyses` 判断，不依赖 phase，因此无需改动 server。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 用户曾在 `field_mapping` 阶段说「对账」时，会回到 `rule_recommendation`，可能丢失中间进度 | 接受：用户说「对账」通常表示「开始/继续对账」，回到规则推荐是可接受行为；若需保留进度，应使用 resume 或更明确的指令 |
| `file_analyses` 与当前 `uploaded_files` 不一致（如文件被替换但未触发 `files_changed`） | 已有 `files_changed` 逻辑会清空 `file_analyses`，正常情况下不会出现 |
| 游客与已登录用户流程差异 | 仅修改 `guest_reconciliation` 分支；已登录用户的 `use_existing_rule` / `create_new_rule` 不受影响 |

## Migration Plan

- 无需数据迁移或部署步骤。
- 修改后重启 data-agent 服务即可：`./START_ALL_SERVICES.sh`。
- 回滚：还原 `routers.py` 的修改即可。

## Open Questions

- 无。
