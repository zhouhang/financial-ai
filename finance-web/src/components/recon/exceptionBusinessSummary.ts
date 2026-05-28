import { formatExceptionSummaryLines } from './exceptionSummaryDisplay';

export type ReconExceptionSide = 'left' | 'right';

export interface ExceptionBusinessItem {
  anomalyType: string;
  summary?: string | null;
  raw?: Record<string, unknown> | null;
}

export interface ExceptionBusinessDisplayContext {
  datasetLabels: Record<ReconExceptionSide, string>;
  fieldLabelForSide: (side: ReconExceptionSide, field: string) => string;
}

export interface ExceptionFieldValueLine {
  side: ReconExceptionSide;
  datasetLabel: string;
  fieldLabel: string;
  value: string;
}

export interface ExceptionCompareValueLine {
  fieldLabel: string;
  sourceDatasetLabel: string;
  targetDatasetLabel: string;
  sourceValue: string;
  targetValue: string;
  diffValue: string;
}

export interface ExceptionRecordEntry {
  field: string;
  label: string;
  value: string;
}

export interface ExceptionRecordSection {
  side: ReconExceptionSide;
  title: string;
  entries: ExceptionRecordEntry[];
  emptyMessage?: string;
}

export interface ExceptionBusinessDisplay {
  shortSummary: string;
  conclusion: string;
  keyLines: ExceptionFieldValueLine[];
  compareLines: ExceptionCompareValueLine[];
  recordSections: ExceptionRecordSection[];
}

type DetailRecord = Record<string, unknown>;

interface JoinKeyDetail {
  sourceField: string;
  targetField: string;
  sourceValue: unknown;
  targetValue: unknown;
}

const EMPTY_VALUE = '--';

const LEFT_PREFIXES = ['left_recon_ready.', 'source.', 'left.'] as const;
const RIGHT_PREFIXES = ['right_recon_ready.', 'target.', 'right.'] as const;
const ALL_RECORD_PREFIXES = [...LEFT_PREFIXES, ...RIGHT_PREFIXES] as const;

function isRecord(value: unknown): value is DetailRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asRecord(value: unknown): DetailRecord {
  return isRecord(value) ? value : {};
}

function asArray(value: unknown): DetailRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function valueToField(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function sideFromRef(value: unknown, fallback: ReconExceptionSide): ReconExceptionSide {
  if (typeof value !== 'string') return fallback;
  const normalized = value.toLowerCase();
  if (normalized.includes('right') || normalized.includes('target')) return 'right';
  if (normalized.includes('left') || normalized.includes('source')) return 'left';
  return fallback;
}

function fieldLabel(
  context: ExceptionBusinessDisplayContext,
  side: ReconExceptionSide,
  field: string,
): string {
  return field ? context.fieldLabelForSide(side, stripExceptionFieldPrefix(field)) : '字段';
}

function detailJsonFor(item: ExceptionBusinessItem): DetailRecord {
  const raw = asRecord(item.raw);
  const candidates = [raw.detail_json, raw.detail, raw];
  for (const candidate of candidates) {
    const record = asRecord(candidate);
    if (Object.keys(record).length > 0) return record;
  }
  return {};
}

function joinDetailsFor(detailJson: DetailRecord): JoinKeyDetail[] {
  return asArray(detailJson.join_key).map((entry) => {
    const field = valueToField(entry.field);
    const value = entry.value;

    return {
      sourceField: valueToField(entry.source_field) || field,
      targetField: valueToField(entry.target_field) || field,
      sourceValue: entry.source_value ?? value,
      targetValue: entry.target_value ?? value,
    };
  });
}

function matchDetailFor(
  joinDetails: JoinKeyDetail[],
  preferredSide?: ReconExceptionSide,
): {
  field: string;
  side: ReconExceptionSide;
  value: unknown;
} | null {
  for (const detail of joinDetails) {
    const sourceValue = normalizeExceptionValue(detail.sourceValue);
    if (sourceValue !== EMPTY_VALUE && (!preferredSide || preferredSide === 'left')) {
      return { field: detail.sourceField || detail.targetField, side: 'left', value: detail.sourceValue };
    }

    const targetValue = normalizeExceptionValue(detail.targetValue);
    if (targetValue !== EMPTY_VALUE && (!preferredSide || preferredSide === 'right')) {
      return { field: detail.targetField || detail.sourceField, side: 'right', value: detail.targetValue };
    }
  }

  return null;
}

function compareFieldLabel(
  context: ExceptionBusinessDisplayContext,
  sourceField: string,
  targetField: string,
): string {
  const sourceLabel = fieldLabel(context, 'left', sourceField);
  const targetLabel = fieldLabel(context, 'right', targetField);
  if (!sourceField && !targetField) return '字段';
  if (!targetField || sourceLabel === targetLabel) return sourceLabel;
  if (!sourceField) return targetLabel;
  return `${sourceLabel} / ${targetLabel}`;
}

function differenceTypeFor(compareLines: ExceptionCompareValueLine[]): string {
  if (compareLines.length > 1) return '多字段不一致';

  const label = compareLines[0]?.fieldLabel || '';
  const normalized = label.toLowerCase();
  if (/金额|实付|含税|销售|amount|paid|money/.test(normalized)) return '金额不一致';
  if (/状态|status/.test(normalized)) return '状态不一致';
  return label && label !== '字段' ? `${label}不一致` : '字段不一致';
}

function prefixedSideFor(field: string): ReconExceptionSide | null {
  if (LEFT_PREFIXES.some((prefix) => field.startsWith(prefix))) return 'left';
  if (RIGHT_PREFIXES.some((prefix) => field.startsWith(prefix))) return 'right';
  return null;
}

function prefixedRecordSection(record: DetailRecord, side: ReconExceptionSide): DetailRecord {
  const section: DetailRecord = {};

  for (const [field, value] of Object.entries(record)) {
    if (prefixedSideFor(field) !== side) continue;
    section[stripExceptionFieldPrefix(field)] = value;
  }

  return section;
}

function hasPrefixedFields(record: DetailRecord): boolean {
  return Object.keys(record).some((field) => prefixedSideFor(field));
}

function unprefixedRecordForSide(
  side: ReconExceptionSide,
  detailJson: DetailRecord,
  raw: DetailRecord,
  fallbackSide: ReconExceptionSide,
): DetailRecord {
  if (side !== fallbackSide) return {};

  for (const source of [detailJson, raw]) {
    for (const key of ['raw_record', 'record']) {
      const record = asRecord(source[key]);
      if (Object.keys(record).length > 0 && !hasPrefixedFields(record)) return record;
    }
  }

  return {};
}

function entriesForRecord(
  record: DetailRecord,
  side: ReconExceptionSide,
  context: ExceptionBusinessDisplayContext,
): ExceptionRecordEntry[] {
  return Object.entries(record)
    .filter(([, value]) => normalizeExceptionValue(value) !== EMPTY_VALUE)
    .map(([field, value]) => {
      const strippedField = stripExceptionFieldPrefix(field);
      return {
        field: strippedField,
        label: fieldLabel(context, side, strippedField),
        value: normalizeExceptionValue(value),
      };
    });
}

function recordForSide(
  side: ReconExceptionSide,
  detailJson: DetailRecord,
  raw: DetailRecord,
  fallbackSide: ReconExceptionSide,
): DetailRecord {
  const directKeys =
    side === 'left'
      ? ['left_record', 'source_record', 'left_row']
      : ['right_record', 'target_record', 'right_row'];

  for (const source of [detailJson, raw]) {
    for (const key of directKeys) {
      const record = asRecord(source[key]);
      if (Object.keys(record).length > 0) return record;
    }
  }

  for (const source of [detailJson, raw]) {
    const rawRecord = asRecord(source.raw_record);
    if (Object.keys(rawRecord).length > 0) {
      const section = prefixedRecordSection(rawRecord, side);
      if (Object.keys(section).length > 0) return section;
      if (hasPrefixedFields(rawRecord)) return {};
    }

    const record = asRecord(source.record);
    if (Object.keys(record).length > 0) {
      const section = prefixedRecordSection(record, side);
      if (Object.keys(section).length > 0) return section;
      if (hasPrefixedFields(record)) return {};
    }
  }

  const fallbackRecord = unprefixedRecordForSide(side, detailJson, raw, fallbackSide);
  if (Object.keys(fallbackRecord).length > 0) return fallbackRecord;

  return {};
}

function hasDisplayValue(value: unknown): boolean {
  return normalizeExceptionValue(value) !== EMPTY_VALUE;
}

function valueFromRecord(record: DetailRecord, field: string): unknown {
  const strippedField = stripExceptionFieldPrefix(field);
  const candidates = [field, strippedField];

  for (const candidate of candidates) {
    if (Object.prototype.hasOwnProperty.call(record, candidate) && hasDisplayValue(record[candidate])) {
      return record[candidate];
    }
  }

  return undefined;
}

function recordValueForSide(
  side: ReconExceptionSide,
  field: string,
  detailJson: DetailRecord,
  raw: DetailRecord,
): unknown {
  if (!field) return undefined;

  const sideRecordValue = valueFromRecord(recordForSide(side, detailJson, raw, side), field);
  if (hasDisplayValue(sideRecordValue)) return sideRecordValue;

  const strippedField = stripExceptionFieldPrefix(field);
  const prefixes = side === 'left' ? LEFT_PREFIXES : RIGHT_PREFIXES;
  for (const source of [detailJson, raw]) {
    for (const recordKey of ['raw_record', 'record']) {
      const record = asRecord(source[recordKey]);
      if (Object.keys(record).length === 0) continue;

      for (const prefix of prefixes) {
        const prefixedValue = record[`${prefix}${strippedField}`];
        if (hasDisplayValue(prefixedValue)) return prefixedValue;
      }

      const unprefixedValue = valueFromRecord(record, strippedField);
      if (hasDisplayValue(unprefixedValue)) return unprefixedValue;
    }
  }

  return undefined;
}

function firstDisplayValue(primary: unknown, fallback: unknown): unknown {
  return hasDisplayValue(primary) ? primary : fallback;
}

function hydratedJoinDetailsFor(
  detailJson: DetailRecord,
  raw: DetailRecord,
): JoinKeyDetail[] {
  const sourceSide = sideFromRef(detailJson.source_ref, 'left');
  const targetSide = sideFromRef(detailJson.target_ref, 'right');

  return joinDetailsFor(detailJson).map((entry) => ({
    ...entry,
    sourceValue: firstDisplayValue(
      entry.sourceValue,
      recordValueForSide(sourceSide, entry.sourceField || entry.targetField, detailJson, raw),
    ),
    targetValue: firstDisplayValue(
      entry.targetValue,
      recordValueForSide(targetSide, entry.targetField || entry.sourceField, detailJson, raw),
    ),
  }));
}

function buildKeyLines(
  joinDetails: JoinKeyDetail[],
  detailJson: DetailRecord,
  context: ExceptionBusinessDisplayContext,
): ExceptionFieldValueLine[] {
  const sourceSide = sideFromRef(detailJson.source_ref, 'left');
  const targetSide = sideFromRef(detailJson.target_ref, 'right');

  return joinDetails.flatMap((entry) => [
    {
      side: sourceSide,
      datasetLabel: context.datasetLabels[sourceSide],
      fieldLabel: fieldLabel(context, sourceSide, entry.sourceField || entry.targetField),
      value: normalizeExceptionValue(entry.sourceValue),
    },
    {
      side: targetSide,
      datasetLabel: context.datasetLabels[targetSide],
      fieldLabel: fieldLabel(context, targetSide, entry.targetField || entry.sourceField),
      value: normalizeExceptionValue(entry.targetValue),
    },
  ]);
}

function buildCompareLines(
  detailJson: DetailRecord,
  raw: DetailRecord,
  context: ExceptionBusinessDisplayContext,
): ExceptionCompareValueLine[] {
  const sourceSide = sideFromRef(detailJson.source_ref, 'left');
  const targetSide = sideFromRef(detailJson.target_ref, 'right');

  return asArray(detailJson.compare_values).map((entry) => {
    const sourceField = valueToField(entry.source_field) || valueToField(entry.field);
    const targetField = valueToField(entry.target_field) || valueToField(entry.field);

    return {
      fieldLabel: compareFieldLabel(context, sourceField, targetField),
      sourceDatasetLabel: context.datasetLabels[sourceSide],
      targetDatasetLabel: context.datasetLabels[targetSide],
      sourceValue: normalizeExceptionValue(
        firstDisplayValue(
          entry.source_value,
          recordValueForSide(sourceSide, sourceField || targetField, detailJson, raw),
        ),
      ),
      targetValue: normalizeExceptionValue(
        firstDisplayValue(
          entry.target_value,
          recordValueForSide(targetSide, targetField || sourceField, detailJson, raw),
        ),
      ),
      diffValue: normalizeExceptionValue(entry.diff_value),
    };
  });
}

function buildRecordSections(
  item: ExceptionBusinessItem,
  detailJson: DetailRecord,
  joinDetails: JoinKeyDetail[],
  context: ExceptionBusinessDisplayContext,
): ExceptionRecordSection[] {
  const raw = asRecord(item.raw);
  const fallbackSide = (
    matchDetailFor(joinDetails, item.anomalyType === 'target_only' ? 'right' : 'left')?.side
    || (item.anomalyType === 'target_only' ? 'right' : 'left')
  );

  return (['left', 'right'] as const).map((side) => {
    const entries = entriesForRecord(recordForSide(side, detailJson, raw, fallbackSide), side, context);
    return {
      side,
      title: context.datasetLabels[side],
      entries,
      ...(entries.length === 0 ? { emptyMessage: '未匹配到原始记录' } : {}),
    };
  });
}

function buildShortSummary(
  item: ExceptionBusinessItem,
  context: ExceptionBusinessDisplayContext,
  joinDetails: JoinKeyDetail[],
  compareLines: ExceptionCompareValueLine[],
): string {
  const preferredSide =
    item.anomalyType === 'target_only' ? 'right' : 'left';
  const matchDetail = matchDetailFor(joinDetails, preferredSide);
  if (!matchDetail) return formatExceptionSummaryLines(item.summary || '');

  const matchLabel = fieldLabel(context, matchDetail.side, matchDetail.field);
  const matchValue = normalizeExceptionValue(matchDetail.value);

  if (item.anomalyType === 'source_only') {
    return `${context.datasetLabels.right}缺失${matchLabel} ${matchValue}`;
  }
  if (item.anomalyType === 'target_only') {
    return `${context.datasetLabels.left}缺失${matchLabel} ${matchValue}`;
  }
  if (item.anomalyType === 'matched_with_diff' || item.anomalyType === 'value_mismatch') {
    return `${matchLabel} ${matchValue} ${differenceTypeFor(compareLines)}`;
  }

  return formatExceptionSummaryLines(item.summary || '');
}

export function normalizeExceptionValue(value: unknown): string {
  if (value === null || value === undefined) return EMPTY_VALUE;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed === '' ? EMPTY_VALUE : trimmed;
  }
  if (typeof value === 'number' || typeof value === 'bigint' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

export function stripExceptionFieldPrefix(field: string): string {
  const prefix = ALL_RECORD_PREFIXES.find((candidate) => field.startsWith(candidate));
  return prefix ? field.slice(prefix.length) : field;
}

export function buildExceptionBusinessDisplay(
  item: ExceptionBusinessItem,
  context: ExceptionBusinessDisplayContext,
): ExceptionBusinessDisplay {
  const detailJson = detailJsonFor(item);
  const raw = asRecord(item.raw);
  const joinDetails = hydratedJoinDetailsFor(detailJson, raw);
  const keyLines = buildKeyLines(joinDetails, detailJson, context);
  const compareLines = buildCompareLines(detailJson, raw, context);
  const shortSummary = buildShortSummary(item, context, joinDetails, compareLines);

  return {
    shortSummary,
    conclusion: shortSummary,
    keyLines,
    compareLines,
    recordSections: buildRecordSections(item, detailJson, joinDetails, context),
  };
}
