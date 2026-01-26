# Finance-UI 完整部署指南

## 项目概述

Finance-UI 是一个全栈 Web 应用，提供可视化界面用于创建和管理财务数据处理 Schema。

### 技术栈
- **后端**: FastAPI + SQLAlchemy + MySQL
- **前端**: React 18 + TypeScript + Ant Design
- **集成**: Dify AI + MCP Server

---

## 后端部署

### 1. 环境准备

确保已安装：
- Python 3.10+
- MySQL 8.0+
- pip

### 2. 安装依赖

```bash
cd finance-ui/backend
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下内容：

```env
# 数据库配置
DATABASE_URL=mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai?charset=utf8mb4

# JWT 密钥（生产环境请更换）
SECRET_KEY=your-secret-key-change-in-production-09a8f7d6e5c4b3a2

# Dify API 配置
DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=app-1ab05125-5865-4833-b6a1-ebfd69338f76

# 文件存储路径
UPLOAD_DIR=../finance-mcp/uploads
SCHEMA_BASE_DIR=../finance-mcp
```

### 4. 初始化数据库

运行数据库初始化脚本：

```bash
python init_db.py
```

这将：
1. 创建 `finance-ai` 数据库（如果不存在）
2. 创建 `users` 表
3. 创建 `user_schemas` 表
4. 验证表结构

**预期输出：**
```
============================================================
Finance UI Database Initialization
============================================================
Database finance-ai already exists
Creating tables...
Tables created successfully

Verifying tables...
Found 2 tables:
  - users
    Columns:
      id (int)
      username (varchar(50))
      email (varchar(100))
      password_hash (varchar(255))
      created_at (timestamp)
      updated_at (timestamp)
  - user_schemas
    Columns:
      id (int)
      user_id (int)
      name_cn (varchar(100))
      type_key (varchar(50))
      work_type (enum('data_preparation','reconciliation'))
      schema_path (varchar(500))
      config_path (varchar(500))
      version (varchar(20))
      status (enum('draft','published'))
      is_public (tinyint(1))
      callback_url (varchar(500))
      description (text)
      created_at (timestamp)
      updated_at (timestamp)

============================================================
Database initialization completed successfully!
============================================================
```

### 5. 启动后端服务

```bash
python main.py
```

或使用 uvicorn：
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**验证服务：**
```bash
# 健康检查
curl http://localhost:8000/health

# 预期响应
{
  "status": "healthy",
  "service": "finance-ui-api",
  "version": "1.0.0"
}
```

### 6. 测试 API

#### 注册用户
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "test123456"
  }'
```

#### 登录获取 Token
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "test123456"
  }'
```

保存返回的 `access_token`，后续请求需要使用。

#### 创建 Schema
```bash
curl -X POST http://localhost:8000/api/schemas \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name_cn": "测试数据整理",
    "work_type": "data_preparation",
    "description": "这是一个测试 Schema"
  }'
```

---

## 前端部署

### 1. 环境准备

确保已安装：
- Node.js 18+
- npm 或 yarn

### 2. 初始化前端项目

```bash
cd finance-ui
npm create vite@latest . -- --template react-ts
```

选择：
- Framework: React
- Variant: TypeScript

### 3. 安装依赖

```bash
npm install
npm install antd zustand axios xlsx react-router-dom
npm install @types/node -D
```

### 4. 配置环境变量

创建 `.env` 文件：
```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_DIFY_API_URL=http://localhost:8000/api/dify
```

### 5. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173

---

## 完整工作流测试

### 1. 用户注册和登录

1. 打开前端应用 http://localhost:5173
2. 点击"注册"，填写用户信息
3. 注册成功后自动跳转到登录页
4. 输入用户名和密码登录
5. 登录成功后进入主页面

### 2. 与 Dify 对话

1. 在主页面的对话框中输入："帮我创建一个货币资金数据整理的规则"
2. Dify 响应并返回 `[create_schema]` 命令
3. 系统自动弹出 Schema 编辑器画布

### 3. 创建 Schema

**第一步：初始化**
1. 选择工作类型：数据整理
2. 输入中文名称：货币资金数据整理
3. 系统自动生成 type_key: `huo_bi_zi_jin_shu_ju_zheng_li`
4. 点击"下一步"

**第二步：配置规则**
1. 上传 Excel 文件（支持多个文件）
2. 系统显示 Excel 预览（分屏显示）
3. 配置处理步骤：
   - 步骤名称：读取本期科目余额表
   - 步骤类型：extract_and_write
   - 文件模式：`*科目余额表*本期*.xlsx`
   - 列映射：科目名称 → account_name
   - 条件提取：科目名称匹配 "银行存款_*"
4. 添加更多步骤（可选）
5. 点击"测试"验证 Schema
6. 测试通过后点击"保存并发布"

### 4. 管理 Schema

1. 在 Schema 列表页面查看所有创建的规则
2. 可以编辑、删除、复制 Schema
3. 查看 Schema 详情和 JSON 配置

---

## 数据库验证

### 连接数据库
```bash
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456
```

### 查看数据
```sql
USE finance-ai;

-- 查看用户
SELECT * FROM users;

-- 查看 Schema
SELECT id, user_id, name_cn, type_key, work_type, status, created_at
FROM user_schemas;

-- 查看用户的所有 Schema
SELECT u.username, s.name_cn, s.type_key, s.work_type, s.status
FROM users u
JOIN user_schemas s ON u.id = s.user_id;
```

---

## 文件系统验证

### Schema 文件结构

创建 Schema 后，文件系统中会生成以下文件：

```
finance-mcp/
├── data_preparation/
│   ├── schemas/
│   │   └── 1/                                    # 用户 ID
│   │       └── huo_bi_zi_jin_shu_ju_zheng_li.json  # Schema JSON
│   └── config/
│       └── 1/                                    # 用户 ID
│           └── data_preparation_schemas.json     # 配置文件
└── reconciliation/
    ├── schemas/
    │   └── 1/
    └── config/
        └── 1/
```

### 查看生成的文件

```bash
# 查看 Schema JSON
cat finance-mcp/data_preparation/schemas/1/huo_bi_zi_jin_shu_ju_zheng_li.json

# 查看配置文件
cat finance-mcp/data_preparation/config/1/data_preparation_schemas.json
```

---

## 与 MCP Server 集成测试

### 1. 确保 MCP Server 运行

```bash
cd finance-mcp
python unified_mcp_server.py
```

MCP Server 应该运行在 http://localhost:3335

### 2. 测试 Schema 执行

使用创建的 Schema 执行数据处理：

```bash
curl -X POST http://localhost:3335/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "data_preparation_start",
    "arguments": {
      "data_preparation_type": "货币资金数据整理",
      "files": [
        "/uploads/2026/1/26/科目余额表_本期_2025.xlsx",
        "/uploads/2026/1/26/科目余额表_上期_2024.xlsx"
      ]
    }
  }'
```

### 3. 查看处理结果

```bash
# 查询任务状态
curl -X POST http://localhost:3335/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "data_preparation_status",
    "arguments": {
      "task_id": "TASK_ID_FROM_PREVIOUS_RESPONSE"
    }
  }'

# 获取处理结果
curl -X POST http://localhost:3335/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "data_preparation_result",
    "arguments": {
      "task_id": "TASK_ID_FROM_PREVIOUS_RESPONSE"
    }
  }'
```

---

## 故障排查

### 后端问题

#### 1. 数据库连接失败
```
Error: Can't connect to MySQL server
```

**解决方案：**
- 检查 MySQL 服务是否运行：`systemctl status mysql`
- 验证数据库凭据：`mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456`
- 检查 `.env` 中的 `DATABASE_URL` 配置

#### 2. 表不存在
```
Error: Table 'finance-ai.users' doesn't exist
```

**解决方案：**
- 重新运行初始化脚本：`python init_db.py`
- 手动创建表（参考 models/user.py 和 models/schema.py）

#### 3. JWT Token 无效
```
Error: Could not validate credentials
```

**解决方案：**
- 检查 Token 是否过期（默认 24 小时）
- 重新登录获取新 Token
- 检查 `SECRET_KEY` 配置是否一致

### 前端问题

#### 1. CORS 错误
```
Access to XMLHttpRequest blocked by CORS policy
```

**解决方案：**
- 检查后端 `config.py` 中的 `CORS_ORIGINS` 配置
- 确保前端 URL 在允许列表中
- 重启后端服务

#### 2. API 请求失败
```
Error: Network Error
```

**解决方案：**
- 检查后端服务是否运行：`curl http://localhost:8000/health`
- 检查 `.env` 中的 `VITE_API_BASE_URL` 配置
- 查看浏览器控制台的网络请求详情

### Dify 集成问题

#### 1. Dify API 连接失败
```
Error: Failed to connect to Dify API
```

**解决方案：**
- 检查 Dify 服务是否运行
- 验证 `DIFY_API_URL` 和 `DIFY_API_KEY` 配置
- 测试 Dify API：`curl http://localhost/v1/chat-messages`

#### 2. 命令检测不工作
```
Dify 响应了但没有触发画布
```

**解决方案：**
- 检查 Dify 响应中是否包含 `[create_schema]` 等命令
- 查看后端日志确认命令检测逻辑
- 在 Dify 工作流中确保输出包含命令标记

---

## 生产环境部署

### 后端

1. **使用 Gunicorn + Uvicorn Workers**
```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

2. **配置 Systemd 服务**
```ini
[Unit]
Description=Finance UI API
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/finance-ui/backend
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000

[Install]
WantedBy=multi-user.target
```

3. **配置 Nginx 反向代理**
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 前端

1. **构建生产版本**
```bash
npm run build
```

2. **配置 Nginx**
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    root /path/to/finance-ui/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

---

## 安全建议

1. **更换 SECRET_KEY**
   - 生产环境使用强随机密钥
   - 使用 `openssl rand -hex 32` 生成

2. **启用 HTTPS**
   - 使用 Let's Encrypt 免费证书
   - 配置 SSL/TLS

3. **数据库安全**
   - 使用强密码
   - 限制数据库访问 IP
   - 定期备份

4. **文件上传限制**
   - 验证文件类型
   - 限制文件大小
   - 扫描恶意文件

5. **API 速率限制**
   - 使用 slowapi 或 nginx limit_req
   - 防止暴力攻击

---

## 监控和日志

### 后端日志

FastAPI 自动记录请求日志，可以配置更详细的日志：

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
```

### 数据库监控

```sql
-- 查看活动连接
SHOW PROCESSLIST;

-- 查看表大小
SELECT
    table_name,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
FROM information_schema.TABLES
WHERE table_schema = 'finance-ai';
```

---

## 下一步开发

当前已完成：
- ✅ 后端 API 完整实现
- ✅ 数据库设计和初始化
- ✅ 认证和授权
- ✅ Schema CRUD 操作
- ✅ 文件上传和预览
- ✅ Dify 集成和命令检测

待开发：
- ⏳ 前端 React 应用
- ⏳ Schema 可视化编辑器
- ⏳ Excel 预览组件
- ⏳ 聊天界面

参考实现计划文档：`/Users/kevin/.claude/plans/recursive-hugging-dream.md`
