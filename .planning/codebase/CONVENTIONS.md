# Coding Conventions

**Analysis Date:** 2026-04-22

## Naming Patterns

**Files:**
- Python implementation files use snake_case module names, especially under `finance-mcp/` and `finance-agents/data-agent/graphs/`, for example `finance-mcp/tools/execution_runs.py`, `finance-mcp/tools/data_sources.py`, and `finance-agents/data-agent/graphs/recon/auto_run_service.py`.
- React component files use PascalCase in `finance-web/src/components/`, for example `finance-web/src/components/DataConnectionsPanel.tsx`, `finance-web/src/components/ReconWorkspace.tsx`, and `finance-web/src/components/Sidebar.tsx`.
- Frontend helper, hook, and config modules use camelCase or lowercase filenames, for example `finance-web/src/components/recon/autoApi.ts`, `finance-web/src/collaborationChannelDrafts.ts`, `finance-web/src/hooks/useConversations.ts`, and `finance-web/src/types.ts`.
- Python tests follow `test_*.py` naming in `finance-mcp/tests/` and `finance-agents/data-agent/tests/`. Frontend tests use descriptive kebab-case names with `.test.ts`, `.test.tsx`, or `.spec.tsx`, for example `finance-web/tests/components/recon-auto-api.test.ts` and `finance-web/tests/components/recon-fallback-warning.spec.tsx`.

**Functions:**
- Python functions are snake_case. Private helpers are prefixed with `_`, for example `_build_anomaly_summary` in `finance-agents/data-agent/graphs/recon/auto_run_service.py` and `_json_default` in `finance-mcp/unified_mcp_server.py`.
- TypeScript functions and hooks are camelCase. Hooks retain `use*` names, for example `fetchReconAutoApi` in `finance-web/src/components/recon/autoApi.ts`, `useConversations` in `finance-web/src/hooks/useConversations.ts`, and `toggleTheme` in `finance-web/src/theme.ts`.

**Variables:**
- Module constants use upper snake case across Python and TypeScript, for example `TRACKED_NODE_NAMES` in `finance-agents/data-agent/server.py`, `_DEFAULT_RECON_OUTPUT_SHEETS` in `finance-mcp/tools/execution_runs.py`, `STORAGE_KEY_THEME` in `finance-web/src/theme.ts`, and `DEFAULT_COMPANY_ID` in `finance-web/tests/e2e/recon-center.spec.ts`.
- TypeScript keeps backend payload fields in snake_case when the UI mirrors API contracts, for example `rule_code`, `created_at`, `dataset_code`, and `resource_key` in `finance-web/src/types.ts` and `finance-web/src/hooks/useConversations.ts`.
- Local runtime state in React components stays camelCase, for example `selectedConnectionView`, `businessNameInput`, and `patchRequests` in `finance-web/src/components/DataConnectionsPanel.tsx` and `finance-web/tests/components/data-connections-panel.test.tsx`.

**Types:**
- Python classes and Pydantic models use PascalCase, for example `DatabaseConfig` in `finance-mcp/db_config.py`, `StrictModel` in `finance-mcp/tools/rule_schema.py`, and `AutoTaskCreateRequest` in `finance-agents/data-agent/graphs/recon/auto_run_api.py`.
- TypeScript uses `type` for unions and aliases and `interface` for object shapes, for example `ThemeMode` in `finance-web/src/theme.ts`, `MessageRole` and `DataSourceKind` in `finance-web/src/types.ts`, and `ApiConversation` in `finance-web/src/hooks/useConversations.ts`.

## Code Style

**Formatting:**
- Frontend formatting is constrained by `finance-web/eslint.config.js` and TypeScript compiler settings in `finance-web/tsconfig.app.json` and `finance-web/tsconfig.node.json`. No Prettier or Biome config is checked in.
- `finance-web/tsconfig.app.json` enables `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, and `noUncheckedSideEffectImports`. New frontend code should remain compatible with those flags.
- Python has no checked-in `ruff`, `black`, `flake8`, or `mypy` config in `finance-mcp/` or `finance-agents/data-agent/`. Formatting is convention-driven rather than tool-enforced.
- Newer Python modules use module docstrings, blank-line grouping, and section dividers, for example `finance-agents/data-agent/config.py`.
- Decorative section dividers also appear in TypeScript files that act as shared schema or state definitions, for example `finance-web/src/types.ts`.
- TypeScript formatting is not globally normalized. `finance-web/src/main.tsx` and `finance-web/vite.config.ts` are semicolonless, while `finance-web/src/types.ts`, `finance-web/src/hooks/useConversations.ts`, and `finance-web/tests/components/recon-auto-api.test.ts` use semicolons. When editing, match the surrounding file style instead of reformatting unrelated lines.

**Linting:**
- `finance-web/eslint.config.js` applies `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, and `eslint-plugin-react-refresh` to `**/*.{ts,tsx}` and ignores `dist/`.
- No equivalent repo-wide Python lint configuration is present. The closest repo guidance is convention-only, not machine-enforced.

## Import Organization

**Order:**
1. In newer Python modules, place `from __future__ import annotations` first, then standard library imports, then third-party packages, then local imports. Examples: `finance-agents/data-agent/server.py`, `finance-agents/data-agent/graphs/recon/auto_run_service.py`, `finance-mcp/tools/data_sources.py`, and `finance-mcp/tools/rule_schema.py`.
2. In TypeScript, import external libraries first, then local values, then `import type` statements when only types are needed. Examples: `finance-web/src/App.tsx`, `finance-web/src/components/DataConnectionsPanel.tsx`, and `finance-web/src/hooks/useConversations.ts`.
3. In tests, Python frequently bootstraps imports manually with `sys.path.insert(...)` and `importlib.util.spec_from_file_location(...)` because packages are not always imported as installed distributions. Examples: `finance-mcp/tests/test_data_source_tools.py`, `finance-mcp/tests/test_unified_mcp_server_routes.py`, and `finance-agents/data-agent/tests/test_data_source_publish_routes.py`.

**Path Aliases:**
- No TypeScript path aliases are configured in `finance-web/tsconfig.json` or `finance-web/tsconfig.app.json`. Use relative imports such as `../types` or `../../src/components/...`.
- Python code uses direct package-relative imports where package layout permits, but tests rely on explicit path setup from `finance-agents/data-agent/tests/conftest.py`.

## Error Handling

**Patterns:**
- `finance-mcp` tool handlers usually return dictionaries with `success`, `error`, and domain payload keys instead of raising. Examples: `finance-mcp/tools/data_sources.py`, `finance-mcp/tools/execution_runs.py`, `finance-mcp/tools/rules.py`, and `finance-mcp/recon/mcp_server/recon_tool.py`.
- `finance-agents/data-agent` FastAPI layers translate service failures into `HTTPException` with user-facing Chinese detail strings. Examples: `finance-agents/data-agent/server.py`, `finance-agents/data-agent/graphs/data_source/api.py`, `finance-agents/data-agent/graphs/platform/api.py`, and `finance-agents/data-agent/graphs/recon/scheme_design/api.py`.
- Frontend network code checks `response.ok`, parses backend error payloads, and throws `Error` with human-readable Chinese messages. Examples: `finance-web/src/components/recon/autoApi.ts` and `finance-web/src/hooks/useConversations.ts`.
- Legacy Python code may still wrap failures in generic `Exception`, for example `finance-mcp/db_config.py`. New work should preserve compatibility in touched files but follow the more explicit pattern already used in `finance-agents/data-agent/` and newer `finance-mcp/tools/*.py` modules.

## Logging

**Framework:** Python `logging`; frontend `console`

**Patterns:**
- Python modules usually create `logger = logging.getLogger(__name__)` or a named logger, then log structured context with localized messages. Examples: `finance-agents/data-agent/graphs/recon/auto_run_service.py`, `finance-agents/data-agent/services/notifications/repository.py`, `finance-mcp/tools/data_sources.py`, and `finance-mcp/recon/mcp_server/recon_tool.py`.
- Entrypoints configure logging once with `logging.basicConfig(...)`, for example `finance-agents/data-agent/server.py` and `finance-mcp/unified_mcp_server.py`.
- Frontend uses `console.log`, `console.warn`, and `console.error` for state debugging and fetch failure diagnostics, especially in `finance-web/src/App.tsx`, `finance-web/src/hooks/useConversations.ts`, `finance-web/src/hooks/useWebSocket.ts`, `finance-web/src/components/ChatArea.tsx`, and `finance-web/src/components/MessageBubble.tsx`.

## Comments

**When to Comment:**
- Python modules commonly open with docstrings that explain the module purpose, often in Chinese or bilingual text, for example `finance-agents/data-agent/server.py`, `finance-agents/data-agent/graphs/recon/auto_run_service.py`, and `finance-mcp/tools/data_sources.py`.
- Inline comments are used for side-effect ordering, environment loading, or UI state management, for example the `.env` load ordering note in `finance-agents/data-agent/server.py` and the localStorage notes in `finance-web/src/App.tsx`.
- Decorative section dividers are part of the local style in both Python and TypeScript, for example `finance-agents/data-agent/config.py` and `finance-web/src/types.ts`.

**JSDoc/TSDoc:**
- TypeScript uses lightweight inline docs rather than heavy API documentation. Examples include field comments in `finance-web/src/types.ts` and helper comments in `finance-web/src/App.tsx`.
- Python docstrings are more common than TS docblocks and are the preferred way to describe service modules and helpers.

## Function Design

**Size:**
- Utility modules keep helpers short and narrowly scoped, for example `finance-web/src/components/recon/autoApi.ts`, `finance-web/src/theme.ts`, and `finance-agents/data-agent/services/notifications/service.py`.
- Core orchestration files are intentionally large and procedural. Examples include `finance-web/src/App.tsx`, `finance-web/src/components/DataConnectionsPanel.tsx`, `finance-web/src/components/ReconWorkspace.tsx`, `finance-mcp/tools/data_sources.py`, and `finance-agents/data-agent/graphs/recon/auto_run_service.py`.
- When extending a large file, prefer adding a focused helper near related logic instead of expanding a single branch in place.

**Parameters:**
- Python service and tool layers often take explicit keyword-heavy arguments and `dict[str, Any]` payloads, for example `execute_run_plan_run(...)` in `finance-agents/data-agent/graphs/recon/auto_run_service.py` and `_handle_data_source_test(...)` in `finance-mcp/tools/data_sources.py`.
- FastAPI request bodies are modeled with `BaseModel` classes and `Field(default_factory=...)`, for example `finance-agents/data-agent/graphs/recon/auto_run_api.py`, `finance-agents/data-agent/graphs/proc/api.py`, and `finance-agents/data-agent/graphs/data_source/api.py`.
- TypeScript components and hooks use explicit prop and result interfaces instead of loose objects, for example `UseConversationsResult` in `finance-web/src/hooks/useConversations.ts` and `DataConnectionsPanelProps` in `finance-web/src/components/DataConnectionsPanel.tsx`.

**Return Values:**
- Python code frequently returns dict-shaped records with a `success` flag rather than custom domain objects, especially in `finance-mcp/tools/*.py` and `finance-agents/data-agent/tools/mcp_client.py`.
- Frontend helpers return typed objects or `Promise<...>` values. Hooks expose explicit result interfaces, as in `finance-web/src/hooks/useConversations.ts` and `finance-web/src/hooks/useWebSocket.ts`.

## Module Design

**Exports:**
- React component modules usually default-export a single component, for example `finance-web/src/App.tsx` and `finance-web/src/components/DataConnectionsPanel.tsx`.
- Frontend utility and hook modules prefer named exports, for example `finance-web/src/theme.ts`, `finance-web/src/hooks/useWebSocket.ts`, and `finance-web/src/collaborationChannelDrafts.ts`.
- Python packages sometimes define explicit public surfaces with `__all__`, for example `finance-mcp/connectors/__init__.py`, `finance-mcp/recon/mcp_server/__init__.py`, `finance-agents/data-agent/graphs/recon/__init__.py`, and `finance-agents/data-agent/graphs/proc/__init__.py`.

**Barrel Files:**
- Barrel usage is minimal and local. `finance-web/src/components/ResponsiveTable/index.ts` is the main TS example.
- Python `__init__.py` files serve the same role when a package wants a curated import surface.
- Prefer direct imports unless a directory already exposes a stable barrel or `__all__` contract.

---

*Convention analysis: 2026-04-22*
