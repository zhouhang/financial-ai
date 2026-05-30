# Recon Wizard Step 3 Trial Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the visible Step 3 `recon` trial flow from the new reconciliation scheme wizard and replace save gating with deterministic structure validation.

**Architecture:** Add a small pure validation helper beside the wizard components, then wire `ReconWorkspace` save behavior to that helper instead of `trialReconDraft()`. Keep Step 2 `proc` trial unchanged because Step 3 depends on prepared left/right output fields.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Playwright E2E.

---

## File Structure

- Create `finance-web/src/components/recon/reconStructureValidation.ts`
  - Owns Step 3 save-time structure validation and the `structure_checked` metadata constants.
  - Has no React dependency.
- Create `finance-web/tests/components/recon-structure-validation.spec.ts`
  - Unit tests for the pure helper.
- Modify `finance-web/src/components/recon/SchemeWizardReconStep.tsx`
  - Remove visible `recon` trial button, loading state, and sample result rendering.
  - Keep structured field editors, compatibility messages, and JSON view.
- Modify `finance-web/tests/components/recon-fallback-warning.spec.tsx`
  - Update props after trial UI props are removed.
  - Add coverage that Step 3 no longer renders `试跑验证` or sample result sections.
- Modify `finance-web/src/components/ReconWorkspace.tsx`
  - Import the structure helper.
  - Remove save-time `trialReconDraft()` gate.
  - Validate current Step 3 structure before saving.
  - Persist `validation_summary.recon.status = "structure_checked"`.
  - Remove unused Step 3 trial preview plumbing after the UI no longer consumes it.
- Modify `finance-web/tests/e2e/recon-center.spec.ts`
  - Stop clicking Step 3 `试跑验证`.
  - Assert the real-run validation save confirmation copy instead.
- Existing scripts used for verification:
  - `cd finance-web && npx vitest run tests/components/recon-structure-validation.spec.ts tests/components/recon-fallback-warning.spec.tsx`
  - `cd finance-web && npx tsc --noEmit --pretty false`
  - `cd finance-web && npm run build`

---

### Task 1: Add Pure Recon Structure Validation

**Files:**
- Create: `finance-web/src/components/recon/reconStructureValidation.ts`
- Create: `finance-web/tests/components/recon-structure-validation.spec.ts`

- [ ] **Step 1: Write the failing helper tests**

Create `finance-web/tests/components/recon-structure-validation.spec.ts` with:

```ts
import { describe, expect, it } from 'vitest';

import {
  RECON_STRUCTURE_CHECK_STATUS,
  RECON_STRUCTURE_CHECK_SUMMARY,
  validateReconStructureForSave,
} from '../../src/components/recon/reconStructureValidation';
import type { OutputFieldDraft, ReconFieldPairDraft } from '../../src/components/recon/schemeWizardState';

function outputField(outputName: string): OutputFieldDraft {
  return {
    id: `field-${outputName}`,
    outputName,
    semanticRole: 'normal',
    valueMode: 'source_field',
    sourceDatasetId: '',
    sourceField: '',
    fixedValue: '',
    formula: '',
    concatDelimiter: '',
    concatParts: [],
  };
}

function pair(id: string, leftField: string, rightField: string): ReconFieldPairDraft {
  return { id, leftField, rightField };
}

const validRule = { schema_version: '1.6', rules: [] };
const leftFields = [outputField('biz_key'), outputField('amount')];
const rightFields = [outputField('biz_key'), outputField('amount')];

describe('validateReconStructureForSave', () => {
  it('passes when recon JSON and complete field pairs match output fields', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result).toEqual({
      ok: true,
      status: RECON_STRUCTURE_CHECK_STATUS,
      message: RECON_STRUCTURE_CHECK_SUMMARY,
      details: [],
    });
  });

  it('fails when recon JSON is missing', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: null,
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result.ok).toBe(false);
    expect(result.message).toBe('请先完成对账字段配置，生成可保存的对账规则 JSON。');
  });

  it('fails when no complete match pair exists', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', '')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result.ok).toBe(false);
    expect(result.message).toBe('请至少配置一组完整的匹配字段。');
  });

  it('fails when no complete compare pair exists', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', '', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result.ok).toBe(false);
    expect(result.message).toBe('请至少配置一组完整的对比字段。');
  });

  it('fails when a left field is not in the prepared left output fields', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'missing_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
      leftFieldLabelMap: { missing_key: '缺失业务单号' },
    });

    expect(result.ok).toBe(false);
    expect(result.message).toBe('对账规则字段不存在: 左侧字段「缺失业务单号」不在第二步输出字段中。');
    expect(result.details).toEqual(['左侧字段「缺失业务单号」不在第二步输出字段中。']);
  });

  it('fails when a right field is not in the prepared right output fields', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', 'missing_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
      rightFieldLabelMap: { missing_key: '缺失平台单号' },
    });

    expect(result.ok).toBe(false);
    expect(result.message).toBe('对账规则字段不存在: 右侧字段「缺失平台单号」不在第二步输出字段中。');
    expect(result.details).toEqual(['右侧字段「缺失平台单号」不在第二步输出字段中。']);
  });
});
```

- [ ] **Step 2: Run the helper tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-structure-validation.spec.ts
```

Expected: FAIL because `../../src/components/recon/reconStructureValidation` does not exist.

- [ ] **Step 3: Implement the helper**

Create `finance-web/src/components/recon/reconStructureValidation.ts` with:

```ts
import type { OutputFieldDraft, ReconFieldPairDraft } from './schemeWizardState';

export const RECON_STRUCTURE_CHECK_STATUS = 'structure_checked';
export const RECON_STRUCTURE_CHECK_SUMMARY = '已完成对账规则结构校验，待首次真实运行验证';

export interface ReconStructureValidationInput {
  reconRuleJson: Record<string, unknown> | null | undefined;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
}

export interface ReconStructureValidationResult {
  ok: boolean;
  status: typeof RECON_STRUCTURE_CHECK_STATUS | 'failed';
  message: string;
  details: string[];
}

function completePairs(pairs: ReconFieldPairDraft[]): ReconFieldPairDraft[] {
  return pairs.filter((pair) => pair.leftField.trim() && pair.rightField.trim());
}

function outputFieldNameSet(fields: OutputFieldDraft[]): Set<string> {
  return new Set(fields.map((field) => field.outputName.trim()).filter(Boolean));
}

function displayFieldName(fieldName: string, labelMap: Record<string, string> | undefined): string {
  const normalized = fieldName.trim();
  return labelMap?.[normalized]?.trim() || normalized;
}

function missingFieldMessage(sideLabel: string, fieldName: string): string {
  return `${sideLabel}字段「${fieldName}」不在第二步输出字段中。`;
}

export function validateReconStructureForSave(
  input: ReconStructureValidationInput,
): ReconStructureValidationResult {
  if (!input.reconRuleJson || Object.keys(input.reconRuleJson).length === 0) {
    return {
      ok: false,
      status: 'failed',
      message: '请先完成对账字段配置，生成可保存的对账规则 JSON。',
      details: [],
    };
  }

  const completeMatchPairs = completePairs(input.matchFieldPairs);
  if (completeMatchPairs.length === 0) {
    return {
      ok: false,
      status: 'failed',
      message: '请至少配置一组完整的匹配字段。',
      details: [],
    };
  }

  const completeComparePairs = completePairs(input.compareFieldPairs);
  if (completeComparePairs.length === 0) {
    return {
      ok: false,
      status: 'failed',
      message: '请至少配置一组完整的对比字段。',
      details: [],
    };
  }

  const leftOutputNames = outputFieldNameSet(input.leftOutputFields);
  const rightOutputNames = outputFieldNameSet(input.rightOutputFields);
  const allPairs = [...completeMatchPairs, ...completeComparePairs];
  const details: string[] = [];

  allPairs.forEach((pair) => {
    const leftField = pair.leftField.trim();
    const rightField = pair.rightField.trim();
    if (!leftOutputNames.has(leftField)) {
      details.push(missingFieldMessage('左侧', displayFieldName(leftField, input.leftFieldLabelMap)));
    }
    if (!rightOutputNames.has(rightField)) {
      details.push(missingFieldMessage('右侧', displayFieldName(rightField, input.rightFieldLabelMap)));
    }
  });

  const uniqueDetails = Array.from(new Set(details));
  if (uniqueDetails.length > 0) {
    return {
      ok: false,
      status: 'failed',
      message: `对账规则字段不存在: ${uniqueDetails[0]}`,
      details: uniqueDetails,
    };
  }

  return {
    ok: true,
    status: RECON_STRUCTURE_CHECK_STATUS,
    message: RECON_STRUCTURE_CHECK_SUMMARY,
    details: [],
  };
}
```

- [ ] **Step 4: Run the helper tests and verify they pass**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-structure-validation.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/components/recon/reconStructureValidation.ts finance-web/tests/components/recon-structure-validation.spec.ts
git commit -m "test: add recon structure save validation"
```

Expected: Commit succeeds.

---

### Task 2: Remove Step 3 Trial UI

**Files:**
- Modify: `finance-web/src/components/recon/SchemeWizardReconStep.tsx`
- Modify: `finance-web/tests/components/recon-fallback-warning.spec.tsx`

- [ ] **Step 1: Update component tests first**

Edit `finance-web/tests/components/recon-fallback-warning.spec.tsx`:

1. Remove every `onTrialRecon={vi.fn()}` prop from `SchemeWizardReconStep`.
2. Replace the second test's fallback warning text so it no longer tells users to retry trial:

```ts
reconCompatibility={{
  status: 'warning',
  message: '对账规则生成失败，已回退为兜底规则，请重点检查字段配置。',
  details: ['mock recon fallback'],
}}
```

3. Replace the matching expectation with:

```ts
expect(screen.getAllByText('对账规则生成失败，已回退为兜底规则，请重点检查字段配置。').length).toBeGreaterThan(0);
```

4. Add this new test inside the existing `describe('对账方案 warning 展示', () => { ... })` block:

```ts
it('第3步不再展示手动试跑入口和样例结果区', () => {
  render(
    <SchemeWizardReconStep
      schemeDraft={{
        reconTrialStatus: 'passed',
        reconTrialSummary: '历史试跑结果不再作为第三步主路径展示',
      }}
      reconRuleName="订单对账逻辑"
      matchFieldPairs={[{ id: 'match-1', leftField: 'biz_key', rightField: 'biz_key' }]}
      compareFieldPairs={[{ id: 'compare-1', leftField: 'amount', rightField: 'amount' }]}
      leftMatchFieldOptions={[{ value: 'biz_key', label: '客户订单号' }]}
      rightMatchFieldOptions={[{ value: 'biz_key', label: '商户订单号' }]}
      leftCompareFieldOptions={[{ value: 'amount', label: '含税销售金额' }]}
      rightCompareFieldOptions={[{ value: 'amount', label: '订单金额' }]}
      leftFieldLabelMap={{ biz_key: '客户订单号', amount: '含税销售金额' }}
      rightFieldLabelMap={{ biz_key: '商户订单号', amount: '订单金额' }}
      onStructuredConfigChange={vi.fn()}
      onViewReconJson={vi.fn()}
      reconJsonPreview='{"rules":[]}'
    />,
  );

  expect(screen.queryByRole('button', { name: '试跑验证' })).not.toBeInTheDocument();
  expect(screen.queryByText('正在试跑对账规则，请稍候…')).not.toBeInTheDocument();
  expect(screen.queryByText('对账结果摘要')).not.toBeInTheDocument();
  expect(screen.queryByText('对账差异')).not.toBeInTheDocument();
  expect(screen.queryByText('历史试跑结果不再作为第三步主路径展示')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查看 JSON' })).toBeEnabled();
});
```

- [ ] **Step 2: Run the component tests and verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-fallback-warning.spec.tsx
```

Expected: FAIL because `SchemeWizardReconStep` still requires `onTrialRecon` and still renders the trial UI.

- [ ] **Step 3: Remove trial UI dependencies from the component**

Edit `finance-web/src/components/recon/SchemeWizardReconStep.tsx`:

1. Change imports from:

```ts
import { useEffect, useRef } from 'react';
import { ChevronDown, FlaskConical, Plus, Trash2 } from 'lucide-react';
```

to:

```ts
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
```

2. In `SchemeWizardReconStepProps`, remove these props:

```ts
  onTrialRecon: () => void;
  reconTrialPreview?: ReconTrialPreview;
  trialDisabled?: boolean;
  isTrialingRecon?: boolean;
```

3. In the component parameter list, remove:

```ts
  onTrialRecon,
  reconTrialPreview,
  trialDisabled,
  isTrialingRecon = false,
```

4. Remove these local variables and effect:

```ts
  const previewAnchorRef = useRef<HTMLDivElement | null>(null);
  const scrollToPreviewPendingRef = useRef(false);
  const preview = reconTrialPreview;
  const showTrialResult = schemeDraft.reconTrialStatus !== 'idle' || Boolean(preview?.summary);
```

```ts
  useEffect(() => {
    if (!scrollToPreviewPendingRef.current || !showTrialResult) {
      return;
    }
    previewAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    scrollToPreviewPendingRef.current = false;
  }, [showTrialResult]);

  const handleTrialRecon = () => {
    scrollToPreviewPendingRef.current = true;
    onTrialRecon();
  };
```

5. Remove the entire trial result banner block:

```tsx
        {showTrialResult ? (
          <div
            className={cn(
              'mt-4 rounded-2xl border px-4 py-3 text-sm',
              (preview?.status || schemeDraft.reconTrialStatus) === 'passed'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : (preview?.status || schemeDraft.reconTrialStatus) === 'needs_adjustment'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : 'border-border bg-surface text-text-secondary',
            )}
          >
            <p>{preview?.summary || schemeDraft.reconTrialSummary}</p>
          </div>
        ) : null}
```

6. Remove the loading block:

```tsx
      {isTrialingRecon ? (
        <div className="flex items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50/60 px-5 py-4">
          <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
          <span className="text-sm font-medium text-sky-700">正在试跑对账规则，请稍候…</span>
        </div>
      ) : null}
```

7. In the action buttons block, remove the `试跑验证` button and change the JSON button disabled expression from:

```tsx
disabled={!reconJsonPreview || isTrialingRecon}
```

to:

```tsx
disabled={!reconJsonPreview}
```

8. Remove the whole sample preview block that starts with:

```tsx
      {showTrialResult ? (
        <div ref={previewAnchorRef} className="space-y-4">
```

and ends with:

```tsx
          {renderSampleTable(preview?.resultSamples, '对账差异', preview?.resultFieldLabelMap, { showCount: false })}
        </div>
      ) : null}
```

9. Keep `renderSampleTable` and exported preview interfaces only until Task 3. Task 3 removes unused workspace preview plumbing after TypeScript shows which declarations are unused.

- [ ] **Step 4: Run the component tests and verify they pass**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-fallback-warning.spec.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/components/recon/SchemeWizardReconStep.tsx finance-web/tests/components/recon-fallback-warning.spec.tsx
git commit -m "fix: remove recon wizard trial UI"
```

Expected: Commit succeeds.

---

### Task 3: Replace Save-Time Recon Trial With Structure Check

**Files:**
- Modify: `finance-web/src/components/ReconWorkspace.tsx`
- Modify: `finance-web/tests/e2e/recon-center.spec.ts`

- [ ] **Step 1: Update E2E expectations before implementation**

Edit both scheme creation flows in `finance-web/tests/e2e/recon-center.spec.ts`.

In the first flow, replace this block:

```ts
  await page.getByRole('button', { name: '试跑验证' }).click();
  await waitForOptionalStatus(page, 'AI 正在试跑数据对账，请稍候…', 120_000);
  await expect(page.getByText('对账结果摘要')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: '下一步' }).click();

  await expect(page.getByText('确认保存前，再看一遍当前方案')).toBeVisible();
  await expect(page.getByText('当前整理配置和对账规则都已试跑通过，可以保存方案。')).toBeVisible();
  await page.getByRole('button', { name: '保存方案' }).click();
```

with:

```ts
  await expect(page.getByRole('button', { name: '试跑验证' })).toHaveCount(0);
  await expect(page.getByText('对账结果摘要')).toHaveCount(0);

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('当前方案已完成规则结构校验');
    expect(dialog.message()).toContain('首次真实运行后查看异常结果');
    await dialog.accept();
  });
  await page.getByRole('button', { name: '保存方案' }).click();
```

In the second flow, replace this block:

```ts
  console.log('Step 3 trial recon start');
  await page.getByRole('button', { name: '试跑验证' }).click();
  await waitForOptionalStatus(page, 'AI 正在试跑数据对账，请稍候…', 120_000);
  await expect(page.getByText('对账结果摘要')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: '下一步' })).toBeEnabled();
  console.log('Step 3 trial recon done');

  await page.getByRole('button', { name: '下一步' }).click();
  await expect(page.getByText('确认保存前，再看一遍当前方案')).toBeVisible();
  await expect(page.getByText('当前整理配置和对账规则都已试跑通过，可以保存方案。')).toBeVisible();
  await page.getByRole('button', { name: '保存方案' }).click();
```

with:

```ts
  console.log('Step 3 recon structure check ready');
  await expect(page.getByRole('button', { name: '试跑验证' })).toHaveCount(0);
  await expect(page.getByText('对账结果摘要')).toHaveCount(0);

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('当前方案已完成规则结构校验');
    expect(dialog.message()).toContain('首次真实运行后查看异常结果');
    await dialog.accept();
  });
  await page.getByRole('button', { name: '保存方案' }).click();
```

- [ ] **Step 2: Run the focused component tests and TypeScript to expose current failures**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-structure-validation.spec.ts tests/components/recon-fallback-warning.spec.tsx
npx tsc --noEmit --pretty false
```

Expected before implementation: TypeScript FAIL because `ReconWorkspace` still passes removed `SchemeWizardReconStep` props.

- [ ] **Step 3: Import the structure validator in `ReconWorkspace.tsx`**

Add this import near the other `./recon/...` imports:

```ts
import {
  RECON_STRUCTURE_CHECK_STATUS,
  RECON_STRUCTURE_CHECK_SUMMARY,
  validateReconStructureForSave,
} from './recon/reconStructureValidation';
```

- [ ] **Step 4: Remove Step 3 trial preview render plumbing**

In `renderSchemeWizardContent`, delete the `mappedReconTrialPreview` constant:

```ts
    const mappedReconTrialPreview = reconTrialPreview
      ? {
          status: reconTrialPreview.status,
          summary: reconTrialPreview.summary,
          leftSamples: reconTrialPreview.leftRows,
          rightSamples: reconTrialPreview.rightRows,
          leftFieldLabelMap: reconTrialPreview.leftFieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
          rightFieldLabelMap: reconTrialPreview.rightFieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
          resultSamples: reconTrialPreview.results.map((item) => ({
            match_fields: item.matchFields,
            left_compare_fields: item.leftCompareFields,
            right_compare_fields: item.rightCompareFields,
            result: item.result,
          })),
          resultFieldLabelMap: reconTrialPreview.resultFieldLabelMap || RECON_RESULT_FIELD_LABEL_MAP,
          resultSummary: reconTrialPreview.resultSummary,
        }
      : undefined;
```

In the `SchemeWizardReconStep` JSX, remove these props:

```tsx
            onTrialRecon={trialReconDraft}
            reconTrialPreview={mappedReconTrialPreview}
            trialDisabled={
              isTrialingRecon
              || !schemeDraft.procRuleJson
              || schemeDraft.procTrialStatus !== 'passed'
              || !compiledReconRuleResult.json
            }
            isTrialingRecon={isTrialingRecon}
```

- [ ] **Step 5: Remove save-time `trialReconDraft()` gate**

In `handleCreateScheme`, replace:

```ts
    if (!compiledReconRuleResult.json && !schemeDraft.reconRuleJson) {
      setModalError(compiledReconRuleResult.error || '请先生成并验证数据对账逻辑。');
      return;
    }
```

with:

```ts
    if (!compiledReconRuleResult.json && !schemeDraft.reconRuleJson) {
      setModalError(compiledReconRuleResult.error || '请先完成对账字段配置。');
      return;
    }
```

Then replace this whole block:

```ts
    if (schemeDraft.reconTrialStatus !== 'passed') {
      const passed = await trialReconDraft();
      if (!passed) {
        setModalError('数据对账试跑未通过，请调整逻辑后重试。');
        return;
      }
      effectiveReconRuleJson = schemeDraft.reconRuleJson || compiledReconRuleResult.json;
      if (!effectiveReconRuleJson) {
        setModalError('数据对账试跑完成后，仍未生成可保存的对账逻辑。');
        return;
      }
      effectiveReconRuleJson = stripReconTimeSemantics(effectiveReconRuleJson);
    }

    if (!window.confirm('确认当前规则、字段映射和试跑结果都已检查完毕，立即保存方案吗？')) {
      return;
    }
```

with:

```ts
    const reconStructureValidation = validateReconStructureForSave({
      reconRuleJson: effectiveReconRuleJson,
      matchFieldPairs: activeMatchFieldPairs,
      compareFieldPairs: activeCompareFieldPairs,
      leftOutputFields: activeLeftOutputFields,
      rightOutputFields: activeRightOutputFields,
      leftFieldLabelMap: leftOutputFieldLabelMap,
      rightFieldLabelMap: rightOutputFieldLabelMap,
    });
    if (!reconStructureValidation.ok) {
      setModalError(reconStructureValidation.message);
      setReconCompatibility({
        status: 'failed',
        message: reconStructureValidation.message,
        details: reconStructureValidation.details,
      });
      return;
    }

    if (!window.confirm('当前方案已完成规则结构校验。样例数据不作为对账结果依据，请在首次真实运行后查看异常结果并修正。确认保存方案吗？')) {
      return;
    }
```

- [ ] **Step 6: Persist structure check metadata**

In the save payload's `validation_summary.recon`, replace:

```ts
              recon: {
                status: schemePayloadDraft.scheme_meta_json.recon_trial_status,
                summary: schemePayloadDraft.scheme_meta_json.recon_trial_summary,
              },
```

with:

```ts
              recon: {
                status: RECON_STRUCTURE_CHECK_STATUS,
                summary: RECON_STRUCTURE_CHECK_SUMMARY,
              },
```

Replace:

```ts
            recon_trial_status: schemePayloadDraft.scheme_meta_json.recon_trial_status,
            recon_trial_summary: schemePayloadDraft.scheme_meta_json.recon_trial_summary,
```

with:

```ts
            recon_trial_status: RECON_STRUCTURE_CHECK_STATUS,
            recon_trial_summary: RECON_STRUCTURE_CHECK_SUMMARY,
```

- [ ] **Step 7: Update dependencies for `handleCreateScheme`**

In the dependency array for `handleCreateScheme`, add:

```ts
    activeCompareFieldPairs,
    activeLeftOutputFields,
    activeMatchFieldPairs,
    activeRightOutputFields,
```

Remove:

```ts
    trialReconDraft,
```

Keep the existing label-map dependencies because the structure validator uses both maps.

- [ ] **Step 8: Remove unused Step 3 trial state and helper code if TypeScript reports it**

Run `npx tsc --noEmit --pretty false` after Steps 3-7. If TypeScript reports unused declarations created by removing the visible trial flow, remove the exact reported declarations from `finance-web/src/components/ReconWorkspace.tsx`.

The most likely removals are:

```ts
const [isTrialingRecon, setIsTrialingRecon] = useState(false);
```

and references to `isTrialingRecon` in:

```ts
const isSchemeWizardBusy =
  isTrialingProc || isTrialingRecon || aiProcGenerationBusy;
```

which should become:

```ts
const isSchemeWizardBusy =
  isTrialingProc || aiProcGenerationBusy;
```

If `trialReconDraft` becomes unused, remove the complete `const trialReconDraft = useCallback(async (): Promise<boolean> => { ... }, [...]);` block. When removing it, also remove helpers and types that TypeScript reports as unused only because `trialReconDraft` was removed, such as:

```ts
interface ReconResultRow { ... }
interface ReconTrialPreview { ... }
const RECON_RESULT_FIELD_LABEL_MAP = { ... };
function markReconTrialPreviewAsReference(...) { ... }
function resolveReconOnlyResultDatasetLabel(...) { ... }
function formatPreviewFieldValueSummary(...) { ... }
function buildReconResultFieldLabelMap(...) { ... }
const buildReconPreviewFromTrial = useCallback(...);
const [reconTrialPreview, setReconTrialPreview] = useState<ReconTrialPreview | null>(null);
```

Keep `setReconCompatibility(...)` and compatibility display behavior. When `handleReconDraftMutation` no longer has `reconTrialPreview`, simplify it to clear stale compatibility without saying "请重新试跑":

```ts
  const handleReconDraftMutation = useCallback(
    (
      updater: (prev: SchemeWizardDraftState) => SchemeWizardDraftState,
    ) => {
      setWizardDraftState((prev) => {
        const next = updater(prev);
        return updateDerivedDraft(next, {
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
          reconPreviewState: 'empty',
        });
      });
      setWizardJsonPanel(null);
      setWizardProcJsonView('proc');
      setWizardReconJsonView('recon');
      setReconCompatibility(emptyCompatibilityResult());
    },
    [setReconCompatibility],
  );
```

If TypeScript reports removed imports from `SchemeWizardReconStep.tsx`, delete the unused imported names rather than suppressing errors.

- [ ] **Step 9: Run focused checks**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-structure-validation.spec.ts tests/components/recon-fallback-warning.spec.tsx
npx tsc --noEmit --pretty false
```

Expected: PASS.

- [ ] **Step 10: Run the production build**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run build
```

Expected: PASS.

- [ ] **Step 11: Commit Task 3**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/components/ReconWorkspace.tsx finance-web/tests/e2e/recon-center.spec.ts
git commit -m "fix: save recon wizard with structure validation"
```

Expected: Commit succeeds.

---

## Final Verification

- [ ] **Run component tests**

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx vitest run tests/components/recon-structure-validation.spec.ts tests/components/recon-fallback-warning.spec.tsx
```

Expected: PASS.

- [ ] **Run TypeScript check**

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npx tsc --noEmit --pretty false
```

Expected: PASS.

- [ ] **Run production build**

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run build
```

Expected: PASS.

- [ ] **Restart services because finance-web code changed**

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: services restart and `finance-web` is reachable at `http://localhost:5173`.

---

## Self-Review

Spec coverage:

1. Third step removes visible `recon` trial: Task 2 removes the button, loading state, and sample result sections.
2. Save no longer requires `reconTrialStatus === "passed"`: Task 3 removes the save-time `trialReconDraft()` gate.
3. Save still blocks structure issues: Task 1 defines the helper, Task 3 wires it into `handleCreateScheme`.
4. Sample no-match does not block save: Task 3 never calls `/recon/trial`.
5. Metadata no longer claims sample trial passed: Task 3 writes `structure_checked`.
6. Large-file discipline: Task 1 adds a focused helper instead of adding validation responsibilities to `ReconWorkspace.tsx`.

Placeholder scan:

1. No placeholder-marker instructions are present.
2. Code-bearing steps include concrete code or exact replacement snippets.
3. Verification commands include expected outcomes.

Type consistency:

1. `RECON_STRUCTURE_CHECK_STATUS` is the same constant used in helper tests and save payload.
2. `validateReconStructureForSave` consumes `OutputFieldDraft[]` and `ReconFieldPairDraft[]`, matching current wizard state types.
3. The plan keeps old `TrialStatus` unchanged and writes `structure_checked` only in the save payload metadata.
