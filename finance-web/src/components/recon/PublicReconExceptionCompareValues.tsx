import type { ExceptionBusinessDisplay } from './exceptionBusinessSummary';

const ANYWHERE_WRAP_STYLE = { overflowWrap: 'anywhere' } as const;

function compareFieldLabels(fieldLabel: string): string[] {
  const labels = fieldLabel.split(/\s+\/\s+/).map((label) => label.trim()).filter(Boolean);
  return labels.length > 0 ? labels : [fieldLabel || '--'];
}

export interface PublicReconExceptionCompareValuesProps {
  compareLines: ExceptionBusinessDisplay['compareLines'];
  leftDatasetLabel: string;
  rightDatasetLabel: string;
}

export default function PublicReconExceptionCompareValues({
  compareLines,
  leftDatasetLabel,
  rightDatasetLabel,
}: PublicReconExceptionCompareValuesProps) {
  if (compareLines.length === 0) return null;

  const firstLine = compareLines[0];

  return (
    <>
      <div className="mt-3 hidden overflow-x-auto rounded-xl border border-border-subtle bg-surface md:block">
        <table className="min-w-[720px] w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs text-text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">字段</th>
              <th className="px-3 py-2 font-medium">{firstLine?.sourceDatasetLabel || leftDatasetLabel}</th>
              <th className="px-3 py-2 font-medium">{firstLine?.targetDatasetLabel || rightDatasetLabel}</th>
              <th className="px-3 py-2 font-medium">差异值</th>
            </tr>
          </thead>
          <tbody>
            {compareLines.map((line, index) => (
              <tr key={`${line.fieldLabel}-${index}`} className="border-b border-border-subtle last:border-b-0">
                <td className="px-3 py-2 text-text-primary">{line.fieldLabel}</td>
                <td className="px-3 py-2 text-text-secondary">{line.sourceValue}</td>
                <td className="px-3 py-2 text-text-secondary">{line.targetValue}</td>
                <td className="px-3 py-2 text-text-secondary">{line.diffValue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div data-testid="mobile-compare-values" className="mt-3 grid gap-3 md:hidden">
        {compareLines.map((line, index) => (
          <article key={`${line.fieldLabel}-${index}`} className="rounded-xl border border-border-subtle bg-surface px-3 py-3">
            <p className="text-[11px] font-medium text-text-muted">字段</p>
            <div className="mt-1 flex flex-wrap gap-1.5 text-sm font-semibold text-text-primary">
              {compareFieldLabels(line.fieldLabel).map((label) => (
                <span key={label} className="rounded-lg border border-border-subtle bg-surface-secondary px-2 py-1">
                  {label}
                </span>
              ))}
            </div>
            <dl className="mt-3 grid gap-2 text-sm">
              <div>
                <dt className="text-xs text-text-muted">{line.sourceDatasetLabel || leftDatasetLabel}</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words text-text-primary" style={ANYWHERE_WRAP_STYLE}>
                  {line.sourceValue}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-text-muted">{line.targetDatasetLabel || rightDatasetLabel}</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words text-text-primary" style={ANYWHERE_WRAP_STYLE}>
                  {line.targetValue}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-text-muted">差异值</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words text-text-primary" style={ANYWHERE_WRAP_STYLE}>
                  {line.diffValue || '--'}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </>
  );
}
