#!/bin/bash
# 启动所有服务（使用根虚拟环境）

set -e  # 遇到错误立即退出

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
TRACE_LANGSMITH_MODE="${TRACE_LANGSMITH:-0}"

for arg in "$@"; do
    case "$arg" in
        --trace-langsmith)
            TRACE_LANGSMITH_MODE="1"
            ;;
        --no-trace-langsmith)
            TRACE_LANGSMITH_MODE="0"
            ;;
        --help|-h)
            cat <<'EOF'
用法：
  ./START_ALL_SERVICES.sh
  TRACE_LANGSMITH=1 ./START_ALL_SERVICES.sh
  ./START_ALL_SERVICES.sh --trace-langsmith

说明：
  - 默认关闭 LangSmith tracing，避免本地网络波动拖慢 data-agent 的 skill 请求。
  - 需要调试 LangGraph / DeepAgent / skill 细节时，再显式开启 tracing。
EOF
            exit 0
            ;;
    esac
done

load_project_env() {
    set -a
    [ -f "$PROJECT_ROOT/.env" ] && source "$PROJECT_ROOT/.env"
    set +a
}

configure_langsmith_env() {
    if [ "$TRACE_LANGSMITH_MODE" = "1" ]; then
        export LANGSMITH_TRACING=true
        export LANGCHAIN_TRACING_V2=true
        export TRACE_LANGSMITH=1
        return
    fi

    export LANGSMITH_TRACING=false
    export LANGCHAIN_TRACING_V2=false
    export TRACE_LANGSMITH=0
}

start_detached() {
    local log_file="$1"
    local work_dir="$2"
    shift 2
    python - "$log_file" "$work_dir" "$@" <<'PY'
import os
import subprocess
import sys

log_path = sys.argv[1]
work_dir = sys.argv[2]
cmd = sys.argv[3:]
log_file = open(log_path, "ab", buffering=0)
process = subprocess.Popen(
    cmd,
    cwd=work_dir,
    stdin=subprocess.DEVNULL,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    env=os.environ.copy(),
)
print(process.pid)
PY
}

# 创建日志目录
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "🚀 启动 Financial AI 服务"
echo "=========================================="
echo "🔎 LangSmith tracing: $([ "$TRACE_LANGSMITH_MODE" = "1" ] && echo "开启" || echo "关闭")"

# 停止现有服务
echo ""
echo "📌 步骤 1: 停止现有服务..."
lsof -ti:3335,8100,5173 | xargs kill -9 2>/dev/null || true
[ -f /tmp/finance-cron.pid ] && kill -9 "$(cat /tmp/finance-cron.pid)" 2>/dev/null || true
rm -f /tmp/finance-cron.pid
# 停止已有的 recon-worker 进程
if [ -f /tmp/recon-workers.pids ]; then
    while IFS= read -r pid; do
        kill -9 "$pid" 2>/dev/null || true
    done < /tmp/recon-workers.pids
    rm -f /tmp/recon-workers.pids
fi
sleep 2
echo "✅ 现有服务已停止"

# 启动 finance-mcp
echo ""
echo "📌 步骤 2: 启动 finance-mcp (端口 3335)..."
cd "$PROJECT_ROOT"
source .venv/bin/activate
load_project_env
FINANCE_MCP_PID="$(start_detached "$LOG_DIR/finance-mcp.log" "$PROJECT_ROOT/finance-mcp" python unified_mcp_server.py)"
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
load_project_env
# 在 Python 启动前导出 LangSmith 环境变量（必须在进程启动时已存在，否则 LangSmith 追踪不生效）
[ -f .env ] && source .env
configure_langsmith_env
DATA_AGENT_PID="$(start_detached "$LOG_DIR/data-agent.log" "$PROJECT_ROOT/finance-agents/data-agent" python -m server)"
echo "✅ data-agent 已启动 (PID: $DATA_AGENT_PID)"

# 等待 data-agent 启动
sleep 3

# 启动 finance-cron
echo ""
echo "📌 步骤 4: 启动 finance-cron..."
cd "$PROJECT_ROOT"
source .venv/bin/activate
load_project_env
FINANCE_CRON_PID="$(start_detached "$LOG_DIR/finance-cron.log" "$PROJECT_ROOT" python finance-cron/run_scheduler.py --config finance-cron/config/cron_config.yaml)"
echo "$FINANCE_CRON_PID" > /tmp/finance-cron.pid
echo "✅ finance-cron 已启动 (PID: $FINANCE_CRON_PID)"

# 等待 finance-cron 启动
sleep 2

# 启动 recon-worker（默认 4 个进程，可通过 RECON_WORKER_COUNT 覆盖）
echo ""
RECON_WORKER_COUNT="${RECON_WORKER_COUNT:-4}"
echo "📌 步骤 5: 启动 recon-worker × ${RECON_WORKER_COUNT}..."
cd "$PROJECT_ROOT"
source .venv/bin/activate
load_project_env
> /tmp/recon-workers.pids
for i in $(seq 1 "$RECON_WORKER_COUNT"); do
    WORKER_PID="$(start_detached "$LOG_DIR/recon-worker-${i}.log" "$PROJECT_ROOT/finance-agents/data-agent" python recon_worker.py)"
    echo "$WORKER_PID" >> /tmp/recon-workers.pids
    echo "  ✅ recon-worker-${i} 已启动 (PID: $WORKER_PID)"
done

# 启动 finance-web
echo ""
echo "📌 步骤 6: 启动 finance-web (端口 5173)..."
FINANCE_WEB_PID="$(start_detached "$LOG_DIR/finance-web.log" "$PROJECT_ROOT/finance-web" npm run dev)"
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

# 检查 finance-cron
if [ -f /tmp/finance-cron.pid ] && kill -0 "$(cat /tmp/finance-cron.pid)" 2>/dev/null; then
    echo "✅ finance-cron  (scheduler) - 运行正常"
else
    echo "❌ finance-cron  (scheduler) - 启动失败"
    SERVICES_OK=false
fi

# 检查 recon-worker
WORKER_ALIVE=0
if [ -f /tmp/recon-workers.pids ]; then
    while IFS= read -r pid; do
        kill -0 "$pid" 2>/dev/null && WORKER_ALIVE=$((WORKER_ALIVE + 1))
    done < /tmp/recon-workers.pids
fi
if [ "$WORKER_ALIVE" -ge 1 ]; then
    echo "✅ recon-worker  (×${WORKER_ALIVE}) - 运行正常"
else
    echo "❌ recon-worker  - 启动失败"
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
    echo "   - finance-mcp:    tail -f $LOG_DIR/finance-mcp.log"
    echo "   - data-agent:     tail -f $LOG_DIR/data-agent.log"
    echo "   - finance-cron:   tail -f $LOG_DIR/finance-cron.log"
    echo "   - recon-worker-1: tail -f $LOG_DIR/recon-worker-1.log"
    echo "   - finance-web:    tail -f $LOG_DIR/finance-web.log"
    echo ""
    echo "🧭 LangSmith 调试："
    echo "   - 默认关闭 tracing：./START_ALL_SERVICES.sh"
    echo "   - 显式开启 tracing：TRACE_LANGSMITH=1 ./START_ALL_SERVICES.sh"
    echo "   - 或：./START_ALL_SERVICES.sh --trace-langsmith"
    echo ""
    echo "🛑 停止所有服务："
    echo "   ./STOP_ALL_SERVICES.sh"
    echo ""
else
    echo "⚠️  部分服务启动失败，请检查日志："
    echo "   ls -lh $LOG_DIR/"
    echo ""
    exit 1
fi
