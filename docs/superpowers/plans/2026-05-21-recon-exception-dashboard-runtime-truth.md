# Recon Exception Dashboard Runtime Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the exception dashboard show the real run process: reconciliation data date, collection/preparation/reconciliation row counts and durations, anomaly count at the difference list, and summary notification status in run details.

**Architecture:** Persist a unified `artifacts_json.runtime_summary` object from the queued automatic run path, then render both the public exception page and the internal exception modal from one frontend view-model helper. Existing exception lists and remediation flows stay unchanged; historical runs with missing metrics display `--` instead of falling back to misleading `execution_runs.started_at/finished_at`.

**Tech Stack:** Python 3.11, FastAPI/MCP tools, LangGraph data-agent nodes, PostgreSQL JSONB fields, React 19, TypeScript, Vitest, Testing Library.

---

## File Structure

- Create `finance-web/src/components/recon/runRuntimeSummary.ts` — shared frontend parsing/formatting for runtime summary, business names, counts, durations, queue fields, and notification state.
- Modify `finance-web/src/components/PublicReconRunExceptionsPage.tsx` — remove old main metrics, render runtime overview, move anomaly count to the difference list header, and add collapsed run details.
- Modify `finance-web/src/components/ReconWorkspace.tsx` — render the same runtime overview and run details in the internal exception modal.
- Modify `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx` — lock public page behavior.
- Modify `finance-web/tests/components/recon-task-list-layout.spec.tsx` — lock internal modal behavior.
- Modify `finance-mcp/proc/mcp_server/steps_runtime.py` — expose per-target proc durations.
- Modify `finance-mcp/proc/mcp_server/proc_rule.py` — return proc runtime metrics from `proc_execute`.
- Modify `finance-mcp/auth/db.py` — return updated queue rows from `complete_recon_run`.
- Modify `finance-mcp/tools/recon_auto_runs.py` — return completed queue job details from `recon_queue_complete`.
- Modify `finance-agents/data-agent/recon_worker.py` — pass queue identity/timestamps into run context and patch queue finish facts after completion.
- Modify `finance-agents/data-agent/graphs/recon/pipeline_service.py` — record reconciliation execution duration.
- Modify `finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py` — carry proc and recon metrics through graph context.
- Modify `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py` — build/persist `runtime_summary` and write back summary notification results.
- Modify `finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py` — cover proc preparation runtime metrics.
- Modify `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py` — cover runtime summary shape and notification merge.

---

### Task 1: Shared Frontend Runtime Summary View Model

**Files:**
- Create: `finance-web/src/components/recon/runRuntimeSummary.ts`
- Test: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`

- [ ] **Step 1: Add failing public page expectations**

In `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`, update the primary public page fixture so `run.artifacts_json` contains:

```typescript
artifacts_json: {
  runtime_summary: {
    biz_date: '2026-05-12',
    queue: {
      job_id: 'queue-001',
      started_at: '2026-05-21T04:00:01+08:00',
      finished_at: '2026-05-21T04:01:15+08:00',
      duration_seconds: 73.854,
    },
    collections: [
      { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 38.42 },
      { side: 'right', business_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺', row_count: 136, duration_seconds: 31.06 },
    ],
    preparation: [
      { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 4.18 },
      { side: 'right', business_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺', row_count: 136, duration_seconds: 3.77 },
    ],
    reconciliation: { duration_seconds: 2.24 },
    summary_notification: {
      status: 'sent',
      recipient_name: '张小毅',
      recipient_identifier: '072007534524160438',
      message_id: 'msg-001',
      error: '',
    },
  },
},
```

Replace the old assertions for `匹配成功`, source read cards, `开始时间`, and `结束时间` with:

```typescript
expect(headerView.getByText('对账数据日期')).toBeInTheDocument();
expect(headerView.getByText('2026-05-12')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '交易订单明细表采集205 行耗时 38.42 秒')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺采集136 行耗时 31.06 秒')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '整理后交易订单明细表205 行耗时 4.18 秒')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '整理后支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺136 行耗时 3.77 秒')).toBeInTheDocument();
expect(headerView.getByText((_, element) => element?.textContent === '对账耗时2.24 秒')).toBeInTheDocument();
expect(headerView.queryByText('开始时间')).not.toBeInTheDocument();
expect(headerView.queryByText('结束时间')).not.toBeInTheDocument();
expect(screen.getByText('差异列表')).toBeInTheDocument();
expect(screen.getByText((_, element) => element?.textContent === '待处理差异 60 条')).toBeInTheDocument();
```

- [ ] **Step 2: Run the public page test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected: FAIL because runtime stage text and list-level anomaly count are not rendered yet.

- [ ] **Step 3: Create the shared runtime helper**

Create `finance-web/src/components/recon/runRuntimeSummary.ts`:

```typescript
export type ReconRuntimeSide = 'left' | 'right';

export interface RuntimeStageMetric {
  side?: ReconRuntimeSide;
  businessName: string;
  rowCount: number | null;
  durationSeconds: number | null;
}

export interface RuntimeNotificationView {
  status: string;
  label: string;
  recipientName: string;
  recipientIdentifier: string;
  messageId: string;
  error: string;
}

export interface RuntimeSummaryViewModel {
  bizDate: string;
  queueJobId: string;
  queueStartedAt: string;
  queueFinishedAt: string;
  queueDurationSeconds: number | null;
  collectionMetrics: RuntimeStageMetric[];
  preparationMetrics: RuntimeStageMetric[];
  reconciliationDurationSeconds: number | null;
  notification: RuntimeNotificationView;
}

export interface RunLikeForRuntimeSummary {
  raw?: Record<string, unknown>;
  dataDate?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function toText(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return fallback;
}

function toOptionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toOptionalInt(value: unknown): number | null {
  const parsed = toOptionalNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
}

export function formatCount(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  return value.toLocaleString('zh-CN');
}

export function formatDuration(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  if (value < 1) return `${value.toFixed(2)} 秒`;
  if (value < 60) return `${value.toFixed(2).replace(/\.?0+$/, '')} 秒`;
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return `${minutes} 分 ${seconds.toFixed(0)} 秒`;
}

export function looksLikeTechnicalName(value: string): boolean {
  const text = value.trim();
  if (!text || /[\u4e00-\u9fff]/.test(text)) return false;
  const normalized = text.toLowerCase();
  return (
    /^[a-z_][\w$]*\.[a-z_][\w$]*$/.test(normalized)
    || /^(ods|dwd|dws|dim|fact|stg|tmp|raw)_/.test(normalized)
    || /^(public|ods|dwd|dws|dim|fact|stg|tmp|raw)[._]/.test(normalized)
    || /^[a-z0-9_]+:[a-z0-9_:/.-]+$/.test(normalized)
  );
}

export function runtimeBusinessName(raw: unknown, fallback: string): string {
  const item = asRecord(raw);
  for (const key of ['business_name', 'dataset_name', 'display_name', 'name', 'dataset_code']) {
    const text = toText(item[key]).trim();
    if (text && !looksLikeTechnicalName(text)) return text;
  }
  return fallback;
}

function sideFallback(side: string): string {
  return side === 'right' ? '右侧数据源' : '左侧数据源';
}

function normalizeSide(value: unknown): ReconRuntimeSide | undefined {
  const text = toText(value).trim().toLowerCase();
  if (text === 'left' || text.startsWith('left_')) return 'left';
  if (text === 'right' || text.startsWith('right_')) return 'right';
  return undefined;
}

function normalizeStageMetric(value: unknown, index: number): RuntimeStageMetric {
  const item = asRecord(value);
  const side = normalizeSide(item.side);
  return {
    side,
    businessName: runtimeBusinessName(item, sideFallback(side || (index === 1 ? 'right' : 'left'))),
    rowCount: toOptionalInt(item.row_count ?? item.rowCount),
    durationSeconds: toOptionalNumber(item.duration_seconds ?? item.durationSeconds),
  };
}

function derivedPreparation(rawRun: Record<string, unknown>, collections: RuntimeStageMetric[]): RuntimeStageMetric[] {
  const summary = asRecord(rawRun.recon_result_summary_json);
  const matchedExact = toOptionalInt(summary.matched_exact);
  const matchedWithDiff = toOptionalInt(summary.matched_with_diff);
  const sourceOnly = toOptionalInt(summary.source_only);
  const targetOnly = toOptionalInt(summary.target_only);
  if (matchedExact === null || matchedWithDiff === null || sourceOnly === null || targetOnly === null) {
    return [];
  }
  return [
    {
      side: 'left',
      businessName: collections.find((item) => item.side === 'left')?.businessName || '左侧数据源',
      rowCount: matchedExact + matchedWithDiff + sourceOnly,
      durationSeconds: null,
    },
    {
      side: 'right',
      businessName: collections.find((item) => item.side === 'right')?.businessName || '右侧数据源',
      rowCount: matchedExact + matchedWithDiff + targetOnly,
      durationSeconds: null,
    },
  ];
}

function notificationLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'sent') return '已发送';
  if (normalized === 'failed') return '发送失败';
  if (normalized === 'skipped') return '已跳过';
  return status || '--';
}

function normalizeNotification(value: unknown): RuntimeNotificationView {
  const item = asRecord(value);
  const status = toText(item.status).trim();
  return {
    status,
    label: notificationLabel(status),
    recipientName: toText(item.recipient_name ?? item.recipientName).trim(),
    recipientIdentifier: toText(item.recipient_identifier ?? item.recipientIdentifier).trim(),
    messageId: toText(item.message_id ?? item.messageId).trim(),
    error: toText(item.error).trim(),
  };
}

export function buildRuntimeSummaryView(run: RunLikeForRuntimeSummary | null | undefined): RuntimeSummaryViewModel {
  const rawRun = asRecord(run?.raw);
  const runContext = asRecord(rawRun.run_context_json);
  const artifacts = asRecord(rawRun.artifacts_json);
  const runtimeSummary = asRecord(artifacts.runtime_summary);
  const queue = asRecord(runtimeSummary.queue);
  const collections = asList(runtimeSummary.collections).map(normalizeStageMetric);
  const preparation = asList(runtimeSummary.preparation).map(normalizeStageMetric);
  const reconciliation = asRecord(runtimeSummary.reconciliation);
  return {
    bizDate: (
      toText(runtimeSummary.biz_date).trim()
      || toText(runContext.biz_date).trim()
      || toText(rawRun.biz_date).trim()
      || toText(rawRun.business_date).trim()
      || toText(rawRun.data_date).trim()
      || run?.dataDate
      || ''
    ),
    queueJobId: toText(queue.job_id ?? queue.jobId).trim(),
    queueStartedAt: toText(queue.started_at ?? queue.startedAt).trim(),
    queueFinishedAt: toText(queue.finished_at ?? queue.finishedAt).trim(),
    queueDurationSeconds: toOptionalNumber(queue.duration_seconds ?? queue.durationSeconds),
    collectionMetrics: collections,
    preparationMetrics: preparation.length > 0 ? preparation : derivedPreparation(rawRun, collections),
    reconciliationDurationSeconds: toOptionalNumber(reconciliation.duration_seconds ?? reconciliation.durationSeconds),
    notification: normalizeNotification(runtimeSummary.summary_notification),
  };
}
```

- [ ] **Step 4: Run the TypeScript check**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected: PASS or existing unrelated errors only. No error should point at `runRuntimeSummary.ts`.

- [ ] **Step 5: Leave the failing test uncommitted**

Do not commit Task 1 by itself. The public page test intentionally fails until Task 2 adds the UI.

---

### Task 2: Public Exception Page Runtime Summary UI

**Files:**
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
- Test: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`
- Include uncommitted create: `finance-web/src/components/recon/runRuntimeSummary.ts`

- [ ] **Step 1: Import the shared helper**

In `finance-web/src/components/PublicReconRunExceptionsPage.tsx`, add:

```typescript
import {
  buildRuntimeSummaryView,
  formatCount,
  formatDuration,
  looksLikeTechnicalName,
} from './recon/runRuntimeSummary';
```

Remove the local `formatCount` and `looksLikeTechnicalName` functions. Keep `containsChinese`, `firstFriendlyText`, and `sourceDisplayName` only if they still have callers after `buildRunMetrics` is removed.

- [ ] **Step 2: Replace old run metrics state**

Replace:

```typescript
const runMetrics = useMemo(() => buildRunMetrics(bundle), [bundle]);
```

with:

```typescript
const runtimeSummary = useMemo(() => buildRuntimeSummaryView(bundle?.run), [bundle?.run]);
const pendingDifferenceTotal = bundle?.total ?? (bundle?.exceptions || []).length;
```

Remove `RunMetricsViewModel`, `SourceReadCountMetric`, and `buildRunMetrics` from this file after removing their JSX callers.

- [ ] **Step 3: Add the metric renderer**

Inside `PublicReconRunExceptionsPage`, before the `return`, add:

```tsx
const renderRuntimeMetric = (label: string, value: string) => (
  <div className="min-w-[180px] rounded-xl border border-border bg-surface-secondary px-3 py-2">
    <p className="text-[11px] font-medium text-text-secondary">{label}</p>
    <p className="mt-1 text-sm font-semibold text-text-primary">{value}</p>
  </div>
);

const collectionMetricNodes = runtimeSummary.collectionMetrics.map((item, index) => (
  <div key={`collection-${item.side || item.businessName}-${index}`}>
    {renderRuntimeMetric(
      `${item.businessName}采集`,
      `${formatCount(item.rowCount)} 行耗时 ${formatDuration(item.durationSeconds)}`,
    )}
  </div>
));

const preparationMetricNodes = runtimeSummary.preparationMetrics.map((item, index) => (
  <div key={`preparation-${item.side || item.businessName}-${index}`}>
    {renderRuntimeMetric(
      `整理后${item.businessName}`,
      `${formatCount(item.rowCount)} 行耗时 ${formatDuration(item.durationSeconds)}`,
    )}
  </div>
));
```

- [ ] **Step 4: Replace the old header metrics**

Remove the `runMetrics.sourceReadCounts` block and the grid containing `匹配成功 / 待处理差异 / 开始时间 / 结束时间`. Insert:

```tsx
<div className="mt-5 flex flex-wrap gap-3">
  {renderRuntimeMetric('对账数据日期', runtimeSummary.bizDate || '--')}
  {collectionMetricNodes}
  {preparationMetricNodes}
  {renderRuntimeMetric('对账耗时', formatDuration(runtimeSummary.reconciliationDurationSeconds))}
</div>
```

- [ ] **Step 5: Add collapsed run details**

Add state near other component state:

```typescript
const [showRunDetails, setShowRunDetails] = useState(false);
```

Below the metric strip, add:

```tsx
<div className="mt-4 rounded-2xl border border-border bg-surface-secondary">
  <button
    type="button"
    onClick={() => setShowRunDetails((value) => !value)}
    className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-text-primary"
  >
    <span>运行详情</span>
    <ChevronDown className={cn('h-4 w-4 transition', showRunDetails && 'rotate-180')} />
  </button>
  {showRunDetails ? (
    <div className="grid gap-3 border-t border-border-subtle px-4 py-4 sm:grid-cols-2 lg:grid-cols-3">
      <div>
        <p className="text-xs text-text-secondary">所属方案</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{bundle?.scheme?.name || bundle?.run?.schemeName || '--'}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">运行状态</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{statusMeta.label}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">队列开始时间</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(runtimeSummary.queueStartedAt)}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">队列结束时间</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(runtimeSummary.queueFinishedAt)}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">队列总耗时</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{formatDuration(runtimeSummary.queueDurationSeconds)}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">记录写入开始时间</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(bundle?.run?.startedAt || '')}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">记录写入结束时间</p>
        <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(bundle?.run?.finishedAt || '')}</p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">汇总接收人</p>
        <p className="mt-1 text-sm font-medium text-text-primary">
          {runtimeSummary.notification.recipientName || runtimeSummary.notification.recipientIdentifier || '--'}
        </p>
      </div>
      <div>
        <p className="text-xs text-text-secondary">汇总消息推送状态</p>
        <p className="mt-1 text-sm font-medium text-text-primary">
          {runtimeSummary.notification.label}
          {runtimeSummary.notification.messageId ? ` · ${runtimeSummary.notification.messageId}` : ''}
          {runtimeSummary.notification.error ? ` · ${runtimeSummary.notification.error}` : ''}
        </p>
      </div>
    </div>
  ) : null}
</div>
```

- [ ] **Step 6: Move anomaly count to the difference list header**

Immediately before the public exception list/table content, add:

```tsx
<div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
  <h2 className="text-base font-semibold text-text-primary">差异列表</h2>
  <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
    待处理差异 {formatCount(pendingDifferenceTotal)} 条
  </span>
</div>
```

- [ ] **Step 7: Run the public page test**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit public page UI**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add -f finance-web/src/components/recon/runRuntimeSummary.ts finance-web/src/components/PublicReconRunExceptionsPage.tsx finance-web/tests/components/public-recon-run-exceptions-page.test.tsx
git commit -m "feat: show runtime summary on public exception page"
```

---

### Task 3: Internal Exception Modal Runtime Summary UI

**Files:**
- Modify: `finance-web/src/components/ReconWorkspace.tsx`
- Modify: `finance-web/tests/components/recon-task-list-layout.spec.tsx`

- [ ] **Step 1: Update modal test first**

In `finance-web/tests/components/recon-task-list-layout.spec.tsx`, add this `artifacts_json` to the mocked run from `/api/recon/runs`:

```typescript
artifacts_json: {
  runtime_summary: {
    biz_date: '2026-05-11',
    queue: {
      job_id: 'queue-001',
      started_at: '2026-05-21T04:00:01+08:00',
      finished_at: '2026-05-21T04:01:15+08:00',
      duration_seconds: 73.854,
    },
    collections: [
      { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 38.42 },
      { side: 'right', business_name: '支付宝资金账单', row_count: 136, duration_seconds: 31.06 },
    ],
    preparation: [
      { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 4.18 },
      { side: 'right', business_name: '支付宝资金账单', row_count: 136, duration_seconds: 3.77 },
    ],
    reconciliation: { duration_seconds: 2.24 },
    summary_notification: {
      status: 'sent',
      recipient_name: '张小毅',
      recipient_identifier: '072007534524160438',
      message_id: 'msg-001',
      error: '',
    },
  },
},
```

Replace old modal assertions with:

```typescript
expect(within(dialog).getByText('对账数据日期')).toBeInTheDocument();
expect(within(dialog).getByText('2026-05-11')).toBeInTheDocument();
expect(within(dialog).getByText((_, element) => element?.textContent === '交易订单明细表采集205 行耗时 38.42 秒')).toBeInTheDocument();
expect(within(dialog).getByText((_, element) => element?.textContent === '整理后支付宝资金账单136 行耗时 3.77 秒')).toBeInTheDocument();
expect(within(dialog).getByText((_, element) => element?.textContent === '对账耗时2.24 秒')).toBeInTheDocument();
expect(within(dialog).getByText('差异列表')).toBeInTheDocument();
expect(within(dialog).getByText((_, element) => element?.textContent === '待处理差异 2 条')).toBeInTheDocument();
expect(within(dialog).queryByText('所属方案')).not.toBeInTheDocument();
expect(within(dialog).queryByText('开始时间')).not.toBeInTheDocument();
expect(within(dialog).queryByText('结束时间')).not.toBeInTheDocument();
```

- [ ] **Step 2: Run the modal test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-task-list-layout.spec.tsx
```

Expected: FAIL because the modal still renders the old cards.

- [ ] **Step 3: Import the helper and add modal state**

In `finance-web/src/components/ReconWorkspace.tsx`, add:

```typescript
import {
  buildRuntimeSummaryView,
  formatCount,
  formatDuration,
} from './recon/runRuntimeSummary';
```

Near the existing `modalState` state, add:

```typescript
const [showRunRuntimeDetails, setShowRunRuntimeDetails] = useState(false);
```

- [ ] **Step 4: Build runtime summary in the run-exceptions branch**

Inside `renderModalContent`, in the `run-exceptions` branch after `const { run } = modalState;`, add:

```typescript
const runtimeSummary = buildRuntimeSummaryView(run);
const renderRuntimeMetric = (label: string, value: string) => (
  <div className="min-w-[180px] rounded-xl border border-border bg-surface-secondary px-3 py-2">
    <p className="text-[11px] font-medium text-text-secondary">{label}</p>
    <p className="mt-1 text-sm font-semibold text-text-primary">{value}</p>
  </div>
);
```

- [ ] **Step 5: Replace the old modal metric cards**

Remove the grid that renders `所属方案`, `数据日期`, `运行状态`, `异常数`, `开始时间`, `结束时间`, and `失败阶段`. Insert:

```tsx
<div className="flex flex-wrap gap-3">
  {renderRuntimeMetric('对账数据日期', runtimeSummary.bizDate || run.dataDate || '--')}
  {runtimeSummary.collectionMetrics.map((item, index) => (
    <div key={`collection-${item.side || item.businessName}-${index}`} className="min-w-[180px] rounded-xl border border-border bg-surface-secondary px-3 py-2">
      <p className="text-[11px] font-medium text-text-secondary">{item.businessName}采集</p>
      <p className="mt-1 text-sm font-semibold text-text-primary">
        {formatCount(item.rowCount)} 行耗时 {formatDuration(item.durationSeconds)}
      </p>
    </div>
  ))}
  {runtimeSummary.preparationMetrics.map((item, index) => (
    <div key={`preparation-${item.side || item.businessName}-${index}`} className="min-w-[180px] rounded-xl border border-border bg-surface-secondary px-3 py-2">
      <p className="text-[11px] font-medium text-text-secondary">整理后{item.businessName}</p>
      <p className="mt-1 text-sm font-semibold text-text-primary">
        {formatCount(item.rowCount)} 行耗时 {formatDuration(item.durationSeconds)}
      </p>
    </div>
  ))}
  {renderRuntimeMetric('对账耗时', formatDuration(runtimeSummary.reconciliationDurationSeconds))}
</div>
```

- [ ] **Step 6: Add collapsed run details and list anomaly badge**

Below the runtime metrics, add:

```tsx
<div className="rounded-2xl border border-border bg-surface-secondary">
  <button
    type="button"
    onClick={() => setShowRunRuntimeDetails((value) => !value)}
    className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-text-primary"
  >
    <span>运行详情</span>
    <span>{showRunRuntimeDetails ? '收起' : '展开'}</span>
  </button>
  {showRunRuntimeDetails ? (
    <div className="divide-y divide-border-subtle border-t border-border-subtle px-4 py-2">
      <DetailRow label="所属方案" value={run.schemeName || '--'} />
      <DetailRow label="运行状态" value={statusMeta.label} />
      <DetailRow label="队列开始时间" value={formatDateTime(runtimeSummary.queueStartedAt)} />
      <DetailRow label="队列结束时间" value={formatDateTime(runtimeSummary.queueFinishedAt)} />
      <DetailRow label="队列总耗时" value={formatDuration(runtimeSummary.queueDurationSeconds)} />
      <DetailRow label="记录写入开始时间" value={formatDateTime(run.startedAt, { includeSeconds: true })} />
      <DetailRow label="记录写入结束时间" value={formatDateTime(run.finishedAt, { includeSeconds: true })} />
      <DetailRow label="汇总接收人" value={runtimeSummary.notification.recipientName || runtimeSummary.notification.recipientIdentifier || '--'} />
      <DetailRow
        label="汇总消息推送状态"
        value={`${runtimeSummary.notification.label}${runtimeSummary.notification.messageId ? ` · ${runtimeSummary.notification.messageId}` : ''}${runtimeSummary.notification.error ? ` · ${runtimeSummary.notification.error}` : ''}`}
      />
    </div>
  ) : null}
</div>

<div className="flex flex-wrap items-center justify-between gap-3">
  <h4 className="text-base font-semibold text-text-primary">差异列表</h4>
  <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
    待处理差异 {formatCount(run.anomalyCount)} 条
  </span>
</div>
```

- [ ] **Step 7: Run and commit modal UI**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-task-list-layout.spec.tsx
```

Expected: PASS.

Commit:

```bash
cd /Users/kevin/workspace/financial-ai
git add -f finance-web/src/components/ReconWorkspace.tsx finance-web/tests/components/recon-task-list-layout.spec.tsx
git commit -m "feat: show runtime summary in exception dashboard"
```

---

### Task 4: Proc Runtime Metrics

**Files:**
- Modify: `finance-mcp/proc/mcp_server/steps_runtime.py`
- Modify: `finance-mcp/proc/mcp_server/proc_rule.py`
- Modify: `finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py`
- Modify: `finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py`

- [ ] **Step 1: Add a failing proc metric test**

In `finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py`, extend `test_execute_proc_preserves_dataset_source_type` so the fake proc response includes:

```python
"runtime_metrics": {
    "preparation": [
        {"side": "right", "target_table": "right_recon_ready", "row_count": 1, "duration_seconds": 0.42},
    ],
},
```

Add:

```python
assert result["recon_ctx"]["runtime_metrics"]["preparation"] == [
    {"side": "right", "target_table": "right_recon_ready", "row_count": 1, "duration_seconds": 0.42}
]
```

- [ ] **Step 2: Run the focused proc test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py::test_execute_proc_preserves_dataset_source_type -q
```

Expected: FAIL because `execute_proc_node` does not carry `runtime_metrics.preparation`.

- [ ] **Step 3: Expose per-target proc durations**

In `finance-mcp/proc/mcp_server/steps_runtime.py`, add in `StepsProcRuntime.__init__`:

```python
self.target_runtime_seconds: dict[str, float] = {}
```

In `_execute_step`, compute elapsed once:

```python
elapsed_seconds = time.perf_counter() - start_time
if target_table:
    self.target_runtime_seconds[target_table] = self.target_runtime_seconds.get(target_table, 0.0) + elapsed_seconds
```

Use `elapsed_seconds` in the existing log line. In `export_tables()` and `export_frame_outputs()`, add:

```python
"duration_seconds": round(max(0.0, self.target_runtime_seconds.get(table_name, 0.0)), 6),
```

- [ ] **Step 4: Return metrics from `proc_execute`**

In `finance-mcp/proc/mcp_server/proc_rule.py`, after `memory_outputs = register_proc_frame_outputs(...)`, add:

```python
runtime_metrics = {
    "preparation": [
        {
            "target_table": str(item.get("target_table") or ""),
            "row_count": int(item.get("row_count") or 0),
            "duration_seconds": item.get("duration_seconds"),
        }
        for item in (memory_outputs or generated_files)
        if str(item.get("target_table") or "")
    ]
}
```

Add `"runtime_metrics": runtime_metrics` to the steps-rule success return.

- [ ] **Step 5: Carry proc metrics through scheme execution**

In `finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py`, add helpers near `_get_recon_ctx`:

```python
def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _proc_side_from_target(target_table: str) -> str:
    normalized = str(target_table or "").strip().lower()
    if normalized == "left_recon_ready":
        return "left"
    if normalized == "right_recon_ready":
        return "right"
    return ""
```

After a successful `proc_result` and before `ctx["recon_inputs"] = proc_recon_inputs`, add:

```python
runtime_metrics = _safe_dict(ctx.get("runtime_metrics"))
preparation_metrics: list[dict[str, Any]] = []
for item in _safe_list(_safe_dict(proc_result.get("runtime_metrics")).get("preparation")):
    if not isinstance(item, dict):
        continue
    target_table = str(item.get("target_table") or "").strip()
    metric = dict(item)
    metric["side"] = str(metric.get("side") or _proc_side_from_target(target_table))
    preparation_metrics.append(metric)
if preparation_metrics:
    runtime_metrics["preparation"] = preparation_metrics
ctx["runtime_metrics"] = runtime_metrics
```

- [ ] **Step 6: Run and commit proc metrics**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py finance-agents/data-agent/tests/recon/test_proc_input_plan_runtime.py -q
```

Expected: PASS.

Commit:

```bash
cd /Users/kevin/workspace/financial-ai
git add -f finance-mcp/proc/mcp_server/steps_runtime.py finance-mcp/proc/mcp_server/proc_rule.py finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py
git commit -m "feat: capture proc runtime metrics"
```

---

### Task 5: Runtime Summary Persistence And Queue Truth

**Files:**
- Modify: `finance-mcp/auth/db.py`
- Modify: `finance-mcp/tools/recon_auto_runs.py`
- Modify: `finance-agents/data-agent/recon_worker.py`
- Modify: `finance-agents/data-agent/graphs/recon/pipeline_service.py`
- Modify: `finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py`
- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
- Modify: `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`

- [ ] **Step 1: Add failing runtime summary tests**

In `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`, add:

```python
def test_runtime_summary_written_to_execution_run_artifacts():
    ctx = {
        "biz_date": "2026-05-20",
        "run_context": {
            "queue_job_id": "queue-001",
            "queue_started_at": "2026-05-21T04:00:01+08:00",
            "queue_finished_at": "2026-05-21T04:01:15+08:00",
        },
        "source_collection_json": {
            "collections": [
                {
                    "binding": {"side": "left", "dataset_name": "交易订单明细表"},
                    "collection_records": {"record_count": 205},
                    "job": {"metrics": {"collection_timing": {"total_seconds": 38.42}}},
                },
                {
                    "binding": {"side": "right", "dataset_name": "支付宝资金账单"},
                    "collection_records": {"record_count": 136},
                    "job": {"metrics": {"collection_timing": {"total_seconds": 31.06}}},
                },
            ]
        },
        "recon_observation": {
            "summary": {"matched_exact": 136, "matched_with_diff": 0, "source_only": 69, "target_only": 0},
            "artifacts": {},
            "anomaly_items": [],
        },
        "runtime_metrics": {
            "preparation": [
                {"side": "left", "target_table": "left_recon_ready", "row_count": 205, "duration_seconds": 4.18},
                {"side": "right", "target_table": "right_recon_ready", "row_count": 136, "duration_seconds": 3.77},
            ],
            "reconciliation": {"duration_seconds": 2.24},
        },
    }

    summary = nodes._build_runtime_summary(ctx)  # noqa: SLF001

    assert summary["biz_date"] == "2026-05-20"
    assert summary["queue"]["job_id"] == "queue-001"
    assert summary["queue"]["duration_seconds"] == 74
    assert summary["collections"][0]["business_name"] == "交易订单明细表"
    assert summary["collections"][0]["row_count"] == 205
    assert summary["collections"][0]["duration_seconds"] == 38.42
    assert summary["preparation"][1]["business_name"] == "支付宝资金账单"
    assert summary["preparation"][1]["row_count"] == 136
    assert summary["reconciliation"]["duration_seconds"] == 2.24


def test_runtime_summary_notification_patch_preserves_existing_artifacts():
    artifacts = {"output_files": ["a.xlsx"], "runtime_summary": {"biz_date": "2026-05-20"}}
    patched = nodes._merge_runtime_summary_notification(  # noqa: SLF001
        artifacts,
        {
            "status": "sent",
            "summary_recipient": {"name": "张小毅", "identifier": "072007534524160438"},
            "message_id": "msg-001",
            "error": "",
        },
    )

    assert patched["output_files"] == ["a.xlsx"]
    assert patched["runtime_summary"]["biz_date"] == "2026-05-20"
    assert patched["runtime_summary"]["summary_notification"]["status"] == "sent"
    assert patched["runtime_summary"]["summary_notification"]["recipient_name"] == "张小毅"
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_runtime_summary_written_to_execution_run_artifacts finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_runtime_summary_notification_patch_preserves_existing_artifacts -q
```

Expected: FAIL because the runtime summary helpers do not exist.

- [ ] **Step 3: Return completed queue job rows**

In `finance-mcp/auth/db.py`, change `complete_recon_run` to return the updated row:

```python
def complete_recon_run(job_id: str) -> dict | None:
    """将 job 标记为 done。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'done', finished_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"complete_recon_run 失败 (job_id={job_id}): {e}")
        return None
```

In `finance-mcp/tools/recon_auto_runs.py`, change `_queue_complete` to:

```python
job = auth_db.complete_recon_run(job_id)
return {"success": bool(job), "job": job}
```

- [ ] **Step 4: Pass and patch queue facts from worker**

In `finance-agents/data-agent/recon_worker.py`, import `execution_run_update`. Replace the `run_context` argument passed to `execute_run_plan_run` with:

```python
run_context={
    **dict(job.get("run_context") or {}),
    "queue_job_id": job_id,
    "queue_started_at": str(job.get("started_at") or ""),
    "queue_created_at": str(job.get("created_at") or ""),
},
```

After `complete_result = await recon_queue_complete(system_token, job_id)`, add:

```python
completed_job = dict(complete_result.get("job") or {})
run = dict(result.get("run") or {})
run_id = str(run.get("id") or "")
artifacts = dict(run.get("artifacts_json") or {})
runtime_summary = dict(artifacts.get("runtime_summary") or {})
queue = dict(runtime_summary.get("queue") or {})
queue["finished_at"] = str(completed_job.get("finished_at") or queue.get("finished_at") or "")
queue["duration_seconds"] = _queue_duration_seconds(queue.get("started_at"), queue.get("finished_at"))
runtime_summary["queue"] = queue
artifacts["runtime_summary"] = runtime_summary
if run_id:
    await execution_run_update(auth_token, run_id, {"artifacts_json": artifacts})
```

Add helper near `_create_system_token`:

```python
def _queue_duration_seconds(started_at: object, finished_at: object) -> float | None:
    try:
        start = datetime.fromisoformat(str(started_at or "").replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(finished_at or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return round(max(0.0, (finish - start).total_seconds()), 6)
```

- [ ] **Step 5: Record recon duration and merge runtime metrics**

In `finance-agents/data-agent/graphs/recon/pipeline_service.py`, add:

```python
import time
```

At the start of `execute_headless_recon_pipeline`, after `display_name_map = dict(ref_to_display_name or {})`, add:

```python
runtime_metrics: dict[str, Any] = {}
```

Add `"runtime_metrics": runtime_metrics` to the request-build failure return dict.

Replace:

```python
recon_result, exec_call_error = await run_recon_execution_fn(execution_request)
```

with:

```python
recon_started_at = time.perf_counter()
recon_result, exec_call_error = await run_recon_execution_fn(execution_request)
runtime_metrics["reconciliation"] = {
    "duration_seconds": round(max(0.0, time.perf_counter() - recon_started_at), 6)
}
```

Add `"runtime_metrics": runtime_metrics` to the execution-call failure return dict and the final success return dict.

In `finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py`, include in the `ctx.update(...)` block:

```python
"runtime_metrics": {
    **_safe_dict(ctx.get("runtime_metrics")),
    **_safe_dict(pipeline_result.get("runtime_metrics")),
},
```

- [ ] **Step 6: Build and persist runtime summary**

In `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`, add helpers near `_safe_int`:

```python
def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_runtime_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _runtime_duration_seconds(started_at: Any, finished_at: Any) -> float | None:
    start = _parse_runtime_datetime(started_at)
    finish = _parse_runtime_datetime(finished_at)
    if not start or not finish:
        return None
    return round(max(0.0, (finish - start).total_seconds()), 6)


def _runtime_metric_name(binding: dict[str, Any], fallback: str) -> str:
    for key in ("business_name", "dataset_name", "display_name", "name", "dataset_code"):
        text = str(binding.get(key) or "").strip()
        if text and not _looks_like_physical_table_name(text):
            return text
    return fallback


def _runtime_metric_side(binding: dict[str, Any]) -> str:
    text = str(binding.get("side") or binding.get("role_code") or "").strip().lower()
    target = str(binding.get("input_plan_target_table") or binding.get("target_table") or "").strip().lower()
    if text == "left" or text.startswith("left_") or target == "left_recon_ready":
        return "left"
    if text == "right" or text.startswith("right_") or target == "right_recon_ready":
        return "right"
    return ""


def _collection_duration(collection: dict[str, Any]) -> float | None:
    job = _safe_dict(collection.get("job"))
    metrics = _safe_dict(job.get("metrics"))
    timing = _safe_dict(metrics.get("collection_timing"))
    return _safe_float(timing.get("total_seconds"))


def _summary_count(summary: dict[str, Any], side: str) -> int | None:
    matched_exact = _safe_float(summary.get("matched_exact"))
    matched_with_diff = _safe_float(summary.get("matched_with_diff"))
    source_only = _safe_float(summary.get("source_only"))
    target_only = _safe_float(summary.get("target_only"))
    if None in {matched_exact, matched_with_diff, source_only, target_only}:
        return None
    if side == "right":
        return int(matched_exact + matched_with_diff + target_only)
    return int(matched_exact + matched_with_diff + source_only)


def _runtime_business_name_by_side(collections: list[dict[str, Any]], side: str) -> str:
    for item in collections:
        if str(item.get("side") or "") == side:
            return str(item.get("business_name") or "")
    return "右侧数据源" if side == "right" else "左侧数据源"


def _build_runtime_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    source_snapshot = _safe_dict(ctx.get("source_collection_json"))
    recon_observation = _safe_dict(ctx.get("recon_observation"))
    recon_summary = _safe_dict(recon_observation.get("summary"))
    runtime_metrics = _safe_dict(ctx.get("runtime_metrics"))
    run_context = _safe_dict(ctx.get("run_context"))
    collections: list[dict[str, Any]] = []

    for index, item in enumerate(_safe_list(source_snapshot.get("collections"))):
        if not isinstance(item, dict):
            continue
        binding = _safe_dict(item.get("binding"))
        side = _runtime_metric_side(binding) or ("right" if index == 1 else "left")
        collection_records = _safe_dict(item.get("collection_records"))
        collections.append(
            {
                "side": side,
                "business_name": _runtime_metric_name(binding, "右侧数据源" if side == "right" else "左侧数据源"),
                "row_count": _safe_int(collection_records.get("record_count"), 0),
                "duration_seconds": _collection_duration(item),
            }
        )

    preparation: list[dict[str, Any]] = []
    for item in _safe_list(runtime_metrics.get("preparation")):
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").strip()
        preparation.append(
            {
                "side": side,
                "business_name": str(item.get("business_name") or _runtime_business_name_by_side(collections, side)),
                "row_count": _safe_int(item.get("row_count"), 0),
                "duration_seconds": _safe_float(item.get("duration_seconds")),
            }
        )
    if not preparation:
        for collection in collections:
            side = str(collection.get("side") or "")
            preparation.append(
                {
                    "side": side,
                    "business_name": str(collection.get("business_name") or ("右侧数据源" if side == "right" else "左侧数据源")),
                    "row_count": _summary_count(recon_summary, side),
                    "duration_seconds": None,
                }
            )

    queue_started_at = str(run_context.get("queue_started_at") or "")
    queue_finished_at = str(run_context.get("queue_finished_at") or "")
    return {
        "biz_date": str(ctx.get("biz_date") or run_context.get("biz_date") or "").strip(),
        "queue": {
            "job_id": str(run_context.get("queue_job_id") or ""),
            "started_at": queue_started_at,
            "finished_at": queue_finished_at,
            "duration_seconds": _runtime_duration_seconds(queue_started_at, queue_finished_at),
        },
        "collections": collections,
        "preparation": preparation,
        "reconciliation": _safe_dict(runtime_metrics.get("reconciliation")),
        "summary_notification": _safe_dict(_safe_dict(runtime_metrics.get("summary_notification"))),
    }


def _merge_runtime_summary_notification(
    artifacts: dict[str, Any],
    summary_result: dict[str, Any],
) -> dict[str, Any]:
    patched = dict(artifacts or {})
    runtime_summary = _safe_dict(patched.get("runtime_summary"))
    recipient = _safe_dict(summary_result.get("summary_recipient"))
    runtime_summary["summary_notification"] = {
        "status": str(summary_result.get("status") or ""),
        "recipient_name": str(recipient.get("name") or recipient.get("display_name") or ""),
        "recipient_identifier": str(recipient.get("identifier") or recipient.get("user_id") or ""),
        "message_id": str(summary_result.get("message_id") or ""),
        "error": str(summary_result.get("error") or ""),
    }
    patched["runtime_summary"] = runtime_summary
    return patched
```

In `_persist_execution_run`, replace:

```python
artifacts = _safe_dict(recon_observation.get("artifacts"))
```

with:

```python
artifacts = _safe_dict(recon_observation.get("artifacts"))
artifacts["runtime_summary"] = _build_runtime_summary(ctx)
```

- [ ] **Step 7: Write notification result back**

In `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`, add:

```python
async def _persist_runtime_summary_notification(
    *,
    auth_token: str,
    ctx: dict[str, Any],
    summary_result: dict[str, Any],
) -> None:
    run = _safe_dict(ctx.get("execution_run_record"))
    run_id = str(run.get("id") or "").strip()
    if not auth_token or not run_id or not summary_result:
        return
    artifacts = _merge_runtime_summary_notification(_safe_dict(run.get("artifacts_json")), summary_result)
    update_result = await call_mcp_tool(
        "execution_run_update",
        {"auth_token": auth_token, "run_id": run_id, "artifacts_json": artifacts},
    )
    if bool(update_result.get("success")):
        ctx["execution_run_record"] = _safe_dict(update_result.get("run")) or {**run, "artifacts_json": artifacts}
```

In `maybe_auto_notify_node`, immediately after each `ctx["auto_notify_result"] = ...` assignment and before each return, add:

```python
await _persist_runtime_summary_notification(
    auth_token=auth_token,
    ctx=ctx,
    summary_result=summary_result,
)
```

- [ ] **Step 8: Run and commit backend runtime summary**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_runtime_summary_written_to_execution_run_artifacts finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_runtime_summary_notification_patch_preserves_existing_artifacts -q
```

Expected: PASS.

Commit:

```bash
cd /Users/kevin/workspace/financial-ai
git add -f finance-mcp/auth/db.py finance-mcp/tools/recon_auto_runs.py finance-agents/data-agent/recon_worker.py finance-agents/data-agent/graphs/recon/pipeline_service.py finance-agents/data-agent/graphs/recon/scheme_execution/nodes.py finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py
git commit -m "feat: persist recon runtime summary"
```

---

### Task 6: Verification And Service Restart

**Files:**
- None

- [ ] **Step 1: Run frontend tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx tests/components/recon-task-list-layout.spec.tsx
```

Expected: PASS.

- [ ] **Step 2: Run TypeScript check**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Run backend focused tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py -q
```

Expected: PASS.

- [ ] **Step 4: Restart services**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, finance-mcp, and recon worker start without new errors.

- [ ] **Step 5: Manual acceptance**

Open a recent “泰斯支付宝对账” exception dashboard and confirm:

```text
对账数据日期
交易订单明细表采集 ... 行 耗时 ...
支付宝资金账单 ... 采集 ... 行 耗时 ...
整理后交易订单明细表 ... 行 耗时 ...
整理后支付宝资金账单 ... 行 耗时 ...
对账耗时 ...
差异列表 / 待处理差异 ... 条
```

Expand `运行详情` and confirm it shows queue start/end/duration, record write times, `汇总接收人` 张小毅, and `汇总消息推送状态` 已发送.
