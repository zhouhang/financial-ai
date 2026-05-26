export interface ExceptionRecordEntry {
  field: string;
  label: string;
  value: string;
}

function normalizeDisplayText(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, '');
}

function isTradeOrderDetailSection(title: string): boolean {
  return normalizeDisplayText(title).includes('交易订单明细表');
}

function tradeOrderDetailFieldRank(entry: ExceptionRecordEntry): number {
  const field = normalizeDisplayText(entry.field);
  const label = normalizeDisplayText(entry.label);
  const combined = `${field}${label}`;

  if (
    combined.includes('平台订单客户订单号')
    || combined.includes('客户订单号')
    || combined.includes('客户订单')
  ) {
    return 0;
  }
  if (combined.includes('含税销售金额')) {
    return 1;
  }
  return 2;
}

export function orderExceptionRecordEntries(
  entries: ExceptionRecordEntry[],
  sectionTitle: string,
): ExceptionRecordEntry[] {
  if (!isTradeOrderDetailSection(sectionTitle)) return entries;
  return entries
    .map((entry, index) => ({ entry, index, rank: tradeOrderDetailFieldRank(entry) }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map(({ entry }) => entry);
}
