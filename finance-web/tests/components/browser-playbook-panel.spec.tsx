import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BrowserPlaybookPanel } from '../../src/components/BrowserPlaybookPanel';
import type { DataSourceListItem } from '../../src/types';

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

const sources: DataSourceListItem[] = [
  {
    id: 'source-1',
    source_kind: 'browser_playbook',
    provider_code: 'browser_playbook',
    name: '千牛每日资金账单',
    code: 'browser-collection-qn',
    status: 'active',
    execution_mode: 'deterministic',
    description: '千牛每日资金账单 浏览器采集',
    updated_at: '2026-05-21T09:00:00.000Z',
    metadata: {
      registration_title: '千牛每日资金账单',
      managed_by: 'browser_collection_registration',
    },
    datasets: [
      {
        id: 'dataset-1',
        dataset_code: 'browser-collection-qn',
        dataset_name: '千牛每日资金账单',
        business_name: '千牛每日资金账单',
        publish_status: 'published',
        resource_key: 'browser-collection-qn@1',
        extract_config: {
          source_type: 'browser_collection_records',
          playbook_id: 'browser-collection-qn',
          playbook_version: '1',
        },
      },
    ],
  },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('BrowserPlaybookPanel', () => {
  it('展示浏览器采集列表，点击列表元素用浮窗查看注册信息', () => {
    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} />);

    expect(screen.queryByText('浏览器抓取')).not.toBeInTheDocument();
    expect(screen.getByText('千牛每日资金账单')).toBeInTheDocument();
    expect(screen.getByText('启用')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /千牛每日资金账单/ }));

    const dialog = screen.getByRole('dialog', { name: '浏览器采集详情' });
    expect(within(dialog).getByText('标题')).toBeInTheDocument();
    expect(within(dialog).getAllByText('千牛每日资金账单').length).toBeGreaterThan(0);
    expect(within(dialog).queryByText('source_id')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('playbook_id')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('version')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('egress_group')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('语义数据集')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('落地数据集')).not.toBeInTheDocument();
  });

  it('通过外部新增信号打开新增浮窗并提交 source-less 注册', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/browser-playbook/registrations') {
        expect(init?.method).toBe('POST');
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        expect(JSON.parse(String(init?.body))).toEqual({
          title: '银行流水下载',
          credential_username: 'bank-user',
          credential_password: 'bank-pass',
          playbook_body: { schema_version: '1.0', steps: [] },
        });
        return jsonResponse({
          success: true,
          source_id: 'source-2',
          dataset: { id: 'dataset-2', dataset_name: '银行流水下载' },
          message: 'ok',
        });
      }
      return jsonResponse({}, 404);
    });

    const { rerender } = render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[]}
        openCreateSignal={0}
        onRegistered={onRegistered}
      />,
    );

    rerender(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[]}
        openCreateSignal={1}
        onRegistered={onRegistered}
      />,
    );

    const dialog = await screen.findByRole('dialog', { name: '新增浏览器采集' });
    expect(within(dialog).getByLabelText('标题')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('登录账号')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('密码')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('playbook_body JSON')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('source_id')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('playbook_id')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('version')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('egress_group')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('验证日期')).not.toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText('标题'), { target: { value: '银行流水下载' } });
    fireEvent.change(within(dialog).getByLabelText('登录账号'), { target: { value: 'bank-user' } });
    fireEvent.change(within(dialog).getByLabelText('密码'), { target: { value: 'bank-pass' } });
    fireEvent.change(within(dialog).getByLabelText('playbook_body JSON'), {
      target: { value: '{"schema_version":"1.0","steps":[]}' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '注册' }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('dialog', { name: '新增浏览器采集' })).not.toBeInTheDocument();
  });
});
