## Why

当前对话系统使用"业务文件"和"财务文件"术语，但作为通用性的财务Agent对账工具，只需要负责对比两个文件的数据，不应强制区分业务或财务类型。这导致：
1. 用户困惑 - 不是所有对账场景都涉及"业务"和"财务"
2. 术语不准确 - "业务文件"和"财务文件"是内部实现细节，不应暴露给用户

## What Changes

- 将对话中所有"业务文件/财务文件"改为"文件1/文件2"或通用术语"文件"
- 移除系统提示词中的业务/财务特定描述
- 保持内部代码的 business/finance 标识不变（技术实现需要）
- 仅修改面向用户的对话输出文本

## Capabilities

### New Capabilities
- (无新能力)

### Modified Capabilities
- `reconciliation-chat`: 对话输出中的文件术语需要通用化

## Impact

### 需要修改的文件
- `finance-agents/data-agent/app/graphs/main_graph/nodes.py` - 系统提示词
- `finance-agents/data-agent/app/graphs/reconciliation/nodes.py` - 对话节点
- `finance-agents/data-agent/app/graphs/reconciliation/helpers.py` - 格式化输出函数
- `finance-mcp/reconciliation/mcp_server/tools.py` - 文件类型识别提示词
- `finance-web/src/components/ChatArea.tsx` - 欢迎语文字

### 不需要修改
- 内部代码逻辑（business/finance 标识保持不变）
- 数据库字段和存储格式
