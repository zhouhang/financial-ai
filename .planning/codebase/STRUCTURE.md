# Codebase Structure

**Analysis Date:** 2026-04-22

## Directory Layout

```text
financial-ai/
├── finance-web/                  # React + Vite frontend, component tests, e2e tests
├── finance-agents/data-agent/    # FastAPI + LangGraph orchestration service
├── finance-mcp/                  # MCP tool server, DB access, proc/recon runtimes
├── finance-cron/                 # APScheduler-based run-plan scheduler
├── tests/                        # Cross-service Python regression tests
├── docs/                         # Project documentation outside planning/spec systems
├── design/                       # Design notes and mockups
├── finance-skills/               # Prompt/skill assets for rule JSON generation
├── openspec/                     # Proposal, design, and task records
├── playwright-mcp/               # Separate Playwright MCP experiment
├── .planning/codebase/           # Generated codebase maps
├── START_ALL_SERVICES.sh         # Local multi-service bootstrap
└── README.md                     # Workspace runtime overview
```

## Directory Purposes

**finance-web/:**
- Purpose: Browser SPA for chat, data connections, and recon workspace operations.
- Contains: Runtime UI in `finance-web/src/`, browser tests in `finance-web/tests/`, static assets in `finance-web/public/`, and package/config files at the service root.
- Key files: `finance-web/src/App.tsx`, `finance-web/src/main.tsx`, `finance-web/vite.config.ts`, `finance-web/package.json`

**finance-web/src/:**
- Purpose: Actual frontend implementation.
- Contains: Feature components under `finance-web/src/components/`, hooks under `finance-web/src/hooks/`, shared types in `finance-web/src/types.ts`, and small helpers under `finance-web/src/utils/`.
- Key files: `finance-web/src/App.tsx`, `finance-web/src/hooks/useWebSocket.ts`, `finance-web/src/components/DataConnectionsPanel.tsx`, `finance-web/src/components/ReconWorkspace.tsx`

**finance-agents/data-agent/:**
- Purpose: Backend-for-frontend service that exposes HTTP/WebSocket APIs and runs LangGraph workflows.
- Contains: Entrypoint `finance-agents/data-agent/server.py`, graph modules in `finance-agents/data-agent/graphs/`, MCP proxy code in `finance-agents/data-agent/tools/`, reusable services in `finance-agents/data-agent/services/`, tests, and local skill prompts.
- Key files: `finance-agents/data-agent/server.py`, `finance-agents/data-agent/config.py`, `finance-agents/data-agent/models.py`, `finance-agents/data-agent/langgraph.json`

**finance-agents/data-agent/graphs/:**
- Purpose: Domain-oriented graph builders and REST route modules.
- Contains: Main graph code in `finance-agents/data-agent/graphs/main_graph/`, proc routes in `finance-agents/data-agent/graphs/proc/`, recon APIs and services in `finance-agents/data-agent/graphs/recon/`, and feature APIs for `platform`, `data_source`, and `collaboration`.
- Key files: `finance-agents/data-agent/graphs/main_graph/routers.py`, `finance-agents/data-agent/graphs/recon/auto_run_api.py`, `finance-agents/data-agent/graphs/recon/pipeline_service.py`, `finance-agents/data-agent/graphs/data_source/api.py`

**finance-agents/data-agent/services/:**
- Purpose: Backend service abstractions that do not belong directly inside graph nodes or HTTP handlers.
- Contains: Notification contracts, adapters, repository helpers, and orchestration service code under `finance-agents/data-agent/services/notifications/`.
- Key files: `finance-agents/data-agent/services/notifications/base.py`, `finance-agents/data-agent/services/notifications/service.py`

**finance-agents/data-agent/skills/:**
- Purpose: Local prompt assets used by scheme/proc/recon configuration workflows.
- Contains: Skill definitions and reference markdown under `finance-agents/data-agent/skills/proc-config/` and `finance-agents/data-agent/skills/recon-config/`.
- Key files: `finance-agents/data-agent/skills/proc-config/SKILL.md`, `finance-agents/data-agent/skills/recon-config/SKILL.md`

**finance-mcp/:**
- Purpose: MCP tool service that owns auth, persistence, file handling, data-source connectors, and proc/recon execution engines.
- Contains: Tool dispatcher `finance-mcp/unified_mcp_server.py`, DB config `finance-mcp/db_config.py`, domain modules in `finance-mcp/tools/`, `finance-mcp/auth/`, `finance-mcp/proc/`, `finance-mcp/recon/`, and backend tests.
- Key files: `finance-mcp/unified_mcp_server.py`, `finance-mcp/db_config.py`, `finance-mcp/README.md`

**finance-mcp/auth/:**
- Purpose: Authentication, conversation persistence, schema bootstrap, and SQL migrations.
- Contains: DB helpers, JWT utilities, auth-related MCP tools, and migration SQL files.
- Key files: `finance-mcp/auth/db.py`, `finance-mcp/auth/tools.py`, `finance-mcp/auth/jwt_utils.py`, `finance-mcp/auth/migrations/001_initial_schema.sql`

**finance-mcp/tools/:**
- Purpose: Generic MCP tool handlers that are not proc/recon runtime engines.
- Contains: File upload/validation, rules, platform connections, unified data sources, and execution scheduler models.
- Key files: `finance-mcp/tools/file_upload_tool.py`, `finance-mcp/tools/file_validate_tool.py`, `finance-mcp/tools/rules.py`, `finance-mcp/tools/data_sources.py`, `finance-mcp/tools/platform_connections.py`, `finance-mcp/tools/execution_runs.py`

**finance-mcp/connectors/ and finance-mcp/platforms/:**
- Purpose: Provider abstraction layers used by data-source and platform authorization tools.
- Contains: Base contracts, factories, and provider-specific implementations.
- Key files: `finance-mcp/connectors/base.py`, `finance-mcp/connectors/factory.py`, `finance-mcp/connectors/providers/database.py`, `finance-mcp/platforms/base.py`, `finance-mcp/platforms/factory.py`, `finance-mcp/platforms/connectors/taobao.py`

**finance-mcp/proc/:**
- Purpose: Proc rule runtime and output configuration.
- Contains: Proc config values and runtime implementations under `finance-mcp/proc/mcp_server/`.
- Key files: `finance-mcp/proc/config/config.py`, `finance-mcp/proc/mcp_server/proc_rule.py`, `finance-mcp/proc/mcp_server/steps_runtime.py`

**finance-mcp/recon/:**
- Purpose: Recon dataset loading and reconciliation runtime.
- Contains: Runtime modules under `finance-mcp/recon/mcp_server/` and generated recon outputs under `finance-mcp/recon/output/`.
- Key files: `finance-mcp/recon/mcp_server/recon_tool.py`, `finance-mcp/recon/mcp_server/dataset_loader.py`

**finance-cron/:**
- Purpose: Scheduler service that keeps run-plan automation outside the request-serving processes.
- Contains: Scheduler startup, config loading, thin finance-mcp/data-agent clients, and tests.
- Key files: `finance-cron/run_scheduler.py`, `finance-cron/scheduler_service.py`, `finance-cron/data_agent_client.py`, `finance-cron/config/cron_config.yaml`

**tests/:**
- Purpose: Repo-level Python regression tests that span services or load modules directly from multiple packages.
- Contains: Headless recon pipeline and internal API semantic tests.
- Key files: `tests/test_recon_pipeline_service.py`, `tests/test_recon_internal_api_semantics.py`, `tests/test_recon_dataset_protocol_rejection.py`

**openspec/:**
- Purpose: Change proposals, design notes, and spec deltas.
- Contains: `openspec/changes/` and `openspec/specs/`.
- Key files: `openspec/changes/refactor-data-agent-graphs/proposal.md`, `openspec/changes/unify-rule-config-display/design.md`

**finance-skills/:**
- Purpose: Standalone prompt/skill definitions for generating finance rule JSON outside the runtime services.
- Contains: One directory per skill with a `SKILL.md`.
- Key files: `finance-skills/generate-file-validation-rule-json/SKILL.md`, `finance-skills/generate-proc-rule-json/SKILL.md`, `finance-skills/generate-recon-rule-json/SKILL.md`

**playwright-mcp/:**
- Purpose: Separate experimental MCP server for Playwright/browser automation.
- Contains: Its own server, config, and README.
- Key files: `playwright-mcp/mcp_sse_server.py`, `playwright-mcp/mcp_server/tools.py`, `playwright-mcp/README.md`

## Key File Locations

**Entry Points:**
- `START_ALL_SERVICES.sh`: Starts `finance-mcp`, `data-agent`, `finance-cron`, and `finance-web` in local development.
- `finance-web/src/main.tsx`: Frontend mount point.
- `finance-agents/data-agent/server.py`: FastAPI and WebSocket entrypoint for the agent service.
- `finance-agents/data-agent/langgraph.json`: LangGraph dev/studio entry that points to `graphs.main_graph.routers:create_app`.
- `finance-mcp/unified_mcp_server.py`: MCP/Starlette server entrypoint.
- `finance-cron/run_scheduler.py`: Scheduler process entrypoint.

**Configuration:**
- `README.md`: High-level runtime topology and startup instructions.
- `finance-web/vite.config.ts`: Frontend dev server and `/api` proxy configuration.
- `finance-web/tsconfig.json`: Frontend TypeScript compilation settings.
- `finance-web/eslint.config.js`: Frontend lint configuration.
- `finance-agents/data-agent/config.py`: Data-agent runtime URLs, DB URLs, upload dir, and LLM/provider configuration.
- `finance-agents/data-agent/pyproject.toml`: Data-agent package and Python dependency metadata.
- `finance-mcp/db_config.py`: Finance-mcp database connection settings.
- `finance-cron/config/cron_config.yaml`: Scheduler refresh interval, timezone, and page-size defaults.

**Core Logic:**
- `finance-agents/data-agent/graphs/main_graph/routers.py`: Main chat graph and subgraph routing.
- `finance-agents/data-agent/graphs/recon/pipeline_service.py`: Shared recon execution pipeline for chat, REST, and scheduler callers.
- `finance-agents/data-agent/graphs/recon/auto_run_api.py`: Recon scheme/task/run REST API surface.
- `finance-agents/data-agent/tools/mcp_client.py`: All data-agent to finance-mcp tool calls.
- `finance-mcp/tools/data_sources.py`: Unified data-source and dataset governance logic.
- `finance-mcp/tools/execution_runs.py`: Scheme/run-plan/run persistence APIs.
- `finance-mcp/proc/mcp_server/proc_rule.py`: Proc execution runtime.
- `finance-mcp/recon/mcp_server/recon_tool.py`: Recon execution runtime.
- `finance-cron/scheduler_service.py`: APScheduler orchestration and slot deduplication.

**Testing:**
- `finance-web/tests/components/`: React component and client utility tests.
- `finance-web/tests/e2e/`: Playwright end-to-end flows.
- `finance-agents/data-agent/tests/`: Data-agent API, graph, recon, platform, and notification tests.
- `finance-mcp/tests/`: MCP tool, DB schema, and route-level tests.
- `tests/`: Cross-service regression tests that load modules directly.

## Naming Conventions

**Files:**
- Python backend files use `snake_case.py`: `finance-agents/data-agent/graphs/recon/auto_run_service.py`, `finance-mcp/tools/platform_connections.py`
- React components use `PascalCase.tsx`: `finance-web/src/components/ChatArea.tsx`, `finance-web/src/components/ReconWorkspace.tsx`
- Frontend helper and type modules use `camelCase.ts` or `types.ts`: `finance-web/src/hooks/useWebSocket.ts`, `finance-web/src/components/recon/autoApi.ts`, `finance-web/src/types.ts`
- Feature-specific documentation and skills use uppercase or descriptive markdown names: `finance-agents/data-agent/skills/proc-config/SKILL.md`

**Directories:**
- Top-level runtime directories use product/service names: `finance-web/`, `finance-mcp/`, `finance-cron/`
- Backend domain folders stay lowercase and singular: `finance-agents/data-agent/graphs/proc/`, `finance-agents/data-agent/graphs/platform/`, `finance-agents/data-agent/services/notifications/`
- React component folders use PascalCase only when the folder is a component namespace, such as `finance-web/src/components/ResponsiveTable/`; feature folders remain lowercase, such as `finance-web/src/components/recon/`

## Where to Add New Code

**New Feature:**
- Primary code: Put browser UI in `finance-web/src/components/` and `finance-web/src/hooks/`. Put orchestration or HTTP endpoints in `finance-agents/data-agent/graphs/` and `finance-agents/data-agent/server.py`. Put persistence-heavy or external-integration logic in `finance-mcp/tools/`, `finance-mcp/proc/mcp_server/`, or `finance-mcp/recon/mcp_server/` depending on the owning domain.
- Tests: Put UI tests in `finance-web/tests/components/` or `finance-web/tests/e2e/`. Put data-agent tests in `finance-agents/data-agent/tests/`. Put MCP and DB behavior tests in `finance-mcp/tests/`. Use `tests/` only when the feature spans multiple services.

**New Component/Module:**
- Implementation: Co-locate by domain. New recon UI belongs under `finance-web/src/components/recon/`. New data-source REST endpoints belong under `finance-agents/data-agent/graphs/data_source/`. New platform auth/provider code belongs under `finance-mcp/platforms/connectors/`. New generic data-source connectors belong under `finance-mcp/connectors/providers/`.

**New Chat Graph Step:**
- Implementation: Add nodes and routing in `finance-agents/data-agent/graphs/<domain>/nodes.py` and `finance-agents/data-agent/graphs/<domain>/routers.py`, then register the graph from `finance-agents/data-agent/graphs/main_graph/routers.py` or expose a REST surface from `finance-agents/data-agent/server.py`.

**New MCP Tool:**
- Implementation: Add the handler in `finance-mcp/tools/<domain>.py` for generic CRUD/service features, or inside `finance-mcp/proc/mcp_server/` or `finance-mcp/recon/mcp_server/` for execution-engine work.
- Registration: Add the tool name set and dispatch branch in `finance-mcp/unified_mcp_server.py`.
- Persistence: Add SQL migrations under `finance-mcp/auth/migrations/` and DB helpers in `finance-mcp/auth/db.py` when the new tool changes schema.

**Utilities:**
- Shared frontend helpers: `finance-web/src/utils/`
- Data-agent helpers: `finance-agents/data-agent/utils/`
- Provider/service abstractions: `finance-agents/data-agent/services/` or `finance-mcp/connectors/` / `finance-mcp/platforms/`, depending on which service owns the boundary

**Do Not Add New Source Code To:**
- `finance-web/dist/`
- `finance-web/node_modules/`
- `finance-agents/data-agent/.venv/`
- `finance-agents/data-agent/.langgraph_api/`
- `finance-mcp/uploads/`
- `finance-mcp/proc/output/`
- `finance-mcp/recon/output/`
- `logs/`

## Special Directories

**.planning/codebase/:**
- Purpose: Generated codebase reference documents for planning tools.
- Generated: Yes
- Committed: No

**finance-agents/data-agent/.langgraph_api/:**
- Purpose: Local LangGraph dev/checkpoint artifacts.
- Generated: Yes
- Committed: No

**finance-web/dist/:**
- Purpose: Vite build output.
- Generated: Yes
- Committed: No

**finance-web/test-results/:**
- Purpose: Playwright and browser-test output artifacts.
- Generated: Yes
- Committed: No

**finance-mcp/uploads/:**
- Purpose: Uploaded input files and generated snapshot export staging data.
- Generated: Yes
- Committed: No

**finance-mcp/proc/output/:**
- Purpose: Generated proc output files.
- Generated: Yes
- Committed: No

**finance-mcp/recon/output/:**
- Purpose: Generated reconciliation spreadsheets and metadata.
- Generated: Yes
- Committed: Yes

**logs/:**
- Purpose: Local service log files written by `START_ALL_SERVICES.sh`.
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-04-22*
