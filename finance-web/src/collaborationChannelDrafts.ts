import type { CollaborationChannelListItem } from './types';

const STORAGE_KEY = 'tally_collaboration_channel_drafts';

export function normalizeChannelConfig(raw: unknown): CollaborationChannelListItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const value = raw as Record<string, unknown>;
  const id = typeof value.id === 'string' ? value.id : '';
  const provider = typeof value.provider === 'string' ? value.provider : '';
  if (!id || !provider) return null;

  return {
    id,
    provider,
    channel_code: typeof value.channel_code === 'string' ? value.channel_code : 'default',
    name: typeof value.name === 'string' ? value.name : '',
    client_id: typeof value.client_id === 'string' ? value.client_id : '',
    client_secret: typeof value.client_secret === 'string' ? value.client_secret : '',
    robot_code: typeof value.robot_code === 'string' ? value.robot_code : '',
    is_default: Boolean(value.is_default),
    is_enabled: value.is_enabled === undefined ? true : Boolean(value.is_enabled),
    updated_at: typeof value.updated_at === 'string' ? value.updated_at : null,
    extra: value.extra && typeof value.extra === 'object' ? (value.extra as Record<string, unknown>) : {},
  };
}

export function loadCollaborationChannelDrafts(): CollaborationChannelListItem[] {
  if (typeof window === 'undefined') return [];

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    const rows = Array.isArray(parsed) ? parsed : [];
    return rows
      .map((item) => normalizeChannelConfig(item))
      .filter(Boolean) as CollaborationChannelListItem[];
  } catch {
    return [];
  }
}

export function saveCollaborationChannelDrafts(items: CollaborationChannelListItem[]): void {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore storage failures and keep the in-memory draft state usable.
  }
}
