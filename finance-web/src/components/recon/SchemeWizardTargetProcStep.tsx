import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ChevronDown, Sparkles } from 'lucide-react';
import type { DataSourceKind } from '../../types';
import { extractCollectionDetailSampleRows } from './datasetPreview';
import SchemeWizardOutputFieldEditor from './SchemeWizardOutputFieldEditor';
import type { OutputFieldDraft } from './schemeWizardState';

export type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';
export type ProcBuildMode = 'simple_mapping' | 'ai_complex_rule';
export type AiProcSide = 'left' | 'right';
export type AiProcGenerationStatus = 'idle' | 'generating' | 'needs_user_input' | 'succeeded' | 'failed';
export type RuleGenerationNodeStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'needs_user_input';

const SIMPLE_MAPPING_UI_ENABLED = false;

export interface RuleGenerationNodeTrace {
  code: string;
  name: string;
  status: RuleGenerationNodeStatus;
  message: string;
  attempt: number;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  summary?: Record<string, unknown>;
  errors?: Array<Record<string, unknown>>;
  warnings?: string[];
}

export type AiProcQuestionCandidate = string | {
  rawName?: string;
  displayName?: string;
  sourceTable?: string;
};

export interface AiProcQuestion {
  id: string;
  question: string;
  role?: string;
  mention?: string;
  candidates?: AiProcQuestionCandidate[];
  evidence?: string[];
}
type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

export interface SchemeDraftLite {
  name: string;
  businessGoal: string;
  leftDescription: string;
  rightDescription: string;
  procTrialStatus: TrialStatus;
  procTrialSummary: string;
}

export interface SchemeSourceOption {
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

export interface ProcSampleRow {
  [key: string]: string | number | null;
}

type PreviewColumnOriginTone = 'sky' | 'emerald' | 'amber' | 'violet';

interface PreviewColumnHintMeta {
  badge?: string;
  helper?: string;
  tone?: PreviewColumnOriginTone;
}

export interface ProcSampleGroup {
  title: string;
  originLabel?: string;
  originHint?: string;
  fieldLabelMap?: Record<string, string>;
  columnHints?: Record<string, PreviewColumnHintMeta>;
  showRawFieldName?: boolean;
  rows: ProcSampleRow[];
}

export interface ProcTrialPreview {
  status: TrialStatus;
  summary: string;
  leftSourceSamples: ProcSampleGroup[];
  rightSourceSamples: ProcSampleGroup[];
  leftOutputSamples: ProcSampleGroup[];
  rightOutputSamples: ProcSampleGroup[];
  validations?: string[];
}

export interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed' | 'warning';
  message: string;
  details: string[];
}

export interface AiProcSideDraft {
  ruleDraft: string;
  status: AiProcGenerationStatus;
  summary: string;
  error: string;
  failureReasons: string[];
  failureDetails: Array<Record<string, unknown>>;
  nodeTraces: RuleGenerationNodeTrace[];
  questions: AiProcQuestion[];
  assumptions: Array<Record<string, unknown>>;
  validations: Array<Record<string, unknown>>;
  warnings: string[];
  procRuleJson?: Record<string, unknown>;
  procSteps?: Array<Record<string, unknown>>;
  outputRows: ProcSampleRow[];
  outputFieldLabelMap: Record<string, string>;
  outputColumnHints?: Record<string, PreviewColumnHintMeta>;
}

export interface SchemeWizardTargetProcStepProps {
  authToken?: string | null;
  schemeDraft: SchemeDraftLite;
  selectedLeftSources: SchemeSourceOption[];
  selectedRightSources: SchemeSourceOption[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
  procBuildMode?: ProcBuildMode;
  aiProcSideDrafts?: Partial<Record<AiProcSide, AiProcSideDraft>>;
  procCompatibility: CompatibilityCheckResult;
  onChangeProcBuildMode?: (mode: ProcBuildMode) => void;
  onChangeAiProcRuleDraft?: (side: AiProcSide, value: string) => void;
  onGenerateAiProcOutput?: (side: AiProcSide) => void;
  onChangeSourceSelection: (side: 'left' | 'right', sources: SchemeSourceOption[]) => void;
  onChangeOutputFields: (side: 'left' | 'right', fields: OutputFieldDraft[]) => void;
  onRecommendOutputFields: (side: 'left' | 'right') => void;
  isTrialingProc?: boolean;
  onTrialProc: () => void;
  onViewProcJson: () => void;
  procJsonPreview?: string;
  procTrialPreview?: ProcTrialPreview;
}

type PreviewSection = 'left' | 'right';

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function trialStatusMeta(status: TrialStatus): { label: string; className: string } {
  if (status === 'passed') {
    return {
      label: '试跑通过',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };
  }
  if (status === 'needs_adjustment') {
    return {
      label: '需调整',
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    };
  }
  return {
    label: '待试跑',
    className: 'border-border bg-surface-secondary text-text-secondary',
  };
}

function formatSourceLabel(source: SchemeSourceOption) {
  return source.description || source.providerCode || source.sourceKind;
}

function resolveDatasetDisplayName(source: SchemeSourceOption): string {
  return source.businessName?.trim() || source.name;
}

function resolveDatasetTechnicalName(source: SchemeSourceOption): string {
  return source.technicalName?.trim()
    || source.datasetCode
    || source.resourceKey
    || source.datasetKind
    || formatSourceLabel(source);
}

function RowTable({
  rows,
  fieldLabelMap,
  columnHints,
  showRawFieldName = true,
}: {
  rows: ProcSampleRow[];
  fieldLabelMap?: Record<string, string>;
  columnHints?: Record<string, PreviewColumnHintMeta>;
  showRawFieldName?: boolean;
}) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-xs text-text-secondary">
        暂无抽样数据
      </div>
    );
  }

  const columns = buildSampleColumns(rows);

  return (
    <div className="max-h-[280px] overflow-auto rounded-2xl border border-border bg-surface">
      <table className="w-max min-w-full border-collapse text-xs">
        <thead className="sticky top-0 z-10 bg-surface-secondary">
          <tr className="border-b border-border-subtle text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">
            {columns.map((col) => {
              const label = fieldLabelMap?.[col]?.trim();
              const hasAlias = showRawFieldName && Boolean(label && label !== col);
              const columnHint = columnHints?.[col];
              return (
                <th key={col} className="px-4 py-2 text-left font-semibold">
                  <span className="block whitespace-nowrap">{label || col}</span>
                  {hasAlias ? (
                    <span className="mt-0.5 block whitespace-nowrap text-[10px] font-normal normal-case tracking-normal text-text-muted">
                      {col}
                    </span>
                  ) : null}
                  {columnHint?.badge ? (
                    <span
                      className={cn(
                        'mt-1 inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium normal-case tracking-normal',
                        columnHint.tone === 'sky' && 'border-sky-200 bg-sky-50 text-sky-700',
                        columnHint.tone === 'emerald' && 'border-emerald-200 bg-emerald-50 text-emerald-700',
                        columnHint.tone === 'amber' && 'border-amber-200 bg-amber-50 text-amber-700',
                        columnHint.tone === 'violet' && 'border-violet-200 bg-violet-50 text-violet-700',
                        !columnHint.tone && 'border-border bg-surface-secondary text-text-secondary',
                      )}
                    >
                      {columnHint.badge}
                    </span>
                  ) : null}
                  {columnHint?.helper ? (
                    <span
                      className={cn(
                        'mt-1 max-w-[260px] text-[10px] font-normal normal-case leading-4 tracking-normal',
                        columnHint.tone && !columnHint.badge
                          ? 'inline-flex rounded-full border px-2 py-0.5 text-left'
                          : false,
                        columnHint.tone === 'sky' && !columnHint.badge && 'border-sky-200 bg-sky-50 text-sky-700',
                        columnHint.tone === 'emerald' && !columnHint.badge && 'border-emerald-200 bg-emerald-50 text-emerald-700',
                        columnHint.tone === 'amber' && !columnHint.badge && 'border-amber-200 bg-amber-50 text-amber-700',
                        columnHint.tone === 'violet' && !columnHint.badge && 'border-violet-200 bg-violet-50 text-violet-700',
                        (!columnHint.tone || columnHint.badge) && 'block whitespace-normal text-text-secondary',
                      )}
                    >
                      {columnHint.helper}
                    </span>
                  ) : null}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`row-${index}`}
              className="border-b border-border-subtle text-text-secondary last:border-b-0"
            >
              {columns.map((col) => (
                <td key={`${col}-${index}`} className="px-4 py-2 align-top">
                  <span className="block max-w-[260px] truncate" title={row[col] === null || row[col] === undefined ? '--' : String(row[col])}>
                    {row[col] === null || row[col] === undefined ? '--' : String(row[col])}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SampleGroup({ group }: { group: ProcSampleGroup }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold text-text-secondary">{group.title}</p>
        {group.originLabel ? (
          <span
            title={group.originHint || group.originLabel}
            className="inline-flex rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700"
          >
            {group.originLabel}
          </span>
        ) : null}
      </div>
      <RowTable
        rows={group.rows}
        fieldLabelMap={group.fieldLabelMap}
        columnHints={group.columnHints}
        showRawFieldName={group.showRawFieldName}
      />
    </div>
  );
}

function PreviewSectionBlock({
  title,
  description,
  groups,
}: {
  title: string;
  description: string;
  groups: ProcSampleGroup[];
}) {
  return (
    <div className="rounded-3xl border border-border bg-surface-secondary p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
        </div>
        <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
          {groups.length} 组
        </span>
      </div>
      <div className="mt-4 space-y-4">
        {groups.length > 0 ? (
          groups.map((group, index) => <SampleGroup key={`${title}-${index}`} group={group} />)
        ) : (
          <div className="rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-sm text-text-secondary">
            当前没有可展示的抽样结果。
          </div>
        )}
      </div>
    </div>
  );
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

function normalizeStringList(value: unknown): string[] {
  return asList(value).map((item) => toText(item).trim()).filter(Boolean);
}

function normalizeFieldLabelMap(value: unknown): Record<string, string> | undefined {
  const rows = Object.entries(asRecord(value))
    .map(([key, raw]) => [key.trim(), toText(raw).trim()] as const)
    .filter(([key, label]) => Boolean(key && label));
  if (rows.length === 0) return undefined;
  return Object.fromEntries(rows);
}

function isSupportedSourceKind(value: string): value is SupportedSourceKind {
  return (
    value === 'platform_oauth' ||
    value === 'database' ||
    value === 'api' ||
    value === 'file' ||
    value === 'browser' ||
    value === 'desktop_cli'
  );
}

function normalizeCandidateDataset(
  raw: unknown,
  sourceFallback?: Record<string, string>,
): SchemeSourceOption | null {
  const value = asRecord(raw);
  const semanticProfile = asRecord(value.semantic_profile);
  const sourceRecord = asRecord(value.source);
  const datasetId = toText(value.dataset_id, toText(value.id)).trim();
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
  if (!enabled) return null;

  const sourceId = toText(
    value.source_id,
    toText(value.data_source_id, toText(sourceRecord.id, sourceFallback?.sourceId || '')),
  ).trim();
  const sourceName = toText(
    value.source_name,
    toText(value.data_source_name, toText(sourceRecord.name, sourceFallback?.sourceName || sourceId)),
  ).trim();
  const rawSourceKind = toText(value.source_kind, toText(sourceRecord.source_kind, sourceFallback?.sourceKind || '')).trim();
  const providerCode = toText(
    value.provider_code,
    toText(sourceRecord.provider_code, sourceFallback?.providerCode || 'unknown'),
  ).trim();
  if (!sourceId || !isSupportedSourceKind(rawSourceKind)) return null;
  const sourceKind = rawSourceKind;

  const businessName = toText(
    value.business_name,
    toText(value.display_name, toText(semanticProfile.business_name)),
  ).trim();
  const technicalName = toText(
    value.technical_name,
    toText(value.resource_key, toText(value.table_name, datasetCode || datasetName || datasetId)),
  ).trim();
  const fieldLabelMap =
    normalizeFieldLabelMap(value.field_label_map)
    || normalizeFieldLabelMap(value.fieldLabelMap)
    || normalizeFieldLabelMap(semanticProfile.field_label_map);
  const schemaSummary = asRecord(value.schema_summary);
  const semanticFields = asList(value.semantic_fields);
  const normalizedSchemaSummary = Object.keys(schemaSummary).length > 0
    ? schemaSummary
    : semanticFields.length > 0
    ? { fields: semanticFields }
    : schemaSummary;
  const explicitKeyFields = normalizeStringList(value.key_fields);
  const keyFields =
    explicitKeyFields.length > 0
      ? explicitKeyFields
      : normalizeStringList(semanticProfile.key_fields);
  return {
    id: datasetId || `${sourceId}-${datasetCode || datasetName}`,
    name: datasetName || datasetCode || datasetId,
    businessName: businessName || undefined,
    technicalName: technicalName || undefined,
    keyFields: keyFields.length > 0 ? keyFields : undefined,
    fieldLabelMap,
    sourceId,
    sourceName: sourceName || sourceId,
    sourceKind,
    providerCode: providerCode || 'unknown',
    description: toText(value.description, sourceFallback?.description || '').trim() || undefined,
    datasetCode: datasetCode || datasetId || datasetName,
    resourceKey: toText(value.resource_key).trim(),
    datasetKind: toText(value.dataset_kind).trim(),
    schemaSummary: normalizedSchemaSummary,
  };
}

function formatSampleCellValue(value: unknown): string {
  if (value === null || value === undefined) return '--';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function buildSampleColumns(rows: Record<string, unknown>[], maxColumns?: number): string[] {
  const columns: string[] = [];
  rows.forEach((row) => {
    Object.keys(row).forEach((column) => {
      if (!columns.includes(column)) columns.push(column);
    });
  });
  return typeof maxColumns === 'number' ? columns.slice(0, maxColumns) : columns;
}

function buildDatasetFieldItems(source: SchemeSourceOption, rows: Record<string, unknown>[] = []): FieldItem[] {
  const fromLabels = Object.entries(source.fieldLabelMap || {}).map(([raw, display]) => ({
    raw_name: raw,
    display_name: display || raw,
  }));
  if (fromLabels.length > 0) return fromLabels;

  const fromRows = buildSampleColumns(rows).map((column) => ({
    raw_name: column,
    display_name: column,
  }));
  if (fromRows.length > 0) return fromRows;

  return (source.keyFields || []).map((field) => ({ raw_name: field, display_name: field }));
}

function mergeDatasetDisplayColumns(fields: FieldItem[], rows: Record<string, unknown>[]): string[] {
  const columns: string[] = [];
  const append = (column: string) => {
    const normalized = column.trim();
    if (normalized && !columns.includes(normalized)) columns.push(normalized);
  };
  fields.forEach((field) => append(field.raw_name));
  buildSampleColumns(rows).forEach(append);
  return columns;
}

type FieldItem = { raw_name: string; display_name: string };
type PopupPos = { top: number; left: number; maxWidth: number };

const RULE_GENERATION_SAMPLE_ROW_LIMIT = 20;
const DATASET_PREVIEW_CACHE = new Map<string, Promise<DatasetPreviewState>>();
const DATASET_FIELD_ITEMS_CACHE = new Map<string, Promise<FieldItem[]>>();

function datasetStructureCacheKey(source: SchemeSourceOption, suffix: string): string {
  return [
    suffix,
    source.sourceId,
    source.id,
    source.resourceKey || source.datasetCode || source.technicalName || source.name,
    RULE_GENERATION_SAMPLE_ROW_LIMIT,
  ].join('|');
}

function mergeFieldItems(primary: FieldItem[], fallback: FieldItem[]): FieldItem[] {
  const labelByRawName = new Map<string, string>();
  [...fallback, ...primary].forEach((field) => {
    const rawName = field.raw_name.trim();
    const displayName = field.display_name.trim() || rawName;
    if (rawName) labelByRawName.set(rawName, displayName);
  });

  const merged: FieldItem[] = [];
  const append = (field: FieldItem) => {
    const rawName = field.raw_name.trim();
    if (!rawName || merged.some((item) => item.raw_name === rawName)) return;
    merged.push({ raw_name: rawName, display_name: labelByRawName.get(rawName) || rawName });
  };
  primary.forEach(append);
  fallback.forEach(append);
  return merged;
}

function useFieldPreview(authToken?: string | null) {
  const [popupDatasetId, setPopupDatasetId] = useState<string | null>(null);
  const [popupPos, setPopupPos] = useState<PopupPos>({ top: 0, left: 0, maxWidth: 320 });
  const [fieldCache, setFieldCache] = useState<Record<string, FieldItem[]>>({});
  const [fetchingFields, setFetchingFields] = useState<string | null>(null);

  const fetchFieldPreview = useCallback(
    async (dataset: SchemeSourceOption) => {
      const localFields = buildDatasetFieldItems(dataset);
      if (!authToken || !dataset.sourceId) {
        setFieldCache((prev) => ({ ...prev, [dataset.id]: localFields }));
        return;
      }
      setFetchingFields(dataset.id);
      try {
        const response = await fetch('/api/recon/schemes/design/dataset-fields', {
          method: 'POST',
          headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_id: dataset.sourceId,
            resource_key: dataset.resourceKey || dataset.datasetCode || '',
          }),
        });
        const data = await response.json().catch(() => ({}));
        const remoteFields = response.ok && Array.isArray(data.fields) ? (data.fields as FieldItem[]) : [];
        setFieldCache((prev) => ({
          ...prev,
          [dataset.id]: mergeFieldItems(remoteFields, localFields),
        }));
      } catch {
        setFieldCache((prev) => ({ ...prev, [dataset.id]: localFields }));
      } finally {
        setFetchingFields(null);
      }
    },
    [authToken],
  );

  const openPopup = useCallback(
    (dataset: SchemeSourceOption, cardEl: HTMLElement) => {
      if (popupDatasetId === dataset.id) {
        setPopupDatasetId(null);
        return;
      }
      const rect = cardEl.getBoundingClientRect();
      const viewportW = window.innerWidth;
      const popupW = 320;
      const spaceRight = viewportW - rect.right - 12;
      let left: number;
      let maxWidth: number;
      if (spaceRight >= popupW) {
        left = rect.right + 8;
        maxWidth = Math.min(popupW, spaceRight);
      } else {
        left = Math.max(8, rect.left - popupW - 8);
        maxWidth = Math.min(popupW, rect.left - 12);
      }
      const top = Math.min(rect.top, window.innerHeight - 320);
      setPopupPos({ top, left, maxWidth });
      setPopupDatasetId(dataset.id);
      if (!fieldCache[dataset.id]) void fetchFieldPreview(dataset);
    },
    [popupDatasetId, fieldCache, fetchFieldPreview],
  );

  const closePopup = useCallback(() => setPopupDatasetId(null), []);

  return { popupDatasetId, popupPos, fieldCache, fetchingFields, openPopup, closePopup };
}

function FieldPreviewPopup({
  datasetName,
  fields,
  loading,
  pos,
  onClose,
}: {
  datasetName: string;
  fields: FieldItem[];
  loading: boolean;
  pos: PopupPos;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, [onClose]);

  return (
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left, maxWidth: pos.maxWidth, minWidth: 260 }}
      className="fixed z-[200] overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <p className="text-sm font-semibold text-text-primary">{datasetName}</p>
        <button
          type="button"
          onClick={onClose}
          className="ml-3 text-text-muted transition hover:text-text-primary"
        >
          ✕
        </button>
      </div>
      <div className="max-h-72 overflow-y-auto p-3">
        {loading ? (
          <p className="text-[11px] text-text-muted">正在加载字段…</p>
        ) : fields.length === 0 ? (
          <p className="text-[11px] text-text-muted">暂无字段信息</p>
        ) : (
          <div className="space-y-1">
            {fields.map((f) => (
              <div
                key={f.raw_name}
                className="flex items-baseline justify-between gap-2 rounded-lg px-2 py-1 hover:bg-surface-secondary"
              >
                <span className="text-sm font-medium text-text-primary">{f.display_name}</span>
                {f.display_name !== f.raw_name ? (
                  <span className="shrink-0 text-[11px] text-text-muted">{f.raw_name}</span>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProcBuildModeSelector({
  value,
  onChange,
}: {
  value: ProcBuildMode;
  onChange: (mode: ProcBuildMode) => void;
}) {
  const modes: Array<{
    value: ProcBuildMode;
    title: string;
    badge: string;
    description: string;
    points: string[];
  }> = [
    {
      value: 'simple_mapping',
      title: '简单字段映射',
      badge: '基础模式',
      description: '适合左右单表字段整理、固定值、公式和拼接输出。',
      points: ['选择左右原始数据集', '调整输出字段', '试跑生成 proc JSON'],
    },
    {
      value: 'ai_complex_rule',
      title: 'AI复杂规则',
      badge: '推荐',
      description: '适合风险资产这类多表、多步骤、完整性检核和条件计算规则。',
      points: ['输入自然语言规则', 'AI 生成 proc JSON', '静态校验、样例执行和断言验证'],
    },
  ];

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {modes.map((mode) => {
        const active = value === mode.value;
        return (
          <button
            key={mode.value}
            type="button"
            onClick={() => onChange(mode.value)}
            className={cn(
              'rounded-3xl border bg-surface p-4 text-left transition',
              active
                ? 'border-sky-300 shadow-[0_18px_45px_rgba(14,165,233,0.12)] ring-2 ring-sky-100'
                : 'border-border hover:border-sky-200 hover:shadow-sm',
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-text-primary">{mode.title}</p>
                <p className="mt-1 text-xs leading-5 text-text-secondary">{mode.description}</p>
              </div>
              <span
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-medium',
                  active
                    ? 'border-sky-200 bg-sky-50 text-sky-700'
                    : 'border-border bg-surface-secondary text-text-secondary',
                )}
              >
                {mode.badge}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {mode.points.map((point) => (
                <span
                  key={point}
                  className="rounded-full border border-border bg-surface-secondary px-2.5 py-1 text-[11px] text-text-secondary"
                >
                  {point}
                </span>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}

interface DatasetPreviewState {
  loading: boolean;
  error: string;
  rows: Record<string, unknown>[];
}

function DatasetStructureCard({
  authToken,
  source,
}: {
  authToken?: string | null;
  source: SchemeSourceOption;
}) {
  const [preview, setPreview] = useState<DatasetPreviewState>({ loading: false, error: '', rows: [] });
  const [fieldItems, setFieldItems] = useState<FieldItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchPreview() {
      if (!authToken || !source.sourceId) {
        setPreview({ loading: false, error: authToken ? '' : '请先登录后查看样例数据。', rows: [] });
        return;
      }
      setPreview({ loading: true, error: '', rows: [] });
      try {
        const cacheKey = datasetStructureCacheKey(source, 'preview');
        let previewRequest = DATASET_PREVIEW_CACHE.get(cacheKey);
        if (!previewRequest) {
          previewRequest = (async () => {
            const params = new URLSearchParams({
              resource_key: source.resourceKey || source.datasetCode || source.technicalName || source.name,
              limit: '1',
              sample_limit: String(RULE_GENERATION_SAMPLE_ROW_LIMIT),
            });
            const response = await fetch(
              `/api/data-sources/${encodeURIComponent(source.sourceId)}/datasets/${encodeURIComponent(source.id)}/collection-detail?${params.toString()}`,
              { headers: { Authorization: `Bearer ${authToken}` } },
            );
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
              throw new Error(String(data.detail || data.message || '样例数据加载失败'));
            }
            return {
              loading: false,
              error: '',
              rows: extractCollectionDetailSampleRows(data, RULE_GENERATION_SAMPLE_ROW_LIMIT),
            };
          })();
          DATASET_PREVIEW_CACHE.set(cacheKey, previewRequest);
        }
        const nextPreview = await previewRequest;
        if (!cancelled) {
          setPreview(nextPreview);
        }
      } catch (error) {
        DATASET_PREVIEW_CACHE.delete(datasetStructureCacheKey(source, 'preview'));
        if (!cancelled) {
          setPreview({
            loading: false,
            error: error instanceof Error ? error.message : '样例数据加载失败',
            rows: [],
          });
        }
      }
    }

    void fetchPreview();
    return () => {
      cancelled = true;
    };
  }, [authToken, source.datasetCode, source.id, source.name, source.resourceKey, source.sourceId, source.technicalName]);

  useEffect(() => {
    let cancelled = false;

    async function fetchFieldLabels() {
      const localFields = buildDatasetFieldItems(source);
      if (!authToken || !source.sourceId) {
        setFieldItems(localFields.length > 0 ? localFields : null);
        return;
      }

      try {
        const cacheKey = datasetStructureCacheKey(source, 'fields');
        let fieldsRequest = DATASET_FIELD_ITEMS_CACHE.get(cacheKey);
        if (!fieldsRequest) {
          fieldsRequest = (async () => {
            const response = await fetch('/api/recon/schemes/design/dataset-fields', {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${authToken}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                source_id: source.sourceId,
                resource_key: source.resourceKey || source.datasetCode || source.technicalName || source.name,
                dataset_id: source.id,
              }),
            });
            const data = await response.json().catch(() => ({}));
            return response.ok && Array.isArray(data.fields)
              ? (data.fields as FieldItem[])
                  .map((field) => ({
                    raw_name: toText(field.raw_name).trim(),
                    display_name: toText(field.display_name, toText(field.raw_name)).trim(),
                  }))
                  .filter((field) => field.raw_name)
              : [];
          })();
          DATASET_FIELD_ITEMS_CACHE.set(cacheKey, fieldsRequest);
        }
        const fields = await fieldsRequest;
        if (!cancelled) {
          const mergedFields = mergeFieldItems(fields, localFields);
          setFieldItems(mergedFields.length > 0 ? mergedFields : null);
        }
      } catch {
        DATASET_FIELD_ITEMS_CACHE.delete(datasetStructureCacheKey(source, 'fields'));
        if (!cancelled) {
          setFieldItems(localFields.length > 0 ? localFields : null);
        }
      }
    }

    void fetchFieldLabels();
    return () => {
      cancelled = true;
    };
  }, [authToken, source.datasetCode, source.id, source.name, source.resourceKey, source.sourceId, source.technicalName]);

  const fields = (fieldItems && fieldItems.length > 0) ? fieldItems : buildDatasetFieldItems(source, preview.rows);
  const fieldByRawName = useMemo(
    () => new Map(fields.map((field) => [field.raw_name, field])),
    [fields],
  );
  const displayColumns = mergeDatasetDisplayColumns(fields, preview.rows);

  return (
    <div className="rounded-3xl border border-border bg-white/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{resolveDatasetDisplayName(source)}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{resolveDatasetTechnicalName(source)}</p>
        </div>
        <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
          {source.sourceKind}
        </span>
      </div>

      <div className="mt-4 rounded-2xl border border-border bg-surface px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">表结构和样例 20 条数据</p>
            <p className="mt-1 text-[11px] text-text-muted">列名优先显示中文名称，下方显示原始字段名。</p>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-text-muted">
            {fields.length > 0 ? <span>{fields.length} 字段</span> : null}
            {preview.loading ? <span className="text-sky-700">加载中...</span> : null}
          </div>
        </div>
        <div className="mt-3 max-h-[280px] overflow-auto rounded-xl border border-border bg-white">
          {preview.loading ? (
            <p className="px-3 py-3 text-sm text-text-secondary">正在加载样例数据...</p>
          ) : preview.error ? (
            <p className="px-3 py-3 text-sm text-amber-700">{preview.error}</p>
          ) : displayColumns.length === 0 ? (
            <p className="px-3 py-3 text-sm text-text-secondary">暂无字段结构和样例数据。后续可通过数据采集或样例执行补充。</p>
          ) : (
            <table className="w-max min-w-full divide-y divide-border text-left text-xs">
              <thead className="sticky top-0 z-10 bg-surface-secondary text-text-secondary">
                <tr>
                  {displayColumns.map((column) => {
                    const field = fieldByRawName.get(column);
                    const displayName = field?.display_name || column;
                    return (
                      <th key={column} className="whitespace-nowrap px-3 py-2 font-medium align-bottom">
                        <span className="block whitespace-nowrap text-text-primary">{displayName}</span>
                        <span className="mt-0.5 block whitespace-nowrap text-[10px] font-normal text-text-muted">
                          {column}
                        </span>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-text-primary">
                {preview.rows.length > 0 ? (
                  preview.rows.map((row, rowIndex) => (
                    <tr key={`ai-dataset-sample-${source.id}-${rowIndex}`} className="hover:bg-surface-secondary/60">
                      {displayColumns.map((column) => (
                        <td
                          key={`${rowIndex}-${column}`}
                          className="max-w-64 truncate px-3 py-2"
                          title={formatSampleCellValue(row[column])}
                        >
                          {formatSampleCellValue(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={displayColumns.length} className="px-3 py-4 text-center text-sm text-text-secondary">
                      暂无样例数据，已先展示字段结构。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function AiSideConfigurationPanel({
  side,
  active,
  authToken,
  schemeDraft,
  selectedSources,
  sideDraft,
  onChangeSourceSelection,
  onChangeRuleDraft,
  onGenerateOutput,
  onSwitchSide,
}: {
  side: AiProcSide;
  active: boolean;
  authToken?: string | null;
  schemeDraft: SchemeDraftLite;
  selectedSources: SchemeSourceOption[];
  sideDraft: AiProcSideDraft;
  onChangeSourceSelection: (side: AiProcSide, sources: SchemeSourceOption[]) => void;
  onChangeRuleDraft: (side: AiProcSide, value: string) => void;
  onGenerateOutput: (side: AiProcSide) => void;
  onSwitchSide: (side: AiProcSide) => void;
}) {
  const isLeft = side === 'left';
  const sideLabel = isLeft ? '左侧' : '右侧';
  const nextSideLabel = isLeft ? '右侧' : '左侧';
  const targetTable = isLeft ? 'left_recon_ready' : 'right_recon_ready';
  const isGenerating = sideDraft.status === 'generating';
  const hasGeneratedOutput = sideDraft.outputRows.length > 0;
  const statusLabel =
    sideDraft.status === 'succeeded'
      ? '已生成'
      : sideDraft.status === 'failed'
      ? '生成失败'
      : sideDraft.status === 'needs_user_input'
      ? '需补充'
      : sideDraft.status === 'generating'
      ? '生成中'
      : '待生成';

  if (!active) return null;

  return (
    <div className="space-y-5">
      <RemoteDatasetSelector
        side={side}
        title={`选择${sideLabel}数据集`}
        description={`可选择 1 个或多个${sideLabel}原始数据集。AI 只负责把这些数据整理成 ${targetTable}。`}
        authToken={authToken}
        businessGoal={schemeDraft.businessGoal}
        sideDescription={isLeft ? schemeDraft.leftDescription : schemeDraft.rightDescription}
        selectedSources={selectedSources}
        onConfirmSelection={(sources) => onChangeSourceSelection(side, sources)}
        allowMultiple
      />

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">{sideLabel}数据集样例</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">
              每个数据集用样例表展示字段和最新 20 条数据，作为 AI 对话的固定上下文。
            </p>
          </div>
          <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
            {selectedSources.length} 个数据集
          </span>
        </div>
        {selectedSources.length > 0 ? (
          selectedSources.map((source) => (
            <DatasetStructureCard key={source.id} authToken={authToken} source={source} />
          ))
        ) : (
          <div className="rounded-3xl border border-dashed border-border bg-white/70 px-5 py-8 text-center text-sm text-text-secondary">
            先选择{sideLabel}数据集，下面会展示字段和样例数据。
          </div>
        )}
      </div>

      <div className="rounded-3xl border border-border bg-white/85 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border-subtle pb-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">{sideLabel} AI 对话</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">
              描述这一侧如何整理。系统会完成规则理解、生成、校验、样例执行和断言验证。
            </p>
          </div>
          <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-700">
            输出：{targetTable}
          </span>
        </div>

        <div className="mt-4 space-y-3">
          <div className="max-w-[88%] rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm leading-6 text-text-secondary">
            你可以直接描述{sideLabel}数据整理规则。我会只处理当前这一侧的数据，生成整理后的输出表。
          </div>
        </div>

        <RuleGenerationInlineProgress traces={sideDraft.nodeTraces} status={sideDraft.status} />
        <RuleGenerationFeedback sideDraft={sideDraft} />

        <label className="mt-4 block">
          <span className="text-xs font-semibold tracking-[0.14em] text-text-muted">输入{sideLabel}整理规则</span>
          <textarea
            rows={5}
            value={sideDraft.ruleDraft}
            onChange={(event) => onChangeRuleDraft(side, event.target.value)}
            placeholder={
              isLeft
                ? '例如：把这些左侧表按客户编码合并，过滤作废记录，统一输出客户、单据号、日期、金额。'
                : '例如：把这些右侧表按订单号汇总，金额统一为本位币，输出订单号、日期、金额和来源系统。'
            }
            className="mt-3 w-full resize-none rounded-2xl border border-border bg-surface px-4 py-3 text-sm leading-6 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          />
        </label>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => onGenerateOutput(side)}
            disabled={isGenerating || !sideDraft.ruleDraft.trim() || selectedSources.length === 0}
            className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isGenerating ? 'AI生成中...' : 'AI生成输出数据'}
          </button>
          <button
            type="button"
            onClick={() => onSwitchSide(isLeft ? 'right' : 'left')}
            className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
          >
            配置{nextSideLabel}数据
          </button>
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-white/85 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">{sideLabel}输出数据预览</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">
              执行成功后，这里展示整理后的字段、样例数据、校验状态和 JSON 入口。
            </p>
          </div>
          <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
            {statusLabel}
          </span>
        </div>
        <div className="mt-4">
          {hasGeneratedOutput ? (
            <RowTable
              rows={sideDraft.outputRows}
              fieldLabelMap={sideDraft.outputFieldLabelMap}
              columnHints={sideDraft.outputColumnHints}
              showRawFieldName={false}
            />
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-surface px-4 py-8 text-center text-sm text-text-secondary">
              完成{sideLabel} AI 生成和样例执行后，将展示 {targetTable} 的输出样例。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RuleGenerationInlineProgress({
  traces,
  status,
}: {
  traces: RuleGenerationNodeTrace[];
  status: AiProcSideDraft['status'];
}) {
  const items = traces.length > 0 ? traces : DEFAULT_RULE_GENERATION_NODES;
  const hasStarted = items.some((trace) => trace.status !== 'pending');
  if (!hasStarted && status === 'idle') return null;

  const activeTrace = resolveActiveRuleGenerationTrace(items);
  const failed = status === 'failed';
  const needsInput = activeTrace?.status === 'needs_user_input' || status === 'needs_user_input';
  const succeeded = status === 'succeeded';
  const title = failed
    ? '生成失败'
    : needsInput
    ? '需要补充规则口径'
    : succeeded
    ? '生成完成'
    : 'AI正在生成输出数据';

  const statusTone = failed
    ? 'border-red-200 bg-red-50 text-red-700'
    : needsInput
    ? 'border-amber-200 bg-amber-50 text-amber-700'
    : succeeded
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-sky-100 bg-sky-50/70 text-sky-800';

  return (
    <div className={cn('mt-4 rounded-2xl border px-4 py-3', statusTone)}>
      <div className="flex items-start gap-3">
        {!failed && !needsInput && !succeeded ? (
          <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
        ) : (
          <span className={cn('mt-1 h-2.5 w-2.5 shrink-0 rounded-full', failed ? 'bg-red-500' : needsInput ? 'bg-amber-500' : 'bg-emerald-500')} />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">
            {formatRuleGenerationProgressLine(activeTrace)}
          </p>
        </div>
      </div>
      {activeTrace ? (
        <p className="mt-2 line-clamp-2 text-xs leading-5 text-text-secondary">
          {formatRuleGenerationProgressMessage(activeTrace)}
        </p>
      ) : null}
      {activeTrace && activeTrace.status === 'running' && activeTrace.code === 'repair_ir' && activeTrace.attempt > 1 ? (
        <p className="mt-1 text-[11px] text-amber-700">正在第 {activeTrace.attempt} 次自动修复。</p>
      ) : null}
    </div>
  );
}

function RuleGenerationFeedback({ sideDraft }: { sideDraft: AiProcSideDraft }) {
  const hasQuestions = sideDraft.questions.length > 0;
  const hasError = sideDraft.status === 'failed' && Boolean(sideDraft.error || sideDraft.summary);
  const technicalDetails = buildRuleGenerationTechnicalDetails(sideDraft);
  const secondaryFailureReasons = sideDraft.failureReasons.filter((reason) => reason !== sideDraft.error);
  if (sideDraft.status === 'idle' || (!hasQuestions && !hasError)) {
    return null;
  }
  const tone = sideDraft.status === 'failed'
    ? 'border-red-200 bg-red-50 text-red-700'
    : sideDraft.status === 'needs_user_input'
    ? 'border-amber-200 bg-amber-50 text-amber-800'
    : sideDraft.status === 'succeeded'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-sky-100 bg-sky-50 text-sky-800';
  return (
    <div className={cn('mt-3 rounded-2xl border px-4 py-3 text-sm leading-6', tone)}>
      {hasError ? (
        <div className="space-y-2">
          <p>{sideDraft.error || sideDraft.summary}</p>
          {secondaryFailureReasons.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs leading-5">
              {secondaryFailureReasons.map((reason, index) => (
                <li key={`${reason}-${index}`}>{reason}</li>
              ))}
            </ul>
          ) : null}
          {technicalDetails ? (
            <details className="rounded-xl border border-red-200/80 bg-white/70 px-3 py-2 text-xs text-text-secondary">
              <summary className="cursor-pointer select-none font-medium text-red-700">技术详情</summary>
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5">
                {technicalDetails}
              </pre>
            </details>
          ) : null}
        </div>
      ) : null}
      {hasQuestions ? (
        <div className="space-y-2">
          {sideDraft.questions.map((question) => (
            <div key={question.id} className="rounded-xl border border-amber-200 bg-white/75 p-3 text-xs leading-5 text-amber-800">
              <p className="font-semibold">{question.question}</p>
              {question.candidates?.length ? (
                <p className="mt-1">候选：{question.candidates.map(formatQuestionCandidate).join(' / ')}</p>
              ) : null}
              <p className="mt-1 text-[11px] text-amber-700/80">请修改上方完整规则描述后重新生成。</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function resolveActiveRuleGenerationTrace(items: RuleGenerationNodeTrace[]) {
  return (
    items.find((trace) => trace.status === 'running')
    || [...items].reverse().find((trace) => trace.status === 'needs_user_input')
    || [...items].reverse().find((trace) => trace.status === 'failed')
    || [...items].reverse().find((trace) => trace.status === 'completed')
    || items.find((trace) => trace.status === 'pending')
  );
}

function formatQuestionCandidate(candidate: AiProcQuestionCandidate): string {
  if (typeof candidate === 'string') return candidate;
  const rawName = String(candidate.rawName || '').trim();
  const displayName = String(candidate.displayName || rawName).trim();
  return displayName || rawName;
}

const DEFAULT_RULE_GENERATION_NODES: RuleGenerationNodeTrace[] = [
  ['prepare_context', '准备数据集信息'],
  ['understand_rule', '理解整理描述'],
  ['validate_ir_structure', '检查描述结构'],
  ['resolve_source_bindings', '检查字段对应关系'],
  ['lint_ir', '检查整理规则'],
  ['repair_ir', '自动修复规则'],
  ['semantic_resolution', '自动处理字段歧义'],
  ['ambiguity_gate', '判断是否需要补充描述'],
  ['generate_proc_json', '生成整理规则'],
  ['check_ir_dsl_consistency', '检查规则一致性'],
  ['lint_proc_json', '检查规则可执行性'],
  ['build_sample_inputs', '读取样例数据'],
  ['run_sample', '试跑输出数据'],
  ['diagnose_sample', '诊断试跑结果'],
  ['assert_output', '核对输出结果'],
  ['result', '整理完成'],
].map(([code, name]) => ({ code, name, status: 'pending', message: '', attempt: 1 }));

function formatRuleGenerationProgressLine(trace?: RuleGenerationNodeTrace) {
  if (!trace) return '等待开始';
  return trace.name || '正在处理';
}

function formatRuleGenerationProgressMessage(trace: RuleGenerationNodeTrace) {
  if (trace.status === 'failed') {
    if (trace.code === 'repair_ir') return '自动修复没有完成，请查看失败原因或修改描述后重新生成。';
    if (trace.code === 'run_sample' || trace.code === 'assert_output') return '规则已生成，但样例试跑结果未达到预期。';
    if (trace.code === 'diagnose_sample') return '样例试跑问题已完成诊断，请查看失败原因。';
    return '当前步骤未通过，请查看失败原因。';
  }
  if (trace.status === 'completed') {
    if (trace.code === 'result') return '输出数据已生成并通过样例试跑。';
    return '已完成。';
  }
  if (trace.status === 'needs_user_input') {
    return '需要你补充或改写描述后重新生成。';
  }
  if (trace.code === 'prepare_context') return '正在读取已选数据集、字段中文名和样例数据。';
  if (trace.code === 'understand_rule') return '正在根据你的描述理解要保留、过滤、关联或计算的数据。';
  if (trace.code === 'resolve_source_bindings') return '正在确认描述中的字段能否对应到已选数据集。';
  if (trace.code === 'lint_ir' || trace.code === 'validate_ir_structure') return '正在检查规则是否完整、是否存在遗漏。';
  if (trace.code === 'repair_ir') return `发现规则问题，正在自动修复，第 ${trace.attempt || 1} 次。`;
  if (trace.code === 'semantic_resolution' || trace.code === 'ambiguity_gate') return '正在判断是否有字段或口径需要你确认。';
  if (trace.code === 'generate_proc_json') return '正在生成可执行的数据整理规则。';
  if (trace.code === 'check_ir_dsl_consistency' || trace.code === 'lint_proc_json') return '正在检查整理规则能否稳定执行。';
  if (trace.code === 'build_sample_inputs') return '正在读取样例数据。';
  if (trace.code === 'run_sample') return '正在用样例数据试跑，验证能否生成输出数据。';
  if (trace.code === 'diagnose_sample') return '试跑结果未达到预期，正在定位原因。';
  if (trace.code === 'assert_output') return '正在核对输出字段和输出样例。';
  return '正在处理。';
}

function buildRuleGenerationTechnicalDetails(sideDraft: AiProcSideDraft) {
  const failedTraces = sideDraft.nodeTraces.filter((trace) => trace.status === 'failed');
  const detail = {
    status: sideDraft.status,
    error: sideDraft.error,
    failure_reasons: sideDraft.failureReasons,
    failure_details: sideDraft.failureDetails,
    failed_nodes: failedTraces.map((trace) => ({
      code: trace.code,
      name: trace.name,
      attempt: trace.attempt,
      duration_ms: trace.durationMs,
      message: trace.message,
      summary: trace.summary,
      errors: trace.errors,
    })),
  };
  if (
    !sideDraft.error
    && sideDraft.failureReasons.length === 0
    && sideDraft.failureDetails.length === 0
    && failedTraces.length === 0
  ) {
    return '';
  }
  return JSON.stringify(detail, null, 2);
}

function createEmptyAiProcSideDraft(): AiProcSideDraft {
  return {
    ruleDraft: '',
    status: 'idle',
    summary: '',
    error: '',
    failureReasons: [],
    failureDetails: [],
    nodeTraces: DEFAULT_RULE_GENERATION_NODES.map((node) => ({ ...node })),
    questions: [],
    assumptions: [],
    validations: [],
    warnings: [],
    outputRows: [],
    outputFieldLabelMap: {},
    outputColumnHints: {},
  };
}

function normalizeAiProcSideDrafts(
  drafts?: Partial<Record<AiProcSide, AiProcSideDraft>>,
): Record<AiProcSide, AiProcSideDraft> {
  return {
    left: drafts?.left || createEmptyAiProcSideDraft(),
    right: drafts?.right || createEmptyAiProcSideDraft(),
  };
}

function AiComplexRuleWorkspace({
  authToken,
  schemeDraft,
  selectedLeftSources,
  selectedRightSources,
  aiProcSideDrafts,
  onChangeSourceSelection,
  onChangeRuleDraft,
  onGenerateOutput,
}: {
  authToken?: string | null;
  schemeDraft: SchemeDraftLite;
  selectedLeftSources: SchemeSourceOption[];
  selectedRightSources: SchemeSourceOption[];
  aiProcSideDrafts: Record<AiProcSide, AiProcSideDraft>;
  onChangeSourceSelection: (side: AiProcSide, sources: SchemeSourceOption[]) => void;
  onChangeRuleDraft: (side: AiProcSide, value: string) => void;
  onGenerateOutput: (side: AiProcSide) => void;
}) {
  const [activeSide, setActiveSide] = useState<'left' | 'right'>('left');
  const leftReady = selectedLeftSources.length > 0;
  const rightReady = selectedRightSources.length > 0;

  return (
    <div className="rounded-3xl border border-sky-100 bg-[linear-gradient(135deg,rgba(240,249,255,0.95),rgba(255,255,255,0.9))] p-5 shadow-[0_18px_55px_rgba(14,165,233,0.10)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-medium text-sky-700">
            <Sparkles className="h-3.5 w-3.5" />
            AI复杂规则分步配置
          </div>
          <p className="mt-3 text-sm font-semibold text-text-primary">先配置左侧数据，再配置右侧数据</p>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
            每一侧都可以选择多个数据集，查看字段样例表，再通过一个 AI 对话完成规则理解、生成、校验、样例执行和断言验证。
            两侧都完成后再进入第三步配置对账逻辑。
          </p>
        </div>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
          当前为 UI 预览
        </span>
      </div>

      <div className="mt-5 rounded-2xl border border-border bg-white/75 p-2">
        <div className="grid gap-2 md:grid-cols-2">
          {(['left', 'right'] as const).map((side) => {
            const active = activeSide === side;
            const label = side === 'left' ? '左侧数据配置' : '右侧数据配置';
            const count = side === 'left' ? selectedLeftSources.length : selectedRightSources.length;
            const ready = side === 'left' ? leftReady : rightReady;
            return (
              <button
                key={side}
                type="button"
                onClick={() => setActiveSide(side)}
                className={cn(
                  'rounded-xl border px-4 py-3 text-left transition',
                  active
                    ? 'border-sky-300 bg-sky-50 text-sky-800'
                    : 'border-transparent bg-surface text-text-secondary hover:border-sky-100 hover:text-sky-700',
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold">{label}</span>
                  <span
                    className={cn(
                      'rounded-full border px-2.5 py-1 text-xs font-medium',
                      ready
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-border bg-white text-text-muted',
                    )}
                  >
                    {ready ? `${count} 个数据集` : '待选择'}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5">
                  {side === 'left'
                    ? '生成 left_recon_ready，后续作为对账左侧输入。'
                    : '生成 right_recon_ready，后续作为对账右侧输入。'}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-5">
        <AiSideConfigurationPanel
          side="left"
          active={activeSide === 'left'}
          authToken={authToken}
          schemeDraft={schemeDraft}
          selectedSources={selectedLeftSources}
          sideDraft={aiProcSideDrafts.left}
          onChangeSourceSelection={onChangeSourceSelection}
          onChangeRuleDraft={onChangeRuleDraft}
          onGenerateOutput={onGenerateOutput}
          onSwitchSide={setActiveSide}
        />
        <AiSideConfigurationPanel
          side="right"
          active={activeSide === 'right'}
          authToken={authToken}
          schemeDraft={schemeDraft}
          selectedSources={selectedRightSources}
          sideDraft={aiProcSideDrafts.right}
          onChangeSourceSelection={onChangeSourceSelection}
          onChangeRuleDraft={onChangeRuleDraft}
          onGenerateOutput={onGenerateOutput}
          onSwitchSide={setActiveSide}
        />
      </div>
    </div>
  );
}

function RemoteDatasetSelector({
  side,
  title,
  description,
  authToken,
  businessGoal,
  sideDescription,
  selectedSources,
  onConfirmSelection,
  allowMultiple = false,
}: {
  side: 'left' | 'right';
  title: string;
  description: string;
  authToken?: string | null;
  businessGoal: string;
  sideDescription: string;
  selectedSources: SchemeSourceOption[];
  onConfirmSelection: (sources: SchemeSourceOption[]) => void;
  allowMultiple?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resultSources, setResultSources] = useState<SchemeSourceOption[]>([]);
  const [draftSources, setDraftSources] = useState<SchemeSourceOption[]>(selectedSources);
  const { popupDatasetId, popupPos, fieldCache, fetchingFields, openPopup, closePopup } =
    useFieldPreview(authToken);
  const searchedRef = useRef(false);

  const selectedNames = useMemo(
    () => selectedSources.map((item) => resolveDatasetDisplayName(item)),
    [selectedSources],
  );
  const resultById = useMemo(
    () => new Map(resultSources.map((item) => [item.id, item])),
    [resultSources],
  );
  const draftIds = useMemo(() => draftSources.map((item) => item.id), [draftSources]);
  const displayText = selectedNames.length > 0
    ? allowMultiple
      ? `已选择 ${selectedNames.length} 个数据集`
      : selectedNames[0]
    : '点击搜索并选择数据集';

  const fetchCandidates = useCallback(
    async (query: string) => {
      const keyword = query.trim();
      if (!authToken) {
        setError('请先登录后再选择数据集。');
        setResultSources([]);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const response = await fetch('/api/data-sources/dataset-candidates', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            binding_scope: 'execution_scheme',
            scene_type: 'recon',
            role_code: side,
            keyword,
            page: 1,
            page_size: 30,
            filters: {
              only_published: true,
              strict_contract: false,
              hints: [businessGoal, sideDescription, title].filter((item) => item.trim().length > 0),
            },
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '候选数据集搜索失败'));
        }
        const rows = asList(data.candidates || data.datasets || data.items);
        const normalized = rows
          .map((item) => normalizeCandidateDataset(item))
          .filter(Boolean) as SchemeSourceOption[];
        setResultSources(normalized);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : '候选数据集搜索失败');
        setResultSources([]);
      } finally {
        setLoading(false);
      }
    },
    [authToken, businessGoal, side, sideDescription, title],
  );


  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      searchedRef.current = true;
      void fetchCandidates(searchText);
    }, 260);
    return () => window.clearTimeout(timer);
  }, [fetchCandidates, open, searchText]);

  const togglePanel = () => {
    if (open) {
      setOpen(false);
      setDraftSources(selectedSources);
      closePopup();
      return;
    }
    setOpen(true);
    setDraftSources(selectedSources);
    setSearchText('');
    setResultSources([]);
    setError('');
    closePopup();
    searchedRef.current = false;
  };

  const toggleSource = (source: SchemeSourceOption) => {
    setDraftSources((prev) => {
      if (prev.some((item) => item.id === source.id)) {
        return allowMultiple ? prev.filter((item) => item.id !== source.id) : [];
      }
      return allowMultiple ? [...prev, source] : [source];
    });
  };

  const handleConfirm = () => {
    onConfirmSelection(allowMultiple ? draftSources : draftSources.slice(0, 1));
    setOpen(false);
    closePopup();
  };

  return (
    <div className="rounded-3xl border border-border bg-surface-secondary p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
        </div>
        <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
          已选 {allowMultiple ? selectedSources.length : Math.min(selectedSources.length, 1)}
        </span>
      </div>

      {selectedSources.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {selectedSources.map((src) => (
            <span
              key={src.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-800"
            >
              {resolveDatasetDisplayName(src)}
            </span>
          ))}
        </div>
      ) : null}

      <div className="relative mt-3">
        <button
          type="button"
          onClick={togglePanel}
          className="flex w-full items-center justify-between rounded-2xl border border-border bg-surface px-4 py-3 text-left text-sm text-text-primary transition hover:border-sky-200"
        >
          <span className="text-text-secondary">{displayText}</span>
          <ChevronDown className={cn('ml-2 h-4 w-4 shrink-0 text-text-muted transition-transform', open && 'rotate-180')} />
        </button>

        {open ? (
          <div className="absolute left-0 right-0 z-20 mt-2 overflow-hidden rounded-2xl border border-border bg-surface shadow-xl">
            <div className="border-b border-border px-3 py-3">
              <input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                placeholder="搜索数据集…"
              />
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-[11px] text-text-muted">
                  {allowMultiple ? '可选择多个数据集，作为当前侧 AI 整理上下文。' : '当前版本每侧先选择 1 个数据集。'}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setDraftSources([])}
                    className="rounded-xl border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary transition hover:border-sky-200 hover:text-sky-700"
                  >
                    清空
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirm}
                    className="rounded-xl bg-sky-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-sky-500"
                  >
                    确定
                  </button>
                </div>
              </div>
            </div>

            <div className="max-h-72 overflow-y-auto p-2 space-y-1">
              {error ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">{error}</div>
              ) : null}
              {loading ? (
                <div className="px-3 py-3 text-xs text-text-muted">正在搜索…</div>
              ) : null}
              {!loading && !error && !searchedRef.current ? (
                <div className="px-3 py-3 text-xs text-text-muted">正在准备候选列表…</div>
              ) : null}
              {!loading && !error && searchedRef.current && resultSources.length === 0 ? (
                <div className="px-3 py-3 text-xs text-text-muted">暂无候选数据集，可更换关键字或先发布数据集。</div>
              ) : null}
              {!loading && !error && resultSources.length > 0
                ? resultSources.map((dataset) => {
                    const checked = draftIds.includes(dataset.id);
                    const checkedSource = checked ? draftSources.find((item) => item.id === dataset.id) : undefined;
                    const resolved = checkedSource || resultById.get(dataset.id) || dataset;
                    const isPopupOpen = popupDatasetId === dataset.id;
                    return (
                      <div
                        key={dataset.id}
                        className={cn(
                          'flex cursor-pointer items-center gap-2.5 rounded-xl border px-2.5 py-2 transition select-none',
                          isPopupOpen
                            ? 'border-sky-300 bg-sky-50'
                            : checked
                            ? 'border-sky-100 bg-sky-50/50 hover:border-sky-200'
                            : 'border-transparent hover:border-border-subtle hover:bg-surface-secondary',
                        )}
                        onClick={(e) => openPopup(dataset, e.currentTarget)}
                      >
                        <input
                          type={allowMultiple ? 'checkbox' : 'radio'}
                          checked={checked}
                          onChange={() => toggleSource(resolved)}
                          onClick={(e) => e.stopPropagation()}
                          name={`dataset-selector-${side}`}
                          className="h-4 w-4 shrink-0 rounded border-border text-sky-600 focus:ring-sky-200"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-text-primary">
                            {resolveDatasetDisplayName(dataset)}
                          </p>
                          <p className="truncate text-[11px] text-text-muted">
                            {resolveDatasetTechnicalName(dataset)}
                          </p>
                        </div>
                        <span className="shrink-0 text-[11px] text-text-muted">查看字段 →</span>
                      </div>
                    );
                  })
                : null}
            </div>
          </div>
        ) : null}

        {popupDatasetId ? (() => {
          const pd = resultSources.find((d) => d.id === popupDatasetId);
          return (
            <FieldPreviewPopup
              datasetName={pd ? resolveDatasetDisplayName(pd) : ''}
              fields={fieldCache[popupDatasetId] ?? []}
              loading={fetchingFields === popupDatasetId}
              pos={popupPos}
              onClose={closePopup}
            />
          );
        })() : null}
      </div>
    </div>
  );
}

function ProcTrialPreviewPanel({
  draftStatus,
  draftSummary,
  preview,
}: {
  draftStatus: TrialStatus;
  draftSummary: string;
  preview?: ProcTrialPreview;
}) {
  const [activeSection, setActiveSection] = useState<PreviewSection>('left');
  const hasPreview = Boolean(preview);
  const summary = preview?.summary || draftSummary;
  const meta = trialStatusMeta(preview?.status || draftStatus);
  const validations = preview?.validations || [];

  if (!hasPreview && !summary) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className={cn('inline-flex rounded-full border px-3 py-1 text-xs font-medium', meta.className)}>
            {meta.label}
          </span>
          <p className="text-sm leading-6 text-text-secondary">
            {summary || '点击试跑验证后，会展示整理前后的抽样数据结果。'}
          </p>
        </div>
        {validations.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {validations.map((item) => (
              <span
                key={item}
                className="rounded-full border border-current/15 bg-white/70 px-2.5 py-1 text-xs text-text-secondary"
              >
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {hasPreview ? (
        <div className="space-y-4">
          <div className="sticky top-0 z-[1] rounded-2xl border border-border bg-surface/95 p-2 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setActiveSection('left')}
                className={cn(
                  'rounded-xl px-4 py-2 text-sm font-medium transition',
                  activeSection === 'left'
                    ? 'bg-text-primary text-white'
                    : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
                )}
              >
                左侧数据
              </button>
              <button
                type="button"
                onClick={() => setActiveSection('right')}
                className={cn(
                  'rounded-xl px-4 py-2 text-sm font-medium transition',
                  activeSection === 'right'
                    ? 'bg-text-primary text-white'
                    : 'border border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
                )}
              >
                右侧数据
              </button>
            </div>
          </div>

          {activeSection === 'left' && preview ? (
            <div className="space-y-4">
              <PreviewSectionBlock
                title="左侧原始数据抽样"
                description="每个数据源分别展示列名与 3 条抽样数据。"
                groups={preview.leftSourceSamples}
              />
              <PreviewSectionBlock
                title="整理后左侧输出"
                description="根据当前数据整理规则生成的左侧标准化结果。"
                groups={preview.leftOutputSamples}
              />
            </div>
          ) : preview ? (
            <div className="space-y-4">
              <PreviewSectionBlock
                title="右侧原始数据抽样"
                description="每个数据源分别展示列名与 3 条抽样数据。"
                groups={preview.rightSourceSamples}
              />
              <PreviewSectionBlock
                title="整理后右侧输出"
                description="根据当前数据整理规则生成的右侧标准化结果。"
                groups={preview.rightOutputSamples}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function SchemeWizardTargetProcStep({
  authToken,
  schemeDraft,
  selectedLeftSources,
  selectedRightSources,
  leftOutputFields,
  rightOutputFields,
  procBuildMode = 'ai_complex_rule',
  aiProcSideDrafts,
  procCompatibility,
  onChangeProcBuildMode = () => undefined,
  onChangeAiProcRuleDraft = () => undefined,
  onGenerateAiProcOutput = () => undefined,
  onChangeSourceSelection,
  onChangeOutputFields,
  onRecommendOutputFields,
  isTrialingProc = false,
  onTrialProc,
  onViewProcJson,
  procJsonPreview,
  procTrialPreview,
}: SchemeWizardTargetProcStepProps) {
  const previewAnchorRef = useRef<HTMLDivElement | null>(null);
  const scrollToPreviewPendingRef = useRef(false);
  const normalizedAiProcSideDrafts = normalizeAiProcSideDrafts(aiProcSideDrafts);
  const showCompatibility =
    procCompatibility.status !== 'idle' ||
    procCompatibility.details.length > 0 ||
    procCompatibility.message !== '等待校验';

  useEffect(() => {
    if (!scrollToPreviewPendingRef.current || !procTrialPreview) {
      return;
    }
    previewAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    scrollToPreviewPendingRef.current = false;
  }, [procTrialPreview]);

  useEffect(() => {
    if (procBuildMode !== 'ai_complex_rule') {
      onChangeProcBuildMode('ai_complex_rule');
    }
  }, [onChangeProcBuildMode, procBuildMode]);

  const handleTrialProc = () => {
    scrollToPreviewPendingRef.current = true;
    onTrialProc();
  };

  const trialMeta = trialStatusMeta(procTrialPreview?.status || schemeDraft.procTrialStatus);
  const compactStatusText = (
    procTrialPreview?.summary
    || schemeDraft.procTrialSummary
    || (showCompatibility ? procCompatibility.message : '')
  ).trim();
  const compactDetailsText = procCompatibility.details.join('；').trim();
  const isSimpleBuildMode = SIMPLE_MAPPING_UI_ENABLED && procBuildMode === 'simple_mapping';

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-5">
        <p className="text-sm font-semibold text-text-primary">第二步：选择数据集并配置输出字段</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          当前版本聚焦 AI 生成整理规则：选择左右侧数据集后，用自然语言描述整理逻辑并生成输出数据。
        </p>

        {SIMPLE_MAPPING_UI_ENABLED ? (
          <div className="mt-5">
          <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">选择数据整理方式</p>
          <div className="mt-3">
            <ProcBuildModeSelector value={procBuildMode} onChange={onChangeProcBuildMode} />
          </div>
          </div>
        ) : null}

        {isSimpleBuildMode ? (
          <>
            <div className="mt-5">
              <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">1. 选择左右原始数据集</p>
              <div className="mt-3 grid gap-4 md:grid-cols-2">
                <RemoteDatasetSelector
                  side="left"
                  title="左侧原始数据"
                  description="按关键字远程搜索候选数据集，当前版本每侧先选择 1 个。"
                  authToken={authToken}
                  businessGoal={schemeDraft.businessGoal}
                  sideDescription={schemeDraft.leftDescription}
                  selectedSources={selectedLeftSources}
                  onConfirmSelection={(sources) => onChangeSourceSelection('left', sources)}
                />
                <RemoteDatasetSelector
                  side="right"
                  title="右侧原始数据"
                  description="按关键字远程搜索候选数据集，当前版本每侧先选择 1 个。"
                  authToken={authToken}
                  businessGoal={schemeDraft.businessGoal}
                  sideDescription={schemeDraft.rightDescription}
                  selectedSources={selectedRightSources}
                  onConfirmSelection={(sources) => onChangeSourceSelection('right', sources)}
                />
              </div>
            </div>

            <div className="mt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs font-semibold tracking-[0.14em] text-text-muted">2. 调整左右输出字段</p>
                <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs text-sky-700">
                  选完数据集后会自动推荐字段
                </span>
              </div>
              <div className="mt-3 grid gap-4 xl:grid-cols-2">
                <SchemeWizardOutputFieldEditor
                  authToken={authToken}
                  title="左侧输出字段"
                  sources={selectedLeftSources}
                  fields={leftOutputFields}
                  onChange={(fields) => onChangeOutputFields('left', fields)}
                  onRecommend={() => onRecommendOutputFields('left')}
                />
                <SchemeWizardOutputFieldEditor
                  authToken={authToken}
                  title="右侧输出字段"
                  sources={selectedRightSources}
                  fields={rightOutputFields}
                  onChange={(fields) => onChangeOutputFields('right', fields)}
                  onRecommend={() => onRecommendOutputFields('right')}
                />
              </div>
            </div>
          </>
        ) : (
          <div className="mt-5">
            <AiComplexRuleWorkspace
              authToken={authToken}
              schemeDraft={schemeDraft}
              selectedLeftSources={selectedLeftSources}
              selectedRightSources={selectedRightSources}
              aiProcSideDrafts={normalizedAiProcSideDrafts}
              onChangeSourceSelection={onChangeSourceSelection}
              onChangeRuleDraft={onChangeAiProcRuleDraft}
              onGenerateOutput={onGenerateAiProcOutput}
            />
          </div>
        )}
      </div>

      {isSimpleBuildMode ? (
        <div className="rounded-3xl border border-border bg-surface-secondary p-4">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleTrialProc}
              disabled={
                isTrialingProc
                || selectedLeftSources.length === 0
                || selectedRightSources.length === 0
                || leftOutputFields.length === 0
                || rightOutputFields.length === 0
              }
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <CheckCircle2 className={cn('h-4 w-4', isTrialingProc && 'animate-pulse')} />
              {isTrialingProc ? '试跑中...' : '试跑验证'}
            </button>
            {procJsonPreview ? (
              <button
                type="button"
                onClick={onViewProcJson}
                disabled={isTrialingProc}
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                查看 JSON
              </button>
            ) : null}
            <span className={cn('inline-flex rounded-full border px-3 py-1 text-xs font-medium', trialMeta.className)}>
              {trialMeta.label}
            </span>
          </div>

          {compactStatusText || compactDetailsText ? (
            <div
              className={cn(
                'mt-3 rounded-2xl border px-4 py-3 text-sm',
                procCompatibility.status === 'passed'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : procCompatibility.status === 'warning'
                  ? 'border-amber-200 bg-amber-50 text-amber-700'
                  : procCompatibility.status === 'failed'
                  ? 'border-amber-200 bg-amber-50 text-amber-700'
                  : 'border-border bg-surface text-text-secondary',
              )}
            >
              {compactStatusText ? <p>{compactStatusText}</p> : null}
              {compactDetailsText ? <p className="mt-1 text-xs leading-5 opacity-90">{compactDetailsText}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {isSimpleBuildMode ? (
        <div ref={previewAnchorRef} className="scroll-mt-24">
          <ProcTrialPreviewPanel
            draftStatus={schemeDraft.procTrialStatus}
            draftSummary={schemeDraft.procTrialSummary}
            preview={procTrialPreview}
          />
        </div>
      ) : null}
    </div>
  );
}
