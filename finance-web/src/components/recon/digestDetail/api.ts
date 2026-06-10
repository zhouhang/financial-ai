import type { PublicReconDigestView } from '../../publicReconDigestRoute';
import { fetchReconAutoApi } from '../autoApi';
import type { DigestBundle, DigestExportRows } from './types';

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null) as {
    detail?: unknown;
    message?: unknown;
    error?: unknown;
  } | null;
  const message = body?.detail || body?.message || body?.error;
  return typeof message === 'string' && message.trim() ? message : fallback;
}

export async function fetchPublicDigestBundle(
  token: string,
  view: PublicReconDigestView,
): Promise<DigestBundle> {
  const response = await fetchReconAutoApi(
    `/public/digests/${encodeURIComponent(token)}/${view}`,
    { method: 'GET' },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '加载日报详情失败'));
  }
  return await response.json() as DigestBundle;
}

export async function fetchPublicDigestExport(
  token: string,
  view: PublicReconDigestView,
  reconType = '',
): Promise<DigestExportRows> {
  const params = new URLSearchParams();
  params.set('recon_type', reconType);
  const response = await fetchReconAutoApi(
    `/public/digests/${encodeURIComponent(token)}/${view}/export?${params.toString()}`,
    { method: 'GET' },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '导出底稿失败'));
  }
  const data = await response.json().catch(() => ({}));
  return data as DigestExportRows;
}
