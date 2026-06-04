import { describe, expect, it } from 'vitest';
import { canSendText } from '../src/handoff/HandoffPage';

describe('text bridge focus gating', () => {
  it('disables send when remote focus is not an editable input', () => {
    expect(canSendText({ text: '123456', disabled: false, focusEditable: false })).toBe(false);
  });
  it('enables send when focus is editable and text present', () => {
    expect(canSendText({ text: '123456', disabled: false, focusEditable: true })).toBe(true);
  });
  it('disables on empty text regardless of focus', () => {
    expect(canSendText({ text: '', disabled: false, focusEditable: true })).toBe(false);
  });
});
