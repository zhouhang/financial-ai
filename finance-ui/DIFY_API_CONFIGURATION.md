# Dify API 配置指南

## 📋 当前状态

✅ 前端已修改：去掉登录注册，直接显示 AI 对话界面
✅ 后端已修改：/api/dify/chat 接口无需认证
⚠️ 需要配置：正确的 Dify API Key

---

## 🔑 获取 Dify API Key

### 步骤 1: 访问 Dify 开发页面

打开浏览器访问：
```
http://localhost/app/1ab05125-5865-4833-b6a1-ebfd69338f76/develop
```

### 步骤 2: 找到 API Key

在开发页面中，找到以下内容：
- **API 端点 (API Endpoint)**: 应该显示为 `http://localhost/v1`
- **API 密钥 (API Key)**: 一个以 `app-` 开头的长字符串

### 步骤 3: 复制 API Key

复制完整的 API Key，格式类似：
```
app-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## ⚙️ 配置 API Key

### 方式 1: 使用环境变量文件（推荐）

在 `backend/` 目录下创建 `.env` 文件：

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui/backend
cat > .env << 'EOF'
# Dify API Configuration
DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=你的API_KEY（替换这里）
EOF
```

### 方式 2: 直接修改配置文件

编辑 `backend/config.py` 文件，修改第 18-19 行：

```python
# Dify API
DIFY_API_URL: str = "http://localhost/v1"
DIFY_API_KEY: str = "你的API_KEY（替换这里）"
```

---

## 🔄 重启服务

配置完成后，重启后端服务：

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
./manage.sh restart
```

或者只重启后端：

```bash
# 停止后端
pkill -f "python3 main.py"

# 启动后端
cd backend
nohup python3 main.py > backend.log 2>&1 &
```

---

## 🧪 测试配置

### 测试 1: 直接测试 Dify API

```bash
# 替换 YOUR_API_KEY 为你的实际 API Key
curl -X POST http://localhost/v1/chat-messages \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {},
    "query": "你好",
    "response_mode": "blocking",
    "user": "test_user"
  }'
```

**预期结果**: 返回 AI 的回复，包含 `answer` 字段

### 测试 2: 测试后端 API

```bash
curl -X POST http://localhost:8000/api/dify/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你好，请介绍一下你自己",
    "streaming": false
  }'
```

**预期结果**: 返回包含 `answer` 和 `message_id` 的 JSON 响应

### 测试 3: 访问前端

打开浏览器访问：
```
http://localhost:5173
```

在 AI 对话框中输入消息，测试是否能正常对话。

---

## 🐛 故障排查

### 问题 1: 401 Unauthorized

**错误信息**:
```json
{"code":"unauthorized","message":"Access token is invalid","status":401}
```

**解决方案**:
1. 检查 API Key 是否正确
2. 确保 API Key 以 `app-` 开头
3. 检查 Dify 服务是否正常运行
4. 重新从 Dify 开发页面获取 API Key

### 问题 2: 503 Service Unavailable

**错误信息**:
```json
{"detail":"Failed to connect to Dify API: ..."}
```

**解决方案**:
1. 检查 Dify 服务是否运行：`curl http://localhost/v1/info`
2. 检查 DIFY_API_URL 配置是否正确
3. 检查网络连接

### 问题 3: 前端无法连接后端

**解决方案**:
1. 检查后端是否运行：`curl http://localhost:8000/health`
2. 检查前端配置：`.env` 文件中的 `VITE_API_BASE_URL`
3. 查看浏览器控制台错误信息

---

## 📝 配置文件说明

### backend/config.py

```python
class Settings(BaseSettings):
    # Dify API
    DIFY_API_URL: str = "http://localhost/v1"  # Dify API 端点
    DIFY_API_KEY: str = "app-xxx"              # Dify API 密钥

    class Config:
        env_file = ".env"  # 从 .env 文件读取配置
```

### backend/.env（可选）

```bash
# Dify API Configuration
DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=app-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 前端 .env

```bash
VITE_API_BASE_URL=http://localhost:8000/api
VITE_DIFY_API_URL=http://localhost:8000/api/dify
```

---

## 🔍 查看日志

### 后端日志

```bash
tail -f /Users/kevin/workspace/financial-ai/finance-ui/backend/backend.log
```

### 前端日志

```bash
tail -f /Users/kevin/workspace/financial-ai/finance-ui/frontend.log
```

### 查看服务状态

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
./manage.sh status
```

---

## 📞 获取帮助

如果配置过程中遇到问题：

1. 查看后端日志：`tail -f backend/backend.log`
2. 查看前端控制台：打开浏览器开发者工具（F12）
3. 测试 Dify API：使用上面的测试命令
4. 检查服务状态：`./manage.sh status`

---

## ✅ 配置完成检查清单

- [ ] 已访问 Dify 开发页面
- [ ] 已获取正确的 API Key
- [ ] 已配置 backend/.env 或 backend/config.py
- [ ] 已重启后端服务
- [ ] 测试 Dify API 成功
- [ ] 测试后端 API 成功
- [ ] 前端可以正常对话

---

**配置完成后，系统将完全可用！**

访问 http://localhost:5173 即可开始使用 AI 对话功能。
