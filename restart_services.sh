#!/bin/bash
# 重启所有服务脚本
# 用途：修改代码后，统一重启 data-agent 和 finance-web

set -e  # 遇到错误立即退出

echo "════════════════════════════════════════════════════════════════"
echo "🔄 重启服务脚本"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ── 1. 停止所有服务 ──
echo "📦 步骤 1/3: 停止现有服务..."
echo ""

# 停止 data-agent (端口 8100)
if lsof -ti:8100 > /dev/null 2>&1; then
    lsof -ti:8100 | xargs kill -9 2>/dev/null
    echo "  ✓ 已停止 data-agent (端口 8100)"
else
    echo "  ℹ data-agent 未运行"
fi

# 停止 finance-web (端口 5173)
if lsof -ti:5173 > /dev/null 2>&1; then
    lsof -ti:5173 | xargs kill -9 2>/dev/null
    echo "  ✓ 已停止 finance-web (端口 5173)"
else
    echo "  ℹ finance-web 未运行"
fi

echo ""
sleep 1

# ── 2. 启动 data-agent ──
echo "📦 步骤 2/3: 启动 data-agent..."
echo ""

cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate

# 后台启动
nohup python -m app.server > ../../logs/data-agent.log 2>&1 &
DATA_AGENT_PID=$!

echo "  ✓ data-agent 已启动 (PID: $DATA_AGENT_PID)"
echo "  ℹ 日志: logs/data-agent.log"

sleep 2

# ── 3. 启动 finance-web ──
echo ""
echo "📦 步骤 3/3: 启动 finance-web..."
echo ""

cd /Users/kevin/workspace/financial-ai/finance-web

# 后台启动
nohup npm run dev > ../logs/finance-web.log 2>&1 &
FINANCE_WEB_PID=$!

echo "  ✓ finance-web 已启动 (PID: $FINANCE_WEB_PID)"
echo "  ℹ 日志: logs/finance-web.log"

sleep 3

# ── 4. 验证服务 ──
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ 服务启动完成"
echo "════════════════════════════════════════════════════════════════"
echo ""

# 检查端口
if lsof -ti:8100 > /dev/null 2>&1; then
    echo "  ✓ data-agent 运行中   → http://0.0.0.0:8100"
else
    echo "  ✗ data-agent 启动失败 → 查看 logs/data-agent.log"
fi

if lsof -ti:5173 > /dev/null 2>&1; then
    echo "  ✓ finance-web 运行中  → http://localhost:5173"
else
    echo "  ✗ finance-web 启动失败 → 查看 logs/finance-web.log"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📖 查看日志："
echo "  • data-agent:  tail -f logs/data-agent.log"
echo "  • finance-web: tail -f logs/finance-web.log"
echo ""
echo "🛑 停止服务："
echo "  • kill $DATA_AGENT_PID (data-agent)"
echo "  • kill $FINANCE_WEB_PID (finance-web)"
echo "  • 或运行: lsof -ti:8100 | xargs kill -9; lsof -ti:5173 | xargs kill -9"
echo "════════════════════════════════════════════════════════════════"
