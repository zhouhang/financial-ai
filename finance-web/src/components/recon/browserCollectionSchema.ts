import type { DataSourceKind } from '../../types';

type SupportedBrowserSourceKind = Extract<DataSourceKind, 'browser_playbook' | 'browser'>;
const BROWSER_COLLECTION_TECHNICAL_FIELDS = new Set(['storage', 'source_type', 'dataset_source_type']);

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function isBrowserCollectionTechnicalSchemaSummary(options: {
  schemaSummary?: Record<string, unknown>;
  extractConfig?: Record<string, unknown>;
  sourceKind?: SupportedBrowserSourceKind | DataSourceKind | string;
}): boolean {
  const sourceKind = normalizeText(options.sourceKind);
  if (sourceKind !== 'browser_playbook' && sourceKind !== 'browser') return false;

  const schemaSummary = asRecord(options.schemaSummary);
  const extractConfig = asRecord(options.extractConfig);
  const keys = Object.entries(schemaSummary)
    .filter(([, value]) => {
      if (Array.isArray(value)) return value.length > 0;
      return value !== null && value !== undefined && normalizeText(value) !== '';
    })
    .map(([key]) => key.trim())
    .filter(Boolean);
  if (keys.length === 0) return false;

  const allowedKeys = new Set(['storage', 'source_type', 'dataset_source_type', 'columns']);
  const columns = Array.isArray(schemaSummary.columns) ? schemaSummary.columns : [];
  const sourceType = normalizeText(
    schemaSummary.source_type
      || schemaSummary.dataset_source_type
      || extractConfig.source_type
      || extractConfig.dataset_source_type,
  );

  return keys.every((key) => allowedKeys.has(key))
    && columns.length === 0
    && sourceType === 'browser_collection_records';
}

export function isBrowserCollectionDataset(options: {
  schemaSummary?: Record<string, unknown>;
  extractConfig?: Record<string, unknown>;
  sourceKind?: SupportedBrowserSourceKind | DataSourceKind | string;
}): boolean {
  const sourceKind = normalizeText(options.sourceKind);
  if (sourceKind !== 'browser_playbook' && sourceKind !== 'browser') return false;

  const schemaSummary = asRecord(options.schemaSummary);
  const extractConfig = asRecord(options.extractConfig);
  const sourceType = normalizeText(
    schemaSummary.source_type
      || schemaSummary.dataset_source_type
      || schemaSummary.storage
      || extractConfig.source_type
      || extractConfig.dataset_source_type
      || extractConfig.storage,
  );
  return sourceType === 'browser_collection_records';
}

export function isBrowserCollectionTechnicalFieldName(rawName: unknown): boolean {
  return BROWSER_COLLECTION_TECHNICAL_FIELDS.has(normalizeText(rawName));
}

export function filterBrowserCollectionFieldItems<T extends { raw_name?: unknown; rawName?: unknown }>(
  fields: T[],
  options: {
    schemaSummary?: Record<string, unknown>;
    extractConfig?: Record<string, unknown>;
    sourceKind?: SupportedBrowserSourceKind | DataSourceKind | string;
  },
): T[] {
  if (!isBrowserCollectionDataset(options)) return fields;
  return fields.filter((field) => {
    const rawName = field.raw_name ?? field.rawName;
    return !isBrowserCollectionTechnicalFieldName(rawName);
  });
}
