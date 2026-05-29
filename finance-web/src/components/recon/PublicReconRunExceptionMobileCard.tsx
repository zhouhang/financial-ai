import { Eye } from 'lucide-react';

import type { ExceptionBusinessDisplay } from './exceptionBusinessSummary';

const ANYWHERE_WRAP_STYLE = { overflowWrap: 'anywhere' } as const;

function compareFieldLabels(fieldLabel: string): string[] {
  const labels = fieldLabel.split(/\s+\/\s+/).map((label) => label.trim()).filter(Boolean);
  return labels.length > 0 ? labels : [fieldLabel || '--'];
}

export interface PublicReconRunExceptionMobileCardProps {
  id: string;
  display: ExceptionBusinessDisplay;
  fieldSummary: string;
  ownerName: string;
  processingStatusLabel: string;
  onOpen: () => void;
}

export default function PublicReconRunExceptionMobileCard({
  id,
  display,
  fieldSummary,
  ownerName,
  processingStatusLabel,
  onOpen,
}: PublicReconRunExceptionMobileCardProps) {
  const firstCompareLine = display.compareLines[0] || null;

  return (
    <article
      data-testid={`mobile-exception-card-${id}`}
      className="border-b border-border-subtle px-4 py-4 last:border-b-0"
    >
      <div className="space-y-3">
        <p
          className="whitespace-pre-line break-words text-sm font-semibold leading-6 text-text-primary"
          style={ANYWHERE_WRAP_STYLE}
        >
          {display.shortSummary}
        </p>
        <div className="rounded-xl border border-border-subtle bg-surface-secondary px-3 py-2">
          <p className="text-[11px] font-medium text-text-muted">关键字段和值</p>
          <p
            className="mt-1 whitespace-pre-line break-words text-sm leading-6 text-text-primary"
            style={ANYWHERE_WRAP_STYLE}
          >
            {fieldSummary}
          </p>
        </div>
        {firstCompareLine ? (
          <div className="rounded-xl border border-border-subtle bg-surface-secondary px-3 py-2">
            <p className="text-[11px] font-medium text-text-muted">差异字段</p>
            <div className="mt-1 flex flex-wrap gap-1.5 text-sm font-medium text-text-primary">
              {compareFieldLabels(firstCompareLine.fieldLabel).map((label) => (
                <span key={label} className="rounded-lg border border-border-subtle bg-surface px-2 py-1">
                  {label}
                </span>
              ))}
            </div>
            <div className="mt-2 grid gap-2 text-sm text-text-secondary">
              <p className="break-words" style={ANYWHERE_WRAP_STYLE}>
                {firstCompareLine.sourceDatasetLabel}：{firstCompareLine.sourceValue}
              </p>
              <p className="break-words" style={ANYWHERE_WRAP_STYLE}>
                {firstCompareLine.targetDatasetLabel}：{firstCompareLine.targetValue}
              </p>
              {firstCompareLine.diffValue ? (
                <p className="break-words" style={ANYWHERE_WRAP_STYLE}>
                  差异值：{firstCompareLine.diffValue}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1">
            <span className="text-text-muted">责任人</span>
            <span>{ownerName}</span>
          </span>
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1">
            <span className="text-text-muted">状态</span>
            <span>{processingStatusLabel}</span>
          </span>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onOpen}
            className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border border-border bg-surface px-3 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
          >
            <Eye className="h-4 w-4" />
            查看详情
          </button>
        </div>
      </div>
    </article>
  );
}
