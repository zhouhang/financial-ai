# Guest Reconciliation - 游客对账流程

## Overview

本规范定义了未登录游客使用对账功能的流程和行为约束。

## ADDED Requirements

### Requirement: 游客可使用推荐规则进行对账

系统 SHALL 允许未登录用户上传文件并使用系统推荐规则进行对账，但仅限于推荐规则。

#### Scenario: 游客上传文件
- **WHEN** 未登录用户上传业务文件和财务文件
- **THEN** 系统分析文件结构，提取字段信息
- **AND** 返回推荐规则列表供选择

#### Scenario: 游客选择推荐规则进行对账
- **WHEN** 游客选择推荐规则并发起对账
- **THEN** 系统执行对账逻辑
- **AND** 返回对账结果（仅展示，不保存）

#### Scenario: 游客尝试访问私有规则
- **WHEN** 游客请求查看自己的保存规则
- **THEN** 系统返回提示：请登录后查看您的规则

### Requirement: 游客对账使用次数限制

系统 SHALL 限制每位游客（每token）最多使用3次对账功能。

#### Scenario: 游客对账次数已达上限
- **WHEN** 游客第3次对账完成后
- **THEN** 系统显示：您已使用3次对账功能，请登录后继续使用
- **AND** 右上角显示醒目的登录按钮

#### Scenario: 超过次数后提示登录
- **WHEN** 游客尝试第4次对账
- **THEN** 系统阻止操作
- **AND** 弹出登录提示框或显示登录按钮

### Requirement: 游客会话数据不持久化

系统 SHALL 确保游客的对账数据不会持久化到数据库，会话结束后数据清除。

#### Scenario: 游客关闭浏览器
- **WHEN** 游客关闭浏览器或结束会话
- **THEN** 所有对账数据从内存清除
- **AND** 下次访问需要重新上传文件

#### Scenario: 游客尝试保存规则
- **WHEN** 游客点击保存推荐规则
- **THEN** 系统显示：请先登录，登录后可保存规则
- **AND** 点击右上角登录按钮进行登录

### Requirement: 游客模式下规则列表过滤

在游客模式下，系统 SHALL 仅返回推荐规则，不返回用户私有规则。

#### Scenario: 游客请求规则列表
- **WHEN** 系统收到guest_token的规则列表请求
- **THEN** 仅返回 is_recommended=true 的规则
- **AND** 不返回任何用户创建的规则

## 游客对账流程状态图

```
开始
  │
  ▼
上传文件 ──► 分析文件 ──► 推荐规则
                      │
                      ▼
               选择规则 ──► 执行对账
                      │
                      ▼
               返回结果 ──► 使用次数+1
                      │
          ┌───────────┴───────────┐
          │                       │
     次数 < 3                 次数 >= 3
          │                       │
          ▼                       ▼
    继续使用                  提示登录
```

## MCP 工具增强

### 新增工具

- `create_guest_token`: 创建游客临时token
- `verify_guest_token`: 验证游客token有效性
- `increment_guest_usage`: 增加游客使用次数

### 修改工具

- `list_reconciliation_rules`: 支持guest_token参数，游客模式返回推荐规则
- `file_upload`: 支持guest_token，游客也可上传
- `reconciliation_start`: 支持guest_token，检查使用次数
