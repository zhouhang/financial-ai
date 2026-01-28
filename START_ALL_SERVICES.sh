#!/bin/bash
# 启动所有服务的脚本

echo "=========================================="
echo "  Finance AI - 启动所有服务"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${RED}✗ 端口 $port 已被占用${NC}"
        return 1
    else
        echo -e "${GREEN}✓ 端口 $port 可用${NC}"
        return 0
    fi
}

# 检查所有端口
echo "1. 检查端口状态..."
check_port 8000 || exit 1
check_port 3335 || exit 1
check_port 5173 || exit 1
echo ""

# 检查数据库
echo "2. 检查数据库连接..."
if mysql -h 127.0.0.1 -u aiuser -p123456 -e "USE finance-ai;" 2>/dev/null; then
    echo -e "${GREEN}✓ 数据库连接成功${NC}"
else
    echo -e "${RED}✗ 数据库连接失败，请检查 MySQL 服务${NC}"
    exit 1
fi
echo ""

# 启动 finance-mcp API 服务器
echo "3. 启动 finance-mcp API 服务器 (端口 8000)..."
cd /Users/kevin/workspace/financial-ai/finance-mcp
python3 api_server.py > /tmp/finance-mcp-api.log 2>&1 &
API_PID=$!
echo "   PID: $API_PID"
sleep 3

# 检查 API 服务器是否启动成功
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API 服务器启动成功${NC}"
else
    echo -e "${RED}✗ API 服务器启动失败${NC}"
    kill $API_PID 2>/dev/null
    exit 1
fi
echo ""

# 启动 finance-mcp MCP 服务器
echo "4. 启动 finance-mcp MCP 服务器 (端口 3335)..."
cd /Users/kevin/workspace/financial-ai/finance-mcp
python3 unified_mcp_server.py > /tmp/finance-mcp-mcp.log 2>&1 &
MCP_PID=$!
echo "   PID: $MCP_PID"
sleep 3
echo -e "${GREEN}✓ MCP 服务器启动成功${NC}"
echo ""

# 启动 finance-ui 前端
echo "5. 启动 finance-ui 前端 (端口 5173)..."
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev > /tmp/finance-ui.log 2>&1 &
UI_PID=$!
echo "   PID: $UI_PID"
sleep 5

# 检查前端是否启动成功
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 前端启动成功${NC}"
else
    echo -e "${YELLOW}⚠ 前端可能需要更多时间启动，请稍后访问 http://localhost:5173${NC}"
fi
echo ""

# 显示服务状态
echo "=========================================="
echo "  所有服务已启动"
echo "=========================================="
echo ""
echo "服务地址:"
echo "  - finance-mcp API:  http://localhost:8000"
echo "  - API 文档:         http://localhost:8000/docs"
echo "  - finance-mcp MCP:  http://localhost:3335"
echo "  - finance-ui:       http://localhost:5173"
echo ""
echo "进程 ID:"
echo "  - API Server:  $API_PID"
echo "  - MCP Server:  $MCP_PID"
echo "  - Frontend:    $UI_PID"
echo ""
echo "日志文件:"
echo "  - API:  /tmp/finance-mcp-api.log"
echo "  - MCP:  /tmp/finance-mcp-mcp.log"
echo "  - UI:   /tmp/finance-ui.log"
echo ""
echo "停止所有服务:"
echo "  kill $API_PID $MCP_PID $UI_PID"
echo ""
echo -e "${GREEN}按 Ctrl+C 停止所有服务${NC}"
echo ""

# 保存 PID 到文件
echo "$API_PID" > /tmp/finance-api.pid
echo "$MCP_PID" > /tmp/finance-mcp.pid
echo "$UI_PID" > /tmp/finance-ui.pid

# 等待用户中断
trap "echo ''; echo '停止所有服务...'; kill $API_PID $MCP_PID $UI_PID 2>/dev/null; rm -f /tmp/finance-*.pid; echo '所有服务已停止'; exit 0" INT

# 持续显示日志
echo "=========================================="
echo "  实时日志 (Ctrl+C 停止)"
echo "=========================================="
echo ""

tail -f /tmp/finance-mcp-api.log /tmp/finance-mcp-mcp.log /tmp/finance-ui.log
