import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SendMessageFn } from '../../src/hooks/useWebSocket';
import type { WsOutgoing } from '../../src/types';

vi.mock('../../src/hooks/useWebSocket', () => ({
  useWebSocket: (options: {
    onMessage?: (data: WsOutgoing) => void;
    onConnect?: (sendMessage: SendMessageFn) => void;
  }) => {
    void options;
    return {
      status: 'connected',
      sendMessage: vi.fn(() => true),
      connect: vi.fn(),
      disconnect: vi.fn(),
    };
  },
}));

function installBrowserStubs() {
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
}

function seedGuestConversation() {
  localStorage.setItem(
    'tally_guest_conversation',
    JSON.stringify({
      id: 'site-filing-layout-thread',
      title: '备案布局测试',
      createdAt: new Date('2026-06-08T00:00:00.000Z').toISOString(),
      updatedAt: new Date('2026-06-08T00:00:00.000Z').toISOString(),
      messages: [],
    }),
  );
}

describe('Site filing layout', () => {
  beforeEach(() => {
    vi.resetModules();
    installBrowserStubs();
    localStorage.clear();
    seedGuestConversation();
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    localStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('renders the main app filing inside the right content column', async () => {
    const { default: App } = await import('../../src/App');
    const { container } = render(<App />);

    const filing = screen.getByLabelText('ICP备案号');
    const rightColumn = filing.closest('main.site-main-column');
    const sidebar = container.querySelector('aside');

    expect(rightColumn).not.toBeNull();
    expect(rightColumn).toContainElement(filing);
    expect(sidebar).not.toBeNull();
    expect(sidebar?.contains(filing)).toBe(false);
  }, 20000);
});
