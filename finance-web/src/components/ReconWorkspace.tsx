import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlertCircle,
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
type SupportedSourceKind = Extract<DataSourceKind, 'platform_oauth' | 'database' | 'api'>;

interface SchemeSourceOption {
  id: string;
  name: string;
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

interface SchemeSourceRecord {
  id: string;
  name: string;
  sourceKind: SupportedSourceKind;
  providerCode: string;
  description?: string;
}

interface SchemeSourceDraft {
  id: string;
  name: string;
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
  leftSourceIds: string[];
  rightSourceIds: string[];
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

interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed';
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
  rows: PreviewTableRow[];
}

interface PreparedPreviewBlock {
  side: 'left' | 'right';
  title: string;
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
  results: ReconResultRow[];
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

const SUPPORTED_SOURCE_KINDS: SupportedSourceKind[] = ['platform_oauth', 'database', 'api'];
const SCHEME_LIST_TEMPLATE =
  'minmax(0,1.6fr) minmax(220px,1fr) minmax(220px,1fr) minmax(268px,auto)';
const TASK_LIST_TEMPLATE =
  'minmax(0,2.3fr) minmax(200px,1.1fr) minmax(180px,0.9fr) minmax(120px,0.7fr) minmax(280px,auto)';
const RUN_LIST_TEMPLATE =
  'minmax(0,2.4fr) minmax(190px,1fr) minmax(120px,0.7fr) minmax(120px,0.7fr) minmax(148px,auto)';

const SCHEME_WIZARD_STEPS: Array<{ id: SchemeWizardStep; title: string; description: string }> = [
  { id: 1, title: '对账目标', description: '选择左右数据并描述口径' },
  { id: 2, title: '数据整理', description: 'AI 生成整理配置并试跑' },
  { id: 3, title: '对账逻辑', description: 'AI 生成对账逻辑并试跑' },
  { id: 4, title: '保存方案', description: '确认摘要后保存方案' },
];

const EMPTY_SCHEME_DRAFT: SchemeDraft = {
  name: '',
  businessGoal: '',
  leftSourceIds: [],
  rightSourceIds: [],
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

function formatDateLabel(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function buildDefaultReconRuleName(schemeName: string): string {
  return `${schemeName.trim() || '未命名对账方案'} · 对账逻辑`;
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
  return {
    label: status || '未知',
    className: 'border-border bg-surface-secondary text-text-secondary',
  };
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

function normalizeSourceRecord(raw: unknown): SchemeSourceRecord | null {
  const value = asRecord(raw);
  const id = toText(value.id).trim();
  const sourceKind = toText(value.source_kind).trim() as SupportedSourceKind;
  if (!id || !SUPPORTED_SOURCE_KINDS.includes(sourceKind)) {
    return null;
  }

  return {
    id,
    name: toText(value.name, id).trim() || id,
    sourceKind,
    providerCode: toText(value.provider_code, 'unknown').trim() || 'unknown',
    description: toText(value.description).trim(),
  };
}

function normalizeSourceDatasetOption(
  raw: unknown,
  source: SchemeSourceRecord,
): SchemeSourceOption | null {
  const value = asRecord(raw);
  if (!value) return null;

  const datasetId = toText(value.id, toText(value.dataset_id)).trim();
  const datasetCode = toText(value.dataset_code, toText(value.code)).trim();
  const datasetName = toText(value.dataset_name, toText(value.name, datasetCode || datasetId)).trim();
  if (!datasetId && !datasetCode && !datasetName) {
    return null;
  }

  const enabled = typeof value.is_enabled === 'boolean'
    ? value.is_enabled
    : typeof value.enabled === 'boolean'
    ? value.enabled
    : true;
  if (!enabled) {
    return null;
  }

  return {
    id: datasetId || datasetCode || `${source.id}-${datasetName}`,
    name: datasetName || datasetCode || datasetId,
    sourceId: source.id,
    sourceName: source.name,
    sourceKind: source.sourceKind,
    providerCode: source.providerCode,
    description: source.description,
    datasetCode: datasetCode || datasetId || datasetName,
    resourceKey: toText(value.resource_key).trim(),
    datasetKind: toText(value.dataset_kind).trim(),
    schemaSummary: asRecord(value.schema_summary),
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
  const leftSources = asList(schemeMeta.left_sources).map((raw) => {
    const value = asRecord(raw);
    return {
      id: toText(value.id),
      name: toText(value.dataset_name, toText(value.name, toText(value.table_name, '未命名数据'))),
      sourceId: toText(value.source_id, toText(value.data_source_id)),
      sourceName: toText(value.source_name),
      sourceKind: (toText(value.source_kind) as SupportedSourceKind) || 'platform_oauth',
      providerCode: toText(value.provider_code),
      datasetCode: toText(value.dataset_code),
      resourceKey: toText(value.resource_key),
      datasetKind: toText(value.dataset_kind),
    };
  });
  const rightSources = asList(schemeMeta.right_sources).map((raw) => {
    const value = asRecord(raw);
    return {
      id: toText(value.id),
      name: toText(value.dataset_name, toText(value.name, toText(value.table_name, '未命名数据'))),
      sourceId: toText(value.source_id, toText(value.data_source_id)),
      sourceName: toText(value.source_name),
      sourceKind: (toText(value.source_kind) as SupportedSourceKind) || 'platform_oauth',
      providerCode: toText(value.provider_code),
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
    schema_summary: options?.schemaSummary || asRecord(source.schemaSummary),
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
  const optionMap = new Map<string, string>();
  sources.forEach((source) => {
    const sourceKind = source.sourceKind || 'platform_oauth';
    const field = getDefaultDateFieldBySourceKind(sourceKind);
    if (!field) return;
    if (!optionMap.has(field)) {
      optionMap.set(field, field);
    }
  });
  if (fallbackValue.trim() && !optionMap.has(fallbackValue.trim())) {
    optionMap.set(fallbackValue.trim(), fallbackValue.trim());
  }
  return Array.from(optionMap.entries()).map(([value, label]) => ({ value, label }));
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
  children,
}: ReconWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<ReconCenterTab>('schemes');
  const [schemes, setSchemes] = useState<ReconSchemeListItem[]>([]);
  const [tasks, setTasks] = useState<ReconTaskListItem[]>([]);
  const [runs, setRuns] = useState<ReconCenterRunItem[]>([]);
  const [exceptionsByRunId, setExceptionsByRunId] = useState<Record<string, ReconRunExceptionDetail[]>>({});
  const [availableSources, setAvailableSources] = useState<SchemeSourceOption[]>([]);
  const [availableChannels, setAvailableChannels] = useState<CollaborationChannelListItem[]>([]);
  const [availableProcRules, setAvailableProcRules] = useState<UserTaskRule[]>([]);
  const [loadingCenter, setLoadingCenter] = useState(false);
  const [loadingSources, setLoadingSources] = useState(false);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [loadingExceptionsRunId, setLoadingExceptionsRunId] = useState<string | null>(null);
  const [centerError, setCenterError] = useState<string | null>(null);
  const [centerNotice, setCenterNotice] = useState<string | null>(null);
  const [sourceLoadError, setSourceLoadError] = useState('');
  const [channelLoadError, setChannelLoadError] = useState('');
  const [modalState, setModalState] = useState<CenterModalState | null>(null);
  const [schemeWizardStep, setSchemeWizardStep] = useState<SchemeWizardStep>(1);
  const [schemeDraft, setSchemeDraft] = useState<SchemeDraft>(() => createEmptySchemeDraft());
  const [planDraft, setPlanDraft] = useState<PlanDraft>(EMPTY_PLAN_DRAFT);
  const [modalError, setModalError] = useState<string | null>(null);
  const [isSubmittingScheme, setIsSubmittingScheme] = useState(false);
  const [isSubmittingPlan, setIsSubmittingPlan] = useState(false);
  const [isGeneratingProc, setIsGeneratingProc] = useState(false);
  const [isTrialingProc, setIsTrialingProc] = useState(false);
  const [isGeneratingRecon, setIsGeneratingRecon] = useState(false);
  const [wizardJsonPanel, setWizardJsonPanel] = useState<'proc' | 'recon' | null>(null);
  const [procTrialPreview, setProcTrialPreview] = useState<ProcTrialPreview | null>(null);
  const [reconTrialPreview, setReconTrialPreview] = useState<ReconTrialPreview | null>(null);
  const [procCompatibility, setProcCompatibility] = useState<CompatibilityCheckResult>(emptyCompatibilityResult);
  const [reconCompatibility, setReconCompatibility] = useState<CompatibilityCheckResult>(emptyCompatibilityResult);
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null);

  const sourceById = useMemo(
    () => new Map(availableSources.map((item) => [item.id, item])),
    [availableSources],
  );
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

  const selectedLeftSources = useMemo(
    () => schemeDraft.leftSourceIds.map((id) => sourceById.get(id)).filter(Boolean) as SchemeSourceOption[],
    [schemeDraft.leftSourceIds, sourceById],
  );
  const selectedRightSources = useMemo(
    () => schemeDraft.rightSourceIds.map((id) => sourceById.get(id)).filter(Boolean) as SchemeSourceOption[],
    [schemeDraft.rightSourceIds, sourceById],
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
        name: `${scheme.name} · 数据整理配置`,
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
      .filter((rule) => rule.task_type === 'recon')
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
        name: meta.reconRuleName || `${scheme.name} · 数据对账逻辑`,
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
    () =>
      JSON.stringify(
        schemeDraft.procRuleJson || buildProcJsonPayload(schemeDraft, selectedLeftSources, selectedRightSources),
        null,
        2,
      ),
    [schemeDraft, selectedLeftSources, selectedRightSources],
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
    () =>
      JSON.stringify(
        schemeDraft.reconRuleJson || buildReconJsonPayload(schemeDraft, parsedReconConfig),
        null,
        2,
      ),
    [parsedReconConfig, schemeDraft],
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
      const nextTasks = allTasks.filter((item) => !isTaskMarkedDeleted(item));
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
    } finally {
      setLoadingCenter(false);
    }
  }, [applyCenterPayload, authToken]);

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

  const loadSourceOptions = useCallback(async () => {
    if (!authToken) {
      setAvailableSources([]);
      setSourceLoadError('请先登录并完成数据连接后，再新建对账方案。');
      return;
    }

    setLoadingSources(true);
    setSourceLoadError('');

    try {
      const response = await fetch('/api/data-sources', {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载数据源失败'));
      }

      const rows = Array.isArray(data?.sources)
        ? data.sources
        : Array.isArray(data?.data_sources)
        ? data.data_sources
        : Array.isArray(data?.items)
        ? data.items
        : [];
      const sourceRecords = rows
        .map((item: unknown) => normalizeSourceRecord(item))
        .filter(Boolean) as SchemeSourceRecord[];
      if (sourceRecords.length === 0) {
        setAvailableSources([]);
        setSourceLoadError('当前没有可用数据源，请先到数据连接中完成接入。');
        return;
      }

      const datasetGroups = await Promise.all(
        sourceRecords.map(async (source) => {
          let datasets: SchemeSourceOption[] = [];
          try {
            const datasetResponse = await fetch(`/api/data-sources/${source.id}/datasets`, {
              headers: { Authorization: `Bearer ${authToken}` },
            });
            if (datasetResponse.status !== 404 && datasetResponse.status !== 405 && datasetResponse.status !== 501) {
              const datasetData = await datasetResponse.json().catch(() => ({}));
              if (!datasetResponse.ok) {
                throw new Error(String(datasetData?.detail || datasetData?.message || '加载数据集失败'));
              }
              const datasetRows = Array.isArray(datasetData?.datasets)
                ? datasetData.datasets
                : Array.isArray(datasetData?.data?.datasets)
                ? datasetData.data.datasets
                : Array.isArray(datasetData?.items)
                ? datasetData.items
                : [];
              datasets = datasetRows
                .map((item: unknown) => normalizeSourceDatasetOption(item, source))
                .filter(Boolean) as SchemeSourceOption[];
            }
          } catch {
            datasets = [];
          }
          return datasets;
        }),
      );

      const normalized = datasetGroups.flat().filter((item) => item && item.name) as SchemeSourceOption[];
      if (normalized.length === 0) {
        setAvailableSources([]);
        setSourceLoadError('当前没有可选数据集，请先到数据连接中完成数据集发现或创建。');
        return;
      }

      setAvailableSources(normalized);
    } catch (error) {
      setAvailableSources([]);
      setSourceLoadError(error instanceof Error ? error.message : '加载数据源失败');
    } finally {
      setLoadingSources(false);
    }
  }, [authToken]);

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

      setAvailableProcRules(nextRules);
    } catch {
      setAvailableProcRules([]);
    }
  }, [authToken]);

  useEffect(() => {
    if (mode !== 'center') return;
    void loadCenterData();
    void loadSourceOptions();
    void loadChannelOptions();
    void loadProcRuleOptions();
  }, [loadCenterData, loadChannelOptions, loadProcRuleOptions, loadSourceOptions, mode]);

  useEffect(() => {
    if (modalState?.kind !== 'run-exceptions') return;
    const runId = modalState.run.id;
    if (exceptionsByRunId[runId]) return;
    void loadRunExceptions(runId);
  }, [exceptionsByRunId, loadRunExceptions, modalState]);

  const resetSchemeWizard = useCallback(() => {
    setSchemeWizardStep(1);
    setSchemeDraft(createEmptySchemeDraft());
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
    void loadSourceOptions();
    void loadProcRuleOptions();
  }, [loadProcRuleOptions, loadSourceOptions, resetSchemeWizard]);

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
    setModalState(null);
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, []);

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
      setWizardJsonPanel(null);
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setProcCompatibility(emptyCompatibilityResult());
      setReconCompatibility(emptyCompatibilityResult());
    },
    [],
  );

  const changeSchemeSources = useCallback((side: 'left' | 'right', sourceIds: string[]) => {
    setSchemeDraft((prev) => {
      const key = side === 'left' ? 'leftSourceIds' : 'rightSourceIds';
      if (sameStringSet(prev[key], sourceIds)) {
        return prev;
      }
      return {
        ...prev,
        [key]: sourceIds,
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
      };
    });
    setWizardJsonPanel(null);
    setProcTrialPreview(null);
    setReconTrialPreview(null);
    setProcCompatibility(emptyCompatibilityResult());
    setReconCompatibility(emptyCompatibilityResult());
  }, []);

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
          details: expectedSources.map((item) => item.name),
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
            `当前：${currentSources.map((item) => item.name).join('、')}`,
            `历史：${expectedSources.map((item) => item.name).join('、')}`,
          ],
        };
      }

      return {
        status: 'failed',
        message: `${label}数据集与历史配置差异较大，请更换配置或重新生成。`,
        details: [
          `当前：${currentSources.map((item) => item.name).join('、') || '--'}`,
          `历史：${expectedSources.map((item) => item.name).join('、') || '--'}`,
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
    const preview: ProcTrialPreview = {
      status: failed ? 'needs_adjustment' : 'passed',
      summary: failed
        ? '试跑结果：当前整理配置与所选数据集仍不兼容，请调整后重试。'
        : '试跑结果：左右两侧已生成可对账数据集，关键字段校验通过，可进入对账逻辑配置。',
      rawSources: [
        ...selectedLeftSources.map((source) => ({
          sourceId: source.id,
          sourceName: source.name,
          side: 'left' as const,
          rows: buildRawSourceRows(source, 'left', seedText),
        })),
        ...selectedRightSources.map((source) => ({
          sourceId: source.id,
          sourceName: source.name,
          side: 'right' as const,
          rows: buildRawSourceRows(source, 'right', seedText),
        })),
      ],
      preparedOutputs: failed
        ? []
        : [
            {
              side: 'left',
              title: 'left_recon_ready',
              rows: buildPreparedRows(selectedLeftSources, 'left', seedText),
            },
            {
              side: 'right',
              title: 'right_recon_ready',
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
        const draftText = option.draftText.trim() || (ruleJson ? summarizeProcDraft(ruleJson) : '');
        setSchemeDraft((prev) => ({
          ...prev,
          procConfigMode: 'existing',
          selectedProcConfigId: configId,
          procDraft: draftText,
          procRuleJson: ruleJson,
          procTrialStatus: 'idle',
          procTrialSummary: '',
          reconDraft: '',
          reconRuleJson: null,
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }));
        setProcTrialPreview(null);
        setReconTrialPreview(null);
        setProcCompatibility({
          status: 'idle',
          message: '已载入已有数据整理配置，请点击试跑验证或直接下一步执行兼容性检查。',
          details: [option.name],
        });
        setReconCompatibility(emptyCompatibilityResult());
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '加载已有数据整理配置失败');
      } finally {
        setIsGeneratingProc(false);
      }
    },
    [existingProcOptions, loadRuleJsonByCode],
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
        setReconTrialPreview(null);
        setReconCompatibility(emptyCompatibilityResult());
        return;
      }

      const option = existingReconOptions.find((item) => item.id === configId) || null;
      if (!option) return;

      setIsGeneratingRecon(true);
      try {
        const ruleJson = option.ruleJson || (option.ruleCode ? await loadRuleJsonByCode(option.ruleCode) : null);
        const parsed = ruleJson
          ? parseReconRuleJsonConfig(ruleJson)
          : {
              matchKey: option.matchKey || '',
              leftAmountField: option.leftAmountField || '',
              rightAmountField: option.rightAmountField || '',
              tolerance: option.tolerance || '',
            };
        const draftText = option.draftText.trim() || (ruleJson ? summarizeReconDraft(ruleJson) : '');
        setSchemeDraft((prev) => ({
          ...prev,
          reconConfigMode: 'existing',
          selectedReconConfigId: configId,
          reconDraft: draftText,
          reconRuleJson: ruleJson,
          matchKey: parsed.matchKey,
          leftAmountField: parsed.leftAmountField,
          rightAmountField: parsed.rightAmountField,
          tolerance: parsed.tolerance,
          reconTrialStatus: 'idle',
          reconTrialSummary: '',
        }));
        setReconTrialPreview(null);
        setReconCompatibility({
          status: 'idle',
          message: '已载入已有数据对账逻辑，请点击试跑验证或直接下一步执行兼容性检查。',
          details: [option.name],
        });
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '加载已有数据对账逻辑失败');
      } finally {
        setIsGeneratingRecon(false);
      }
    },
    [existingReconOptions, loadRuleJsonByCode],
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
    setModalError(null);
    try {
      const response = await fetchReconAutoApi('/schemes/design/start', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          scheme_name: schemeDraft.name.trim(),
          biz_goal: schemeDraft.businessGoal.trim(),
          source_description: [
            `左侧数据描述：${schemeDraft.leftDescription.trim() || '--'}`,
            `右侧数据描述：${schemeDraft.rightDescription.trim() || '--'}`,
          ].join('\n'),
          sample_datasets: [
            ...selectedLeftSources.map((item) =>
              buildDatasetSamplePayload(item, 'left', schemeDraft.leftDescription.trim(), schemeDraft.procDraft.trim()),
            ),
            ...selectedRightSources.map((item) =>
              buildDatasetSamplePayload(item, 'right', schemeDraft.rightDescription.trim(), schemeDraft.procDraft.trim()),
            ),
          ],
          initial_message: [
            '只生成proc。',
            '请输出可用于 left_recon_ready / right_recon_ready 的数据整理配置。',
            schemeDraft.procDraft.trim()
              ? `以下是当前的数据整理配置说明，用户已经做过调整，请优先按这个说明重新生成：\n${schemeDraft.procDraft.trim()}`
              : '',
          ]
            .filter(Boolean)
            .join('\n\n'),
          run_trial: false,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || 'AI 生成整理配置失败'));
      }
      const normalizedProcRuleJson = asRecord(data.session?.drafts?.proc_trial_result?.normalized_rule);
      const procRuleJson = Object.keys(normalizedProcRuleJson).length > 0
        ? normalizedProcRuleJson
        : asRecord(data.session?.drafts?.proc_draft_json);
      if (!procRuleJson || !Array.isArray(procRuleJson.steps)) {
        throw new Error('AI 未返回有效的数据整理配置');
      }
      setSchemeDraft((prev) => ({
        ...prev,
        procDraft: summarizeProcDraft(procRuleJson),
        procRuleJson,
        procTrialStatus: 'idle',
        procTrialSummary: '',
        procConfigMode: 'ai',
        selectedProcConfigId: '',
        reconDraft: '',
        reconRuleJson: null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview(null);
      setReconTrialPreview(null);
      setProcCompatibility(emptyCompatibilityResult());
      setReconCompatibility(emptyCompatibilityResult());
    } catch (error) {
      setModalError(error instanceof Error ? error.message : 'AI 生成整理配置失败');
    } finally {
      setIsGeneratingProc(false);
    }
  }, [
    authToken,
    schemeDraft.businessGoal,
    schemeDraft.leftDescription,
    schemeDraft.name,
    schemeDraft.procDraft,
    schemeDraft.rightDescription,
    selectedLeftSources,
    selectedRightSources,
  ]);

  const trialProcDraft = useCallback(async () => {
    setModalError(null);
    const preflight = evaluateProcDraftState();
    setProcCompatibility(preflight.compatibility);
    if (!preflight.passed || !preflight.ruleJson) {
      applyProcEvaluation(preflight);
      return;
    }
    if (!authToken) {
      setModalError('请先登录后再试跑验证。');
      return;
    }

    const seedText =
      preflight.draftText
      || JSON.stringify(preflight.ruleJson, null, 2)
      || schemeDraft.name
      || 'proc';

    setIsTrialingProc(true);
    try {
      const response = await fetchReconAutoApi('/schemes/design/proc-trial', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          proc_rule_json: preflight.ruleJson,
          sample_datasets: [
            ...selectedLeftSources.map((item) =>
              buildDatasetSamplePayload(item, 'left', schemeDraft.leftDescription.trim(), seedText),
            ),
            ...selectedRightSources.map((item) =>
              buildDatasetSamplePayload(item, 'right', schemeDraft.rightDescription.trim(), seedText),
            ),
          ],
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || data.error || '数据整理试跑失败'));
      }

      const normalizedRule = asRecord(data.normalized_rule);
      const rawSources: SourcePreviewBlock[] = Array.isArray(data.source_samples)
        ? data.source_samples
          .filter((item: unknown): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map((item: Record<string, unknown>) => ({
            sourceId: toText(item.source_id, toText(item.table_name, 'source')),
            sourceName: toText(item.display_name, toText(item.table_name, '数据源')),
            side: toText(item.side) === 'right' ? 'right' as const : 'left' as const,
            rows: toPreviewTableRows(item.rows),
          }))
          : preflight.preview.rawSources;
      const preparedOutputs: PreparedPreviewBlock[] = Array.isArray(data.output_samples)
        ? data.output_samples
          .filter((item: unknown): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map((item: Record<string, unknown>) => ({
            side: toText(item.side) === 'right' ? 'right' as const : 'left' as const,
            title: toText(item.title, toText(item.target_table, 'output')),
            rows: toPreviewTableRows(item.rows),
          }))
        : [];
      const details = [
        ...parseTrialMessages(data.errors),
        ...parseTrialMessages(data.warnings),
        ...parseTrialMessages(data.highlights),
      ];
      const readyForConfirm =
        Boolean(data.ready_for_confirm)
        || (
          preparedOutputs.some((item) => item.title === 'left_recon_ready')
          && preparedOutputs.some((item) => item.title === 'right_recon_ready')
        );
      const passed = Boolean(data.success) && readyForConfirm;
      const summary = toText(
        data.summary,
        toText(
          data.message,
          passed
            ? '已完成数据整理试跑，左右两侧对账数据均已生成。'
            : toText(data.error, '数据整理试跑未通过，请调整配置后重试。'),
        ),
      );

      setProcCompatibility({
        status: passed ? 'passed' : 'failed',
        message: passed ? '试跑验证通过，可进入下一步。' : '试跑未通过，请调整数据整理配置后重试。',
        details: details.length > 0 ? details : [summary],
      });
      setSchemeDraft((prev) => ({
        ...prev,
        procDraft: preflight.draftText || prev.procDraft,
        procRuleJson: Object.keys(normalizedRule).length > 0 ? normalizedRule : preflight.ruleJson,
        procTrialStatus: passed ? 'passed' : 'needs_adjustment',
        procTrialSummary: summary,
        reconDraft: passed ? prev.reconDraft : '',
        reconRuleJson: passed ? prev.reconRuleJson : null,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setProcTrialPreview({
        status: passed ? 'passed' : 'needs_adjustment',
        summary,
        rawSources,
        preparedOutputs,
        validations: details,
      });
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
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
      setProcTrialPreview({
        status: 'needs_adjustment',
        summary: message,
        rawSources: preflight.preview.rawSources,
        preparedOutputs: [],
        validations: [message],
      });
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
    } finally {
      setIsTrialingProc(false);
    }
  }, [
    applyProcEvaluation,
    authToken,
    evaluateProcDraftState,
    schemeDraft.leftDescription,
    schemeDraft.name,
    schemeDraft.rightDescription,
    selectedLeftSources,
    selectedRightSources,
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
    const { leftRows, rightRows } = resolvePreparedRowsForRecon();
    const leftSchemaSummary = inferSchemaSummaryFromRows(leftRows);
    const rightSchemaSummary = inferSchemaSummaryFromRows(rightRows);
    if (!leftRows.length || !rightRows.length) {
      setModalError('请先完成数据整理试跑，再生成对账逻辑。');
      return;
    }

    setIsGeneratingRecon(true);
    setModalError(null);
    try {
      const response = await fetchReconAutoApi('/schemes/design/start', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          scheme_name: schemeDraft.name.trim(),
          biz_goal: schemeDraft.businessGoal.trim(),
          source_description: [
            `左侧数据描述：${schemeDraft.leftDescription.trim() || '--'}`,
            `右侧数据描述：${schemeDraft.rightDescription.trim() || '--'}`,
            `左侧整理后抽样：${JSON.stringify(leftRows, null, 2)}`,
            `右侧整理后抽样：${JSON.stringify(rightRows, null, 2)}`,
          ].join('\n'),
          sample_datasets: [
            ...selectedLeftSources.map((item) => ({
              side: 'left',
              dataset_name: item.name,
              dataset_code: item.datasetCode,
              table_name: 'left_recon_ready',
              source_type: 'dataset',
              source_id: item.sourceId,
              source_key: item.sourceId,
              resource_key: item.resourceKey || item.datasetCode || item.name,
              source_kind: item.sourceKind,
              provider_code: item.providerCode,
              description: schemeDraft.leftDescription.trim(),
              schema_summary: leftSchemaSummary,
              sample_rows: leftRows.slice(0, 3),
            })),
            ...selectedRightSources.map((item) => ({
              side: 'right',
              dataset_name: item.name,
              dataset_code: item.datasetCode,
              table_name: 'right_recon_ready',
              source_type: 'dataset',
              source_id: item.sourceId,
              source_key: item.sourceId,
              resource_key: item.resourceKey || item.datasetCode || item.name,
              source_kind: item.sourceKind,
              provider_code: item.providerCode,
              description: schemeDraft.rightDescription.trim(),
              schema_summary: rightSchemaSummary,
              sample_rows: rightRows.slice(0, 3),
            })),
          ],
          initial_message: [
            '只生成recon。',
            '请基于 left_recon_ready 与 right_recon_ready 生成符合现有 recon 引擎定义的对账逻辑。',
            schemeDraft.reconDraft.trim()
              ? `以下是当前的数据对账逻辑说明，用户已经做过调整，请优先按这个说明重新生成：\n${schemeDraft.reconDraft.trim()}`
              : '',
          ].join('\n'),
          run_trial: false,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data.detail || data.message || 'AI 生成对账逻辑失败'));
      }
      const reconRuleJson = asRecord(data.session?.drafts?.recon_draft_json);
      if (!reconRuleJson || !Array.isArray(reconRuleJson.rules) || reconRuleJson.rules.length === 0) {
        throw new Error('AI 未返回有效的数据对账逻辑');
      }
      const nextConfig = parseReconRuleJsonConfig(reconRuleJson);
      setSchemeDraft((prev) => ({
        ...prev,
        reconConfigMode: 'ai',
        selectedReconConfigId: '',
        matchKey: nextConfig.matchKey,
        leftAmountField: nextConfig.leftAmountField,
        rightAmountField: nextConfig.rightAmountField,
        tolerance: nextConfig.tolerance,
        reconDraft: summarizeReconDraft(reconRuleJson),
        reconRuleJson,
        reconTrialStatus: 'idle',
        reconTrialSummary: '',
      }));
      setReconTrialPreview(null);
      setReconCompatibility(emptyCompatibilityResult());
      setWizardJsonPanel(null);
    } catch (error) {
      setModalError(error instanceof Error ? error.message : 'AI 生成对账逻辑失败');
    } finally {
      setIsGeneratingRecon(false);
    }
  }, [
    authToken,
    resolvePreparedRowsForRecon,
    schemeDraft.businessGoal,
    schemeDraft.leftDescription,
    schemeDraft.name,
    schemeDraft.reconDraft,
    schemeDraft.rightDescription,
    selectedLeftSources,
    selectedRightSources,
  ]);

  const trialReconDraft = useCallback(() => {
    setModalError(null);
    applyReconEvaluation(evaluateReconDraftState());
  }, [applyReconEvaluation, evaluateReconDraftState]);

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

    setIsSubmittingScheme(true);
    setModalError(null);

    try {
      const reconRuleName = buildDefaultReconRuleName(schemeDraft.name);
      const procRuleJson =
        schemeDraft.procRuleJson || buildProcJsonPayload(schemeDraft, selectedLeftSources, selectedRightSources);
      const reconRuleJson = {
        ...(schemeDraft.reconRuleJson || buildReconJsonPayload(schemeDraft, parsedReconConfig)),
        rule_id: sanitizeRuleId(reconRuleName, 'DRAFT_RECON_RULE'),
        rule_name: reconRuleName,
      };
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
          scheme_meta_json: {
            business_goal: schemeDraft.businessGoal.trim(),
            left_sources: selectedLeftSources.map((item) => ({
              id: item.id,
              name: item.name,
              source_id: item.sourceId,
              source_name: item.sourceName,
              source_kind: item.sourceKind,
              provider_code: item.providerCode,
              dataset_code: item.datasetCode,
              resource_key: item.resourceKey,
              dataset_kind: item.datasetKind,
            })),
            right_sources: selectedRightSources.map((item) => ({
              id: item.id,
              name: item.name,
              source_id: item.sourceId,
              source_name: item.sourceName,
              source_kind: item.sourceKind,
              provider_code: item.providerCode,
              dataset_code: item.datasetCode,
              resource_key: item.resourceKey,
              dataset_kind: item.datasetKind,
            })),
            left_description: schemeDraft.leftDescription.trim(),
            right_description: schemeDraft.rightDescription.trim(),
            proc_trial_status: schemeDraft.procTrialStatus,
            proc_trial_summary: schemeDraft.procTrialSummary.trim(),
            recon_trial_status: schemeDraft.reconTrialStatus,
            recon_trial_summary: schemeDraft.reconTrialSummary.trim(),
            match_key: parsedReconConfig.matchKey.trim(),
            left_amount_field: parsedReconConfig.leftAmountField.trim(),
            right_amount_field: parsedReconConfig.rightAmountField.trim(),
            tolerance: parsedReconConfig.tolerance.trim(),
            proc_rule_name:
              selectedProcOption?.name
              || (schemeDraft.name.trim() ? `${schemeDraft.name.trim()} · 数据整理配置` : '数据整理配置'),
            recon_rule_name: reconRuleName,
            proc_draft_text: schemeDraft.procDraft.trim(),
            recon_draft_text: schemeDraft.reconDraft.trim(),
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
    const todayStr = new Date().toISOString().slice(0, 10);
    const autoName = `${schemeName} ${todayStr}`;

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
        setModalError('请先登录后再删除对账方案。');
        return;
      }
      const relatedTaskCount = tasks.filter((item) => item.schemeCode === scheme.schemeCode).length;
      if (relatedTaskCount > 0) {
        setModalError(`当前方案下还有 ${relatedTaskCount} 个运行计划，请先删除运行计划后再删除对账方案。`);
        return;
      }
      if (!window.confirm(`确定要删除对账方案「${scheme.name}」吗？此操作不可恢复。`)) {
        return;
      }
      try {
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
        await loadCenterData();
      } catch (error) {
        setModalError(error instanceof Error ? error.message : '删除对账方案失败');
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
  const schemeStepTwoReady =
    schemeDraft.procConfigMode === 'existing'
      ? Boolean(schemeDraft.selectedProcConfigId)
      : Boolean(schemeDraft.procDraft.trim() || schemeDraft.procRuleJson);
  const schemeStepThreeReady =
    (schemeDraft.reconConfigMode === 'existing'
      ? Boolean(schemeDraft.selectedReconConfigId)
      : Boolean(schemeDraft.reconDraft.trim() || schemeDraft.reconRuleJson));

  const goToNextSchemeStep = useCallback(() => {
    setModalError(null);
    if (schemeWizardStep === 1) {
      if (!schemeStepOneReady) {
        setModalError('请先完成方案名称、对账目标以及左右数据集选择。');
        return;
      }
      setSchemeWizardStep(2);
      return;
    }
    if (schemeWizardStep === 2) {
      const result = evaluateProcDraftState();
      if (!result.passed) {
        applyProcEvaluation(result);
        setModalError(result.compatibility.message);
        return;
      }
      setProcCompatibility(result.compatibility);
      if (!(schemeDraft.procTrialStatus === 'passed' && procTrialPreview)) {
        applyProcEvaluation(result);
      }
      setSchemeWizardStep(3);
      return;
    }
    if (schemeWizardStep === 3) {
      const result = evaluateReconDraftState();
      applyReconEvaluation(result);
      if (!result.passed) {
        setModalError(result.compatibility.message);
        return;
      }
      setSchemeWizardStep(4);
    }
  }, [
    applyProcEvaluation,
    applyReconEvaluation,
    evaluateProcDraftState,
    evaluateReconDraftState,
    procTrialPreview,
    schemeStepOneReady,
    schemeDraft.procTrialStatus,
    schemeWizardStep,
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
          const procRuleLabel =
            schemeMeta.procRuleName || (item.name ? `${item.name} · 数据整理配置` : '未命名整理规则');
          const savedDateLabel = formatDateLabel(item.updatedAt || item.createdAt);
          const reconRuleLabel = `${item.name || '未命名对账方案'}${savedDateLabel ? ` · ${savedDateLabel}` : ''}`;
          const reconRuleHint = schemeMeta.reconRuleName || '已保存对账逻辑';
          return (
            <div
              key={item.id}
              className="grid items-center gap-4 border-b border-border-subtle px-5 py-4 last:border-b-0"
              style={{ gridTemplateColumns: SCHEME_LIST_TEMPLATE }}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-text-primary">{item.name}</p>
                <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-secondary">
                  {schemeMeta.businessGoal || item.description || item.schemeCode || '--'}
                </p>
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-text-primary">{procRuleLabel}</p>
                <p className="mt-1 truncate text-xs text-text-secondary">
                  {schemeMeta.procTrialSummary || '已保存整理规则'}
                </p>
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-text-primary">{reconRuleLabel}</p>
                <p className="mt-1 truncate text-xs text-text-secondary">{reconRuleHint}</p>
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
          return (
            <div
              key={item.id}
              className="grid items-center gap-6 border-b border-border-subtle px-5 py-4 last:border-b-0"
              style={{ gridTemplateColumns: TASK_LIST_TEMPLATE }}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-text-primary">{item.name}</p>
                <p className="mt-1 line-clamp-2 text-sm leading-6 text-text-secondary">
                  通道 {resolveChannelProviderLabel(item.channelConfigId)} · 责任人 {item.ownerSummary || '--'}
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
                  {item.executionStatus.trim().toLowerCase() === 'failed' ? (
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
    const mappedProcTrialPreview = procTrialPreview
      ? {
          status: procTrialPreview.status,
          summary: procTrialPreview.summary,
          leftSourceSamples: procTrialPreview.rawSources
            .filter((item) => item.side === 'left')
            .map((item) => ({ title: item.sourceName, rows: item.rows })),
          rightSourceSamples: procTrialPreview.rawSources
            .filter((item) => item.side === 'right')
            .map((item) => ({ title: item.sourceName, rows: item.rows })),
          leftOutputSamples: procTrialPreview.preparedOutputs
            .filter((item) => item.side === 'left')
            .map((item) => ({ title: item.title, rows: item.rows })),
          rightOutputSamples: procTrialPreview.preparedOutputs
            .filter((item) => item.side === 'right')
            .map((item) => ({ title: item.title, rows: item.rows })),
        }
      : undefined;
    const mappedReconTrialPreview = reconTrialPreview
      ? {
          status: reconTrialPreview.status,
          summary: reconTrialPreview.summary,
          leftSamples: reconTrialPreview.leftRows,
          rightSamples: reconTrialPreview.rightRows,
          resultSamples: reconTrialPreview.results.map((item) => ({
            match_key: item.matchKey,
            result: item.result,
            left_amount: item.leftAmount,
            right_amount: item.rightAmount,
            diff_amount: item.diffAmount,
            note: item.note,
          })),
          resultSummary: {
            matched: reconTrialPreview.results.filter((item) => item.result === 'matched').length,
            unmatchedLeft: reconTrialPreview.results.filter((item) => item.result === 'left_only').length,
            unmatchedRight: reconTrialPreview.results.filter((item) => item.result === 'right_only').length,
            diffCount: reconTrialPreview.results.filter((item) => item.result === 'amount_diff').length,
          },
        }
      : undefined;

    if (schemeWizardStep === 1 || schemeWizardStep === 2) {
      return (
        <div className="space-y-5">
          <SchemeWizardTargetProcStep
            step={schemeWizardStep as 1 | 2}
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
            availableSources={availableSources}
            loadingSources={loadingSources}
            sourceLoadError={sourceLoadError}
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
            onChangeSourceSelection={changeSchemeSources}
            onProcConfigModeChange={(mode) => {
              setSchemeDraft((prev) => ({
                ...prev,
                procConfigMode: mode,
                selectedProcConfigId: mode === 'existing' ? prev.selectedProcConfigId : '',
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
            isTrialingProc={isTrialingProc}
            onGenerateProc={generateProcDraft}
            onTrialProc={trialProcDraft}
            onProcDraftChange={(value) => {
              setSchemeDraft((prev) => ({
                ...prev,
                procDraft: value,
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

          {schemeWizardStep === 2 && wizardJsonPanel === 'proc' ? (
            <div className="rounded-3xl border border-border bg-surface-secondary p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-text-primary">PROC JSON</p>
                <button
                  type="button"
                  onClick={handleViewProcJson}
                  className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:border-sky-200 hover:text-sky-700"
                >
                  收起
                </button>
              </div>
              <pre className="mt-3 overflow-x-auto rounded-2xl border border-border bg-surface px-4 py-3 text-xs leading-6 text-text-primary">
                {procJsonPreview}
              </pre>
            </div>
          ) : null}
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
              setSchemeDraft((prev) => {
                const nextConfig = parseReconDraftConfig({
                  reconDraft: value,
                  matchKey: prev.matchKey,
                  leftAmountField: prev.leftAmountField,
                  rightAmountField: prev.rightAmountField,
                  tolerance: prev.tolerance,
                });

                return {
                  ...prev,
                  reconDraft: value,
                  matchKey: nextConfig.matchKey,
                  leftAmountField: nextConfig.leftAmountField,
                  rightAmountField: nextConfig.rightAmountField,
                  tolerance: nextConfig.tolerance,
                  reconRuleJson: buildReconJsonPayload(
                    {
                      ...prev,
                      reconDraft: value,
                      matchKey: nextConfig.matchKey,
                      leftAmountField: nextConfig.leftAmountField,
                      rightAmountField: nextConfig.rightAmountField,
                      tolerance: nextConfig.tolerance,
                    },
                    nextConfig,
                  ),
                  reconTrialStatus: 'idle',
                  reconTrialSummary: '',
                };
              });
              setReconTrialPreview(null);
              setReconCompatibility(emptyCompatibilityResult());
            }}
            onViewReconJson={handleViewReconJson}
            reconJsonPreview={reconJsonPreview}
            reconTrialPreview={mappedReconTrialPreview}
            trialDisabled={
              !(
                (schemeDraft.reconConfigMode === 'existing'
                  ? schemeDraft.selectedReconConfigId
                  : schemeDraft.reconDraft.trim() || schemeDraft.reconRuleJson)
              )
            }
            isGeneratingRecon={isGeneratingRecon}
          />

          {wizardJsonPanel === 'recon' ? (
            <div className="rounded-3xl border border-border bg-surface-secondary p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-text-primary">RECON JSON</p>
                <button
                  type="button"
                  onClick={handleViewReconJson}
                  className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:border-sky-200 hover:text-sky-700"
                >
                  收起
                </button>
              </div>
              <pre className="mt-3 overflow-x-auto rounded-2xl border border-border bg-surface px-4 py-3 text-xs leading-6 text-text-primary">
                {reconJsonPreview}
              </pre>
            </div>
          ) : null}
        </div>
      );
    }

    const procDisplayName =
      selectedProcOption?.name || (schemeDraft.name ? `${schemeDraft.name} · 数据整理配置` : '数据整理配置');
    const reconDisplayName = buildDefaultReconRuleName(schemeDraft.name);

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
                  !schemeStepTwoReady ||
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
              <div className="rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">左侧数据</p>
                <div className="mt-3 space-y-2">
                  {schemeMeta.leftSources.map((source) => (
                    <div key={source.id || source.name} className="rounded-2xl border border-border bg-surface px-4 py-3">
                      <p className="text-sm font-medium text-text-primary">{source.name}</p>
                      <p className="mt-1 text-xs text-text-secondary">
                        {source.sourceName ? `${source.sourceName} · ` : ''}
                        {sourceKindLabel(source.sourceKind)}
                      </p>
                    </div>
                  ))}
                  <p className="text-sm leading-6 text-text-secondary">{schemeMeta.leftDescription || '未补充说明。'}</p>
                </div>
              </div>
              <div className="rounded-3xl border border-border bg-surface-secondary p-4">
                <p className="text-sm font-semibold text-text-primary">右侧数据</p>
                <div className="mt-3 space-y-2">
                  {schemeMeta.rightSources.map((source) => (
                    <div key={source.id || source.name} className="rounded-2xl border border-border bg-surface px-4 py-3">
                      <p className="text-sm font-medium text-text-primary">{source.name}</p>
                      <p className="mt-1 text-xs text-text-secondary">
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
                <div className="grid grid-cols-[minmax(0,2.2fr)_140px_120px_120px_140px] gap-6 border-b border-border-subtle px-5 py-3 text-[11px] font-semibold tracking-[0.14em] text-text-muted">
                  <span>异常内容</span>
                  <span>责任人</span>
                  <span>催办</span>
                  <span>处理进展</span>
                  <span>修复状态</span>
                </div>
                {modalExceptions.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[minmax(0,2.2fr)_140px_120px_120px_140px] items-start gap-6 border-b border-border-subtle px-5 py-4 last:border-b-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text-primary">{item.summary}</p>
                      <p className="mt-1 text-xs leading-5 text-text-secondary">
                        {item.anomalyType || 'unknown'}
                        {item.latestFeedback ? ` · 最新反馈：${item.latestFeedback}` : ''}
                      </p>
                    </div>
                    <span className="text-sm text-text-secondary">{item.ownerName || '--'}</span>
                    <span className="text-sm text-text-secondary">{item.reminderStatus || '--'}</span>
                    <span className="text-sm text-text-secondary">{item.processingStatus || '--'}</span>
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          'rounded-full border px-2.5 py-1 text-xs font-medium',
                          item.isClosed
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                            : 'border-amber-200 bg-amber-50 text-amber-700',
                        )}
                      >
                        {item.fixStatus || (item.isClosed ? '已关闭' : '待修复')}
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
    </div>
  );
}
