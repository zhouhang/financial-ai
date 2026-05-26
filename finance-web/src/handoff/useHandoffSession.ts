import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildHandoffWsUrl } from './handoffWs';
import type { HandoffFrame, HandoffInputEvent, HandoffSession, HandoffStatus } from './types';

interface HandoffMessage {
  type: string;
  status?: HandoffStatus;
  session?: HandoffSession;
  controller_id?: string;
  error?: string;
  reason?: string;
  frame_id?: number;
  mime?: string;
  width?: number;
  height?: number;
  data?: string;
}

const TERMINAL_STATUSES = new Set<HandoffStatus>(['completed', 'expired', 'revoked']);

export function useHandoffSession(token: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<HandoffStatus>(token ? 'connecting' : 'expired');
  const [session, setSession] = useState<HandoffSession | null>(null);
  const [frame, setFrame] = useState<HandoffFrame | null>(null);
  const [error, setError] = useState('');
  const wsUrl = useMemo(() => (token ? buildHandoffWsUrl(token) : ''), [token]);

  const send = useCallback((payload: unknown) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    ws.send(JSON.stringify(payload));
    return true;
  }, []);

  const sendInput = useCallback(
    (event: HandoffInputEvent) => {
      send({ type: 'handoff_input', event });
    },
    [send],
  );

  const resume = useCallback(() => {
    setStatus('resuming');
    send({ type: 'resume_requested' });
  }, [send]);

  const reconnect = useCallback(() => {
    send({ type: 'reconnect_stream' });
  }, [send]);

  useEffect(() => {
    if (!token) {
      return undefined;
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus((current) => (current === 'connecting' ? 'active' : current));
    };

    ws.onmessage = (event) => {
      let msg: HandoffMessage;
      try {
        msg = JSON.parse(String(event.data || '{}')) as HandoffMessage;
      } catch {
        setError('收到无效消息');
        return;
      }

      if (msg.type === 'session') {
        setSession({ ...(msg.session || {}), controller_id: msg.controller_id });
        setStatus(msg.status || 'active');
        return;
      }

      if (msg.type === 'frame') {
        setFrame({
          frame_id: Number(msg.frame_id || 0),
          mime: msg.mime || 'image/jpeg',
          width: Number(msg.width || 0),
          height: Number(msg.height || 0),
          data: msg.data || '',
        });
        setStatus((current) => (current === 'connecting' ? 'active' : current));
        return;
      }

      if (msg.type === 'status') {
        setStatus(msg.status || 'active');
        if (msg.reason) {
          setError(msg.reason);
        }
        return;
      }

      if (msg.type === 'controller_revoked') {
        setStatus('revoked');
        return;
      }

      if (msg.type === 'error') {
        setStatus(msg.status || 'error');
        setError(msg.error || '链接不可用');
      }
    };

    ws.onclose = () => {
      setStatus((current) => (TERMINAL_STATUSES.has(current) ? current : 'waiting_agent'));
    };

    return () => {
      wsRef.current = null;
      ws.close();
    };
  }, [token, wsUrl]);

  return {
    status: token ? status : 'expired',
    session,
    frame,
    error: token ? error : '链接缺少 token',
    sendInput,
    resume,
    reconnect,
  };
}
