import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ChatArea from '../../src/components/ChatArea';
import type { MessageAttachment, UploadedFile } from '../../src/types';

function mockJsonResponse(payload: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

function renderChatArea(options?: {
  onSendMessage?: (text: string, attachments?: MessageAttachment[], silent?: boolean) => void;
  onFileUploaded?: (file: UploadedFile) => void;
}) {
  return render(
    <ChatArea
      messages={[]}
      isLoading={false}
      connectionStatus="connected"
      onSendMessage={options?.onSendMessage ?? vi.fn()}
      onFileUploaded={options?.onFileUploaded ?? vi.fn()}
      threadId="thread-1"
      authToken="token-1"
      currentUser={{ id: 'user-1' }}
    />,
  );
}

function stageFile(container: HTMLElement, file: File) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;
  expect(input).toBeTruthy();
  fireEvent.change(input as HTMLInputElement, {
    target: {
      files: [file],
    },
  });
}

function sendStagedFiles(container: HTMLElement) {
  const sendButton = container.querySelector('button.sidebar-primary-cta') as HTMLButtonElement | null;
  expect(sendButton).toBeTruthy();
  fireEvent.click(sendButton as HTMLButtonElement);
}

describe('ChatArea direct OSS upload', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('uploads staged files through presign, OSS PUT, and confirm before sending attachments', async () => {
    const file = new File(['direct upload bytes'], 'direct.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const onSendMessage = vi.fn();
    const onFileUploaded = vi.fn();

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });

        if (url === '/api/upload/presign') {
          return mockJsonResponse({
            success: true,
            direct_upload: true,
            url: 'https://oss.example.com/upload/direct.xlsx',
            key: 'uploads/thread-1/direct.xlsx',
            headers: {
              'Content-Type': file.type,
              'x-oss-meta-source': 'chat',
            },
          });
        }

        if (url === 'https://oss.example.com/upload/direct.xlsx') {
          return mockJsonResponse({ success: true });
        }

        if (url === '/api/upload/confirm') {
          return mockJsonResponse({
            success: true,
            filename: 'confirmed-direct.xlsx',
            size: file.size,
            file_path: 'oss://bucket/uploads/thread-1/direct.xlsx',
          });
        }

        throw new Error(`Unexpected request: ${url}`);
      }),
    );

    const { container } = renderChatArea({ onSendMessage, onFileUploaded });

    stageFile(container, file);
    expect(screen.getByText('direct.xlsx')).toBeInTheDocument();

    sendStagedFiles(container);

    await waitFor(() => {
      expect(onSendMessage).toHaveBeenCalledTimes(1);
    });

    expect(requests.map((request) => request.url)).toEqual([
      '/api/upload/presign',
      'https://oss.example.com/upload/direct.xlsx',
      '/api/upload/confirm',
    ]);

    const presignRequest = requests[0];
    expect(presignRequest.init?.method).toBe('POST');
    expect(presignRequest.init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer token-1',
    });
    expect(JSON.parse(String(presignRequest.init?.body))).toEqual({
      filename: 'direct.xlsx',
      size: file.size,
      content_type: file.type,
    });

    const putRequest = requests[1];
    expect(putRequest.init?.method).toBe('PUT');
    expect(putRequest.init?.headers).toEqual({
      'Content-Type': file.type,
      'x-oss-meta-source': 'chat',
    });
    expect(putRequest.init?.body).toBe(file);

    const confirmRequest = requests[2];
    expect(confirmRequest.init?.method).toBe('POST');
    expect(confirmRequest.init?.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer token-1',
    });
    expect(JSON.parse(String(confirmRequest.init?.body))).toEqual({
      storage_key: 'uploads/thread-1/direct.xlsx',
      filename: 'direct.xlsx',
      size: file.size,
      content_type: file.type,
      thread_id: 'thread-1',
    });

    expect(onSendMessage).toHaveBeenCalledWith('已上传 1 个文件，请按当前规则处理。', [
      {
        name: 'confirmed-direct.xlsx',
        size: file.size,
        path: 'oss://bucket/uploads/thread-1/direct.xlsx',
      },
    ]);
    expect(onFileUploaded).toHaveBeenCalledWith({
      name: 'confirmed-direct.xlsx',
      path: 'oss://bucket/uploads/thread-1/direct.xlsx',
      size: file.size,
      uploadedAt: expect.any(Date),
    });
  });

  it('falls back to the legacy upload endpoint when presign disables direct upload', async () => {
    const file = new File(['legacy upload bytes'], 'legacy.csv', { type: 'text/csv' });
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const onSendMessage = vi.fn();
    const onFileUploaded = vi.fn();

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, init });

        if (url === '/api/upload/presign') {
          return mockJsonResponse({
            success: true,
            direct_upload: false,
          });
        }

        if (url === '/api/upload') {
          return mockJsonResponse({
            filename: 'legacy-uploaded.csv',
            size: file.size,
            file_path: '/uploads/legacy-uploaded.csv',
          });
        }

        throw new Error(`Unexpected request: ${url}`);
      }),
    );

    const { container } = renderChatArea({ onSendMessage, onFileUploaded });

    stageFile(container, file);
    sendStagedFiles(container);

    await waitFor(() => {
      expect(onSendMessage).toHaveBeenCalledTimes(1);
    });

    expect(requests.map((request) => request.url)).toEqual([
      '/api/upload/presign',
      '/api/upload',
    ]);

    const legacyRequest = requests[1];
    expect(legacyRequest.init?.method).toBe('POST');
    expect(legacyRequest.init?.body).toBeInstanceOf(FormData);
    const legacyBody = legacyRequest.init?.body as FormData;
    expect(legacyBody.get('file')).toBe(file);
    expect(legacyBody.get('thread_id')).toBe('thread-1');
    expect(legacyBody.get('is_first_file')).toBe('1');
    expect(legacyBody.get('auth_token')).toBe('token-1');

    expect(onSendMessage).toHaveBeenCalledWith('已上传 1 个文件，请按当前规则处理。', [
      {
        name: 'legacy-uploaded.csv',
        size: file.size,
        path: '/uploads/legacy-uploaded.csv',
      },
    ]);
    expect(onFileUploaded).toHaveBeenCalledWith({
      name: 'legacy-uploaded.csv',
      path: '/uploads/legacy-uploaded.csv',
      size: file.size,
      uploadedAt: expect.any(Date),
    });
  });
});
