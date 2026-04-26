import type { DataSourceKind } from '../../types';

export type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';
export type ConfigMode = 'ai' | 'existing';
type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

export interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed' | 'warning';
  message: string;
  details: string[];
}

export interface SchemeSourceSelection {
  id: string;
  name: string;
  businessName?: string;
  technicalName?: string;
  keyFields?: string[];
  fieldLabelMap?: Record<string, string>;
  sourceId: string;
  sourceName: string;
  sourceKind: SupportedSourceKind;
  providerCode: string;
  description?: string;
  datasetCode?: string;
  resourceKey?: string;
  datasetKind?: string;
  schemaSummary?: Record<string, unknown>;
}

export type OutputFieldValueMode = 'source_field' | 'fixed_value' | 'formula' | 'concat';
export type OutputFieldSemanticRole = 'normal' | 'match_key' | 'compare_field' | 'time_field';

export interface OutputFieldConcatPart {
  id: string;
  datasetId: string;
  fieldName: string;
}

export interface OutputFieldDraft {
  id: string;
  outputName: string;
  semanticRole?: OutputFieldSemanticRole;
  valueMode: OutputFieldValueMode;
  sourceDatasetId: string;
  sourceField: string;
  fixedValue: string;
  formula: string;
  concatDelimiter: string;
  concatParts: OutputFieldConcatPart[];
}

export interface ReconFieldPairDraft {
  id: string;
  leftField: string;
  rightField: string;
}

export interface SchemeDraft {
  name: string;
  businessGoal: string;
  leftDescription: string;
  rightDescription: string;
  procConfigMode: ConfigMode;
  selectedProcConfigId: string;
  procDraft: string;
  procRuleJson: Record<string, unknown> | null;
  procTrialStatus: TrialStatus;
  procTrialSummary: string;
  reconConfigMode: ConfigMode;
  selectedReconConfigId: string;
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  matchKey: string;
  leftAmountField: string;
  rightAmountField: string;
  tolerance: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  reconDraft: string;
  reconRuleJson: Record<string, unknown> | null;
  reconTrialStatus: TrialStatus;
  reconTrialSummary: string;
}

export interface SchemeWizardIntentDraft {
  name: string;
  businessGoal: string;
}

export interface SchemeWizardPreparationDraft {
  leftSources: SchemeSourceSelection[];
  rightSources: SchemeSourceSelection[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
  leftDescription: string;
  rightDescription: string;
  procConfigMode: ConfigMode;
  selectedProcConfigId: string;
  procDraft: string;
}

export interface SchemeWizardReconciliationDraft {
  reconConfigMode: ConfigMode;
  selectedReconConfigId: string;
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  matchKey: string;
  leftAmountField: string;
  rightAmountField: string;
  tolerance: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  reconDraft: string;
}

export type DerivedPreviewState = 'empty' | 'current' | 'reference';

export interface SchemeWizardDerivedState {
  procRuleJson: Record<string, unknown> | null;
  procTrialStatus: TrialStatus;
  procTrialSummary: string;
  procCompatibility: CompatibilityCheckResult;
  procPreviewState: DerivedPreviewState;
  reconRuleJson: Record<string, unknown> | null;
  reconTrialStatus: TrialStatus;
  reconTrialSummary: string;
  reconCompatibility: CompatibilityCheckResult;
  reconPreviewState: DerivedPreviewState;
}

export interface SchemeWizardDraftState {
  intent: SchemeWizardIntentDraft;
  preparation: SchemeWizardPreparationDraft;
  reconciliation: SchemeWizardReconciliationDraft;
  derived: SchemeWizardDerivedState;
}

interface ProcDraftEditOptions {
  draftText: string;
  referenceSummary?: string;
  preserveReferencePreview?: boolean;
}

const OUTPUT_FIELD_SEMANTIC_ROLE_LABEL_MAP: Record<OutputFieldSemanticRole, string> = {
  normal: '普通字段',
  match_key: '匹配字段',
  compare_field: '对比字段',
  time_field: '时间字段',
};

function buildDraftId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function resolveDatasetLabelMap(
  sources: SchemeSourceSelection[],
): Map<string, { datasetName: string; fieldLabelMap: Record<string, string> }> {
  return new Map(
    sources.map((source) => [
      source.id,
      {
        datasetName: source.businessName?.trim() || source.name,
        fieldLabelMap: source.fieldLabelMap || {},
      },
    ]),
  );
}

function formatFieldReference(
  datasetId: string,
  fieldName: string,
  sourceMap: Map<string, { datasetName: string; fieldLabelMap: Record<string, string> }>,
): string {
  if (!datasetId || !fieldName) return '待补充';
  const source = sourceMap.get(datasetId);
  const datasetName = source?.datasetName || '数据集';
  const displayName = source?.fieldLabelMap?.[fieldName]?.trim();
  return displayName && displayName !== fieldName
    ? `${datasetName}.${displayName}(${fieldName})`
    : `${datasetName}.${fieldName}`;
}

export function normalizeOutputFieldSemanticRole(value: unknown): OutputFieldSemanticRole {
  const normalized = toText(value).trim();
  if (
    normalized === 'match_key'
    || normalized === 'compare_field'
    || normalized === 'time_field'
  ) {
    return normalized;
  }
  return 'normal';
}

export function resolveOutputFieldSemanticRoleLabel(role: unknown): string {
  return OUTPUT_FIELD_SEMANTIC_ROLE_LABEL_MAP[normalizeOutputFieldSemanticRole(role)];
}

export function inferOutputFieldSemanticRole(
  outputName: string,
  sourceField = '',
): OutputFieldSemanticRole {
  const combined = `${outputName} ${sourceField}`.trim();
  const normalized = combined.toLowerCase();
  if (!combined) return 'normal';
  if (
    /(时间|日期|账期|created_at|updated_at|date|time|day|dt|gmt|settle|payment|accounting|posting|entry|occurred|happened)/i.test(
      combined,
    )
  ) {
    return 'time_field';
  }
  if (
    /(匹配|主键|唯一|单号|编号|业务键|biz_key|match_key|key|id|no|code|uuid|identifier|order_id|order_no|trade_no|serial_no|record_id|ledger_id)/i.test(
      combined,
    )
  ) {
    return 'match_key';
  }
  if (
    /(对比|金额|税额|单价|费率|数量|余额|应收|应付|收入|支出|amount|amt|fee|price|money|balance|tax|cost|rate|ratio|qty|quantity|count)/i.test(
      normalized,
    )
  ) {
    return 'compare_field';
  }
  return 'normal';
}

function renderOutputFieldSummary(
  fields: OutputFieldDraft[],
  sources: SchemeSourceSelection[],
): string {
  if (fields.length === 0) return '';
  const sourceMap = resolveDatasetLabelMap(sources);
  const lines = fields.map((field, index) => {
    const outputName = field.outputName.trim() || `字段${index + 1}`;
    const roleLabel = resolveOutputFieldSemanticRoleLabel(field.semanticRole);
    const roleSuffix = normalizeOutputFieldSemanticRole(field.semanticRole) === 'normal' ? '' : `（${roleLabel}）`;
    if (field.valueMode === 'source_field') {
      return `${outputName}${roleSuffix}：取自 ${formatFieldReference(field.sourceDatasetId, field.sourceField, sourceMap)}`;
    }
    if (field.valueMode === 'fixed_value') {
      return `${outputName}${roleSuffix}：固定值 ${field.fixedValue.trim() || '--'}`;
    }
    if (field.valueMode === 'formula') {
      return `${outputName}${roleSuffix}：按公式 ${field.formula.trim() || '--'} 计算`;
    }
    const concatParts = field.concatParts
      .map((part) => formatFieldReference(part.datasetId, part.fieldName, sourceMap))
      .filter((item) => item !== '待补充');
    const concatText = concatParts.length > 0 ? concatParts.join('、') : '待补充字段';
    const delimiterText = field.concatDelimiter.trim() ? `，连接符为“${field.concatDelimiter.trim()}”` : '';
    return `${outputName}${roleSuffix}：由 ${concatText} 拼接${delimiterText}`;
  });
  return lines.join('\n');
}

function sanitizeOutputFieldDrafts(
  fields: OutputFieldDraft[],
  allowedDatasetIds: Set<string>,
): OutputFieldDraft[] {
  return fields.map((field) => {
    const sourceDatasetId = allowedDatasetIds.has(field.sourceDatasetId) ? field.sourceDatasetId : '';
    const concatParts = field.concatParts.filter((part) => allowedDatasetIds.has(part.datasetId));
    return {
      ...field,
      sourceDatasetId,
      sourceField: sourceDatasetId ? field.sourceField : '',
      concatParts,
    };
  });
}

function filterSupportedPreparationOutputFields(fields: OutputFieldDraft[]): OutputFieldDraft[] {
  return fields.filter((field) => field.valueMode === 'source_field');
}

function buildPreparationWithRenderedDescriptions(
  preparation: SchemeWizardPreparationDraft,
): SchemeWizardPreparationDraft {
  return {
    ...preparation,
    leftDescription: renderOutputFieldSummary(preparation.leftOutputFields, preparation.leftSources),
    rightDescription: renderOutputFieldSummary(preparation.rightOutputFields, preparation.rightSources),
  };
}

export function createOutputFieldConcatPart(): OutputFieldConcatPart {
  return {
    id: buildDraftId('concat'),
    datasetId: '',
    fieldName: '',
  };
}

export function createOutputFieldDraft(seedName = ''): OutputFieldDraft {
  return {
    id: buildDraftId('field'),
    outputName: seedName,
    semanticRole: inferOutputFieldSemanticRole(seedName),
    valueMode: 'source_field',
    sourceDatasetId: '',
    sourceField: '',
    fixedValue: '',
    formula: '',
    concatDelimiter: '',
    concatParts: [],
  };
}

export function createReconFieldPairDraft(
  seed: Partial<Pick<ReconFieldPairDraft, 'leftField' | 'rightField'>> = {},
): ReconFieldPairDraft {
  return {
    id: buildDraftId('recon_pair'),
    leftField: seed.leftField || '',
    rightField: seed.rightField || '',
  };
}

function cloneReconFieldPairDrafts(pairs: ReconFieldPairDraft[]): ReconFieldPairDraft[] {
  return pairs.map((pair) => ({
    id: pair.id || buildDraftId('recon_pair'),
    leftField: pair.leftField || '',
    rightField: pair.rightField || '',
  }));
}

function resolveFirstPairField(
  pairs: ReconFieldPairDraft[],
  side: 'left' | 'right',
  fallback = '',
): string {
  for (const pair of pairs) {
    const value = (side === 'left' ? pair.leftField : pair.rightField).trim();
    if (value) return value;
  }
  return fallback;
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
  return fallback;
}

function registerSourceIdentifier(map: Map<string, string>, rawKey: string | undefined, datasetId: string): void {
  const key = rawKey?.trim().toLowerCase();
  if (!key || map.has(key)) return;
  map.set(key, datasetId);
}

function buildSourceIdentifierMap(sources: SchemeSourceSelection[]): Map<string, string> {
  const identifiers = new Map<string, string>();
  sources.forEach((source) => {
    [
      source.id,
      source.name,
      source.businessName,
      source.technicalName,
      source.sourceId,
      source.sourceName,
      source.datasetCode,
      source.resourceKey,
    ].forEach((value) => registerSourceIdentifier(identifiers, value, source.id));
  });
  return identifiers;
}

function inferProcAction(step: Record<string, unknown>): string {
  const action = toText(step.action, toText(step.step)).trim();
  if (action) return action;
  const stepId = toText(step.step_id).trim().toLowerCase();
  if (stepId.startsWith('create_') || asList(asRecord(step.schema).columns).length > 0) {
    return 'create_schema';
  }
  if (asList(step.sources).length > 0 || asList(step.mappings).length > 0) {
    return 'write_dataset';
  }
  return '';
}

function resolveProcTargetFieldName(mapping: Record<string, unknown>): string {
  const targetField = toText(mapping.target_field).trim();
  if (targetField) return targetField;
  return toText(asRecord(mapping.target_field_template).template).trim();
}

function parseQuotedLiteral(expr: string): string | null {
  const text = expr.trim();
  if (text.length < 2) return null;
  if (text.startsWith('"') && text.endsWith('"')) {
    try {
      const parsed = JSON.parse(text);
      return typeof parsed === 'string' ? parsed : null;
    } catch {
      return null;
    }
  }
  if (text.startsWith("'") && text.endsWith("'")) {
    return text
      .slice(1, -1)
      .replace(/\\\\/g, '\\')
      .replace(/\\'/g, '\'')
      .replace(/\\"/g, '"')
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
      .replace(/\\t/g, '\t');
  }
  return null;
}

function parseFixedValueFromFormula(expr: string): string | null {
  const text = expr.trim();
  if (!text) return null;
  const quoted = parseQuotedLiteral(text);
  if (quoted !== null) return quoted;
  return /[(){}+*?:<>=]/.test(text) ? null : text;
}

function summarizeProcValueForEditor(value: Record<string, unknown>): string {
  const valueType = toText(value.type).trim();
  if (valueType === 'template_source') {
    const template = toText(value.template).trim();
    return template ? `template_source(${template})` : 'template_source';
  }
  if (valueType === 'function') {
    return toText(value.function, toText(value.name, 'function')).trim() || 'function';
  }
  if (valueType === 'context') {
    return `context(${toText(value.name, toText(value.context, '变量')).trim() || '变量'})`;
  }
  if (valueType === 'lookup') {
    return `lookup(${toText(value.source_alias, toText(value.table, '映射表')).trim() || '映射表'})`;
  }
  const expr = toText(value.expr, toText(value.formula)).trim();
  if (expr) return expr;
  const serialized = JSON.stringify(value);
  return serialized && serialized !== '{}' ? serialized : '自定义表达式';
}

function buildStepDatasetMap(
  stepSources: unknown[],
  sourceIdentifierMap: Map<string, string>,
): Map<string, string> {
  const datasetMap = new Map<string, string>();
  stepSources.forEach((item) => {
    const entry = asRecord(item);
    const alias = toText(entry.alias).trim();
    const table = toText(entry.table, toText(entry.name)).trim();
    const datasetId = sourceIdentifierMap.get(alias.toLowerCase()) || sourceIdentifierMap.get(table.toLowerCase());
    if (!datasetId) return;
    registerSourceIdentifier(datasetMap, alias, datasetId);
    registerSourceIdentifier(datasetMap, table, datasetId);
  });
  return datasetMap;
}

function resolveProcSourceDatasetId(
  source: Record<string, unknown>,
  stepDatasetMap: Map<string, string>,
  sourceIdentifierMap: Map<string, string>,
  fallbackDatasetId: string,
): string {
  const candidates = [
    toText(source.alias).trim(),
    toText(source.table).trim(),
    toText(source.dataset_id, toText(source.datasetId)).trim(),
    toText(source.source_id, toText(source.sourceId)).trim(),
  ].filter(Boolean);
  for (const candidate of candidates) {
    const normalized = candidate.toLowerCase();
    const datasetId = stepDatasetMap.get(normalized) || sourceIdentifierMap.get(normalized);
    if (datasetId) return datasetId;
  }
  return fallbackDatasetId;
}

function createParsedOutputFieldDraft(
  side: 'left' | 'right',
  outputName: string,
  index: number,
): OutputFieldDraft {
  const draft = createOutputFieldDraft(outputName);
  draft.id = `parsed_${side}_${index}_${outputName || 'field'}`;
  draft.outputName = outputName;
  return draft;
}

function buildOutputFieldsForProcSide(
  ruleJson: Record<string, unknown> | null | undefined,
  side: 'left' | 'right',
  sources: SchemeSourceSelection[],
): OutputFieldDraft[] {
  if (!ruleJson) return [];

  const targetTable = side === 'left' ? 'left_recon_ready' : 'right_recon_ready';
  const steps = asList(ruleJson.steps);
  const sourceIdentifierMap = buildSourceIdentifierMap(sources);
  const fallbackDatasetId = sources.length === 1 ? sources[0].id : '';
  const orderedFieldNames: string[] = [];
  const parsedFieldsByName = new Map<string, OutputFieldDraft>();

  steps.forEach((item) => {
    const step = asRecord(item);
    if (toText(step.target_table).trim() !== targetTable) return;
    if (inferProcAction(step) !== 'create_schema') return;
    asList(asRecord(step.schema).columns).forEach((column) => {
      const name = toText(asRecord(column).name).trim();
      if (name && !orderedFieldNames.includes(name)) {
        orderedFieldNames.push(name);
      }
    });
  });

  steps.forEach((item) => {
    const step = asRecord(item);
    if (toText(step.target_table).trim() !== targetTable) return;
    if (inferProcAction(step) !== 'write_dataset') return;

    const stepDatasetMap = buildStepDatasetMap(asList(step.sources), sourceIdentifierMap);
    asList(step.mappings).forEach((mappingItem, index) => {
      const mapping = asRecord(mappingItem);
      const outputName = resolveProcTargetFieldName(mapping);
      if (!outputName) return;
      if (!orderedFieldNames.includes(outputName)) {
        orderedFieldNames.push(outputName);
      }

      const value = asRecord(mapping.value);
      const valueType = toText(value.type).trim();
      const nextField = createParsedOutputFieldDraft(side, outputName, index);
      nextField.semanticRole = inferOutputFieldSemanticRole(outputName);

      if (valueType === 'source') {
        const source = asRecord(value.source);
        nextField.valueMode = 'source_field';
        nextField.sourceDatasetId = resolveProcSourceDatasetId(
          source,
          stepDatasetMap,
          sourceIdentifierMap,
          fallbackDatasetId,
        );
        nextField.sourceField = toText(source.field).trim();
        nextField.semanticRole = inferOutputFieldSemanticRole(outputName, nextField.sourceField);
      } else if (valueType === 'formula') {
        const expr = toText(value.expr, toText(value.formula)).trim();
        const fixedValue = parseFixedValueFromFormula(expr);
        if (fixedValue !== null) {
          nextField.valueMode = 'fixed_value';
          nextField.fixedValue = fixedValue;
        } else {
          nextField.valueMode = 'formula';
          nextField.formula = expr;
        }
      } else if (valueType) {
        nextField.valueMode = 'formula';
        nextField.formula = summarizeProcValueForEditor(value);
      }

      parsedFieldsByName.set(outputName, nextField);
    });
  });

  return orderedFieldNames
    .map((outputName, index) => parsedFieldsByName.get(outputName) || createParsedOutputFieldDraft(side, outputName, index))
    .filter((field) => field.outputName.trim());
}

export function deriveOutputFieldsFromProcRuleJson(
  ruleJson: Record<string, unknown> | null | undefined,
  leftSources: SchemeSourceSelection[],
  rightSources: SchemeSourceSelection[],
): {
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
} {
  return {
    leftOutputFields: buildOutputFieldsForProcSide(ruleJson, 'left', leftSources),
    rightOutputFields: buildOutputFieldsForProcSide(ruleJson, 'right', rightSources),
  };
}

function syncPreparationOutputFields(
  state: SchemeWizardDraftState,
  patch: {
    leftOutputFields?: OutputFieldDraft[];
    rightOutputFields?: OutputFieldDraft[];
  },
): SchemeWizardDraftState {
  const leftOutputFields = patch.leftOutputFields
    ? sanitizeOutputFieldDrafts(
        filterSupportedPreparationOutputFields(patch.leftOutputFields),
        new Set(state.preparation.leftSources.map((source) => source.id)),
      )
    : state.preparation.leftOutputFields;
  const rightOutputFields = patch.rightOutputFields
    ? sanitizeOutputFieldDrafts(
        filterSupportedPreparationOutputFields(patch.rightOutputFields),
        new Set(state.preparation.rightSources.map((source) => source.id)),
      )
    : state.preparation.rightOutputFields;
  return {
    ...state,
    preparation: buildPreparationWithRenderedDescriptions({
      ...state.preparation,
      leftOutputFields,
      rightOutputFields,
    }),
  };
}

export function hydratePreparationOutputFieldsFromProcRule(
  state: SchemeWizardDraftState,
  ruleJson: Record<string, unknown> | null | undefined,
): SchemeWizardDraftState {
  const { leftOutputFields, rightOutputFields } = deriveOutputFieldsFromProcRuleJson(
    ruleJson,
    state.preparation.leftSources,
    state.preparation.rightSources,
  );
  if (leftOutputFields.length === 0 && rightOutputFields.length === 0) {
    return state;
  }
  return syncPreparationOutputFields(state, {
    leftOutputFields,
    rightOutputFields,
  });
}

export function createEmptyCompatibilityState(): CompatibilityCheckResult {
  return {
    status: 'idle',
    message: '等待校验',
    details: [],
  };
}

export function createEmptySchemeWizardDerivedState(): SchemeWizardDerivedState {
  return {
    procRuleJson: null,
    procTrialStatus: 'idle',
    procTrialSummary: '',
    procCompatibility: createEmptyCompatibilityState(),
    procPreviewState: 'empty',
    reconRuleJson: null,
    reconTrialStatus: 'idle',
    reconTrialSummary: '',
    reconCompatibility: createEmptyCompatibilityState(),
    reconPreviewState: 'empty',
  };
}

export function createEmptySchemeWizardDraftState(): SchemeWizardDraftState {
  return {
    intent: {
      name: '',
      businessGoal: '',
    },
    preparation: {
      leftSources: [],
      rightSources: [],
      leftOutputFields: [],
      rightOutputFields: [],
      leftDescription: '',
      rightDescription: '',
      procConfigMode: 'ai',
      selectedProcConfigId: '',
      procDraft: '',
    },
    reconciliation: {
      reconConfigMode: 'ai',
      selectedReconConfigId: '',
      reconRuleName: '',
      matchFieldPairs: [],
      compareFieldPairs: [],
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
      reconDraft: '',
    },
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function buildLegacySchemeDraftSnapshot(state: SchemeWizardDraftState): SchemeDraft {
  const preparation = buildPreparationWithRenderedDescriptions(state.preparation);
  const matchFieldPairs = cloneReconFieldPairDrafts(state.reconciliation.matchFieldPairs);
  const compareFieldPairs = cloneReconFieldPairDrafts(state.reconciliation.compareFieldPairs);
  return {
    name: state.intent.name,
    businessGoal: state.intent.businessGoal,
    leftDescription: preparation.leftDescription,
    rightDescription: preparation.rightDescription,
    procConfigMode: preparation.procConfigMode,
    selectedProcConfigId: preparation.selectedProcConfigId,
    procDraft: preparation.procDraft,
    procRuleJson: state.derived.procRuleJson,
    procTrialStatus: state.derived.procTrialStatus,
    procTrialSummary: state.derived.procTrialSummary,
    reconConfigMode: state.reconciliation.reconConfigMode,
    selectedReconConfigId: state.reconciliation.selectedReconConfigId,
    reconRuleName: state.reconciliation.reconRuleName,
    matchFieldPairs,
    compareFieldPairs,
    matchKey: resolveFirstPairField(matchFieldPairs, 'left', state.reconciliation.matchKey),
    leftAmountField: resolveFirstPairField(compareFieldPairs, 'left', state.reconciliation.leftAmountField),
    rightAmountField: resolveFirstPairField(compareFieldPairs, 'right', state.reconciliation.rightAmountField),
    tolerance: state.reconciliation.tolerance,
    leftTimeSemantic: state.reconciliation.leftTimeSemantic,
    rightTimeSemantic: state.reconciliation.rightTimeSemantic,
    reconDraft: state.reconciliation.reconDraft,
    reconRuleJson: state.derived.reconRuleJson,
    reconTrialStatus: state.derived.reconTrialStatus,
    reconTrialSummary: state.derived.reconTrialSummary,
  };
}

export function applyLegacySchemeDraftSnapshot(
  state: SchemeWizardDraftState,
  nextDraft: SchemeDraft,
): SchemeWizardDraftState {
  return {
    ...state,
    intent: {
      name: nextDraft.name,
      businessGoal: nextDraft.businessGoal,
    },
    preparation: buildPreparationWithRenderedDescriptions({
      ...state.preparation,
      leftDescription: nextDraft.leftDescription,
      rightDescription: nextDraft.rightDescription,
      procConfigMode: nextDraft.procConfigMode,
      selectedProcConfigId: nextDraft.selectedProcConfigId,
      procDraft: nextDraft.procDraft,
    }),
    reconciliation: {
      ...state.reconciliation,
      reconConfigMode: nextDraft.reconConfigMode,
      selectedReconConfigId: nextDraft.selectedReconConfigId,
      reconRuleName: nextDraft.reconRuleName,
      matchFieldPairs: cloneReconFieldPairDrafts(nextDraft.matchFieldPairs),
      compareFieldPairs: cloneReconFieldPairDrafts(nextDraft.compareFieldPairs),
      matchKey: nextDraft.matchKey,
      leftAmountField: nextDraft.leftAmountField,
      rightAmountField: nextDraft.rightAmountField,
      tolerance: nextDraft.tolerance,
      leftTimeSemantic: nextDraft.leftTimeSemantic,
      rightTimeSemantic: nextDraft.rightTimeSemantic,
      reconDraft: nextDraft.reconDraft,
    },
    derived: {
      ...state.derived,
      procRuleJson: nextDraft.procRuleJson,
      procTrialStatus: nextDraft.procTrialStatus,
      procTrialSummary: nextDraft.procTrialSummary,
      reconRuleJson: nextDraft.reconRuleJson,
      reconTrialStatus: nextDraft.reconTrialStatus,
      reconTrialSummary: nextDraft.reconTrialSummary,
    },
  };
}

export function updateIntentDraft(
  state: SchemeWizardDraftState,
  patch: Partial<SchemeWizardIntentDraft>,
): SchemeWizardDraftState {
  return {
    ...state,
    intent: {
      ...state.intent,
      ...patch,
    },
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function updatePreparationDraft(
  state: SchemeWizardDraftState,
  patch: Partial<SchemeWizardPreparationDraft>,
): SchemeWizardDraftState {
  return {
    ...state,
    preparation: buildPreparationWithRenderedDescriptions({
      ...state.preparation,
      ...patch,
    }),
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function applyPreparationSources(
  state: SchemeWizardDraftState,
  side: 'left' | 'right',
  sources: SchemeSourceSelection[],
): SchemeWizardDraftState {
  const leftSources = side === 'left' ? sources : state.preparation.leftSources;
  const rightSources = side === 'right' ? sources : state.preparation.rightSources;
  const leftOutputFields = sanitizeOutputFieldDrafts(
    state.preparation.leftOutputFields,
    new Set(leftSources.map((source) => source.id)),
  );
  const rightOutputFields = sanitizeOutputFieldDrafts(
    state.preparation.rightOutputFields,
    new Set(rightSources.map((source) => source.id)),
  );
  return {
    ...state,
    preparation: buildPreparationWithRenderedDescriptions({
      ...state.preparation,
      leftSources,
      rightSources,
      leftOutputFields,
      rightOutputFields,
    }),
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function applyPreparationOutputFields(
  state: SchemeWizardDraftState,
  side: 'left' | 'right',
  fields: OutputFieldDraft[],
): SchemeWizardDraftState {
  const allowedDatasetIds = new Set(
    (side === 'left' ? state.preparation.leftSources : state.preparation.rightSources).map((source) => source.id),
  );
  return {
    ...state,
    preparation: buildPreparationWithRenderedDescriptions({
      ...state.preparation,
      leftOutputFields:
        side === 'left'
          ? sanitizeOutputFieldDrafts(filterSupportedPreparationOutputFields(fields), allowedDatasetIds)
          : state.preparation.leftOutputFields,
      rightOutputFields:
        side === 'right'
          ? sanitizeOutputFieldDrafts(filterSupportedPreparationOutputFields(fields), allowedDatasetIds)
          : state.preparation.rightOutputFields,
    }),
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function switchProcConfigMode(
  state: SchemeWizardDraftState,
  mode: ConfigMode,
): SchemeWizardDraftState {
  return {
    ...state,
    preparation: {
      ...state.preparation,
      procConfigMode: mode,
      selectedProcConfigId: mode === 'existing' ? state.preparation.selectedProcConfigId : '',
    },
    reconciliation: {
      ...state.reconciliation,
      reconDraft: '',
      reconRuleName: '',
      matchFieldPairs: [],
      compareFieldPairs: [],
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
      selectedReconConfigId: '',
    },
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function clearProcConfigSelection(state: SchemeWizardDraftState): SchemeWizardDraftState {
  return {
    ...state,
    preparation: {
      ...state.preparation,
      selectedProcConfigId: '',
      procDraft: '',
    },
    reconciliation: {
      ...state.reconciliation,
      reconDraft: '',
      reconRuleName: '',
      matchFieldPairs: [],
      compareFieldPairs: [],
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
      selectedReconConfigId: '',
    },
    derived: createEmptySchemeWizardDerivedState(),
  };
}

export function applyExistingProcConfig(
  state: SchemeWizardDraftState,
  payload: {
    configId: string;
    draftText: string;
    ruleJson: Record<string, unknown> | null;
  },
): SchemeWizardDraftState {
  return {
    ...state,
    preparation: {
      ...state.preparation,
      procConfigMode: 'existing',
      selectedProcConfigId: payload.configId,
      procDraft: payload.draftText,
    },
    reconciliation: {
      ...state.reconciliation,
      reconDraft: '',
      reconRuleName: '',
      matchFieldPairs: [],
      compareFieldPairs: [],
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
      selectedReconConfigId: '',
    },
    derived: {
      ...createEmptySchemeWizardDerivedState(),
      procRuleJson: payload.ruleJson,
    },
  };
}

export function applyProcDraftEdit(
  state: SchemeWizardDraftState,
  options: ProcDraftEditOptions,
): SchemeWizardDraftState {
  return {
    ...state,
    preparation: {
      ...state.preparation,
      procDraft: options.draftText,
    },
    reconciliation: {
      ...state.reconciliation,
      reconDraft: '',
      reconRuleName: '',
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
      selectedReconConfigId: '',
    },
    derived: {
      ...createEmptySchemeWizardDerivedState(),
      procTrialStatus: options.preserveReferencePreview ? 'needs_adjustment' : 'idle',
      procTrialSummary: options.preserveReferencePreview ? options.referenceSummary || '' : '',
      procPreviewState: options.preserveReferencePreview ? 'reference' : 'empty',
    },
  };
}

export function updateReconciliationDraft(
  state: SchemeWizardDraftState,
  patch: Partial<SchemeWizardReconciliationDraft>,
): SchemeWizardDraftState {
  return {
    ...state,
    reconciliation: {
      ...state.reconciliation,
      ...patch,
    },
    derived: {
      ...state.derived,
      reconRuleJson: null,
      reconTrialStatus: 'idle',
      reconTrialSummary: '',
      reconCompatibility: createEmptyCompatibilityState(),
      reconPreviewState: 'empty',
    },
  };
}

export function switchReconConfigMode(
  state: SchemeWizardDraftState,
  mode: ConfigMode,
): SchemeWizardDraftState {
  return {
    ...state,
    reconciliation: {
      ...state.reconciliation,
      reconConfigMode: mode,
      selectedReconConfigId: mode === 'existing' ? state.reconciliation.selectedReconConfigId : '',
      reconRuleName: '',
      matchFieldPairs: [],
      compareFieldPairs: [],
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
    },
    derived: {
      ...state.derived,
      reconRuleJson: null,
      reconTrialStatus: 'idle',
      reconTrialSummary: '',
      reconCompatibility: createEmptyCompatibilityState(),
      reconPreviewState: 'empty',
    },
  };
}

export function clearReconConfigSelection(state: SchemeWizardDraftState): SchemeWizardDraftState {
  return {
    ...state,
    reconciliation: {
      ...state.reconciliation,
      selectedReconConfigId: '',
      reconDraft: '',
      reconRuleName: '',
      matchFieldPairs: [],
      compareFieldPairs: [],
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
    },
    derived: {
      ...state.derived,
      reconRuleJson: null,
      reconTrialStatus: 'idle',
      reconTrialSummary: '',
      reconCompatibility: createEmptyCompatibilityState(),
      reconPreviewState: 'empty',
    },
  };
}

export function applyExistingReconConfig(
  state: SchemeWizardDraftState,
  payload: {
    configId: string;
    draftText: string;
    ruleJson: Record<string, unknown> | null;
    reconRuleName?: string;
    matchFieldPairs?: ReconFieldPairDraft[];
    compareFieldPairs?: ReconFieldPairDraft[];
    matchKey: string;
    leftAmountField: string;
    rightAmountField: string;
    leftTimeSemantic?: string;
    rightTimeSemantic?: string;
    tolerance: string;
  },
): SchemeWizardDraftState {
  return {
    ...state,
    reconciliation: {
      ...state.reconciliation,
      reconConfigMode: 'existing',
      selectedReconConfigId: payload.configId,
      reconDraft: payload.draftText,
      reconRuleName: payload.reconRuleName || state.reconciliation.reconRuleName,
      matchFieldPairs: cloneReconFieldPairDrafts(
        payload.matchFieldPairs
        || (payload.matchKey ? [createReconFieldPairDraft({ leftField: payload.matchKey, rightField: payload.matchKey })] : []),
      ),
      compareFieldPairs: cloneReconFieldPairDrafts(
        payload.compareFieldPairs
        || (
          payload.leftAmountField || payload.rightAmountField
            ? [createReconFieldPairDraft({ leftField: payload.leftAmountField, rightField: payload.rightAmountField })]
            : []
        ),
      ),
      matchKey: payload.matchKey,
      leftAmountField: payload.leftAmountField,
      rightAmountField: payload.rightAmountField,
      leftTimeSemantic: payload.leftTimeSemantic ?? state.reconciliation.leftTimeSemantic,
      rightTimeSemantic: payload.rightTimeSemantic ?? state.reconciliation.rightTimeSemantic,
      tolerance: payload.tolerance,
    },
    derived: {
      ...state.derived,
      reconRuleJson: payload.ruleJson,
      reconTrialStatus: 'idle',
      reconTrialSummary: '',
      reconCompatibility: createEmptyCompatibilityState(),
      reconPreviewState: 'empty',
    },
  };
}

export function updateDerivedDraft(
  state: SchemeWizardDraftState,
  patch: Partial<SchemeWizardDerivedState>,
): SchemeWizardDraftState {
  return {
    ...state,
    derived: {
      ...state.derived,
      ...patch,
    },
  };
}

export function buildSchemeCreatePayloadDraft(state: SchemeWizardDraftState) {
  const preparation = buildPreparationWithRenderedDescriptions(state.preparation);
  const matchFieldPairs = cloneReconFieldPairDrafts(state.reconciliation.matchFieldPairs);
  const compareFieldPairs = cloneReconFieldPairDrafts(state.reconciliation.compareFieldPairs);
  const matchKey = resolveFirstPairField(matchFieldPairs, 'left', state.reconciliation.matchKey).trim();
  const leftAmountField = resolveFirstPairField(
    compareFieldPairs,
    'left',
    state.reconciliation.leftAmountField,
  ).trim();
  const rightAmountField = resolveFirstPairField(
    compareFieldPairs,
    'right',
    state.reconciliation.rightAmountField,
  ).trim();
  return {
    scheme_name: state.intent.name.trim(),
    description: state.intent.businessGoal.trim(),
    left_sources: preparation.leftSources,
    right_sources: preparation.rightSources,
    proc_rule_json: state.derived.procRuleJson,
    recon_rule_json: state.derived.reconRuleJson,
    scheme_meta_json: {
      business_goal: state.intent.businessGoal.trim(),
      left_description: preparation.leftDescription.trim(),
      right_description: preparation.rightDescription.trim(),
      left_output_fields: preparation.leftOutputFields,
      right_output_fields: preparation.rightOutputFields,
      proc_trial_status: state.derived.procTrialStatus,
      proc_trial_summary: state.derived.procTrialSummary.trim(),
      recon_trial_status: state.derived.reconTrialStatus,
      recon_trial_summary: state.derived.reconTrialSummary.trim(),
      proc_draft_text: preparation.procDraft.trim(),
      recon_draft_text: state.reconciliation.reconDraft.trim(),
      recon_rule_name: state.reconciliation.reconRuleName.trim(),
      match_field_pairs: matchFieldPairs.map((pair) => ({
        id: pair.id,
        left_field: pair.leftField.trim(),
        right_field: pair.rightField.trim(),
      })),
      compare_field_pairs: compareFieldPairs.map((pair) => ({
        id: pair.id,
        left_field: pair.leftField.trim(),
        right_field: pair.rightField.trim(),
      })),
      match_key: matchKey,
      left_amount_field: leftAmountField,
      right_amount_field: rightAmountField,
      tolerance: state.reconciliation.tolerance.trim(),
      left_time_semantic: state.reconciliation.leftTimeSemantic.trim(),
      right_time_semantic: state.reconciliation.rightTimeSemantic.trim(),
    },
  };
}
