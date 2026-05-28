import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

function expectStructuredSummary(container: HTMLElement) {
  const diffTypeRow = within(container).getByTestId('exception-summary-row-差异类型');
  expect(within(diffTypeRow).getByText('差异类型')).toBeInTheDocument();
  expect(within(diffTypeRow).getByText('金额差异')).toBeInTheDocument();

  const matchFieldRow = within(container).getByTestId('exception-summary-row-匹配字段');
  expect(within(matchFieldRow).getByText('匹配字段')).toBeInTheDocument();
  expect(within(matchFieldRow).getByText('订单号=TB001')).toBeInTheDocument();

  const compareFieldRow = within(container).getByTestId('exception-summary-row-对比字段');
  expect(within(compareFieldRow).getByText('对比字段')).toBeInTheDocument();
  expect(within(compareFieldRow).getByText('实收金额 100 / 98')).toBeInTheDocument();
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

  it('shows runtime summary and list-level pending differences', async () => {
    fetchMock.mockResolvedValueOnce(buildJsonResponse({
      run: {
        id: 'run-001',
        run_code: 'run_code_001',
        scheme_code: 'scheme-001',
        plan_code: 'plan-001',
        scheme_name: '泰斯支付宝对账方案',
        plan_name: '泰斯支付宝对账',
        execution_status: 'success',
        started_at: '2026-05-12T09:00:07+08:00',
        finished_at: '2026-05-12T09:05:42+08:00',
        run_context_json: { biz_date: '2026-05-12' },
        artifacts_json: {
          runtime_summary: {
            biz_date: '2026-05-12',
            queue: {
              job_id: 'queue-001',
              started_at: '2026-05-21T04:00:01+08:00',
              finished_at: '2026-05-21T04:01:15+08:00',
              duration_seconds: 73.854,
            },
            collections: [
              { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 38.42 },
              { side: 'right', business_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺', row_count: 136, duration_seconds: 31.06 },
            ],
            preparation: [
              { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 4.18 },
              { side: 'right', business_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺', row_count: 136, duration_seconds: 3.77 },
            ],
            reconciliation: { duration_seconds: 2.24 },
            summary_notification: {
              status: 'sent',
              recipient_name: '张小毅',
              recipient_identifier: '072007534524160438',
              message_id: 'msg-001',
              error: '',
            },
          },
        },
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
      expect(screen.getByText('对账数据日期')).toBeInTheDocument();
    });

    const header = screen.getByText('对账差异公开分享').closest('header');
    expect(header).not.toBeNull();
    const headerView = within(header as HTMLElement);

    expect(headerView.getByText('成功')).toBeInTheDocument();
    expect(headerView.getByText('对账数据日期')).toBeInTheDocument();
    expect(headerView.getByText('2026-05-12')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '交易订单明细表采集205 行耗时 38.42 秒')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺采集136 行耗时 31.06 秒')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '整理后交易订单明细表205 行耗时 4.18 秒')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '整理后支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺136 行耗时 3.77 秒')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '对账耗时2.24 秒')).toBeInTheDocument();
    expect(headerView.queryByText('匹配成功')).not.toBeInTheDocument();
    expect(headerView.queryByText('开始时间')).not.toBeInTheDocument();
    expect(headerView.queryByText('结束时间')).not.toBeInTheDocument();
    expect(headerView.queryByText('差异总数')).not.toBeInTheDocument();
    expect(headerView.queryByText('本次读取数据')).not.toBeInTheDocument();
    expect(headerView.queryByText('新增 0 / 更新 340')).not.toBeInTheDocument();
    expect(headerView.queryByText((_, element) => element?.textContent === '本次读取 1 条')).not.toBeInTheDocument();
    expect(screen.getByText('差异列表')).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === '待处理差异 60 条')).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/recon/public/runs/run-001/exceptions?limit=100&offset=0&owner=ding-user-001',
      undefined,
    );
  });

  it('shows zero pending differences in the difference list header', async () => {
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
        artifacts_json: {
          runtime_summary: {
            biz_date: '2026-05-12',
            collections: [
              { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 40 },
              { side: 'right', business_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺', row_count: 136, duration_seconds: 30 },
            ],
            preparation: [
              { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: null },
              { side: 'right', business_name: '支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺', row_count: 136, duration_seconds: null },
            ],
            reconciliation: { duration_seconds: 2 },
          },
        },
        recon_result_summary_json: {
          matched_exact: 136,
          source_only: 69,
          target_only: 0,
          matched_with_diff: 0,
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
      expect(screen.getByText('对账数据日期')).toBeInTheDocument();
    });

    const header = screen.getByText('对账差异公开分享').closest('header');
    expect(header).not.toBeNull();
    const headerView = within(header as HTMLElement);

    expect(headerView.getByText('对账数据日期')).toBeInTheDocument();
    expect(headerView.getByText((_, element) => element?.textContent === '对账耗时2 秒')).toBeInTheDocument();
    expect(headerView.queryByText('待处理差异')).not.toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === '待处理差异 0 条')).toBeInTheDocument();
    expect(headerView.queryByText('差异总数')).not.toBeInTheDocument();
  });

  it('formats exception summaries consistently in the public difference list', async () => {
    fetchMock.mockResolvedValueOnce(buildJsonResponse({
      run: {
        id: 'run-003',
        run_code: 'run_code_003',
        scheme_code: 'scheme-003',
        plan_code: 'plan-003',
        scheme_name: '泰斯支付宝对账方案',
        plan_name: '泰斯支付宝对账',
        execution_status: 'success',
        run_context_json: { biz_date: '2026-05-12' },
        artifacts_json: {
          runtime_summary: {
            biz_date: '2026-05-12',
          },
        },
      },
      scheme: {
        id: 'scheme-003',
        scheme_code: 'scheme-003',
        scheme_name: '泰斯支付宝对账方案',
        scheme_meta_json: {},
      },
      run_plan: {
        id: 'plan-003',
        plan_code: 'plan-003',
        plan_name: '泰斯支付宝对账',
      },
      exceptions: [
        {
          id: 'exception-003',
          anomaly_type: 'matched_with_diff',
          summary: '差异类型：金额差异 匹配字段：订单号=TB001 对比字段：实收金额 100 / 98',
          owner_name: '周行',
          processing_status: 'pending',
          detail_json: {},
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    }));

    render(<PublicReconRunExceptionsPage />);

    await screen.findByTestId('exception-summary-row-差异类型');
    expectStructuredSummary(document.body);

    fireEvent.click(screen.getByRole('button', { name: '详情' }));

    const detailDialog = await screen.findByRole('dialog', { name: '差异详情' });
    expectStructuredSummary(detailDialog);
  });
});
