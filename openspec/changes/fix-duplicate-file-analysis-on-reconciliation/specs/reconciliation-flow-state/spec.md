## ADDED Requirements

### Requirement: 游客对账意图下根据 file_analyses 决定路由

当用户意图为 `guest_reconciliation` 时，系统 SHALL 根据 `file_analyses` 是否为空决定路由目标：若已有分析结果则进入 `rule_recommendation`，否则进入 `file_analysis`，以避免同一批文件被重复分析。

#### Scenario: 首次说「对账」且已上传文件

- **WHEN** 用户意图为 `guest_reconciliation`，且 `file_analyses` 为空，且 `uploaded_files` 非空
- **THEN** 系统 SHALL 路由到 `file_analysis` 节点执行文件分析

#### Scenario: 再次说「对账」且已有分析结果

- **WHEN** 用户意图为 `guest_reconciliation`，且 `file_analyses` 非空
- **THEN** 系统 SHALL 路由到 `rule_recommendation` 节点，跳过 `file_analysis`，直接展示推荐规则

#### Scenario: 文件变更后说「对账」

- **WHEN** 用户意图为 `guest_reconciliation`，且 `uploaded_files` 与上次相比已变更（`files_changed` 为真）
- **THEN** 系统 SHALL 在 `file_analyses` 被清空后路由到 `file_analysis` 节点执行重新分析
