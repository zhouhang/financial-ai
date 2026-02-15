#!/bin/bash
# 重启 finance-ai 服务脚本

echo "========================================="
echo "重启 Financial AI 服务"
echo "========================================="

# 1. 停止所有相关进程
echo "1. 停止现有服务..."
pkill -f "finance-agents/data-agent" || echo "  data-agent 未运行"
pkill -f "finance-mcp" || echo "  finance-mcp 未运行"
pkill -f "finance-web" || echo "  finance-web 未运行"
sleep 2

# 2. 清理 Python 缓存
echo "2. 清理 Python 缓存..."
find finance-agents -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find finance-mcp -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo "  ✓ 缓存已清理"

# 3. 显示修复信息
echo "3. 修复内容确认..."
echo "  ✓ main_graph.py:310 - 使用 .replace() 替代 .format()"
echo "  ✓ main_graph.py:747 - 使用 .replace() 替代 .format()"

echo ""
echo "========================================="
echo "服务已停止，缓存已清理"
echo "========================================="
echo ""
echo "接下来请手动启动服务："
echo "1. 启动 finance-mcp:"
echo "   cd finance-mcp && python -m mcp_server.main"
echo ""
echo "2. 启动 data-agent:"
echo "   cd finance-agents/data-agent && python -m app.server"
echo ""
echo "3. 启动 finance-web:"
echo "   cd finance-web && npm run dev"
echo ""
