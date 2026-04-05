import { useEffect, useMemo } from 'react';
import { ArrowUpRight, RefreshCw } from 'lucide-react';

import { cn } from './types';
import type { ReconExceptionItem, ReconRunItem } from './types';

export interface ReconAutoRunsPanelProps {
  runs: ReconRunItem[];
  focusedRunId: string | null;
  exceptionsByRunId: Record<string, ReconExceptionItem[]>;
  loadingRuns?: boolean;
  loadingExceptionsRunId?: string | null;
  verifyRunId?: string | null;
  exceptionActionId?: string | null;
  exceptionError?: string | null;
  emptyRunsText?: string;
  onFocusRun: (runId: string) => void;
  onOpenFollowup: (runId: string) => void | Promise<void>;
  onVerifyRun: (runId: string) => void | Promise<void>;
  onRemindException: (exceptionId: string, runId: string) => void | Promise<void>;
  onSyncException: (exceptionId: string, runId: string) => void | Promise<void>;
}

function statusBadge(status: ReconRunItem['status']) {
  if (status === 'success') return 'bg-emerald-50 text-emerald-600 border-emerald-200';
  if (status === 'running') return 'bg-blue-50 text-blue-600 border-blue-200';
  if (status === 'warning') return 'bg-amber-50 text-amber-600 border-amber-200';
  return 'bg-red-50 text-red-600 border-red-200';
}

function statusLabel(status: ReconRunItem['status']) {
  if (status === 'success') return '已完成';
  if (status === 'running') return '运行中';
  if (status === 'warning') return '有异常';
  return '执行失败';
}

function triggerModeLabel(triggerMode: string) {
  const normalized = triggerMode.trim().toLowerCase();
  if (normalized === 'manual') return '手动';
  if (normalized === 'cron') return '自动';
  if (normalized === 'rerun') return '重跑';
  if (normalized === 'verify') return '验证';
  return triggerMode || '未知';
}

function triggerModeBadge(triggerMode: string) {
  const normalized = triggerMode.trim().toLowerCase();
  if (normalized === 'manual') return 'border-violet-200 bg-violet-50 text-violet-700';
  if (normalized === 'cron') return 'border-sky-200 bg-sky-50 text-sky-700';
  if (normalized === 'rerun') return 'border-amber-200 bg-amber-50 text-amber-700';
  if (normalized === 'verify') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  return 'border-border bg-surface-secondary text-text-secondary';
}

function isClosedHandlingStatus(status: string) {
  const normalized = status.trim().toLowerCase();
  return normalized.includes('closed') || status.includes('关闭');
}

export default function ReconAutoRunsPanel({
  runs,
  focusedRunId,
  exceptionsByRunId,
  loadingRuns = false,
  loadingExceptionsRunId = null,
  verifyRunId = null,
  exceptionActionId = null,
  exceptionError = null,
  emptyRunsText = '暂无运行批次数据',
  onFocusRun,
  onOpenFollowup,
  onVerifyRun,
  onRemindException,
  onSyncException,
}: ReconAutoRunsPanelProps) {
  useEffect(() => {
    if (runs.length === 0) return;
    if (focusedRunId && runs.some((run) => run.id === focusedRunId)) return;
    onFocusRun(runs[0].id);
  }, [focusedRunId, onFocusRun, runs]);

  const focusedRun = useMemo(
    () => runs.find((run) => run.id === focusedRunId) || null,
    [focusedRunId, runs],
  );
  const focusedExceptions = focusedRun ? exceptionsByRunId[focusedRun.id] || [] : [];
  const unresolvedCount = focusedExceptions.filter(
    (item) => !isClosedHandlingStatus(item.handlingStatus),
  ).length;

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-2xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface-secondary text-left text-text-secondary">
            <tr>
              <th className="px-4 py-3 font-medium">任务名称</th>
              <th className="px-4 py-3 font-medium">业务日期</th>
              <th className="px-4 py-3 font-medium">执行状态</th>
              <th className="px-4 py-3 font-medium">数据就绪</th>
              <th className="px-4 py-3 font-medium">异常数</th>
              <th className="px-4 py-3 font-medium">闭环状态</th>
              <th className="px-4 py-3 font-medium">开始 / 完成</th>
              <th className="px-4 py-3 font-medium">
                <div className="flex justify-end">操作</div>
              </th>
            </tr>
          </thead>
          <tbody>
            {loadingRuns ? (
              <tr className="border-t border-border-subtle text-text-secondary">
                <td className="px-4 py-8 text-center" colSpan={8}>
                  正在加载运行批次...
                </td>
              </tr>
            ) : runs.length > 0 ? (
              runs.map((run) => {
                const focused = run.id === focusedRunId;
                return (
                  <tr
                    key={run.id}
                    className={cn(
                      'border-t border-border-subtle text-text-primary',
                      focused && 'bg-sky-50/40',
                    )}
                  >
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{run.taskName}</span>
                        <span
                          className={cn(
                            'inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium',
                            triggerModeBadge(run.triggerMode),
                          )}
                        >
                          {triggerModeLabel(run.triggerMode)}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{run.businessDate}</td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-flex rounded-full border px-2.5 py-1 text-xs font-medium',
                          statusBadge(run.status),
                        )}
                      >
                        {statusLabel(run.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{run.dataReady}</td>
                    <td className="px-4 py-3 text-text-secondary">{run.exceptionCount}</td>
                    <td className="px-4 py-3 text-text-secondary">{run.closureStatus}</td>
                    <td className="px-4 py-3 text-xs text-text-secondary">
                      <div>{run.startedAt}</div>
                      <div className="mt-1">{run.finishedAt}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            onFocusRun(run.id);
                            void onOpenFollowup(run.id);
                          }}
                          className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-secondary"
                        >
                          <ArrowUpRight className="h-3.5 w-3.5" />
                          异常跟进
                        </button>
                        <button
                          type="button"
                          disabled={verifyRunId === run.id}
                          onClick={() => {
                            onFocusRun(run.id);
                            void onVerifyRun(run.id);
                          }}
                          className="inline-flex items-center gap-1 rounded-lg border border-sky-200 px-2.5 py-1.5 text-xs text-sky-700 transition-colors hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          <RefreshCw className={cn('h-3.5 w-3.5', verifyRunId === run.id && 'animate-spin')} />
                          {verifyRunId === run.id ? '验证中...' : '重新验证'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr className="border-t border-border-subtle text-text-secondary">
                <td className="px-4 py-8 text-center" colSpan={8}>
                  {emptyRunsText}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {focusedRun && (
        <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 className="text-base font-semibold text-text-primary">运行明细与异常跟进</h4>
              <p className="mt-1 text-sm text-text-secondary">
                批次 {focusedRun.id}，任务 {focusedRun.taskName}，业务日期 {focusedRun.businessDate}
              </p>
            </div>
            <div className="rounded-full bg-surface-secondary px-3 py-1.5 text-xs text-text-secondary">
              异常 {focusedExceptions.length} 条，待处理 {unresolvedCount} 条
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-5">
            <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
              <div className="text-xs text-text-muted">执行状态</div>
              <div className="mt-1 text-sm font-medium text-text-primary">{statusLabel(focusedRun.status)}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
              <div className="text-xs text-text-muted">数据就绪</div>
              <div className="mt-1 text-sm font-medium text-text-primary">{focusedRun.dataReady}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
              <div className="text-xs text-text-muted">闭环状态</div>
              <div className="mt-1 text-sm font-medium text-text-primary">{focusedRun.closureStatus}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
              <div className="text-xs text-text-muted">触发方式</div>
              <div className="mt-1 text-sm font-medium text-text-primary">{triggerModeLabel(focusedRun.triggerMode)}</div>
            </div>
            <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
              <div className="text-xs text-text-muted">开始 / 完成</div>
              <div className="mt-1 text-sm font-medium text-text-primary">{focusedRun.startedAt}</div>
              <div className="mt-0.5 text-sm font-medium text-text-primary">{focusedRun.finishedAt}</div>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {exceptionError && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                {exceptionError}
              </div>
            )}

            {loadingExceptionsRunId === focusedRun.id && (
              <div className="rounded-2xl border border-border px-4 py-3 text-sm text-text-secondary">
                正在加载异常列表...
              </div>
            )}

            {focusedExceptions.length > 0 ? (
              focusedExceptions.map((exception) => (
                <div
                  key={exception.id}
                  className="rounded-2xl border border-border bg-surface-secondary px-4 py-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">{exception.type}</div>
                    <div className="rounded-full bg-surface px-2.5 py-1 text-xs text-text-secondary">
                      {exception.handlingStatus}
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-text-secondary">{exception.summary}</p>
                  <div className="mt-3 grid gap-2 text-xs text-text-secondary md:grid-cols-3">
                    <div>责任人：{exception.owner}</div>
                    <div>催办状态：{exception.reminderStatus}</div>
                    <div>最新反馈：{exception.feedback}</div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={exceptionActionId === exception.id}
                      onClick={() => {
                        if (!focusedRun) return;
                        void onRemindException(exception.id, focusedRun.id);
                      }}
                      className="inline-flex items-center gap-1 rounded-lg border border-sky-200 px-2.5 py-1.5 text-xs text-sky-700 transition-colors hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {exceptionActionId === exception.id ? '处理中...' : '发送催办'}
                    </button>
                    <button
                      type="button"
                      disabled={exceptionActionId === exception.id}
                      onClick={() => {
                        if (!focusedRun) return;
                        void onSyncException(exception.id, focusedRun.id);
                      }}
                      className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      同步状态
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
                当前批次暂无异常数据。
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
