# Guest Auth - 临时认证机制

## Overview

本规范定义了游客临时认证机制，允许未注册用户使用部分系统功能。

## ADDED Requirements

### Requirement: 系统可生成临时游客Token

MCP工具 SHALL 支持生成临时游客auth_token，该token具有以下特性：
- 有效期为7天
- 存储在PostgreSQL `guest_auth_tokens` 表中
- 包含唯一标识符、使用次数计数、创建时间和过期时间

#### Scenario: 首次访问生成Token
- **WHEN** 未登录用户首次调用需要认证的MCP工具
- **THEN** 系统自动生成临时token并返回给客户端
- **AND** token存储在 `guest_auth_tokens` 表，初始使用次数为0

#### Scenario: Token验证成功
- **WHEN** 客户端使用guest_token调用MCP工具
- **THEN** 系统验证token有效性和过期时间
- **AND** 验证通过后执行对应业务逻辑

#### Scenario: Token已过期
- **WHEN** 客户端使用已过期的guest_token调用MCP工具
- **THEN** 系统返回错误：游客token已过期，请重新尝试

### Requirement: 临时Token使用次数限制

系统 SHALL 限制每个临时token的使用次数为3次，用于对账功能。

#### Scenario: 使用次数未达上限
- **WHEN** 游客token使用次数小于3
- **THEN** 系统允许执行对账操作
- **AND** 使用完成后使用次数+1

#### Scenario: 使用次数已达上限
- **WHEN** 游客token使用次数已达到3次
- **THEN** 系统拒绝执行对账操作
- **AND** 返回提示：请登录后继续使用，已为您登录后可继续使用

### Requirement: 游客Token与用户Token隔离

系统 SHALL 确保游客token与正式用户token使用不同的验证逻辑和数据存储。

#### Scenario: 游客访问用户专属功能
- **WHEN** 游客token尝试访问需要用户认证的功能（如查看历史会话、保存规则）
- **THEN** 系统返回错误：此功能需要登录后使用
- **AND** 不影响游客的正常使用功能

## Data Model

### guest_auth_tokens 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| token | VARCHAR(64) | 唯一token值 |
| session_id | VARCHAR(64) | 关联的会话ID |
| usage_count | INTEGER | 已使用次数 |
| max_usage | INTEGER | 最大使用次数（默认3） |
| created_at | TIMESTAMP | 创建时间 |
| expires_at | TIMESTAMP | 过期时间 |
| ip_address | VARCHAR(45) | 用户IP地址 |
