#!/usr/bin/env bash
# Start browser-agent on a collection machine.
#
# Real secrets should live in .env.browser-agent at the repository root. That
# file is ignored by git via the existing .env.* rule.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${BROWSER_AGENT_ENV_FILE:-$ROOT_DIR/.env.browser-agent}"
PYTHON_BIN="${PYTHON_BIN:-}"

usage() {
  cat <<'EOF'
Usage:
  scripts/start-browser-agent.sh [--check]

Options:
  --check   Run the browser-agent environment readiness check, then exit.

Configuration:
  Copy scripts/browser-agent.env.example to .env.browser-agent and fill the
  production values before starting the agent.
EOF
}

CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --check)
      CHECK_ONLY=1
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

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Missing config file: $ENV_FILE" >&2
  echo "Create it from scripts/browser-agent.env.example." >&2
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
export PYTHONPATH="$ROOT_DIR/finance-agents/browser-agent${PYTHONPATH:+:$PYTHONPATH}"

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

cd "$ROOT_DIR/finance-agents/browser-agent"

if [ "$CHECK_ONLY" = "1" ]; then
  exec "$PYTHON_BIN" scripts/check_environment.py
fi

echo "Starting browser-agent:"
echo "  agent_id=$BROWSER_AGENT_ID"
echo "  company_id=$BROWSER_AGENT_COMPANY_ID"
echo "  ws=$DATA_AGENT_WS_URL"
echo "  channel=$BROWSER_AGENT_BROWSER_CHANNEL headless=$BROWSER_AGENT_HEADLESS"

exec "$PYTHON_BIN" service.py
