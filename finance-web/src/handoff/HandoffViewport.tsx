import { useRef } from 'react';
import type { HandoffFrame, HandoffInputEvent } from './types';

export function gestureLockState(gestureActive: boolean): { controlsLocked: boolean } {
  return { controlsLocked: gestureActive };
}

interface HandoffViewportProps {
  frame: HandoffFrame | null;
  disabled?: boolean;
  mode?: 'control' | 'pan';
  zoom?: number;
  onInput: (event: HandoffInputEvent) => void;
  onGestureChange?: (active: boolean) => void;
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function displayedFrameRect(target: HTMLElement, frame: HandoffFrame | null) {
  const rect = target.getBoundingClientRect();
  const frameWidth = Number(frame?.width || 0);
  const frameHeight = Number(frame?.height || 0);
  if (rect.width <= 0 || rect.height <= 0 || frameWidth <= 0 || frameHeight <= 0) {
    return rect;
  }

  const frameRatio = frameWidth / frameHeight;
  const rectRatio = rect.width / rect.height;
  if (rectRatio > frameRatio) {
    const width = rect.height * frameRatio;
    return {
      left: rect.left + (rect.width - width) / 2,
      top: rect.top,
      width,
      height: rect.height,
    };
  }

  const height = rect.width / frameRatio;
  return {
    left: rect.left,
    top: rect.top + (rect.height - height) / 2,
    width: rect.width,
    height,
  };
}

function pointFromEvent(target: HTMLElement, event: { clientX: number; clientY: number }, frame: HandoffFrame | null) {
  const rect = displayedFrameRect(target, frame);
  const x = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
  const y = rect.height > 0 ? (event.clientY - rect.top) / rect.height : 0;
  return {
    x: Number(clamp(x).toFixed(4)),
    y: Number(clamp(y).toFixed(4)),
  };
}

function pointFromImageOrContainer(
  target: HTMLElement,
  image: HTMLImageElement | null,
  event: { clientX: number; clientY: number },
  frame: HandoffFrame | null,
) {
  const imageRect = image?.getBoundingClientRect();
  if (image && imageRect && imageRect.width > 0 && imageRect.height > 0) {
    const renderedFrame = displayedFrameRect(image, frame);
    const x = (event.clientX - renderedFrame.left) / renderedFrame.width;
    const y = (event.clientY - renderedFrame.top) / renderedFrame.height;
    return {
      x: Number(clamp(x).toFixed(4)),
      y: Number(clamp(y).toFixed(4)),
    };
  }
  return pointFromEvent(target, event, frame);
}

export default function HandoffViewport({
  frame,
  disabled = false,
  mode = 'control',
  zoom = 1,
  onInput,
  onGestureChange,
}: HandoffViewportProps) {
  const imageRef = useRef<HTMLImageElement | null>(null);
  const src = frame ? `data:${frame.mime};base64,${frame.data}` : '';
  const controlsEnabled = !disabled && mode === 'control';

  return (
    <div
      data-testid="handoff-viewport"
      className={`relative h-full min-h-[52dvh] w-full select-none overflow-auto bg-neutral-950 ${
        mode === 'control' ? 'touch-none' : 'touch-pan-x touch-pan-y'
      }`}
      onPointerDown={(event) => {
        if (!controlsEnabled) return;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        onGestureChange?.(true);
        onInput({
          kind: 'mouse_down',
          ...pointFromImageOrContainer(event.currentTarget, imageRef.current, event, frame),
          button: 'left',
        });
      }}
      onPointerMove={(event) => {
        if (!controlsEnabled || event.buttons !== 1) return;
        onInput({
          kind: 'mouse_move',
          ...pointFromImageOrContainer(event.currentTarget, imageRef.current, event, frame),
          button: 'left',
        });
      }}
      onPointerUp={(event) => {
        if (!controlsEnabled) return;
        onGestureChange?.(false);
        onInput({
          kind: 'mouse_up',
          ...pointFromImageOrContainer(event.currentTarget, imageRef.current, event, frame),
          button: 'left',
        });
      }}
      onPointerCancel={(event) => {
        if (!controlsEnabled) return;
        onGestureChange?.(false);
        onInput({
          kind: 'mouse_up',
          ...pointFromImageOrContainer(event.currentTarget, imageRef.current, event, frame),
          button: 'left',
        });
      }}
      onWheel={(event) => {
        if (!controlsEnabled) return;
        onInput({ kind: 'wheel', delta_x: event.deltaX, delta_y: event.deltaY });
      }}
    >
      {src ? (
        <div
          className="flex min-h-full min-w-full items-center justify-center p-2"
          style={{
            width: `${Math.max(1, zoom) * 100}%`,
            height: `${Math.max(1, zoom) * 100}%`,
          }}
        >
          <img
            ref={imageRef}
            alt=""
            src={src}
            className="block h-full w-full select-none object-contain"
            draggable={false}
          />
        </div>
      ) : (
        <div className="flex h-full min-h-[46dvh] w-full items-center justify-center bg-neutral-950">
          <div className="h-10 w-10 animate-pulse rounded-md border border-neutral-700 bg-neutral-900" />
        </div>
      )}
    </div>
  );
}
