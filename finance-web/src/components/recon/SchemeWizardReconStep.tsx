import { useEffect, useRef } from 'react';
import { ChevronDown, FlaskConical, Plus, Trash2 } from 'lucide-react';

import type { ReconFieldPairDraft } from './schemeWizardState';

type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';

export interface ReconDraftShape {
  reconTrialStatus: TrialStatus;
  reconTrialSummary: string;
}

export interface ReconFieldOption {
  value: string;
  label: string;
}

export interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed' | 'warning';
  message: string;
  details: string[];
}

export interface ReconSampleRow {
  [key: string]: string | number | null | undefined;
}

export interface ReconResultSummary {
  matched?: number;
  unmatchedLeft?: number;
  unmatchedRight?: number;
  amountDiff?: number;
  diffCount?: number;
}

export interface ReconTrialPreview {
  status: TrialStatus;
  summary: string;
  leftSamples?: ReconSampleRow[];
  rightSamples?: ReconSampleRow[];
  resultSamples?: ReconSampleRow[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
  resultFieldLabelMap?: Record<string, string>;
  resultSummary?: ReconResultSummary;
}

interface SchemeWizardReconStepProps {
  schemeDraft: ReconDraftShape;
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  leftMatchFieldOptions?: ReconFieldOption[];
  rightMatchFieldOptions?: ReconFieldOption[];
  leftCompareFieldOptions?: ReconFieldOption[];
  rightCompareFieldOptions?: ReconFieldOption[];
  leftTimeFieldOptions?: ReconFieldOption[];
  rightTimeFieldOptions?: ReconFieldOption[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
  reconCompatibility?: CompatibilityCheckResult;
  onStructuredConfigChange?: (patch: Partial<{
    reconRuleName: string;
    matchFieldPairs: ReconFieldPairDraft[];
    compareFieldPairs: ReconFieldPairDraft[];
    leftTimeSemantic: string;
    rightTimeSemantic: string;
  }>) => void;
  onTrialRecon: () => void;
  onViewReconJson: () => void;
  reconJsonPreview?: string;
  reconTrialPreview?: ReconTrialPreview;
  trialDisabled?: boolean;
  isTrialingRecon?: boolean;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function renderSampleTable(
  rows: ReconSampleRow[] | undefined,
  title: string,
  fieldLabelMap?: Record<string, string>,
) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface px-4 py-3 text-sm text-text-secondary">
        {title}暂无数据
      </div>
    );
  }

  const columns = Array.from(
    rows.reduce<Set<string>>((acc, row) => {
      Object.keys(row).forEach((key) => acc.add(key));
      return acc;
    }, new Set<string>()),
  );

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
      <div className="min-w-[680px]">
        <div className="border-b border-border-subtle px-4 py-2 text-xs font-semibold tracking-[0.16em] text-text-muted">
          {title}
        </div>
        <table className="w-full text-left text-sm text-text-secondary">
          <thead className="text-[11px] uppercase tracking-[0.14em] text-text-muted">
            <tr>
              {columns.map((col) => (
                <th key={col} className="px-4 py-2 font-semibold">
                  <span className="block max-w-[220px] truncate">{fieldLabelMap?.[col] || col}</span>
                  {fieldLabelMap?.[col] && fieldLabelMap[col] !== col ? (
                    <span className="mt-0.5 block max-w-[220px] truncate text-[10px] font-normal normal-case tracking-normal text-text-muted">
                      {col}
                    </span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${title}-${index}`} className="border-t border-border-subtle">
                {columns.map((col) => (
                  <td key={`${title}-${index}-${col}`} className="px-4 py-2">
                    {row[col] ?? '--'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SelectField({
  value,
  options,
  onChange,
  placeholder,
}: {
  value: string;
  options: ReconFieldOption[];
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-9 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
    </div>
  );
}

function fieldDisplayName(fieldName: string, fieldLabelMap?: Record<string, string>): string {
  const normalized = fieldName.trim();
  if (!normalized) return '';
  return fieldLabelMap?.[normalized] || normalized;
}

function createReconPairDraft(seed: Partial<Pick<ReconFieldPairDraft, 'leftField' | 'rightField'>> = {}): ReconFieldPairDraft {
  return {
    id: `recon_pair_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    leftField: seed.leftField || '',
    rightField: seed.rightField || '',
  };
}

function ensureEditablePairs(pairs: ReconFieldPairDraft[]): ReconFieldPairDraft[] {
  return pairs.length > 0 ? pairs : [createReconPairDraft()];
}

function FieldPairEditorSection({
  title,
  description,
  pairs,
  leftOptions,
  rightOptions,
  leftFieldLabelMap,
  rightFieldLabelMap,
  onChange,
}: {
  title: string;
  description: string;
  pairs: ReconFieldPairDraft[];
  leftOptions: ReconFieldOption[];
  rightOptions: ReconFieldOption[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
  onChange: (pairs: ReconFieldPairDraft[]) => void;
}) {
  const editablePairs = ensureEditablePairs(pairs);

  const updatePair = (id: string, patch: Partial<Pick<ReconFieldPairDraft, 'leftField' | 'rightField'>>) => {
    onChange(editablePairs.map((pair) => (pair.id === id ? { ...pair, ...patch } : pair)));
  };

  const removePair = (id: string) => {
    const nextPairs = editablePairs.filter((pair) => pair.id !== id);
    onChange(nextPairs.length > 0 ? nextPairs : [createReconPairDraft()]);
  };

  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => onChange([...editablePairs, createReconPairDraft()])}
          className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
        >
          <Plus className="h-3.5 w-3.5" />
          新增字段对
        </button>
      </div>

      <div className="mt-4 space-y-3">
        {editablePairs.map((pair, index) => (
          <div key={pair.id} className="grid gap-2 rounded-2xl border border-border-subtle bg-surface-secondary p-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] lg:items-center">
            <SelectField
              value={pair.leftField}
              options={leftOptions}
              onChange={(value) => updatePair(pair.id, { leftField: value })}
              placeholder="选择左侧字段"
            />
            <span className="hidden text-xs font-medium text-text-muted lg:block">↔</span>
            <SelectField
              value={pair.rightField}
              options={rightOptions}
              onChange={(value) => updatePair(pair.id, { rightField: value })}
              placeholder="选择右侧字段"
            />
            <button
              type="button"
              onClick={() => removePair(pair.id)}
              disabled={editablePairs.length === 1 && !pair.leftField && !pair.rightField}
              className="inline-flex items-center justify-center gap-1 rounded-xl border border-border bg-surface px-3 py-2 text-xs font-medium text-text-secondary transition hover:border-red-200 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除
            </button>
            <p className="text-[11px] leading-5 text-text-muted lg:col-span-4">
              字段对 {index + 1}：{fieldDisplayName(pair.leftField, leftFieldLabelMap) || '未选左侧字段'} ↔ {fieldDisplayName(pair.rightField, rightFieldLabelMap) || '未选右侧字段'}
            </p>
          </div>
        ))}
        {leftOptions.length === 0 || rightOptions.length === 0 ? (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
            第二步尚未生成可选字段，请先回到数据整理步骤补充字段角色。
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default function SchemeWizardReconStep({
  schemeDraft,
  reconRuleName,
  matchFieldPairs = [],
  compareFieldPairs = [],
  leftTimeSemantic,
  rightTimeSemantic,
  leftMatchFieldOptions = [],
  rightMatchFieldOptions = [],
  leftCompareFieldOptions = [],
  rightCompareFieldOptions = [],
  leftTimeFieldOptions = [],
  rightTimeFieldOptions = [],
  leftFieldLabelMap,
  rightFieldLabelMap,
  reconCompatibility,
  onStructuredConfigChange,
  onTrialRecon,
  onViewReconJson,
  reconJsonPreview,
  reconTrialPreview,
  trialDisabled,
  isTrialingRecon = false,
}: SchemeWizardReconStepProps) {
  const previewAnchorRef = useRef<HTMLDivElement | null>(null);
  const scrollToPreviewPendingRef = useRef(false);
  const preview = reconTrialPreview;
  const showTrialResult = schemeDraft.reconTrialStatus !== 'idle' || Boolean(preview?.summary);
  const compatibility = reconCompatibility;
  const showCompatibility =
    (compatibility?.status || 'idle') !== 'idle'
    || (compatibility?.details.length || 0) > 0
    || (compatibility?.message || '等待校验') !== '等待校验';

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

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">对账规则配置</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          匹配字段和对比字段默认沿用第二步已配置的字段角色，也可以在这里调整字段对。当前对账逻辑将保存为
          <span className="mx-1 font-medium text-text-primary">{reconRuleName}</span>
          。
        </p>

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

        {showCompatibility ? (
          <div
            className={cn(
              'mt-4 rounded-2xl border px-4 py-3 text-sm',
              compatibility?.status === 'passed'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : compatibility?.status === 'warning'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : compatibility?.status === 'failed'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : 'border-border bg-surface text-text-secondary',
            )}
          >
            <p>{compatibility?.message || '等待校验'}</p>
            {compatibility?.details.length ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {compatibility.details.map((detail: string) => (
                  <span
                    key={detail}
                    className="rounded-full border border-current/15 bg-white/70 px-2.5 py-1 text-xs"
                  >
                    {detail}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <FieldPairEditorSection
        title="匹配字段"
        description="用于左右记录对齐，可配置一组或多组联合匹配字段。"
        pairs={matchFieldPairs}
        leftOptions={leftMatchFieldOptions}
        rightOptions={rightMatchFieldOptions}
        leftFieldLabelMap={leftFieldLabelMap}
        rightFieldLabelMap={rightFieldLabelMap}
        onChange={(pairs) => onStructuredConfigChange?.({ matchFieldPairs: pairs })}
      />

      <FieldPairEditorSection
        title="对比字段"
        description="用于比较左右金额或数量等指标，可配置多组对比字段。"
        pairs={compareFieldPairs}
        leftOptions={leftCompareFieldOptions}
        rightOptions={rightCompareFieldOptions}
        leftFieldLabelMap={leftFieldLabelMap}
        rightFieldLabelMap={rightFieldLabelMap}
        onChange={(pairs) => onStructuredConfigChange?.({ compareFieldPairs: pairs })}
      />

      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">时间字段</p>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <label className="block">
            <span className="text-xs font-medium text-text-secondary">左时间字段</span>
            <div className="mt-1.5">
              <SelectField
                value={leftTimeSemantic}
                options={leftTimeFieldOptions}
                onChange={(value) => onStructuredConfigChange?.({ leftTimeSemantic: value })}
                placeholder="暂不配置"
              />
            </div>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-text-secondary">右时间字段</span>
            <div className="mt-1.5">
              <SelectField
                value={rightTimeSemantic}
                options={rightTimeFieldOptions}
                onChange={(value) => onStructuredConfigChange?.({ rightTimeSemantic: value })}
                placeholder="暂不配置"
              />
            </div>
          </label>
        </div>
      </div>

      {isTrialingRecon ? (
        <div className="flex items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50/60 px-5 py-4">
          <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
          <span className="text-sm font-medium text-sky-700">正在试跑对账规则，请稍候…</span>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleTrialRecon}
          disabled={trialDisabled || isTrialingRecon}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <FlaskConical className="h-4 w-4" />
          试跑验证
        </button>
        <button
          type="button"
          onClick={onViewReconJson}
          disabled={!reconJsonPreview || isTrialingRecon}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          查看 JSON
        </button>
        {reconJsonPreview ? (
          <span className="text-xs text-text-muted">当前字段配置已可编译为 JSON</span>
        ) : null}
      </div>

      {showTrialResult ? (
        <div ref={previewAnchorRef} className="space-y-4">
          {renderSampleTable(preview?.leftSamples, '左侧整理结果抽样', preview?.leftFieldLabelMap)}
          {renderSampleTable(preview?.rightSamples, '右侧整理结果抽样', preview?.rightFieldLabelMap)}

          <div className="rounded-3xl border border-border bg-surface-secondary p-4">
            <p className="text-sm font-semibold text-text-primary">对账结果摘要</p>
            {preview?.resultSummary ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-border bg-surface px-4 py-3">
                  <p className="text-xs text-text-secondary">匹配成功</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {preview.resultSummary.matched ?? '--'}
                  </p>
                </div>
                <div className="rounded-2xl border border-border bg-surface px-4 py-3">
                  <p className="text-xs text-text-secondary">左侧缺失</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {preview.resultSummary.unmatchedLeft ?? '--'}
                  </p>
                </div>
                <div className="rounded-2xl border border-border bg-surface px-4 py-3">
                  <p className="text-xs text-text-secondary">右侧缺失</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {preview.resultSummary.unmatchedRight ?? '--'}
                  </p>
                </div>
                <div className="rounded-2xl border border-border bg-surface px-4 py-3">
                  <p className="text-xs text-text-secondary">差异记录</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {preview.resultSummary.amountDiff ?? preview.resultSummary.diffCount ?? '--'}
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-text-secondary">
                试跑结果摘要会在这里展示匹配成功、差异和缺失情况。
              </p>
            )}
          </div>

          {renderSampleTable(preview?.resultSamples, '对账差异抽样', preview?.resultFieldLabelMap)}
        </div>
      ) : null}
    </div>
  );
}
