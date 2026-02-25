## Why

当前创建对账规则的流程需要用户从头配置字段映射和规则，即使已存在相似的规则。随着规则数量增长（预计达到几万甚至几十万），用户需要一种方式快速找到并复用已有规则，提高对账效率，减少重复配置工作。

## What Changes

- 在文件上传和字段映射完成后，新增规则推荐步骤
- 根据字段映射（订单号、金额、订单时间字段名称完全匹配）查询现有规则
- 展示最相关的 3 个匹配规则供用户选择（显示规则名称和部分配置信息）
- 用户可选择使用推荐规则直接对账，或继续创建新规则
- 对账完成后，AI 评估规则匹配度并提示用户是否保存
- 用户输入"保存"时，提示输入新规则名称，复制一份规则到用户名下
- 用户输入"不要"时，回到字段映射流程继续创建新规则
- 使用预计算索引（字段映射哈希）支持高性能规则查询

## Capabilities

### New Capabilities
- `rule-recommendation`: 基于字段映射推荐匹配的对账规则，包括规则搜索、匹配展示、规则复用、对账后保存

### Modified Capabilities
- (无)

## Impact

- **后端** (`finance-agents/data-agent/app/graphs/reconciliation/`): 
  - 新增规则推荐节点 `rule_recommendation_node`
  - 修改工作流路由，在字段映射后插入推荐步骤
  - 修改 `result_analysis_node`，添加保存提示逻辑
- **后端** (`finance-mcp/`): 
  - 新增规则搜索 MCP 工具 `search_rules_by_mapping`
  - 新增规则复制 MCP 工具 `copy_rule`
- **数据库**: 
  - `reconciliation_rules` 表新增 `field_mapping_hash` 索引字段
  - 添加数据库迁移脚本，为现有规则计算哈希值
- **前端**: 无变化（复用现有消息展示）
