# External Integrations

**Analysis Date:** 2026-04-22

## APIs & External Services

**Internal service-to-service integration:**
- `finance-web` -> `finance-agents/data-agent`
  - What it's used for: browser requests to `/api/*` and `/api/chat` are proxied to the agent backend from `finance-web/vite.config.ts` and `finance-web/src/hooks/useWebSocket.ts`.
  - SDK/Client: browser `fetch` and `WebSocket` calls in `finance-web/src/components/*.tsx` and `finance-web/src/hooks/useWebSocket.ts`.
  - Auth: Bearer JWT passed from the frontend in headers from `finance-web/src/hooks/useConversations.ts`, `finance-web/src/components/DataConnectionsPanel.tsx`, and `finance-web/src/components/ReconWorkspace.tsx`.
- `finance-agents/data-agent` -> `finance-mcp`
  - What it's used for: MCP tool invocation for auth, rules, data sources, platform connections, proc, recon, and execution models through SSE transport in `finance-agents/data-agent/tools/mcp_client.py`.
  - SDK/Client: `httpx` SSE + JSON-RPC wrapper in `finance-agents/data-agent/tools/mcp_client.py`.
  - Auth: `FINANCE_MCP_BASE_URL` for service location in `finance-agents/data-agent/config.py`; user/system JWT tokens are forwarded as tool arguments.
- `finance-cron` -> `finance-mcp` and `finance-agents/data-agent`
  - What it's used for: schedule refresh and run-plan execution in `finance-cron/mcp_client.py` and `finance-cron/data_agent_client.py`.
  - SDK/Client: `httpx` clients in `finance-cron/mcp_client.py` and `finance-cron/data_agent_client.py`.
  - Auth: scheduler-generated JWT from `finance-cron/scheduler_service.py` using `JWT_SECRET`.

**LLM providers (OpenAI-compatible):**
- OpenAI - primary/default chat model provider configured in `finance-agents/data-agent/config.py` and instantiated through `langchain_openai.ChatOpenAI` in `finance-agents/data-agent/utils/llm.py`.
  - SDK/Client: `langchain-openai` / `ChatOpenAI` from `finance-agents/data-agent/utils/llm.py`.
  - Auth: `OPENAI_API_KEY`.
- Qwen (DashScope OpenAI-compatible endpoint) - alternate chat model provider configured in `finance-agents/data-agent/config.py`.
  - SDK/Client: same `ChatOpenAI` wrapper in `finance-agents/data-agent/utils/llm.py`.
  - Auth: `QWEN_API_KEY`.
- DeepSeek - alternate chat model provider configured in `finance-agents/data-agent/config.py`.
  - SDK/Client: same `ChatOpenAI` wrapper in `finance-agents/data-agent/utils/llm.py`.
  - Auth: `DEEPSEEK_API_KEY`.
- The same provider family is also referenced by the data-source semantic logic in `finance-mcp/tools/data_sources.py`.

**Retrieval / ranking APIs:**
- Zhipu AI - embedding and rerank API client implemented in `finance-agents/data-agent/utils/retrieval_api.py`.
  - SDK/Client: direct `httpx` client in `finance-agents/data-agent/utils/retrieval_api.py`.
  - Auth: `ZHIPU_API_KEY`.

**Enterprise notification / collaboration:**
- DingTalk via local `dws` CLI - notification adapter for bot messages and todo management in `finance-agents/data-agent/services/notifications/dingtalk_dws.py`.
  - SDK/Client: subprocess wrapper around the `dws` binary in `finance-agents/data-agent/services/notifications/cli.py`.
  - Auth: `DINGTALK_CLIENT_ID`, `DINGTALK_CLIENT_SECRET`, `DINGTALK_ROBOT_CODE`.

**Platform OAuth / commerce connectors:**
- Taobao, Tmall, Douyin Shop - platform authorization scaffolding lives in `finance-mcp/tools/platform_connections.py`, `finance-mcp/platforms/factory.py`, `finance-mcp/platforms/connectors/taobao.py`, and `finance-mcp/platforms/connectors/douyin_shop.py`.
  - SDK/Client: custom connector classes from `finance-mcp/platforms/connectors/*.py`.
  - Auth: platform app credentials are persisted via `finance-mcp/auth/db.py`; callback handling is exposed by `finance-agents/data-agent/graphs/platform/api.py`.
- Current repo state uses mock-first behavior by default (`PLATFORM_CONNECTION_MODE` defaults to `mock` in `finance-agents/data-agent/tools/mcp_client.py`), and the real token exchange methods still raise `NotImplementedError` in `finance-mcp/platforms/connectors/taobao.py` and `finance-mcp/platforms/connectors/douyin_shop.py`.

**Generic external data-source connectors:**
- PostgreSQL / MySQL / SQLite source systems - external database discovery and preview in `finance-mcp/connectors/providers/database.py`.
  - SDK/Client: `psycopg2`, `PyMySQL`, and `sqlite3` in `finance-mcp/connectors/providers/database.py`.
  - Auth: credentials are stored in data-source configs handled by `finance-mcp/tools/data_sources.py`.
- Arbitrary REST / OpenAPI services - API source connector and OpenAPI/manual discovery in `finance-mcp/connectors/providers/api.py` and `finance-agents/data-agent/graphs/data_source/api.py`.
  - SDK/Client: `requests` in `finance-mcp/connectors/providers/api.py`, `httpx` in `finance-agents/data-agent/graphs/data_source/api.py`.
  - Auth: bearer/api-key/basic/request-auth config stored in source config models handled by `finance-mcp/tools/data_sources.py`.

**Browser automation service:**
- Playwright MCP server - separate SSE service for browser automation in `playwright-mcp/mcp_sse_official.py`.
  - SDK/Client: `playwright` + `mcp` from `playwright-mcp/requirements.txt`.
  - Auth: none detected; the service is documented for Dify consumption in `playwright-mcp/README.md`.

## Data Storage

**Databases:**
- PostgreSQL (`tally`) - primary application database for auth, rules, conversations, data-source metadata, execution plans, and collaboration configs in `finance-mcp/db_config.py`, `finance-mcp/auth/db.py`, and `finance-agents/data-agent/services/notifications/repository.py`.
  - Connection: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, or `DATABASE_URL`.
  - Client: `psycopg2`, `asyncpg`, and `psycopg` usage in `finance-mcp/db_config.py`, `finance-mcp/auth/db.py`, and `finance-agents/data-agent/server.py`.
- PostgreSQL LangGraph checkpoint storage - same backend database, separate schema configured by `LANGGRAPH_CHECKPOINT_DATABASE_URL` and `LANGGRAPH_CHECKPOINT_SCHEMA` in `finance-agents/data-agent/config.py` and initialized in `finance-agents/data-agent/server.py`.
  - Connection: `LANGGRAPH_CHECKPOINT_DATABASE_URL`, `LANGGRAPH_CHECKPOINT_SCHEMA`.
  - Client: `langgraph-checkpoint-postgres` in `finance-agents/data-agent/server.py`.
- MySQL - supported as a user-configured external source through `finance-mcp/connectors/providers/database.py`.
  - Connection: source-level connection config persisted by `finance-mcp/tools/data_sources.py`.
  - Client: `PyMySQL` in `finance-mcp/connectors/providers/database.py`.
- No repo-local application service was found that boots against a dedicated internal MySQL schema; current startup wiring in `START_ALL_SERVICES.sh` only initializes services that depend on PostgreSQL.

**File Storage:**
- Local filesystem only.
- Uploads and snapshot artifacts live under `finance-mcp/uploads/`, `finance-mcp/proc/output/`, and `finance-mcp/recon/output/`.
- Download access is served from `finance-mcp/unified_mcp_server.py` through `/output/{module}/{path}` with JWT and ownership checks.

**Caching:**
- No Redis, Memcached, or other external cache service detected.
- Only in-process memoization is present via `functools.lru_cache` in `finance-agents/data-agent/utils/llm.py` and `finance-agents/data-agent/utils/retrieval_api.py`.

## Authentication & Identity

**Auth Provider:**
- Custom JWT authentication.
  - Implementation: token creation/validation in `finance-mcp/auth/jwt_utils.py`; frontend Bearer usage in `finance-web/src/`; additional JWT decoding in `finance-agents/data-agent/graphs/collaboration/api.py`; system scheduler token minting in `finance-cron/scheduler_service.py`.

## Monitoring & Observability

**Error Tracking:**
- No external error tracking service such as Sentry was detected.
- Optional LangSmith tracing is wired in `START_ALL_SERVICES.sh` and checked during `finance-agents/data-agent/server.py` startup.

**Logs:**
- Python `logging` is used throughout `finance-mcp/`, `finance-agents/data-agent/`, and `finance-cron/`.
- Service logs are redirected to `logs/finance-mcp.log`, `logs/data-agent.log`, `logs/finance-cron.log`, and `logs/finance-web.log` by `START_ALL_SERVICES.sh`.

## CI/CD & Deployment

**Hosting:**
- Local multi-process startup via `START_ALL_SERVICES.sh`.
- Frontend dev hosting is Vite on port `5173` from `finance-web/vite.config.ts`.
- Backend dev hosting is Uvicorn/FastAPI on port `8100` from `finance-agents/data-agent/config.py`.
- MCP hosting is Starlette/SSE on port `3335` from `finance-mcp/unified_mcp_server.py`.

**CI Pipeline:**
- None detected.
- No `.github/workflows/`, Docker Compose file, or deployment manifest was found during repo scan.

## Environment Configuration

**Required env vars:**
- Database and auth: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DATABASE_URL`, `LANGGRAPH_CHECKPOINT_DATABASE_URL`, `LANGGRAPH_CHECKPOINT_SCHEMA`, `JWT_SECRET` from `finance-mcp/db_config.py`, `finance-agents/data-agent/config.py`, and `finance-cron/scheduler_service.py`.
- Service routing: `FINANCE_MCP_BASE_URL`, `DATA_AGENT_BASE_URL`, `MCP_HOST`, `MCP_PORT`, `MCP_PUBLIC_BASE_URL` from `finance-agents/data-agent/config.py`, `finance-cron/data_agent_client.py`, `finance-cron/mcp_client.py`, and `finance-mcp/unified_mcp_server.py`.
- LLM providers: `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_MODEL`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL` from `finance-agents/data-agent/config.py` and `finance-mcp/tools/data_sources.py`.
- Retrieval APIs: `ZHIPU_API_KEY`, `ZHIPU_BASE_URL`, `ZHIPU_EMBEDDING_MODEL`, `ZHIPU_RERANK_MODEL`, `ZHIPU_EMBEDDING_DIMENSIONS`, `ZHIPU_TIMEOUT_SECONDS` from `finance-agents/data-agent/config.py`.
- Notifications: `NOTIFICATION_PROVIDER`, `DINGTALK_DWS_BIN`, `DINGTALK_CLIENT_ID`, `DINGTALK_CLIENT_SECRET`, `DINGTALK_ROBOT_CODE` from `finance-agents/data-agent/config.py`.
- Optional observability/test knobs: `LANGSMITH_TRACING`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_PROJECT`, `LANGSMITH_API_KEY`, `PLAYWRIGHT_BASE_URL`, `PLAYWRIGHT_CHROMIUM_CHANNEL`, `PLAYWRIGHT_EXECUTABLE_PATH`.

**Secrets location:**
- Root `.env` file is present at `.env`; it is sourced by `START_ALL_SERVICES.sh`, `finance-mcp/unified_mcp_server.py`, `finance-agents/data-agent/server.py`, and `finance-cron/run_scheduler.py`.
- Service-local override `.env` is present at `finance-agents/data-agent/.env`; it is loaded by `finance-agents/data-agent/server.py` and `finance-agents/data-agent/config.py`.
- Secret values were not read.

## Webhooks & Callbacks

**Incoming:**
- Platform OAuth callback: `GET /platform-auth/callback/{platform_code}` in `finance-agents/data-agent/graphs/platform/api.py`.
- Unified data-source auth callback: `GET /data-sources/auth/callback/{source_id}` in `finance-agents/data-agent/graphs/data_source/api.py`.
- MCP transport endpoints: `/sse`, `/mcp`, and `/messages/` in `finance-mcp/unified_mcp_server.py` and `playwright-mcp/mcp_sse_official.py`.

**Outgoing:**
- Outbound MCP/HTTP calls from `finance-agents/data-agent/tools/mcp_client.py`, `finance-cron/mcp_client.py`, and `finance-cron/data_agent_client.py`.
- Outbound API/data-source calls from `finance-mcp/connectors/providers/api.py` and document fetches in `finance-agents/data-agent/graphs/data_source/api.py`.
- Outbound LLM/retrieval calls from `finance-agents/data-agent/utils/llm.py` and `finance-agents/data-agent/utils/retrieval_api.py`.
- DingTalk actions are executed via the local CLI adapter in `finance-agents/data-agent/services/notifications/dingtalk_dws.py`.

---

*Integration audit: 2026-04-22*
