# Testing Patterns

**Analysis Date:** 2026-04-22

## Test Framework

**Runner:**
- Frontend component tests use Vitest `3.2.4` from `finance-web/package.json`, configured in `finance-web/vitest.config.ts`.
- Frontend browser tests use Playwright `1.59.1` from `finance-web/package.json`, configured in `finance-web/playwright.config.ts`.
- Python service tests use pytest-style suites under `finance-agents/data-agent/tests/` and `finance-mcp/tests/`. No checked-in `pytest.ini`, `tox.ini`, or `[tool.pytest.ini_options]` section was detected.

**Assertion Library:**
- Vitest `expect` plus `@testing-library/jest-dom/vitest` from `finance-web/tests/setup.ts`.
- Playwright `expect` from `@playwright/test` in `finance-web/tests/e2e/*.spec.ts`.
- Python uses plain `assert`, `pytest.raises`, and `pytest.mark.parametrize`, for example `finance-agents/data-agent/tests/recon/test_auto_scheme_run_nodes.py` and `finance-agents/data-agent/tests/recon/test_scheme_design_executor.py`.

**Run Commands:**
```bash
cd /Users/kevin/workspace/financial-ai/finance-web && npm run test:components
cd /Users/kevin/workspace/financial-ai/finance-web && npx vitest
cd /Users/kevin/workspace/financial-ai/finance-web && npm run test:e2e
cd /Users/kevin/workspace/financial-ai && pytest finance-mcp/tests finance-agents/data-agent/tests
```

## Test File Organization

**Location:**
- Frontend tests are kept in a separate `finance-web/tests/` tree rather than next to source files. `finance-web/tests/components/` holds jsdom tests and `finance-web/tests/e2e/` holds Playwright specs.
- Python tests live inside each service package: `finance-agents/data-agent/tests/` and `finance-mcp/tests/`.

**Naming:**
- Python uses `test_*.py`, for example `finance-mcp/tests/test_database_connector.py` and `finance-agents/data-agent/tests/recon/test_auto_run_service.py`.
- Frontend component tests use descriptive kebab-case names with `.test.ts`, `.test.tsx`, or `.spec.tsx`, for example `finance-web/tests/components/recon-auto-api.test.ts` and `finance-web/tests/components/recon-workspace-scheme-delete-guard.test.tsx`.
- Frontend E2E tests use `.spec.ts` under `finance-web/tests/e2e/`, for example `finance-web/tests/e2e/recon-center.spec.ts` and `finance-web/tests/e2e/data-connections-governance.spec.ts`.
- `finance-web/tests/e2e/tmp-manual-semantic-refresh.spec.ts` is a checked-in Playwright spec and is part of the detected test tree.

**Structure:**
```text
finance-web/tests/
  components/
  e2e/
  setup.ts

finance-agents/data-agent/tests/
  conftest.py
  notifications/
  platform/
  recon/
  test_*.py

finance-mcp/tests/
  test_*.py
```

## Test Structure

**Suite Organization:**
```typescript
describe('recon auto api', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('falls back to the secondary recon proxy path after a 404', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 404 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const response = await fetchReconAutoApi('/schemes/design/session-1', {
      method: 'GET',
    });

    expect(response.ok).toBe(true);
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/recon/schemes/design/session-1', {
      method: 'GET',
    });
  });
});
```

```python
@pytest.mark.parametrize(
    ("raw_trigger_type", "expected_trigger_type"),
    [("manual", "api"), ("cron", "schedule")],
)
def test_build_auto_run_context_node_normalizes_trigger_type(
    raw_trigger_type: str,
    expected_trigger_type: str,
) -> None:
    result = auto_scheme_run_nodes.build_auto_run_context_node(...)
    assert result["recon_ctx"]["run_context"]["trigger_type"] == expected_trigger_type
```

**Patterns:**
- Frontend component tests use `beforeEach` and `afterEach`, stub browser globals, render real components, and assert visible UI through `screen.findBy...`, `screen.getBy...`, and `waitFor(...)`. See `finance-web/tests/components/data-connections-panel.test.tsx` and `finance-web/tests/components/scheme-wizard-components.test.tsx`.
- Frontend E2E tests keep helper functions inside the spec file for auth setup, localStorage seeding, and ad hoc API calls. See `registerAuthSession`, `seedAuthSession`, and `fetchAuthedJson` in `finance-web/tests/e2e/recon-center.spec.ts`.
- Python tests usually call module functions directly instead of spinning up an HTTP test client. Async functions are invoked with `asyncio.run(...)`. See `finance-agents/data-agent/tests/recon/test_auto_run_service.py` and `finance-mcp/tests/test_data_source_tools.py`.
- Route tests in `finance-agents/data-agent/tests/` call FastAPI route functions directly rather than using `TestClient`, for example `finance-agents/data-agent/tests/test_data_source_publish_routes.py` and `finance-agents/data-agent/tests/recon/test_auto_run_api.py`.

## Mocking

**Framework:** Vitest spies/stubs in frontend; pytest `monkeypatch` in Python

**Patterns:**
```typescript
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});
```

```python
monkeypatch.setattr(auto_run_service, "recon_auto_task_get", fake_task_get)
monkeypatch.setattr(auto_run_service, "execute_headless_recon_pipeline", fake_pipeline)

result = asyncio.run(
    auto_run_service.execute_auto_task_run(
        auth_token="token",
        auto_task_id="task_001",
        biz_date="2026-04-02",
    )
)
assert result["success"] is True
```

**What to Mock:**
- Frontend mocks network boundaries and browser globals, especially `fetch`, `window.confirm`, and localStorage state. See `finance-web/tests/components/data-connections-panel.test.tsx` and `finance-web/tests/components/recon-workspace-scheme-delete-guard.test.tsx`.
- Python tests mock MCP calls, database access, connector methods, repository helpers, and adapter side effects. See `finance-mcp/tests/test_data_source_tools.py`, `finance-mcp/tests/test_database_connector.py`, and `finance-agents/data-agent/tests/recon/test_auto_scheme_run_nodes.py`.
- External process execution is mocked instead of invoked, for example `services.notifications.cli.subprocess.run` in `finance-agents/data-agent/tests/test_notifications_dingtalk.py`.

**What NOT to Mock:**
- Local parsing and shaping helpers are usually tested directly instead of wrapped behind mocks, for example `parseSseChunk` in `finance-web/tests/components/recon-auto-api.test.ts`.
- Component tests render the real component tree with realistic prop objects; they do not shallow render or replace the component under test with stubs.
- No default `TestClient`-style HTTP integration layer is present for Python. Follow the existing pattern of direct function invocation unless a new test explicitly needs request/response middleware coverage.

## Fixtures and Factories

**Test Data:**
```typescript
function buildJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}
```

```python
class FakeConnector:
    def preview(self, arguments):
        return {"rows": [{"id": 1, "name": "foo"}]}
```

**Location:**
- Frontend helper builders are local to the spec file, for example `buildJsonResponse` in `finance-web/tests/components/data-connections-panel.test.tsx` and `createStreamResponse` in `finance-web/tests/components/recon-auto-api.test.ts`.
- E2E helpers are also file-local rather than shared utilities, for example `registerAuthSession`, `openReconCenter`, and `selectDatasetInDropdown` in `finance-web/tests/e2e/recon-center.spec.ts`.
- Python uses inline fake async functions, fake connector classes, and temporary captured dicts inside each file. Shared setup is minimal and mostly limited to import bootstrapping in `finance-agents/data-agent/tests/conftest.py`.
- No centralized fixture factory package or shared test-data library was detected.

## Coverage

**Requirements:** None enforced

**View Coverage:**
```bash
Not configured in `finance-web/package.json`, `finance-web/vitest.config.ts`, or any checked-in Python pytest config.
```

## Test Types

**Unit Tests:**
- Frontend unit and component tests live in `finance-web/tests/components/` and run in jsdom with React Testing Library. They verify render output, interaction state, request payload shaping, and small utilities.
- Python tests under `finance-mcp/tests/` and `finance-agents/data-agent/tests/` are mostly unit tests around service functions, route helpers, connector classes, and orchestration nodes.

**Integration Tests:**
- Playwright specs are the main checked-in integration layer because they exercise the real browser UI against live `/api` flows via the Vite proxy configured in `finance-web/vite.config.ts`.
- Python does not currently maintain a separate HTTP integration suite using `TestClient` or `AsyncClient`. Route-level tests invoke async route functions directly, for example `finance-agents/data-agent/tests/test_data_source_publish_routes.py`.
- Some `finance-mcp` tests instantiate real connector classes and patch only the low-level DB or HTTP edges, which makes them closer to targeted integration tests than pure unit tests. See `finance-mcp/tests/test_database_connector.py`.

**E2E Tests:**
- Playwright only. `finance-web/playwright.config.ts` sets `testDir: './tests/e2e'`, `workers: 1`, `fullyParallel: false`, a `60_000` ms test timeout, retries only in `CI`, and retained traces/screenshots/videos on failure.
- E2E specs create users, seed tokens into localStorage, and drive the real UI through role-based selectors. See `finance-web/tests/e2e/recon-center.spec.ts` and `finance-web/tests/e2e/recon-center-keyflows.spec.ts`.

## Common Patterns

**Async Testing:**
```typescript
await waitFor(() => {
  expect(patchRequests).toHaveLength(1);
});
```

```python
result = asyncio.run(
    auto_run_service.execute_run_plan_run(
        auth_token="token",
        run_plan_code="plan_100",
        biz_date="2026-04-13",
        trigger_mode="manual",
        run_context={"initiated_by": "pytest"},
    )
)
assert result["success"] is True
```

**Error Testing:**
```typescript
await expect(
  fetchReconAutoApi('/schemes/design/sess-2/proc/generate/stream', { method: 'POST' }),
).rejects.toThrow('请检查前端代理或 data-agent 服务是否可用后重试');
```

```python
with pytest.raises(ValueError, match="真实 table_name"):
    ...
```

---

*Testing analysis: 2026-04-22*
