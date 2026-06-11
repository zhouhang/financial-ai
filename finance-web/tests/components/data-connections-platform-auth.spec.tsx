import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DataConnectionsPanel from '../../src/components/DataConnectionsPanel';
import type { CollaborationProvider } from '../../src/types';

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

  it('数据库连接列表加载中展示加载态而不是空态', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/data-sources') {
          return new Promise<Response>(() => undefined);
        }
        if (url.startsWith('/api/platform-connections')) {
          return Promise.resolve(mockJsonResponse({ platforms: [] }));
        }
        if (url === '/api/collaboration-channels') {
          return Promise.resolve(mockJsonResponse({ channels: [] }));
        }
        if (url === '/api/auth/me') {
          return Promise.resolve(mockJsonResponse({ user: { role: 'admin' } }));
        }
        return Promise.resolve(mockJsonResponse({}));
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('数据库连接列表')).toBeInTheDocument();
    expect(screen.getByText('正在加载连接列表')).toBeInTheDocument();
    expect(screen.queryByText('当前类型暂无连接，可先新增占位连接。')).not.toBeInTheDocument();
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

  it('淘宝天猫 ISV 申请期间禁用新增授权入口', async () => {
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
          throw new Error('淘宝/天猫 ISV 申请期间不应请求授权会话');
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
    const isvButton = screen.getByRole('button', { name: 'ISV申请中' });
    expect(isvButton).toBeDisabled();
    fireEvent.click(isvButton);
    expect(screen.queryByRole('dialog', { name: '新增支付宝商户授权' })).not.toBeInTheDocument();
    expect(requests.some((request) => request.url.includes('/auth-sessions'))).toBe(false);
  });

  it.each([
    ['dingtalk_dws', '钉钉'],
    ['feishu', '飞书'],
    ['wechat_work', '企微'],
  ] satisfies Array<[CollaborationProvider, string]>)(
    '%s 新增协作通道配置使用弹窗交互',
    async (provider, label) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: RequestInfo | URL) => {
          const url = String(input);
          if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
          if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
          if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
          return mockJsonResponse({});
        }),
      );

      render(
        <DataConnectionsPanel
          authToken="token"
          selectedConnectionView="collaboration_channels"
          selectedSourceKind="platform_oauth"
          selectedCollaborationProvider={provider}
        />,
      );

      await screen.findByRole('button', { name: '新增配置' });
      expect(screen.getByText('当前协作通道还没有配置，可先新增默认通道。')).toBeInTheDocument();
      expect(screen.queryByText('请选择一条协作通道配置进行编辑，或点击“新增配置”创建新的通道。')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: '新增配置' }));

      const dialog = await screen.findByRole('dialog', { name: `新增${label}协作通道配置` });
      expect(within(dialog).getByLabelText('通道名称')).toHaveValue(`${label}默认通道`);
      expect(within(dialog).getByRole('button', { name: '保存配置' })).toBeInTheDocument();
      expect(within(dialog).getByRole('button', { name: '取消' })).toBeInTheDocument();
      expect(screen.queryByText('请选择一条协作通道配置进行编辑，或点击“新增配置”创建新的通道。')).not.toBeInTheDocument();
    },
  );

  it('支付宝新增授权生成企业专属授权链接', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url === '/api/platform-connections/alipay/auth-sessions') {
          return mockJsonResponse({
            success: true,
            platform_code: 'alipay',
            state: 'state-alipay-1',
            auth_url:
              'https://openauth.alipay.com/oauth2/appToAppAuth.htm?app_id=2021006152656574&state=state-alipay-1',
          });
        }
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: true,
            config: {
              platform_code: 'alipay',
              app_key: '2021006152656574',
              has_app_secret: true,
              redirect_uri: 'https://dev.tallyai.cn/api/platform-auth/callback/alipay',
              merchant_auth_pc_url: 'https://b.alipay.com/page/message/tasksDetail?bizData=abc',
              merchant_auth_qr_url: 'https://static.example.com/alipay-qr.png',
            },
          });
        }
        if (url.includes('/pending-authorizations')) {
          return mockJsonResponse({ success: true, pending_authorizations: [], count: 0 });
        }
        if (url.includes('/shops')) return mockJsonResponse({ shops: [] });
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

    await screen.findByText('编码：alipay');
    const alipayCard = screen.getByText('编码：alipay').closest('div.rounded-2xl');
    expect(alipayCard).toBeTruthy();
    fireEvent.click(within(alipayCard as HTMLElement).getByRole('button', { name: '新增授权' }));

    const dialog = await screen.findByRole('dialog', { name: '新增支付宝商户授权' });
    fireEvent.change(within(dialog).getByLabelText('商户显示名称'), {
      target: { value: '对对科技' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '生成专属授权链接' }));

    expect(await within(dialog).findByText('企业专属授权链接')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('企业专属授权链接')).toHaveValue(
      'https://openauth.alipay.com/oauth2/appToAppAuth.htm?app_id=2021006152656574&state=state-alipay-1',
    );
    const sessionRequest = requests.find((request) => request.url === '/api/platform-connections/alipay/auth-sessions');
    expect(sessionRequest).toBeTruthy();
    expect(JSON.parse(String(sessionRequest?.init?.body))).toMatchObject({
      return_path: '/data-connections?mode=platform&platform=alipay',
      mode: 'real',
      merchant_display_name: '对对科技',
    });
  });

  it('淘宝天猫详情页禁用新增店铺授权入口', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/app-config')) {
          return mockJsonResponse({ success: true, configured: false, config: {} });
        }
        if (url.includes('/shops')) {
          return mockJsonResponse({ shops: [] });
        }
        if (url.includes('/auth-sessions')) {
          throw new Error('淘宝/天猫 ISV 申请期间不应请求授权会话');
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
    const isvButton = screen.getByRole('button', { name: 'ISV申请中' });
    expect(isvButton).toBeDisabled();
    fireEvent.click(isvButton);
    expect(requests.some((request) => request.url.includes('/auth-sessions'))).toBe(false);
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
              merchant_auth_pc_url: 'https://b.alipay.com/page/message/tasksDetail?bizData=abc',
              merchant_auth_qr_url: '',
            },
          });
        }
        if (url.includes('/platform-connections/alipay/app-config/merchant-auth-qr')) {
          return mockJsonResponse({
            success: true,
            message: '支付宝商家授权二维码已上传',
            merchant_auth_qr_url: '/api/platform-connections/alipay/assets/merchant-auth-qr.png',
            config: {
              platform_code: 'alipay',
              app_key: '2021006152656574',
              merchant_auth_qr_url: '/api/platform-connections/alipay/assets/merchant-auth-qr.png',
              has_app_secret: true,
              has_app_public_cert: true,
              has_alipay_public_cert: true,
              has_alipay_root_cert: true,
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
    fireEvent.change(screen.getByLabelText('商家授权 PC 链接'), {
      target: { value: 'https://b.alipay.com/page/message/tasksDetail?bizData=abc' },
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
      merchant_auth_mode: 'static_invite',
      merchant_auth_pc_url: 'https://b.alipay.com/page/message/tasksDetail?bizData=abc',
      merchant_auth_qr_url: '',
      mode: 'real',
    });

    const qrFile = new File(['qr'], 'alipay-qr.png', { type: 'image/png' });
    const qrInput = screen.getByLabelText('上传二维码图片');
    fireEvent.change(qrInput, { target: { files: [qrFile] } });

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.url === '/api/platform-connections/alipay/app-config/merchant-auth-qr' &&
            request.init?.method === 'POST',
        ),
      ).toBe(true);
    });
    const uploadRequest = requests.find(
      (request) =>
        request.url === '/api/platform-connections/alipay/app-config/merchant-auth-qr' &&
        request.init?.method === 'POST',
    );
    expect(uploadRequest?.init?.body).toBeInstanceOf(FormData);
    expect(await screen.findByText('支付宝商家授权二维码已上传')).toBeInTheDocument();
    expect(await screen.findByAltText('已上传支付宝商家授权二维码')).toHaveAttribute(
      'src',
      '/api/platform-connections/alipay/assets/merchant-auth-qr.png',
    );
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

  it('支付宝商户列表不展示额外授权入口', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: true,
            config: {
              platform_code: 'alipay',
              app_key: '2021006152656574',
              has_app_secret: true,
              redirect_uri: 'https://dev.tallyai.cn/api/platform-auth/callback/alipay',
              merchant_auth_mode: 'static_invite',
              merchant_auth_pc_url: 'https://b.alipay.com/page/message/tasksDetail?bizData=abc',
              merchant_auth_qr_url: 'https://static.example.com/alipay-qr.png',
            },
          });
        }
        if (url.includes('/pending-authorizations')) {
          return mockJsonResponse({ success: true, pending_authorizations: [], count: 0 });
        }
        if (url.includes('/shops')) return mockJsonResponse({ shops: [] });
        if (url.includes('/app-config')) return mockJsonResponse({ success: true, configured: false, config: {} });
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
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

    await screen.findByText('编码：alipay');
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));

    expect(await screen.findByText('支付宝商户列表')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新增授权' })).toBeInTheDocument();
    expect(screen.queryByText('支付宝商家授权入口')).not.toBeInTheDocument();
    expect(screen.queryByAltText('支付宝商家授权二维码')).not.toBeInTheDocument();
    expect(screen.queryByText('待配置支付宝商家授权二维码')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '生成专属授权链接' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '打开支付宝商家授权' })).not.toBeInTheDocument();
  });

  it('支付宝商户列表隐藏待绑定区域并保留商户字段和可用操作', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({
            success: true,
            configured: true,
            config: {
              platform_code: 'alipay',
              app_key: '2021006152656574',
              has_app_secret: true,
              redirect_uri: 'https://dev.tallyai.cn/api/platform-auth/callback/alipay',
              merchant_auth_pc_url: 'https://b.alipay.com/page/message/tasksDetail?bizData=abc',
              merchant_auth_qr_url: 'https://static.example.com/alipay-qr.png',
            },
          });
        }
        if (url.includes('/pending-authorizations')) {
          return mockJsonResponse({
            success: true,
            pending_authorizations: [
              {
                id: 'pending-1',
                platform_code: 'alipay',
                claim_code: 'ALIPAY-123456',
                status: 'pending_claim',
                external_shop_id: '2088123412341234',
                expires_at: '2026-05-10T00:00:00+08:00',
                created_at: '2026-05-09T12:00:00+08:00',
              },
            ],
            count: 1,
          });
        }
        if (url.includes('/shops')) {
          return mockJsonResponse({
            shops: [
              {
                id: 'shop-alipay-1',
                platform_code: 'alipay',
                external_shop_id: '2088123412341234',
                external_shop_name: '对对科技',
                auth_status: 'authorized',
                token_expires_at: '2027-05-09T12:00:00+08:00',
                last_sync_at: '2026-05-09T12:30:00+08:00',
              },
            ],
          });
        }
        if (url.includes('/app-config')) return mockJsonResponse({ success: true, configured: false, config: {} });
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
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

    await screen.findByText('编码：alipay');
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));

    expect(await screen.findByText('对对科技')).toBeInTheDocument();
    expect(screen.getByText('商户名称')).toBeInTheDocument();
    expect(screen.getByText('商户 ID')).toBeInTheDocument();
    expect(screen.getByText('2088123412341234')).toBeInTheDocument();
    expect(screen.getByText('已授权')).toBeInTheDocument();
    expect(screen.queryByText('店铺名称')).not.toBeInTheDocument();
    expect(screen.queryByText('店铺 ID')).not.toBeInTheDocument();
    expect(screen.queryByText('待绑定授权')).not.toBeInTheDocument();
    expect(screen.queryByText('绑定到当前企业')).not.toBeInTheDocument();
    expect(screen.queryByText('认领码：ALIPAY-123456')).not.toBeInTheDocument();
    expect(screen.queryByText('ALIPAY-123456')).not.toBeInTheDocument();
    const shopTable = screen.getByText('商户 ID').closest('table');
    expect(shopTable).toHaveClass('min-w-[1100px]');
    expect(shopTable?.parentElement).toHaveClass('overflow-x-auto');
    expect(screen.getByRole('button', { name: '重授权' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '停用' })).toBeInTheDocument();
    expect(requests.some((request) => request.url.includes('/pending-authorizations'))).toBe(false);
  });

  it('无 state 支付宝回调成功页隐藏认领码并直接绑定当前企业', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/pending-authorizations/pending-1/claim')) {
          return mockJsonResponse({
            success: true,
            message: '支付宝商户授权已绑定',
            shop: { id: 'shop-alipay-1', platform_code: 'alipay', external_shop_name: '福游网络' },
          });
        }
        if (url.includes('/platform-connections/alipay/shops')) {
          return mockJsonResponse({
            shops: [
              {
                id: 'shop-alipay-1',
                platform_code: 'alipay',
                external_shop_id: '2088123412341234',
                external_shop_name: '福游网络',
                auth_status: 'authorized',
                token_expires_at: '2027-05-09T12:00:00+08:00',
                last_sync_at: '2026-05-09T12:30:00+08:00',
              },
            ],
          });
        }
        if (url.includes('/app-config')) return mockJsonResponse({ success: true, configured: false, config: {} });
        if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
        if (url === '/api/data-sources') return mockJsonResponse({ data_sources: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        initialCallback={{
          platformCode: 'alipay',
          status: 'success',
          message: '支付宝授权已收到，请填写支付宝商户名称完成绑定',
          pendingAuthorizationId: 'pending-1',
          claimCode: 'ALIPAY-123456',
        }}
        selectedConnectionView="data_sources"
        selectedSourceKind="platform_oauth"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('绑定支付宝授权到当前企业')).toBeInTheDocument();
    expect(screen.getByText('支付宝授权已收到，请填写支付宝商户名称完成绑定')).toBeInTheDocument();
    expect(screen.getByLabelText('支付宝商户名称')).toBeInTheDocument();
    expect(screen.queryByText('支付宝授权认领码')).not.toBeInTheDocument();
    expect(screen.queryByText(/认领码/)).not.toBeInTheDocument();
    expect(screen.queryByText('ALIPAY-123456')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('支付宝商户名称'), { target: { value: '福游网络' } });
    fireEvent.click(screen.getByRole('button', { name: '绑定到当前企业' }));

    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.url === '/api/platform-connections/alipay/pending-authorizations/pending-1/claim' &&
            request.init?.method === 'POST',
        ),
      ).toBe(true);
    });
    const claimRequest = requests.find(
      (request) => request.url === '/api/platform-connections/alipay/pending-authorizations/pending-1/claim',
    );
    expect(JSON.parse(String(claimRequest?.init?.body || '{}'))).toEqual({
      claim_code: 'ALIPAY-123456',
      merchant_display_name: '福游网络',
      mode: 'real',
    });
    expect(await screen.findByText('支付宝商户列表')).toBeInTheDocument();
    expect(screen.getByText('福游网络')).toBeInTheDocument();
    expect(screen.getByText('商户名称')).toBeInTheDocument();
    expect(screen.queryByText('绑定支付宝授权到当前企业')).not.toBeInTheDocument();
  });

  it('支付宝商户绑定后可直接展开固定数据集', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({ success: true, configured: true, config: { platform_code: 'alipay' } });
        }
        if (url.includes('/platform-connections/alipay/shops')) {
          return mockJsonResponse({
            shops: [
              {
                id: 'shop-alipay-1',
                platform_code: 'alipay',
                external_shop_id: '2088123412341234',
                external_shop_name: '对对科技',
                auth_status: 'authorized',
                token_expires_at: '2027-05-09T12:00:00+08:00',
                last_sync_at: '2026-05-09T12:30:00+08:00',
              },
            ],
          });
        }
        if (url.includes('/data-sources/source-alipay-1/datasets/dataset-trade/collection-detail')) {
          return mockJsonResponse({
            dataset: {
              id: 'dataset-trade',
              data_source_id: 'source-alipay-1',
              dataset_code: 'alipay_trade_bill_shop_alipay_1',
              dataset_name: '支付宝交易账单 - 对对科技',
              business_name: '业务数据集',
              resource_key: 'alipay_bill:trade:shop-alipay-1',
            },
            collection_status: { status: 'failed', message: '此账单类型不支持下载' },
            semantic_status: { status: 'ready' },
            field_groups: [
              {
                key: 'normalized',
                label: '标准字段',
                default_open: true,
                fields: [
                  { raw_name: '账务流水号', display_name: '账务流水号' },
                  { raw_name: '业务流水号', display_name: '业务流水号' },
                  { raw_name: '商品名称', display_name: '商品名称' },
                  { raw_name: '发生时间', display_name: '发生时间' },
                  { raw_name: '收入金额（+元）', display_name: '收入金额（+元）' },
                  { raw_name: '支出金额（-元）', display_name: '支出金额（-元）' },
                  { raw_name: '账户余额（元）', display_name: '账户余额（元）' },
                  { raw_name: '交易渠道', display_name: '交易渠道' },
                  { raw_name: '业务类型', display_name: '业务类型' },
                  { raw_name: '备注', display_name: '备注' },
                  { raw_name: '商户订单号', display_name: '商户订单号' },
                  { raw_name: '对方账号', display_name: '对方账号' },
                  { raw_name: '业务基础订单号', display_name: '业务基础订单号' },
                  { raw_name: '业务订单号', display_name: '业务订单号' },
                  { raw_name: '业务账单来源', display_name: '业务账单来源' },
                  { raw_name: '业务描述', display_name: '业务描述' },
                ],
              },
              {
                key: 'raw_bill',
                label: '原始账单字段',
                default_open: true,
                fields: [{ raw_name: 'raw.收入', display_name: 'RAW重复收入列' }],
              },
              {
                key: 'system',
                label: '系统字段',
                default_open: false,
                fields: [{ raw_name: 'dataset_id', display_name: '数据集ID' }],
              },
            ],
            rows: [],
          });
        }
        if (
          url.includes('/data-sources/source-alipay-1/datasets/dataset-trade/collection') &&
          init?.method === 'POST'
        ) {
          return mockJsonResponse({ success: true, message: '已提交初始化任务' });
        }
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'source-alipay-1',
                source_kind: 'platform_oauth',
                provider_code: 'alipay',
                name: '支付宝授权 - 对对科技',
                status: 'active',
                execution_mode: 'deterministic',
                datasets: [
                  {
                    id: 'dataset-trade',
                    data_source_id: 'source-alipay-1',
                    dataset_code: 'alipay_trade_bill_shop_alipay_1',
                    dataset_name: '支付宝交易账单 - 对对科技',
                    business_name: '业务数据集',
                    resource_key: 'alipay_bill:trade:shop-alipay-1',
                    status: 'active',
                    publish_status: 'unpublished',
                  },
                ],
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 1,
                error_shop_count: 0,
                status: 'active',
              },
            ],
          });
        }
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
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));
    await screen.findByText('对对科技');
    fireEvent.click(screen.getByRole('button', { name: '数据集' }));

    expect(await screen.findByRole('dialog', { name: '支付宝商户数据集' })).toBeInTheDocument();
    expect(await screen.findByText('支付宝交易账单 - 对对科技')).toBeInTheDocument();
    expect(screen.queryByText('业务数据集')).not.toBeInTheDocument();
    expect(screen.queryByText('固定数据集')).not.toBeInTheDocument();
    expect(screen.queryByText('字段结构')).not.toBeInTheDocument();
    expect(screen.getByText('数据预览')).toBeInTheDocument();
    expect(screen.queryByText('真实数据预览')).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '账务流水号' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '业务基础订单号' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '业务订单号' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '业务账单来源' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '业务描述' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'dataset_id' })).not.toBeInTheDocument();
    expect(screen.getByText('暂无数据。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新初始化' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '初始化重试' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新初始化' }));
    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.url.includes('/data-sources/source-alipay-1/datasets/dataset-trade/collection') &&
            request.init?.method === 'POST',
        ),
      ).toBe(true);
    });
    expect(screen.queryByText('未找到该店铺的固定数据集。')).not.toBeInTheDocument();
    expect(
      requests.some((request) =>
        request.url.includes('/data-sources/source-alipay-1/datasets/dataset-trade/collection-detail'),
      ),
    ).toBe(true);

    const shopTable = screen.getByText('商户 ID').closest('table');
    expect(shopTable).toHaveClass('min-w-[1100px]');
    expect(within(shopTable as HTMLElement).queryByText('支付宝交易账单 - 对对科技')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '数据集' })).toHaveClass('whitespace-nowrap');
    expect(screen.getByRole('button', { name: '重授权' })).toHaveClass('whitespace-nowrap');
    expect(screen.getByRole('button', { name: '停用' })).toHaveClass('whitespace-nowrap');
  });

  it('数据库数据集详情按钮打开预览抽屉展示最新数据', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/data-sources/source-db-1/datasets/dataset-order/detail')) {
          return mockJsonResponse({
            success: true,
            source_id: 'source-db-1',
            resource_key: 'public.ods_yxst_trd_order_di_o',
            dataset: { id: 'dataset-order' },
            field_groups: [
              {
                key: 'default',
                label: '字段',
                defaultOpen: true,
                fields: [
                  { raw_name: 'order_id', display_name: '订单ID', semantic_type: 'id' },
                  { raw_name: 'create_date', display_name: '创建日期', semantic_type: 'date' },
                ],
              },
            ],
            preview_sample: {
              rows: [{ order_id: 'ORD001', create_date: '2026-06-10' }],
              order: 'date_field_desc',
              order_field: 'create_date',
            },
            rows: [{ order_id: 'ORD001', create_date: '2026-06-10' }],
            sample_limit: 10,
            row_count: 1,
            message: '已获取数据集详情',
          });
        }
        if (url.includes('/data-sources/source-db-1/datasets?')) {
          return mockJsonResponse({
            datasets: [
              {
                id: 'dataset-order',
                data_source_id: 'source-db-1',
                dataset_code: 'public_ods_yxst_trd_order_di_o',
                dataset_name: 'public.ods_yxst_trd_order_di_o',
                business_name: '交易订单明细表',
                resource_key: 'public.ods_yxst_trd_order_di_o',
                status: 'active',
                publish_status: 'published',
              },
            ],
          });
        }
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'source-db-1',
                source_kind: 'database',
                provider_code: 'hologres',
                name: 'Hologres 订单库',
                status: 'active',
                execution_mode: 'deterministic',
                datasets: [
                  {
                    id: 'dataset-order',
                    data_source_id: 'source-db-1',
                    dataset_code: 'public_ods_yxst_trd_order_di_o',
                    dataset_name: 'public.ods_yxst_trd_order_di_o',
                    business_name: '交易订单明细表',
                    resource_key: 'public.ods_yxst_trd_order_di_o',
                    status: 'active',
                    publish_status: 'published',
                  },
                ],
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('Hologres 订单库')).toBeInTheDocument();
    fireEvent.click(screen.getByText('进入详情'));
    expect(await screen.findByText('交易订单明细表')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(await screen.findByRole('heading', { name: '详情' })).toBeInTheDocument();
    expect(await screen.findByText('最新 10 条数据')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '立即采集' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '按日期采集' })).not.toBeInTheDocument();
    expect(screen.queryByText('最近采集任务')).not.toBeInTheDocument();
  });

  it('数据库数据集详情抽屉不展示采集相关操作', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/data-sources/source-db-1/datasets/dataset-no-date/detail')) {
          return mockJsonResponse({
            success: true,
            source_id: 'source-db-1',
            resource_key: 'public.no_date_table',
            dataset: { id: 'dataset-no-date' },
            field_groups: [],
            preview_sample: {},
            rows: [],
            sample_limit: 10,
            row_count: 0,
            message: '已获取数据集详情',
          });
        }
        if (url.includes('/data-sources/source-db-1/datasets?')) {
          return mockJsonResponse({
            datasets: [
              {
                id: 'dataset-no-date',
                data_source_id: 'source-db-1',
                dataset_code: 'public_no_date_table',
                dataset_name: 'public.no_date_table',
                business_name: '无日期字段表',
                resource_key: 'public.no_date_table',
                status: 'active',
                publish_status: 'published',
              },
            ],
          });
        }
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'source-db-1',
                source_kind: 'database',
                provider_code: 'hologres',
                name: 'Hologres 订单库',
                status: 'active',
                execution_mode: 'deterministic',
                datasets: [
                  {
                    id: 'dataset-no-date',
                    data_source_id: 'source-db-1',
                    dataset_code: 'public_no_date_table',
                    dataset_name: 'public.no_date_table',
                    business_name: '无日期字段表',
                    resource_key: 'public.no_date_table',
                    status: 'active',
                    publish_status: 'published',
                    collection_config: { mode: 'manual' },
                  },
                ],
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) return mockJsonResponse({ platforms: [] });
        if (url === '/api/collaboration-channels') return mockJsonResponse({ channels: [] });
        return mockJsonResponse({});
      }),
    );

    render(
      <DataConnectionsPanel
        authToken="token"
        selectedConnectionView="data_sources"
        selectedSourceKind="database"
        selectedCollaborationProvider="dingtalk_dws"
      />,
    );

    expect(await screen.findByText('Hologres 订单库')).toBeInTheDocument();
    fireEvent.click(screen.getByText('进入详情'));
    expect(await screen.findByText('无日期字段表')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(await screen.findByRole('heading', { name: '详情' })).toBeInTheDocument();
    expect(await screen.findByText('最新 10 条数据')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '按日期采集' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '立即采集' })).not.toBeInTheDocument();
  });

  it('支付宝商户数据集展示初始化采集条数并按状态控制发布入口', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    let publishAttempts = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({ success: true, configured: true, config: { platform_code: 'alipay' } });
        }
        if (url.includes('/data-sources/source-alipay-1/datasets/dataset-fund/publish')) {
          publishAttempts += 1;
          if (publishAttempts === 1) {
            return mockJsonResponse(
              { detail: 'field_label_map 包含不存在字段: bill_date' },
              false,
              400,
            );
          }
          return mockJsonResponse({
            success: true,
            message: '数据集已发布',
            dataset: {
              id: 'dataset-fund',
              data_source_id: 'source-alipay-1',
              dataset_code: 'alipay_fund_bill_shop_alipay_1',
              dataset_name: '支付宝资金账单 - 对对科技',
              resource_key: 'alipay_bill:signcustomer:shop-alipay-1',
              status: 'active',
              publish_status: 'published',
              semantic_status: 'manual_updated',
              field_label_map: { 账务流水号: '账务流水号' },
              semantic_fields: [{ raw_name: '账务流水号', display_name: '账务流水号' }],
            },
          });
        }
        if (url.includes('/platform-connections/alipay/shops')) {
          return mockJsonResponse({
            shops: [
              {
                id: 'shop-alipay-1',
                platform_code: 'alipay',
                external_shop_id: '2088123412341234',
                external_shop_name: '对对科技',
                auth_status: 'authorized',
                token_expires_at: '2027-05-09T12:00:00+08:00',
                last_sync_at: '2026-05-11T10:30:00+08:00',
              },
            ],
          });
        }
        if (url.includes('/data-sources/source-alipay-1/datasets/dataset-fund/collection-detail')) {
          return mockJsonResponse({
            dataset: {
              id: 'dataset-fund',
              data_source_id: 'source-alipay-1',
              dataset_code: 'alipay_fund_bill_shop_alipay_1',
              dataset_name: '支付宝资金账单 - 对对科技',
              resource_key: 'alipay_bill:signcustomer:shop-alipay-1',
              publish_status: 'unpublished',
              schema_summary: {
                columns: [{ name: 'raw' }, { name: '账务流水号' }],
              },
              field_label_map: { raw: '原始对象', 账务流水号: '账务流水号' },
              semantic_fields: [
                { raw_name: 'raw', display_name: '原始对象' },
                { raw_name: '账务流水号', display_name: '账务流水号' },
              ],
            },
            collection_stats: { total_count: 233 },
            collection_status: {
              status: 'succeeded',
              message: '已采集真实样本',
              total_count: 233,
              row_count: 20,
              latest_job: {
                request_payload: { bill_date: '2026-05-10', bill_type: 'signcustomer' },
                checkpoint_after: { last_row_count: 233 },
                completed_at: '2026-05-11T10:30:00+08:00',
              },
            },
            semantic_status: { status: 'succeeded', message: '已生成语义结构' },
            field_groups: [
              {
                key: 'normalized',
                label: '标准字段',
                fields: [{ raw_name: '账务流水号', display_name: '账务流水号' }],
              },
              {
                key: 'raw_bill',
                label: '原始账单字段',
                default_open: true,
                fields: [{ raw_name: 'raw.收入', display_name: 'RAW重复收入列' }],
              },
            ],
            rows: [{ 账务流水号: 'A001' }],
          });
        }
        if (url.includes('/data-sources/source-alipay-1/datasets/dataset-trade/collection-detail')) {
          return mockJsonResponse({
            dataset: {
              id: 'dataset-trade',
              data_source_id: 'source-alipay-1',
              dataset_code: 'alipay_trade_bill_shop_alipay_1',
              dataset_name: '支付宝交易账单 - 对对科技',
              resource_key: 'alipay_bill:trade:shop-alipay-1',
              publish_status: 'unpublished',
            },
            collection_stats: { total_count: 0 },
            collection_status: {
              status: 'failed',
              message: '此账单类型不支持下载（TYPE_NOT_SUPPORTED）',
              total_count: 0,
              row_count: 0,
              latest_job: {
                request_payload: { bill_date: '2026-05-10', bill_type: 'trade' },
                error_message: '此账单类型不支持下载（TYPE_NOT_SUPPORTED）',
                completed_at: '2026-05-11T10:30:00+08:00',
              },
            },
            semantic_status: { status: 'waiting_for_samples', message: '等待采集样本后生成语义结构' },
            field_groups: [],
            rows: [],
          });
        }
        if (url === '/api/data-sources') {
          return mockJsonResponse({
            data_sources: [
              {
                id: 'source-alipay-1',
                source_kind: 'platform_oauth',
                provider_code: 'alipay',
                name: '支付宝授权 - 对对科技',
                status: 'active',
                execution_mode: 'deterministic',
                datasets: [
                  {
                    id: 'dataset-fund',
                    data_source_id: 'source-alipay-1',
                    dataset_code: 'alipay_fund_bill_shop_alipay_1',
                    dataset_name: '支付宝资金账单 - 对对科技',
                    resource_key: 'alipay_bill:signcustomer:shop-alipay-1',
                    status: 'active',
                    publish_status: 'unpublished',
                    key_fields: ['raw.收入', '账务流水号'],
                    field_label_map: {
                      'raw.收入': 'RAW重复收入列',
                      账务流水号: '账务流水号',
                    },
                  },
                  {
                    id: 'dataset-trade',
                    data_source_id: 'source-alipay-1',
                    dataset_code: 'alipay_trade_bill_shop_alipay_1',
                    dataset_name: '支付宝交易账单 - 对对科技',
                    resource_key: 'alipay_bill:trade:shop-alipay-1',
                    status: 'active',
                    publish_status: 'unpublished',
                  },
                ],
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: 1,
                error_shop_count: 0,
                status: 'active',
              },
            ],
          });
        }
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
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));
    await screen.findByText('对对科技');
    fireEvent.click(screen.getByRole('button', { name: '数据集' }));

    expect(await screen.findByText('支付宝资金账单 - 对对科技')).toBeInTheDocument();
    expect(screen.getByText('初始化：已采集真实样本 233 条')).toBeInTheDocument();
    expect(screen.getByText('每日采集：最近 2026-05-10，233 条')).toBeInTheDocument();
    expect(screen.getByText('支付宝交易账单 - 对对科技')).toBeInTheDocument();
    expect(screen.getByText('初始化失败：此账单类型不支持下载（TYPE_NOT_SUPPORTED）')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '采集详情' })).toHaveLength(2);
    expect(screen.getByRole('button', { name: '发布' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '管理发布' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '刷新语义' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新生成语义' })).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: '采集详情' })[0]);
    expect(await screen.findByRole('heading', { name: '采集详情' })).toBeInTheDocument();
    expect(screen.queryByText('raw.收入')).not.toBeInTheDocument();
    expect(screen.queryByText('RAW重复收入列')).not.toBeInTheDocument();
    expect(screen.getByText('采集记录数')).toBeInTheDocument();
    const closeButtons = screen.getAllByRole('button', { name: '关闭' });
    fireEvent.click(closeButtons[closeButtons.length - 1]);

    fireEvent.click(screen.getByRole('button', { name: '发布' }));
    expect(await screen.findByRole('heading', { name: '发布数据集' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '确认发布' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '确认发布' }));
    const publishError = await screen.findByText('field_label_map 包含不存在字段: bill_date');
    expect(publishError).toBeVisible();
    expect(publishError.closest('div')).toHaveClass('sticky');

    fireEvent.click(screen.getByRole('button', { name: '确认发布' }));
    expect(await screen.findByText('数据集已发布')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '管理发布' })).toBeInTheDocument();
    expect(screen.getByText('已发布')).toBeInTheDocument();
    const drawerCloseButtons = screen.getAllByRole('button', { name: '关闭' });
    fireEvent.click(drawerCloseButtons[drawerCloseButtons.length - 1]);
    expect(await screen.findByRole('button', { name: '管理发布' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '发布' })).not.toBeInTheDocument();
    expect(
      requests.some(
        (request) =>
          request.url === '/api/data-sources/source-alipay-1/datasets/dataset-fund/publish' &&
          request.init?.method === 'POST',
      ),
    ).toBe(true);
    const publishRequest = requests.find(
      (request) =>
        request.url === '/api/data-sources/source-alipay-1/datasets/dataset-fund/publish' &&
        request.init?.method === 'POST',
    );
    const publishPayload = JSON.parse(String(publishRequest?.init?.body || '{}'));
    expect(publishPayload.field_label_map.raw).toBeUndefined();
    expect(publishPayload.field_label_map['raw.收入']).toBeUndefined();
    expect(publishPayload.fields.some((field: { raw_name?: string }) => field.raw_name === 'raw')).toBe(false);
    expect(publishPayload.fields.some((field: { raw_name?: string }) => field.raw_name === 'raw.收入')).toBe(false);
    expect(publishPayload.key_fields).not.toContain('raw');
    expect(publishPayload.key_fields).not.toContain('raw.收入');
    expect(publishAttempts).toBe(2);
  }, 20000);

  it('支付宝商户停用需要二次确认后才执行停用', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    let disabled = false;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });
        if (url.includes('/shop-connections/shop-alipay-1/disable')) {
          disabled = true;
          return mockJsonResponse({
            success: true,
            message: '支付宝商户已停用',
            connection: {
              id: 'shop-alipay-1',
              platform_code: 'alipay',
              external_shop_id: '2088123412341234',
              external_shop_name: '对对科技',
              auth_status: 'disabled',
              status: 'disabled',
              token_expires_at: null,
              last_sync_at: '2026-05-09T12:30:00+08:00',
            },
          });
        }
        if (url.includes('/shop-connections/shop-alipay-1/reauthorize')) {
          return mockJsonResponse({
            success: true,
          });
        }
        if (url.includes('/platform-connections/alipay/app-config')) {
          return mockJsonResponse({ success: true, configured: true, config: { platform_code: 'alipay' } });
        }
        if (url.includes('/platform-connections/alipay/shops')) {
          return mockJsonResponse({
            shops: [
              {
                id: 'shop-alipay-1',
                platform_code: 'alipay',
                external_shop_id: '2088123412341234',
                external_shop_name: '对对科技',
                auth_status: disabled ? 'disabled' : 'authorized',
                status: disabled ? 'disabled' : 'authorized',
                token_expires_at: '2027-05-09T12:00:00+08:00',
                last_sync_at: '2026-05-09T12:30:00+08:00',
              },
            ],
          });
        }
        if (url.startsWith('/api/platform-connections')) {
          return mockJsonResponse({
            platforms: [
              {
                platform_code: 'alipay',
                platform_name: '支付宝',
                authorized_shop_count: disabled ? 0 : 1,
                error_shop_count: 0,
                status: disabled ? 'pending' : 'active',
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
    fireEvent.click(screen.getByRole('button', { name: '查看店铺' }));
    await screen.findByText('对对科技');
    fireEvent.click(screen.getByRole('button', { name: '停用' }));

    expect(await screen.findByRole('dialog', { name: '确认停用授权？' })).toBeInTheDocument();
    expect(screen.getByText('停用后该商户授权将不可用于后续采集；如需恢复，需要重新授权。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '确认停用' })).toHaveTextContent('确认停用');
    expect(screen.getByRole('button', { name: '确认停用' })).toBeVisible();
    expect(
      requests.some(
        (request) =>
          request.url === '/api/shop-connections/shop-alipay-1/disable' &&
          request.init?.method === 'POST',
      ),
    ).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('dialog', { name: '确认停用授权？' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '停用' }));
    fireEvent.click(await screen.findByRole('button', { name: '确认停用' }));

    expect(await screen.findByText('支付宝商户已停用')).toBeInTheDocument();
    expect(await screen.findByText('已停用')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重授权' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '停用' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新授权启用' }));
    expect(
      requests.some(
        (request) =>
          request.url === '/api/shop-connections/shop-alipay-1/disable' &&
          request.init?.method === 'POST',
      ),
    ).toBe(true);
    expect(
      requests.some(
        (request) =>
          request.url === '/api/shop-connections/shop-alipay-1/reauthorize' &&
          request.init?.method === 'POST',
      ),
    ).toBe(true);
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
