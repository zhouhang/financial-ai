## 1. 数据库索引

- [x] 1.1 在 reconciliation_rules 表添加 field_mapping_hash 字段 (VARCHAR(32))
- [x] 1.2 创建 field_mapping_hash 字段的 B-tree 索引
- [x] 1.3 实现 compute_field_mapping_hash 函数（提取6个字段，排序，MD5）
- [x] 1.4 编写迁移脚本，为现有规则计算并填充 field_mapping_hash

## 2. MCP 工具

- [x] 2.1 新增 search_rules_by_mapping MCP 工具（输入字段映射，返回最多3个匹配规则）
- [x] 2.2 新增 copy_rule MCP 工具（输入 source_rule_id、new_name、user_id，复制规则）
- [x] 2.3 修改 save_rule 工具，保存时自动计算并存储 field_mapping_hash

## 3. 工作流节点

- [x] 3.1 新增 rule_recommendation_node 节点（查询匹配规则，展示推荐，等待用户选择）
- [x] 3.2 实现推荐规则展示格式（名称 + 字段映射摘要 + 规则配置摘要）
- [x] 3.3 处理用户选择逻辑（选择推荐规则 / 创建新规则）

## 4. 路由修改

- [x] 4.1 修改 field_mapping 后的路由，插入 rule_recommendation 节点
- [x] 4.2 添加 route_after_rule_recommendation 路由函数
- [x] 4.3 选择推荐规则时直接路由到 task_execution

## 6. 状态管理

- [x] 6.1 在 AgentState 中添加 recommended_rules 字段（存储推荐的规则列表）
- [x] 6.2 添加 selected_rule_id 字段（用户选择的推荐规则 ID）
- [x] 6.3 添加 using_recommended_rule 标志（标识是否使用推荐规则）

## 7. 测试

- [x] 7.1 测试规则搜索功能（有匹配 / 无匹配场景）
- [x] 7.2 测试推荐规则选择流程
- [x] 7.3 测试对账后保存规则流程
- [x] 7.4 测试"不要"回到字段映射流程
- [x] 7.5 性能测试（模拟大量规则查询）
