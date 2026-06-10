import type { HandoffCapabilities } from './types';

export function canSendText(
  s: { text: string; disabled: boolean; focusEditable: boolean | null },
): boolean {
  return Boolean(s.text) && !s.disabled && s.focusEditable === true;
}

export function backendStatusLabel(caps: HandoffCapabilities | undefined): string {
  if (!caps?.backend) return '';
  if (caps.backend === 'playwright') return '兼容模式';
  return '远程操作';
}

export function gestureLockState(gestureActive: boolean): { controlsLocked: boolean } {
  return { controlsLocked: gestureActive };
}
