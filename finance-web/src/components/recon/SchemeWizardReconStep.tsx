import { ChevronDown, Plus, Trash2 } from 'lucide-react';

import type { ReconFieldPairDraft } from './schemeWizardState';

export interface ReconFieldOption {
  value: string;
  label: string;
}

export interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed' | 'warning';
  message: string;
  details: string[];
}

interface SchemeWizardReconStepProps {
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  leftMatchFieldOptions?: ReconFieldOption[];
  rightMatchFieldOptions?: ReconFieldOption[];
  leftCompareFieldOptions?: ReconFieldOption[];
  rightCompareFieldOptions?: ReconFieldOption[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
  reconCompatibility?: CompatibilityCheckResult;
  onStructuredConfigChange?: (patch: Partial<{
    reconRuleName: string;
    matchFieldPairs: ReconFieldPairDraft[];
    compareFieldPairs: ReconFieldPairDraft[];
  }>) => void;
  onViewReconJson: () => void;
  reconJsonPreview?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
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
  reconRuleName,
  matchFieldPairs = [],
  compareFieldPairs = [],
  leftMatchFieldOptions = [],
  rightMatchFieldOptions = [],
  leftCompareFieldOptions = [],
  rightCompareFieldOptions = [],
  leftFieldLabelMap,
  rightFieldLabelMap,
  reconCompatibility,
  onStructuredConfigChange,
  onViewReconJson,
  reconJsonPreview,
}: SchemeWizardReconStepProps) {
  const compatibility = reconCompatibility;
  const showCompatibility =
    (compatibility?.status || 'idle') !== 'idle'
    || (compatibility?.details.length || 0) > 0
    || (compatibility?.message || '等待校验') !== '等待校验';

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">对账规则配置</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          匹配字段和对比字段默认沿用第二步已配置的字段角色，也可以在这里调整字段对。当前对账逻辑将保存为
          <span className="mx-1 font-medium text-text-primary">{reconRuleName}</span>
          。
        </p>

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

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onViewReconJson}
          disabled={!reconJsonPreview}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          查看 JSON
        </button>
        {reconJsonPreview ? (
          <span className="text-xs text-text-muted">当前字段配置已可编译为 JSON</span>
        ) : null}
      </div>
    </div>
  );
}
