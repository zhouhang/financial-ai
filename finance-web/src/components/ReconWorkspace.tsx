import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlertCircle,
  ChevronRight,
  Files,
  PlayCircle,
  RefreshCw,
} from 'lucide-react';
import type { CollaborationProvider, ReconWorkspaceMode, UserTaskRule } from '../types';
import type { ReconExecutionMode } from './recon/ReconConversationBar';
import ReconConversationBar from './recon/ReconConversationBar';
import { fetchReconAutoApi } from './recon/autoApi';
import ReconWorkspaceHeader from './recon/ReconWorkspaceHeader';
import {
  cn,
  type ReconCenterRunItem,
  type ReconCenterTab,
  type ReconRunExceptionDetail,
  type ReconSchemeListItem,
  type ReconTaskListItem,
} from './recon/types';

interface ReconWorkspaceProps {
  selectedTask: UserTaskRule;
  mode?: ReconWorkspaceMode;
  availableRules?: UserTaskRule[];
  selectedRuleCode?: string | null;
  executionMode?: ReconExecutionMode;
  authToken?: string | null;
  onSelectRule?: (ruleCode: string) => void;
  onChangeExecutionMode?: (mode: ReconExecutionMode) => void;
  onOpenDataConnections?: () => void;
  onOpenCollaborationChannels?: (provider?: CollaborationProvider) => void;
  children?: ReactNode;
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
  return fallback;
}

function toInt(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toBool(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  return fallback;
}

function formatDateTime(value: string): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatScheduleLabel(scheduleType: string, scheduleExpr: string): string {
  const normalized = scheduleType.trim().toLowerCase();
  const base =
    normalized === 'manual_trigger'
      ? '手动触发'
      : normalized === 'daily'
        ? '每日'
        : normalized === 'weekly'
          ? '每周'
          : normalized === 'cron'
            ? 'Cron'
            : scheduleType || '--';
  return scheduleExpr ? `${base} / ${scheduleExpr}` : base;
}

function summarizeOwnerMapping(raw: unknown): string {
  const ownerMapping = asRecord(raw);
  const mappings = asList(ownerMapping.mappings);
  const defaultOwner = asRecord(ownerMapping.default_owner);
  const defaultName = toText(defaultOwner.name).trim();
  if (mappings.length > 0) {
    return `映射 ${mappings.length} 组`;
  }
  if (defaultName) {
    return defaultName;
  }
  return '未配置';
}

function executionStatusMeta(status: string): { label: string; className: string } {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'success') {
    return {
      label: '成功',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };
  }
  if (normalized === 'running') {
    return {
      label: '运行中',
      className: 'border-sky-200 bg-sky-50 text-sky-700',
    };
  }
  if (normalized === 'failed') {
    return {
      label: '失败',
      className: 'border-red-200 bg-red-50 text-red-700',
    };
  }
  return {
    label: status || '未知',
    className: 'border-border bg-surface-secondary text-text-secondary',
  };
}

function enabledStatusMeta(enabled: boolean): { label: string; className: string } {
  return enabled
    ? {
        label: '启用中',
        className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      }
    : {
        label: '已停用',
        className: 'border-border bg-surface-secondary text-text-secondary',
      };
}

function mapScheme(item: unknown): ReconSchemeListItem {
  const raw = asRecord(item);
  const enabled = toBool(raw.is_enabled, true);
  return {
    id: toText(raw.id),
    schemeCode: toText(raw.scheme_code),
    name: toText(raw.scheme_name || raw.name, '未命名方案'),
    description: toText(raw.description),
    fileRuleCode: toText(raw.file_rule_code),
    procRuleCode: toText(raw.proc_rule_code),
    reconRuleCode: toText(raw.recon_rule_code),
    status: enabled ? 'enabled' : 'paused',
    updatedAt: toText(raw.updated_at),
    createdAt: toText(raw.created_at),
    raw,
  };
}

function mapTask(item: unknown, schemeNameByCode: Map<string, string>): ReconTaskListItem {
  const raw = asRecord(item);
  const enabled = toBool(raw.is_enabled, true);
  const schemeCode = toText(raw.scheme_code);
  return {
    id: toText(raw.id),
    planCode: toText(raw.plan_code),
    name: toText(raw.plan_name, '未命名任务'),
    schemeCode,
    schemeName: schemeNameByCode.get(schemeCode) || schemeCode || '--',
    scheduleType: toText(raw.schedule_type),
    scheduleExpr: toText(raw.schedule_expr),
    bizDateOffset: toText(raw.biz_date_offset),
    channelConfigId: toText(raw.channel_config_id),
    ownerSummary: summarizeOwnerMapping(raw.owner_mapping_json),
    status: enabled ? 'enabled' : 'paused',
    updatedAt: toText(raw.updated_at),
    createdAt: toText(raw.created_at),
    raw,
  };
}

function mapRun(
  item: unknown,
  schemeNameByCode: Map<string, string>,
  taskNameByCode: Map<string, string>,
): ReconCenterRunItem {
  const raw = asRecord(item);
  const schemeCode = toText(raw.scheme_code);
  const planCode = toText(raw.plan_code);
  return {
    id: toText(raw.id),
    runCode: toText(raw.run_code),
    schemeCode,
    planCode,
    schemeName: schemeNameByCode.get(schemeCode) || schemeCode || '--',
    planName: taskNameByCode.get(planCode) || planCode || '--',
    executionStatus: toText(raw.execution_status),
    triggerType: toText(raw.trigger_type),
    entryMode: toText(raw.entry_mode),
    anomalyCount: toInt(raw.anomaly_count, 0),
    failedStage: toText(raw.failed_stage),
    failedReason: toText(raw.failed_reason),
    startedAt: toText(raw.started_at),
    finishedAt: toText(raw.finished_at),
    raw,
  };
}

function mapRunException(item: unknown): ReconRunExceptionDetail {
  const raw = asRecord(item);
  return {
    id: toText(raw.id),
    anomalyType: toText(raw.anomaly_type),
    summary: toText(raw.summary),
    ownerName: toText(raw.owner_name, '--'),
    reminderStatus: toText(raw.reminder_status, '--'),
    processingStatus: toText(raw.processing_status, '--'),
    fixStatus: toText(raw.fix_status, '--'),
    latestFeedback: toText(raw.latest_feedback),
    isClosed: toBool(raw.is_closed, false),
    createdAt: toText(raw.created_at),
    updatedAt: toText(raw.updated_at),
    raw,
  };
}

function SummaryBadge({ label, value }: { label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-text-secondary">
      <span>{label}</span>
      <span className="rounded-full bg-surface-secondary px-1.5 py-0.5 text-text-primary">
        {value}
      </span>
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="text-xs text-text-secondary">{label}</span>
      <span className="max-w-[70%] text-right text-sm text-text-primary">{value || '--'}</span>
    </div>
  );
}

export default function ReconWorkspace({
  selectedTask,
  mode = 'upload',
  availableRules = [],
  selectedRuleCode = null,
  executionMode = 'upload',
  authToken,
  onSelectRule,
  onChangeExecutionMode,
  onOpenDataConnections,
  onOpenCollaborationChannels,
  children,
}: ReconWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<ReconCenterTab>('schemes');
  const [schemes, setSchemes] = useState<ReconSchemeListItem[]>([]);
  const [tasks, setTasks] = useState<ReconTaskListItem[]>([]);
  const [runs, setRuns] = useState<ReconCenterRunItem[]>([]);
  const [exceptionsByRunId, setExceptionsByRunId] = useState<Record<string, ReconRunExceptionDetail[]>>({});
  const [selectedSchemeId, setSelectedSchemeId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loadingCenter, setLoadingCenter] = useState(false);
  const [loadingExceptionsRunId, setLoadingExceptionsRunId] = useState<string | null>(null);
  const [executingPlanId, setExecutingPlanId] = useState<string | null>(null);
  const [centerError, setCenterError] = useState<string | null>(null);

  const uploadRules = useMemo(() => {
    if (availableRules.length > 0) return availableRules.filter((rule) => rule.task_type === 'recon');
    return selectedTask?.task_type === 'recon' ? [selectedTask] : [];
  }, [availableRules, selectedTask]);

  const currentUploadRule =
    uploadRules.find((rule) => rule.rule_code === (selectedRuleCode || selectedTask.rule_code)) ||
    uploadRules[0] ||
    selectedTask;

  const loadCenterData = useCallback(async () => {
    if (!authToken) {
      setSchemes([]);
      setTasks([]);
      setRuns([]);
      return;
    }

    setLoadingCenter(true);
    setCenterError(null);

    try {
      const headers = { Authorization: `Bearer ${authToken}` };
      const [schemeResponse, taskResponse, runResponse] = await Promise.all([
        fetchReconAutoApi('/schemes', { headers }),
        fetchReconAutoApi('/tasks', { headers }),
        fetchReconAutoApi('/runs', { headers }),
      ]);

      const [schemeData, taskData, runData] = await Promise.all([
        schemeResponse.json().catch(() => ({})),
        taskResponse.json().catch(() => ({})),
        runResponse.json().catch(() => ({})),
      ]);

      if (!schemeResponse.ok) {
        throw new Error(String(schemeData.detail || schemeData.message || '对账方案加载失败'));
      }
      if (!taskResponse.ok) {
        throw new Error(String(taskData.detail || taskData.message || '对账任务加载失败'));
      }
      if (!runResponse.ok) {
        throw new Error(String(runData.detail || runData.message || '运行记录加载失败'));
      }

      const nextSchemes = asList(schemeData.schemes).map(mapScheme);
      const schemeNameByCode = new Map(nextSchemes.map((item) => [item.schemeCode, item.name]));
      const nextTasks = asList(taskData.tasks || taskData.run_plans).map((item) =>
        mapTask(item, schemeNameByCode),
      );
      const taskNameByCode = new Map(nextTasks.map((item) => [item.planCode, item.name]));
      const nextRuns = asList(runData.runs).map((item) =>
        mapRun(item, schemeNameByCode, taskNameByCode),
      );

      setSchemes(nextSchemes);
      setTasks(nextTasks);
      setRuns(nextRuns);
      setSelectedSchemeId((prev) =>
        prev && nextSchemes.some((item) => item.id === prev) ? prev : nextSchemes[0]?.id || null,
      );
      setSelectedTaskId((prev) =>
        prev && nextTasks.some((item) => item.id === prev) ? prev : nextTasks[0]?.id || null,
      );
      setSelectedRunId((prev) =>
        prev && nextRuns.some((item) => item.id === prev) ? prev : nextRuns[0]?.id || null,
      );
    } catch (error) {
      setCenterError(error instanceof Error ? error.message : '对账中心加载失败');
    } finally {
      setLoadingCenter(false);
    }
  }, [authToken]);

  const loadRunExceptions = useCallback(
    async (runId: string) => {
      if (!authToken || !runId) return;
      setLoadingExceptionsRunId(runId);
      try {
        const response = await fetchReconAutoApi(`/runs/${runId}/exceptions`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '异常处理加载失败'));
        }
        setExceptionsByRunId((prev) => ({
          ...prev,
          [runId]: asList(data.exceptions).map(mapRunException),
        }));
      } catch (error) {
        setCenterError(error instanceof Error ? error.message : '异常处理加载失败');
      } finally {
        setLoadingExceptionsRunId((prev) => (prev === runId ? null : prev));
      }
    },
    [authToken],
  );

  const handleExecuteTask = useCallback(
    async (task: ReconTaskListItem) => {
      if (!authToken || !task.planCode) return;
      setExecutingPlanId(task.id);
      setCenterError(null);
      try {
        const response = await fetchReconAutoApi(`/run-plans/${task.planCode}/run`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            trigger_mode: 'manual',
            biz_date: '',
            run_context: {},
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '执行对账任务失败'));
        }
        await loadCenterData();
        setActiveTab('runs');
        const run = asRecord(data.run);
        const runId = toText(run.id);
        if (runId) {
          setSelectedRunId(runId);
        }
      } catch (error) {
        setCenterError(error instanceof Error ? error.message : '执行对账任务失败');
      } finally {
        setExecutingPlanId((prev) => (prev === task.id ? null : prev));
      }
    },
    [authToken, loadCenterData],
  );

  useEffect(() => {
    if (mode !== 'center') return;
    void loadCenterData();
  }, [mode, loadCenterData]);

  useEffect(() => {
    if (mode !== 'center' || activeTab !== 'runs' || !selectedRunId) return;
    if (exceptionsByRunId[selectedRunId]) return;
    void loadRunExceptions(selectedRunId);
  }, [activeTab, exceptionsByRunId, loadRunExceptions, mode, selectedRunId]);

  const selectedScheme = schemes.find((item) => item.id === selectedSchemeId) || null;
  const selectedTaskItem = tasks.find((item) => item.id === selectedTaskId) || null;
  const selectedRun = runs.find((item) => item.id === selectedRunId) || null;
  const selectedRunExceptions = selectedRunId ? exceptionsByRunId[selectedRunId] || [] : [];

  const headerRightSlot = (
    <div className="hidden items-center gap-2 lg:flex">
      <SummaryBadge label="方案" value={schemes.length} />
      <SummaryBadge label="任务" value={tasks.length} />
      <SummaryBadge label="运行" value={runs.length} />
    </div>
  );

  const renderEmpty = (
    title: string,
    description: string,
    action?: ReactNode,
  ) => (
    <div className="flex min-h-[240px] flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-surface px-6 py-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-secondary text-text-secondary">
        <Files className="h-5 w-5" />
      </div>
      <h3 className="mt-4 text-base font-semibold text-text-primary">{title}</h3>
      <p className="mt-2 max-w-md text-sm leading-6 text-text-secondary">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );

  const renderSchemesTab = () => (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_360px]">
      <section className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">对账方案</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">固化数据准备与对账逻辑</h3>
          </div>
          <span className="rounded-full border border-border bg-surface-secondary px-3 py-1 text-xs text-text-secondary">
            {schemes.length} 个方案
          </span>
        </div>

        <div className="mt-4 space-y-3">
          {schemes.map((item) => {
            const isActive = item.id === selectedSchemeId;
            const statusMeta = enabledStatusMeta(item.status === 'enabled');
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedSchemeId(item.id)}
                className={cn(
                  'w-full rounded-2xl border px-4 py-4 text-left transition',
                  isActive
                    ? 'border-sky-200 bg-sky-50 shadow-sm'
                    : 'border-border bg-surface hover:border-sky-100 hover:bg-surface-secondary',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-text-primary">{item.name}</span>
                      <span className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', statusMeta.className)}>
                        {statusMeta.label}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">{item.schemeCode || '未配置编码'}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
                </div>
                <p className="mt-3 line-clamp-2 text-sm leading-6 text-text-secondary">
                  {item.description || '当前方案已绑定对账规则，可进一步补充数据准备与业务说明。'}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.procRuleCode ? (
                    <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
                      PROC: {item.procRuleCode}
                    </span>
                  ) : null}
                  <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
                    RECON: {item.reconRuleCode || '--'}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <aside className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
        {selectedScheme ? (
          <>
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">方案详情</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">{selectedScheme.name}</h3>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              {selectedScheme.description || '当前方案尚未补充业务说明，可在后续 AI 配置向导中继续完善。'}
            </p>
            <div className="mt-4 divide-y divide-border-subtle">
              <DetailRow label="方案编码" value={selectedScheme.schemeCode || '--'} />
              <DetailRow label="文件规则" value={selectedScheme.fileRuleCode || '--'} />
              <DetailRow label="整理规则" value={selectedScheme.procRuleCode || '--'} />
              <DetailRow label="对账规则" value={selectedScheme.reconRuleCode || '--'} />
              <DetailRow label="创建时间" value={formatDateTime(selectedScheme.createdAt)} />
              <DetailRow label="更新时间" value={formatDateTime(selectedScheme.updatedAt)} />
            </div>
          </>
        ) : (
          renderEmpty(
            '暂无对账方案',
            '后续会从这里统一承接 AI 方案配置、数据准备确认和规则试跑验证。',
            <button
              type="button"
              onClick={onOpenDataConnections}
              className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
            >
              先去配置数据连接
            </button>,
          )
        )}
      </aside>
    </div>
  );

  const renderTasksTab = () => (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_360px]">
      <section className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">对账任务</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">将方案绑定到运行计划</h3>
          </div>
          <span className="rounded-full border border-border bg-surface-secondary px-3 py-1 text-xs text-text-secondary">
            {tasks.length} 个任务
          </span>
        </div>

        <div className="mt-4 space-y-3">
          {tasks.map((item) => {
            const isActive = item.id === selectedTaskId;
            const statusMeta = enabledStatusMeta(item.status === 'enabled');
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedTaskId(item.id)}
                className={cn(
                  'w-full rounded-2xl border px-4 py-4 text-left transition',
                  isActive
                    ? 'border-sky-200 bg-sky-50 shadow-sm'
                    : 'border-border bg-surface hover:border-sky-100 hover:bg-surface-secondary',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-text-primary">{item.name}</span>
                      <span className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', statusMeta.className)}>
                        {statusMeta.label}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">{item.schemeName}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
                  <span className="rounded-full border border-border bg-surface px-2.5 py-1">
                    {formatScheduleLabel(item.scheduleType, item.scheduleExpr)}
                  </span>
                  <span className="rounded-full border border-border bg-surface px-2.5 py-1">
                    口径: {item.bizDateOffset || '--'}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <aside className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
        {selectedTaskItem ? (
          <>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">任务详情</p>
                <h3 className="mt-1 text-lg font-semibold text-text-primary">{selectedTaskItem.name}</h3>
              </div>
              <button
                type="button"
                onClick={() => void handleExecuteTask(selectedTaskItem)}
                disabled={executingPlanId === selectedTaskItem.id}
                className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {executingPlanId === selectedTaskItem.id ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <PlayCircle className="h-4 w-4" />
                )}
                立即执行
              </button>
            </div>
            <div className="mt-4 divide-y divide-border-subtle">
              <DetailRow label="任务编码" value={selectedTaskItem.planCode || '--'} />
              <DetailRow label="所属方案" value={selectedTaskItem.schemeName} />
              <DetailRow
                label="运行计划"
                value={formatScheduleLabel(selectedTaskItem.scheduleType, selectedTaskItem.scheduleExpr)}
              />
              <DetailRow label="业务日期口径" value={selectedTaskItem.bizDateOffset || '--'} />
              <DetailRow label="责任人映射" value={selectedTaskItem.ownerSummary} />
              <DetailRow label="协作通道" value={selectedTaskItem.channelConfigId || '--'} />
              <DetailRow label="创建时间" value={formatDateTime(selectedTaskItem.createdAt)} />
              <DetailRow label="更新时间" value={formatDateTime(selectedTaskItem.updatedAt)} />
            </div>
            {!selectedTaskItem.channelConfigId && onOpenCollaborationChannels ? (
              <button
                type="button"
                onClick={() => onOpenCollaborationChannels()}
                className="mt-4 inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
              >
                去配置协作通道
              </button>
            ) : null}
          </>
        ) : (
          renderEmpty(
            '暂无对账任务',
            '对账任务负责为方案补充运行计划、通知通道和责任人配置。',
          )
        )}
      </aside>
    </div>
  );

  const renderRunsTab = () => (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_360px]">
      <section className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">运行记录</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">查看每次执行结果与异常处理进展</h3>
          </div>
          <span className="rounded-full border border-border bg-surface-secondary px-3 py-1 text-xs text-text-secondary">
            {runs.length} 次运行
          </span>
        </div>

        <div className="mt-4 space-y-3">
          {runs.map((item) => {
            const isActive = item.id === selectedRunId;
            const statusMeta = executionStatusMeta(item.executionStatus);
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedRunId(item.id)}
                className={cn(
                  'w-full rounded-2xl border px-4 py-4 text-left transition',
                  isActive
                    ? 'border-sky-200 bg-sky-50 shadow-sm'
                    : 'border-border bg-surface hover:border-sky-100 hover:bg-surface-secondary',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-text-primary">{item.planName}</span>
                      <span className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', statusMeta.className)}>
                        {statusMeta.label}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">
                      {item.schemeName} · {item.triggerType || '--'} · {item.entryMode || '--'}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
                  <span className="rounded-full border border-border bg-surface px-2.5 py-1">
                    异常 {item.anomalyCount}
                  </span>
                  <span className="rounded-full border border-border bg-surface px-2.5 py-1">
                    开始 {formatDateTime(item.startedAt)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <aside className="rounded-[28px] border border-border bg-surface p-5 shadow-sm">
        {selectedRun ? (
          <>
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">运行详情</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">{selectedRun.planName}</h3>
            <div className="mt-4 divide-y divide-border-subtle">
              <DetailRow label="运行编码" value={selectedRun.runCode || '--'} />
              <DetailRow label="所属方案" value={selectedRun.schemeName} />
              <DetailRow label="触发方式" value={selectedRun.triggerType || '--'} />
              <DetailRow label="入口模式" value={selectedRun.entryMode || '--'} />
              <DetailRow label="失败阶段" value={selectedRun.failedStage || '--'} />
              <DetailRow label="失败原因" value={selectedRun.failedReason || '--'} />
              <DetailRow label="开始时间" value={formatDateTime(selectedRun.startedAt)} />
              <DetailRow label="结束时间" value={formatDateTime(selectedRun.finishedAt)} />
            </div>

            <div className="mt-5 rounded-2xl border border-border bg-surface-secondary p-4">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-text-secondary" />
                <span className="text-sm font-medium text-text-primary">异常处理</span>
              </div>

              {loadingExceptionsRunId === selectedRun.id ? (
                <p className="mt-3 text-sm text-text-secondary">正在加载异常处理记录...</p>
              ) : selectedRunExceptions.length > 0 ? (
                <div className="mt-3 space-y-3">
                  {selectedRunExceptions.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-border bg-surface p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-text-primary">{item.summary}</p>
                          <p className="mt-1 text-xs text-text-secondary">
                            {item.anomalyType || 'unknown'} · 责任人 {item.ownerName || '--'}
                          </p>
                        </div>
                        <span
                          className={cn(
                            'rounded-full border px-2 py-0.5 text-[11px] font-medium',
                            item.isClosed
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                              : 'border-amber-200 bg-amber-50 text-amber-700',
                          )}
                        >
                          {item.isClosed ? '已关闭' : '处理中'}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-text-secondary">
                        <span className="rounded-full border border-border bg-surface-secondary px-2 py-1">
                          催办 {item.reminderStatus || '--'}
                        </span>
                        <span className="rounded-full border border-border bg-surface-secondary px-2 py-1">
                          处理 {item.processingStatus || '--'}
                        </span>
                        <span className="rounded-full border border-border bg-surface-secondary px-2 py-1">
                          修复 {item.fixStatus || '--'}
                        </span>
                      </div>
                      {item.latestFeedback ? (
                        <p className="mt-3 text-xs leading-5 text-text-secondary">
                          最新反馈：{item.latestFeedback}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-sm text-text-secondary">当前运行暂无异常处理记录。</p>
              )}
            </div>
          </>
        ) : (
          renderEmpty(
            '暂无运行记录',
            '任务执行后，这里会统一展示取数、对账和异常处理的执行结果。',
          )
        )}
      </aside>
    </div>
  );

  if (mode === 'upload') {
    return (
      <div className="flex h-full min-w-0 flex-1 flex-col bg-surface-secondary">
        <div className="shrink-0 border-b border-border bg-surface/90 px-6 py-5 backdrop-blur">
          <div className="mx-auto w-full max-w-6xl">
            <div className="mb-4">
              <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">上传文件对账</p>
              <h2 className="mt-1 text-lg font-semibold text-text-primary">按规则上传文件并直接发起对账</h2>
              <p className="mt-2 text-sm text-text-secondary">
                先确认当前方案与执行方式，再继续在对话里上传文件、提问或发起对账。
              </p>
            </div>
            <ReconConversationBar
              ruleName={currentUploadRule?.name ?? null}
              rules={uploadRules}
              selectedRuleCode={selectedRuleCode ?? currentUploadRule?.rule_code ?? null}
              executionMode={executionMode}
              showRuleSelector
              onSelectRule={onSelectRule}
              onChangeExecutionMode={onChangeExecutionMode}
              onOpenDataConnections={onOpenDataConnections}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-surface-secondary">
      <ReconWorkspaceHeader activeTab={activeTab} onTabChange={setActiveTab} rightSlot={headerRightSlot} />

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[28px] border border-border bg-surface px-5 py-4 shadow-sm">
            <div>
              <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">对账中心</p>
              <p className="mt-1 text-sm text-text-secondary">
                集中查看对账方案、对账任务与运行记录。异常处理从运行详情进入。
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadCenterData()}
              disabled={loadingCenter}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={cn('h-4 w-4', loadingCenter && 'animate-spin')} />
              刷新
            </button>
          </div>

          {centerError ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {centerError}
            </div>
          ) : null}

          {loadingCenter ? (
            renderEmpty('正在加载对账中心', '正在同步对账方案、对账任务和运行记录。')
          ) : activeTab === 'schemes' ? (
            schemes.length > 0 ? (
              renderSchemesTab()
            ) : (
              renderEmpty(
                '还没有对账方案',
                '后续 AI 方案配置向导会从这里进入。先准备好数据连接和规则样本，再逐步沉淀为可复用方案。',
                onOpenDataConnections ? (
                  <button
                    type="button"
                    onClick={onOpenDataConnections}
                    className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                  >
                    去配置数据连接
                  </button>
                ) : undefined,
              )
            )
          ) : activeTab === 'tasks' ? (
            tasks.length > 0 ? (
              renderTasksTab()
            ) : (
              renderEmpty('还没有对账任务', '任务会在方案确认后补充运行计划、通知通道和责任人。')
            )
          ) : runs.length > 0 ? (
            renderRunsTab()
          ) : (
            renderEmpty('还没有运行记录', '当任务开始执行后，这里会显示每次取数、对账与异常处理结果。')
          )}
        </div>
      </div>
    </div>
  );
}
