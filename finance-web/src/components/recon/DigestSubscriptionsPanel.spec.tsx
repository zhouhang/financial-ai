import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReconWorkspace from '../ReconWorkspace';
import DigestSubscriptionsPanel from './DigestSubscriptionsPanel';
import type { UserTaskRule } from '../../types';

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

const selectedTask: UserTaskRule = {
  id: 1,
  rule_code: 'rule-1',
  name: '资金对账',
  rule_type: 'recon',
  task_code: 'task-1',
  task_name: '资金对账',
  task_type: 'recon',
};

const channelPayload = {
  channels: [
    {
      id: 'channel-001',
      provider: 'dingtalk_dws',
      channel_code: 'default',
      name: '安徽纳迈',
      is_default: true,
      is_enabled: true,
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('DigestSubscriptionsPanel', () => {
  it('loads current company channel and existing boss/finance names', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/collaboration-channels') {
        return jsonResponse(channelPayload);
      }
      if (url === '/api/recon/digest-subscriptions?period=daily&view=') {
        return jsonResponse({
          subscriptions: [
            {
              id: 'sub-boss',
              view: 'boss',
              enabled: true,
              channel_config_id: 'channel-001',
              scope: { mode: 'company_all' },
              recipient_json: { user_id: 'u-boss', display_name: '王总' },
            },
            {
              id: 'sub-finance',
              view: 'finance',
              enabled: true,
              channel_config_id: 'channel-001',
              scope: { mode: 'company_all' },
              recipient_json: { user_id: 'u-finance', display_name: '李财务' },
            },
          ],
        });
      }
      return jsonResponse({}, 404);
    });

    render(<DigestSubscriptionsPanel authToken="test-token" />);

    await waitFor(() => {
      expect((screen.getByLabelText('发送通道') as HTMLSelectElement).value).toBe('channel-001');
    });
    expect(screen.getByText('钉钉 - 安徽纳迈')).toBeTruthy();
    expect(screen.getByDisplayValue('王总')).toBeTruthy();
    expect(screen.getByDisplayValue('李财务')).toBeTruthy();
  });

  it('resolves names in selected channel and saves boss plus finance subscriptions', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/collaboration-channels') {
        return jsonResponse(channelPayload);
      }
      if (url === '/api/recon/digest-subscriptions?period=daily&view=') {
        return jsonResponse({ subscriptions: [] });
      }
      if (url === '/api/recon/owner-candidates/search' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}')) as { query?: string };
        return jsonResponse({
          success: true,
          organization: '安徽纳迈',
          candidates: [
            {
              display_name: body.query,
              identifier: body.query === '王总' ? 'u-boss' : 'u-finance',
              disambiguation_label: `${body.query} · 安徽纳迈`,
            },
          ],
        });
      }
      if (url === '/api/recon/digest-subscriptions' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
        return jsonResponse({
          success: true,
          subscription: {
            id: body.view === 'boss' ? 'sub-boss' : 'sub-finance',
            ...body,
          },
        });
      }
      return jsonResponse({}, 404);
    });

    render(<DigestSubscriptionsPanel authToken="test-token" />);

    await waitFor(() => {
      expect((screen.getByLabelText('发送通道') as HTMLSelectElement).value).toBe('channel-001');
    });
    fireEvent.change(screen.getByLabelText('老板姓名'), { target: { value: '王总' } });
    fireEvent.change(screen.getByLabelText('财务姓名'), { target: { value: '李财务' } });
    fireEvent.click(screen.getByRole('button', { name: '保存日报接收人' }));

    await waitFor(() => {
      const saveCalls = fetchMock.mock.calls.filter(
        ([input, init]) => String(input) === '/api/recon/digest-subscriptions' && init?.method === 'POST',
      );
      expect(saveCalls).toHaveLength(2);
    });

    const searchCalls = fetchMock.mock.calls.filter(
      ([input, init]) => String(input) === '/api/recon/owner-candidates/search' && init?.method === 'POST',
    );
    expect(searchCalls).toHaveLength(2);
    expect(searchCalls.map(([, init]) => JSON.parse(String(init?.body || '{}')))).toEqual([
      { query: '王总', channel_config_id: 'channel-001' },
      { query: '李财务', channel_config_id: 'channel-001' },
    ]);

    const savePayloads = fetchMock.mock.calls
      .filter(([input, init]) => String(input) === '/api/recon/digest-subscriptions' && init?.method === 'POST')
      .map(([, init]) => JSON.parse(String(init?.body || '{}')));
    expect(savePayloads).toEqual([
      {
        subscription_id: '',
        period: 'daily',
        view: 'boss',
        enabled: true,
        channel_config_id: 'channel-001',
        target_type: 'user',
        recipient_json: {
          user_id: 'u-boss',
          display_name: '王总',
        },
        scope: {
          mode: 'company_all',
        },
      },
      {
        subscription_id: '',
        period: 'daily',
        view: 'finance',
        enabled: true,
        channel_config_id: 'channel-001',
        target_type: 'user',
        recipient_json: {
          user_id: 'u-finance',
          display_name: '李财务',
        },
        scope: {
          mode: 'company_all',
        },
      },
    ]);
    expect(await screen.findByText('老板和财务日报接收人已保存。')).toBeTruthy();
  });

  it('shows candidates when a name matches multiple channel members', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/collaboration-channels') return jsonResponse(channelPayload);
      if (url === '/api/recon/digest-subscriptions?period=daily&view=') return jsonResponse({ subscriptions: [] });
      if (url === '/api/recon/owner-candidates/search' && init?.method === 'POST') {
        return jsonResponse({
          success: true,
          organization: '安徽纳迈',
          candidates: [
            { display_name: '张三', identifier: 'u-1', disambiguation_label: '张三 · 财务部' },
            { display_name: '张三', identifier: 'u-2', disambiguation_label: '张三 · 运营部' },
          ],
        });
      }
      return jsonResponse({}, 404);
    });

    render(<DigestSubscriptionsPanel authToken="test-token" />);

    await waitFor(() => {
      expect((screen.getByLabelText('发送通道') as HTMLSelectElement).value).toBe('channel-001');
    });
    fireEvent.change(screen.getByLabelText('老板姓名'), { target: { value: '张三' } });
    fireEvent.click(screen.getByRole('button', { name: '保存日报接收人' }));

    expect(await screen.findByText('“张三”匹配到 2 位同名成员，请选择明确候选人后再保存。')).toBeTruthy();
    const bossSection = screen.getByTestId('digest-recipient-boss');
    expect(within(bossSection).getByText('张三 · 财务部')).toBeTruthy();
    expect(within(bossSection).getByText('张三 · 运营部')).toBeTruthy();
  });
});

describe('ReconWorkspace digest subscription entry', () => {
  it('renders the daily subscription tab entry in the recon center', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.split('?')[0] === '/api/recon/schemes') return jsonResponse({ schemes: [] });
      if (url.split('?')[0] === '/api/recon/tasks') return jsonResponse({ tasks: [] });
      if (url.split('?')[0] === '/api/recon/runs') return jsonResponse({ runs: [] });
      if (url === '/api/collaboration-channels') return jsonResponse(channelPayload);
      if (url === '/api/recon/digest-subscriptions?period=daily&view=') {
        return jsonResponse({ subscriptions: [] });
      }
      return jsonResponse({}, 404);
    });

    render(<ReconWorkspace selectedTask={selectedTask} authToken="test-token" />);

    const tab = screen.getByRole('button', { name: '日报订阅' });
    expect(tab).toBeTruthy();

    fireEvent.click(tab);

    expect(await screen.findByText('老板 / 财务日报接收人')).toBeTruthy();
  });
});
