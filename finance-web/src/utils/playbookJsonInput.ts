export interface PlaybookJsonParseResult {
  value?: unknown;
  error?: string;
  repairCount: number;
  repairedText: string;
}

const cjkPattern = /[\u3400-\u9fff\uf900-\ufaff]/;

function isCjk(char: string): boolean {
  return cjkPattern.test(char);
}

function normalizeLineBreakInString(text: string, index: number): { replacement: string; nextIndex: number } {
  const previous = text[index - 1] || '';
  let nextIndex = index + 1;
  if (text[index] === '\r' && text[nextIndex] === '\n') {
    nextIndex += 1;
  }
  while (nextIndex < text.length && (text[nextIndex] === ' ' || text[nextIndex] === '\t')) {
    nextIndex += 1;
  }
  const next = text[nextIndex] || '';
  if (isCjk(previous) && isCjk(next)) {
    return { replacement: '', nextIndex };
  }
  return { replacement: ' ', nextIndex };
}

function sanitizeJsonStringControlCharacters(text: string): { text: string; repairCount: number } {
  let repaired = '';
  let inString = false;
  let escaped = false;
  let repairCount = 0;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (!inString) {
      repaired += char;
      if (char === '"') {
        inString = true;
      }
      continue;
    }

    if (escaped) {
      repaired += char;
      escaped = false;
      continue;
    }

    if (char === '\\') {
      repaired += char;
      escaped = true;
      continue;
    }

    if (char === '"') {
      repaired += char;
      inString = false;
      continue;
    }

    if (char === '\n' || char === '\r') {
      const lineBreak = normalizeLineBreakInString(text, index);
      repaired += lineBreak.replacement;
      repairCount += 1;
      index = lineBreak.nextIndex - 1;
      continue;
    }

    if (char === '\t' || char.charCodeAt(0) < 0x20) {
      repaired += ' ';
      repairCount += 1;
      continue;
    }

    repaired += char;
  }

  return { text: repaired, repairCount };
}

function lineColumnFromPosition(text: string, position: number): { line: number; column: number } {
  const prefix = text.slice(0, Math.max(0, position));
  const lines = prefix.split('\n');
  return {
    line: lines.length,
    column: lines[lines.length - 1].length + 1,
  };
}

function guessLineColumn(text: string, message: string): { line: number; column: number } | null {
  const positionMatch = message.match(/position\s+(\d+)/i);
  if (positionMatch) {
    return lineColumnFromPosition(text, Number(positionMatch[1]));
  }

  const tokenMatch = message.match(/Unexpected token\s+'([^']+)'/i);
  if (tokenMatch) {
    const token = tokenMatch[1];
    const lines = text.split('\n');
    for (let index = 0; index < lines.length; index += 1) {
      const column = lines[index].indexOf(token);
      if (column >= 0) {
        return { line: index + 1, column: column + 1 };
      }
    }
  }
  return null;
}

function formatJsonParseError(error: unknown, text: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const match = message.match(/line\s+(\d+)\s+column\s+(\d+)/i);
  const location = match
    ? { line: Number(match[1]), column: Number(match[2]) }
    : guessLineColumn(text, message);
  if (!location) return message;
  return `${message}（第 ${location.line} 行，第 ${location.column} 列）`;
}

export function parsePlaybookJsonInput(text: string): PlaybookJsonParseResult {
  const source = text || '{}';
  try {
    return {
      value: JSON.parse(source) as unknown,
      repairCount: 0,
      repairedText: source,
    };
  } catch (strictError) {
    const sanitized = sanitizeJsonStringControlCharacters(source);
    if (sanitized.repairCount <= 0 || sanitized.text === source) {
      return {
        error: formatJsonParseError(strictError, source),
        repairCount: 0,
        repairedText: source,
      };
    }

    try {
      return {
        value: JSON.parse(sanitized.text) as unknown,
        repairCount: sanitized.repairCount,
        repairedText: sanitized.text,
      };
    } catch (repairedError) {
      return {
        error: formatJsonParseError(repairedError, sanitized.text),
        repairCount: sanitized.repairCount,
        repairedText: sanitized.text,
      };
    }
  }
}
