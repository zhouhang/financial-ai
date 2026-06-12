import { describe, expect, it } from 'vitest';
import { canDigestRun, canRetryRun, runActionForStatus } from './runActions';

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
});
