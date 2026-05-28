# Recon Exception Summary Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace verbose recon exception summaries with finance-facing business conclusions in lists, while keeping structured details and raw records in detail views.

**Architecture:** Add one focused display helper under `finance-web/src/components/recon/` that turns existing exception `detail_json`, anomaly type, dataset labels, and field-label callbacks into a reusable view model. Then wire both public exception pages and the recon center to that view model instead of rendering the raw `summary` everywhere.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, existing `finance-web` Vite setup.

---

## File Structure

- Create: `finance-web/src/components/recon/exceptionBusinessSummary.ts`
  - Owns parsing `detail_json.join_key`, `compare_values`, side records, and producing short business summaries.
  - Has no React dependency.
- Create: `finance-web/tests/components/exception-business-summary.test.ts`
  - Unit coverage for missing-order, amount-diff, dynamic match field names, and record sections.
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
  - Reuse the helper for list summary, detail conclusion, compare rows, and raw record sections.
- Modify: `finance-web/src/components/ReconWorkspace.tsx`
  - Reuse the helper in the recon center run-exceptions modal and detail modal.
- Modify: existing component tests:
  - `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`
  - `finance-web/tests/components/recon-task-list-layout.spec.tsx`
  - `finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx`

## Task 1: Add Business Summary Helper

**Files:**
- Create: `finance-web/src/components/recon/exceptionBusinessSummary.ts`
- Create: `finance-web/tests/components/exception-business-summary.test.ts`

- [ ] **Step 1: Write failing helper tests**

Create `finance-web/tests/components/exception-business-summary.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import {
  buildExceptionBusinessDisplay,
  type ExceptionBusinessDisplayContext,
  type ExceptionBusinessItem,
} from '../../src/components/recon/exceptionBusinessSummary';

const context: ExceptionBusinessDisplayContext = {
  datasetLabels: {
    left: 'tb0131100248-店铺订单',
    right: '交易订单明细表',
  },
  fieldLabelForSide: (_side, field) => {
    const labels: Record<string, string> = {
      biz_key: '订单编号',
      merchant_order_no: '商户订单号',
      amount: '含税销售金额',
      paid_amount: '买家实付金额',
      order_status: '订单状态',
      pay_status: '支付状态',
    };
    return labels[field] || field;
  },
};

function buildItem(patch: Partial<ExceptionBusinessItem>): ExceptionBusinessItem {
  return {
    anomalyType: 'source_only',
    summary: '仅 tb0131100248-店铺订单 存在（交易订单明细表 缺失）：订单编号=5118002676174023242',
    raw: {},
    ...patch,
  };
}

describe('exception business summary display', () => {
  it('states which dataset misses which dynamic match field value', () => {
    const item = buildItem({
      anomalyType: 'source_only',
      raw: {
        detail_json: {
          source_ref: 'left_recon_ready',
          target_ref: 'right_recon_ready',
          join_key: [
            {
              source_field: 'biz_key',
              target_field: 'biz_key',
              source_value: '5118002676174023242',
              target_value: null,
            },
          ],
          compare_values: [
            {
              source_field: 'amount',
              target_field: 'paid_amount',
              source_value: '0.00',
              target_value: null,
            },
          ],
          left_record: {
            biz_key: '5118002676174023242',
            amount: '0.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('交易订单明细表缺失订单编号 5118002676174023242');
    expect(display.conclusion).toBe('交易订单明细表缺失订单编号 5118002676174023242');
    expect(display.keyLines).toEqual([
      {
        side: 'left',
        datasetLabel: 'tb0131100248-店铺订单',
        fieldLabel: '订单编号',
        value: '5118002676174023242',
      },
      {
        side: 'right',
        datasetLabel: '交易订单明细表',
        fieldLabel: '订单编号',
        value: '--',
      },
    ]);
    expect(display.compareLines).toEqual([
      {
        fieldLabel: '含税销售金额 / 买家实付金额',
        sourceDatasetLabel: 'tb0131100248-店铺订单',
        targetDatasetLabel: '交易订单明细表',
        sourceValue: '0.00',
        targetValue: '--',
        diffValue: '--',
      },
    ]);
    expect(display.recordSections).toHaveLength(2);
    expect(display.recordSections[0].title).toBe('tb0131100248-店铺订单');
    expect(display.recordSections[0].entries.map((entry) => entry.label)).toEqual(['订单编号', '含税销售金额']);
    expect(display.recordSections[1]).toMatchObject({
      title: '交易订单明细表',
      entries: [],
      emptyMessage: '未匹配到原始记录',
    });
  });

  it('uses the match field name from join_key instead of hard-coded order wording', () => {
    const item = buildItem({
      anomalyType: 'target_only',
      raw: {
        detail_json: {
          source_ref: 'left_recon_ready',
          target_ref: 'right_recon_ready',
          join_key: [
            {
              source_field: 'merchant_order_no',
              target_field: 'merchant_order_no',
              source_value: null,
              target_value: '202605280001',
            },
          ],
          right_record: {
            merchant_order_no: '202605280001',
            paid_amount: '88.00',
          },
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('tb0131100248-店铺订单缺失商户订单号 202605280001');
  });

  it('summarizes amount mismatches by match field and match value', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      raw: {
        detail_json: {
          join_key: [
            {
              field: 'biz_key',
              value: '5118002676174023242',
            },
          ],
          compare_values: [
            {
              source_field: 'amount',
              target_field: 'paid_amount',
              source_value: '10.00',
              target_value: '9.00',
              diff_value: '1.00',
            },
          ],
        },
      },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toBe('订单编号 5118002676174023242 金额不一致');
  });

  it('falls back to formatted original summary when join_key is unavailable', () => {
    const item = buildItem({
      anomalyType: 'matched_with_diff',
      summary: '差异类型：金额差异 匹配字段：订单号=TB001 对比字段：实收金额 100 / 98',
      raw: { detail_json: {} },
    });

    const display = buildExceptionBusinessDisplay(item, context);

    expect(display.shortSummary).toContain('差异类型：金额差异');
    expect(display.shortSummary).toContain('匹配字段：订单号=TB001');
  });
});
```

- [ ] **Step 2: Run helper test and verify it fails**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/exception-business-summary.test.ts
```

Expected: FAIL because `exceptionBusinessSummary.ts` does not exist.

- [ ] **Step 3: Implement the helper**

Create `finance-web/src/components/recon/exceptionBusinessSummary.ts`:

```typescript
export type ReconExceptionSide = 'left' | 'right';

export interface ExceptionBusinessItem {
  anomalyType: string;
  summary?: string;
  raw?: Record<string, unknown>;
}

export interface ExceptionBusinessDisplayContext {
  datasetLabels: Record<ReconExceptionSide, string>;
  fieldLabelForSide?: (side: ReconExceptionSide, field: string) => string;
}

export interface ExceptionFieldValueLine {
  side: ReconExceptionSide;
  datasetLabel: string;
  fieldLabel: string;
  value: string;
}

export interface ExceptionCompareValueLine {
  fieldLabel: string;
  sourceDatasetLabel: string;
  targetDatasetLabel: string;
  sourceValue: string;
  targetValue: string;
  diffValue: string;
}

export interface ExceptionRecordEntry {
  field: string;
  label: string;
  value: string;
}

export interface ExceptionRecordSection {
  side: ReconExceptionSide;
  title: string;
  entries: ExceptionRecordEntry[];
  emptyMessage?: string;
}

export interface ExceptionBusinessDisplay {
  shortSummary: string;
  conclusion: string;
  keyLines: ExceptionFieldValueLine[];
  compareLines: ExceptionCompareValueLine[];
  recordSections: ExceptionRecordSection[];
  fallbackSummary: string;
}

const COMMON_FIELD_LABELS: Record<string, string> = {
  biz_key: '业务单号',
  biz_date: '业务日期',
  amount: '金额',
  fee: '手续费',
  refund_amount: '退款金额',
  order_no: '订单号',
  trade_no: '交易号',
  trans_no: '交易流水号',
  merchant_order_no: '商户订单号',
  source_name: '来源名称',
};

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

function firstNonEmptyRecord(...values: unknown[]): Record<string, unknown> {
  for (const value of values) {
    if (typeof value === 'object' && value !== null && Object.keys(value).length > 0) {
      return value as Record<string, unknown>;
    }
  }
  return {};
}

export function normalizeExceptionValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function stripExceptionFieldPrefix(field: string): string {
  const normalized = field.trim();
  const prefixes = ['left_recon_ready.', 'right_recon_ready.', 'source.', 'target.', 'left.', 'right.'];
  const matchedPrefix = prefixes.find((prefix) => normalized.startsWith(prefix));
  return matchedPrefix ? normalized.slice(matchedPrefix.length) : normalized;
}

function sideFromRef(value: unknown): ReconExceptionSide | '' {
  const normalized = toText(value).trim().toLowerCase();
  if (normalized.includes('left') || normalized.includes('source')) return 'left';
  if (normalized.includes('right') || normalized.includes('target')) return 'right';
  return '';
}

function fallbackSummary(text: string): string {
  const source = (text || '异常详情待补充。').trim() || '异常详情待补充。';
  return source
    .replace(/\r\n?/g, '\n')
    .replace(/[；;]\s*/g, '\n')
    .replace(/\s{2,}/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join('\n');
}

function fieldLabel(ctx: ExceptionBusinessDisplayContext, side: ReconExceptionSide, field: string): string {
  const normalized = stripExceptionFieldPrefix(field);
  return ctx.fieldLabelForSide?.(side, normalized) || COMMON_FIELD_LABELS[normalized] || normalized || '--';
}

function detailRecord(item: ExceptionBusinessItem): Record<string, unknown> {
  const raw = asRecord(item.raw);
  return firstNonEmptyRecord(raw.detail_json, raw.detail, raw);
}

function recordsBySide(item: ExceptionBusinessItem): Record<ReconExceptionSide, Record<string, unknown>> {
  const detail = detailRecord(item);
  const explicitLeft = firstNonEmptyRecord(detail.left_record, detail.source_record, detail.left_row);
  const explicitRight = firstNonEmptyRecord(detail.right_record, detail.target_record, detail.right_row);
  const rawRecord = firstNonEmptyRecord(detail.raw_record, detail.record);

  const normalizeRecord = (record: Record<string, unknown>) =>
    Object.fromEntries(Object.entries(record).map(([key, value]) => [stripExceptionFieldPrefix(key), value]));

  if (Object.keys(explicitLeft).length > 0 || Object.keys(explicitRight).length > 0) {
    return {
      left: normalizeRecord(explicitLeft),
      right: normalizeRecord(explicitRight),
    };
  }

  const left: Record<string, unknown> = {};
  const right: Record<string, unknown> = {};
  Object.entries(rawRecord).forEach(([key, value]) => {
    if (key.startsWith('left_recon_ready.') || key.startsWith('source.') || key.startsWith('left.')) {
      left[stripExceptionFieldPrefix(key)] = value;
      return;
    }
    if (key.startsWith('right_recon_ready.') || key.startsWith('target.') || key.startsWith('right.')) {
      right[stripExceptionFieldPrefix(key)] = value;
    }
  });
  return { left, right };
}

function rawValue(item: ExceptionBusinessItem, side: ReconExceptionSide, field: string): unknown {
  const detail = detailRecord(item);
  const rawRecord = firstNonEmptyRecord(detail.raw_record, detail.record);
  const normalized = stripExceptionFieldPrefix(field);
  const prefixes = side === 'left'
    ? ['left_recon_ready.', 'source.', 'left.']
    : ['right_recon_ready.', 'target.', 'right.'];

  for (const prefix of prefixes) {
    const value = rawRecord[`${prefix}${normalized}`];
    if (value !== null && value !== undefined && value !== '') return value;
  }

  const sideRecord = recordsBySide(item)[side];
  const value = sideRecord[normalized];
  if (value !== null && value !== undefined && value !== '') return value;
  return rawRecord[normalized];
}

function joinKeyLines(
  item: ExceptionBusinessItem,
  ctx: ExceptionBusinessDisplayContext,
): ExceptionFieldValueLine[] {
  const detail = detailRecord(item);
  const sourceSide = sideFromRef(detail.source_ref) || 'left';
  const targetSide = sideFromRef(detail.target_ref) || 'right';

  return asList(detail.join_key)
    .filter((entry) => typeof entry === 'object' && entry !== null)
    .flatMap((entry) => {
      const row = asRecord(entry);
      const sourceField = toText(row.source_field || row.field).trim();
      const targetField = toText(row.target_field || row.field).trim();
      const lines: ExceptionFieldValueLine[] = [];

      if (sourceField) {
        lines.push({
          side: sourceSide,
          datasetLabel: ctx.datasetLabels[sourceSide],
          fieldLabel: fieldLabel(ctx, sourceSide, sourceField),
          value: normalizeExceptionValue(row.source_value ?? row.value ?? rawValue(item, sourceSide, sourceField)),
        });
      }

      if (targetField) {
        lines.push({
          side: targetSide,
          datasetLabel: ctx.datasetLabels[targetSide],
          fieldLabel: fieldLabel(ctx, targetSide, targetField),
          value: normalizeExceptionValue(row.target_value ?? row.value ?? rawValue(item, targetSide, targetField)),
        });
      }

      return lines;
    });
}

function compareLines(
  item: ExceptionBusinessItem,
  ctx: ExceptionBusinessDisplayContext,
): ExceptionCompareValueLine[] {
  const detail = detailRecord(item);
  const sourceSide = sideFromRef(detail.source_ref) || 'left';
  const targetSide = sideFromRef(detail.target_ref) || 'right';

  return asList(detail.compare_values)
    .filter((entry) => typeof entry === 'object' && entry !== null)
    .map((entry) => {
      const row = asRecord(entry);
      const sourceField = toText(row.source_field).trim();
      const targetField = toText(row.target_field).trim();
      const sourceLabel = sourceField ? fieldLabel(ctx, sourceSide, sourceField) : '';
      const targetLabel = targetField ? fieldLabel(ctx, targetSide, targetField) : '';
      return {
        fieldLabel: sourceLabel && targetLabel && sourceLabel !== targetLabel
          ? `${sourceLabel} / ${targetLabel}`
          : sourceLabel || targetLabel || toText(row.name, '对比值'),
        sourceDatasetLabel: ctx.datasetLabels[sourceSide],
        targetDatasetLabel: ctx.datasetLabels[targetSide],
        sourceValue: normalizeExceptionValue(row.source_value ?? rawValue(item, sourceSide, sourceField)),
        targetValue: normalizeExceptionValue(row.target_value ?? rawValue(item, targetSide, targetField)),
        diffValue: normalizeExceptionValue(row.diff_value),
      };
    });
}

function primaryJoinLine(lines: ExceptionFieldValueLine[], preferredSide?: ReconExceptionSide): ExceptionFieldValueLine | null {
  const preferred = preferredSide ? lines.find((line) => line.side === preferredSide && line.value !== '--') : null;
  return preferred || lines.find((line) => line.value !== '--') || lines[0] || null;
}

function classifyCompareDifference(lines: ExceptionCompareValueLine[]): string {
  if (lines.length > 1) return '多字段不一致';
  const label = lines[0]?.fieldLabel || '';
  if (/金额|实付|含税|销售|amount|paid/i.test(label)) return '金额不一致';
  if (/状态|status/i.test(label)) return '状态不一致';
  return label ? `${label}不一致` : '字段不一致';
}

function buildShortSummary(
  item: ExceptionBusinessItem,
  keyLines: ExceptionFieldValueLine[],
  compareValueLines: ExceptionCompareValueLine[],
  originalFallback: string,
): string {
  const type = item.anomalyType.trim().toLowerCase();

  if (type === 'source_only') {
    const keyLine = primaryJoinLine(keyLines, 'left');
    if (keyLine) {
      const missingDataset = keyLines.find((line) => line.side === 'right')?.datasetLabel || '目标数据集';
      return `${missingDataset}缺失${keyLine.fieldLabel} ${keyLine.value}`;
    }
  }

  if (type === 'target_only') {
    const keyLine = primaryJoinLine(keyLines, 'right');
    if (keyLine) return `${keyLines.find((line) => line.side === 'left')?.datasetLabel || '源数据集'}缺失${keyLine.fieldLabel} ${keyLine.value}`;
  }

  if (type === 'matched_with_diff' || type === 'value_mismatch') {
    const keyLine = primaryJoinLine(keyLines);
    if (keyLine) return `${keyLine.fieldLabel} ${keyLine.value} ${classifyCompareDifference(compareValueLines)}`;
  }

  return originalFallback;
}

function recordEntries(
  side: ReconExceptionSide,
  record: Record<string, unknown>,
  ctx: ExceptionBusinessDisplayContext,
): ExceptionRecordEntry[] {
  return Object.entries(record)
    .filter(([field]) => !['source_name', 'source_side', 'source_count'].includes(stripExceptionFieldPrefix(field)))
    .map(([field, value]) => ({
      field: stripExceptionFieldPrefix(field),
      label: fieldLabel(ctx, side, field),
      value: normalizeExceptionValue(value),
    }));
}

export function buildExceptionBusinessDisplay(
  item: ExceptionBusinessItem,
  ctx: ExceptionBusinessDisplayContext,
): ExceptionBusinessDisplay {
  const originalFallback = fallbackSummary(item.summary || '');
  const keyLines = joinKeyLines(item, ctx);
  const compareValueLines = compareLines(item, ctx);
  const shortSummary = buildShortSummary(item, keyLines, compareValueLines, originalFallback);
  const sideRecords = recordsBySide(item);

  return {
    shortSummary,
    conclusion: shortSummary,
    keyLines,
    compareLines: compareValueLines,
    recordSections: (['left', 'right'] as ReconExceptionSide[]).map((side) => {
      const entries = recordEntries(side, sideRecords[side], ctx);
      return {
        side,
        title: ctx.datasetLabels[side],
        entries,
        emptyMessage: entries.length === 0 ? '未匹配到原始记录' : undefined,
      };
    }),
    fallbackSummary: originalFallback,
  };
}
```

- [ ] **Step 4: Run helper tests and type-check this helper**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/exception-business-summary.test.ts
npx tsc --noEmit
```

Expected: PASS for the new helper test and no TypeScript errors.

- [ ] **Step 5: Commit helper**

Run:

```bash
git add finance-web/src/components/recon/exceptionBusinessSummary.ts finance-web/tests/components/exception-business-summary.test.ts
git commit -m "feat: add recon exception business summary helper"
```

## Task 2: Use Business Summary in Public Exception Page

**Files:**
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
- Modify: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`

- [ ] **Step 1: Replace public page summary test with business-summary expectations**

In `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`, replace `expectStructuredSummary` with:

```typescript
function expectNoStructuredSummaryLabels(container: HTMLElement) {
  expect(within(container).queryByText('差异类型')).not.toBeInTheDocument();
  expect(within(container).queryByText('匹配字段')).not.toBeInTheDocument();
  expect(within(container).queryByText('对比字段')).not.toBeInTheDocument();
  expect(within(container).queryByText('含税销售金额 ↔ 买家实付金额')).not.toBeInTheDocument();
}
```

Replace the `formats exception summaries consistently in the public difference list` fixture exception with:

```typescript
{
  id: 'exception-003',
  anomaly_type: 'source_only',
  summary: '仅 tb0131100248-店铺订单 存在（交易订单明细表 缺失）：订单编号=5118002676174023242 含税销售金额 ↔ 买家实付金额：tb0131100248-店铺订单 0.00',
  owner_name: '周行',
  processing_status: 'pending',
  detail_json: {
    source_ref: 'left_recon_ready',
    target_ref: 'right_recon_ready',
    join_key: [
      {
        source_field: 'biz_key',
        target_field: 'biz_key',
        source_value: '5118002676174023242',
        target_value: null,
      },
    ],
    compare_values: [
      {
        source_field: 'amount',
        target_field: 'paid_amount',
        source_value: '0.00',
        target_value: null,
      },
    ],
    left_record: {
      biz_key: '5118002676174023242',
      amount: '0.00',
    },
  },
}
```

Give the scheme a usable `scheme_meta_json`:

```typescript
scheme_meta_json: {
  dataset_bindings: {
    left: [
      {
        dataset_id: 'dataset-left',
        dataset_name: 'tb0131100248-店铺订单',
        business_name: 'tb0131100248-店铺订单',
        field_label_map: {
          biz_key: '订单编号',
          amount: '含税销售金额',
        },
      },
    ],
    right: [
      {
        dataset_id: 'dataset-right',
        dataset_name: '交易订单明细表',
        business_name: '交易订单明细表',
        field_label_map: {
          biz_key: '订单编号',
          paid_amount: '买家实付金额',
        },
      },
    ],
  },
}
```

Update expectations:

```typescript
await screen.findByText('交易订单明细表缺失订单编号 5118002676174023242');
expectNoStructuredSummaryLabels(document.body);

fireEvent.click(screen.getByRole('button', { name: '详情' }));

const detailDialog = await screen.findByRole('dialog', { name: '差异详情' });
expect(within(detailDialog).getByText('交易订单明细表缺失订单编号 5118002676174023242')).toBeInTheDocument();
expect(within(detailDialog).getByText('对账关键字段')).toBeInTheDocument();
expect(within(detailDialog).getByText('差异字段和值')).toBeInTheDocument();
expect(within(detailDialog).getByText('tb0131100248-店铺订单')).toBeInTheDocument();
expect(within(detailDialog).getByText('交易订单明细表')).toBeInTheDocument();
expect(within(detailDialog).getByText('未匹配到原始记录')).toBeInTheDocument();
expectNoStructuredSummaryLabels(detailDialog);
```

- [ ] **Step 2: Run public page test and verify it fails**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected: FAIL because the public page still renders `ExceptionSummary` from the raw long summary.

- [ ] **Step 3: Import and build display models in the public page**

In `finance-web/src/components/PublicReconRunExceptionsPage.tsx`, import:

```typescript
import {
  buildExceptionBusinessDisplay,
  normalizeExceptionValue,
  stripExceptionFieldPrefix,
  type ExceptionBusinessDisplay,
  type ExceptionRecordEntry,
} from './recon/exceptionBusinessSummary';
```

Add:

```typescript
function businessDisplayForException(
  item: ReconRunExceptionDetail,
  ctx: ExceptionDisplayContext,
): ExceptionBusinessDisplay {
  return buildExceptionBusinessDisplay(
    {
      anomalyType: item.anomalyType,
      summary: readableExceptionSummary(item, ctx),
      raw: item.raw,
    },
    {
      datasetLabels: ctx.datasetLabels,
      fieldLabelForSide: (side, field) => displayFieldLabelForSide(ctx, side, field),
    },
  );
}
```

Replace `normalizeValue` internals with `normalizeExceptionValue` or remove local duplication where safe:

```typescript
function normalizeValue(value: unknown): string {
  return normalizeExceptionValue(value);
}
```

- [ ] **Step 4: Replace public list rendering**

In the list row, replace:

```tsx
<ExceptionSummary
  text={readableExceptionSummary(item, displayContext)}
  valueClassName="text-sm text-text-primary"
/>
```

with:

```tsx
<p className="break-words text-sm font-medium leading-6 text-text-primary" style={ANYWHERE_WRAP_STYLE}>
  {businessDisplayForException(item, displayContext).shortSummary}
</p>
```

Remove the `fieldValueSummary` column content or keep it as a hidden-search source only. The visible column `关键字段和值` should no longer show amount details. If the column remains in this task, render only the first key line:

```tsx
{(() => {
  const display = businessDisplayForException(item, displayContext);
  const firstKey = display.keyLines.find((line) => line.value !== '--') || display.keyLines[0];
  return (
    <p className="whitespace-pre-line break-words text-sm leading-6 text-text-secondary" style={ANYWHERE_WRAP_STYLE}>
      {firstKey ? `${firstKey.fieldLabel} = ${firstKey.value}` : '--'}
    </p>
  );
})()}
```

- [ ] **Step 5: Replace public detail rendering**

In the selected-exception detail modal, compute once near existing selected vars:

```typescript
const selectedBusinessDisplay = selectedException
  ? businessDisplayForException(selectedException, displayContext)
  : null;
```

In the summary section, replace `ExceptionSummary` with:

```tsx
{selectedBusinessDisplay ? (
  <p className="mt-2 break-words text-sm font-medium leading-6 text-text-primary" style={ANYWHERE_WRAP_STYLE}>
    {selectedBusinessDisplay.conclusion}
  </p>
) : null}
```

Replace selected key/compare line vars:

```typescript
const selectedJoinLines = selectedBusinessDisplay?.keyLines || [];
const selectedCompareLines = selectedBusinessDisplay?.compareLines || [];
```

Update compare table headers:

```tsx
<th className="px-3 py-2 font-medium">字段</th>
<th className="px-3 py-2 font-medium">{selectedCompareLines[0]?.sourceDatasetLabel || displayContext.datasetLabels.left}</th>
<th className="px-3 py-2 font-medium">{selectedCompareLines[0]?.targetDatasetLabel || displayContext.datasetLabels.right}</th>
<th className="px-3 py-2 font-medium">差异值</th>
```

Map compare rows using `sourceValue` and `targetValue`.

Replace `recordSectionEntriesForSide` usage with helper record sections. Update `PublicRecordSection` props:

```typescript
function PublicRecordSection({
  title,
  entries,
  emptyMessage,
}: {
  title: string;
  entries: ExceptionRecordEntry[];
  emptyMessage?: string;
}) {
  const orderedEntries = orderExceptionRecordEntries(entries, title);
  return (
    <section className="rounded-2xl border border-border bg-surface-secondary p-4">
      <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
      {orderedEntries.length > 0 ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {orderedEntries.map((entry) => (
            <div key={`${entry.field}-${entry.label}`} className="min-w-0 rounded-xl border border-border-subtle bg-surface px-3 py-2">
              <dt className="text-xs text-text-muted">{entry.label}</dt>
              <dd className="mt-1 whitespace-pre-wrap break-words text-sm text-text-primary">{entry.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-3 rounded-xl border border-dashed border-border-subtle bg-surface px-3 py-3 text-sm text-text-secondary">
          {emptyMessage || '未匹配到原始记录'}
        </p>
      )}
    </section>
  );
}
```

Render:

```tsx
{selectedBusinessDisplay?.recordSections.map((section) => (
  <PublicRecordSection
    key={`${selectedException.id}-${section.side}`}
    title={section.title}
    entries={section.entries}
    emptyMessage={section.emptyMessage}
  />
))}
```

- [ ] **Step 6: Update public page search haystack**

Replace `readableExceptionSummary(item, displayContext)` and `fieldValueSummary(item, displayContext)` in the haystack with:

```typescript
const display = businessDisplayForException(item, displayContext);
display.shortSummary,
display.conclusion,
display.keyLines.map((line) => `${line.datasetLabel} ${line.fieldLabel} ${line.value}`).join('\n'),
display.compareLines.map((line) => `${line.fieldLabel} ${line.sourceValue} ${line.targetValue}`).join('\n'),
display.fallbackSummary,
```

- [ ] **Step 7: Run public page tests**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/public-recon-run-exceptions-page.test.tsx tests/components/exception-business-summary.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit public page integration**

Run:

```bash
git add finance-web/src/components/PublicReconRunExceptionsPage.tsx finance-web/tests/components/public-recon-run-exceptions-page.test.tsx
git commit -m "feat: simplify public recon exception summaries"
```

## Task 3: Use Business Summary in Recon Center

**Files:**
- Modify: `finance-web/src/components/ReconWorkspace.tsx`
- Modify: `finance-web/tests/components/recon-task-list-layout.spec.tsx`
- Modify: `finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx`

- [ ] **Step 1: Update recon center tests**

In `finance-web/tests/components/recon-task-list-layout.spec.tsx`, rename the test `异常看板按段换行展示异常摘要` to `异常看板展示业务化短摘要`.

Use exception fixture:

```typescript
{
  id: 'exception-1',
  anomaly_type: 'source_only',
  summary: '仅 tb0131100248-店铺订单 存在（交易订单明细表 缺失）：订单编号=5118002676174023242 含税销售金额 ↔ 买家实付金额：tb0131100248-店铺订单 0.00',
  owner_name: '周行',
  processing_status: 'pending',
  detail_json: {
    source_ref: 'left_recon_ready',
    target_ref: 'right_recon_ready',
    join_key: [
      {
        source_field: 'biz_key',
        target_field: 'biz_key',
        source_value: '5118002676174023242',
        target_value: null,
      },
    ],
    compare_values: [
      {
        source_field: 'amount',
        target_field: 'paid_amount',
        source_value: '0.00',
        target_value: null,
      },
    ],
    left_record: {
      biz_key: '5118002676174023242',
      amount: '0.00',
    },
  },
}
```

Add `scheme_meta_json` to the schemes fixture:

```typescript
scheme_meta_json: {
  dataset_bindings: {
    left: [
      {
        dataset_id: 'left-dataset',
        dataset_name: 'tb0131100248-店铺订单',
        business_name: 'tb0131100248-店铺订单',
        field_label_map: { biz_key: '订单编号', amount: '含税销售金额' },
      },
    ],
    right: [
      {
        dataset_id: 'right-dataset',
        dataset_name: '交易订单明细表',
        business_name: '交易订单明细表',
        field_label_map: { biz_key: '订单编号', paid_amount: '买家实付金额' },
      },
    ],
  },
}
```

Update expectations:

```typescript
expect(within(dialog).getByText('交易订单明细表缺失订单编号 5118002676174023242')).toBeInTheDocument();
expect(within(dialog).queryByText('差异类型')).not.toBeInTheDocument();
expect(within(dialog).queryByText('匹配字段')).not.toBeInTheDocument();
expect(within(dialog).queryByText('对比字段')).not.toBeInTheDocument();

fireEvent.click(within(dialog).getByRole('button', { name: '查看详情' }));

const detailDialog = await screen.findByRole('dialog', { name: '异常详情' });
expect(within(detailDialog).getByText('交易订单明细表缺失订单编号 5118002676174023242')).toBeInTheDocument();
expect(within(detailDialog).getByText('tb0131100248-店铺订单')).toBeInTheDocument();
expect(within(detailDialog).getByText('交易订单明细表')).toBeInTheDocument();
expect(within(detailDialog).getByText('未匹配到原始记录')).toBeInTheDocument();
```

In `finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx`, update the expected dialog summary from the generic sentence to:

```typescript
expect(within(dialog).getByText('资金流水缺失平台订单客户订单号 5115360674997007548')).toBeInTheDocument();
```

and add a scheme meta fixture with dataset labels:

```typescript
scheme_meta_json: {
  dataset_bindings: {
    left: [
      {
        dataset_id: 'left-dataset',
        dataset_name: '订单表',
        business_name: '订单表',
        field_label_map: { 平台订单客户订单号: '平台订单客户订单号', 含税销售金额: '含税销售金额' },
      },
    ],
    right: [
      {
        dataset_id: 'right-dataset',
        dataset_name: '资金流水',
        business_name: '资金流水',
        field_label_map: { 平台订单客户订单号: '平台订单客户订单号' },
      },
    ],
  },
}
```

- [ ] **Step 2: Run recon center tests and verify they fail**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/recon-task-list-layout.spec.tsx tests/components/recon-workspace-run-exceptions-panel.test.tsx
```

Expected: FAIL because `ReconWorkspace` still renders `ExceptionSummary` from raw `summary`.

- [ ] **Step 3: Import helper in ReconWorkspace**

In `finance-web/src/components/ReconWorkspace.tsx`, replace the `ExceptionSummary` import with:

```typescript
import {
  buildExceptionBusinessDisplay,
  normalizeExceptionValue,
  stripExceptionFieldPrefix,
  type ExceptionBusinessDisplay,
  type ExceptionRecordEntry,
} from './recon/exceptionBusinessSummary';
```

Remove `ExceptionSummary` if no other usage remains.

Change:

```typescript
function formatDetailValue(value: unknown): string {
  ...
}
```

to:

```typescript
function formatDetailValue(value: unknown): string {
  return normalizeExceptionValue(value);
}
```

Change:

```typescript
function stripRunExceptionFieldPrefix(field: string): string {
  ...
}
```

to:

```typescript
function stripRunExceptionFieldPrefix(field: string): string {
  return stripExceptionFieldPrefix(field);
}
```

- [ ] **Step 4: Add recon center display adapter**

Near the existing `selectedExceptionSchemeMeta` code, add:

```typescript
function buildRunExceptionDisplay(
  item: ReconRunExceptionDetail,
  schemeMeta: SchemeMetaSummary | null,
): ExceptionBusinessDisplay {
  const leftLabel = schemeMeta
    ? resolveResultDatasetLabel(
        'left',
        schemeMeta.matchFieldPairs,
        schemeMeta.leftOutputFields,
        schemeMeta.leftSources,
      )
    : '数据集 A';
  const rightLabel = schemeMeta
    ? resolveResultDatasetLabel(
        'right',
        schemeMeta.matchFieldPairs,
        schemeMeta.rightOutputFields,
        schemeMeta.rightSources,
      )
    : '数据集 B';

  const labelMaps = schemeMeta
    ? {
        left: schemeMeta.leftOutputFieldLabelMap,
        right: schemeMeta.rightOutputFieldLabelMap,
      }
    : { left: {}, right: {} };

  return buildExceptionBusinessDisplay(
    {
      anomalyType: item.anomalyType,
      summary: item.summary,
      raw: item.raw,
    },
    {
      datasetLabels: {
        left: leftLabel || '数据集 A',
        right: rightLabel || '数据集 B',
      },
      fieldLabelForSide: (side, field) => {
        const label = labelMaps[side][stripRunExceptionFieldPrefix(field)];
        return label || humanizeExceptionFieldName(field);
      },
    },
  );
}
```

Define `buildRunExceptionDisplay` above `ReconWorkspace` component body and below the helper functions it calls, so it can reference `resolveResultDatasetLabel`, `stripRunExceptionFieldPrefix`, and `humanizeExceptionFieldName`.

- [ ] **Step 5: Replace recon center list rendering**

Inside `renderRunExceptionModal`, compute:

```typescript
const exceptionScheme = selectedExceptionRun
  ? schemes.find((item) => item.schemeCode === selectedExceptionRun.schemeCode) || null
  : null;
const exceptionSchemeMeta = exceptionScheme ? extractSchemeMeta(exceptionScheme) : null;
```

For each `modalExceptions.map((item) => ...)`, compute:

```tsx
const display = buildRunExceptionDisplay(item, exceptionSchemeMeta);
```

and replace:

```tsx
<ExceptionSummary
  text={item.summary}
  valueClassName="text-sm font-medium text-text-primary"
/>
```

with:

```tsx
<p className="break-words text-sm font-medium leading-6 text-text-primary">
  {display.shortSummary}
</p>
```

- [ ] **Step 6: Replace recon center detail header and raw sections**

For `selectedExceptionDetail`, compute:

```typescript
const selectedExceptionBusinessDisplay = selectedExceptionDetail
  ? buildRunExceptionDisplay(selectedExceptionDetail, selectedExceptionSchemeMeta)
  : null;
```

Replace detail header `ExceptionSummary` with:

```tsx
{selectedExceptionBusinessDisplay ? (
  <p className="mt-1 break-words text-base font-semibold leading-7 text-text-primary">
    {selectedExceptionBusinessDisplay.conclusion}
  </p>
) : null}
```

Replace `selectedExceptionRecordSections` construction with:

```typescript
const selectedExceptionRecordSections = selectedExceptionBusinessDisplay?.recordSections || [];
```

Render sections with empty state support:

```tsx
{selectedExceptionRecordSections.length > 0 ? (
  <div className={cn('grid gap-5', selectedExceptionRecordSections.length > 1 && 'xl:grid-cols-2')}>
    {selectedExceptionRecordSections.map((section) => (
      <div key={`${selectedExceptionDetail.id}-${section.side}`} className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
        <p className="text-sm font-semibold text-text-primary">{section.title}</p>
        {section.entries.length > 0 ? (
          <div className="mt-3 grid gap-3">
            {orderExceptionRecordEntries(section.entries, section.title).map((entry) => (
              <div key={`${selectedExceptionDetail.id}-${section.title}-${entry.field}`} className="rounded-2xl border border-border bg-surface px-4 py-3">
                <p className="text-xs text-text-secondary">{entry.label}</p>
                <p className="mt-1 whitespace-pre-wrap break-all text-sm text-text-primary">
                  {entry.value}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 rounded-2xl border border-dashed border-border bg-surface px-4 py-3 text-sm text-text-secondary">
            {section.emptyMessage || '未匹配到原始记录'}
          </p>
        )}
      </div>
    ))}
  </div>
) : (
  <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-5 text-sm text-text-secondary">
    当前没有返回原始记录。
  </div>
)}
```

- [ ] **Step 7: Run recon center tests**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/recon-task-list-layout.spec.tsx tests/components/recon-workspace-run-exceptions-panel.test.tsx tests/components/exception-business-summary.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit recon center integration**

Run:

```bash
git add finance-web/src/components/ReconWorkspace.tsx finance-web/tests/components/recon-task-list-layout.spec.tsx finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx
git commit -m "feat: simplify recon center exception summaries"
```

## Task 4: Full Frontend Verification and Service Restart

**Files:**
- No planned source edits unless verification exposes a bug.

- [ ] **Step 1: Run focused component tests**

Run:

```bash
cd finance-web
npm run test:components -- tests/components/exception-business-summary.test.ts tests/components/public-recon-run-exceptions-page.test.tsx tests/components/recon-task-list-layout.spec.tsx tests/components/recon-workspace-run-exceptions-panel.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run TypeScript check**

Run:

```bash
cd finance-web
npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd finance-web
npm run build
```

Expected: PASS.

- [ ] **Step 4: Restart services after finance-web changes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: services restart and `finance-web` is available at `http://localhost:5173`.

- [ ] **Step 5: Commit any verification fixes**

Only if Steps 1-3 required fixes, commit them:

```bash
git status --short
git add <fixed-files>
git commit -m "fix: stabilize recon exception summary display"
```

If there were no fixes, do not create an empty commit.

## Self-Review

Spec coverage:

- List uses short business conclusion: Task 1 helper and Tasks 2-3 list render replacements.
- Missing dataset plus dynamic match field value: Task 1 tests and helper logic.
- Amount/field details only in detail: Task 2 and Task 3 detail rendering.
- Dataset names instead of technical side labels: Task 1 compare model plus Task 2 public detail table.
- Raw records by source dataset, missing side empty state: Task 1 record sections plus Tasks 2-3 section rendering.
- Avoid growing large files: helper module isolates parsing/display rules.

Placeholder scan:

- The plan contains no unresolved placeholder language.
- The only conditional path is the verification-fix commit in Task 4, which has an explicit no-empty-commit rule.

Type consistency:

- The helper types are named consistently as `ExceptionBusinessDisplay`, `ExceptionFieldValueLine`, `ExceptionCompareValueLine`, `ExceptionRecordSection`, and `ReconExceptionSide`.
- React components consume helper fields `shortSummary`, `conclusion`, `keyLines`, `compareLines`, and `recordSections`.
