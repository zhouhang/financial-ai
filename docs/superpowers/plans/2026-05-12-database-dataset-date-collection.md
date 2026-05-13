# Database Dataset Date Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-day `按日期采集` action beside `立即采集` in database dataset collection details.

**Architecture:** Reuse the existing dataset collection endpoint and pass `params.biz_date` from the UI. Keep backend collection behavior unchanged: the backend still resolves the dataset's configured collection date field, key fields, driver, and storage. Add only focused frontend state, modal UI, request wiring, and component tests.

**Tech Stack:** React + TypeScript, existing `DataConnectionsPanel`, Vitest + Testing Library, existing FastAPI/MCP proxy endpoints.

---

## File Structure

- Modify: `finance-web/src/components/DataConnectionsPanel.tsx`
  - Add modal state for date collection.
  - Add helpers to read the configured collection date field from collection detail or dataset metadata.
  - Split the current immediate collection request into a reusable function that accepts an optional selected date.
  - Render `按日期采集` beside `立即采集` in the database collection detail drawer.
  - Render a small date modal and submit `params.biz_date`.
- Modify: `finance-web/tests/components/data-connections-platform-auth.spec.tsx`
  - Add a database data source scenario test for the collection detail drawer.
  - Verify the modal and collection request body.
  - Verify the disabled/missing date field behavior.

No backend files should be changed in this implementation.

---

### Task 1: Add Date Collection Request Wiring

**Files:**
- Modify: `finance-web/src/components/DataConnectionsPanel.tsx`
- Test: `finance-web/tests/components/data-connections-platform-auth.spec.tsx`

- [ ] **Step 1: Add a failing test for date collection request payload**

Append this test near the existing collection-detail tests in `finance-web/tests/components/data-connections-platform-auth.spec.tsx`.

```tsx
  it('数据库数据集采集详情支持按单日日期采集', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    let detailCalls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/data-sources/source-db-1/datasets/dataset-order/collection-detail')) {
          detailCalls += 1;
          return mockJsonResponse({
            dataset: {
              id: 'dataset-order',
              data_source_id: 'source-db-1',
              dataset_code: 'public_ods_yxst_trd_order_di_o',
              dataset_name: 'public.ods_yxst_trd_order_di_o',
              business_name: '交易订单明细表',
              resource_key: 'public.ods_yxst_trd_order_di_o',
              collection_config: {
                mode: 'date_field',
                date_field: 'create_date',
              },
            },
            collection_stats: { total_count: 805284 },
            jobs: [
              {
                id: 'job-1',
                status: 'success',
                request_payload: {
                  biz_date: '2026-04-15',
                  date_field: 'create_date',
                },
                metrics: {
                  row_count: 80591,
                  collection_upserted: 80591,
                },
                completed_at: '2026-05-12T09:30:00+08:00',
              },
            ],
            rows: [],
          });
        }
        if (
          url.includes('/data-sources/source-db-1/datasets/dataset-order/collection') &&
          init?.method === 'POST'
        ) {
          return mockJsonResponse({ success: true, message: '同步成功并写入采集记录' });
        }
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'source-db-1',
                source_kind: 'database',
                provider_code: 'hologres',
                name: 'Hologres 订单库',
                status: 'active',
                execution_mode: 'deterministic',
                datasets: [
                  {
                    id: 'dataset-order',
                    data_source_id: 'source-db-1',
                    dataset_code: 'public_ods_yxst_trd_order_di_o',
                    dataset_name: 'public.ods_yxst_trd_order_di_o',
                    business_name: '交易订单明细表',
                    resource_key: 'public.ods_yxst_trd_order_di_o',
                    status: 'active',
                    publish_status: 'published',
                    collection_config: {
                      mode: 'date_field',
                      date_field: 'create_date',
                    },
                  },
                ],
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('交易订单明细表')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '采集详情' }));
    expect(await screen.findByRole('heading', { name: '采集详情' })).toBeInTheDocument();
    expect(screen.getByText('采集时间字段：create_date')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '按日期采集' }));
    expect(await screen.findByRole('heading', { name: '按日期采集' })).toBeInTheDocument();
    expect(screen.getByText('交易订单明细表')).toBeInTheDocument();
    expect(screen.getByText('采集时间字段：create_date')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('采集日期'), { target: { value: '2026-04-01' } });
    fireEvent.click(screen.getByRole('button', { name: '采集' }));

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.url.includes('/data-sources/source-db-1/datasets/dataset-order/collection') &&
            request.init?.method === 'POST',
        ),
      ).toBe(true);
    });

    const collectionRequest = requests.find(
      (request) =>
        request.url.includes('/data-sources/source-db-1/datasets/dataset-order/collection') &&
        request.init?.method === 'POST',
    );
    const payload = JSON.parse(String(collectionRequest?.init?.body || '{}'));
    expect(payload.resource_key).toBe('public.ods_yxst_trd_order_di_o');
    expect(payload.params).toEqual({
      resource_key: 'public.ods_yxst_trd_order_di_o',
      biz_date: '2026-04-01',
      query: { resource_key: 'public.ods_yxst_trd_order_di_o' },
    });
    expect(payload.idempotency_key).toBe('manual-date-collection:source-db-1:dataset-order:2026-04-01');

    await waitFor(() => {
      expect(detailCalls).toBeGreaterThan(1);
    });
    expect(screen.queryByRole('heading', { name: '按日期采集' })).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/data-connections-platform-auth.spec.tsx -t "数据库数据集采集详情支持按单日日期采集"
```

Expected: FAIL because `按日期采集` and the date modal do not exist yet.

- [ ] **Step 3: Add state and helper types**

In `finance-web/src/components/DataConnectionsPanel.tsx`, add this interface after `DatasetCollectionDetailDialogState`.

```tsx
interface DateCollectionDialogState {
  sourceId: string;
  sourceName: string;
  datasetId: string;
  datasetName: string;
  resourceKey: string;
  dateField: string;
  selectedDate: string;
  submitting: boolean;
  error: string;
}
```

Add this helper near the other collection helper functions, before the component or near `formatCollectionFilterDisplay`.

```tsx
function readCollectionDateFieldFromDetail(
  detail: Record<string, unknown> | null | undefined,
  fallbackDataset?: DataSourceDatasetSummary,
): string {
  const detailDataset = asRecord(detail?.dataset);
  const detailCollectionConfig =
    asRecord(detailDataset?.collection_config) ??
    asRecord(asRecord(detailDataset?.meta)?.collection_config) ??
    asRecord(asRecord(detailDataset?.catalog_profile)?.collection_config);
  const fallbackCollectionConfig =
    asRecord(fallbackDataset?.collection_config) ??
    asRecord(asRecord(fallbackDataset?.meta)?.collection_config) ??
    asRecord(asRecord(fallbackDataset?.meta)?.catalog_profile)?.collection_config as Record<string, unknown> | undefined;
  return (
    asString(detailCollectionConfig?.date_field) ||
    asString(detailCollectionConfig?.collection_date_field) ||
    asString(detailCollectionConfig?.physical_date_field) ||
    asString(fallbackCollectionConfig?.date_field) ||
    asString(fallbackCollectionConfig?.collection_date_field) ||
    asString(fallbackCollectionConfig?.physical_date_field) ||
    ''
  );
}
```

If TypeScript rejects the inline cast, use this safer version:

```tsx
function readCollectionDateFieldFromDetail(
  detail: Record<string, unknown> | null | undefined,
  fallbackDataset?: DataSourceDatasetSummary,
): string {
  const detailDataset = asRecord(detail?.dataset);
  const detailMeta = asRecord(detailDataset?.meta);
  const detailCatalogProfile = asRecord(detailMeta?.catalog_profile) ?? asRecord(detailDataset?.catalog_profile);
  const detailCollectionConfig =
    asRecord(detailDataset?.collection_config) ??
    asRecord(detailMeta?.collection_config) ??
    asRecord(detailCatalogProfile?.collection_config);

  const fallbackMeta = asRecord(fallbackDataset?.meta);
  const fallbackCatalogProfile = asRecord(fallbackMeta?.catalog_profile) ?? asRecord(fallbackDataset?.catalog_profile);
  const fallbackCollectionConfig =
    asRecord(fallbackDataset?.collection_config) ??
    asRecord(fallbackMeta?.collection_config) ??
    asRecord(fallbackCatalogProfile?.collection_config);

  return (
    asString(detailCollectionConfig?.date_field) ||
    asString(detailCollectionConfig?.collection_date_field) ||
    asString(detailCollectionConfig?.physical_date_field) ||
    asString(fallbackCollectionConfig?.date_field) ||
    asString(fallbackCollectionConfig?.collection_date_field) ||
    asString(fallbackCollectionConfig?.physical_date_field) ||
    ''
  );
}
```

Add this state beside `collectionDetailDialog`.

```tsx
const [dateCollectionDialog, setDateCollectionDialog] = useState<DateCollectionDialogState | null>(null);
```

- [ ] **Step 4: Run typecheck to catch helper mistakes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected: either PASS or fail only on the not-yet-used state/helper if lint rules differ. Fix any TypeScript syntax issue before continuing.

---

### Task 2: Implement Date Collection Modal and Submission

**Files:**
- Modify: `finance-web/src/components/DataConnectionsPanel.tsx`
- Test: `finance-web/tests/components/data-connections-platform-auth.spec.tsx`

- [ ] **Step 1: Extract reusable collection trigger**

Replace `retryCollectionDetailDataset` with a shared `triggerCollectionDetailDataset` callback plus a thin immediate wrapper.

The implementation should preserve existing immediate behavior when `bizDate` is omitted.

```tsx
  const triggerCollectionDetailDataset = useCallback(
    async (options?: { bizDate?: string; onSuccess?: () => void }) => {
      if (!collectionDetailDialog || !authToken || draftSourceIdSet.has(collectionDetailDialog.sourceId)) return;
      const source = remoteSources.find((item) => item.id === collectionDetailDialog.sourceId);
      const dataset = source?.datasets?.find((item) => item.id === collectionDetailDialog.datasetId) ?? {
        id: collectionDetailDialog.datasetId,
        dataset_code: collectionDetailDialog.resourceKey,
        dataset_name: collectionDetailDialog.datasetName,
        resource_key: collectionDetailDialog.resourceKey,
      } as DataSourceDatasetSummary;
      const bizDate = (options?.bizDate || '').trim();
      setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: true, actionError: '' } : prev));
      try {
        const body: Record<string, unknown> = {
          resource_key: collectionDetailDialog.resourceKey,
          params: {
            resource_key: collectionDetailDialog.resourceKey,
            ...(bizDate ? { biz_date: bizDate } : {}),
            query: { resource_key: collectionDetailDialog.resourceKey },
          },
        };
        if (bizDate) {
          body.idempotency_key = `manual-date-collection:${collectionDetailDialog.sourceId}:${collectionDetailDialog.datasetId}:${bizDate}`;
        }
        const response = await fetch(
          `/api/data-sources/${collectionDetailDialog.sourceId}/datasets/${encodeURIComponent(collectionDetailDialog.datasetId)}/collection`,
          {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify(body),
          },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || (bizDate ? '按日期采集失败' : '立即采集失败')));
        }
        options?.onSuccess?.();
        if (source) {
          await openDatasetCollectionDetail(source, dataset);
        } else {
          setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: false } : prev));
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : bizDate ? '按日期采集失败' : '立即采集失败';
        if (source) {
          await openDatasetCollectionDetail(source, dataset);
          setCollectionDetailDialog((prev) => (prev ? { ...prev, actionError: message } : prev));
        } else {
          setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: false, actionError: message } : prev));
        }
        throw error;
      }
    },
    [authHeaders, authToken, collectionDetailDialog, draftSourceIdSet, openDatasetCollectionDetail, remoteSources],
  );

  const retryCollectionDetailDataset = useCallback(async () => {
    await triggerCollectionDetailDataset();
  }, [triggerCollectionDetailDataset]);
```

- [ ] **Step 2: Add modal open and submit callbacks**

Add these callbacks after `retryCollectionDetailDataset`.

```tsx
  const openDateCollectionDialog = useCallback(() => {
    if (!collectionDetailDialog) return;
    const source = remoteSources.find((item) => item.id === collectionDetailDialog.sourceId);
    const dataset = source?.datasets?.find((item) => item.id === collectionDetailDialog.datasetId);
    const dateField = readCollectionDateFieldFromDetail(collectionDetailDialog.detail, dataset);
    if (!dateField) {
      setCollectionDetailDialog((prev) =>
        prev
          ? {
              ...prev,
              actionError: '该数据集未配置采集时间字段，无法按日期采集。',
            }
          : prev,
      );
      return;
    }
    setDateCollectionDialog({
      sourceId: collectionDetailDialog.sourceId,
      sourceName: collectionDetailDialog.sourceName,
      datasetId: collectionDetailDialog.datasetId,
      datasetName: collectionDetailDialog.datasetName,
      resourceKey: collectionDetailDialog.resourceKey,
      dateField,
      selectedDate: '',
      submitting: false,
      error: '',
    });
  }, [collectionDetailDialog, remoteSources]);

  const submitDateCollectionDialog = useCallback(async () => {
    if (!dateCollectionDialog || dateCollectionDialog.submitting) return;
    const selectedDate = dateCollectionDialog.selectedDate.trim();
    if (!selectedDate) {
      setDateCollectionDialog((prev) => (prev ? { ...prev, error: '请选择采集日期。' } : prev));
      return;
    }
    setDateCollectionDialog((prev) => (prev ? { ...prev, submitting: true, error: '' } : prev));
    try {
      await triggerCollectionDetailDataset({
        bizDate: selectedDate,
        onSuccess: () => setDateCollectionDialog(null),
      });
    } catch (error) {
      setDateCollectionDialog((prev) =>
        prev
          ? {
              ...prev,
              submitting: false,
              error: error instanceof Error ? error.message : '按日期采集失败',
            }
          : prev,
      );
    }
  }, [dateCollectionDialog, triggerCollectionDetailDataset]);
```

- [ ] **Step 3: Render the `按日期采集` button**

Inside the database collection detail drawer, in the button group that currently renders `刷新` and `立即采集`, compute the date field before the `return` for that panel block.

Within the existing IIFE around collection detail rendering, after `const latestJob = jobs[0] ?? {};`, add:

```tsx
const sourceForCollectionDetail = remoteSources.find((item) => item.id === collectionDetailDialog.sourceId);
const datasetForCollectionDetail = sourceForCollectionDetail?.datasets?.find(
  (item) => item.id === collectionDetailDialog.datasetId,
);
const collectionDateField = readCollectionDateFieldFromDetail(
  collectionDetailDialog.detail,
  datasetForCollectionDetail,
);
```

Then add this button between `刷新` and `立即采集`.

```tsx
                              <button
                                type="button"
                                onClick={openDateCollectionDialog}
                                disabled={!collectionDateField}
                                title={!collectionDateField ? '该数据集未配置采集时间字段，无法按日期采集' : undefined}
                                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                <CalendarDays className="h-4 w-4" />
                                按日期采集
                              </button>
```

If `CalendarDays` is not already imported from `lucide-react`, add it to the existing icon import list.

- [ ] **Step 4: Render the modal**

Add this JSX near other top-level modals in `DataConnectionsPanel.tsx`, after the collection detail drawer is acceptable.

```tsx
      {dateCollectionDialog && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/35 px-4" onClick={() => setDateCollectionDialog(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="date-collection-title"
            className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 id="date-collection-title" className="text-base font-semibold text-text-primary">
                  按日期采集
                </h4>
                <p className="mt-1 text-sm text-text-primary">{dateCollectionDialog.datasetName}</p>
                <p className="mt-1 text-xs text-text-secondary">
                  {dateCollectionDialog.sourceName} · {dateCollectionDialog.resourceKey}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDateCollectionDialog(null)}
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
              采集时间字段：{dateCollectionDialog.dateField}
            </div>
            {dateCollectionDialog.error && (
              <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {dateCollectionDialog.error}
              </div>
            )}
            <label className="mt-4 block text-sm font-medium text-text-primary" htmlFor="date-collection-date">
              采集日期
            </label>
            <input
              id="date-collection-date"
              type="date"
              value={dateCollectionDialog.selectedDate}
              onChange={(event) =>
                setDateCollectionDialog((prev) =>
                  prev ? { ...prev, selectedDate: event.target.value, error: '' } : prev,
                )
              }
              className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-blue-400"
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDateCollectionDialog(null)}
                disabled={dateCollectionDialog.submitting}
                className="inline-flex items-center rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void submitDateCollectionDialog()}
                disabled={dateCollectionDialog.submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {dateCollectionDialog.submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarDays className="h-4 w-4" />}
                采集
              </button>
            </div>
          </div>
        </div>
      )}
```

- [ ] **Step 5: Run the focused test**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/data-connections-platform-auth.spec.tsx -t "数据库数据集采集详情支持按单日日期采集"
```

Expected: PASS.

---

### Task 3: Disabled State and Regression Coverage

**Files:**
- Modify: `finance-web/tests/components/data-connections-platform-auth.spec.tsx`
- Modify: `finance-web/src/components/DataConnectionsPanel.tsx` only if the test reveals a bug

- [ ] **Step 1: Add a failing test for missing date field**

Append this test near the previous date collection test.

```tsx
  it('数据库数据集未配置采集时间字段时禁用按日期采集', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/data-sources/source-db-1/datasets/dataset-no-date/collection-detail')) {
          return mockJsonResponse({
            dataset: {
              id: 'dataset-no-date',
              data_source_id: 'source-db-1',
              dataset_code: 'public_no_date_table',
              dataset_name: 'public.no_date_table',
              business_name: '无日期字段表',
              resource_key: 'public.no_date_table',
              collection_config: { mode: 'manual' },
            },
            collection_stats: { total_count: 0 },
            jobs: [],
            rows: [],
          });
        }
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'source-db-1',
                source_kind: 'database',
                provider_code: 'hologres',
                name: 'Hologres 订单库',
                status: 'active',
                execution_mode: 'deterministic',
                datasets: [
                  {
                    id: 'dataset-no-date',
                    data_source_id: 'source-db-1',
                    dataset_code: 'public_no_date_table',
                    dataset_name: 'public.no_date_table',
                    business_name: '无日期字段表',
                    resource_key: 'public.no_date_table',
                    status: 'active',
                    publish_status: 'published',
                    collection_config: { mode: 'manual' },
                  },
                ],
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('无日期字段表')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '采集详情' }));
    expect(await screen.findByRole('heading', { name: '采集详情' })).toBeInTheDocument();
    const dateCollectionButton = screen.getByRole('button', { name: '按日期采集' });
    expect(dateCollectionButton).toBeDisabled();
    expect(dateCollectionButton).toHaveAttribute('title', '该数据集未配置采集时间字段，无法按日期采集');
  });
```

- [ ] **Step 2: Run both focused tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/data-connections-platform-auth.spec.tsx -t "数据库数据集"
```

Expected: PASS.

- [ ] **Step 3: Run the full component test file**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/data-connections-platform-auth.spec.tsx
```

Expected: PASS.

---

### Task 4: Build Verification and Service Restart

**Files:**
- No code files expected beyond previous tasks.

- [ ] **Step 1: Run TypeScript build**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run build
```

Expected: PASS.

- [ ] **Step 2: Restart services**

Run from repo root:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web, finance-mcp, and data-agent services start successfully.

- [ ] **Step 3: Commit the implementation**

Only add files changed for this feature. Do not add unrelated dirty files already present in the worktree.

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/components/DataConnectionsPanel.tsx finance-web/tests/components/data-connections-platform-auth.spec.tsx
git commit -m "feat: add manual date dataset collection"
```

Expected: one implementation commit.

---

## Self-Review

Spec coverage:

- Adds `按日期采集` beside `立即采集`: Task 2 Step 3.
- Single-day modal: Task 2 Step 4.
- Uses configured date field and displays it: Task 1 Step 3 and Task 2 Step 4.
- Sends `params.biz_date`: Task 2 Step 1 and Task 1 test assertion.
- Reuses existing backend endpoint: Task 2 Step 1.
- Refreshes collection detail after success: Task 2 Step 1.
- Disabled when no date field exists: Task 3.
- No range collection: no task implements range selection.
- No backend storage or collection architecture change: File Structure and Task 4 constrain touched files.

Placeholder scan:

- No deferred implementation steps remain.
- Code blocks define exact test and implementation snippets.

Type consistency:

- `DateCollectionDialogState` is introduced before use.
- `triggerCollectionDetailDataset`, `openDateCollectionDialog`, and `submitDateCollectionDialog` are named consistently.
- Request body uses existing `resource_key`, `params`, and `idempotency_key` names.
