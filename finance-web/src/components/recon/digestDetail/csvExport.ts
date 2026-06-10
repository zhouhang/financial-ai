type StructuredTotals = {
  totals?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function readMetric(
  row: Record<string, unknown>,
  metric: string,
  structured?: StructuredTotals,
): unknown {
  if (isRecord(structured?.totals) && metric in structured.totals) {
    return structured.totals[metric];
  }

  return row[metric];
}

export function sortRowsBySpec<T extends Record<string, unknown>>(rows: T[], sortSpec = ''): T[] {
  const [metric, direction = 'asc'] = sortSpec.trim().split(/\s+/);
  if (!metric) {
    return rows;
  }

  const factor = direction.toLowerCase() === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => {
    const left = Number(a[metric] ?? 0);
    const right = Number(b[metric] ?? 0);
    if (Number.isFinite(left) && Number.isFinite(right)) {
      return (left - right) * factor;
    }
    return String(a[metric] ?? '').localeCompare(String(b[metric] ?? '')) * factor;
  });
}

function escapeCsv(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}

export function buildCsv(rows: Array<Record<string, unknown>>, columns: string[]): string {
  const header = columns.map(escapeCsv).join(',');
  const body = rows.map((row) => columns.map((column) => escapeCsv(row[column])).join(','));

  return [header, ...body].join('\n');
}
