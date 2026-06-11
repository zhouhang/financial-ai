import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ReconAutoRunsPanel from '../../src/components/recon/ReconAutoRunsPanel';
import type { ReconRunItem } from '../../src/components/recon/types';

const run: ReconRunItem = {
  id: 'run-001',
  autoTaskId: 'task-001',
  taskName: '博宽资金对账',
  triggerMode: 'resolve',
  businessDate: '2026-06-09',
  status: 'success',
  dataReady: '已就绪',
  exceptionCount: 22,
  reviewRound: 2,
  lastResolvedAt: 'latest-review-time',
  resolutionSummary: { resolved: 9, reclassified: 2, kept: 20 },
  closureStatus: '待处理',
  startedAt: '2026-06-10 08:00',
  finishedAt: '2026-06-10 08:03',
};

afterEach(() => {
  cleanup();
});

describe('ReconAutoRunsPanel diff digestion audit fields', () => {
  it('renders resolve trigger and review audit fields', () => {
    render(
      <ReconAutoRunsPanel
        runs={[run]}
        focusedRunId="run-001"
        exceptionsByRunId={{}}
        onFocusRun={vi.fn()}
        onOpenFollowup={vi.fn()}
        onVerifyRun={vi.fn()}
        onRemindException={vi.fn()}
        onSyncException={vi.fn()}
      />,
    );

    expect(screen.getAllByText('差异消化').length).toBeGreaterThan(0);
    expect(screen.getAllByText('第 2 轮').length).toBeGreaterThan(0);
    expect(screen.getAllByText('latest-review-time').length).toBeGreaterThan(0);
    expect(screen.getByText('复核轮次')).toBeInTheDocument();
  });
});
