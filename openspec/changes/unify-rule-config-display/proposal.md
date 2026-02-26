## Why

编辑规则和推荐规则的配置规则部分，展示来源不一致：编辑规则从 `data_cleaning_rules` 的 description 获取，推荐规则之前错误地从 `custom_validations` 获取。导致用户看到的配置规则描述不统一，部分推荐规则无法正确显示用户实际配置的规则。

## What Changes

- 修改推荐规则的配置规则展示逻辑，统一从 `rule_config_text` 获取
- 确保编辑规则和推荐规则的配置规则展示逻辑一致
- 不再使用 `custom_validations` 作为配置规则展示（这只是系统定义的验证规则，非用户实际配置）
- 修改 `list_recommended_rules` 函数，返回 `rule_template` 字段（包含 `rule_config_text`）

## Capabilities

### New Capabilities
- (无)

### Modified Capabilities
- `rule-recommendation`: 修改配置规则展示逻辑，统一从 rule_config_text 获取

## Impact

- `finance-agents/data-agent/app/graphs/reconciliation/nodes.py`: rule_recommendation_node 中的配置规则展示逻辑
- `finance-mcp/auth/db.py`: list_recommended_rules 函数
