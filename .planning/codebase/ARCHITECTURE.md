# Architecture

**Analysis Date:** 2026-04-22

## Pattern Overview

**Overall:** Service-oriented monorepo with a browser frontend, a FastAPI/LangGraph backend-for-frontend, a separate MCP tool server, and an out-of-process scheduler.

**Key Characteristics:**
- User-facing traffic starts in `finance-web/src/main.tsx` and `finance-web/src/App.tsx`; `finance-web/vite.config.ts` proxies `/api` HTTP and WebSocket traffic to `finance-agents/data-agent/server.py`.
- `finance-agents/data-agent/server.py` combines a FastAPI facade with LangGraph orchestration built in `finance-agents/data-agent/graphs/main_graph/routers.py`.
- Cross-service integration is networked instead of in-process. `finance-agents/data-agent/tools/mcp_client.py` talks to `finance-mcp/unified_mcp_server.py` over the MCP SSE protocol instead of importing finance-mcp business logic directly.
- `finance-mcp/unified_mcp_server.py` is a dispatcher. Business logic is split into domain modules such as `finance-mcp/tools/data_sources.py`, `finance-mcp/tools/platform_connections.py`, `finance-mcp/proc/mcp_server/proc_rule.py`, and `finance-mcp/recon/mcp_server/recon_tool.py`.
- Scheduling is isolated in `finance-cron/scheduler_service.py`, which polls run plans from finance-mcp and triggers execution through data-agent HTTP endpoints.

## Layers

**Frontend/UI Layer:**
- Purpose: Render chat, data connections, recon workspace, and auth flows in the browser.
- Location: `finance-web/src/`
- Contains: App shell in `finance-web/src/App.tsx`, feature components in `finance-web/src/components/`, hooks in `finance-web/src/hooks/`, and shared client types in `finance-web/src/types.ts`.
- Depends on: Browser `fetch`/`WebSocket`, Vite proxy rules in `finance-web/vite.config.ts`, and backend routes exposed by `finance-agents/data-agent/server.py`.
- Used by: End users accessing the SPA on port 5173.

**API and Orchestration Layer:**
- Purpose: Expose HTTP/WebSocket endpoints, manage thread/auth context, and run LangGraph workflows.
- Location: `finance-agents/data-agent/server.py`, `finance-agents/data-agent/graphs/`
- Contains: `FastAPI` routes, `WebSocket /chat`, graph builders such as `finance-agents/data-agent/graphs/main_graph/routers.py`, and shared execution services such as `finance-agents/data-agent/graphs/recon/pipeline_service.py`.
- Depends on: `finance-agents/data-agent/tools/mcp_client.py`, `finance-agents/data-agent/models.py`, `finance-agents/data-agent/config.py`, and utilities under `finance-agents/data-agent/utils/`.
- Used by: `finance-web/` and `finance-cron/`.

**Tool and Persistence Layer:**
- Purpose: Own authentication, conversations, rules, data sources, platform connections, proc execution, recon execution, and file download authorization.
- Location: `finance-mcp/unified_mcp_server.py`, `finance-mcp/auth/`, `finance-mcp/tools/`, `finance-mcp/proc/mcp_server/`, `finance-mcp/recon/mcp_server/`
- Contains: MCP tool registration, DB access in `finance-mcp/auth/db.py`, connector factories in `finance-mcp/connectors/factory.py`, and execution engines in `finance-mcp/proc/mcp_server/proc_rule.py` and `finance-mcp/recon/mcp_server/recon_tool.py`.
- Depends on: Postgres config from `finance-mcp/db_config.py`, auth helpers in `finance-mcp/auth/jwt_utils.py`, and connector contracts in `finance-mcp/connectors/base.py` and `finance-mcp/platforms/base.py`.
- Used by: `finance-agents/data-agent/tools/mcp_client.py` and `finance-cron/mcp_client.py`.

**Automation Layer:**
- Purpose: Register run-plan schedules and trigger automatic reconciliation work without keeping scheduler logic inside request-serving processes.
- Location: `finance-cron/`
- Contains: Startup entrypoint `finance-cron/run_scheduler.py`, APScheduler logic in `finance-cron/scheduler_service.py`, and thin clients in `finance-cron/data_agent_client.py` and `finance-cron/mcp_client.py`.
- Depends on: Execution scheduler tools in finance-mcp and run-plan APIs in `finance-agents/data-agent/graphs/recon/auto_run_api.py`.
- Used by: `START_ALL_SERVICES.sh` and manual CLI runs.

**Support and Artifact Layer:**
- Purpose: Hold tests, specs, prompt assets, and experimental utilities that support development but are not the live runtime request path.
- Location: `finance-web/tests/`, `finance-agents/data-agent/tests/`, `finance-mcp/tests/`, `tests/`, `openspec/`, `design/`, `finance-skills/`, `playwright-mcp/`
- Contains: Browser tests, Python tests, OpenSpec change records, prompt/skill files, and a separate Playwright MCP experiment.
- Depends on: Active runtime packages.
- Used by: Developers, CI-style test runs, and planning workflows.

## Data Flow

**Interactive Chat and Manual Execution:**

1. `finance-web/src/hooks/useWebSocket.ts` opens `ws://` or `wss://` against `/api/chat`; `finance-web/vite.config.ts` forwards that socket to `finance-agents/data-agent/server.py`.
2. `finance-agents/data-agent/server.py` receives the message, merges auth/rule/file context into LangGraph state, and executes the compiled app created by `finance-agents/data-agent/graphs/main_graph/routers.py:create_app`.
3. The main graph routes into proc or recon flows implemented by `finance-agents/data-agent/graphs/proc/routers.py` and `finance-agents/data-agent/graphs/recon/manual_scheme_run/routers.py`.
4. Execution nodes call helper functions in `finance-agents/data-agent/tools/mcp_client.py`, which maintain an MCP SSE session to `finance-mcp/unified_mcp_server.py`.
5. `finance-mcp/unified_mcp_server.py` dispatches named tools such as `get_rule`, `validate_files`, `proc_execute`, or `recon_execute` to domain handlers under `finance-mcp/tools/`, `finance-mcp/proc/mcp_server/`, and `finance-mcp/recon/mcp_server/`.
6. Results, progress, and download URLs flow back to the browser and render in `finance-web/src/components/ChatArea.tsx` and `finance-web/src/components/ReconWorkspace.tsx`.

**Configuration and Governance APIs:**

1. The browser calls REST paths such as `/api/data-sources`, `/api/platform-connections`, `/api/recon/schemes`, and `/api/collaboration-channels` from `finance-web/src/components/DataConnectionsPanel.tsx` and `finance-web/src/components/recon/autoApi.ts`.
2. `finance-agents/data-agent/server.py` mounts routers from `finance-agents/data-agent/graphs/data_source/api.py`, `finance-agents/data-agent/graphs/platform/api.py`, `finance-agents/data-agent/graphs/recon/auto_run_api.py`, and `finance-agents/data-agent/graphs/collaboration/api.py`.
3. Those routers stay thin. They validate HTTP payloads, extract bearer tokens, and delegate business operations to `finance-agents/data-agent/tools/mcp_client.py`.
4. Persistence and provider-specific behavior live in finance-mcp modules such as `finance-mcp/tools/data_sources.py`, `finance-mcp/tools/platform_connections.py`, `finance-mcp/tools/execution_runs.py`, and `finance-mcp/auth/db.py`.

**Scheduled Run Plans:**

1. `START_ALL_SERVICES.sh` launches `finance-cron/run_scheduler.py` as a separate process after the API services are up.
2. `finance-cron/scheduler_service.py` refreshes enabled plans through `finance-cron/mcp_client.py`, which uses finance-mcp execution scheduler tools.
3. APScheduler jobs compute a `schedule_slot`, deduplicate with `execution_scheduler_get_slot_run`, and only then trigger the plan.
4. `finance-cron/data_agent_client.py` POSTs to `/recon/run-plans/{run_plan_code}/run`, handled by `finance-agents/data-agent/graphs/recon/auto_run_api.py`.
5. `finance-agents/data-agent/graphs/recon/auto_run_service.py` and `finance-agents/data-agent/graphs/recon/pipeline_service.py` reuse the same recon execution pipeline used by non-scheduled callers.
6. Final run state and exceptions are persisted through finance-mcp tools such as `finance-mcp/tools/execution_runs.py` and `finance-mcp/tools/recon_auto_runs.py`.

**State Management:**
- Browser state is local React state in `finance-web/src/App.tsx`, with persistence in `localStorage` and connection state in `finance-web/src/hooks/useWebSocket.ts`.
- Conversation and workflow state is keyed by `thread_id` in `finance-agents/data-agent/server.py` and checkpointed to Postgres through `AsyncPostgresSaver` configured by `finance-agents/data-agent/config.py`.
- Business state lives in Postgres through `finance-mcp/auth/db.py`; uploaded files and generated outputs live under `finance-mcp/uploads/`, `finance-mcp/proc/output/`, and `finance-mcp/recon/output/`.
- Scheduler state is partly persistent in finance-mcp tables and partly in-memory in `finance-cron/scheduler_service.py` via `_plan_signatures` and `_inflight_slots`.

## Key Abstractions

**LangGraph Agent State:**
- Purpose: Carry messages, selected task/rule codes, uploaded files, and proc/recon context across pauses and resumes.
- Examples: `finance-agents/data-agent/models.py`, `finance-agents/data-agent/graphs/main_graph/routers.py`, `finance-agents/data-agent/server.py`
- Pattern: `TypedDict` state plus `StateGraph` builder functions compiled with an external Postgres checkpointer.

**Shared Recon Execution Pipeline:**
- Purpose: Keep chat execution, internal API execution, and scheduled execution aligned on one recon pipeline.
- Examples: `finance-agents/data-agent/graphs/recon/pipeline_service.py`, `finance-agents/data-agent/graphs/recon/execution_service.py`, `finance-agents/data-agent/graphs/recon/api.py`
- Pattern: Shared service functions that return normalized `{ok, execution_status, failure_stage}` dictionaries instead of letting each caller implement its own flow.

**MCP Proxy Session:**
- Purpose: Hide SSE handshake, request ID tracking, and tool-specific timeouts from the rest of data-agent.
- Examples: `finance-agents/data-agent/tools/mcp_client.py`
- Pattern: A long-lived async session object plus thin helper functions such as `get_file_validation_rule`, `execute_recon`, and `execution_scheme_create`.

**Tool Dispatch Registry:**
- Purpose: Map public MCP tool names to concrete handler modules without duplicating routing logic in callers.
- Examples: `finance-mcp/unified_mcp_server.py`, `finance-mcp/tools/rules.py`, `finance-mcp/tools/data_sources.py`, `finance-mcp/proc/mcp_server/proc_rule.py`, `finance-mcp/recon/mcp_server/recon_tool.py`
- Pattern: Name-set based dispatch in `call_tool()` plus domain-local `create_tools()` / `handle_tool_call()` pairs.

**Connector Contracts:**
- Purpose: Isolate provider-specific data-source and platform behavior behind stable abstractions.
- Examples: `finance-mcp/connectors/base.py`, `finance-mcp/connectors/factory.py`, `finance-mcp/platforms/base.py`, `finance-mcp/platforms/factory.py`
- Pattern: Abstract base classes plus factory-selected concrete implementations such as `finance-mcp/connectors/providers/database.py` and `finance-mcp/platforms/connectors/taobao.py`.

**Notification Adapter:**
- Purpose: Standardize reminder and todo delivery for exception follow-up workflows.
- Examples: `finance-agents/data-agent/services/notifications/base.py`, `finance-agents/data-agent/services/notifications/dingtalk_dws.py`, `finance-agents/data-agent/services/notifications/service.py`
- Pattern: Provider-agnostic interface with adapter-specific implementations and repository-backed configuration.

## Entry Points

**Frontend SPA:**
- Location: `finance-web/src/main.tsx`
- Triggers: Browser page load from the Vite dev server or built assets.
- Responsibilities: Apply theme initialization and mount the React app.

**Frontend App Shell:**
- Location: `finance-web/src/App.tsx`
- Triggers: React render lifecycle.
- Responsibilities: Own top-level auth, conversation, panel, and workspace state; wire WebSocket and REST hooks; switch between chat and governance views.

**Data-Agent API Server:**
- Location: `finance-agents/data-agent/server.py`
- Triggers: `python -m server` and proxied HTTP/WebSocket traffic.
- Responsibilities: Initialize LangGraph, expose `/chat`, `/upload`, `/auth/*`, `/conversations/*`, `/proc/*`, `/recon/*`, `/data-sources*`, `/platform-*`, and `/collaboration-*`.

**Compiled LangGraph App:**
- Location: `finance-agents/data-agent/graphs/main_graph/routers.py`
- Triggers: Startup initialization from `finance-agents/data-agent/server.py` and each incoming chat turn.
- Responsibilities: Compile the main graph with a checkpointer and route to proc, recon, or manual-notify subgraphs.

**MCP Tool Server:**
- Location: `finance-mcp/unified_mcp_server.py`
- Triggers: `python unified_mcp_server.py` and requests to `/sse`, `/mcp`, `/messages/`, `/health`, and `/output/{module}/{path}`.
- Responsibilities: List tools, dispatch tool calls, perform schema bootstrap checks, and authorize output downloads.

**Scheduler Service:**
- Location: `finance-cron/run_scheduler.py`
- Triggers: `START_ALL_SERVICES.sh` or direct CLI execution.
- Responsibilities: Load scheduler config, start `FinanceCronSchedulerService`, and keep run plans refreshed until shutdown.

## Error Handling

**Strategy:** Normalize failures at service boundaries and keep mutation-heavy logic in the service that owns the state being changed.

**Patterns:**
- `finance-agents/data-agent/server.py` turns runtime problems into WebSocket `error` / `done` messages or `HTTPException` responses instead of leaking raw stack traces to clients.
- `finance-agents/data-agent/graphs/recon/pipeline_service.py` returns explicit failure stages such as `request_build_failed` and `execution_call_failed` so REST and scheduler callers can react consistently.
- `finance-agents/data-agent/tools/mcp_client.py` controls retries, per-tool timeouts, and SSE reconnect behavior, then normalizes failures into structured dictionaries.
- `finance-mcp/unified_mcp_server.py` catches handler exceptions and returns a text payload or error dictionary rather than crashing the MCP server process.
- `finance-cron/data_agent_client.py` retries transient local HTTP failures, while `finance-cron/scheduler_service.py` avoids duplicate runs by checking the scheduler slot before dispatch.

## Cross-Cutting Concerns

**Logging:** `finance-agents/data-agent/server.py`, `finance-mcp/unified_mcp_server.py`, and `finance-cron/run_scheduler.py` configure Python logging at process startup. Domain modules reuse named loggers. Frontend runtime errors are surfaced with `console.error` and `console.warn` in `finance-web/src/hooks/useWebSocket.ts` and `finance-web/src/hooks/useConversations.ts`.

**Validation:** HTTP contracts use Pydantic models in routers such as `finance-agents/data-agent/graphs/recon/api.py`, `finance-agents/data-agent/graphs/recon/auto_run_api.py`, and `finance-agents/data-agent/graphs/data_source/api.py`. Rule payloads are validated in `finance-mcp/tools/rule_schema.py`, and tool handlers normalize request shapes before execution.

**Authentication:** Browser tokens are stored in `localStorage` by `finance-web/src/App.tsx`. `finance-agents/data-agent/tools/mcp_client.py` passes tokens through to finance-mcp. JWT parsing and ownership checks live in `finance-mcp/auth/jwt_utils.py`, `finance-mcp/tools/rules.py`, and `finance-mcp/unified_mcp_server.py`. Output file authorization is enforced through metadata written by finance-mcp security helpers and checked on download.

---

*Architecture analysis: 2026-04-22*
