import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConnectionStatus, WsOutgoing } from '../types';

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/chat`;

const MAX_RECONNECT_ATTEMPTS = 50;
const BASE_RECONNECT_INTERVAL = 3000;
const MAX_RECONNECT_INTERVAL = 30000;

interface UseWebSocketOptions {
  onMessage?: (data: WsOutgoing) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  autoReconnect?: boolean;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    autoReconnect = true,
  } = options;

  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const callbacksRef = useRef(options);
  callbacksRef.current = options;

  const connect = useCallback(() => {
    // 如果已有 OPEN 或 CONNECTING 状态的连接，不重复创建
    const current = wsRef.current;
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    setStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      // 只有当前连接才更新状态
      if (wsRef.current === ws) {
        setStatus('connected');
        reconnectAttemptsRef.current = 0;
        callbacksRef.current.onConnect?.();
      }
    };

    ws.onmessage = (event) => {
      try {
        const data: WsOutgoing = JSON.parse(event.data);
        callbacksRef.current.onMessage?.(data);
      } catch {
        console.error('Failed to parse WS message:', event.data);
      }
    };

    ws.onclose = () => {
      // 关键：只有当关闭的是当前活跃连接时才清理引用和重连
      if (wsRef.current !== ws) return;
      
      setStatus('disconnected');
      wsRef.current = null;
      callbacksRef.current.onDisconnect?.();

      if (autoReconnect && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = Math.min(
          BASE_RECONNECT_INTERVAL * Math.pow(1.5, reconnectAttemptsRef.current),
          MAX_RECONNECT_INTERVAL
        );
        reconnectAttemptsRef.current++;
        reconnectTimerRef.current = window.setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [autoReconnect]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectAttemptsRef.current = MAX_RECONNECT_ATTEMPTS; // 阻止自动重连
    wsRef.current?.close();
    wsRef.current = null;
    setStatus('disconnected');
  }, []);

  const sendMessage = useCallback(
    (message: string, threadId: string, resume = false, authToken?: string) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        console.warn('WebSocket is not connected');
        return false;
      }
      const payload: Record<string, unknown> = {
        message,
        thread_id: threadId,
        resume,
      };
      if (authToken) {
        payload.auth_token = authToken;
      }
      wsRef.current.send(JSON.stringify(payload));
      return true;
    },
    []
  );

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { status, sendMessage, connect, disconnect };
}
