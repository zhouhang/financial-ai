#!/bin/bash

echo "=========================================="
echo "  Finance AI - 停止所有服务"
echo "=========================================="
echo ""

stop_pid_file() {
  local name=$1
  local pid_file=$2

  if [ ! -f "$pid_file" ]; then
    return
  fi

  local pid
  pid=$(cat "$pid_file")
  if kill -0 "$pid" 2>/dev/null; then
    echo "停止 $name (PID: $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pid_file"
}

stop_pid_file "finance-cron" "/tmp/finance-cron.pid"

for port in 3335 8100 5173; do
  pid=$(lsof -ti:$port 2>/dev/null)
  if [ ! -z "$pid" ]; then
    echo "清理端口 $port (PID: $pid)..."
    kill -9 $pid 2>/dev/null || true
  fi
done

echo ""
echo "所有服务已停止"
