export async function fetchReconAutoApi(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const candidates = [`/api/recon${normalizedPath}`, `/api/api/recon${normalizedPath}`];

  let fallbackResponse: Response | null = null;
  let lastError: Error | null = null;

  for (const candidate of candidates) {
    let response: Response;
    try {
      response = await fetch(candidate, init);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      continue;
    }
    if (response.status !== 404) {
      return response;
    }
    fallbackResponse = response;
  }

  if (lastError) {
    throw new Error(
      `请求 ${normalizedPath} 失败，请检查前端代理或 data-agent 服务是否可用后重试。原始错误：${lastError.message}`,
    );
  }

  return fallbackResponse ?? fetch(candidates[0], init);
}

export interface ReconAutoSseEvent {
  event: string;
  data: unknown;
}

function findSseBoundary(buffer: string): { index: number; length: number } | null {
  const crlfIndex = buffer.indexOf('\r\n\r\n');
  const lfIndex = buffer.indexOf('\n\n');
  if (crlfIndex === -1 && lfIndex === -1) {
    return null;
  }
  if (crlfIndex === -1) {
    return { index: lfIndex, length: 2 };
  }
  if (lfIndex === -1 || crlfIndex < lfIndex) {
    return { index: crlfIndex, length: 4 };
  }
  return { index: lfIndex, length: 2 };
}

export function parseSseChunk(chunk: string): ReconAutoSseEvent | null {
  const lines = chunk
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trimEnd())
    .filter(Boolean);
  if (lines.length === 0) {
    return null;
  }

  let event = 'message';
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim() || 'message';
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart());
    }
  }

  const rawData = dataLines.join('\n');
  if (!rawData) {
    return { event, data: null };
  }

  try {
    return {
      event,
      data: JSON.parse(rawData) as unknown,
    };
  } catch {
    return {
      event,
      data: rawData,
    };
  }
}

export async function consumeReconAutoSse(
  path: string,
  init: RequestInit | undefined,
  onEvent: (event: ReconAutoSseEvent) => void,
): Promise<Response> {
  const response = await fetchReconAutoApi(path, init);
  if (!response.ok) {
    return response;
  }

  if (!response.body) {
    throw new Error(`请求 ${path} 成功，但未返回可读取的流。`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      while (true) {
        const boundary = findSseBoundary(buffer);
        if (!boundary) {
          break;
        }
        const chunk = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary.length);
        const parsed = parseSseChunk(chunk);
        if (parsed) {
          onEvent(parsed);
        }
      }
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    throw error;
  }

  const remaining = buffer.trim();
  if (remaining) {
    const parsed = parseSseChunk(remaining);
    if (parsed) {
      onEvent(parsed);
    }
  }

  return response;
}
