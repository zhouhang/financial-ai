# Tally Chat Draft Title UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide empty chat/task drafts from the sidebar history and generate readable task titles for data processing and reconciliation conversations.

**Architecture:** Add a small pure title-formatting utility, then have `App.tsx` use it whenever a local conversation is created from the first user message. Keep the existing chat-based task flow intact; the sidebar history simply stops rendering empty pending drafts and starts rendering task-aware titles once a conversation has a message.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, Testing Library, existing WebSocket chat flow.

---

## File Structure

- Create `finance-web/src/utils/conversationTitles.ts`
  - Owns all title-building rules for normal chat, proc task chat, and recon task chat.
  - Pure functions only; no React state or browser APIs.
- Create `finance-web/tests/components/conversationTitles.test.ts`
  - Unit coverage for title formatting edge cases.
- Create `finance-web/tests/components/conversation-draft-title-ux.spec.tsx`
  - Integration coverage for sidebar draft hiding and task history title behavior in `App`.
- Modify `finance-web/src/App.tsx`
  - Import the title helper.
  - Use it in first-message local conversation creation and first-message append fallback.
  - Stop showing `pendingNewConvRef` in `mergedConversations`.
  - Stop hiding task conversations through `hiddenConversationIds` when selecting a task entry.

No backend files change. No database migration. No task-running card UI.

---

### Task 1: Add Pure Conversation Title Utility

**Files:**
- Create: `finance-web/src/utils/conversationTitles.ts`
- Create: `finance-web/tests/components/conversationTitles.test.ts`

- [ ] **Step 1: Write the failing unit tests**

Create `finance-web/tests/components/conversationTitles.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { buildConversationTitle, formatConversationTitleDate } from '../../src/utils/conversationTitles';
import type { MessageAttachment, UserTaskRule } from '../../src/types';

function buildRule(overrides: Partial<UserTaskRule>): UserTaskRule {
  return {
    id: 1,
    rule_code: 'rule-1',
    name: '默认规则',
    rule_type: 'task',
    task_code: 'task',
    task_name: '默认任务',
    task_type: 'proc',
    ...overrides,
  };
}

describe('conversation title formatting', () => {
  it('formats local dates as YYYY-MM-DD', () => {
    expect(formatConversationTitleDate(new Date('2026-05-19T04:30:00.000Z'))).toBe('2026-05-19');
  });

  it('uses the first user message for normal chat titles', () => {
    expect(
      buildConversationTitle({
        text: '请帮我分析本月店铺经营情况，并给出风险提示',
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('请帮我分析本月店铺经营情况，并...');
  });

  it('falls back to 新对话 for empty non-task conversations with only attachments', () => {
    const attachments: MessageAttachment[] = [
      { name: 'orders.xlsx', size: 1024, path: '/uploads/orders.xlsx' },
    ];

    expect(
      buildConversationTitle({
        text: '',
        attachments,
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('新对话');
  });

  it('builds reconciliation task titles with rule name and date', () => {
    expect(
      buildConversationTitle({
        text: '已上传 2 个文件，请按当前规则处理。',
        taskContext: buildRule({
          task_type: 'recon',
          task_name: '数据对账',
          name: '淘宝结算规则',
        }),
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('数据对账 · 淘宝结算规则 · 2026-05-19');
  });

  it('builds proc task titles with rule name and uploaded file count', () => {
    const attachments: MessageAttachment[] = [
      { name: 'source.xlsx', size: 100, path: '/uploads/source.xlsx' },
      { name: 'target.xlsx', size: 100, path: '/uploads/target.xlsx' },
    ];

    expect(
      buildConversationTitle({
        text: '已上传 2 个文件，请按当前规则处理。',
        attachments,
        taskContext: buildRule({
          task_type: 'proc',
          task_name: '数据整理',
          name: '逾期文件整理',
        }),
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('数据整理 · 逾期文件整理 · 2个文件');
  });

  it('falls back to date for proc task titles without uploaded files', () => {
    expect(
      buildConversationTitle({
        text: '请按当前规则处理。',
        taskContext: buildRule({
          task_type: 'proc',
          task_name: '数据整理',
          name: '逾期文件整理',
        }),
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('数据整理 · 逾期文件整理 · 2026-05-19');
  });

  it('falls back from empty rule name to task name and then 当前规则', () => {
    expect(
      buildConversationTitle({
        text: '请按当前规则处理。',
        taskContext: buildRule({
          task_type: 'recon',
          task_name: '数据对账',
          name: '',
        }),
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('数据对账 · 数据对账 · 2026-05-19');

    expect(
      buildConversationTitle({
        text: '请按当前规则处理。',
        taskContext: buildRule({
          task_type: 'recon',
          task_name: '',
          name: '',
        }),
        date: new Date('2026-05-19T00:00:00.000Z'),
      }),
    ).toBe('数据对账 · 当前规则 · 2026-05-19');
  });
});
```

- [ ] **Step 2: Run the unit test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/conversationTitles.test.ts
```

Expected: FAIL because `../../src/utils/conversationTitles` does not exist.

- [ ] **Step 3: Add the title utility**

Create `finance-web/src/utils/conversationTitles.ts`:

```typescript
import type { MessageAttachment, UserTaskRule } from '../types';

interface BuildConversationTitleArgs {
  text: string;
  attachments?: MessageAttachment[];
  taskContext?: Pick<UserTaskRule, 'task_type' | 'task_name' | 'name'> | null;
  date?: Date;
}

function padDatePart(value: number): string {
  return String(value).padStart(2, '0');
}

export function formatConversationTitleDate(date: Date): string {
  const year = date.getFullYear();
  const month = padDatePart(date.getMonth() + 1);
  const day = padDatePart(date.getDate());
  return `${year}-${month}-${day}`;
}

function normalizeRuleName(taskContext: BuildConversationTitleArgs['taskContext']): string {
  const ruleName = taskContext?.name?.trim();
  if (ruleName) return ruleName;

  const taskName = taskContext?.task_name?.trim();
  if (taskName) return taskName;

  return '当前规则';
}

function buildNormalChatTitle(text: string): string {
  const normalized = text.trim();
  if (!normalized) return '新对话';
  return normalized.slice(0, 20) + (normalized.length > 20 ? '...' : '');
}

export function buildConversationTitle({
  text,
  attachments = [],
  taskContext = null,
  date = new Date(),
}: BuildConversationTitleArgs): string {
  const taskType = taskContext?.task_type;
  const ruleName = normalizeRuleName(taskContext);
  const formattedDate = formatConversationTitleDate(date);

  if (taskType === 'recon') {
    return `数据对账 · ${ruleName} · ${formattedDate}`;
  }

  if (taskType === 'proc') {
    if (attachments.length > 0) {
      return `数据整理 · ${ruleName} · ${attachments.length}个文件`;
    }
    return `数据整理 · ${ruleName} · ${formattedDate}`;
  }

  return buildNormalChatTitle(text);
}
```

- [ ] **Step 4: Run the unit test and verify it passes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/conversationTitles.test.ts
```

Expected: PASS for all tests in `conversationTitles.test.ts`.

- [ ] **Step 5: Commit the utility and unit tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/utils/conversationTitles.ts finance-web/tests/components/conversationTitles.test.ts
git commit -m "feat: add conversation title formatter"
```

---

### Task 2: Hide Empty Drafts and Apply Task Titles in App

**Files:**
- Create: `finance-web/tests/components/conversation-draft-title-ux.spec.tsx`
- Modify: `finance-web/src/App.tsx`

- [ ] **Step 1: Write the failing integration tests**

Create `finance-web/tests/components/conversation-draft-title-ux.spec.tsx`:

```typescript
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SendMessageFn } from '../../src/hooks/useWebSocket';

const sendMessageMock = vi.fn<SendMessageFn>(() => true);

vi.mock('../../src/hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    status: 'connected',
    sendMessage: sendMessageMock,
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}));

function buildJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

function installBrowserMocks() {
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

const tasksResponse = {
  success: true,
  tasks: [
    {
      id: 10,
      task_code: 'proc',
      task_name: '数据整理',
      task_type: 'proc',
      rules: [
        {
          id: 101,
          rule_code: 'overdue_proc',
          name: '逾期文件整理',
          rule_type: 'proc',
          task_code: 'proc',
          task_name: '数据整理',
          task_type: 'proc',
          file_rule_code: 'overdue_file_rule',
          supported_entry_modes: ['upload'],
        },
      ],
    },
    {
      id: 20,
      task_code: 'recon',
      task_name: '数据对账',
      task_type: 'recon',
      rules: [
        {
          id: 201,
          rule_code: 'taobao_recon',
          name: '淘宝结算规则',
          rule_type: 'recon',
          task_code: 'recon',
          task_name: '数据对账',
          task_type: 'recon',
          file_rule_code: 'taobao_file_rule',
          supported_entry_modes: ['upload'],
        },
      ],
    },
  ],
};

const historyConversation = {
  id: '11111111-1111-4111-8111-111111111111',
  title: '历史对话',
  created_at: '2026-05-18T08:00:00.000Z',
  updated_at: '2026-05-18T08:00:00.000Z',
  status: 'active',
};

function mockFetch(options: { withHistory?: boolean } = {}) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);

    if (url === '/api/conversations') {
      return buildJsonResponse({
        success: true,
        conversations: options.withHistory ? [historyConversation] : [],
      });
    }

    if (url === `/api/conversations/${historyConversation.id}`) {
      return buildJsonResponse({
        success: true,
        conversation: {
          ...historyConversation,
          messages: [
            {
              id: 'message-1',
              role: 'user',
              content: '历史问题',
              created_at: '2026-05-18T08:00:00.000Z',
            },
          ],
        },
      });
    }

    if (url === '/api/proc/list_user_tasks') {
      return buildJsonResponse(tasksResponse);
    }

    if (url === '/api/upload') {
      const formData = init?.body as FormData;
      const file = formData.get('file') as File;
      return buildJsonResponse({
        filename: file.name,
        size: file.size,
        file_path: `/uploads/${file.name}`,
      });
    }

    throw new Error(`Unexpected fetch url: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function renderApp() {
  vi.resetModules();
  const { default: App } = await import('../../src/App');
  return render(<App />);
}

function getSidebar(container: HTMLElement): HTMLElement {
  const sidebar = container.querySelector('aside');
  if (!sidebar) {
    throw new Error('Expected sidebar to render');
  }
  return sidebar as HTMLElement;
}

describe('Tally conversation draft and task titles', () => {
  beforeEach(() => {
    installBrowserMocks();
    sendMessageMock.mockClear();
    localStorage.clear();
    localStorage.setItem('tally_auth_token', 'mock-token');
    localStorage.setItem(
      'tally_current_user',
      JSON.stringify({
        id: 'user-1',
        username: 'admin',
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.resetModules();
    localStorage.clear();
  });

  it('does not render empty new conversation drafts in the sidebar history', async () => {
    mockFetch({ withHistory: true });

    const { container } = await renderApp();
    const sidebar = getSidebar(container);

    expect(await within(sidebar).findByText('历史对话')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '开启新对话' }));

    await waitFor(() => {
      expect(within(sidebar).queryByText('新对话')).not.toBeInTheDocument();
    });

    fireEvent.click(within(sidebar).getByText('历史对话'));

    await waitFor(() => {
      expect(within(sidebar).queryByText('新对话')).not.toBeInTheDocument();
    });
  });

  it('shows a proc task conversation title only after files are sent', async () => {
    mockFetch();

    const { container } = await renderApp();
    const sidebar = getSidebar(container);

    expect(await screen.findByRole('button', { name: '数据整理' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '数据整理' }));
    fireEvent.click(await screen.findByRole('button', { name: '上传文件整理' }));

    expect(within(sidebar).queryByText('新对话')).not.toBeInTheDocument();
    expect(within(sidebar).queryByText(/数据整理 · 逾期文件整理/)).not.toBeInTheDocument();

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null;
    if (!fileInput) {
      throw new Error('Expected file input to render');
    }

    const files = [
      new File(['source'], 'source.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
      new File(['target'], 'target.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    ];

    fireEvent.change(fileInput, { target: { files } });

    const textarea = screen.getByPlaceholderText(/当前规则：逾期文件整理/);
    fireEvent.keyDown(textarea, {
      key: 'Enter',
      code: 'Enter',
      charCode: 13,
    });

    expect(await within(sidebar).findByText('数据整理 · 逾期文件整理 · 2个文件')).toBeInTheDocument();
    expect(sendMessageMock).toHaveBeenCalledWith(
      '已上传 2 个文件，请按当前规则处理。',
      expect.any(String),
      false,
      'mock-token',
      [
        { name: 'source.xlsx', path: '/uploads/source.xlsx' },
        { name: 'target.xlsx', path: '/uploads/target.xlsx' },
      ],
      undefined,
      'proc',
      'overdue_proc',
      '逾期文件整理',
      'overdue_file_rule',
    );
  });
});
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/conversation-draft-title-ux.spec.tsx
```

Expected: FAIL. Current behavior still renders empty pending drafts in `mergedConversations`, and task titles are not generated from `taskContext`.

- [ ] **Step 3: Import the title helper in `App.tsx`**

Modify the imports near the top of `finance-web/src/App.tsx`:

```typescript
import { ruleSupportsEntryMode } from './utils/ruleEntryModes';
import { buildConversationTitle } from './utils/conversationTitles';
```

- [ ] **Step 4: Use task-aware titles when appending the first user message**

In `finance-web/src/App.tsx`, replace the `title:` calculation inside `appendMessage` with:

```typescript
                title:
                  c.messages.length === 0 && msg.role === 'user'
                    ? buildConversationTitle({
                        text: msg.content,
                        attachments: msg.attachments,
                        taskContext: c.taskContext,
                        date: msg.timestamp,
                      })
                    : c.title,
```

The surrounding `appendMessage` map should still return the same object shape and still update `messages` and `updatedAt`.

- [ ] **Step 5: Use task-aware titles when converting a pending draft to a real local conversation**

In `handleSendMessage`, update the non-silent first-message branch from the current inline `text.slice(...)` title to:

```typescript
        const newConv: Conversation = {
          ...baseConv,
          id: activeConvId,
          title: buildConversationTitle({
            text,
            attachments,
            taskContext: baseConv.taskContext,
            date: userMsg.timestamp,
          }),
          messages: [userMsg],
        };
```

Update the silent first-message branch to keep the same behavior shape while using the shared helper:

```typescript
        const createdAt = new Date();
        const newConv: Conversation = {
          ...baseConv,
          id: activeConvId,
          title: buildConversationTitle({
            text,
            attachments,
            taskContext: baseConv.taskContext,
            date: createdAt,
          }),
        };
```

- [ ] **Step 6: Stop hiding task conversations when a task entry is selected**

In `handleSelectTask`, delete this block:

```typescript
    setHiddenConversationIds((prev) =>
      prev.includes(conversation.id) ? prev : [...prev, conversation.id],
    );
```

The task selection should still create a pending conversation with `taskContext`, set it active, clear task/result state, clear `waitingForFileUpload`, and set `isLoading` to false.

- [ ] **Step 7: Hide empty pending and empty local drafts from sidebar history**

In `mergedConversations`, change the `localOnly` filter so it only includes local conversations that already have messages:

```typescript
    const localOnly = conversations.filter(
      (c) =>
        c.messages.length > 0 &&
        !serverIds.has(c.id) &&
        c.id !== loginLocalId &&
        !hiddenConversationIds.includes(c.id),
    );
```

Then remove the pending-conversation append block entirely:

```typescript
    // Remove this entire block:
    const pending = pendingNewConvRef.current;
    if (
      pending &&
      activeConvId === pending.id &&
      !hiddenConversationIds.includes(pending.id) &&
      !base.some((c) => c.id === pending.id)
    ) {
      return [pending, ...base];
    }
```

The end of `mergedConversations` should be:

```typescript
    const base = [...localOnly, ...serverFiltered.filter((c) => !hiddenConversationIds.includes(c.id))];
    return base;
```

- [ ] **Step 8: Run the integration test and verify it passes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/conversation-draft-title-ux.spec.tsx
```

Expected: PASS for both tests.

- [ ] **Step 9: Run the title unit test again**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/conversationTitles.test.ts
```

Expected: PASS.

- [ ] **Step 10: Commit the App behavior and integration tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git add finance-web/src/App.tsx finance-web/tests/components/conversation-draft-title-ux.spec.tsx
git commit -m "fix: hide empty chat drafts and title task conversations"
```

---

### Task 3: Full Frontend Verification and Service Restart

**Files:**
- No planned file changes.

- [ ] **Step 1: Run focused component tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/conversationTitles.test.ts tests/components/conversation-draft-title-ux.spec.tsx tests/components/chat-streaming-message.spec.tsx
```

Expected: PASS. This checks the new title utility, the new draft/title integration behavior, and the existing streaming-message regression around `App`.

- [ ] **Step 2: Run the frontend lint**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run lint
```

Expected: PASS. If lint reports import ordering or unused variables in the new tests/helper, fix those exact files and rerun this command before continuing.

- [ ] **Step 3: Run the production build**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run build
```

Expected: PASS. This catches TypeScript errors in `conversationTitles.ts`, `App.tsx`, and the Vite production bundle.

- [ ] **Step 4: Restart services as required for finance-web changes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: all configured services restart. After startup, finance-web should be available at `http://localhost:5173`.

- [ ] **Step 5: Commit any verification-only fixes**

If Steps 1-3 required a lint/type/test fix, commit only those changed files:

```bash
cd /Users/kevin/workspace/financial-ai
git status --short
git add finance-web/src/utils/conversationTitles.ts finance-web/src/App.tsx finance-web/tests/components/conversationTitles.test.ts finance-web/tests/components/conversation-draft-title-ux.spec.tsx
git commit -m "fix: satisfy chat draft title verification"
```

If Steps 1-3 passed without code changes, do not create an empty commit.

---

## Self-Review

- Spec coverage:
  - Empty new conversation drafts hidden from sidebar: Task 2 Steps 1, 7, 8.
  - Ordinary chat first-message titles retained: Task 1 unit tests and Task 2 Step 5.
  - Data reconciliation title `数据对账 · <规则名> · <YYYY-MM-DD>`: Task 1 unit test.
  - Data processing title `数据整理 · <规则名> · <文件数>个文件`: Task 1 unit test and Task 2 integration test.
  - No task-running card or backend changes: File Structure and Task list touch only frontend utility/tests/App.
  - Existing login/history/WebSocket behavior guarded: Task 2 uses existing `conversation_created` path unchanged; Task 3 reruns App streaming regression.
- Placeholder scan: no placeholder red flags or open-ended implementation steps remain.
- Type consistency:
  - `buildConversationTitle` accepts `MessageAttachment[]` and `UserTaskRule` fields already present in `types.ts`.
  - `App.tsx` call sites pass `msg.attachments`, first-send `attachments`, `baseConv.taskContext`, and `Date` instances.
  - Tests use the existing `SendMessageFn` argument order from `useWebSocket.ts`.
