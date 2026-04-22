type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';
type PreviewState = 'empty' | 'current' | 'reference';

interface SchemeWizardSummaryStepProps {
  schemeName: string;
  businessGoal: string;
  leftSources: string[];
  rightSources: string[];
  leftOutputFields: string[];
  rightOutputFields: string[];
  procDisplayName: string;
  reconDisplayName: string;
  procHasConfig: boolean;
  reconHasConfig: boolean;
  procTrialStatus: TrialStatus;
  reconTrialStatus: TrialStatus;
  procTrialSummary: string;
  reconTrialSummary: string;
  procPreviewState?: PreviewState;
  reconPreviewState?: PreviewState;
}

function statusChip(
  hasConfig: boolean,
  trialStatus: TrialStatus,
  previewState: PreviewState = 'empty',
): { label: string; className: string } {
  if (previewState === 'reference') {
    return {
      label: '仅供参考',
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    };
  }
  if (!hasConfig) {
    return {
      label: '待生成',
      className: 'border-border bg-surface text-text-secondary',
    };
  }
  if (trialStatus === 'passed') {
    return {
      label: '已通过',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };
  }
  return {
    label: '待试跑',
    className: 'border-border bg-surface text-text-secondary',
  };
}

function SummaryCard({
  title,
  value,
  helper,
}: {
  title: string;
  value: string;
  helper?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-3">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-text-muted">{title}</p>
      <p className="mt-2 text-sm leading-6 text-text-primary">{value || '--'}</p>
      {helper ? <p className="mt-2 text-xs leading-5 text-text-secondary">{helper}</p> : null}
    </div>
  );
}

export default function SchemeWizardSummaryStep({
  schemeName,
  businessGoal,
  leftSources,
  rightSources,
  leftOutputFields,
  rightOutputFields,
  procDisplayName,
  reconDisplayName,
  procHasConfig,
  reconHasConfig,
  procTrialStatus,
  reconTrialStatus,
  procTrialSummary,
  reconTrialSummary,
  procPreviewState = 'empty',
  reconPreviewState = 'empty',
}: SchemeWizardSummaryStepProps) {
  const procStatus = statusChip(procHasConfig, procTrialStatus, procPreviewState);
  const reconStatus = statusChip(reconHasConfig, reconTrialStatus, reconPreviewState);
  const readyToSave = procTrialStatus === 'passed' && reconTrialStatus === 'passed';

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-5">
        <p className="text-sm font-semibold text-text-primary">确认保存前，再看一遍当前方案</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          第四步只做确认和保存门禁，不在这里重新编辑配置。
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SummaryCard title="方案名称" value={schemeName || '--'} />
        <SummaryCard title="对账目的" value={businessGoal || '--'} />
      </div>

      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">数据准备</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <SummaryCard title="左侧数据" value={leftSources.join('、') || '--'} />
          <SummaryCard title="左侧输出字段" value={leftOutputFields.join('、') || '--'} />
          <SummaryCard title="右侧数据" value={rightSources.join('、') || '--'} />
          <SummaryCard title="右侧输出字段" value={rightOutputFields.join('、') || '--'} />
          <SummaryCard title="数据整理配置" value={procDisplayName} />
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">对账规则</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-1">
          <SummaryCard title="当前对账逻辑" value={reconDisplayName} />
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">校验状态</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-border bg-surface px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-text-primary">数据整理试跑</p>
              <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${procStatus.className}`}>
                {procStatus.label}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              {procTrialSummary || '当前还没有最新的试跑结果。'}
            </p>
          </div>
          <div className="rounded-2xl border border-border bg-surface px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-text-primary">对账规则试跑</p>
              <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${reconStatus.className}`}>
                {reconStatus.label}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              {reconTrialSummary || '当前还没有最新的试跑结果。'}
            </p>
          </div>
        </div>
      </div>

      <div
        className={`rounded-2xl border px-4 py-3 text-sm ${
          readyToSave
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'border-amber-200 bg-amber-50 text-amber-700'
        }`}
      >
        {readyToSave
          ? '当前整理配置和对账规则都已试跑通过，可以保存方案。'
          : '保存前需先让数据整理和对账规则都完成最新一次试跑通过。'}
      </div>
    </div>
  );
}
