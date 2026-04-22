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
  return {
    name: state.intent.name,
    businessGoal: state.intent.businessGoal,
    leftDescription: state.preparation.leftDescription,
    rightDescription: state.preparation.rightDescription,
    procConfigMode: state.preparation.procConfigMode,
    selectedProcConfigId: state.preparation.selectedProcConfigId,
    procDraft: state.preparation.procDraft,
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
    preparation: {
      ...state.preparation,
      leftDescription: nextDraft.leftDescription,
      rightDescription: nextDraft.rightDescription,
      procConfigMode: nextDraft.procConfigMode,
      selectedProcConfigId: nextDraft.selectedProcConfigId,
      procDraft: nextDraft.procDraft,
    },
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
    preparation: {
      ...state.preparation,
      ...patch,
    },
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
  return {
    scheme_name: state.intent.name.trim(),
    description: state.intent.businessGoal.trim(),
    left_sources: state.preparation.leftSources,
    right_sources: state.preparation.rightSources,
    proc_rule_json: state.derived.procRuleJson,
    recon_rule_json: state.derived.reconRuleJson,
    scheme_meta_json: {
      business_goal: state.intent.businessGoal.trim(),
      left_description: state.preparation.leftDescription.trim(),
      right_description: state.preparation.rightDescription.trim(),
      proc_trial_status: state.derived.procTrialStatus,
      proc_trial_summary: state.derived.procTrialSummary.trim(),
      recon_trial_status: state.derived.reconTrialStatus,
      recon_trial_summary: state.derived.reconTrialSummary.trim(),
      proc_draft_text: state.preparation.procDraft.trim(),
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
