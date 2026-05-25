import { CheckCircle2, Keyboard, RefreshCw, ShieldAlert, WifiOff } from 'lucide-react';
import { useMemo, useState } from 'react';
import HandoffViewport from './HandoffViewport';
import { parseHandoffToken } from './handoffWs';
import { useHandoffSession } from './useHandoffSession';

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

export default function HandoffPage() {
  const token = useMemo(() => parseHandoffToken(), []);
  const { status, session, frame, error, sendInput, resume, reconnect } = useHandoffSession(token);
  const [text, setText] = useState('');
  const disabled = status === 'revoked' || status === 'completed' || status === 'expired' || status === 'error';

  return (
    <main className="min-h-dvh bg-neutral-100 text-neutral-950">
      <section className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col bg-white">
        <header className="shrink-0 border-b border-neutral-200 px-4 pb-3 pt-[calc(env(safe-area-inset-top)+12px)]">
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
          <HandoffViewport frame={frame} disabled={disabled} onInput={sendInput} />
        </div>

        <footer className="shrink-0 space-y-3 border-t border-neutral-200 bg-white px-4 py-3 pb-[calc(env(safe-area-inset-bottom)+12px)]">
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
              type="button"
              disabled={disabled || !text}
              onClick={() => {
                sendInput({ kind: 'text', text });
                setText('');
              }}
              className="h-11 shrink-0 rounded-md bg-neutral-950 px-4 text-sm font-semibold text-white disabled:opacity-40"
            >
              发送
            </button>
          </div>

          <button
            type="button"
            disabled={disabled || status === 'resuming'}
            onClick={resume}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-md bg-orange-600 text-base font-semibold text-white disabled:opacity-50"
          >
            <CheckCircle2 size={20} />
            <span>我已完成验证</span>
          </button>
        </footer>
      </section>
    </main>
  );
}
