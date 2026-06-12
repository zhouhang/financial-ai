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
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === '/api/recon/schemes?include_disabled=false&limit=20&offset=0') {
      return jsonResponse({
        schemes: [
          {
            id: 'scheme-001',
            scheme_code: 'scheme-001',
            scheme_name: '资金对账方案',
            is_enabled: true,
          },
        ],
        total: 1,
      });
    }
    if (url === '/api/recon/tasks?limit=20&offset=0') {
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
    if (url === '/api/recon/runs?limit=20&offset=0') {
      return jsonResponse({ runs: runsPayload, total: runsPayload.length });
    }
    if (url === '/api/recon/runs/run-failed') {
      return jsonResponse({ run: runPayload('run-failed', 'failed', '失败运行') });
    }
    if (url === '/api/recon/runs/rerun' && init?.method === 'POST') {
      return jsonResponse({ success: true, run_id: 'run-retry-001' });
    }
    if (url === '/api/collaboration-channels') {
      return jsonResponse({ channels: [] });
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
  it('shows one primary action for failed and successful runs only', async () => {
    setupFetch();

    await renderRunsTab();

    const failedRow = screen.getByTestId('execution-run-row-run-failed');
    expect(within(failedRow).getByRole('button', { name: '重试' })).toBeTruthy();
    expect(within(failedRow).queryByRole('button', { name: '差异消化' })).toBeNull();

    const successRow = screen.getByTestId('execution-run-row-run-success');
    expect(within(successRow).getByRole('button', { name: '差异消化' })).toBeTruthy();
    expect(within(successRow).queryByRole('button', { name: '重试' })).toBeNull();

    const runningRow = screen.getByTestId('execution-run-row-run-running');
    expect(within(runningRow).queryByRole('button', { name: '重试' })).toBeNull();
    expect(within(runningRow).queryByRole('button', { name: '差异消化' })).toBeNull();
  });

  it('posts retry request and shows notice after refreshing runs', async () => {
    const fetchMock = setupFetch();

    await renderRunsTab();
    fireEvent.click(within(screen.getByTestId('execution-run-row-run-failed')).getByRole('button', { name: '重试' }));

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
  });
});
