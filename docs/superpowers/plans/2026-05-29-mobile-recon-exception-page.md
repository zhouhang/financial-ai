# Mobile Recon Exception Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public reconciliation difference page usable on phones while keeping the existing PC table layout unchanged.

**Architecture:** Keep the current public page data flow and desktop table. Add a mobile-only exception card component, a responsive compare-values component, and small responsive class changes to the existing detail dialog so phone users see a full-screen detail layer with card-based compare values and all raw-record fields.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind utility classes, Vitest, Testing Library, Playwright for manual visual verification.

---

## File Structure

- Modify: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`
  - Add failing coverage for the mobile exception card and mobile compare-value detail content.
  - Adjust the existing exact summary assertion to tolerate both desktop and mobile DOM copies.
- Create: `finance-web/src/components/recon/PublicReconRunExceptionMobileCard.tsx`
  - Owns the phone-only list item view: summary, key field, first compare line, owner, processing status, and `查看详情`.
- Create: `finance-web/src/components/recon/PublicReconExceptionCompareValues.tsx`
  - Owns the responsive rendering of compare values: current desktop table for `md` and wider, card list below `md`.
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
  - Import the two new components.
  - Render desktop list as `hidden md:block` and mobile list as `md:hidden`.
  - Keep desktop detail modal dimensions at `md` and wider, while phone uses a full-screen fixed detail layer.
  - Replace the inline compare-value table with `PublicReconExceptionCompareValues`.

## Task 1: Add Failing Mobile Behavior Tests

**Files:**
- Modify: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`

- [ ] **Step 1: Add mobile assertions to the public exception summary test**

In `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`, update the third test payload so `detail_json.left_record` contains one raw-only field and add assertions for the mobile list. Replace this block:

```tsx
    await screen.findByText('交易订单明细表缺失订单编号 5118002676174023242');
```

with:

```tsx
    const summaryMatches = await screen.findAllByText('交易订单明细表缺失订单编号 5118002676174023242');
    expect(summaryMatches.length).toBeGreaterThanOrEqual(1);
```

Then add this raw field to the existing `left_record` object in the same test:

```tsx
            left_record: {
              biz_key: '5118002676174023242',
              amount: '0.00',
              buyer_nick: 'mobile-buyer-001',
            },
```

Then add these assertions immediately after `expectNoStructuredSummaryLabels(document.body);`:

```tsx
    const mobileCard = screen.getByTestId('mobile-exception-card-exception-003');
    expect(within(mobileCard).getByText('交易订单明细表缺失订单编号 5118002676174023242')).toBeInTheDocument();
    expect(within(mobileCard).getByText('tb0131100248-店铺订单：订单编号 = 5118002676174023242')).toBeInTheDocument();
    expect(within(mobileCard).getByText('含税销售金额')).toBeInTheDocument();
    expect(within(mobileCard).getByText('周行')).toBeInTheDocument();
    expect(within(mobileCard).getByText('待处理')).toBeInTheDocument();
    expect(within(mobileCard).getByRole('button', { name: '查看详情' })).toBeInTheDocument();
```

- [ ] **Step 2: Add mobile detail assertions**

In the same test, replace:

```tsx
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
```

with:

```tsx
    fireEvent.click(within(mobileCard).getByRole('button', { name: '查看详情' }));
```

Then add these assertions after `expect(within(detailDialog).getByText('差异字段和值')).toBeInTheDocument();`:

```tsx
    const mobileCompareValues = within(detailDialog).getByTestId('mobile-compare-values');
    expect(within(mobileCompareValues).getByText('含税销售金额')).toBeInTheDocument();
    expect(within(mobileCompareValues).getByText('tb0131100248-店铺订单')).toBeInTheDocument();
    expect(within(mobileCompareValues).getByText('0.00')).toBeInTheDocument();
    expect(within(detailDialog).getByText('mobile-buyer-001')).toBeInTheDocument();
```

- [ ] **Step 3: Run the focused test and verify it fails for missing mobile UI**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected result:

```text
FAIL tests/components/public-recon-run-exceptions-page.test.tsx
Unable to find an element by: [data-testid="mobile-exception-card-exception-003"]
```

- [ ] **Step 4: Commit the failing test**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/tests/components/public-recon-run-exceptions-page.test.tsx
git commit -m "test: cover mobile public recon exceptions"
```

## Task 2: Build the Mobile Exception Card

**Files:**
- Create: `finance-web/src/components/recon/PublicReconRunExceptionMobileCard.tsx`

- [ ] **Step 1: Create the mobile card component**

Create `finance-web/src/components/recon/PublicReconRunExceptionMobileCard.tsx` with:

```tsx
import { Eye } from 'lucide-react';

import type { ExceptionBusinessDisplay } from './exceptionBusinessSummary';

const ANYWHERE_WRAP_STYLE = { overflowWrap: 'anywhere' } as const;

export interface PublicReconRunExceptionMobileCardProps {
  id: string;
  display: ExceptionBusinessDisplay;
  fieldSummary: string;
  ownerName: string;
  processingStatusLabel: string;
  onOpen: () => void;
}

export default function PublicReconRunExceptionMobileCard({
  id,
  display,
  fieldSummary,
  ownerName,
  processingStatusLabel,
  onOpen,
}: PublicReconRunExceptionMobileCardProps) {
  const firstCompareLine = display.compareLines[0] || null;

  return (
    <article
      data-testid={`mobile-exception-card-${id}`}
      className="border-b border-border-subtle px-4 py-4 last:border-b-0"
    >
      <div className="space-y-3">
        <p
          className="whitespace-pre-line break-words text-sm font-semibold leading-6 text-text-primary"
          style={ANYWHERE_WRAP_STYLE}
        >
          {display.shortSummary}
        </p>
        <div className="rounded-xl border border-border-subtle bg-surface-secondary px-3 py-2">
          <p className="text-[11px] font-medium text-text-muted">关键字段和值</p>
          <p
            className="mt-1 whitespace-pre-line break-words text-sm leading-6 text-text-primary"
            style={ANYWHERE_WRAP_STYLE}
          >
            {fieldSummary}
          </p>
        </div>
        {firstCompareLine ? (
          <div className="rounded-xl border border-border-subtle bg-surface-secondary px-3 py-2">
            <p className="text-[11px] font-medium text-text-muted">差异字段</p>
            <p className="mt-1 text-sm font-medium text-text-primary">{firstCompareLine.fieldLabel}</p>
            <div className="mt-2 grid gap-2 text-sm text-text-secondary">
              <p className="break-words" style={ANYWHERE_WRAP_STYLE}>
                {firstCompareLine.sourceDatasetLabel}：{firstCompareLine.sourceValue}
              </p>
              <p className="break-words" style={ANYWHERE_WRAP_STYLE}>
                {firstCompareLine.targetDatasetLabel}：{firstCompareLine.targetValue}
              </p>
              {firstCompareLine.diffValue ? (
                <p className="break-words" style={ANYWHERE_WRAP_STYLE}>
                  差异值：{firstCompareLine.diffValue}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
          <span className="rounded-full border border-border bg-surface px-2.5 py-1">责任人：{ownerName}</span>
          <span className="rounded-full border border-border bg-surface px-2.5 py-1">状态：{processingStatusLabel}</span>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onOpen}
            className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border border-border bg-surface px-3 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
          >
            <Eye className="h-4 w-4" />
            查看详情
          </button>
        </div>
      </div>
    </article>
  );
}
```

- [ ] **Step 2: Run type checking to expose integration errors**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected result before integration:

```text
No TypeScript errors from the new standalone component.
```

## Task 3: Build Responsive Compare Values

**Files:**
- Create: `finance-web/src/components/recon/PublicReconExceptionCompareValues.tsx`

- [ ] **Step 1: Create the responsive compare-value component**

Create `finance-web/src/components/recon/PublicReconExceptionCompareValues.tsx` with:

```tsx
import type { ExceptionBusinessDisplay } from './exceptionBusinessSummary';

const ANYWHERE_WRAP_STYLE = { overflowWrap: 'anywhere' } as const;

export interface PublicReconExceptionCompareValuesProps {
  compareLines: ExceptionBusinessDisplay['compareLines'];
  leftDatasetLabel: string;
  rightDatasetLabel: string;
}

export default function PublicReconExceptionCompareValues({
  compareLines,
  leftDatasetLabel,
  rightDatasetLabel,
}: PublicReconExceptionCompareValuesProps) {
  if (compareLines.length === 0) return null;

  const firstLine = compareLines[0];

  return (
    <>
      <div className="mt-3 hidden overflow-x-auto rounded-xl border border-border-subtle bg-surface md:block">
        <table className="min-w-[720px] w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs text-text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">字段</th>
              <th className="px-3 py-2 font-medium">{firstLine?.sourceDatasetLabel || leftDatasetLabel}</th>
              <th className="px-3 py-2 font-medium">{firstLine?.targetDatasetLabel || rightDatasetLabel}</th>
              <th className="px-3 py-2 font-medium">差异值</th>
            </tr>
          </thead>
          <tbody>
            {compareLines.map((line, index) => (
              <tr key={`${line.fieldLabel}-${index}`} className="border-b border-border-subtle last:border-b-0">
                <td className="px-3 py-2 text-text-primary">{line.fieldLabel}</td>
                <td className="px-3 py-2 text-text-secondary">{line.sourceValue}</td>
                <td className="px-3 py-2 text-text-secondary">{line.targetValue}</td>
                <td className="px-3 py-2 text-text-secondary">{line.diffValue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div data-testid="mobile-compare-values" className="mt-3 grid gap-3 md:hidden">
        {compareLines.map((line, index) => (
          <article key={`${line.fieldLabel}-${index}`} className="rounded-xl border border-border-subtle bg-surface px-3 py-3">
            <p className="text-[11px] font-medium text-text-muted">字段</p>
            <p className="mt-1 break-words text-sm font-semibold text-text-primary" style={ANYWHERE_WRAP_STYLE}>
              {line.fieldLabel}
            </p>
            <dl className="mt-3 grid gap-2 text-sm">
              <div>
                <dt className="text-xs text-text-muted">{line.sourceDatasetLabel || leftDatasetLabel}</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words text-text-primary" style={ANYWHERE_WRAP_STYLE}>
                  {line.sourceValue}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-text-muted">{line.targetDatasetLabel || rightDatasetLabel}</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words text-text-primary" style={ANYWHERE_WRAP_STYLE}>
                  {line.targetValue}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-text-muted">差异值</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words text-text-primary" style={ANYWHERE_WRAP_STYLE}>
                  {line.diffValue || '--'}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </>
  );
}
```

- [ ] **Step 2: Run TypeScript check**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected result:

```text
No TypeScript errors from the new standalone compare component.
```

## Task 4: Integrate Mobile Components Into the Public Page

**Files:**
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`

- [ ] **Step 1: Add imports**

Add these imports after the existing `parsePublicReconRunExceptionsRunId` import:

```tsx
import PublicReconExceptionCompareValues from './recon/PublicReconExceptionCompareValues';
import PublicReconRunExceptionMobileCard from './recon/PublicReconRunExceptionMobileCard';
```

- [ ] **Step 2: Split desktop and mobile exception list rendering**

In the `filteredExceptions.length > 0` branch, replace the single desktop table wrapper:

```tsx
            <div className="overflow-x-auto">
```

with:

```tsx
            <>
              <div className="md:hidden">
                {filteredExceptions.map((item) => {
                  const businessDisplay = exceptionBusinessDisplays.get(item.id) || businessDisplayForException(item, displayContext);
                  return (
                    <PublicReconRunExceptionMobileCard
                      key={item.id}
                      id={item.id}
                      display={businessDisplay}
                      fieldSummary={fieldValueSummary(businessDisplay)}
                      ownerName={ownerDisplayName(item, bundle)}
                      processingStatusLabel={formatProcessingStatus(item.processingStatus)}
                      onOpen={() => setSelectedException(item)}
                    />
                  );
                })}
              </div>
              <div className="hidden overflow-x-auto md:block">
```

Then close the fragment immediately after the existing desktop table wrapper:

```tsx
              </div>
            </>
```

Keep the existing desktop grid columns and desktop `详情` button unchanged.

- [ ] **Step 3: Make the detail overlay full-screen only on phones**

Replace the overlay wrapper class:

```tsx
className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4 py-6"
```

with:

```tsx
className="fixed inset-0 z-50 flex items-stretch justify-stretch bg-black/30 p-0 md:items-center md:justify-center md:px-4 md:py-6"
```

Replace the dialog class:

```tsx
className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-border bg-surface shadow-2xl"
```

with:

```tsx
className="flex h-full max-h-none w-full max-w-none flex-col overflow-hidden rounded-none border-0 bg-surface shadow-2xl md:h-auto md:max-h-[90vh] md:max-w-5xl md:rounded-[28px] md:border md:border-border"
```

- [ ] **Step 4: Replace the inline compare-value table**

Replace the current `selectedBusinessDisplay.compareLines.length > 0` section body with:

```tsx
                {selectedBusinessDisplay.compareLines.length > 0 ? (
                  <section className="rounded-2xl border border-border bg-surface-secondary p-4">
                    <h3 className="text-sm font-semibold text-text-primary">差异字段和值</h3>
                    <PublicReconExceptionCompareValues
                      compareLines={selectedBusinessDisplay.compareLines}
                      leftDatasetLabel={displayContext.datasetLabels.left}
                      rightDatasetLabel={displayContext.datasetLabels.right}
                    />
                  </section>
                ) : null}
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected result:

```text
PASS tests/components/public-recon-run-exceptions-page.test.tsx
```

- [ ] **Step 6: Commit implementation**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/components/PublicReconRunExceptionsPage.tsx finance-web/src/components/recon/PublicReconExceptionCompareValues.tsx finance-web/src/components/recon/PublicReconRunExceptionMobileCard.tsx
git commit -m "feat: adapt public recon exceptions for mobile"
```

## Task 5: Verify Build, Lint, and Mobile Visual Behavior

**Files:**
- No source edits expected unless verification exposes an issue.

- [ ] **Step 1: Run component test suite for the touched area**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/public-recon-run-exceptions-page.test.tsx
```

Expected result:

```text
PASS tests/components/public-recon-run-exceptions-page.test.tsx
```

- [ ] **Step 2: Run TypeScript build check**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit
```

Expected result:

```text
No TypeScript errors.
```

- [ ] **Step 3: Run lint**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run lint
```

Expected result:

```text
No ESLint errors.
```

- [ ] **Step 4: Restart services because frontend code changed**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected result:

```text
Services start successfully and finance-web is available at http://localhost:5173
```

- [ ] **Step 5: Take desktop and mobile screenshots**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx playwright screenshot --viewport-size=390,844 http://127.0.0.1:5173/recon/runs/8e386cda-3879-4ba6-a384-1fc3fb7f840c/exceptions /private/tmp/public-recon-mobile.png
npx playwright screenshot --viewport-size=1440,1000 http://127.0.0.1:5173/recon/runs/8e386cda-3879-4ba6-a384-1fc3fb7f840c/exceptions /private/tmp/public-recon-desktop.png
```

Expected result:

```text
Mobile screenshot shows card list without whole-page horizontal overflow.
Desktop screenshot shows the original wide table layout.
```

- [ ] **Step 6: Commit verification notes only if source changes were needed**

If verification required a fix, commit only the source and test files changed by that fix:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/components/PublicReconRunExceptionsPage.tsx finance-web/src/components/recon/PublicReconExceptionCompareValues.tsx finance-web/src/components/recon/PublicReconRunExceptionMobileCard.tsx finance-web/tests/components/public-recon-run-exceptions-page.test.tsx
git commit -m "fix: polish mobile recon exception layout"
```

If verification passed without additional edits, do not create an empty commit.

## Self-Review

- Spec coverage: phone list cards are Task 2 and Task 4; phone full-screen detail is Task 4; raw source fields remain through existing `PublicRecordSection`; desktop table remains through the existing grid wrapper with `hidden md:block`; 390px and 1440px visual checks are Task 5.
- Placeholder scan: no unresolved implementation placeholders are intentionally left in this plan.
- Type consistency: `ExceptionBusinessDisplay`, `display.compareLines`, `fieldValueSummary`, `ownerDisplayName`, and `formatProcessingStatus` match the current public page and summary module APIs.
