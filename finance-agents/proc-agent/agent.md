# Agent 描述

- **name**: 数据整理数字员工 (Data-Process Agent)
- **desc**: 本 agent 是一个通用的数据整理平台，可以根据配置的业务 skill 及规则描述等对各类数据进行整理工作。当前支持审计数据整理 skill，后续可扩展其他业务领域的整理技能。

## 核心能力

1. **Skill 管理**: 支持加载和管理多个业务 skill
2. **意图识别**: 根据用户请求自动识别业务类型
3. **规则加载**: 从 references 目录加载业务规则文件
4. **脚本执行**: 调用或生成 Python 脚本执行数据处理
5. **结果输出**: 生成标准化的 Excel 和 Markdown 格式结果

## 支持的 Skill

| Skill ID | Skill 名称 | 描述 | 路径 |
|----------|-----------|------|------|
| `AUDIT-DATA-ORGANIZER-001` | 审计数据整理 | 处理审计部门的数据整理业务 | `skills/audit/` |

## 技术架构

- 基于 LangGraph 框架开发
- 前端集成到 finance-web
- 支持 MCP 协议（可选）
