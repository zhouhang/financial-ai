import {
  CheckCircle2,
  Keyboard,
  Minus,
  MousePointerClick,
  Move,
  Plus,
  RefreshCw,
  ShieldAlert,
  WifiOff,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import HandoffViewport, { gestureLockState } from './HandoffViewport';
import { parseHandoffToken } from './handoffWs';
import { useHandoffSession } from './useHandoffSession';
import type { HandoffCapabilities } from './types';

export function canSendText(
  s: { text: string; disabled: boolean; focusEditable: boolean | null },
): boolean {
  return Boolean(s.text) && !s.disabled && s.focusEditable === true;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    connecting: '连接中',
    active: '可操作',
    waiting_agent: '等待采集机',
    revoked: '已被接管',
    resuming: '复检中',
    still_blocked: '仍需验证',
    completed: '已通过',
    expired: '已失效',
    error: '不可用',
  };
  return labels[status] || status;
}

function statusTone(status: string): string {
  if (status === 'active' || status === 'completed') {
    return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  }
  if (status === 'waiting_agent' || status === 'still_blocked') {
    return 'text-amber-800 bg-amber-50 border-amber-200';
  }
  if (status === 'expired' || status === 'error' || status === 'revoked') {
    return 'text-red-700 bg-red-50 border-red-200';
  }
  return 'text-orange-700 bg-orange-50 border-orange-200';
}

export function backendStatusLabel(caps: HandoffCapabilities | undefined): string {
  if (!caps?.backend) return '';
  if (caps.backend === 'playwright') return '兼容模式';
  return '远程操作';
}

const ZOOM_LEVELS = [1, 1.5, 2.25];

export default function HandoffPage() {
  const token = useMemo(() => parseHandoffToken(), []);
  const { status, session, frame, error, sendInput, resume, reconnect, focusEditable } = useHandoffSession(token);
  const [text, setText] = useState('');
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [panMode, setPanMode] = useState(false);
  const [zoomIndex, setZoomIndex] = useState(0);
  const [gestureActive, setGestureActive] = useState(false);
  const zoom = ZOOM_LEVELS[zoomIndex] || 1;
  const disabled = status === 'revoked' || status === 'completed' || status === 'expired' || status === 'error';
  const { controlsLocked } = gestureLockState(gestureActive);

  return (
    <main className="h-full overflow-hidden bg-neutral-100 text-neutral-950">
      <section className="mx-auto flex h-full w-full max-w-3xl flex-col bg-white">
        <header className="shrink-0 border-b border-neutral-200 px-3 pb-2 pt-[calc(env(safe-area-inset-top)+8px)]">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-semibold ${statusTone(status)}`}>
                <ShieldAlert size={15} />
                <span>{statusLabel(status)}</span>
              </div>
              <h1 className="mt-2 truncate text-lg font-semibold leading-6 text-neutral-950">
                {session?.profile_key || '人工验证'}
              </h1>
              <p className="mt-1 truncate text-xs leading-5 text-neutral-500">
                {session?.reason || 'RISK_VERIFICATION'} · {session?.agent_id || '采集机'}
                {backendStatusLabel(session?.capabilities) ? (
                  <> · {backendStatusLabel(session?.capabilities)}</>
                ) : null}
              </p>
            </div>
            <button
              type="button"
              onClick={reconnect}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-neutral-200 bg-white text-neutral-700 shadow-sm disabled:opacity-40"
              aria-label="重连画面"
              disabled={disabled}
            >
              <RefreshCw size={18} />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 bg-neutral-950">
          <HandoffViewport
            frame={frame}
            disabled={disabled}
            mode={panMode ? 'pan' : 'control'}
            zoom={zoom}
            onInput={sendInput}
            onGestureChange={setGestureActive}
          />
        </div>

        <footer className="shrink-0 space-y-2 border-t border-neutral-200 bg-white px-3 py-2 pb-[calc(env(safe-area-inset-bottom)+8px)]">
          {status === 'waiting_agent' ? (
            <div className="flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <WifiOff size={16} />
              <span>采集机暂未连接</span>
            </div>
          ) : null}
          {status === 'revoked' ? (
            <div className="rounded-md bg-neutral-100 px-3 py-2 text-sm text-neutral-600">新的页面已接管</div>
          ) : null}
          {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

          {keyboardOpen ? (
            <form
              className="flex flex-col gap-1.5 rounded-md border border-neutral-200 bg-neutral-50 p-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (!canSendText({ text, disabled, focusEditable })) return;
                sendInput({ kind: 'text', text });
                setText('');
              }}
            >
              <div className="flex gap-2">
                <label className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-neutral-300 bg-white px-3 py-2 focus-within:border-orange-500">
                  <Keyboard size={17} className="shrink-0 text-neutral-500" />
                  <input
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    disabled={disabled}
                    className="min-w-0 flex-1 bg-transparent text-base leading-6 outline-none placeholder:text-neutral-400"
                    placeholder="短信验证码或文本"
                    inputMode="text"
                    enterKeyHint="send"
                  />
                </label>
                <button
                  type="submit"
                  disabled={!canSendText({ text, disabled, focusEditable })}
                  className="h-11 shrink-0 rounded-md bg-neutral-950 px-4 text-sm font-semibold text-white disabled:opacity-40"
                >
                  发送
                </button>
              </div>
              {focusEditable === false ? (
                <p className="px-1 text-xs text-amber-700">请先点中输入框</p>
              ) : null}
            </form>
          ) : null}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setKeyboardOpen((value) => !value)}
              className={`grid h-11 w-11 shrink-0 place-items-center rounded-md border text-neutral-700 shadow-sm disabled:opacity-40 ${
                keyboardOpen ? 'border-orange-300 bg-orange-50' : 'border-neutral-200 bg-white'
              }`}
              aria-label={keyboardOpen ? '关闭键盘输入' : '打开键盘输入'}
              aria-pressed={keyboardOpen}
              disabled={disabled || controlsLocked}
            >
              <Keyboard size={17} className="shrink-0 text-neutral-500" />
            </button>
            <button
              type="button"
              onClick={() => setZoomIndex((value) => Math.max(0, value - 1))}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-md border border-neutral-200 bg-white text-neutral-700 shadow-sm disabled:opacity-40"
              aria-label="缩小画面"
              disabled={zoomIndex === 0 || controlsLocked}
            >
              <Minus size={18} />
            </button>
            <button
              type="button"
              onClick={() => setZoomIndex((value) => Math.min(ZOOM_LEVELS.length - 1, value + 1))}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-md border border-neutral-200 bg-white text-neutral-700 shadow-sm disabled:opacity-40"
              aria-label="放大画面"
              disabled={zoomIndex >= ZOOM_LEVELS.length - 1 || controlsLocked}
            >
              <Plus size={18} />
            </button>
            <button
              type="button"
              onClick={() => {
                if (gestureActive) {
                  sendInput({ kind: 'mouse_up', button: 'left', x: 0, y: 0 });
                }
                setPanMode((value) => !value);
              }}
              className={`grid h-11 w-11 shrink-0 place-items-center rounded-md border shadow-sm disabled:opacity-40 ${
                panMode ? 'border-orange-300 bg-orange-50 text-orange-700' : 'border-neutral-200 bg-white text-neutral-700'
              }`}
              aria-label={panMode ? '切换到远程操作' : '切换到移动画面'}
              aria-pressed={panMode}
              disabled={disabled || controlsLocked}
            >
              {panMode ? <Move size={18} /> : <MousePointerClick size={18} />}
            </button>
            <button
              type="button"
              disabled={disabled || status === 'resuming'}
              onClick={resume}
              className="flex h-11 min-w-0 flex-1 items-center justify-center gap-2 rounded-md bg-orange-600 px-3 text-base font-semibold text-white disabled:opacity-50"
            >
              <CheckCircle2 size={19} />
              <span className="truncate">我已完成验证</span>
            </button>
          </div>
        </footer>
      </section>
    </main>
  );
}
