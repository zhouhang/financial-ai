import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DataConnectionsPanel from '../../src/components/DataConnectionsPanel';

function mockJsonResponse(payload: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

describe('DataConnectionsPanel 浏览器任务列表', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('从数据源接口加载浏览器任务时保留 last_sync_at 作为最近更新时间', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'browser-source-1',
                source_kind: 'browser_playbook',
                provider_code: 'browser_playbook',
                name: '千牛每日资金账单',
                code: 'browser-collection-qn',
                status: 'active',
                execution_mode: 'deterministic',
                updated_at: '2026-05-21T09:00:00+08:00',
                last_sync_at: '2026-06-16T10:15:30+08:00',
                metadata: {
                  registration_title: '千牛每日资金账单',
                  managed_by: 'browser_collection_registration',
                },
                browser_verification: {
                  sync_job_id: 'sync-success-older',
                  job_status: 'success',
                  completed_at: '2026-05-25T15:31:51+08:00',
                  is_verification: true,
                },
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        if (url === '/api/auth/me') return mockJsonResponse({ user: { role: 'admin' } });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="browser_playbook"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('浏览器任务列表')).toBeInTheDocument();
    expect(screen.getByText('2026/6/16 10:15:30')).toBeInTheDocument();
    expect(screen.queryByText('2026/5/25 15:31:51')).not.toBeInTheDocument();
    expect(screen.queryByText('2026/5/21 09:00:00')).not.toBeInTheDocument();
  });
});
