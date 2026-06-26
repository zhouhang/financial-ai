import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import HandoffPage from '../../src/handoff/HandoffPage';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  readyState = FakeWebSocket.OPEN;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
    setTimeout(() => this.onopen?.(), 0);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.onclose?.();
  }

  feed(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe('HandoffPage', () => {
  const originalWebSocket = globalThis.WebSocket;

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    FakeWebSocket.instances = [];
    globalThis.WebSocket = originalWebSocket;
    window.history.replaceState({}, '', '/');
  });

  it('connects to /api/handoff/ws with token and renders session metadata', async () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    window.history.replaceState({}, '', '/handoff?t=TKN');

    render(<HandoffPage />);

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(FakeWebSocket.instances[0].url).toContain('/api/handoff/ws?t=TKN');

    FakeWebSocket.instances[0].feed({
      type: 'session',
      controller_id: 'ctrl-1',
      status: 'active',
      session: {
        profile_key: '单枪旗舰店',
        reason: 'RISK_VERIFICATION',
        agent_id: 'browser-agent-win',
        expires_at: '2026-05-25T12:00:00Z',
      },
    });

    expect(await screen.findByText('单枪旗舰店')).toBeInTheDocument();
    expect(screen.getByText(/browser-agent-win/)).toBeInTheDocument();
  });

  it('renders frames and sends normalized pointer input', async () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    window.history.replaceState({}, '', '/handoff?t=TKN');

    render(<HandoffPage />);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const ws = FakeWebSocket.instances[0];
    ws.feed({
      type: 'frame',
      mime: 'image/jpeg',
      width: 100,
      height: 80,
      frame_id: 1,
      data: 'YWJj',
    });

    const viewport = await screen.findByTestId('handoff-viewport');
    const image = viewport.querySelector('img');
    if (!image) {
      throw new Error('handoff frame image not rendered');
    }
    vi.spyOn(image, 'getBoundingClientRect').mockReturnValue({
      left: 47.5,
      top: 20,
      width: 125,
      height: 100,
      right: 172.5,
      bottom: 120,
      x: 47.5,
      y: 20,
      toJSON: () => ({}),
    } as DOMRect);
    vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({
      left: 10,
      top: 20,
      width: 200,
      height: 100,
      right: 210,
      bottom: 120,
      x: 10,
      y: 20,
      toJSON: () => ({}),
    } as DOMRect);

    fireEvent.pointerDown(viewport, { clientX: 110, clientY: 70, pointerId: 1, button: 0 });
    fireEvent.pointerUp(viewport, { clientX: 110, clientY: 70, pointerId: 1, button: 0 });

    const sent = ws.sent.map((item) => JSON.parse(item));
    expect(sent.some((msg) => msg.type === 'handoff_input' && msg.event.kind === 'mouse_down')).toBe(true);
    expect(sent.some((msg) => msg.type === 'handoff_input' && msg.event.x === 0.5 && msg.event.y === 0.5)).toBe(true);
  });

  it('sends text input and resume request', async () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    window.history.replaceState({}, '', '/handoff?t=TKN');

    render(<HandoffPage />);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const ws = FakeWebSocket.instances[0];

    // Establish editable focus so the send button is enabled (focusEditable gates send).
    ws.feed({ type: 'focus_state', editable: true });

    expect(screen.queryByPlaceholderText('短信验证码或文本')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '打开键盘输入' }));
    fireEvent.change(screen.getByPlaceholderText('短信验证码或文本'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '填入' }));
    fireEvent.click(screen.getByRole('button', { name: '我已完成验证' }));

    const sent = ws.sent.map((item) => JSON.parse(item));
    expect(sent).toContainEqual({ type: 'handoff_input', event: { kind: 'text', text: '123456' } });
    expect(sent).toContainEqual({ type: 'resume_requested' });
  });

  it('does not show agent offline when only the controller websocket closes', async () => {
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    window.history.replaceState({}, '', '/handoff?t=TKN');

    render(<HandoffPage />);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const ws = FakeWebSocket.instances[0];
    ws.feed({
      type: 'session',
      controller_id: 'ctrl-1',
      status: 'active',
      session: {
        profile_key: '单枪旗舰店',
        reason: 'RISK_VERIFICATION',
        agent_id: 'browser-agent-win',
      },
    });
    expect(await screen.findByText('可操作')).toBeInTheDocument();

    ws.close();

    expect(screen.queryByText('等待采集机')).not.toBeInTheDocument();
    expect(await screen.findByText('连接中')).toBeInTheDocument();
  });
});
