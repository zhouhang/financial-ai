# 服务重启指南

## ✅ 服务已成功启动

### 当前状态

| 服务 | 状态 | 地址 | 终端 |
|------|------|------|------|
| **data-agent** | ✅ 运行中 | http://0.0.0.0:8100 | terminal 11 |
| **finance-web** | ✅ 运行中 | http://localhost:5173 | terminal 12 |

---

## 📝 重要规则

### ⚠️ 修改代码后必须重启服务

**原因：**
- **后端 (data-agent)**: Python 代码修改后，虽然有 auto-reload，但某些情况下可能不生效
- **前端 (finance-web)**: Vite 有 HMR (热模块替换)，但有时也需要完全重启

**流程：**
```bash
1. 修改代码
2. kill 旧进程
3. 重启服务
4. 测试功能
```

---

## 🚀 推荐方法：使用重启脚本

### 方法一：运行脚本（推荐）

```bash
cd /Users/kevin/workspace/financial-ai
./restart_services.sh
```

**脚本功能：**
- ✅ 自动 kill 端口 8100 和 5173 的进程
- ✅ 启动 data-agent（后台运行）
- ✅ 启动 finance-web（后台运行）
- ✅ 验证服务启动状态
- ✅ 显示日志位置和 PID

**输出示例：**
```
════════════════════════════════════════════════════════════════
🔄 重启服务脚本
════════════════════════════════════════════════════════════════

📦 步骤 1/3: 停止现有服务...
  ✓ 已停止 data-agent (端口 8100)
  ✓ 已停止 finance-web (端口 5173)

📦 步骤 2/3: 启动 data-agent...
  ✓ data-agent 已启动 (PID: 12345)
  ℹ 日志: logs/data-agent.log

📦 步骤 3/3: 启动 finance-web...
  ✓ finance-web 已启动 (PID: 12346)
  ℹ 日志: logs/finance-web.log

════════════════════════════════════════════════════════════════
✅ 服务启动完成
════════════════════════════════════════════════════════════════

  ✓ data-agent 运行中   → http://0.0.0.0:8100
  ✓ finance-web 运行中  → http://localhost:5173
```

---

### 方法二：手动命令

#### 1. 停止所有服务
```bash
lsof -ti:8100 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null
```

#### 2. 启动 data-agent
```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate
python -m app.server
```

#### 3. 启动 finance-web（新终端）
```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

---

## 📊 查看日志

### 实时查看日志

```bash
# data-agent 日志
tail -f /Users/kevin/workspace/financial-ai/logs/data-agent.log

# finance-web 日志
tail -f /Users/kevin/workspace/financial-ai/logs/finance-web.log

# Cursor 终端日志（当前运行的）
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/11.txt  # data-agent
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/12.txt  # finance-web
```

### 查看最近的错误

```bash
# 后端错误
tail -50 /Users/kevin/workspace/financial-ai/logs/data-agent.log | grep -i error

# 前端错误
tail -50 /Users/kevin/workspace/financial-ai/logs/finance-web.log | grep -i error
```

---

## 🛑 停止服务

### 方法一：按端口停止（推荐）

```bash
# 停止 data-agent
lsof -ti:8100 | xargs kill -9

# 停止 finance-web
lsof -ti:5173 | xargs kill -9

# 一次性停止所有
lsof -ti:8100,5173 | xargs kill -9
```

### 方法二：按 PID 停止

```bash
# 查找 PID
ps aux | grep "app.server"
ps aux | grep "vite"

# 停止进程
kill -9 <PID>
```

---

## 🔍 验证服务状态

### 检查端口占用

```bash
# 查看端口 8100 (data-agent)
lsof -i:8100

# 查看端口 5173 (finance-web)
lsof -i:5173
```

**输出示例：**
```
COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
python  48382  kevin   5u  IPv4  ...      0t0  TCP *:8100 (LISTEN)
node    48500  kevin  24u  IPv4  ...      0t0  TCP localhost:5173 (LISTEN)
```

### 测试 API 连接

```bash
# 测试后端健康检查
curl http://localhost:8100/health

# 测试前端页面
curl http://localhost:5173
```

---

## 🐛 常见问题

### 问题1：端口被占用

**现象：**
```
Error: listen EADDRINUSE: address already in use :::8100
```

**解决：**
```bash
lsof -ti:8100 | xargs kill -9
# 然后重新启动
```

---

### 问题2：虚拟环境未激活

**现象：**
```
ModuleNotFoundError: No module named 'fastapi'
```

**解决：**
```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate
python -m app.server
```

---

### 问题3：npm 依赖问题

**现象：**
```
Error: Cannot find module 'vite'
```

**解决：**
```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm install
npm run dev
```

---

### 问题4：WebSocket 连接失败

**前端显示：**
```
WebSocket connection failed
```

**检查步骤：**
1. 确认后端运行：`lsof -i:8100`
2. 检查后端日志：`tail -20 logs/data-agent.log`
3. 确认前端代理配置：检查 `vite.config.ts`

---

## 📁 项目结构

```
financial-ai/
├── restart_services.sh          # 🆕 重启脚本
├── logs/                        # 🆕 日志目录
│   ├── data-agent.log          # 后端日志
│   └── finance-web.log         # 前端日志
├── finance-agents/
│   └── data-agent/
│       ├── .venv/               # Python 虚拟环境
│       └── app/
│           └── server.py        # FastAPI 服务器
└── finance-web/
    ├── vite.config.ts           # Vite 配置
    └── src/
        ├── App.tsx              # 主应用
        └── components/          # 组件
```

---

## 🎯 快速参考

### 完整重启流程（3个命令）

```bash
# 1. 进入项目目录
cd /Users/kevin/workspace/financial-ai

# 2. 运行重启脚本
./restart_services.sh

# 3. 打开浏览器测试
open http://localhost:5173
```

### 调试模式启动（查看实时日志）

```bash
# 终端 1: data-agent
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate
python -m app.server

# 终端 2: finance-web
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

---

## 📝 备注

- **修改后端代码**: 必须重启 data-agent
- **修改前端代码**: Vite 通常会自动热更新，但如果不生效，重启 finance-web
- **修改配置文件**: 必须重启相应服务
- **日志文件**: 如果使用脚本启动，日志会保存到 `logs/` 目录

---

**创建时间**：2026-02-11  
**当前服务状态**：✅ 运行中
