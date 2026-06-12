import { describe, expect, it } from 'vitest';
import { canDigestRun, canRetryRun, isRunInProgress, runActionForStatus } from './runActions';

describe('runActions', () => {
  it('shows retry only for failed runs', () => {
    expect(canRetryRun({ executionStatus: 'failed' })).toBe(true);
    expect(canDigestRun({ executionStatus: 'failed' })).toBe(false);
    expect(runActionForStatus({ executionStatus: 'failed' })).toBe('retry');
  });

  it('shows diff digestion only for successful runs', () => {
    expect(canRetryRun({ executionStatus: 'success' })).toBe(false);
    expect(canDigestRun({ executionStatus: 'success' })).toBe(true);
    expect(runActionForStatus({ executionStatus: 'success' })).toBe('digest');
  });

  it.each(['running', 'waiting_data', 'queued', 'scheduled', 'unknown', ''])(
    'shows no action for %s',
    (executionStatus) => {
      expect(canRetryRun({ executionStatus })).toBe(false);
      expect(canDigestRun({ executionStatus })).toBe(false);
      expect(runActionForStatus({ executionStatus })).toBeNull();
    },
  );

  it.each(['running', 'waiting_data', 'queued', 'scheduled'])(
    'treats %s as still in progress',
    (executionStatus) => {
      expect(isRunInProgress({ executionStatus })).toBe(true);
    },
  );

  it.each(['success', 'failed', 'error', 'unknown', ''])(
    'treats %s as terminal or non-progress',
    (executionStatus) => {
      expect(isRunInProgress({ executionStatus })).toBe(false);
    },
  );
});
