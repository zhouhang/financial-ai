import { describe, expect, it } from 'vitest';
import { buildReconnectCleanupEvents } from '../src/handoff/useHandoffSession';

describe('reconnect gesture cleanup', () => {
  it('emits mouse_up release when a gesture was mid-flight', () => {
    const events = buildReconnectCleanupEvents({ gestureActive: true, button: 'left' });
    expect(events).toEqual([{ kind: 'mouse_up', button: 'left' }]);
  });

  it('emits nothing when no gesture in flight', () => {
    expect(buildReconnectCleanupEvents({ gestureActive: false, button: 'left' })).toEqual([]);
  });
});
