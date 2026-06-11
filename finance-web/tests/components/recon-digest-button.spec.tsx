import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReconWorkspace from '../../src/components/ReconWorkspace';

const authToken = 'test-token';

function jsonResponse(body: Record<string, unknown>, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function runPayload(reviewRound: number, anomalyCount: number) {
  return {
    id: 'run-001',
    scheme_code: 'scheme-001',
    plan_code: 'plan-001',
    scheme_name: '博宽资金对账',
    plan_name: '博宽资金对账',
    execution_status: 'success',
    anomaly_count: anomalyCount,
    review_round: reviewRound,
    last_resolved_at: reviewRound > 0 ? '2026-06-10T08:30:00.000Z' : null,
    resolution_summary_json: reviewRound > 0 ? { resolved: 2, kept: 1 } : {},
    recon_result_summary_json: {
      source_only: anomalyCount,
      target_only: 0,
      matched_with_diff: 0,
    },
    run_context_json: { biz_date: '2026-06-09' },
    started_at: '2026-06-10T02:42:09.000Z',
    finished_at: '2026-06-10T02:43:09.000Z',
  };
}

function schemePayload() {
  return {
    id: 'scheme-001',
    scheme_code: 'scheme-001',
    scheme_name: '博宽资金对账',
    status: 'enabled',
  };
}

function setupFetch(options: { digestStatus?: number; digestBody?: Record<string, unknown> } = {}) {
  let digestRequested = false;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes('/runs/run-001/diff-digestion')) {
      digestRequested = true;
      return jsonResponse(options.digestBody || { queued: true, status: 'queued' }, options.digestStatus || 200);
    }
    if (url.includes('/runs/run-001') && !url.includes('/exceptions') && !url.includes('/diff-digestion')) {
      return jsonResponse({
        success: true,
        run: digestRequested ? runPayload(1, 1) : runPayload(0, 3),
      });
    }
    if (url.includes('/schemes?')) {
      return jsonResponse({ success: true, schemes: [schemePayload()], total: 1 });
    }
    if (url.includes('/tasks?')) {
      return jsonResponse({ success: true, tasks: [], total: 0 });
    }
    if (url.includes('/runs/run-001/exceptions')) {
      return jsonResponse({
        success: true,
        count: 0,
        scheme: schemePayload(),
        exceptions: [],
      });
    }
    if (url.includes('/runs?')) {
      return jsonResponse({
        success: true,
        runs: [digestRequested ? runPayload(1, 1) : runPayload(0, 3)],
        total: 1,
      });
    }
    if (url.includes('/collaboration-channels')) {
      return jsonResponse({ success: true, channels: [] });
    }
    return jsonResponse({ success: true });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function openRunExceptions() {
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
    expect(screen.getAllByText('博宽资金对账').length).toBeGreaterThan(0);
  });
  fireEvent.click(screen.getByRole('button', { name: '异常看板' }));
  await screen.findByRole('button', { name: '差异消化' });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('对账中心差异消化按钮', () => {
  it('调用差异消化接口并轮询同一运行记录的复核轮次', async () => {
    const fetchMock = setupFetch();

    await openRunExceptions();
    fireEvent.click(screen.getByRole('button', { name: '差异消化' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/runs/run-001/diff-digestion'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
    await waitFor(() => {
      expect(screen.getAllByText(/差异消化完成/).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText('第 1 轮').length).toBeGreaterThan(0);
    const afterDigestCalls = fetchMock.mock.calls.slice(
      fetchMock.mock.calls.findIndex(([input]) => String(input).includes('/runs/run-001/diff-digestion')) + 1,
    );
    expect(afterDigestCalls.some(([input]) => String(input).includes('/schemes?'))).toBe(false);
    expect(afterDigestCalls.some(([input]) => String(input).includes('/tasks?'))).toBe(false);
    expect(afterDigestCalls.some(([input]) => String(input).includes('/runs/run-001'))).toBe(true);
  });

  it('展示差异消化失败时的后端提示', async () => {
    setupFetch({
      digestStatus: 400,
      digestBody: {
        detail: {
          status: 'invalid_state',
          message: '该运行记录暂不可差异消化',
        },
      },
    });

    await openRunExceptions();
    fireEvent.click(screen.getByRole('button', { name: '差异消化' }));

    await waitFor(() => {
      expect(screen.getAllByText('该运行记录暂不可差异消化').length).toBeGreaterThan(0);
    });
  });
});
