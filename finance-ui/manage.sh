#!/bin/bash

# Finance-UI 服务管理脚本
# 用于启动、停止、重启和查看服务状态

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目路径
PROJECT_DIR="/Users/kevin/workspace/financial-ai/finance-ui"
BACKEND_DIR="$PROJECT_DIR/backend"

# PID 文件
FRONTEND_PID_FILE="$PROJECT_DIR/.frontend.pid"
BACKEND_PID_FILE="$PROJECT_DIR/.backend.pid"

# 日志文件
FRONTEND_LOG="$PROJECT_DIR/frontend.log"
BACKEND_LOG="$BACKEND_DIR/backend.log"

# 显示帮助信息
show_help() {
    echo "=================================="
    echo "Finance-UI 服务管理脚本"
    echo "=================================="
    echo ""
    echo "用法: ./manage.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start       - 启动所有服务"
    echo "  stop        - 停止所有服务"
    echo "  restart     - 重启所有服务"
    echo "  status      - 查看服务状态"
    echo "  logs        - 查看实时日志"
    echo "  test        - 测试服务是否正常"
    echo "  clean       - 清理日志文件"
    echo "  help        - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  ./manage.sh start    # 启动服务"
    echo "  ./manage.sh status   # 查看状态"
    echo "  ./manage.sh logs     # 查看日志"
    echo ""
}

# 检查服务是否运行
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# 启动前端服务
start_frontend() {
    echo -e "${BLUE}启动前端服务...${NC}"

    if is_running "$FRONTEND_PID_FILE"; then
        echo -e "${YELLOW}前端服务已在运行中${NC}"
        return
    fi

    cd "$PROJECT_DIR"

    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}安装前端依赖...${NC}"
        npm install
    fi

    # 启动前端
    nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
    local pid=$!
    echo $pid > "$FRONTEND_PID_FILE"

    sleep 3

    if is_running "$FRONTEND_PID_FILE"; then
        echo -e "${GREEN}✓ 前端服务启动成功 (PID: $pid)${NC}"
        echo -e "${GREEN}  访问地址: http://localhost:5173${NC}"
    else
        echo -e "${RED}✗ 前端服务启动失败${NC}"
        echo -e "${RED}  查看日志: tail -f $FRONTEND_LOG${NC}"
    fi
}

# 启动后端服务
start_backend() {
    echo -e "${BLUE}启动后端服务...${NC}"

    if is_running "$BACKEND_PID_FILE"; then
        echo -e "${YELLOW}后端服务已在运行中${NC}"
        return
    fi

    cd "$BACKEND_DIR"

    # 检查 Python 依赖
    if ! python3 -c "import fastapi" 2>/dev/null; then
        echo -e "${YELLOW}安装后端依赖...${NC}"
        pip3 install -r requirements.txt
    fi

    # 检查数据库
    if ! python3 -c "from database import engine; engine.connect()" 2>/dev/null; then
        echo -e "${YELLOW}初始化数据库...${NC}"
        python3 init_db.py
    fi

    # 启动后端
    nohup python3 main.py > "$BACKEND_LOG" 2>&1 &
    local pid=$!
    echo $pid > "$BACKEND_PID_FILE"

    sleep 3

    if is_running "$BACKEND_PID_FILE"; then
        echo -e "${GREEN}✓ 后端服务启动成功 (PID: $pid)${NC}"
        echo -e "${GREEN}  访问地址: http://localhost:8000${NC}"
        echo -e "${GREEN}  API 文档: http://localhost:8000/docs${NC}"
    else
        echo -e "${RED}✗ 后端服务启动失败${NC}"
        echo -e "${RED}  查看日志: tail -f $BACKEND_LOG${NC}"
    fi
}

# 停止前端服务
stop_frontend() {
    echo -e "${BLUE}停止前端服务...${NC}"

    if is_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        kill $pid 2>/dev/null
        rm -f "$FRONTEND_PID_FILE"
        echo -e "${GREEN}✓ 前端服务已停止${NC}"
    else
        echo -e "${YELLOW}前端服务未运行${NC}"
    fi
}

# 停止后端服务
stop_backend() {
    echo -e "${BLUE}停止后端服务...${NC}"

    if is_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        kill $pid 2>/dev/null
        rm -f "$BACKEND_PID_FILE"
        echo -e "${GREEN}✓ 后端服务已停止${NC}"
    else
        echo -e "${YELLOW}后端服务未运行${NC}"
    fi
}

# 启动所有服务
start_all() {
    echo "=================================="
    echo "启动 Finance-UI 服务"
    echo "=================================="
    echo ""

    start_backend
    echo ""
    start_frontend

    echo ""
    echo "=================================="
    echo -e "${GREEN}服务启动完成！${NC}"
    echo "=================================="
    echo ""
    echo "访问地址:"
    echo "  前端: http://localhost:5173"
    echo "  后端: http://localhost:8000"
    echo "  文档: http://localhost:8000/docs"
    echo ""
}

# 停止所有服务
stop_all() {
    echo "=================================="
    echo "停止 Finance-UI 服务"
    echo "=================================="
    echo ""

    stop_frontend
    stop_backend

    echo ""
    echo "=================================="
    echo -e "${GREEN}所有服务已停止${NC}"
    echo "=================================="
    echo ""
}

# 重启所有服务
restart_all() {
    echo "=================================="
    echo "重启 Finance-UI 服务"
    echo "=================================="
    echo ""

    stop_all
    sleep 2
    start_all
}

# 查看服务状态
show_status() {
    echo "=================================="
    echo "Finance-UI 服务状态"
    echo "=================================="
    echo ""

    # 前端状态
    echo -n "前端服务: "
    if is_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        echo -e "${GREEN}运行中${NC} (PID: $pid)"
        echo "  地址: http://localhost:5173"

        # 测试前端是否可访问
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 | grep -q "200"; then
            echo -e "  状态: ${GREEN}可访问${NC}"
        else
            echo -e "  状态: ${RED}无法访问${NC}"
        fi
    else
        echo -e "${RED}未运行${NC}"
    fi

    echo ""

    # 后端状态
    echo -n "后端服务: "
    if is_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        echo -e "${GREEN}运行中${NC} (PID: $pid)"
        echo "  地址: http://localhost:8000"
        echo "  文档: http://localhost:8000/docs"

        # 测试后端是否可访问
        if curl -s http://localhost:8000/health | grep -q "healthy"; then
            echo -e "  状态: ${GREEN}健康${NC}"
        else
            echo -e "  状态: ${RED}异常${NC}"
        fi
    else
        echo -e "${RED}未运行${NC}"
    fi

    echo ""

    # 数据库状态
    echo -n "数据库: "
    if mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 -e "USE \`finance-ai\`" 2>/dev/null; then
        echo -e "${GREEN}已连接${NC}"
        echo "  地址: mysql://127.0.0.1:3306/finance-ai"
    else
        echo -e "${RED}无法连接${NC}"
    fi

    echo ""
    echo "=================================="
}

# 查看实时日志
show_logs() {
    echo "=================================="
    echo "查看实时日志 (Ctrl+C 退出)"
    echo "=================================="
    echo ""

    if [ -f "$FRONTEND_LOG" ] && [ -f "$BACKEND_LOG" ]; then
        tail -f "$FRONTEND_LOG" "$BACKEND_LOG"
    elif [ -f "$FRONTEND_LOG" ]; then
        tail -f "$FRONTEND_LOG"
    elif [ -f "$BACKEND_LOG" ]; then
        tail -f "$BACKEND_LOG"
    else
        echo -e "${YELLOW}没有找到日志文件${NC}"
    fi
}

# 测试服务
test_services() {
    echo "=================================="
    echo "测试 Finance-UI 服务"
    echo "=================================="
    echo ""

    # 测试后端健康检查
    echo -n "测试后端健康检查... "
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo -e "${GREEN}✓ 通过${NC}"
    else
        echo -e "${RED}✗ 失败${NC}"
    fi

    # 测试前端访问
    echo -n "测试前端访问... "
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 | grep -q "200"; then
        echo -e "${GREEN}✓ 通过${NC}"
    else
        echo -e "${RED}✗ 失败${NC}"
    fi

    # 测试 API 文档
    echo -n "测试 API 文档... "
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs | grep -q "200"; then
        echo -e "${GREEN}✓ 通过${NC}"
    else
        echo -e "${RED}✗ 失败${NC}"
    fi

    # 测试数据库连接
    echo -n "测试数据库连接... "
    if mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 -e "USE \`finance-ai\`" 2>/dev/null; then
        echo -e "${GREEN}✓ 通过${NC}"
    else
        echo -e "${RED}✗ 失败${NC}"
    fi

    echo ""
    echo "=================================="
}

# 清理日志文件
clean_logs() {
    echo "=================================="
    echo "清理日志文件"
    echo "=================================="
    echo ""

    if [ -f "$FRONTEND_LOG" ]; then
        rm -f "$FRONTEND_LOG"
        echo -e "${GREEN}✓ 前端日志已清理${NC}"
    fi

    if [ -f "$BACKEND_LOG" ]; then
        rm -f "$BACKEND_LOG"
        echo -e "${GREEN}✓ 后端日志已清理${NC}"
    fi

    echo ""
    echo "=================================="
}

# 主函数
main() {
    case "$1" in
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            restart_all
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        test)
            test_services
            ;;
        clean)
            clean_logs
            ;;
        help|--help|-h|"")
            show_help
            ;;
        *)
            echo -e "${RED}错误: 未知命令 '$1'${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
