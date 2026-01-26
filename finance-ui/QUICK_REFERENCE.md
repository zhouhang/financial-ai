# Finance-UI 快速参考卡片

## 🚀 快速启动

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui

# 方式 1: 使用管理脚本（推荐）
./manage.sh start

# 方式 2: 使用启动脚本
./start.sh

# 方式 3: 手动启动
npm run dev &                    # 前端
cd backend && python3 main.py &  # 后端
```

## 📍 访问地址

| 服务 | 地址 |
|------|------|
| **前端应用** | http://localhost:5173 |
| **后端 API** | http://localhost:8000 |
| **API 文档** | http://localhost:8000/docs |
| **健康检查** | http://localhost:8000/health |

## 🔧 常用命令

### 服务管理

```bash
./manage.sh start      # 启动所有服务
./manage.sh stop       # 停止所有服务
./manage.sh restart    # 重启所有服务
./manage.sh status     # 查看服务状态
./manage.sh logs       # 查看实时日志
./manage.sh test       # 测试服务
./manage.sh clean      # 清理日志
```

### 查看日志

```bash
# 前端日志
tail -f frontend.log

# 后端日志
tail -f backend/backend.log

# 同时查看
tail -f frontend.log backend/backend.log
```

### 停止服务

```bash
# 使用管理脚本
./manage.sh stop

# 手动停止（当前运行的 PID）
kill 69239  # 前端
kill 70567  # 后端
```

## 🧪 快速测试

### 测试后端

```bash
# 健康检查
curl http://localhost:8000/health

# 注册用户
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","email":"test@example.com","password":"test123"}'

# 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
```

### 测试前端

```bash
# 访问前端
open http://localhost:5173

# 或使用 curl
curl -I http://localhost:5173
```

## 💾 数据库操作

### 连接数据库

```bash
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 finance-ai
```

### 常用查询

```sql
-- 查看所有用户
SELECT * FROM users;

-- 查看所有 Schema
SELECT * FROM user_schemas;

-- 查看用户的 Schema
SELECT u.username, s.name_cn, s.type_key
FROM users u
JOIN user_schemas s ON u.id = s.user_id;
```

### 重置数据库

```bash
cd backend
python3 init_db.py
```

## 📊 项目结构

```
finance-ui/
├── backend/              # 后端 API
│   ├── main.py          # 入口文件
│   ├── config.py        # 配置
│   ├── models/          # 数据模型
│   ├── routers/         # API 路由
│   └── services/        # 业务逻辑
├── src/                 # 前端源码
│   ├── api/            # API 客户端
│   ├── components/     # React 组件
│   ├── stores/         # 状态管理
│   └── types/          # TypeScript 类型
├── manage.sh           # 服务管理脚本 ⭐
├── start.sh            # 启动脚本
└── verify.sh           # 验证脚本
```

## 🔍 故障排查

### 服务无法启动

```bash
# 检查端口占用
lsof -i :5173  # 前端
lsof -i :8000  # 后端

# 杀死占用进程
kill -9 $(lsof -t -i:5173)
kill -9 $(lsof -t -i:8000)

# 查看日志
./manage.sh logs
```

### 依赖问题

```bash
# 重新安装前端依赖
rm -rf node_modules package-lock.json
npm install

# 重新安装后端依赖
cd backend
pip3 install -r requirements.txt
```

### 数据库问题

```bash
# 测试数据库连接
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 -e "SELECT 1"

# 重新初始化
cd backend
python3 init_db.py
```

## 📚 文档导航

| 文档 | 说明 |
|------|------|
| [QUICKSTART.md](QUICKSTART.md) | 5分钟快速开始 |
| [USER_MANUAL.md](USER_MANUAL.md) | 完整使用手册 |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | 部署指南 |
| [RUNNING_SERVICES.md](RUNNING_SERVICES.md) | 运行服务信息 |
| [PROJECT_COMPLETION_REPORT.md](PROJECT_COMPLETION_REPORT.md) | 项目完成报告 |

## 🎯 核心 API 端点

### 认证

```bash
POST /api/auth/register  # 注册
POST /api/auth/login     # 登录
GET  /api/auth/me        # 获取当前用户
```

### Schema 管理

```bash
GET    /api/schemas      # 列表查询
POST   /api/schemas      # 创建
GET    /api/schemas/{id} # 获取详情
PUT    /api/schemas/{id} # 更新
DELETE /api/schemas/{id} # 删除
```

### 文件操作

```bash
POST /api/files/upload   # 上传文件
GET  /api/files/preview  # 预览文件
```

### Dify 集成

```bash
POST /api/dify/chat      # AI 对话
```

## 💡 使用技巧

### 1. 快速重启服务

```bash
./manage.sh restart
```

### 2. 实时监控日志

```bash
./manage.sh logs
```

### 3. 检查服务状态

```bash
./manage.sh status
```

### 4. 测试所有功能

```bash
./manage.sh test
```

### 5. 清理日志文件

```bash
./manage.sh clean
```

## 🔐 安全提示

### 开发环境
- ✅ 使用默认配置即可
- ✅ Token 24小时有效期

### 生产环境
- ⚠️ 更换 SECRET_KEY
- ⚠️ 启用 HTTPS
- ⚠️ 配置防火墙
- ⚠️ 定期备份数据库

## 📞 获取帮助

### 查看帮助

```bash
./manage.sh help
```

### 在线文档

- API 文档: http://localhost:8000/docs
- 项目文档: 查看 `docs/` 目录

### 常见问题

参考 [USER_MANUAL.md](USER_MANUAL.md) 的"常见问题"章节

---

**提示**: 将此文件保存为书签，方便随时查阅！

**最后更新**: 2026-01-26
**版本**: v1.0.0
