import { cn } from './types';
import {
  EXCEPTION_SUMMARY_SECTION_LABELS,
  formatExceptionSummaryLines,
} from './exceptionSummaryDisplay';

interface ExceptionSummaryProps {
  text: string;
  className?: string;
  valueClassName?: string;
}

const LABEL_PATTERN = new RegExp(`(${EXCEPTION_SUMMARY_SECTION_LABELS.join('|')})[:：]`, 'g');
const SUMMARY_TEST_ID = 'exception-summary';
const SUMMARY_ROW_TEST_ID_PREFIX = 'exception-summary-row';

const SECTION_LABEL_CLASSES: Record<string, string> = {
  差异类型: 'border-amber-200 bg-amber-50 text-amber-700',
  匹配字段: 'border-sky-200 bg-sky-50 text-sky-700',
  对比字段: 'border-rose-200 bg-rose-50 text-rose-700',
};

type Segment =
  | { kind: 'kv'; label: string; value: string }
  | { kind: 'text'; content: string };

function parseLineSegments(line: string): Segment[] {
  const matches = Array.from(line.matchAll(LABEL_PATTERN));
  if (matches.length === 0) {
    const trimmed = line.trim();
    return trimmed ? [{ kind: 'text', content: trimmed }] : [];
  }
  const out: Segment[] = [];
  let cursor = 0;
  matches.forEach((match, index) => {
    const start = match.index ?? 0;
    if (start > cursor) {
      const free = line.slice(cursor, start).trim();
      if (free) out.push({ kind: 'text', content: free });
    }
    const label = match[1];
    const valueStart = start + match[0].length;
    const valueEnd = index + 1 < matches.length ? (matches[index + 1].index ?? line.length) : line.length;
    const value = line.slice(valueStart, valueEnd).trim();
    out.push({ kind: 'kv', label, value });
    cursor = valueEnd;
  });
  if (cursor < line.length) {
    const tail = line.slice(cursor).trim();
    if (tail) out.push({ kind: 'text', content: tail });
  }
  return out;
}

export default function ExceptionSummary({
  text,
  className = '',
  valueClassName = '',
}: ExceptionSummaryProps) {
  const lines = formatExceptionSummaryLines(text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const segments = lines.flatMap(parseLineSegments);
  return (
    <div
      className={cn('space-y-1.5', className)}
      data-testid={SUMMARY_TEST_ID}
      style={{ overflowWrap: 'anywhere' }}
    >
      {segments.map((segment, index) => {
        if (segment.kind === 'kv') {
          const labelClassName = SECTION_LABEL_CLASSES[segment.label] || 'border-border bg-surface-secondary text-text-secondary';
          return (
            <div
              key={index}
              className="grid grid-cols-[5rem_minmax(0,1fr)] items-start gap-x-3 leading-6"
              data-testid={`${SUMMARY_ROW_TEST_ID_PREFIX}-${segment.label}`}
            >
              <span
                className={cn(
                  'inline-flex w-fit rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4',
                  labelClassName,
                )}
              >
                {segment.label}
              </span>
              <span className={cn('break-words', valueClassName)}>{segment.value || '--'}</span>
            </div>
          );
        }
        return (
          <p
            key={index}
            className={cn('break-words leading-6', valueClassName)}
            data-testid="exception-summary-text"
          >
            {segment.content}
          </p>
        );
      })}
    </div>
  );
}
