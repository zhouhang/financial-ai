# Finance AI

Financial AI workspace with three active runtime services:

- `finance-web/`: React + Vite frontend. In development it proxies `/api` traffic to `data-agent`.
- `finance-agents/data-agent/`: FastAPI + WebSocket service for chat, upload, auth, conversation history, and internal proc/recon APIs.
- `finance-mcp/`: MCP server exposing auth, file upload, file validation, proc, and recon tools over `/sse` and `/mcp`.

## Quick Start

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Stop services:

```bash
cd /Users/kevin/workspace/financial-ai
./STOP_ALL_SERVICES.sh
```

The startup script launches:

- `finance-mcp` on `3335`
- `data-agent` on `8100`
- `finance-web` on `5173`

## Service URLs

| Service | URL | Purpose |
| --- | --- | --- |
| `finance-web` | http://localhost:5173 | Frontend UI |
| `data-agent` | http://localhost:8100 | Chat/upload/auth/conversation APIs |
| `finance-mcp` | http://localhost:3335 | MCP SSE/MCP server |

## Current Runtime Flow

1. Users access `finance-web` on port `5173`.
2. Vite proxies `/api` HTTP requests and WebSocket traffic to `data-agent` on port `8100`.
3. `data-agent` handles `/chat`, `/upload`, `/auth/*`, `/conversations/*`, `/proc/*`, and `/api/internal/recon/*`.
4. `data-agent` calls `finance-mcp` on port `3335` for MCP tools and file-processing capabilities.

## Key Entry Points

- `finance-web`: `/Users/kevin/workspace/financial-ai/finance-web/src`
- `data-agent`: `/Users/kevin/workspace/financial-ai/finance-agents/data-agent/server.py`
- `finance-mcp`: `/Users/kevin/workspace/financial-ai/finance-mcp/unified_mcp_server.py`
- service startup: `/Users/kevin/workspace/financial-ai/START_ALL_SERVICES.sh`

## Manual Startup

`finance-mcp`

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
cd finance-mcp
python unified_mcp_server.py
```

`data-agent`

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
cd finance-agents/data-agent
python -m server
```

`finance-web`

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

## Logs

```bash
tail -f logs/finance-web.log
tail -f logs/data-agent.log
tail -f logs/finance-mcp.log
```

## Health Checks

```bash
curl http://localhost:8100/health
curl http://localhost:3335/health
```

## Notes

- The current frontend directory is `finance-web`, not `finance-ui`.
- The current `data-agent` entrypoint is `python -m server` from `finance-agents/data-agent`.
- `finance-mcp` is currently the MCP/tool service; the old `finance-mcp/api/` layout is no longer the active runtime path described by this repository.

## Operational Notes

- The actual script names are `START_ALL_SERVICES.sh` and `STOP_ALL_SERVICES.sh`.
- The default Python environment is the root `.venv`.
- `finance-agents/data-agent/.venv` still exists as historical residue, but it is not the main runtime environment.
