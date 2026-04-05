import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ArrowUpRight, ChevronDown, Loader2, X } from 'lucide-react';
import {
  COLLABORATION_CHANNEL_CARDS,
  collaborationProviderLabel,
} from '../../collaborationChannelConfig';
import {
  loadCollaborationChannelDrafts,
  normalizeChannelConfig,
} from '../../collaborationChannelDrafts';
import { sourceKindLabel } from '../../dataSourceConfig';
import type {
  CollaborationChannelListItem,
  CollaborationProvider,
  DataSourceKind,
} from '../../types';
import { cn, type ReconAutoTaskItem, type ReconRuleListItem } from './types';
import { fetchReconAutoApi } from './autoApi';

export interface ReconAutoTaskConfigsProps {
  tasks: ReconAutoTaskItem[];
  availableRules?: ReconRuleListItem[];
  defaultRuleCode?: string | null;
  authToken?: string | null;
  loading?: boolean;
  errorText?: string | null;
  createButtonLabel?: string;
  onCreatedTaskConfig?: () => void | Promise<void>;
  onCreateRule?: () => void;
  onOpenCollaborationChannels?: (provider?: CollaborationProvider) => void;
}

type ScheduleType = 'daily' | 'weekly' | 'monthly';
type SupportedSourceKind = Extract<DataSourceKind, 'platform_oauth' | 'database' | 'api'>;
type WizardStepId = 1 | 2 | 3 | 4 | 5 | 6;
type AssessmentStatus = 'ready' | 'needs_preparation' | 'unknown';
type ValidationStatus = 'idle' | 'running' | 'success' | 'warning' | 'error';

interface RuleInputSlot {
  key: string;
  tableName: string;
  label: string;
}

interface DatasetOption {
  key: string;
  sourceId: string;
  sourceName: string;
  sourceKind: SupportedSourceKind;
  datasetId: string;
  datasetName: string;
  datasetCode: string;
  resourceKey: string;
  fields: string[];
}

interface BindingQueryDraft {
  dayOffset: string;
}

interface TableSchemaRequirement {
  tableName: string;
  requiredColumns: string[];
}

interface LikelyFieldMatch {
  requiredColumn: string;
  candidates: string[];
}

interface BindingAssessment {
  slot: RuleInputSlot;
  option: DatasetOption | null;
  status: AssessmentStatus;
  requiredColumns: string[];
  matchedColumns: string[];
  missingColumns: string[];
  likelyMatches: LikelyFieldMatch[];
  dateField: string;
  suggestions: string[];
}

interface ValidationPreview {
  status: ValidationStatus;
  summary: string;
  checkedAt: string;
  errors: string[];
  warnings: string[];
  highlights: string[];
}

const SUPPORTED_SOURCE_KINDS: SupportedSourceKind[] = ['platform_oauth', 'database', 'api'];

const WEEKDAY_OPTIONS = [
  { value: 'MON', label: '周一' },
  { value: 'TUE', label: '周二' },
  { value: 'WED', label: '周三' },
  { value: 'THU', label: '周四' },
  { value: 'FRI', label: '周五' },
  { value: 'SAT', label: '周六' },
  { value: 'SUN', label: '周日' },
] as const;

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, index) => `${index}`.padStart(2, '0'));
const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, index) => `${index}`.padStart(2, '0'));
const MONTH_DAY_OPTIONS = Array.from({ length: 31 }, (_, index) => String(index + 1));
const WIZARD_STEPS: Array<{ id: WizardStepId; title: string; description: string }> = [
  { id: 1, title: '任务与规则', description: '填写任务名称并绑定规则' },
  { id: 2, title: '数据源', description: '选择对账输入数据源和 T+N' },
  { id: 3, title: '输入准备', description: '判断是否需要先做输入准备' },
  { id: 4, title: '调度设置', description: '选择运行周期和时间' },
  { id: 5, title: '协作与责任人', description: '设置提醒通道和异常处理人' },
  { id: 6, title: '验证并保存', description: '验证配置并决定是否启用任务' },
];

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : fallback;
}

function normalizeSource(raw: unknown): {
  id: string;
  name: string;
  sourceKind: SupportedSourceKind;
} | null {
  const value = asRecord(raw);
  if (!value) return null;

  const id = asString(value.id).trim();
  const sourceKind = asString(value.source_kind).trim() as SupportedSourceKind;
  if (!id || !SUPPORTED_SOURCE_KINDS.includes(sourceKind)) return null;

  return {
    id,
    name: asString(value.name).trim() || id,
    sourceKind,
  };
}

function normalizeDatasetOptions(
  source: { id: string; name: string; sourceKind: SupportedSourceKind },
  rawDatasets: unknown[],
): DatasetOption[] {
  const options: DatasetOption[] = [];

  for (const raw of rawDatasets) {
    const value = asRecord(raw);
    if (!value) continue;

    const datasetId = asString(value.id).trim() || asString(value.dataset_id).trim();
    const datasetCode = asString(value.dataset_code).trim() || asString(value.code).trim();
    const datasetName =
      asString(value.dataset_name).trim() || asString(value.name).trim() || datasetCode || datasetId;
    if (!datasetId && !datasetCode && !datasetName) continue;

    const status = asString(value.status).trim().toLowerCase();
    const isEnabledValue = value.is_enabled;
    const isEnabled =
      typeof isEnabledValue === 'boolean'
        ? isEnabledValue
        : typeof value.enabled === 'boolean'
          ? Boolean(value.enabled)
          : true;
    if (status === 'deleted' || isEnabled === false) continue;

    const normalizedDatasetId = datasetId || datasetCode || datasetName;
    const schemaSummary = asRecord(value.schema_summary);
    const extractConfig = asRecord(value.extract_config);
    const schemaColumns = Array.isArray(schemaSummary?.columns) ? schemaSummary.columns : [];
    const apiParameters = Array.isArray(extractConfig?.parameters) ? extractConfig.parameters : [];
    const fieldNames = Array.from(
      new Set(
        [...schemaColumns, ...apiParameters]
          .map((item) => {
            const field = asRecord(item);
            return (
              asString(field?.name).trim() ||
              asString(field?.column_name).trim() ||
              asString(field?.field_name).trim() ||
              asString(field?.key).trim()
            );
          })
          .filter(Boolean),
      ),
    );
    options.push({
      key: `${source.id}::${normalizedDatasetId}`,
      sourceId: source.id,
      sourceName: source.name,
      sourceKind: source.sourceKind,
      datasetId: normalizedDatasetId,
      datasetName,
      datasetCode: datasetCode || normalizedDatasetId,
      resourceKey:
        asString(value.resource_key).trim() || datasetCode || datasetName || normalizedDatasetId,
      fields: fieldNames,
    });
  }

  return options;
}

function extractReconInputSlots(rulePayload: unknown): RuleInputSlot[] {
  const root = asRecord(rulePayload) ?? {};
  const resolvedRule =
    Array.isArray(root.rules) && root.rules.length > 0 ? (asRecord(root.rules[0]) ?? root) : root;

  const slots: RuleInputSlot[] = [];
  const sourceFile = asRecord(resolvedRule.source_file);
  const targetFile = asRecord(resolvedRule.target_file);

  const sourceTableName = asString(sourceFile?.table_name).trim();
  if (sourceTableName) {
    slots.push({
      key: 'source_file',
      tableName: sourceTableName,
      label: sourceTableName,
    });
  }

  const targetTableName = asString(targetFile?.table_name).trim();
  if (targetTableName) {
    slots.push({
      key: 'target_file',
      tableName: targetTableName,
      label: targetTableName,
    });
  }

  return slots;
}

function extractTableSchemaMap(rulePayload: unknown): Record<string, TableSchemaRequirement> {
  const root = asRecord(rulePayload) ?? {};
  const validationRules = asRecord(root.file_validation_rules);
  const schemas = Array.isArray(validationRules?.table_schemas) ? validationRules?.table_schemas : [];
  return schemas.reduce<Record<string, TableSchemaRequirement>>((result, rawSchema) => {
    const schema = asRecord(rawSchema);
    const tableName = asString(schema?.table_name).trim();
    if (!tableName) return result;
    const requiredColumns = Array.isArray(schema?.required_columns)
      ? schema.required_columns.map((column) => asString(column).trim()).filter(Boolean)
      : [];
    result[tableName] = {
      tableName,
      requiredColumns,
    };
    return result;
  }, {});
}

function buildScheduleExpr(
  scheduleType: ScheduleType,
  hour: string,
  minute: string,
  weekday: string,
  monthDay: string,
): string {
  if (scheduleType === 'weekly') {
    return `${weekday} ${hour}:${minute}`;
  }
  if (scheduleType === 'monthly') {
    return `${monthDay} ${hour}:${minute}`;
  }
  return `${hour}:${minute}`;
}

function formatScheduleSummary(
  scheduleType: ScheduleType,
  hour: string,
  minute: string,
  weekday: string,
  monthDay: string,
): string {
  if (scheduleType === 'weekly') {
    const label = WEEKDAY_OPTIONS.find((item) => item.value === weekday)?.label || weekday;
    return `每周 ${label} ${hour}:${minute}`;
  }
  if (scheduleType === 'monthly') {
    return `每月 ${monthDay} 号 ${hour}:${minute}`;
  }
  return `每日 ${hour}:${minute}`;
}

function sourceLabel(kind: SupportedSourceKind): string {
  return kind === 'platform_oauth' ? '电商平台' : sourceKindLabel(kind);
}

function buildInitialRuleCode(
  rules: ReconRuleListItem[],
  defaultRuleCode?: string | null,
): string {
  return defaultRuleCode || rules[0]?.rule_code || '';
}

function SelectField({
  value,
  onChange,
  children,
  className,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <div className={cn('relative mt-2', className)}>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'w-full appearance-none rounded-xl border border-border bg-surface-secondary px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-sky-300',
          disabled ? 'cursor-not-allowed opacity-60' : '',
        )}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
    </div>
  );
}

function datasetOptionLabel(option: DatasetOption): string {
  return `[${sourceLabel(option.sourceKind)}] ${option.sourceName} / ${option.datasetName}`;
}

function createEmptyBindingQuery(): BindingQueryDraft {
  return {
    dayOffset: '0',
  };
}

function suggestTimeField(fields: string[]): string {
  return fields.find((field) => /date|time|dt|日期|时间|账期|业务日期|交易日/i.test(field)) || '';
}

function formatDayOffset(offset: number): string {
  if (offset === 0) return 'T';
  if (offset > 0) return `T+${offset}`;
  return `T${offset}`;
}

function parseDayOffset(value: string): number | null {
  const text = value.trim();
  if (!text) return 0;
  if (!/^-?\d+$/.test(text)) return null;
  return Number.parseInt(text, 10);
}

function summarizeBindingScope(bindingQuery: BindingQueryDraft | undefined): string[] {
  if (!bindingQuery) return [];
  const offset = parseDayOffset(bindingQuery.dayOffset);
  if (offset === null) return [];
  return [`取数日期：${formatDayOffset(offset)}`];
}

function normalizeCompareText(value: string): string {
  return value.replace(/[\s_./\\\-()[\]{}【】（）]/g, '').toLowerCase();
}

function findLikelyFieldMatches(requiredColumn: string, fields: string[]): string[] {
  const requiredText = normalizeCompareText(requiredColumn);
  if (!requiredText) return [];
  return fields
    .filter((field) => {
      const fieldText = normalizeCompareText(field);
      if (!fieldText) return false;
      return (
        fieldText.includes(requiredText) ||
        requiredText.includes(fieldText) ||
        field.includes(requiredColumn) ||
        requiredColumn.includes(field)
      );
    })
    .slice(0, 3);
}

function assessBinding(
  slot: RuleInputSlot,
  option: DatasetOption | null,
  schemaMap: Record<string, TableSchemaRequirement>,
): BindingAssessment {
  if (!option) {
    return {
      slot,
      option: null,
      status: 'unknown',
      requiredColumns: [],
      matchedColumns: [],
      missingColumns: [],
      likelyMatches: [],
      dateField: '',
      suggestions: ['请先为这个输入选择一个数据源。'],
    };
  }

  const schema = schemaMap[slot.tableName];
  const dateField = suggestTimeField(option.fields);
  if (!schema) {
    const suggestions = ['当前规则没有配置这一输入的结构要求，建议首次运行前人工确认字段是否能直接用于对账。'];
    if (!dateField) {
      suggestions.push('当前数据源未识别到日期字段，T+N 自动取数可能无法执行。');
    }
    return {
      slot,
      option,
      status: 'unknown',
      requiredColumns: [],
      matchedColumns: [],
      missingColumns: [],
      likelyMatches: [],
      dateField,
      suggestions,
    };
  }

  const fieldMap = new Map<string, string>();
  option.fields.forEach((field) => {
    fieldMap.set(field, field);
    fieldMap.set(normalizeCompareText(field), field);
  });

  const matchedColumns: string[] = [];
  const missingColumns: string[] = [];
  const likelyMatches: LikelyFieldMatch[] = [];

  schema.requiredColumns.forEach((column) => {
    const matched = fieldMap.get(column) || fieldMap.get(normalizeCompareText(column));
    if (matched) {
      matchedColumns.push(column);
      return;
    }
    missingColumns.push(column);
    const candidates = findLikelyFieldMatches(column, option.fields);
    if (candidates.length > 0) {
      likelyMatches.push({ requiredColumn: column, candidates });
    }
  });

  const suggestions: string[] = [];
  if (missingColumns.length > 0) {
    suggestions.push(`缺少规则要求字段：${missingColumns.join('、')}`);
  }
  if (likelyMatches.length > 0) {
    suggestions.push(
      `可优先确认字段映射：${likelyMatches
        .map((item) => `${item.requiredColumn} -> ${item.candidates.join(' / ')}`)
        .join('；')}`,
    );
  }
  if (!dateField) {
    suggestions.push('当前数据源未识别到日期字段，无法按 T+N 自动取数。');
  }
  if (suggestions.length === 0) {
    suggestions.push('字段结构可直接用于当前规则。');
  }

  return {
    slot,
    option,
    status: missingColumns.length === 0 && Boolean(dateField) ? 'ready' : 'needs_preparation',
    requiredColumns: schema.requiredColumns,
    matchedColumns,
    missingColumns,
    likelyMatches,
    dateField,
    suggestions,
  };
}

function statusLabel(status: AssessmentStatus): string {
  if (status === 'ready') return '可直接使用';
  if (status === 'needs_preparation') return '建议先做输入准备';
  return '待人工确认';
}

function statusClassName(status: AssessmentStatus): string {
  if (status === 'ready') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'needs_preparation') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-slate-200 bg-slate-100 text-slate-700';
}

export default function ReconAutoTaskConfigs({
  tasks,
  availableRules = [],
  defaultRuleCode = null,
  authToken = null,
  loading = false,
  errorText = null,
  createButtonLabel = '新建任务配置',
  onCreatedTaskConfig,
  onCreateRule,
  onOpenCollaborationChannels,
}: ReconAutoTaskConfigsProps) {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [currentStep, setCurrentStep] = useState<WizardStepId>(1);
  const [validationPreview, setValidationPreview] = useState<ValidationPreview | null>(null);
  const [inputPreparationConfirmed, setInputPreparationConfirmed] = useState(false);

  const [taskName, setTaskName] = useState('');
  const [ruleCode, setRuleCode] = useState('');
  const [scheduleType, setScheduleType] = useState<ScheduleType>('daily');
  const [scheduleHour, setScheduleHour] = useState('12');
  const [scheduleMinute, setScheduleMinute] = useState('30');
  const [scheduleWeekday, setScheduleWeekday] = useState('MON');
  const [scheduleMonthDay, setScheduleMonthDay] = useState('1');
  const [isEnabled, setIsEnabled] = useState(true);
  const [defaultOwnerName, setDefaultOwnerName] = useState('');
  const [defaultOwnerMobile, setDefaultOwnerMobile] = useState('');

  const [ruleInputSlots, setRuleInputSlots] = useState<RuleInputSlot[]>([]);
  const [loadingRuleInputs, setLoadingRuleInputs] = useState(false);
  const [ruleInputError, setRuleInputError] = useState('');
  const [tableSchemaMap, setTableSchemaMap] = useState<Record<string, TableSchemaRequirement>>({});
  const [loadingTableSchemas, setLoadingTableSchemas] = useState(false);
  const [tableSchemaError, setTableSchemaError] = useState('');

  const [datasetOptions, setDatasetOptions] = useState<DatasetOption[]>([]);
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [datasetLoadError, setDatasetLoadError] = useState('');
  const [selectedDatasetKeys, setSelectedDatasetKeys] = useState<Record<string, string>>({});
  const [bindingQueries, setBindingQueries] = useState<Record<string, BindingQueryDraft>>({});
  const [channelOptions, setChannelOptions] = useState<CollaborationChannelListItem[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [channelLoadError, setChannelLoadError] = useState('');
  const [selectedChannelId, setSelectedChannelId] = useState('');

  const ruleOptions = useMemo(
    () => availableRules.filter((rule) => rule.task_type === 'recon'),
    [availableRules],
  );

  const selectedRule = useMemo(
    () => ruleOptions.find((rule) => rule.rule_code === ruleCode) || null,
    [ruleCode, ruleOptions],
  );

  const channelOptionMap = useMemo(() => {
    const map = new Map<string, CollaborationChannelListItem>();
    channelOptions.forEach((option) => {
      map.set(option.id, option);
    });
    return map;
  }, [channelOptions]);

  const channelSetupCards = useMemo(() => COLLABORATION_CHANNEL_CARDS.slice(0, 3), []);

  const datasetOptionMap = useMemo(() => {
    const map = new Map<string, DatasetOption>();
    datasetOptions.forEach((option) => {
      map.set(option.key, option);
    });
    return map;
  }, [datasetOptions]);

  const datasetOptionsByKind = useMemo(() => {
    return SUPPORTED_SOURCE_KINDS.map((kind) => ({
      kind,
      options: datasetOptions.filter((option) => option.sourceKind === kind),
    })).filter((group) => group.options.length > 0);
  }, [datasetOptions]);

  const selectedBindingsPreview = useMemo(() => {
    return ruleInputSlots
      .map((slot) => {
        const option = datasetOptionMap.get(selectedDatasetKeys[slot.key] || '');
        if (!option) return null;
        return {
          slot,
          option,
          scope: summarizeBindingScope(bindingQueries[slot.key]),
        };
      })
      .filter(Boolean) as Array<{ slot: RuleInputSlot; option: DatasetOption; scope: string[] }>;
  }, [bindingQueries, datasetOptionMap, ruleInputSlots, selectedDatasetKeys]);

  const bindingAssessments = useMemo(() => {
    return ruleInputSlots.map((slot) => {
      const option = datasetOptionMap.get(selectedDatasetKeys[slot.key] || '') || null;
      return assessBinding(slot, option, tableSchemaMap);
    });
  }, [datasetOptionMap, ruleInputSlots, selectedDatasetKeys, tableSchemaMap]);

  const shouldSkipPreparationStep = useMemo(() => {
    return bindingAssessments.length > 0 && bindingAssessments.every((item) => item.status === 'ready');
  }, [bindingAssessments]);

  const visibleStepIds = useMemo<WizardStepId[]>(() => {
    return shouldSkipPreparationStep ? [1, 2, 4, 5, 6] : [1, 2, 3, 4, 5, 6];
  }, [shouldSkipPreparationStep]);

  const visibleSteps = useMemo(
    () => WIZARD_STEPS.filter((step) => visibleStepIds.includes(step.id)),
    [visibleStepIds],
  );

  const currentStepIndex = visibleStepIds.indexOf(currentStep);
  const currentStepMeta = visibleSteps[currentStepIndex] || visibleSteps[0];
  const nextStepId = currentStepIndex >= 0 ? visibleStepIds[currentStepIndex + 1] : undefined;
  const previousStepId = currentStepIndex > 0 ? visibleStepIds[currentStepIndex - 1] : undefined;

  const preparationSummary = useMemo(() => {
    const readyCount = bindingAssessments.filter((item) => item.status === 'ready').length;
    const prepareCount = bindingAssessments.filter((item) => item.status === 'needs_preparation').length;
    const unknownCount = bindingAssessments.filter((item) => item.status === 'unknown').length;
    return { readyCount, prepareCount, unknownCount };
  }, [bindingAssessments]);

  const configurationSignature = useMemo(
    () =>
      JSON.stringify({
        taskName,
        ruleCode,
        selectedDatasetKeys,
        bindingQueries,
        scheduleType,
        scheduleHour,
        scheduleMinute,
        scheduleWeekday,
        scheduleMonthDay,
        selectedChannelId,
        defaultOwnerName,
        defaultOwnerMobile,
        isEnabled,
      }),
    [
      bindingQueries,
      defaultOwnerMobile,
      defaultOwnerName,
      isEnabled,
      ruleCode,
      scheduleHour,
      scheduleMinute,
      scheduleMonthDay,
      scheduleType,
      scheduleWeekday,
      selectedChannelId,
      selectedDatasetKeys,
      taskName,
    ],
  );

  const resetForm = () => {
    setTaskName('');
    setRuleCode(buildInitialRuleCode(ruleOptions, defaultRuleCode));
    setScheduleType('daily');
    setScheduleHour('12');
    setScheduleMinute('30');
    setScheduleWeekday('MON');
    setScheduleMonthDay('1');
    setIsEnabled(true);
    setDefaultOwnerName('');
    setDefaultOwnerMobile('');
    setSelectedChannelId(channelOptions.find((item) => item.is_default)?.id || channelOptions[0]?.id || '');
    setSelectedDatasetKeys({});
    setBindingQueries({});
    setCurrentStep(1);
    setValidationPreview(null);
    setInputPreparationConfirmed(false);
    setTableSchemaMap({});
    setTableSchemaError('');
  };

  useEffect(() => {
    if (!isCreateOpen) {
      document.body.style.overflow = 'unset';
      return undefined;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsCreateOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isCreateOpen]);

  useEffect(() => {
    setSelectedDatasetKeys((previous) => {
      const next: Record<string, string> = {};
      ruleInputSlots.forEach((slot) => {
        next[slot.key] = previous[slot.key] || '';
      });
      return next;
    });
  }, [ruleInputSlots]);

  useEffect(() => {
    setBindingQueries((previous) => {
      const next: Record<string, BindingQueryDraft> = {};
      ruleInputSlots.forEach((slot) => {
        next[slot.key] = previous[slot.key] || createEmptyBindingQuery();
      });
      return next;
    });
  }, [ruleInputSlots]);

  useEffect(() => {
    if (!isCreateOpen || !authToken || !ruleCode) {
      if (!isCreateOpen) {
        setRuleInputSlots([]);
        setRuleInputError('');
        setTableSchemaMap({});
        setTableSchemaError('');
      }
      return;
    }

    let cancelled = false;

    const loadRuleInputs = async () => {
      setLoadingRuleInputs(true);
      setLoadingTableSchemas(true);
      setRuleInputError('');
      setTableSchemaError('');
      try {
        const response = await fetch(`/api/proc/get_file_validation_rule?rule_code=${encodeURIComponent(ruleCode)}`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data?.success === false) {
          throw new Error(String(data?.detail || data?.message || '读取规则详情失败'));
        }

        const dataRecord = asRecord(data?.data);
        const rulePayload = dataRecord?.rule;
        const slots = extractReconInputSlots(rulePayload);
        const directSchemaMap = extractTableSchemaMap(rulePayload);

        if (!cancelled) {
          setRuleInputSlots(slots);
          if (slots.length === 0) {
            setRuleInputError('当前规则未解析到对账输入表，请先完善规则后再创建自动任务。');
          }
          if (Object.keys(directSchemaMap).length > 0) {
            setTableSchemaMap(directSchemaMap);
          } else {
            setTableSchemaMap({});
          }
        }

        const fallbackFileRuleCode = asString(dataRecord?.file_rule_code).trim();
        const fileRuleCode = selectedRule?.file_rule_code?.trim() || fallbackFileRuleCode;
        if (Object.keys(directSchemaMap).length > 0 || !fileRuleCode) {
          if (!cancelled && !fileRuleCode && Object.keys(directSchemaMap).length === 0) {
            setTableSchemaError('当前规则未配置输入结构规则，后续会按数据源字段做基础判断。');
          }
          return;
        }

        const fileRuleResponse = await fetch(
          `/api/proc/get_file_validation_rule?rule_code=${encodeURIComponent(fileRuleCode)}`,
          {
            headers: { Authorization: `Bearer ${authToken}` },
          },
        );
        const fileRuleData = await fileRuleResponse.json().catch(() => ({}));
        if (!fileRuleResponse.ok || fileRuleData?.success === false) {
          throw new Error(String(fileRuleData?.detail || fileRuleData?.message || '读取输入结构规则失败'));
        }

        const fileRulePayload = asRecord(fileRuleData?.data)?.rule;
        const schemaMap = extractTableSchemaMap(fileRulePayload);
        if (!cancelled) {
          setTableSchemaMap(schemaMap);
          if (Object.keys(schemaMap).length === 0) {
            setTableSchemaError('当前规则已绑定输入结构规则，但未识别到 required_columns。');
          }
        }
      } catch (error) {
        if (!cancelled) {
          setRuleInputSlots([]);
          setTableSchemaMap({});
          setRuleInputError(error instanceof Error ? error.message : '读取规则详情失败');
        }
      } finally {
        if (!cancelled) {
          setLoadingRuleInputs(false);
          setLoadingTableSchemas(false);
        }
      }
    };

    void loadRuleInputs();
    return () => {
      cancelled = true;
    };
  }, [authToken, isCreateOpen, ruleCode, selectedRule?.file_rule_code]);

  useEffect(() => {
    if (!isCreateOpen || !authToken) {
      if (!isCreateOpen) {
        setDatasetOptions([]);
        setDatasetLoadError('');
      }
      return;
    }

    let cancelled = false;

    const loadDatasets = async () => {
      setLoadingDatasets(true);
      setDatasetLoadError('');
      try {
        const sourcesResponse = await fetch('/api/data-sources', {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const sourcesData = await sourcesResponse.json().catch(() => ({}));
        if (!sourcesResponse.ok) {
          throw new Error(String(sourcesData?.detail || sourcesData?.message || '加载数据源失败'));
        }

        const rawSources = Array.isArray(sourcesData?.sources)
          ? sourcesData.sources
          : Array.isArray(sourcesData?.data_sources)
            ? sourcesData.data_sources
            : Array.isArray(sourcesData?.items)
              ? sourcesData.items
              : [];
        const sources = rawSources
          .map((item: unknown) => normalizeSource(item))
          .filter(Boolean) as Array<{ id: string; name: string; sourceKind: SupportedSourceKind }>;

        const datasetResultGroups = await Promise.all(
          sources.map(async (source) => {
            const response = await fetch(`/api/data-sources/${source.id}/datasets`, {
              headers: { Authorization: `Bearer ${authToken}` },
            });

            if (!response.ok) {
              return [];
            }

            const data = await response.json().catch(() => ({}));
            const rawDatasets = Array.isArray(data?.datasets)
              ? data.datasets
              : Array.isArray(data?.items)
                ? data.items
                : [];
            return normalizeDatasetOptions(source, rawDatasets);
          }),
        );

        const nextOptions = datasetResultGroups
          .flat()
          .sort((left, right) =>
            `${left.sourceKind}-${left.sourceName}-${left.datasetName}`.localeCompare(
              `${right.sourceKind}-${right.sourceName}-${right.datasetName}`,
              'zh-CN',
            ),
          );

        if (!cancelled) {
          setDatasetOptions(nextOptions);
          if (nextOptions.length === 0) {
            setDatasetLoadError('当前还没有可用的数据集，请先在数据连接中启用电商平台、数据库或 API 数据集。');
          }
        }
      } catch (error) {
        if (!cancelled) {
          setDatasetOptions([]);
          setDatasetLoadError(error instanceof Error ? error.message : '加载数据集失败');
        }
      } finally {
        if (!cancelled) {
          setLoadingDatasets(false);
        }
      }
    };

    void loadDatasets();
    return () => {
      cancelled = true;
    };
  }, [authToken, isCreateOpen]);

  useEffect(() => {
    if (!authToken) {
      setChannelOptions([]);
      setChannelLoadError('');
      return;
    }

    let cancelled = false;

    const loadChannels = async () => {
      setLoadingChannels(true);
      setChannelLoadError('');
      try {
        const localDraftChannels = loadCollaborationChannelDrafts().filter((item) => item.is_enabled !== false);
        const response = await fetch('/api/collaboration-channels', {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        if (response.status === 404 || response.status === 405 || response.status === 501) {
          if (!cancelled) {
            setChannelOptions(localDraftChannels);
            setSelectedChannelId((previous) => {
              if (previous && localDraftChannels.some((item) => item.id === previous)) {
                return previous;
              }
              const defaultChannel = localDraftChannels.find((item) => item.is_default);
              return defaultChannel?.id || localDraftChannels[0]?.id || '';
            });
            setChannelLoadError(
              localDraftChannels.length > 0
                ? '当前展示的是本地草稿协作通道，接入服务端接口后可统一托管。'
                : '请先连接一个协作通道，保存后再回来选择。',
            );
          }
          return;
        }

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
        const normalized = rows
          .map((item: unknown) => normalizeChannelConfig(item))
          .filter(Boolean) as CollaborationChannelListItem[];
        const mergedChannels = [...normalized, ...localDraftChannels].reduce<CollaborationChannelListItem[]>(
          (result, item) => {
            if (result.some((existing) => existing.id === item.id)) return result;
            result.push(item);
            return result;
          },
          [],
        );
        const enabledChannels = mergedChannels.filter((item) => item.is_enabled !== false);

        if (!cancelled) {
          setChannelOptions(enabledChannels);
          setSelectedChannelId((previous) => {
            if (previous && enabledChannels.some((item) => item.id === previous)) {
              return previous;
            }
            const defaultChannel = enabledChannels.find((item) => item.is_default);
            return defaultChannel?.id || enabledChannels[0]?.id || '';
          });
          if (enabledChannels.length === 0) {
            setChannelLoadError('请先连接并启用一个协作通道。');
          } else if (normalized.length === 0 && localDraftChannels.length > 0) {
            setChannelLoadError('当前展示的是本地草稿协作通道，接入服务端接口后可统一托管。');
          }
        }
      } catch (error) {
        if (!cancelled) {
          const localDraftChannels = loadCollaborationChannelDrafts().filter((item) => item.is_enabled !== false);
          setChannelOptions(localDraftChannels);
          setSelectedChannelId((previous) => {
            if (previous && localDraftChannels.some((item) => item.id === previous)) {
              return previous;
            }
            const defaultChannel = localDraftChannels.find((item) => item.is_default);
            return defaultChannel?.id || localDraftChannels[0]?.id || '';
          });
          setChannelLoadError(
            localDraftChannels.length > 0
              ? '协作通道服务暂不可用，当前先使用本地草稿通道。'
              : error instanceof Error
                ? error.message
                : '加载协作通道失败',
          );
        }
      } finally {
        if (!cancelled) {
          setLoadingChannels(false);
        }
      }
    };

    void loadChannels();
    return () => {
      cancelled = true;
    };
  }, [authToken]);

  useEffect(() => {
    if (!isCreateOpen) return;
    setValidationPreview(null);
  }, [configurationSignature, isCreateOpen]);

  useEffect(() => {
    if (!isCreateOpen) return;
    if (shouldSkipPreparationStep && currentStep === 3) {
      setCurrentStep(4);
    }
  }, [currentStep, isCreateOpen, shouldSkipPreparationStep]);

  useEffect(() => {
    if (!isCreateOpen) return;
    setInputPreparationConfirmed(false);
  }, [bindingAssessments, isCreateOpen]);

  const handleCreate = () => {
    resetForm();
    setSubmitError(null);
    setSuccessNotice(null);
    setRuleInputError('');
    setDatasetLoadError('');
    setIsCreateOpen(true);
  };

  const handleCloseModal = () => {
    if (isSaving) return;
    setIsCreateOpen(false);
    setSubmitError(null);
  };

  const handleOpenCreateRule = () => {
    if (isSaving) return;
    handleCloseModal();
    onCreateRule?.();
  };

  const resolveInputBindings = () => {
    return ruleInputSlots.map((slot) => {
      const selectedKey = selectedDatasetKeys[slot.key] || '';
      const option = datasetOptionMap.get(selectedKey);
      if (!option) {
        throw new Error(`请为「${slot.label}」选择数据源。`);
      }
      const bindingQuery = bindingQueries[slot.key] || createEmptyBindingQuery();
      const dayOffset = parseDayOffset(bindingQuery.dayOffset);
      if (dayOffset === null) {
        throw new Error(`请输入合法的 T+N 参数：${slot.label}`);
      }
      const dateField = suggestTimeField(option.fields);
      if (!dateField) {
        throw new Error(`数据源「${option.datasetName}」未识别到日期字段，暂不支持按 T+N 自动取数。`);
      }
      return {
        data_source_id: option.sourceId,
        table_name: slot.tableName,
        resource_key: option.resourceKey || 'default',
        dataset_source_type: 'snapshot',
        query: {
          biz_date_filter: {
            field: dateField,
            offset_days: dayOffset,
          },
        },
      };
    });
  };

  const getStepError = (stepId: WizardStepId): string | null => {
    if (stepId === 1) {
      if (!taskName.trim()) return '请先填写任务名称。';
      if (!ruleCode) return '请选择要绑定的对账规则。';
      if (loadingRuleInputs) return '正在读取规则输入，请稍候。';
      if (ruleInputError) return ruleInputError;
      if (ruleInputSlots.length === 0) return '当前规则未配置对账输入，暂时无法创建自动任务。';
      return null;
    }

    if (stepId === 2) {
      if (loadingDatasets) return '正在加载数据源，请稍候。';
      if (ruleInputSlots.length === 0) return '请先完成任务与规则配置。';
      for (const slot of ruleInputSlots) {
        if (!selectedDatasetKeys[slot.key]) {
          return `请为「${slot.label}」选择数据源。`;
        }
        const dayOffset = parseDayOffset((bindingQueries[slot.key] || createEmptyBindingQuery()).dayOffset);
        if (dayOffset === null) {
          return `请输入合法的 T+N 参数：${slot.label}`;
        }
      }
      return null;
    }

    if (stepId === 3) {
      if (loadingTableSchemas) return '正在分析输入结构，请稍候。';
      if (!inputPreparationConfirmed) {
        return '请先确认输入准备建议，或返回上一步调整数据源。';
      }
      return null;
    }

    if (stepId === 5) {
      if (loadingChannels) return '正在加载协作通道，请稍候。';
      if (!selectedChannelId) return '请选择协作通道。';
      if (!defaultOwnerName.trim()) return '请输入对账异常处理人。';
      return null;
    }

    if (stepId === 6) {
      if (!validationPreview) return '请先运行一次验证。';
      if (validationPreview.status === 'running') return '验证进行中，请稍候。';
      if (validationPreview.status === 'error') return '验证未通过，请先修正问题后再保存。';
    }

    return null;
  };

  const handleNextStep = () => {
    const stepError = getStepError(currentStep);
    if (stepError) {
      setSubmitError(stepError);
      return;
    }
    setSubmitError(null);
    if (nextStepId) {
      setCurrentStep(nextStepId);
    }
  };

  const handleRunValidation = async () => {
    setSubmitError(null);
    setValidationPreview({
      status: 'running',
      summary: '正在验证当前任务配置...',
      checkedAt: '',
      errors: [],
      warnings: [],
      highlights: [],
    });

    const errors: string[] = [];
    const warnings: string[] = [];
    const highlights: string[] = [];

    if (!taskName.trim()) {
      errors.push('缺少任务名称。');
    }
    if (!ruleCode) {
      errors.push('缺少绑定规则。');
    }
    if (ruleInputError) {
      errors.push(ruleInputError);
    }
    if (ruleInputSlots.length === 0) {
      errors.push('当前规则没有识别到可用的对账输入。');
    }
    if (!selectedChannelId) {
      errors.push('缺少协作通道。');
    }
    if (!defaultOwnerName.trim()) {
      errors.push('缺少对账异常处理人。');
    }

    try {
      const bindings = resolveInputBindings();
      highlights.push(`已绑定 ${bindings.length} 个输入数据源。`);
    } catch (error) {
      errors.push(error instanceof Error ? error.message : '输入数据源校验失败。');
    }

    if (tableSchemaError) {
      warnings.push(tableSchemaError);
    }
    if (datasetLoadError && selectedBindingsPreview.length === 0) {
      warnings.push(datasetLoadError);
    }
    if (channelLoadError && !selectedChannelId) {
      warnings.push(channelLoadError);
    }

    bindingAssessments.forEach((assessment) => {
      if (!assessment.option) return;
      if (assessment.status === 'needs_preparation') {
        warnings.push(`「${assessment.slot.label}」建议先做输入准备：${assessment.suggestions.join('；')}`);
      } else if (assessment.status === 'unknown') {
        warnings.push(`「${assessment.slot.label}」暂无法自动确认字段完全匹配，建议首跑前人工确认。`);
      }
      if (assessment.dateField) {
        highlights.push(`「${assessment.slot.label}」将使用字段「${assessment.dateField}」做 T+N 取数。`);
      }
    });

    const checkedAt = new Date().toLocaleString('zh-CN', { hour12: false });
    const status: ValidationStatus =
      errors.length > 0 ? 'error' : warnings.length > 0 ? 'warning' : 'success';
    const summary =
      status === 'error'
        ? '验证未通过，请先修正关键问题。'
        : status === 'warning'
          ? '验证通过，但存在需要你确认的建议。'
          : '验证通过，可以直接保存并启用任务。';

    setValidationPreview({
      status,
      summary,
      checkedAt,
      errors,
      warnings,
      highlights: Array.from(new Set(highlights)),
    });
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    setSuccessNotice(null);

    const stepError = getStepError(6);
    if (stepError) {
      setSubmitError(stepError);
      return;
    }

    if (!authToken) {
      setSubmitError('请先登录后再创建自动对账任务。');
      return;
    }

    let resolvedBindings: Array<{
      data_source_id: string;
      table_name: string;
      resource_key: string;
      dataset_source_type: string;
      query: Record<string, unknown>;
    }> = [];

    try {
      resolvedBindings = resolveInputBindings();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '请检查数据源与 T+N 配置');
      return;
    }

    setIsSaving(true);
    try {
      const response = await fetchReconAutoApi('/auto-tasks', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          task_name: taskName.trim(),
          rule_code: ruleCode,
          is_enabled: isEnabled,
          schedule_type: scheduleType,
          schedule_expr: buildScheduleExpr(
            scheduleType,
            scheduleHour,
            scheduleMinute,
            scheduleWeekday,
            scheduleMonthDay,
          ),
          biz_date_offset: 'T-1',
          input_mode: 'bound_source',
          bound_data_source_ids: Array.from(new Set(resolvedBindings.map((item) => item.data_source_id))),
          channel_config_id: selectedChannelId,
          input_bindings: resolvedBindings,
          owner_mapping_json: {
            default_owner: {
              name: defaultOwnerName.trim(),
              contact: {
                mobile: defaultOwnerMobile.trim(),
              },
            },
          },
          task_meta_json: {
            input_bindings: resolvedBindings,
            validation_preview: validationPreview,
            input_preparation: {
              skipped: shouldSkipPreparationStep,
              confirmed: shouldSkipPreparationStep ? true : inputPreparationConfirmed,
              assessments: bindingAssessments.map((assessment) => ({
                table_name: assessment.slot.tableName,
                dataset_name: assessment.option?.datasetName || '',
                status: assessment.status,
                missing_columns: assessment.missingColumns,
                date_field: assessment.dateField,
                suggestions: assessment.suggestions,
              })),
            },
          },
          auto_create_exceptions: true,
          auto_remind: false,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '创建任务配置失败'));
      }

      setIsCreateOpen(false);
      setSuccessNotice(`已创建任务配置「${taskName.trim()}」`);
      await onCreatedTaskConfig?.();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '创建任务配置失败');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="mt-4 rounded-2xl border border-border bg-surface shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-4 py-3">
        <div>
          <h4 className="text-sm font-semibold text-text-primary">任务配置</h4>
          <p className="mt-1 text-xs text-text-secondary">
            管理自动对账任务、调度、对账异常处理人与协作通道。
          </p>
        </div>
        <button
          type="button"
          onClick={handleCreate}
          disabled={!authToken || ruleOptions.length === 0}
          className={cn(
            'inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
            !authToken || ruleOptions.length === 0
              ? 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400'
              : 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
          )}
        >
          {createButtonLabel}
        </button>
      </div>

      {successNotice && (
        <div className="mx-4 mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          {successNotice}
        </div>
      )}

      {errorText && (
        <div className="mx-4 mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          {errorText}
        </div>
      )}

      <div className="mt-3 overflow-hidden rounded-b-2xl">
        <table className="w-full text-sm">
          <thead className="bg-surface-secondary text-left text-text-secondary">
            <tr>
              <th className="px-4 py-3 font-medium">任务名称</th>
              <th className="px-4 py-3 font-medium">公司</th>
              <th className="px-4 py-3 font-medium">绑定规则</th>
              <th className="px-4 py-3 font-medium">调度</th>
              <th className="px-4 py-3 font-medium">对账异常处理人</th>
              <th className="px-4 py-3 font-medium">协作通道</th>
              <th className="px-4 py-3 font-medium">
                <div className="flex justify-center">状态</div>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr className="border-t border-border-subtle text-text-secondary">
                <td className="px-4 py-8 text-center" colSpan={7}>
                  正在加载任务配置...
                </td>
              </tr>
            ) : tasks.length > 0 ? (
              tasks.map((task) => (
                <tr key={task.id} className="border-t border-border-subtle text-text-primary">
                  <td className="px-4 py-3 font-medium">{task.name}</td>
                  <td className="px-4 py-3 text-text-secondary">{task.company}</td>
                  <td className="px-4 py-3 text-text-secondary">{task.ruleName}</td>
                  <td className="px-4 py-3 text-text-secondary">{task.schedule}</td>
                  <td className="px-4 py-3 text-text-secondary">{task.ownerMode}</td>
                  <td className="px-4 py-3 text-text-secondary">
                    {channelOptionMap.get(task.channel)?.name || task.channel}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-center">
                      <span
                        className={cn(
                          'inline-flex rounded-full border px-2.5 py-1 text-xs font-medium',
                          task.status === 'enabled'
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-600'
                            : 'border-slate-200 bg-slate-50 text-slate-600',
                        )}
                      >
                        {task.status === 'enabled' ? '启用中' : '已暂停'}
                      </span>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr className="border-t border-border-subtle text-text-secondary">
                <td className="px-4 py-8 text-center" colSpan={7}>
                  暂无任务配置数据，点击右上角“新建任务配置”开始创建。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {isCreateOpen && (
        <div
          className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/45 px-4 py-6"
          onClick={handleCloseModal}
        >
          <div
            className="my-auto flex max-h-[calc(100vh-3rem)] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-border bg-surface shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-border-subtle px-5 py-4">
              <div>
                <h4 className="text-base font-semibold text-text-primary">新建任务配置</h4>
                <p className="mt-1 text-sm text-text-secondary">
                  按步骤完成任务、数据源、调度与协作设置，保存前先跑一次验证。
                </p>
              </div>
              <button
                type="button"
                onClick={handleCloseModal}
                className="rounded-lg p-2 text-text-secondary transition-colors hover:bg-surface-secondary hover:text-text-primary"
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="border-b border-border-subtle bg-surface-secondary/60 px-5 py-4">
              <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                {visibleSteps.map((step, index) => {
                  const isCurrent = currentStep === step.id;
                  const isDone = currentStepIndex > index;
                  return (
                    <button
                      key={step.id}
                      type="button"
                      onClick={() => {
                        if (isSaving) return;
                        setSubmitError(null);
                        setCurrentStep(step.id);
                      }}
                      className={cn(
                        'rounded-2xl border px-3 py-3 text-left transition-colors',
                        isCurrent
                          ? 'border-sky-200 bg-sky-50'
                          : isDone
                            ? 'border-emerald-200 bg-emerald-50/70'
                            : 'border-border bg-surface',
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold',
                            isCurrent
                              ? 'bg-sky-600 text-white'
                              : isDone
                                ? 'bg-emerald-600 text-white'
                                : 'bg-surface-secondary text-text-secondary',
                          )}
                        >
                          {step.id}
                        </span>
                        <span className="text-sm font-medium text-text-primary">{step.title}</span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-text-secondary">{step.description}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <form className="overflow-y-auto px-5 py-5" onSubmit={handleSubmit}>
              <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-muted">Step {currentStep}</p>
                    <h5 className="mt-1 text-lg font-semibold text-text-primary">{currentStepMeta?.title}</h5>
                    <p className="mt-1 text-sm text-text-secondary">{currentStepMeta?.description}</p>
                  </div>
                  {currentStep === 1 && (
                    <button
                      type="button"
                      onClick={handleOpenCreateRule}
                      className="shrink-0 rounded-lg border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 transition-colors hover:bg-sky-100"
                    >
                      新建规则
                    </button>
                  )}
                </div>

                {currentStep === 1 && (
                  <div className="mt-5 grid gap-5 md:grid-cols-2">
                    <label className="block">
                      <span className="text-sm font-medium text-text-primary">任务名称</span>
                      <input
                        value={taskName}
                        onChange={(event) => setTaskName(event.target.value)}
                        placeholder="例如：商户对账 T+1 自动任务"
                        className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-sky-300"
                      />
                    </label>

                    <div className="block">
                      <span className="text-sm font-medium text-text-primary">绑定规则</span>
                      <SelectField value={ruleCode} onChange={setRuleCode}>
                        <option value="">请选择规则</option>
                        {ruleOptions.map((rule) => (
                          <option key={rule.rule_code} value={rule.rule_code}>
                            {rule.name}
                          </option>
                        ))}
                      </SelectField>
                    </div>

                    <div className="md:col-span-2 rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <h6 className="text-sm font-medium text-text-primary">规则输入解析</h6>
                          <p className="mt-1 text-xs text-text-secondary">
                            系统会先读取规则要求的输入表结构，用于后续自动判断数据源是否能直接使用。
                          </p>
                        </div>
                        {(loadingRuleInputs || loadingTableSchemas) && (
                          <span className="inline-flex items-center gap-2 text-xs text-text-secondary">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            正在分析
                          </span>
                        )}
                      </div>

                      {ruleInputError && (
                        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                          {ruleInputError}
                        </div>
                      )}

                      {!ruleInputError && ruleInputSlots.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {ruleInputSlots.map((slot) => (
                            <span
                              key={slot.key}
                              className="rounded-full border border-border bg-surface-secondary px-3 py-1 text-xs text-text-primary"
                            >
                              {slot.tableName}
                            </span>
                          ))}
                        </div>
                      )}

                      {tableSchemaError && !ruleInputError && (
                        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                          {tableSchemaError}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {currentStep === 2 && (
                  <div className="mt-5">
                    {(loadingRuleInputs || loadingDatasets) && (
                      <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-3 text-sm text-text-secondary">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        正在加载数据源和规则输入...
                      </div>
                    )}

                    {datasetLoadError && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                        {datasetLoadError}
                      </div>
                    )}

                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      {ruleInputSlots.map((slot) => {
                        const selectedOption = datasetOptionMap.get(selectedDatasetKeys[slot.key] || '');
                        const bindingQuery = bindingQueries[slot.key] || createEmptyBindingQuery();
                        const schema = tableSchemaMap[slot.tableName];
                        return (
                          <div key={slot.key} className="rounded-2xl border border-border bg-surface px-4 py-4">
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <h6 className="text-sm font-medium text-text-primary">{slot.label}</h6>
                                <p className="mt-1 text-xs text-text-secondary">为这个输入绑定实际运行时的数据源。</p>
                              </div>
                              {schema?.requiredColumns?.length ? (
                                <span className="rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
                                  必要字段 {schema.requiredColumns.length} 个
                                </span>
                              ) : null}
                            </div>

                            <label className="mt-4 block">
                              <span className="text-xs font-medium text-text-secondary">选择数据源</span>
                              <SelectField
                                value={selectedDatasetKeys[slot.key] || ''}
                                onChange={(value) => {
                                  setSelectedDatasetKeys((previous) => ({
                                    ...previous,
                                    [slot.key]: value,
                                  }));
                                }}
                                disabled={loadingRuleInputs || loadingDatasets || datasetOptions.length === 0}
                              >
                                <option value="">请选择数据源</option>
                                {datasetOptionsByKind.map((group) => (
                                  <optgroup key={group.kind} label={sourceLabel(group.kind)}>
                                    {group.options.map((option) => (
                                      <option key={option.key} value={option.key}>
                                        {datasetOptionLabel(option)}
                                      </option>
                                    ))}
                                  </optgroup>
                                ))}
                              </SelectField>
                            </label>

                            <label className="mt-4 block">
                              <span className="text-xs font-medium text-text-secondary">T+N</span>
                              <input
                                type="text"
                                inputMode="text"
                                value={bindingQuery.dayOffset}
                                onChange={(event) => {
                                  const nextValue = event.target.value;
                                  if (!/^-?\d*$/.test(nextValue)) return;
                                  setBindingQueries((previous) => ({
                                    ...previous,
                                    [slot.key]: {
                                      ...(previous[slot.key] || createEmptyBindingQuery()),
                                      dayOffset: nextValue,
                                    },
                                  }));
                                }}
                                placeholder="0"
                                className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-sky-300"
                              />
                              <span className="mt-2 block text-xs text-text-muted">
                                例如：`0` 表示 T，`1` 表示 T+1，`-1` 表示 T-1。
                              </span>
                            </label>

                            {selectedOption && (
                              <div className="mt-4 rounded-xl border border-border bg-surface-secondary px-3 py-3">
                                <p className="text-xs text-text-secondary">
                                  当前数据源：{selectedOption.sourceName} / {selectedOption.datasetName}
                                </p>
                                <p className="mt-2 text-xs text-text-secondary">
                                  已识别字段：{selectedOption.fields.length > 0 ? selectedOption.fields.slice(0, 8).join('、') : '暂无'}
                                  {selectedOption.fields.length > 8 ? ' ...' : ''}
                                </p>
                                {schema?.requiredColumns?.length ? (
                                  <p className="mt-2 text-xs text-text-secondary">
                                    规则要求：{schema.requiredColumns.join('、')}
                                  </p>
                                ) : null}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {selectedBindingsPreview.length > 0 && (
                      <div className="mt-4 rounded-xl border border-border bg-surface px-3 py-3">
                        <p className="text-xs font-medium text-text-secondary">当前已绑定</p>
                        <div className="mt-2 flex flex-col gap-2">
                          {selectedBindingsPreview.map(({ slot, option, scope }) => (
                            <div
                              key={`${slot.key}-${option.key}`}
                              className="rounded-xl border border-border-subtle px-3 py-3 text-xs text-text-primary"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="rounded-full bg-surface-secondary px-2 py-1 font-medium">
                                  {slot.tableName}
                                </span>
                                <span>{option.sourceName}</span>
                                <span className="text-text-muted">/</span>
                                <span>{option.datasetName}</span>
                              </div>
                              {scope.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-2 text-text-secondary">
                                  {scope.map((item) => (
                                    <span key={`${slot.key}-${item}`} className="rounded-full bg-surface-secondary px-2 py-1">
                                      {item}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {currentStep === 3 && (
                  <div className="mt-5">
                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <h6 className="text-sm font-medium text-text-primary">AI 输入准备建议</h6>
                          <p className="mt-1 text-xs text-text-secondary">
                            系统会根据当前数据源字段和规则要求的字段结构，判断是否可以直接跑对账。
                          </p>
                        </div>
                        {loadingTableSchemas && (
                          <span className="inline-flex items-center gap-2 text-xs text-text-secondary">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            正在分析
                          </span>
                        )}
                      </div>

                      <div className="mt-4 grid gap-3 md:grid-cols-3">
                        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3">
                          <p className="text-xs text-emerald-700">可直接使用</p>
                          <p className="mt-1 text-2xl font-semibold text-emerald-700">{preparationSummary.readyCount}</p>
                        </div>
                        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
                          <p className="text-xs text-amber-700">建议输入准备</p>
                          <p className="mt-1 text-2xl font-semibold text-amber-700">{preparationSummary.prepareCount}</p>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                          <p className="text-xs text-slate-700">待人工确认</p>
                          <p className="mt-1 text-2xl font-semibold text-slate-700">{preparationSummary.unknownCount}</p>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-4">
                        {bindingAssessments.map((assessment) => (
                          <div key={assessment.slot.key} className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <h6 className="text-sm font-medium text-text-primary">{assessment.slot.label}</h6>
                                <p className="mt-1 text-xs text-text-secondary">
                                  {assessment.option
                                    ? `${assessment.option.sourceName} / ${assessment.option.datasetName}`
                                    : '尚未选择数据源'}
                                </p>
                              </div>
                              <span className={cn('rounded-full border px-2.5 py-1 text-xs font-medium', statusClassName(assessment.status))}>
                                {statusLabel(assessment.status)}
                              </span>
                            </div>

                            {assessment.requiredColumns.length > 0 && (
                              <p className="mt-3 text-xs text-text-secondary">
                                规则要求字段：{assessment.requiredColumns.join('、')}
                              </p>
                            )}

                            {assessment.missingColumns.length > 0 && (
                              <p className="mt-2 text-xs text-amber-700">
                                缺少字段：{assessment.missingColumns.join('、')}
                              </p>
                            )}

                            {assessment.dateField ? (
                              <p className="mt-2 text-xs text-text-secondary">已识别日期字段：{assessment.dateField}</p>
                            ) : (
                              <p className="mt-2 text-xs text-amber-700">未识别日期字段，当前无法按 T+N 自动取数。</p>
                            )}

                            {assessment.likelyMatches.length > 0 && (
                              <div className="mt-3 rounded-xl border border-border bg-surface px-3 py-3">
                                <p className="text-xs font-medium text-text-primary">建议优先确认这些字段映射</p>
                                <div className="mt-2 flex flex-col gap-1 text-xs text-text-secondary">
                                  {assessment.likelyMatches.map((item) => (
                                    <span key={`${assessment.slot.key}-${item.requiredColumn}`}>
                                      {item.requiredColumn}
                                      {' -> '}
                                      {item.candidates.join(' / ')}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            <div className="mt-3 flex flex-col gap-2">
                              {assessment.suggestions.map((suggestion, index) => (
                                <div
                                  key={`${assessment.slot.key}-${index}`}
                                  className="rounded-xl border border-border-subtle bg-surface px-3 py-2 text-xs text-text-secondary"
                                >
                                  {suggestion}
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>

                      <label className="mt-4 flex items-start gap-3 rounded-2xl border border-border bg-surface px-4 py-3">
                        <input
                          type="checkbox"
                          checked={inputPreparationConfirmed}
                          onChange={(event) => setInputPreparationConfirmed(event.target.checked)}
                          className="mt-0.5 h-4 w-4 rounded border-border text-sky-600 focus:ring-sky-300"
                        />
                        <span>
                          <span className="block text-sm font-medium text-text-primary">我已确认上述输入准备建议</span>
                          <span className="block text-xs text-text-secondary">
                            如需调整数据源，请返回上一步修改；如先按当前配置继续，可进入下一步保存任务。
                          </span>
                        </span>
                      </label>
                    </div>
                  </div>
                )}

                {currentStep === 4 && (
                  <div className="mt-5 grid gap-5 md:grid-cols-2">
                    <label className="block">
                      <span className="text-sm font-medium text-text-primary">调度类型</span>
                      <SelectField
                        value={scheduleType}
                        onChange={(value) => setScheduleType(value as ScheduleType)}
                      >
                        <option value="daily">每日</option>
                        <option value="weekly">每周</option>
                        <option value="monthly">每月</option>
                      </SelectField>
                    </label>

                    <div className="block">
                      <span className="text-sm font-medium text-text-primary">调度表达式</span>

                      {scheduleType === 'daily' && (
                        <div className="mt-2 grid grid-cols-2 gap-3">
                          <SelectField value={scheduleHour} onChange={setScheduleHour} className="mt-0">
                            {HOUR_OPTIONS.map((hour) => (
                              <option key={hour} value={hour}>
                                {hour} 时
                              </option>
                            ))}
                          </SelectField>
                          <SelectField value={scheduleMinute} onChange={setScheduleMinute} className="mt-0">
                            {MINUTE_OPTIONS.map((minute) => (
                              <option key={minute} value={minute}>
                                {minute} 分
                              </option>
                            ))}
                          </SelectField>
                        </div>
                      )}

                      {scheduleType === 'weekly' && (
                        <div className="mt-2 grid grid-cols-3 gap-3">
                          <SelectField value={scheduleWeekday} onChange={setScheduleWeekday} className="mt-0">
                            {WEEKDAY_OPTIONS.map((weekday) => (
                              <option key={weekday.value} value={weekday.value}>
                                {weekday.label}
                              </option>
                            ))}
                          </SelectField>
                          <SelectField value={scheduleHour} onChange={setScheduleHour} className="mt-0">
                            {HOUR_OPTIONS.map((hour) => (
                              <option key={hour} value={hour}>
                                {hour} 时
                              </option>
                            ))}
                          </SelectField>
                          <SelectField value={scheduleMinute} onChange={setScheduleMinute} className="mt-0">
                            {MINUTE_OPTIONS.map((minute) => (
                              <option key={minute} value={minute}>
                                {minute} 分
                              </option>
                            ))}
                          </SelectField>
                        </div>
                      )}

                      {scheduleType === 'monthly' && (
                        <div className="mt-2 grid grid-cols-3 gap-3">
                          <SelectField value={scheduleMonthDay} onChange={setScheduleMonthDay} className="mt-0">
                            {MONTH_DAY_OPTIONS.map((day) => (
                              <option key={day} value={day}>
                                {day} 号
                              </option>
                            ))}
                          </SelectField>
                          <SelectField value={scheduleHour} onChange={setScheduleHour} className="mt-0">
                            {HOUR_OPTIONS.map((hour) => (
                              <option key={hour} value={hour}>
                                {hour} 时
                              </option>
                            ))}
                          </SelectField>
                          <SelectField value={scheduleMinute} onChange={setScheduleMinute} className="mt-0">
                            {MINUTE_OPTIONS.map((minute) => (
                              <option key={minute} value={minute}>
                                {minute} 分
                              </option>
                            ))}
                          </SelectField>
                        </div>
                      )}

                      <div className="mt-4 rounded-xl border border-border bg-surface px-3 py-3 text-xs text-text-secondary">
                        任务将按「{formatScheduleSummary(scheduleType, scheduleHour, scheduleMinute, scheduleWeekday, scheduleMonthDay)}」自动执行。
                      </div>
                    </div>
                  </div>
                )}

                {currentStep === 5 && (
                  <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h6 className="text-sm font-medium text-text-primary">协作通道</h6>
                          <p className="mt-1 text-xs text-text-secondary">
                            异常催办、待办创建和后续提醒都会走这里。
                          </p>
                        </div>
                        {onOpenCollaborationChannels && (
                          <button
                            type="button"
                            onClick={() => onOpenCollaborationChannels()}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-secondary px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                          >
                            管理协作通道
                            <ArrowUpRight className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>

                      {channelLoadError && (
                        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                          {channelLoadError}
                        </div>
                      )}

                      {loadingChannels ? (
                        <div className="mt-4 flex items-center gap-2 rounded-xl border border-border bg-surface-secondary px-3 py-3 text-sm text-text-secondary">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          正在加载协作通道
                        </div>
                      ) : channelOptions.length > 0 ? (
                        <div className="mt-4">
                          <label className="block">
                            <span className="text-sm font-medium text-text-primary">选择协作通道</span>
                            <SelectField value={selectedChannelId} onChange={setSelectedChannelId}>
                              <option value="">请选择协作通道</option>
                              {channelOptions.map((channel) => (
                                <option key={channel.id} value={channel.id}>
                                  {collaborationProviderLabel(channel.provider)} / {channel.name}
                                </option>
                              ))}
                            </SelectField>
                          </label>
                        </div>
                      ) : (
                        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface-secondary px-4 py-4">
                          <div className="max-w-2xl">
                            <h6 className="text-sm font-medium text-text-primary">还没有可用的协作通道</h6>
                            <p className="mt-1 text-xs leading-6 text-text-secondary">
                              先连接一个默认通道，后续异常催办、消息提醒和待办创建都会走这里。连接完成后，返回任务配置重新选择即可。
                            </p>
                          </div>

                          <div className="mt-4 grid gap-3 md:grid-cols-3">
                            {channelSetupCards.map((card) => (
                              <button
                                key={card.provider}
                                type="button"
                                onClick={() => onOpenCollaborationChannels?.(card.provider)}
                                disabled={!onOpenCollaborationChannels}
                                className={cn(
                                  'rounded-2xl border px-4 py-4 text-left transition-colors',
                                  onOpenCollaborationChannels
                                    ? 'border-border bg-surface hover:bg-surface-tertiary'
                                    : 'cursor-not-allowed border-border bg-surface opacity-70',
                                )}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <span className="text-sm font-medium text-text-primary">{card.title}</span>
                                  <ArrowUpRight className="h-4 w-4 text-text-muted" />
                                </div>
                                <p className="mt-2 text-xs leading-5 text-text-secondary">{card.description}</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div>
                        <h6 className="text-sm font-medium text-text-primary">对账异常处理人</h6>
                        <p className="mt-1 text-xs text-text-secondary">
                          第一版按任务级配置处理人，所有异常默认指向这里填写的人。
                        </p>
                      </div>

                      <label className="mt-4 block">
                        <span className="text-sm font-medium text-text-primary">处理人姓名</span>
                        <input
                          value={defaultOwnerName}
                          onChange={(event) => setDefaultOwnerName(event.target.value)}
                          placeholder="例如：张三"
                          className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-sky-300"
                        />
                      </label>

                      <label className="mt-4 block">
                        <span className="text-sm font-medium text-text-primary">手机号</span>
                        <input
                          value={defaultOwnerMobile}
                          onChange={(event) => setDefaultOwnerMobile(event.target.value)}
                          placeholder="可选，用于后续定位和催办扩展"
                          className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-sky-300"
                        />
                      </label>
                    </div>
                  </div>
                )}

                {currentStep === 6 && (
                  <div className="mt-5 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <h6 className="text-sm font-medium text-text-primary">配置总览</h6>
                      <div className="mt-4 grid gap-3 text-sm">
                        <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
                          <p className="text-xs text-text-muted">任务名称</p>
                          <p className="mt-1 text-text-primary">{taskName || '未填写'}</p>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
                          <p className="text-xs text-text-muted">绑定规则</p>
                          <p className="mt-1 text-text-primary">{selectedRule?.name || '未选择'}</p>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
                          <p className="text-xs text-text-muted">数据源</p>
                          <div className="mt-1 flex flex-col gap-2 text-text-primary">
                            {selectedBindingsPreview.length > 0 ? (
                              selectedBindingsPreview.map(({ slot, option, scope }) => (
                                <div key={`${slot.key}-${option.key}`} className="rounded-lg bg-surface px-3 py-2 text-xs">
                                  <div>
                                    {slot.tableName}
                                    {' -> '}
                                    {option.sourceName} / {option.datasetName}
                                  </div>
                                  {scope.length > 0 ? (
                                    <div className="mt-1 text-text-secondary">{scope.join(' · ')}</div>
                                  ) : null}
                                </div>
                              ))
                            ) : (
                              <span className="text-text-secondary">未选择</span>
                            )}
                          </div>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
                          <p className="text-xs text-text-muted">调度</p>
                          <p className="mt-1 text-text-primary">
                            {formatScheduleSummary(
                              scheduleType,
                              scheduleHour,
                              scheduleMinute,
                              scheduleWeekday,
                              scheduleMonthDay,
                            )}
                          </p>
                        </div>
                        <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3">
                          <p className="text-xs text-text-muted">协作与责任人</p>
                          <p className="mt-1 text-text-primary">
                            {(selectedChannelId && channelOptionMap.get(selectedChannelId)?.name) || '未选择协作通道'}
                          </p>
                          <p className="mt-1 text-xs text-text-secondary">
                            对账异常处理人：{defaultOwnerName || '未填写'}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-border bg-surface px-4 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <h6 className="text-sm font-medium text-text-primary">验证结果</h6>
                          <p className="mt-1 text-xs text-text-secondary">
                            保存前跑一次配置验证，确认是否可以直接启用任务。
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => void handleRunValidation()}
                          className={cn(
                            'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                            validationPreview?.status === 'running'
                              ? 'cursor-not-allowed border-sky-200 bg-sky-100 text-sky-500'
                              : 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
                          )}
                          disabled={validationPreview?.status === 'running'}
                        >
                          {validationPreview?.status === 'running' ? '验证中...' : validationPreview ? '重新验证' : '开始验证'}
                        </button>
                      </div>

                      <label className="mt-4 flex items-center gap-3 rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isEnabled}
                          onChange={(event) => setIsEnabled(event.target.checked)}
                          className="h-4 w-4 rounded border-border text-sky-600 focus:ring-sky-300"
                        />
                        <span>
                          <span className="block text-sm font-medium text-text-primary">保存后立即启用</span>
                          <span className="block text-xs text-text-secondary">
                            关闭后任务会先保存为停用状态，后续再手动启用。
                          </span>
                        </span>
                      </label>

                      {validationPreview ? (
                        <div
                          className={cn(
                            'mt-4 rounded-2xl border px-4 py-4',
                            validationPreview.status === 'success'
                              ? 'border-emerald-200 bg-emerald-50'
                              : validationPreview.status === 'warning'
                                ? 'border-amber-200 bg-amber-50'
                                : validationPreview.status === 'error'
                                  ? 'border-rose-200 bg-rose-50'
                                  : 'border-border bg-surface-secondary',
                          )}
                        >
                          <p className="text-sm font-medium text-text-primary">{validationPreview.summary}</p>
                          {validationPreview.checkedAt ? (
                            <p className="mt-1 text-xs text-text-secondary">最近验证时间：{validationPreview.checkedAt}</p>
                          ) : null}

                          {validationPreview.errors.length > 0 && (
                            <div className="mt-3">
                              <p className="text-xs font-medium text-rose-700">需修正的问题</p>
                              <div className="mt-2 flex flex-col gap-2">
                                {validationPreview.errors.map((item) => (
                                  <div key={item} className="rounded-xl bg-white/70 px-3 py-2 text-xs text-rose-700">
                                    {item}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {validationPreview.warnings.length > 0 && (
                            <div className="mt-3">
                              <p className="text-xs font-medium text-amber-700">需要确认的建议</p>
                              <div className="mt-2 flex flex-col gap-2">
                                {validationPreview.warnings.map((item) => (
                                  <div key={item} className="rounded-xl bg-white/70 px-3 py-2 text-xs text-amber-700">
                                    {item}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {validationPreview.highlights.length > 0 && (
                            <div className="mt-3">
                              <p className="text-xs font-medium text-text-primary">验证通过的关键信息</p>
                              <div className="mt-2 flex flex-col gap-2">
                                {validationPreview.highlights.map((item) => (
                                  <div key={item} className="rounded-xl bg-white/70 px-3 py-2 text-xs text-text-secondary">
                                    {item}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface-secondary px-4 py-4 text-xs leading-6 text-text-secondary">
                          还未执行验证。点击“开始验证”后，系统会检查任务配置是否完整，并给出需要确认的建议。
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {submitError && (
                <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                  {submitError}
                </div>
              )}

              <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                <div className="text-xs text-text-secondary">
                  {shouldSkipPreparationStep
                    ? '当前数据源结构可直接匹配规则要求，已自动跳过“输入准备”步骤。'
                    : '如 AI 判断需要输入准备，可先返回上一步调整数据源。'}
                </div>
                <div className="flex flex-wrap justify-end gap-3">
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    className="rounded-xl border border-border px-4 py-2.5 text-sm text-text-secondary transition-colors hover:bg-surface-secondary"
                  >
                    取消
                  </button>
                  {previousStepId && (
                    <button
                      type="button"
                      onClick={() => {
                        setSubmitError(null);
                        setCurrentStep(previousStepId);
                      }}
                      className="rounded-xl border border-border px-4 py-2.5 text-sm text-text-primary transition-colors hover:bg-surface-secondary"
                    >
                      上一步
                    </button>
                  )}
                  {nextStepId ? (
                    <button
                      type="button"
                      onClick={handleNextStep}
                      className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-2.5 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100"
                    >
                      下一步
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={isSaving}
                      className={cn(
                        'rounded-xl border px-4 py-2.5 text-sm font-medium transition-colors',
                        isSaving
                          ? 'cursor-not-allowed border-sky-200 bg-sky-100 text-sky-500'
                          : 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
                      )}
                    >
                      {isSaving ? '保存中...' : '保存任务'}
                    </button>
                  )}
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
