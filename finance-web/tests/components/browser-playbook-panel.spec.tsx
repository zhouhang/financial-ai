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
  it('加载浏览器任务时显示加载态而不是空态', () => {
    render(<BrowserPlaybookPanel authToken="token-1" sources={[]} loadingSources />);

    expect(screen.getByText('正在加载浏览器任务')).toBeInTheDocument();
    expect(screen.queryByText('暂无浏览器任务')).not.toBeInTheDocument();
  });

  it('展示浏览器任务列表和详情入口', () => {
    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            browser_verification: {
              sync_job_id: 'sync-success-1',
              job_status: 'success',
              completed_at: '2026-05-25T15:31:51+08:00',
              is_verification: true,
            },
          },
        ]}
      />,
    );

    expect(screen.queryByText('浏览器抓取')).not.toBeInTheDocument();
    expect(screen.getByText('浏览器任务列表')).toBeInTheDocument();
    expect(screen.queryByText('浏览器采集列表')).not.toBeInTheDocument();
    expect(screen.getByText('任务状态')).toBeInTheDocument();
    expect(screen.queryByText('验证状态')).not.toBeInTheDocument();
    expect(screen.getByText('千牛每日资金账单')).toBeInTheDocument();
    expect(screen.getByText('已激活')).toBeInTheDocument();
    expect(screen.getByText('成功')).toBeInTheDocument();
    expect(screen.queryByText('未记录')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /详情 千牛每日资金账单/ })).toBeInTheDocument();
    const retryButton = screen.getByRole('button', { name: /重试 千牛每日资金账单/ });
    const deleteButton = screen.getByRole('button', { name: /删除 千牛每日资金账单/ });
    expect(retryButton).toBeInTheDocument();
    expect(deleteButton).toBeInTheDocument();
    expect(retryButton).toHaveClass('whitespace-nowrap');
    expect(deleteButton).toHaveClass('whitespace-nowrap');
  });

  it('最近更新展示浏览器任务的真实更新时间而不是数据源配置更新时间', () => {
    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            updated_at: '2026-05-21T09:00:00+08:00',
            browser_verification: {
              sync_job_id: 'sync-success-1',
              job_status: 'success',
              updated_at: '2026-05-25T15:30:00+08:00',
              completed_at: '2026-05-25T15:31:51+08:00',
              is_verification: true,
            },
          },
        ]}
      />,
    );

    expect(screen.getByText('2026/5/25 15:31:51')).toBeInTheDocument();
    expect(screen.queryByText('2026/5/21 09:00:00')).not.toBeInTheDocument();
  });

  it('浏览器任务列表超过一页时分页显示', () => {
    const manySources = Array.from({ length: 25 }, (_, index) => {
      const itemNumber = String(index + 1).padStart(2, '0');
      const title = `浏览器任务 ${itemNumber}`;
      return {
        ...sources[0],
        id: `source-${itemNumber}`,
        code: `browser-task-${itemNumber}`,
        name: title,
        metadata: {
          ...sources[0].metadata,
          registration_title: title,
        },
      };
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={manySources} />);

    expect(screen.getByText('浏览器任务 01')).toBeInTheDocument();
    expect(screen.getByText('浏览器任务 20')).toBeInTheDocument();
    expect(screen.queryByText('浏览器任务 21')).not.toBeInTheDocument();
    expect(screen.getByText('显示 1-20 / 25 条')).toBeInTheDocument();
    expect(screen.getByText('第 1 / 2 页')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '下一页' }));

    expect(screen.queryByText('浏览器任务 01')).not.toBeInTheDocument();
    expect(screen.getByText('浏览器任务 21')).toBeInTheDocument();
    expect(screen.getByText('浏览器任务 25')).toBeInTheDocument();
    expect(screen.getByText('显示 21-25 / 25 条')).toBeInTheDocument();
    expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '上一页' }));

    expect(screen.getByText('浏览器任务 01')).toBeInTheDocument();
    expect(screen.queryByText('浏览器任务 21')).not.toBeInTheDocument();
  }, 10000);

  it('浏览器任务列表按创建时间倒序排列', () => {
    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            id: 'task-oldest',
            name: '最早任务',
            metadata: { registration_title: '最早任务' },
            created_at: '2026-05-20T09:00:00+08:00',
          },
          {
            ...sources[0],
            id: 'task-newest',
            name: '最新任务',
            metadata: { registration_title: '最新任务' },
            created_at: '2026-05-25T09:00:00+08:00',
          },
          {
            ...sources[0],
            id: 'task-middle',
            name: '居中任务',
            metadata: { registration_title: '居中任务' },
            created_at: '2026-05-22T09:00:00+08:00',
          },
        ]}
      />,
    );

    const newest = screen.getByText('最新任务');
    const middle = screen.getByText('居中任务');
    const oldest = screen.getByText('最早任务');

    expect(newest.compareDocumentPosition(middle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(middle.compareDocumentPosition(oldest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('缺少创建时间的浏览器任务排在有创建时间的任务之后', () => {
    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            id: 'task-no-created',
            name: '无创建时间任务',
            metadata: { registration_title: '无创建时间任务' },
            created_at: null,
          },
          {
            ...sources[0],
            id: 'task-with-created',
            name: '有创建时间任务',
            metadata: { registration_title: '有创建时间任务' },
            created_at: '2026-05-22T09:00:00+08:00',
          },
        ]}
      />,
    );

    const withCreated = screen.getByText('有创建时间任务');
    const noCreated = screen.getByText('无创建时间任务');

    expect(withCreated.compareDocumentPosition(noCreated) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('手动清除只展示在卡住任务上并将 MANUAL_CLEARED 显示为已清除', () => {
    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            browser_verification: {
              sync_job_id: 'sync-waiting-1',
              job_status: 'waiting_human_verification',
              updated_at: '2026-05-25T15:31:51+08:00',
              is_verification: true,
            },
          },
          {
            ...sources[0],
            id: 'source-cleared',
            name: '已清除任务',
            metadata: { registration_title: '已清除任务' },
            browser_verification: {
              sync_job_id: 'sync-cleared-1',
              job_status: 'cancelled',
              browser_fail_reason: 'MANUAL_CLEARED',
              error_message: 'MANUAL_CLEARED: operator cleared stuck browser task',
              updated_at: '2026-05-25T15:32:51+08:00',
              is_verification: true,
            },
          },
          {
            ...sources[0],
            id: 'source-success',
            name: '成功任务',
            metadata: { registration_title: '成功任务' },
            browser_verification: {
              sync_job_id: 'sync-success-2',
              job_status: 'success',
              completed_at: '2026-05-25T15:33:51+08:00',
              is_verification: true,
            },
          },
        ]}
      />,
    );

    expect(screen.getByText('待人工验证')).toBeInTheDocument();
    expect(screen.getByText('已清除')).toBeInTheDocument();
    expect(screen.getByText('成功')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /清除任务 千牛每日资金账单/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /清除任务 已清除任务/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /清除任务 成功任务/ })).not.toBeInTheDocument();
  });

  it('点击详情加载最新采集数据、playbook 和凭证摘要，并支持复制 playbook', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/detail?record_limit=100') {
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        return jsonResponse({
          success: true,
          source: { id: 'source-1', name: '千牛每日资金账单' },
          browser_verification: { sync_job_id: 'sync-1', job_status: 'success' },
          record_count: 23,
          latest_records: [
            {
              id: 'record-1',
              biz_date: '2026-05-21',
              item_key: 'bill-1',
              payload: { custom_b: 'bill-1', custom_a: '12.30', custom_c: '2026-05-21 13:00:00' },
              captured_at: '2026-05-22T13:30:00+08:00',
            },
          ],
          playbook: {
            playbook_id: 'browser-collection-qn',
            version: '1',
            title: '千牛每日资金账单',
            status: 'active',
            playbook_body: {
              schema_version: '1.0',
              output: {
                columns: [
                  { name: 'custom_a' },
                  { name: 'custom_b' },
                  { name: 'missing_from_payload' },
                ],
              },
              steps: [{ action: 'click' }],
            },
          },
          credential: {
            username: 'finance_ops@example.com',
            password_saved: true,
          },
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} />);

    fireEvent.click(screen.getByRole('button', { name: /详情 千牛每日资金账单/ }));

    const dialog = await screen.findByRole('dialog', { name: '浏览器任务详情' });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(await within(dialog).findByText('最新采集数据')).toBeInTheDocument();
    expect(within(dialog).getByText('已加载 1 / 共 23 条')).toBeInTheDocument();
    const recordsTable = within(dialog).getByRole('table', { name: '最新采集数据表' });
    const headerTexts = within(recordsTable)
      .getAllByRole('columnheader')
      .map((header) => header.textContent);
    expect(headerTexts.slice(0, 3)).toEqual(['custom_a', 'custom_b', 'custom_c']);
    expect(within(recordsTable).queryByText('missing_from_payload')).not.toBeInTheDocument();
    expect(within(dialog).getAllByText(/bill-1/).length).toBeGreaterThan(0);
    expect(within(recordsTable).getByText('12.30')).toBeInTheDocument();
    expect(within(recordsTable).queryByText(/"custom_a"/)).not.toBeInTheDocument();
    expect(within(dialog).getByText('Playbook')).toBeInTheDocument();
    expect(within(dialog).getByText(/"action": "click"/)).toBeInTheDocument();
    expect(within(dialog).getByText('凭证')).toBeInTheDocument();
    expect(within(dialog).getByText('finance_ops@example.com')).toBeInTheDocument();
    expect(within(dialog).getByText('密码已保存')).toBeInTheDocument();
    expect(within(dialog).queryByText('secret')).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '复制 Playbook' }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        JSON.stringify(
          {
            schema_version: '1.0',
            output: {
              columns: [
                { name: 'custom_a' },
                { name: 'custom_b' },
                { name: 'missing_from_payload' },
              ],
            },
            steps: [{ action: 'click' }],
          },
          null,
          2,
        ),
      ),
    );
    expect(await within(dialog).findByText('Playbook 已复制')).toBeInTheDocument();
  });

  it('列表和详情展示历史浏览器验证失败原因', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/detail?record_limit=100') {
        return jsonResponse({
          success: true,
          source: { id: 'source-1', name: '千牛每日资金账单' },
          latest_records: [],
          playbook: {},
          credential: {},
        });
      }
      return jsonResponse({}, 404);
    });

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

    expect(screen.getByText('失败')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /详情 千牛每日资金账单/ }));

    const dialog = await screen.findByRole('dialog', { name: '浏览器任务详情' });
    expect(within(dialog).getByText('任务ID')).toBeInTheDocument();
    expect(within(dialog).getByText('sync-failed-1')).toBeInTheDocument();
    expect(within(dialog).getByText('失败原因')).toBeInTheDocument();
    expect(within(dialog).getByText('PAGE_CHANGED: login selector missing')).toBeInTheDocument();
  });

  it('重试浏览器任务会重新下发任务并刷新列表', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/retry') {
        expect(init?.method).toBe('POST');
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        expect(JSON.parse(String(init?.body))).toEqual({ force_collection: true });
        return jsonResponse({
          success: true,
          verification_sync_job_id: 'sync-retry-1',
          verification_biz_date: '2026-05-20',
          message: '浏览器任务已重新下发到采集机，请等待任务状态更新',
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} onRegistered={onRegistered} />);

    fireEvent.click(screen.getByRole('button', { name: /重试 千牛每日资金账单/ }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    const notice = await screen.findByText(/sync-retry-1/);
    const table = screen.getByRole('table');
    expect(notice.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
  });

  it('填密码弹窗回显已保存的登录名而不是按标题现算的默认值', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/detail?record_limit=1') {
        return jsonResponse({
          success: true,
          credential: { username: '博宽网游财务ai', password_saved: true },
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} />);
    fireEvent.click(screen.getByRole('button', { name: /填密码 千牛每日资金账单/ }));

    const dialog = await screen.findByRole('dialog', { name: '填写浏览器任务密码' });
    await waitFor(() =>
      expect((within(dialog).getByLabelText('登录账号') as HTMLInputElement).value).toBe('博宽网游财务ai'),
    );
  });

  it('填密码弹窗在无已存凭证时回退到按标题现算的默认登录名', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/detail?record_limit=1') {
        return jsonResponse({ success: true, credential: {} });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} />);
    fireEvent.click(screen.getByRole('button', { name: /填密码 千牛每日资金账单/ }));

    const dialog = await screen.findByRole('dialog', { name: '填写浏览器任务密码' });
    expect((within(dialog).getByLabelText('登录账号') as HTMLInputElement).value).toBe(
      '千牛每日资金账单:ai财务',
    );
  });

  it('更新浏览器任务密码时只提交凭证且不回显密码', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/credential') {
        expect(init?.method).toBe('POST');
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        expect(JSON.parse(String(init?.body))).toEqual({
          credential_username: '千牛每日资金账单:ai财务',
          credential_password: 'secret-password',
        });
        return jsonResponse({
          success: true,
          source_id: 'source-1',
          credential: {
            username: '千牛每日资金账单:ai财务',
            password_saved: true,
          },
          message: '浏览器任务凭证已保存',
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} onRegistered={onRegistered} />);

    fireEvent.click(screen.getByRole('button', { name: /填密码 千牛每日资金账单/ }));

    const dialog = await screen.findByRole('dialog', { name: '填写浏览器任务密码' });
    fireEvent.change(within(dialog).getByLabelText('登录账号'), {
      target: { value: '千牛每日资金账单:ai财务' },
    });
    fireEvent.change(within(dialog).getByLabelText('密码'), {
      target: { value: 'secret-password' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '保存' }));

    await waitFor(() => {
      const credentialCalls = fetchSpy.mock.calls.filter(
        ([input]) => String(input) === '/api/data-sources/source-1/browser-playbook/credential',
      );
      expect(credentialCalls).toHaveLength(1);
    });
    expect(await screen.findByText('浏览器任务凭证已保存')).toBeInTheDocument();
    expect(screen.queryByText('secret-password')).not.toBeInTheDocument();
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
  });

  it('重试浏览器任务后轮询任务状态并更新提示', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/retry') {
        return jsonResponse({
          success: true,
          verification_sync_job_id: 'sync-retry-success-1',
          verification_biz_date: '2026-05-20',
          message: '浏览器任务已重新下发到采集机，请等待任务状态更新',
        });
      }
      if (url === '/api/sync-jobs/sync-retry-success-1') {
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        return jsonResponse({
          success: true,
          job: {
            id: 'sync-retry-success-1',
            job_status: 'success',
            error_message: '',
          },
        });
      }
      if (url === '/api/data-sources/browser-playbook/finalize') {
        expect(init?.method).toBe('POST');
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        expect(JSON.parse(String(init?.body))).toEqual({
          verification_sync_job_id: 'sync-retry-success-1',
        });
        return jsonResponse({
          success: true,
          message: '浏览器任务已完成并激活',
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} onRegistered={onRegistered} />);

    fireEvent.click(screen.getByRole('button', { name: /重试 千牛每日资金账单/ }));

    expect(await screen.findByText(/sync-retry-success-1/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/浏览器任务已完成/)).toBeInTheDocument());
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith('/api/sync-jobs/sync-retry-success-1', expect.any(Object)));
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(2));
  });

  it('重试浏览器任务轮询到失败状态时展示 browser-agent 失败原因', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1/browser-playbook/retry') {
        return jsonResponse({
          success: true,
          verification_sync_job_id: 'sync-retry-failed-1',
          message: '浏览器任务已重新下发到采集机，请等待任务状态更新',
        });
      }
      if (url === '/api/sync-jobs/sync-retry-failed-1') {
        return jsonResponse({
          success: true,
          job: {
            id: 'sync-retry-failed-1',
            job_status: 'failed',
            browser_fail_reason: 'DATA_MISMATCH',
            error_message: 'DATA_MISMATCH: 行数与日汇总不一致: 明细 23 行，日汇总 24 行',
          },
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} />);

    fireEvent.click(screen.getByRole('button', { name: /重试 千牛每日资金账单/ }));

    expect(await screen.findByText(/sync-retry-failed-1/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/DATA_MISMATCH: 行数与日汇总不一致: 明细 23 行，日汇总 24 行/)).toBeInTheDocument(),
    );
  });

  it('手动清除浏览器任务会调用清除接口并刷新列表', async () => {
    const onRegistered = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/sync-jobs/sync-waiting-1/clear') {
        expect(init?.method).toBe('POST');
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        expect(JSON.parse(String(init?.body))).toEqual({ reason: 'operator cleared stuck browser task' });
        return jsonResponse({
          success: true,
          job: {
            id: 'sync-waiting-1',
            job_status: 'cancelled',
            browser_fail_reason: 'MANUAL_CLEARED',
          },
          message: '当前浏览器任务已清除，可重新下发或等待后续任务执行',
        });
      }
      return jsonResponse({}, 404);
    });

    render(
      <BrowserPlaybookPanel
        authToken="token-1"
        sources={[
          {
            ...sources[0],
            browser_verification: {
              sync_job_id: 'sync-waiting-1',
              job_status: 'waiting_human_verification',
              updated_at: '2026-05-25T15:31:51+08:00',
              is_verification: true,
            },
          },
        ]}
        onRegistered={onRegistered}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /清除任务 千牛每日资金账单/ }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('当前浏览器任务已清除，可重新下发或等待后续任务执行')).toBeInTheDocument();
  });

  it('删除浏览器任务会调用数据源删除接口并刷新列表', async () => {
    const onRegistered = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/data-sources/source-1') {
        expect(init?.method).toBe('DELETE');
        expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-1' });
        return jsonResponse({
          success: true,
          message: '数据源已删除',
        });
      }
      return jsonResponse({}, 404);
    });

    render(<BrowserPlaybookPanel authToken="token-1" sources={sources} onRegistered={onRegistered} />);

    fireEvent.click(screen.getByRole('button', { name: /删除 千牛每日资金账单/ }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onRegistered).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('数据源已删除')).toBeInTheDocument();
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
