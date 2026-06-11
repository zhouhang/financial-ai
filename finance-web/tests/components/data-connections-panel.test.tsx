import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DataConnectionsPanel from '../../src/components/DataConnectionsPanel';

const sourceId = 'source-db-1';
const datasetId = 'dataset-orders';

function buildJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

describe('DataConnectionsPanel 数据集命名编辑', () => {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  beforeEach(() => {
    localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('支持编辑业务名称和字段中文名并保存到后端', async () => {
    const publishRequests: Array<{ url: string; init?: RequestInit; body: Record<string, unknown> }> = [];

    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);

      if (url === '/api/auth/me') {
        return buildJsonResponse({
          success: true,
          user: {
            id: 'user-1',
            username: 'admin',
            role: 'admin',
          },
        });
      }

      if (url === '/api/platform-connections') {
        return buildJsonResponse({ platforms: [] });
      }

      if (url === '/api/collaboration-channels') {
        return buildJsonResponse({ channels: [] });
      }

      if (url === '/api/data-sources') {
        return buildJsonResponse({
          data_sources: [
            {
              id: sourceId,
              source_kind: 'database',
              provider_code: 'mysql',
              name: '订单数据库',
              status: 'healthy',
              execution_mode: 'deterministic',
              updated_at: '2026-04-16T09:00:00Z',
              dataset_count: 1,
            },
          ],
        });
      }

      if (
        url === `/api/data-sources/${sourceId}/datasets`
        || url.startsWith(`/api/data-sources/${sourceId}/datasets?`)
      ) {
        return buildJsonResponse({
          total: 1,
          page: 1,
          page_size: 100,
          datasets: [
            {
              id: datasetId,
              dataset_code: 'orders',
              dataset_name: 'ods_trade_order',
              business_name: '订单业务台账',
              field_label_map: {
                order_id: '订单号',
                pay_amount: '支付金额',
              },
              key_fields: ['订单号'],
              dataset_kind: 'table',
              resource_key: 'trade.orders',
              publish_status: 'published',
              status: 'active',
              health_status: 'healthy',
              schema_summary: {
                columns: [
                  { name: 'order_id' },
                  { name: 'pay_amount' },
                  { name: 'biz_date' },
                ],
              },
            },
          ],
        });
      }

      if (url === `/api/data-sources/${sourceId}/events`) {
        return buildJsonResponse({ events: [] });
      }

      if (url === `/api/data-sources/${sourceId}/datasets/${datasetId}`) {
        return buildJsonResponse({
          dataset: {
            id: datasetId,
            dataset_code: 'orders',
            dataset_name: 'ods_trade_order',
            business_name: '订单业务台账',
            field_label_map: {
              order_id: '订单号',
              pay_amount: '支付金额',
            },
            key_fields: ['订单号'],
            dataset_kind: 'table',
            resource_key: 'trade.orders',
            publish_status: 'published',
            status: 'active',
            health_status: 'healthy',
            schema_summary: {
              columns: [
                { name: 'order_id' },
                { name: 'pay_amount' },
                { name: 'biz_date' },
              ],
            },
          },
        });
      }

      if (url === `/api/data-sources/${sourceId}/datasets/${datasetId}/publish`) {
        const rawBody = String(init?.body ?? '{}');
        const parsedBody = JSON.parse(rawBody) as Record<string, unknown>;
        publishRequests.push({ url, init, body: parsedBody });

        return buildJsonResponse({
          message: '已发布为可用数据集',
          dataset: {
            id: datasetId,
            dataset_code: 'orders',
            dataset_name: 'ods_trade_order',
            business_name: parsedBody.business_name,
            field_label_map: parsedBody.field_label_map,
            key_fields: parsedBody.key_fields,
            dataset_kind: 'table',
            resource_key: 'trade.orders',
            status: 'healthy',
            health_status: 'healthy',
            publish_status: 'published',
            collection_config: parsedBody.collection_config,
            schema_summary: {
              columns: [
                { name: 'order_id' },
                { name: 'pay_amount' },
                { name: 'biz_date' },
              ],
            },
          },
        });
      }

      throw new Error(`Unexpected fetch url: ${url}`);
    });

    render(
      <DataConnectionsPanel
        authToken="mock-token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk"
      />,
    );

    expect(await screen.findByText('订单数据库')).toBeInTheDocument();
    fireEvent.click(screen.getByText('进入详情'));
    expect(await screen.findByText('订单业务台账')).toBeInTheDocument();
    expect(screen.getByText(/trade\.orders/)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: '物理目录' }));
    fireEvent.click(await screen.findByRole('button', { name: '管理发布' }));

    expect(await screen.findByRole('heading', { name: '管理发布' })).toBeInTheDocument();

    const businessNameInput = screen.getByDisplayValue('订单业务台账');
    fireEvent.change(businessNameInput, { target: { value: '订单收款明细' } });

    const fieldLabelInput = screen
      .getAllByRole('textbox')
      .find((input) => input !== businessNameInput && (input as HTMLInputElement).value !== '订单收款明细');
    expect(fieldLabelInput).toBeDefined();
    fireEvent.change(fieldLabelInput, { target: { value: '业务订单号' } });

    fireEvent.click(screen.getByRole('button', { name: '保存发布信息' }));

    await waitFor(() => {
      expect(publishRequests).toHaveLength(1);
    });

    expect(publishRequests[0]?.init?.method).toBe('POST');
    expect(publishRequests[0]?.init?.headers).toMatchObject({
      Authorization: 'Bearer mock-token',
      'Content-Type': 'application/json',
    });
    expect(publishRequests[0]?.body).toMatchObject({
      business_name: '订单收款明细',
      field_label_map: {
        order_id: '业务订单号',
        pay_amount: '支付金额',
      },
    });
    expect(publishRequests[0]?.body.fields).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          raw_name: 'order_id',
          display_name: '业务订单号',
        }),
      ]),
    );

    expect(await screen.findByText('已发布为可用数据集')).toBeInTheDocument();
  }, 20000);

  it('发布数据库表时不展示或提交每日自动采集配置', async () => {
    const publishRequests: Array<Record<string, unknown>> = [];

    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);

      if (url === '/api/auth/me') {
        return buildJsonResponse({
          success: true,
          user: {
            id: 'user-1',
            username: 'admin',
            role: 'admin',
          },
        });
      }

      if (url === '/api/platform-connections') {
        return buildJsonResponse({ platforms: [] });
      }

      if (url === '/api/collaboration-channels') {
        return buildJsonResponse({ channels: [] });
      }

      if (url === '/api/data-sources') {
        return buildJsonResponse({
          data_sources: [
            {
              id: sourceId,
              source_kind: 'database',
              provider_code: 'mysql',
              name: '订单数据库',
              status: 'healthy',
              execution_mode: 'deterministic',
              updated_at: '2026-04-16T09:00:00Z',
            },
          ],
        });
      }

      if (
        url === `/api/data-sources/${sourceId}/datasets`
        || url.startsWith(`/api/data-sources/${sourceId}/datasets?`)
      ) {
        return buildJsonResponse({
          total: 1,
          page: 1,
          page_size: 100,
          datasets: [
            {
              id: datasetId,
              dataset_code: 'orders',
              dataset_name: 'ods_trade_order',
              business_name: '订单业务台账',
              key_fields: ['order_id'],
              dataset_kind: 'table',
              resource_key: 'trade.orders',
              publish_status: 'published',
              status: 'active',
              health_status: 'healthy',
              collection_config: {
                mode: 'date_field',
                date_field: 'updated_at',
                schedule: {
                  enabled: true,
                  frequency: 'daily',
                  time: '08:30',
                },
              },
              schema_summary: {
                columns: [
                  { name: 'order_id' },
                  { name: 'updated_at' },
                ],
              },
            },
          ],
        });
      }

      if (url === `/api/data-sources/${sourceId}/events`) {
        return buildJsonResponse({ events: [] });
      }

      if (url === `/api/data-sources/${sourceId}/datasets/${datasetId}`) {
        return buildJsonResponse({
          dataset: {
            id: datasetId,
            dataset_code: 'orders',
            dataset_name: 'ods_trade_order',
            business_name: '订单业务台账',
            key_fields: ['order_id'],
            dataset_kind: 'table',
            resource_key: 'trade.orders',
            publish_status: 'published',
            status: 'active',
            health_status: 'healthy',
            collection_config: {
              mode: 'date_field',
              date_field: 'updated_at',
              schedule: {
                enabled: true,
                frequency: 'daily',
                time: '08:30',
              },
            },
            schema_summary: {
              columns: [
                { name: 'order_id' },
                { name: 'updated_at' },
              ],
            },
          },
        });
      }

      if (url === `/api/data-sources/${sourceId}/datasets/${datasetId}/publish`) {
        const rawBody = String(init?.body ?? '{}');
        const parsedBody = JSON.parse(rawBody) as Record<string, unknown>;
        publishRequests.push(parsedBody);
        return buildJsonResponse({
          success: true,
          message: '已发布为可用数据集',
          dataset: {
            id: datasetId,
            dataset_code: 'orders',
            dataset_name: 'ods_trade_order',
            business_name: parsedBody.business_name,
            key_fields: parsedBody.key_fields,
            dataset_kind: 'table',
            resource_key: 'trade.orders',
            publish_status: 'published',
            status: 'active',
            health_status: 'healthy',
            collection_config: parsedBody.collection_config,
            schema_summary: {
              columns: [
                { name: 'order_id' },
                { name: 'updated_at' },
              ],
            },
          },
        });
      }

      throw new Error(`Unexpected fetch url: ${url}`);
    });

    render(
      <DataConnectionsPanel
        authToken="mock-token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk"
      />,
    );

    expect(await screen.findByText('订单数据库')).toBeInTheDocument();

    fireEvent.click(screen.getByText('进入详情'));
    expect(await screen.findByText('订单业务台账')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '物理目录' }));
    fireEvent.click(await screen.findByRole('button', { name: '管理发布' }));

    expect(await screen.findByRole('heading', { name: '管理发布' })).toBeInTheDocument();
    expect(screen.queryByText('频率')).not.toBeInTheDocument();
    expect(screen.queryByText('执行时间')).not.toBeInTheDocument();
    expect(screen.queryByText(/发布后系统会按采集计划/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '保存发布信息' }));

    await waitFor(() => {
      expect(publishRequests).toHaveLength(1);
    });

    expect(publishRequests[0]?.collection_config).toMatchObject({
      mode: 'date_field',
      date_field: 'updated_at',
    });
    expect((publishRequests[0]?.collection_config as Record<string, unknown>).schedule).toBeUndefined();
  });
});


describe('DataConnectionsPanel 数据集详情入口路由', () => {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  beforeEach(() => {
    localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('数据库数据集卡片按钮显示详情', async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/auth/me') return buildJsonResponse({ user: { role: 'admin' } });
      if (url === '/api/platform-connections') return buildJsonResponse({ platforms: [] });
      if (url === '/api/collaboration-channels') return buildJsonResponse({ channels: [] });
      if (url === '/api/data-sources') {
        return buildJsonResponse({
          data_sources: [
            {
              id: sourceId,
              source_kind: 'database',
              provider_code: 'postgresql',
              name: 'Test DB',
              status: 'active',
              execution_mode: 'deterministic',
              datasets: [
                {
                  id: datasetId,
                  dataset_code: 'orders',
                  dataset_name: 'orders',
                  business_name: '订单表',
                  resource_key: 'public.orders',
                  publish_status: 'published',
                  status: 'active',
                },
              ],
            },
          ],
        });
      }
      if (url.startsWith(`/api/data-sources/${sourceId}/datasets`)) {
        return buildJsonResponse({
          datasets: [
            {
              id: datasetId,
              dataset_code: 'orders',
              dataset_name: 'orders',
              business_name: '订单表',
              resource_key: 'public.orders',
              publish_status: 'published',
              status: 'active',
            },
          ],
        });
      }
      if (url === `/api/data-sources/${sourceId}/events`) return buildJsonResponse({ events: [] });
      return buildJsonResponse({});
    });

    render(
      <DataConnectionsPanel
        authToken="mock-token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk"
      />,
    );

    expect(await screen.findByText('Test DB')).toBeInTheDocument();
    fireEvent.click(screen.getByText('进入详情'));
    expect(await screen.findByText('订单表')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '详情' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '采集详情' })).not.toBeInTheDocument();
  });
});

describe('DataConnectionsPanel 数据集更新增强交互', () => {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  beforeEach(() => {
    localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('支持指定表更新，并支持继续扫描下一批', async () => {
    const discoverRequests: Array<Record<string, unknown>> = [];

    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);

      if (url === '/api/auth/me') {
        return buildJsonResponse({
          success: true,
          user: {
            id: 'user-1',
            username: 'admin',
            role: 'admin',
          },
        });
      }

      if (url === '/api/platform-connections') {
        return buildJsonResponse({ platforms: [] });
      }

      if (url === '/api/collaboration-channels') {
        return buildJsonResponse({ channels: [] });
      }

      if (url === '/api/data-sources') {
        return buildJsonResponse({
          data_sources: [
            {
              id: sourceId,
              source_kind: 'database',
              provider_code: 'hologres',
              name: '财务中台订单 holo',
              status: 'healthy',
              execution_mode: 'deterministic',
              updated_at: '2026-04-16T09:00:00Z',
              discover_summary: {
                scan_mode: 'batch',
                scanned_count: 500,
                total_count: 1200,
                requested_limit: 500,
                has_more: true,
                next_offset: 500,
                last_discover_at: '2026-04-16T10:00:00Z',
                last_discover_status: 'success',
              },
            },
          ],
        });
      }

      if (url.startsWith(`/api/data-sources/${sourceId}/datasets`)) {
        return buildJsonResponse({
          total: 0,
          page: 1,
          page_size: 100,
          datasets: [],
        });
      }

      if (url === `/api/data-sources/${sourceId}/events`) {
        return buildJsonResponse({ events: [] });
      }

      if (url === `/api/data-sources/${sourceId}/discover`) {
        const rawBody = String(init?.body ?? '{}');
        const parsedBody = JSON.parse(rawBody) as Record<string, unknown>;
        discoverRequests.push(parsedBody);
        return buildJsonResponse({
          success: true,
          source_id: sourceId,
          provider_code: 'hologres',
          datasets: [],
          dataset_count: 0,
          persist: true,
          persisted_count: 0,
          discover_summary:
            Array.isArray(parsedBody.target_resource_keys) && parsedBody.target_resource_keys.length > 0
              ? {
                  scan_mode: 'targeted',
                  requested_count: parsedBody.target_resource_keys.length,
                  matched_count: parsedBody.target_resource_keys.length,
                  missing_targets: [],
                  last_discover_at: '2026-04-16T11:00:00Z',
                  last_discover_status: 'success',
                }
              : {
                  scan_mode: 'batch',
                  scanned_count: 500,
                  total_count: 1200,
                  requested_limit: 500,
                  has_more: true,
                  next_offset: 1000,
                  last_discover_at: '2026-04-16T11:00:00Z',
                  last_discover_status: 'success',
                },
          message: '数据集目录已刷新',
        });
      }

      throw new Error(`Unexpected fetch url: ${url}`);
    });

    render(
      <DataConnectionsPanel
        authToken="mock-token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk"
      />,
    );

    expect(await screen.findByText('财务中台订单 holo')).toBeInTheDocument();
    fireEvent.click(screen.getByText('进入详情'));
    expect(await screen.findByText('最近一次目录扫描')).toBeInTheDocument();
    expect(screen.getByText('本次扫描 500 / 1200 个对象')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '继续扫描下一批' }));

    await waitFor(() => {
      expect(discoverRequests).toHaveLength(1);
    });
    expect(discoverRequests[0]).toMatchObject({
      limit: 500,
      offset: 500,
    });

    fireEvent.click(screen.getByRole('button', { name: '指定表更新' }));
    expect(await screen.findByRole('heading', { name: '指定表更新' })).toBeInTheDocument();

    const targetResourceInput = screen.getAllByRole('textbox').at(-1);
    expect(targetResourceInput).toBeDefined();
    fireEvent.change(targetResourceInput as HTMLTextAreaElement, {
      target: { value: 'public.orders\npublic.order_items' },
    });
    fireEvent.click(screen.getByRole('button', { name: '开始更新' }));

    await waitFor(() => {
      expect(discoverRequests).toHaveLength(2);
    });
    expect(discoverRequests[1]).toMatchObject({
      limit: 2,
      target_resource_keys: ['public.orders', 'public.order_items'],
    });
  });
});
