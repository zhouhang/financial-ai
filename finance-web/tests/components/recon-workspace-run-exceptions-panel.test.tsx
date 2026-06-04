import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReconWorkspace from '../../src/components/ReconWorkspace';
import type { UserTaskRule } from '../../src/types';

function buildJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

const selectedTask: UserTaskRule = {
  id: 1,
  rule_code: 'recon_upload',
  name: '上传文件对账',
  rule_type: 'recon',
  task_code: 'recon',
  task_name: '数据对账',
  task_type: 'recon',
};

describe('ReconWorkspace 运行记录异常看板', () => {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('精简异常看板列和摘要，并且成功运行不展示失败信息', async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);

      if (url.split('?')[0] === '/api/recon/schemes') {
        return buildJsonResponse({
          schemes: [
            {
              id: 'scheme-1',
              scheme_code: 'scheme_code_1',
              scheme_name: '订单资金对账',
              is_enabled: true,
              scheme_meta_json: {
                dataset_bindings: {
                  left: [
                    {
                      dataset_id: 'left-dataset',
                      dataset_name: '订单表',
                      business_name: '订单表',
                      field_label_map: { 平台订单客户订单号: '平台订单客户订单号', 含税销售金额: '含税销售金额' },
                    },
                  ],
                  right: [
                    {
                      dataset_id: 'right-dataset',
                      dataset_name: '资金流水',
                      business_name: '资金流水',
                      field_label_map: { 平台订单客户订单号: '平台订单客户订单号' },
                    },
                  ],
                },
              },
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/tasks') {
        return buildJsonResponse({
          tasks: [
            {
              id: 'plan-1',
              plan_code: 'plan_code_1',
              plan_name: '订单资金对账',
              scheme_code: 'scheme_code_1',
              schedule_type: 'daily',
              schedule_expr: '09:30',
              owner_mapping_json: {},
              plan_meta_json: {},
              is_enabled: true,
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/runs') {
        return buildJsonResponse({
          runs: [
            {
              id: 'run-1',
              run_code: 'run_code_1',
              scheme_code: 'scheme_code_1',
              plan_code: 'plan_code_1',
              execution_status: 'success',
              anomaly_count: 1,
              failed_stage: 'reconcile',
              failed_reason: '成功运行不应展示这段失败原因',
              started_at: '2026-05-12T09:00:00+08:00',
              finished_at: '2026-05-12T09:05:00+08:00',
              artifacts_json: {
                runtime_summary: {
                  exception_sampling: {
                    enabled: true,
                    total_count: 35665,
                    sample_count: 200,
                    sample_limit: 200,
                    threshold: 1000,
                    strategy: 'stratified_by_anomaly_type_owner',
                  },
                },
              },
            },
          ],
        });
      }
      if (url === '/api/recon/runs/run-1/exceptions') {
        return buildJsonResponse({
          exceptions: [
            {
              id: 'exception-1',
              anomaly_type: 'source_only',
              summary: '订单和资金流水存在待处理差异，需要财务确认业务归属和后续处理方式。',
              owner_name: '周行',
              reminder_status: 'sent',
              processing_status: 'in_progress',
              fix_status: 'pending',
              latest_feedback: '处理中',
              detail_json: {
                source_ref: 'left_recon_ready',
                target_ref: 'right_recon_ready',
                join_key: [
                  {
                    source_field: '平台订单客户订单号',
                    target_field: '平台订单客户订单号',
                    source_value: '5115360674997007548',
                    target_value: null,
                  },
                ],
                compare_values: [
                  {
                    name: '含税销售金额 ↔ 对比字段',
                    source_field: '含税销售金额',
                    target_field: '平台订单客户订单号',
                    source_value: 29.65,
                    target_value: null,
                  },
                ],
              },
            },
          ],
        });
      }
      if (url === '/api/collaboration-channels') return buildJsonResponse({ channels: [] });
      if (url === '/api/proc/list_user_tasks') return buildJsonResponse({ success: true, tasks: [] });
      if (url === '/api/data-sources') return buildJsonResponse({ data_sources: [] });
      throw new Error(`Unexpected fetch url: ${url}`);
    });

    render(<ReconWorkspace mode="center" selectedTask={selectedTask} authToken="mock-token" />);

    fireEvent.click(await screen.findByRole('button', { name: '运行记录' }));
    fireEvent.click(await screen.findByRole('button', { name: '异常看板' }));

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => {
      expect(within(dialog).getByText('资金流水缺失平台订单客户订单号 5115360674997007548')).toBeInTheDocument();
    });

    expect(within(dialog).getByText((_, element) => element?.textContent === '全量差异 35,665 条，当前抽样展示 200 条')).toBeInTheDocument();

    expect(within(dialog).queryByText('失败阶段')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('失败原因')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('成功运行不应展示这段失败原因')).not.toBeInTheDocument();

    expect(within(dialog).queryByText('催办')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('修复状态')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('已催办')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('待修复')).not.toBeInTheDocument();

    expect(within(dialog).getByText('责任人')).toBeInTheDocument();
    expect(within(dialog).getByText('处理进展')).toBeInTheDocument();
    expect(within(dialog).getByText('查看详情')).toBeInTheDocument();

    expect(within(dialog).queryByText('左侧独有')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('平台订单客户订单号：5115360674997007548')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('含税销售金额 ↔ 对比字段：左侧 29.65 / 右侧 --')).not.toBeInTheDocument();
  });
});
