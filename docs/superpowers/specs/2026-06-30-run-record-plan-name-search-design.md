# Run Record Plan Name Search Design

## Goal

Add keyword search to the reconciliation run records page, limited to run plan names, and show an in-list loading state when refreshing the run records list.

## Scope

- Applies only to the run records tab in `ReconWorkspace`.
- Keyword search matches `execution_run_plans.plan_name`.
- Existing date filters, pagination, run actions, and exception dashboard behavior remain unchanged.
- Search does not include scheme names, statuses, failure reasons, run codes, exception details, or raw record contents.

## User Experience

The run records filter bar adds a `运行计划名` text input next to the existing start and end date filters.

Clicking `筛选` reloads page 1 with the current plan-name keyword and date filters. Clicking `清空` clears keyword and date filters, then reloads page 1. The top-level `刷新` button on the run records tab preserves the current filters and reloads page 1.

When a refresh or page/filter load is running and rows already exist, the list area shows a lightweight overlay with a spinning refresh icon and loading text. The existing rows remain visible behind the overlay. When no rows are loaded yet, the existing empty or initial loading behavior is used.

## Architecture

Frontend:
- Add run keyword state in `ReconWorkspace`.
- Extend `buildRunListQuery` to include `keyword`.
- Pass keyword through `loadCenterData`, `loadRunsPage`, apply-filter, clear-filter, pagination, and refresh paths.
- Add a small list-area loading overlay in the run records table wrapper, using existing `runsPageLoading`.

Data-agent API:
- Add `keyword` query parameter to `GET /api/recon/runs`.
- Pass keyword to `execution_run_list`.

MCP/client:
- Add optional `keyword` to `execution_run_list` tool schema and data-agent MCP client helper.
- Pass keyword to run list/count DB functions.

Database:
- Update `list_execution_runs` and `count_execution_runs` to apply:
  `plan.plan_name ILIKE %keyword%`
- Keep the count query using the same filter as the list query, so pagination totals remain accurate.

## Error Handling

Existing run-list error handling remains the authority. If the filtered query fails, the page shows the current `centerError` message. The loading overlay is removed in the existing `finally` path.

## Testing

Frontend component tests should verify:
- Entering a plan name and clicking `筛选` calls `/api/recon/runs` with `keyword`.
- Clicking `清空` removes keyword and date filters.
- Refresh on the run records tab preserves the keyword filter.
- Loading existing rows renders an in-list loading indicator instead of replacing the whole center content.

Backend tests should verify:
- Data-agent `/api/recon/runs` accepts and forwards `keyword`.
- MCP `execution_run_list` forwards keyword to DB list and count calls.
- DB list/count SQL applies the same `plan_name ILIKE` filter.
