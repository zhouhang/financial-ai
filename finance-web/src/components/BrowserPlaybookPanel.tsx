import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, MonitorSmartphone, X } from 'lucide-react';

import type { DataSourceListItem } from '../types';
import type { ReactNode } from 'react';

interface BrowserPlaybookPanelProps {
  authToken: string | null;
  sources?: DataSourceListItem[];
  openCreateSignal?: number;
  onRegistered?: () => void | Promise<void>;
}

interface BrowserCollectionRegistrationResponse {
  success: boolean;
  message?: string;
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
  updatedAt: string;
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
  if (status === 'active') return '启用';
  if (status === 'disabled') return '停用';
  if (status === 'draft') return '草稿';
  if (status === 'published') return '已发布';
  if (status === 'unpublished') return '未发布';
  return status || '未知';
}

function formatDateTime(value: string): string {
  if (!value) return '未记录';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export function BrowserPlaybookPanel({
  authToken,
  sources = [],
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
          updatedAt: source.updated_at || source.last_checked_at || '',
        })),
    [sources],
  );

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState<BrowserCollectionFormState>(emptyForm);
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [selectedRow, setSelectedRow] = useState<BrowserCollectionRow | null>(null);

  useEffect(() => {
    if (openCreateSignal <= 0) return;
    setForm(emptyForm);
    setSubmitError('');
    setIsCreateOpen(true);
  }, [openCreateSignal]);

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

    let playbookBody: unknown;
    try {
      playbookBody = JSON.parse(form.playbookBodyText || '{}');
    } catch (error) {
      setSubmitError(`playbook_body JSON 解析失败: ${error instanceof Error ? error.message : String(error)}`);
      return;
    }
    if (!isRecord(playbookBody) || Object.keys(playbookBody).length === 0) {
      setSubmitError('playbook_body JSON 必须是非空对象');
      return;
    }

    setSubmitting(true);
    setSubmitError('');
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
      const body = (await response.json().catch(() => ({}))) as BrowserCollectionRegistrationResponse & {
        detail?: string;
        error?: string;
      };
      if (!response.ok || !body.success) {
        setSubmitError(String(body.detail || body.error || body.message || '浏览器采集注册失败'));
        return;
      }
      setForm(emptyForm);
      setIsCreateOpen(false);
      await onRegistered?.();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '浏览器采集注册失败');
    } finally {
      setSubmitting(false);
    }
  }, [authHeaders, authToken, form, onRegistered]);

  return (
    <>
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-text-primary">浏览器采集列表</h3>
            <p className="mt-1 text-sm text-text-secondary">
              展示已注册的浏览器采集配置，点击一条记录查看注册信息。
            </p>
          </div>
          <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-xs text-text-secondary">
            共 {rows.length} 条
          </span>
        </div>

        {rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
            暂无浏览器采集配置
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="min-w-[720px] w-full table-fixed text-sm">
              <colgroup>
                <col className="w-[54%]" />
                <col className="w-[20%]" />
                <col className="w-[26%]" />
              </colgroup>
              <thead className="bg-surface-secondary text-left text-text-secondary">
                <tr>
                  <th className="px-4 py-3 font-medium">标题</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">最近更新</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.source.id} className="border-t border-border-subtle">
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setSelectedRow(row)}
                        className="flex max-w-full items-center gap-2 text-left font-medium text-text-primary hover:text-blue-600"
                      >
                        <MonitorSmartphone className="h-4 w-4 shrink-0 text-cyan-600" />
                        <span className="truncate">{row.title}</span>
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
                        {statusLabel(row.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{formatDateTime(row.updatedAt)}</td>
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
            <label className="block text-sm font-medium text-text-primary">
              playbook_body JSON
              <textarea
                aria-label="playbook_body JSON"
                value={form.playbookBodyText}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, playbookBodyText: event.target.value }))
                }
                className="mt-2 h-56 w-full rounded-xl border border-border bg-surface px-3 py-2 font-mono text-xs text-text-primary outline-none focus:border-blue-300"
                placeholder='{"schema_version":"1.0","steps":[]}'
              />
            </label>

            {submitError && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                disabled={submitting}
                className="inline-flex items-center rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary disabled:opacity-60"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void submitRegistration()}
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                注册
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {selectedRow && (
        <Dialog title="浏览器采集详情" onClose={() => setSelectedRow(null)}>
          <div className="space-y-4">
            <DetailItem label="标题" value={selectedRow.title} />
            <DetailItem label="状态" value={statusLabel(selectedRow.status)} />
            <DetailItem label="最近更新" value={formatDateTime(selectedRow.updatedAt)} />
            {selectedRow.source.description && (
              <DetailItem label="说明" value={selectedRow.source.description} />
            )}
          </div>
        </Dialog>
      )}
    </>
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
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`browser-playbook-dialog-${title}`}
        className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-2xl border border-border bg-surface shadow-xl"
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
