# Recon Exception Page Run Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the public reconciliation exception page so source row counts show the rows that actually entered reconciliation, with the execution status moved beside the task title.

**Architecture:** Keep the change in the existing React page component. Build run metrics from `recon_result_summary_json` instead of collection snapshot counts, and update the component test to lock the new UI and count formula.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, Vite.

---

### Task 1: Public Exception Page Metrics

**Files:**
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
- Modify: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`

- [ ] **Step 1: Update the component test expectation first**

Edit `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx` so the main test describes recon-input row counts instead of snapshot read counts:

```typescript
it('shows matched success and per-source recon input counts from run summary', async () => {
```

Use this `recon_result_summary_json` in the mocked run:

```typescript
recon_result_summary_json: {
  matched_exact: 170,
  source_only: 60,
  target_only: 12,
  matched_with_diff: 5,
},
```

Keep `source_snapshot_json.collections` only for dataset names, and make the snapshot counts intentionally misleading:

```typescript
collection_records: {
  record_count: 1,
},
```

and:

```typescript
collection_records: {
  record_count: 340,
},
```

Assert the header shows:

```typescript
expect(headerView.getByText('成功')).toBeInTheDocument();
expect(headerView.getByText('175')).toBeInTheDocument();
expect(headerView.getByText('差异总数')).toBeInTheDocument();
expect(headerView.getByText('60')).toBeInTheDocument();
expect(headerView.getByText('交易订单明细表')).toBeInTheDocument();
expect(headerView.getByText('支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '数据 235 条')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '数据 187 条')).toBeInTheDocument();
expect(headerView.queryByText('本次读取数据')).not.toBeInTheDocument();
expect(headerView.queryByText('新增 0 / 更新 340')).not.toBeInTheDocument();
expect(headerView.queryByText((_, element) => element?.textContent === '本次读取 1 条')).not.toBeInTheDocument();
```

The formula represented by those numbers is:

```text
left = 170 + 5 + 60 = 235
right = 170 + 5 + 12 = 187
```

- [ ] **Step 2: Run the component test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected: FAIL because the current component still displays snapshot read counts and the old standalone read-data section.

- [ ] **Step 3: Update the metrics view model**

In `finance-web/src/components/PublicReconRunExceptionsPage.tsx`, remove collection inserted/updated/upserted fields from `SourceReadCountMetric`:

```typescript
interface SourceReadCountMetric {
  id: string;
  name: string;
  count: number | null;
}
```

Update `buildRunMetrics` so it reads `matched_exact`, `matched_with_diff`, `source_only`, and `target_only` from `recon_result_summary_json`, then assigns:

```typescript
const leftCount = hasSummaryNumbers
  ? matchedExact + matchedWithDiff + sourceOnly
  : null;
const rightCount = hasSummaryNumbers
  ? matchedExact + matchedWithDiff + targetOnly
  : null;
```

Build the source count list from existing left/right collection labels, but use `leftCount` and `rightCount` instead of `collection_records.record_count`.

- [ ] **Step 4: Update the header layout**

In `PublicReconRunExceptionsPage.tsx`, move the execution status badge into the task/title row:

```tsx
<div className="flex flex-wrap items-center gap-3">
  <h1 className="text-2xl font-semibold text-text-primary">
    {bundle.task?.name || bundle.run?.planName || '对账任务'}
  </h1>
  {bundle.run ? (
    <span className={cn('inline-flex ...', statusInfo.className)}>
      {statusInfo.label}
    </span>
  ) : null}
</div>
```

Remove the old execution status metric card from the metrics grid.

Render source row counts as a two-column row above the metric cards:

```tsx
{runMetrics.sourceReadCounts.length > 0 ? (
  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
    {runMetrics.sourceReadCounts.map((source) => (
      <div key={source.id} className="rounded-lg border border-border bg-surface-secondary p-4">
        <div className="text-sm font-medium text-text-primary">{source.name}</div>
        <div className="mt-2 text-lg font-semibold text-text-primary">
          数据 {formatCount(source.count)} 条
        </div>
      </div>
    ))}
  </div>
) : null}
```

Keep the existing matched success and difference total cards below this source row.

- [ ] **Step 5: Run the focused component test**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run TypeScript check**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 7: Restart services**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, and finance-mcp start without new errors.

- [ ] **Step 8: Commit the implementation**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add -f finance-web/src/components/PublicReconRunExceptionsPage.tsx finance-web/tests/components/public-recon-run-exceptions-page.test.tsx docs/superpowers/plans/2026-05-13-recon-exception-page-run-metrics.md
git commit -m "fix: show recon input counts on exception page"
```

Expected: commit succeeds with only the planned files staged.
