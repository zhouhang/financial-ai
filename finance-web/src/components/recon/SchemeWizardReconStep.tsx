import { useEffect, useRef } from 'react';
import { FlaskConical, Sparkles } from 'lucide-react';

type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';
type ConfigMode = 'ai' | 'existing';

export interface ReconDraftShape {
  reconDraft: string;
  reconTrialStatus: TrialStatus;
  reconTrialSummary: string;
}

export interface ExistingConfigOption {
  id: string;
  name: string;
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
  reconConfigMode?: ConfigMode;
  selectedReconConfigId?: string;
  existingReconOptions?: ExistingConfigOption[];
  reconCompatibility?: CompatibilityCheckResult;
  onReconConfigModeChange?: (mode: ConfigMode) => void;
  onSelectExistingReconConfig?: (configId: string) => void;
  onGenerateRecon: () => void;
  onTrialRecon: () => void;
  onReconDraftChange: (value: string) => void;
  onViewReconJson: () => void;
  reconJsonPreview?: string;
  reconTrialPreview?: ReconTrialPreview;
  trialDisabled?: boolean;
  isGeneratingRecon?: boolean;
  generationSkill?: string;
  generationPhase?: string;
  generationMessage?: string;
  isTrialingRecon?: boolean;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function formatGenerationPhase(phase: string) {
  if (phase === 'preparing_context') return '准备样例';
  if (phase === 'generating_rule') return '生成规则';
  if (phase === 'validating_rule') return '校验 JSON';
  if (phase === 'rendering_draft_text') return '整理说明';
  if (phase === 'completed') return '生成完成';
  if (phase === 'failed') return '生成失败';
  return '处理中';
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

export default function SchemeWizardReconStep({
  schemeDraft,
  reconConfigMode = 'ai',
  selectedReconConfigId = '',
  existingReconOptions = [],
  reconCompatibility,
  onReconConfigModeChange,
  onSelectExistingReconConfig,
  onGenerateRecon,
  onTrialRecon,
  onReconDraftChange,
  onViewReconJson,
  reconJsonPreview,
  reconTrialPreview,
  trialDisabled,
  isGeneratingRecon = false,
  generationSkill = '对账逻辑生成器',
  generationPhase = 'generating_rule',
  generationMessage = '正在分析整理后的左右数据，并生成数据对账 JSON。',
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
        <p className="text-sm font-semibold text-text-primary">配置方式</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onReconConfigModeChange?.('ai')}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition',
              reconConfigMode === 'ai'
                ? 'border-sky-200 bg-sky-50 text-sky-700'
                : 'border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
            )}
          >
            AI生成配置
          </button>
          <button
            type="button"
            onClick={() => onReconConfigModeChange?.('existing')}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition',
              reconConfigMode === 'existing'
                ? 'border-sky-200 bg-sky-50 text-sky-700'
                : 'border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
            )}
          >
            选择已有配置
          </button>
        </div>

        {reconConfigMode === 'existing' ? (
          <label className="mt-4 block">
            <span className="text-xs font-medium text-text-secondary">已有对账逻辑配置</span>
            <select
              value={selectedReconConfigId}
              onChange={(event) => onSelectExistingReconConfig?.(event.target.value)}
              className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            >
              <option value="">请选择一条已有配置</option>
              {existingReconOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

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

      {reconConfigMode === 'ai' ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {isGeneratingRecon ? (
              <div className="w-full rounded-2xl border border-sky-200 bg-sky-50/70 px-4 py-3 text-sky-700">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
                  AI 正在生成对账逻辑，请稍候…
                </div>
                <div className="mt-2 space-y-1 text-xs leading-6 text-sky-700/90">
                  <p>
                    当前生成器：
                    <span className="ml-1 rounded-full border border-sky-200 bg-white/70 px-2 py-0.5 font-semibold text-sky-700">
                      {generationSkill}
                    </span>
                  </p>
                  <p>当前阶段：{formatGenerationPhase(generationPhase)}</p>
                  <p>{generationMessage}</p>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={onGenerateRecon}
                disabled={isTrialingRecon}
                className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Sparkles className="h-4 w-4" />
                AI生成对账逻辑
              </button>
            )}
          </div>

          <label className="block">
            <span className="text-xs font-medium text-text-secondary">数据对账逻辑</span>
            <textarea
              value={schemeDraft.reconDraft}
              onChange={(event) => onReconDraftChange(event.target.value)}
              rows={12}
              className="mt-1.5 w-full rounded-2xl border border-border bg-surface px-4 py-3 font-mono text-sm leading-6 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
              placeholder="如需改动说明，请修改后重新点击 AI 生成对账逻辑。"
            />
            <p className="mt-2 text-xs leading-5 text-text-muted">
              手动修改这里的说明后，需要重新点击“AI生成对账逻辑”，系统不会直接把文字改写成可执行 JSON。
            </p>
          </label>
        </>
      ) : null}

      {isTrialingRecon ? (
        <div className="flex items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50/60 px-5 py-4">
          <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
          <span className="text-sm font-medium text-sky-700">AI 正在试跑数据对账，请稍候…</span>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleTrialRecon}
          disabled={trialDisabled || isTrialingRecon || isGeneratingRecon}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <FlaskConical className="h-4 w-4" />
          试跑验证
        </button>
        <button
          type="button"
          onClick={onViewReconJson}
          disabled={!reconJsonPreview || isTrialingRecon || isGeneratingRecon}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          JSON
        </button>
        {reconJsonPreview ? (
          <span className="text-xs text-text-muted">已生成 JSON 预览</span>
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
                  <p className="text-xs text-text-secondary">金额差异</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {preview.resultSummary.amountDiff ?? preview.resultSummary.diffCount ?? '--'}
                  </p>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm leading-6 text-text-secondary">
                试跑结果摘要将在这里展示匹配成功、差异和缺失情况。
              </p>
            )}
          </div>

          {renderSampleTable(preview?.resultSamples, '对账差异抽样', preview?.resultFieldLabelMap)}
        </div>
      ) : null}
    </div>
  );
}
