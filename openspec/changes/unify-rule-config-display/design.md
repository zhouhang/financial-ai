## Context

编辑规则和推荐规则的配置规则展示逻辑不一致：
1. **编辑规则**：从 `data_cleaning_rules` 的 description 获取
2. **推荐规则**：之前错误地从 `custom_validations` 获取

用户实际配置的规则保存在 `rule_config_text` 中，但推荐规则的 `list_recommended_rules` 函数没有返回 `rule_template` 字段，导致无法获取。

## Goals / Non-Goals

**Goals:**
- 统一编辑规则和推荐规则的配置规则展示逻辑
- 统一从 `rule_config_text` 获取配置规则
- 不再使用 `custom_validations` 作为配置规则展示

**Non-Goals:**
- 不修改数据库结构
- 不修改规则保存逻辑

## Decisions

### 1. 修改 list_recommended_rules 返回 rule_template

**Decision**: 在 SQL 查询中添加 `rule_template` 字段。

**Rationale**: `rule_template` 包含完整的规则配置，包括 `rule_config_text`。

### 2. 推荐规则展示逻辑

**Decision**: 配置规则展示按以下优先级获取：
1. `rule_config_items`（用户实际配置的规则列表）
2. `rule_config_text`（用户配置的规则文本）
3. 不使用 `custom_validations`

**Rationale**: 
- `rule_config_items` 是内存中的运行时数据结构
- `rule_config_text` 是持久化的用户配置描述
- `custom_validations` 是系统定义的验证规则，非用户实际配置

## Risks / Trade-offs

- **风险**: 部分旧规则没有 `rule_config_text`，将无法显示配置规则
- **缓解**: 这些规则将显示为空，与编辑规则保持一致

## Migration Plan

1. 修改 `finance-mcp/auth/db.py` 的 `list_recommended_rules` 函数
2. 修改 `finance-agents/data-agent/app/graphs/reconciliation/nodes.py` 中的推荐规则展示逻辑
3. 重启服务测试
