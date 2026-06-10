import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import { parsePublicReconDigestPath } from './publicReconDigestRoute';
import { fetchPublicDigestBundle, fetchPublicDigestExport } from './recon/digestDetail/api';
import { buildCsv } from './recon/digestDetail/csvExport';
import DigestDetailRenderer from './recon/digestDetail/DigestDetailRenderer';
import type { DigestBundle } from './recon/digestDetail/types';

function downloadCsv(rows: Array<Record<string, unknown>>, columns: string[], filename: string) {
  const csv = buildCsv(rows, columns);
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function PublicReconDigestPage() {
  const route = useMemo(() => parsePublicReconDigestPath(window.location.pathname), []);
  const [bundle, setBundle] = useState<DigestBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!route.token || !route.view) {
      setError('详情链接无效。');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');
    try {
      setBundle(await fetchPublicDigestBundle(route.token, route.view));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载日报详情失败');
    } finally {
      setLoading(false);
    }
  }, [route.token, route.view]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleExport = useCallback(async (reconType: string, columns: string[]) => {
    if (!route.token || route.view !== 'finance') return;
    try {
      setError('');
      const result = await fetchPublicDigestExport(route.token, route.view, reconType);
      const groupLabel = reconType || 'all';
      const filename = `${bundle?.biz_date || 'digest'}_${route.view}_${groupLabel}_对账底稿.csv`;
      downloadCsv(result.rows as Array<Record<string, unknown>>, columns, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出底稿失败');
    }
  }, [bundle?.biz_date, route.token, route.view]);

  return (
    <main className="h-screen overflow-y-auto bg-surface-secondary text-text-primary">
      <div className="mx-auto min-h-full w-full max-w-[1360px] px-4 py-5 sm:px-6 lg:px-8">
        <header className="border-b border-border-subtle pb-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-medium text-text-muted">对账日报详情</p>
              <h1 className="mt-2 break-words text-xl font-semibold text-text-primary">
                {route.view === 'finance' ? '财务详情页' : '老板详情页'}
              </h1>
              <p className="mt-2 break-words text-sm text-text-secondary">
                {bundle?.biz_date || '--'} · {bundle?.domain || '--'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-border bg-surface px-3 text-sm font-medium"
            >
              <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
              刷新
            </button>
          </div>
          {route.view === 'boss' ? (
            <p className="mt-4 rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-secondary">
              本报告反映对账与资金健康，非经营损益（不含成本/毛利/利润）
            </p>
          ) : null}
        </header>

        {loading ? <p className="py-8 text-sm text-text-secondary">加载中...</p> : null}
        {error ? <p className="py-8 text-sm text-red-600">{error}</p> : null}
        {!loading && !error && bundle ? (
          <DigestDetailRenderer bundle={bundle} onExportCsv={handleExport} />
        ) : null}
      </div>
    </main>
  );
}
