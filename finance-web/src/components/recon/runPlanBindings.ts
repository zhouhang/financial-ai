import type { OutputFieldDraft } from './schemeWizardState';
import type { DataSourceKind } from '../../types';

type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

export interface RunPlanSourceDraft {
  id: string;
  name: string;
  businessName?: string;
  sourceId?: string;
  sourceKind: SupportedSourceKind;
  providerCode: string;
  datasetCode?: string;
  resourceKey?: string;
  fieldLabelMap?: Record<string, string>;
  schemaSummary?: Record<string, unknown>;
}

export interface RunPlanSchemeMetaSummary {
  leftSources: RunPlanSourceDraft[];
  rightSources: RunPlanSourceDraft[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
  inputPlanJson?: Record<string, unknown> | null;
}

export interface RunPlanInputDatasetDraft {
  key: string;
  side: 'left' | 'right';
  targetTable: string;
  alias: string;
  table: string;
  datasetId: string;
  sourceId: string;
  resourceKey: string;
  readMode: string;
  applyBizDateFilter: boolean;
  requiresDateField: boolean;
  displayName: string;
  source?: RunPlanSourceDraft;
}

function toText(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return fallback;
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    const text = toText(value).trim();
    if (text) return text;
  }
  return '';
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function normalizeReadMode(value: unknown): string {
  return toText(value, 'base').trim().toLowerCase() || 'base';
}

function buildInputDatasetKey(input: {
  side: string;
  targetTable: string;
  alias: string;
  table: string;
  sourceId: string;
  resourceKey: string;
}): string {
  return [
    input.side,
    input.targetTable,
    input.alias,
    input.table,
    input.sourceId,
    input.resourceKey,
  ].map((item) => item.trim()).join('::');
}

function sourceKeys(source: RunPlanSourceDraft): Set<string> {
  return new Set(
    [
      source.resourceKey,
      source.datasetCode,
      source.name,
    ].map((item) => toText(item).trim()).filter(Boolean),
  );
}

function inputKeys(input: {
  table: string;
  resourceKey: string;
}): Set<string> {
  return new Set(
    [
      input.table,
      input.resourceKey,
    ].map((item) => toText(item).trim()).filter(Boolean),
  );
}

function findSourceForInput(
  sources: RunPlanSourceDraft[],
  input: {
    datasetId: string;
    sourceId: string;
    table: string;
    resourceKey: string;
  },
): RunPlanSourceDraft | undefined {
  const byDatasetId = sources.find((source) => input.datasetId && source.id === input.datasetId);
  if (byDatasetId) return byDatasetId;

  const keys = inputKeys(input);
  return sources.find((source) => {
    const sourceId = toText(source.sourceId).trim();
    if (input.sourceId && sourceId && sourceId !== input.sourceId) {
      return false;
    }
    const overlap = [...sourceKeys(source)].some((key) => keys.has(key));
    return overlap || (!input.resourceKey && !input.table && input.sourceId && sourceId === input.sourceId);
  });
}

function resolveInputDisplayName(input: {
  alias: string;
  table: string;
  resourceKey: string;
  source?: RunPlanSourceDraft;
}): string {
  return firstText(
    input.source?.businessName,
    input.source?.name,
    input.alias,
    input.table,
    input.resourceKey,
    '未命名数据集',
  );
}

export function extractRunPlanInputDatasets(
  schemeMeta: RunPlanSchemeMetaSummary | null,
): RunPlanInputDatasetDraft[] {
  if (!schemeMeta) return [];
  const planJson = asRecord(schemeMeta.inputPlanJson);
  const plans = asList(planJson.plans).filter((item): item is Record<string, unknown> => {
    return typeof item === 'object' && item !== null;
  });
  const normalizedPlans = plans.length > 0 ? plans : (asList(planJson.datasets).length > 0 ? [planJson] : []);
  const inputs: RunPlanInputDatasetDraft[] = [];

  normalizedPlans.forEach((plan) => {
    const side = toText(plan.side).trim() === 'right' ? 'right' : 'left';
    const sources = side === 'left' ? schemeMeta.leftSources : schemeMeta.rightSources;
    asList(plan.datasets).forEach((raw) => {
      const item = asRecord(raw);
      const table = toText(item.table).trim();
      const alias = toText(item.alias, table).trim();
      const targetTable = toText(item.target_table, toText(plan.target_table)).trim();
      if (!table || !alias) return;
      const sourceId = firstText(item.source_id, item.data_source_id);
      const resourceKey = firstText(item.resource_key, item.dataset_code, table);
      const datasetId = firstText(item.dataset_id, item.id);
      const readMode = normalizeReadMode(item.read_mode);
      const applyBizDateFilter = item.apply_biz_date_filter !== false;
      const requiresDateField = readMode === 'base' && applyBizDateFilter;
      const source = findSourceForInput(sources, { datasetId, sourceId, table, resourceKey });
      const resolvedSourceId = sourceId || toText(source?.sourceId).trim();
      const resolvedResourceKey = resourceKey || firstText(source?.resourceKey, source?.datasetCode, table);

      inputs.push({
        key: buildInputDatasetKey({
          side,
          targetTable,
          alias,
          table,
          sourceId: resolvedSourceId,
          resourceKey: resolvedResourceKey,
        }),
        side,
        targetTable,
        alias,
        table,
        datasetId: datasetId || toText(source?.id).trim(),
        sourceId: resolvedSourceId,
        resourceKey: resolvedResourceKey,
        readMode,
        applyBizDateFilter,
        requiresDateField,
        displayName: resolveInputDisplayName({ alias, table, resourceKey: resolvedResourceKey, source }),
        source,
      });
    });
  });

  if (inputs.length > 0) {
    return inputs;
  }

  return [
    ...schemeMeta.leftSources.map((source, index) => {
      const table = toText(source.resourceKey, toText(source.datasetCode, source.name)).trim();
      const sourceId = toText(source.sourceId).trim();
      return {
        key: buildInputDatasetKey({
          side: 'left',
          targetTable: 'left_recon_ready',
          alias: `left_${index + 1}`,
          table,
          sourceId,
          resourceKey: table,
        }),
        side: 'left' as const,
        targetTable: 'left_recon_ready',
        alias: `left_${index + 1}`,
        table,
        datasetId: source.id,
        sourceId,
        resourceKey: table,
        readMode: 'base',
        applyBizDateFilter: true,
        requiresDateField: true,
        displayName: resolveInputDisplayName({ alias: `left_${index + 1}`, table, resourceKey: table, source }),
        source,
      };
    }),
    ...schemeMeta.rightSources.map((source, index) => {
      const table = toText(source.resourceKey, toText(source.datasetCode, source.name)).trim();
      const sourceId = toText(source.sourceId).trim();
      return {
        key: buildInputDatasetKey({
          side: 'right',
          targetTable: 'right_recon_ready',
          alias: `right_${index + 1}`,
          table,
          sourceId,
          resourceKey: table,
        }),
        side: 'right' as const,
        targetTable: 'right_recon_ready',
        alias: `right_${index + 1}`,
        table,
        datasetId: source.id,
        sourceId,
        resourceKey: table,
        readMode: 'base',
        applyBizDateFilter: true,
        requiresDateField: true,
        displayName: resolveInputDisplayName({ alias: `right_${index + 1}`, table, resourceKey: table, source }),
        source,
      };
    }),
  ];
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

export function buildRunPlanBindings(
  schemeMeta: RunPlanSchemeMetaSummary | null,
  dateFieldByInputKey: Record<string, string>,
): Array<Record<string, unknown>> {
  if (!schemeMeta) return [];
  const sideCounts = { left: 0, right: 0 };
  const bindings = extractRunPlanInputDatasets(schemeMeta).map((input) => {
    const source = input.source || {
      id: input.datasetId,
      name: input.displayName,
      sourceId: input.sourceId,
      sourceKind: 'database' as SupportedSourceKind,
      providerCode: '',
      resourceKey: input.resourceKey,
      datasetCode: input.resourceKey,
    };
    const index = sideCounts[input.side];
    sideCounts[input.side] += 1;
    const selectedDateField = input.requiresDateField ? toText(dateFieldByInputKey[input.key]).trim() : '';
    const dateFieldLabel = selectedDateField
      ? toText(input.source?.fieldLabelMap?.[selectedDateField], selectedDateField)
      : '';
    const binding = buildRunPlanBinding(
      {
        ...source,
        sourceId: input.sourceId || source.sourceId,
        resourceKey: input.resourceKey || source.resourceKey,
        datasetCode: input.resourceKey || source.datasetCode,
      },
      dateFieldLabel,
      selectedDateField,
      input.side,
      index,
    );
    if (!binding) return null;
    return {
      ...binding,
      role_code: `${input.side}_${index + 1}`,
      input_plan_key: input.key,
      input_plan_alias: input.alias,
      input_plan_read_mode: input.readMode,
      input_plan_target_table: input.targetTable,
      input_plan_apply_biz_date_filter: input.applyBizDateFilter,
      dataset_id: input.datasetId,
      query: {
        ...asRecord(binding.query),
        resource_key: input.resourceKey || asRecord(binding.query).resource_key,
        dataset_id: input.datasetId || undefined,
      },
    };
  }).filter(Boolean) as Array<Record<string, unknown>>;

  const seen = new Set<string>();
  return bindings.filter((item) => {
    const query = asRecord(item.query);
    const key = [
      toText(item.data_source_id),
      toText(item.table_name),
      toText(item.resource_key),
      toText(item.side),
      toText(item.input_plan_alias),
      toText(item.input_plan_target_table),
      toText(query.date_field),
    ].join('::');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
