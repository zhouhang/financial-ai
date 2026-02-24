# Financial AI - 快速参考卡

## 🚀 一键启动

```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
./START_ALL_SERVICES.sh
```

## 🛑 一键停止

```bash
./STOP_ALL_SERVICES.sh
```

或者：
```bash
lsof -ti:3335,8100,5173 | xargs kill -9
```

## 📍 服务访问地址

| 服务 | 端口 | 地址 |
|------|------|------|
| finance-web | 5173 | http://localhost:5173 |
| data-agent | 8100 | http://localhost:8100 |
| finance-mcp | 3335 | http://localhost:3335 |

## 📋 查看日志

```bash
# 实时查看日志
tail -f logs/finance-mcp.log
tail -f logs/data-agent.log
tail -f logs/finance-web.log

# 查看最近20行日志
tail -20 logs/finance-mcp.log
tail -20 logs/data-agent.log
tail -20 logs/finance-web.log
```

## 🔍 检查服务状态

```bash
# 检查端口占用
lsof -i:3335,8100,5173 | grep LISTEN

# 检查单个端口
lsof -i:3335  # finance-mcp
lsof -i:8100  # data-agent
lsof -i:5173  # finance-web
```

## 🔧 验证配置

```bash
./VERIFY_CONFIG.sh
```

## 💻 手动启动（三个终端）

**终端 1 - finance-mcp：**
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
cd finance-mcp
python unified_mcp_server.py
```

**终端 2 - data-agent：**
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
cd finance-agents/data-agent
python -m app.server
```

**终端 3 - finance-web：**
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai/finance-web
npm run dev
```

## 🐛 常见问题快速修复

### 端口被占用
```bash
# 查看占用端口的进程
lsof -i:3335

# 杀死进程
lsof -ti:3335 | xargs kill -9
```

### 虚拟环境错误
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
which python  # 验证是否使用正确的虚拟环境
```

### 依赖缺失
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
pip install -r requirements.txt

# finance-web 依赖
cd finance-web
npm install
```

### 脚本无执行权限
```bash
chmod +x START_ALL_SERVICES.sh
chmod +x STOP_ALL_SERVICES.sh
chmod +x VERIFY_CONFIG.sh
```

## 📂 项目结构

```
financial-ai/
├── finance-web/          # 前端 (端口 5173)
├── finance-agents/       # AI 后端 (端口 8100)
├── finance-mcp/          # MCP 服务 (端口 3335)
├── .venv/                # Python 虚拟环境
├── logs/                 # 日志目录
├── START_ALL_SERVICES.sh # 启动脚本
├── STOP_ALL_SERVICES.sh  # 停止脚本
└── README.md             # 详细文档
```

## 📚 详细文档

- [README.md](./README.md) - 完整项目说明
- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) - 系统架构
- [README_SERVICES.md](./README_SERVICES.md) - 服务管理指南

## 🔐 环境变量

创建 `.env` 文件（如果不存在）：

```bash
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=finflux
DB_USER=finflux_user
DB_PASSWORD=123456

# MCP 服务器配置
MCP_SERVER_PORT=3335
```

## 🎯 快速测试

```bash
# 健康检查
curl http://localhost:3335/health  # finance-mcp
curl http://localhost:8100/health  # data-agent

# 访问前端
open http://localhost:5173
```

---

**提示**：首次启动前运行 `./VERIFY_CONFIG.sh` 验证配置！
