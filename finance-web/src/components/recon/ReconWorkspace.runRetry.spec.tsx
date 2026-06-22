import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReconWorkspace from '../ReconWorkspace';
import type { UserTaskRule } from '../../types';

const authToken = 'test-token';

function jsonResponse(body: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const selectedTask: UserTaskRule = {
  id: 1,
  rule_code: 'rule-001',
  name: '资金对账',
  rule_type: 'recon',
  task_code: 'task-001',
  task_name: '资金对账',
  task_type: 'recon',
};

function runPayload(id: string, executionStatus: string, planName: string) {
  return {
    id,
    run_code: `${id}-code`,
    scheme_code: 'scheme-001',
    plan_code: 'plan-001',
    scheme_name: '资金对账方案',
    plan_name: planName,
    execution_status: executionStatus,
    anomaly_count: executionStatus === 'success' ? 2 : 0,
    review_round: 0,
    run_context_json: { biz_date: '2026-06-10' },
    started_at: '2026-06-11T02:42:09.000Z',
    finished_at: '2026-06-11T02:43:09.000Z',
  };
}

const runsPayload = [
  runPayload('run-failed', 'failed', '失败运行'),
  runPayload('run-success', 'success', '成功运行'),
  runPayload('run-running', 'running', '运行中记录'),
];

function setupFetch() {
  let failedRunFetches = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const parsedUrl = new URL(url, 'http://localhost');
    const pathname = parsedUrl.pathname;
    if (pathname === '/api/recon/schemes') {
      return jsonResponse({
        schemes: [
          {
            id: 'scheme-001',
            scheme_code: 'scheme-001',
            scheme_name: '资金对账方案',
            is_enabled: true,
            scheme_meta_json: {
              left_sources: [
                {
                  id: 'left-dataset',
                  name: '左侧订单',
                  schema_summary: {
                    columns: [
                      { name: 'biz_date', data_type: 'date' },
                      { name: 'amount', data_type: 'number' },
                    ],
                  },
                },
              ],
              right_sources: [
                {
                  id: 'right-dataset',
                  name: '右侧账单',
                  schema_summary: {
                    columns: [
                      { name: 'bill_date', data_type: 'date' },
                      { name: 'amount', data_type: 'number' },
                    ],
                  },
                },
              ],
            },
          },
        ],
        total: 1,
      });
    }
    if (pathname === '/api/recon/tasks' && init?.method !== 'POST') {
      return jsonResponse({
        tasks: [
          {
            id: 'plan-001',
            plan_code: 'plan-001',
            plan_name: '资金对账计划',
            scheme_code: 'scheme-001',
            schedule_type: 'daily',
            schedule_expr: '09:00',
            owner_mapping_json: {},
            plan_meta_json: {},
            is_enabled: true,
          },
        ],
        total: 1,
      });
    }
    if (pathname === '/api/recon/tasks' && init?.method === 'POST') {
      return jsonResponse({ success: true });
    }
    if (pathname === '/api/recon/runs') {
      return jsonResponse({ runs: runsPayload, total: runsPayload.length });
    }
    if (pathname === '/api/recon/runs/run-failed') {
      failedRunFetches += 1;
      return jsonResponse({
        run: runPayload(
          'run-failed',
          failedRunFetches === 1 ? 'running' : 'failed',
          '失败运行',
        ),
      });
    }
    if (pathname === '/api/recon/runs/run-success') {
      return jsonResponse({ run: runPayload('run-success', 'success', '成功运行') });
    }
    if (pathname === '/api/recon/runs/run-running') {
      return jsonResponse({ run: runPayload('run-running', 'running', '运行中记录') });
    }
    if (pathname === '/api/recon/runs/run-failed/exceptions') {
      return jsonResponse({ exceptions: [], total: 0 });
    }
    if (pathname === '/api/recon/runs/run-success/exceptions') {
      return jsonResponse({ exceptions: [], total: 0 });
    }
    if (pathname === '/api/recon/runs/run-running/exceptions') {
      return jsonResponse({ exceptions: [], total: 0 });
    }
    if (pathname === '/api/recon/runs/rerun' && init?.method === 'POST') {
      return jsonResponse({ success: true, run_id: 'run-retry-001' });
    }
    if (pathname === '/api/collaboration-channels') {
      return jsonResponse({ channels: [] });
    }
    if (pathname === '/api/owner-candidates/search') {
      return jsonResponse({
        candidates: [
          {
            display_name: '张三',
            identifier: 'user-001',
            organization: '',
            departments: [],
            mobile_masked: '',
            disambiguation_label: '',
          },
        ],
      });
    }
    return jsonResponse({}, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function renderRunsTab() {
  render(<ReconWorkspace selectedTask={selectedTask} mode="center" authToken={authToken} />);

  fireEvent.click(await screen.findByRole('button', { name: '运行记录' }));
  await screen.findByTestId('execution-run-row-run-failed');
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ReconWorkspace run retry actions', () => {
  it('filters run records by started date range', async () => {
    const fetchMock = setupFetch();

    await renderRunsTab();
    fireEvent.change(screen.getByLabelText('开始日期'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByLabelText('结束日期'), { target: { value: '2026-06-22' } });
    fireEvent.click(screen.getByRole('button', { name: '筛选' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/recon/runs?limit=20&offset=0&started_at_from=2026-06-01&started_at_to=2026-06-22',
        expect.any(Object),
      );
    });
  });

  it('does not show date field selection when creating a run plan', async () => {
    setupFetch();

    render(<ReconWorkspace selectedTask={selectedTask} mode="center" authToken={authToken} />);
    await screen.findByText('资金对账方案');
    fireEvent.click(await screen.findByRole('button', { name: '对账任务' }));
    fireEvent.click(screen.getByRole('button', { name: '新增运行计划' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByText('对账日期字段')).toBeNull();
    expect(within(dialog).queryByRole('option', { name: '请选择对账日期字段' })).toBeNull();
  });

  it('keeps primary actions out of the run list and shows them in details only', async () => {
    setupFetch();

    await renderRunsTab();

    const failedRow = screen.getByTestId('execution-run-row-run-failed');
    expect(within(failedRow).queryByRole('button', { name: '重试' })).toBeNull();
    expect(within(failedRow).queryByRole('button', { name: '差异消化' })).toBeNull();

    const successRow = screen.getByTestId('execution-run-row-run-success');
    expect(within(successRow).queryByRole('button', { name: '差异消化' })).toBeNull();
    expect(within(successRow).queryByRole('button', { name: '重试' })).toBeNull();

    const runningRow = screen.getByTestId('execution-run-row-run-running');
    expect(within(runningRow).queryByRole('button', { name: '重试' })).toBeNull();
    expect(within(runningRow).queryByRole('button', { name: '差异消化' })).toBeNull();

    fireEvent.click(within(failedRow).getByRole('button', { name: '异常看板' }));
    expect(await screen.findByRole('button', { name: '重试' })).toBeTruthy();

    cleanup();
    setupFetch();
    await renderRunsTab();
    fireEvent.click(within(screen.getByTestId('execution-run-row-run-success')).getByRole('button', { name: '异常看板' }));
    expect(await screen.findByRole('button', { name: '差异消化' })).toBeTruthy();
  });

  it('posts retry request and reloads exception details after the original run finishes', async () => {
    const fetchMock = setupFetch();

    await renderRunsTab();
    fireEvent.click(within(screen.getByTestId('execution-run-row-run-failed')).getByRole('button', { name: '异常看板' }));
    const retryButton = await screen.findByRole('button', { name: '重试' });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/recon/runs/rerun',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ original_run_id: 'run-failed', reason: '用户触发重试' }),
        }),
      );
    });
    expect(await screen.findByText('已发起重试,当前运行记录将更新为最新执行结果。')).toBeTruthy();
    await waitFor(() => {
      const runFetchCalls = fetchMock.mock.calls.filter(([input]) => String(input) === '/api/recon/runs/run-failed');
      expect(runFetchCalls).toHaveLength(2);
    });
    await waitFor(() => {
      const exceptionFetchCalls = fetchMock.mock.calls.filter(([input]) => (
        String(input) === '/api/recon/runs/run-failed/exceptions'
      ));
      expect(exceptionFetchCalls).toHaveLength(2);
    });
  });
});
