import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WsOutgoing } from '../../src/types';

const wsMockState = vi.hoisted(() => ({
  sendMessageMock: vi.fn(() => true),
  onMessage: undefined as ((data: WsOutgoing) => void) | undefined,
}));
const conversationListResponses = vi.hoisted(() => [] as unknown[]);

vi.mock('../../src/hooks/useWebSocket', () => ({
  useWebSocket: (options: { onMessage?: (data: WsOutgoing) => void }) => {
    wsMockState.onMessage = options.onMessage;
    return {
      status: 'connected',
      sendMessage: wsMockState.sendMessageMock,
      connect: vi.fn(),
      disconnect: vi.fn(),
    };
  },
}));

function setConversationListResponses(...responses: unknown[]) {
  conversationListResponses.splice(0, conversationListResponses.length, ...responses);
}

function mockJsonResponse(payload: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

const userTasksPayload = {
  success: true,
  tasks: [
    {
      id: 1,
      task_code: 'proc',
      task_name: '数据整理',
      task_type: 'proc',
      rules: [
        {
          id: 11,
          rule_code: 'overdue_proc',
          name: '逾期文件整理',
          rule_type: 'proc',
          file_rule_code: 'overdue_file_rule',
          supported_entry_modes: ['upload'],
        },
      ],
    },
  ],
};

function installFetchMock() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === '/api/conversations') {
        const nextResponse = conversationListResponses.shift() ?? { success: true, conversations: [] };
        return mockJsonResponse(nextResponse);
      }

      if (url.startsWith('/api/conversations/')) {
        return mockJsonResponse({ success: true, conversation: null });
      }

      if (url === '/api/proc/list_user_tasks') {
        return mockJsonResponse(userTasksPayload);
      }

      if (url === '/api/upload') {
        return mockJsonResponse({
          filename: 'uploaded.xlsx',
          size: 128,
          file_path: `/uploads/${crypto.randomUUID()}.xlsx`,
        });
      }

      return mockJsonResponse({});
    }),
  );
}

async function renderApp() {
  vi.resetModules();
  const { default: App } = await import('../../src/App');
  return render(<App />);
}

function getSidebar(container: HTMLElement): HTMLElement {
  const sidebar = container.querySelector('aside');
  expect(sidebar).toBeTruthy();
  return sidebar as HTMLElement;
}

async function openProcUploadTask(sidebar: HTMLElement) {
  await waitFor(() => {
    expect(within(sidebar).getByRole('button', { name: '数据整理' })).toBeInTheDocument();
  });

  fireEvent.click(within(sidebar).getByRole('button', { name: '数据整理' }));

  await waitFor(() => {
    expect(within(sidebar).getByRole('button', { name: '上传文件整理' })).toBeInTheDocument();
  });

  fireEvent.click(within(sidebar).getByRole('button', { name: '上传文件整理' }));
}

describe('conversation draft and task title UX', () => {
  beforeEach(() => {
    wsMockState.sendMessageMock.mockClear();
    wsMockState.onMessage = undefined;
    setConversationListResponses({ success: true, conversations: [] });
    localStorage.clear();
    localStorage.setItem('tally_auth_token', 'token-1');
    localStorage.setItem('tally_current_user', JSON.stringify({ id: 'user-1', username: '测试用户' }));

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
    installFetchMock();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('keeps empty new and task drafts out of sidebar history', async () => {
    const { container } = await renderApp();
    const sidebar = getSidebar(container);

    await waitFor(() => {
      expect(screen.getByText('开始一条财务对话')).toBeInTheDocument();
    });

    fireEvent.click(within(sidebar).getByRole('button', { name: '开启新对话' }));

    expect(screen.getByText('开始一条财务对话')).toBeInTheDocument();
    expect(within(sidebar).queryByText('新对话')).not.toBeInTheDocument();

    fireEvent.click(within(sidebar).getByRole('button', { name: '数据连接' }));
    await waitFor(() => {
      expect(within(sidebar).queryByText('新对话')).not.toBeInTheDocument();
    });

    fireEvent.click(within(sidebar).getByRole('button', { name: '对话' }));
    await openProcUploadTask(sidebar);

    await waitFor(() => {
      expect(screen.getByText('开始一条财务对话')).toBeInTheDocument();
    });
    expect(within(sidebar).queryByText('新对话')).not.toBeInTheDocument();
    expect(within(sidebar).queryByText('数据整理 · 逾期文件整理 · 2个文件')).not.toBeInTheDocument();
  }, 20000);

  it('uses task file count title after uploading and sends task context', async () => {
    const { container } = await renderApp();
    const sidebar = getSidebar(container);

    await openProcUploadTask(sidebar);

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).toBeTruthy();

    fireEvent.change(fileInput as HTMLInputElement, {
      target: {
        files: [
          new File(['source'], 'source.xlsx', {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          }),
          new File(['target'], 'target.xlsx', {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          }),
        ],
      },
    });

    fireEvent.click(container.querySelector('button.sidebar-primary-cta.w-9.h-9') as HTMLButtonElement);

    await waitFor(() => {
      expect(within(sidebar).getByText('数据整理 · 逾期文件整理 · 2个文件')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(wsMockState.sendMessageMock).toHaveBeenCalledTimes(1);
    });

    const firstCall = wsMockState.sendMessageMock.mock.calls[0];
    expect(firstCall[0]).toBe('已上传 2 个文件，请按当前规则处理。');
    expect(firstCall[4]).toHaveLength(2);
    expect(firstCall[6]).toBe('proc');
    expect(firstCall[7]).toBe('overdue_proc');
    expect(firstCall[8]).toBe('逾期文件整理');
    expect(firstCall[9]).toBe('overdue_file_rule');
  }, 20000);

  it('keeps the task title when the server returns a generic same-id conversation', async () => {
    setConversationListResponses(
      { success: true, conversations: [] },
      {
        success: true,
        conversations: [
          {
            id: '22222222-2222-4222-8222-222222222222',
            title: '已上传 2 个文件，请按当前规则处理。',
            created_at: '2026-05-19T12:00:00.000Z',
            updated_at: '2026-05-19T12:00:00.000Z',
            status: 'active',
            messages: [],
          },
        ],
      },
    );

    const { container } = await renderApp();
    const sidebar = getSidebar(container);

    await openProcUploadTask(sidebar);

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(fileInput).toBeTruthy();

    fireEvent.change(fileInput as HTMLInputElement, {
      target: {
        files: [
          new File(['source'], 'source.xlsx', {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          }),
          new File(['target'], 'target.xlsx', {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          }),
        ],
      },
    });

    fireEvent.click(container.querySelector('button.sidebar-primary-cta.w-9.h-9') as HTMLButtonElement);

    await waitFor(() => {
      expect(within(sidebar).getByText('数据整理 · 逾期文件整理 · 2个文件')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(wsMockState.sendMessageMock).toHaveBeenCalledTimes(1);
    });

    const localThreadId = wsMockState.sendMessageMock.mock.calls[0][1] as string;

    await act(async () => {
      wsMockState.onMessage?.({
        type: 'conversation_created',
        thread_id: localThreadId,
        conversation_id: '22222222-2222-4222-8222-222222222222',
      });
    });

    await waitFor(() => {
      expect(within(sidebar).getByText('数据整理 · 逾期文件整理 · 2个文件')).toBeInTheDocument();
    });
    expect(within(sidebar).queryByText('已上传 2 个文件，请按当前规则处理。')).not.toBeInTheDocument();
  }, 20000);
});
