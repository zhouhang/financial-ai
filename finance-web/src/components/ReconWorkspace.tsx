import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import { ruleSupportsEntryMode } from '../utils/ruleEntryModes';
import type {
  CollaborationChannelListItem,
  CollaborationProvider,
  DataSourceKind,
  ReconWorkspaceMode,
  UserTaskRule,
} from '../types';
import { consumeReconAutoSse, fetchReconAutoApi } from './recon/autoApi';
import ReconWorkspaceHeader from './recon/ReconWorkspaceHeader';
import SchemeWizardReconStep from './recon/SchemeWizardReconStep';
import SchemeWizardTargetProcStep from './recon/SchemeWizardTargetProcStep';
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

type SchemeWizardStep = 1 | 2 | 3 | 4;
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

interface ExistingConfigOption {
  id: string;
  name: string;
  draftText: string;
  ruleJson?: Record<string, unknown> | null;
  schemeCode?: string;
  ruleCode?: string;
  leftSources?: SchemeSourceDraft[];
  rightSources?: SchemeSourceDraft[];
  matchKey?: string;
  leftAmountField?: string;
  rightAmountField?: string;
  tolerance?: string;
  leftTimeSemantic?: string;
  rightTimeSemantic?: string;
}

interface RuleGenerationProgress {
  skill: string;
  phase: string;
  message: string;
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
  matchKey: string;
  result: 'matched' | 'amount_diff' | 'left_only' | 'right_only';
  leftAmount: number | '--';
  rightAmount: number | '--';
  diffAmount: number | '--';
  note: string;
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
  matchKey: string;
  leftAmountField: string;
  rightAmountField: string;
  tolerance: string;
}

interface SourceFieldProfile {
  keyField: string;
  amountField: string;
  dateField: string;
  labelField?: string;
}

interface PlanDraft {
  schemeCode: string;
  scheduleType: 'daily' | 'weekly' | 'monthly';
  scheduleHour: string;
  scheduleMinute: string;
  scheduleDayOfWeek: string;
  scheduleDayOfMonth: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  channelConfigId: string;
  ownerSummary: string;
}

interface SchemeMetaSummary {
  businessGoal: string;
  leftSources: SchemeSourceDraft[];
  rightSources: SchemeSourceDraft[];
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
  matchKey: string;
  leftAmountField: string;
  rightAmountField: string;
  tolerance: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
}

const SCHEME_LIST_TEMPLATE =
  'minmax(0,1.6fr) minmax(220px,1fr) minmax(220px,1fr) minmax(268px,auto)';
const TASK_LIST_TEMPLATE =
  'minmax(0,2.3fr) minmax(200px,1.1fr) minmax(180px,0.9fr) minmax(120px,0.7fr) minmax(280px,auto)';
const RUN_LIST_TEMPLATE =
  'minmax(0,2.4fr) minmax(190px,1fr) minmax(120px,0.7fr) minmax(120px,0.7fr) minmax(148px,auto)';

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
  match_key: '匹配键',
  result: '对账结果',
  left_amount: '左侧金额',
  right_amount: '右侧金额',
  diff_amount: '差额',
  note: '说明',
};

const SCHEME_WIZARD_STEPS: Array<{ id: SchemeWizardStep; title: string; description: string }> = [
  { id: 1, title: '对账目标', description: '选择左右数据并描述口径' },
  { id: 2, title: '数据整理', description: 'AI 生成整理配置并试跑' },
  { id: 3, title: '对账逻辑', description: 'AI 生成对账逻辑并试跑' },
  { id: 4, title: '保存方案', description: '确认摘要后保存方案' },
];

const EMPTY_SCHEME_DRAFT: SchemeDraft = {
  name: '',
  businessGoal: '',
  leftDescription: '',
  rightDescription: '',
  procConfigMode: 'ai',
  selectedProcConfigId: '',
  procDraft: '',
  procRuleJson: null,
  procTrialStatus: 'idle',
  procTrialSummary: '',
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
  reconRuleJson: null,
  reconTrialStatus: 'idle',
  reconTrialSummary: '',
};

const EMPTY_PLAN_DRAFT: PlanDraft = {
  schemeCode: '',
  scheduleType: 'daily',
  scheduleHour: '09',
  scheduleMinute: '30',
  scheduleDayOfWeek: '1',
  scheduleDayOfMonth: '1',
  leftTimeSemantic: '',
  rightTimeSemantic: '',
  channelConfigId: '',
  ownerSummary: '',
};

function createEmptySchemeDraft(): SchemeDraft {
  return {
    ...EMPTY_SCHEME_DRAFT,
  };
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
  if (normalized === 'left_recon_ready') return '左侧整理结果表';
  if (normalized === 'right_recon_ready') return '右侧整理结果表';
  return normalized || '整理结果表';
}

function humanizeProcDescription(text: string): string {
  return text
    .replaceAll('left_recon_ready', '左侧整理结果表')
    .replaceAll('right_recon_ready', '右侧整理结果表')
    .replaceAll('biz_key', '业务主键')
    .replaceAll('amount', '金额')
    .replaceAll('biz_date', '业务日期')
    .replaceAll('source_name', '来源名称')
    .trim();
}

function humanizeProcRoleDesc(roleDesc: string): string {
  const normalized = humanizeProcDescription(roleDesc);
  if (!normalized) return '数据整理配置说明';
  if (/(规则生成器|draft proc|fallback proc|tally 财务 ai)/i.test(normalized)) {
    return '数据整理配置说明';
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

function summarizeReconDraft(json: Record<string, unknown>): string {
  const ruleName = toText(json.rule_name, '未命名对账逻辑');
  const rules = Array.isArray(json.rules) ? json.rules : [];
  const firstRule = asRecord(rules[0]);
  const recon = asRecord(firstRule.recon);
  const keyColumns = asRecord(recon.key_columns);
  const compareColumns = asRecord(recon.compare_columns);
  const mappings = Array.isArray(keyColumns.mappings) ? keyColumns.mappings : [];
  const columns = Array.isArray(compareColumns.columns) ? compareColumns.columns : [];
  const firstMapping = asRecord(mappings[0]);
  const firstColumn = asRecord(columns[0]);
  const sourceFile = asRecord(firstRule.source_file);
  const targetFile = asRecord(firstRule.target_file);

  return [
    `# ${ruleName}`,
    `输入：${toText(sourceFile.table_name, 'left_recon_ready')} ↔ ${toText(targetFile.table_name, 'right_recon_ready')}`,
    `匹配主键：${toText(firstMapping.source_field, 'biz_key')}`,
    `左金额字段：${toText(firstColumn.source_column, 'amount')}`,
    `右金额字段：${toText(firstColumn.target_column, 'amount')}`,
    `容差：${toText(firstColumn.tolerance, '0')}`,
    '识别方式：按匹配主键对齐左右记录，比较金额差异并输出差异结果。',
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

function canRetryExecutionRun(status: string): boolean {
  const normalized = status.trim().toLowerCase();
  return normalized === 'failed' || normalized === 'error';
}

function formatAnomalyTypeLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'source_only') return '源侧独有';
  if (normalized === 'target_only') return '目标侧独有';
  if (normalized === 'matched_with_diff') return '匹配但字段有差异';
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

function buildRunExceptionReasonLines(item: ReconRunExceptionDetail): string[] {
  const detail = firstNonEmptyRecord(item.raw.detail_json, item.raw.detail, item.raw);
  const compareValues = asList(detail.compare_values).map((entry) => asRecord(entry));
  const anomalyType = item.anomalyType.trim().toLowerCase();

  if (compareValues.length > 0) {
    const lines = compareValues
      .map((entry) => {
        const label = toText(entry.name, '差异字段');
        const sourceField = toText(entry.source_field);
        const targetField = toText(entry.target_field);
        const sourceValue = formatDetailValue(entry.source_value);
        const targetValue = formatDetailValue(entry.target_value);
        const diffValue = formatDetailValue(entry.diff_value);
        return `${label}不一致：源侧${sourceField || '--'}=${sourceValue}，目标侧${targetField || '--'}=${targetValue}，差额=${diffValue}。`;
      })
      .filter(Boolean);
    if (lines.length > 0) return lines;
  }

  if (anomalyType === 'source_only') {
    return ['该记录只出现在源侧数据，目标侧没有找到相同对账键的记录。'];
  }
  if (anomalyType === 'target_only') {
    return ['该记录只出现在目标侧数据，源侧没有找到相同对账键的记录。'];
  }
  if (anomalyType === 'matched_with_diff' || anomalyType === 'value_mismatch' || anomalyType === 'amount_diff') {
    return ['源侧与目标侧已匹配到同一笔记录，但用于核对的字段值不一致。'];
  }

  const latestFeedback = item.latestFeedback.trim();
  if (latestFeedback) {
    return [latestFeedback];
  }
  return ['当前没有更详细的差异原因，建议结合明细数据继续核查。'];
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
    bizDateOffset: toText(raw.biz_date_offset, 'T'),
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
    triggerType: toText(raw.trigger_type),
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

  return {
    businessGoal: toText(schemeMeta.business_goal, item.description),
    leftSources,
    rightSources,
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
    matchKey: toText(schemeMeta.match_key),
    leftAmountField: toText(schemeMeta.left_amount_field),
    rightAmountField: toText(schemeMeta.right_amount_field),
    tolerance: toText(schemeMeta.tolerance),
    leftTimeSemantic: toText(schemeMeta.left_time_semantic, toText(schemeMeta.time_semantic)),
    rightTimeSemantic: toText(schemeMeta.right_time_semantic, toText(schemeMeta.time_semantic)),
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
  snapshotId?: unknown,
): {
  key: string;
  label: string;
  hint?: string;
} {
  const originKey = toText(origin).trim().toLowerCase();
  const resolvedSnapshotId = toText(snapshotId).trim();
  if (originKey === 'published_snapshot') {
    return {
      key: originKey,
      label: '已发布快照',
      hint: resolvedSnapshotId ? `来自真实已发布快照：${resolvedSnapshotId}` : '来自真实已发布快照',
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

function buildRunPlanBinding(
  source: SchemeSourceDraft,
  dateField: string,
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
  if (dateField.trim()) {
    query.date_field = dateField.trim();
  }

  return {
    data_source_id: sourceId,
    table_name: tableName,
    resource_key: tableName,
    dataset_source_type: 'snapshot',
    role_code: `${side}_${index + 1}`,
    side,
    query,
  };
}

function buildRunPlanBindings(
  schemeMeta: SchemeMetaSummary | null,
  leftTimeSemantic: string,
  rightTimeSemantic: string,
): Array<Record<string, unknown>> {
  if (!schemeMeta) return [];
  const bindings = [
    ...schemeMeta.leftSources.map((source, index) => buildRunPlanBinding(source, leftTimeSemantic, 'left', index)),
    ...schemeMeta.rightSources.map((source, index) => buildRunPlanBinding(source, rightTimeSemantic, 'right', index)),
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

function buildPreparedRows(
  sources: SchemeSourceOption[],
  side: 'left' | 'right',
  procDraft: string,
): PreviewTableRow[] {
  const draftSeed = hashText(`${procDraft}-${side}`);
  const prefix = procDraft.includes('退款') ? 'REF' : procDraft.includes('游戏') ? 'GAME' : 'BIZ';
  return Array.from({ length: 3 }, (_, index) => {
    const seq = index + 1;
    return {
      biz_key: `${prefix}-${seq.toString().padStart(3, '0')}`,
      amount: formatPreviewAmount(120 + seq * 18.4 + (draftSeed % 7) * 0.11),
      biz_date: `2026-04-${String(seq + 1).padStart(2, '0')}`,
      source_count: sources.length,
      source_side: side === 'left' ? 'left_recon_ready' : 'right_recon_ready',
      source_hint:
        sources.map((item) => (item.sourceName ? `${item.sourceName}/${item.name}` : item.name)).join(' / ') || '--',
    };
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
  },
): Record<string, unknown> {
  const tableName = options?.tableName || resolveDatasetTableName(source);
  const sampleRows = options?.sampleRows || buildRawSourceRows(source, side, seedText);
  const sourceSchemaSummary = asRecord(source.schemaSummary);
  return {
    side,
    dataset_name: source.name,
    table_name: tableName,
    dataset_code: source.datasetCode,
    source_type: 'dataset',
    source_id: source.sourceId,
    source_key: source.sourceId,
    resource_key: tableName,
    source_kind: source.sourceKind,
    provider_code: source.providerCode,
    description,
    schema_summary:
      options?.schemaSummary
      || (Object.keys(sourceSchemaSummary).length > 0
        ? sourceSchemaSummary
        : inferSchemaSummaryFromRows(sampleRows)),
    sample_rows: sampleRows,
  };
}

function inferSchemaSummaryFromRows(rows: PreviewTableRow[]): Record<string, string> {
  const summary = new Map<string, string>();
  rows.forEach((row) => {
    Object.entries(row).forEach(([key, value]) => {
      if (summary.has(key)) return;
      if (typeof value === 'number') {
        summary.set(key, Number.isInteger(value) ? 'integer' : 'number');
        return;
      }
      if (typeof value === 'string') {
        if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
          summary.set(key, 'date');
        } else if (!Number.isNaN(Number(value)) && value.trim() !== '') {
          summary.set(key, 'number');
        } else {
          summary.set(key, 'string');
        }
        return;
      }
      if (value === null) {
        summary.set(key, 'null');
        return;
      }
      summary.set(key, 'unknown');
    });
  });
  return Object.fromEntries(summary);
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

function extractConfigValue(draft: string, label: string, fallback: string): string {
  const pattern = new RegExp(`${label}[：:]\\s*([^\\n]+)`);
  const match = draft.match(pattern);
  return match?.[1]?.trim() || fallback;
}

function parseReconDraftConfig({
  reconDraft,
  matchKey,
  leftAmountField,
  rightAmountField,
  tolerance,
}: Pick<
  SchemeDraft,
  | 'reconDraft'
  | 'matchKey'
  | 'leftAmountField'
  | 'rightAmountField'
  | 'tolerance'
>): ParsedReconDraftConfig {
  return {
    matchKey: extractConfigValue(reconDraft, '匹配主键', matchKey || 'biz_key'),
    leftAmountField: extractConfigValue(reconDraft, '左金额字段', leftAmountField || 'amount'),
    rightAmountField: extractConfigValue(reconDraft, '右金额字段', rightAmountField || 'amount'),
    tolerance: extractConfigValue(reconDraft, '容差', tolerance || '0.00'),
  };
}

function parseReconRuleJsonConfig(json: Record<string, unknown>): ParsedReconDraftConfig {
  const rules = Array.isArray(json.rules) ? json.rules : [];
  const firstRule = asRecord(rules[0]);
  const recon = asRecord(firstRule.recon);
  const keyColumns = asRecord(recon.key_columns);
  const compareColumns = asRecord(recon.compare_columns);
  const mappings = Array.isArray(keyColumns.mappings) ? keyColumns.mappings : [];
  const columns = Array.isArray(compareColumns.columns) ? compareColumns.columns : [];
  const firstMapping = asRecord(mappings[0]);
  const firstColumn = asRecord(columns[0]);

  return {
    matchKey: toText(firstMapping.source_field, 'biz_key'),
    leftAmountField: toText(firstColumn.source_column, 'amount'),
    rightAmountField: toText(firstColumn.target_column, 'amount'),
    tolerance: toText(firstColumn.tolerance, '0'),
  };
}

function getPreviewRowKey(row: PreviewTableRow, field: string, fallback: string): string {
  const value = row[field];
  if (value === null || value === undefined) {
    return fallback;
  }
  const text = String(value).trim();
  return text || fallback;
}

function sanitizeRuleId(input: string, fallback: string): string {
  const normalized = input
    .trim()
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toUpperCase();
  return normalized || fallback;
}

function buildRuleTimestamp(): string {
  return new Date().toISOString();
}

function getDefaultDateFieldBySourceKind(sourceKind: SupportedSourceKind): string {
  if (sourceKind === 'platform_oauth') return 'biz_date';
  if (sourceKind === 'database') return 'accounting_date';
  return 'happened_at';
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

function buildDateFieldLabel(rawName: string, label: string): string {
  const normalizedLabel = label.trim();
  if (normalizedLabel && normalizedLabel !== rawName) {
    return `${normalizedLabel} (${rawName})`;
  }
  return rawName;
}

function resolveSourceFieldProfile(source: SchemeSourceOption): SourceFieldProfile {
  if (source.sourceKind === 'platform_oauth') {
    return {
      keyField: 'order_no',
      amountField: 'gross_amount',
      dateField: 'biz_date',
      labelField: 'shop_name',
    };
  }
  if (source.sourceKind === 'database') {
    return {
      keyField: 'ledger_id',
      amountField: 'booked_amount',
      dateField: 'accounting_date',
      labelField: 'table_name',
    };
  }
  return {
    keyField: 'request_id',
    amountField: 'amount',
    dateField: 'happened_at',
    labelField: 'endpoint',
  };
}

function inferTimeOptionsFromSources(
  sources: SchemeSourceDraft[],
  fallbackValue = '',
): Array<{ value: string; label: string }> {
  const optionMap = new Map<string, { value: string; label: string; score: number }>();
  sources.forEach((source) => {
    const fieldLabelMap = normalizeFieldLabelMap(source.fieldLabelMap) || {};
    const rawNames = Array.from(
      new Set<string>([
        ...extractSchemaFieldNames(source.schemaSummary),
        ...Object.keys(fieldLabelMap),
      ]),
    );
    rawNames.forEach((rawName) => {
      const normalizedRawName = rawName.trim();
      if (!normalizedRawName) return;
      const label = toText(fieldLabelMap[normalizedRawName], normalizedRawName);
      const score = scoreDateFieldCandidate(normalizedRawName, label);
      if (score <= 0) return;
      const current = optionMap.get(normalizedRawName);
      if (!current || score > current.score) {
        optionMap.set(normalizedRawName, {
          value: normalizedRawName,
          label: buildDateFieldLabel(normalizedRawName, label),
          score,
        });
      }
    });
  });
  if (optionMap.size === 0) {
    sources.forEach((source) => {
      const field = getDefaultDateFieldBySourceKind(source.sourceKind || 'platform_oauth');
      if (!field || optionMap.has(field)) return;
      optionMap.set(field, { value: field, label: field, score: 1 });
    });
  }
  if (fallbackValue.trim() && !optionMap.has(fallbackValue.trim())) {
    optionMap.set(fallbackValue.trim(), {
      value: fallbackValue.trim(),
      label: fallbackValue.trim(),
      score: 999,
    });
  }
  return Array.from(optionMap.values())
    .sort((left, right) => right.score - left.score || left.label.localeCompare(right.label, 'zh-CN'))
    .map(({ value, label }) => ({ value, label }));
}

function buildProcSourceAlias(side: 'left' | 'right', index: number): string {
  return `${side}_source_${index + 1}`;
}

function buildProcJsonPayload(
  draft: SchemeDraft,
  leftSources: SchemeSourceOption[],
  rightSources: SchemeSourceOption[],
): Record<string, unknown> {
  const timestamp = buildRuleTimestamp();
  const roleDesc = draft.name.trim() || draft.businessGoal.trim() || '未命名数据整理配置';
  const buildCreateSchemaStep = (targetTable: string, stepId: string) => ({
    step_id: stepId,
    action: 'create_schema',
    target_table: targetTable,
    description: `创建 ${targetTable} 标准化输出结构`,
    schema: {
      columns: [
        { name: 'biz_key', data_type: 'string', nullable: false },
        { name: 'amount', data_type: 'decimal', precision: 18, scale: 2, default: 0 },
        { name: 'biz_date', data_type: 'date', nullable: true },
        { name: 'source_name', data_type: 'string', nullable: true },
      ],
      primary_key: ['biz_key'],
      export_enabled: true,
    },
  });

  const buildWriteDatasetStep = (
    side: 'left' | 'right',
    targetTable: string,
    dependsOn: string,
    sources: SchemeSourceOption[],
  ) => ({
    step_id: `${side}_write_recon_ready`,
    action: 'write_dataset',
    target_table: targetTable,
    depends_on: [dependsOn],
    description: `${side === 'left' ? '左侧' : '右侧'}原始数据标准化到 ${targetTable}`,
    row_write_mode: 'upsert',
    sources: sources.map((source, index) => ({
      alias: buildProcSourceAlias(side, index),
      table: source.resourceKey || source.datasetCode || source.name,
    })),
    match: {
      sources: sources.map((source, index) => {
        const profile = resolveSourceFieldProfile(source);
        return {
          alias: buildProcSourceAlias(side, index),
          keys: [{ field: profile.keyField, target_field: 'biz_key' }],
        };
      }),
    },
    mappings: sources.flatMap((source, index) => {
      const alias = buildProcSourceAlias(side, index);
      const profile = resolveSourceFieldProfile(source);
      const mappings: Array<Record<string, unknown>> = [
        {
          target_field: 'amount',
          value: {
            type: 'source',
            source: { alias, field: profile.amountField },
          },
          field_write_mode: 'overwrite',
        },
        {
          target_field: 'biz_date',
          value: {
            type: 'source',
            source: { alias, field: profile.dateField },
          },
          field_write_mode: 'overwrite',
        },
      ];
      if (profile.labelField) {
        mappings.push({
          target_field: 'source_name',
          value: {
            type: 'source',
            source: { alias, field: profile.labelField },
          },
          field_write_mode: 'overwrite',
        });
      }
      return mappings;
    }),
  });

  return {
    role_desc: roleDesc,
    version: '4.5',
    metadata: {
      created_at: timestamp,
      author: 'finance-web',
      tags: ['数据整理', '对账方案'],
    },
    global_config: {
      default_round_precision: 2,
      date_format: 'YYYY-MM-DD',
      null_value_handling: 'keep',
      error_handling: 'stop',
    },
    file_rule_code: '',
    dsl_constraints: {
      actions: ['create_schema', 'write_dataset'],
      builtin_functions: ['earliest_date', 'current_date', 'month_of'],
      aggregate_operators: ['sum', 'min'],
      field_write_modes: ['overwrite', 'increment'],
      row_write_modes: ['insert_if_missing', 'update_only', 'upsert'],
      column_data_types: ['string', 'date', 'decimal'],
      value_node_types: ['source', 'formula', 'template_source', 'function', 'context'],
      merge_strategies: ['union_distinct'],
      loop_context_vars: ['month', 'prev_month', 'is_first_month'],
    },
    steps: [
      buildCreateSchemaStep('left_recon_ready', 'create_left_recon_ready'),
      buildWriteDatasetStep('left', 'left_recon_ready', 'create_left_recon_ready', leftSources),
      buildCreateSchemaStep('right_recon_ready', 'create_right_recon_ready'),
      buildWriteDatasetStep('right', 'right_recon_ready', 'create_right_recon_ready', rightSources),
    ],
  };
}

function buildReconJsonPayload(
  draft: SchemeDraft,
  config: ParsedReconDraftConfig = parseReconDraftConfig(draft),
): Record<string, unknown> {
  const ruleName = buildDefaultReconRuleName(draft.name);
  const tolerance = Number(config.tolerance);
  const toleranceValue = Number.isFinite(tolerance) ? tolerance : 0;
  return {
    rule_id: sanitizeRuleId(ruleName, 'DRAFT_RECON_RULE'),
    rule_name: ruleName,
    description: draft.businessGoal || '数据对账逻辑',
    file_rule_code: '',
    schema_version: '1.6',
    rules: [
      {
        enabled: true,
        source_file: {
          table_name: 'left_recon_ready',
          description: '左侧整理输出。',
          identification: {
            match_by: 'table_name',
            match_value: 'left_recon_ready',
            match_strategy: 'exact',
          },
        },
        target_file: {
          table_name: 'right_recon_ready',
          description: '右侧整理输出。',
          identification: {
            match_by: 'table_name',
            match_value: 'right_recon_ready',
            match_strategy: 'exact',
          },
        },
        recon: {
          key_columns: {
            mappings: [
              {
                source_field: config.matchKey,
                target_field: config.matchKey,
              },
            ],
            match_type: 'exact',
            transformations: {
              source: {},
              target: {},
            },
          },
          compare_columns: {
            columns: [
              {
                name: '金额差异',
                compare_type: 'numeric',
                source_column: config.leftAmountField,
                target_column: config.rightAmountField,
                tolerance: toleranceValue,
              },
            ],
          },
          aggregation: {
            enabled: false,
            group_by: [],
            aggregations: [],
          },
        },
        output: {
          format: 'xlsx',
          file_name_template: '{rule_name}_核对结果_{timestamp}',
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
  availableRules = [],
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
  const [selectedLeftSources, setSelectedLeftSources] = useState<SchemeSourceOption[]>([]);
  const [selectedRightSources, setSelectedRightSources] = useState<SchemeSourceOption[]>([]);
  const [availableChannels, setAvailableChannels] = useState<CollaborationChannelListItem[]>([]);
  const [availableProcRules, setAvailableProcRules] = useState<UserTaskRule[]>([]);
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
  const [schemeDraft, setSchemeDraft] = useState<SchemeDraft>(() => createEmptySchemeDraft());
  const [designSessionId, setDesignSessionId] = useState('');
  const [planDraft, setPlanDraft] = useState<PlanDraft>(EMPTY_PLAN_DRAFT);
  const [modalError, setModalError] = useState<string | null>(null);
  const [isSubmittingScheme, setIsSubmittingScheme] = useState(false);
  const [isSubmittingPlan, setIsSubmittingPlan] = useState(false);
  const [isGeneratingProc, setIsGeneratingProc] = useState(false);
  const [isTrialingProc, setIsTrialingProc] = useState(false);
  const [isGeneratingRecon, setIsGeneratingRecon] = useState(false);
  const [isTrialingRecon, setIsTrialingRecon] = useState(false);
  const [procGenerationProgress, setProcGenerationProgress] = useState<RuleGenerationProgress | null>(null);
  const [reconGenerationProgress, setReconGenerationProgress] = useState<RuleGenerationProgress | null>(null);
  const [wizardJsonPanel, setWizardJsonPanel] = useState<'proc' | 'recon' | null>(null);
  const [procTrialPreview, setProcTrialPreview] = useState<ProcTrialPreview | null>(null);
  const [reconTrialPreview, setReconTrialPreview] = useState<ReconTrialPreview | null>(null);
  const [procCompatibility, setProcCompatibility] = useState<CompatibilityCheckResult>(emptyCompatibilityResult);
  const [reconCompatibility, setReconCompatibility] = useState<CompatibilityCheckResult>(emptyCompatibilityResult);
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null);
  const [selectedExceptionDetail, setSelectedExceptionDetail] = useState<ReconRunExceptionDetail | null>(null);
  const [wizardJsonCopyState, setWizardJsonCopyState] = useState<{
    panel: 'proc' | 'recon';
    status: 'success' | 'error';
  } | null>(null);
  const taskRowRefs = useRef<Record<string, HTMLDivElement | null>>({});

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
  const planLeftTimeOptions = useMemo(
    () =>
      inferTimeOptionsFromSources(
        selectedPlanSchemeMeta?.leftSources || [],
        selectedPlanSchemeMeta?.leftTimeSemantic || '',
      ),
    [selectedPlanSchemeMeta],
  );
  const planRightTimeOptions = useMemo(
    () =>
      inferTimeOptionsFromSources(
        selectedPlanSchemeMeta?.rightSources || [],
        selectedPlanSchemeMeta?.rightTimeSemantic || '',
      ),
    [selectedPlanSchemeMeta],
  );

  const existingProcOptions = useMemo<ExistingConfigOption[]>(() => {
    const options: ExistingConfigOption[] = [];
    const seen = new Set<string>();

    availableProcRules
      .forEach((rule) => {
        const id = `rule:${rule.rule_code}`;
        if (seen.has(id)) return;
        seen.add(id);
        options.push({
          id,
          name: rule.name,
          draftText: '',
          ruleJson: null,
          ruleCode: rule.rule_code,
        });
      });

    // From existing schemes
    schemes.forEach((scheme) => {
      const meta = extractSchemeMeta(scheme);
      const draftText = meta.procDraftText.trim();
      const schemeMeta = firstNonEmptyRecord(scheme.raw.scheme_meta_json, scheme.raw.scheme_meta, scheme.raw.meta);
      const procRuleJson = asRecord(schemeMeta.proc_rule_json);
      if (!draftText && !scheme.procRuleCode) return;
      const id = `scheme:${scheme.schemeCode || scheme.id}:proc`;
      if (seen.has(id)) return;
      seen.add(id);
options.push({
          id,
          name: `${scheme.name} 整理规则`,
          draftText,
          ruleJson: Object.keys(procRuleJson).length > 0 ? procRuleJson : null,
          schemeCode: scheme.schemeCode,
          ruleCode: scheme.procRuleCode || toText(scheme.raw.proc_rule_code),
          leftSources: meta.leftSources,
          rightSources: meta.rightSources,
        });
    });
    return options;
  }, [availableProcRules, schemes]);
  const existingReconOptions = useMemo<ExistingConfigOption[]>(() => {
    const options: ExistingConfigOption[] = [];
    const seen = new Set<string>();

    availableRules
      .filter((rule) => rule.task_type === 'recon' && ruleSupportsEntryMode(rule, 'dataset'))
      .forEach((rule) => {
        const id = `rule:${rule.rule_code}`;
        if (seen.has(id)) return;
        seen.add(id);
        options.push({
          id,
          name: rule.name,
          draftText: '',
          ruleJson: null,
          ruleCode: rule.rule_code,
        });
      });

    schemes.forEach((scheme) => {
      const meta = extractSchemeMeta(scheme);
      const draftText = meta.reconDraftText.trim();
      const schemeMeta = firstNonEmptyRecord(scheme.raw.scheme_meta_json, scheme.raw.scheme_meta, scheme.raw.meta);
      const reconRuleJson = asRecord(schemeMeta.recon_rule_json);
      if (!draftText && !scheme.reconRuleCode) return;
      const id = `scheme:${scheme.schemeCode || scheme.id}:recon`;
      if (seen.has(id)) return;
      seen.add(id);
      options.push({
        id,
        name: meta.reconRuleName || `${scheme.name} 对账逻辑`,
        draftText,
        ruleJson: Object.keys(reconRuleJson).length > 0 ? reconRuleJson : null,
        schemeCode: scheme.schemeCode,
        ruleCode: scheme.reconRuleCode || toText(scheme.raw.recon_rule_code),
        leftSources: meta.leftSources,
        rightSources: meta.rightSources,
        matchKey: meta.matchKey,
        leftAmountField: meta.leftAmountField,
        rightAmountField: meta.rightAmountField,
        tolerance: meta.tolerance,
        leftTimeSemantic: meta.leftTimeSemantic,
        rightTimeSemantic: meta.rightTimeSemantic,
      });
    });
    return options;
  }, [availableRules, schemes]);
  const selectedProcOption = useMemo(
    () => existingProcOptions.find((item) => item.id === schemeDraft.selectedProcConfigId) || null,
    [existingProcOptions, schemeDraft.selectedProcConfigId],
  );
  const selectedReconOption = useMemo(
    () => existingReconOptions.find((item) => item.id === schemeDraft.selectedReconConfigId) || null,
    [existingReconOptions, schemeDraft.selectedReconConfigId],
  );
  const procJsonPreview = useMemo(
    () => (schemeDraft.procRuleJson ? JSON.stringify(schemeDraft.procRuleJson, null, 2) : ''),
    [schemeDraft.procRuleJson],
  );
  const parsedReconConfig = useMemo(
    () =>
      parseReconDraftConfig({
        reconDraft: schemeDraft.reconDraft,
        matchKey: schemeDraft.matchKey,
        leftAmountField: schemeDraft.leftAmountField,
        rightAmountField: schemeDraft.rightAmountField,
        tolerance: schemeDraft.tolerance,
      }),
    [
      schemeDraft.leftAmountField,
      schemeDraft.matchKey,
      schemeDraft.reconDraft,
      schemeDraft.rightAmountField,
      schemeDraft.tolerance,
    ],
  );
  const reconJsonPreview = useMemo(
    () => (schemeDraft.reconRuleJson ? JSON.stringify(schemeDraft.reconRuleJson, null, 2) : ''),
    [schemeDraft.reconRuleJson],
  );
  const preparedLeftRows = useMemo(
    () => procTrialPreview?.preparedOutputs.find((item) => item.side === 'left')?.rows || [],
    [procTrialPreview],
  );
  const preparedRightRows = useMemo(
    () => procTrialPreview?.preparedOutputs.find((item) => item.side === 'right')?.rows || [],
    [procTrialPreview],
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

  const loadProcRuleOptions = useCallback(async () => {
    if (!authToken) {
      setAvailableProcRules([]);
      return;
    }

    try {
      const response = await fetch('/api/proc/list_user_tasks', {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.success === false) {
        throw new Error(String(data?.detail || data?.message || '加载数据整理规则失败'));
      }

      const nextRules = asList(data?.tasks).flatMap((task) => {
        const taskValue = asRecord(task);
        const taskType = toText(taskValue.task_type);
        if (taskType !== 'proc') return [];
        return asList(taskValue.rules).flatMap((rule) => {
          const ruleValue = asRecord(rule);
          const ruleCode = toText(ruleValue.rule_code).trim();
          if (!ruleCode) return [];
          return [
            {
              id: toInt(ruleValue.id, 0),
              user_id: toText(ruleValue.user_id) || null,
              task_id: ruleValue.task_id == null ? null : toInt(ruleValue.task_id, 0),
              rule_code: ruleCode,
              name: toText(ruleValue.name, ruleCode),
              rule_type: toText(ruleValue.rule_type),
              remark: toText(ruleValue.remark),
              task_code: toText(ruleValue.task_code),
              task_name: toText(ruleValue.task_name),
              task_type: 'proc',
              file_rule_code: toText(ruleValue.file_rule_code),
            } satisfies UserTaskRule,
          ];
        });
      });

      setAvailableProcRules(nextRules.filter((rule) => ruleSupportsEntryMode(rule, 'dataset')));
    } catch {
      setAvailableProcRules([]);
    }
  }, [authToken]);

  useEffect(() => {
    if (mode !== 'center') return;
    void loadCenterData();
    void loadChannelOptions();
    void loadProcRuleOptions();
  }, [loadCenterData, loadChannelOptions, loadProcRuleOptions, mode]);

  useEffect(() => {
    if (modalState?.kind !== 'run-exceptions') return;
    const runId = modalState.run.id;
    if (exceptionsByRunId[runId]) return;
    void loadRunExceptions(runId);
  }, [exceptionsByRunId, loadRunExceptions, modalState]);

  const resetSchemeWizard = useCallback(() => {
    setSchemeWizardStep(1);
    setSchemeDraft(createEmptySchemeDraft());
    setSelectedLeftSources([]);
    setSelectedRightSources([]);
    setDesignSessionId('');
    setWizardJsonPanel(null);
    setProcTrialPreview(null);
    setReconTrialPreview(null);
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, []);

  const openCreateSchemeModal = useCallback(() => {
    setModalError(null);
    resetSchemeWizard();
    setModalState({ kind: 'create-scheme' });
    void loadProcRuleOptions();
  }, [loadProcRuleOptions, resetSchemeWizard]);

  const openCreatePlanModal = useCallback(
    (scheme: ReconSchemeListItem | null = null) => {
      setModalError(null);
      const resolvedScheme = scheme || schemes[0] || null;
      const resolvedSchemeMeta = resolvedScheme ? extractSchemeMeta(resolvedScheme) : null;
      const leftTimeOptions = inferTimeOptionsFromSources(
        resolvedSchemeMeta?.leftSources || [],
        resolvedSchemeMeta?.leftTimeSemantic || '',
      );
      const rightTimeOptions = inferTimeOptionsFromSources(
        resolvedSchemeMeta?.rightSources || [],
        resolvedSchemeMeta?.rightTimeSemantic || '',
      );
      setPlanDraft({
        ...EMPTY_PLAN_DRAFT,
        schemeCode: resolvedScheme?.schemeCode || '',
        leftTimeSemantic: resolvedSchemeMeta?.leftTimeSemantic || leftTimeOptions[0]?.value || '',
        rightTimeSemantic: resolvedSchemeMeta?.rightTimeSemantic || rightTimeOptions[0]?.value || '',
      });
      setModalState({ kind: 'create-plan', scheme: resolvedScheme });
      void loadChannelOptions();
    },
    [loadChannelOptions, schemes],
  );

  const closeModal = useCallback(() => {
    setModalError(null);
    setWizardJsonPanel(null);
    setWizardJsonCopyState(null);
    setSelectedExceptionDetail(null);
    setModalState(null);
    setDesignSessionId('');
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, []);

  const handleCopyWizardJson = useCallback(async (panel: 'proc' | 'recon') => {
    const jsonText = panel === 'proc' ? procJsonPreview : reconJsonPreview;
    if (!jsonText.trim()) {
      setWizardJsonCopyState({ panel, status: 'error' });
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
      setWizardJsonCopyState({ panel, status: 'success' });
    } catch {
      setWizardJsonCopyState({ panel, status: 'error' });
    }

    window.setTimeout(() => {
      setWizardJsonCopyState((prev) => (prev?.panel === panel ? null : prev));
    }, 1800);
  }, [procJsonPreview, reconJsonPreview]);

  const resetSchemeDraftFromGoalChange = useCallback(
    (patch: Partial<SchemeDraft>) => {
      setSchemeDraft((prev) => ({
        ...prev,
        ...patch,
        procDraft: '',
        procRuleJson: null,
        procTrialStatus: 'idle',
        procTrialSummary: '',
        matchKey: '',
        leftAmountField: '',
        rightAmountField: '',
        tolerance: '',
        leftTimeSemantic: '',
        rightTimeSemantic: '',
        reconDraft: '',
        reconRuleJson: null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setDesignSessionId('');
      setWizardJsonPanel(null);
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setProcCompatibility(emptyCompatibilityResult());
      setReconCompatibility(emptyCompatibilityResult());
    },
    [],
  );

  const changeSchemeSources = useCallback((side: 'left' | 'right', sources: SchemeSourceOption[]) => {
    const current = side === 'left' ? selectedLeftSources : selectedRightSources;
    const currentIds = current.map((item) => item.id);
    const nextIds = sources.map((item) => item.id);
    if (sameStringSet(currentIds, nextIds)) {
      return;
    }

    if (side === 'left') {
      setSelectedLeftSources(sources);
    } else {
      setSelectedRightSources(sources);
    }

    setSchemeDraft((prev) => ({
      ...prev,
      procDraft: '',
      procRuleJson: null,
      procTrialStatus: 'idle',
      procTrialSummary: '',
      matchKey: '',
      leftAmountField: '',
      rightAmountField: '',
      tolerance: '',
      leftTimeSemantic: '',
      rightTimeSemantic: '',
      reconDraft: '',
      reconRuleJson: null,
      reconTrialStatus: 'idle',
      reconTrialSummary: '',
    }));
    setDesignSessionId('');
    setWizardJsonPanel(null);
    setProcTrialPreview(null);
    setReconTrialPreview(null);
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, [selectedLeftSources, selectedRightSources]);

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
      const nextLeft =
        prev.leftTimeSemantic && planLeftTimeOptions.some((option) => option.value === prev.leftTimeSemantic)
          ? prev.leftTimeSemantic
          : planLeftTimeOptions[0]?.value || '';
      const nextRight =
        prev.rightTimeSemantic && planRightTimeOptions.some((option) => option.value === prev.rightTimeSemantic)
          ? prev.rightTimeSemantic
          : planRightTimeOptions[0]?.value || '';
      if (nextLeft === prev.leftTimeSemantic && nextRight === prev.rightTimeSemantic) {
        return prev;
      }
      return {
        ...prev,
        leftTimeSemantic: nextLeft,
        rightTimeSemantic: nextRight,
      };
    });
  }, [modalState, planLeftTimeOptions, planRightTimeOptions]);

  const loadRuleJsonByCode = useCallback(
    async (ruleCode: string) => {
      const normalizedRuleCode = ruleCode.trim();
      if (!normalizedRuleCode) return null;
      const response = await fetch(
        `/api/proc/get_proc_rule?rule_code=${encodeURIComponent(normalizedRuleCode)}`,
        {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.success === false) {
        throw new Error(String(data?.detail || data?.message || '加载规则详情失败'));
      }
      const ruleRecord = asRecord(data?.data);
      const ruleJson = asRecord(ruleRecord.rule);
      return Object.keys(ruleJson).length > 0 ? ruleJson : null;
    },
    [authToken],
  );

  const buildTargetSampleDatasets = useCallback(
    (seedText = '') => [
      ...selectedLeftSources.map((item) =>
        buildDatasetSamplePayload(item, 'left', schemeDraft.leftDescription.trim(), seedText || schemeDraft.procDraft.trim()),
      ),
      ...selectedRightSources.map((item) =>
        buildDatasetSamplePayload(item, 'right', schemeDraft.rightDescription.trim(), seedText || schemeDraft.procDraft.trim()),
      ),
    ],
    [
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

  const consumeRuleGenerationStream = useCallback(
    async (
      sessionId: string,
      stage: 'proc' | 'recon',
      instructionText: string,
    ): Promise<Record<string, unknown>> => {
      let finalSession: Record<string, unknown> | null = null;

      const response = await consumeReconAutoSse(
        `/schemes/design/${encodeURIComponent(sessionId)}/${stage}/generate/stream`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            instruction_text: instructionText,
          }),
        },
        (event) => {
          const payload = asRecord(event.data);
          const progress = {
            skill: toText(payload.skill, stage === 'proc' ? '整理配置生成器' : '对账逻辑生成器'),
            phase: toText(payload.phase, 'generating_rule'),
            message: toText(
              payload.message,
              stage === 'proc'
                ? '正在生成数据整理 JSON'
                : '正在生成数据对账 JSON',
            ),
          };

          if (stage === 'proc') {
            setProcGenerationProgress(progress);
          } else {
            setReconGenerationProgress(progress);
          }

          if (event.event === 'error') {
            throw new Error(
              toText(
                payload.message,
                stage === 'proc' ? 'AI 生成整理配置失败' : 'AI 生成对账逻辑失败',
              ),
            );
          }
          if (event.event === 'completed') {
            finalSession = asRecord(payload.session);
          }
        },
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          String(
            data.detail
            || data.message
            || (stage === 'proc' ? 'AI 生成整理配置失败' : 'AI 生成对账逻辑失败'),
          ),
        );
      }
      if (!finalSession) {
        throw new Error(stage === 'proc' ? 'AI 生成整理配置未返回完成结果' : 'AI 生成对账逻辑未返回完成结果');
      }
      return finalSession;
    },
    [authToken],
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

  const buildProcPreviewFromTrial = useCallback((trialResult: unknown): ProcTrialPreview | null => {
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
        const snapshotId = toText(item.snapshot_id);
        const originMeta = resolveSampleOriginMeta(item.sample_origin, snapshotId);
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
          snapshotId: snapshotId || undefined,
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
  }, []);

  const buildReconPreviewFromTrial = useCallback((trialResult: unknown): ReconTrialPreview | null => {
    const raw = asRecord(trialResult);
    if (Object.keys(raw).length === 0) return null;
    const resultSamples = asRecord(raw.result_samples);
    const matchedWithDiff = toPreviewTableRows(resultSamples.matched_with_diff);
    const sourceOnly = toPreviewTableRows(resultSamples.source_only);
    const targetOnly = toPreviewTableRows(resultSamples.target_only);
    const resolvePreviewNumber = (row: PreviewTableRow, keys: string[]): number | '--' => {
      for (const key of keys) {
        const value = row[key];
        if (typeof value === 'number') return value;
        const parsed = Number(value);
        if (value !== null && value !== undefined && Number.isFinite(parsed)) {
          return parsed;
        }
      }
      return '--';
    };
    const resolveMatchKey = (row: PreviewTableRow): string =>
      toText(
        row.source_biz_key,
        toText(row.target_biz_key, toText(row.biz_key, toText(row.match_key, '--'))),
      );
    const rows: ReconResultRow[] = [
      ...matchedWithDiff.map((item) => ({
        matchKey: resolveMatchKey(item),
        result: 'amount_diff' as const,
        leftAmount: resolvePreviewNumber(item, ['source_amount', 'left_amount', 'amount']),
        rightAmount: resolvePreviewNumber(item, ['target_amount', 'right_amount']),
        diffAmount: resolvePreviewNumber(item, ['diff_amount', '金额差异']),
        note: '金额差异',
      })),
      ...sourceOnly.map((item) => ({
        matchKey: resolveMatchKey(item),
        result: 'left_only' as const,
        leftAmount: resolvePreviewNumber(item, ['source_amount', 'left_amount', 'amount']),
        rightAmount: '--' as const,
        diffAmount: '--' as const,
        note: '左侧独有',
      })),
      ...targetOnly.map((item) => ({
        matchKey: resolveMatchKey(item),
        result: 'right_only' as const,
        leftAmount: '--' as const,
        rightAmount: resolvePreviewNumber(item, ['target_amount', 'right_amount', 'amount']),
        diffAmount: '--' as const,
        note: '右侧独有',
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
      || RECON_RESULT_FIELD_LABEL_MAP;
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
  }, []);

  const evaluateSourceCompatibility = useCallback(
    (
      label: string,
      currentSources: SchemeSourceOption[],
      expectedSources?: SchemeSourceDraft[],
    ): CompatibilityCheckResult => {
      if (currentSources.length === 0) {
        return {
          status: 'failed',
          message: `${label}还未选择数据集。`,
          details: [],
        };
      }
      if (!expectedSources || expectedSources.length === 0) {
        return {
          status: 'passed',
          message: `${label}缺少历史绑定信息，已按当前所选数据集做弱校验。`,
          details: [`当前选择 ${currentSources.length} 个数据集`],
        };
      }

      const currentIds = currentSources.map((item) => item.id);
      const expectedIds = expectedSources.map((item) => item.id);
      if (sameStringSet(currentIds, expectedIds)) {
        return {
          status: 'passed',
          message: `${label}数据集与历史配置一致。`,
          details: expectedSources.map((item) => resolveDatasetDisplayName(item)),
        };
      }

      const currentKinds = currentSources
        .map((item) => item.sourceKind)
        .sort()
        .join('|');
      const expectedKinds = expectedSources
        .map((item) => item.sourceKind)
        .sort()
        .join('|');
      if (currentSources.length === expectedSources.length && currentKinds === expectedKinds) {
        return {
          status: 'passed',
          message: `${label}数据集发生变化，但数据源类型结构一致，允许继续试跑。`,
          details: [
            `当前：${currentSources.map((item) => resolveDatasetDisplayName(item)).join('、')}`,
            `历史：${expectedSources.map((item) => resolveDatasetDisplayName(item)).join('、')}`,
          ],
        };
      }

      return {
        status: 'failed',
        message: `${label}数据集与历史配置差异较大，请更换配置或重新生成。`,
        details: [
          `当前：${currentSources.map((item) => resolveDatasetDisplayName(item)).join('、') || '--'}`,
          `历史：${expectedSources.map((item) => resolveDatasetDisplayName(item)).join('、') || '--'}`,
        ],
      };
    },
    [],
  );

  const evaluateProcDraftState = useCallback(() => {
    const details: string[] = [];
    let failed = false;
    const draftText =
      schemeDraft.procDraft.trim()
      || selectedProcOption?.draftText?.trim()
      || (selectedProcOption?.ruleJson ? summarizeProcDraft(selectedProcOption.ruleJson) : '');
    const ruleJson =
      schemeDraft.procRuleJson
      || selectedProcOption?.ruleJson
      || (draftText ? buildProcJsonPayload(schemeDraft, selectedLeftSources, selectedRightSources) : null);
    const leftCheck = evaluateSourceCompatibility('左侧', selectedLeftSources, selectedProcOption?.leftSources);
    const rightCheck = evaluateSourceCompatibility('右侧', selectedRightSources, selectedProcOption?.rightSources);

    details.push(leftCheck.message, ...leftCheck.details, rightCheck.message, ...rightCheck.details);
    failed = leftCheck.status === 'failed' || rightCheck.status === 'failed';

    if (!draftText && !ruleJson) {
      failed = true;
      details.push('当前没有可试跑的数据整理配置内容。');
    }

    const targetTables = new Set(
      (Array.isArray(ruleJson?.steps) ? ruleJson.steps : [])
        .map((step) => toText(asRecord(step).target_table))
        .filter(Boolean),
    );
    const hasOutputHint =
      (targetTables.has('left_recon_ready') && targetTables.has('right_recon_ready'))
      || draftText.includes('left_recon_ready')
      || draftText.includes('right_recon_ready')
      || draftText.includes('target_table');
    if (!hasOutputHint) {
      failed = true;
      details.push('整理配置缺少 left_recon_ready / right_recon_ready 输出标识。');
    }

    const seedText = draftText || JSON.stringify(ruleJson || {}, null, 2) || schemeDraft.name || 'proc';
    const sampleOriginMeta = resolveSampleOriginMeta('sample_rows');
    const preview: ProcTrialPreview = {
      status: failed ? 'needs_adjustment' : 'passed',
      summary: failed
        ? '试跑结果：当前整理配置与所选数据集仍不兼容，请调整后重试。'
        : '试跑结果：左右两侧已生成可对账数据集，关键字段校验通过，可进入对账逻辑配置。',
      rawSources: [
        ...selectedLeftSources.map((source) => ({
          sourceId: source.id,
          sourceName: resolveDatasetDisplayName(source),
          side: 'left' as const,
          fieldLabelMap: resolveSourceFieldLabelMap(source),
          sampleOrigin: sampleOriginMeta.key,
          sampleOriginLabel: sampleOriginMeta.label,
          sampleOriginHint: sampleOriginMeta.hint,
          rows: buildRawSourceRows(source, 'left', seedText),
        })),
        ...selectedRightSources.map((source) => ({
          sourceId: source.id,
          sourceName: resolveDatasetDisplayName(source),
          side: 'right' as const,
          fieldLabelMap: resolveSourceFieldLabelMap(source),
          sampleOrigin: sampleOriginMeta.key,
          sampleOriginLabel: sampleOriginMeta.label,
          sampleOriginHint: sampleOriginMeta.hint,
          rows: buildRawSourceRows(source, 'right', seedText),
        })),
      ],
      preparedOutputs: failed
        ? []
        : [
            {
              side: 'left',
              title: 'left_recon_ready',
              fieldLabelMap: PREPARED_OUTPUT_FIELD_LABEL_MAP,
              rows: buildPreparedRows(selectedLeftSources, 'left', seedText),
            },
            {
              side: 'right',
              title: 'right_recon_ready',
              fieldLabelMap: PREPARED_OUTPUT_FIELD_LABEL_MAP,
              rows: buildPreparedRows(selectedRightSources, 'right', seedText),
            },
          ],
      validations: failed
        ? details
        : ['已生成 left_recon_ready', '已生成 right_recon_ready', '金额与业务日期字段可用于后续对账'],
    };

    return {
      passed: !failed,
      draftText,
      ruleJson,
      compatibility: {
        status: failed ? 'failed' : 'passed',
        message: failed ? '兼容性检查未通过，请调整数据整理配置。' : '兼容性检查通过，可继续试跑或进入下一步。',
        details,
      } as CompatibilityCheckResult,
      preview,
    };
  }, [
    evaluateSourceCompatibility,
    schemeDraft,
    selectedLeftSources,
    selectedProcOption,
    selectedRightSources,
  ]);

  const applyProcEvaluation = useCallback(
    (result: ReturnType<typeof evaluateProcDraftState>) => {
      setProcCompatibility(result.compatibility);
      setSchemeDraft((prev) => ({
        ...prev,
        procDraft: result.draftText || prev.procDraft,
        procRuleJson: result.ruleJson,
        procTrialStatus: result.preview.status,
        procTrialSummary: result.preview.summary,
        reconDraft: result.passed ? prev.reconDraft : '',
        reconRuleJson: result.passed ? prev.reconRuleJson : null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview(result.preview);
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
    },
    [],
  );
  void applyProcEvaluation;

  const resolvePreparedRowsForRecon = useCallback(() => {
    const procSeed =
      schemeDraft.procDraft.trim()
      || selectedProcOption?.draftText?.trim()
      || (selectedProcOption?.ruleJson ? summarizeProcDraft(selectedProcOption.ruleJson) : '')
      || selectedProcOption?.name
      || schemeDraft.name
      || 'proc';

    if (procTrialPreview) {
      return {
        leftRows: preparedLeftRows.slice(0, 3),
        rightRows: preparedRightRows.slice(0, 3),
      };
    }

    return {
      leftRows: buildPreparedRows(selectedLeftSources, 'left', procSeed),
      rightRows: buildPreparedRows(selectedRightSources, 'right', procSeed),
    };
  }, [
    procTrialPreview,
    preparedLeftRows,
    preparedRightRows,
    schemeDraft.name,
    schemeDraft.procDraft,
    selectedLeftSources,
    selectedProcOption,
    selectedRightSources,
  ]);

  const evaluateReconDraftState = useCallback(() => {
    const details: string[] = [];
    let failed = false;
    const baseDraftText =
      schemeDraft.reconDraft.trim()
      || selectedReconOption?.draftText?.trim()
      || (selectedReconOption?.ruleJson ? summarizeReconDraft(selectedReconOption.ruleJson) : '');
    const baseRuleJson = schemeDraft.reconRuleJson || selectedReconOption?.ruleJson || null;
    const parsedConfig =
      baseDraftText.trim()
        ? parseReconDraftConfig({
            reconDraft: baseDraftText,
            matchKey: schemeDraft.matchKey || selectedReconOption?.matchKey || '',
            leftAmountField: schemeDraft.leftAmountField || selectedReconOption?.leftAmountField || '',
            rightAmountField: schemeDraft.rightAmountField || selectedReconOption?.rightAmountField || '',
            tolerance: schemeDraft.tolerance || selectedReconOption?.tolerance || '',
          })
        : baseRuleJson
        ? parseReconRuleJsonConfig(baseRuleJson)
        : {
            matchKey: selectedReconOption?.matchKey || '',
            leftAmountField: selectedReconOption?.leftAmountField || '',
            rightAmountField: selectedReconOption?.rightAmountField || '',
            tolerance: selectedReconOption?.tolerance || '',
          };

    const leftCheck = evaluateSourceCompatibility('左侧', selectedLeftSources, selectedReconOption?.leftSources);
    const rightCheck = evaluateSourceCompatibility('右侧', selectedRightSources, selectedReconOption?.rightSources);
    details.push(leftCheck.message, ...leftCheck.details, rightCheck.message, ...rightCheck.details);
    failed = leftCheck.status === 'failed' || rightCheck.status === 'failed';

    if (!baseDraftText && !baseRuleJson) {
      failed = true;
      details.push('当前没有可试跑的数据对账逻辑。');
    }
    if (!parsedConfig.matchKey.trim()) {
      failed = true;
      details.push('缺少匹配主键。');
    }
    if (!parsedConfig.leftAmountField.trim() || !parsedConfig.rightAmountField.trim()) {
      failed = true;
      details.push('缺少左右金额字段。');
    }

    const toleranceValue = Number(parsedConfig.tolerance);
    if (!Number.isFinite(toleranceValue)) {
      failed = true;
      details.push('容差必须是数字。');
    }

    const { leftRows, rightRows } = resolvePreparedRowsForRecon();
    if (!leftRows.length || !rightRows.length) {
      failed = true;
      details.push('缺少整理后的左右数据抽样，请先完成数据整理试跑。');
    }

    const leftColumns = new Set(Object.keys(leftRows[0] || {}));
    const rightColumns = new Set(Object.keys(rightRows[0] || {}));
    if (parsedConfig.matchKey && (!leftColumns.has(parsedConfig.matchKey) || !rightColumns.has(parsedConfig.matchKey))) {
      failed = true;
      details.push(`匹配主键 ${parsedConfig.matchKey} 不存在于整理后的左右数据中。`);
    }
    if (parsedConfig.leftAmountField && !leftColumns.has(parsedConfig.leftAmountField)) {
      failed = true;
      details.push(`左金额字段 ${parsedConfig.leftAmountField} 不存在于左侧整理结果中。`);
    }
    if (parsedConfig.rightAmountField && !rightColumns.has(parsedConfig.rightAmountField)) {
      failed = true;
      details.push(`右金额字段 ${parsedConfig.rightAmountField} 不存在于右侧整理结果中。`);
    }

    const orderedKeys = Array.from(
      new Set([
        ...leftRows.map((row, index) => getPreviewRowKey(row, parsedConfig.matchKey, `LEFT-${index + 1}`)),
        ...rightRows.map((row, index) => getPreviewRowKey(row, parsedConfig.matchKey, `RIGHT-${index + 1}`)),
      ]),
    );
    const leftBuckets = new Map<string, PreviewTableRow[]>();
    const rightBuckets = new Map<string, PreviewTableRow[]>();
    leftRows.forEach((row, index) => {
      const key = getPreviewRowKey(row, parsedConfig.matchKey, `LEFT-${index + 1}`);
      leftBuckets.set(key, [...(leftBuckets.get(key) || []), row]);
    });
    rightRows.forEach((row, index) => {
      const key = getPreviewRowKey(row, parsedConfig.matchKey, `RIGHT-${index + 1}`);
      rightBuckets.set(key, [...(rightBuckets.get(key) || []), row]);
    });
    const results: ReconResultRow[] = orderedKeys.flatMap((key) => {
      const leftBucket = leftBuckets.get(key) || [];
      const rightBucket = rightBuckets.get(key) || [];
      const rowCount = Math.max(leftBucket.length, rightBucket.length);
      return Array.from({ length: rowCount }, (_, index) => {
        const leftRow = leftBucket[index];
        const rightRow = rightBucket[index];
        const leftAmount = Number(leftRow?.[parsedConfig.leftAmountField]);
        const rightAmount = Number(rightRow?.[parsedConfig.rightAmountField]);
        const displayKey = rowCount > 1 ? `${key} #${index + 1}` : key;
        if (leftRow && rightRow) {
          const diffAmount = formatPreviewAmount(leftAmount - rightAmount);
          const isMatched = !failed && Math.abs(diffAmount) <= toleranceValue;
          return {
            matchKey: displayKey,
            result: isMatched ? 'matched' : 'amount_diff',
            leftAmount: Number.isFinite(leftAmount) ? leftAmount : '--',
            rightAmount: Number.isFinite(rightAmount) ? rightAmount : '--',
            diffAmount: Number.isFinite(diffAmount) ? diffAmount : '--',
            note: isMatched ? '匹配通过' : '金额超出容差',
          };
        }
        if (leftRow) {
          return {
            matchKey: displayKey,
            result: 'left_only',
            leftAmount: Number.isFinite(leftAmount) ? leftAmount : '--',
            rightAmount: '--',
            diffAmount: '--',
            note: '右侧缺少对应记录',
          };
        }
        return {
          matchKey: displayKey,
          result: 'right_only',
          leftAmount: '--',
          rightAmount: Number.isFinite(rightAmount) ? rightAmount : '--',
          diffAmount: '--',
          note: '左侧缺少对应记录',
        };
      });
    });

    const reconRuleName = buildDefaultReconRuleName(schemeDraft.name);
    const resolvedRuleJson =
      baseDraftText.trim() && (!baseRuleJson || summarizeReconDraft(baseRuleJson) !== baseDraftText)
        ? buildReconJsonPayload(
            {
              ...schemeDraft,
              reconRuleName,
              matchKey: parsedConfig.matchKey,
              leftAmountField: parsedConfig.leftAmountField,
              rightAmountField: parsedConfig.rightAmountField,
              tolerance: parsedConfig.tolerance,
            },
            parsedConfig,
          )
        : baseRuleJson
        ? baseRuleJson
        : buildReconJsonPayload(
            {
              ...schemeDraft,
              reconRuleName,
              matchKey: parsedConfig.matchKey,
              leftAmountField: parsedConfig.leftAmountField,
              rightAmountField: parsedConfig.rightAmountField,
              tolerance: parsedConfig.tolerance,
            },
            parsedConfig,
          );

    return {
      passed: !failed,
      draftText: baseDraftText,
      ruleJson: resolvedRuleJson,
      parsedConfig,
      reconRuleName,
      compatibility: {
        status: failed ? 'failed' : 'passed',
        message: failed ? '兼容性检查未通过，请调整数据对账逻辑。' : '兼容性检查通过，可进入保存方案。',
        details,
      } as CompatibilityCheckResult,
      preview: {
        status: failed ? 'needs_adjustment' : 'passed',
        summary: failed
          ? '试跑结果：当前对账逻辑仍与整理后数据不兼容，请调整后重试。'
          : `试跑结果：已按 ${parsedConfig.matchKey} 对抽样数据完成验证，可进入保存方案。`,
        leftRows,
        rightRows,
        leftFieldLabelMap: PREPARED_OUTPUT_FIELD_LABEL_MAP,
        rightFieldLabelMap: PREPARED_OUTPUT_FIELD_LABEL_MAP,
        resultFieldLabelMap: RECON_RESULT_FIELD_LABEL_MAP,
        results,
      } as ReconTrialPreview,
    };
  }, [
    evaluateSourceCompatibility,
    resolvePreparedRowsForRecon,
    schemeDraft,
    selectedLeftSources,
    selectedReconOption,
    selectedRightSources,
  ]);

  const applyReconEvaluation = useCallback(
    (result: ReturnType<typeof evaluateReconDraftState>) => {
      setReconCompatibility(result.compatibility);
      setSchemeDraft((prev) => ({
        ...prev,
        reconDraft: result.draftText || prev.reconDraft,
        reconRuleJson: result.ruleJson,
        reconRuleName: result.reconRuleName,
        matchKey: result.parsedConfig.matchKey,
        leftAmountField: result.parsedConfig.leftAmountField,
        rightAmountField: result.parsedConfig.rightAmountField,
        tolerance: result.parsedConfig.tolerance,
        reconTrialStatus: result.preview.status,
        reconTrialSummary: result.preview.summary,
      }));
      setReconTrialPreview(result.preview);
    },
    [],
  );
  void applyReconEvaluation;

  const handleSelectExistingProcConfig = useCallback(
    async (configId: string) => {
      setModalError(null);
      if (!configId) {
        setSchemeDraft((prev) => ({
          ...prev,
          selectedProcConfigId: '',
          procDraft: '',
          procRuleJson: null,
          procTrialStatus: 'idle',
          procTrialSummary: '',
          reconDraft: '',
          reconRuleJson: null,
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }));
        setDesignSessionId('');
        setProcTrialPreview(null);
        setReconTrialPreview(null);
        setProcCompatibility(emptyCompatibilityResult());
        setReconCompatibility(emptyCompatibilityResult());
        return;
      }

      const option = existingProcOptions.find((item) => item.id === configId) || null;
      if (!option) return;

      setIsGeneratingProc(true);
      try {
        const ruleJson = option.ruleJson || (option.ruleCode ? await loadRuleJsonByCode(option.ruleCode) : null);
        if (!ruleJson) {
          throw new Error('已有数据整理配置缺少可用的规则 JSON');
        }
        const sessionId = await ensureDesignSession();
        await syncDesignTarget(sessionId);
        const response = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/proc/use-existing`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            rule_code: option.ruleCode || '',
            rule_json: ruleJson,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '加载已有数据整理配置失败'));
        }
        const session = asRecord(data.session);
        const procStep = asRecord(session.proc_step);
        const compatibility = toCompatibilityResult(
          procStep.compatibility_result,
          '已载入已有数据整理配置，请继续试跑验证。',
        );
        const normalizedRuleJson = asRecord(procStep.effective_rule_json);
        const draftText = resolveWizardDraftText(
          procStep.draft_text,
          procStep.rule_summary,
          option.draftText.trim() || summarizeProcDraft(normalizedRuleJson),
        );
        setSchemeDraft((prev) => ({
          ...prev,
          procConfigMode: 'existing',
          selectedProcConfigId: configId,
          procDraft: draftText,
          procRuleJson: normalizedRuleJson,
          procTrialStatus: 'idle',
          procTrialSummary: '',
          reconDraft: '',
          reconRuleJson: null,
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }));
        setProcTrialPreview(null);
        setReconTrialPreview(null);
        setProcCompatibility(compatibility);
        setReconCompatibility(emptyCompatibilityResult());
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '加载已有数据整理配置失败');
      } finally {
        setIsGeneratingProc(false);
      }
    },
    [
      authToken,
      ensureDesignSession,
      existingProcOptions,
      loadRuleJsonByCode,
      syncDesignTarget,
      toCompatibilityResult,
    ],
  );

  const handleSelectExistingReconConfig = useCallback(
    async (configId: string) => {
      setModalError(null);
      if (!configId) {
        setSchemeDraft((prev) => ({
          ...prev,
          selectedReconConfigId: '',
          reconDraft: '',
          reconRuleJson: null,
          reconRuleName: '',
          matchKey: '',
          leftAmountField: '',
          rightAmountField: '',
          tolerance: '',
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }));
        setDesignSessionId('');
        setReconTrialPreview(null);
        setReconCompatibility(emptyCompatibilityResult());
        return;
      }

      const option = existingReconOptions.find((item) => item.id === configId) || null;
      if (!option) return;

      setIsGeneratingRecon(true);
      try {
        const ruleJson = option.ruleJson || (option.ruleCode ? await loadRuleJsonByCode(option.ruleCode) : null);
        if (!ruleJson) {
          throw new Error('已有对账逻辑缺少可用的规则 JSON');
        }
        const sessionId = await ensureDesignSession();
        await syncDesignTarget(sessionId);
        const response = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/recon/use-existing`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            rule_code: option.ruleCode || '',
            rule_json: ruleJson,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '加载已有数据对账逻辑失败'));
        }
        const session = asRecord(data.session);
        const reconStep = asRecord(session.recon_step);
        const normalizedRuleJson = asRecord(reconStep.effective_rule_json);
        const parsed = parseReconRuleJsonConfig(normalizedRuleJson);
        const draftText = resolveWizardDraftText(
          reconStep.draft_text,
          reconStep.rule_summary,
          option.draftText.trim() || summarizeReconDraft(normalizedRuleJson),
        );
        setSchemeDraft((prev) => ({
          ...prev,
          reconConfigMode: 'existing',
          selectedReconConfigId: configId,
          reconDraft: draftText,
          reconRuleJson: normalizedRuleJson,
          matchKey: parsed.matchKey,
          leftAmountField: parsed.leftAmountField,
          rightAmountField: parsed.rightAmountField,
          tolerance: parsed.tolerance,
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }));
        setReconTrialPreview(null);
        setReconCompatibility(
          toCompatibilityResult(reconStep.compatibility_result, '已载入已有数据对账逻辑，请继续试跑验证。'),
        );
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '加载已有数据对账逻辑失败');
      } finally {
        setIsGeneratingRecon(false);
      }
    },
    [
      authToken,
      ensureDesignSession,
      existingReconOptions,
      loadRuleJsonByCode,
      syncDesignTarget,
      toCompatibilityResult,
    ],
  );

  const generateProcDraft = useCallback(async () => {
    if (!authToken) {
      setModalError('请先登录后再使用 AI 生成整理配置。');
      return;
    }
    if (!selectedLeftSources.length || !selectedRightSources.length) {
      setModalError('请先完成左右数据集选择。');
      return;
    }

    setIsGeneratingProc(true);
    setProcGenerationProgress({
      skill: '整理配置生成器',
      phase: 'preparing_context',
      message: '正在准备左右数据集样例',
    });
    setModalError(null);
    try {
      const sessionId = await ensureDesignSession();
      await syncDesignTarget(sessionId);
      const session = await consumeRuleGenerationStream(sessionId, 'proc', schemeDraft.procDraft.trim());
      const procStep = asRecord(session.proc_step);
      const procRuleJson = asRecord(procStep.effective_rule_json);
      if (!procRuleJson || !Array.isArray(procRuleJson.steps)) {
        throw new Error('AI 未返回有效的数据整理配置');
      }
      setSchemeDraft((prev) => ({
        ...prev,
        procConfigMode: 'ai',
        selectedProcConfigId: '',
        procDraft: resolveWizardDraftText(
          procStep.draft_text,
          procStep.rule_summary,
          summarizeProcDraft(procRuleJson),
        ),
        procRuleJson,
        procTrialStatus: 'idle',
        procTrialSummary: '',
        reconDraft: '',
        reconRuleJson: null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setProcCompatibility(toCompatibilityResult(procStep.compatibility_result, 'AI 已生成数据整理配置。'));
      setReconCompatibility(emptyCompatibilityResult());
    } catch (error) {
      setModalError(error instanceof Error ? error.message : 'AI 生成整理配置失败');
    } finally {
      setProcGenerationProgress(null);
      setIsGeneratingProc(false);
    }
  }, [
    authToken,
    schemeDraft.procDraft,
    consumeRuleGenerationStream,
    ensureDesignSession,
    syncDesignTarget,
    toCompatibilityResult,
  ]);

  const trialProcDraft = useCallback(async (): Promise<boolean> => {
    setModalError(null);
    if (!schemeDraft.procRuleJson) {
      setModalError('请先 AI 生成或选择已有数据整理配置。');
      return false;
    }
    if (!authToken) {
      setModalError('请先登录后再试跑验证。');
      return false;
    }

    setIsTrialingProc(true);
    try {
      const sessionId = await ensureDesignSession();
      await syncDesignTarget(sessionId);
      const response = await fetchReconAutoApi(`/schemes/design/${encodeURIComponent(sessionId)}/proc/trial`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
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
          passed ? '试跑验证通过，可进入下一步。' : '试跑未通过，请调整数据整理配置后重试。',
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
        reconRuleJson: passed ? prev.reconRuleJson : null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview(buildProcPreviewFromTrial(trialResult));
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
      return passed;
    } catch (error) {
      const message = error instanceof Error ? error.message : '数据整理试跑失败';
      setModalError(message);
      setProcCompatibility({
        status: 'failed',
        message: '试跑未通过，请检查整理配置或样本数据。',
        details: [message],
      });
      setSchemeDraft((prev) => ({
        ...prev,
        procTrialStatus: 'needs_adjustment',
        procTrialSummary: message,
        reconDraft: '',
        reconRuleJson: null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
      return false;
    } finally {
      setIsTrialingProc(false);
    }
  }, [
    authToken,
    buildProcPreviewFromTrial,
    ensureDesignSession,
    schemeDraft.procRuleJson,
    syncDesignTarget,
    toCompatibilityResult,
  ]);

  const generateReconDraft = useCallback(async () => {
    if (!authToken) {
      setModalError('请先登录后再使用 AI 生成对账逻辑。');
      return;
    }
    if (!selectedLeftSources.length || !selectedRightSources.length) {
      setModalError('请先完成左右数据集选择。');
      return;
    }
    if (schemeDraft.procTrialStatus !== 'passed' || !schemeDraft.procRuleJson) {
      setModalError('请先完成数据整理试跑，再生成对账逻辑。');
      return;
    }

    setIsGeneratingRecon(true);
    setReconGenerationProgress({
      skill: '对账逻辑生成器',
      phase: 'preparing_context',
      message: '正在准备数据整理后的左右输出样例',
    });
    setModalError(null);
    try {
      const sessionId = await ensureDesignSession();
      await syncDesignTarget(sessionId);
      const session = await consumeRuleGenerationStream(sessionId, 'recon', schemeDraft.reconDraft.trim());
      const reconStep = asRecord(session.recon_step);
      const reconRuleJson = asRecord(reconStep.effective_rule_json);
      if (!Array.isArray(reconRuleJson.rules) || reconRuleJson.rules.length === 0) {
        throw new Error('AI 未返回有效的数据对账逻辑');
      }
      const nextConfig = parseReconRuleJsonConfig(reconRuleJson);
      const draftText = resolveWizardDraftText(
        reconStep.draft_text,
        reconStep.rule_summary,
        summarizeReconDraft(reconRuleJson),
      );
      setSchemeDraft((prev) => ({
        ...prev,
        reconConfigMode: 'ai',
        selectedReconConfigId: '',
        reconRuleName: toText(reconRuleJson.rule_name, prev.reconRuleName || buildDefaultReconRuleName(prev.name)),
        matchKey: nextConfig.matchKey,
        leftAmountField: nextConfig.leftAmountField,
        rightAmountField: nextConfig.rightAmountField,
        tolerance: nextConfig.tolerance,
        reconDraft: draftText,
        reconRuleJson,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setReconTrialPreview(null);
      setReconCompatibility(
        toCompatibilityResult(reconStep.compatibility_result, 'AI 已生成数据对账逻辑。'),
      );
      setWizardJsonPanel(null);
    } catch (error) {
      setModalError(error instanceof Error ? error.message : 'AI 生成对账逻辑失败');
    } finally {
      setReconGenerationProgress(null);
      setIsGeneratingRecon(false);
    }
  }, [
    authToken,
    consumeRuleGenerationStream,
    ensureDesignSession,
    schemeDraft.procRuleJson,
    schemeDraft.procTrialStatus,
    syncDesignTarget,
    toCompatibilityResult,
    schemeDraft.businessGoal,
    schemeDraft.leftDescription,
    schemeDraft.name,
    schemeDraft.reconDraft,
    schemeDraft.rightDescription,
    selectedLeftSources,
    selectedRightSources,
  ]);

  const trialReconDraft = useCallback(async (): Promise<boolean> => {
    setModalError(null);
    if (!schemeDraft.reconRuleJson) {
      setModalError('请先 AI 生成或选择已有数据对账逻辑。');
      return false;
    }
    if (!authToken) {
      setModalError('请先登录后再试跑验证。');
      return false;
    }
    if (schemeDraft.procTrialStatus !== 'passed' || !schemeDraft.procRuleJson) {
      setModalError('请先完成数据整理试跑，再进行对账试跑。');
      return false;
    }

    setIsTrialingRecon(true);
    try {
      const sessionId = await ensureDesignSession();
      await syncDesignTarget(sessionId);
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
      const normalizedRule = asRecord(reconStep.effective_rule_json);
      const parsed = parseReconRuleJsonConfig(normalizedRule);
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
        reconDraft: resolveWizardDraftText(
          reconStep.draft_text,
          reconStep.rule_summary,
          prev.reconDraft,
        ),
        reconRuleJson: Object.keys(normalizedRule).length > 0 ? normalizedRule : prev.reconRuleJson,
        reconRuleName: toText(normalizedRule.rule_name, prev.reconRuleName || buildDefaultReconRuleName(prev.name)),
        matchKey: parsed.matchKey,
        leftAmountField: parsed.leftAmountField,
        rightAmountField: parsed.rightAmountField,
        tolerance: parsed.tolerance,
        reconTrialStatus: passed ? 'passed' : 'needs_adjustment',
        reconTrialSummary: summary,
      }));
      setReconTrialPreview(buildReconPreviewFromTrial(trialResult));
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
      return false;
    } finally {
      setIsTrialingRecon(false);
    }
  }, [
    authToken,
    buildReconPreviewFromTrial,
    ensureDesignSession,
    schemeDraft.procRuleJson,
    schemeDraft.procTrialStatus,
    schemeDraft.reconRuleJson,
    syncDesignTarget,
    toCompatibilityResult,
  ]);

  const handleViewProcJson = useCallback(() => {
    setWizardJsonPanel((prev) => (prev === 'proc' ? null : 'proc'));
  }, []);

  const handleViewReconJson = useCallback(() => {
    setWizardJsonPanel((prev) => (prev === 'recon' ? null : 'recon'));
  }, []);

  const handleCreateScheme = useCallback(async () => {
    if (!authToken) {
      setModalError('请先登录后再保存对账方案。');
      return;
    }
    if (!schemeDraft.procRuleJson || !schemeDraft.reconRuleJson) {
      setModalError('请先生成并验证数据整理与对账逻辑。');
      return;
    }
    if (schemeDraft.procTrialStatus !== 'passed' || schemeDraft.reconTrialStatus !== 'passed') {
      setModalError('请先完成数据整理和对账逻辑的试跑验证，再保存方案。');
      return;
    }

    setIsSubmittingScheme(true);
    setModalError(null);

    try {
      const procRuleJson = schemeDraft.procRuleJson;
      const reconRuleJson = schemeDraft.reconRuleJson;
      const parsedReconRule = parseReconRuleJsonConfig(reconRuleJson);
      const procRuleName =
        selectedProcOption?.name
        || (schemeDraft.name.trim() ? `${schemeDraft.name.trim()} 整理规则` : '整理规则');
      const reconRuleName =
        selectedReconOption?.name
        || toText(asRecord(reconRuleJson).rule_name, buildDefaultReconRuleName(schemeDraft.name));
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
          dataset_source_type: 'snapshot',
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
          dataset_source_type: 'snapshot',
        })),
      ];
      const response = await fetchReconAutoApi('/schemes', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          scheme_name: schemeDraft.name.trim(),
          description: schemeDraft.businessGoal.trim(),
          file_rule_code: '',
          proc_rule_code: selectedProcOption?.ruleCode || '',
          recon_rule_code: selectedReconOption?.ruleCode || '',
          dataset_bindings_json: datasetBindingsJson,
          scheme_meta_json: {
            business_goal: schemeDraft.businessGoal.trim(),
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
            left_description: schemeDraft.leftDescription.trim(),
            right_description: schemeDraft.rightDescription.trim(),
            validation_summary: {
              proc: {
                status: schemeDraft.procTrialStatus,
                summary: schemeDraft.procTrialSummary.trim(),
              },
              recon: {
                status: schemeDraft.reconTrialStatus,
                summary: schemeDraft.reconTrialSummary.trim(),
              },
            },
            proc_trial_status: schemeDraft.procTrialStatus,
            proc_trial_summary: schemeDraft.procTrialSummary.trim(),
            recon_trial_status: schemeDraft.reconTrialStatus,
            recon_trial_summary: schemeDraft.reconTrialSummary.trim(),
            match_key: parsedReconRule.matchKey.trim() || parsedReconConfig.matchKey.trim(),
            left_amount_field: parsedReconRule.leftAmountField.trim() || parsedReconConfig.leftAmountField.trim(),
            right_amount_field: parsedReconRule.rightAmountField.trim() || parsedReconConfig.rightAmountField.trim(),
            tolerance: parsedReconRule.tolerance.trim() || parsedReconConfig.tolerance.trim(),
            proc_rule_name: procRuleName,
            recon_rule_name: reconRuleName,
            proc_draft_text: schemeDraft.procDraft.trim() || summarizeProcDraft(procRuleJson),
            recon_draft_text: schemeDraft.reconDraft.trim() || summarizeReconDraft(reconRuleJson),
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
    loadCenterData,
    parsedReconConfig,
    schemeDraft,
    selectedProcOption?.name,
    selectedProcOption?.ruleCode,
    selectedReconOption?.name,
    selectedReconOption?.ruleCode,
    selectedLeftSources,
    selectedRightSources,
  ]);

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
    if (!planDraft.leftTimeSemantic.trim() || !planDraft.rightTimeSemantic.trim()) {
      setModalError('请先选择左右时间口径。');
      return;
    }

    const matchedScheme = schemes.find((s) => s.schemeCode === schemeCode);
    const schemeName = matchedScheme?.name || schemeCode;
    const matchedSchemeMeta = matchedScheme ? extractSchemeMeta(matchedScheme) : null;
    const todayStr = new Date().toISOString().slice(0, 10);
    const autoName = `${schemeName} ${todayStr}`;
    const inputBindings = buildRunPlanBindings(
      matchedSchemeMeta,
      planDraft.leftTimeSemantic.trim(),
      planDraft.rightTimeSemantic.trim(),
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
          biz_date_offset: 'previous_day',
          input_bindings_json: inputBindings,
          channel_config_id: planDraft.channelConfigId.trim(),
          owner_mapping_json: planDraft.ownerSummary.trim()
            ? { default_owner: { name: planDraft.ownerSummary.trim() } }
            : {},
          plan_meta_json: {
            left_time_semantic: planDraft.leftTimeSemantic.trim(),
            right_time_semantic: planDraft.rightTimeSemantic.trim(),
            time_semantic: [planDraft.leftTimeSemantic.trim(), planDraft.rightTimeSemantic.trim()]
              .filter(Boolean)
              .join(' / '),
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
  }, [authToken, closeModal, loadCenterData, planDraft, schemes]);

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

  const handleRetryRun = useCallback(
    async (runId: string) => {
      if (!authToken) {
        setCenterError('请先登录后再重试运行。');
        return;
      }
      setRetryingRunId(runId);
      setCenterError(null);
      setCenterNotice(null);
      try {
        const response = await fetchReconAutoApi(`/runs/${runId}/retry`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ reason: '前端手动重试' }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data.detail || data.message || '重试运行失败'));
        }
        await loadCenterData();
        setActiveTab('runs');
        setCenterNotice('已重新触发该运行任务，请稍后刷新查看最新状态。');
      } catch (error) {
        setCenterError(error instanceof Error ? error.message : '重试运行失败');
      } finally {
        setRetryingRunId((prev) => (prev === runId ? null : prev));
      }
    },
    [authToken, loadCenterData],
  );

  const schemeStepOneReady =
    Boolean(schemeDraft.name.trim()) &&
    Boolean(schemeDraft.businessGoal.trim()) &&
    selectedLeftSources.length > 0 &&
    selectedRightSources.length > 0;
  const schemeStepTwoReady = Boolean(
    schemeDraft.procConfigMode === 'existing'
      ? schemeDraft.selectedProcConfigId || schemeDraft.procRuleJson
      : schemeDraft.procDraft.trim() || schemeDraft.procRuleJson,
  );
  const schemeStepThreeReady = Boolean(
    schemeDraft.reconConfigMode === 'existing'
      ? schemeDraft.selectedReconConfigId || schemeDraft.reconRuleJson
      : schemeDraft.reconDraft.trim() || schemeDraft.reconRuleJson,
  );
  const schemeStepTwoPassed =
    schemeDraft.procTrialStatus === 'passed' && Boolean(schemeDraft.procRuleJson);
  const schemeStepThreePassed =
    schemeDraft.reconTrialStatus === 'passed' && Boolean(schemeDraft.reconRuleJson);
  const isSchemeWizardBusy =
    isGeneratingProc || isTrialingProc || isGeneratingRecon || isTrialingRecon;

  const goToNextSchemeStep = useCallback(async () => {
    setModalError(null);
    if (isSchemeWizardBusy) {
      setModalError('当前正在生成或试跑，请等待本次操作完成后再进入下一步。');
      return;
    }
    if (schemeWizardStep === 1) {
      if (!schemeStepOneReady) {
        setModalError('请先完成方案名称、对账目标以及左右数据集选择。');
        return;
      }
      setSchemeWizardStep(2);
      return;
    }
    if (schemeWizardStep === 2) {
      if (!schemeStepTwoReady) {
        setModalError('请先生成或选择一条可用的数据整理配置。');
        return;
      }
      if (!schemeStepTwoPassed) {
        const passed = await trialProcDraft();
        if (!passed) {
          setModalError('数据整理试跑未通过，请调整配置后重试。');
          return;
        }
      }
      setSchemeWizardStep(3);
      return;
    }
    if (schemeWizardStep === 3) {
      if (!schemeStepThreeReady) {
        setModalError('请先生成或选择一条可用的数据对账逻辑。');
        return;
      }
      if (!schemeStepThreePassed) {
        const passed = await trialReconDraft();
        if (!passed) {
          setModalError('数据对账试跑未通过，请调整逻辑后重试。');
          return;
        }
      }
      if (!schemeDraft.reconRuleJson) {
        setModalError('当前缺少可保存的数据对账逻辑。');
        return;
      }
      setSchemeWizardStep(4);
    }
  }, [
    schemeStepOneReady,
    schemeStepThreePassed,
    schemeStepThreeReady,
    schemeStepTwoPassed,
    schemeStepTwoReady,
    isSchemeWizardBusy,
    schemeDraft.reconRuleJson,
    schemeWizardStep,
    trialProcDraft,
    trialReconDraft,
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

  const selectedExceptionReasonLines = selectedExceptionDetail
    ? buildRunExceptionReasonLines(selectedExceptionDetail)
    : [];
  const selectedExceptionPayload = selectedExceptionDetail
    ? firstNonEmptyRecord(
        selectedExceptionDetail.raw.detail_json,
        selectedExceptionDetail.raw.detail,
        selectedExceptionDetail.raw,
      )
    : {};
  const selectedExceptionJoinKeys = selectedExceptionDetail
    ? getRunExceptionJoinKeys(selectedExceptionDetail)
    : [];
  const selectedExceptionCompareValues = selectedExceptionDetail
    ? getRunExceptionCompareValues(selectedExceptionDetail)
    : [];
  const selectedExceptionRawRecord = selectedExceptionDetail
    ? getRunExceptionRawRecord(selectedExceptionDetail)
    : {};

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
          const procRuleLabel = schemeMeta.procRuleName || (item.name ? `${item.name} 整理规则` : '未命名整理规则');
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
          columns={['运行任务', '触发信息', '异常数', '状态', '操作']}
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
              <span className="text-sm text-text-secondary">
                {item.triggerType || '--'} / {item.entryMode || '--'}
              </span>
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
                  {canRetryExecutionRun(item.executionStatus) ? (
                    <button
                      type="button"
                      onClick={() => void handleRetryRun(item.id)}
                      disabled={retryingRunId === item.id}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <RefreshCw className={cn('h-4 w-4', retryingRunId === item.id && 'animate-spin')} />
                      {retryingRunId === item.id ? '重试中...' : '重试'}
                    </button>
                  ) : null}
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
              return {
                title: matchedSource ? resolveDatasetDisplayName(matchedSource) : item.sourceName,
                fieldLabelMap: mergeFieldLabelMaps(
                  item.fieldLabelMap,
                  resolveSourceFieldLabelMap(matchedSource),
                ),
                originLabel: item.sampleOriginLabel,
                originHint: item.sampleOriginHint,
                rows: item.rows,
              };
            }),
          rightSourceSamples: procTrialPreview.rawSources
            .filter((item) => item.side === 'right')
            .map((item) => {
              const matchedSource = findSourceByPreview(item);
              return {
                title: matchedSource ? resolveDatasetDisplayName(matchedSource) : item.sourceName,
                fieldLabelMap: mergeFieldLabelMaps(
                  item.fieldLabelMap,
                  resolveSourceFieldLabelMap(matchedSource),
                ),
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
              rows: item.rows,
            })),
          rightOutputSamples: procTrialPreview.preparedOutputs
            .filter((item) => item.side === 'right')
            .map((item) => ({
              title: item.title,
              fieldLabelMap: item.fieldLabelMap || PREPARED_OUTPUT_FIELD_LABEL_MAP,
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
            match_key: item.matchKey,
            result: item.result,
            left_amount: item.leftAmount,
            right_amount: item.rightAmount,
            diff_amount: item.diffAmount,
            note: item.note,
          })),
          resultFieldLabelMap: reconTrialPreview.resultFieldLabelMap || RECON_RESULT_FIELD_LABEL_MAP,
          resultSummary: reconTrialPreview.resultSummary,
        }
      : undefined;

    if (schemeWizardStep === 1 || schemeWizardStep === 2) {
      return (
        <div className="space-y-5">
          <SchemeWizardTargetProcStep
            step={schemeWizardStep as 1 | 2}
            authToken={authToken}
            schemeDraft={{
              name: schemeDraft.name,
              businessGoal: schemeDraft.businessGoal,
              leftDescription: schemeDraft.leftDescription,
              rightDescription: schemeDraft.rightDescription,
              procConfigMode: schemeDraft.procConfigMode,
              selectedProcConfigId: schemeDraft.selectedProcConfigId,
              procDraft: schemeDraft.procDraft,
              procTrialStatus: schemeDraft.procTrialStatus,
              procTrialSummary: schemeDraft.procTrialSummary,
            }}
            selectedLeftSources={selectedLeftSources}
            selectedRightSources={selectedRightSources}
            existingProcOptions={existingProcOptions}
            procCompatibility={procCompatibility}
            onNameChange={(value) => resetSchemeDraftFromGoalChange({ name: value })}
            onBusinessGoalChange={(value) => resetSchemeDraftFromGoalChange({ businessGoal: value })}
            onDescriptionChange={(side, value) =>
              resetSchemeDraftFromGoalChange(
                side === 'left' ? { leftDescription: value } : { rightDescription: value },
              )
            }
            onChangeSourceSelection={(side, sources) => changeSchemeSources(side, sources)}
            onProcConfigModeChange={(mode) => {
              setSchemeDraft((prev) => ({
                ...prev,
                procConfigMode: mode,
                selectedProcConfigId: mode === 'existing' ? prev.selectedProcConfigId : '',
                procRuleJson: null,
                procTrialStatus: 'idle',
                procTrialSummary: '',
                reconDraft: '',
                reconRuleJson: null,
                reconTrialStatus: 'idle',
                reconTrialSummary: '',
              }));
              setProcTrialPreview(null);
              setReconTrialPreview(null);
              setProcCompatibility(emptyCompatibilityResult());
              setReconCompatibility(emptyCompatibilityResult());
            }}
            onSelectExistingProcConfig={(configId) => void handleSelectExistingProcConfig(configId)}
            isGeneratingProc={isGeneratingProc}
            generationSkill={procGenerationProgress?.skill}
            generationPhase={procGenerationProgress?.phase}
            generationMessage={procGenerationProgress?.message}
            isTrialingProc={isTrialingProc}
            onGenerateProc={generateProcDraft}
            onTrialProc={trialProcDraft}
            onProcDraftChange={(value) => {
              setSchemeDraft((prev) => ({
                ...prev,
                procDraft: value,
                procRuleJson: null,
                procTrialStatus: 'idle',
                procTrialSummary: '',
                reconDraft: '',
                reconRuleJson: null,
                reconTrialStatus: 'idle',
                reconTrialSummary: '',
              }));
              setProcTrialPreview(null);
              setReconTrialPreview(null);
              setProcCompatibility(emptyCompatibilityResult());
              setReconCompatibility(emptyCompatibilityResult());
            }}
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
              reconDraft: schemeDraft.reconDraft,
              reconTrialStatus: schemeDraft.reconTrialStatus,
              reconTrialSummary: schemeDraft.reconTrialSummary,
            }}
            reconConfigMode={schemeDraft.reconConfigMode}
            selectedReconConfigId={schemeDraft.selectedReconConfigId}
            existingReconOptions={existingReconOptions.map((item) => ({ id: item.id, name: item.name }))}
            reconCompatibility={reconCompatibility}
            onReconConfigModeChange={(mode) => {
              setSchemeDraft((prev) => ({
                ...prev,
                reconConfigMode: mode,
                selectedReconConfigId: mode === 'existing' ? prev.selectedReconConfigId : '',
                reconRuleName: '',
                matchKey: '',
                leftAmountField: '',
                rightAmountField: '',
                tolerance: '',
                reconRuleJson: null,
                reconTrialStatus: 'idle',
                reconTrialSummary: '',
              }));
              setReconTrialPreview(null);
              setReconCompatibility(
                mode === 'existing'
                  ? {
                      status: 'idle',
                      message: '请选择一条已有数据对账逻辑后再试跑。',
                      details: [],
                    }
                  : emptyCompatibilityResult(),
              );
            }}
            onSelectExistingReconConfig={(configId) => void handleSelectExistingReconConfig(configId)}
            onGenerateRecon={generateReconDraft}
            onTrialRecon={trialReconDraft}
            onReconDraftChange={(value) => {
              setSchemeDraft((prev) => ({
                ...prev,
                reconDraft: value,
                reconRuleJson: null,
                reconTrialStatus: 'idle',
                reconTrialSummary: '',
              }));
              setReconTrialPreview(null);
              setReconCompatibility(emptyCompatibilityResult());
            }}
            onViewReconJson={handleViewReconJson}
            reconJsonPreview={reconJsonPreview}
            reconTrialPreview={mappedReconTrialPreview}
            trialDisabled={
              isTrialingRecon
              || isGeneratingRecon
              || !schemeDraft.procRuleJson
              || schemeDraft.procTrialStatus !== 'passed'
              || !(
                (schemeDraft.reconConfigMode === 'existing'
                  ? schemeDraft.selectedReconConfigId
                  : schemeDraft.reconDraft.trim() || schemeDraft.reconRuleJson)
              )
            }
            isGeneratingRecon={isGeneratingRecon}
            generationSkill={reconGenerationProgress?.skill}
            generationPhase={reconGenerationProgress?.phase}
            generationMessage={reconGenerationProgress?.message}
            isTrialingRecon={isTrialingRecon}
          />

        </div>
      );
    }

    const procDisplayName =
      selectedProcOption?.name || (schemeDraft.name ? `${schemeDraft.name} · 数据整理配置` : '数据整理配置');
    const reconDisplayName =
      selectedReconOption?.name
      || schemeDraft.reconRuleName
      || toText(asRecord(schemeDraft.reconRuleJson || {}).rule_name)
      || buildDefaultReconRuleName(schemeDraft.name);

    return (
      <div className="space-y-5">
        <div className="rounded-3xl border border-border bg-surface-secondary p-4">
          <p className="text-sm font-semibold text-text-primary">方案摘要</p>
          <div className="mt-4 space-y-4">
            <div className="rounded-2xl border border-border bg-surface px-4 py-3">
              <p className="text-xs text-text-secondary">对账目标</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{schemeDraft.businessGoal || '--'}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-4 py-3">
              <p className="text-xs text-text-secondary">数据整理</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{procDisplayName}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-4 py-3">
              <p className="text-xs text-text-secondary">对账逻辑</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{reconDisplayName}</p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderModalContent = () => {
    if (!modalState) return null;

    if (modalState.kind === 'create-scheme') {
      return (
        <>
          <div className="border-b border-border px-6 py-5">
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">新增对账方案</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">按四步完成方案设计与试跑确认</h3>
          </div>
          <div className="space-y-6 px-6 py-5">
            <div className="grid gap-3 lg:grid-cols-4">
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
            {schemeWizardStep < 4 ? (
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
                  !schemeStepThreePassed
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
            <h3 className="mt-1 text-lg font-semibold text-text-primary">为方案补充调度、时间口径、协作通道与责任人</h3>
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
                  const nextLeftOptions = inferTimeOptionsFromSources(
                    nextSchemeMeta?.leftSources || [],
                    nextSchemeMeta?.leftTimeSemantic || '',
                  );
                  const nextRightOptions = inferTimeOptionsFromSources(
                    nextSchemeMeta?.rightSources || [],
                    nextSchemeMeta?.rightTimeSemantic || '',
                  );
                  setPlanDraft((prev) => ({
                    ...prev,
                    schemeCode: nextSchemeCode,
                    leftTimeSemantic: nextSchemeMeta?.leftTimeSemantic || nextLeftOptions[0]?.value || '',
                    rightTimeSemantic: nextSchemeMeta?.rightTimeSemantic || nextRightOptions[0]?.value || '',
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
            </label>

            <div className="grid gap-4 md:grid-cols-2">
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
                <span className="text-xs font-medium text-text-secondary">左侧时间口径</span>
                <select
                  value={planDraft.leftTimeSemantic}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, leftTimeSemantic: event.target.value }))
                  }
                  className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  <option value="">请选择左侧时间字段</option>
                  {planLeftTimeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-text-secondary">右侧时间口径</span>
                <select
                  value={planDraft.rightTimeSemantic}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, rightTimeSemantic: event.target.value }))
                  }
                  className="mt-1.5 w-full appearance-none rounded-xl border border-border bg-surface bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23999%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                >
                  <option value="">请选择右侧时间字段</option>
                  {planRightTimeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="text-xs font-medium text-text-secondary">协作通道</span>
                <select
                  value={planDraft.channelConfigId}
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, channelConfigId: event.target.value }))
                  }
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
                  onChange={(event) =>
                    setPlanDraft((prev) => ({ ...prev, ownerSummary: event.target.value }))
                  }
                  required
                  className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                  placeholder="例如：张三"
                />
              </label>
            </div>

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
                  !planDraft.ownerSummary.trim() ||
                  !planDraft.leftTimeSemantic.trim() ||
                  !planDraft.rightTimeSemantic.trim()
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
                      <p
                        className="whitespace-normal break-words [overflow-wrap:anywhere] text-sm font-medium leading-6 text-text-primary"
                        title={source.name}
                      >
                        {source.name}
                      </p>
                      <p className="mt-1 whitespace-normal break-words [overflow-wrap:anywhere] text-xs leading-5 text-text-secondary">
                        {source.sourceName ? `${source.sourceName} · ` : ''}
                        {sourceKindLabel(source.sourceKind)}
                      </p>
                    </div>
                  ))}
                  <p className="text-sm leading-6 text-text-secondary">{schemeMeta.leftDescription || '未补充说明。'}</p>
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
                      <p
                        className="whitespace-normal break-words [overflow-wrap:anywhere] text-sm font-medium leading-6 text-text-primary"
                        title={source.name}
                      >
                        {source.name}
                      </p>
                      <p className="mt-1 whitespace-normal break-words [overflow-wrap:anywhere] text-xs leading-5 text-text-secondary">
                        {source.sourceName ? `${source.sourceName} · ` : ''}
                        {sourceKindLabel(source.sourceKind)}
                      </p>
                    </div>
                  ))}
                  <p className="text-sm leading-6 text-text-secondary">{schemeMeta.rightDescription || '未补充说明。'}</p>
                </div>
              </div>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">数据整理</p>
                <p className="mt-2 text-sm leading-6 text-text-secondary">
                  {schemeMeta.procTrialSummary || '暂无摘要。'}
                </p>
                {scheme.procRuleCode ? (
                  <p className="mt-2 text-xs text-text-muted">规则：{scheme.procRuleCode}</p>
                ) : null}
              </div>
              <div className="rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">数据对账</p>
                <p className="mt-2 text-sm leading-6 text-text-secondary">
                  {schemeMeta.reconTrialSummary || '暂无摘要。'}
                </p>
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
              <DetailRow label="时间口径" value={`左 ${task.leftTimeSemantic || '--'} / 右 ${task.rightTimeSemantic || '--'}`} />
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
          <h3 className="mt-1 text-lg font-semibold text-text-primary">{run.planName}</h3>
        </div>
        <div className="space-y-5 px-6 py-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">所属方案</p>
              <p className="mt-1 text-sm font-medium text-text-primary">{run.schemeName || '--'}</p>
            </div>
            <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
              <p className="text-xs text-text-secondary">触发信息</p>
              <p className="mt-1 text-sm font-medium text-text-primary">
                {run.triggerType || '--'} / {run.entryMode || '--'}
              </p>
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
                  <span>异常内容</span>
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
                      <p className="mt-1 text-xs leading-5 text-text-secondary">
                        {formatAnomalyTypeLabel(item.anomalyType)}
                        {item.latestFeedback ? ` · 最新反馈：${item.latestFeedback}` : ''}
                      </p>
                      <button
                        type="button"
                        onClick={() => setSelectedExceptionDetail(item)}
                        className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        查看详细
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
                <p className="mt-2 text-sm text-text-secondary">
                  {formatAnomalyTypeLabel(selectedExceptionDetail.anomalyType)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedExceptionDetail(null)}
                className="rounded-lg p-2 text-text-secondary transition hover:bg-surface-secondary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                  <p className="text-xs text-text-secondary">责任人</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">{selectedExceptionDetail.ownerName || '--'}</p>
                </div>
                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                  <p className="text-xs text-text-secondary">催办状态</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {formatReminderStatusLabel(selectedExceptionDetail.reminderStatus)}
                  </p>
                </div>
                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                  <p className="text-xs text-text-secondary">处理进展</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {formatProcessingStatusLabel(selectedExceptionDetail.processingStatus)}
                  </p>
                </div>
                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                  <p className="text-xs text-text-secondary">修复状态</p>
                  <p className="mt-1 text-sm font-medium text-text-primary">
                    {formatFixStatusLabel(selectedExceptionDetail.fixStatus, selectedExceptionDetail.isClosed)}
                  </p>
                </div>
              </div>

              <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                <p className="text-sm font-semibold text-text-primary">为什么对不上</p>
                <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                  {selectedExceptionReasonLines.map((line) => (
                    <p key={line}>{line}</p>
                  ))}
                </div>
              </div>

              <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
                <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                  <p className="text-sm font-semibold text-text-primary">对账键</p>
                  {selectedExceptionJoinKeys.length > 0 ? (
                    <div className="mt-3 space-y-3">
                      {selectedExceptionJoinKeys.map((entry, index) => (
                        <div key={`${selectedExceptionDetail.id}-join-${index}`} className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <div className="grid gap-2 md:grid-cols-2">
                            <DetailRow
                              label={`源侧字段 ${index + 1}`}
                              value={`${toText(entry.source_field, '--')} = ${formatDetailValue(entry.source_value)}`}
                            />
                            <DetailRow
                              label={`目标侧字段 ${index + 1}`}
                              value={`${toText(entry.target_field, '--')} = ${formatDetailValue(entry.target_value)}`}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-text-secondary">当前没有返回对账键明细。</p>
                  )}
                </div>

                <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                  <p className="text-sm font-semibold text-text-primary">差异字段</p>
                  {selectedExceptionCompareValues.length > 0 ? (
                    <div className="mt-3 space-y-3">
                      {selectedExceptionCompareValues.map((entry, index) => (
                        <div key={`${selectedExceptionDetail.id}-compare-${index}`} className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <p className="text-sm font-medium text-text-primary">{toText(entry.name, `差异字段 ${index + 1}`)}</p>
                          <div className="mt-2 grid gap-2 md:grid-cols-2">
                            <DetailRow
                              label="源侧"
                              value={`${toText(entry.source_field, '--')} = ${formatDetailValue(entry.source_value)}`}
                            />
                            <DetailRow
                              label="目标侧"
                              value={`${toText(entry.target_field, '--')} = ${formatDetailValue(entry.target_value)}`}
                            />
                          </div>
                          <DetailRow label="差额" value={formatDetailValue(entry.diff_value)} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-text-secondary">当前没有返回差异字段明细。</p>
                  )}
                </div>
              </div>

              <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                <p className="text-sm font-semibold text-text-primary">异常记录明细</p>
                {Object.keys(selectedExceptionRawRecord).length > 0 ? (
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {Object.entries(selectedExceptionRawRecord).map(([key, value]) => (
                      <div key={`${selectedExceptionDetail.id}-field-${key}`} className="rounded-2xl border border-border bg-surface px-4 py-3">
                        <p className="text-xs text-text-secondary">{key}</p>
                        <p className="mt-1 whitespace-pre-wrap break-all text-sm text-text-primary">
                          {formatDetailValue(value)}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-text-secondary">当前没有返回原始异常记录。</p>
                )}
              </div>

              {selectedExceptionDetail.latestFeedback ? (
                <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                  <p className="text-sm font-semibold text-text-primary">最新反馈</p>
                  <p className="mt-3 text-sm leading-6 text-text-secondary">{selectedExceptionDetail.latestFeedback}</p>
                </div>
              ) : null}

              {(toText(selectedExceptionPayload.source_ref) || toText(selectedExceptionPayload.target_ref)) ? (
                <div className="rounded-3xl border border-border bg-surface-secondary px-5 py-4">
                  <p className="text-sm font-semibold text-text-primary">来源文件</p>
                  <div className="mt-3 divide-y divide-border-subtle">
                    <DetailRow label="源侧文件" value={toText(selectedExceptionPayload.source_ref, '--')} />
                    <DetailRow label="目标侧文件" value={toText(selectedExceptionPayload.target_ref, '--')} />
                  </div>
                </div>
              ) : null}
            </div>

            <div className="flex items-center justify-end border-t border-border px-6 py-4">
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
                {wizardJsonPanel === 'proc' ? '数据整理配置 JSON' : '对账逻辑 JSON'}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleCopyWizardJson(wizardJsonPanel)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition',
                    wizardJsonCopyState?.panel === wizardJsonPanel && wizardJsonCopyState.status === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : wizardJsonCopyState?.panel === wizardJsonPanel && wizardJsonCopyState.status === 'error'
                      ? 'border-red-200 bg-red-50 text-red-700'
                      : 'border-border bg-surface text-text-primary hover:border-sky-200 hover:text-sky-700',
                  )}
                >
                  {wizardJsonCopyState?.panel === wizardJsonPanel && wizardJsonCopyState.status === 'success' ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                  {wizardJsonCopyState?.panel === wizardJsonPanel && wizardJsonCopyState.status === 'success'
                    ? '已复制'
                    : wizardJsonCopyState?.panel === wizardJsonPanel && wizardJsonCopyState.status === 'error'
                    ? '复制失败'
                    : '复制 JSON'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setWizardJsonPanel(null);
                    setWizardJsonCopyState(null);
                  }}
                  className="rounded-lg p-2 text-text-secondary transition hover:bg-surface-secondary hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              <pre className="overflow-x-auto rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-xs leading-6 text-text-primary">
                {wizardJsonPanel === 'proc' ? procJsonPreview : reconJsonPreview}
              </pre>
            </div>
            <div className="flex items-center justify-end border-t border-border px-6 py-4">
              <button
                type="button"
                onClick={() => setWizardJsonPanel(null)}
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
