import { describe, expect, it } from 'vitest';
import type { HandoffInputEvent, HandoffStatus, HandoffCapabilities } from '../src/handoff/types';

describe('handoff input schema', () => {
  it('input events carry controller_id and normalized coords', () => {
    const ev: HandoffInputEvent = { kind: 'mouse_move', x: 0.5, y: 0.5, button: 'left', controller_id: 'ctrl-1' };
    expect(ev.x).toBeGreaterThanOrEqual(0);
    expect(ev.controller_id).toBe('ctrl-1');
  });

  it('status union includes os-backend states', () => {
    const states: HandoffStatus[] = ['control_unavailable', 'window_unavailable', 'desktop_locked'];
    expect(states).toHaveLength(3);
  });

  it('capabilities expose backend + can_clipboard_paste', () => {
    const caps: HandoffCapabilities = { backend: 'os_windows', can_clipboard_paste: true, text_input: true };
    expect(caps.backend).toBe('os_windows');
  });
});
