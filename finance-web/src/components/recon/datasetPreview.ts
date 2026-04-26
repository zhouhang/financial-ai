type PreviewRow = Record<string, unknown>;

function asRecord(value: unknown): PreviewRow {
  return typeof value === 'object' && value !== null ? (value as PreviewRow) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function nonEmptyRecord(value: unknown): PreviewRow | null {
  const record = asRecord(value);
  return Object.keys(record).length > 0 ? record : null;
}

function normalizeDetailRows(value: unknown): PreviewRow[] {
  return asList(value)
    .map((item) => {
      const record = asRecord(item);
      const payload = nonEmptyRecord(record.payload);
      const data = nonEmptyRecord(record.data);
      return payload ?? data ?? nonEmptyRecord(record);
    })
    .filter((item): item is PreviewRow => Boolean(item));
}

export function extractCollectionDetailSampleRows(data: unknown, maxRows = 5): PreviewRow[] {
  const root = asRecord(data);
  const nestedData = asRecord(root.data);
  const preview = asRecord(root.preview);
  const candidateRows = [
    root.rows,
    root.sample_rows,
    root.records,
    root.items,
    root.collection_records,
    nestedData.rows,
    nestedData.sample_rows,
    nestedData.records,
    nestedData.items,
    preview.rows,
    preview.sample_rows,
  ];

  for (const candidate of candidateRows) {
    const rows = normalizeDetailRows(candidate);
    if (rows.length > 0) return rows.slice(0, maxRows);
  }

  return [];
}
