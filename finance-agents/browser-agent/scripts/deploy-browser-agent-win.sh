#!/usr/bin/env bash
# 从 mac 开发环境一键部署 browser-agent 到 Windows 采集机(同内网 SSH 直连)。
#
#   流程:本地冒烟测试 → 打包(排除 .venv/.env/logs)→ scp 到 win → 更新依赖 → 干净重启 → 校验
#
#   用法:
#     scripts/deploy-browser-agent-win.sh                 # 部署到默认 collector-win-1
#     WIN_HOST=Administrator@10.0.80.75 scripts/deploy-browser-agent-win.sh
#     SKIP_TESTS=1 scripts/deploy-browser-agent-win.sh    # 跳过本地测试(CI 已跑过时)
#
#   依赖:mac 自带 ssh/scp/tar;win 自带 tar.exe、OpenSSH、已有 C:\tally\browser-agent\.venv 与 .env。
set -euo pipefail

WIN_HOST="${WIN_HOST:-Administrator@10.0.80.75}"
WIN_ROOT='C:\tally\browser-agent'
WIN_TMP='C:\tally\_deploy'
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
TARBALL="/tmp/browser-agent-${TS}.tar.gz"

cd "$AGENT_DIR"
echo "==> 部署源: $AGENT_DIR"
echo "==> 目标:  $WIN_HOST : $WIN_ROOT"

# 1) 本地冒烟测试(跨平台子集,缓存 venv 复用)
SMOKE_TESTS=(tests/test_data_agent_ws.py tests/test_tally_client.py tests/test_service_config.py)
PRESENT_TESTS=()
for t in "${SMOKE_TESTS[@]}"; do [[ -f "$t" ]] && PRESENT_TESTS+=("$t"); done

if [[ "${SKIP_TESTS:-0}" == "1" ]]; then
  echo "==> 跳过本地测试(SKIP_TESTS=1)"
elif [[ ${#PRESENT_TESTS[@]} -eq 0 ]]; then
  # test_*.py 按约定不入库(.gitignore 的 *TEST*),clean clone 上本就不存在。
  # 这种情况优雅跳过冒烟门、不当作失败 —— 否则会让 pre-push 误报"部署失败"并(strict 下)阻断 push。
  echo "==> 未发现本地 test_*.py(按约定不提交 git),跳过冒烟测试"
else
  GATE_VENV="$HOME/.cache/tally-browser-agent-gate-venv"
  if [[ ! -x "$GATE_VENV/bin/python" ]]; then
    echo "==> 首次创建测试 venv: $GATE_VENV"
    python3 -m venv "$GATE_VENV"
    "$GATE_VENV/bin/pip" install -q --upgrade pip
    "$GATE_VENV/bin/pip" install -q pytest pytest-asyncio websockets PyJWT httpx
  fi
  echo "==> 本地冒烟测试(轻量单元子集,不拉 playwright/win32): ${PRESENT_TESTS[*]}"
  # 仅纯单元测试;需 playwright/真实浏览器的集成测试由 CI(windows-latest)或采集机覆盖。
  "$GATE_VENV/bin/python" -m pytest -q "${PRESENT_TESTS[@]}"
fi

# 2) 打包(排除运行态/机器本地内容)
echo "==> 打包 $TARBALL"
tar --exclude='./.venv' --exclude='./.env' --exclude='./logs' \
    --exclude='./__pycache__' --exclude='*.pyc' --exclude='./.pytest_cache' \
    --exclude='./tests/__pycache__' --exclude='*/__pycache__' \
    -czf "$TARBALL" -C "$AGENT_DIR" .

# 3) 上传并在 win 上展开 + 更新依赖 + 重启
echo "==> 上传到 $WIN_HOST"
ssh "$WIN_HOST" "if not exist \"$WIN_TMP\" mkdir \"$WIN_TMP\""
scp -q "$TARBALL" "$WIN_HOST:$WIN_TMP\\agent.tar.gz"

echo "==> win:解包(保留 .env/.venv/logs)"
ssh "$WIN_HOST" "tar -xzf \"$WIN_TMP\\agent.tar.gz\" -C \"$WIN_ROOT\""

echo "==> win:同步依赖 requirements.txt"
ssh "$WIN_HOST" "\"$WIN_ROOT\\.venv\\Scripts\\python.exe\" -m pip install -q -r \"$WIN_ROOT\\requirements.txt\""

echo "==> win:干净重启(单实例)"
ssh "$WIN_HOST" "powershell -NoProfile -ExecutionPolicy Bypass -File \"$WIN_ROOT\\scripts\\win\\manage-browser-agent.ps1\" -Action Restart"

# 4) 校验:进程在 + 日志出现重连
echo "==> win:状态校验"
ssh "$WIN_HOST" "powershell -NoProfile -ExecutionPolicy Bypass -File \"$WIN_ROOT\\scripts\\win\\manage-browser-agent.ps1\" -Action Status"
echo "==> win:最近日志"
ssh "$WIN_HOST" "powershell -NoProfile -Command \"Get-Content '$WIN_ROOT\\logs\\browser-agent.log' -Tail 8\""

rm -f "$TARBALL"
echo "==> 部署完成。请确认日志中出现『browser-agent 启动』与『data-agent WS 已连接』,"
echo "    并在云端确认 collector-win-1 心跳已恢复在线。"
