import { describe, expect, it } from 'vitest';
import { gestureLockState } from '../src/handoff/handoffPresentation';

describe('gesture exclusivity', () => {
  it('locks mode/zoom buttons while a gesture is active', () => {
    expect(gestureLockState(true).controlsLocked).toBe(true);
  });
  it('unlocks when no gesture', () => {
    expect(gestureLockState(false).controlsLocked).toBe(false);
  });
});
