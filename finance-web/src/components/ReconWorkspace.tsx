import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type SetStateAction } from 'react';
import {
  AlertCircle,
  Check,
  Copy,
  Eye,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';
import { collaborationProviderLabel } from '../collaborationChannelConfig';
import { normalizeChannelConfig } from '../collaborationChannelDrafts';
import { sourceKindLabel } from '../dataSourceConfig';
import type {
  CollaborationChannelListItem,
  CollaborationProvider,
  DataSourceKind,
  ReconWorkspaceMode,
  UserTaskRule,
} from '../types';
import { fetchReconAutoApi } from './recon/autoApi';
import SchemeWizardIntentStep from './recon/SchemeWizardIntentStep';
import ReconWorkspaceHeader from './recon/ReconWorkspaceHeader';
import SchemeWizardReconStep from './recon/SchemeWizardReconStep';
import {
  applyPreparationOutputFields,
  applyPreparationSources,
  applyLegacySchemeDraftSnapshot,
  buildLegacySchemeDraftSnapshot,
  buildSchemeCreatePayloadDraft,
  createOutputFieldDraft,
  createEmptySchemeWizardDraftState,
  createReconFieldPairDraft,
  hydratePreparationOutputFieldsFromProcRule,
  inferOutputFieldSemanticRole,
  normalizeOutputFieldSemanticRole,
  type OutputFieldDraft,
  type OutputFieldSemanticRole,
  type ReconFieldPairDraft,
  updateDerivedDraft,
  updateIntentDraft,
  updateReconciliationDraft,
  type SchemeWizardDraftState,
} from './recon/schemeWizardState';
import SchemeWizardTargetProcStep, {
  type AiProcSide,
  type AiProcSideDraft,
  type ProcBuildMode,
} from './recon/SchemeWizardTargetProcStep';
import {
  applyRuleGenerationEventToDraft,
  buildAiSideInputPlanJson,
  buildAiSideProcRuleJson,
  buildRuleGenerationSourcePayloads,
  createDefaultRuleGenerationNodeTraces,
  createEmptyAiProcSideDrafts,
  normalizeAiOutputFields,
  parseSseFrame,
} from './recon/ruleGenerationState';
import {
  buildRunPlanBindings,
  extractRunPlanInputDatasets,
  type RunPlanInputDatasetDraft,
} from './recon/runPlanBindings';
import {
  cn,
  type ReconCenterRunItem,
  type ReconCenterTab,
  type ReconRunExceptionDetail,
  type ReconSchemeListItem,
  type ReconTaskListItem,
} from './recon/types';

interface ReconWorkspaceProps {
  selectedTask: UserTaskRule;
  mode?: ReconWorkspaceMode;
  availableRules?: UserTaskRule[];
  selectedRuleCode?: string | null;
  executionMode?: 'upload' | 'data_source';
  authToken?: string | null;
  onSelectRule?: (ruleCode: string) => void;
  onChangeExecutionMode?: (mode: 'upload' | 'data_source') => void;
  onOpenDataConnections?: () => void;
  onOpenCollaborationChannels?: (provider?: CollaborationProvider) => void;
  onSchemeCreated?: () => void;
  children?: ReactNode;
}

type CenterModalState =
  | { kind: 'create-scheme' }
  | { kind: 'create-plan'; scheme: ReconSchemeListItem | null }
  | { kind: 'scheme-detail'; scheme: ReconSchemeListItem }
  | { kind: 'task-detail'; task: ReconTaskListItem }
  | { kind: 'run-exceptions'; run: ReconCenterRunItem };

type SchemeWizardStep = 1 | 2 | 3;
type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';
type ConfigMode = 'ai' | 'existing';
type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

interface SchemeSourceOption {
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

interface SchemeSourceDraft {
  id: string;
  name: string;
  businessName?: string;
  technicalName?: string;
  fieldLabelMap?: Record<string, string>;
  keyFields?: string[];
  schemaSummary?: Record<string, unknown>;
  sourceId?: string;
  sourceName?: string;
  sourceKind: SupportedSourceKind;
  providerCode: string;
  datasetCode?: string;
  resourceKey?: string;
  datasetKind?: string;
}

interface SchemeDraft {
  name: string;
  businessGoal: string;
  leftDescription: string;
  rightDescription: string;
  procConfigMode: ConfigMode;
  selectedProcConfigId: string;
  procDraft: string;
  procRuleJson: Record<string, unknown> | null;
  inputPlanJson: Record<string, unknown> | null;
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

interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed' | 'warning';
  message: string;
  details: string[];
}

type PreviewCellValue = string | number | null;

interface PreviewTableRow {
  [key: string]: PreviewCellValue;
}

interface SourcePreviewBlock {
  sourceId: string;
  sourceName: string;
  side: 'left' | 'right';
  fieldLabelMap?: Record<string, string>;
  sampleOrigin: string;
  sampleOriginLabel: string;
  sampleOriginHint?: string;
  snapshotId?: string;
  rows: PreviewTableRow[];
}

interface PreparedPreviewBlock {
  side: 'left' | 'right';
  title: string;
  fieldLabelMap?: Record<string, string>;
  rows: PreviewTableRow[];
}

interface ProcTrialPreview {
  status: TrialStatus;
  summary: string;
  rawSources: SourcePreviewBlock[];
  preparedOutputs: PreparedPreviewBlock[];
  validations: string[];
}

interface ReconResultRow {
  matchFields: string;
  leftCompareFields: string;
  rightCompareFields: string;
  result: string;
}

interface ReconTrialPreview {
  status: TrialStatus;
  summary: string;
  leftRows: PreviewTableRow[];
  rightRows: PreviewTableRow[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
  resultFieldLabelMap?: Record<string, string>;
  results: ReconResultRow[];
  resultSummary?: {
    matched?: number;
    unmatchedLeft?: number;
    unmatchedRight?: number;
    amountDiff?: number;
    diffCount?: number;
  };
}

interface ParsedReconDraftConfig {
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  matchKey: string;
  leftAmountField: string;
  rightAmountField: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  tolerance: string;
}

interface ReconFieldOption {
  value: string;
  label: string;
}

type PreviewColumnOriginTone = 'sky' | 'emerald' | 'amber' | 'violet';

interface PreviewColumnHintMeta {
  badge?: string;
  helper?: string;
  tone?: PreviewColumnOriginTone;
}

interface PlanDraft {
  schemeCode: string;
  scheduleType: 'daily' | 'weekly' | 'monthly';
  scheduleHour: string;
  scheduleMinute: string;
  scheduleDayOfWeek: string;
  scheduleDayOfMonth: string;
  bizDateOffset: string;
  dateFieldByInputKey: Record<string, string>;
  channelConfigId: string;
  ownerSummary: string;
  ownerIdentifier: string;
}

interface OwnerCandidate {
  display_name: string;
  identifier: string;
  organization: string;
  departments: string[];
  mobile_masked: string;
  disambiguation_label: string;
}

interface SchemeMetaSummary {
  businessGoal: string;
  leftSources: SchemeSourceDraft[];
  rightSources: SchemeSourceDraft[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
  leftOutputFieldLabelMap: Record<string, string>;
  rightOutputFieldLabelMap: Record<string, string>;
  leftDescription: string;
  rightDescription: string;
  procRuleName: string;
  procTrialStatus: TrialStatus;
  procTrialSummary: string;
  reconTrialStatus: TrialStatus;
  reconTrialSummary: string;
  procDraftText: string;
  reconDraftText: string;
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  matchKey: string;
  leftAmountField: string;
  rightAmountField: string;
  tolerance: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  inputPlanJson?: Record<string, unknown> | null;
}

const SCHEME_LIST_TEMPLATE =
  'minmax(0,1.6fr) minmax(220px,1fr) minmax(220px,1fr) minmax(268px,auto)';
const TASK_LIST_TEMPLATE =
  'minmax(0,2.3fr) minmax(200px,1.1fr) minmax(180px,0.9fr) minmax(120px,0.7fr) minmax(280px,auto)';
const RUN_LIST_TEMPLATE =
  'minmax(0,2.9fr) minmax(120px,0.7fr) minmax(120px,0.7fr) minmax(188px,auto)';

const PREPARED_OUTPUT_FIELD_LABEL_MAP: Record<string, string> = {
  biz_key: '业务主键',
  amount: '金额',
  biz_date: '业务日期',
  source_name: '来源名称',
  source_count: '来源数量',
  source_side: '输出侧',
  source_hint: '来源提示',
};

const RECON_RESULT_FIELD_LABEL_MAP: Record<string, string> = {
  match_fields: '匹配字段',
  left_compare_fields: '左侧对比字段',
  right_compare_fields: '右侧对比字段',
  result: '对账结果',
};

const SCHEME_WIZARD_STEPS: Array<{ id: SchemeWizardStep; title: string; description: string }> = [
  { id: 1, title: '方案目标', description: '先说明这次对账要解决什么问题' },
  { id: 2, title: '数据整理', description: '选择左右数据并整理成可对账结构' },
  { id: 3, title: '对账规则', description: '基于整理后的结构生成、修正规则并保存方案' },
];

const EMPTY_PLAN_DRAFT: PlanDraft = {
  schemeCode: '',
  scheduleType: 'daily',
  scheduleHour: '09',
  scheduleMinute: '30',
  scheduleDayOfWeek: '1',
  scheduleDayOfMonth: '1',
  bizDateOffset: 'T-1',
  dateFieldByInputKey: {},
  channelConfigId: '',
  ownerSummary: '',
  ownerIdentifier: '',
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
  return fallback;
}

function normalizeFieldLabelMap(value: unknown): Record<string, string> | undefined {
  const record = asRecord(value);
  const entries = Object.entries(record)
    .map(([key, raw]) => [key.trim(), toText(raw).trim()] as const)
    .filter(([key, label]) => Boolean(key && label));
  if (entries.length === 0) {
    return undefined;
  }
  return Object.fromEntries(entries);
}

function normalizeStringList(value: unknown): string[] {
  return asList(value).map((item) => toText(item).trim()).filter(Boolean);
}

function extractMobileTail(maskedMobile: string): string {
  const match = maskedMobile.match(/(\d{4})$/);
  return match?.[1] || '';
}

function formatOwnerCandidateHint(candidate: OwnerCandidate): string {
  const departments = Array.isArray(candidate.departments)
    ? candidate.departments.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const mobileTail = extractMobileTail(candidate.mobile_masked || '');
  const hints = [
    departments.length > 0 ? `部门：${departments.join(' / ')}` : '',
    mobileTail ? `手机号后四位：${mobileTail}` : '',
  ].filter(Boolean);
  return hints.join(' · ') || candidate.disambiguation_label || candidate.identifier;
}

function normalizeOutputFieldDrafts(value: unknown): OutputFieldDraft[] {
  return asList(value)
    .map((item, index) => {
      const record = asRecord(item);
      const valueMode = toText(record.value_mode ?? record.valueMode, 'source_field');
      const concatParts = asList(record.concat_parts ?? record.concatParts)
        .map((part, partIndex) => {
          const partRecord = asRecord(part);
          return {
            id: toText(partRecord.id, `concat_${index}_${partIndex}`),
            datasetId: toText(partRecord.dataset_id ?? partRecord.datasetId),
            fieldName: toText(partRecord.field_name ?? partRecord.fieldName),
          };
        });
      return {
        id: toText(record.id, `field_${index}`),
        outputName: toText(record.output_name ?? record.outputName),
        semanticRole: normalizeOutputFieldSemanticRole(
          record.semantic_role
            ?? record.semanticRole
            ?? inferOutputFieldSemanticRole(
              toText(record.output_name ?? record.outputName),
              toText(record.source_field ?? record.sourceField),
            ),
        ),
        valueMode:
          valueMode === 'fixed_value' || valueMode === 'formula' || valueMode === 'concat'
            ? valueMode
            : 'source_field',
        sourceDatasetId: toText(record.source_dataset_id ?? record.sourceDatasetId),
        sourceField: toText(record.source_field ?? record.sourceField),
        fixedValue: toText(record.fixed_value ?? record.fixedValue),
        formula: toText(record.formula),
        concatDelimiter: toText(record.concat_delimiter ?? record.concatDelimiter),
        concatParts,
      } satisfies OutputFieldDraft;
    })
    .filter((item) => item.outputName || item.sourceDatasetId || item.sourceField || item.fixedValue || item.formula || item.concatParts.length > 0);
}

function mergeFieldLabelMaps(
  ...maps: Array<Record<string, string> | undefined>
): Record<string, string> | undefined {
  const merged: Record<string, string> = {};
  maps.forEach((map) => {
    if (!map) return;
    Object.entries(map).forEach(([key, value]) => {
      if (!key || !value || merged[key]) return;
      merged[key] = value;
    });
  });
  return Object.keys(merged).length > 0 ? merged : undefined;
}

function resolveWizardDraftText(
  draftText: unknown,
  ruleSummary: unknown,
  fallback = '',
): string {
  const resolvedDraftText = toText(draftText).trim();
  if (resolvedDraftText) return resolvedDraftText;
  const resolvedRuleSummary = toText(ruleSummary).trim();
  return resolvedRuleSummary || fallback;
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

function humanizeProcTargetTable(targetTable: string): string {
  const normalized = targetTable.trim();
  if (normalized === 'left_recon_ready') return '左侧输出结果表';
  if (normalized === 'right_recon_ready') return '右侧输出结果表';
  return normalized || '输出结果表';
}

function humanizeProcDescription(text: string): string {
  return text
    .replaceAll('left_recon_ready', '左侧输出结果表')
    .replaceAll('right_recon_ready', '右侧输出结果表')
    .replaceAll('biz_key', '业务主键')
    .replaceAll('amount', '金额')
    .replaceAll('biz_date', '业务日期')
    .replaceAll('source_name', '来源名称')
    .trim();
}

function humanizeProcRoleDesc(roleDesc: string): string {
  const normalized = humanizeProcDescription(roleDesc);
  if (!normalized) return '整理规则说明';
  if (/(规则生成器|draft proc|fallback proc|tally 财务 ai)/i.test(normalized)) {
    return '整理规则说明';
  }
  return normalized;
}

function inferProcAction(step: Record<string, unknown>): string {
  const action = toText(step.step || step.action).trim();
  if (action) return action;
  const stepId = toText(step.step_id).trim().toLowerCase();
  if (stepId.startsWith('create_') || asRecord(step.schema).columns) return 'create_schema';
  if (Array.isArray(step.sources) || Array.isArray(step.mappings)) return 'write_dataset';
  return '';
}

function formatProcFieldName(field: string): string {
  return humanizeProcDescription(field || '').trim() || field || '--';
}

function summarizeProcColumns(step: Record<string, unknown>): string[] {
  const schema = asRecord(step.schema);
  const columns = Array.isArray(schema.columns) ? schema.columns : [];
  const columnNames = columns
    .map((item) => formatProcFieldName(toText(asRecord(item).name)))
    .filter(Boolean);
  if (columnNames.length === 0) return [];

  const lines = [`输出字段：${columnNames.join('、')}。`];
  const primaryKeys = Array.isArray(schema.primary_key) ? schema.primary_key.map((item) => formatProcFieldName(toText(item))).filter(Boolean) : [];
  if (primaryKeys.length > 0) {
    lines.push(`主键字段：${primaryKeys.join('、')}。`);
  }
  return lines;
}

function summarizeProcMatch(step: Record<string, unknown>, aliasNameMap: Map<string, string>): string[] {
  const match = asRecord(step.match);
  const sources = Array.isArray(match.sources) ? match.sources : [];
  const segments = sources
    .map((item) => {
      const source = asRecord(item);
      const alias = toText(source.alias).trim();
      const sourceName = aliasNameMap.get(alias) || alias || '当前数据集';
      const keys = Array.isArray(source.keys) ? source.keys : [];
      const pairs = keys
        .map((entry) => {
          const key = asRecord(entry);
          const sourceField = formatProcFieldName(toText(key.field));
          const targetField = formatProcFieldName(toText(key.target_field));
          if (!sourceField || !targetField) return '';
          return `${sourceField} -> ${targetField}`;
        })
        .filter(Boolean);
      if (pairs.length === 0) return '';
      return `${sourceName}：${pairs.join('；')}`;
    })
    .filter(Boolean);

  return segments.length > 0 ? [`主键/匹配映射：${segments.join('；')}。`] : [];
}

function summarizeProcMappings(step: Record<string, unknown>, aliasNameMap: Map<string, string>): string[] {
  const mappings = Array.isArray(step.mappings) ? step.mappings : [];
  const segments = mappings
    .map((item) => {
      const mapping = asRecord(item);
      const targetField = formatProcFieldName(toText(mapping.target_field));
      const value = asRecord(mapping.value);
      const valueType = toText(value.type).trim();
      if (!targetField) return '';

      if (valueType === 'source') {
        const source = asRecord(value.source);
        const alias = toText(source.alias).trim();
        const sourceName = aliasNameMap.get(alias) || alias || '当前数据集';
        const sourceField = formatProcFieldName(toText(source.field));
        return `${targetField} <- ${sourceName}.${sourceField}`;
      }
      if (valueType === 'formula') {
        const expr = humanizeProcDescription(toText(value.expr));
        return `${targetField} <- 按公式计算（${expr || '公式'}）`;
      }
      if (valueType === 'template_source') {
        const template = humanizeProcDescription(toText(value.template));
        return `${targetField} <- 模板字段（${template || '模板映射'}）`;
      }
      if (valueType === 'function') {
        const fn = humanizeProcDescription(toText(value.function));
        return `${targetField} <- 函数计算（${fn || '函数'}）`;
      }
      if (valueType === 'lookup') {
        return `${targetField} <- 查表结果`;
      }
      if (valueType === 'context') {
        return `${targetField} <- 上下文变量`;
      }
      return `${targetField} <- ${humanizeProcDescription(JSON.stringify(value)) || '自定义规则'}`;
    })
    .filter(Boolean);
  return segments.length > 0 ? [`字段整理规则：${segments.join('；')}。`] : [];
}

function summarizeProcAggregations(step: Record<string, unknown>, aliasNameMap: Map<string, string>): string[] {
  const aggregate = Array.isArray(step.aggregate) ? step.aggregate : [];
  const segments = aggregate
    .map((item) => {
      const entry = asRecord(item);
      const sourceAlias = toText(entry.source_alias).trim();
      const sourceName = aliasNameMap.get(sourceAlias) || sourceAlias || '当前数据集';
      const groupFields = Array.isArray(entry.group_fields) ? entry.group_fields.map((field) => formatProcFieldName(toText(field))).filter(Boolean) : [];
      const aggregations = Array.isArray(entry.aggregations) ? entry.aggregations : [];
      const aggText = aggregations
        .map((agg) => {
          const aggItem = asRecord(agg);
          const field = formatProcFieldName(toText(aggItem.field));
          const operator = toText(aggItem.operator).trim();
          if (!field || !operator) return '';
          const operatorText = operator === 'sum' ? '求和' : operator === 'min' ? '取最小值' : operator === 'max' ? '取最大值' : operator;
          return `${field}${operatorText}`;
        })
        .filter(Boolean);
      if (groupFields.length === 0 && aggText.length === 0) return '';
      const parts: string[] = [];
      if (groupFields.length > 0) parts.push(`按${groupFields.join('、')}分组`);
      if (aggText.length > 0) parts.push(`对${aggText.join('、')}`);
      return `${sourceName}${parts.join('，')}`;
    })
    .filter(Boolean);
  return segments.length > 0 ? [`聚合处理：${segments.join('；')}。`] : [];
}

function summarizeProcFilters(step: Record<string, unknown>, aliasNameMap: Map<string, string>): string[] {
  const lines: string[] = [];
  const filter = asRecord(step.filter);
  if (Object.keys(filter).length > 0) {
    const expr = humanizeProcDescription(toText(filter.expr));
    if (expr) {
      lines.push(`过滤条件：${expr}。`);
    }
  }

  const referenceFilter = asRecord(step.reference_filter);
  if (Object.keys(referenceFilter).length > 0) {
    const sourceAlias = toText(referenceFilter.source_alias).trim();
    const sourceName = aliasNameMap.get(sourceAlias) || sourceAlias || '当前数据集';
    const referenceTable = humanizeProcTargetTable(toText(referenceFilter.reference_table));
    const keys = Array.isArray(referenceFilter.keys) ? referenceFilter.keys : [];
    const pairs = keys
      .map((item) => {
        const entry = asRecord(item);
        const sourceField = formatProcFieldName(toText(entry.source_field));
        const referenceField = formatProcFieldName(toText(entry.reference_field));
        if (!sourceField || !referenceField) return '';
        return `${sourceField} -> ${referenceField}`;
      })
      .filter(Boolean);
    const pairText = pairs.length > 0 ? `，匹配关系：${pairs.join('；')}` : '';
    lines.push(`参考过滤：仅保留${sourceName}中能匹配${referenceTable}的数据${pairText}。`);
  }

  return lines;
}

function summarizeProcDraft(json: Record<string, unknown>): string {
  const steps = Array.isArray(json.steps) ? json.steps : [];
  const lines: string[] = [];
  const roleDesc = humanizeProcRoleDesc(toText(json.role_desc));
  lines.push(roleDesc);
  steps.forEach((step: unknown, index: number) => {
    if (typeof step !== 'object' || step === null) return;
    const s = step as Record<string, unknown>;
    const action = inferProcAction(s);
    const target = humanizeProcTargetTable(toText(s.target_table));
    const description = humanizeProcDescription(toText(s.description));
    const sources = Array.isArray(s.sources) ? s.sources : [];
    const sourceNames: string[] = [];
    const aliasNameMap = new Map<string, string>();
    sources.forEach((src: unknown) => {
      if (typeof src !== 'object' || src === null) return;
      const source = src as Record<string, unknown>;
      const alias = toText(source.alias).trim();
      const name = toText(source.table || source.name || source.alias).trim();
      if (name) {
        sourceNames.push(name);
      }
      if (alias) {
        aliasNameMap.set(alias, name || alias);
      }
    });

    if (action === 'create_schema') {
      lines.push(`步骤${index + 1}：创建${target}。`);
      lines.push(...summarizeProcColumns(s));
    } else if (action === 'write_dataset') {
      const sourceLabel = sourceNames.length > 0 ? sourceNames.join('、') : '当前选择的数据集';
      lines.push(`步骤${index + 1}：将${sourceLabel}整理后写入${target}。`);
      lines.push(`写入方式：${toText(s.row_write_mode, 'upsert')}。`);
      lines.push(...summarizeProcMatch(s, aliasNameMap));
      lines.push(...summarizeProcMappings(s, aliasNameMap));
      lines.push(...summarizeProcAggregations(s, aliasNameMap));
      lines.push(...summarizeProcFilters(s, aliasNameMap));
    } else {
      lines.push(`步骤${index + 1}：处理${target}。`);
      if (sourceNames.length > 0) {
        lines.push(`涉及数据集：${sourceNames.join('、')}。`);
      }
    }

    if (description) {
      lines.push(`说明：${description}`);
    }
    if (sourceNames.length > 0 && action === 'create_schema') {
      lines.push(`涉及数据集：${sourceNames.join('、')}`);
    }
    lines.push('');
  });
  if (lines.length === 0) return JSON.stringify(json, null, 2);
  return lines.join('\n').trim();
}

function summarizeReconDraft(
  json: Record<string, unknown>,
  fallback: Partial<ParsedReconDraftConfig> = {},
): string {
  const parsed = parseReconRuleJsonConfig(json, fallback);
  const ruleName = toText(json.rule_name, '未命名对账逻辑');
  const rules = Array.isArray(json.rules) ? json.rules : [];
  const firstRule = asRecord(rules[0]);
  const sourceFile = asRecord(firstRule.source_file);
  const targetFile = asRecord(firstRule.target_file);

  return [
    `# ${ruleName}`,
    `输入：${toText(sourceFile.table_name, 'left_recon_ready')} ↔ ${toText(targetFile.table_name, 'right_recon_ready')}`,
    `匹配字段：${resolveReconFieldPairsSummary(parsed.matchFieldPairs)}`,
    `对比字段：${resolveReconFieldPairsSummary(parsed.compareFieldPairs)}`,
    '识别方式：按匹配字段对齐左右记录，比较对比字段差异并输出差异结果。',
  ].join('\n');
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
  });
}

function toSortableTimestamp(value: string): number {
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function buildDefaultReconRuleName(schemeName: string): string {
  return `${schemeName.trim() || '未命名对账方案'} 对账逻辑`;
}

function formatScheduleLabel(scheduleType: string, scheduleExpr: string): string {
  const normalized = scheduleType.trim().toLowerCase();
  const expr = scheduleExpr.trim();
  const dailyMatch = normalized === 'daily' ? expr.match(/^(\d{1,2}:\d{2})$/) : null;
  const weeklyMatch = normalized === 'weekly' ? expr.match(/^W([0-6])\s+(\d{1,2}:\d{2})$/) : null;
  const monthlyMatch = normalized === 'monthly' ? expr.match(/^D(\d{1,2})\s+(\d{1,2}:\d{2})$/) : null;
  const monthlyCronMatch =
    normalized === 'cron'
      ? expr.match(/^0\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+\*\s+\*$/)
      : null;
  const weekdayLabels: Record<string, string> = {
    '1': '一',
    '2': '二',
    '3': '三',
    '4': '四',
    '5': '五',
    '6': '六',
    '0': '日',
  };
  if (dailyMatch) {
    return `每日 ${dailyMatch[1]}`;
  }
  if (weeklyMatch) {
    const [, dayOfWeek, time] = weeklyMatch;
    return `每周${weekdayLabels[dayOfWeek] || dayOfWeek} ${time}`;
  }
  if (monthlyMatch) {
    const [, dayOfMonth, time] = monthlyMatch;
    return `每月${dayOfMonth}日 ${time}`;
  }
  if (monthlyCronMatch) {
    const [, minute, hour, day] = monthlyCronMatch;
    return `每月${day}日 ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;
  }
  const base =
    normalized === 'manual_trigger'
      ? '手动触发'
      : normalized === 'daily'
      ? '每日'
      : normalized === 'weekly'
      ? '每周'
      : normalized === 'monthly'
      ? '每月'
      : normalized === 'cron'
      ? 'Cron'
      : scheduleType || '--';
  return expr ? `${base} / ${expr}` : base;
}

function formatBizDateOffsetLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return '--';
  if (normalized === 't-1' || normalized === 'previous_day') return 'T-1';
  if (normalized === 't' || normalized === 'today') return 'T';
  return value;
}

function summarizeOwnerMapping(raw: unknown): string {
  const ownerMapping = asRecord(raw);
  const mappings = asList(ownerMapping.mappings);
  const defaultOwner = asRecord(ownerMapping.default_owner);
  const defaultName = toText(defaultOwner.name).trim();
  if (mappings.length > 0) {
    return `映射 ${mappings.length} 组`;
  }
  if (defaultName) {
    return defaultName;
  }
  return '未配置';
}

function sameStringSet(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  const rightSet = new Set(right);
  return left.every((item) => rightSet.has(item));
}

function executionStatusMeta(status: string): { label: string; className: string } {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'success') {
    return {
      label: '成功',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };
  }
  if (normalized === 'running') {
    return {
      label: '运行中',
      className: 'border-sky-200 bg-sky-50 text-sky-700',
    };
  }
  if (normalized === 'failed') {
    return {
      label: '失败',
      className: 'border-red-200 bg-red-50 text-red-700',
    };
  }
  if (normalized === 'error') {
    return {
      label: '失败',
      className: 'border-red-200 bg-red-50 text-red-700',
    };
  }
  return {
    label: status || '未知',
    className: 'border-border bg-surface-secondary text-text-secondary',
  };
}

function formatAnomalyTypeLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'source_only') return '左侧独有';
  if (normalized === 'target_only') return '右侧独有';
  if (normalized === 'matched_with_diff') return '已匹配但字段不一致';
  if (normalized === 'value_mismatch') return '字段值不一致';
  if (normalized === 'amount_diff') return '金额不一致';
  return value || '未知异常';
}

function formatReminderStatusLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'pending') return '待催办';
  if (normalized === 'sent') return '已催办';
  if (normalized === 'completed') return '已完成';
  if (normalized === 'channel_missing') return '缺少协作通道';
  if (normalized === 'owner_missing') return '缺少责任人';
  if (normalized === 'owner_unresolved') return '责任人未识别';
  if (normalized === 'send_failed') return '催办发送失败';
  if (normalized === 'cancelled') return '已取消';
  if (normalized === 'sync_failed') return '状态同步失败';
  if (normalized === 'skipped') return '已跳过';
  return value || '--';
}

function formatProcessingStatusLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'pending') return '待处理';
  if (normalized === 'owner_done') return '责任人已处理';
  if (normalized === 'in_progress' || normalized === 'processing') return '处理中';
  if (normalized === 'verifying') return '复核中';
  if (normalized === 'verified') return '已复核';
  if (normalized === 'closed') return '已关闭';
  return value || '--';
}

function formatFixStatusLabel(value: string, isClosed: boolean): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'pending') return '待修复';
  if (normalized === 'ready_for_verify') return '待复核';
  if (normalized === 'fixed') return '已修复';
  if (normalized === 'verified') return '已确认';
  if (normalized === 'cancelled') return '已取消';
  if (!value && isClosed) return '已关闭';
  return value || '--';
}

function formatDetailValue(value: unknown): string {
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

function stripRunExceptionFieldPrefix(field: string): string {
  const normalized = field.trim();
  if (!normalized) return '';
  const prefixes = ['left_recon_ready.', 'right_recon_ready.', 'source.', 'target.', 'left.', 'right.'];
  for (const prefix of prefixes) {
    if (normalized.startsWith(prefix)) {
      return normalized.slice(prefix.length);
    }
  }
  return normalized;
}

function humanizeExceptionFieldName(field: string, fallback = ''): string {
  const normalized = stripRunExceptionFieldPrefix(field || fallback);
  if (!normalized) return fallback || '--';
  return PREPARED_OUTPUT_FIELD_LABEL_MAP[normalized] || humanizeProcDescription(normalized).trim() || normalized;
}

function buildRunExceptionJoinKeySummary(item: ReconRunExceptionDetail): string[] {
  return getRunExceptionJoinKeys(item)
    .map((entry) => {
      const label = humanizeExceptionFieldName(
        toText(entry.source_field),
        toText(entry.target_field, '匹配字段'),
      );
      const sourceValue = formatDetailValue(entry.source_value);
      const targetValue = formatDetailValue(entry.target_value);
      if (sourceValue !== '--') {
        return `${label}：${sourceValue}`;
      }
      if (targetValue !== '--') {
        return `${label}：${targetValue}`;
      }
      return '';
    })
    .filter(Boolean);
}

function buildRunExceptionCompareSummary(item: ReconRunExceptionDetail): string[] {
  return getRunExceptionCompareValues(item)
    .map((entry) => {
      const label = toText(
        entry.name,
        humanizeExceptionFieldName(toText(entry.source_field), toText(entry.target_field, '对比字段')),
      );
      const sourceValue = formatDetailValue(entry.source_value);
      const targetValue = formatDetailValue(entry.target_value);
      const diffValue = formatDetailValue(entry.diff_value);
      return `${label}：左侧 ${sourceValue} / 右侧 ${targetValue}${diffValue !== '--' ? ` / 差额 ${diffValue}` : ''}`;
    })
    .filter(Boolean);
}

function getRunExceptionJoinKeys(item: ReconRunExceptionDetail): Array<Record<string, unknown>> {
  const detail = firstNonEmptyRecord(item.raw.detail_json, item.raw.detail, item.raw);
  return asList(detail.join_key)
    .map((entry) => asRecord(entry))
    .filter((entry) => Object.keys(entry).length > 0);
}

function getRunExceptionCompareValues(item: ReconRunExceptionDetail): Array<Record<string, unknown>> {
  const detail = firstNonEmptyRecord(item.raw.detail_json, item.raw.detail, item.raw);
  return asList(detail.compare_values)
    .map((entry) => asRecord(entry))
    .filter((entry) => Object.keys(entry).length > 0);
}

function getRunExceptionRawRecord(item: ReconRunExceptionDetail): Record<string, unknown> {
  const detail = firstNonEmptyRecord(item.raw.detail_json, item.raw.detail, item.raw);
  return firstNonEmptyRecord(detail.raw_record, detail.record, detail.source_record, detail.left_record);
}

function getRunExceptionRecordsBySide(
  item: ReconRunExceptionDetail,
): { left: Record<string, unknown>; right: Record<string, unknown>; extra: Record<string, unknown> } {
  const detail = firstNonEmptyRecord(item.raw.detail_json, item.raw.detail, item.raw);
  const explicitLeft = firstNonEmptyRecord(detail.left_record, detail.source_record, detail.left_row);
  const explicitRight = firstNonEmptyRecord(detail.right_record, detail.target_record, detail.right_row);
  const rawRecord = firstNonEmptyRecord(detail.raw_record, detail.record);

  const normalizeRecordKeys = (record: Record<string, unknown>): Record<string, unknown> =>
    Object.fromEntries(
      Object.entries(record).map(([key, value]) => [stripRunExceptionFieldPrefix(key), value]),
    );

  if (Object.keys(explicitLeft).length > 0 || Object.keys(explicitRight).length > 0) {
    return {
      left: normalizeRecordKeys(explicitLeft),
      right: normalizeRecordKeys(explicitRight),
      extra: {},
    };
  }

  const left: Record<string, unknown> = {};
  const right: Record<string, unknown> = {};
  const extra: Record<string, unknown> = {};

  Object.entries(rawRecord).forEach(([key, value]) => {
    if (key.startsWith('left_recon_ready.') || key.startsWith('source.') || key.startsWith('left.')) {
      left[stripRunExceptionFieldPrefix(key)] = value;
      return;
    }
    if (key.startsWith('right_recon_ready.') || key.startsWith('target.') || key.startsWith('right.')) {
      right[stripRunExceptionFieldPrefix(key)] = value;
      return;
    }
    extra[stripRunExceptionFieldPrefix(key)] = value;
  });

  return { left, right, extra };
}

function enabledStatusMeta(enabled: boolean): { label: string; className: string } {
  return enabled
    ? {
        label: '启用中',
        className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      }
    : {
        label: '已停用',
        className: 'border-border bg-surface-secondary text-text-secondary',
      };
}

function emptyCompatibilityResult(): CompatibilityCheckResult {
  return {
    status: 'idle',
    message: '等待校验',
    details: [],
  };
}

const PROC_REFERENCE_VALIDATION = '以下展示的是上一次试跑的数据样例，仅供参考。';
const PREPARATION_REFERENCE_EDIT_SUMMARY =
  '已保留上一次试跑结果的数据样例供参考。当前数据整理已修改，请重新试跑。';
const RECON_REFERENCE_EDIT_SUMMARY =
  '已保留上一次对账试跑结果供参考。当前对账设置已修改，请重新试跑。';

function markProcTrialPreviewAsReference(
  preview: ProcTrialPreview | null,
  summary: string,
): ProcTrialPreview | null {
  if (!preview) return preview;
  const validations = preview.validations.includes(PROC_REFERENCE_VALIDATION)
    ? preview.validations
    : [PROC_REFERENCE_VALIDATION, ...preview.validations];
  return {
    ...preview,
    status: 'needs_adjustment',
    summary,
    validations,
  };
}

function markReconTrialPreviewAsReference(
  preview: ReconTrialPreview | null,
  summary: string,
): ReconTrialPreview | null {
  if (!preview) return preview;
  return {
    ...preview,
    status: 'needs_adjustment',
    summary,
  };
}

function mapScheme(item: unknown): ReconSchemeListItem {
  const raw = asRecord(item);
  const enabled = toBool(raw.is_enabled, true);
  return {
    id: toText(raw.id),
    schemeCode: toText(raw.scheme_code),
    name: toText(raw.scheme_name || raw.name, '未命名方案'),
    description: toText(raw.description),
    fileRuleCode: toText(raw.file_rule_code),
    procRuleCode: toText(raw.proc_rule_code),
    reconRuleCode: toText(raw.recon_rule_code),
    status: enabled ? 'enabled' : 'paused',
    updatedAt: toText(raw.updated_at),
    createdAt: toText(raw.created_at),
    raw,
  };
}

function mapTask(item: unknown, schemeNameByCode: Map<string, string>): ReconTaskListItem {
  const raw = asRecord(item);
  const enabled = toBool(raw.is_enabled, true);
  const schemeCode = toText(raw.scheme_code);
  const planMeta = firstNonEmptyRecord(raw.plan_meta_json, raw.plan_meta, raw.meta);
  return {
    id: toText(raw.id),
    planCode: toText(raw.plan_code),
    name: toText(raw.plan_name, '未命名任务'),
    schemeCode,
    schemeName: schemeNameByCode.get(schemeCode) || schemeCode || '--',
    scheduleType: toText(raw.schedule_type),
    scheduleExpr: toText(raw.schedule_expr),
    bizDateOffset: toText(raw.biz_date_offset, 'T-1'),
    leftTimeSemantic: toText(planMeta.left_time_semantic),
    rightTimeSemantic: toText(planMeta.right_time_semantic),
    channelConfigId: toText(raw.channel_config_id),
    ownerSummary: summarizeOwnerMapping(raw.owner_mapping_json),
    status: enabled ? 'enabled' : 'paused',
    updatedAt: toText(raw.updated_at),
    createdAt: toText(raw.created_at),
    raw,
  };
}

function isTaskMarkedDeleted(item: ReconTaskListItem): boolean {
  const planMeta = firstNonEmptyRecord(item.raw.plan_meta_json, item.raw.plan_meta, item.raw.meta);
  return (
    toBool(planMeta.is_deleted, false)
    || toBool(planMeta.deleted, false)
    || Boolean(toText(planMeta.deleted_at).trim())
  );
}

function mapRun(
  item: unknown,
  schemeNameByCode: Map<string, string>,
  taskNameByCode: Map<string, string>,
): ReconCenterRunItem {
  const raw = asRecord(item);
  const runContext = asRecord(raw.run_context_json);
  const schemeCode = toText(raw.scheme_code);
  const planCode = toText(raw.plan_code);
  return {
    id: toText(raw.id),
    runCode: toText(raw.run_code),
    schemeCode,
    planCode,
    schemeName: schemeNameByCode.get(schemeCode) || schemeCode || '--',
    planName: taskNameByCode.get(planCode) || planCode || '--',
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

function mapRunException(item: unknown): ReconRunExceptionDetail {
  const raw = asRecord(item);
  return {
    id: toText(raw.id),
    anomalyType: toText(raw.anomaly_type),
    summary: toText(raw.summary),
    ownerName: toText(raw.owner_name, '--'),
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

function firstNonEmptyRecord(...values: unknown[]): Record<string, unknown> {
  for (const value of values) {
    if (typeof value === 'object' && value !== null) {
      return value as Record<string, unknown>;
    }
  }
  return {};
}

function extractSchemeMeta(item: ReconSchemeListItem): SchemeMetaSummary {
  const schemeMeta = firstNonEmptyRecord(item.raw.scheme_meta_json, item.raw.scheme_meta, item.raw.meta);
  const procRuleJson = asRecord(schemeMeta.proc_rule_json);
  const reconRuleJson = asRecord(schemeMeta.recon_rule_json);
  const datasetBindings = asRecord(schemeMeta.dataset_bindings);
  const leftBindingRows = asList(datasetBindings.left);
  const rightBindingRows = asList(datasetBindings.right);
  const leftRows = leftBindingRows.length > 0 ? leftBindingRows : asList(schemeMeta.left_sources);
  const rightRows = rightBindingRows.length > 0 ? rightBindingRows : asList(schemeMeta.right_sources);
  const leftSources = leftRows.map((raw) => {
    const value = asRecord(raw);
    const semanticProfile = asRecord(value.semantic_profile);
    const sourceRecord = asRecord(value.source);
    const explicitKeyFields = normalizeStringList(value.key_fields);
    return {
      id: toText(value.dataset_id, toText(value.id)),
      name: toText(value.dataset_name, toText(value.name, toText(value.table_name, '未命名数据'))),
      businessName: toText(value.business_name, toText(value.display_name, toText(semanticProfile.business_name))),
      technicalName: toText(value.technical_name, toText(value.resource_key, toText(value.table_name))),
      fieldLabelMap:
        normalizeFieldLabelMap(value.field_label_map) || normalizeFieldLabelMap(semanticProfile.field_label_map),
      keyFields: explicitKeyFields.length ? explicitKeyFields : normalizeStringList(semanticProfile.key_fields),
      schemaSummary: firstNonEmptyRecord(value.schema_summary, value.schemaSummary),
      sourceId: toText(value.data_source_id, toText(value.source_id, toText(sourceRecord.id))),
      sourceName: toText(value.data_source_name, toText(value.source_name, toText(sourceRecord.name))),
      sourceKind:
        (toText(value.source_kind, toText(sourceRecord.source_kind)) as SupportedSourceKind) || 'platform_oauth',
      providerCode: toText(value.provider_code, toText(sourceRecord.provider_code)),
      datasetCode: toText(value.dataset_code),
      resourceKey: toText(value.resource_key),
      datasetKind: toText(value.dataset_kind),
    };
  });
  const rightSources = rightRows.map((raw) => {
    const value = asRecord(raw);
    const semanticProfile = asRecord(value.semantic_profile);
    const sourceRecord = asRecord(value.source);
    const explicitKeyFields = normalizeStringList(value.key_fields);
    return {
      id: toText(value.dataset_id, toText(value.id)),
      name: toText(value.dataset_name, toText(value.name, toText(value.table_name, '未命名数据'))),
      businessName: toText(value.business_name, toText(value.display_name, toText(semanticProfile.business_name))),
      technicalName: toText(value.technical_name, toText(value.resource_key, toText(value.table_name))),
      fieldLabelMap:
        normalizeFieldLabelMap(value.field_label_map) || normalizeFieldLabelMap(semanticProfile.field_label_map),
      keyFields: explicitKeyFields.length ? explicitKeyFields : normalizeStringList(semanticProfile.key_fields),
      schemaSummary: firstNonEmptyRecord(value.schema_summary, value.schemaSummary),
      sourceId: toText(value.data_source_id, toText(value.source_id, toText(sourceRecord.id))),
      sourceName: toText(value.data_source_name, toText(value.source_name, toText(sourceRecord.name))),
      sourceKind:
        (toText(value.source_kind, toText(sourceRecord.source_kind)) as SupportedSourceKind) || 'platform_oauth',
      providerCode: toText(value.provider_code, toText(sourceRecord.provider_code)),
      datasetCode: toText(value.dataset_code),
      resourceKey: toText(value.resource_key),
      datasetKind: toText(value.dataset_kind),
    };
  });
  const parsedReconConfig = parseReconRuleJsonConfig(reconRuleJson, {
    matchFieldPairs: normalizeReconFieldPairs(
      schemeMeta.match_field_pairs,
      toText(schemeMeta.match_key)
        ? [{ leftField: toText(schemeMeta.match_key), rightField: toText(schemeMeta.match_key) }]
        : [],
    ),
    compareFieldPairs: normalizeReconFieldPairs(
      schemeMeta.compare_field_pairs,
      toText(schemeMeta.left_amount_field) || toText(schemeMeta.right_amount_field)
        ? [
            {
              leftField: toText(schemeMeta.left_amount_field),
              rightField: toText(schemeMeta.right_amount_field),
            },
          ]
        : [],
    ),
    matchKey: toText(schemeMeta.match_key),
    leftAmountField: toText(schemeMeta.left_amount_field),
    rightAmountField: toText(schemeMeta.right_amount_field),
    leftTimeSemantic: toText(schemeMeta.left_time_semantic, toText(schemeMeta.time_semantic)),
    rightTimeSemantic: toText(schemeMeta.right_time_semantic, toText(schemeMeta.time_semantic)),
    tolerance: toText(schemeMeta.tolerance),
  });
  const leftOutputFields = normalizeOutputFieldDrafts(schemeMeta.left_output_fields);
  const rightOutputFields = normalizeOutputFieldDrafts(schemeMeta.right_output_fields);
  const leftOutputFieldLabelMap = mergeLabelMaps(
    buildOutputFieldLabelMap(leftOutputFields, leftSources),
    buildProcOutputFieldLabelMap(procRuleJson, 'left_recon_ready', leftSources),
    normalizeFieldLabelMap(schemeMeta.left_output_field_label_map),
    normalizeFieldLabelMap(schemeMeta.leftOutputFieldLabelMap),
  );
  const rightOutputFieldLabelMap = mergeLabelMaps(
    buildOutputFieldLabelMap(rightOutputFields, rightSources),
    buildProcOutputFieldLabelMap(procRuleJson, 'right_recon_ready', rightSources),
    normalizeFieldLabelMap(schemeMeta.right_output_field_label_map),
    normalizeFieldLabelMap(schemeMeta.rightOutputFieldLabelMap),
  );

  return {
    businessGoal: toText(schemeMeta.business_goal, item.description),
    leftSources,
    rightSources,
    leftOutputFields,
    rightOutputFields,
    leftOutputFieldLabelMap,
    rightOutputFieldLabelMap,
    leftDescription: toText(schemeMeta.left_description),
    rightDescription: toText(schemeMeta.right_description),
    procRuleName: toText(schemeMeta.proc_rule_name),
    procTrialStatus: (toText(schemeMeta.proc_trial_status) as TrialStatus) || 'idle',
    procTrialSummary: toText(schemeMeta.proc_trial_summary),
    reconTrialStatus: (toText(schemeMeta.recon_trial_status) as TrialStatus) || 'idle',
    reconTrialSummary: toText(schemeMeta.recon_trial_summary),
    procDraftText: toText(schemeMeta.proc_draft_text),
    reconDraftText: toText(schemeMeta.recon_draft_text),
    reconRuleName: toText(schemeMeta.recon_rule_name, toText(schemeMeta.bound_recon_rule_name)),
    matchFieldPairs: parsedReconConfig.matchFieldPairs,
    compareFieldPairs: parsedReconConfig.compareFieldPairs,
    matchKey: parsedReconConfig.matchKey,
    leftAmountField: parsedReconConfig.leftAmountField,
    rightAmountField: parsedReconConfig.rightAmountField,
    tolerance: parsedReconConfig.tolerance,
    leftTimeSemantic: parsedReconConfig.leftTimeSemantic,
    rightTimeSemantic: parsedReconConfig.rightTimeSemantic,
    inputPlanJson: firstNonEmptyRecord(schemeMeta.input_plan_json, schemeMeta.inputPlanJson),
  };
}

function hashText(input: string): number {
  let hash = 0;
  for (let index = 0; index < input.length; index += 1) {
    hash = (hash * 31 + input.charCodeAt(index)) % 1000003;
  }
  return Math.abs(hash);
}

function formatPreviewAmount(value: number): number {
  return Number(value.toFixed(2));
}

function resolveDatasetTableName(source: SchemeSourceOption): string {
  return source.resourceKey || source.datasetCode || source.name;
}

function resolveDatasetDisplayName(source: SchemeSourceOption | SchemeSourceDraft): string {
  return toText((source as { businessName?: string }).businessName, source.name).trim() || source.name;
}

function resolveSourceFieldLabelMap(
  source: SchemeSourceOption | SchemeSourceDraft | null | undefined,
): Record<string, string> | undefined {
  if (!source) return undefined;
  return normalizeFieldLabelMap((source as { fieldLabelMap?: unknown }).fieldLabelMap);
}

function resolveSampleOriginMeta(
  origin: unknown,
  collectionId?: unknown,
): {
  key: string;
  label: string;
  hint?: string;
} {
  const originKey = toText(origin).trim().toLowerCase();
  const resolvedCollectionId = toText(collectionId).trim();
  if (originKey === 'collection_records') {
    return {
      key: originKey,
      label: '已采集数据',
      hint: resolvedCollectionId ? `来自已采集数据：${resolvedCollectionId}` : '来自已采集数据',
    };
  }
  if (originKey === 'uploaded_file') {
    return {
      key: originKey,
      label: '上传文件',
      hint: '当前抽样来自上传文件',
    };
  }
  return {
    key: originKey || 'sample_rows',
    label: '样本数据',
    hint: '当前抽样来自数据集内置样本',
  };
}

function runPlanInputSideLabel(side: 'left' | 'right'): string {
  return side === 'left' ? '左侧' : '右侧';
}

function buildRunPlanDateFieldOptions(input: RunPlanInputDatasetDraft): ReconFieldOption[] {
  const source = input.source;
  const fieldLabelMap = normalizeFieldLabelMap(source?.fieldLabelMap) || {};
  const rawNames = Array.from(
    new Set<string>([
      ...extractSchemaFieldNames(source?.schemaSummary),
      ...Object.keys(fieldLabelMap),
    ]),
  ).map((item) => item.trim()).filter(Boolean);

  return rawNames
    .map((rawName) => {
      const label = toText(fieldLabelMap[rawName], rawName);
      const schemaType = normalizeSchemaType(asRecord(source?.schemaSummary)[rawName]);
      const typeScore = schemaType === 'datetime' || schemaType === 'date' ? 20 : 0;
      const score = scoreDateFieldCandidate(rawName, label) + typeScore;
      return {
        value: rawName,
        label: label && label !== rawName ? `${label}（${rawName}）` : rawName,
        score,
      };
    })
    .sort((left, right) => right.score - left.score || left.label.localeCompare(right.label, 'zh-CN'))
    .map(({ value, label }) => ({ value, label }));
}

function pickDefaultRunPlanDateField(input: RunPlanInputDatasetDraft): string {
  const options = buildRunPlanDateFieldOptions(input);
  return options[0]?.value || '';
}

function buildDefaultRunPlanDateFieldMap(
  schemeMeta: SchemeMetaSummary | null,
  existing: Record<string, string> = {},
): Record<string, string> {
  const next: Record<string, string> = {};
  extractRunPlanInputDatasets(schemeMeta)
    .filter((input) => input.requiresDateField)
    .forEach((input) => {
      const current = toText(existing[input.key]).trim();
      const options = buildRunPlanDateFieldOptions(input);
      const currentIsValid = current && options.some((option) => option.value === current);
      next[input.key] = currentIsValid ? current : pickDefaultRunPlanDateField(input);
    });
  return next;
}

function normalizeSchemaType(value: unknown): string {
  const text = toText(value).toLowerCase();
  if (!text) return 'string';
  if (text.includes('timestamp') || text.includes('datetime')) return 'datetime';
  if (text.includes('date')) return 'date';
  if (text.includes('decimal') || text.includes('number') || text.includes('numeric') || text.includes('float')) {
    return 'number';
  }
  if (text.includes('int')) return 'integer';
  if (text.includes('bool')) return 'boolean';
  return 'string';
}

function buildSchemaValue(
  columnName: string,
  schemaType: string,
  source: SchemeSourceOption,
  side: 'left' | 'right',
  seq: number,
  seed: number,
): PreviewCellValue {
  const lowerName = columnName.toLowerCase();
  const tableName = resolveDatasetTableName(source);
  const amount = formatPreviewAmount(100 + (seed % 17) * 3 + seq * 12.35 + (side === 'left' ? 0.18 : 0.12));
  const day = String((seed + seq) % 9 + 1).padStart(2, '0');

  if (schemaType === 'number' || schemaType === 'integer') {
    if (lowerName.includes('amount') || lowerName.includes('amt') || lowerName.includes('fee') || lowerName.includes('price')) {
      return amount;
    }
    return schemaType === 'integer' ? seed % 1000 + seq : amount;
  }
  if (schemaType === 'date') {
    return `2026-04-${day}`;
  }
  if (schemaType === 'datetime') {
    return `2026-04-${day} 10:${String(seq).padStart(2, '0')}:00`;
  }
  if (schemaType === 'boolean') {
    return seq % 2 === 0 ? 'true' : 'false';
  }
  if (lowerName.includes('order') || lowerName.includes('request') || lowerName.includes('ledger')) {
    return `${side === 'left' ? 'L' : 'R'}-${seq.toString().padStart(3, '0')}`;
  }
  if (lowerName.endsWith('_id') || lowerName === 'id' || lowerName.includes('code') || lowerName.includes('no')) {
    return `${tableName}-${seq.toString().padStart(3, '0')}`;
  }
  if (lowerName.includes('shop') || lowerName.includes('store') || lowerName.includes('merchant')) {
    return source.sourceName || source.name;
  }
  if (lowerName.includes('dataset')) {
    return source.name;
  }
  if (lowerName.includes('table') || lowerName.includes('endpoint')) {
    return tableName;
  }
  if (lowerName.includes('status') || lowerName.includes('state') || lowerName.includes('result')) {
    return seq % 2 === 0 ? 'success' : 'ready';
  }
  if (lowerName.includes('name') || lowerName.includes('title')) {
    return `${source.name}-${seq}`;
  }
  return `${columnName}_${seq}`;
}

function buildRawSourceRows(
  source: SchemeSourceOption,
  side: 'left' | 'right',
  seedText: string,
): PreviewTableRow[] {
  const seed = hashText(`${source.id}-${side}-${seedText}`);
  const schemaSummaryEntries = Object.entries(asRecord(source.schemaSummary));
  if (schemaSummaryEntries.length > 0) {
    return Array.from({ length: 3 }, (_, index) => {
      const seq = index + 1;
      const rowEntries = schemaSummaryEntries.map(([columnName, rawType]) => [
        columnName,
        buildSchemaValue(columnName, normalizeSchemaType(rawType), source, side, seq, seed),
      ]);
      return Object.fromEntries(rowEntries) as PreviewTableRow;
    });
  }

  return Array.from({ length: 3 }, (_, index) => {
    const seq = index + 1;
    const amount = formatPreviewAmount(100 + (seed % 17) * 3 + seq * 12.35 + (side === 'left' ? 0.18 : 0.12));
    const day = String((seed + seq) % 9 + 1).padStart(2, '0');
    if (source.sourceKind === 'platform_oauth') {
      return {
        order_no: `ORD-${seq.toString().padStart(3, '0')}`,
        shop_name: source.sourceName || source.name,
        dataset_name: source.name,
        gross_amount: amount,
        biz_date: `2026-04-${day}`,
        status: seq % 2 === 0 ? 'paid' : 'settled',
      } as PreviewTableRow;
    }
    if (source.sourceKind === 'database') {
      return {
        ledger_id: `LEDGER-${seq.toString().padStart(3, '0')}`,
        table_name: source.resourceKey || source.datasetCode || source.name,
        booked_amount: amount,
        accounting_date: `2026-04-${day}`,
        status: seq % 2 === 0 ? 'posted' : 'ready',
      } as PreviewTableRow;
    }
    return {
      request_id: `API-${seq.toString().padStart(3, '0')}`,
      endpoint: source.resourceKey || source.datasetCode || source.name,
      amount,
      happened_at: `2026-04-${day}`,
      result: seq % 2 === 0 ? 'success' : 'ok',
    } as PreviewTableRow;
  });
}

function buildDatasetSamplePayload(
  source: SchemeSourceOption,
  side: 'left' | 'right',
  description: string,
  seedText: string,
  options?: {
    tableName?: string;
    schemaSummary?: Record<string, unknown>;
    sampleRows?: PreviewTableRow[];
    preparedOutputFields?: Array<Record<string, unknown>>;
  },
): Record<string, unknown> {
  const tableName = options?.tableName || resolveDatasetTableName(source);
  const sampleRows = options?.sampleRows || buildRawSourceRows(source, side, seedText);
  return {
    side,
    dataset_name: source.name,
    business_name: source.businessName || source.name,
    table_name: tableName,
    dataset_code: source.datasetCode,
    source_type: 'dataset',
    source_id: source.sourceId,
    source_key: source.sourceId,
    resource_key: tableName,
    source_kind: source.sourceKind,
    provider_code: source.providerCode,
    description,
    field_label_map: source.fieldLabelMap || undefined,
    prepared_output_fields: options?.preparedOutputFields,
    sample_rows: sampleRows,
  };
}

function toPreviewTableRows(value: unknown): PreviewTableRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) =>
      Object.fromEntries(
        Object.entries(item).map(([key, rawValue]) => {
          if (rawValue === null || rawValue === undefined) return [key, null];
          if (typeof rawValue === 'number') return [key, rawValue];
          return [key, String(rawValue)];
        }),
      ) as PreviewTableRow,
    );
}

function parseTrialMessages(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim();
      if (typeof item === 'object' && item !== null) {
        const record = item as Record<string, unknown>;
        const path = toText(record.path);
        const message = toText(record.message || record.error || record.detail);
        if (!path && !message) return '';
        return path ? `${path} ${message}`.trim() : message;
      }
      return '';
    })
    .filter(Boolean);
}

function buildProcPreviewFromTrialResult(trialResult: unknown): ProcTrialPreview | null {
  const raw = asRecord(trialResult);
  if (Object.keys(raw).length === 0) return null;
  const sourceSamples = asList(raw.source_samples)
    .filter((item) => typeof item === 'object' && item !== null)
    .map((item) => asRecord(item));
  const outputSamples = asList(raw.output_samples)
    .filter((item) => typeof item === 'object' && item !== null)
    .map((item) => asRecord(item));
  return {
    status: raw.ready_for_confirm === true && raw.success !== false ? 'passed' : 'needs_adjustment',
    summary: toText(raw.summary, toText(raw.message, toText(raw.error, '数据整理试跑完成'))),
    rawSources: sourceSamples.map((item) => {
      const collectionId = toText(item.collection_id, toText(item.snapshot_id));
      const originMeta = resolveSampleOriginMeta(item.sample_origin, collectionId);
      const fieldLabelMap =
        normalizeFieldLabelMap(item.field_label_map)
        || normalizeFieldLabelMap(item.columns_label_map)
        || normalizeFieldLabelMap(item.column_display_map);
      return {
        sourceId: toText(item.source_id, toText(item.table_name)),
        sourceName: toText(item.display_name, toText(item.table_name, '数据源')),
        side: toText(item.side) === 'right' ? 'right' : 'left',
        fieldLabelMap,
        sampleOrigin: originMeta.key,
        sampleOriginLabel: originMeta.label,
        sampleOriginHint: originMeta.hint,
        snapshotId: collectionId || undefined,
        rows: toPreviewTableRows(item.rows),
      };
    }),
    preparedOutputs: outputSamples.map((item) => {
      const fieldLabelMap =
        normalizeFieldLabelMap(item.field_label_map)
        || normalizeFieldLabelMap(item.columns_label_map)
        || PREPARED_OUTPUT_FIELD_LABEL_MAP;
      return {
        side: toText(item.side) === 'right' ? 'right' : 'left',
        title: toText(item.title, toText(item.target_table, 'output')),
        fieldLabelMap,
        rows: toPreviewTableRows(item.rows),
      };
    }),
    validations: [
      ...parseTrialMessages(raw.errors),
      ...parseTrialMessages(raw.warnings),
      ...parseTrialMessages(raw.highlights),
    ],
  };
}

function normalizeReconFieldPairs(
  value: unknown,
  fallbackPairs: Array<{ leftField: string; rightField: string }> = [],
): ReconFieldPairDraft[] {
  const rows = Array.isArray(value)
    ? value
    : fallbackPairs.map((pair) => ({
        left_field: pair.leftField,
        right_field: pair.rightField,
      }));
  const seen = new Set<string>();
  const normalized: ReconFieldPairDraft[] = [];
  rows.forEach((item) => {
    const record = asRecord(item);
    const leftField = toText(record.left_field, toText(record.leftField)).trim();
    const rightField = toText(record.right_field, toText(record.rightField)).trim();
    if (!leftField && !rightField) return;
    const dedupeKey = `${leftField}::${rightField}`;
    if (seen.has(dedupeKey)) return;
    seen.add(dedupeKey);
    normalized.push({
      id: toText(record.id).trim() || createReconFieldPairDraft().id,
      leftField,
      rightField,
    });
  });
  return normalized;
}

function isCompleteReconFieldPair(pair: ReconFieldPairDraft): boolean {
  return Boolean(pair.leftField.trim() && pair.rightField.trim());
}

function filterCompleteReconFieldPairs(pairs: ReconFieldPairDraft[]): ReconFieldPairDraft[] {
  return normalizeReconFieldPairs(pairs).filter(isCompleteReconFieldPair);
}

function resolveFirstReconFieldPairValue(
  pairs: ReconFieldPairDraft[],
  side: 'left' | 'right',
  fallback = '',
): string {
  const firstPair = filterCompleteReconFieldPairs(pairs)[0];
  if (!firstPair) return fallback;
  return side === 'left' ? firstPair.leftField : firstPair.rightField;
}

function resolveReconFieldPairsSummary(
  pairs: ReconFieldPairDraft[],
  fallback = '--',
): string {
  const text = filterCompleteReconFieldPairs(pairs)
    .map((pair) => `${pair.leftField} ↔ ${pair.rightField}`)
    .join('；');
  return text || fallback;
}

function buildSemanticRoleReconFieldPairs(
  leftFields: OutputFieldDraft[],
  rightFields: OutputFieldDraft[],
  role: OutputFieldSemanticRole,
): ReconFieldPairDraft[] {
  const leftCandidates = leftFields.filter(
    (field) => normalizeOutputFieldSemanticRole(field.semanticRole) === role && field.outputName.trim(),
  );
  const rightCandidates = rightFields.filter(
    (field) => normalizeOutputFieldSemanticRole(field.semanticRole) === role && field.outputName.trim(),
  );
  if (leftCandidates.length === 0 || rightCandidates.length === 0) {
    return [];
  }

  const usedRightIndexes = new Set<number>();
  const nextPairs: ReconFieldPairDraft[] = [];

  leftCandidates.forEach((leftField, index) => {
    const leftName = leftField.outputName.trim();
    const exactRightIndex = rightCandidates.findIndex(
      (candidate, candidateIndex) =>
        !usedRightIndexes.has(candidateIndex)
        && candidate.outputName.trim() === leftName,
    );
    const fallbackRightIndex = rightCandidates.findIndex(
      (_candidate, candidateIndex) => !usedRightIndexes.has(candidateIndex),
    );
    const resolvedRightIndex = exactRightIndex >= 0
      ? exactRightIndex
      : index < rightCandidates.length && !usedRightIndexes.has(index)
      ? index
      : fallbackRightIndex;
    if (resolvedRightIndex < 0) return;
    usedRightIndexes.add(resolvedRightIndex);
    nextPairs.push(
      createReconFieldPairDraft({
        leftField: leftName,
        rightField: rightCandidates[resolvedRightIndex].outputName.trim(),
      }),
    );
  });

  return filterCompleteReconFieldPairs(nextPairs);
}

function buildSourceDisplayNameMap(
  sources: Array<SchemeSourceOption | SchemeSourceDraft>,
): Map<string, string> {
  return new Map(
    sources
      .filter((source) => source.id.trim())
      .map((source) => [source.id, resolveDatasetDisplayName(source)] as const),
  );
}

function buildSourceFieldLabelMapById(
  sources: Array<SchemeSourceOption | SchemeSourceDraft>,
): Map<string, Record<string, string>> {
  return new Map(
    sources
      .filter((source) => source.id.trim())
      .map((source) => [source.id, normalizeFieldLabelMap((source as { fieldLabelMap?: unknown }).fieldLabelMap) || {}] as const),
  );
}

function formatPreviewFieldReference(
  datasetName: string,
  fieldName: string,
  fieldLabelMap?: Record<string, string>,
): string {
  const normalizedFieldName = fieldName.trim();
  const displayName = toText(fieldLabelMap?.[normalizedFieldName], normalizedFieldName).trim();
  if (!normalizedFieldName) return datasetName;
  if (displayName && displayName !== normalizedFieldName) {
    return `${datasetName}.${displayName} (${normalizedFieldName})`;
  }
  return `${datasetName}.${normalizedFieldName}`;
}

function formatPreviewFieldLabel(
  fieldName: string,
  fieldLabelMap?: Record<string, string>,
): string {
  const normalizedFieldName = fieldName.trim();
  const displayName = toText(fieldLabelMap?.[normalizedFieldName], normalizedFieldName).trim();
  if (!normalizedFieldName) return '--';
  if (displayName && displayName !== normalizedFieldName) {
    return `${displayName} (${normalizedFieldName})`;
  }
  return normalizedFieldName;
}

function buildOutputPreviewColumnHints(
  fields: OutputFieldDraft[],
  sources: Array<SchemeSourceOption | SchemeSourceDraft>,
  fieldLabelMap?: Record<string, string>,
): Record<string, PreviewColumnHintMeta> | undefined {
  if (fields.length === 0 || sources.length === 0) return undefined;

  const sourceNameById = buildSourceDisplayNameMap(sources);
  const sourceFieldLabelMapById = buildSourceFieldLabelMapById(sources);
  const normalizedFields = fields
    .map((field) => ({
      valueMode: field.valueMode,
      outputName: field.outputName.trim(),
      sourceDatasetId: field.sourceDatasetId,
      sourceField: field.sourceField,
      fixedValue: field.fixedValue,
      formula: field.formula,
      concatParts: field.concatParts,
    }))
    .filter((field) => field.outputName);

  const hints: Record<string, PreviewColumnHintMeta> = {};
  const resolveFieldHint = (columnKey: string): PreviewColumnHintMeta | null => {
    const label = toText(fieldLabelMap?.[columnKey]).trim();
    const matchedField = normalizedFields.find((field) => (
      field.outputName === columnKey.trim() || (label && field.outputName === label)
    ));
    if (!matchedField) return null;
    const sourceFieldLabelMap = sourceFieldLabelMapById.get(matchedField.sourceDatasetId) || {};
    if (matchedField.valueMode === 'source_field') {
      return {
        helper: `源字段：${formatPreviewFieldLabel(matchedField.sourceField, sourceFieldLabelMap)}`,
        tone: 'sky',
      };
    }
    if (matchedField.valueMode === 'fixed_value') {
      return {
        badge: '固定值',
        helper: `值：${matchedField.fixedValue.trim() || '--'}`,
        tone: 'amber',
      };
    }
    if (matchedField.valueMode === 'formula') {
      return {
        badge: '公式',
        helper: `表达式：${matchedField.formula.trim() || '--'}`,
        tone: 'violet',
      };
    }
    const concatParts = matchedField.concatParts
      .map((part) => {
        const datasetName = sourceNameById.get(part.datasetId) || '数据集';
        const fieldLabelMapBySourceId = sourceFieldLabelMapById.get(part.datasetId) || {};
        return formatPreviewFieldReference(datasetName, part.fieldName, fieldLabelMapBySourceId);
      })
      .filter((item) => item !== '数据集');
    return {
      badge: concatParts.length > 1 ? '多来源拼接' : '拼接',
      helper: `字段：${concatParts.length > 0 ? concatParts.join(' + ') : '待补充'}`,
      tone: concatParts.length > 1 ? 'violet' : 'sky',
    };
  };

  Object.keys(fieldLabelMap || {}).forEach((columnKey) => {
    const meta = resolveFieldHint(columnKey);
    if (meta) {
      hints[columnKey] = meta;
    }
  });

  normalizedFields.forEach((field) => {
    if (hints[field.outputName]) return;
    const sourceFieldLabelMap = sourceFieldLabelMapById.get(field.sourceDatasetId) || {};
    if (field.valueMode === 'source_field') {
      hints[field.outputName] = {
        helper: `源字段：${formatPreviewFieldLabel(field.sourceField, sourceFieldLabelMap)}`,
        tone: 'sky',
      };
      return;
    }
    if (field.valueMode === 'fixed_value') {
      hints[field.outputName] = {
        badge: '固定值',
        helper: `值：${field.fixedValue.trim() || '--'}`,
        tone: 'amber',
      };
      return;
    }
    if (field.valueMode === 'formula') {
      hints[field.outputName] = {
        badge: '公式',
        helper: `表达式：${field.formula.trim() || '--'}`,
        tone: 'violet',
      };
      return;
    }
    const concatParts = field.concatParts
      .map((part) => {
        const datasetName = sourceNameById.get(part.datasetId) || '数据集';
        const fieldLabelMapBySourceId = sourceFieldLabelMapById.get(part.datasetId) || {};
        return formatPreviewFieldReference(datasetName, part.fieldName, fieldLabelMapBySourceId);
      })
      .filter((item) => item !== '数据集');
    hints[field.outputName] = {
      badge: concatParts.length > 1 ? '多来源拼接' : '拼接',
      helper: `字段：${concatParts.length > 0 ? concatParts.join(' + ') : '待补充'}`,
      tone: concatParts.length > 1 ? 'violet' : 'sky',
    };
  });

  return Object.keys(hints).length > 0 ? hints : undefined;
}

function buildInputPreviewColumnHints(
  source: SchemeSourceOption | SchemeSourceDraft | undefined,
  fields: OutputFieldDraft[],
  fieldLabelMap?: Record<string, string>,
): Record<string, PreviewColumnHintMeta> | undefined {
  if (!source || !source.id.trim()) return undefined;
  const sourceFieldLabelMap = normalizeFieldLabelMap((source as { fieldLabelMap?: unknown }).fieldLabelMap) || {};
  const outputFieldNames = fields
    .filter((field) => field.sourceDatasetId === source.id || field.concatParts.some((part) => part.datasetId === source.id))
    .map((field) => field.outputName.trim())
    .filter(Boolean);
  if (outputFieldNames.length === 0) return undefined;

  const hints: Record<string, PreviewColumnHintMeta> = {};
  const sampleColumns = Array.from(
    new Set<string>([
      ...Object.keys(fieldLabelMap || {}),
      ...Object.keys(sourceFieldLabelMap),
    ]),
  );
  sampleColumns.forEach((columnKey) => {
    const normalizedColumnKey = columnKey.trim();
    if (!normalizedColumnKey) return;
    const displayName = toText(
      fieldLabelMap?.[normalizedColumnKey],
      toText(sourceFieldLabelMap[normalizedColumnKey], normalizedColumnKey),
    ).trim();
    const matchedOutputs = fields.flatMap((field) => {
      const outputName = field.outputName.trim();
      if (!outputName) return [];
      if (
        field.valueMode === 'source_field'
        && field.sourceDatasetId === source.id
        && (field.sourceField.trim() === normalizedColumnKey || field.sourceField.trim() === displayName)
      ) {
        return [outputName];
      }
      if (
        field.valueMode === 'concat'
        && field.concatParts.some((part) => part.datasetId === source.id && (part.fieldName.trim() === normalizedColumnKey || part.fieldName.trim() === displayName))
      ) {
        return [`${outputName}（拼接）`];
      }
      return [];
    });
    if (matchedOutputs.length === 0) return;
    hints[normalizedColumnKey] = {
      helper: `被用于：${Array.from(new Set(matchedOutputs)).join('、')}`,
      tone: 'sky',
    };
  });

  return Object.keys(hints).length > 0 ? hints : undefined;
}

function resolveFieldDrivenDatasetLabel(
  fieldName: string,
  fields: OutputFieldDraft[],
  sources: Array<SchemeSourceOption | SchemeSourceDraft>,
): string {
  if (sources.length === 0) return '--';
  const normalizedFieldName = fieldName.trim();
  const sourceNameById = buildSourceDisplayNameMap(sources);
  const matchedField = fields.find((field) => field.outputName.trim() === normalizedFieldName);
  const matchedSourceName = matchedField?.sourceDatasetId
    ? sourceNameById.get(matchedField.sourceDatasetId)
    : '';
  return matchedSourceName || resolveDatasetDisplayName(sources[0]);
}

function resolveResultDatasetLabel(
  side: 'left' | 'right',
  matchFieldPairs: ReconFieldPairDraft[],
  fields: OutputFieldDraft[],
  sources: Array<SchemeSourceOption | SchemeSourceDraft>,
): string {
  if (sources.length > 1) {
    return side === 'left' ? '左侧表' : '右侧表';
  }
  const firstPair = filterCompleteReconFieldPairs(matchFieldPairs)[0];
  const fieldName = side === 'left' ? firstPair?.leftField : firstPair?.rightField;
  return resolveFieldDrivenDatasetLabel(fieldName || '', fields, sources);
}

function hasExplicitRunPlanDatasets(inputPlanJson: unknown): boolean {
  const planJson = asRecord(inputPlanJson);
  if (asList(planJson.datasets).length > 0) return true;
  return asList(planJson.plans).some((rawPlan) => asList(asRecord(rawPlan).datasets).length > 0);
}

function resolveRunPlanBaseDatasetLabel(
  side: 'left' | 'right',
  inputPlanJson: unknown,
  leftSources: Array<SchemeSourceOption | SchemeSourceDraft>,
  rightSources: Array<SchemeSourceOption | SchemeSourceDraft>,
): string {
  if (!hasExplicitRunPlanDatasets(inputPlanJson)) return '';
  const inputs = extractRunPlanInputDatasets({
    leftSources,
    rightSources,
    leftOutputFields: [],
    rightOutputFields: [],
    inputPlanJson: asRecord(inputPlanJson),
  });
  const sideInputs = inputs.filter((input) => input.side === side);
  const baseInput =
    sideInputs.find((input) => input.readMode === 'base')
    || sideInputs.find((input) => input.requiresDateField);
  return baseInput?.displayName.trim() || '';
}

function resolveReconOnlyResultDatasetLabel(
  side: 'left' | 'right',
  matchFieldPairs: ReconFieldPairDraft[],
  fields: OutputFieldDraft[],
  sources: Array<SchemeSourceOption | SchemeSourceDraft>,
  inputPlanJson: unknown,
  leftSources: Array<SchemeSourceOption | SchemeSourceDraft>,
  rightSources: Array<SchemeSourceOption | SchemeSourceDraft>,
): string {
  if (sources.length <= 1) {
    return resolveResultDatasetLabel(side, matchFieldPairs, fields, sources);
  }
  return (
    resolveRunPlanBaseDatasetLabel(side, inputPlanJson, leftSources, rightSources)
    || resolveResultDatasetLabel(side, matchFieldPairs, fields, sources)
  );
}

function resolvePreviewFieldValue(row: PreviewTableRow, candidateKeys: string[]): string {
  for (const key of candidateKeys) {
    const rawValue = row[key];
    if (rawValue === null || rawValue === undefined || rawValue === '') {
      continue;
    }
    return String(rawValue);
  }
  return '--';
}

function formatPreviewFieldValueSummary(
  row: PreviewTableRow,
  pairs: ReconFieldPairDraft[],
  side: 'match' | 'left_compare' | 'right_compare',
): string {
  const normalizedPairs = filterCompleteReconFieldPairs(pairs);
  if (normalizedPairs.length === 0) return '--';
  return normalizedPairs
    .map((pair) => {
      if (side === 'match') {
        const value = resolvePreviewFieldValue(row, [
          `source_${pair.leftField}`,
          pair.leftField,
          `target_${pair.rightField}`,
          pair.rightField,
          'match_key',
          'biz_key',
        ]);
        return normalizedPairs.length === 1 ? value : `${pair.leftField}: ${value}`;
      }
      if (side === 'left_compare') {
        const value = resolvePreviewFieldValue(row, [`source_${pair.leftField}`, pair.leftField]);
        return normalizedPairs.length === 1 ? value : `${pair.leftField}: ${value}`;
      }
      const value = resolvePreviewFieldValue(row, [`target_${pair.rightField}`, pair.rightField]);
      return normalizedPairs.length === 1 ? value : `${pair.rightField}: ${value}`;
    })
    .join('；');
}

function buildReconResultFieldLabelMap(
  matchFieldPairs: ReconFieldPairDraft[],
  compareFieldPairs: ReconFieldPairDraft[],
): Record<string, string> {
  const matchLabel = filterCompleteReconFieldPairs(matchFieldPairs)
    .map((pair) => pair.leftField.trim())
    .filter(Boolean)
    .join('、');
  const leftCompareLabel = filterCompleteReconFieldPairs(compareFieldPairs)
    .map((pair) => pair.leftField.trim())
    .filter(Boolean)
    .join('、');
  const rightCompareLabel = filterCompleteReconFieldPairs(compareFieldPairs)
    .map((pair) => pair.rightField.trim())
    .filter(Boolean)
    .join('、');
  return {
    match_fields: matchLabel ? `匹配字段（${matchLabel}）` : '匹配字段',
    left_compare_fields: leftCompareLabel ? `左侧对比字段（${leftCompareLabel}）` : '左侧对比字段',
    right_compare_fields: rightCompareLabel ? `右侧对比字段（${rightCompareLabel}）` : '右侧对比字段',
    result: '对账结果',
  };
}

function parseReconDraftConfig({
  matchFieldPairs,
  compareFieldPairs,
  matchKey,
  leftAmountField,
  rightAmountField,
  leftTimeSemantic,
  rightTimeSemantic,
  tolerance,
}: Pick<
  SchemeDraft,
  | 'matchFieldPairs'
  | 'compareFieldPairs'
  | 'matchKey'
  | 'leftAmountField'
  | 'rightAmountField'
  | 'leftTimeSemantic'
  | 'rightTimeSemantic'
  | 'tolerance'
>): ParsedReconDraftConfig {
  const normalizedMatchFieldPairs = normalizeReconFieldPairs(
    matchFieldPairs,
    matchKey ? [{ leftField: matchKey, rightField: matchKey }] : [],
  );
  const normalizedCompareFieldPairs = normalizeReconFieldPairs(
    compareFieldPairs,
    leftAmountField || rightAmountField
      ? [{ leftField: leftAmountField, rightField: rightAmountField }]
      : [],
  );
  return {
    matchFieldPairs: normalizedMatchFieldPairs,
    compareFieldPairs: normalizedCompareFieldPairs,
    matchKey: resolveFirstReconFieldPairValue(normalizedMatchFieldPairs, 'left', matchKey || ''),
    leftAmountField: resolveFirstReconFieldPairValue(
      normalizedCompareFieldPairs,
      'left',
      leftAmountField || '',
    ),
    rightAmountField: resolveFirstReconFieldPairValue(
      normalizedCompareFieldPairs,
      'right',
      rightAmountField || '',
    ),
    leftTimeSemantic: leftTimeSemantic || '',
    rightTimeSemantic: rightTimeSemantic || '',
    tolerance: tolerance || '0.00',
  };
}

function parseReconRuleJsonConfig(
  json: Record<string, unknown>,
  fallback: Partial<ParsedReconDraftConfig> = {},
): ParsedReconDraftConfig {
  const rules = Array.isArray(json.rules) ? json.rules : [];
  const firstRule = asRecord(rules[0]);
  const recon = asRecord(firstRule.recon);
  const keyColumns = asRecord(recon.key_columns);
  const compareColumns = asRecord(recon.compare_columns);
  const mappings = Array.isArray(keyColumns.mappings) ? keyColumns.mappings : [];
  const columns = Array.isArray(compareColumns.columns) ? compareColumns.columns : [];
  const normalizedMatchFieldPairs = normalizeReconFieldPairs(
    mappings.map((item) => {
      const record = asRecord(item);
      return {
        left_field: toText(record.source_field).trim(),
        right_field: toText(record.target_field).trim(),
      };
    }),
    fallback.matchFieldPairs || (fallback.matchKey ? [{ leftField: fallback.matchKey, rightField: fallback.matchKey }] : []),
  );
  const normalizedCompareFieldPairs = normalizeReconFieldPairs(
    columns.map((item) => {
      const record = asRecord(item);
      return {
        left_field: toText(record.source_column).trim(),
        right_field: toText(record.target_column).trim(),
      };
    }),
    fallback.compareFieldPairs || (
      fallback.leftAmountField || fallback.rightAmountField
        ? [{ leftField: fallback.leftAmountField || '', rightField: fallback.rightAmountField || '' }]
        : []
    ),
  );
  const firstColumn = asRecord(columns[0]);

  return {
    matchFieldPairs: normalizedMatchFieldPairs,
    compareFieldPairs: normalizedCompareFieldPairs,
    matchKey: resolveFirstReconFieldPairValue(normalizedMatchFieldPairs, 'left', fallback.matchKey || ''),
    leftAmountField: resolveFirstReconFieldPairValue(
      normalizedCompareFieldPairs,
      'left',
      fallback.leftAmountField || '',
    ),
    rightAmountField: resolveFirstReconFieldPairValue(
      normalizedCompareFieldPairs,
      'right',
      fallback.rightAmountField || '',
    ),
    leftTimeSemantic: toText(
      json.left_time_semantic,
      toText(firstRule.left_time_semantic, fallback.leftTimeSemantic || ''),
    ),
    rightTimeSemantic: toText(
      json.right_time_semantic,
      toText(firstRule.right_time_semantic, fallback.rightTimeSemantic || ''),
    ),
    tolerance: toText(firstColumn.tolerance, fallback.tolerance || '0'),
  };
}

function renderPreparedFieldOptionLabel(fieldName: string): string {
  const normalized = fieldName.trim();
  return PREPARED_OUTPUT_FIELD_LABEL_MAP[normalized] || humanizeProcDescription(normalized).trim() || normalized;
}

function buildOutputFieldLabelMap(
  fields: OutputFieldDraft[],
  sources: SchemeSourceDraft[] = [],
): Record<string, string> {
  const labels: Record<string, string> = {};
  const sourceLabelMaps = new Map(
    sources.map((source) => [source.id, source.fieldLabelMap || {}] as const),
  );
  fields.forEach((field) => {
    const outputName = field.outputName.trim();
    if (!outputName) return;
    const sourceFieldLabel = field.sourceDatasetId && field.sourceField
      ? sourceLabelMaps.get(field.sourceDatasetId)?.[field.sourceField]?.trim()
      : '';
    labels[outputName] = sourceFieldLabel || renderPreparedFieldOptionLabel(outputName);
  });
  return labels;
}

function buildProcOutputFieldLabelMap(
  ruleJson: Record<string, unknown>,
  targetTable: string,
  sources: SchemeSourceDraft[],
): Record<string, string> {
  const labels: Record<string, string> = {};
  const sourceFieldLabels = Object.assign({}, ...sources.map((source) => source.fieldLabelMap || {}));
  asList(ruleJson.steps).forEach((item) => {
    const step = asRecord(item);
    if (toText(step.target_table).trim() !== targetTable) return;

    asList(asRecord(step.schema).columns).forEach((columnItem) => {
      const column = asRecord(columnItem);
      const name = toText(column.name, toText(column.column_name)).trim();
      const label = toText(column.label, toText(column.display_name)).trim();
      if (name && label) {
        labels[name] = label;
      }
    });

    asList(step.mappings).forEach((mappingItem) => {
      const mapping = asRecord(mappingItem);
      const targetField = toText(mapping.target_field).trim();
      if (!targetField || labels[targetField]) return;
      const value = asRecord(mapping.value);
      if (toText(value.type).trim() !== 'source') return;
      const sourceField = toText(asRecord(value.source).field, toText(value.field)).trim();
      const sourceLabel = sourceFieldLabels[sourceField]?.trim();
      if (sourceLabel) {
        labels[targetField] = sourceLabel;
      }
    });
  });
  return labels;
}

function mergeLabelMaps(...maps: Array<Record<string, string> | undefined>): Record<string, string> {
  return Object.assign({}, ...maps.filter(Boolean));
}

function scoreMatchFieldCandidate(rawName: string): number {
  const raw = rawName.trim().toLowerCase();
  if (!raw) return Number.NEGATIVE_INFINITY;

  let score = 0;
  if (/(^biz_key$|match_key|unique_key|primary_key|pk|order_no|order_id|trade_no|trade_id|transaction_id|serial_no|ledger_id|record_id)/.test(raw)) {
    score += 16;
  }
  if (/(key|id|no|code|sn|uuid|number|identifier)/.test(raw)) {
    score += 8;
  }
  if (/(amount|amt|money|fee|price|balance|date|time|status|type|name|desc|remark)/.test(raw)) {
    score -= 6;
  }
  return score;
}

function scoreAmountFieldCandidate(rawName: string): number {
  const raw = rawName.trim().toLowerCase();
  if (!raw) return Number.NEGATIVE_INFINITY;

  let score = 0;
  if (/(^amount$|gross_amount|net_amount|booked_amount|paid_amount|settled_amount|total_amount|tax_amount)/.test(raw)) {
    score += 16;
  }
  if (/(amount|amt|money|fee|price|balance|total|income|payment|paid|booked|settled|tax|cost)/.test(raw)) {
    score += 8;
  }
  if (/(id|code|date|time|status|type|name|desc|remark|order)/.test(raw)) {
    score -= 6;
  }
  return score;
}

function buildReconFieldOptions(
  fields: OutputFieldDraft[],
  fallbackValue = '',
  scorer?: (fieldName: string, label: string) => number,
  preferredRole: OutputFieldSemanticRole = 'normal',
  fieldLabelMap?: Record<string, string>,
  options?: { onlyTimeRelated?: boolean; includeFallback?: boolean },
): ReconFieldOption[] {
  const optionMap = new Map<string, { value: string; label: string; score: number }>();
  fields.forEach((field) => {
    const value = field.outputName.trim();
    if (!value) return;
    const label = fieldLabelMap?.[value] || renderPreparedFieldOptionLabel(value);
    const role = normalizeOutputFieldSemanticRole(field.semanticRole);
    if (options?.onlyTimeRelated && role !== 'time_field' && !isTimeRelatedFieldName(value, label)) {
      return;
    }
    optionMap.set(value, {
      value,
      label,
      score: (scorer ? scorer(value, label) : 0) + (preferredRole !== 'normal' && role === preferredRole ? 100 : 0),
    });
  });
  const normalizedFallback = fallbackValue.trim();
  const fallbackLabel = fieldLabelMap?.[normalizedFallback] || renderPreparedFieldOptionLabel(normalizedFallback);
  const shouldIncludeFallback = options?.includeFallback !== false
    && normalizedFallback
    && !optionMap.has(normalizedFallback)
    && (!options?.onlyTimeRelated || isTimeRelatedFieldName(normalizedFallback, fallbackLabel));
  if (shouldIncludeFallback) {
    optionMap.set(fallbackValue.trim(), {
      value: fallbackValue.trim(),
      label: fallbackLabel,
      score: 999,
    });
  }
  return Array.from(optionMap.values())
    .sort((left, right) => right.score - left.score || left.label.localeCompare(right.label, 'zh-CN'))
    .map(({ value, label }) => ({ value, label }));
}

function buildAllReconFieldOptions(
  fields: OutputFieldDraft[],
  fieldLabelMap?: Record<string, string>,
): ReconFieldOption[] {
  return buildReconFieldOptions(fields, '', undefined, 'normal', fieldLabelMap);
}

function buildStructuredReconDraftText(config: {
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
}): string {
  return [
    `# ${config.reconRuleName.trim() || '数据对账逻辑'}`,
    `匹配字段: ${resolveReconFieldPairsSummary(config.matchFieldPairs)}`,
    `对比字段: ${resolveReconFieldPairsSummary(config.compareFieldPairs)}`,
    '识别方式：按匹配字段对齐左右记录，再逐项比较对比字段差异。',
  ].join('\n');
}

function buildLocalReconRuleJson(config: {
  schemeName: string;
  businessGoal: string;
  reconRuleName: string;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
}): Record<string, unknown> {
  const matchFieldPairs = filterCompleteReconFieldPairs(config.matchFieldPairs);
  const compareFieldPairs = filterCompleteReconFieldPairs(config.compareFieldPairs);
  if (matchFieldPairs.length === 0) {
    throw new Error('请至少配置一组完整的匹配字段。');
  }
  if (compareFieldPairs.length === 0) {
    throw new Error('请至少配置一组完整的对比字段。');
  }

  const ruleName = config.reconRuleName.trim() || buildDefaultReconRuleName(config.schemeName);
  const tolerance = 0;
  const signature = [
    ruleName,
    ...matchFieldPairs.map((pair) => `${pair.leftField}:${pair.rightField}`),
    ...compareFieldPairs.map((pair) => `${pair.leftField}:${pair.rightField}`),
  ].join('|');

  return {
    rule_id: `wizard_recon_${hashText(signature)}`,
    rule_name: ruleName,
    description: config.businessGoal.trim() || `${ruleName} 自动生成对账逻辑`,
    schema_version: '1.6',
    rules: [
      {
        enabled: true,
        source_file: {
          table_name: 'left_recon_ready',
          identification: {
            match_by: 'table_name',
            match_value: 'left_recon_ready',
            match_strategy: 'exact',
          },
        },
        target_file: {
          table_name: 'right_recon_ready',
          identification: {
            match_by: 'table_name',
            match_value: 'right_recon_ready',
            match_strategy: 'exact',
          },
        },
        recon: {
          key_columns: {
            source_field: matchFieldPairs[0].leftField,
            target_field: matchFieldPairs[0].rightField,
            mappings: matchFieldPairs.map((pair) => ({
              source_field: pair.leftField,
              target_field: pair.rightField,
            })),
          },
          compare_columns: {
            columns: compareFieldPairs.map((pair) => ({
              name: pair.leftField === pair.rightField
                ? pair.leftField
                : `${pair.leftField} ↔ ${pair.rightField}`,
              source_column: pair.leftField,
              target_column: pair.rightField,
              tolerance,
            })),
          },
        },
        output: {
          format: 'xlsx',
          sheets: {
            summary: { name: '核对汇总', enabled: true },
            source_only: { name: '左侧独有', enabled: true },
            target_only: { name: '右侧独有', enabled: true },
            matched_with_diff: { name: '差异记录', enabled: true },
          },
        },
      },
    ],
  };
}

function stripReconTimeSemantics(ruleJson: Record<string, unknown>): Record<string, unknown> {
  const nextRule = { ...ruleJson };
  delete nextRule.left_time_semantic;
  delete nextRule.right_time_semantic;
  delete nextRule.time_semantic;
  const rules = asList(nextRule.rules).map((rawRule) => {
    const rule = asRecord(rawRule);
    const nextItem = { ...rule };
    delete nextItem.left_time_semantic;
    delete nextItem.right_time_semantic;
    delete nextItem.time_semantic;
    return nextItem;
  });
  if (rules.length > 0) {
    nextRule.rules = rules;
  }
  return nextRule;
}

function buildPreparedOutputFieldPayload(fields: OutputFieldDraft[]): Array<Record<string, unknown>> {
  return fields.map((field) => ({
    output_name: field.outputName.trim(),
    semantic_role: normalizeOutputFieldSemanticRole(field.semanticRole),
    value_mode: field.valueMode,
    source_dataset_id: field.sourceDatasetId,
    source_field: field.sourceField.trim(),
    fixed_value: field.fixedValue.trim(),
    formula: field.formula.trim(),
    concat_delimiter: field.concatDelimiter,
    concat_parts: field.concatParts.map((part) => ({
      dataset_id: part.datasetId,
      field_name: part.fieldName.trim(),
    })),
  }));
}

interface SourceFieldCandidate {
  rawName: string;
  label: string;
  schemaType: string;
  matchScore: number;
  amountScore: number;
  dateScore: number;
}

function collectSourceFieldCandidates(source: SchemeSourceOption): SourceFieldCandidate[] {
  const fieldLabelMap = resolveSourceFieldLabelMap(source) || {};
  const keyFieldSet = new Set(normalizeStringList(source.keyFields).map((item) => item.trim()));
  const rawNames = Array.from(
    new Set<string>([
      ...extractSchemaFieldNames(source.schemaSummary),
      ...Object.keys(fieldLabelMap),
    ]),
  ).map((item) => item.trim()).filter(Boolean);

  return rawNames.map((rawName) => {
    const label = toText(fieldLabelMap[rawName], rawName);
    return {
      rawName,
      label,
      schemaType: normalizeSchemaType(asRecord(source.schemaSummary)[rawName]),
      matchScore:
        scoreMatchFieldCandidate(rawName)
        + (keyFieldSet.has(rawName) ? 24 : 0)
        + (/(订单|单号|流水|业务|交易|凭证|识别|唯一|主键|编号)/.test(label) ? 4 : 0),
      amountScore:
        scoreAmountFieldCandidate(rawName)
        + (/(金额|实收|实付|收入|支出|收款|付款|入账|到账|结算|含税|未税)/.test(label) ? 4 : 0),
      dateScore: scoreDateFieldCandidate(rawName, label),
    };
  });
}

function buildRecommendedOutputFieldsForSources(
  sources: SchemeSourceOption[],
): OutputFieldDraft[] {
  const source = sources[0];
  if (!source) return [];

  const candidates = collectSourceFieldCandidates(source);
  if (candidates.length === 0) return [];

  const usedRawNames = new Set<string>();
  const nextFields: OutputFieldDraft[] = [];

  const appendSourceField = (
    outputName: string,
    candidate: SourceFieldCandidate | undefined,
    semanticRole: OutputFieldSemanticRole,
  ) => {
    if (!candidate || usedRawNames.has(candidate.rawName)) return;
    usedRawNames.add(candidate.rawName);
    const draft = createOutputFieldDraft(outputName);
    draft.semanticRole = semanticRole;
    draft.valueMode = 'source_field';
    draft.sourceDatasetId = source.id;
    draft.sourceField = candidate.rawName;
    nextFields.push(draft);
  };

  const keyCandidate =
    [...candidates].sort((left, right) => right.matchScore - left.matchScore)[0]
    || candidates[0];
  appendSourceField('业务单号', keyCandidate, 'match_key');

  const amountCandidate = [...candidates]
    .filter((candidate) => !usedRawNames.has(candidate.rawName))
    .sort((left, right) => right.amountScore - left.amountScore)[0];
  if (amountCandidate && amountCandidate.amountScore > 0) {
    appendSourceField('金额', amountCandidate, 'compare_field');
  }

  const dateCandidate = [...candidates]
    .filter((candidate) => !usedRawNames.has(candidate.rawName))
    .sort((left, right) => right.dateScore - left.dateScore)[0];
  if (dateCandidate && dateCandidate.dateScore > 0) {
    appendSourceField('业务时间', dateCandidate, 'time_field');
  }

  return nextFields;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function sourceHasRecommendationMetadata(source: SchemeSourceOption): boolean {
  if (source.fieldLabelMap && Object.keys(source.fieldLabelMap).length > 0) {
    return true;
  }
  return extractSchemaFieldNames(source.schemaSummary).length > 0;
}

function inferFixedValueFormulaExpr(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '""';
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) {
    return trimmed;
  }
  return JSON.stringify(trimmed);
}

function inferOutputFieldDataType(
  field: OutputFieldDraft,
  sourceMap: Map<string, SchemeSourceOption>,
): 'string' | 'decimal' | 'date' {
  const outputName = field.outputName.trim();
  const lowerOutputName = outputName.toLowerCase();
  const source = sourceMap.get(field.sourceDatasetId);
  const fieldCandidates = source ? collectSourceFieldCandidates(source) : [];
  const matchedSourceField = fieldCandidates.find((item) => item.rawName === field.sourceField.trim());
  const sourceSchemaType = matchedSourceField?.schemaType || '';

  if (field.valueMode === 'source_field') {
    if (sourceSchemaType === 'date' || sourceSchemaType === 'datetime') return 'date';
    if (sourceSchemaType === 'number' || sourceSchemaType === 'integer' || sourceSchemaType === 'decimal') {
      return 'decimal';
    }
  }

  if (
    field.valueMode === 'fixed_value'
    && /^-?\d+(?:\.\d+)?$/.test(field.fixedValue.trim())
  ) {
    return 'decimal';
  }

  if (field.valueMode === 'concat') return 'string';

  if (scoreDateFieldCandidate(outputName, outputName) > 0 || /(time|date|日期|时间)/i.test(lowerOutputName)) {
    return 'date';
  }
  if (scoreAmountFieldCandidate(outputName) > 0 || /(金额|amount|amt|fee|price|money)/i.test(outputName)) {
    return 'decimal';
  }
  return 'string';
}

function buildFormulaBindingsForSource(
  source: SchemeSourceOption,
  alias: string,
): Record<string, Record<string, unknown>> {
  const bindings: Record<string, Record<string, unknown>> = {};
  collectSourceFieldCandidates(source).forEach((candidate) => {
    bindings[candidate.rawName] = {
      type: 'source',
      source: {
        alias,
        field: candidate.rawName,
      },
    };
  });
  return bindings;
}

function validateOutputFieldsForCompilation(
  side: 'left' | 'right',
  sources: SchemeSourceOption[],
  fields: OutputFieldDraft[],
): void {
  if (sources.length !== 1) {
    throw new Error(`请先选择${side === 'left' ? '左侧' : '右侧'}数据集，当前版本每侧仅支持 1 个数据集。`);
  }
  const namedFields = fields.filter((field) => field.outputName.trim());
  if (namedFields.length === 0) {
    throw new Error(`请先配置${side === 'left' ? '左侧' : '右侧'}输出字段。`);
  }
  const duplicatedField = namedFields
    .map((field) => field.outputName.trim())
    .find((name, index, items) => items.indexOf(name) !== index);
  if (duplicatedField) {
    throw new Error(`${side === 'left' ? '左侧' : '右侧'}输出字段存在重复字段名：${duplicatedField}`);
  }

  namedFields.forEach((field, index) => {
    if (field.valueMode === 'source_field') {
      if (!field.sourceField.trim()) {
        throw new Error(`${side === 'left' ? '左侧' : '右侧'}字段 ${index + 1} 未选择来源字段。`);
      }
      return;
    }
    if (field.valueMode === 'formula' && !field.formula.trim()) {
      throw new Error(`${side === 'left' ? '左侧' : '右侧'}字段 ${index + 1} 的公式不能为空。`);
    }
    if (field.valueMode === 'concat') {
      if (field.concatParts.length === 0) {
        throw new Error(`${side === 'left' ? '左侧' : '右侧'}字段 ${index + 1} 至少需要 1 个拼接字段。`);
      }
      field.concatParts.forEach((part, partIndex) => {
        if (!part.fieldName.trim()) {
          throw new Error(
            `${side === 'left' ? '左侧' : '右侧'}字段 ${index + 1} 的拼接字段 ${partIndex + 1} 未选择来源字段。`,
          );
        }
      });
    }
  });
}

function buildProcMappingFromOutputField(
  field: OutputFieldDraft,
  options: {
    fallbackSource: SchemeSourceOption;
    sourceMap: Map<string, SchemeSourceOption>;
    aliasMap: Map<string, string>;
  },
): Record<string, unknown> {
  const { fallbackSource, sourceMap, aliasMap } = options;
  const outputName = field.outputName.trim();
  if (!outputName) {
    throw new Error('输出字段名不能为空。');
  }

  if (field.valueMode === 'source_field') {
    const datasetId = field.sourceDatasetId || fallbackSource.id;
    const source = sourceMap.get(datasetId) || fallbackSource;
    const alias = aliasMap.get(source.id) || aliasMap.get(fallbackSource.id) || 'source_1';
    return {
      target_field: outputName,
      value: {
        type: 'source',
        source: {
          alias,
          field: field.sourceField.trim(),
        },
      },
      field_write_mode: 'overwrite',
    };
  }

  if (field.valueMode === 'fixed_value') {
    return {
      target_field: outputName,
      value: {
        type: 'formula',
        expr: inferFixedValueFormulaExpr(field.fixedValue),
      },
      field_write_mode: 'overwrite',
    };
  }

  if (field.valueMode === 'formula') {
    const datasetId = field.sourceDatasetId || fallbackSource.id;
    const source = sourceMap.get(datasetId) || fallbackSource;
    const alias = aliasMap.get(source.id) || aliasMap.get(fallbackSource.id) || 'source_1';
    return {
      target_field: outputName,
      value: {
        type: 'formula',
        expr: field.formula.trim(),
      },
      bindings: buildFormulaBindingsForSource(source, alias),
      field_write_mode: 'overwrite',
    };
  }

  const parts = field.concatParts
    .map((part, index) => {
      const datasetId = part.datasetId || fallbackSource.id;
      const source = sourceMap.get(datasetId) || fallbackSource;
      const alias = aliasMap.get(source.id) || aliasMap.get(fallbackSource.id) || 'source_1';
      return {
        expr: `coalesce({part_${index}}, '')`,
        binding: {
          type: 'source',
          source: {
            alias,
            field: part.fieldName.trim(),
          },
        },
      };
    })
    .filter((item) => item.binding.source.field);
  const delimiter = JSON.stringify(field.concatDelimiter || '');
  const expr = parts
    .map((item, index) => (index === 0 ? item.expr : `${delimiter} + ${item.expr}`))
    .join(' + ');
  return {
    target_field: outputName,
    value: {
      type: 'formula',
      expr: expr || '""',
    },
    bindings: Object.fromEntries(parts.map((item, index) => [`part_${index}`, item.binding])),
    field_write_mode: 'overwrite',
  };
}

function buildLocalProcRuleJson(options: {
  schemeName: string;
  businessGoal: string;
  leftSources: SchemeSourceOption[];
  rightSources: SchemeSourceOption[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
}): Record<string, unknown> {
  validateOutputFieldsForCompilation('left', options.leftSources, options.leftOutputFields);
  validateOutputFieldsForCompilation('right', options.rightSources, options.rightOutputFields);

  const buildSideSteps = (
    side: 'left' | 'right',
    sources: SchemeSourceOption[],
    fields: OutputFieldDraft[],
  ) => {
    const source = sources[0];
    const targetTable = side === 'left' ? 'left_recon_ready' : 'right_recon_ready';
    const createStepId = `create_${targetTable}`;
    const writeStepId = `${side}_write_recon_ready`;
    const alias = `${side}_source_1`;
    const sourceMap = new Map(sources.map((item) => [item.id, item]));
    const aliasMap = new Map(sources.map((item) => [item.id, alias]));
    const namedFields = fields.filter((field) => field.outputName.trim());

    return [
      {
        step_id: createStepId,
        action: 'create_schema',
        target_table: targetTable,
        schema: {
          columns: namedFields.map((field) => ({
            name: field.outputName.trim(),
            data_type: inferOutputFieldDataType(field, sourceMap),
          })),
        },
      },
      {
        step_id: writeStepId,
        action: 'write_dataset',
        target_table: targetTable,
        depends_on: [createStepId],
        row_write_mode: 'upsert',
        sources: [
          {
            table: resolveDatasetTableName(source),
            alias,
          },
        ],
        mappings: namedFields.map((field) =>
          buildProcMappingFromOutputField(field, {
            fallbackSource: source,
            sourceMap,
            aliasMap,
          }),
        ),
      },
    ];
  };

  return {
    role_desc: options.businessGoal.trim() || `${options.schemeName.trim() || '未命名方案'}整理规则`,
    file_rule_code: '',
    version: '4.5',
    steps: [
      ...buildSideSteps('left', options.leftSources, options.leftOutputFields),
      ...buildSideSteps('right', options.rightSources, options.rightOutputFields),
    ],
  };
}

function extractSchemaFieldNames(schemaSummary: Record<string, unknown> | undefined): string[] {
  const summary = asRecord(schemaSummary);
  const columns = asList(summary.columns);
  if (columns.length > 0) {
    return columns
      .map((item) => {
        const column = asRecord(item);
        return toText(column.name, toText(column.column_name)).trim();
      })
      .filter(Boolean);
  }
  return Object.keys(summary).filter((key) => key !== 'columns');
}

function scoreDateFieldCandidate(rawName: string, label: string): number {
  const raw = rawName.trim().toLowerCase();
  if (!raw) return Number.NEGATIVE_INFINITY;

  let score = 0;
  if (/(biz_date|business_date|accounting_date|trade_time|trade_date|payment_time|pay_time|gmt_payment|gmt_create|created_at|updated_at|occurred_at|happened_at|booked_at|settle_date|settle_time|posting_date|entry_date)/.test(raw)) {
    score += 12;
  }
  if (/(date|time|day|dt|gmt|created|updated|trade|payment|pay|settle|account|book|occur|happen|posting|entry)/.test(raw)) {
    score += 6;
  }
  if (/(日期|时间|时刻|账期|交易|支付|付款|入账|到账|创建|更新|结算|记账|发生|下单|业务)/.test(label || rawName)) {
    score += 8;
  }
  if (/(id|code|amount|amt|fee|price|status|name|type|order|key|remark|desc|flag)/.test(raw)) {
    score -= 6;
  }
  return score;
}

function isTimeRelatedFieldName(rawName: string, label: string): boolean {
  const raw = rawName.trim().toLowerCase();
  const display = label.trim();
  if (!raw && !display) return false;
  const rawHasTimeToken = /(^|[_\-.])(date|time|datetime|timestamp|dt|day)([_\-.]|$)|(^|[_\-.])gmt[_\-.]?|created_at|updated_at|occurred_at|happened_at|booked_at|posted_at|settled_at|paid_at|completed_at|finished_at/.test(raw);
  const labelHasTimeToken = /(日期|时间|时刻|账期|期间|年月|年度|月份|自然日|业务日|结算日|记账日|入账日|发生日|完成日|创建日|更新日|支付日|付款日|下单日)/.test(display);
  return rawHasTimeToken || labelHasTimeToken;
}

function SummaryBadge({ label, value }: { label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-text-secondary">
      <span>{label}</span>
      <span className="rounded-full bg-surface-secondary px-1.5 py-0.5 text-text-primary">
        {value}
      </span>
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="text-xs text-text-secondary">{label}</span>
      <span className="max-w-[70%] text-right text-sm text-text-primary">{value || '--'}</span>
    </div>
  );
}

function dedupeTextList(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function collectReconSideFieldValues(
  side: 'left' | 'right',
  pairs: ReconFieldPairDraft[],
): string[] {
  return dedupeTextList(
    filterCompleteReconFieldPairs(pairs).map((pair) => (side === 'left' ? pair.leftField : pair.rightField)),
  );
}

function formatDetailFieldValues(
  values: string[],
  fieldLabelMap: Record<string, string>,
): string[] {
  return dedupeTextList(values).map((value) => fieldLabelMap[value] || renderPreparedFieldOptionLabel(value));
}

function DetailListRow({ label, values }: { label: string; values: string[] }) {
  const normalizedValues = dedupeTextList(values);

  return (
    <div className="py-2">
      <p className="text-xs text-text-secondary">{label}</p>
      <div className="mt-2 space-y-1.5 text-sm text-text-primary">
        {normalizedValues.length > 0 ? (
          normalizedValues.map((value) => (
            <p key={`${label}-${value}`} className="leading-6">
              {value}
            </p>
          ))
        ) : (
          <p className="leading-6 text-text-secondary">--</p>
        )}
      </div>
    </div>
  );
}

function ListHeader({ columns, template }: { columns: string[]; template: string }) {
  return (
    <div
      className="grid items-center gap-6 border-b border-border-subtle px-5 py-3 text-[11px] font-semibold tracking-[0.14em] text-text-muted"
      style={{ gridTemplateColumns: template }}
    >
      {columns.map((column, index) => (
        <span key={column} className={index === columns.length - 1 ? 'justify-self-end' : undefined}>
          {column}
        </span>
      ))}
    </div>
  );
}

function WizardStepBadge({
  active,
  completed,
  index,
  title,
  description,
}: {
  active: boolean;
  completed: boolean;
  index: number;
  title: string;
  description: string;
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border px-4 py-3 transition-colors',
        active
          ? 'border-sky-200 bg-sky-50'
          : completed
          ? 'border-emerald-200 bg-emerald-50'
          : 'border-border bg-surface-secondary',
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold',
            active
              ? 'bg-sky-600 text-white'
              : completed
              ? 'bg-emerald-600 text-white'
              : 'bg-surface text-text-secondary',
          )}
        >
          {index}
        </span>
        <span className="text-sm font-semibold text-text-primary">{title}</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-text-secondary">{description}</p>
    </div>
  );
}

export default function ReconWorkspace({
  mode = 'center',
  authToken,
  onOpenCollaborationChannels,
  onSchemeCreated,
  children,
}: ReconWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<ReconCenterTab>('schemes');
  const [schemes, setSchemes] = useState<ReconSchemeListItem[]>([]);
  const [tasks, setTasks] = useState<ReconTaskListItem[]>([]);
  const [runs, setRuns] = useState<ReconCenterRunItem[]>([]);
  const [exceptionsByRunId, setExceptionsByRunId] = useState<Record<string, ReconRunExceptionDetail[]>>({});
  const [availableChannels, setAvailableChannels] = useState<CollaborationChannelListItem[]>([]);
  const [loadingCenter, setLoadingCenter] = useState(false);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [loadingExceptionsRunId, setLoadingExceptionsRunId] = useState<string | null>(null);
  const [centerError, setCenterError] = useState<string | null>(null);
  const [centerNotice, setCenterNotice] = useState<string | null>(null);
  const [schemeDeleteGuard, setSchemeDeleteGuard] = useState<{
    schemeId: string;
    message: string;
    tasks: Array<{
      id: string;
      name: string;
      scheduleLabel: string;
      statusLabel: string;
    }>;
  } | null>(null);
  const [focusedTaskId, setFocusedTaskId] = useState<string | null>(null);
  const [channelLoadError, setChannelLoadError] = useState('');
  const [modalState, setModalState] = useState<CenterModalState | null>(null);
  const [schemeWizardStep, setSchemeWizardStep] = useState<SchemeWizardStep>(1);
  const [procBuildMode, setProcBuildMode] = useState<ProcBuildMode>('ai_complex_rule');
  const [aiProcSideDrafts, setAiProcSideDrafts] = useState<Record<AiProcSide, AiProcSideDraft>>(() =>
    createEmptyAiProcSideDrafts(),
  );
  const aiProcSideDraftsRef = useRef<Record<AiProcSide, AiProcSideDraft>>(aiProcSideDrafts);
  const [wizardDraftState, setWizardDraftState] = useState<SchemeWizardDraftState>(() =>
    createEmptySchemeWizardDraftState(),
  );
  const [designSessionId, setDesignSessionId] = useState('');
  const [planDraft, setPlanDraft] = useState<PlanDraft>(EMPTY_PLAN_DRAFT);
  const [modalError, setModalError] = useState<string | null>(null);
  const [isSubmittingScheme, setIsSubmittingScheme] = useState(false);
  const [isSubmittingPlan, setIsSubmittingPlan] = useState(false);
  const [ownerCandidates, setOwnerCandidates] = useState<OwnerCandidate[]>([]);
  const [ownerSearchMessage, setOwnerSearchMessage] = useState('');
  const [isTrialingProc, setIsTrialingProc] = useState(false);
  const [isTrialingRecon, setIsTrialingRecon] = useState(false);
  const [wizardJsonPanel, setWizardJsonPanel] = useState<'proc' | 'recon' | null>(null);
  const [wizardProcJsonView, setWizardProcJsonView] = useState<'proc' | 'inputPlan'>('proc');
  const [wizardReconJsonView, setWizardReconJsonView] = useState<'proc' | 'recon'>('recon');
  const [procTrialPreview, setProcTrialPreview] = useState<ProcTrialPreview | null>(null);
  const [reconTrialPreview, setReconTrialPreview] = useState<ReconTrialPreview | null>(null);
  const [rerunningRunId, setRerunningRunId] = useState<string | null>(null);
  const [selectedExceptionDetail, setSelectedExceptionDetail] = useState<ReconRunExceptionDetail | null>(null);
  const [wizardJsonCopyState, setWizardJsonCopyState] = useState<{
    panel: 'proc' | 'inputPlan' | 'recon';
    status: 'success' | 'error';
  } | null>(null);
  const taskRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const aiProcAbortControllersRef = useRef<Partial<Record<AiProcSide, AbortController>>>({});
  const aiProcGenerationSeqRef = useRef<Record<AiProcSide, number>>({ left: 0, right: 0 });
  const schemeDraft = useMemo<SchemeDraft>(() => buildLegacySchemeDraftSnapshot(wizardDraftState), [wizardDraftState]);
  const selectedLeftSources = wizardDraftState.preparation.leftSources as SchemeSourceOption[];
  const selectedRightSources = wizardDraftState.preparation.rightSources as SchemeSourceOption[];
  const leftOutputFields = wizardDraftState.preparation.leftOutputFields;
  const rightOutputFields = wizardDraftState.preparation.rightOutputFields;
  const procCompatibilityState = wizardDraftState.derived.procCompatibility as CompatibilityCheckResult;
  const reconCompatibilityState = wizardDraftState.derived.reconCompatibility as CompatibilityCheckResult;
  const setSchemeDraft = useCallback((updater: SetStateAction<SchemeDraft>) => {
    setWizardDraftState((prev) => {
      const prevDraft = buildLegacySchemeDraftSnapshot(prev);
      const nextDraft = typeof updater === 'function'
        ? (updater as (value: SchemeDraft) => SchemeDraft)(prevDraft)
        : updater;
      return applyLegacySchemeDraftSnapshot(prev, nextDraft);
    });
  }, []);
  const setProcCompatibility = useCallback((next: SetStateAction<CompatibilityCheckResult>) => {
    setWizardDraftState((prev) =>
      updateDerivedDraft(prev, {
        procCompatibility:
          typeof next === 'function'
            ? (next as (value: CompatibilityCheckResult) => CompatibilityCheckResult)(
                prev.derived.procCompatibility as CompatibilityCheckResult,
              )
            : next,
      }),
    );
  }, []);
  const setReconCompatibility = useCallback((next: SetStateAction<CompatibilityCheckResult>) => {
    setWizardDraftState((prev) =>
      updateDerivedDraft(prev, {
        reconCompatibility:
          typeof next === 'function'
            ? (next as (value: CompatibilityCheckResult) => CompatibilityCheckResult)(
                prev.derived.reconCompatibility as CompatibilityCheckResult,
              )
            : next,
      }),
    );
  }, []);

  const channelById = useMemo(
    () => new Map(availableChannels.map((item) => [item.id, item])),
    [availableChannels],
  );
  const selectedPlanScheme = useMemo(
    () => schemes.find((scheme) => scheme.schemeCode === planDraft.schemeCode) || null,
    [planDraft.schemeCode, schemes],
  );
  const selectedPlanSchemeMeta = useMemo(
    () => (selectedPlanScheme ? extractSchemeMeta(selectedPlanScheme) : null),
    [selectedPlanScheme],
  );
  const selectedPlanInputDatasets = useMemo(
    () => extractRunPlanInputDatasets(selectedPlanSchemeMeta),
    [selectedPlanSchemeMeta],
  );
  const selectedPlanDateInputs = useMemo(
    () => selectedPlanInputDatasets.filter((input) => input.requiresDateField),
    [selectedPlanInputDatasets],
  );

  useEffect(() => {
    aiProcSideDraftsRef.current = aiProcSideDrafts;
  }, [aiProcSideDrafts]);

  const procJsonPreview = useMemo(
    () => (schemeDraft.procRuleJson ? JSON.stringify(schemeDraft.procRuleJson, null, 2) : ''),
    [schemeDraft.procRuleJson],
  );
  const inputPlanJsonPreview = useMemo(
    () => (schemeDraft.inputPlanJson ? JSON.stringify(schemeDraft.inputPlanJson, null, 2) : ''),
    [schemeDraft.inputPlanJson],
  );
  const parsedReconConfig = useMemo(
    () =>
      parseReconDraftConfig({
        matchFieldPairs: schemeDraft.matchFieldPairs,
        compareFieldPairs: schemeDraft.compareFieldPairs,
        matchKey: schemeDraft.matchKey,
        leftAmountField: schemeDraft.leftAmountField,
        rightAmountField: schemeDraft.rightAmountField,
        leftTimeSemantic: schemeDraft.leftTimeSemantic,
        rightTimeSemantic: schemeDraft.rightTimeSemantic,
        tolerance: schemeDraft.tolerance,
      }),
    [
      schemeDraft.compareFieldPairs,
      schemeDraft.leftAmountField,
      schemeDraft.leftTimeSemantic,
      schemeDraft.matchFieldPairs,
      schemeDraft.matchKey,
      schemeDraft.rightAmountField,
      schemeDraft.rightTimeSemantic,
      schemeDraft.tolerance,
    ],
  );
  const roleDerivedMatchFieldPairs = useMemo(
    () => buildSemanticRoleReconFieldPairs(leftOutputFields, rightOutputFields, 'match_key'),
    [leftOutputFields, rightOutputFields],
  );
  const roleDerivedCompareFieldPairs = useMemo(
    () => buildSemanticRoleReconFieldPairs(leftOutputFields, rightOutputFields, 'compare_field'),
    [leftOutputFields, rightOutputFields],
  );
  const activeMatchFieldPairs = useMemo(
    () => (
      parsedReconConfig.matchFieldPairs.length > 0
        ? parsedReconConfig.matchFieldPairs
        : roleDerivedMatchFieldPairs
    ),
    [parsedReconConfig.matchFieldPairs, roleDerivedMatchFieldPairs],
  );
  const activeCompareFieldPairs = useMemo(
    () => (
      parsedReconConfig.compareFieldPairs.length > 0
        ? parsedReconConfig.compareFieldPairs
        : roleDerivedCompareFieldPairs
    ),
    [parsedReconConfig.compareFieldPairs, roleDerivedCompareFieldPairs],
  );
  const leftOutputFieldLabelMap = useMemo(
    () => mergeLabelMaps(
      buildOutputFieldLabelMap(leftOutputFields, selectedLeftSources),
      aiProcSideDrafts.left.outputFieldLabelMap,
    ),
    [aiProcSideDrafts.left.outputFieldLabelMap, leftOutputFields, selectedLeftSources],
  );
  const rightOutputFieldLabelMap = useMemo(
    () => mergeLabelMaps(
      buildOutputFieldLabelMap(rightOutputFields, selectedRightSources),
      aiProcSideDrafts.right.outputFieldLabelMap,
    ),
    [aiProcSideDrafts.right.outputFieldLabelMap, rightOutputFields, selectedRightSources],
  );
  const leftReconFieldOptions = useMemo(
    () => buildAllReconFieldOptions(leftOutputFields, leftOutputFieldLabelMap),
    [leftOutputFieldLabelMap, leftOutputFields],
  );
  const rightReconFieldOptions = useMemo(
    () => buildAllReconFieldOptions(rightOutputFields, rightOutputFieldLabelMap),
    [rightOutputFieldLabelMap, rightOutputFields],
  );
  const compiledReconRuleResult = useMemo(() => {
    try {
      return {
        json: buildLocalReconRuleJson({
          schemeName: schemeDraft.name,
          businessGoal: schemeDraft.businessGoal,
          reconRuleName: schemeDraft.reconRuleName || buildDefaultReconRuleName(schemeDraft.name),
          matchFieldPairs: activeMatchFieldPairs,
          compareFieldPairs: activeCompareFieldPairs,
        }),
        error: '',
      };
    } catch (error) {
      return {
        json: null,
        error: error instanceof Error ? error.message : '当前对账配置无法生成 JSON。',
      };
    }
  }, [
    activeCompareFieldPairs,
    activeMatchFieldPairs,
    schemeDraft.businessGoal,
    schemeDraft.name,
    schemeDraft.reconRuleName,
  ]);
  const reconJsonPreview = useMemo(
    () => (compiledReconRuleResult.json ? JSON.stringify(compiledReconRuleResult.json, null, 2) : ''),
    [compiledReconRuleResult.json],
  );
  const resolveChannelProviderLabel = useCallback(
    (channelConfigId: string) => {
      if (!channelConfigId) return '未配置';
      const channel = channelById.get(channelConfigId);
      if (!channel) return channelConfigId;
      return collaborationProviderLabel(channel.provider);
    },
    [channelById],
  );

  const applyCenterPayload = useCallback(
    (
      nextSchemes: ReconSchemeListItem[],
      nextTasks: ReconTaskListItem[],
      nextRuns: ReconCenterRunItem[],
      options?: {
        notice?: string | null;
        exceptionsByRunId?: Record<string, ReconRunExceptionDetail[]>;
      },
    ) => {
      setSchemes(nextSchemes);
      setTasks(nextTasks);
      setRuns(nextRuns);
      setExceptionsByRunId(options?.exceptionsByRunId || {});
      setCenterNotice(options?.notice || null);
      setCenterError(null);
      setSchemeDeleteGuard(null);
      setFocusedTaskId(null);
    },
    [],
  );

  const loadCenterData = useCallback(async () => {
    if (!authToken) {
      applyCenterPayload([], [], [], {
        notice: '登录后可查看对账方案、对账任务和运行记录。',
      });
      return;
    }

    setLoadingCenter(true);
    setCenterError(null);

    try {
      const headers = { Authorization: `Bearer ${authToken}` };
      const [schemeResponse, taskResponse, runResponse] = await Promise.all([
        fetchReconAutoApi('/schemes', { headers }),
        fetchReconAutoApi('/tasks', { headers }),
        fetchReconAutoApi('/runs', { headers }),
      ]);

      const [schemeData, taskData, runData] = await Promise.all([
        schemeResponse.json().catch(() => ({})),
        taskResponse.json().catch(() => ({})),
        runResponse.json().catch(() => ({})),
      ]);

      if (!schemeResponse.ok) {
        throw new Error(String(schemeData.detail || schemeData.message || '对账方案加载失败'));
      }
      if (!taskResponse.ok) {
        throw new Error(String(taskData.detail || taskData.message || '对账任务加载失败'));
      }
      if (!runResponse.ok) {
        throw new Error(String(runData.detail || runData.message || '运行记录加载失败'));
      }

      const allSchemes = asList(schemeData.schemes).map(mapScheme);
      const nextSchemes = allSchemes.filter((item) => item.status === 'enabled');
      const backendSchemeNameByCode = new Map(allSchemes.map((item) => [item.schemeCode, item.name]));
      const allTasks = asList(taskData.tasks || taskData.run_plans).map((item) =>
        mapTask(item, backendSchemeNameByCode),
      );
      const nextTasks = allTasks
        .filter((item) => !isTaskMarkedDeleted(item))
        .sort((left, right) => {
          const timeDiff = toSortableTimestamp(right.createdAt) - toSortableTimestamp(left.createdAt);
          if (timeDiff !== 0) return timeDiff;
          return left.name.localeCompare(right.name, 'zh-CN');
        });
      const backendTaskNameByCode = new Map(allTasks.map((item) => [item.planCode, item.name]));
      const nextRuns = asList(runData.runs).map((item) =>
        mapRun(item, backendSchemeNameByCode, backendTaskNameByCode),
      );
      applyCenterPayload(nextSchemes, nextTasks, nextRuns, {
        notice: null,
        exceptionsByRunId: {},
      });
    } catch (error) {
      setSchemes([]);
      setTasks([]);
      setRuns([]);
      setExceptionsByRunId({});
      setCenterNotice(null);
      setCenterError(error instanceof Error ? error.message : '对账中心加载失败');
      setSchemeDeleteGuard(null);
      setFocusedTaskId(null);
    } finally {
      setLoadingCenter(false);
    }
  }, [applyCenterPayload, authToken]);

  useEffect(() => {
    if (activeTab !== 'schemes') {
      setSchemeDeleteGuard(null);
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== 'tasks' || !focusedTaskId) return;
    const target = taskRowRefs.current[focusedTaskId];
    if (!target) return;

    target.scrollIntoView?.({
      behavior: 'smooth',
      block: 'center',
    });

    const timer = window.setTimeout(() => {
      setFocusedTaskId((current) => (current === focusedTaskId ? null : current));
    }, 2400);

    return () => {
      window.clearTimeout(timer);
    };
  }, [activeTab, focusedTaskId, tasks]);

  const loadRunExceptions = useCallback(
    async (runId: string) => {
      if (!authToken || !runId) return;
      setLoadingExceptionsRunId(runId);
      try {
        const response = await fetchReconAutoApi(`/runs/${runId}/exceptions`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '异常处理加载失败'));
        }
        setExceptionsByRunId((prev) => ({
          ...prev,
          [runId]: asList(data.exceptions).map(mapRunException),
        }));
      } catch (error) {
        setCenterError(error instanceof Error ? error.message : '异常处理加载失败');
      } finally {
        setLoadingExceptionsRunId((prev) => (prev === runId ? null : prev));
      }
    },
    [authToken],
  );

  const loadChannelOptions = useCallback(async () => {
    if (!authToken) {
      setAvailableChannels([]);
      setChannelLoadError('请先登录并配置协作通道。');
      return;
    }

    setLoadingChannels(true);
    setChannelLoadError('');

    try {
      const response = await fetch('/api/collaboration-channels', {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载协作通道失败'));
      }

      const rows = Array.isArray(data?.channels)
        ? data.channels
        : Array.isArray(data?.configs)
        ? data.configs
        : Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data)
        ? data
        : [];
      const enabledChannels = rows
        .map((item: unknown) => normalizeChannelConfig(item))
        .filter(Boolean)
        .filter((item: CollaborationChannelListItem) => item.is_enabled !== false) as CollaborationChannelListItem[];
      setAvailableChannels(enabledChannels);
      if (enabledChannels.length === 0) {
        setChannelLoadError('当前没有可用协作通道，请先去数据连接中配置。');
      }
    } catch (error) {
      setAvailableChannels([]);
      setChannelLoadError(error instanceof Error ? error.message : '加载协作通道失败');
    } finally {
      setLoadingChannels(false);
    }
  }, [authToken]);

  useEffect(() => {
    if (mode !== 'center') return;
    void loadCenterData();
    void loadChannelOptions();
  }, [loadCenterData, loadChannelOptions, mode]);

  useEffect(() => {
    if (modalState?.kind !== 'run-exceptions') return;
    const runId = modalState.run.id;
    if (exceptionsByRunId[runId]) return;
    void loadRunExceptions(runId);
  }, [exceptionsByRunId, loadRunExceptions, modalState]);

  const resetSchemeWizard = useCallback(() => {
    setSchemeWizardStep(1);
    setProcBuildMode('ai_complex_rule');
    setAiProcSideDrafts(createEmptyAiProcSideDrafts());
    setWizardDraftState(createEmptySchemeWizardDraftState());
    setDesignSessionId('');
    setWizardJsonPanel(null);
    setWizardProcJsonView('proc');
    setWizardReconJsonView('recon');
    setProcTrialPreview(null);
    setReconTrialPreview(null);
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, [setProcCompatibility, setReconCompatibility]);

  const openCreateSchemeModal = useCallback(() => {
    setModalError(null);
    resetSchemeWizard();
    setModalState({ kind: 'create-scheme' });
  }, [resetSchemeWizard]);

  const openCreatePlanModal = useCallback(
    (scheme: ReconSchemeListItem | null = null) => {
      setModalError(null);
      setOwnerCandidates([]);
      setOwnerSearchMessage('');
      const resolvedScheme = scheme || schemes[0] || null;
      const resolvedSchemeMeta = resolvedScheme ? extractSchemeMeta(resolvedScheme) : null;
      setPlanDraft({
        ...EMPTY_PLAN_DRAFT,
        schemeCode: resolvedScheme?.schemeCode || '',
        dateFieldByInputKey: buildDefaultRunPlanDateFieldMap(resolvedSchemeMeta),
      });
      setModalState({ kind: 'create-plan', scheme: resolvedScheme });
      void loadChannelOptions();
    },
    [loadChannelOptions, schemes],
  );

  const closeModal = useCallback(() => {
    setModalError(null);
    setWizardJsonPanel(null);
    setWizardProcJsonView('proc');
    setWizardReconJsonView('recon');
    setWizardJsonCopyState(null);
    setSelectedExceptionDetail(null);
    setModalState(null);
    setDesignSessionId('');
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, [setProcCompatibility, setReconCompatibility]);

  const handleCopyWizardJson = useCallback(async (panel: 'proc' | 'recon') => {
    const copyPanel = panel === 'proc'
      ? wizardProcJsonView === 'inputPlan' ? 'inputPlan' : 'proc'
      : wizardReconJsonView;
    const jsonText = panel === 'proc'
      ? wizardProcJsonView === 'inputPlan'
        ? inputPlanJsonPreview
        : procJsonPreview
      : wizardReconJsonView === 'proc'
      ? procJsonPreview
      : reconJsonPreview;
    if (!jsonText.trim()) {
      setWizardJsonCopyState({ panel: copyPanel, status: 'error' });
      return;
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(jsonText);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = jsonText;
        textarea.setAttribute('readonly', 'true');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setWizardJsonCopyState({ panel: copyPanel, status: 'success' });
    } catch {
      setWizardJsonCopyState({ panel: copyPanel, status: 'error' });
    }

    window.setTimeout(() => {
      setWizardJsonCopyState((prev) => (prev?.panel === copyPanel ? null : prev));
    }, 1800);
  }, [inputPlanJsonPreview, procJsonPreview, reconJsonPreview, wizardProcJsonView, wizardReconJsonView]);

  const resetSchemeDraftFromGoalChange = useCallback(
    (patch: Partial<SchemeDraft>) => {
      setWizardDraftState((prev) =>
        updateIntentDraft(prev, {
          name: patch.name ?? prev.intent.name,
          businessGoal: patch.businessGoal ?? prev.intent.businessGoal,
        }),
      );
      setDesignSessionId('');
      setWizardJsonPanel(null);
      setWizardProcJsonView('proc');
      setWizardReconJsonView('recon');
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setProcCompatibility(emptyCompatibilityResult());
      setReconCompatibility(emptyCompatibilityResult());
    },
    [setProcCompatibility, setReconCompatibility],
  );

  const handlePreparationDraftChange = useCallback(
    (updater: (prev: SchemeWizardDraftState) => SchemeWizardDraftState) => {
      const hasExistingPreview = Boolean(procTrialPreview);
      setWizardDraftState((prev) => {
        const next = updater(prev);
        if (!hasExistingPreview) {
          return next;
        }
        return updateDerivedDraft(next, {
          procTrialStatus: 'needs_adjustment',
          procTrialSummary: PREPARATION_REFERENCE_EDIT_SUMMARY,
          procPreviewState: 'reference',
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
          reconPreviewState: 'empty',
        });
      });
      setDesignSessionId('');
      setWizardJsonPanel(null);
      setWizardProcJsonView('proc');
      setWizardReconJsonView('recon');
      if (hasExistingPreview) {
        setProcTrialPreview((prev) =>
          markProcTrialPreviewAsReference(prev, PREPARATION_REFERENCE_EDIT_SUMMARY),
        );
        setProcCompatibility({
          status: 'warning',
          message: '数据整理已修改，下面保留的是上一次试跑结果，仅供参考。请重新试跑。',
          details: [],
        });
      } else {
        setProcTrialPreview(null);
        setProcCompatibility(emptyCompatibilityResult());
      }
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
    },
    [procTrialPreview, setProcCompatibility, setReconCompatibility],
  );

  const handleProcBuildModeChange = useCallback(
    (mode: ProcBuildMode) => {
      setProcBuildMode(mode);
      setModalError(null);
      if (mode === 'simple_mapping') {
        setAiProcSideDrafts(createEmptyAiProcSideDrafts());
        return;
      }

      setDesignSessionId('');
      setWizardJsonPanel(null);
      setWizardProcJsonView('proc');
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setWizardDraftState((prev) =>
        updateDerivedDraft(prev, {
          procTrialStatus: 'idle',
          procTrialSummary: '',
          procRuleJson: null,
          inputPlanJson: null,
          procCompatibility: emptyCompatibilityResult(),
          procPreviewState: 'empty',
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
          reconRuleJson: null,
          reconCompatibility: emptyCompatibilityResult(),
          reconPreviewState: 'empty',
        }),
      );
    },
    [],
  );

  const handleAiProcRuleDraftChange = useCallback((side: AiProcSide, value: string) => {
    aiProcGenerationSeqRef.current[side] += 1;
    aiProcAbortControllersRef.current[side]?.abort();
    delete aiProcAbortControllersRef.current[side];
    setAiProcSideDrafts((prev) => {
      const current = prev[side];
      const hasGeneratedResult = current.outputRows.length > 0 || Boolean(current.procRuleJson);
      return {
        ...prev,
        [side]: {
          ...current,
          ruleDraft: value,
          status: hasGeneratedResult ? 'succeeded' : 'idle',
          summary: hasGeneratedResult ? current.summary : '',
          error: '',
          failureReasons: [],
          failureDetails: [],
          questions: [],
          nodeTraces: hasGeneratedResult ? current.nodeTraces : createDefaultRuleGenerationNodeTraces(),
        },
      };
    });
  }, []);

  const applyRuleGenerationEvent = useCallback((side: AiProcSide, sideLabel: string, payload: Record<string, unknown>) => {
    setAiProcSideDrafts((prev) => {
      const current = prev[side];
      const { draft: nextDraft } = applyRuleGenerationEventToDraft(current, sideLabel, payload);

      return {
        ...prev,
        [side]: nextDraft,
      };
    });
  }, []);

  const handleGenerateAiProcOutput = useCallback(
    async (side: AiProcSide) => {
      const selectedSources = side === 'left' ? selectedLeftSources : selectedRightSources;
      const currentDraft = aiProcSideDraftsRef.current[side];
      const ruleText = currentDraft.ruleDraft.trim();
      const sideLabel = side === 'left' ? '左侧' : '右侧';
      const targetTable = side === 'left' ? 'left_recon_ready' : 'right_recon_ready';
      if (!ruleText) {
        setAiProcSideDrafts((prev) => ({
          ...prev,
          [side]: {
            ...prev[side],
            status: 'failed',
            error: `请先输入${sideLabel}整理规则描述。`,
            summary: '',
            failureReasons: [],
            failureDetails: [],
          },
        }));
        return;
      }
      if (selectedSources.length === 0) {
        setAiProcSideDrafts((prev) => ({
          ...prev,
          [side]: {
            ...prev[side],
            status: 'failed',
            error: `请先选择${sideLabel}数据集。`,
            summary: '',
            failureReasons: [],
            failureDetails: [],
          },
        }));
        return;
      }

      setModalError(null);
      aiProcAbortControllersRef.current[side]?.abort();
      const generationSeq = aiProcGenerationSeqRef.current[side] + 1;
      aiProcGenerationSeqRef.current[side] = generationSeq;
      const controller = new AbortController();
      aiProcAbortControllersRef.current[side] = controller;
      setAiProcSideDrafts((prev) => ({
        ...prev,
        [side]: {
          ...prev[side],
          status: 'generating',
          summary: `${sideLabel}规则已提交，正在理解描述、检查字段、生成规则并试跑输出数据。`,
          error: '',
          failureReasons: [],
          failureDetails: [],
          nodeTraces: createDefaultRuleGenerationNodeTraces(),
          questions: [],
          warnings: [],
        },
      }));

      try {
        const sourcePayloads = await buildRuleGenerationSourcePayloads(selectedSources, authToken);
        const response = await fetch('/api/rule-generation/proc/side/stream', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken || ''}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            side,
            target_table: targetTable,
            rule_text: ruleText,
            sources: sourcePayloads,
          }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          const detail = await response.text().catch(() => '');
          throw new Error(detail || 'AI生成输出数据请求失败');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalEvent: Record<string, unknown> | null = null;

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop() || '';
          frames.forEach((frame) => {
            const eventPayload = parseSseFrame(frame);
            if (!eventPayload) return;
            if (aiProcGenerationSeqRef.current[side] !== generationSeq) return;
            finalEvent = eventPayload;
            applyRuleGenerationEvent(side, sideLabel, eventPayload);
          });
        }
        if (buffer.trim()) {
          const eventPayload = parseSseFrame(buffer);
          if (eventPayload) {
            if (aiProcGenerationSeqRef.current[side] !== generationSeq) return;
            finalEvent = eventPayload;
            applyRuleGenerationEvent(side, sideLabel, eventPayload);
          }
        }
        if (aiProcGenerationSeqRef.current[side] !== generationSeq) {
          return;
        }
        if (!finalEvent || finalEvent.event !== 'graph_completed') {
          return;
        }

        const outputFields = normalizeAiOutputFields(finalEvent.output_fields);
        const currentRule = isRecord(finalEvent.proc_rule_json) ? finalEvent.proc_rule_json : undefined;
        const currentInputPlan = isRecord(finalEvent.input_plan_json) ? finalEvent.input_plan_json : undefined;
        const latestSideDrafts = aiProcSideDraftsRef.current;
        const leftRule = side === 'left' ? currentRule : latestSideDrafts.left.procRuleJson;
        const rightRule = side === 'right' ? currentRule : latestSideDrafts.right.procRuleJson;
        const leftInputPlan = side === 'left' ? currentInputPlan : latestSideDrafts.left.inputPlanJson;
        const rightInputPlan = side === 'right' ? currentInputPlan : latestSideDrafts.right.inputPlanJson;
        const mergedRule = leftRule && rightRule
          ? buildAiSideProcRuleJson({
              schemeName: schemeDraft.name,
              businessGoal: schemeDraft.businessGoal,
              leftRule,
              rightRule,
            })
          : null;
        const mergedInputPlan = leftInputPlan && rightInputPlan
          ? buildAiSideInputPlanJson({ leftPlan: leftInputPlan, rightPlan: rightInputPlan })
          : null;
        let mergedTrialPassed = false;
        let mergedTrialSummary = `${sideLabel}输出数据已生成，请继续生成${side === 'left' ? '右侧' : '左侧'}输出数据。`;
        let verifiedMergedRule = mergedRule;

        if (mergedRule) {
          setIsTrialingProc(true);
          try {
            const [leftSamples, rightSamples] = await Promise.all([
              buildRuleGenerationSourcePayloads(selectedLeftSources, authToken),
              buildRuleGenerationSourcePayloads(selectedRightSources, authToken),
            ]);
            const trialResponse = await fetchReconAutoApi('/schemes/design/proc-trial', {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${authToken || ''}`,
                'Content-Type': 'application/json',
              },
        body: JSON.stringify({
          proc_rule_json: mergedRule,
          input_plan_json: mergedInputPlan || undefined,
          sample_datasets: [
            ...leftSamples.map((source) => ({ ...source, side: 'left' })),
            ...rightSamples.map((source) => ({ ...source, side: 'right' })),
                ],
              }),
            });
            const trialData = await trialResponse.json().catch(() => ({}));
            if (!trialResponse.ok) {
              throw new Error(String(trialData.detail || trialData.message || trialData.error || '合并后数据整理试跑失败'));
            }
            const trialResult = asRecord(trialData);
            const normalizedRule = asRecord(trialResult.normalized_rule);
            verifiedMergedRule = Object.keys(normalizedRule).length > 0 ? normalizedRule : mergedRule;
            mergedTrialPassed = trialResult.ready_for_confirm === true && trialResult.success !== false;
            mergedTrialSummary = toText(
              trialResult.summary,
              toText(trialResult.message, toText(trialResult.error, mergedTrialPassed ? '合并后数据整理试跑通过。' : '合并后数据整理试跑未通过。')),
            );
            setProcCompatibility({
              status: mergedTrialPassed ? 'passed' : 'warning',
              message: mergedTrialPassed
                ? 'AI 复杂规则合并后试跑通过，可进入第三步配置对账逻辑。'
                : 'AI 复杂规则已生成，但合并后试跑未通过，请调整规则描述后重新生成。',
              details: parseTrialMessages(trialResult.errors).concat(parseTrialMessages(trialResult.warnings)),
            });
            setProcTrialPreview(buildProcPreviewFromTrialResult(trialResult));
          } catch (trialError) {
            mergedTrialPassed = false;
            mergedTrialSummary = trialError instanceof Error ? trialError.message : '合并后数据整理试跑失败。';
            setProcCompatibility({
              status: 'failed',
              message: 'AI 复杂规则合并后试跑失败。',
              details: [mergedTrialSummary],
            });
            setProcTrialPreview(null);
          } finally {
            setIsTrialingProc(false);
          }
        }

        setDesignSessionId('');
        setWizardJsonPanel(null);
        setWizardProcJsonView('proc');
        setReconTrialPreview(null);
        setReconCompatibility(emptyCompatibilityResult());
        setWizardDraftState((prev) => {
          const withGeneratedFields = outputFields.length > 0
            ? applyPreparationOutputFields(prev, side, outputFields)
            : prev;
          const next = withGeneratedFields;
          const leftGenerated = Boolean(leftRule);
          const rightGenerated = Boolean(rightRule);
          const withMergedFields = leftGenerated && rightGenerated && verifiedMergedRule
            ? hydratePreparationOutputFieldsFromProcRule(next, verifiedMergedRule)
            : next;
          if (
            !leftGenerated
            || !rightGenerated
            || withMergedFields.preparation.leftOutputFields.length === 0
            || withMergedFields.preparation.rightOutputFields.length === 0
          ) {
            return updateDerivedDraft(withMergedFields, {
              procTrialStatus: 'needs_adjustment',
              procTrialSummary: `${sideLabel}输出数据已生成，请继续生成${side === 'left' ? '右侧' : '左侧'}输出数据。`,
              inputPlanJson: null,
              procPreviewState: 'current',
              reconTrialStatus: 'idle',
              reconTrialSummary: '',
              reconRuleJson: null,
              reconPreviewState: 'empty',
            });
          }
          return updateDerivedDraft(withMergedFields, {
            procRuleJson: verifiedMergedRule,
            procTrialStatus: mergedTrialPassed ? 'passed' : 'needs_adjustment',
            procTrialSummary: mergedTrialSummary,
            inputPlanJson: mergedInputPlan,
            procCompatibility: {
              status: mergedTrialPassed ? 'passed' : 'failed',
              message: mergedTrialPassed
                ? 'AI 复杂规则合并后试跑通过，生成 left_recon_ready / right_recon_ready。'
                : 'AI 复杂规则合并后试跑未通过。',
              details: mergedTrialPassed ? [] : [mergedTrialSummary],
            },
            procPreviewState: 'current',
            reconTrialStatus: 'idle',
            reconTrialSummary: '',
            reconRuleJson: null,
            reconPreviewState: 'empty',
          });
        });
        setReconTrialPreview(null);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        if (aiProcGenerationSeqRef.current[side] !== generationSeq) {
          return;
        }
        const message = error instanceof Error ? error.message : 'AI生成输出数据失败';
        setAiProcSideDrafts((prev) => ({
          ...prev,
          [side]: {
            ...prev[side],
            status: 'failed',
            summary: `${sideLabel}AI生成失败。`,
            error: message,
            failureReasons: [message],
            failureDetails: [],
          },
        }));
      } finally {
        if (aiProcGenerationSeqRef.current[side] === generationSeq) {
          delete aiProcAbortControllersRef.current[side];
        }
      }
    },
    [
      authToken,
      applyRuleGenerationEvent,
      schemeDraft.businessGoal,
      schemeDraft.name,
      selectedLeftSources,
      selectedRightSources,
      setProcCompatibility,
      setReconCompatibility,
    ],
  );

  const hydrateSourcesForRecommendation = useCallback(
    async (sources: SchemeSourceOption[]): Promise<SchemeSourceOption[]> => {
      const normalizedSources = sources.slice(0, 1);
      if (!authToken) {
        return normalizedSources;
      }

      return Promise.all(
        normalizedSources.map(async (source) => {
          if (!source.sourceId || sourceHasRecommendationMetadata(source)) {
            return source;
          }

          try {
            const response = await fetch('/api/recon/schemes/design/dataset-fields', {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${authToken}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                source_id: source.sourceId,
                resource_key: source.resourceKey || source.datasetCode || '',
                dataset_id: source.id,
              }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !Array.isArray(data.fields)) {
              return source;
            }

            const fieldEntries = (data.fields as Array<Record<string, string>>)
              .map((item) => ({
                rawName: toText(item.raw_name).trim(),
                displayName: toText(item.display_name, toText(item.raw_name)).trim(),
              }))
              .filter((item) => item.rawName);
            if (fieldEntries.length === 0) {
              return source;
            }

            return {
              ...source,
              fieldLabelMap: Object.fromEntries(
                fieldEntries.map((item) => [item.rawName, item.displayName || item.rawName]),
              ),
              schemaSummary: {
                ...(source.schemaSummary || {}),
                columns: fieldEntries.map((item) => ({
                  name: item.rawName,
                })),
              },
            } satisfies SchemeSourceOption;
          } catch {
            return source;
          }
        }),
      );
    },
    [authToken],
  );

  const recommendPreparationOutputFields = useCallback(
    async (side: 'left' | 'right', overrideSources?: SchemeSourceOption[]) => {
      const nextSources = (overrideSources || (side === 'left' ? selectedLeftSources : selectedRightSources)).slice(0, 1);
      const hydratedSources = await hydrateSourcesForRecommendation(nextSources);
      handlePreparationDraftChange((prev) => {
        const stateWithSources = overrideSources ? applyPreparationSources(prev, side, hydratedSources) : prev;
        return applyPreparationOutputFields(
          stateWithSources,
          side,
          buildRecommendedOutputFieldsForSources(hydratedSources),
        );
      });
    },
    [handlePreparationDraftChange, hydrateSourcesForRecommendation, selectedLeftSources, selectedRightSources],
  );

  const changeSchemeSources = useCallback((side: 'left' | 'right', sources: SchemeSourceOption[]) => {
    const allowMultipleSources = procBuildMode === 'ai_complex_rule';
    const normalizedSources = allowMultipleSources ? sources : sources.slice(0, 1);
    const current = side === 'left' ? selectedLeftSources : selectedRightSources;
    const currentIds = current.map((item) => item.id);
    const nextIds = normalizedSources.map((item) => item.id);
    if (sameStringSet(currentIds, nextIds)) {
      return;
    }

    handlePreparationDraftChange((prev) => applyPreparationSources(prev, side, normalizedSources));
    if (!allowMultipleSources) {
      void recommendPreparationOutputFields(side, normalizedSources);
    }
  }, [handlePreparationDraftChange, procBuildMode, recommendPreparationOutputFields, selectedLeftSources, selectedRightSources]);

  const handleReconDraftMutation = useCallback(
    (
      updater: (prev: SchemeWizardDraftState) => SchemeWizardDraftState,
      referenceSummary = RECON_REFERENCE_EDIT_SUMMARY,
    ) => {
      const hasExistingPreview = Boolean(reconTrialPreview);
      setWizardDraftState((prev) => {
        const next = updater(prev);
        return updateDerivedDraft(next, {
          reconTrialStatus: hasExistingPreview ? 'needs_adjustment' : 'idle',
          reconTrialSummary: hasExistingPreview ? referenceSummary : '',
          reconPreviewState: hasExistingPreview ? 'reference' : 'empty',
        });
      });
      setWizardJsonPanel(null);
      setWizardProcJsonView('proc');
      setWizardReconJsonView('recon');
      if (hasExistingPreview) {
        setReconTrialPreview((prev) => markReconTrialPreviewAsReference(prev, referenceSummary));
        setReconCompatibility({
          status: 'warning',
          message: '对账设置已修改，下面保留的是上一次试跑结果，仅供参考。请重新试跑。',
          details: [],
        });
      } else {
        setReconTrialPreview(null);
        setReconCompatibility(emptyCompatibilityResult());
      }
    },
    [reconTrialPreview, setReconCompatibility],
  );

  const applyStructuredReconConfig = useCallback(
    (
      patch: Partial<{
        reconRuleName: string;
        matchFieldPairs: ReconFieldPairDraft[];
        compareFieldPairs: ReconFieldPairDraft[];
        tolerance: string;
      }>,
    ) => {
      handleReconDraftMutation((prev) => {
        const current = buildLegacySchemeDraftSnapshot(prev);
        const nextRuleName =
          patch.reconRuleName ?? current.reconRuleName ?? buildDefaultReconRuleName(current.name);
        const defaultMatchFieldPairs = current.matchFieldPairs.length > 0
          ? current.matchFieldPairs
          : activeMatchFieldPairs;
        const defaultCompareFieldPairs = current.compareFieldPairs.length > 0
          ? current.compareFieldPairs
          : activeCompareFieldPairs;
        const nextMatchFieldPairs = normalizeReconFieldPairs(
          patch.matchFieldPairs ?? defaultMatchFieldPairs,
          current.matchKey ? [{ leftField: current.matchKey, rightField: current.matchKey }] : [],
        );
        const nextCompareFieldPairs = normalizeReconFieldPairs(
          patch.compareFieldPairs ?? defaultCompareFieldPairs,
          current.leftAmountField || current.rightAmountField
            ? [{ leftField: current.leftAmountField, rightField: current.rightAmountField }]
            : [],
        );
        const nextMatchKey = resolveFirstReconFieldPairValue(
          nextMatchFieldPairs,
          'left',
          current.matchKey,
        );
        const nextLeftAmountField = resolveFirstReconFieldPairValue(
          nextCompareFieldPairs,
          'left',
          current.leftAmountField,
        );
        const nextRightAmountField = resolveFirstReconFieldPairValue(
          nextCompareFieldPairs,
          'right',
          current.rightAmountField,
        );
        const nextTolerance = patch.tolerance ?? current.tolerance ?? '0.00';
        return updateReconciliationDraft(prev, {
          reconConfigMode: 'ai',
          selectedReconConfigId: '',
          reconRuleName: nextRuleName,
          matchFieldPairs: nextMatchFieldPairs,
          compareFieldPairs: nextCompareFieldPairs,
          matchKey: nextMatchKey,
          leftAmountField: nextLeftAmountField,
          rightAmountField: nextRightAmountField,
          leftTimeSemantic: '',
          rightTimeSemantic: '',
          tolerance: nextTolerance,
          reconDraft: buildStructuredReconDraftText({
            reconRuleName: nextRuleName,
            matchFieldPairs: nextMatchFieldPairs,
            compareFieldPairs: nextCompareFieldPairs,
          }),
        });
      });
    },
    [activeCompareFieldPairs, activeMatchFieldPairs, handleReconDraftMutation],
  );

  useEffect(() => {
    if (modalState?.kind !== 'create-plan') return;
    if (planDraft.channelConfigId || availableChannels.length === 0) return;
    const defaultChannel = availableChannels.find((item) => item.is_default) ?? availableChannels[0];
    if (!defaultChannel) return;
    setPlanDraft((prev) => ({ ...prev, channelConfigId: defaultChannel.id }));
  }, [availableChannels, modalState, planDraft.channelConfigId]);

  useEffect(() => {
    if (modalState?.kind !== 'create-plan') return;
    setPlanDraft((prev) => {
      const nextMap = buildDefaultRunPlanDateFieldMap(selectedPlanSchemeMeta, prev.dateFieldByInputKey);
      if (JSON.stringify(nextMap) === JSON.stringify(prev.dateFieldByInputKey)) {
        return prev;
      }
      return {
        ...prev,
        dateFieldByInputKey: nextMap,
      };
    });
  }, [modalState, selectedPlanSchemeMeta]);

  const buildTargetSampleDatasets = useCallback(
    (seedText = '') => [
      ...selectedLeftSources.map((item) =>
        buildDatasetSamplePayload(item, 'left', schemeDraft.leftDescription.trim(), seedText || schemeDraft.procDraft.trim(), {
          preparedOutputFields: buildPreparedOutputFieldPayload(leftOutputFields),
        }),
      ),
      ...selectedRightSources.map((item) =>
        buildDatasetSamplePayload(item, 'right', schemeDraft.rightDescription.trim(), seedText || schemeDraft.procDraft.trim(), {
          preparedOutputFields: buildPreparedOutputFieldPayload(rightOutputFields),
        }),
      ),
    ],
    [
      leftOutputFields,
      rightOutputFields,
      schemeDraft.leftDescription,
      schemeDraft.procDraft,
      schemeDraft.rightDescription,
      selectedLeftSources,
      selectedRightSources,
    ],
  );

  const ensureDesignSession = useCallback(async () => {
    if (!authToken) {
      throw new Error('请先登录后再配置对账方案。');
    }
    if (designSessionId) {
      return designSessionId;
    }
    const response = await fetchReconAutoApi('/schemes/design/start', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        scheme_name: schemeDraft.name.trim(),
        biz_goal: schemeDraft.businessGoal.trim(),
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(data.detail || data.message || '创建设计会话失败'));
    }
    const nextSessionId = toText(data.design_session_id, toText(asRecord(data.session).session_id));
    if (!nextSessionId) {
      throw new Error('后端未返回 design session id');
    }
    setDesignSessionId(nextSessionId);
    return nextSessionId;
  }, [authToken, designSessionId, schemeDraft.businessGoal, schemeDraft.name]);

  const syncDesignTarget = useCallback(
    async (sessionId: string) => {
      const response = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/target`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          left_datasets: buildTargetSampleDatasets(schemeDraft.procDraft.trim()).filter((item) => item.side === 'left'),
          right_datasets: buildTargetSampleDatasets(schemeDraft.procDraft.trim()).filter((item) => item.side === 'right'),
          left_description: schemeDraft.leftDescription.trim(),
          right_description: schemeDraft.rightDescription.trim(),
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || '同步目标数据失败'));
      }
      return asRecord(data.session);
    },
    [
      authToken,
      buildTargetSampleDatasets,
      schemeDraft.leftDescription,
      schemeDraft.procDraft,
      schemeDraft.rightDescription,
    ],
  );


  const toCompatibilityResult = useCallback((value: unknown, fallbackMessage = '等待校验'): CompatibilityCheckResult => {
    const raw = asRecord(value);
    const statusText = toText(raw.status).trim().toLowerCase();
    const usedFallback = raw.used_fallback === true;
    const compatible =
      raw.compatible === true
      || statusText === 'compatible'
      || statusText === 'passed'
      || statusText === 'trial_passed';
    const issues = parseTrialMessages(raw.issues);
    const missingFields = Object.entries(asRecord(raw.missing_fields)).flatMap(([bucket, fields]) => {
      const items = asList(fields).map((item) => toText(item)).filter(Boolean);
      if (items.length === 0) return [];
      const label = bucket === 'left' || bucket === 'source' ? '左侧' : '右侧';
      return [`${label}缺少字段：${items.join('、')}`];
    });
    const details = [
      ...issues,
      ...missingFields,
    ].filter(Boolean);
    return {
      status: usedFallback ? 'warning' : compatible ? 'passed' : raw.status ? 'failed' : 'idle',
      message: toText(raw.message, fallbackMessage),
      details,
    };
  }, []);

  const buildReconPreviewFromTrial = useCallback((trialResult: unknown): ReconTrialPreview | null => {
    const raw = asRecord(trialResult);
    if (Object.keys(raw).length === 0) return null;
    const resultSamples = asRecord(raw.result_samples);
    const matchedWithDiff = toPreviewTableRows(resultSamples.matched_with_diff);
    const sourceOnly = toPreviewTableRows(resultSamples.source_only);
    const targetOnly = toPreviewTableRows(resultSamples.target_only);
    const leftDatasetLabel = resolveReconOnlyResultDatasetLabel(
      'left',
      activeMatchFieldPairs,
      leftOutputFields,
      selectedLeftSources,
      schemeDraft.inputPlanJson,
      selectedLeftSources,
      selectedRightSources,
    );
    const rightDatasetLabel = resolveReconOnlyResultDatasetLabel(
      'right',
      activeMatchFieldPairs,
      rightOutputFields,
      selectedRightSources,
      schemeDraft.inputPlanJson,
      selectedLeftSources,
      selectedRightSources,
    );
    const rows: ReconResultRow[] = [
      ...matchedWithDiff.map((item) => ({
        matchFields: formatPreviewFieldValueSummary(item, activeMatchFieldPairs, 'match'),
        leftCompareFields: formatPreviewFieldValueSummary(item, activeCompareFieldPairs, 'left_compare'),
        rightCompareFields: formatPreviewFieldValueSummary(item, activeCompareFieldPairs, 'right_compare'),
        result: '存在差异',
      })),
      ...sourceOnly.map((item) => ({
        matchFields: formatPreviewFieldValueSummary(item, activeMatchFieldPairs, 'match'),
        leftCompareFields: formatPreviewFieldValueSummary(item, activeCompareFieldPairs, 'left_compare'),
        rightCompareFields: formatPreviewFieldValueSummary(item, activeCompareFieldPairs, 'right_compare'),
        result: `${leftDatasetLabel}独有`,
      })),
      ...targetOnly.map((item) => ({
        matchFields: formatPreviewFieldValueSummary(item, activeMatchFieldPairs, 'match'),
        leftCompareFields: formatPreviewFieldValueSummary(item, activeCompareFieldPairs, 'left_compare'),
        rightCompareFields: formatPreviewFieldValueSummary(item, activeCompareFieldPairs, 'right_compare'),
        result: `${rightDatasetLabel}独有`,
      })),
    ];
    const resultSummary = asRecord(raw.result_summary);
    const leftFieldLabelMap =
      normalizeFieldLabelMap(raw.left_field_label_map)
      || normalizeFieldLabelMap(resultSamples.left_field_label_map)
      || PREPARED_OUTPUT_FIELD_LABEL_MAP;
    const rightFieldLabelMap =
      normalizeFieldLabelMap(raw.right_field_label_map)
      || normalizeFieldLabelMap(resultSamples.right_field_label_map)
      || PREPARED_OUTPUT_FIELD_LABEL_MAP;
    const resultFieldLabelMap =
      normalizeFieldLabelMap(raw.result_field_label_map)
      || normalizeFieldLabelMap(resultSamples.result_field_label_map)
      || buildReconResultFieldLabelMap(activeMatchFieldPairs, activeCompareFieldPairs);
    return {
      status: raw.ready_for_confirm === true && raw.success !== false ? 'passed' : 'needs_adjustment',
      summary: toText(raw.summary, toText(raw.message, toText(raw.error, '数据对账试跑完成'))),
      leftRows: toPreviewTableRows(raw.left_samples),
      rightRows: toPreviewTableRows(raw.right_samples),
      leftFieldLabelMap,
      rightFieldLabelMap,
      resultFieldLabelMap,
      results: rows,
      resultSummary: {
        matched: toInt(resultSummary.matched_exact, 0),
        unmatchedLeft: toInt(resultSummary.source_only, 0),
        unmatchedRight: toInt(resultSummary.target_only, 0),
        diffCount: toInt(resultSummary.matched_with_diff, 0),
      },
    };
  }, [
    activeCompareFieldPairs,
    activeMatchFieldPairs,
    leftOutputFields,
    rightOutputFields,
    schemeDraft.inputPlanJson,
    selectedLeftSources,
    selectedRightSources,
  ]);

  const trialProcDraft = useCallback(async (): Promise<boolean> => {
    setModalError(null);
    if (!authToken) {
      setModalError('请先登录后再试跑验证。');
      return false;
    }
    if (!selectedLeftSources.length || !selectedRightSources.length) {
      setModalError('请先完成左右数据集选择。');
      return false;
    }

    let compiledProcRuleJson: Record<string, unknown>;
    try {
      compiledProcRuleJson = buildLocalProcRuleJson({
        schemeName: schemeDraft.name,
        businessGoal: schemeDraft.businessGoal,
        leftSources: selectedLeftSources,
        rightSources: selectedRightSources,
        leftOutputFields,
        rightOutputFields,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : '当前输出字段配置无法生成可执行的数据整理规则。';
      setModalError(message);
      return false;
    }

    setIsTrialingProc(true);
    try {
      const sessionId = await ensureDesignSession();
      await syncDesignTarget(sessionId);
      const prepareResponse = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/proc/use-existing`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          rule_json: compiledProcRuleJson,
        }),
      });
      const prepareData = await prepareResponse.json().catch(() => ({}));
      if (!prepareResponse.ok) {
        throw new Error(String(prepareData.detail || prepareData.message || '生成数据整理规则失败'));
      }
      const prepareSession = asRecord(prepareData.session);
      const prepareProcStep = asRecord(prepareSession.proc_step);
      const preparedRule = asRecord(prepareProcStep.effective_rule_json);
      const preparedCompatibility = toCompatibilityResult(
        prepareProcStep.compatibility_result,
        '已根据当前输出字段生成数据整理规则。',
      );
      if (preparedCompatibility.status === 'failed') {
        const firstDetail = preparedCompatibility.details[0];
        throw new Error(firstDetail || preparedCompatibility.message || '当前输出字段配置无法生成可执行的数据整理规则。');
      }
      const preparedRuleJson = Object.keys(preparedRule).length > 0 ? preparedRule : compiledProcRuleJson;
      setSchemeDraft((prev) => ({
        ...prev,
        procConfigMode: 'ai',
        selectedProcConfigId: '',
        procDraft: resolveWizardDraftText(
          prepareProcStep.draft_text,
          prepareProcStep.rule_summary,
          summarizeProcDraft(preparedRuleJson),
        ),
        procRuleJson: preparedRuleJson,
        inputPlanJson: prev.inputPlanJson,
        procTrialStatus: 'idle',
        procTrialSummary: '',
        reconDraft: '',
        matchFieldPairs: [],
        compareFieldPairs: [],
        matchKey: '',
        leftAmountField: '',
        rightAmountField: '',
        leftTimeSemantic: '',
        rightTimeSemantic: '',
        tolerance: '',
        reconRuleJson: null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      if (Object.keys(preparedRule).length > 0) {
        setWizardDraftState((prev) => hydratePreparationOutputFieldsFromProcRule(prev, preparedRule));
      }
      setProcCompatibility(preparedCompatibility);
      const response = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/proc/trial`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          input_plan_json: schemeDraft.inputPlanJson || undefined,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || data.error || '数据整理试跑失败'));
      }
      const session = asRecord(data.session);
      const procStep = asRecord(session.proc_step);
      const trialResult = asRecord(procStep.trial_result);
      const normalizedRule = asRecord(procStep.effective_rule_json);
      const passed = trialResult.ready_for_confirm === true && trialResult.success !== false;
      const summary = toText(
        trialResult.summary,
        toText(trialResult.message, toText(trialResult.error, passed ? '数据整理试跑通过' : '数据整理试跑未通过')),
      );
      setProcCompatibility(
        toCompatibilityResult(
          procStep.compatibility_result,
          passed ? '试跑验证通过，可进入下一步。' : '试跑未通过，请调整输出字段配置后重试。',
        ),
      );
      setSchemeDraft((prev) => ({
        ...prev,
        procDraft: resolveWizardDraftText(
          procStep.draft_text,
          procStep.rule_summary,
          prev.procDraft,
        ),
        procRuleJson: Object.keys(normalizedRule).length > 0 ? normalizedRule : prev.procRuleJson,
        procTrialStatus: passed ? 'passed' : 'needs_adjustment',
        procTrialSummary: summary,
        reconDraft: passed ? prev.reconDraft : '',
        matchFieldPairs: passed ? prev.matchFieldPairs : [],
        compareFieldPairs: passed ? prev.compareFieldPairs : [],
        matchKey: passed ? prev.matchKey : '',
        leftAmountField: passed ? prev.leftAmountField : '',
        rightAmountField: passed ? prev.rightAmountField : '',
        leftTimeSemantic: passed ? prev.leftTimeSemantic : '',
        rightTimeSemantic: passed ? prev.rightTimeSemantic : '',
        tolerance: passed ? prev.tolerance : '',
        reconRuleJson: passed ? prev.reconRuleJson : null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      if (Object.keys(normalizedRule).length > 0) {
        setWizardDraftState((prev) => hydratePreparationOutputFieldsFromProcRule(prev, normalizedRule));
      }
      const procPreview = buildProcPreviewFromTrialResult(trialResult);
      setProcTrialPreview(procPreview);
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
      setWizardDraftState((prev) =>
        updateDerivedDraft(prev, {
          procPreviewState: procPreview ? 'current' : 'empty',
          reconPreviewState: 'empty',
        }),
      );
      return passed;
    } catch (error) {
      const message = error instanceof Error ? error.message : '数据整理试跑失败';
      setModalError(message);
      setProcCompatibility({
        status: 'failed',
        message: '试跑未通过，请检查输出字段配置或样本数据。',
        details: [message],
      });
      setSchemeDraft((prev) => ({
        ...prev,
        procTrialStatus: 'needs_adjustment',
        procTrialSummary: message,
        reconDraft: '',
        matchFieldPairs: [],
        compareFieldPairs: [],
        matchKey: '',
        leftAmountField: '',
        rightAmountField: '',
        leftTimeSemantic: '',
        rightTimeSemantic: '',
        tolerance: '',
        reconRuleJson: null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
      setWizardDraftState((prev) =>
        updateDerivedDraft(prev, {
          procPreviewState: 'empty',
          reconPreviewState: 'empty',
        }),
      );
      return false;
    } finally {
      setIsTrialingProc(false);
    }
  }, [
    authToken,
    ensureDesignSession,
    leftOutputFields,
    rightOutputFields,
    schemeDraft.businessGoal,
    schemeDraft.name,
    selectedLeftSources,
    selectedRightSources,
    setProcCompatibility,
    setReconCompatibility,
    setSchemeDraft,
    syncDesignTarget,
    toCompatibilityResult,
  ]);

  const trialReconDraft = useCallback(async (): Promise<boolean> => {
    setModalError(null);
    if (!authToken) {
      setModalError('请先登录后再试跑验证。');
      return false;
    }
    if (schemeDraft.procTrialStatus !== 'passed' || !schemeDraft.procRuleJson) {
      setModalError('请先完成数据整理试跑，再进行对账试跑。');
      return false;
    }
    if (!compiledReconRuleResult.json) {
      setModalError(compiledReconRuleResult.error || '请先完成对账字段配置。');
      return false;
    }

    setIsTrialingRecon(true);
    try {
      const sessionId = await ensureDesignSession();
      await syncDesignTarget(sessionId);
      const procPrepareResponse = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/proc/use-existing`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          rule_json: schemeDraft.procRuleJson,
        }),
      });
      const procPrepareData = await procPrepareResponse.json().catch(() => ({}));
      if (!procPrepareResponse.ok) {
        throw new Error(String(procPrepareData.detail || procPrepareData.message || '同步数据整理规则失败'));
      }
      const procTrialResponse = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/proc/trial`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          input_plan_json: schemeDraft.inputPlanJson || undefined,
        }),
      });
      const procTrialData = await procTrialResponse.json().catch(() => ({}));
      if (!procTrialResponse.ok) {
        throw new Error(String(procTrialData.detail || procTrialData.message || procTrialData.error || '数据整理结果同步试跑失败'));
      }
      const procTrialResult = asRecord(asRecord(asRecord(procTrialData.session).proc_step).trial_result);
      if (procTrialResult.ready_for_confirm !== true || procTrialResult.success === false) {
        throw new Error(String(procTrialResult.summary || procTrialResult.message || procTrialResult.error || '数据整理结果未生成可用于对账的左右样例数据'));
      }
      const prepareResponse = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/recon/use-existing`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          rule_json: stripReconTimeSemantics(compiledReconRuleResult.json),
        }),
      });
      const prepareData = await prepareResponse.json().catch(() => ({}));
      if (!prepareResponse.ok) {
        throw new Error(String(prepareData.detail || prepareData.message || '生成数据对账逻辑失败'));
      }
      const response = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/recon/trial`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || data.error || '数据对账试跑失败'));
      }
      const session = asRecord(data.session);
      const reconStep = asRecord(session.recon_step);
      const trialResult = asRecord(reconStep.trial_result);
      const normalizedRule = stripReconTimeSemantics(asRecord(reconStep.effective_rule_json));
      const parsed = parseReconRuleJsonConfig(normalizedRule, parsedReconConfig);
      const passed = trialResult.ready_for_confirm === true && trialResult.success !== false;
      const summary = toText(
        trialResult.summary,
        toText(trialResult.message, toText(trialResult.error, passed ? '数据对账试跑通过' : '数据对账试跑未通过')),
      );
      setReconCompatibility(
        toCompatibilityResult(
          reconStep.compatibility_result,
          passed ? '试跑验证通过，可进入保存方案。' : '试跑未通过，请调整数据对账逻辑后重试。',
        ),
      );
      setSchemeDraft((prev) => ({
        ...prev,
        reconDraft: buildStructuredReconDraftText({
          reconRuleName: toText(
            normalizedRule.rule_name,
            prev.reconRuleName || buildDefaultReconRuleName(prev.name),
          ),
          matchFieldPairs: parsed.matchFieldPairs,
          compareFieldPairs: parsed.compareFieldPairs,
        }),
        reconRuleJson: Object.keys(normalizedRule).length > 0 ? normalizedRule : prev.reconRuleJson,
        reconRuleName: toText(normalizedRule.rule_name, prev.reconRuleName || buildDefaultReconRuleName(prev.name)),
        matchFieldPairs: parsed.matchFieldPairs,
        compareFieldPairs: parsed.compareFieldPairs,
        matchKey: parsed.matchKey,
        leftAmountField: parsed.leftAmountField,
        rightAmountField: parsed.rightAmountField,
        leftTimeSemantic: '',
        rightTimeSemantic: '',
        tolerance: parsed.tolerance,
        reconTrialStatus: passed ? 'passed' : 'needs_adjustment',
        reconTrialSummary: summary,
      }));
      const reconPreview = buildReconPreviewFromTrial(trialResult);
      setReconTrialPreview(reconPreview);
      setWizardDraftState((prev) =>
        updateDerivedDraft(prev, {
          reconPreviewState: reconPreview ? 'current' : 'empty',
        }),
      );
      return passed;
    } catch (error) {
      const message = error instanceof Error ? error.message : '数据对账试跑失败';
      setModalError(message);
      setReconCompatibility({
        status: 'failed',
        message: '试跑未通过，请检查对账逻辑或整理后的样本数据。',
        details: [message],
      });
      setSchemeDraft((prev) => ({
        ...prev,
        reconTrialStatus: 'needs_adjustment',
        reconTrialSummary: message,
      }));
      setReconTrialPreview(null);
      setWizardDraftState((prev) =>
        updateDerivedDraft(prev, {
          reconPreviewState: 'empty',
        }),
      );
      return false;
    } finally {
      setIsTrialingRecon(false);
    }
  }, [
    authToken,
    buildReconPreviewFromTrial,
    compiledReconRuleResult.error,
    compiledReconRuleResult.json,
    ensureDesignSession,
    parsedReconConfig,
    schemeDraft.procRuleJson,
    schemeDraft.procTrialStatus,
    syncDesignTarget,
    toCompatibilityResult,
  ]);

  const handleViewProcJson = useCallback(() => {
    setWizardProcJsonView('proc');
    setWizardReconJsonView('recon');
    setWizardJsonCopyState(null);
    setWizardJsonPanel((prev) => (prev === 'proc' ? null : 'proc'));
  }, []);

  const handleViewReconJson = useCallback(() => {
    if (!compiledReconRuleResult.json) {
      setModalError(compiledReconRuleResult.error || '请先完成对账字段配置。');
      return;
    }
    setModalError(null);
    setWizardProcJsonView('proc');
    setWizardReconJsonView('recon');
    setWizardJsonCopyState(null);
    setWizardJsonPanel((prev) => (prev === 'recon' ? null : 'recon'));
  }, [compiledReconRuleResult.error, compiledReconRuleResult.json]);

  const handleCreateScheme = useCallback(async () => {
    if (!authToken) {
      setModalError('请先登录后再保存对账方案。');
      return;
    }
    if (!schemeDraft.procRuleJson) {
      setModalError('请先生成并验证数据整理规则。');
      return;
    }
    if (!compiledReconRuleResult.json && !schemeDraft.reconRuleJson) {
      setModalError(compiledReconRuleResult.error || '请先生成并验证数据对账逻辑。');
      return;
    }
    if (schemeDraft.procTrialStatus !== 'passed') {
      setModalError('请先完成数据整理试跑验证，再保存方案。');
      return;
    }

    let effectiveReconRuleJson = schemeDraft.reconRuleJson || compiledReconRuleResult.json;
    if (!effectiveReconRuleJson) {
      setModalError('请先生成并验证数据整理规则与对账逻辑。');
      return;
    }
    effectiveReconRuleJson = stripReconTimeSemantics(effectiveReconRuleJson);

    if (schemeDraft.reconTrialStatus !== 'passed') {
      const passed = await trialReconDraft();
      if (!passed) {
        setModalError('数据对账试跑未通过，请调整逻辑后重试。');
        return;
      }
      effectiveReconRuleJson = schemeDraft.reconRuleJson || compiledReconRuleResult.json;
      if (!effectiveReconRuleJson) {
        setModalError('数据对账试跑完成后，仍未生成可保存的对账逻辑。');
        return;
      }
      effectiveReconRuleJson = stripReconTimeSemantics(effectiveReconRuleJson);
    }

    if (!window.confirm('确认当前规则、字段映射和试跑结果都已检查完毕，立即保存方案吗？')) {
      return;
    }

    setIsSubmittingScheme(true);
    setModalError(null);

    try {
      const schemePayloadDraft = buildSchemeCreatePayloadDraft(wizardDraftState);
      const procRuleJson = schemeDraft.procRuleJson;
      const reconRuleJson = effectiveReconRuleJson;
      const activeInputPlanJson = firstNonEmptyRecord(
        schemePayloadDraft.scheme_meta_json.input_plan_json,
        schemeDraft.inputPlanJson,
      );
      const parsedReconRule = parseReconRuleJsonConfig(reconRuleJson, parsedReconConfig);
      const procRuleName = schemeDraft.name.trim() ? `${schemeDraft.name.trim()}整理规则` : '整理规则';
      const reconRuleName =
        toText(asRecord(reconRuleJson).rule_name, buildDefaultReconRuleName(schemeDraft.name));
      const leftDatasetBindings = selectedLeftSources.map((item, index) => ({
        side: 'left',
        slot_key: `left_${index + 1}`,
        dataset_id: item.id,
        dataset_name: item.name,
        business_name: item.businessName || item.name,
        technical_name: item.technicalName || item.resourceKey || item.datasetCode || item.name,
        data_source_id: item.sourceId,
        data_source_name: item.sourceName,
        source_kind: item.sourceKind,
        provider_code: item.providerCode,
        dataset_code: item.datasetCode || item.id,
        resource_key: item.resourceKey || item.datasetCode || item.name,
        dataset_kind: item.datasetKind,
        key_fields: item.keyFields,
        field_label_map: item.fieldLabelMap,
        schema_summary: item.schemaSummary,
      }));
      const rightDatasetBindings = selectedRightSources.map((item, index) => ({
        side: 'right',
        slot_key: `right_${index + 1}`,
        dataset_id: item.id,
        dataset_name: item.name,
        business_name: item.businessName || item.name,
        technical_name: item.technicalName || item.resourceKey || item.datasetCode || item.name,
        data_source_id: item.sourceId,
        data_source_name: item.sourceName,
        source_kind: item.sourceKind,
        provider_code: item.providerCode,
        dataset_code: item.datasetCode || item.id,
        resource_key: item.resourceKey || item.datasetCode || item.name,
        dataset_kind: item.datasetKind,
        key_fields: item.keyFields,
        field_label_map: item.fieldLabelMap,
        schema_summary: item.schemaSummary,
      }));
      const datasetBindingsJson = [
        ...leftDatasetBindings.map((item, index) => ({
          role_code: `left_${index + 1}`,
          data_source_id: item.data_source_id,
          resource_key: item.resource_key,
          binding_name: item.business_name || item.dataset_name || item.resource_key,
          is_required: true,
          priority: 10 + index,
          query: {},
          side: 'left',
          dataset_code: item.dataset_code,
          table_name: item.resource_key,
          dataset_source_type: 'collection_records',
        })),
        ...rightDatasetBindings.map((item, index) => ({
          role_code: `right_${index + 1}`,
          data_source_id: item.data_source_id,
          resource_key: item.resource_key,
          binding_name: item.business_name || item.dataset_name || item.resource_key,
          is_required: true,
          priority: 100 + index,
          query: {},
          side: 'right',
          dataset_code: item.dataset_code,
          table_name: item.resource_key,
          dataset_source_type: 'collection_records',
        })),
      ];
      const response = await fetchReconAutoApi('/schemes', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          scheme_name: schemePayloadDraft.scheme_name,
          description: schemePayloadDraft.description,
          file_rule_code: '',
          proc_rule_code: '',
          recon_rule_code: '',
          dataset_bindings_json: datasetBindingsJson,
          scheme_meta_json: {
            ...schemePayloadDraft.scheme_meta_json,
            dataset_bindings: {
              version: 'v1',
              left: leftDatasetBindings,
              right: rightDatasetBindings,
            },
            source_summary: {
              left: leftDatasetBindings.map((item) => ({
                slot_key: item.slot_key,
                business_name: item.business_name,
                technical_name: item.technical_name,
                data_source_name: item.data_source_name,
              })),
              right: rightDatasetBindings.map((item) => ({
                slot_key: item.slot_key,
                business_name: item.business_name,
                technical_name: item.technical_name,
                data_source_name: item.data_source_name,
              })),
            },
            left_description: schemePayloadDraft.scheme_meta_json.left_description,
            right_description: schemePayloadDraft.scheme_meta_json.right_description,
            validation_summary: {
              proc: {
                status: schemePayloadDraft.scheme_meta_json.proc_trial_status,
                summary: schemePayloadDraft.scheme_meta_json.proc_trial_summary,
              },
              recon: {
                status: schemePayloadDraft.scheme_meta_json.recon_trial_status,
                summary: schemePayloadDraft.scheme_meta_json.recon_trial_summary,
              },
            },
            proc_trial_status: schemePayloadDraft.scheme_meta_json.proc_trial_status,
            proc_trial_summary: schemePayloadDraft.scheme_meta_json.proc_trial_summary,
            recon_trial_status: schemePayloadDraft.scheme_meta_json.recon_trial_status,
            recon_trial_summary: schemePayloadDraft.scheme_meta_json.recon_trial_summary,
            left_output_field_label_map: leftOutputFieldLabelMap,
            right_output_field_label_map: rightOutputFieldLabelMap,
            match_key: parsedReconRule.matchKey.trim() || parsedReconConfig.matchKey.trim(),
            left_amount_field: parsedReconRule.leftAmountField.trim() || parsedReconConfig.leftAmountField.trim(),
            right_amount_field: parsedReconRule.rightAmountField.trim() || parsedReconConfig.rightAmountField.trim(),
            left_time_semantic: '',
            right_time_semantic: '',
            tolerance: parsedReconRule.tolerance.trim() || parsedReconConfig.tolerance.trim(),
            proc_rule_name: procRuleName,
            recon_rule_name: reconRuleName,
            proc_draft_text: schemePayloadDraft.scheme_meta_json.proc_draft_text || summarizeProcDraft(procRuleJson),
            input_plan_json: activeInputPlanJson,
            recon_draft_text:
              schemePayloadDraft.scheme_meta_json.recon_draft_text || summarizeReconDraft(reconRuleJson, parsedReconRule),
            proc_rule_json: procRuleJson,
            recon_rule_json: reconRuleJson,
          },
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || '保存对账方案失败'));
      }
      await loadCenterData();
      onSchemeCreated?.();
      setActiveTab('schemes');
      closeModal();
    } catch (error) {
      setModalError(error instanceof Error ? error.message : '保存对账方案失败');
    } finally {
      setIsSubmittingScheme(false);
    }
  }, [
    authToken,
    closeModal,
    compiledReconRuleResult.error,
    compiledReconRuleResult.json,
    leftOutputFieldLabelMap,
    loadCenterData,
    parsedReconConfig,
    rightOutputFieldLabelMap,
    schemeDraft,
    selectedLeftSources,
    selectedRightSources,
    trialReconDraft,
    wizardDraftState,
  ]);

  const searchOwnerCandidates = useCallback(async () => {
    const query = planDraft.ownerSummary.trim();
    if (!authToken) {
      throw new Error('请先登录后再保存责任人。');
    }
    if (!query) {
      throw new Error('请输入责任人姓名。');
    }
    if (!planDraft.channelConfigId.trim()) {
      throw new Error('请先选择协作通道。');
    }

    const response = await fetchReconAutoApi('/owner-candidates/search', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        channel_config_id: planDraft.channelConfigId.trim(),
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(data.detail || data.message || '查找责任人失败'));
    }
    const candidates = Array.isArray(data.candidates)
      ? (data.candidates as OwnerCandidate[]).filter((item) => item.identifier)
      : [];
    return {
      candidates,
      message: String(data.message || ''),
    };
  }, [authToken, planDraft.channelConfigId, planDraft.ownerSummary]);

  const handleCreatePlan = useCallback(async () => {
    const schemeCode = planDraft.schemeCode.trim();
    if (!authToken) {
      setModalError('请先登录后再保存运行计划。');
      return;
    }
    if (!schemeCode) {
      setModalError('请先选择所属方案。');
      return;
    }
    if (!planDraft.ownerSummary.trim()) {
      setModalError('请填写责任人。');
      return;
    }

    const matchedScheme = schemes.find((s) => s.schemeCode === schemeCode);
    const schemeName = matchedScheme?.name || schemeCode;
    const matchedSchemeMeta = matchedScheme ? extractSchemeMeta(matchedScheme) : null;
    const planInputDatasets = extractRunPlanInputDatasets(matchedSchemeMeta);
    const missingDateInputs = planInputDatasets.filter(
      (input) => input.requiresDateField && !toText(planDraft.dateFieldByInputKey[input.key]).trim(),
    );
    if (missingDateInputs.length > 0) {
      setModalError(
        `请先选择对账日期字段：${missingDateInputs
          .map((input) => `${runPlanInputSideLabel(input.side)} ${input.displayName}`)
          .join('、')}`,
      );
      return;
    }
    const todayStr = new Date().toISOString().slice(0, 10);
    const autoName = `${schemeName} ${todayStr}`;
    const inputBindings = buildRunPlanBindings(
      matchedSchemeMeta,
      planDraft.dateFieldByInputKey,
    );

    if (inputBindings.length === 0) {
      setModalError('当前方案未配置可用的数据源绑定，无法保存运行计划。');
      return;
    }

    const timeExpr = `${planDraft.scheduleHour}:${planDraft.scheduleMinute}`;
    let scheduleTypeForSave: string = planDraft.scheduleType;
    let scheduleExpr = timeExpr;
    if (planDraft.scheduleType === 'weekly') {
      scheduleExpr = `W${planDraft.scheduleDayOfWeek} ${timeExpr}`;
    } else if (planDraft.scheduleType === 'monthly') {
      // 兼容仍在运行的旧后端：monthly 尚未热更新时，回退为 cron 保存。
      scheduleTypeForSave = 'cron';
      scheduleExpr = `0 ${planDraft.scheduleMinute} ${planDraft.scheduleHour} ${planDraft.scheduleDayOfMonth} * *`;
    }

    setIsSubmittingPlan(true);
    setModalError(null);

    try {
      let ownerSummaryForSubmit = planDraft.ownerSummary.trim();
      let ownerIdentifierForSubmit = planDraft.ownerIdentifier.trim();
      if (!ownerIdentifierForSubmit) {
        setOwnerSearchMessage('');
        setOwnerCandidates([]);
        const ownerSearch = await searchOwnerCandidates();
        if (ownerSearch.candidates.length === 0) {
          setOwnerSearchMessage(ownerSearch.message || '未找到匹配的责任人，请检查姓名。');
          return;
        }
        if (ownerSearch.candidates.length > 1) {
          setOwnerCandidates(ownerSearch.candidates);
          setOwnerSearchMessage(`匹配到 ${ownerSearch.candidates.length} 位同名候选人，请根据部门或手机号后四位选择后再保存。`);
          return;
        }
        const [candidate] = ownerSearch.candidates;
        ownerSummaryForSubmit = candidate.display_name || ownerSummaryForSubmit;
        ownerIdentifierForSubmit = candidate.identifier;
        setPlanDraft((prev) => ({
          ...prev,
          ownerSummary: ownerSummaryForSubmit,
          ownerIdentifier: ownerIdentifierForSubmit,
        }));
        setOwnerSearchMessage('已自动匹配到明确责任人。');
      }

      const response = await fetchReconAutoApi('/tasks', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          plan_name: autoName,
          scheme_code: schemeCode,
          schedule_type: scheduleTypeForSave,
          schedule_expr: scheduleExpr,
          biz_date_offset: planDraft.bizDateOffset.trim() || 'T-1',
          input_bindings_json: inputBindings,
          channel_config_id: planDraft.channelConfigId.trim(),
          owner_mapping_json: ownerSummaryForSubmit
            ? {
                default_owner: {
                  name: ownerSummaryForSubmit,
                  identifier: ownerIdentifierForSubmit,
                },
              }
            : {},
          plan_meta_json: {
            biz_date_offset: planDraft.bizDateOffset.trim() || 'T-1',
            reconciliation_period: planDraft.bizDateOffset.trim() || 'T-1',
            date_field_by_input_key: planDraft.dateFieldByInputKey,
            input_bindings: inputBindings,
          },
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || '保存运行计划失败'));
      }
      await loadCenterData();
      setActiveTab('tasks');
      closeModal();
    } catch (error) {
      setModalError(error instanceof Error ? error.message : '保存运行计划失败');
    } finally {
      setIsSubmittingPlan(false);
    }
  }, [authToken, closeModal, loadCenterData, planDraft, schemes, searchOwnerCandidates]);

  const handleDeleteScheme = useCallback(
    async (scheme: ReconSchemeListItem) => {
      if (!authToken) {
        setSchemeDeleteGuard(null);
        setCenterNotice(null);
        setCenterError('请先登录后再删除对账方案。');
        return;
      }
      const relatedTasks = tasks.filter((item) => item.schemeCode === scheme.schemeCode);
      const relatedTaskCount = relatedTasks.length;
      if (relatedTaskCount > 0) {
        setSchemeDeleteGuard({
          schemeId: scheme.id,
          message: `当前方案下还有 ${relatedTaskCount} 个运行计划，请先删除运行计划后再删除对账方案。`,
          tasks: relatedTasks.map((item) => ({
            id: item.id,
            name: item.name,
            scheduleLabel: formatScheduleLabel(item.scheduleType, item.scheduleExpr),
            statusLabel: enabledStatusMeta(item.status === 'enabled').label,
          })),
        });
        setCenterNotice(null);
        setCenterError(null);
        return;
      }
      setSchemeDeleteGuard(null);
      if (!window.confirm(`确定要删除对账方案「${scheme.name}」吗？此操作不可恢复。`)) {
        return;
      }
      try {
        setCenterError(null);
        setCenterNotice(null);
        const response = await fetchReconAutoApi(`/schemes/${encodeURIComponent(scheme.id)}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '删除对账方案失败'));
        }
        setSchemes((prev) => prev.filter((item) => item.id !== scheme.id));
        if (modalState?.kind === 'scheme-detail' && modalState.scheme.id === scheme.id) {
          closeModal();
        }
        setCenterNotice(`对账方案「${scheme.name}」已删除。`);
        await loadCenterData();
      } catch (error) {
        setCenterNotice(null);
        setCenterError(error instanceof Error ? error.message : '删除对账方案失败');
      }
    },
    [authToken, closeModal, loadCenterData, modalState, tasks],
  );

  const handleDeleteTask = useCallback(
    async (task: ReconTaskListItem) => {
      if (!authToken) {
        setModalError('请先登录后再删除任务。');
        return;
      }
      if (!window.confirm('确定要删除该任务吗？此操作不可恢复。')) {
        return;
      }
      try {
        const planId = encodeURIComponent(task.id);
        const deletePath = task.planCode
          ? `/tasks/${planId}?plan_code=${encodeURIComponent(task.planCode)}`
          : `/tasks/${planId}`;
        const response = await fetchReconAutoApi(deletePath, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${authToken}` },
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(String(data.detail || data.message || '删除任务失败'));
        }

        // 兼容旧后端：DELETE 可能只是逻辑停用，这里再补一个前端可识别的删除标记。
        const existingPlanMeta = firstNonEmptyRecord(task.raw.plan_meta_json, task.raw.plan_meta, task.raw.meta);
        const deletedPlanMeta = {
          ...existingPlanMeta,
          is_deleted: true,
          deleted_at: new Date().toISOString(),
        };
        await fetchReconAutoApi(`/tasks/${planId}`, {
          method: 'PATCH',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            is_enabled: false,
            plan_meta_json: deletedPlanMeta,
          }),
        }).catch(() => null);

        setTasks((prev) => prev.filter((item) => item.id !== task.id));
        await loadCenterData();
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '删除任务失败');
      }
    },
    [authToken, loadCenterData],
  );

  const handleToggleTask = useCallback(
    async (taskId: string, currentEnabled: boolean) => {
      if (!authToken) {
        setModalError('请先登录后再修改任务状态。');
        return;
      }
      try {
        const response = await fetchReconAutoApi(`/tasks/${taskId}`, {
          method: 'PATCH',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ is_enabled: !currentEnabled }),
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(String(data.detail || data.message || '更新任务状态失败'));
        }
        setTasks((prev) =>
          prev.map((item) =>
            item.id === taskId
              ? {
                  ...item,
                  status: currentEnabled ? 'paused' : 'enabled',
                  raw: {
                    ...item.raw,
                    is_enabled: !currentEnabled,
                  },
                }
              : item,
          ),
        );
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '更新任务状态失败');
      }
    },
    [authToken],
  );

  const handleRerunValidation = useCallback(
    async (originalRunId: string, exceptionId = '') => {
      if (!authToken) {
        setCenterError('请先登录后再重新对账验证。');
        return;
      }
      setRerunningRunId(originalRunId);
      setCenterError(null);
      setCenterNotice(null);
      setModalError(null);
      try {
        const response = await fetchReconAutoApi('/runs/rerun', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            original_run_id: originalRunId,
            exception_id: exceptionId,
            reason: exceptionId ? '前端按异常重新对账验证' : '前端按运行重新对账验证',
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = data.detail;
          if (typeof detail === 'object' && detail !== null) {
            const message = toText(detail.message) || toText(detail.error) || '重新对账验证失败';
            const todo = toText(detail.todo);
            throw new Error(todo ? `${message}：${todo}` : message);
          }
          throw new Error(String(detail || data.message || '重新对账验证失败'));
        }
        await loadCenterData();
        setActiveTab('runs');
        setCenterNotice(toText(data.message) || '重新对账验证已提交，请稍后刷新查看最新状态。');
      } catch (error) {
        const message = error instanceof Error ? error.message : '重新对账验证失败';
        setCenterError(message);
        setModalError(message);
      } finally {
        setRerunningRunId((prev) => (prev === originalRunId ? null : prev));
      }
    },
    [authToken, loadCenterData],
  );

  const schemeStepOneReady = Boolean(schemeDraft.name.trim());
  const aiProcGenerationBusy =
    aiProcSideDrafts.left.status === 'generating' || aiProcSideDrafts.right.status === 'generating';
  const aiProcStepReady = Boolean(
    aiProcSideDrafts.left.status === 'succeeded'
    && aiProcSideDrafts.right.status === 'succeeded'
    && schemeDraft.procRuleJson
    && leftOutputFields.length > 0
    && rightOutputFields.length > 0,
  );
  const schemeStepTwoReady = Boolean(
    procBuildMode === 'ai_complex_rule'
      ? aiProcStepReady
      : selectedLeftSources.length > 0
        && selectedRightSources.length > 0
        && leftOutputFields.length > 0
        && rightOutputFields.length > 0,
  );
  const schemeStepTwoPassed =
    schemeDraft.procTrialStatus === 'passed' && Boolean(schemeDraft.procRuleJson);
  const schemeStepThreeReady = Boolean(compiledReconRuleResult.json);
  const isSchemeWizardBusy =
    isTrialingProc || isTrialingRecon || aiProcGenerationBusy;

  const goToNextSchemeStep = useCallback(async () => {
    setModalError(null);
    if (isSchemeWizardBusy) {
      setModalError('当前正在生成或试跑，请等待本次操作完成后再进入下一步。');
      return;
    }
    if (schemeWizardStep === 1) {
      if (!schemeStepOneReady) {
        setModalError('请先完成方案名称和对账目标。');
        return;
      }
      setSchemeWizardStep(2);
      return;
    }
    if (schemeWizardStep === 2) {
      if (!schemeStepTwoReady) {
        setModalError(
          procBuildMode === 'ai_complex_rule'
            ? '请先分别完成左侧和右侧的“AI生成输出数据”。'
            : '请先完成左右数据集选择与输出字段配置。',
        );
        return;
      }
      if (!schemeStepTwoPassed) {
        if (procBuildMode === 'ai_complex_rule') {
          setModalError('AI生成输出数据尚未通过，请重新生成左右侧输出数据。');
          return;
        }
        const passed = await trialProcDraft();
        if (!passed) {
          setModalError('数据整理试跑未通过，请调整配置后重试。');
          return;
        }
      }
      const nextMatchFieldPairs = filterCompleteReconFieldPairs(activeMatchFieldPairs);
      const nextCompareFieldPairs = filterCompleteReconFieldPairs(activeCompareFieldPairs);
      applyStructuredReconConfig({
        reconRuleName: schemeDraft.reconRuleName || buildDefaultReconRuleName(schemeDraft.name),
        matchFieldPairs: nextMatchFieldPairs,
        compareFieldPairs: nextCompareFieldPairs,
      });
      setSchemeWizardStep(3);
      return;
    }
    if (schemeWizardStep === 3) {
      if (!schemeStepThreeReady) {
        setModalError(compiledReconRuleResult.error || '请至少配置一组匹配字段和一组对比字段。');
        return;
      }
      setModalError('第三步已是最后一步，请直接点击“保存方案”。');
    }
  }, [
    compiledReconRuleResult.error,
    compiledReconRuleResult.json,
    schemeStepOneReady,
    schemeStepThreeReady,
    schemeStepTwoPassed,
    schemeStepTwoReady,
    procBuildMode,
    aiProcGenerationBusy,
    isSchemeWizardBusy,
    schemeDraft.reconRuleJson,
    schemeWizardStep,
    trialProcDraft,
    applyStructuredReconConfig,
    activeCompareFieldPairs,
    activeMatchFieldPairs,
  ]);

  const goToPreviousSchemeStep = useCallback(() => {
    setSchemeWizardStep((prev) => (prev === 1 ? prev : ((prev - 1) as SchemeWizardStep)));
  }, []);

  const renderEmptyState = useCallback(
    ({
      title,
      description,
      actionLabel,
      onAction,
      actionDisabled,
    }: {
      title: string;
      description: string;
      actionLabel?: string;
      onAction?: () => void;
      actionDisabled?: boolean;
    }) => (
      <div className="flex min-h-[280px] flex-col items-center justify-center rounded-[26px] border border-dashed border-border bg-surface px-6 py-10 text-center">
        <p className="text-base font-semibold text-text-primary">{title}</p>
        <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">{description}</p>
        {actionLabel && onAction ? (
          <button
            type="button"
            onClick={onAction}
            disabled={actionDisabled}
            className="mt-5 inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Plus className="h-4 w-4" />
            {actionLabel}
          </button>
        ) : null}
      </div>
    ),
    [],
  );

  const headerRightSlot = (
    <div className="hidden items-center gap-2 lg:flex">
      <SummaryBadge label="方案" value={schemes.length} />
      <SummaryBadge label="任务" value={tasks.length} />
      <SummaryBadge label="运行" value={runs.length} />
    </div>
  );

  const selectedExceptionRawRecord = selectedExceptionDetail
    ? getRunExceptionRawRecord(selectedExceptionDetail)
    : {};
  const selectedExceptionSideRecords = selectedExceptionDetail
    ? getRunExceptionRecordsBySide(selectedExceptionDetail)
    : { left: {}, right: {}, extra: {} };
  const selectedExceptionRun =
    selectedExceptionDetail && modalState?.kind === 'run-exceptions' ? modalState.run : null;
  const selectedExceptionScheme = selectedExceptionRun
    ? schemes.find((item) => item.schemeCode === selectedExceptionRun.schemeCode) || null
    : null;
  const selectedExceptionSchemeMeta = selectedExceptionScheme
    ? extractSchemeMeta(selectedExceptionScheme)
    : null;
  const selectedExceptionLeftDatasetLabel = (
    selectedExceptionSchemeMeta
      ? resolveResultDatasetLabel(
          'left',
          selectedExceptionSchemeMeta.matchFieldPairs,
          selectedExceptionSchemeMeta.leftOutputFields,
          selectedExceptionSchemeMeta.leftSources,
        )
      : ''
  ) || toText(selectedExceptionSideRecords.left.source_name, toText(selectedExceptionRawRecord.source_name, '原始记录'));
  const selectedExceptionRightDatasetLabel = (
    selectedExceptionSchemeMeta
      ? resolveResultDatasetLabel(
          'right',
          selectedExceptionSchemeMeta.matchFieldPairs,
          selectedExceptionSchemeMeta.rightOutputFields,
          selectedExceptionSchemeMeta.rightSources,
        )
      : ''
  ) || toText(selectedExceptionSideRecords.right.source_name, toText(selectedExceptionRawRecord.source_name, '原始记录'));
  const selectedExceptionRecordSections = selectedExceptionDetail
    ? [
        Object.keys(selectedExceptionSideRecords.left).length > 0
          ? {
              title: selectedExceptionLeftDatasetLabel || '原始记录',
              record: selectedExceptionSideRecords.left,
            }
          : null,
        Object.keys(selectedExceptionSideRecords.right).length > 0
          ? {
              title: selectedExceptionRightDatasetLabel || '原始记录',
              record: selectedExceptionSideRecords.right,
            }
          : null,
      ].filter((item): item is { title: string; record: Record<string, unknown> } => Boolean(item))
    : [];

  const renderSchemeRows = () =>
    schemes.length === 0
      ? renderEmptyState({
          title: '还没有对账方案',
          description: '先新增一个对账方案，完成对账目标、数据整理和对账逻辑配置。',
        })
      : (
    <div className="overflow-x-auto rounded-[26px] border border-border bg-surface shadow-sm">
      <div className="w-full min-w-[1080px]">
        <ListHeader
          columns={['对账方案', '整理规则', '对账逻辑', '操作']}
          template={SCHEME_LIST_TEMPLATE}
        />
        {schemes.map((item) => {
          const schemeMeta = extractSchemeMeta(item);
          const procRuleLabel = schemeMeta.procRuleName || (item.name ? `${item.name}整理规则` : '整理规则');
          const reconRuleLabel = schemeMeta.reconRuleName || (item.name ? `${item.name} 对账逻辑` : '未命名对账逻辑');
          const isGuardVisible = schemeDeleteGuard?.schemeId === item.id;
          const guardTasks = isGuardVisible ? schemeDeleteGuard?.tasks || [] : [];
          return (
            <div
              key={item.id}
              className="border-b border-border-subtle last:border-b-0"
            >
              <div
                className="grid items-center gap-4 px-5 py-4"
                style={{ gridTemplateColumns: SCHEME_LIST_TEMPLATE }}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-text-primary">{item.name}</p>
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text-primary">{procRuleLabel}</p>
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text-primary">{reconRuleLabel}</p>
                </div>
                <div className="flex items-center justify-self-end gap-2">
                  <button
                    type="button"
                    onClick={() => setModalState({ kind: 'scheme-detail', scheme: item })}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                  >
                    <Eye className="h-4 w-4" />
                    查看详情
                  </button>
                  <button
                    type="button"
                    onClick={() => openCreatePlanModal(item)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100"
                  >
                    <Plus className="h-4 w-4" />
                    新增运行计划
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeleteScheme(item)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-secondary transition hover:border-red-200 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                    删除
                  </button>
                </div>
              </div>
              {isGuardVisible ? (
                <div className="px-5 pb-4">
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-start gap-2">
                          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                          <p className="min-w-0">{schemeDeleteGuard?.message}</p>
                        </div>
                        {guardTasks.length > 0 ? (
                          <div className="mt-3 rounded-xl border border-amber-200/70 bg-white/65 px-3 py-2.5">
                            <p className="text-xs font-semibold tracking-[0.08em] text-amber-700">关联运行计划</p>
                            <div className="mt-2 space-y-1.5">
                              {guardTasks.map((task, index) => (
                                <div
                                  key={task.id}
                                  className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-amber-900"
                                >
                                  <span className="font-medium">{index + 1}. {task.name}</span>
                                  <span className="text-amber-700">· {task.scheduleLabel}</span>
                                  <span className="text-amber-700">· {task.statusLabel}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          const firstTaskId = guardTasks[0]?.id || null;
                          setSchemeDeleteGuard(null);
                          setActiveTab('tasks');
                          setFocusedTaskId(firstTaskId);
                        }}
                        className="inline-flex shrink-0 items-center rounded-xl border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-800 transition hover:bg-amber-100"
                      >
                        去运行计划
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );

  const renderTaskRows = () =>
    tasks.length === 0
      ? renderEmptyState({
          title: '还没有对账任务',
          description: '运行计划保存后会生成对账任务，用于后续自动执行和责任人通知。',
          actionLabel: schemes.length > 0 ? '新增运行计划' : undefined,
          onAction: schemes.length > 0 ? () => openCreatePlanModal(null) : undefined,
          actionDisabled: schemes.length === 0,
        })
      : (
    <div className="overflow-x-auto rounded-[26px] border border-border bg-surface shadow-sm">
      <div className="min-w-[1080px]">
        <ListHeader
          columns={['任务名称', '对账方案', '运行计划', '状态', '操作']}
          template={TASK_LIST_TEMPLATE}
        />
        {tasks.map((item) => {
          const statusMeta = enabledStatusMeta(item.status === 'enabled');
          const isFocusedTask = focusedTaskId === item.id;
          return (
            <div
              key={item.id}
              ref={(node) => {
                taskRowRefs.current[item.id] = node;
              }}
              data-testid={`recon-task-row-${item.id}`}
              data-highlighted={isFocusedTask ? 'true' : 'false'}
              className={cn(
                'grid items-center gap-6 border-b border-border-subtle px-5 py-4 last:border-b-0 transition-colors',
                isFocusedTask && 'bg-sky-50/80 ring-1 ring-inset ring-sky-200',
              )}
              style={{ gridTemplateColumns: TASK_LIST_TEMPLATE }}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-text-primary">{item.name}</p>
                <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-secondary">
                  {resolveChannelProviderLabel(item.channelConfigId)} · {item.ownerSummary || '--'}
                </p>
              </div>
              <span className="truncate text-sm text-text-secondary">{item.schemeName || '--'}</span>
              <span className="text-sm text-text-secondary">
                {formatScheduleLabel(item.scheduleType, item.scheduleExpr)}
              </span>
              <span
                className={cn(
                  'justify-self-start rounded-full border px-2.5 py-1 text-xs font-medium',
                  statusMeta.className,
                )}
              >
                {statusMeta.label}
              </span>
              <div className="justify-self-end flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleToggleTask(item.id, item.status === 'enabled')}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm transition',
                    item.status === 'enabled'
                      ? 'border-border bg-surface text-text-secondary hover:border-amber-300 hover:text-amber-600'
                      : 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
                  )}
                >
                  {item.status === 'enabled' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  {item.status === 'enabled' ? '停用' : '启用'}
                </button>
                <button
                  type="button"
                  onClick={() => handleDeleteTask(item)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-secondary transition hover:border-red-200 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" />
                  删除
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  const renderRunRows = () =>
    runs.length === 0
      ? renderEmptyState({
          title: '还没有运行记录',
          description: '对账任务执行后，成功或失败都会在这里沉淀运行记录和异常处理入口。',
        })
      : (
    <div className="overflow-x-auto rounded-[26px] border border-border bg-surface shadow-sm">
      <div className="min-w-[1080px]">
        <ListHeader
          columns={['运行任务', '异常数', '状态', '操作']}
          template={RUN_LIST_TEMPLATE}
        />
        {runs.map((item) => {
          const statusMeta = executionStatusMeta(item.executionStatus);
          return (
            <div
              key={item.id}
              data-testid={`execution-run-row-${item.id}`}
              className="grid items-center gap-6 border-b border-border-subtle px-5 py-4 last:border-b-0"
              style={{ gridTemplateColumns: RUN_LIST_TEMPLATE }}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-text-primary">{item.planName}</p>
                <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-secondary">
                  {item.failedReason
                    ? `失败于 ${item.failedStage || '未知阶段'} · ${item.failedReason}`
                    : `${item.schemeName} · ${formatDateTime(item.startedAt)}`}
                </p>
              </div>
              <span className="text-sm text-text-secondary">{item.anomalyCount}</span>
              <span
                className={cn(
                  'justify-self-start rounded-full border px-2.5 py-1 text-xs font-medium',
                  statusMeta.className,
                )}
              >
                {statusMeta.label}
              </span>
              <div className="justify-self-end">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRerunValidation(item.id)}
                    disabled={rerunningRunId === item.id}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <RefreshCw className={cn('h-4 w-4', rerunningRunId === item.id && 'animate-spin')} />
                    {rerunningRunId === item.id ? '验证中...' : '重新对账验证'}
                  </button>
                  <button
                    type="button"
                    data-testid={`execution-run-exceptions-${item.id}`}
                    onClick={() => setModalState({ kind: 'run-exceptions', run: item })}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                  >
                    <AlertCircle className="h-4 w-4" />
                    异常看板
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  const renderSchemeWizardContent = () => {
    const selectedSourcesForLookup = [...selectedLeftSources, ...selectedRightSources];
    const findSourceByPreview = (previewSource: { sourceId: string; sourceName: string }) =>
      selectedSourcesForLookup.find((source) => (
        source.id === previewSource.sourceId
        || source.datasetCode === previewSource.sourceId
        || source.resourceKey === previewSource.sourceId
        || source.name === previewSource.sourceName
        || source.businessName === previewSource.sourceName
      ));

    const mappedProcTrialPreview = procTrialPreview
      ? {
          status: procTrialPreview.status,
          summary: procTrialPreview.summary,
          leftSourceSamples: procTrialPreview.rawSources
            .filter((item) => item.side === 'left')
            .map((item) => {
              const matchedSource = findSourceByPreview(item);
              const mergedFieldLabelMap = mergeFieldLabelMaps(
                item.fieldLabelMap,
                resolveSourceFieldLabelMap(matchedSource),
              );
              return {
                title: matchedSource ? resolveDatasetDisplayName(matchedSource) : item.sourceName,
                fieldLabelMap: mergedFieldLabelMap,
                columnHints: buildInputPreviewColumnHints(
                  matchedSource,
                  leftOutputFields,
                  mergedFieldLabelMap,
                ),
                showRawFieldName: false,
                originLabel: item.sampleOriginLabel,
                originHint: item.sampleOriginHint,
                rows: item.rows,
              };
            }),
          rightSourceSamples: procTrialPreview.rawSources
            .filter((item) => item.side === 'right')
            .map((item) => {
              const matchedSource = findSourceByPreview(item);
              const mergedFieldLabelMap = mergeFieldLabelMaps(
                item.fieldLabelMap,
                resolveSourceFieldLabelMap(matchedSource),
              );
              return {
                title: matchedSource ? resolveDatasetDisplayName(matchedSource) : item.sourceName,
                fieldLabelMap: mergedFieldLabelMap,
                columnHints: buildInputPreviewColumnHints(
                  matchedSource,
                  rightOutputFields,
                  mergedFieldLabelMap,
                ),
                showRawFieldName: false,
                originLabel: item.sampleOriginLabel,
                originHint: item.sampleOriginHint,
                rows: item.rows,
              };
            }),
          leftOutputSamples: procTrialPreview.preparedOutputs
            .filter((item) => item.side === 'left')
            .map((item) => ({
              title: item.title,
              fieldLabelMap: item.fieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
              columnHints: buildOutputPreviewColumnHints(
                leftOutputFields,
                selectedLeftSources,
                item.fieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
              ),
              showRawFieldName: true,
              rows: item.rows,
            })),
          rightOutputSamples: procTrialPreview.preparedOutputs
            .filter((item) => item.side === 'right')
            .map((item) => ({
              title: item.title,
              fieldLabelMap: item.fieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
              columnHints: buildOutputPreviewColumnHints(
                rightOutputFields,
                selectedRightSources,
                item.fieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
              ),
              showRawFieldName: true,
              rows: item.rows,
            })),
          validations: procTrialPreview.validations,
        }
      : undefined;
    const mappedReconTrialPreview = reconTrialPreview
      ? {
          status: reconTrialPreview.status,
          summary: reconTrialPreview.summary,
          leftSamples: reconTrialPreview.leftRows,
          rightSamples: reconTrialPreview.rightRows,
          leftFieldLabelMap: reconTrialPreview.leftFieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
          rightFieldLabelMap: reconTrialPreview.rightFieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
          resultSamples: reconTrialPreview.results.map((item) => ({
            match_fields: item.matchFields,
            left_compare_fields: item.leftCompareFields,
            right_compare_fields: item.rightCompareFields,
            result: item.result,
          })),
          resultFieldLabelMap: reconTrialPreview.resultFieldLabelMap || RECON_RESULT_FIELD_LABEL_MAP,
          resultSummary: reconTrialPreview.resultSummary,
        }
      : undefined;

    if (schemeWizardStep === 1) {
      return (
        <SchemeWizardIntentStep
          name={schemeDraft.name}
          onNameChange={(value) => resetSchemeDraftFromGoalChange({ name: value })}
        />
      );
    }

    if (schemeWizardStep === 2) {
      return (
        <div className="space-y-5">
          <SchemeWizardTargetProcStep
            authToken={authToken}
            schemeDraft={{
              name: schemeDraft.name,
              businessGoal: schemeDraft.businessGoal,
              leftDescription: schemeDraft.leftDescription,
              rightDescription: schemeDraft.rightDescription,
              procTrialStatus: schemeDraft.procTrialStatus,
              procTrialSummary: schemeDraft.procTrialSummary,
            }}
            selectedLeftSources={selectedLeftSources}
            selectedRightSources={selectedRightSources}
            leftOutputFields={leftOutputFields}
            rightOutputFields={rightOutputFields}
            procBuildMode={procBuildMode}
            aiProcSideDrafts={aiProcSideDrafts}
            procCompatibility={procCompatibilityState}
            onChangeProcBuildMode={handleProcBuildModeChange}
            onChangeAiProcRuleDraft={handleAiProcRuleDraftChange}
            onGenerateAiProcOutput={handleGenerateAiProcOutput}
            onChangeSourceSelection={(side, sources) => changeSchemeSources(side, sources)}
            onChangeOutputFields={(side, fields) =>
              handlePreparationDraftChange((prev) => applyPreparationOutputFields(prev, side, fields))
            }
            onRecommendOutputFields={(side) => recommendPreparationOutputFields(side)}
            isTrialingProc={isTrialingProc}
            onTrialProc={trialProcDraft}
            onViewProcJson={handleViewProcJson}
            procJsonPreview={procJsonPreview}
            procTrialPreview={mappedProcTrialPreview}
          />

        </div>
      );
    }

    if (schemeWizardStep === 3) {
      return (
        <div className="space-y-5">
          <SchemeWizardReconStep
            schemeDraft={{
              reconTrialStatus: schemeDraft.reconTrialStatus,
              reconTrialSummary: schemeDraft.reconTrialSummary,
            }}
            reconRuleName={schemeDraft.reconRuleName || buildDefaultReconRuleName(schemeDraft.name)}
            matchFieldPairs={activeMatchFieldPairs}
            compareFieldPairs={activeCompareFieldPairs}
            leftMatchFieldOptions={leftReconFieldOptions}
            rightMatchFieldOptions={rightReconFieldOptions}
            leftCompareFieldOptions={leftReconFieldOptions}
            rightCompareFieldOptions={rightReconFieldOptions}
            leftFieldLabelMap={leftOutputFieldLabelMap}
            rightFieldLabelMap={rightOutputFieldLabelMap}
            reconCompatibility={reconCompatibilityState}
            onStructuredConfigChange={(patch) => applyStructuredReconConfig(patch)}
            onTrialRecon={trialReconDraft}
            onViewReconJson={handleViewReconJson}
            reconJsonPreview={reconJsonPreview}
            reconTrialPreview={mappedReconTrialPreview}
            trialDisabled={
              isTrialingRecon
              || !schemeDraft.procRuleJson
              || schemeDraft.procTrialStatus !== 'passed'
              || !compiledReconRuleResult.json
            }
            isTrialingRecon={isTrialingRecon}
          />

        </div>
      );
    }

    return null;
  };

  const renderModalContent = () => {
    if (!modalState) return null;

    if (modalState.kind === 'create-scheme') {
      return (
        <>
          <div className="border-b border-border px-6 py-5">
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">新增对账方案</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">按三步完成方案设计与试跑确认</h3>
          </div>
          <div className="space-y-6 px-6 py-5">
            <div className="grid gap-3 lg:grid-cols-3">
              {SCHEME_WIZARD_STEPS.map((step) => (
                <WizardStepBadge
                  key={step.id}
                  active={schemeWizardStep === step.id}
                  completed={schemeWizardStep > step.id}
                  index={step.id}
                  title={step.title}
                  description={step.description}
                />
              ))}
            </div>
            {modalError ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {modalError}
              </div>
            ) : null}
            {renderSchemeWizardContent()}
          </div>
          <div className="flex items-center justify-between border-t border-border px-6 py-4">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200"
              >
                取消
              </button>
              {schemeWizardStep > 1 ? (
                <button
                  type="button"
                  onClick={goToPreviousSchemeStep}
                  className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200"
                >
                  上一步
                </button>
              ) : null}
            </div>
            {schemeWizardStep < 3 ? (
              <button
                type="button"
                onClick={goToNextSchemeStep}
                disabled={
                  isSubmittingScheme ||
                  isSchemeWizardBusy ||
                  (schemeWizardStep === 1 && !schemeStepOneReady) ||
                  (schemeWizardStep === 2 && !schemeStepTwoReady) ||
                  (schemeWizardStep === 3 && !schemeStepThreeReady)
                }
                className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                下一步
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCreateScheme}
                disabled={
                  isSubmittingScheme ||
                  !schemeStepOneReady ||
                  !schemeStepTwoPassed ||
                  !schemeStepThreeReady
                }
                className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmittingScheme ? '保存中...' : '保存方案'}
              </button>
            )}
          </div>
        </>
      );
    }

    if (modalState.kind === 'create-plan') {
      return (
        <>
          <div className="border-b border-border px-6 py-5">
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">新增运行计划</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">为方案补充调度、对账周期、协作通道与责任人</h3>
          </div>
          <div className="space-y-4 px-6 py-5">
            {modalError ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {modalError}
              </div>
            ) : null}
            <label className="block">
              <span className="text-xs font-medium text-text-secondary">对账方案</span>
              <select
                value={planDraft.schemeCode}
                onChange={(event) => {
                  const nextSchemeCode = event.target.value;
                  const nextScheme = schemes.find((scheme) => scheme.schemeCode === nextSchemeCode) || null;
                  const nextSchemeMeta = nextScheme ? extractSchemeMeta(nextScheme) : null;
                  setPlanDraft((prev) => ({
                    ...prev,
                    schemeCode: nextSchemeCode,
                    dateFieldByInputKey: buildDefaultRunPlanDateFieldMap(nextSchemeMeta),
                  }));
                }}
                className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
              >
                <option value="">请选择对账方案</option>
                {schemes.map((scheme) => (
                  <option key={scheme.id} value={scheme.schemeCode}>
                    {scheme.name}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-xs leading-5 text-text-muted">
                对账逻辑只负责“怎么匹配、怎么比较”；这里选择本次要按哪一天的数据发起对账。
              </p>
            </label>

            <div className="rounded-3xl border border-border bg-surface-secondary p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-text-primary">对账日期字段</p>
                  <p className="mt-1 text-xs leading-5 text-text-secondary">
                    选择每个基础数据集里代表业务发生日期的字段。运行计划是 T-1 时，系统会先从已采集数据中筛出“该字段等于昨天”的数据，再按整理规则自动补充关联数据。
                  </p>
                </div>
                <span className="rounded-full border border-sky-100 bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-700">
                  {selectedPlanDateInputs.length} 个基础数据集
                </span>
              </div>
              {selectedPlanDateInputs.length > 0 ? (
                <div className="mt-4 grid gap-3">
                  {selectedPlanDateInputs.map((input) => {
                    const options = buildRunPlanDateFieldOptions(input);
                    return (
                      <label
                        key={input.key}
                        className="grid gap-2 rounded-2xl border border-border-subtle bg-surface px-3 py-3 md:grid-cols-[minmax(160px,0.9fr)_minmax(0,1.4fr)] md:items-center"
                      >
                        <span>
                          <span className="block text-xs font-medium text-text-secondary">
                            {runPlanInputSideLabel(input.side)} {input.displayName}
                          </span>
                          <span className="mt-0.5 block truncate text-[11px] text-text-muted">
                            {input.alias} / {input.table}
                          </span>
                        </span>
                        <select
                          value={planDraft.dateFieldByInputKey[input.key] || ''}
                          onChange={(event) =>
                            setPlanDraft((prev) => ({
                              ...prev,
                              dateFieldByInputKey: {
                                ...prev.dateFieldByInputKey,
                                [input.key]: event.target.value,
                              },
                            }))
                          }
                          className="w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                        >
                          <option value="">请选择对账日期字段</option>
                          {options.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                  当前方案没有可识别的基础输入数据集，请先重新生成数据整理规则。
                </p>
              )}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="text-xs font-medium text-text-secondary">对账周期</span>
                <select
                  value={planDraft.bizDateOffset}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, bizDateOffset: event.target.value }))
                  }
                  className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  <option value="T-1">T-1</option>
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-text-secondary">调度方式</span>
                <select
                  value={planDraft.scheduleType}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({
                      ...prev,
                      scheduleType: event.target.value as PlanDraft['scheduleType'],
                    }))
                  }
                  className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  <option value="daily">每日</option>
                  <option value="weekly">每周</option>
                  <option value="monthly">每月</option>
                </select>
              </label>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {planDraft.scheduleType === 'weekly' ? (
                <label className="block">
                  <span className="text-xs font-medium text-text-secondary">星期几</span>
                  <select
                    value={planDraft.scheduleDayOfWeek}
                    onChange={(event) =>
                      setPlanDraft((prev) => ({ ...prev, scheduleDayOfWeek: event.target.value }))
                    }
                    className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                  >
                    <option value="1">星期一</option>
                    <option value="2">星期二</option>
                    <option value="3">星期三</option>
                    <option value="4">星期四</option>
                    <option value="5">星期五</option>
                    <option value="6">星期六</option>
                    <option value="0">星期日</option>
                  </select>
                </label>
              ) : planDraft.scheduleType === 'monthly' ? (
                <label className="block">
                  <span className="text-xs font-medium text-text-secondary">每月几日</span>
                  <select
                    value={planDraft.scheduleDayOfMonth}
                    onChange={(event) =>
                      setPlanDraft((prev) => ({ ...prev, scheduleDayOfMonth: event.target.value }))
                    }
                    className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                  >
                    {Array.from({ length: 28 }, (_, i) => (
                      <option key={i + 1} value={String(i + 1)}>
                        {i + 1} 日
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <div />
              )}
            </div>

            <div>
              <span className="text-xs font-medium text-text-secondary">执行时间</span>
              <div className="mt-1.5 grid grid-cols-2 gap-3">
                <select
                  value={planDraft.scheduleHour}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, scheduleHour: event.target.value }))
                  }
                  className="w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  {Array.from({ length: 24 }, (_, i) => {
                    const h = String(i).padStart(2, '0');
                    return (
                      <option key={h} value={h}>
                        {h} 时
                      </option>
                    );
                  })}
                </select>
                <select
                  value={planDraft.scheduleMinute}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, scheduleMinute: event.target.value }))
                  }
                  className="w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  {Array.from({ length: 12 }, (_, i) => {
                    const m = String(i * 5).padStart(2, '0');
                    return (
                      <option key={m} value={m}>
                        {m} 分
                      </option>
                    );
                  })}
                </select>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="text-xs font-medium text-text-secondary">协作通道</span>
                <select
                  value={planDraft.channelConfigId}
                  onChange={(event) => {
                    setPlanDraft((prev) => ({
                      ...prev,
                      channelConfigId: event.target.value,
                      ownerIdentifier: '',
                    }));
                    setOwnerCandidates([]);
                    setOwnerSearchMessage('');
                  }}
                  className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  <option value="">暂不通知</option>
                  {availableChannels.map((channel) => (
                    <option key={channel.id} value={channel.id}>
                      {collaborationProviderLabel(channel.provider)} / {channel.name || channel.channel_code}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-text-secondary">责任人</span>
                <input
                  value={planDraft.ownerSummary}
                  onChange={(event) => {
                    const value = event.target.value;
                    setPlanDraft((prev) => ({
                      ...prev,
                      ownerSummary: value,
                      ownerIdentifier: '',
                    }));
                    setOwnerCandidates([]);
                    setOwnerSearchMessage('');
                  }}
                  required
                  className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                  placeholder="例如：张三"
                />
                {planDraft.ownerIdentifier ? (
                  <p className="mt-1.5 text-xs text-emerald-700">已选择明确责任人，保存后将使用钉钉 userId 发送通知。</p>
                ) : (
                  <p className="mt-1.5 text-xs text-text-muted">保存时自动校验责任人；同名时会提示选择候选人。</p>
                )}
              </label>
            </div>

            {ownerSearchMessage ? (
              <div className="rounded-2xl border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-800">
                {ownerSearchMessage}
              </div>
            ) : null}

            {ownerCandidates.length > 0 ? (
              <div className="grid gap-2">
                {ownerCandidates.map((candidate) => {
                  const selected = planDraft.ownerIdentifier === candidate.identifier;
                  return (
                    <button
                      key={candidate.identifier}
                      type="button"
                      onClick={() => {
                        setPlanDraft((prev) => ({
                          ...prev,
                          ownerSummary: candidate.display_name || prev.ownerSummary,
                          ownerIdentifier: candidate.identifier,
                        }));
                        setOwnerSearchMessage('已选择明确责任人，请再次点击保存运行计划。');
                      }}
                      className={cn(
                        'rounded-2xl border px-4 py-3 text-left text-sm transition',
                        selected
                          ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
                          : 'border-border bg-surface text-text-primary hover:border-sky-200',
                      )}
                    >
                      <div className="font-medium">{candidate.display_name || '未命名用户'}</div>
                      <div className="mt-1 text-xs text-text-secondary">
                        {formatOwnerCandidateHint(candidate)}
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : null}

            {loadingChannels ? (
              <div className="flex items-center gap-2 rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm text-text-secondary">
                <RefreshCw className="h-4 w-4 animate-spin" />
                正在加载协作通道...
              </div>
            ) : null}

            {channelLoadError ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {channelLoadError}
              </div>
            ) : null}
          </div>
          <div className="flex items-center justify-between border-t border-border px-6 py-4">
            {availableChannels.length === 0 && onOpenCollaborationChannels ? (
              <button
                type="button"
                onClick={() => onOpenCollaborationChannels()}
                className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
              >
                去配置协作通道
              </button>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleCreatePlan}
                disabled={
                  isSubmittingPlan ||
                  !planDraft.schemeCode.trim() ||
                  !planDraft.ownerSummary.trim()
                }
                className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmittingPlan ? '保存中...' : '保存任务'}
              </button>
            </div>
          </div>
        </>
      );
    }

    if (modalState.kind === 'scheme-detail') {
      const { scheme } = modalState;
      const schemeMeta = extractSchemeMeta(scheme);
      const leftMatchFields = formatDetailFieldValues(
        collectReconSideFieldValues('left', schemeMeta.matchFieldPairs),
        schemeMeta.leftOutputFieldLabelMap,
      );
      const rightMatchFields = formatDetailFieldValues(
        collectReconSideFieldValues('right', schemeMeta.matchFieldPairs),
        schemeMeta.rightOutputFieldLabelMap,
      );
      const leftCompareFields = formatDetailFieldValues(
        collectReconSideFieldValues('left', schemeMeta.compareFieldPairs),
        schemeMeta.leftOutputFieldLabelMap,
      );
      const rightCompareFields = formatDetailFieldValues(
        collectReconSideFieldValues('right', schemeMeta.compareFieldPairs),
        schemeMeta.rightOutputFieldLabelMap,
      );
      return (
        <>
          <div className="border-b border-border px-6 py-5">
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">方案详情</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">{scheme.name}</h3>
          </div>
          <div className="space-y-5 px-6 py-5">
            <div className="rounded-3xl border border-border bg-surface-secondary p-4">
              <p className="text-sm font-semibold text-text-primary">对账目标</p>
              <p className="mt-2 text-sm leading-6 text-text-secondary">
                {schemeMeta.businessGoal || '当前方案尚未补充业务说明。'}
              </p>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <div className="min-w-0 overflow-hidden rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">左侧数据</p>
                <div className="mt-3 min-w-0 space-y-2">
                  {schemeMeta.leftSources.map((source) => (
                    <div
                      key={source.id || source.name}
                      className="min-w-0 overflow-hidden rounded-2xl border border-border bg-surface px-4 py-3"
                    >
                      {(() => {
                        const sourceDisplayName = resolveDatasetDisplayName(source);
                        return (
                          <>
                            <p
                              className="whitespace-normal break-words [overflow-wrap:anywhere] text-sm font-medium leading-6 text-text-primary"
                              title={sourceDisplayName}
                            >
                              {sourceDisplayName}
                            </p>
                            <p className="mt-1 whitespace-normal break-words [overflow-wrap:anywhere] text-xs leading-5 text-text-secondary">
                              {source.sourceName ? `${source.sourceName} · ` : ''}
                              {sourceKindLabel(source.sourceKind)}
                            </p>
                          </>
                        );
                      })()}
                    </div>
                  ))}
                  <div className="rounded-2xl border border-border bg-surface px-4 py-2">
                    <DetailListRow label="匹配字段" values={leftMatchFields} />
                    <DetailListRow label="对比字段" values={leftCompareFields} />
                  </div>
                </div>
              </div>
              <div className="min-w-0 overflow-hidden rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">右侧数据</p>
                <div className="mt-3 min-w-0 space-y-2">
                  {schemeMeta.rightSources.map((source) => (
                    <div
                      key={source.id || source.name}
                      className="min-w-0 overflow-hidden rounded-2xl border border-border bg-surface px-4 py-3"
                    >
                      {(() => {
                        const sourceDisplayName = resolveDatasetDisplayName(source);
                        return (
                          <>
                            <p
                              className="whitespace-normal break-words [overflow-wrap:anywhere] text-sm font-medium leading-6 text-text-primary"
                              title={sourceDisplayName}
                            >
                              {sourceDisplayName}
                            </p>
                            <p className="mt-1 whitespace-normal break-words [overflow-wrap:anywhere] text-xs leading-5 text-text-secondary">
                              {source.sourceName ? `${source.sourceName} · ` : ''}
                              {sourceKindLabel(source.sourceKind)}
                            </p>
                          </>
                        );
                      })()}
                    </div>
                  ))}
                  <div className="rounded-2xl border border-border bg-surface px-4 py-2">
                    <DetailListRow label="匹配字段" values={rightMatchFields} />
                    <DetailListRow label="对比字段" values={rightCompareFields} />
                  </div>
                </div>
              </div>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">数据整理</p>
                <p className="mt-2 text-sm leading-6 text-text-secondary">
                  {schemeMeta.procTrialSummary || '暂无摘要。'}
                </p>
                <p className="mt-2 text-xs text-text-muted">
                  规则：{schemeMeta.procRuleName || scheme.procRuleCode || '--'}
                </p>
              </div>
              <div className="rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">数据对账</p>
                {(schemeMeta.reconRuleName || scheme.reconRuleCode) ? (
                  <p className="mt-2 text-xs text-text-muted">规则：{schemeMeta.reconRuleName || scheme.reconRuleCode}</p>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
            <button
              type="button"
              onClick={() => openCreatePlanModal(scheme)}
              className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100"
            >
              新增运行计划
            </button>
          </div>
        </>
      );
    }

    if (modalState.kind === 'task-detail') {
      const { task } = modalState;
      return (
        <>
          <div className="border-b border-border px-6 py-5">
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">任务详情</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">{task.name}</h3>
          </div>
          <div className="px-6 py-5">
            <div className="divide-y divide-border-subtle">
              <DetailRow label="任务编码" value={task.planCode || '--'} />
              <DetailRow label="对账方案" value={task.schemeName || '--'} />
              <DetailRow label="运行计划" value={formatScheduleLabel(task.scheduleType, task.scheduleExpr)} />
              <DetailRow label="对账周期" value={formatBizDateOffsetLabel(task.bizDateOffset)} />
              <DetailRow label="协作通道" value={resolveChannelProviderLabel(task.channelConfigId)} />
              <DetailRow label="责任人" value={task.ownerSummary || '--'} />
              <DetailRow label="创建时间" value={formatDateTime(task.createdAt)} />
              <DetailRow label="更新时间" value={formatDateTime(task.updatedAt)} />
            </div>
          </div>
        </>
      );
    }

    const { run } = modalState;
    const modalExceptions = exceptionsByRunId[run.id] || [];
    const statusMeta = executionStatusMeta(run.executionStatus);

    return (
      <>
        <div className="border-b border-border px-6 py-5">
          <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">异常看板</p>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-lg font-semibold text-text-primary">{run.planName}</h3>
            <button
              type="button"
              onClick={() => void handleRerunValidation(run.id)}
              disabled={rerunningRunId === run.id}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={cn('h-4 w-4', rerunningRunId === run.id && 'animate-spin')} />
              {rerunningRunId === run.id ? '验证中...' : '重新对账验证'}
            </button>
          </div>
        </div>
        <div className="space-y-5 px-6 py-5">
          {modalError ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              {modalError}
            </div>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">所属方案</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{run.schemeName || '--'}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">运行状态</p>
              <span className={cn('mt-2 inline-flex rounded-full border px-2.5 py-1 text-xs font-medium', statusMeta.className)}>
                {statusMeta.label}
              </span>
            </div>
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">异常数</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{run.anomalyCount}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">开始时间</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(run.startedAt)}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">结束时间</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{formatDateTime(run.finishedAt)}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">失败阶段</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{run.failedStage || '--'}</p>
            </div>
          </div>

          <div className="rounded-3xl border border-border bg-surface-secondary px-4 py-4">
            <p className="text-xs text-text-secondary">失败原因</p>
            <p className="mt-2 text-sm leading-6 text-text-primary">
              {run.failedReason || '本次运行没有失败原因，通常表示执行成功或尚未返回失败明细。'}
            </p>
          </div>

          {loadingExceptionsRunId === run.id ? (
            <div className="flex items-center gap-2 rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm text-text-secondary">
              <RefreshCw className="h-4 w-4 animate-spin" />
              正在加载异常处理记录...
            </div>
          ) : modalExceptions.length > 0 ? (
            <div className="overflow-x-auto rounded-3xl border border-border bg-surface">
              <div className="min-w-[940px]">
                <div className="grid grid-cols-[minmax(0,2.2fr)_140px_120px_120px_170px] gap-6 border-b border-border-subtle px-5 py-3 text-[11px] font-semibold tracking-[0.14em] text-text-muted">
                  <span>异常摘要</span>
                  <span>责任人</span>
                  <span>催办</span>
                  <span>处理进展</span>
                  <span>修复状态</span>
                </div>
                {modalExceptions.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[minmax(0,2.2fr)_140px_120px_120px_170px] items-start gap-6 border-b border-border-subtle px-5 py-4 last:border-b-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text-primary">{item.summary}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className="inline-flex rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700">
                          {formatAnomalyTypeLabel(item.anomalyType)}
                        </span>
                        {buildRunExceptionJoinKeySummary(item).slice(0, 1).map((line) => (
                          <span
                            key={`${item.id}-${line}`}
                            className="inline-flex rounded-full border border-border bg-surface-secondary px-2 py-0.5 text-[11px] text-text-secondary"
                          >
                            {line}
                          </span>
                        ))}
                      </div>
                      <p className="mt-2 text-xs leading-5 text-text-secondary">
                        {buildRunExceptionCompareSummary(item)[0]
                          || item.latestFeedback
                          || '打开详情查看匹配字段、对比字段差异与左右侧原始记录。'}
                      </p>
                      <button
                        type="button"
                        onClick={() => setSelectedExceptionDetail(item)}
                        className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        查看详情
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleRerunValidation(run.id, item.id)}
                        disabled={rerunningRunId === run.id}
                        className="mt-3 ml-2 inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <RefreshCw className={cn('h-3.5 w-3.5', rerunningRunId === run.id && 'animate-spin')} />
                        {rerunningRunId === run.id ? '验证中...' : '重新对账验证'}
                      </button>
                    </div>
                    <span className="text-sm text-text-secondary">{item.ownerName || '--'}</span>
                    <span className="text-sm text-text-secondary">{formatReminderStatusLabel(item.reminderStatus)}</span>
                    <span className="text-sm text-text-secondary">{formatProcessingStatusLabel(item.processingStatus)}</span>
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          'rounded-full border px-2.5 py-1 text-xs font-medium',
                          item.isClosed
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                            : 'border-amber-200 bg-amber-50 text-amber-700',
                        )}
                      >
                        {formatFixStatusLabel(item.fixStatus, item.isClosed)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-3xl border border-border bg-surface-secondary px-4 py-5 text-sm text-text-secondary">
              当前运行暂无异常处理记录。
            </div>
          )}
        </div>
      </>
    );
  };

  const modalMaxWidthClass =
    modalState?.kind === 'create-scheme' ? 'max-w-6xl' : modalState?.kind === 'run-exceptions' ? 'max-w-5xl' : 'max-w-3xl';

  if (mode !== 'center') {
    return <div className="flex h-full min-w-0 flex-1 flex-col bg-surface-secondary">{children}</div>;
  }

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-surface-secondary">
      <ReconWorkspaceHeader activeTab={activeTab} onTabChange={setActiveTab} rightSlot={headerRightSlot} />

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[28px] border border-border bg-surface px-5 py-4 shadow-sm">
            <div>
              <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">对账中心</p>
              <p className="mt-1 text-sm text-text-secondary">
                统一查看对账方案、对账任务与运行记录
              </p>
            </div>
            <div className="flex items-center gap-2">
              {activeTab === 'schemes' ? (
                <button
                  type="button"
                  onClick={openCreateSchemeModal}
                  className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100"
                >
                  <Plus className="h-4 w-4" />
                  新增对账方案
                </button>
              ) : activeTab === 'tasks' ? (
                <button
                  type="button"
                  onClick={() => openCreatePlanModal(null)}
                  disabled={schemes.length === 0}
                  className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Plus className="h-4 w-4" />
                  新增运行计划
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => void loadCenterData()}
                disabled={loadingCenter}
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCw className={cn('h-4 w-4', loadingCenter && 'animate-spin')} />
                刷新
              </button>
            </div>
          </div>

          {centerError ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {centerError}
            </div>
          ) : null}

          {centerNotice ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {centerNotice}
            </div>
          ) : null}

          {loadingCenter ? (
            <div className="flex min-h-[260px] flex-col items-center justify-center rounded-[28px] border border-dashed border-border bg-surface px-6 py-10 text-center">
              <RefreshCw className="h-8 w-8 animate-spin text-text-secondary" />
              <p className="mt-4 text-sm text-text-secondary">正在同步对账中心数据...</p>
            </div>
          ) : activeTab === 'schemes' ? (
            renderSchemeRows()
          ) : activeTab === 'tasks' ? (
            renderTaskRows()
          ) : (
            renderRunRows()
          )}
        </div>
      </div>

      {modalState ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(15,23,42,0.24)] px-4 py-8">
          <div
            className={cn(
              'max-h-[88vh] w-full overflow-hidden rounded-[28px] border border-border bg-surface shadow-[0_24px_80px_rgba(15,23,42,0.22)]',
              modalMaxWidthClass,
            )}
          >
            <div className="flex items-center justify-end border-b border-border px-4 py-3">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-lg p-2 text-text-secondary transition hover:bg-surface-secondary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[calc(88vh-57px)] overflow-y-auto">{renderModalContent()}</div>
          </div>
        </div>
      ) : null}

      {selectedExceptionDetail ? (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[rgba(15,23,42,0.32)] px-4 py-8">
          <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-[28px] border border-border bg-surface shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
            <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">异常详情</p>
                <h3 className="mt-1 text-lg font-semibold text-text-primary">{selectedExceptionDetail.summary}</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedExceptionDetail(null)}
                className="rounded-lg p-2 text-text-secondary transition hover:bg-surface-secondary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              {modalError ? (
                <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                  {modalError}
                </div>
              ) : null}
              {selectedExceptionRecordSections.length > 0 ? (
                <div className={cn('grid gap-5', selectedExceptionRecordSections.length > 1 && 'xl:grid-cols-2')}>
                  {selectedExceptionRecordSections.map((section) => (
                    <div key={`${selectedExceptionDetail.id}-${section.title}`} className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                      <p className="text-sm font-semibold text-text-primary">{section.title}</p>
                      <div className="mt-3 grid gap-3">
                        {Object.entries(section.record)
                          .filter(([key]) => stripRunExceptionFieldPrefix(key) !== 'source_name')
                          .map(([key, value]) => (
                            <div key={`${selectedExceptionDetail.id}-${section.title}-${key}`} className="rounded-2xl border border-border bg-surface px-4 py-3">
                              <p className="text-xs text-text-secondary">{humanizeExceptionFieldName(key)}</p>
                              <p className="mt-1 whitespace-pre-wrap break-all text-sm text-text-primary">
                                {formatDetailValue(value)}
                              </p>
                            </div>
                          ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : Object.keys(selectedExceptionRawRecord).length > 0 ? (
                <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                  <p className="text-sm font-semibold text-text-primary">原始记录</p>
                  <div className="mt-3 grid gap-3">
                    {Object.entries(selectedExceptionRawRecord)
                      .filter(([key]) => stripRunExceptionFieldPrefix(key) !== 'source_name')
                      .map(([key, value]) => (
                        <div key={`${selectedExceptionDetail.id}-field-${key}`} className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <p className="text-xs text-text-secondary">{humanizeExceptionFieldName(key)}</p>
                          <p className="mt-1 whitespace-pre-wrap break-all text-sm text-text-primary">
                            {formatDetailValue(value)}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              ) : (
                <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-5 text-sm text-text-secondary">
                  当前没有返回原始记录。
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-6 py-4">
              {selectedExceptionRun ? (
                <button
                  type="button"
                  onClick={() => void handleRerunValidation(selectedExceptionRun.id, selectedExceptionDetail.id)}
                  disabled={rerunningRunId === selectedExceptionRun.id}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <RefreshCw className={cn('h-4 w-4', rerunningRunId === selectedExceptionRun.id && 'animate-spin')} />
                  {rerunningRunId === selectedExceptionRun.id ? '验证中...' : '重新对账验证'}
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => setSelectedExceptionDetail(null)}
                className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {wizardJsonPanel ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-[rgba(15,23,42,0.24)] px-4 py-8">
          <div className="flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-[28px] border border-border bg-surface shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <p className="text-sm font-semibold text-text-primary">
                {wizardJsonPanel === 'proc' ? '数据整理规则 JSON' : '对账逻辑 JSON'}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleCopyWizardJson(wizardJsonPanel)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition',
                    wizardJsonCopyState?.panel === (wizardJsonPanel === 'proc' ? wizardProcJsonView : wizardReconJsonView)
                      && wizardJsonCopyState.status === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : wizardJsonCopyState?.panel === (wizardJsonPanel === 'proc' ? wizardProcJsonView : wizardReconJsonView)
                        && wizardJsonCopyState.status === 'error'
                      ? 'border-red-200 bg-red-50 text-red-700'
                      : 'border-border bg-surface text-text-primary hover:border-sky-200 hover:text-sky-700',
                  )}
                >
                  {wizardJsonCopyState?.panel === (wizardJsonPanel === 'proc' ? wizardProcJsonView : wizardReconJsonView)
                    && wizardJsonCopyState.status === 'success' ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                  {wizardJsonCopyState?.panel === (wizardJsonPanel === 'proc' ? wizardProcJsonView : wizardReconJsonView)
                    && wizardJsonCopyState.status === 'success'
                    ? '已复制'
                    : wizardJsonCopyState?.panel === (wizardJsonPanel === 'proc' ? wizardProcJsonView : wizardReconJsonView)
                      && wizardJsonCopyState.status === 'error'
                    ? '复制失败'
                    : '复制 JSON'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setWizardJsonPanel(null);
                    setWizardProcJsonView('proc');
                    setWizardReconJsonView('recon');
                    setWizardJsonCopyState(null);
                  }}
                  className="rounded-lg p-2 text-text-secondary transition hover:bg-surface-secondary hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {wizardJsonPanel === 'proc' ? (
                <div className="mb-4 flex flex-wrap gap-2 rounded-2xl border border-border bg-surface-secondary p-2">
                  <button
                    type="button"
                    onClick={() => {
                      setWizardProcJsonView('proc');
                      setWizardJsonCopyState(null);
                    }}
                    className={cn(
                      'rounded-xl px-3 py-2 text-sm font-medium transition',
                      wizardProcJsonView === 'proc'
                        ? 'bg-text-primary text-white'
                        : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
                    )}
                  >
                    Proc JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setWizardProcJsonView('inputPlan');
                      setWizardJsonCopyState(null);
                    }}
                    disabled={!inputPlanJsonPreview}
                    className={cn(
                      'rounded-xl px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60',
                      wizardProcJsonView === 'inputPlan'
                        ? 'bg-text-primary text-white'
                        : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
                    )}
                  >
                    Input Plan JSON
                  </button>
                </div>
              ) : (
                <div className="mb-4 flex flex-wrap gap-2 rounded-2xl border border-border bg-surface-secondary p-2">
                  <button
                    type="button"
                    onClick={() => {
                      setWizardReconJsonView('proc');
                      setWizardJsonCopyState(null);
                    }}
                    disabled={!procJsonPreview}
                    className={cn(
                      'rounded-xl px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60',
                      wizardReconJsonView === 'proc'
                        ? 'bg-text-primary text-white'
                        : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
                    )}
                  >
                    Proc JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setWizardReconJsonView('recon');
                      setWizardJsonCopyState(null);
                    }}
                    className={cn(
                      'rounded-xl px-3 py-2 text-sm font-medium transition',
                      wizardReconJsonView === 'recon'
                        ? 'bg-text-primary text-white'
                        : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
                    )}
                  >
                    Recon JSON
                  </button>
                </div>
              )}
              <pre className="overflow-x-auto rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-xs leading-6 text-text-primary">
                {wizardJsonPanel === 'proc'
                  ? wizardProcJsonView === 'inputPlan'
                    ? inputPlanJsonPreview || '当前还没有生成 input plan json。'
                    : procJsonPreview
                  : wizardReconJsonView === 'proc'
                  ? procJsonPreview || '当前还没有生成 proc json。'
                  : reconJsonPreview}
              </pre>
            </div>
            <div className="flex items-center justify-end border-t border-border px-6 py-4">
              <button
                type="button"
                onClick={() => {
                  setWizardJsonPanel(null);
                  setWizardProcJsonView('proc');
                  setWizardReconJsonView('recon');
                }}
                className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
