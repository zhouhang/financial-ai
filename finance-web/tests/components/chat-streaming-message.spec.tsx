import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SendMessageFn } from '../../src/hooks/useWebSocket';
import type { WsOutgoing } from '../../src/types';

let wsOnMessage: ((data: WsOutgoing) => void) | undefined;

vi.mock('../../src/hooks/useWebSocket', () => ({
  useWebSocket: (options: {
    onMessage?: (data: WsOutgoing) => void;
    onConnect?: (sendMessage: SendMessageFn) => void;
  }) => {
    wsOnMessage = options.onMessage;
    return {
      status: 'connected',
      sendMessage: vi.fn(() => true),
      connect: vi.fn(),
      disconnect: vi.fn(),
    };
  },
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  wsOnMessage = undefined;
});

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  window.scrollTo = vi.fn();
  Element.prototype.scrollTo = vi.fn();
  localStorage.clear();
  localStorage.setItem(
    'tally_guest_conversation',
    JSON.stringify({
      id: 'test-thread',
      title: '测试对话',
      createdAt: new Date('2026-05-09T00:00:00.000Z').toISOString(),
      updatedAt: new Date('2026-05-09T00:00:00.000Z').toISOString(),
      messages: [],
    }),
  );
});

describe('聊天流式响应', () => {
  it('连续 stream 帧归并到同一条助手消息', async () => {
    const { default: App } = await import('../../src/App');

    const { container } = render(<App />);

    await waitFor(() => {
      expect(wsOnMessage).toBeDefined();
    });

    act(() => {
      wsOnMessage?.({
        type: 'stream',
        content: '你好！我是 Tally，专业的智能财务助手，主要帮你处理两件事：\n',
        thread_id: 'test-thread',
      });
      wsOnMessage?.({
        type: 'stream',
        content: '数据整理：根据预设规则，从多张源表中聚合、匹配、计算并生成汇总表\n',
        thread_id: 'test-thread',
      });
      wsOnMessage?.({
        type: 'stream',
        content: '数据对账：按对账规则比对两边的数据，找出差异记录',
        thread_id: 'test-thread',
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/数据对账：按对账规则/)).toBeInTheDocument();
    });
    expect(screen.getByText(/数据整理：根据预设规则/)).toBeInTheDocument();
    expect(container.querySelectorAll('.message-content')).toHaveLength(1);
  });
});
