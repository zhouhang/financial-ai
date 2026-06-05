#!/usr/bin/env bash
# Start browser-agent on a collection machine.
#
# Real secrets should live in finance-agents/browser-agent/.env. That file is
# ignored by git via the existing **/.env rule.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BROWSER_AGENT_DIR="$ROOT_DIR/finance-agents/browser-agent"
ENV_FILE="${BROWSER_AGENT_ENV_FILE:-$BROWSER_AGENT_DIR/.env}"
PYTHON_BIN="${PYTHON_BIN:-}"
LOG_DIR="${BROWSER_AGENT_LOG_DIR:-$BROWSER_AGENT_DIR/logs}"
LOG_FILE="${BROWSER_AGENT_LOG_FILE:-$LOG_DIR/browser-agent.log}"
PID_FILE="${BROWSER_AGENT_PID_FILE:-$LOG_DIR/browser-agent.pid}"

usage() {
  cat <<'EOF'
Usage:
  scripts/start-browser-agent.sh [--check|--daemon|--stop|--status]

Options:
  --check    Run the browser-agent environment readiness check, then exit.
  --daemon   Start browser-agent in the background with nohup.
  --stop     Stop the background browser-agent started by this script.
  --status   Show background browser-agent status.

Configuration:
  Copy finance-agents/browser-agent/.env.example to finance-agents/browser-agent/.env
  and fill the production values before starting the agent.
EOF
}

CHECK_ONLY=0
DAEMON_MODE=0
STOP_MODE=0
STATUS_MODE=0
for arg in "$@"; do
  case "$arg" in
    --check)
      CHECK_ONLY=1
      ;;
    --daemon)
      DAEMON_MODE=1
      ;;
    --stop)
      STOP_MODE=1
      ;;
    --status)
      STATUS_MODE=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$CHECK_ONLY" -eq 1 ] && { [ "$DAEMON_MODE" -eq 1 ] || [ "$STOP_MODE" -eq 1 ] || [ "$STATUS_MODE" -eq 1 ]; }; then
  echo "--check cannot be combined with --daemon, --stop, or --status." >&2
  exit 2
fi

if [ "$DAEMON_MODE" -eq 1 ] && { [ "$STOP_MODE" -eq 1 ] || [ "$STATUS_MODE" -eq 1 ]; }; then
  echo "--daemon cannot be combined with --stop or --status." >&2
  exit 2
fi

is_running() {
  if [ ! -f "$PID_FILE" ]; then
    return 1
  fi

  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    return 1
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  # Some sandboxed shells return EPERM for kill -0 even when the process exists.
  ps -p "$pid" >/dev/null 2>&1
}

if [ "$STATUS_MODE" -eq 1 ]; then
  if is_running; then
    echo "browser-agent is running: pid=$(cat "$PID_FILE")"
    echo "log=$LOG_FILE"
    exit 0
  fi

  echo "browser-agent is not running"
  exit 1
fi

if [ "$STOP_MODE" -eq 1 ]; then
  if ! is_running; then
    echo "browser-agent is not running"
    rm -f "$PID_FILE"
    exit 0
  fi

  pid="$(cat "$PID_FILE")"
  kill "$pid"
  rm -f "$PID_FILE"
  echo "Stopped browser-agent: pid=$pid"
  exit 0
fi

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Missing config file: $ENV_FILE" >&2
  echo "Create it from finance-agents/browser-agent/.env.example." >&2
  exit 1
fi

if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "Python is required but was not found." >&2
    exit 1
  fi
fi

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
}

require_env DATA_AGENT_WS_URL
require_env JWT_SECRET
require_env BROWSER_AGENT_COMPANY_ID

export BROWSER_AGENT_ID="${BROWSER_AGENT_ID:-browser-agent-$(hostname)}"
export BROWSER_AGENT_RUNNER_MODE="${BROWSER_AGENT_RUNNER_MODE:-playwright}"
export BROWSER_AGENT_BROWSER_CHANNEL="${BROWSER_AGENT_BROWSER_CHANNEL:-chrome}"
export BROWSER_AGENT_HEADLESS="${BROWSER_AGENT_HEADLESS:-0}"
export BROWSER_AGENT_MAX_CONCURRENCY="${BROWSER_AGENT_MAX_CONCURRENCY:-1}"
export BROWSER_AGENT_POLL_INTERVAL_SECONDS="${BROWSER_AGENT_POLL_INTERVAL_SECONDS:-2}"
export BROWSER_AGENT_HEARTBEAT_INTERVAL_SECONDS="${BROWSER_AGENT_HEARTBEAT_INTERVAL_SECONDS:-30}"
export BROWSER_AGENT_TIMEZONE="${BROWSER_AGENT_TIMEZONE:-Asia/Shanghai}"
export PYTHONPATH="$BROWSER_AGENT_DIR${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" - <<'PY'
import importlib
import sys

missing = []
for module in ("jwt", "websockets", "playwright"):
    try:
        importlib.import_module(module)
    except Exception:
        missing.append(module)

if missing:
    print("Missing Python modules: " + ", ".join(missing), file=sys.stderr)
    print("Install them in the selected Python environment:", file=sys.stderr)
    print("  python -m pip install PyJWT websockets playwright", file=sys.stderr)
    print("  python -m playwright install chrome", file=sys.stderr)
    sys.exit(1)
PY

cd "$BROWSER_AGENT_DIR"

if [ "$CHECK_ONLY" = "1" ]; then
  exec "$PYTHON_BIN" scripts/check_environment.py
fi

echo "Starting browser-agent:"
echo "  agent_id=$BROWSER_AGENT_ID"
echo "  company_id=$BROWSER_AGENT_COMPANY_ID"
echo "  ws=$DATA_AGENT_WS_URL"
echo "  channel=$BROWSER_AGENT_BROWSER_CHANNEL headless=$BROWSER_AGENT_HEADLESS"

if [ "$DAEMON_MODE" = "1" ]; then
  mkdir -p "$LOG_DIR"

  if is_running; then
    echo "browser-agent is already running: pid=$(cat "$PID_FILE")"
    echo "log=$LOG_FILE"
    exit 0
  fi

  agent_pid="$("$PYTHON_BIN" - "$LOG_FILE" "$PID_FILE" "$BROWSER_AGENT_DIR" "$PYTHON_BIN" <<'PY'
import os
import subprocess
import sys

log_path, pid_path, work_dir, python_bin = sys.argv[1:]
log_file = open(log_path, "ab", buffering=0)
env = os.environ.copy()
for key in list(env):
    if key.startswith("CODEX_"):
        env.pop(key, None)
process = subprocess.Popen(
    [python_bin, "service.py"],
    cwd=work_dir,
    stdin=subprocess.DEVNULL,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    env=env,
)
with open(pid_path, "w", encoding="utf-8") as handle:
    handle.write(f"{process.pid}\n")
print(process.pid)
PY
)"
  echo "browser-agent started in background: pid=$agent_pid"
  echo "log=$LOG_FILE"
  exit 0
fi

exec "$PYTHON_BIN" service.py
