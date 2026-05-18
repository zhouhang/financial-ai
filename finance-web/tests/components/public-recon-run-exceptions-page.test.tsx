import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import PublicReconRunExceptionsPage from '../../src/components/PublicReconRunExceptionsPage';

function buildJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

describe('PublicReconRunExceptionsPage run metrics', () => {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    window.history.pushState({}, '', '/recon/runs/run-001/exceptions?owner=ding-user-001');
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
  });

  it('shows matched success and per-source recon input counts from run summary', async () => {
    fetchMock.mockResolvedValueOnce(buildJsonResponse({
      run: {
        id: 'run-001',
        run_code: 'run_code_001',
        scheme_code: 'scheme-001',
        plan_code: 'plan-001',
        scheme_name: '泰斯支付宝对账方案',
        plan_name: '泰斯支付宝对账',
        execution_status: 'success',
        started_at: '2026-05-12T09:00:00+08:00',
        finished_at: '2026-05-12T09:05:00+08:00',
        run_context_json: { biz_date: '2026-05-12' },
        recon_result_summary_json: {
          matched_exact: 170,
          source_only: 60,
          target_only: 12,
          matched_with_diff: 5,
        },
        source_snapshot_json: {
          collections: [
            {
              binding: {
                dataset_id: 'dataset-left',
                data_source_id: 'source-left',
                dataset_name: '交易订单明细表',
                resource_key: 'public.ods_yxst_trd_order_di_o',
              },
              collection_records: {
                record_count: 1,
              },
            },
            {
              binding: {
                dataset_id: 'dataset-right',
                data_source_id: 'source-right',
                dataset_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺',
                resource_key: 'alipay_bill:signcustomer:shop-001',
              },
              collection_records: {
                record_count: 340,
              },
            },
          ],
          collection_attempts: [
            {
              binding: {
                dataset_id: 'dataset-right',
                data_source_id: 'source-right',
                resource_key: 'alipay_bill:signcustomer:shop-001',
              },
              job: {
                metrics: {
                  collection_inserted: 0,
                  collection_updated: 340,
                  collection_upserted: 340,
                },
              },
            },
          ],
        },
      },
      scheme: {
        id: 'scheme-001',
        scheme_code: 'scheme-001',
        scheme_name: '泰斯支付宝对账方案',
        scheme_meta_json: {},
      },
      run_plan: {
        id: 'plan-001',
        plan_code: 'plan-001',
        plan_name: '泰斯支付宝对账',
      },
      exceptions: [],
      total: 60,
      limit: 100,
      offset: 0,
    }));

    render(<PublicReconRunExceptionsPage />);

    await waitFor(() => {
      expect(screen.getByText('匹配成功')).toBeInTheDocument();
    });

    const header = screen.getByText('对账差异公开分享').closest('header');
    expect(header).not.toBeNull();
    const headerView = within(header as HTMLElement);

    expect(headerView.getByText('成功')).toBeInTheDocument();
    expect(headerView.getByText('170')).toBeInTheDocument();
    expect(headerView.getByText('待处理差异')).toBeInTheDocument();
    expect(headerView.getByText('60')).toBeInTheDocument();
    expect(headerView.getByText('交易订单明细表')).toBeInTheDocument();
    expect(headerView.getByText('支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '数据 235 条')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '数据 187 条')).toBeInTheDocument();
    expect(headerView.queryByText('差异总数')).not.toBeInTheDocument();
    expect(headerView.queryByText('本次读取数据')).not.toBeInTheDocument();
    expect(headerView.queryByText('新增 0 / 更新 340')).not.toBeInTheDocument();
    expect(headerView.queryByText((_, element) => element?.textContent === '本次读取 1 条')).not.toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/recon/public/runs/run-001/exceptions?limit=100&offset=0&owner=ding-user-001',
      undefined,
    );
  });

  it('shows pending difference metrics and source-only suppression note from run summary', async () => {
    fetchMock.mockResolvedValueOnce(buildJsonResponse({
      run: {
        id: 'run-002',
        run_code: 'run_code_002',
        scheme_code: 'scheme-002',
        plan_code: 'plan-002',
        scheme_name: '泰斯支付宝对账方案',
        plan_name: '泰斯支付宝对账',
        execution_status: 'success',
        started_at: '2026-05-12T09:00:00+08:00',
        finished_at: '2026-05-12T09:05:00+08:00',
        run_context_json: { biz_date: '2026-05-12' },
        recon_result_summary_json: {
          matched_exact: 136,
          source_only: 69,
          target_only: 0,
          matched_with_diff: 0,
          pending_total: 0,
          temporary_suppression: {
            suppressed_source_only: 69,
            label: '非支付宝支付订单',
          },
        },
        source_snapshot_json: {
          collections: [
            {
              binding: {
                dataset_id: 'dataset-left',
                data_source_id: 'source-left',
                dataset_name: '交易订单明细表',
                resource_key: 'public.ods_yxst_trd_order_di_o',
              },
            },
            {
              binding: {
                dataset_id: 'dataset-right',
                data_source_id: 'source-right',
                dataset_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺',
                resource_key: 'alipay_bill:signcustomer:shop-001',
              },
            },
          ],
        },
      },
      scheme: {
        id: 'scheme-002',
        scheme_code: 'scheme-002',
        scheme_name: '泰斯支付宝对账方案',
        scheme_meta_json: {},
      },
      run_plan: {
        id: 'plan-002',
        plan_code: 'plan-002',
        plan_name: '泰斯支付宝对账',
      },
      exceptions: [],
      total: 0,
      limit: 100,
      offset: 0,
    }));

    render(<PublicReconRunExceptionsPage />);

    await waitFor(() => {
      expect(screen.getByText('匹配成功')).toBeInTheDocument();
    });

    const header = screen.getByText('对账差异公开分享').closest('header');
    expect(header).not.toBeNull();
    const headerView = within(header as HTMLElement);

    expect(headerView.getByText((_, element) => element?.textContent === '数据 205 条（其中 69 条为非支付宝支付订单）')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '数据 136 条')).toBeInTheDocument();
    expect(headerView.getByText('待处理差异')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '待处理差异0')).toBeInTheDocument();
    expect(headerView.queryByText('差异总数')).not.toBeInTheDocument();
  });
});
