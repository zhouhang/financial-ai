import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReconWorkspace from '../../src/components/ReconWorkspace';
import type { UserTaskRule } from '../../src/types';

const selectedTask: UserTaskRule = {
  id: 1,
  rule_code: 'rule-1',
  name: '资金对账',
  rule_type: 'recon',
  task_code: 'task-1',
  task_name: '资金对账',
  task_type: 'recon',
};

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

function expectNoStructuredSummaryLabels(container: HTMLElement) {
  expect(within(container).queryByText('差异类型')).not.toBeInTheDocument();
  expect(within(container).queryByText('匹配字段')).not.toBeInTheDocument();
  expect(within(container).queryByText('对比字段')).not.toBeInTheDocument();
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('对账任务列表布局', () => {
  it('在任务名称下方展示创建时间和协作责任信息，并隐藏独立方案和创建时间列', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.split('?')[0] === '/api/recon/schemes') {
        return jsonResponse({
          schemes: [
            {
              id: 'scheme-1',
              scheme_code: 'scheme_code_1',
              scheme_name: '订单对账方案',
              is_enabled: true,
              created_at: '2026-05-17T09:00:00.000Z',
              updated_at: '2026-05-17T09:00:00.000Z',
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/tasks') {
        return jsonResponse({
          tasks: [
            {
              id: 'task-1',
              plan_code: 'plan-1',
              plan_name: '每日订单对账',
              scheme_code: 'scheme_code_1',
              schedule_type: 'daily',
              schedule_expr: '09:30',
              biz_date_offset: 'T-1',
              channel_config_id: 'channel-dingtalk',
              plan_meta_json: {
                summary_recipient: {
                  display_name: '张小毅',
                  user_id: 'zhangxiaoyi',
                },
              },
              owner_mapping_json: {
                default_owner: {
                  name: '周行',
                  identifier: 'zhouxing',
                },
              },
              is_enabled: true,
              created_at: '2026-05-18T01:23:00.000Z',
              updated_at: '2026-05-18T01:23:00.000Z',
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/runs') {
        return jsonResponse({ runs: [] });
      }
      if (url === '/api/collaboration-channels') {
        return jsonResponse({
          channels: [
            {
              id: 'channel-dingtalk',
              provider: 'dingtalk_dws',
              channel_code: 'default',
              name: '钉钉默认通道',
              is_default: true,
              is_enabled: true,
            },
          ],
        });
      }
      return jsonResponse({}, 404);
    });

    render(<ReconWorkspace selectedTask={selectedTask} authToken="test-token" />);

    fireEvent.click(screen.getByRole('button', { name: '对账任务' }));

    const row = await screen.findByTestId('recon-task-row-task-1');
    const taskList = row.parentElement;
    if (!taskList) {
      throw new Error('任务列表容器未渲染');
    }

    expect(within(row).getByText('每日订单对账')).toBeInTheDocument();
    expect(within(taskList).queryByText('对账方案')).not.toBeInTheDocument();
    expect(within(taskList).queryByText('任务创建时间')).not.toBeInTheDocument();

    const taskNameCell = row.firstElementChild;
    if (!taskNameCell) {
      throw new Error('任务名称单元格未渲染');
    }
    expect(within(taskNameCell as HTMLElement).getByText('2026/05/18 09:23')).toBeInTheDocument();
    expect(within(taskNameCell as HTMLElement).getByText('钉钉 汇总：张小毅 · 责任：周行')).toBeInTheDocument();
    expect(within(row).queryByText('订单对账方案')).not.toBeInTheDocument();
  });

  it('异常看板展示运行真实摘要和差异列表异常数', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.split('?')[0] === '/api/recon/schemes') {
        return jsonResponse({
          schemes: [
            {
              id: 'scheme-1',
              scheme_code: 'scheme_code_1',
              scheme_name: '订单对账方案',
              is_enabled: true,
              created_at: '2026-05-17T09:00:00.000Z',
              updated_at: '2026-05-17T09:00:00.000Z',
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/tasks') {
        return jsonResponse({
          tasks: [
            {
              id: 'task-1',
              plan_code: 'plan-1',
              plan_name: '每日订单对账',
              scheme_code: 'scheme_code_1',
              is_enabled: true,
              created_at: '2026-05-18T01:23:00.000Z',
              updated_at: '2026-05-18T01:23:00.000Z',
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/runs') {
        return jsonResponse({
          runs: [
            {
              id: 'run-1',
              run_code: 'run-code-1',
              scheme_code: 'scheme_code_1',
              plan_code: 'plan-1',
              execution_status: 'warning',
              anomaly_count: 2,
              biz_date: '2026-05-11',
              run_context_json: {
                trigger_type: 'manual',
              },
              artifacts_json: {
                runtime_summary: {
                  biz_date: '2026-05-11',
                  queue: {
                    job_id: 'queue-001',
                    started_at: '2026-05-21T04:00:01+08:00',
                    finished_at: '2026-05-21T04:01:15+08:00',
                    duration_seconds: 73.854,
                  },
                  collections: [
                    { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 38.42 },
                    { side: 'right', business_name: '支付宝资金账单', row_count: 136, duration_seconds: 31.06 },
                  ],
                  preparation: [
                    { side: 'left', business_name: '交易订单明细表', row_count: 205, duration_seconds: 4.18 },
                    { side: 'right', business_name: '支付宝资金账单', row_count: 136, duration_seconds: 3.77 },
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
              started_at: '2026-05-18T02:00:00.000Z',
              finished_at: '2026-05-18T02:03:00.000Z',
            },
          ],
        });
      }
      if (url === '/api/recon/runs/run-1/exceptions') {
        return jsonResponse({ exceptions: [] });
      }
      if (url === '/api/collaboration-channels') {
        return jsonResponse({ channels: [] });
      }
      return jsonResponse({}, 404);
    });

    render(<ReconWorkspace selectedTask={selectedTask} authToken="test-token" />);

    fireEvent.click(screen.getByRole('button', { name: '运行记录' }));

    const runRow = await screen.findByTestId('execution-run-row-run-1');
    fireEvent.click(within(runRow).getByRole('button', { name: '异常看板' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('对账数据日期')).toBeInTheDocument();
    expect(within(dialog).getByText('2026-05-11')).toBeInTheDocument();
    expect(within(dialog).getByText((_, element) => element?.textContent === '交易订单明细表采集205 行耗时 38.42 秒')).toBeInTheDocument();
    expect(within(dialog).getByText((_, element) => element?.textContent === '整理后支付宝资金账单136 行耗时 3.77 秒')).toBeInTheDocument();
    expect(within(dialog).getByText((_, element) => element?.textContent === '对账耗时2.24 秒')).toBeInTheDocument();
    expect(within(dialog).getByText('差异列表')).toBeInTheDocument();
    expect(within(dialog).getByText((_, element) => element?.textContent === '待处理差异 2 条')).toBeInTheDocument();
    expect(within(dialog).queryByText('所属方案')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('开始时间')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('结束时间')).not.toBeInTheDocument();
  });

  it('异常看板展示业务化短摘要', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.split('?')[0] === '/api/recon/schemes') {
        return jsonResponse({
          schemes: [
            {
              id: 'scheme-1',
              scheme_code: 'scheme_code_1',
              scheme_name: '订单对账方案',
              is_enabled: true,
              scheme_meta_json: {
                dataset_bindings: {
                  left: [
                    {
                      dataset_id: 'left-dataset',
                      dataset_name: 'tb0131100248-店铺订单',
                      business_name: 'tb0131100248-店铺订单',
                      field_label_map: { biz_key: '订单编号', amount: '含税销售金额' },
                    },
                  ],
                  right: [
                    {
                      dataset_id: 'right-dataset',
                      dataset_name: '交易订单明细表',
                      business_name: '交易订单明细表',
                      field_label_map: { biz_key: '订单编号', paid_amount: '买家实付金额' },
                    },
                  ],
                },
              },
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/tasks') {
        return jsonResponse({
          tasks: [
            {
              id: 'task-1',
              plan_code: 'plan-1',
              plan_name: '每日订单对账',
              scheme_code: 'scheme_code_1',
              is_enabled: true,
            },
          ],
        });
      }
      if (url.split('?')[0] === '/api/recon/runs') {
        return jsonResponse({
          runs: [
            {
              id: 'run-1',
              run_code: 'run-code-1',
              scheme_code: 'scheme_code_1',
              plan_code: 'plan-1',
              execution_status: 'warning',
              anomaly_count: 1,
              artifacts_json: {
                runtime_summary: {
                  biz_date: '2026-05-11',
                },
              },
            },
          ],
        });
      }
      if (url === '/api/recon/runs/run-1/exceptions') {
        return jsonResponse({
          exceptions: [
            {
              id: 'exception-1',
              anomaly_type: 'source_only',
              summary: '仅 tb0131100248-店铺订单 存在（交易订单明细表 缺失）：订单编号=5118002676174023242 含税销售金额 ↔ 买家实付金额：tb0131100248-店铺订单 0.00',
              owner_name: '周行',
              processing_status: 'pending',
              detail_json: {
                source_ref: 'left_recon_ready',
                target_ref: 'right_recon_ready',
                join_key: [
                  {
                    source_field: 'biz_key',
                    target_field: 'biz_key',
                    source_value: '5118002676174023242',
                    target_value: null,
                  },
                ],
                compare_values: [
                  {
                    source_field: 'amount',
                    target_field: 'paid_amount',
                    source_value: '0.00',
                    target_value: null,
                  },
                ],
                left_record: {
                  biz_key: '5118002676174023242',
                  amount: '0.00',
                },
              },
            },
          ],
        });
      }
      if (url === '/api/collaboration-channels') {
        return jsonResponse({ channels: [] });
      }
      return jsonResponse({}, 404);
    });

    render(<ReconWorkspace selectedTask={selectedTask} authToken="test-token" />);

    fireEvent.click(screen.getByRole('button', { name: '运行记录' }));

    const runRow = await screen.findByTestId('execution-run-row-run-1');
    fireEvent.click(within(runRow).getByRole('button', { name: '异常看板' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('交易订单明细表缺失订单编号 5118002676174023242')).toBeInTheDocument();
    expectNoStructuredSummaryLabels(dialog);

    fireEvent.click(within(dialog).getByRole('button', { name: '查看详情' }));

    const detailDialog = await screen.findByRole('dialog', { name: '异常详情' });
    expect(within(detailDialog).getByText('交易订单明细表缺失订单编号 5118002676174023242')).toBeInTheDocument();
    expect(within(detailDialog).getByText('tb0131100248-店铺订单')).toBeInTheDocument();
    expect(within(detailDialog).getByText('交易订单明细表')).toBeInTheDocument();
    expect(within(detailDialog).getByText('未匹配到原始记录')).toBeInTheDocument();
    expectNoStructuredSummaryLabels(detailDialog);
  });
});
