## MODIFIED Requirements

### Requirement: 推荐规则配置规则展示
推荐规则的配置规则部分 SHALL 从 rule_config_text 获取，而非 custom_validations。

#### Scenario: 推荐规则包含 rule_config_text
- **WHEN** 推荐规则的 rule_template 包含非空的 rule_config_text
- **THEN** 配置规则部分 SHALL 显示 rule_config_text 的内容

#### Scenario: 推荐规则不包含 rule_config_text
- **WHEN** 推荐规则的 rule_template 不包含 rule_config_text 或为空
- **THEN** 配置规则部分 SHALL 显示为空（与编辑规则行为一致）

#### Scenario: 编辑规则配置规则展示
- **WHEN** 用户编辑规则时查看配置规则
- **THEN** 配置规则 SHALL 从 rule_config_items 或 rule_config_text 获取

### Requirement: list_recommended_rules 返回 rule_template
系统 SHALL 在 list_recommended_rules 函数返回时包含 rule_template 字段。

#### Scenario: 获取推荐规则列表
- **WHEN** 调用 list_recommended_rules 函数
- **THEN** 返回的每条规则 SHALL 包含完整的 rule_template 字段
