# Database Dataset Detail Preview Design

## Context

Database connection datasets no longer need the old "daily collection" product surface.
However, the database data connection page still exposes collection-oriented UI in available
datasets:

- dataset card action text: `采集详情`
- modal title/loading text: `采集详情` / `正在加载采集详情。`
- manual collection actions such as `立即采集` and date collection
- recent collection job/status sections

Users now need a generic dataset detail surface instead. The detail view should keep the useful
part of the old modal: showing the latest 10 data rows for the selected dataset.

Those same latest 10 rows also support the new reconciliation scheme wizard. In step 2, after a
user selects a database dataset, the wizard must be able to preview real data from that dataset.

## Goal

Replace database dataset collection detail with dataset detail and make latest-row preview a
shared dataset capability.

The result should be:

- In database connections, available dataset cards show `详情`, not `采集详情`.
- The database dataset detail modal shows dataset metadata and `最新 10 条数据`.
- The database dataset detail modal does not show collection jobs, collection stats, `立即采集`,
  or date collection controls.
- `更新数据集` and `指定数据集更新` refresh a cached latest-10 preview for database datasets.
- Reconciliation scheme wizard step 2 can show those rows after a database dataset is selected.
- If cached rows are missing or stale, the wizard/detail view can fetch preview rows on demand
  through the same preview capability.

## Non-Goals

- Do not remove collection detail for platform OAuth or browser collection datasets. Those
  datasets still have real collection tasks and should keep their collection UI.
- Do not reintroduce daily database dataset collection or scheduler configuration.
- Do not delete backend collection APIs in this change; other dataset kinds may still depend on
  them.
- Do not redesign the full data connection page or reconciliation wizard.
- Do not special-case a single customer table or reconciliation plan.

## Data Contract

Add a cached preview sample to the unified dataset metadata for database datasets.

Recommended storage shape inside dataset `meta`:

```json
{
  "preview_sample": {
    "rows": [{ "id": 1, "amount": 100 }],
    "limit": 10,
    "row_count": 10,
    "resource_key": "public.orders",
    "fetched_at": "2026-06-11T10:00:00+08:00",
    "source": "dataset_discover",
    "order": "date_field_desc",
    "order_field": "updated_at"
  }
}
```

If preview fetching fails during dataset update, do not fail the dataset update. Keep the previous
successful `rows` when available and store failure metadata:

```json
{
  "preview_sample": {
    "rows": [{ "id": 1, "amount": 100 }],
    "limit": 10,
    "row_count": 10,
    "resource_key": "public.orders",
    "fetched_at": "2026-06-11T10:00:00+08:00",
    "source": "dataset_discover",
    "order": "date_field_desc",
    "order_field": "updated_at",
    "error": "permission denied",
    "error_at": "2026-06-11T10:05:00+08:00"
  }
}
```

Expose `preview_sample` on dataset list/detail responses so frontend source options can carry
sample rows without calling a collection endpoint.

## Latest Row Ordering

For database previews, "latest" should be best-effort and explicit:

1. Prefer the dataset configured date/update field when present.
2. Otherwise prefer common sortable fields from schema metadata, such as `updated_at`,
   `update_time`, `modified_at`, `created_at`, `create_time`, or an integer primary key.
3. If no reliable sort field exists, fall back to the connector's current preview order and mark
   `preview_sample.order` as `connector_default`.

The UI can still label the table `最新 10 条数据`; the metadata keeps the ordering truth available
for debugging and future refinement.

## Backend Design

### Dataset Update Preview Refresh

In `data_source_discover_datasets`, refresh preview samples for database datasets when datasets are
updated or persisted.

Behavior:

- For `指定数据集更新`, refresh preview rows for the specified dataset resource keys.
- For broad `更新数据集`, refresh previews for the datasets processed in that update. Use batching
  or low concurrency if needed, but do not silently skip processed datasets; the refreshed previews
  are what let later reconciliation scheme creation show real rows immediately.
- Preview failures should be non-fatal. Dataset discovery/update should still succeed.
- Successful preview refresh writes `meta.preview_sample`.

The preview fetch should use the database connector with the selected `resource_key`, `limit: 10`,
and the ordering rules above.

### Generic Dataset Detail

Add a database-oriented dataset detail API instead of reusing collection detail:

```text
GET /api/data-sources/{source_id}/datasets/{dataset_id}/detail
  ?resource_key=...
  &sample_limit=10
  &refresh=false
```

Response shape:

```json
{
  "success": true,
  "source_id": "source-id",
  "resource_key": "public.orders",
  "dataset": { "id": "dataset-id", "meta": { "preview_sample": {} } },
  "field_groups": [],
  "rows": [],
  "preview_sample": {},
  "sample_limit": 10,
  "row_count": 0,
  "message": "已获取数据集详情"
}
```

For database datasets:

- `refresh=false` returns cached preview rows when available.
- `refresh=true` performs a live connector preview, updates `meta.preview_sample`, and returns the
  refreshed rows.
- If live preview fails but cached rows exist, return cached rows plus preview error metadata.
- The response does not include collection jobs or collection status.

The existing `collection-detail` endpoint remains for platform/browser datasets.

### Data Source Preview

The data-agent REST request model for `/data-sources/{source_id}/preview` currently accepts `limit`
and `mode`, while the lower-level MCP client already supports `resource_key`. Extend the REST
request model and route so preview requests can pass:

- `resource_key`
- optional `dataset_id`

Then pass `resource_key` through to `data_source_preview`.

This is required so the reconciliation wizard can preview the exact selected dataset instead of
falling back to a source-level default.

## Frontend Design

### Data Connections

In `DataConnectionsPanel`:

- For database sources, change available dataset card action text from `采集详情` to `详情`.
- Open a database dataset detail dialog backed by the generic detail API.
- Use loading/error copy with detail language, for example `正在加载详情。`.
- Show the existing field-aware sample table pattern, limited to 10 rows.
- Remove database collection controls from this modal:
  - no `立即采集`
  - no `按日期采集`
  - no recent collection jobs
  - no collection task/stat cards

Keep collection detail UI for platform OAuth and browser collection datasets.

Because `DataConnectionsPanel.tsx` is already a large hotspot, implementation should avoid adding
another large block there. Prefer extracting a focused database detail dialog/helper module if the
change would otherwise grow the file materially.

### Reconciliation Scheme Wizard Step 2

The scheme wizard must consume the same preview sample.

Implementation shape:

- Add optional sample fields to `SchemeSourceOption`, such as `sampleRows` and `sampleOrigin`.
- When building source options from available datasets, map `dataset.meta.preview_sample.rows` into
  `sampleRows`.
- When a user selects a dataset, show cached `sampleRows` immediately if present.
- If rows are missing, use the preview API with `source_id`, `dataset_id`, `resource_key`, and
  `limit: 10` to fetch rows for that dataset.
- Stop using database `collection-detail` as the source of sample rows in the wizard and rule
  generation code.

Relevant current callers to replace include:

- `finance-web/src/components/recon/SchemeWizardTargetProcStep.tsx`
- `finance-web/src/components/recon/ruleGenerationState.ts`

Field metadata can continue using the existing `/api/recon/schemes/design/dataset-fields` route.
The row preview should come from the shared dataset preview capability.

### Data-Agent Scheme Design

`finance-agents/data-agent/graphs/recon/scheme_design/service.py` already falls back to
`data_source_preview` when sample rows are missing. After the preview route accepts and forwards
`resource_key`, this fallback becomes the backend counterpart to the frontend wizard preview.

This keeps AI rule generation and frontend preview aligned: both see sample rows from the selected
database dataset, not synthetic rows or a different table.

## Error Handling

- Dataset update preview refresh failure should not fail dataset update.
- Detail view should show cached rows when live refresh fails and cached rows exist.
- Detail view should show a concise empty/error state when no cached or live rows are available.
- Scheme wizard should fall back to field-only display if preview rows cannot be loaded.
- Rule generation should continue with schema fields when sample rows are unavailable, but should
  prefer real rows whenever the preview API returns them.

## Testing

Backend tests:

- Database dataset discovery/update stores `meta.preview_sample.rows` for targeted datasets.
- Preview refresh failure leaves discovery/update successful.
- Dataset detail for database returns rows from `preview_sample` and does not return collection
  jobs.
- Preview API accepts `resource_key` and forwards it to MCP/client preview.
- Database preview ordering chooses a configured date field when available and records the selected
  ordering metadata.

Frontend tests:

- Database available dataset action renders `详情`.
- Database detail modal loading/error/title copy uses detail language, not collection language.
- Database detail modal does not render `立即采集`, `按日期采集`, or recent collection job sections.
- Database detail modal renders latest 10 rows from the detail/preview response.
- Scheme wizard step 2 shows cached `preview_sample.rows` after selecting a database dataset.
- Scheme wizard/rule generation preview calls the preview API with the selected `resource_key`
  instead of database `collection-detail`.
- Platform/browser collection detail still renders collection actions where applicable.

Build/verification:

- Run focused backend pytest for data source preview/detail behavior.
- Run focused frontend tests for data connections and scheme wizard preview behavior.
- Run `npm run build` in `finance-web`.

## Rollout

No database migration is required if `preview_sample` is stored in existing dataset `meta` JSON.

After implementation, restart affected services:

- finance-mcp
- data-agent
- finance-web

Existing database datasets will get preview samples the next time the user runs `更新数据集` or
`指定数据集更新`. On-demand preview still covers datasets whose cache has not been warmed yet.

## Confirmed Direction

No open product decisions remain. The confirmed direction is the hybrid approach:

- update flows warm/cache latest 10 rows
- detail and wizard prefer cached rows
- detail and wizard can fetch preview rows on demand when cache is absent or stale
