# Financial AI 服务管理指南

## 🚀 快速启动

### 方式一：使用启动脚本（推荐）
```bash
cd /Users/kevin/workspace/financial-ai
./start_all_services.sh
```

脚本会自动：
- ✅ 停止旧服务
- ✅ 启动 finance-mcp（端口 3335）
- ✅ 启动 data-agent（端口 8100）
- ✅ 启动 finance-web（端口 5173）
- ✅ 验证服务状态
- ✅ 显示访问地址和日志路径

### 方式二：手动启动

**终端 1 - finance-mcp:**
```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
cd finance-mcp
python unified_mcp_server.py
```

**终端 2 - data-agent:**
```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
cd finance-agents/data-agent
python -m app.server
```

**终端 3 - finance-web:**
```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

---

## 🛑 停止服务

### 停止所有服务
```bash
lsof -ti:3335,8100,5173 | xargs kill -9
```

### 停止单个服务
```bash
# 停止 finance-mcp
lsof -ti:3335 | xargs kill -9

# 停止 data-agent
lsof -ti:8100 | xargs kill -9

# 停止 finance-web
lsof -ti:5173 | xargs kill -9
```

---

## 📊 检查服务状态

### 查看运行的服务
```bash
lsof -i:3335,8100,5173 | grep LISTEN
```

### 测试服务健康
```bash
# data-agent 健康检查
curl http://localhost:8100/health

# finance-web 首页
curl http://localhost:5173

# finance-mcp（如果有健康端点）
curl http://localhost:3335/health
```

---

## 📋 查看日志

### 使用自动脚本启动的日志
```bash
# 实时查看 finance-mcp 日志
tail -f logs/finance-mcp.log

# 实时查看 data-agent 日志
tail -f logs/data-agent.log

# 实时查看 finance-web 日志
tail -f logs/finance-web.log
```

### 手动启动的日志
日志会直接显示在启动服务的终端窗口中。

---

## 🔧 常见问题排查

### 1. 端口被占用
**现象：** 启动失败，提示 "Address already in use"

**解决：**
```bash
# 查看占用端口的进程
lsof -i:8100  # 替换为实际端口号

# 杀死进程
lsof -ti:8100 | xargs kill -9
```

### 2. 依赖缺失
**现象：** `ModuleNotFoundError: No module named 'xxx'`

**解决：**
```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pip install <missing-package>

# 然后重启服务
```

### 3. 虚拟环境问题
**现象：** 各种导入错误

**解决：** 确保使用根虚拟环境
```bash
# 检查当前虚拟环境
which python
# 应该输出: /Users/kevin/workspace/financial-ai/.venv/bin/python

# 如果不是，重新激活
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
```

### 4. data-agent 无法调用 finance-mcp
**现象：** "MCP 工具调用未实现" 或 "ModuleNotFoundError: No module named 'reconciliation'"

**检查清单：**
1. ✅ finance-mcp 是否在运行？（端口 3335）
2. ✅ data-agent 是否使用根虚拟环境启动？
3. ✅ sys.path 是否正确？（查看日志中的 "MCP root path"）

**验证：**
```bash
# 查看 data-agent 日志
tail -20 logs/data-agent.log | grep "MCP root path"
# 应该看到: MCP root path: /Users/kevin/workspace/financial-ai/finance-mcp
```

---

## 🧪 测试功能

### 1. 测试文件上传
```bash
# 创建测试文件
echo "日期,订单号,金额
2024-01-01,A001,100.00
2024-01-02,A002,200.00" > /tmp/test.csv

# 上传文件
curl -X POST http://localhost:8100/upload \
  -F "file=@/tmp/test.csv" \
  -F "thread_id=test_123"

# 期望返回: {"file_path":"...","filename":"test.csv","size":...}
```

### 2. 测试 WebSocket 连接
```javascript
// 在浏览器控制台执行
const ws = new WebSocket('ws://localhost:5173/chat');
ws.onopen = () => console.log('✅ WebSocket 连接成功');
ws.onmessage = (e) => console.log('📨 收到消息:', JSON.parse(e.data));
ws.send(JSON.stringify({
  type: 'message',
  content: '你好',
  thread_id: 'test'
}));
```

---

## 📦 虚拟环境说明

### 当前架构
```
financial-ai/
├── .venv/                          # ✅ 根虚拟环境（主环境）
│   ├── mcp                         # MCP 协议库
│   ├── simpleeval                  # 表达式求值
│   ├── fastapi, langgraph, ...     # data-agent 依赖
│   └── pandas, openpyxl, ...       # 通用依赖
├── finance-mcp/                    # 使用根 .venv
├── finance-agents/data-agent/      # 使用根 .venv
│   └── .venv/                      # ⚠️ 已废弃，不再使用
└── finance-web/                    # 独立的 npm 环境
```

### 依赖管理
- ✅ **所有 Python 服务**使用 **根虚拟环境** (`.venv`)
- ✅ 添加新依赖时，在根环境安装：
  ```bash
  cd /Users/kevin/workspace/financial-ai
  source .venv/bin/activate
  pip install <package-name>
  ```

---

## 🎯 访问地址

| 服务 | 端口 | 地址 | 用途 |
|------|------|------|------|
| **finance-web** | 5173 | http://localhost:5173 | 用户界面 |
| **data-agent** | 8100 | http://localhost:8100 | API 服务 |
| **finance-mcp** | 3335 | http://localhost:3335 | MCP 工具服务 |

---

## 📝 开发流程

### 修改代码后
1. ✅ 停止相关服务
2. ✅ 修改代码
3. ✅ 如有新依赖，安装到根环境
4. ✅ 重启服务
5. ✅ 测试功能

**快捷命令：**
```bash
# 停止、重启、验证一条龙
lsof -ti:3335,8100,5173 | xargs kill -9 && \
./start_all_services.sh
```

---

## 🔍 调试技巧

### 1. 查看实时日志
```bash
# 使用 tmux 同时查看多个日志
tmux new-session \; \
  split-window -h \; \
  split-window -v \; \
  select-pane -t 0 \; \
  send-keys 'tail -f logs/finance-mcp.log' C-m \; \
  select-pane -t 1 \; \
  send-keys 'tail -f logs/data-agent.log' C-m \; \
  select-pane -t 2 \; \
  send-keys 'tail -f logs/finance-web.log' C-m
```

### 2. 过滤日志
```bash
# 只看错误
tail -f logs/data-agent.log | grep -i "error\|exception"

# 只看 MCP 调用
tail -f logs/data-agent.log | grep -i "mcp"

# 只看文件上传
tail -f logs/data-agent.log | grep -i "upload\|file"
```

### 3. 查看进程详情
```bash
# 查看服务进程
ps aux | grep -E "unified_mcp_server|app.server|vite"

# 查看端口监听
netstat -an | grep -E "3335|8100|5173"
```

---

## 📚 相关文档

- `FINAL_BUGFIX_SUMMARY.md` - 最新修复总结
- `BUGFIX_STREAMING_AND_UPLOAD.md` - 流式输出和文件上传详解
- `SERVICE_RESTART_GUIDE.md` - 服务重启指南

---

**最后更新：** 2026-02-11  
**系统状态：** ✅ 所有功能正常
