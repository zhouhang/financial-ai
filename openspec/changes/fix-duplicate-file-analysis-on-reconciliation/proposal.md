## Why

当用户输入「对账」时，若已上传文件且处于对账流程中（如等待选择推荐规则），系统会错误地重置 `phase` 并重新执行文件分析和推荐规则，导致同一批文件被分析两次。这造成重复的 AI 调用、冗余的界面展示，以及用户体验混乱。

## What Changes

- **修复重复分析**：当用户说「对账」且已有 `file_analyses` 时，不再重新进入 `file_analysis`，而是路由到当前流程的下一步（如 `rule_recommendation` 或 `field_mapping`）。
- **推荐规则缩进**：确保「字段映射：」与「配置规则：」标签缩进一致（此前已实现）。

## Capabilities

### New Capabilities

- `reconciliation-flow-state`: 对账流程状态管理——在用户输入「对账」等意图时，根据已有 `file_analyses`、`phase` 等状态决定是进入文件分析还是继续后续步骤。

### Modified Capabilities

（无——`openspec/specs/` 下暂无现有 spec）

## Impact

- **finance-agents/data-agent/app/server.py**：新消息时重置 `phase` 的逻辑需调整，避免在 reconciliation 流程中误清空。
- **finance-agents/data-agent/app/graphs/main_graph/routers.py**：`route_after_router` 需在 `guest_reconciliation` 意图下检查 `file_analyses`，若已有分析则路由到 `rule_recommendation` 而非 `file_analysis`。
- **finance-agents/data-agent/app/graphs/main_graph/nodes.py**：`intent_router` 中 `guest_reconciliation` 分支可能需传递/保留 `phase` 或 `file_analyses`，供路由使用。
