import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, FolderOpen } from 'lucide-react';

import type { CollaborationProvider, ReconWorkspaceMode, UserTaskRule } from '../types';
import ReconAutoRunsPanel from './recon/ReconAutoRunsPanel';
import ReconAutoTaskConfigs from './recon/ReconAutoTaskConfigs';
import ReconRulesList from './recon/ReconRulesList';
import ReconWorkspaceHeader from './recon/ReconWorkspaceHeader';
import { fetchReconAutoApi } from './recon/autoApi';
import { RECON_COPY } from './recon/reconCopy';
import type { ReconExecutionMode } from './recon/ReconConversationBar';
import { type ReconCenterTab, type ReconExceptionItem, type ReconRuleListItem, type ReconRunItem } from './recon/types';

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

const READINESS_LABEL: Record<string, string> = {
  waiting_data: '待补数',
  data_partial: '部分就绪',
  data_ready: '已就绪',
  data_failed: '取数失败',
};

const CLOSURE_LABEL: Record<string, string> = {
  open: '未闭环',
  in_progress: '处理中',
  waiting_verify: '待验证',
  closed: '已关闭',
};

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'object' && value !== null) return value as Record<string, unknown>;
  return {};
}

function toText(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return fallback;
}

function toBool(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  return fallback;
}

function toInt(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatDateTime(value: string): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hours = `${date.getHours()}`.padStart(2, '0');
  const minutes = `${date.getMinutes()}`.padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

function scheduleLabel(scheduleType: string, scheduleExpr: string): string {
  const normalized = scheduleType.trim().toLowerCase();
  const base =
    normalized === 'daily'
      ? '每日'
      : normalized === 'weekly'
        ? '每周'
        : normalized === 'monthly'
          ? '每月'
          : normalized === 'cron'
            ? 'Cron'
            : scheduleType || '--';
  return scheduleExpr ? `${base} / ${scheduleExpr}` : base;
}

function toRunUiStatus(runStatus: string, exceptionCount: number): ReconRunItem['status'] {
  const status = runStatus.trim().toLowerCase();
  if (status === 'recon_failed') return 'failed';
  if (status === 'running_recon' || status === 'verifying') return 'running';
  if (
    exceptionCount > 0 ||
    status === 'exception_open' ||
    status === 'waiting_manual_fix' ||
    status === 'waiting_verify'
  ) {
    return 'warning';
  }
  if (status === 'recon_succeeded' || status === 'closed') return 'success';
  return 'running';
}

export default function ReconWorkspace({
  selectedTask,
  mode = 'upload',
  availableRules = [],
  selectedRuleCode = null,
  authToken,
  onSelectRule,
  onOpenCollaborationChannels,
  children,
}: ReconWorkspaceProps) {
  const [centerTab, setCenterTab] = useState<ReconCenterTab>('schemes');
  const [autoTasks, setAutoTasks] = useState<Array<{
    id: string;
    name: string;
    company: string;
    ruleCode: string;
    ruleName: string;
    schedule: string;
    dateOffset: string;
    ownerMode: string;
    channel: string;
    status: 'enabled' | 'paused';
  }>>([]);
  const [autoRuns, setAutoRuns] = useState<ReconRunItem[]>([]);
  const [exceptionsByRunId, setExceptionsByRunId] = useState<Record<string, ReconExceptionItem[]>>(
    {},
  );
  const [loadingAutoTasks, setLoadingAutoTasks] = useState(false);
  const [loadingAutoRuns, setLoadingAutoRuns] = useState(false);
  const [loadingExceptionsRunId, setLoadingExceptionsRunId] = useState<string | null>(null);
  const [verifyRunId, setVerifyRunId] = useState<string | null>(null);
  const [exceptionActionId, setExceptionActionId] = useState<string | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);
  const [exceptionError, setExceptionError] = useState<string | null>(null);
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null);
  const [showCreateSchemePlaceholder, setShowCreateSchemePlaceholder] = useState(false);

  useEffect(() => {
    if (mode === 'upload') return;
    setAutoError(null);
    setExceptionError(null);
  }, [mode]);

  const ruleList = useMemo<ReconRuleListItem[]>(() => {
    const sourceRules = availableRules.filter((rule) => rule.task_type === 'recon');
    const rules = sourceRules.length > 0 ? sourceRules : [selectedTask];
    return rules.map((rule) => ({
      ...rule,
      updated_hint: rule.rule_code === selectedTask.rule_code ? '当前方案' : '方案实例',
    }));
  }, [availableRules, selectedTask]);

  const activeRule = useMemo(() => {
    return (
      ruleList.find((rule) => rule.rule_code === (selectedRuleCode || selectedTask.rule_code)) || {
        ...selectedTask,
        updated_hint: '当前方案',
      }
    );
  }, [ruleList, selectedRuleCode, selectedTask]);

  const uploadRightControls = (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {ruleList.length > 0 && onSelectRule ? (
        <div className="relative min-w-[280px]">
          <select
            value={selectedRuleCode ?? activeRule.rule_code}
            onChange={(event) => onSelectRule(event.target.value)}
            className="h-11 w-full appearance-none rounded-xl border border-border bg-surface px-4 pr-11 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          >
            {ruleList.map((rule) => (
              <option key={rule.rule_code} value={rule.rule_code}>
                {rule.name}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
        </div>
      ) : null}
    </div>
  );

  const loadAutoTasks = async (token: string) => {
    setLoadingAutoTasks(true);
    try {
      const response = await fetchReconAutoApi('/auto-tasks', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '对账任务加载失败'));
      }

      const rows = Array.isArray(data?.tasks) ? data.tasks : [];
      const mapped = rows.map((raw: unknown) => {
        const item = asRecord(raw);
        const ownerMapping = asRecord(item.owner_mapping_json);
        const ownerMappings = Array.isArray(ownerMapping.mappings) ? ownerMapping.mappings.length : 0;
        const defaultOwner = asRecord(ownerMapping.default_owner);
        const defaultOwnerName = toText(defaultOwner?.name, '').trim();
        const ruleCode = toText(item.rule_code, '');
        const matchedRuleName = ruleList.find((rule) => rule.rule_code === ruleCode)?.name || '';
        return {
          id: toText(item.id, ''),
          name: toText(item.task_name, '未命名任务'),
          company: toText(item.company_name, '--'),
          ruleCode,
          ruleName: toText(item.rule_name, matchedRuleName || ruleCode || '--'),
          schedule: scheduleLabel(toText(item.schedule_type, ''), toText(item.schedule_expr, '')),
          dateOffset: toText(item.biz_date_offset, '--'),
          ownerMode: ownerMappings > 0 ? `映射 ${ownerMappings} 组` : defaultOwnerName || '未配置',
          channel: toText(item.channel_name, toText(item.channel_config_id, '--')),
          status: toBool(item.is_enabled, true) ? 'enabled' : 'paused',
        };
      });
      setAutoTasks(mapped);
    } catch (error) {
      setAutoTasks([]);
      setAutoError(error instanceof Error ? error.message : '对账任务加载失败');
    } finally {
      setLoadingAutoTasks(false);
    }
  };

  const loadAutoRuns = async (token: string) => {
    setLoadingAutoRuns(true);
    try {
      const response = await fetchReconAutoApi('/auto-runs', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '运行记录加载失败'));
      }

      const rows = Array.isArray(data?.runs) ? data.runs : [];
      const mapped: ReconRunItem[] = rows.map((raw: unknown) => {
        const item = asRecord(raw);
        const runStatus = toText(item.run_status, '');
        const exceptionCount = toInt(item.anomaly_count, 0);
        return {
          id: toText(item.id, ''),
          autoTaskId: toText(item.auto_task_id, ''),
          taskName: toText(item.task_name, '--'),
          triggerMode: toText(item.trigger_mode, ''),
          businessDate: toText(item.biz_date, '--'),
          status: toRunUiStatus(runStatus, exceptionCount),
          dataReady:
            READINESS_LABEL[toText(item.readiness_status, '')] ||
            toText(item.readiness_status, '--'),
          exceptionCount,
          closureStatus:
            CLOSURE_LABEL[toText(item.closure_status, '')] ||
            toText(item.closure_status, '--'),
          startedAt: formatDateTime(toText(item.started_at, '')),
          finishedAt: formatDateTime(toText(item.finished_at, '')),
        };
      });
      setAutoRuns(mapped);
    } catch (error) {
      setAutoRuns([]);
      setAutoError(error instanceof Error ? error.message : '运行记录加载失败');
    } finally {
      setLoadingAutoRuns(false);
    }
  };

  const loadRunExceptions = async (runId: string) => {
    if (!authToken) {
      setExceptionError('请先登录后查看异常列表');
      return;
    }

    setLoadingExceptionsRunId(runId);
    setExceptionError(null);
    try {
      const response = await fetchReconAutoApi(`/auto-runs/${runId}/exceptions`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '异常列表加载失败'));
      }

      const rows = Array.isArray(data?.exceptions) ? data.exceptions : [];
      const mapped: ReconExceptionItem[] = rows.map((raw: unknown) => {
        const item = asRecord(raw);
        return {
          id: toText(item.id, ''),
          type: toText(item.anomaly_type, '--'),
          summary: toText(item.summary, '--'),
          owner: toText(item.owner_name, '--'),
          reminderStatus: toText(item.reminder_status, '--'),
          feedback: toText(item.latest_feedback, '暂无反馈'),
          handlingStatus: toText(item.processing_status, '--'),
        };
      });
      setExceptionsByRunId((prev) => ({ ...prev, [runId]: mapped }));
    } catch (error) {
      setExceptionError(error instanceof Error ? error.message : '异常列表加载失败');
      setExceptionsByRunId((prev) => ({ ...prev, [runId]: [] }));
    } finally {
      setLoadingExceptionsRunId(null);
    }
  };

  const handleVerifyRun = async (runId: string) => {
    if (!authToken) {
      setAutoError('请先登录后发起重新验证');
      return;
    }

    setFocusedRunId(runId);
    setVerifyRunId(runId);
    setAutoError(null);
    try {
      const response = await fetchReconAutoApi(`/auto-runs/${runId}/verify`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ reason: '前端手动触发重新验证' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '重新验证失败'));
      }
      await loadAutoRuns(authToken);
    } catch (error) {
      setAutoError(error instanceof Error ? error.message : '重新验证失败');
    } finally {
      setVerifyRunId(null);
    }
  };

  const handleRemindException = async (exceptionId: string, runId: string) => {
    if (!authToken) {
      setExceptionError('请先登录后发送催办');
      return;
    }

    setExceptionActionId(exceptionId);
    setExceptionError(null);
    try {
      const response = await fetchReconAutoApi(`/exceptions/${exceptionId}/remind`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '发送催办失败'));
      }
      await loadRunExceptions(runId);
    } catch (error) {
      setExceptionError(error instanceof Error ? error.message : '发送催办失败');
    } finally {
      setExceptionActionId(null);
    }
  };

  const handleSyncException = async (exceptionId: string, runId: string) => {
    if (!authToken) {
      setExceptionError('请先登录后同步待办状态');
      return;
    }

    setExceptionActionId(exceptionId);
    setExceptionError(null);
    try {
      const response = await fetchReconAutoApi(`/exceptions/${exceptionId}/sync`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ max_polls: 1, poll_interval_seconds: 1 }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '同步状态失败'));
      }
      await loadRunExceptions(runId);
      await loadAutoRuns(authToken);
    } catch (error) {
      setExceptionError(error instanceof Error ? error.message : '同步状态失败');
    } finally {
      setExceptionActionId(null);
    }
  };

  useEffect(() => {
    if (mode !== 'center') return;
    if (!authToken) {
      setAutoError('请先登录后查看对账中心数据');
      setAutoTasks([]);
      setAutoRuns([]);
      setFocusedRunId(null);
      return;
    }

    setAutoError(null);
    void Promise.all([loadAutoTasks(authToken), loadAutoRuns(authToken)]);
  }, [mode, authToken]);

  useEffect(() => {
    if (autoRuns.length === 0) {
      setFocusedRunId(null);
      return;
    }
    if (focusedRunId && autoRuns.some((run) => run.id === focusedRunId)) return;
    setFocusedRunId(autoRuns[0].id);
  }, [focusedRunId, autoRuns]);

  useEffect(() => {
    if (mode !== 'center') return;
    if (centerTab !== 'runs') return;
    if (!focusedRunId) return;
    if (exceptionsByRunId[focusedRunId]) return;
    void loadRunExceptions(focusedRunId);
  }, [mode, centerTab, focusedRunId, exceptionsByRunId]);

  if (mode === 'upload') {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface-secondary">
        <div className="sticky top-0 z-20 shrink-0 border-b border-border bg-surface/95 px-6 py-4 backdrop-blur">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-surface-secondary text-sky-600">
                <FolderOpen className="h-4 w-4" />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-text-primary">上传文件对账</h3>
                <p className="text-xs text-text-secondary">选择方案后上传文件，执行手工对账</p>
              </div>
            </div>
            {uploadRightControls}
          </div>
        </div>
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface-secondary">
      <ReconWorkspaceHeader activeTab={centerTab} onTabChange={setCenterTab} />

      <div className="flex min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{RECON_COPY.center.sectionTitle}</h3>
            <p className="mt-1 text-sm text-text-secondary">{RECON_COPY.center.sectionSubtitle}</p>
          </div>

          {autoError && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              {autoError}
            </div>
          )}

          {centerTab === 'schemes' && (
            <ReconRulesList
              rules={ruleList}
              emptyText="当前暂无对账方案，请先新增方案。"
              aiEntryLabel="AI 新建对账方案"
              showCreatePlaceholder={showCreateSchemePlaceholder}
              onCreateByAI={() => setShowCreateSchemePlaceholder(true)}
              onCloseCreatePlaceholder={() => setShowCreateSchemePlaceholder(false)}
            />
          )}

          {centerTab === 'tasks' && (
            <ReconAutoTaskConfigs
              tasks={autoTasks}
              availableRules={ruleList}
              defaultRuleCode={activeRule.rule_code}
              authToken={authToken}
              loading={loadingAutoTasks}
              errorText={null}
              createButtonLabel={RECON_COPY.center.actions.createTask}
              onCreateRule={() => setCenterTab('schemes')}
              onOpenCollaborationChannels={onOpenCollaborationChannels}
              onCreatedTaskConfig={() => {
                if (!authToken) return;
                setAutoError(null);
                return loadAutoTasks(authToken);
              }}
            />
          )}

          {centerTab === 'runs' && (
            <div className="space-y-4">
              <ReconAutoRunsPanel
                runs={autoRuns}
                focusedRunId={focusedRunId}
                exceptionsByRunId={exceptionsByRunId}
                loadingRuns={loadingAutoRuns}
                loadingExceptionsRunId={loadingExceptionsRunId}
                verifyRunId={verifyRunId}
                exceptionActionId={exceptionActionId}
                exceptionError={exceptionError}
                emptyRunsText="暂无运行记录"
                onFocusRun={setFocusedRunId}
                onOpenFollowup={loadRunExceptions}
                onVerifyRun={handleVerifyRun}
                onRemindException={handleRemindException}
                onSyncException={handleSyncException}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
