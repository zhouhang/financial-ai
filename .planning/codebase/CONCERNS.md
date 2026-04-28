# Codebase Concerns

**Analysis Date:** 2026-04-22

## Tech Debt

**God modules across backend and frontend:**
- Issue: core behavior is concentrated in a few very large files that mix transport, domain logic, persistence, rendering, and formatting concerns.
- Files: `finance-mcp/auth/db.py`, `finance-mcp/tools/data_sources.py`, `finance-agents/data-agent/tools/mcp_client.py`, `finance-web/src/components/DataConnectionsPanel.tsx`, `finance-web/src/components/ReconWorkspace.tsx`, `finance-web/src/App.tsx`
- Impact: small changes have wide blast radius, review cost is high, and broad exception handling or inline networking patterns make regressions hard to localize.
- Fix approach: split by bounded context first, not by file size alone; extract repository/service/api layers on the Python side and API hooks plus presentational subcomponents on the React side; move shared normalization and formatting helpers into small modules with direct tests.

**Mock and real integration paths are coupled in one client:**
- Issue: the same module owns MCP SSE transport, auth wrappers, platform mocks, data-source mocks, semantic-profile mocks, and real-mode fallbacks.
- Files: `finance-agents/data-agent/tools/mcp_client.py`, `finance-agents/data-agent/tests/platform/test_platform_connections.py`, `finance-agents/data-agent/tests/recon/test_auto_run_service.py`
- Impact: mock behavior can drift from real `finance-mcp` behavior, so tests can stay green while production paths break.
- Fix approach: separate MCP transport/session management, real adapters, and mock fixtures; keep contract tests that run the same high-level calls against both mock and real stubs.

**Private cross-module calls create hidden coupling:**
- Issue: execution preview code reaches into private helpers from the recon engine instead of depending on a stable public interface.
- Files: `finance-mcp/tools/execution_runs.py`, `finance-mcp/recon/mcp_server/recon_tool.py`, `finance-mcp/tests/test_execution_runs_preview.py`
- Impact: internal refactors in `finance-mcp/recon/mcp_server/recon_tool.py` can break preview and trial flows without a clear compiler signal.
- Fix approach: expose a public preview API in `finance-mcp/recon/mcp_server/recon_tool.py` or a separate service module, then stop importing `_find_input_by_identification`, `_resolve_input_to_df`, `_apply_column_mapping`, `_execute_comparison`, `_write_recon_result`, `_build_recon_summary`, and `_derive_recon_status` from outside.

## Known Bugs

**Repository includes persisted download links with signed auth query parameters:**
- Symptoms: seeded conversation content contains downloadable result links with `auth_token=` query strings, and generated recon result artifacts are tracked in the repo.
- Files: `finance-mcp/auth/migrations/002_seed_data.sql`, `finance-mcp/recon/output/*`
- Trigger: loading seed data, browsing git history, or reusing sample conversations/results from the repo.
- Workaround: no safe runtime workaround; the tokens and artifacts need to be removed from tracked content and rotated.

**Real platform OAuth flows are incomplete outside mock mode:**
- Symptoms: real Taobao and Douyin Shop authorization paths raise `NotImplementedError` for token exchange, refresh, and shop profile lookup.
- Files: `finance-mcp/platforms/connectors/taobao.py`, `finance-mcp/platforms/connectors/douyin_shop.py`, `finance-agents/data-agent/tests/platform/test_platform_connections.py`
- Trigger: using `platform_oauth` flows with real app credentials instead of mock mode.
- Workaround: keep these connectors in mock mode; real production onboarding is not complete.

**Manual E2E test file mutates shared state and depends on a fixed admin account:**
- Symptoms: the semantic-refresh spec resets database rows through `psql`, logs in with a shared admin user, and prints response payloads.
- Files: `finance-web/tests/e2e/tmp-manual-semantic-refresh.spec.ts`, `finance-web/tests/e2e/data-connections-semantic-cache.spec.ts`
- Trigger: running the tracked E2E suite in an environment that shares the same `tally` database or admin account.
- Workaround: run only in an isolated local environment; it is not safe as a default CI path.

## Security Considerations

**Default credentials and secrets are accepted in production code paths:**
- Risk: JWT signing and database access fall back to hard-coded development defaults when env vars are missing.
- Files: `finance-mcp/auth/jwt_utils.py`, `finance-agents/data-agent/graphs/collaboration/api.py`, `finance-agents/data-agent/graphs/recon/scheme_design/service.py`, `finance-agents/data-agent/config.py`, `finance-mcp/db_config.py`
- Current mitigation: `finance-mcp/auth/jwt_utils.py` logs a warning when the default JWT secret is used; env vars can override the defaults.
- Recommendations: fail fast on startup when default JWT or database credentials remain active outside explicit dev mode; add a single configuration validator that blocks server startup for `finance-mcp` and `finance-agents/data-agent`.

**Sensitive connector values can fall back to weak storage behavior:**
- Risk: if crypto helpers are unavailable, `finance-mcp/auth/db.py` falls back to plaintext pass-through; if `FINANCE_MCP_SECRET_KEY` is missing, `finance-mcp/auth/crypto.py` stores a reversible fallback encoding instead of strong encryption.
- Files: `finance-mcp/auth/db.py`, `finance-mcp/auth/crypto.py`
- Current mitigation: `finance-mcp/auth/crypto.py` supports key-based reversible sealing when `FINANCE_MCP_SECRET_KEY` is present.
- Recommendations: make `FINANCE_MCP_SECRET_KEY` mandatory whenever platform apps, channel configs, or data-source credentials are enabled; add tests that fail if plaintext or fallback storage is still reachable in non-dev environments.

**Browser storage keeps bearer tokens in long-lived local state:**
- Risk: the frontend stores the auth token in `localStorage`, which is exposed to any successful XSS payload and survives browser restarts.
- Files: `finance-web/src/App.tsx`, `finance-web/src/hooks/useWebSocket.ts`
- Current mitigation: token verification happens after WebSocket connection and invalid tokens are cleared.
- Recommendations: move to secure, httpOnly session cookies or short-lived browser memory plus refresh endpoints; avoid sending long-lived tokens in URLs or persistent browser storage.

**Repo-tracked outputs and tests expose operational secrets and sample data patterns:**
- Risk: tracked seed SQL, E2E tests, and generated outputs reveal shared admin flows, fixed test users, signed result URLs, and sample business data names.
- Files: `finance-mcp/auth/migrations/002_seed_data.sql`, `finance-mcp/recon/output/*`, `finance-web/tests/e2e/data-connections-governance.spec.ts`, `finance-web/tests/e2e/data-connections-semantic-cache.spec.ts`, `finance-web/tests/e2e/tmp-manual-semantic-refresh.spec.ts`
- Current mitigation: none in the repo layout itself.
- Recommendations: stop tracking generated result files, scrub auth-bearing URLs from seeded content, move destructive/manual specs out of the default test tree, and rotate any leaked tokens or shared credentials.

## Performance Bottlenecks

**Dataset candidate selection scales by scanning and enriching large result sets in Python:**
- Problem: candidate listing loads pages of datasets, enriches source context, then scores and filters rows in Python. The scan cap is high enough to become expensive before the UI paginates results.
- Files: `finance-mcp/tools/data_sources.py`
- Cause: `_handle_data_source_list_dataset_candidates()` can iterate up to `DATASET_CANDIDATE_MAX_SCAN_PAGES` pages and calls `_enrich_dataset_rows_with_source_context()` before final filtering and scoring.
- Improvement path: push more filtering, ranking, and pagination into PostgreSQL; compute candidate scores on indexed catalog/search fields; enrich only the returned page.

**Auto discovery and sample refresh run synchronously against live connectors:**
- Problem: one request can trigger dataset discovery plus repeated preview sampling across multiple datasets.
- Files: `finance-mcp/tools/data_sources.py`
- Cause: `_auto_refresh_datasets_and_samples()` and `_refresh_dataset_samples()` loop through discovered datasets and connector previews inline, with `AUTO_DISCOVER_DATASET_LIMIT` and `AUTO_SAMPLE_DATASET_LIMIT` acting as hard caps instead of true backpressure.
- Improvement path: move discovery and sample refresh into background jobs, persist progress, and rate-limit connector previews per source.

**Draft recon preview path is memory and disk heavy:**
- Problem: preview flow loads DataFrames, runs comparison, and writes temp Excel output for each rule trial.
- Files: `finance-mcp/tools/execution_runs.py`, `finance-mcp/recon/mcp_server/recon_tool.py`
- Cause: `_handle_execution_recon_draft_trial()` materializes full preview data and writes temp output files through private recon helpers.
- Improvement path: add a lightweight preview mode that samples rows and emits structured summaries without always generating full XLSX artifacts.

## Fragile Areas

**`finance-mcp/auth/db.py` is a single failure domain for unrelated product areas:**
- Files: `finance-mcp/auth/db.py`, `finance-mcp/tests/test_auth_db_schema.py`
- Why fragile: the file owns schema bootstrapping, auth, conversations, platform apps, unified data sources, snapshots, bindings, auto runs, execution schemes, and exception tasks. It also contains many broad `except Exception` blocks and return-value fallbacks.
- Safe modification: extract one bounded context at a time, starting with `conversations`, `data_sources`, and `execution_runs`; keep compatibility shims at the import boundary until call sites are moved.
- Test coverage: current tests focus on schema helpers and a small slice of data-source behavior; there is no comparable direct test suite for conversation flows, auth flows, or most execution-plan CRUD in `finance-mcp/auth/db.py`.

**`finance-agents/data-agent/server.py` mixes app bootstrap, routers, websocket streaming, upload handling, and persistence side effects:**
- Files: `finance-agents/data-agent/server.py`
- Why fragile: websocket request handling, conversation persistence, LangGraph bootstrapping, error formatting, and REST route wiring live in one module, with broad exception handling and direct `print()` fallback on graph failures.
- Safe modification: extract websocket session handling and upload flow into dedicated service modules before changing protocol behavior; keep startup and shutdown wiring thin.
- Test coverage: there is no direct test module for `finance-agents/data-agent/server.py`; root tests cover only narrow recon API/service slices in `tests/test_recon_internal_api_semantics.py` and `tests/test_recon_pipeline_service.py`.

**Frontend core screens are stateful god components with inline networking:**
- Files: `finance-web/src/App.tsx`, `finance-web/src/components/DataConnectionsPanel.tsx`, `finance-web/src/components/ReconWorkspace.tsx`
- Why fragile: UI state, fetch orchestration, optimistic updates, and conditional rendering are coupled in large files. `finance-web/src/App.tsx` still contains an explicit TODO for unused task-panel state and many debug `console.log` statements.
- Safe modification: extract API access into hooks, move derived state into reducers or state machines, and only then split JSX sections into smaller components.
- Test coverage: tracked frontend tests emphasize end-to-end flows in `finance-web/tests/e2e/*.spec.ts`; direct unit coverage for these largest screen components is comparatively thin.

**`finance-agents/data-agent/tools/mcp_client.py` couples transport reliability to application behavior:**
- Files: `finance-agents/data-agent/tools/mcp_client.py`, `finance-agents/data-agent/tests/platform/test_platform_connections.py`, `finance-agents/data-agent/tests/recon/test_auto_run_service.py`
- Why fragile: one module owns SSE session management, retry and timeout behavior, auth wrappers, mock connectors, dataset semantics mocks, and many domain-specific call helpers.
- Safe modification: separate transport and session code from business wrappers first, then split platform, data-source, and recon clients into focused modules.
- Test coverage: tests mostly monkeypatch high-level functions; they do not exercise the real SSE handshake and request/response matching end to end.

## Scaling Limits

**Dataset catalog and candidate discovery are hard-capped in application code:**
- Current capacity: `AUTO_DISCOVER_DATASET_LIMIT = 300`, `AUTO_SAMPLE_DATASET_LIMIT = 20`, `DATASET_CANDIDATE_MAX_SCAN_PAGES = 200`, `SEMANTIC_SAMPLE_ROW_LIMIT = 10`.
- Limit: large organizations with many sources and datasets will see incomplete discovery, slow candidate search, or both.
- Scaling path: add indexed dataset catalog tables or search views, background refresh, and page-local scoring instead of whole-catalog scans.
- Files: `finance-mcp/tools/data_sources.py`

**Execution preview and recon trial flows depend on local temp files and single-request work:**
- Current capacity: one request builds previews, DataFrames, diff results, and output files inside the request path.
- Limit: concurrent large-file previews will compete for RAM, CPU, and temp filesystem space.
- Scaling path: isolate preview workers, persist trial jobs, and cap concurrent heavy previews per company and source.
- Files: `finance-mcp/tools/execution_runs.py`, `finance-mcp/recon/mcp_server/recon_tool.py`

**Frontend E2E validation is effectively single-threaded and environment-bound:**
- Current capacity: Playwright runs with `workers: 1` and `fullyParallel: false`, against live local services.
- Limit: suite runtime grows linearly and failures often depend on shared database and browser state.
- Scaling path: seed isolated test tenants, remove destructive/manual specs from the default suite, and split smoke versus full-stack scenarios.
- Files: `finance-web/playwright.config.ts`, `finance-web/tests/e2e/recon-center.spec.ts`, `finance-web/tests/e2e/data-connections-semantic-cache.spec.ts`, `finance-web/tests/e2e/tmp-manual-semantic-refresh.spec.ts`

## Dependencies at Risk

**Primary risk is custom integration code, not a single package version:**
- Risk: the highest-maintenance surface is the repo’s own integration glue around MCP SSE, connector previews, LangGraph orchestration, and React screen logic.
- Impact: upgrading supporting libraries will be less dangerous than changing the app-specific abstraction layers without stronger contracts.
- Migration plan: stabilize internal boundaries first in `finance-agents/data-agent/tools/mcp_client.py`, `finance-mcp/tools/data_sources.py`, `finance-mcp/tools/execution_runs.py`, and `finance-web/src/components/*` before any broad dependency refresh.

## Missing Critical Features

**Real platform connector support is incomplete:**
- Problem: real Taobao and Douyin Shop connector flows stop at `NotImplementedError`, so the platform OAuth feature set is only fully usable in mock mode.
- Blocks: real store authorization, token refresh, and shop profile sync for those platforms.
- Files: `finance-mcp/platforms/connectors/taobao.py`, `finance-mcp/platforms/connectors/douyin_shop.py`

**Secrets management is optional instead of enforced:**
- Problem: the servers start and continue working with default JWT credentials, default database credentials, and reversible fallback secret storage.
- Blocks: secure production deployment and auditable credential handling.
- Files: `finance-mcp/auth/jwt_utils.py`, `finance-mcp/db_config.py`, `finance-agents/data-agent/config.py`, `finance-mcp/auth/crypto.py`, `finance-mcp/auth/db.py`

## Test Coverage Gaps

**Core backend servers have only narrow slice tests:**
- What's not tested: direct coverage for websocket chat flow, upload flow, auth session persistence side effects, and most of the `finance-mcp/auth/db.py` CRUD surface.
- Files: `finance-agents/data-agent/server.py`, `finance-mcp/auth/db.py`, `tests/test_recon_internal_api_semantics.py`, `tests/test_recon_pipeline_service.py`, `finance-mcp/tests/test_auth_db_schema.py`
- Risk: protocol regressions or persistence bugs can ship even when the current test suite stays green.
- Priority: High

**Real transport and real connector paths are lightly exercised:**
- What's not tested: end-to-end MCP SSE request and response handling in `finance-agents/data-agent/tools/mcp_client.py` and non-mock platform OAuth or data-source flows.
- Files: `finance-agents/data-agent/tools/mcp_client.py`, `finance-agents/data-agent/tests/platform/test_platform_connections.py`, `finance-mcp/platforms/connectors/taobao.py`, `finance-mcp/platforms/connectors/douyin_shop.py`
- Risk: mock mode hides transport bugs, timeout handling issues, and real API contract drift.
- Priority: High

**Frontend screen logic is larger than its direct unit coverage:**
- What's not tested: many branches inside `finance-web/src/App.tsx`, `finance-web/src/components/DataConnectionsPanel.tsx`, and `finance-web/src/components/ReconWorkspace.tsx`, especially localStorage recovery, inline error states, and long multi-step editing flows.
- Files: `finance-web/src/App.tsx`, `finance-web/src/components/DataConnectionsPanel.tsx`, `finance-web/src/components/ReconWorkspace.tsx`, `finance-web/tests/e2e/recon-center.spec.ts`, `finance-web/tests/e2e/data-connections-governance.spec.ts`, `finance-web/tests/e2e/data-connections-semantic-cache.spec.ts`
- Risk: UI regressions remain hard to localize, and failures surface only in slow full-stack tests.
- Priority: Medium

**Security fallback behavior lacks targeted tests:**
- What's not tested: startup rejection when default JWT or DB secrets remain, mandatory secret-key enforcement, and the plaintext or fallback branches around secret sealing.
- Files: `finance-mcp/auth/jwt_utils.py`, `finance-mcp/auth/crypto.py`, `finance-mcp/auth/db.py`, `finance-agents/data-agent/graphs/collaboration/api.py`
- Risk: insecure defaults survive refactors because the repo currently tests mostly happy-path behavior.
- Priority: High

---

*Concerns audit: 2026-04-22*
