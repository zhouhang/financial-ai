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

  it('列表和详情展示历史浏览器验证失败原因', () => {
    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            browser_verification: {
              sync_job_id: 'sync-failed-1',
              job_status: 'failed',
              browser_fail_reason: 'PAGE_CHANGED',
              error_message: 'PAGE_CHANGED: login selector missing',
              updated_at: '2026-05-22T13:32:56.000+08:00',
              is_verification: true,
            },
          },
        ]}
      />,
    );

    expect(screen.getByText('验证失败')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /千牛每日资金账单/ }));

    const dialog = screen.getByRole('dialog', { name: '浏览器采集详情' });
    expect(within(dialog).getByText('验证任务')).toBeInTheDocument();
    expect(within(dialog).getByText('sync-failed-1')).toBeInTheDocument();
    expect(within(dialog).getByText('失败原因')).toBeInTheDocument();
    expect(within(dialog).getByText('PAGE_CHANGED: login selector missing')).toBeInTheDocument();
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

  it('注册返回验证任务后轮询任务状态，成功时自动激活 playbook', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/browser-playbook/registrations') {
        return jsonResponse({
          success: true,
          status: 'verification_pending',
          source_id: 'source-verify',
          verification_sync_job_id: 'sync-verify-1',
          verification_biz_date: '2026-05-21',
          message: '验证任务已创建',
        });
      }
      if (url === '/api/sync-jobs/sync-verify-1') {
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        return jsonResponse({
          success: true,
          job: {
            id: 'sync-verify-1',
            job_status: 'success',
            current_attempt: 1,
            error_message: '',
          },
        });
      }
      if (url === '/api/data-sources/browser-playbook/finalize') {
        expect(init?.method).toBe('POST');
        expect(JSON.parse(String(init?.body))).toEqual({
          verification_sync_job_id: 'sync-verify-1',
        });
        return jsonResponse({
          success: true,
          message: '浏览器采集已激活',
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
    fireEvent.change(within(dialog).getByLabelText('标题'), { target: { value: '单枪旗舰店-收支明细' } });
    fireEvent.change(within(dialog).getByLabelText('登录账号'), { target: { value: 'qianniu-user' } });
    fireEvent.change(within(dialog).getByLabelText('密码'), { target: { value: 'qianniu-pass' } });
    fireEvent.change(within(dialog).getByLabelText('playbook_body JSON'), {
      target: { value: '{"schema_version":"1.0","steps":[]}' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '注册' }));

    expect(await within(dialog).findByText(/验证任务已创建/)).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/data-sources/browser-playbook/finalize',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
    expect(within(dialog).getByText(/浏览器采集已激活/)).toBeInTheDocument();
  });

  it('注册返回验证任务后轮询失败状态并展示 browser-agent 失败原因', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/data-sources/browser-playbook/registrations') {
        return jsonResponse({
          success: true,
          status: 'verification_pending',
          verification_sync_job_id: 'sync-failed-1',
          verification_biz_date: '2026-05-21',
          message: '验证任务已创建',
        });
      }
      if (url === '/api/sync-jobs/sync-failed-1') {
        return jsonResponse({
          success: true,
          job: {
            id: 'sync-failed-1',
            job_status: 'failed',
            browser_fail_reason: 'PAGE_CHANGED',
            error_message: 'PAGE_CHANGED: login selector missing',
          },
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
    fireEvent.change(within(dialog).getByLabelText('标题'), { target: { value: '单枪旗舰店-收支明细' } });
    fireEvent.change(within(dialog).getByLabelText('登录账号'), { target: { value: 'qianniu-user' } });
    fireEvent.change(within(dialog).getByLabelText('密码'), { target: { value: 'qianniu-pass' } });
    fireEvent.change(within(dialog).getByLabelText('playbook_body JSON'), {
      target: { value: '{"schema_version":"1.0","steps":[]}' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '注册' }));

    expect(await within(dialog).findByText(/浏览器验证失败/)).toBeInTheDocument();
    expect(within(dialog).getByText(/PAGE_CHANGED: login selector missing/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalledWith(
      '/api/data-sources/browser-playbook/finalize',
      expect.anything(),
    );
    expect(onRegistered).not.toHaveBeenCalled();
  });

  it('新增浮窗显示 playbook JSON 行号，并自动修复字符串内断行后提交', async () => {
    const onRegistered = vi.fn();
    let resolveRegistration: ((value: Response) => void) | undefined;
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/browser-playbook/registrations') {
        expect(JSON.parse(String(init?.body))).toMatchObject({
          title: '千牛收入账单',
          credential_username: 'qianniu-user',
          credential_password: 'qianniu-pass',
          playbook_body: {
            selector: "input[name='TPL_password'], input[type='password']",
            label: '历史下载记录',
          },
        });
        return new Promise<Response>((resolve) => {
          resolveRegistration = resolve;
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
    expect(within(dialog).getByText('1')).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText('标题'), { target: { value: '千牛收入账单' } });
    fireEvent.change(within(dialog).getByLabelText('登录账号'), { target: { value: 'qianniu-user' } });
    fireEvent.change(within(dialog).getByLabelText('密码'), { target: { value: 'qianniu-pass' } });
    fireEvent.change(within(dialog).getByLabelText('playbook_body JSON'), {
      target: {
        value: `{
          "selector": "input[name='TPL_password'],
            input[type='password']",
          "label": "历史下载记
录"
        }`,
      },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '注册' }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    expect(await within(dialog).findByText(/已自动修复/)).toBeInTheDocument();
    resolveRegistration?.(
      new Response(JSON.stringify({ success: true, source_id: 'source-3', message: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
  });
});
