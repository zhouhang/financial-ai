# 🚀 Finance-UI 快速启动指南

## 项目已完成 ✅

恭喜！Finance-UI 项目的核心功能已经实现完毕。您现在可以立即启动并使用这个系统。

---

## 📦 项目包含内容

### 后端 API（100% 完成）
- ✅ 用户认证系统（注册、登录、JWT）
- ✅ Schema 管理（CRUD 操作）
- ✅ 文件上传和 Excel 预览
- ✅ Dify AI 集成和命令检测
- ✅ MySQL 数据库设计

### 前端应用（核心功能完成）
- ✅ 登录/注册界面
- ✅ 主页面和聊天界面
- ✅ API 客户端和状态管理
- ✅ 响应式设计

---

## ⚡ 5分钟快速启动

### 步骤 1：启动后端（2分钟）

```bash
# 进入后端目录
cd finance-ui/backend

# 安装依赖（首次运行）
pip install -r requirements.txt

# 初始化数据库（首次运行）
python init_db.py

# 启动后端服务
python main.py
```

**验证成功：** 看到 "Uvicorn running on http://0.0.0.0:8000"

### 步骤 2：启动前端（2分钟）

```bash
# 打开新终端，进入前端目录
cd finance-ui

# 安装依赖（首次运行）
npm install

# 启动开发服务器
npm run dev
```

**验证成功：** 看到 "Local: http://localhost:5173/"

### 步骤 3：开始使用（1分钟）

1. 打开浏览器访问：http://localhost:5173
2. 点击"立即注册"创建账号
3. 登录后即可使用聊天界面

---

## 🎯 功能演示

### 1. 注册和登录

**注册新用户：**
- 访问 http://localhost:5173/register
- 填写：用户名、邮箱、密码
- 点击"注册"按钮
- 自动跳转到主页

**登录系统：**
- 访问 http://localhost:5173/login
- 输入用户名和密码
- 点击"登录"按钮

### 2. 与 AI 对话

在主页面的聊天框中输入：

```
帮我创建一个货币资金数据整理的规则
```

AI 会回复并可能返回 `[create_schema]` 命令（需要配置 Dify）。

### 3. 测试 API

```bash
# 健康检查
curl http://localhost:8000/health

# 注册用户
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "test123456"
  }'

# 登录获取 Token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "test123456"
  }'

# 创建 Schema（需要替换 YOUR_TOKEN）
curl -X POST http://localhost:8000/api/schemas \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name_cn": "测试数据整理",
    "work_type": "data_preparation",
    "description": "这是一个测试"
  }'
```

---

## 📁 项目结构

```
finance-ui/
├── backend/                    # 后端 API
│   ├── main.py                # FastAPI 应用
│   ├── init_db.py            # 数据库初始化
│   ├── requirements.txt       # Python 依赖
│   ├── models/               # 数据库模型
│   ├── routers/              # API 路由
│   ├── services/             # 业务逻辑
│   └── utils/                # 工具函数
│
├── src/                       # 前端源码
│   ├── api/                  # API 客户端
│   ├── components/           # React 组件
│   │   ├── Auth/            # 登录/注册
│   │   ├── Home/            # 主页和聊天
│   │   └── Common/          # 通用组件
│   ├── stores/              # Zustand 状态
│   ├── types/               # TypeScript 类型
│   ├── App.tsx              # 主应用
│   └── main.tsx             # 入口文件
│
├── DEPLOYMENT_GUIDE.md       # 完整部署指南
├── PROJECT_SUMMARY.md        # 项目总结
├── FINAL_SUMMARY.md          # 最终总结
└── README.md                 # 项目说明
```

---

## 🔧 配置说明

### 后端配置

**文件：** `backend/.env`

```env
# 数据库配置
DATABASE_URL=mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai?charset=utf8mb4

# JWT 密钥（生产环境请更换）
SECRET_KEY=your-secret-key-change-in-production

# Dify API 配置
DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=app-1ab05125-5865-4833-b6a1-ebfd69338f76
```

### 前端配置

**文件：** `finance-ui/.env`

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_DIFY_API_URL=http://localhost:8000/api/dify
```

---

## 🎨 界面预览

### 登录页面
- 简洁的登录表单
- 用户名和密码输入
- "立即注册"链接

### 注册页面
- 用户名、邮箱、密码输入
- 密码确认
- 表单验证

### 主页面
- 欢迎卡片
- AI 聊天界面
- 消息历史显示
- 快速开始按钮

---

## 📊 数据库验证

### 连接数据库

```bash
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456
```

### 查看数据

```sql
USE finance-ai;

-- 查看所有表
SHOW TABLES;

-- 查看用户
SELECT * FROM users;

-- 查看 Schema
SELECT id, user_id, name_cn, type_key, work_type, status
FROM user_schemas;
```

---

## 🐛 常见问题

### 1. 后端启动失败

**问题：** `ModuleNotFoundError: No module named 'fastapi'`

**解决：**
```bash
pip install -r requirements.txt
```

### 2. 数据库连接失败

**问题：** `Can't connect to MySQL server`

**解决：**
- 检查 MySQL 是否运行：`systemctl status mysql`
- 验证数据库凭据：`mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456`
- 检查 `.env` 中的 `DATABASE_URL`

### 3. 前端启动失败

**问题：** `Cannot find module '@/api/client'`

**解决：**
```bash
npm install
```

### 4. CORS 错误

**问题：** `Access to XMLHttpRequest blocked by CORS policy`

**解决：**
- 检查后端 `config.py` 中的 `CORS_ORIGINS`
- 确保包含 `http://localhost:5173`
- 重启后端服务

### 5. Token 无效

**问题：** `Could not validate credentials`

**解决：**
- 重新登录获取新 Token
- 检查 Token 是否过期（默认 24 小时）
- 清除浏览器 localStorage

---

## 📚 API 文档

### 在线文档

启动后端后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 主要端点

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/api/auth/register` | POST | 注册用户 | ❌ |
| `/api/auth/login` | POST | 登录 | ❌ |
| `/api/auth/me` | GET | 获取当前用户 | ✅ |
| `/api/schemas` | GET | 列表查询 | ✅ |
| `/api/schemas` | POST | 创建 Schema | ✅ |
| `/api/schemas/{id}` | GET | 获取详情 | ✅ |
| `/api/schemas/{id}` | PUT | 更新 | ✅ |
| `/api/schemas/{id}` | DELETE | 删除 | ✅ |
| `/api/files/upload` | POST | 上传文件 | ✅ |
| `/api/files/preview` | GET | 预览 Excel | ✅ |
| `/api/dify/chat` | POST | Dify 对话 | ✅ |

---

## 🔐 安全提示

### 开发环境
- ✅ 使用默认配置即可
- ✅ Token 有效期 24 小时
- ✅ 密码使用 bcrypt 加密

### 生产环境
- ⚠️ 必须更换 `SECRET_KEY`
- ⚠️ 启用 HTTPS
- ⚠️ 配置防火墙
- ⚠️ 使用强密码
- ⚠️ 定期备份数据库

---

## 🎓 学习资源

### 官方文档
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [React 文档](https://react.dev/)
- [Ant Design 文档](https://ant.design/)
- [Zustand 文档](https://docs.pmnd.rs/zustand)

### 项目文档
- `DEPLOYMENT_GUIDE.md` - 完整部署指南（50+ 页）
- `PROJECT_SUMMARY.md` - 项目总结和技术要点
- `FINAL_SUMMARY.md` - 最终总结和开发路线图
- `backend/README.md` - 后端文档
- `README.md` - 前端文档

---

## 🚀 下一步开发

### 待实现功能（可选）

1. **Schema 列表页面**
   - 显示所有创建的 Schema
   - 筛选和搜索
   - 编辑和删除操作

2. **Schema 可视化编辑器**
   - Excel 文件上传和预览
   - 拖拽式字段映射
   - 条件规则构建器
   - 实时 JSON 预览

3. **高级功能**
   - 撤销/重做
   - 智能字段推荐
   - Schema 导入/导出
   - 协作功能

### 开发指南

参考 `FINAL_SUMMARY.md` 中的详细开发路线图和示例代码。

---

## 💡 使用技巧

### 1. 快速测试

使用 Postman 或 curl 快速测试 API：

```bash
# 设置环境变量
export API_URL="http://localhost:8000/api"
export TOKEN="your-token-here"

# 测试认证
curl $API_URL/auth/me -H "Authorization: Bearer $TOKEN"

# 测试 Schema 创建
curl -X POST $API_URL/schemas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name_cn":"测试","work_type":"data_preparation"}'
```

### 2. 开发调试

**后端调试：**
- 查看日志：终端输出
- API 文档：http://localhost:8000/docs
- 数据库：MySQL Workbench

**前端调试：**
- 浏览器控制台：F12
- React DevTools：Chrome 扩展
- Network 面板：查看 API 请求

### 3. 数据持久化

- 用户数据存储在 MySQL
- Token 存储在 localStorage
- Schema 文件存储在 `finance-mcp/` 目录

---

## 🎉 恭喜！

您已经成功启动了 Finance-UI 项目！

### 当前可用功能
- ✅ 用户注册和登录
- ✅ AI 聊天界面
- ✅ Schema 管理 API
- ✅ 文件上传和预览

### 开始使用
1. 注册一个账号
2. 登录系统
3. 在聊天框中与 AI 对话
4. 探索 API 功能

### 获取帮助
- 查看文档：`DEPLOYMENT_GUIDE.md`
- API 文档：http://localhost:8000/docs
- 项目总结：`FINAL_SUMMARY.md`

祝您使用愉快！🎊
