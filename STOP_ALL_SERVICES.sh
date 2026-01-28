#!/bin/bash
# 停止所有服务的脚本

echo "=========================================="
echo "  Finance AI - 停止所有服务"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 从 PID 文件读取并停止服务
stop_service() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            echo "停止 $name (PID: $pid)..."
            kill $pid 2>/dev/null
            sleep 1
            if kill -0 $pid 2>/dev/null; then
                kill -9 $pid 2>/dev/null
            fi
            echo -e "${GREEN}✓ $name 已停止${NC}"
        else
            echo -e "${RED}✗ $name 进程不存在${NC}"
        fi
        rm -f "$pid_file"
    else
        echo "未找到 $name 的 PID 文件"
    fi
}

# 停止所有服务
stop_service "API Server" "/tmp/finance-api.pid"
stop_service "MCP Server" "/tmp/finance-mcp.pid"
stop_service "Frontend" "/tmp/finance-ui.pid"

# 额外检查端口并清理
echo ""
echo "检查端口占用..."

for port in 8000 3335 5173; do
    pid=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pid" ]; then
        echo "清理端口 $port (PID: $pid)..."
        kill -9 $pid 2>/dev/null
    fi
done

echo ""
echo -e "${GREEN}所有服务已停止${NC}"
