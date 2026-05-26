import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, ChevronDown, ChevronLeft, ChevronRight, Eye, Filter, RefreshCw, X } from 'lucide-react';
import { fetchReconAutoApi } from './recon/autoApi';
import { cn } from './recon/types';
import { parsePublicReconRunExceptionsRunId } from './publicReconRunExceptionsRoute';
import {
  buildRuntimeSummaryView,
  formatCount,
  formatDuration,
  looksLikeTechnicalName,
  runtimeBusinessName,
} from './recon/runRuntimeSummary';

interface ReconCenterRunItem {
  id: string;
  runCode: string;
  schemeCode: string;
  planCode: string;
  schemeName: string;
  planName: string;
  executionStatus: string;
  triggerType: string;
  entryMode: string;
  anomalyCount: number;
  failedStage: string;
  failedReason: string;
  startedAt: string;
  finishedAt: string;
  raw: Record<string, unknown>;
}

interface ReconSchemeListItem {
  id: string;
  schemeCode: string;
  name: string;
  description: string;
  raw: Record<string, unknown>;
}

interface ReconTaskListItem {
  id: string;
  planCode: string;
  name: string;
  schemeCode: string;
  raw: Record<string, unknown>;
}

interface ReconRunExceptionDetail {
  id: string;
  anomalyType: string;
  summary: string;
  ownerName: string;
  ownerIdentifier: string;
  reminderStatus: string;
  processingStatus: string;
  fixStatus: string;
  latestFeedback: string;
  isClosed: boolean;
  createdAt: string;
  updatedAt: string;
  raw: Record<string, unknown>;
}

interface PublicExceptionBundle {
  run: ReconCenterRunItem | null;
  scheme: ReconSchemeListItem | null;
  task: ReconTaskListItem | null;
  exceptions: ReconRunExceptionDetail[];
  total: number;
  limit: number;
  offset: number;
}

type ReconSide = 'left' | 'right';

interface SchemeSourceSummary {
  id: string;
  name: string;
  aliases: string[];
  fieldLabelMap: Record<string, string>;
}

interface FieldDisplayInfo {
  label: string;
  sourceField: string;
  transformLabel: string;
}

interface ExceptionDisplayContext {
  datasetLabels: Record<ReconSide, string>;
  sourceNameAliases: Record<string, string>;
  outputFieldLabels: Record<ReconSide, Record<string, string>>;
  fieldInfo: Record<ReconSide, Record<string, FieldDisplayInfo>>;
  sourceFieldLabels: Record<ReconSide, Record<string, string>>;
}

interface FieldValueLine {
  side: ReconSide;
  datasetLabel: string;
  fieldLabel: string;
  value: string;
}

interface CompareValueLine {
  fieldLabel: string;
  sourceValue: string;
  targetValue: string;
  diffValue: string;
}

const PAGE_SIZE = 100;
const ANYWHERE_WRAP_STYLE = { overflowWrap: 'anywhere' } as const;

const COMMON_FIELD_LABELS: Record<string, string> = {
  biz_key: '业务单号',
  biz_date: '业务日期',
  amount: '金额',
  fee: '手续费',
  refund_amount: '退款金额',
  order_no: '订单号',
  trade_no: '交易号',
  trans_no: '交易流水号',
  merchant_order_no: '商户订单号',
  source_name: '来源名称',
};

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

function toInt(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toBool(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  return fallback;
}

function firstNonEmptyRecord(...values: unknown[]): Record<string, unknown> {
  for (const value of values) {
    if (typeof value === 'object' && value !== null && Object.keys(value).length > 0) {
      return value as Record<string, unknown>;
    }
  }
  return {};
}

function normalizeFieldLabelMap(value: unknown): Record<string, string> {
  return Object.fromEntries(
    Object.entries(asRecord(value))
      .map(([key, raw]) => [key.trim(), toText(raw).trim()] as const)
      .filter(([key, label]) => Boolean(key && label)),
  );
}

function normalizeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const text = toText(value).trim();
    if (text) return text;
  }
  return '';
}

function formatDateTime(value: string): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatExecutionStatus(status: string): { label: string; className: string } {
  const normalized = status.trim().toLowerCase();
  if (['success', 'succeeded', 'completed'].includes(normalized)) {
    return { label: '成功', className: 'border-emerald-200 bg-emerald-50 text-emerald-700' };
  }
  if (normalized === 'running') {
    return { label: '运行中', className: 'border-sky-200 bg-sky-50 text-sky-700' };
  }
  if (['failed', 'error'].includes(normalized)) {
    return { label: '失败', className: 'border-red-200 bg-red-50 text-red-700' };
  }
  return { label: status || '未知', className: 'border-border bg-surface-secondary text-text-secondary' };
}

function formatProcessingStatus(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'pending') return '待处理';
  if (normalized === 'owner_done') return '责任人已处理';
  if (normalized === 'in_progress' || normalized === 'processing') return '处理中';
  if (normalized === 'verifying') return '复核中';
  if (normalized === 'verified') return '已复核';
  if (normalized === 'verified_closed') return '复核关闭';
  if (normalized === 'closed') return '已关闭';
  if (normalized === 'reopened') return '重新打开';
  return value || '--';
}

function stripFieldPrefix(field: string): string {
  const normalized = field.trim();
  const prefixes = ['left_recon_ready.', 'right_recon_ready.', 'source.', 'target.', 'left.', 'right.'];
  const matchedPrefix = prefixes.find((prefix) => normalized.startsWith(prefix));
  return matchedPrefix ? normalized.slice(matchedPrefix.length) : normalized;
}

function mapRun(item: unknown): ReconCenterRunItem | null {
  const raw = asRecord(item);
  if (Object.keys(raw).length === 0) return null;
  const runContext = asRecord(raw.run_context_json);
  return {
    id: toText(raw.id),
    runCode: toText(raw.run_code),
    schemeCode: toText(raw.scheme_code),
    planCode: toText(raw.plan_code),
    schemeName: toText(raw.scheme_name || raw.scheme_code, '--'),
    planName: toText(raw.plan_name || raw.plan_code, '--'),
    executionStatus: toText(raw.execution_status),
    triggerType: toText(runContext.trigger_type, toText(raw.trigger_type)),
    entryMode: toText(raw.entry_mode),
    anomalyCount: toInt(raw.anomaly_count, 0),
    failedStage: toText(raw.failed_stage),
    failedReason: toText(raw.failed_reason),
    startedAt: toText(raw.started_at),
    finishedAt: toText(raw.finished_at),
    raw,
  };
}

function mapScheme(item: unknown): ReconSchemeListItem | null {
  const raw = asRecord(item);
  if (Object.keys(raw).length === 0) return null;
  return {
    id: toText(raw.id),
    schemeCode: toText(raw.scheme_code),
    name: toText(raw.scheme_name || raw.name, '未命名方案'),
    description: toText(raw.description),
    raw,
  };
}

function mapTask(item: unknown): ReconTaskListItem | null {
  const raw = asRecord(item);
  if (Object.keys(raw).length === 0) return null;
  return {
    id: toText(raw.id),
    planCode: toText(raw.plan_code),
    name: toText(raw.plan_name || raw.name, '未命名任务'),
    schemeCode: toText(raw.scheme_code),
    raw,
  };
}

function mapException(item: unknown): ReconRunExceptionDetail {
  const raw = asRecord(item);
  const ownerContact = asRecord(raw.owner_contact_json);
  const displayOwner = (
    toText(raw.owner_name).trim()
    || toText(ownerContact.display_name).trim()
    || toText(ownerContact.name).trim()
    || toText(raw.owner_identifier).trim()
    || '--'
  );
  return {
    id: toText(raw.id),
    anomalyType: toText(raw.anomaly_type),
    summary: toText(raw.summary),
    ownerName: displayOwner,
    ownerIdentifier: toText(raw.owner_identifier),
    reminderStatus: toText(raw.reminder_status, '--'),
    processingStatus: toText(raw.processing_status, '--'),
    fixStatus: toText(raw.fix_status, '--'),
    latestFeedback: toText(raw.latest_feedback),
    isClosed: toBool(raw.is_closed, false),
    createdAt: toText(raw.created_at),
    updatedAt: toText(raw.updated_at),
    raw,
  };
}

function mapBundle(rawBundle: unknown): PublicExceptionBundle {
  const raw = asRecord(rawBundle);
  return {
    run: mapRun(raw.run),
    scheme: mapScheme(raw.scheme),
    task: mapTask(raw.run_plan || raw.task || raw.plan),
    exceptions: asList(raw.exceptions).map(mapException),
    total: toInt(raw.total, 0),
    limit: toInt(raw.limit, PAGE_SIZE),
    offset: toInt(raw.offset, 0),
  };
}

function sourceNameAliases(rawSource: unknown, displayName: string): string[] {
  const source = asRecord(rawSource);
  const metadata = asRecord(source.dataset_metadata);
  return Array.from(new Set([
    toText(source.dataset_name).trim(),
    toText(source.technical_name).trim(),
    toText(source.table_name).trim(),
    toText(source.resource_key).trim(),
    toText(source.dataset_code).trim(),
    toText(source.name).trim(),
    toText(source.id).trim(),
    toText(source.dataset_id).trim(),
    toText(source.data_source_id).trim(),
    toText(metadata.external_shop_id).trim(),
    toText(metadata.shop_connection_id).trim(),
  ].filter((value) => value && value !== displayName && looksLikeTechnicalName(value))));
}

function normalizeSources(value: unknown): SchemeSourceSummary[] {
  return asList(value)
    .map((item) => {
      const record = asRecord(item);
      const semanticProfile = asRecord(record.semantic_profile);
      const id = toText(record.dataset_id, toText(record.id)).trim();
      const name = runtimeBusinessName(
        {
          ...record,
          business_name: record.business_name || semanticProfile.business_name,
          display_name: record.display_name || semanticProfile.display_name,
        },
        firstText(record.resource_key, record.table_name) || '数据集',
      );
      return {
        id,
        name,
        aliases: sourceNameAliases(record, name),
        fieldLabelMap: {
          ...normalizeFieldLabelMap(semanticProfile.field_label_map),
          ...normalizeFieldLabelMap(record.field_label_map),
        },
      };
    })
    .filter((item) => item.id || item.name);
}

function extractSchemeMeta(scheme: ReconSchemeListItem | null): Record<string, unknown> {
  if (!scheme) return {};
  return firstNonEmptyRecord(scheme.raw.scheme_meta_json, scheme.raw.scheme_meta, scheme.raw.meta);
}

function extractSourcesBySide(schemeMeta: Record<string, unknown>): Record<ReconSide, SchemeSourceSummary[]> {
  const datasetBindings = asRecord(schemeMeta.dataset_bindings);
  const leftBindingRows = asList(datasetBindings.left);
  const rightBindingRows = asList(datasetBindings.right);
  return {
    left: normalizeSources(leftBindingRows.length > 0 ? leftBindingRows : schemeMeta.left_sources),
    right: normalizeSources(rightBindingRows.length > 0 ? rightBindingRows : schemeMeta.right_sources),
  };
}

function datasetLabelForSide(side: ReconSide, sources: SchemeSourceSummary[]): string {
  if (sources.length === 0) return side === 'left' ? '数据集 A' : '数据集 B';
  if (sources.length === 1) return sources[0].name;
  return sources.map((source) => source.name).join('、');
}

function sourceFieldLabel(sources: SchemeSourceSummary[], field: string): string {
  const normalized = stripFieldPrefix(field);
  for (const source of sources) {
    const label = source.fieldLabelMap[normalized];
    if (label) return label;
  }
  return COMMON_FIELD_LABELS[normalized] || normalized;
}

function mergeSourceFieldLabels(sources: SchemeSourceSummary[]): Record<string, string> {
  return sources.reduce<Record<string, string>>((acc, source) => {
    Object.entries(source.fieldLabelMap).forEach(([key, value]) => {
      if (key && value && !acc[key]) {
        acc[key] = value;
      }
    });
    return acc;
  }, {});
}

function mergeSourceNameAliases(sourcesBySide: Record<ReconSide, SchemeSourceSummary[]>): Record<string, string> {
  return (['left', 'right'] as ReconSide[]).reduce<Record<string, string>>((acc, side) => {
    sourcesBySide[side].forEach((source) => {
      source.aliases.forEach((alias) => {
        if (alias && source.name && !acc[alias]) {
          acc[alias] = source.name;
        }
      });
    });
    return acc;
  }, {});
}

function expressionSourceField(valueSpec: Record<string, unknown>): string {
  const valueType = toText(valueSpec.type).trim();
  if (valueType === 'source') {
    return toText(asRecord(valueSpec.source).field, toText(valueSpec.field)).trim();
  }
  if (valueType === 'function') {
    return expressionSourceField(asRecord(asRecord(valueSpec.args).value));
  }
  return '';
}

function expressionTransformLabel(valueSpec: Record<string, unknown>): string {
  const valueType = toText(valueSpec.type).trim();
  if (valueType !== 'function') return '';
  const functionName = toText(valueSpec.function || valueSpec.name).trim();
  const args = asRecord(valueSpec.args);
  if (functionName === 'strip_prefix') {
    const prefix = toText(asRecord(args.prefix).value).trim();
    return prefix ? `去除 ${prefix} 后` : '去除前缀后';
  }
  if (functionName === 'to_decimal') return '转数值后';
  if (functionName === 'strip_whitespace') return '去除空白后';
  return functionName ? `${functionName} 后` : '';
}

function buildOutputFieldLabels(
  side: ReconSide,
  schemeMeta: Record<string, unknown>,
  sources: SchemeSourceSummary[],
): {
  labels: Record<string, string>;
  fieldInfo: Record<string, FieldDisplayInfo>;
} {
  const targetTable = side === 'left' ? 'left_recon_ready' : 'right_recon_ready';
  const explicitMap = {
    ...normalizeFieldLabelMap(
      side === 'left' ? schemeMeta.left_output_field_label_map : schemeMeta.right_output_field_label_map,
    ),
    ...normalizeFieldLabelMap(
      side === 'left' ? schemeMeta.leftOutputFieldLabelMap : schemeMeta.rightOutputFieldLabelMap,
    ),
  };
  const labels: Record<string, string> = {};
  const fieldInfo: Record<string, FieldDisplayInfo> = {};
  const procRuleJson = asRecord(schemeMeta.proc_rule_json);

  asList(procRuleJson.steps).forEach((item) => {
    const step = asRecord(item);
    if (toText(step.target_table).trim() !== targetTable) return;

    asList(asRecord(step.schema).columns).forEach((columnItem) => {
      const column = asRecord(columnItem);
      const name = toText(column.name, toText(column.column_name)).trim();
      const label = toText(column.label, toText(column.display_name)).trim();
      if (name && label) {
        labels[name] = label;
        fieldInfo[name] = { label, sourceField: '', transformLabel: '' };
      }
    });

    asList(step.mappings).forEach((mappingItem) => {
      const mapping = asRecord(mappingItem);
      const targetField = toText(mapping.target_field).trim();
      if (!targetField) return;
      const valueSpec = asRecord(mapping.value);
      const sourceField = expressionSourceField(valueSpec);
      const transformLabel = expressionTransformLabel(valueSpec);
      const sourceLabel = sourceField ? sourceFieldLabel(sources, sourceField) : '';
      const explicitLabel = explicitMap[targetField] || '';
      const label = transformLabel && sourceLabel
        ? `${sourceLabel}（${transformLabel}）`
        : explicitLabel || sourceLabel || labels[targetField] || COMMON_FIELD_LABELS[targetField] || targetField;
      labels[targetField] = label;
      fieldInfo[targetField] = { label, sourceField, transformLabel };
    });
  });

  Object.entries(explicitMap).forEach(([key, value]) => {
    if (!key || !value || labels[key]) return;
    labels[key] = value;
    fieldInfo[key] = { label: value, sourceField: '', transformLabel: '' };
  });

  return { labels, fieldInfo };
}

function buildDisplayContext(scheme: ReconSchemeListItem | null): ExceptionDisplayContext {
  const schemeMeta = extractSchemeMeta(scheme);
  const sourcesBySide = extractSourcesBySide(schemeMeta);
  const leftOutput = buildOutputFieldLabels('left', schemeMeta, sourcesBySide.left);
  const rightOutput = buildOutputFieldLabels('right', schemeMeta, sourcesBySide.right);
  return {
    datasetLabels: {
      left: datasetLabelForSide('left', sourcesBySide.left),
      right: datasetLabelForSide('right', sourcesBySide.right),
    },
    sourceNameAliases: mergeSourceNameAliases(sourcesBySide),
    outputFieldLabels: {
      left: leftOutput.labels,
      right: rightOutput.labels,
    },
    fieldInfo: {
      left: leftOutput.fieldInfo,
      right: rightOutput.fieldInfo,
    },
    sourceFieldLabels: {
      left: mergeSourceFieldLabels(sourcesBySide.left),
      right: mergeSourceFieldLabels(sourcesBySide.right),
    },
  };
}

function fieldLabelForSide(ctx: ExceptionDisplayContext, side: ReconSide, field: string): string {
  const normalized = stripFieldPrefix(field);
  return (
    ctx.fieldInfo[side][normalized]?.label
    || ctx.outputFieldLabels[side][normalized]
    || COMMON_FIELD_LABELS[normalized]
    || normalized
    || '--'
  );
}

function fieldDisplayInfoForSide(
  ctx: ExceptionDisplayContext,
  side: ReconSide,
  field: string,
): FieldDisplayInfo {
  const normalized = stripFieldPrefix(field);
  const label = fieldLabelForSide(ctx, side, normalized);
  return ctx.fieldInfo[side][normalized] || { label, sourceField: '', transformLabel: '' };
}

function sourceFieldLabelForSide(ctx: ExceptionDisplayContext, side: ReconSide, field: string): string {
  const normalized = stripFieldPrefix(field);
  return ctx.sourceFieldLabels[side][normalized] || COMMON_FIELD_LABELS[normalized] || normalized;
}

function isGenericReconField(label: string): boolean {
  return ['匹配字段', '对比字段', 'match_key', 'compare_field'].includes(label.trim());
}

function displayFieldLabelForSide(ctx: ExceptionDisplayContext, side: ReconSide, field: string): string {
  const info = fieldDisplayInfoForSide(ctx, side, field);
  if (info.sourceField) {
    const sourceLabel = sourceFieldLabelForSide(ctx, side, info.sourceField);
    if (info.transformLabel) return `${sourceLabel}（${info.transformLabel}）`;
    if (isGenericReconField(info.label)) return sourceLabel;
  }
  return info.label;
}

function anomalyTypeLabel(item: ReconRunExceptionDetail, ctx: ExceptionDisplayContext): string {
  const left = ctx.datasetLabels.left;
  const right = ctx.datasetLabels.right;
  const type = item.anomalyType.trim().toLowerCase();
  if (type === 'source_only') return `仅 ${left} 存在`;
  if (type === 'target_only') return `仅 ${right} 存在`;
  if (type === 'matched_with_diff' || type === 'value_mismatch') return `${left} 与 ${right} 存在差异`;
  return item.anomalyType || '未知异常';
}

function replaceOutputFieldLabels(text: string, ctx: ExceptionDisplayContext): string {
  let value = text;
  const replacements = new Map<string, string>();
  (['left', 'right'] as ReconSide[]).forEach((side) => {
    Object.keys(ctx.outputFieldLabels[side]).forEach((field) => {
      const label = displayFieldLabelForSide(ctx, side, field);
      if (field && label && field !== label) {
        replacements.set(field, label);
      }
    });
  });
  Array.from(replacements.entries())
    .sort((a, b) => b[0].length - a[0].length)
    .forEach(([field, label]) => {
      value = value.replaceAll(field, label);
    });
  return value;
}

function replaceSourceNameLabels(text: string, ctx: ExceptionDisplayContext): string {
  let value = text;
  Object.entries(ctx.sourceNameAliases)
    .sort((a, b) => b[0].length - a[0].length)
    .forEach(([alias, label]) => {
      if (alias && label) {
        value = value.replaceAll(alias, label);
      }
    });
  return value;
}

function formatSummaryLines(text: string): string {
  return text
    .replace(/[；;]\s*/g, '\n')
    .replace(/\s{2,}/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join('\n');
}

function readableExceptionSummary(item: ReconRunExceptionDetail, ctx: ExceptionDisplayContext): string {
  return formatSummaryLines(replaceSourceNameLabels(replaceOutputFieldLabels(item.summary || '异常详情待补充。', ctx), ctx)
    .replaceAll('左侧基础表', ctx.datasetLabels.left)
    .replaceAll('右侧基础表', ctx.datasetLabels.right)
    .replaceAll('左侧数据', ctx.datasetLabels.left)
    .replaceAll('右侧数据', ctx.datasetLabels.right)
    .replaceAll('左侧', ctx.datasetLabels.left)
    .replaceAll('右侧', ctx.datasetLabels.right));
}

function getExceptionDetail(item: ReconRunExceptionDetail): Record<string, unknown> {
  return firstNonEmptyRecord(item.raw.detail_json, item.raw.detail, item.raw);
}

function getRawRecord(item: ReconRunExceptionDetail): Record<string, unknown> {
  const detail = getExceptionDetail(item);
  return firstNonEmptyRecord(detail.raw_record, detail.record, detail.source_record, detail.left_record);
}

function getRecordsBySide(item: ReconRunExceptionDetail): Record<ReconSide, Record<string, unknown>> {
  const detail = getExceptionDetail(item);
  const explicitLeft = firstNonEmptyRecord(detail.left_record, detail.source_record, detail.left_row);
  const explicitRight = firstNonEmptyRecord(detail.right_record, detail.target_record, detail.right_row);
  const rawRecord = firstNonEmptyRecord(detail.raw_record, detail.record);

  const normalizeRecord = (record: Record<string, unknown>) =>
    Object.fromEntries(Object.entries(record).map(([key, value]) => [stripFieldPrefix(key), value]));

  if (Object.keys(explicitLeft).length > 0 || Object.keys(explicitRight).length > 0) {
    return {
      left: normalizeRecord(explicitLeft),
      right: normalizeRecord(explicitRight),
    };
  }

  const left: Record<string, unknown> = {};
  const right: Record<string, unknown> = {};
  Object.entries(rawRecord).forEach(([key, value]) => {
    if (key.startsWith('left_recon_ready.') || key.startsWith('source.') || key.startsWith('left.')) {
      left[stripFieldPrefix(key)] = value;
      return;
    }
    if (key.startsWith('right_recon_ready.') || key.startsWith('target.') || key.startsWith('right.')) {
      right[stripFieldPrefix(key)] = value;
    }
  });
  return { left, right };
}

function sideFromRef(value: unknown): ReconSide | '' {
  const normalized = toText(value).trim().toLowerCase();
  if (normalized.includes('left') || normalized.includes('source')) return 'left';
  if (normalized.includes('right') || normalized.includes('target')) return 'right';
  return '';
}

function findRawValue(item: ReconRunExceptionDetail, side: ReconSide, field: string): unknown {
  const rawRecord = getRawRecord(item);
  const normalized = stripFieldPrefix(field);
  const prefixes = side === 'left'
    ? ['left_recon_ready.', 'source.', 'left.']
    : ['right_recon_ready.', 'target.', 'right.'];
  for (const prefix of prefixes) {
    const value = rawRecord[`${prefix}${normalized}`];
    if (value !== null && value !== undefined && value !== '') return value;
  }
  const records = getRecordsBySide(item);
  const sideRecordValue = records[side][normalized];
  if (sideRecordValue !== null && sideRecordValue !== undefined && sideRecordValue !== '') {
    return sideRecordValue;
  }
  return rawRecord[normalized];
}

function getJoinKeyLines(item: ReconRunExceptionDetail, ctx: ExceptionDisplayContext): FieldValueLine[] {
  const detail = getExceptionDetail(item);
  return asList(detail.join_key)
    .filter((entry) => typeof entry === 'object' && entry !== null)
    .flatMap((entry) => {
      const row = asRecord(entry);
      const sourceField = toText(row.source_field || row.field).trim();
      const targetField = toText(row.target_field || row.field).trim();
      const detail = getExceptionDetail(item);
      const sourceSide = sideFromRef(detail.source_ref) || 'left';
      const targetSide = sideFromRef(detail.target_ref) || 'right';
      const lines: FieldValueLine[] = [];
      if (sourceField) {
        lines.push({
          side: sourceSide,
          datasetLabel: ctx.datasetLabels[sourceSide],
          fieldLabel: displayFieldLabelForSide(ctx, sourceSide, sourceField),
          value: normalizeValue(row.source_value ?? row.value ?? findRawValue(item, sourceSide, sourceField)),
        });
      }
      if (targetField) {
        lines.push({
          side: targetSide,
          datasetLabel: ctx.datasetLabels[targetSide],
          fieldLabel: displayFieldLabelForSide(ctx, targetSide, targetField),
          value: normalizeValue(row.target_value ?? row.value ?? findRawValue(item, targetSide, targetField)),
        });
      }
      return lines;
    });
}

function getCompareValueLines(item: ReconRunExceptionDetail, ctx: ExceptionDisplayContext): CompareValueLine[] {
  const detail = getExceptionDetail(item);
  const sourceSide = sideFromRef(detail.source_ref) || 'left';
  const targetSide = sideFromRef(detail.target_ref) || 'right';
  return asList(detail.compare_values)
    .filter((entry) => typeof entry === 'object' && entry !== null)
    .map((entry) => {
      const row = asRecord(entry);
      const sourceField = toText(row.source_field).trim();
      const targetField = toText(row.target_field).trim();
      const leftLabel = sourceField ? displayFieldLabelForSide(ctx, sourceSide, sourceField) : '';
      const rightLabel = targetField ? displayFieldLabelForSide(ctx, targetSide, targetField) : '';
      return {
        fieldLabel: leftLabel && rightLabel && leftLabel !== rightLabel
          ? `${leftLabel} / ${rightLabel}`
          : leftLabel || rightLabel || toText(row.name, '对比值'),
        sourceValue: normalizeValue(row.source_value ?? findRawValue(item, sourceSide, sourceField)),
        targetValue: normalizeValue(row.target_value ?? findRawValue(item, targetSide, targetField)),
        diffValue: normalizeValue(row.diff_value),
      };
    });
}

function fieldValueSummary(item: ReconRunExceptionDetail, ctx: ExceptionDisplayContext): string {
  const joinLines = getJoinKeyLines(item, ctx)
    .filter((line) => line.value !== '--')
    .slice(0, 3)
    .map((line) => `${line.datasetLabel}：${line.fieldLabel} = ${line.value}`);
  if (joinLines.length > 0) return joinLines.join('；');
  const compareLines = getCompareValueLines(item, ctx).slice(0, 2);
  return compareLines
    .map((line) => `${line.fieldLabel}：${line.sourceValue} / ${line.targetValue}`)
    .join('；') || '--';
}

function recordSectionEntriesForSide(
  item: ReconRunExceptionDetail | null,
  side: ReconSide,
  ctx: ExceptionDisplayContext,
): Array<{ field: string; label: string; value: string }> {
  if (!item) return [];
  const records = getRecordsBySide(item);
  const fromRecord = recordEntriesForDisplay(records[side], side, ctx);
  if (fromRecord.length > 0) return fromRecord;

  const detail = getExceptionDetail(item);
  const refSide = sideFromRef(detail.source_ref) || 'left';
  if (refSide !== side) return [];
  return recordEntriesForDisplay(getRawRecord(item), side, ctx);
}

function recordEntriesForDisplay(
  record: Record<string, unknown>,
  side: ReconSide,
  ctx: ExceptionDisplayContext,
): Array<{ field: string; label: string; value: string }> {
  return Object.entries(record)
    .filter(([field]) => !['source_name', 'source_side', 'source_count'].includes(field))
    .map(([field, value]) => ({
      field,
      label: displayFieldLabelForSide(ctx, side, field),
      value: normalizeValue(value),
    }));
}

function businessDateFromBundle(bundle: PublicExceptionBundle | null): string {
  const runContext = asRecord(bundle?.run?.raw.run_context_json);
  return (
    toText(runContext.biz_date).trim()
    || toText(bundle?.run?.raw.biz_date).trim()
    || toText(bundle?.task?.raw.biz_date).trim()
    || '--'
  );
}

function defaultOwnerFromBundle(bundle: PublicExceptionBundle | null): { name: string; identifier: string } {
  const ownerMapping = asRecord(bundle?.task?.raw.owner_mapping_json);
  const defaultOwner = asRecord(ownerMapping.default_owner);
  return {
    name: toText(defaultOwner.name || defaultOwner.display_name).trim(),
    identifier: toText(defaultOwner.identifier || defaultOwner.owner_identifier).trim(),
  };
}

function ownerDisplayName(item: ReconRunExceptionDetail, bundle: PublicExceptionBundle | null): string {
  const configuredOwner = defaultOwnerFromBundle(bundle);
  if (
    configuredOwner.name
    && configuredOwner.identifier
    && item.ownerIdentifier
    && item.ownerIdentifier === configuredOwner.identifier
  ) {
    return configuredOwner.name;
  }
  if (item.ownerName && item.ownerName !== item.ownerIdentifier) return item.ownerName;
  return configuredOwner.name || item.ownerName || item.ownerIdentifier || '--';
}

function statusOptions(exceptions: ReconRunExceptionDetail[]): string[] {
  return Array.from(
    new Set(exceptions.map((item) => item.processingStatus).filter(Boolean)),
  );
}

function PublicRecordSection({
  title,
  entries,
}: {
  title: string;
  entries: Array<{ field: string; label: string; value: string }>;
}) {
  if (entries.length === 0) return null;
  return (
    <section className="rounded-2xl border border-border bg-surface-secondary p-4">
      <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        {entries.map((entry) => (
          <div key={`${entry.field}-${entry.label}`} className="min-w-0 rounded-xl border border-border-subtle bg-surface px-3 py-2">
            <dt className="text-xs text-text-muted">{entry.label}</dt>
            <dd className="mt-1 whitespace-pre-wrap break-words text-sm text-text-primary">{entry.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function PublicReconRunExceptionsPage() {
  const runId = parsePublicReconRunExceptionsRunId(window.location.pathname);
  const initialOwner = new URLSearchParams(window.location.search).get('owner') || '';
  const [bundle, setBundle] = useState<PublicExceptionBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [keyword, setKeyword] = useState('');
  const [selectedException, setSelectedException] = useState<ReconRunExceptionDetail | null>(null);
  const [showRunDetails, setShowRunDetails] = useState(false);

  const loadBundle = useCallback(async (nextOffset: number) => {
    if (!runId) {
      setError('差异链接缺少运行记录 ID。');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(nextOffset),
      });
      if (initialOwner) {
        params.set('owner', initialOwner);
      }
      const response = await fetchReconAutoApi(`/public/runs/${encodeURIComponent(runId)}/exceptions?${params.toString()}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || '加载对账差异失败'));
      }
      setBundle(mapBundle(data));
      setOffset(nextOffset);
      setSelectedException(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载对账差异失败');
    } finally {
      setLoading(false);
    }
  }, [initialOwner, runId]);

  useEffect(() => {
    void loadBundle(0);
  }, [loadBundle]);

  const displayContext = useMemo(() => buildDisplayContext(bundle?.scheme || null), [bundle?.scheme]);
  const filteredExceptions = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return (bundle?.exceptions || []).filter((item) => {
      if (statusFilter && item.processingStatus !== statusFilter) return false;
      if (!normalizedKeyword) return true;
      const haystack = [
        readableExceptionSummary(item, displayContext),
        ownerDisplayName(item, bundle),
        item.ownerName,
        item.ownerIdentifier,
        anomalyTypeLabel(item, displayContext),
        fieldValueSummary(item, displayContext),
        item.latestFeedback,
      ].join('\n').toLowerCase();
      return haystack.includes(normalizedKeyword);
    });
  }, [bundle, bundle?.exceptions, displayContext, keyword, statusFilter]);

  const selectedLeftRecordEntries = recordSectionEntriesForSide(selectedException, 'left', displayContext);
  const selectedRightRecordEntries = recordSectionEntriesForSide(selectedException, 'right', displayContext);
  const selectedJoinLines = selectedException ? getJoinKeyLines(selectedException, displayContext) : [];
  const selectedCompareLines = selectedException ? getCompareValueLines(selectedException, displayContext) : [];
  const statusMeta = formatExecutionStatus(bundle?.run?.executionStatus || '');
  const runtimeSummary = useMemo(() => buildRuntimeSummaryView(bundle?.run), [bundle?.run]);
  const pendingDifferenceTotal = bundle?.total ?? (bundle?.exceptions || []).length;
  const hasPrevious = offset > 0;
  const hasNext = bundle ? offset + bundle.limit < bundle.total : false;
  const uniqueStatuses = statusOptions(bundle?.exceptions || []);

  const renderRuntimeMetric = (label: string, value: string, key?: string) => (
    <div key={key} className="min-w-[180px] rounded-xl border border-border bg-surface-secondary px-3 py-2">
      <p className="text-[11px] font-medium text-text-secondary">{label}</p>
      <p className="mt-1 text-sm font-semibold text-text-primary">{value}</p>
    </div>
  );

  const collectionMetricNodes = runtimeSummary.collectionMetrics.map((item, index) => renderRuntimeMetric(
    `${item.businessName}采集`,
    `${formatCount(item.rowCount)} 行耗时 ${formatDuration(item.durationSeconds)}`,
    `collection-${item.side || item.businessName}-${index}`,
  ));

  const preparationMetricNodes = runtimeSummary.preparationMetrics.map((item, index) => renderRuntimeMetric(
    `整理后${item.businessName}`,
    `${formatCount(item.rowCount)} 行耗时 ${formatDuration(item.durationSeconds)}`,
    `preparation-${item.side || item.businessName}-${index}`,
  ));

  return (
    <main className="h-screen overflow-y-auto bg-surface-secondary text-text-primary">
      <div className="mx-auto flex min-h-full w-full max-w-[1500px] flex-col gap-5 px-5 py-6 lg:px-8">
        <header className="rounded-[28px] border border-border bg-surface px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">对账差异公开分享</p>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <h1 className="break-words text-xl font-semibold text-text-primary">
                  {bundle?.task?.name || bundle?.run?.planName || bundle?.scheme?.name || '对账差异明细'}
                </h1>
                {bundle?.run ? (
                  <span className={cn('inline-flex rounded-full border px-2.5 py-1 text-xs font-medium', statusMeta.className)}>
                    {statusMeta.label}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-text-secondary">
                {bundle?.scheme?.name || bundle?.run?.schemeName || '--'} · 对账日期 {businessDateFromBundle(bundle)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadBundle(offset)}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
            >
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
              刷新
            </button>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            {renderRuntimeMetric('对账数据日期', runtimeSummary.bizDate || '--')}
            {collectionMetricNodes}
            {preparationMetricNodes}
            {renderRuntimeMetric('对账耗时', formatDuration(runtimeSummary.reconciliationDurationSeconds))}
          </div>
          <div className="mt-4 rounded-2xl border border-border bg-surface-secondary">
            <button
              type="button"
              onClick={() => setShowRunDetails((value) => !value)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-text-primary"
            >
              <span>运行详情</span>
              <ChevronDown className={cn('h-4 w-4 transition', showRunDetails && 'rotate-180')} />
            </button>
            {showRunDetails ? (
              <div className="grid gap-3 border-t border-border-subtle px-4 py-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <p className="text-xs text-text-secondary">所属方案</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{bundle?.scheme?.name || bundle?.run?.schemeName || '--'}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">运行状态</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{statusMeta.label}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">队列开始时间</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(runtimeSummary.queueStartedAt)}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">队列结束时间</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(runtimeSummary.queueFinishedAt)}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">队列总耗时</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{formatDuration(runtimeSummary.queueDurationSeconds)}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">记录写入开始时间</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(bundle?.run?.startedAt || '')}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">记录写入结束时间</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(bundle?.run?.finishedAt || '')}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">汇总接收人</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {runtimeSummary.notification.recipientName || runtimeSummary.notification.recipientIdentifier || '--'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary">汇总消息推送状态</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {runtimeSummary.notification.label}
                    {runtimeSummary.notification.error ? ` · ${runtimeSummary.notification.error}` : ''}
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        </header>

        <section className="rounded-[28px] border border-border bg-surface p-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 text-sm font-medium text-text-secondary">
              <Filter className="h-4 w-4" />
              筛选
            </span>
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="appearance-none rounded-xl border border-border bg-surface py-2 pl-3 pr-9 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
              >
                <option value="">全部处理状态</option>
                {uniqueStatuses.map((status) => (
                  <option key={status} value={status}>
                    {formatProcessingStatus(status)}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
            </div>
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索订单号、金额、责任人"
              className="min-w-[240px] flex-1 rounded-xl border border-border bg-surface px-3 py-2 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            />
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <section className="overflow-hidden rounded-[28px] border border-border bg-surface shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
            <h2 className="text-base font-semibold text-text-primary">差异列表</h2>
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
              待处理差异 {formatCount(pendingDifferenceTotal)} 条
            </span>
          </div>
          {loading ? (
            <div className="flex min-h-[280px] items-center justify-center gap-2 text-sm text-text-secondary">
              <RefreshCw className="h-4 w-4 animate-spin" />
              正在加载全量差异...
            </div>
          ) : filteredExceptions.length > 0 ? (
            <div className="overflow-x-auto">
              <div className="min-w-[1320px] divide-y divide-border-subtle">
                <div className="grid grid-cols-[minmax(440px,1.5fr)_minmax(360px,1fr)_140px_140px_100px] gap-4 border-b border-border-subtle px-5 py-3 text-[11px] font-semibold tracking-[0.14em] text-text-muted">
                  <span>摘要</span>
                  <span>关键字段和值</span>
                  <span>责任人</span>
                  <span>处理状态</span>
                  <span className="text-right">操作</span>
                </div>
                {filteredExceptions.map((item) => (
                  <article
                    key={item.id}
                    className="grid grid-cols-[minmax(440px,1.5fr)_minmax(360px,1fr)_140px_140px_100px] items-start gap-4 px-5 py-4"
                  >
                    <p
                      className="whitespace-pre-line break-words text-sm leading-6 text-text-primary"
                      style={ANYWHERE_WRAP_STYLE}
                    >
                      {readableExceptionSummary(item, displayContext)}
                    </p>
                    <p
                      className="whitespace-pre-line break-words text-sm leading-6 text-text-secondary"
                      style={ANYWHERE_WRAP_STYLE}
                    >
                      {fieldValueSummary(item, displayContext)}
                    </p>
                    <span className="break-words text-sm leading-6 text-text-secondary">{ownerDisplayName(item, bundle)}</span>
                    <span className="break-words text-sm leading-6 text-text-secondary">{formatProcessingStatus(item.processingStatus)}</span>
                    <button
                      type="button"
                      onClick={() => setSelectedException(item)}
                      className="justify-self-end inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-xs font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      详情
                    </button>
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex min-h-[280px] flex-col items-center justify-center px-6 text-center">
              <AlertCircle className="h-8 w-8 text-text-muted" />
              <p className="mt-3 text-sm font-medium text-text-primary">当前筛选条件下没有差异</p>
              <p className="mt-1 text-sm text-text-secondary">可以清空筛选条件或切换分页查看。</p>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle px-5 py-4 text-sm text-text-secondary">
            <span>
              第 {Math.floor(offset / PAGE_SIZE) + 1} 页 · 当前页 {filteredExceptions.length} 条 · 总计 {bundle?.total ?? 0} 条
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!hasPrevious || loading}
                onClick={() => void loadBundle(Math.max(0, offset - PAGE_SIZE))}
                className="inline-flex items-center gap-1 rounded-xl border border-border bg-surface px-3 py-2 text-sm transition hover:border-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ChevronLeft className="h-4 w-4" />
                上一页
              </button>
              <button
                type="button"
                disabled={!hasNext || loading}
                onClick={() => void loadBundle(offset + PAGE_SIZE)}
                className="inline-flex items-center gap-1 rounded-xl border border-border bg-surface px-3 py-2 text-sm transition hover:border-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                下一页
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </section>
      </div>

      {selectedException ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4 py-6">
          <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-border bg-surface shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">差异详情</p>
                <h2 className="mt-1 text-lg font-semibold text-text-primary">差异记录</h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedException(null)}
                className="rounded-xl border border-border p-2 text-text-secondary transition hover:border-sky-200 hover:text-sky-700"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
              <div className="space-y-4">
                <section className="rounded-2xl border border-border bg-surface-secondary p-4">
                  <p className="text-sm font-semibold text-text-primary">摘要</p>
                  <p className="mt-2 whitespace-pre-line text-sm leading-6 text-text-secondary">
                    {readableExceptionSummary(selectedException, displayContext)}
                  </p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div>
                      <p className="text-xs text-text-muted">责任人</p>
                      <p className="mt-1 text-sm text-text-primary">{ownerDisplayName(selectedException, bundle)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted">处理状态</p>
                      <p className="mt-1 text-sm text-text-primary">{formatProcessingStatus(selectedException.processingStatus)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-text-muted">最新反馈</p>
                      <p className="mt-1 text-sm text-text-primary">{selectedException.latestFeedback || '--'}</p>
                    </div>
                  </div>
                </section>

                {selectedJoinLines.length > 0 ? (
                  <section className="rounded-2xl border border-border bg-surface-secondary p-4">
                    <h3 className="text-sm font-semibold text-text-primary">对账关键字段</h3>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {selectedJoinLines.map((line, index) => (
                        <div key={`${line.side}-${line.fieldLabel}-${index}`} className="rounded-xl border border-border-subtle bg-surface px-3 py-2">
                          <p className="text-xs text-text-muted">{line.datasetLabel}：{line.fieldLabel}</p>
                          <p className="mt-1 break-words text-sm text-text-primary">{line.value}</p>
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}

                {selectedCompareLines.length > 0 ? (
                  <section className="rounded-2xl border border-border bg-surface-secondary p-4">
                    <h3 className="text-sm font-semibold text-text-primary">差异字段和值</h3>
                    <div className="mt-3 overflow-x-auto rounded-xl border border-border-subtle bg-surface">
                      <table className="min-w-[720px] w-full text-left text-sm">
                        <thead className="border-b border-border-subtle text-xs text-text-muted">
                          <tr>
                            <th className="px-3 py-2 font-medium">字段</th>
                            <th className="px-3 py-2 font-medium">{displayContext.datasetLabels.left}</th>
                            <th className="px-3 py-2 font-medium">{displayContext.datasetLabels.right}</th>
                            <th className="px-3 py-2 font-medium">差异值</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCompareLines.map((line, index) => (
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
                  </section>
                ) : null}

                <PublicRecordSection
                  title={`${displayContext.datasetLabels.left} 整理输出行`}
                  entries={selectedLeftRecordEntries}
                />
                <PublicRecordSection
                  title={`${displayContext.datasetLabels.right} 整理输出行`}
                  entries={selectedRightRecordEntries}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
