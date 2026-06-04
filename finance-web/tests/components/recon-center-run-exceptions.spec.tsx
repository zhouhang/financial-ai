import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReconWorkspace from '../../src/components/ReconWorkspace';

const authToken = 'test-token';

function jsonResponse(body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('对账中心运行异常展示', () => {
  it('方案不在当前分页时使用异常接口返回的 scheme 元数据展示数据集名称', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/schemes?')) {
        return jsonResponse({ success: true, schemes: [], total: 34 });
      }
      if (url.includes('/tasks?')) {
        return jsonResponse({ success: true, tasks: [], total: 0 });
      }
      if (url.includes('/runs/run-001/exceptions')) {
        return jsonResponse({
          success: true,
          count: 1,
          scheme: {
            id: 'scheme-001',
            scheme_code: 'scheme-outside-first-page',
            scheme_name: 'tb0131100248订单对账',
            scheme_meta_json: {
              dataset_bindings: {
                left: [{ business_name: '交易订单明细表' }],
                right: [{ business_name: 'tb0131100248-店铺订单' }],
              },
              match_field_pairs: [{ left_field: '客户订单号', right_field: '订单编号' }],
              left_output_fields: [{ output_name: '客户订单号', source_dataset_id: '' }],
              right_output_fields: [{ output_name: '订单编号', source_dataset_id: '' }],
              left_output_field_label_map: { 客户订单号: '客户订单号' },
              right_output_field_label_map: { 订单编号: '订单编号' },
            },
          },
          exceptions: [
            {
              id: 'exception-001',
              run_id: 'run-001',
              scheme_code: 'scheme-outside-first-page',
              anomaly_type: 'source_only',
              summary: '',
              detail_json: {
                source_ref: 'left_recon_ready',
                target_ref: 'right_recon_ready',
                join_key: [
                  {
                    source_field: '客户订单号',
                    target_field: '订单编号',
                    source_value: '3303304537801026497',
                    target_value: '',
                  },
                ],
                raw_record: {
                  'source.客户订单号': '3303304537801026497',
                },
              },
              owner_name: '',
              reminder_status: 'pending',
              processing_status: 'pending',
              fix_status: 'pending',
              latest_feedback: '',
              is_closed: false,
            },
          ],
        });
      }
      if (url.includes('/runs?')) {
        return jsonResponse({
          success: true,
          runs: [
            {
              id: 'run-001',
              scheme_code: 'scheme-outside-first-page',
              plan_code: 'plan-001',
              scheme_name: 'tb0131100248订单对账',
              plan_name: 'tb0131100248订单对账',
              execution_status: 'success',
              anomaly_count: 1,
              run_context_json: { biz_date: '2026-06-03' },
              started_at: '2026-06-04T02:42:09.000Z',
              finished_at: '2026-06-04T02:43:09.000Z',
            },
          ],
          total: 1,
        });
      }
      if (url.includes('/collaboration-channels')) {
        return jsonResponse({ success: true, channels: [] });
      }
      return jsonResponse({ success: true });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <ReconWorkspace
        selectedTask={{ ruleCode: 'rule-001', ruleName: '测试规则' } as never}
        mode="center"
        authToken={authToken}
      />,
    );

    await screen.findByText('统一查看对账方案、对账任务与运行记录');
    fireEvent.click(screen.getByRole('button', { name: '运行记录' }));
    await waitFor(() => {
      expect(screen.getAllByText('tb0131100248订单对账').length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getByRole('button', { name: '异常看板' }));

    await waitFor(() => {
      expect(screen.getByText('tb0131100248-店铺订单缺失客户订单号 3303304537801026497')).toBeInTheDocument();
    });
    expect(screen.queryByText('数据集 B缺失客户订单号 3303304537801026497')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '查看详情' }));

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: '异常详情' })).toBeInTheDocument();
    });
    expect(screen.getAllByText('交易订单明细表').length).toBeGreaterThan(0);
    expect(screen.getAllByText('tb0131100248-店铺订单').length).toBeGreaterThan(0);
    expect(screen.queryByText('数据集 A')).not.toBeInTheDocument();
    expect(screen.queryByText('数据集 B')).not.toBeInTheDocument();
  });
});
