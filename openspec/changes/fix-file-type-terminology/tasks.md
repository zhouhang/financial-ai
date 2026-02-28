## 1. 前端修改

- [x] 1.1 修改 ChatArea.tsx 欢迎语 - "智能财务助手" 改为通用对账助手

## 2. Data Agent 系统提示词修改

- [x] 2.1 修改 main_graph/nodes.py 系统提示词 - 移除"业务文件/财务文件"描述
- [x] 2.2 修改 reconciliation/nodes.py 对话节点提示词

## 3. 对话输出格式化修改

- [x] 3.1 修改 helpers.py file_names 格式化 - 使用"文件1/文件2"
- [x] 3.2 修改 helpers.py 字段映射格式化 - 使用文件1/文件2
- [x] 3.3 修改 helpers.py 预览结果格式化 - "文件1记录数/文件2记录数"
- [x] 3.4 修改 helpers.py 推荐规则提示 - 使用通用术语
- [x] 3.5 修改 helpers.py row_filters 日志 - 移除业务/财务特定描述

## 4. MCP Server 提示词修改

- [x] 4.1 修改 mcp_server/tools.py 文件类型识别提示词 - 输出使用"文件1/文件2"
  - 注：内部 LLM 提示词保持不变（技术实现需要，用户不可见）

## 5. 验证测试

- [x] 5.1 使用 grep 全面检查是否遗漏
- [x] 5.2 启动服务测试对话流程
- [x] 5.3 验证对账结果输出格式
