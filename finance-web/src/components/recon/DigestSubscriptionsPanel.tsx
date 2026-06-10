import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, RefreshCw, Save } from 'lucide-react';

import { collaborationProviderLabel } from '../../collaborationChannelConfig';
import type { CollaborationChannelListItem } from '../../types';
import { fetchReconAutoApi } from './autoApi';
import { cn } from './types';

type DigestView = 'boss' | 'finance';

interface DigestRecipientDraft {
  subscriptionId: string;
  name: string;
  userId: string;
}

interface OwnerCandidate {
  display_name: string;
  identifier: string;
  disambiguation_label?: string;
}

interface DigestSubscriptionsPanelProps {
  authToken?: string | null;
}

const DIGEST_VIEWS: Array<{ view: DigestView; label: string; nameLabel: string }> = [
  { view: 'boss', label: '老板日报', nameLabel: '老板姓名' },
  { view: 'finance', label: '财务日报', nameLabel: '财务姓名' },
];

function createEmptyRecipient(): DigestRecipientDraft {
  return {
    subscriptionId: '',
    name: '',
    userId: '',
  };
}

function createEmptyRecipients(): Record<DigestView, DigestRecipientDraft> {
  return {
    boss: createEmptyRecipient(),
    finance: createEmptyRecipient(),
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeView(value: unknown): DigestView | null {
  const text = asText(value).toLowerCase();
  return text === 'boss' || text === 'finance' ? text : null;
}

function normalizeChannel(value: unknown): CollaborationChannelListItem | null {
  const raw = asRecord(value);
  const id = asText(raw.id);
  const provider = asText(raw.provider);
  if (!id || !provider) return null;
  return {
    id,
    provider,
    channel_code: asText(raw.channel_code),
    name: asText(raw.name),
    is_default: Boolean(raw.is_default),
    is_enabled: raw.is_enabled !== false,
    extra: asRecord(raw.extra),
  };
}

function normalizeCandidate(value: unknown): OwnerCandidate | null {
  const raw = asRecord(value);
  const identifier = asText(raw.identifier);
  if (!identifier) return null;
  return {
    identifier,
    display_name: asText(raw.display_name),
    disambiguation_label: asText(raw.disambiguation_label),
  };
}

function isPresent<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

function mapSubscription(value: unknown): { view: DigestView; recipient: DigestRecipientDraft; channelId: string } | null {
  const raw = asRecord(value);
  const view = normalizeView(raw.view);
  if (!view) return null;
  const recipient = asRecord(raw.recipient_json);
  return {
    view,
    recipient: {
      subscriptionId: asText(raw.id || raw.subscription_id),
      name: asText(recipient.display_name || recipient.name),
      userId: asText(recipient.user_id || recipient.identifier),
    },
    channelId: asText(raw.channel_config_id),
  };
}

function resolveErrorMessage(data: Record<string, unknown>, fallback: string): string {
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  const message = data.message || data.error;
  return typeof message === 'string' && message.trim() ? message : fallback;
}

function channelLabel(channel: CollaborationChannelListItem): string {
  return `${collaborationProviderLabel(channel.provider)} - ${channel.name || channel.channel_code || '默认通道'}`;
}

function recipientPayload(recipient: DigestRecipientDraft): Record<string, unknown> {
  return {
    user_id: recipient.userId,
    display_name: recipient.name,
  };
}

export default function DigestSubscriptionsPanel({ authToken }: DigestSubscriptionsPanelProps) {
  const [channels, setChannels] = useState<CollaborationChannelListItem[]>([]);
  const [channelId, setChannelId] = useState('');
  const [recipients, setRecipients] = useState<Record<DigestView, DigestRecipientDraft>>(() => createEmptyRecipients());
  const [candidatesByView, setCandidatesByView] = useState<Record<DigestView, OwnerCandidate[]>>({
    boss: [],
    finance: [],
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const selectedChannel = useMemo(
    () => channels.find((channel) => channel.id === channelId) || null,
    [channels, channelId],
  );

  const updateRecipient = useCallback((view: DigestView, patch: Partial<DigestRecipientDraft>) => {
    setRecipients((current) => ({
      ...current,
      [view]: {
        ...current[view],
        ...patch,
      },
    }));
    setCandidatesByView((current) => ({ ...current, [view]: [] }));
    setNotice('');
    setError('');
  }, []);

  const loadState = useCallback(async () => {
    if (!authToken) {
      setChannels([]);
      setChannelId('');
      setRecipients(createEmptyRecipients());
      setNotice('登录后可配置老板和财务日报接收人。');
      setError('');
      return;
    }

    setLoading(true);
    setError('');
    setNotice('');

    try {
      const [channelResponse, subscriptionResponse] = await Promise.all([
        fetch('/api/collaboration-channels', {
          headers: { Authorization: `Bearer ${authToken}` },
        }),
        fetchReconAutoApi('/digest-subscriptions?period=daily&view=', {
          headers: { Authorization: `Bearer ${authToken}` },
        }),
      ]);

      const channelData = asRecord(await channelResponse.json().catch(() => ({})));
      if (!channelResponse.ok) {
        throw new Error(resolveErrorMessage(channelData, '协作通道加载失败'));
      }
      const loadedChannels = asList(channelData.channels)
        .map(normalizeChannel)
        .filter(isPresent)
        .filter((item) => item.is_enabled !== false) as CollaborationChannelListItem[];
      setChannels(loadedChannels);

      const subscriptionData = asRecord(await subscriptionResponse.json().catch(() => ({})));
      if (!subscriptionResponse.ok) {
        throw new Error(resolveErrorMessage(subscriptionData, '日报订阅加载失败'));
      }

      const nextRecipients = createEmptyRecipients();
      let existingChannelId = '';
      asList(subscriptionData.subscriptions).forEach((item) => {
        const mapped = mapSubscription(item);
        if (!mapped) return;
        nextRecipients[mapped.view] = mapped.recipient;
        if (!existingChannelId && mapped.channelId) {
          existingChannelId = mapped.channelId;
        }
      });
      setRecipients(nextRecipients);

      const defaultChannel = loadedChannels.find((channel) => channel.is_default) || loadedChannels[0] || null;
      setChannelId(
        loadedChannels.some((channel) => channel.id === existingChannelId)
          ? existingChannelId
          : defaultChannel?.id || '',
      );
      if (loadedChannels.length === 0) {
        setError('当前公司还没有可用协作通道，请先在数据连接中配置。');
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '日报订阅加载失败');
    } finally {
      setLoading(false);
    }
  }, [authToken]);

  useEffect(() => {
    void loadState();
  }, [loadState]);

  const resolveRecipient = useCallback(
    async (view: DigestView): Promise<DigestRecipientDraft | null> => {
      const current = recipients[view];
      const name = current.name.trim();
      if (!name) {
        return { ...current, name: '', userId: '' };
      }
      if (current.userId.trim()) {
        return { ...current, name, userId: current.userId.trim() };
      }

      const response = await fetchReconAutoApi('/owner-candidates/search', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: name,
          channel_config_id: channelId,
        }),
      });
      const data = asRecord(await response.json().catch(() => ({})));
      if (!response.ok) {
        throw new Error(resolveErrorMessage(data, `${DIGEST_VIEWS.find((item) => item.view === view)?.nameLabel || '姓名'}校验失败`));
      }

      const candidates = asList(data.candidates).map(normalizeCandidate).filter(isPresent);
      if (candidates.length === 0) {
        throw new Error(resolveErrorMessage(data, `未在${selectedChannel ? `「${channelLabel(selectedChannel)}」` : '当前通道'}组织中找到“${name}”`));
      }
      if (candidates.length > 1) {
        setCandidatesByView((currentCandidates) => ({ ...currentCandidates, [view]: candidates }));
        throw new Error(`“${name}”匹配到 ${candidates.length} 位同名成员，请选择明确候选人后再保存。`);
      }

      const [candidate] = candidates;
      const resolved = {
        ...current,
        name: candidate.display_name || name,
        userId: candidate.identifier,
      };
      setRecipients((currentRecipients) => ({ ...currentRecipients, [view]: resolved }));
      return resolved;
    },
    [authToken, channelId, recipients, selectedChannel],
  );

  const saveSubscription = useCallback(
    async (view: DigestView, recipient: DigestRecipientDraft) => {
      const response = await fetchReconAutoApi('/digest-subscriptions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          subscription_id: recipient.subscriptionId,
          period: 'daily',
          view,
          enabled: Boolean(recipient.name && recipient.userId),
          channel_config_id: channelId,
          target_type: 'user',
          recipient_json: recipientPayload(recipient),
          scope: { mode: 'company_all' },
        }),
      });
      const data = asRecord(await response.json().catch(() => ({})));
      if (!response.ok) {
        throw new Error(resolveErrorMessage(data, `${DIGEST_VIEWS.find((item) => item.view === view)?.label || '日报'}保存失败`));
      }
      const mapped = mapSubscription(data.subscription);
      if (mapped) {
        setRecipients((current) => ({ ...current, [view]: mapped.recipient }));
      }
    },
    [authToken, channelId],
  );

  const saveAll = useCallback(async () => {
    if (!authToken) {
      setError('请先登录后保存日报订阅配置。');
      return;
    }
    if (!channelId) {
      setError('请先选择协作通道。');
      return;
    }

    setSaving(true);
    setError('');
    setNotice('');
    setCandidatesByView({ boss: [], finance: [] });

    try {
      const resolvedBoss = await resolveRecipient('boss');
      const resolvedFinance = await resolveRecipient('finance');
      if (!resolvedBoss || !resolvedFinance) return;

      await Promise.all([
        saveSubscription('boss', resolvedBoss),
        saveSubscription('finance', resolvedFinance),
      ]);
      setNotice('老板和财务日报接收人已保存。');
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '日报订阅保存失败');
    } finally {
      setSaving(false);
    }
  }, [authToken, channelId, resolveRecipient, saveSubscription]);

  return (
    <section className="flex flex-col gap-4" aria-labelledby="digest-subscriptions-title">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[28px] border border-border bg-surface px-5 py-4 shadow-sm">
        <div>
          <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">日报订阅</p>
          <h2 id="digest-subscriptions-title" className="mt-1 text-base font-semibold text-text-primary">
            老板 / 财务日报接收人
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            选择当前公司的协作通道，填写姓名后保存；系统会先在该通道组织内核验成员。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadState()}
          disabled={loading}
          className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-border bg-surface px-3 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          刷新
        </button>
      </div>

      {error ? (
        <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {notice ? (
        <div className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <Check className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{notice}</span>
        </div>
      ) : null}

      <form
        aria-label="日报接收人配置"
        onSubmit={(event) => {
          event.preventDefault();
          void saveAll();
        }}
        className="rounded-[28px] border border-border bg-surface px-5 py-5 shadow-sm"
      >
        <div className="grid gap-5">
          <label className="grid gap-2 text-sm font-medium text-text-primary">
            <span>发送通道</span>
            <select
              value={channelId}
              onChange={(event) => {
                setChannelId(event.target.value);
                setRecipients((current) => ({
                  boss: { ...current.boss, userId: '' },
                  finance: { ...current.finance, userId: '' },
                }));
                setCandidatesByView({ boss: [], finance: [] });
                setNotice('');
                setError('');
              }}
              disabled={loading || channels.length === 0}
              className="h-11 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 pr-9 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-surface-secondary"
            >
              <option value="">请选择协作通道</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channelLabel(channel)}
                </option>
              ))}
            </select>
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            {DIGEST_VIEWS.map(({ view, label, nameLabel }) => {
              const recipient = recipients[view];
              const candidates = candidatesByView[view];
              return (
                <div key={view} data-testid={`digest-recipient-${view}`} className="grid gap-3">
                  <label className="grid gap-2 text-sm font-medium text-text-primary">
                    <span>{nameLabel}</span>
                    <input
                      value={recipient.name}
                      onChange={(event) => updateRecipient(view, { name: event.target.value, userId: '' })}
                      placeholder={view === 'boss' ? '例如：王总' : '例如：李财务'}
                      className="h-11 rounded-xl border border-border bg-surface px-3 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                    />
                  </label>
                  {recipient.userId ? (
                    <p className="text-xs text-emerald-700">
                      已匹配 {recipient.name}，保存后 {label} 会发送到该成员。
                    </p>
                  ) : (
                    <p className="text-xs text-text-muted">保存时自动核验姓名；同名时会提示选择候选人。</p>
                  )}
                  {candidates.length > 0 ? (
                    <div className="grid gap-2">
                      {candidates.map((candidate) => (
                        <button
                          key={candidate.identifier}
                          type="button"
                          onClick={() => {
                            updateRecipient(view, {
                              name: candidate.display_name || recipient.name,
                              userId: candidate.identifier,
                            });
                            setNotice(`已选择${nameLabel}候选人，请再次点击保存。`);
                          }}
                          className="rounded-2xl border border-border bg-surface-secondary px-3 py-2 text-left text-sm transition hover:border-sky-200 hover:text-sky-700"
                        >
                          <span className="font-medium text-text-primary">{candidate.display_name || recipient.name}</span>
                          {candidate.disambiguation_label ? (
                            <span className="mt-1 block text-xs text-text-secondary">{candidate.disambiguation_label}</span>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end">
          <button
            type="submit"
            disabled={saving || loading || !channelId}
            className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            保存日报接收人
          </button>
        </div>
      </form>
    </section>
  );
}
