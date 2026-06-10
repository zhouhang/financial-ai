const RATE_METRIC_PATTERN = /rate|ratio|pct|percent/i;
const AMOUNT_METRIC_PATTERN = /amount|total|receivable|settled|deduction|refund|profit|cost/i;

export function isRateMetric(metric: string): boolean {
  return RATE_METRIC_PATTERN.test(metric);
}

export function isAmountMetric(metric: string): boolean {
  return AMOUNT_METRIC_PATTERN.test(metric);
}

export function formatMetricValue(metric: string, value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '--';
  }

  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }

  if (isRateMetric(metric)) {
    return `${(numeric * 100).toFixed(2)}%`;
  }

  if (isAmountMetric(metric)) {
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: 'CNY',
      minimumFractionDigits: 2,
    }).format(numeric);
  }

  return new Intl.NumberFormat('zh-CN').format(numeric);
}
