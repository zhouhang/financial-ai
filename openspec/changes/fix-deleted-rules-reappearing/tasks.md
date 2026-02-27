## 1. 修改删除逻辑

- [x] 1.1 修改 `auth/tools.py` 的 `_handle_delete_rule` 函数，根据用户角色区分删除方式
- [x] 1.2 普通用户删除：调用 `update_rule(rule_id, status='archived')` 实现软删除
- [x] 1.3 管理员删除：调用 `delete_rule(rule_id)` 实现硬删除

## 2. 验证规则列表过滤

- [x] 2.1 确认 `list_rules_for_user` 函数默认过滤 status='active'（已实现）
- [x] 2.2 确认管理员可以查询 archived 规则（设置 status='archived'）

## 3. 验证推荐规则逻辑

- [x] 3.1 确认 `list_recommended_rules` 函数只返回 status='active' 的规则
- [ ] 3.2 测试游客获取推荐规则不包含已删除规则

## 4. 测试验证

- [ ] 4.1 测试普通用户删除规则后，规则列表不显示该规则
- [ ] 4.2 测试管理员删除规则后，规则被物理删除
- [ ] 4.3 测试规则 status 与 visibility 字段独立工作
