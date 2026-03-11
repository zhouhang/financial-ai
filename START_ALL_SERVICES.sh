#!/bin/bash
# 启动所有服务（使用根虚拟环境）

set -e  # 遇到错误立即退出

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"

# 创建日志目录
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "🚀 启动 Financial AI 服务"
echo "=========================================="

# 停止现有服务
echo ""
echo "📌 步骤 1: 停止现有服务..."
lsof -ti:3335,8100,5173 | xargs kill -9 2>/dev/null || true
sleep 2
echo "✅ 现有服务已停止"

# 启动 finance-mcp
echo ""
echo "📌 步骤 2: 启动 finance-mcp (端口 3335)..."
cd "$PROJECT_ROOT"
source .venv/bin/activate
cd finance-mcp
nohup python unified_mcp_server.py > "$LOG_DIR/finance-mcp.log" 2>&1 &
FINANCE_MCP_PID=$!
echo "✅ finance-mcp 已启动 (PID: $FINANCE_MCP_PID)"

# 等待 finance-mcp 启动
sleep 3

# 启动 data-agent
# 开发调试：可在 finance-agents/data-agent 目录运行 `pip install -e .` 后执行 `langgraph dev --allow-blocking` 接入 LangSmith Studio（端口 2024）；--allow-blocking 可避免当前代码中 llm.invoke 等同步调用触发的 BlockingError
echo ""
echo "📌 步骤 3: 启动 data-agent (端口 8100)..."
cd "$PROJECT_ROOT"
source .venv/bin/activate
cd finance-agents/data-agent
# 在 Python 启动前导出 LangSmith 环境变量（必须在进程启动时已存在，否则 LangSmith 追踪不生效）
set -a
[ -f .env ] && source .env
set +a
nohup python -m server > "$LOG_DIR/data-agent.log" 2>&1 &
DATA_AGENT_PID=$!
echo "✅ data-agent 已启动 (PID: $DATA_AGENT_PID)"

# 等待 data-agent 启动
sleep 3

# 启动 finance-web
echo ""
echo "📌 步骤 4: 启动 finance-web (端口 5173)..."
cd "$PROJECT_ROOT/finance-web"
nohup npm run dev > "$LOG_DIR/finance-web.log" 2>&1 &
FINANCE_WEB_PID=$!
echo "✅ finance-web 已启动 (PID: $FINANCE_WEB_PID)"

# 等待所有服务完全启动
sleep 5

# 验证服务状态
echo ""
echo "=========================================="
echo "📊 验证服务状态"
echo "=========================================="

SERVICES_OK=true

# 检查 finance-mcp
if lsof -i:3335 > /dev/null 2>&1; then
    echo "✅ finance-mcp   (3335) - 运行正常"
else
    echo "❌ finance-mcp   (3335) - 启动失败"
    SERVICES_OK=false
fi

# 检查 data-agent
if lsof -i:8100 > /dev/null 2>&1; then
    echo "✅ data-agent    (8100) - 运行正常"
else
    echo "❌ data-agent    (8100) - 启动失败"
    SERVICES_OK=false
fi

# 检查 finance-web
if lsof -i:5173 > /dev/null 2>&1; then
    echo "✅ finance-web   (5173) - 运行正常"
else
    echo "❌ finance-web   (5173) - 启动失败"
    SERVICES_OK=false
fi

echo ""
echo "=========================================="

if [ "$SERVICES_OK" = true ]; then
    echo "🎉 所有服务启动成功！"
    echo ""
    echo "📝 访问地址："
    echo "   - 前端界面: http://localhost:5173"
    echo "   - data-agent API: http://localhost:8100"
    echo "   - finance-mcp: http://localhost:3335"
    echo ""
    echo "📋 查看日志："
    echo "   - finance-mcp: tail -f $LOG_DIR/finance-mcp.log"
    echo "   - data-agent:  tail -f $LOG_DIR/data-agent.log"
    echo "   - finance-web: tail -f $LOG_DIR/finance-web.log"
    echo ""
    echo "🛑 停止所有服务："
    echo "   lsof -ti:3335,8100,5173 | xargs kill -9"
    echo ""
else
    echo "⚠️  部分服务启动失败，请检查日志："
    echo "   ls -lh $LOG_DIR/"
    echo ""
    exit 1
fi
