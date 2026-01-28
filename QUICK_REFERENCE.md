# 🚀 Finance AI - 快速参考卡片

## 📐 架构图（最重要！）

```
用户
 ↓
finance-ui (纯前端)
 ↓ 只调用 Dify API
 ↓ Bearer app-pffBjBphPBhbrSwz8mxku2R3
Dify API
 ↓
 ├─→ finance-mcp API (认证、Schema、文件)
 └─→ finance-mcp MCP (数据整理、对账)
```

## ⚡ 一键启动

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

## 🔑 关键配置

### Dify API
- **URL**: `http://localhost/v1/chat-messages`
- **Key**: `app-pffBjBphPBhbrSwz8mxku2R3`
- **文件**: `finance-ui/src/api/dify.ts`

### 请求示例
```javascript
fetch('http://localhost/v1/chat-messages', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer app-pffBjBphPBhbrSwz8mxku2R3',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    inputs: {},
    query: '用户消息',
    response_mode: 'streaming',
    user: 'anonymous_user',
  }),
});
```

## 🌐 服务地址

| 服务 | 地址 | 用途 |
|------|------|------|
| finance-ui | http://localhost:5173 | 前端界面 |
| Dify API | http://localhost/v1 | AI 对话 |
| finance-mcp API | http://localhost:8000 | RESTful API |
| API 文档 | http://localhost:8000/docs | Swagger |
| finance-mcp MCP | http://localhost:3335 | MCP 工具 |

## 🎯 特殊指令

| 指令 | 触发 UI |
|------|---------|
| `[login_form]` | 登录表单 |
| `[create_schema]` | 创建 Schema 表单 |
| `[update_schema]` | 更新 Schema 表单 |
| `[schema_list]` | Schema 列表 |

## 🔄 典型流程

### 用户登录
```
用户: "登录"
→ Dify 返回: [login_form]
→ 显示登录表单
→ 用户填写
→ Dify 调用: POST /api/auth/login
→ 返回 token
→ 保存认证状态
```

### 创建 Schema
```
用户: "创建规则"
→ Dify 返回: [create_schema]
→ 显示创建表单
→ 用户填写
→ Dify 调用: POST /api/schemas
→ 返回 Schema
→ 更新本地状态
```

## 🧪 快速测试

### 测试 Dify API
```bash
curl -X POST http://localhost/v1/chat-messages \
  -H "Authorization: Bearer app-pffBjBphPBhbrSwz8mxku2R3" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{},"query":"你好","response_mode":"blocking","user":"test"}'
```

### 测试 finance-mcp API
```bash
curl http://localhost:8000/health
```

### 测试前端
```bash
open http://localhost:5173
```

## 📋 验证架构
```bash
./verify_architecture.sh
```

## 🛑 停止服务
```bash
./STOP_ALL_SERVICES.sh
```

## 📚 完整文档

| 文档 | 说明 |
|------|------|
| [FINAL_ARCHITECTURE.md](./FINAL_ARCHITECTURE.md) | 完整架构说明 ⭐ |
| [COMPLETION_SUMMARY.md](./COMPLETION_SUMMARY.md) | 完成总结 ⭐ |
| [ARCHITECTURE_FIX_REPORT.md](./ARCHITECTURE_FIX_REPORT.md) | 修正报告 |
| [TESTING_CHECKLIST.md](./TESTING_CHECKLIST.md) | 测试清单 |

## ⚠️ 重要提示

### ✅ 正确
- finance-ui → Dify → finance-mcp
- finance-ui 只调用 Dify API
- 所有业务逻辑通过 Dify 协调

### ❌ 错误
- ~~finance-ui → finance-mcp API~~
- ~~finance-ui 直接调用后端~~

## 🎯 下一步

1. ✅ 架构已验证通过
2. ⏳ 启动所有服务
3. ⏳ 在 Dify 中配置 finance-mcp 集成
4. ⏳ 测试完整流程

---

**版本**: 2.0 Final
**日期**: 2026-01-27
**状态**: ✅ 就绪
