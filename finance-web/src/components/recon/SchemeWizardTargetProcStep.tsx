import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ChevronDown, Sparkles } from 'lucide-react';

export type SchemeWizardStep = 1 | 2;
export type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';

export interface SchemeDraftLite {
  name: string;
  businessGoal: string;
  leftDescription: string;
  rightDescription: string;
  procConfigMode: 'ai' | 'existing';
  selectedProcConfigId: string;
  procDraft: string;
  procTrialStatus: TrialStatus;
  procTrialSummary: string;
}

export interface SchemeSourceOption {
  id: string;
  name: string;
  sourceId: string;
  sourceName: string;
  sourceKind: string;
  providerCode: string;
  description?: string;
  datasetCode?: string;
  resourceKey?: string;
  datasetKind?: string;
}

export interface ProcSampleRow {
  [key: string]: string | number | null;
}

export interface ProcSampleGroup {
  title: string;
  rows: ProcSampleRow[];
}

export interface ProcTrialPreview {
  status: TrialStatus;
  summary: string;
  leftSourceSamples: ProcSampleGroup[];
  rightSourceSamples: ProcSampleGroup[];
  leftOutputSamples: ProcSampleGroup[];
  rightOutputSamples: ProcSampleGroup[];
}

export interface ExistingConfigOption {
  id: string;
  name: string;
}

export interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed';
  message: string;
  details: string[];
}

export interface SchemeWizardTargetProcStepProps {
  step: SchemeWizardStep;
  schemeDraft: SchemeDraftLite;
  availableSources: SchemeSourceOption[];
  loadingSources: boolean;
  sourceLoadError?: string;
  selectedLeftSources: SchemeSourceOption[];
  selectedRightSources: SchemeSourceOption[];
  existingProcOptions: ExistingConfigOption[];
  procCompatibility: CompatibilityCheckResult;
  onNameChange: (value: string) => void;
  onBusinessGoalChange: (value: string) => void;
  onDescriptionChange: (side: 'left' | 'right', value: string) => void;
  onChangeSourceSelection: (side: 'left' | 'right', sourceIds: string[]) => void;
  onProcConfigModeChange: (mode: 'ai' | 'existing') => void;
  onSelectExistingProcConfig: (configId: string) => void;
  isGeneratingProc?: boolean;
  isTrialingProc?: boolean;
  onGenerateProc: () => void;
  onTrialProc: () => void;
  onProcDraftChange: (value: string) => void;
  onViewProcJson: () => void;
  procJsonPreview?: string;
  procTrialPreview?: ProcTrialPreview;
}

type PreviewSection = 'left' | 'right';

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function trialStatusMeta(status: TrialStatus): { label: string; className: string } {
  if (status === 'passed') {
    return {
      label: '试跑通过',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };
  }
  if (status === 'needs_adjustment') {
    return {
      label: '需调整',
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    };
  }
  return {
    label: '待试跑',
    className: 'border-border bg-surface-secondary text-text-secondary',
  };
}

function formatSourceLabel(source: SchemeSourceOption) {
  return source.description || source.providerCode || source.sourceKind;
}

function RowTable({ rows }: { rows: ProcSampleRow[] }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-xs text-text-secondary">
        暂无抽样数据
      </div>
    );
  }

  const columns = Object.keys(rows[0] || {});

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
      <table className="w-full min-w-[520px] border-collapse text-xs">
        <thead>
          <tr className="border-b border-border-subtle text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">
            {columns.map((col) => (
              <th key={col} className="px-4 py-2 text-left font-semibold">
                <span className="block max-w-[200px] truncate">{col}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`row-${index}`}
              className="border-b border-border-subtle text-text-secondary last:border-b-0"
            >
              {columns.map((col) => (
                <td key={`${col}-${index}`} className="px-4 py-2 align-top">
                  <span className="block max-w-[220px] truncate">
                    {row[col] === null || row[col] === undefined ? '--' : String(row[col])}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SampleGroup({ group }: { group: ProcSampleGroup }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-text-secondary">{group.title}</p>
      <RowTable rows={group.rows} />
    </div>
  );
}

function PreviewSectionBlock({
  title,
  description,
  groups,
}: {
  title: string;
  description: string;
  groups: ProcSampleGroup[];
}) {
  return (
    <div className="rounded-3xl border border-border bg-surface-secondary p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
        </div>
        <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
          {groups.length} 组
        </span>
      </div>
      <div className="mt-4 space-y-4">
        {groups.length > 0 ? (
          groups.map((group, index) => <SampleGroup key={`${title}-${index}`} group={group} />)
        ) : (
          <div className="rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-sm text-text-secondary">
            当前没有可展示的抽样结果。
          </div>
        )}
      </div>
    </div>
  );
}

function MultiSelectDropdown({
  title,
  description,
  sources,
  selectedIds,
  onConfirmSelection,
}: {
  title: string;
  description: string;
  sources: SchemeSourceOption[];
  selectedIds: string[];
  onConfirmSelection: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftIds, setDraftIds] = useState<string[]>(selectedIds);
  const groupedSources = useMemo(() => {
    const groups = new Map<
      string,
      {
        sourceId: string;
        sourceName: string;
        sourceKind: string;
        providerCode: string;
        description?: string;
        datasets: SchemeSourceOption[];
      }
    >();
    sources.forEach((source) => {
      const current = groups.get(source.sourceId);
      if (current) {
        current.datasets.push(source);
        return;
      }
      groups.set(source.sourceId, {
        sourceId: source.sourceId,
        sourceName: source.sourceName,
        sourceKind: source.sourceKind,
        providerCode: source.providerCode,
        description: source.description,
        datasets: [source],
      });
    });
    return Array.from(groups.values());
  }, [sources]);
  const selectedNames = useMemo(
    () => sources.filter((s) => selectedIds.includes(s.id)).map((s) => s.name),
    [sources, selectedIds],
  );
  const displayText = selectedNames.length > 0 ? selectedNames.join('、') : '请选择数据集（可多选）';

  const toggleDropdown = () => {
    if (open) {
      setDraftIds(selectedIds);
      setOpen(false);
      return;
    }
    setDraftIds(selectedIds);
    setOpen(true);
  };

  const toggleDraftId = (id: string) => {
    setDraftIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const handleConfirm = () => {
    onConfirmSelection(draftIds);
    setOpen(false);
  };

  return (
    <div className="rounded-3xl border border-border bg-surface-secondary p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
        </div>
        <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
          已选 {selectedIds.length}
        </span>
      </div>

      <div className="relative mt-4">
        <button
          type="button"
          onClick={toggleDropdown}
          className="flex w-full items-center justify-between rounded-2xl border border-border bg-surface px-4 py-3 text-left text-sm text-text-primary transition hover:border-sky-200"
        >
          <span className={cn('truncate', selectedNames.length === 0 && 'text-text-secondary')}>
            {displayText}
          </span>
          <ChevronDown className={cn('ml-2 h-4 w-4 shrink-0 text-text-muted transition-transform', open && 'rotate-180')} />
        </button>

        {open ? (
          <div className="absolute z-10 mt-2 w-full rounded-2xl border border-border bg-surface shadow-lg">
            {groupedSources.length > 0 ? (
              <div className="border-b border-border bg-surface px-3 py-3">
                <button
                  type="button"
                  onClick={handleConfirm}
                  className="w-full rounded-xl bg-text-primary px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
                >
                  确定
                </button>
              </div>
            ) : null}
            <div className="max-h-72 overflow-y-auto p-3">
              {groupedSources.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-surface-secondary px-4 py-4 text-sm text-text-secondary">
                  暂无可选数据集
                </div>
              ) : (
                <div className="space-y-3">
                  {groupedSources.map((group) => (
                    <div key={group.sourceId} className="rounded-2xl border border-border-subtle bg-surface-secondary p-3">
                      <div className="pb-2">
                        <p className="text-sm font-semibold text-text-primary">{group.sourceName}</p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {group.description || group.providerCode || group.sourceKind}
                        </p>
                      </div>
                      <div className="space-y-2">
                        {group.datasets.map((dataset) => {
                          const checked = draftIds.includes(dataset.id);
                          return (
                            <label
                              key={dataset.id}
                              className={cn(
                                'flex items-start gap-3 rounded-xl border px-3 py-2 text-left transition',
                                checked
                                  ? 'border-sky-200 bg-sky-50'
                                  : 'border-transparent bg-surface hover:border-border-subtle',
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleDraftId(dataset.id)}
                                className="mt-1 h-4 w-4 rounded border-border text-sky-600 focus:ring-sky-200"
                              />
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium text-text-primary">{dataset.name}</p>
                                <p className="mt-1 text-xs text-text-secondary">
                                  {dataset.datasetCode || dataset.resourceKey || dataset.datasetKind || formatSourceLabel(dataset)}
                                </p>
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ProcTrialPreviewPanel({
  draftStatus,
  draftSummary,
  preview,
}: {
  draftStatus: TrialStatus;
  draftSummary: string;
  preview?: ProcTrialPreview;
}) {
  const [activeSection, setActiveSection] = useState<PreviewSection>('left');
  const hasPreview = Boolean(preview);

  if (!hasPreview) {
    return null;
  }

  const meta = trialStatusMeta(preview?.status || draftStatus);
  const summary = preview?.summary || draftSummary;

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className={cn('inline-flex rounded-full border px-3 py-1 text-xs font-medium', meta.className)}>
            {meta.label}
          </span>
          <p className="text-sm leading-6 text-text-secondary">
            {summary || '点击试跑验证后，会展示整理前后的抽样数据结果。'}
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="sticky top-0 z-[1] rounded-2xl border border-border bg-surface/95 p-2 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveSection('left')}
              className={cn(
                'rounded-xl px-4 py-2 text-sm font-medium transition',
                activeSection === 'left'
                  ? 'bg-text-primary text-white'
                  : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
              )}
            >
              左侧数据
            </button>
            <button
              type="button"
              onClick={() => setActiveSection('right')}
              className={cn(
                'rounded-xl px-4 py-2 text-sm font-medium transition',
                activeSection === 'right'
                  ? 'bg-text-primary text-white'
                  : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
              )}
            >
              右侧数据
            </button>
          </div>
        </div>

        {activeSection === 'left' && preview ? (
          <div className="space-y-4">
            <PreviewSectionBlock
              title="左侧原始数据抽样"
              description="每个数据源分别展示列名与 3 条抽样数据。"
              groups={preview.leftSourceSamples}
            />
            <PreviewSectionBlock
              title="整理后左侧输出"
              description="根据当前数据整理配置生成的左侧标准化结果。"
              groups={preview.leftOutputSamples}
            />
          </div>
        ) : preview ? (
          <div className="space-y-4">
            <PreviewSectionBlock
              title="右侧原始数据抽样"
              description="每个数据源分别展示列名与 3 条抽样数据。"
              groups={preview.rightSourceSamples}
            />
            <PreviewSectionBlock
              title="整理后右侧输出"
              description="根据当前数据整理配置生成的右侧标准化结果。"
              groups={preview.rightOutputSamples}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function SchemeWizardTargetProcStep({
  step,
  schemeDraft,
  availableSources,
  loadingSources,
  sourceLoadError,
  selectedLeftSources,
  selectedRightSources,
  existingProcOptions,
  procCompatibility,
  onNameChange,
  onBusinessGoalChange,
  onDescriptionChange,
  onChangeSourceSelection,
  onProcConfigModeChange,
  onSelectExistingProcConfig,
  isGeneratingProc = false,
  isTrialingProc = false,
  onGenerateProc,
  onTrialProc,
  onProcDraftChange,
  onViewProcJson,
  procJsonPreview,
  procTrialPreview,
}: SchemeWizardTargetProcStepProps) {
  const previewAnchorRef = useRef<HTMLDivElement | null>(null);
  const scrollToPreviewPendingRef = useRef(false);
  const showCompatibility =
    procCompatibility.status !== 'idle' ||
    procCompatibility.details.length > 0 ||
    procCompatibility.message !== '等待校验';

  useEffect(() => {
    if (!scrollToPreviewPendingRef.current || !procTrialPreview) {
      return;
    }
    previewAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    scrollToPreviewPendingRef.current = false;
  }, [procTrialPreview]);

  const handleTrialProc = () => {
    scrollToPreviewPendingRef.current = true;
    onTrialProc();
  };

  if (step === 1) {
    return (
      <div className="space-y-5">
        <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
          <p className="text-xs font-medium text-text-secondary">步骤说明</p>
          <p className="mt-2 text-sm leading-6 text-text-primary">
            先明确这次要核对什么，再分别选择左侧和右侧原始数据集，每侧可选多份数据集。
          </p>
        </div>

        <label className="block">
          <span className="text-xs font-medium text-text-secondary">方案名称</span>
          <input
            value={schemeDraft.name}
            onChange={(event) => onNameChange(event.target.value)}
            className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            placeholder="例如：平台结算日清方案"
          />
        </label>

        <label className="block">
          <span className="text-xs font-medium text-text-secondary">对账目标</span>
          <textarea
            value={schemeDraft.businessGoal}
            onChange={(event) => onBusinessGoalChange(event.target.value)}
            rows={4}
            className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm leading-6 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            placeholder="一句话描述对账的目的，比如核对平台订单数据与电商店铺订单数据是否一致，并输出差异订单明细，让AI更好的帮你达成目的。"
          />
        </label>

        {sourceLoadError ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {sourceLoadError}
          </div>
        ) : null}

        {loadingSources ? (
          <div className="flex items-center gap-2 rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm text-text-secondary">
            <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-border border-t-sky-500" />
            正在加载可选数据集...
          </div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            <MultiSelectDropdown
              title="左侧原始数据"
              description="选择左侧原始数据集，可同时选多份平台、数据库或 API 数据集。"
              sources={availableSources}
              selectedIds={selectedLeftSources.map((item) => item.id)}
              onConfirmSelection={(ids) => onChangeSourceSelection('left', ids)}
            />
            <MultiSelectDropdown
              title="右侧原始数据"
              description="选择右侧原始数据集，可同时选多份平台、数据库或 API 数据集。"
              sources={availableSources}
              selectedIds={selectedRightSources.map((item) => item.id)}
              onConfirmSelection={(ids) => onChangeSourceSelection('right', ids)}
            />
          </div>
        )}

        <div className="grid gap-4 xl:grid-cols-2">
          <label className="block">
            <span className="text-xs font-medium text-text-secondary">左侧数据描述</span>
            <textarea
              value={schemeDraft.leftDescription}
              onChange={(event) => onDescriptionChange('left', event.target.value)}
              rows={4}
              className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm leading-6 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
              placeholder="一句话描述期望将原始数据转化成一个结果数据让AI理解后进行转化，例如：将左侧原始数据转化成有订单号、金额、时间的数据。"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-text-secondary">右侧数据描述</span>
            <textarea
              value={schemeDraft.rightDescription}
              onChange={(event) => onDescriptionChange('right', event.target.value)}
              rows={4}
              className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm leading-6 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
              placeholder="一句话描述期望将原始数据转化成一个结果数据让AI理解后进行转化，例如：将右侧原始数据转化成有订单号、金额、时间的数据。"
            />
          </label>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">配置方式</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onProcConfigModeChange('ai')}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition',
              schemeDraft.procConfigMode === 'ai'
                ? 'border-sky-200 bg-sky-50 text-sky-700'
                : 'border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
            )}
          >
            AI生成配置
          </button>
          <button
            type="button"
            onClick={() => onProcConfigModeChange('existing')}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition',
              schemeDraft.procConfigMode === 'existing'
                ? 'border-sky-200 bg-sky-50 text-sky-700'
                : 'border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
            )}
          >
            选择已有配置
          </button>
        </div>

        {schemeDraft.procConfigMode === 'existing' ? (
          <label className="mt-4 block">
            <span className="text-xs font-medium text-text-secondary">已有数据整理配置</span>
            <select
              value={schemeDraft.selectedProcConfigId}
              onChange={(event) => onSelectExistingProcConfig(event.target.value)}
              className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            >
              <option value="">请选择一条已有配置</option>
              {existingProcOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {showCompatibility ? (
          <div
            className={cn(
              'mt-4 rounded-2xl border px-4 py-3 text-sm',
              procCompatibility.status === 'passed'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : procCompatibility.status === 'failed'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : 'border-border bg-surface text-text-secondary',
            )}
          >
            <p>{procCompatibility.message}</p>
            {procCompatibility.details.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {procCompatibility.details.map((detail) => (
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

      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-sky-600" />
          <p className="text-sm font-semibold text-text-primary">数据整理</p>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {[
            { label: '左侧数据', value: selectedLeftSources.map((item) => item.name).join('、') || '--' },
            { label: '左侧描述', value: schemeDraft.leftDescription || '--' },
            { label: '右侧数据', value: selectedRightSources.map((item) => item.name).join('、') || '--' },
            { label: '右侧描述', value: schemeDraft.rightDescription || '--' },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl border border-border bg-surface px-4 py-3">
              <p className="text-[11px] font-semibold tracking-[0.14em] text-text-muted">{item.label}</p>
              <p className="mt-2 text-sm leading-6 text-text-primary">{item.value}</p>
            </div>
          ))}
        </div>
      </div>

      {isGeneratingProc || isTrialingProc ? (
        <div className="flex items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50/60 px-5 py-4">
          <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
          <span className="text-sm font-medium text-sky-700">
            {isTrialingProc
              ? 'AI 正在试跑数据整理，请稍候…'
              : schemeDraft.procConfigMode === 'existing'
              ? '正在加载已有配置，请稍候…'
              : 'AI 正在生成整理配置，请稍候…'}
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          {schemeDraft.procConfigMode === 'ai' ? (
            <button
              type="button"
              onClick={onGenerateProc}
              disabled={isTrialingProc}
              className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100"
            >
              <Sparkles className="h-4 w-4" />
              AI生成整理配置
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleTrialProc}
            disabled={
              isTrialingProc
              || isGeneratingProc
              || (
              !schemeDraft.procDraft.trim()
              && !(schemeDraft.procConfigMode === 'existing' && schemeDraft.selectedProcConfigId)
              )
            }
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <CheckCircle2 className="h-4 w-4" />
            试跑验证
          </button>
          <button
            type="button"
            onClick={onViewProcJson}
            disabled={
              isTrialingProc
              || isGeneratingProc
              || (
              !procJsonPreview
              || (
                !schemeDraft.procDraft.trim()
                && !(schemeDraft.procConfigMode === 'existing' && schemeDraft.selectedProcConfigId)
              )
              )
            }
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            JSON
          </button>
          {procJsonPreview ? <span className="text-xs text-text-secondary">已生成 JSON</span> : null}
        </div>
      )}

      <label className="block">
        <span className="text-xs font-medium text-text-secondary">数据整理配置</span>
        <textarea
          value={schemeDraft.procDraft}
          onChange={(event) => onProcDraftChange(event.target.value)}
          rows={14}
          className="mt-1.5 w-full rounded-2xl border border-border bg-surface px-4 py-3 text-sm leading-7 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          placeholder={
            schemeDraft.procConfigMode === 'existing'
              ? '选择已有配置后，可在这里继续调整数据整理配置。'
              : 'AI 生成后，可在这里继续调整数据整理配置。'
          }
        />
      </label>

      <div ref={previewAnchorRef} className="scroll-mt-24">
        <ProcTrialPreviewPanel
          draftStatus={schemeDraft.procTrialStatus}
          draftSummary={schemeDraft.procTrialSummary}
          preview={procTrialPreview}
        />
      </div>
    </div>
  );
}
