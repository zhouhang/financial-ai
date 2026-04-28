# Technology Stack

**Analysis Date:** 2026-04-22

## Languages

**Primary:**
- Python 3.12+ - backend services in `finance-mcp/requirements.txt`, `finance-agents/data-agent/pyproject.toml`, `finance-cron/requirements.txt`, and `playwright-mcp/requirements.txt`; `finance-agents/data-agent/pyproject.toml` explicitly requires `>=3.12`, and the local interpreter at `.venv/bin/python` reports `Python 3.12.10`.
- TypeScript - frontend application code in `finance-web/src/` compiled with `typescript` `~5.9.3` from `finance-web/package.json`.

**Secondary:**
- JavaScript (ES modules) - build and lint config in `finance-web/vite.config.ts`, `finance-web/eslint.config.js`, and `finance-web/playwright.config.ts`.
- SQL - PostgreSQL schema and seed migrations in `finance-mcp/auth/migrations/001_initial_schema.sql` through `finance-mcp/auth/migrations/014_expand_dataset_bindings_scope_role_constraints.sql`.
- YAML - scheduler config in `finance-cron/config/cron_config.yaml`.
- Markdown/docs - operational and design docs in `docs/`, `AGENTS.md`, and `playwright-mcp/README.md`.

## Runtime

**Environment:**
- Python services run from the shared repo virtualenv in `.venv/`, started by `START_ALL_SERVICES.sh` for `finance-mcp`, `finance-agents/data-agent`, and `finance-cron`.
- Node.js runs the frontend in `finance-web/`; the local environment currently reports `node v23.11.0` and `npm 10.9.2`, but no repo pin file such as `.nvmrc` or `packageManager` field is present.
- Service entrypoints are `finance-mcp/unified_mcp_server.py`, `finance-agents/data-agent/server.py`, `finance-cron/run_scheduler.py`, and `playwright-mcp/mcp_sse_official.py`.

**Package Manager:**
- npm - frontend package manager defined by `finance-web/package.json` with lockfile `finance-web/package-lock.json`.
- pip / setuptools - Python services use `requirements.txt` files in `finance-mcp/`, `finance-cron/`, `playwright-mcp/`, and `finance-agents/data-agent/`; `finance-agents/data-agent/pyproject.toml` uses `setuptools.build_meta`.
- Lockfile: frontend lockfile present at `finance-web/package-lock.json`; no Python lockfile (`poetry.lock`, `Pipfile.lock`, `uv.lock`) detected in the repo root or service directories.

## Frameworks

**Core:**
- FastAPI - API and WebSocket server for the LangGraph agent in `finance-agents/data-agent/server.py`.
- LangGraph + LangChain - agent orchestration and checkpointing in `finance-agents/data-agent/server.py`, `finance-agents/data-agent/graphs/`, and `finance-agents/data-agent/utils/llm.py`.
- MCP Python SDK + Starlette - unified MCP server in `finance-mcp/unified_mcp_server.py` and browser automation MCP service in `playwright-mcp/mcp_sse_official.py`.
- React 19 - frontend UI in `finance-web/package.json` and `finance-web/src/main.tsx`.

**Testing:**
- pytest - backend tests organized in `finance-mcp/tests/`, `finance-agents/data-agent/tests/`, and `finance-cron/tests/`.
- Vitest + Testing Library + jsdom - component tests configured in `finance-web/vitest.config.ts` and located under `finance-web/tests/components/`.
- Playwright - end-to-end frontend tests configured in `finance-web/playwright.config.ts` and located under `finance-web/tests/e2e/`.

**Build/Dev:**
- Vite 7 - frontend dev/build tool in `finance-web/package.json` and `finance-web/vite.config.ts`.
- Tailwind CSS 4 - frontend styling pipeline in `finance-web/package.json` and `finance-web/vite.config.ts`.
- ESLint 9 + typescript-eslint - frontend linting in `finance-web/eslint.config.js`.
- Uvicorn - Python ASGI runtime in `finance-mcp/requirements.txt`, `finance-agents/data-agent/requirements.txt`, and `playwright-mcp/requirements.txt`.
- APScheduler - recurring scheduler in `finance-cron/scheduler_service.py`.

## Key Dependencies

**Critical:**
- `langgraph`, `langgraph-checkpoint-postgres`, `langchain`, `langchain-openai` - core agent runtime in `finance-agents/data-agent/pyproject.toml`.
- `mcp` - tool transport layer in `finance-mcp/requirements.txt`, `playwright-mcp/requirements.txt`, and `finance-mcp/unified_mcp_server.py`.
- `fastapi` - REST/WebSocket layer in `finance-agents/data-agent/requirements.txt` and `finance-agents/data-agent/server.py`.
- `react`, `react-dom` - SPA runtime in `finance-web/package.json`.
- `pandas` and `openpyxl` - spreadsheet ingestion/export in `finance-mcp/recon/mcp_server/recon_tool.py`, `finance-mcp/proc/mcp_server/merge_rule.py`, and `finance-agents/data-agent/requirements.txt`.

**Infrastructure:**
- `psycopg2-binary` and `asyncpg` - PostgreSQL sync/async access in `finance-mcp/db_config.py`, `finance-mcp/auth/db.py`, and `finance-agents/data-agent/server.py`.
- `PyMySQL` - MySQL data-source connector support in `finance-mcp/connectors/providers/database.py`.
- `httpx` and `requests` - outbound HTTP clients in `finance-cron/mcp_client.py`, `finance-cron/data_agent_client.py`, `finance-agents/data-agent/utils/retrieval_api.py`, and `finance-mcp/connectors/providers/api.py`.
- `PyJWT` and `bcrypt` - auth token/password tooling in `finance-mcp/requirements.txt`, `finance-mcp/auth/jwt_utils.py`, and `finance-cron/scheduler_service.py`.
- `python-dotenv` - env loading in `finance-mcp/unified_mcp_server.py`, `finance-agents/data-agent/config.py`, and `finance-cron/run_scheduler.py`.
- `playwright` - browser automation service dependency in `playwright-mcp/requirements.txt`.

## Configuration

**Environment:**
- Root environment file is loaded by `finance-mcp/unified_mcp_server.py`, `finance-agents/data-agent/server.py`, `finance-agents/data-agent/config.py`, `finance-cron/run_scheduler.py`, and `START_ALL_SERVICES.sh`; `.env` is present at repo root but was not read.
- Service-local environment override exists at `finance-agents/data-agent/.env`; the file is present but was not read.
- Database, JWT, LLM, DingTalk, and service base URL settings are defined through environment lookups in `finance-mcp/db_config.py`, `finance-mcp/auth/jwt_utils.py`, `finance-agents/data-agent/config.py`, and `finance-cron/data_agent_client.py`.

**Build:**
- Frontend build config lives in `finance-web/vite.config.ts`, `finance-web/tsconfig.json`, `finance-web/tsconfig.app.json`, `finance-web/tsconfig.node.json`, and `finance-web/eslint.config.js`.
- Frontend test config lives in `finance-web/vitest.config.ts` and `finance-web/playwright.config.ts`.
- Python service startup is coordinated by `START_ALL_SERVICES.sh`; no Dockerfile, `docker-compose.yml`, or `.github/workflows/` pipeline file was detected.

## Platform Requirements

**Development:**
- Local PostgreSQL is required by `finance-mcp/db_config.py` and `finance-agents/data-agent/config.py`; `finance-agents/data-agent/server.py` also creates a dedicated LangGraph checkpoint schema in the same database.
- Local Node/npm is required for `finance-web/` and Playwright E2E execution in `finance-web/package.json`.
- Expected local service ports are `3335` for `finance-mcp`, `8100` for `finance-agents/data-agent`, `5173` for `finance-web`, and `3334` for `playwright-mcp` as documented in `START_ALL_SERVICES.sh`, `finance-web/vite.config.ts`, and `playwright-mcp/README.md`.
- Local writable filesystem storage is used under `finance-mcp/uploads/`, `finance-mcp/proc/output/`, `finance-mcp/recon/output/`, and `logs/`.

**Production:**
- Not detected as a separate deployment target; repo state is optimized for local multi-service startup via `START_ALL_SERVICES.sh`.
- Optional LangSmith tracing is toggled in `START_ALL_SERVICES.sh` and observed by `finance-agents/data-agent/server.py`, but no deployment manifests for hosted infrastructure are present.

---

*Stack analysis: 2026-04-22*
