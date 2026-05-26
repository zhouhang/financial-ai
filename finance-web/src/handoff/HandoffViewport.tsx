import type { HandoffFrame, HandoffInputEvent } from './types';

interface HandoffViewportProps {
  frame: HandoffFrame | null;
  disabled?: boolean;
  onInput: (event: HandoffInputEvent) => void;
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function pointFromEvent(target: HTMLElement, event: { clientX: number; clientY: number }) {
  const rect = target.getBoundingClientRect();
  const x = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
  const y = rect.height > 0 ? (event.clientY - rect.top) / rect.height : 0;
  return {
    x: Number(clamp(x).toFixed(4)),
    y: Number(clamp(y).toFixed(4)),
  };
}

export default function HandoffViewport({ frame, disabled = false, onInput }: HandoffViewportProps) {
  const src = frame ? `data:${frame.mime};base64,${frame.data}` : '';

  return (
    <div
      data-testid="handoff-viewport"
      className="relative flex h-full min-h-[46dvh] w-full touch-none select-none items-center justify-center overflow-hidden bg-neutral-950"
      onPointerDown={(event) => {
        if (disabled) return;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        onInput({ kind: 'mouse_down', ...pointFromEvent(event.currentTarget, event), button: 'left' });
      }}
      onPointerMove={(event) => {
        if (disabled || event.buttons !== 1) return;
        onInput({ kind: 'mouse_move', ...pointFromEvent(event.currentTarget, event), button: 'left' });
      }}
      onPointerUp={(event) => {
        if (disabled) return;
        onInput({ kind: 'mouse_up', ...pointFromEvent(event.currentTarget, event), button: 'left' });
      }}
      onWheel={(event) => {
        if (disabled) return;
        onInput({ kind: 'wheel', delta_x: event.deltaX, delta_y: event.deltaY });
      }}
    >
      {src ? (
        <img
          alt=""
          src={src}
          className="h-full max-h-[68dvh] w-full object-contain"
          draggable={false}
        />
      ) : (
        <div className="flex h-full min-h-[46dvh] w-full items-center justify-center bg-neutral-950">
          <div className="h-10 w-10 animate-pulse rounded-md border border-neutral-700 bg-neutral-900" />
        </div>
      )}
    </div>
  );
}
