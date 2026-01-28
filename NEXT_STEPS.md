# 🎯 下一步行动清单

## ✅ 已完成的工作

### 架构重构
- ✅ 理解并实现了正确的架构：`用户 → finance-ui → Dify → finance-mcp`
- ✅ 删除了 finance-ui 中所有直接调用 finance-mcp API 的代码
- ✅ 配置了正确的 Dify API Key: `app-pffBjBphPBhbrSwz8mxku2R3`
- ✅ 修改了所有 Store 和组件，移除了 API 调用
- ✅ 创建了完整的文档和启动脚本
- ✅ 验证了架构配置

### 文件变更
**删除的文件**:
- `finance-ui/src/api/auth.ts`
- `finance-ui/src/api/schemas.ts`
- `finance-ui/src/api/files.ts`
- `finance-ui/src/api/client.ts`
- `finance-ui/backend/` (整个目录)

**保留的文件**:
- `finance-ui/src/api/dify.ts` (唯一的 API 调用)

**修改的文件**:
- `finance-ui/src/stores/authStore.ts` - 添加 `setAuthFromDify()`
- `finance-ui/src/stores/schemaStore.ts` - 改为本地状态管理
- `finance-ui/src/stores/canvasStore.ts` - 移除 API 调用
- `finance-ui/src/components/Canvas/SchemaMetadataForm.tsx` - 移除 API 调用

## 📋 立即执行（今天）

### 1. 启动所有服务 ⏰ 5 分钟
```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

**验证**:
- [ ] finance-mcp API 运行在 http://localhost:8000
- [ ] finance-mcp MCP 运行在 http://localhost:3335
- [ ] finance-ui 运行在 http://localhost:5173
- [ ] Dify 运行在 http://localhost

### 2. 测试 Dify API 连接 ⏰ 5 分钟
```bash
# 测试 Dify API
curl -X POST http://localhost/v1/chat-messages \
  -H "Authorization: Bearer app-pffBjBphPBhbrSwz8mxku2R3" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {},
    "query": "你好",
    "response_mode": "blocking",
    "user": "test_user"
  }'
```

**预期结果**:
- 返回 200 状态码
- 返回 JSON 响应，包含 `answer` 字段

### 3. 测试前端界面 ⏰ 5 分钟
```bash
open http://localhost:5173
```

**验证**:
- [ ] 页面正常加载
- [ ] 聊天界面显示正常
- [ ] 可以输入消息
- [ ] 可以发送消息到 Dify

## 📅 短期任务（本周）

### 1. 配置 Dify 集成 ⏰ 2-3 小时

#### 1.1 配置 finance-mcp API 集成
在 Dify 中添加 HTTP API 工具:

**认证 API**:
- `POST http://localhost:8000/api/auth/register`
  - Body: `{ "username": "...", "email": "...", "password": "..." }`
- `POST http://localhost:8000/api/auth/login`
  - Body: `{ "username": "...", "password": "..." }`
  - Response: `{ "access_token": "...", "user": {...} }`

**Schema API**:
- `POST http://localhost:8000/api/schemas`
  - Headers: `Authorization: Bearer {token}`
  - Body: `{ "name_cn": "...", "work_type": "...", "description": "..." }`
- `GET http://localhost:8000/api/schemas`
  - Headers: `Authorization: Bearer {token}`
- `GET http://localhost:8000/api/schemas/{id}`
  - Headers: `Authorization: Bearer {token}`

**文件 API**:
- `POST http://localhost:8000/api/files/upload`
  - Headers: `Authorization: Bearer {token}`
  - Body: multipart/form-data

#### 1.2 配置 finance-mcp MCP 集成
在 Dify 中添加 MCP 服务器:
- MCP Server URL: `http://localhost:3335`
- 可用工具:
  - `data_preparation_start`
  - `data_preparation_status`
  - `data_preparation_result`
  - `reconciliation_start`
  - `reconciliation_status`
  - `reconciliation_result`
  - `file_upload`

#### 1.3 定义对话流程
在 Dify 中创建工作流:

**登录流程**:
```
用户输入包含 "登录" 关键词
  → 返回消息: "请登录 [login_form]"
  → 用户填写表单
  → 调用 POST /api/auth/login
  → 返回: "登录成功！" + token
```

**创建 Schema 流程**:
```
用户输入包含 "创建规则" 关键词
  → 返回消息: "请填写规则信息 [create_schema]"
  → 用户填写表单
  → 调用 POST /api/schemas
  → 返回: "规则创建成功！" + schema
```

**数据整理流程**:
```
用户上传文件并输入 "整理数据"
  → 调用 MCP 工具: data_preparation_start
  → 返回: "数据整理完成！" + 结果
```

### 2. 端到端测试 ⏰ 1-2 小时

#### 测试场景 1: 用户注册和登录
1. [ ] 访问 http://localhost:5173
2. [ ] 在聊天框输入 "我要注册"
3. [ ] 检查是否显示注册表单
4. [ ] 填写注册信息并提交
5. [ ] 检查是否注册成功
6. [ ] 输入 "登录"
7. [ ] 检查是否显示登录表单
8. [ ] 填写登录信息并提交
9. [ ] 检查是否登录成功

#### 测试场景 2: 创建 Schema
1. [ ] 确保已登录
2. [ ] 输入 "创建一个数据整理规则"
3. [ ] 检查是否显示创建表单
4. [ ] 填写规则信息
5. [ ] 提交表单
6. [ ] 检查是否创建成功
7. [ ] 输入 "查看我的规则"
8. [ ] 检查是否显示规则列表

#### 测试场景 3: 数据整理
1. [ ] 确保已登录
2. [ ] 上传 Excel 文件
3. [ ] 输入 "帮我整理这个文件"
4. [ ] 检查是否调用 MCP 工具
5. [ ] 检查是否返回处理结果
6. [ ] 检查是否可以下载结果文件

### 3. 问题修复 ⏰ 根据测试结果

根据测试中发现的问题进行修复:
- [ ] 修复 Dify API 调用问题
- [ ] 修复指令检测问题
- [ ] 修复 UI 渲染问题
- [ ] 修复状态管理问题

## 📆 中期任务（本月）

### 1. 完善功能
- [ ] 添加更多 Schema 模板
- [ ] 完善错误处理
- [ ] 优化用户体验
- [ ] 添加加载状态提示

### 2. 性能优化
- [ ] 优化 Dify API 调用
- [ ] 优化前端渲染性能
- [ ] 添加请求缓存
- [ ] 优化文件上传

### 3. 安全加固
- [ ] 将 Dify API Key 移到环境变量
- [ ] 添加请求签名验证
- [ ] 添加 CSRF 保护
- [ ] 添加 XSS 防护

### 4. 监控和日志
- [ ] 添加 API 访问日志
- [ ] 添加错误追踪
- [ ] 添加性能监控
- [ ] 添加用户行为分析

## 📆 长期任务（下月）

### 1. 容器化部署
- [ ] 创建 Dockerfile
- [ ] 创建 docker-compose.yml
- [ ] 配置 Kubernetes
- [ ] 设置 CI/CD 流水线

### 2. 功能扩展
- [ ] 添加更多数据整理模板
- [ ] 添加更多对账规则
- [ ] 添加批量处理功能
- [ ] 添加定时任务功能

### 3. 文档完善
- [ ] 编写用户手册
- [ ] 编写开发者指南
- [ ] 编写 API 文档
- [ ] 编写部署文档

## 🆘 遇到问题？

### 问题 1: Dify API 返回 401
**原因**: API Key 不正确
**解决**: 检查 `finance-ui/src/api/dify.ts` 中的 API Key 是否为 `app-pffBjBphPBhbrSwz8mxku2R3`

### 问题 2: 前端无法发送消息
**原因**: Dify 服务未启动或 API Key 错误
**解决**: 
1. 检查 Dify 是否运行: `curl http://localhost/health`
2. 检查 API Key 配置

### 问题 3: finance-mcp API 无法访问
**原因**: API 服务器未启动
**解决**: 
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_api_server.sh
```

### 问题 4: MCP 工具调用失败
**原因**: MCP 服务器未启动或 Dify 未配置 MCP 集成
**解决**:
1. 启动 MCP 服务器: `./start_server.sh`
2. 在 Dify 中配置 MCP 服务器地址

## 📞 获取帮助

### 查看日志
```bash
# API 日志
tail -f /tmp/finance-mcp-api.log

# MCP 日志
tail -f /Users/kevin/workspace/financial-ai/finance-mcp/unified_mcp.log

# 前端日志
# 在浏览器开发者工具的 Console 中查看
```

### 查看文档
- [FINAL_ARCHITECTURE.md](./FINAL_ARCHITECTURE.md) - 完整架构说明
- [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - 快速参考
- [TESTING_CHECKLIST.md](./TESTING_CHECKLIST.md) - 测试清单

### 验证架构
```bash
./verify_architecture.sh
```

## ✅ 完成标准

### 立即任务完成标准
- [x] 所有服务成功启动
- [x] Dify API 连接测试通过
- [x] 前端界面正常显示
- [x] 可以发送消息到 Dify

### 短期任务完成标准
- [ ] Dify 中配置了 finance-mcp API 集成
- [ ] Dify 中配置了 MCP 工具集成
- [ ] 定义了完整的对话流程
- [ ] 所有测试场景通过

### 中期任务完成标准
- [ ] 所有核心功能正常工作
- [ ] 性能达到预期目标
- [ ] 安全措施已实施
- [ ] 监控和日志系统运行

### 长期任务完成标准
- [ ] 容器化部署完成
- [ ] CI/CD 流水线运行
- [ ] 文档完整且最新
- [ ] 生产环境稳定运行

---

**创建日期**: 2026-01-27
**优先级**: 高
**负责人**: 开发团队
**状态**: 🚀 准备开始
