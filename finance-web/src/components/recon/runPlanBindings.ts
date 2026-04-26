import type { OutputFieldDraft } from './schemeWizardState';
import { normalizeOutputFieldSemanticRole } from './schemeWizardState';
import type { DataSourceKind } from '../../types';

type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

export interface RunPlanSourceDraft {
  id: string;
  name: string;
  sourceId?: string;
  sourceKind: SupportedSourceKind;
  providerCode: string;
  datasetCode?: string;
  resourceKey?: string;
}

export interface RunPlanSchemeMetaSummary {
  leftSources: RunPlanSourceDraft[];
  rightSources: RunPlanSourceDraft[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
}

function toText(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return fallback;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

export function buildRunPlanBinding(
  source: RunPlanSourceDraft,
  dateField: string,
  sourceDateField: string,
  side: 'left' | 'right',
  index: number,
): Record<string, unknown> | null {
  const sourceId = toText(source.sourceId).trim();
  const tableName = toText(source.resourceKey, toText(source.datasetCode, source.name)).trim();
  if (!sourceId || !tableName) return null;

  const query: Record<string, unknown> = {};
  if (tableName) {
    query.resource_key = tableName;
  }
  if (sourceDateField.trim()) {
    query.date_field = sourceDateField.trim();
  }
  if (dateField.trim()) {
    query.display_date_field = dateField.trim();
  }

  return {
    data_source_id: sourceId,
    table_name: tableName,
    resource_key: tableName,
    dataset_source_type: 'collection_records',
    source_kind: source.sourceKind,
    provider_code: source.providerCode,
    role_code: `${side}_${index + 1}`,
    side,
    query,
  };
}

export function resolveRunPlanSourceDateField(
  source: RunPlanSourceDraft,
  timeSemantic: string,
  outputFields: OutputFieldDraft[],
): string {
  const sourceId = toText(source.id).trim();
  const displayName = timeSemantic.trim();
  const candidates = outputFields.filter(
    (field) => normalizeOutputFieldSemanticRole(field.semanticRole) === 'time_field' && field.sourceField.trim(),
  );

  const matchesSourceId = (field: OutputFieldDraft): boolean => {
    const fieldSourceId = toText(field.sourceDatasetId).trim();
    return !sourceId || !fieldSourceId || fieldSourceId === sourceId;
  };

  const exactMatch = candidates.find(
    (field) => matchesSourceId(field) && (!displayName || field.outputName.trim() === displayName),
  );
  if (exactMatch) {
    return exactMatch.sourceField.trim();
  }

  const sameSourceFallback = candidates.find(matchesSourceId);
  if (sameSourceFallback) {
    return sameSourceFallback.sourceField.trim();
  }

  const displayFallback = candidates.find((field) => !displayName || field.outputName.trim() === displayName);
  if (displayFallback) {
    return displayFallback.sourceField.trim();
  }

  return '';
}

export function buildRunPlanBindings(
  schemeMeta: RunPlanSchemeMetaSummary | null,
  leftTimeSemantic: string,
  rightTimeSemantic: string,
): Array<Record<string, unknown>> {
  if (!schemeMeta) return [];
  const bindings = [
    ...schemeMeta.leftSources.map((source, index) => buildRunPlanBinding(
      source,
      leftTimeSemantic,
      resolveRunPlanSourceDateField(source, leftTimeSemantic, schemeMeta.leftOutputFields),
      'left',
      index,
    )),
    ...schemeMeta.rightSources.map((source, index) => buildRunPlanBinding(
      source,
      rightTimeSemantic,
      resolveRunPlanSourceDateField(source, rightTimeSemantic, schemeMeta.rightOutputFields),
      'right',
      index,
    )),
  ].filter(Boolean) as Array<Record<string, unknown>>;

  const seen = new Set<string>();
  return bindings.filter((item) => {
    const query = asRecord(item.query);
    const key = [
      toText(item.data_source_id),
      toText(item.table_name),
      toText(item.resource_key),
      toText(item.side),
      toText(query.date_field),
    ].join('::');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
