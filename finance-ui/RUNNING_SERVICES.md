# Finance-UI 运行服务信息

## 🟢 当前运行状态

**启动时间**: 2026-01-26 20:53

### 服务列表

| 服务 | 状态 | PID | 地址 |
|------|------|-----|------|
| 前端服务 | 🟢 运行中 | 69239 | http://localhost:5173 |
| 后端服务 | 🟢 运行中 | 70567 | http://localhost:8000 |
| 数据库 | 🟢 已连接 | - | mysql://127.0.0.1:3306/finance-ai |

---

## 📍 访问地址

### 用户界面
- **前端应用**: http://localhost:5173
  - 登录/注册页面
  - AI 聊天界面
  - Schema 管理（待实现）

### API 服务
- **后端 API**: http://localhost:8000
- **API 文档 (Swagger)**: http://localhost:8000/docs
- **API 文档 (ReDoc)**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health

---

## 🔧 管理命令

### 停止服务

```bash
# 停止前端
kill 69239

# 停止后端
kill 70567

# 停止所有服务
pkill -f "npm run dev"
pkill -f "python3 main.py"
```

### 重启服务

```bash
# 重启前端
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev

# 重启后端
cd /Users/kevin/workspace/financial-ai/finance-ui/backend
python3 main.py
```

### 一键启动

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
./start.sh
```

### 查看日志

```bash
# 前端日志
tail -f /Users/kevin/workspace/financial-ai/finance-ui/frontend.log

# 后端日志
tail -f /Users/kevin/workspace/financial-ai/finance-ui/backend/backend.log

# 实时查看所有日志
tail -f frontend.log backend/backend.log
```

---

## 🧪 快速测试

### 1. 测试后端健康状态

```bash
curl http://localhost:8000/health
```

**预期输出**:
```json
{"status":"healthy","service":"finance-ui-api","version":"1.0.0"}
```

### 2. 测试用户注册

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "test123456"
  }'
```

### 3. 测试用户登录

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "test123456"
  }'
```

### 4. 测试 Schema 创建

```bash
# 先登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"test123456"}' \
  | jq -r '.access_token')

# 创建 Schema
curl -X POST http://localhost:8000/api/schemas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name_cn": "测试数据整理",
    "work_type": "data_preparation",
    "description": "这是一个测试"
  }'
```

---

## 📊 数据库信息

### 连接信息
- **主机**: 127.0.0.1
- **端口**: 3306
- **数据库**: finance-ai
- **用户**: aiuser
- **密码**: 123456

### 数据表

1. **users** - 用户表
   - id, username, email, password_hash
   - created_at, updated_at

2. **user_schemas** - 用户 Schema 表
   - id, user_id, name_cn, type_key
   - work_type, schema_path, config_path
   - version, status, is_public
   - callback_url, description
   - created_at, updated_at

### 连接数据库

```bash
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 finance-ai
```

### 常用查询

```sql
-- 查看所有用户
SELECT id, username, email, created_at FROM users;

-- 查看所有 Schema
SELECT id, user_id, name_cn, type_key, work_type, status
FROM user_schemas;

-- 查看用户的 Schema
SELECT u.username, s.name_cn, s.type_key, s.status
FROM users u
JOIN user_schemas s ON u.id = s.user_id;
```

---

## 🎯 核心功能

### 已实现功能 ✅

1. **用户认证**
   - 用户注册（用户名、邮箱唯一性验证）
   - 用户登录（JWT Token，24小时有效期）
   - 密码加密（bcrypt，cost factor 12）
   - Token 自动管理

2. **AI 对话**
   - 与 Dify AI 实时对话
   - 消息历史记录
   - 命令检测（[create_schema], [update_schema], [schema_list]）
   - 流式响应支持

3. **Schema 管理 API**
   - 创建 Schema（中文转拼音）
   - 查询 Schema 列表（支持过滤、分页）
   - 获取 Schema 详情
   - 更新 Schema
   - 删除 Schema

4. **文件处理**
   - 多文件上传
   - Excel 文件解析
   - 文件预览（表头 + 前100行）
   - 文件类型和大小验证

### 待实现功能 ⏳

1. **Schema 列表页面**（优先级：高）
   - 显示所有 Schema
   - 筛选和搜索
   - 编辑和删除操作

2. **Schema 编辑器**（优先级：高）
   - Canvas 模态框
   - Excel 预览组件
   - 步骤编辑器
   - Schema 生成和保存

3. **高级功能**（优先级：中）
   - 撤销/重做
   - 智能推荐
   - 导入/导出
   - 协作功能

---

## 📚 文档资源

### 快速开始
- [QUICKSTART.md](QUICKSTART.md) - 5分钟快速启动指南
- [README.md](README.md) - 项目说明

### 完整指南
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 完整部署指南（50+页）
- [USER_MANUAL.md](USER_MANUAL.md) - 用户使用手册
- [PROJECT_COMPLETION_REPORT.md](PROJECT_COMPLETION_REPORT.md) - 项目完成报告

### 项目总结
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - 项目总结
- [FINAL_SUMMARY.md](FINAL_SUMMARY.md) - 最终总结
- [DELIVERY.md](DELIVERY.md) - 交付文档
- [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md) - 项目检查清单

### 脚本工具
- [start.sh](start.sh) - 一键启动脚本
- [verify.sh](verify.sh) - 项目验证脚本

---

## 🔍 故障排查

### 前端无法访问

```bash
# 检查前端进程
ps aux | grep "npm run dev"

# 查看前端日志
tail -f frontend.log

# 重启前端
kill 69239
npm run dev
```

### 后端无法访问

```bash
# 检查后端进程
ps aux | grep "python3 main.py"

# 查看后端日志
tail -f backend/backend.log

# 重启后端
kill 70567
cd backend && python3 main.py
```

### 数据库连接失败

```bash
# 检查 MySQL 是否运行
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 -e "SELECT 1"

# 检查数据库是否存在
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 -e "SHOW DATABASES LIKE 'finance-ai'"

# 重新初始化数据库
cd backend && python3 init_db.py
```

### 端口被占用

```bash
# 检查端口占用
lsof -i :5173  # 前端端口
lsof -i :8000  # 后端端口

# 杀死占用端口的进程
kill -9 $(lsof -t -i:5173)
kill -9 $(lsof -t -i:8000)
```

---

## 📞 获取帮助

### 在线资源
- FastAPI 文档: https://fastapi.tiangolo.com/
- React 文档: https://react.dev/
- Ant Design 文档: https://ant.design/
- Zustand 文档: https://docs.pmnd.rs/zustand

### 本地 API 文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 📝 更新日志

### 2026-01-26
- ✅ 项目初始化完成
- ✅ 后端 API 开发完成（25个文件，11个端点）
- ✅ 前端核心功能完成（28个文件）
- ✅ 数据库设计和初始化完成
- ✅ 文档编写完成（11个文档文件）
- ✅ 服务成功启动并运行

---

**最后更新**: 2026-01-26 20:53
**版本**: v1.0.0
**状态**: ✅ 运行中
