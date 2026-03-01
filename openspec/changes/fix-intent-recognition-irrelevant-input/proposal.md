## Why

用户在任何流程阶段（登录/游客模式下的创建规则、编辑规则等）输入无关内容（如"不要"、闲聊等）时，AI 应当正确识别意图并给出友好回复。当前存在问题：
- 某些节点可能缺少意图识别逻辑
- 登录模式下部分流程的意图切换处理不完整

## What Changes

- 审查并补全所有 reconciliation 节点中的意图识别逻辑
- 确保登录模式和游客模式的处理一致
- 添加日志便于调试

## Capabilities

### New Capabilities
- (无新能力)

### Modified Capabilities
- `reconciliation-chat`: 完善意图识别和无关输入处理

## Impact

- `finance-agents/data-agent/app/graphs/reconciliation/nodes.py` - 各节点意图处理
- `finance-agents/data-agent/app/utils/workflow_intent.py` - 意图分类函数
