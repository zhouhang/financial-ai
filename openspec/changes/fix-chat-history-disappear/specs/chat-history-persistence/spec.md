## ADDED Requirements

### Requirement: 登录用户对话本地持久化
系统 SHALL 在 localStorage 中保存登录用户的对话消息，刷新页面后能从本地恢复。

#### Scenario: 登录用户刷新页面
- **WHEN** 登录用户刷新页面
- **THEN** 系统从 localStorage 恢复对话消息
- **AND** 对话历史完整保留

#### Scenario: 对话更新时保存到本地
- **WHEN** 登录用户发送或收到新消息
- **THEN** 系统立即将对话保存到 localStorage
- **AND** 即使浏览器崩溃也能恢复

### Requirement: 本地与服务器数据同步
系统 SHALL 以服务器数据为准，本地数据作为缓存。

#### Scenario: 服务器加载成功
- **WHEN** 从服务器加载会话成功
- **THEN** 使用服务器数据更新本地显示
- **AND** 保留最新对话

#### Scenario: 服务器加载失败
- **WHEN** 从服务器加载会话失败
- **THEN** 使用本地缓存的对话
- **AND** 显示提示"使用本地缓存"
