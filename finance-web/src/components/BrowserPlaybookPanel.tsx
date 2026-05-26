import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCopy,
  Eye,
  Loader2,
  MonitorSmartphone,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';

import type { BrowserPlaybookTaskDetail, DataSourceListItem } from '../types';
import type { ReactNode } from 'react';
import { parsePlaybookJsonInput } from '../utils/playbookJsonInput';

interface BrowserPlaybookPanelProps {
  authToken: string | null;
  sources?: DataSourceListItem[];
  loadingSources?: boolean;
  openCreateSignal?: number;
  onRegistered?: () => void | Promise<void>;
}

interface BrowserCollectionRegistrationResponse {
  success: boolean;
  status?: string;
  source_id?: string;
  verification_sync_job_id?: string;
  verification_biz_date?: string;
  message?: string;
  detail?: string;
  error?: string;
}

interface BrowserSyncJobResponse {
  success?: boolean;
  job?: Record<string, unknown> | null;
  detail?: string;
  error?: string;
  message?: string;
}

interface BrowserPlaybookFinalizeResponse {
  success?: boolean;
  browser_fail_reason?: string;
  error_message?: string;
  message?: string;
  detail?: string;
  error?: string;
}

interface BrowserPlaybookDetailResponse extends BrowserPlaybookTaskDetail {
  success?: boolean;
  record_count?: number;
  detail?: string;
  error?: string;
}

interface BrowserCollectionFormState {
  title: string;
  credentialUsername: string;
  credentialPassword: string;
  playbookBodyText: string;
}

interface BrowserCollectionRow {
  source: DataSourceListItem;
  title: string;
  status: string;
  taskStatus: string;
  taskLabel: string;
  taskError: string;
  taskUpdatedAt: string;
  updatedAt: string;
}

type VerificationStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed' | 'finalizing' | 'finalized';

interface DetailState {
  loading: boolean;
  error: string;
  detail: BrowserPlaybookTaskDetail | null;
  copied: boolean;
}

interface VerificationState {
  syncJobId: string;
  bizDate: string;
  status: VerificationStatus;
  message: string;
  errorMessage: string;
}

const emptyForm: BrowserCollectionFormState = {
  title: '',
  credentialUsername: '',
  credentialPassword: '',
  playbookBodyText: '',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function registrationTitle(source: DataSourceListItem): string {
  return text(source.metadata?.registration_title) || source.name || source.code || '未命名浏览器采集';
}

function statusLabel(status: string): string {
  if (status === 'active') return '已激活';
  if (status === 'disabled') return '停用';
  if (status === 'draft') return '草稿';
  if (status === 'published') return '已发布';
  if (status === 'unpublished') return '未发布';
  return status || '未知';
}

function taskStatusLabel(source: DataSourceListItem): string {
  const verification = source.browser_verification || {};
  const jobStatus = text(verification.job_status).toLowerCase();
  if (jobStatus === 'success' || jobStatus === 'completed') return '成功';
  if (['failed', 'error'].includes(jobStatus)) return '失败';
  if (['cancelled', 'canceled'].includes(jobStatus)) return '已取消';
  if (jobStatus === 'running') return '运行中';
  if (['queued', 'pending'].includes(jobStatus)) return '等待中';
  if (jobStatus === 'waiting_human_verification') return '待人工验证';
  if (jobStatus === 'resuming') return '恢复中';
  return '未记录';
}

function taskStatusClass(label: string): string {
  if (label === '失败' || label === '已取消') return 'bg-red-50 text-red-700';
  if (label === '成功') return 'bg-emerald-50 text-emerald-700';
  if (['运行中', '等待中', '待人工验证', '恢复中'].includes(label)) return 'bg-blue-50 text-blue-700';
  return 'bg-surface-secondary text-text-secondary';
}

function taskError(source: DataSourceListItem): string {
  const verification = source.browser_verification || {};
  const reason = text(verification.browser_fail_reason);
  const message = text(verification.error_message) || text(source.last_error_message);
  if (reason && message && !message.startsWith(`${reason}:`)) return `${reason}: ${message}`;
  return message || reason;
}

function taskUpdatedAt(source: DataSourceListItem): string {
  const verification = source.browser_verification || {};
  return text(verification.completed_at) || text(verification.updated_at);
}

function formatDateTime(value: string): string {
  if (!value) return '未记录';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function verificationStatusLabel(status: VerificationStatus): string {
  if (status === 'pending') return '验证任务已创建';
  if (status === 'running') return '正在执行浏览器验证';
  if (status === 'success') return '浏览器验证通过';
  if (status === 'finalizing') return '正在激活浏览器采集';
  if (status === 'finalized') return '浏览器采集已激活';
  if (status === 'failed') return '浏览器验证失败';
  return '';
}

function syncJobStatus(job: Record<string, unknown> | null | undefined): string {
  return text(job?.job_status) || text(job?.status);
}

function syncJobError(job: Record<string, unknown> | null | undefined): string {
  const reason = text(job?.browser_fail_reason);
  const message = text(job?.error_message) || text(job?.message);
  if (reason && message && !message.startsWith(`${reason}:`)) return `${reason}: ${message}`;
  return message || reason;
}

function prettyJson(value: unknown): string {
  if (value === undefined || value === null || value === '') return '未记录';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const BROWSER_DETAIL_RECORD_LIMIT = 100;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function verificationIsBusy(status: VerificationStatus): boolean {
  return ['pending', 'running', 'success', 'finalizing'].includes(status);
}

export function BrowserPlaybookPanel({
  authToken,
  sources = [],
  loadingSources = false,
  openCreateSignal = 0,
  onRegistered,
}: BrowserPlaybookPanelProps) {
  const authHeaders = useMemo(
    () => ({
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    }),
    [authToken],
  );

  const rows = useMemo<BrowserCollectionRow[]>(
    () =>
      sources
        .filter((source) => source.source_kind === 'browser_playbook')
        .map((source) => ({
          source,
          title: registrationTitle(source),
          status: source.status || source.health_status || 'unknown',
          taskStatus: text(source.browser_verification?.job_status),
          taskLabel: taskStatusLabel(source),
          taskError: taskError(source),
          taskUpdatedAt: taskUpdatedAt(source),
          updatedAt: source.updated_at || source.last_checked_at || '',
        })),
    [sources],
  );

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState<BrowserCollectionFormState>(emptyForm);
  const [submitError, setSubmitError] = useState('');
  const [submitWarning, setSubmitWarning] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [selectedRow, setSelectedRow] = useState<BrowserCollectionRow | null>(null);
  const [detailState, setDetailState] = useState<DetailState>({
    loading: false,
    error: '',
    detail: null,
    copied: false,
  });
  const [actionBusy, setActionBusy] = useState('');
  const [actionError, setActionError] = useState('');
  const [actionNotice, setActionNotice] = useState('');
  const [verification, setVerification] = useState<VerificationState>({
    syncJobId: '',
    bizDate: '',
    status: 'idle',
    message: '',
    errorMessage: '',
  });

  useEffect(() => {
    if (openCreateSignal <= 0) return;
    setForm(emptyForm);
    setSubmitError('');
    setSubmitWarning('');
    setVerification({ syncJobId: '', bizDate: '', status: 'idle', message: '', errorMessage: '' });
    setIsCreateOpen(true);
  }, [openCreateSignal]);

  const finalizeRegistration = useCallback(
    async (syncJobId: string) => {
      setVerification((prev) => ({
        ...prev,
        status: 'finalizing',
        message: verificationStatusLabel('finalizing'),
        errorMessage: '',
      }));
      const response = await fetch('/api/data-sources/browser-playbook/finalize', {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ verification_sync_job_id: syncJobId }),
      });
      const body = (await response.json().catch(() => ({}))) as BrowserPlaybookFinalizeResponse;
      if (!response.ok || !body.success) {
        const message = String(
          body.detail || body.error_message || body.error || body.message || '浏览器采集激活失败',
        );
        setVerification((prev) => ({
          ...prev,
          status: 'failed',
          message: verificationStatusLabel('failed'),
          errorMessage: message,
        }));
        return;
      }
      setVerification((prev) => ({
        ...prev,
        status: 'finalized',
        message: String(body.message || verificationStatusLabel('finalized')),
        errorMessage: '',
      }));
      await onRegistered?.();
    },
    [authHeaders, onRegistered],
  );

  const pollVerificationJob = useCallback(
    async (syncJobId: string) => {
      await delay(50);
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const response = await fetch(`/api/sync-jobs/${encodeURIComponent(syncJobId)}`, {
          headers: authHeaders,
        });
        const body = (await response.json().catch(() => ({}))) as BrowserSyncJobResponse;
        if (!response.ok || !body.success) {
          throw new Error(String(body.detail || body.error || body.message || '获取验证任务状态失败'));
        }

        const job = isRecord(body.job) ? body.job : null;
        const status = syncJobStatus(job).toLowerCase();
        if (status === 'success' || status === 'completed') {
          setVerification((prev) => ({
            ...prev,
            status: 'success',
            message: verificationStatusLabel('success'),
            errorMessage: '',
          }));
          await finalizeRegistration(syncJobId);
          return;
        }
        if (['failed', 'error', 'cancelled', 'canceled'].includes(status)) {
          setVerification((prev) => ({
            ...prev,
            status: 'failed',
            message: verificationStatusLabel('failed'),
            errorMessage: syncJobError(job) || '浏览器验证失败',
          }));
          return;
        }

        setVerification((prev) => ({
          ...prev,
          status: status === 'running' ? 'running' : 'pending',
          message: status === 'running' ? verificationStatusLabel('running') : verificationStatusLabel('pending'),
          errorMessage: '',
        }));
        await delay(2000);
      }
      setVerification((prev) => ({
        ...prev,
        status: 'failed',
        message: verificationStatusLabel('failed'),
        errorMessage: '验证任务超时，请稍后刷新查看任务状态。',
      }));
    },
    [authHeaders, finalizeRegistration],
  );

  const pollRetryJob = useCallback(
    async (syncJobId: string) => {
      await delay(50);
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const response = await fetch(`/api/sync-jobs/${encodeURIComponent(syncJobId)}`, {
          headers: authHeaders,
        });
        const body = (await response.json().catch(() => ({}))) as BrowserSyncJobResponse;
        if (!response.ok || !body.success) {
          throw new Error(String(body.detail || body.error || body.message || '获取浏览器任务状态失败'));
        }

        const job = isRecord(body.job) ? body.job : null;
        const status = syncJobStatus(job).toLowerCase();
        if (status === 'success' || status === 'completed') {
          setActionNotice(`浏览器任务已完成（任务ID：${syncJobId}）`);
          await onRegistered?.();
          return;
        }
        if (['failed', 'error', 'cancelled', 'canceled'].includes(status)) {
          setActionError(syncJobError(job) || '浏览器任务执行失败');
          setActionNotice('');
          await onRegistered?.();
          return;
        }

        if (status === 'running') {
          setActionNotice(`浏览器任务运行中（任务ID：${syncJobId}）`);
        } else {
          setActionNotice(`浏览器任务等待采集机执行（任务ID：${syncJobId}）`);
        }
        await delay(2000);
      }
      setActionError('浏览器任务执行超时，请稍后刷新查看任务状态。');
      setActionNotice('');
    },
    [authHeaders, onRegistered],
  );

  const submitRegistration = useCallback(async () => {
    if (!authToken) {
      setSubmitError('未登录');
      return;
    }
    const title = form.title.trim();
    const credentialUsername = form.credentialUsername.trim();
    const credentialPassword = form.credentialPassword;
    if (!title) {
      setSubmitError('标题不能为空');
      return;
    }
    if (!credentialUsername || !credentialPassword) {
      setSubmitError('登录账号和密码不能为空');
      return;
    }

    const parsedPlaybook = parsePlaybookJsonInput(form.playbookBodyText);
    if (parsedPlaybook.error) {
      setSubmitWarning('');
      setSubmitError(`playbook_body JSON 解析失败: ${parsedPlaybook.error}`);
      return;
    }
    const playbookBody = parsedPlaybook.value;
    if (!isRecord(playbookBody) || Object.keys(playbookBody).length === 0) {
      setSubmitWarning('');
      setSubmitError('playbook_body JSON 必须是非空对象');
      return;
    }

    setSubmitting(true);
    setSubmitError('');
    setVerification({ syncJobId: '', bizDate: '', status: 'idle', message: '', errorMessage: '' });
    setSubmitWarning(
      parsedPlaybook.repairCount > 0
        ? `已自动修复 ${parsedPlaybook.repairCount} 处 playbook JSON 字符串内换行/控制字符`
        : '',
    );
    try {
      const response = await fetch('/api/data-sources/browser-playbook/registrations', {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          title,
          credential_username: credentialUsername,
          credential_password: credentialPassword,
          playbook_body: playbookBody,
        }),
      });
      const body = (await response.json().catch(() => ({}))) as BrowserCollectionRegistrationResponse;
      if (!response.ok || !body.success) {
        setSubmitError(String(body.detail || body.error || body.message || '浏览器采集注册失败'));
        return;
      }
      const syncJobId = String(body.verification_sync_job_id || '');
      if (!syncJobId) {
        setForm(emptyForm);
        setIsCreateOpen(false);
        setSubmitWarning('');
        await onRegistered?.();
        return;
      }
      setVerification({
        syncJobId,
        bizDate: String(body.verification_biz_date || ''),
        status: 'pending',
        message: String(body.message || verificationStatusLabel('pending')),
        errorMessage: '',
      });
      void pollVerificationJob(syncJobId).catch((error) => {
        setVerification((prev) => ({
          ...prev,
          status: 'failed',
          message: verificationStatusLabel('failed'),
          errorMessage: error instanceof Error ? error.message : '浏览器验证失败',
        }));
      });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '浏览器采集注册失败');
    } finally {
      setSubmitting(false);
    }
  }, [authHeaders, authToken, form, onRegistered, pollVerificationJob]);

  const retryBrowserTask = useCallback(
    async (row: BrowserCollectionRow) => {
      if (!authToken) {
        setActionError('未登录');
        return;
      }
      const actionId = `retry:${row.source.id}`;
      setActionBusy(actionId);
      setActionError('');
      setActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${encodeURIComponent(row.source.id)}/browser-playbook/retry`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ force_collection: true }),
        });
        const body = (await response.json().catch(() => ({}))) as BrowserCollectionRegistrationResponse;
        if (!response.ok || !body.success) {
          throw new Error(String(body.detail || body.error || body.message || '浏览器任务重试失败'));
        }
        const syncJobId = String(body.verification_sync_job_id || '');
        const message = String(body.message || '浏览器任务已重新下发到采集机，请等待任务状态更新');
        setActionNotice(syncJobId ? `${message}（任务ID：${syncJobId}）` : message);
        await onRegistered?.();
        if (syncJobId) {
          void pollRetryJob(syncJobId).catch((error) => {
            setActionError(error instanceof Error ? error.message : '浏览器任务执行失败');
            setActionNotice('');
          });
        }
      } catch (error) {
        setActionError(error instanceof Error ? error.message : '浏览器任务重试失败');
      } finally {
        setActionBusy('');
      }
    },
    [authHeaders, authToken, onRegistered, pollRetryJob],
  );

  const openTaskDetail = useCallback(
    async (row: BrowserCollectionRow) => {
      setSelectedRow(row);
      setDetailState({ loading: true, error: '', detail: null, copied: false });
      if (!authToken) {
        setDetailState({ loading: false, error: '未登录', detail: null, copied: false });
        return;
      }
      try {
        const response = await fetch(
          `/api/data-sources/${encodeURIComponent(row.source.id)}/browser-playbook/detail?record_limit=${BROWSER_DETAIL_RECORD_LIMIT}`,
          { headers: authHeaders },
        );
        const body = (await response.json().catch(() => ({}))) as BrowserPlaybookDetailResponse;
        if (!response.ok || !body.success) {
          throw new Error(String(body.detail || body.error || body.message || '获取浏览器任务详情失败'));
        }
        setDetailState({
          loading: false,
          error: '',
          detail: {
            source: body.source,
            browser_verification: body.browser_verification,
            record_count: body.record_count,
            latest_records: body.latest_records || [],
            playbook: body.playbook || {},
            credential: body.credential || {},
            message: body.message,
          },
          copied: false,
        });
      } catch (error) {
        setDetailState({
          loading: false,
          error: error instanceof Error ? error.message : '获取浏览器任务详情失败',
          detail: null,
          copied: false,
        });
      }
    },
    [authHeaders, authToken],
  );

  const closeTaskDetail = useCallback(() => {
    setSelectedRow(null);
    setDetailState({ loading: false, error: '', detail: null, copied: false });
  }, []);

  const copyPlaybook = useCallback(async () => {
    const playbookBody = detailState.detail?.playbook?.playbook_body || {};
    try {
      await navigator.clipboard.writeText(prettyJson(playbookBody));
      setDetailState((prev) => ({ ...prev, copied: true }));
    } catch {
      setDetailState((prev) => ({ ...prev, error: '复制 Playbook 失败' }));
    }
  }, [detailState.detail?.playbook?.playbook_body]);

  const deleteBrowserTask = useCallback(
    async (row: BrowserCollectionRow) => {
      if (!authToken) {
        setActionError('未登录');
        return;
      }
      const confirmed = window.confirm(`确认删除“${row.title || '未命名浏览器任务'}”？此操作不可恢复。`);
      if (!confirmed) return;

      const actionId = `delete:${row.source.id}`;
      setActionBusy(actionId);
      setActionError('');
      setActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${encodeURIComponent(row.source.id)}`, {
          method: 'DELETE',
          headers: authHeaders,
        });
        const body = (await response.json().catch(() => ({}))) as BrowserCollectionRegistrationResponse;
        if (!response.ok) {
          throw new Error(String(body.detail || body.error || body.message || '浏览器任务删除失败'));
        }
        setActionNotice(String(body.message || '浏览器任务已删除'));
        setSelectedRow((current) => (current?.source.id === row.source.id ? null : current));
        await onRegistered?.();
      } catch (error) {
        setActionError(error instanceof Error ? error.message : '浏览器任务删除失败');
      } finally {
        setActionBusy('');
      }
    },
    [authHeaders, authToken, onRegistered],
  );

  const verificationBusy = verificationIsBusy(verification.status);

  return (
    <>
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-text-primary">浏览器任务列表</h3>
            <p className="mt-1 text-sm text-text-secondary">
              展示已注册的浏览器任务，点击一条记录查看注册信息。
            </p>
          </div>
          <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-xs text-text-secondary">
            共 {rows.length} 条
          </span>
        </div>

        {actionError && (
          <div className="mb-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}
        {actionNotice && (
          <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {actionNotice}
          </div>
        )}

        {loadingSources && rows.length === 0 ? (
          <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载浏览器任务
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
            暂无浏览器任务
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="min-w-[960px] w-full table-fixed text-sm">
              <colgroup>
                <col className="w-[30%]" />
                <col className="w-[16%]" />
                <col className="w-[14%]" />
                <col className="w-[18%]" />
                <col className="w-[22%]" />
              </colgroup>
              <thead className="bg-surface-secondary text-left text-text-secondary">
                <tr>
                  <th className="px-4 py-3 font-medium">标题</th>
                  <th className="px-4 py-3 font-medium">任务状态</th>
                  <th className="px-4 py-3 font-medium">启用状态</th>
                  <th className="px-4 py-3 font-medium">最近更新</th>
                  <th className="px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.source.id} className="border-t border-border-subtle">
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <MonitorSmartphone className="h-4 w-4 shrink-0 text-cyan-600" />
                        <span className="truncate font-medium text-text-primary">{row.title}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-1 text-xs ${taskStatusClass(row.taskLabel)}`}
                      >
                        {row.taskLabel}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{statusLabel(row.status)}</td>
                    <td className="px-4 py-3 text-text-secondary">{formatDateTime(row.updatedAt)}</td>
                    <td className="px-4 py-3">
                      <div className="flex min-w-[204px] items-center gap-2 whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => void openTaskDetail(row)}
                          disabled={Boolean(actionBusy)}
                          aria-label={`详情 ${row.title}`}
                          className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-tertiary disabled:opacity-60"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          详情
                        </button>
                        <button
                          type="button"
                          onClick={() => void retryBrowserTask(row)}
                          disabled={Boolean(actionBusy)}
                          aria-label={`重试 ${row.title}`}
                          className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-tertiary disabled:opacity-60"
                        >
                          {actionBusy === `retry:${row.source.id}` ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3.5 w-3.5" />
                          )}
                          重试
                        </button>
                        <button
                          type="button"
                          onClick={() => void deleteBrowserTask(row)}
                          disabled={Boolean(actionBusy)}
                          aria-label={`删除 ${row.title}`}
                          className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-red-100 bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60"
                        >
                          {actionBusy === `delete:${row.source.id}` ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {isCreateOpen && (
        <Dialog title="新增浏览器采集" onClose={() => setIsCreateOpen(false)}>
          <div className="space-y-4">
            <Field label="标题" value={form.title} onChange={(title) => setForm((prev) => ({ ...prev, title }))} />
            <div className="grid gap-3 md:grid-cols-2">
              <Field
                label="登录账号"
                value={form.credentialUsername}
                onChange={(credentialUsername) => setForm((prev) => ({ ...prev, credentialUsername }))}
              />
              <Field
                label="密码"
                type="password"
                value={form.credentialPassword}
                onChange={(credentialPassword) => setForm((prev) => ({ ...prev, credentialPassword }))}
              />
            </div>
            <PlaybookJsonEditor
              value={form.playbookBodyText}
              onChange={(playbookBodyText) => setForm((prev) => ({ ...prev, playbookBodyText }))}
            />

            {submitError && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{submitError}</span>
              </div>
            )}
            {submitWarning && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                {submitWarning}
              </div>
            )}
            {verification.status !== 'idle' && (
              <VerificationStatusPanel verification={verification} />
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                disabled={(submitting || verificationBusy) && verification.status !== 'finalized'}
                className="inline-flex items-center rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary disabled:opacity-60"
              >
                {verification.status === 'finalized' ? '关闭' : '取消'}
              </button>
              {verification.status !== 'finalized' && (
                <button
                  type="button"
                  onClick={() => void submitRegistration()}
                  disabled={submitting || verificationBusy}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
                >
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  注册
                </button>
              )}
            </div>
          </div>
        </Dialog>
      )}

      {selectedRow && (
        <Dialog title="浏览器任务详情" onClose={closeTaskDetail} maxWidthClassName="max-w-4xl">
          <div className="space-y-4">
            <section className="space-y-3 rounded-xl border border-border bg-surface-secondary p-3">
              <DetailItem label="标题" value={selectedRow.title} />
              <DetailItem label="启用状态" value={statusLabel(selectedRow.status)} />
              <DetailItem label="任务状态" value={selectedRow.taskLabel} />
              {selectedRow.source.browser_verification?.sync_job_id && (
                <DetailItem label="任务ID" value={selectedRow.source.browser_verification.sync_job_id} />
              )}
              {selectedRow.taskUpdatedAt && (
                <DetailItem label="最近任务" value={formatDateTime(selectedRow.taskUpdatedAt)} />
              )}
              {selectedRow.taskError && (
                <DetailItem label="失败原因" value={selectedRow.taskError} />
              )}
              <DetailItem label="最近更新" value={formatDateTime(selectedRow.updatedAt)} />
              {selectedRow.source.description && (
                <DetailItem label="说明" value={selectedRow.source.description} />
              )}
            </section>
            {detailState.loading && (
              <div className="flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在加载详情
              </div>
            )}
            {detailState.error && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{detailState.error}</span>
              </div>
            )}
            {detailState.detail && (
              <BrowserTaskDetailSections
                detail={detailState.detail}
                copied={detailState.copied}
                onCopyPlaybook={() => void copyPlaybook()}
              />
            )}
          </div>
        </Dialog>
      )}
    </>
  );
}

function VerificationStatusPanel({ verification }: { verification: VerificationState }) {
  const isFailed = verification.status === 'failed';
  const isDone = verification.status === 'finalized';
  const isBusy = !isFailed && !isDone;
  return (
    <div
      className={`rounded-xl border px-3 py-2 text-sm ${
        isFailed
          ? 'border-red-200 bg-red-50 text-red-700'
          : isDone
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'border-blue-200 bg-blue-50 text-blue-700'
      }`}
    >
      <div className="flex items-start gap-2">
        {isBusy ? (
          <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
        ) : isDone ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        <div className="min-w-0">
          <p className="font-medium">{verification.message || verificationStatusLabel(verification.status)}</p>
          {verification.syncJobId && (
            <p className="mt-1 break-all text-xs opacity-80">验证任务：{verification.syncJobId}</p>
          )}
          {verification.bizDate && (
            <p className="mt-1 text-xs opacity-80">验证日期：{verification.bizDate}</p>
          )}
          {verification.errorMessage && (
            <p className="mt-1 break-words text-xs">{verification.errorMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function recordValue(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return prettyJson(value);
}

function playbookOutputColumns(detail: BrowserPlaybookTaskDetail): string[] {
  const output = detail.playbook?.playbook_body?.output;
  if (!isRecord(output) || !Array.isArray(output.columns)) return [];
  const names: string[] = [];
  for (const column of output.columns) {
    if (!isRecord(column)) continue;
    const name = text(column.name).trim();
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

function browserRecordColumns(detail: BrowserPlaybookTaskDetail): string[] {
  const records = detail.latest_records || [];
  const keys = new Set<string>();
  for (const record of records) {
    for (const key of Object.keys(record.payload || {})) {
      keys.add(key);
    }
  }
  const schemaColumns = playbookOutputColumns(detail).filter((key) => keys.has(key));
  const rest = Array.from(keys).filter((key) => !schemaColumns.includes(key));
  return [...schemaColumns, ...rest];
}

function BrowserRecordsTable({ detail }: { detail: BrowserPlaybookTaskDetail }) {
  const records = detail.latest_records || [];
  const columns = browserRecordColumns(detail);
  if (records.length === 0) {
    return <p className="text-sm text-text-secondary">暂无采集数据</p>;
  }
  if (columns.length === 0) {
    return <p className="text-sm text-text-secondary">暂无可展示字段</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border-subtle">
      <table aria-label="最新采集数据表" className="min-w-[1200px] w-full text-left text-xs">
        <thead className="bg-surface-secondary text-text-secondary">
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                {column}
              </th>
            ))}
            <th scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
              业务日期
            </th>
            <th scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
              采集时间
            </th>
          </tr>
        </thead>
        <tbody>
          {records.map((record, index) => (
            <tr key={record.id || `${record.item_key || 'record'}-${index}`} className="border-t border-border-subtle">
              {columns.map((column) => (
                <td key={column} className="max-w-[260px] whitespace-nowrap px-3 py-2 text-text-primary">
                  <span className="block overflow-hidden text-ellipsis">
                    {recordValue(record.payload?.[column]) || '—'}
                  </span>
                </td>
              ))}
              <td className="whitespace-nowrap px-3 py-2 text-text-secondary">{record.biz_date || '—'}</td>
              <td className="whitespace-nowrap px-3 py-2 text-text-secondary">
                {record.captured_at ? formatDateTime(record.captured_at) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BrowserTaskDetailSections({
  detail,
  copied,
  onCopyPlaybook,
}: {
  detail: BrowserPlaybookTaskDetail;
  copied: boolean;
  onCopyPlaybook: () => void;
}) {
  const records = detail.latest_records || [];
  const recordCount = typeof detail.record_count === 'number' ? detail.record_count : records.length;
  const playbookBody = detail.playbook?.playbook_body || {};
  const credential = detail.credential || {};

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-border bg-surface p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-text-primary">最新采集数据</h4>
          <span className="rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
            已加载 {records.length} / 共 {recordCount} 条
          </span>
        </div>
        <BrowserRecordsTable detail={detail} />
      </section>

      <section className="rounded-xl border border-border bg-surface p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-text-primary">Playbook</h4>
          <button
            type="button"
            onClick={onCopyPlaybook}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-tertiary"
          >
            <ClipboardCopy className="h-3.5 w-3.5" />
            复制 Playbook
          </button>
        </div>
        <div className="mb-3 grid gap-2 text-sm md:grid-cols-2">
          <DetailItem label="Playbook ID" value={detail.playbook?.playbook_id || ''} />
          <DetailItem label="版本" value={detail.playbook?.version || ''} />
          <DetailItem label="状态" value={statusLabel(detail.playbook?.status || '')} />
          <DetailItem label="最近更新" value={formatDateTime(detail.playbook?.updated_at || '')} />
        </div>
        {copied && (
          <div className="mb-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            Playbook 已复制
          </div>
        )}
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-secondary px-3 py-2 font-mono text-xs text-text-primary">
          {prettyJson(playbookBody)}
        </pre>
      </section>

      <section className="rounded-xl border border-border bg-surface p-3">
        <h4 className="mb-3 text-sm font-semibold text-text-primary">凭证</h4>
        <div className="space-y-2">
          <DetailItem label="登录账号" value={credential.username || ''} />
          <DetailItem label="密码状态" value={credential.password_saved ? '密码已保存' : '未保存'} />
        </div>
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="block text-sm font-medium text-text-primary">
      {label}
      <input
        aria-label={label}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none focus:border-blue-300"
      />
    </label>
  );
}

function PlaybookJsonEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const lineNumberRef = useRef<HTMLDivElement | null>(null);
  const lineCount = Math.max(1, value.split('\n').length);
  const lineNumbers = Array.from({ length: lineCount }, (_, index) => index + 1);

  return (
    <label className="block text-sm font-medium text-text-primary">
      playbook_body JSON
      <div className="mt-2 flex h-56 overflow-hidden rounded-xl border border-border bg-surface font-mono text-xs text-text-primary focus-within:border-blue-300">
        <div
          ref={lineNumberRef}
          aria-hidden="true"
          className="w-12 shrink-0 overflow-hidden border-r border-border-subtle bg-surface-secondary px-2 py-2 text-right leading-5 text-text-muted"
        >
          {lineNumbers.map((lineNumber) => (
            <div key={lineNumber} className="h-5">
              {lineNumber}
            </div>
          ))}
        </div>
        <textarea
          aria-label="playbook_body JSON"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onScroll={(event) => {
            if (lineNumberRef.current) {
              lineNumberRef.current.scrollTop = event.currentTarget.scrollTop;
            }
          }}
          className="h-full min-w-0 flex-1 resize-none overflow-auto bg-surface px-3 py-2 leading-5 text-text-primary outline-none"
          placeholder='{"schema_version":"1.0","steps":[]}'
          spellCheck={false}
        />
      </div>
    </label>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 text-sm md:grid-cols-[120px_minmax(0,1fr)]">
      <div className="font-medium text-text-primary">{label}</div>
      <div className="min-w-0 break-words text-text-secondary">{value || '未记录'}</div>
    </div>
  );
}

function Dialog({
  title,
  children,
  onClose,
  maxWidthClassName = 'max-w-2xl',
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  maxWidthClassName?: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`browser-playbook-dialog-${title}`}
        className={`flex max-h-[88vh] w-full ${maxWidthClassName} flex-col rounded-2xl border border-border bg-surface shadow-xl`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <h3 id={`browser-playbook-dialog-${title}`} className="text-base font-semibold text-text-primary">
            {title}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary hover:bg-surface-secondary"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
