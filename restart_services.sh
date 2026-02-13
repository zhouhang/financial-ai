#!/bin/bash
# 统一重启所有服务的脚本

echo "正在重启所有服务..."

# 清理端口
echo "1. 清理端口占用..."
lsof -ti:5173 | xargs kill -9 2>/dev/null
lsof -ti:5174 | xargs kill -9 2>/dev/null
lsof -ti:8100 | xargs kill -9 2>/dev/null
sleep 2

# 启动后端服务 (data-agent)
echo "2. 启动后端服务 (8100)..."
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
.venv/bin/python -u -m app.server > /tmp/data-agent.log 2>&1 &
BACKEND_PID=$!

# 启动前端服务 (finance-web)
echo "3. 启动前端服务 (5173)..."
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev > /tmp/finance-web.log 2>&1 &
FRONTEND_PID=$!

# 等待服务启动
echo "4. 等待服务启动..."
sleep 8

# 检查服务状态
echo ""
echo "=== 服务状态 ==="
if curl -s http://localhost:8100/health 2>/dev/null | grep -q ok; then
    echo "✅ 后端服务 (8100) 运行正常"
else
    echo "❌ 后端服务 (8100) 未启动，查看日志: tail -20 /tmp/data-agent.log"
fi

if curl -s http://localhost:5173 2>/dev/null | head -1 | grep -q "html\|<!DOCTYPE"; then
    echo "✅ 前端服务 (5173) 运行正常"
else
    echo "❌ 前端服务 (5173) 未启动，查看日志: tail -20 /tmp/finance-web.log"
fi

echo ""
echo "服务重启完成！"
echo "后端日志: tail -f /tmp/data-agent.log"
echo "前端日志: tail -f /tmp/finance-web.log"
