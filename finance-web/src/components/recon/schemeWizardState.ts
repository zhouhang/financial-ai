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

export interface OutputFieldConcatPart {
  id: string;
  datasetId: string;
  fieldName: string;
}

export interface OutputFieldDraft {
  id: string;
  outputName: string;
  valueMode: OutputFieldValueMode;
  sourceDatasetId: string;
  sourceField: string;
  fixedValue: string;
  formula: string;
  concatDelimiter: string;
  concatParts: OutputFieldConcatPart[];
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

function renderOutputFieldSummary(
  fields: OutputFieldDraft[],
  sources: SchemeSourceSelection[],
): string {
  if (fields.length === 0) return '';
  const sourceMap = resolveDatasetLabelMap(sources);
  const lines = fields.map((field, index) => {
    const outputName = field.outputName.trim() || `字段${index + 1}`;
    if (field.valueMode === 'source_field') {
      return `${outputName}：取自 ${formatFieldReference(field.sourceDatasetId, field.sourceField, sourceMap)}`;
    }
    if (field.valueMode === 'fixed_value') {
      return `${outputName}：固定值 ${field.fixedValue.trim() || '--'}`;
    }
    if (field.valueMode === 'formula') {
      return `${outputName}：按公式 ${field.formula.trim() || '--'} 计算`;
    }
    const concatParts = field.concatParts
      .map((part) => formatFieldReference(part.datasetId, part.fieldName, sourceMap))
      .filter((item) => item !== '待补充');
    const concatText = concatParts.length > 0 ? concatParts.join('、') : '待补充字段';
    const delimiterText = field.concatDelimiter.trim() ? `，连接符为“${field.concatDelimiter.trim()}”` : '';
    return `${outputName}：由 ${concatText} 拼接${delimiterText}`;
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
    valueMode: 'source_field',
    sourceDatasetId: '',
    sourceField: '',
    fixedValue: '',
    formula: '',
    concatDelimiter: '',
    concatParts: [],
  };
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
    matchKey: state.reconciliation.matchKey,
    leftAmountField: state.reconciliation.leftAmountField,
    rightAmountField: state.reconciliation.rightAmountField,
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
          ? sanitizeOutputFieldDrafts(fields, allowedDatasetIds)
          : state.preparation.leftOutputFields,
      rightOutputFields:
        side === 'right'
          ? sanitizeOutputFieldDrafts(fields, allowedDatasetIds)
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
    matchKey: string;
    leftAmountField: string;
    rightAmountField: string;
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
      matchKey: payload.matchKey,
      leftAmountField: payload.leftAmountField,
      rightAmountField: payload.rightAmountField,
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
      match_key: state.reconciliation.matchKey.trim(),
      left_amount_field: state.reconciliation.leftAmountField.trim(),
      right_amount_field: state.reconciliation.rightAmountField.trim(),
      tolerance: state.reconciliation.tolerance.trim(),
      left_time_semantic: state.reconciliation.leftTimeSemantic.trim(),
      right_time_semantic: state.reconciliation.rightTimeSemantic.trim(),
    },
  };
}
