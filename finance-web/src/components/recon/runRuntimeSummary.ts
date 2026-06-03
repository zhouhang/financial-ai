export type ReconRuntimeSide = 'left' | 'right';

export interface RuntimeStageMetric {
  side?: ReconRuntimeSide;
  businessName: string;
  rowCount: number | null;
  durationSeconds: number | null;
}

export interface RuntimeNotificationView {
  status: string;
  label: string;
  recipientName: string;
  recipientIdentifier: string;
  messageId: string;
  error: string;
}

export interface RuntimeExceptionSamplingView {
  enabled: boolean;
  totalCount: number | null;
  sampleCount: number | null;
  sampleLimit: number | null;
  threshold: number | null;
  strategy: string;
  fallbackUsed: boolean;
}

export interface RuntimeSummaryViewModel {
  bizDate: string;
  queueJobId: string;
  queueStartedAt: string;
  queueFinishedAt: string;
  queueDurationSeconds: number | null;
  collectionMetrics: RuntimeStageMetric[];
  preparationMetrics: RuntimeStageMetric[];
  reconciliationDurationSeconds: number | null;
  notification: RuntimeNotificationView;
  exceptionSampling: RuntimeExceptionSamplingView;
}

export interface RunLikeForRuntimeSummary {
  raw?: Record<string, unknown>;
  dataDate?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function toText(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return fallback;
}

function toOptionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toOptionalInt(value: unknown): number | null {
  const parsed = toOptionalNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
}

export function formatCount(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  return value.toLocaleString('zh-CN');
}

export function formatDuration(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  if (value < 1) return `${value.toFixed(2)} 秒`;
  if (value < 60) return `${value.toFixed(2).replace(/\.?0+$/, '')} 秒`;
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return `${minutes} 分 ${seconds.toFixed(0)} 秒`;
}

export function looksLikeTechnicalName(value: string): boolean {
  const text = value.trim();
  if (!text || /[\u4e00-\u9fff]/.test(text)) return false;
  const normalized = text.toLowerCase();
  return (
    /^[a-z_][\w$]*\.[a-z_][\w$]*$/.test(normalized)
    || /^(ods|dwd|dws|dim|fact|stg|tmp|raw)_/.test(normalized)
    || /^(public|ods|dwd|dws|dim|fact|stg|tmp|raw)[._]/.test(normalized)
    || /^[a-z0-9_]+:[a-z0-9_:/.-]+$/.test(normalized)
  );
}

export function runtimeBusinessName(raw: unknown, fallback: string): string {
  const item = asRecord(raw);
  for (const key of ['business_name', 'dataset_name', 'display_name', 'name', 'dataset_code']) {
    const text = toText(item[key]).trim();
    if (text && !looksLikeTechnicalName(text)) return text;
  }
  return fallback;
}

function sideFallback(side: string): string {
  return side === 'right' ? '右侧数据源' : '左侧数据源';
}

function normalizeSide(value: unknown): ReconRuntimeSide | undefined {
  const text = toText(value).trim().toLowerCase();
  if (text === 'left' || text.startsWith('left_')) return 'left';
  if (text === 'right' || text.startsWith('right_')) return 'right';
  return undefined;
}

function normalizeStageMetric(value: unknown, index: number): RuntimeStageMetric {
  const item = asRecord(value);
  const side = normalizeSide(item.side);
  return {
    side,
    businessName: runtimeBusinessName(item, sideFallback(side || (index === 1 ? 'right' : 'left'))),
    rowCount: toOptionalInt(item.row_count ?? item.rowCount),
    durationSeconds: toOptionalNumber(item.duration_seconds ?? item.durationSeconds),
  };
}

function derivedPreparation(rawRun: Record<string, unknown>, collections: RuntimeStageMetric[]): RuntimeStageMetric[] {
  const summary = asRecord(rawRun.recon_result_summary_json);
  const matchedExact = toOptionalInt(summary.matched_exact);
  const matchedWithDiff = toOptionalInt(summary.matched_with_diff);
  const sourceOnly = toOptionalInt(summary.source_only);
  const targetOnly = toOptionalInt(summary.target_only);
  if (matchedExact === null || matchedWithDiff === null || sourceOnly === null || targetOnly === null) {
    return [];
  }
  return [
    {
      side: 'left',
      businessName: collections.find((item) => item.side === 'left')?.businessName || '左侧数据源',
      rowCount: matchedExact + matchedWithDiff + sourceOnly,
      durationSeconds: null,
    },
    {
      side: 'right',
      businessName: collections.find((item) => item.side === 'right')?.businessName || '右侧数据源',
      rowCount: matchedExact + matchedWithDiff + targetOnly,
      durationSeconds: null,
    },
  ];
}

function notificationLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'sent') return '已发送';
  if (normalized === 'failed') return '发送失败';
  if (normalized === 'skipped') return '已跳过';
  return status || '--';
}

function normalizeNotification(value: unknown): RuntimeNotificationView {
  const item = asRecord(value);
  const status = toText(item.status).trim();
  return {
    status,
    label: notificationLabel(status),
    recipientName: toText(item.recipient_name ?? item.recipientName).trim(),
    recipientIdentifier: toText(item.recipient_identifier ?? item.recipientIdentifier).trim(),
    messageId: toText(item.message_id ?? item.messageId).trim(),
    error: toText(item.error).trim(),
  };
}

function normalizeExceptionSampling(value: unknown): RuntimeExceptionSamplingView {
  const item = asRecord(value);
  return {
    enabled: item.enabled === true,
    totalCount: toOptionalInt(item.total_count ?? item.totalCount),
    sampleCount: toOptionalInt(item.sample_count ?? item.sampleCount),
    sampleLimit: toOptionalInt(item.sample_limit ?? item.sampleLimit),
    threshold: toOptionalInt(item.threshold),
    strategy: toText(item.strategy).trim(),
    fallbackUsed: item.fallback_used === true || item.fallbackUsed === true,
  };
}

export function buildRuntimeSummaryView(run: RunLikeForRuntimeSummary | null | undefined): RuntimeSummaryViewModel {
  const rawRun = asRecord(run?.raw);
  const runContext = asRecord(rawRun.run_context_json);
  const artifacts = asRecord(rawRun.artifacts_json);
  const runtimeSummary = asRecord(artifacts.runtime_summary);
  const queue = asRecord(runtimeSummary.queue);
  const collections = asList(runtimeSummary.collections).map(normalizeStageMetric);
  const preparation = asList(runtimeSummary.preparation).map(normalizeStageMetric);
  const reconciliation = asRecord(runtimeSummary.reconciliation);
  return {
    bizDate: (
      toText(runtimeSummary.biz_date).trim()
      || toText(runContext.biz_date).trim()
      || toText(rawRun.biz_date).trim()
      || toText(rawRun.business_date).trim()
      || toText(rawRun.data_date).trim()
      || run?.dataDate
      || ''
    ),
    queueJobId: toText(queue.job_id ?? queue.jobId).trim(),
    queueStartedAt: toText(queue.started_at ?? queue.startedAt).trim(),
    queueFinishedAt: toText(queue.finished_at ?? queue.finishedAt).trim(),
    queueDurationSeconds: toOptionalNumber(queue.duration_seconds ?? queue.durationSeconds),
    collectionMetrics: collections,
    preparationMetrics: preparation.length > 0 ? preparation : derivedPreparation(rawRun, collections),
    reconciliationDurationSeconds: toOptionalNumber(reconciliation.duration_seconds ?? reconciliation.durationSeconds),
    notification: normalizeNotification(runtimeSummary.summary_notification),
    exceptionSampling: normalizeExceptionSampling(runtimeSummary.exception_sampling ?? runtimeSummary.exceptionSampling),
  };
}
