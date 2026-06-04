import { describe, expect, it } from 'vitest';
import { backendStatusLabel } from '../src/handoff/HandoffPage';

describe('capabilities label', () => {
  it('shows generic status, not backend internals', () => {
    expect(backendStatusLabel({ backend: 'os_windows' })).toBe('远程操作');
    expect(backendStatusLabel({ backend: 'playwright' })).toBe('兼容模式');
    expect(backendStatusLabel(undefined)).toBe('');
  });
});
