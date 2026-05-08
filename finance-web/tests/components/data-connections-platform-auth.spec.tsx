import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DataConnectionsPanel from '../../src/components/DataConnectionsPanel';

const SERVICE_PROVIDER_COMPANY_ID = '00000000-0000-0000-0000-00000000dd01';

function mockJsonResponse(payload: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

describe('电商平台授权入口', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('只展示淘宝天猫和支付宝平台卡片', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝',
                authorized_shop_count: 1,
                error_shop_count: 0,
                status: 'supported',
              },
              {
                platform_code: 'tmall',
                platform_name: '天猫',
                authorized_shop_count: 2,
                error_shop_count: 1,
                status: 'supported',
              },
              {
                platform_code: 'douyin_shop',
                platform_name: '抖店',
                authorized_shop_count: 1,
                error_shop_count: 0,
                status: 'supported',
              },
              {
                platform_code: 'kuaishou',
                platform_name: '快手小店',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
              {
                platform_code: 'jd',
                platform_name: '京东',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('淘宝/天猫')).toBeInTheDocument();
    expect(screen.getByText('支付宝')).toBeInTheDocument();
    expect(screen.getByText('编码：taobao')).toBeInTheDocument();
    expect(screen.getByText('编码：alipay')).toBeInTheDocument();
    expect(screen.queryByText('编码：tmall')).not.toBeInTheDocument();
    expect(screen.queryByText('抖店')).not.toBeInTheDocument();
    expect(screen.queryByText('快手小店')).not.toBeInTheDocument();
    expect(screen.queryByText('京东')).not.toBeInTheDocument();
    expect(screen.getByText('已授权店铺：3')).toBeInTheDocument();
    expect(screen.getByText('异常店铺：1')).toBeInTheDocument();
  });

  it('新增授权时显式请求真实淘宝授权模式', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.startsWith('/api/platform-connections/taobao/auth-sessions')) {
          return mockJsonResponse({
            success: true,
            auth_url: '#taobao-auth',
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(screen.getByRole('button', { name: '新增授权' }));
    expect(screen.queryByRole('dialog', { name: '新增支付宝商户授权' })).not.toBeInTheDocument();

    await waitFor(() => {
      expect(requests.some((request) => request.url.includes('/auth-sessions'))).toBe(true);
    });
    const authRequest = requests.find((request) => request.url.includes('/auth-sessions'));
    expect(authRequest).toBeTruthy();
    expect(JSON.parse(String(authRequest?.init?.body || '{}'))).toMatchObject({
      return_path: '/',
      mode: 'real',
    });
  });

  it('支付宝新增授权先填写商户显示名称并提交真实授权会话', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.startsWith('/api/platform-connections/alipay/auth-sessions')) {
          return mockJsonResponse({
            success: true,
            auth_url: '#alipay-auth',
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：alipay');
    const alipayCard = screen.getByText('编码：alipay').closest('div.rounded-2xl');
    expect(alipayCard).toBeTruthy();
    fireEvent.click(within(alipayCard as HTMLElement).getByRole('button', { name: '新增授权' }));

    const dialog = await screen.findByRole('dialog', { name: '新增支付宝商户授权' });
    const submitButton = within(dialog).getByRole('button', { name: '新增授权' });
    expect(submitButton).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText('商户显示名称'), { target: { value: '福游网络' } });
    expect(submitButton).not.toBeDisabled();
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(requests.some((request) => request.url === '/api/platform-connections/alipay/auth-sessions')).toBe(true);
    });
    const authRequest = requests.find(
      (request) => request.url === '/api/platform-connections/alipay/auth-sessions',
    );
    expect(JSON.parse(String(authRequest?.init?.body || '{}'))).toEqual({
      return_path: '/data-connections?mode=platform&platform=alipay',
      mode: 'real',
      merchant_display_name: '福游网络',
    });
  });

  it('详情页新增店铺授权失败时在当前页展示错误', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.includes('/shops')) {
          return mockJsonResponse({ shops: [] });
        }
        if (url.includes('/auth-sessions')) {
          return mockJsonResponse({ detail: '平台应用未配置，请先配置淘宝/天猫 AppKey、AppSecret 和回调地址' }, false, 400);
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));
    await screen.findByText('淘宝/天猫 店铺列表');
    fireEvent.click(screen.getByRole('button', { name: '新增店铺授权' }));

    expect(
      await screen.findByText('平台应用未配置，请先配置淘宝/天猫 AppKey、AppSecret 和回调地址'),
    ).toBeInTheDocument();
  });

  it('客户店铺详情页不展示 AppKey 和 AppSecret 配置表单', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: true,
            config: {
              platform_code: 'taobao',
              app_key: 'tally-app-key',
              app_secret: '',
              has_app_secret: true,
              redirect_uri: 'https://tally.example.com/api/platform-auth/callback/taobao',
            },
          });
        }
        if (url.includes('/shops')) return mockJsonResponse({ shops: [] });
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));
    expect(await screen.findByText('Tally 服务商应用已配置，客户只需要完成店铺授权。')).toBeInTheDocument();
    expect(screen.queryByLabelText('AppKey')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('AppSecret')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存应用配置' })).not.toBeInTheDocument();
    expect(requests.some((request) => request.url.includes('/app-config') && request.init?.method === 'PUT')).toBe(false);
  });

  it('普通成员不展示服务商应用配置入口', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url === '/api/auth/me') {
          return mockJsonResponse({
            success: true,
            user: {
              id: 'user-customer',
              username: 'customer',
              role: 'member',
              company_id: 'customer-company-1',
            },
          });
        }
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    await waitFor(() => {
      expect(requests.some((request) => request.url === '/api/auth/me')).toBe(true);
    });
    expect(screen.queryByRole('button', { name: '服务商应用配置' })).not.toBeInTheDocument();
  });

  it('当前版本允许客户公司 admin 测试服务商应用配置入口', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/auth/me') {
          return mockJsonResponse({
            success: true,
            user: {
              id: 'user-customer-admin',
              username: 'admin',
              role: 'admin',
              company_id: '00000000-0000-0000-0000-000000000001',
            },
          });
        }
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    expect(await screen.findByRole('button', { name: '服务商应用配置' })).toBeInTheDocument();
  });

  it('Tally 服务商管理员可打开并保存淘宝天猫应用配置', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url === '/api/auth/me') {
          return mockJsonResponse({
            success: true,
            user: {
              id: 'user-provider-admin',
              username: 'provider-admin',
              role: 'admin',
              company_id: SERVICE_PROVIDER_COMPANY_ID,
            },
          });
        }
        if (url.includes('/app-config') && init?.method === 'PUT') {
          return mockJsonResponse({
            success: true,
            message: '平台应用配置已保存。',
            config: {
              platform_code: 'taobao',
              app_key: 'new-app-key',
              app_secret: '',
              has_app_secret: true,
              redirect_uri: 'https://callback.example.com/taobao',
            },
          });
        }
        if (url.includes('/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: true,
            config: {
              platform_code: 'taobao',
              app_key: 'old-app-key',
              app_secret: '',
              has_app_secret: true,
              redirect_uri: 'https://old.example.com/callback',
            },
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(await screen.findByRole('button', { name: '服务商应用配置' }));

    expect(await screen.findByRole('heading', { name: '服务商应用配置' })).toBeInTheDocument();
    expect(await screen.findByLabelText('AppKey')).toHaveValue('old-app-key');

    fireEvent.change(screen.getByLabelText('AppKey'), { target: { value: 'new-app-key' } });
    fireEvent.change(screen.getByLabelText('AppSecret'), { target: { value: 'new-secret' } });
    fireEvent.change(screen.getByLabelText('回调地址'), {
      target: { value: 'https://callback.example.com/taobao' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存应用配置' }));

    await waitFor(() => {
      expect(
        requests.some(
          (request) => request.url === '/api/platform-connections/taobao/app-config' && request.init?.method === 'PUT',
        ),
      ).toBe(true);
    });
    const saveRequest = requests.find(
      (request) => request.url === '/api/platform-connections/taobao/app-config' && request.init?.method === 'PUT',
    );
    expect(JSON.parse(String(saveRequest?.init?.body || '{}'))).toEqual({
      app_key: 'new-app-key',
      app_secret: 'new-secret',
      redirect_uri: 'https://callback.example.com/taobao',
      app_public_cert: '',
      alipay_public_cert: '',
      alipay_root_cert: '',
      mode: 'real',
    });
    expect(await screen.findByText('平台应用配置已保存。')).toBeInTheDocument();
  });

  it('Tally 服务商管理员可保存支付宝应用配置和证书字段', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url === '/api/auth/me') {
          return mockJsonResponse({
            success: true,
            user: {
              id: 'user-provider-admin',
              username: 'provider-admin',
              role: 'admin',
              company_id: SERVICE_PROVIDER_COMPANY_ID,
            },
          });
        }
        if (url.includes('/platform-connections/alipay/app-config') && init?.method === 'PUT') {
          return mockJsonResponse({
            success: true,
            message: '平台应用配置已保存。',
            config: {
              platform_code: 'alipay',
              app_key: '2021006152656574',
              app_secret: '',
              has_app_secret: true,
              has_app_public_cert: true,
              has_alipay_public_cert: true,
              has_alipay_root_cert: true,
              redirect_uri: 'https://tally.example.com/api/platform-auth/callback/alipay',
            },
          });
        }
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: false,
            config: {
              platform_code: 'alipay',
              app_key: '',
              app_secret: '',
              has_app_secret: false,
              has_app_public_cert: false,
              has_alipay_public_cert: false,
              has_alipay_root_cert: false,
              redirect_uri: 'https://tally.example.com/api/platform-auth/callback/alipay',
            },
          });
        }
        if (url.includes('/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: false,
            config: {
              platform_code: 'taobao',
              app_key: '',
              app_secret: '',
              has_app_secret: false,
              redirect_uri: 'https://tally.example.com/api/platform-auth/callback/taobao',
            },
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(await screen.findByRole('button', { name: '服务商应用配置' }));
    fireEvent.click(await screen.findByRole('button', { name: '支付宝' }));

    expect(await screen.findByLabelText('AppID')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('AppID'), { target: { value: '2021006152656574' } });
    fireEvent.change(screen.getByLabelText('应用私钥'), { target: { value: 'PRIVATE-KEY' } });
    fireEvent.change(screen.getByLabelText('应用公钥证书'), { target: { value: 'APP-CERT' } });
    fireEvent.change(screen.getByLabelText('支付宝公钥证书'), { target: { value: 'ALIPAY-CERT' } });
    fireEvent.change(screen.getByLabelText('支付宝根证书'), { target: { value: 'ROOT-CERT' } });
    fireEvent.change(screen.getByLabelText('授权回调地址'), {
      target: { value: 'https://tally.example.com/api/platform-auth/callback/alipay' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存应用配置' }));

    await waitFor(() => {
      expect(
        requests.some(
          (request) => request.url === '/api/platform-connections/alipay/app-config' && request.init?.method === 'PUT',
        ),
      ).toBe(true);
    });
    const saveRequest = requests.find(
      (request) => request.url === '/api/platform-connections/alipay/app-config' && request.init?.method === 'PUT',
    );
    expect(JSON.parse(String(saveRequest?.init?.body || '{}'))).toEqual({
      app_key: '2021006152656574',
      app_secret: 'PRIVATE-KEY',
      redirect_uri: 'https://tally.example.com/api/platform-auth/callback/alipay',
      app_public_cert: 'APP-CERT',
      alipay_public_cert: 'ALIPAY-CERT',
      alipay_root_cert: 'ROOT-CERT',
      mode: 'real',
    });
  });

  it('支付宝应用配置加载时只展示密钥和证书存在状态', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/auth/me') {
          return mockJsonResponse({
            success: true,
            user: {
              id: 'user-provider-admin',
              username: 'provider-admin',
              role: 'admin',
              company_id: SERVICE_PROVIDER_COMPANY_ID,
            },
          });
        }
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: true,
            config: {
              platform_code: 'alipay',
              app_key: '2021006152656574',
              app_secret: '',
              has_app_secret: true,
              has_app_public_cert: true,
              has_alipay_public_cert: true,
              has_alipay_root_cert: true,
              redirect_uri: 'https://tally.example.com/api/platform-auth/callback/alipay',
            },
          });
        }
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'supported',
              },
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 0,
                error_shop_count: 0,
                status: 'planned',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(await screen.findByRole('button', { name: '服务商应用配置' }));
    fireEvent.click(await screen.findByRole('button', { name: '支付宝' }));

    expect(await screen.findByLabelText('AppID')).toHaveValue('2021006152656574');
    expect(screen.getByPlaceholderText('留空则沿用已保存应用私钥')).toHaveValue('');
    expect(screen.getByPlaceholderText('留空则沿用已保存应用公钥证书')).toHaveValue('');
    expect(screen.getByPlaceholderText('留空则沿用已保存支付宝公钥证书')).toHaveValue('');
    expect(screen.getByPlaceholderText('留空则沿用已保存支付宝根证书')).toHaveValue('');
    expect(screen.queryByDisplayValue('PRIVATE-KEY')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('APP-CERT')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('ALIPAY-CERT')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('ROOT-CERT')).not.toBeInTheDocument();
  });

  it('店铺需重授权状态展示为需重授权且保留重授权操作', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/auth/me') {
          return mockJsonResponse({
            success: true,
            user: {
              id: 'user-customer',
              username: 'customer',
              role: 'user',
              company_id: 'customer-company-1',
            },
          });
        }
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.includes('/shops')) {
          return mockJsonResponse({
            shops: [
              {
                id: 'shop-reauth-1',
                platform_code: 'taobao',
                external_shop_id: 'tb-shop-1',
                external_shop_name: 'Tally 测试店',
                auth_status: 'reauth_required',
                token_expires_at: null,
                last_sync_at: null,
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'taobao',
                platform_name: '淘宝/天猫',
                authorized_shop_count: 1,
                error_shop_count: 1,
                status: 'supported',
              },
            ],
          });
        }
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    await screen.findByText('编码：taobao');
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));

    expect(await screen.findByText('需重授权')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重授权' })).toBeInTheDocument();
  });
});
