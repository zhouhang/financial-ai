import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ChevronDown, Sparkles } from 'lucide-react';
import type { DataSourceKind } from '../../types';

export type TrialStatus = 'idle' | 'passed' | 'needs_adjustment';
type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

export interface SchemeDraftLite {
  name: string;
  businessGoal: string;
  leftDescription: string;
  rightDescription: string;
  procConfigMode: 'ai' | 'existing';
  selectedProcConfigId: string;
  procDraft: string;
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

export interface ProcSampleGroup {
  title: string;
  originLabel?: string;
  originHint?: string;
  fieldLabelMap?: Record<string, string>;
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

export interface ExistingConfigOption {
  id: string;
  name: string;
}

export interface CompatibilityCheckResult {
  status: 'idle' | 'passed' | 'failed' | 'warning';
  message: string;
  details: string[];
}

export interface SchemeWizardTargetProcStepProps {
  authToken?: string | null;
  schemeDraft: SchemeDraftLite;
  selectedLeftSources: SchemeSourceOption[];
  selectedRightSources: SchemeSourceOption[];
  existingProcOptions: ExistingConfigOption[];
  procCompatibility: CompatibilityCheckResult;
  onChangeSourceSelection: (side: 'left' | 'right', sources: SchemeSourceOption[]) => void;
  onProcConfigModeChange: (mode: 'ai' | 'existing') => void;
  onSelectExistingProcConfig: (configId: string) => void;
  isGeneratingProc?: boolean;
  generationSkill?: string;
  generationPhase?: string;
  generationMessage?: string;
  isTrialingProc?: boolean;
  onGenerateProc: () => void;
  onTrialProc: () => void;
  onProcDraftChange: (value: string) => void;
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

function formatGenerationPhase(phase: string) {
  if (phase === 'preparing_context') return '准备样例';
  if (phase === 'generating_rule') return '生成规则';
  if (phase === 'validating_rule') return '校验 JSON';
  if (phase === 'rendering_draft_text') return '整理说明';
  if (phase === 'completed') return '生成完成';
  if (phase === 'failed') return '生成失败';
  return '处理中';
}

function RowTable({
  rows,
  fieldLabelMap,
  showRawFieldName = true,
}: {
  rows: ProcSampleRow[];
  fieldLabelMap?: Record<string, string>;
  showRawFieldName?: boolean;
}) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-xs text-text-secondary">
        暂无抽样数据
      </div>
    );
  }

  const columns = Object.keys(rows[0] || {});

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
      <table className="w-full min-w-[520px] border-collapse text-xs">
        <thead>
          <tr className="border-b border-border-subtle text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">
            {columns.map((col) => {
              const label = fieldLabelMap?.[col]?.trim();
              const hasAlias = showRawFieldName && Boolean(label && label !== col);
              return (
                <th key={col} className="px-4 py-2 text-left font-semibold">
                  <span className="block max-w-[220px] truncate">{label || col}</span>
                  {hasAlias ? (
                    <span className="mt-0.5 block max-w-[220px] truncate text-[10px] font-normal normal-case tracking-normal text-text-muted">
                      {col}
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
                  <span className="block max-w-[220px] truncate">
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
    || normalizeFieldLabelMap(semanticProfile.field_label_map);
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
    schemaSummary: asRecord(value.schema_summary),
  };
}

type FieldItem = { raw_name: string; display_name: string };
type PopupPos = { top: number; left: number; maxWidth: number };

function useFieldPreview(authToken?: string | null) {
  const [popupDatasetId, setPopupDatasetId] = useState<string | null>(null);
  const [popupPos, setPopupPos] = useState<PopupPos>({ top: 0, left: 0, maxWidth: 320 });
  const [fieldCache, setFieldCache] = useState<Record<string, FieldItem[]>>({});
  const [fetchingFields, setFetchingFields] = useState<string | null>(null);

  const fetchFieldPreview = useCallback(
    async (dataset: SchemeSourceOption) => {
      if (dataset.fieldLabelMap && Object.keys(dataset.fieldLabelMap).length > 0) {
        const fields: FieldItem[] = Object.entries(dataset.fieldLabelMap).map(([raw, display]) => ({
          raw_name: raw,
          display_name: display,
        }));
        setFieldCache((prev) => ({ ...prev, [dataset.id]: fields }));
        return;
      }
      if (!authToken || !dataset.sourceId) return;
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
        setFieldCache((prev) => ({
          ...prev,
          [dataset.id]: response.ok && Array.isArray(data.fields) ? (data.fields as FieldItem[]) : [],
        }));
      } catch {
        setFieldCache((prev) => ({ ...prev, [dataset.id]: [] }));
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

function SourcesPreviewCard({
  label,
  sources,
  authToken,
}: {
  label: string;
  sources: SchemeSourceOption[];
  authToken?: string | null;
}) {
  const { popupDatasetId, popupPos, fieldCache, fetchingFields, openPopup, closePopup } =
    useFieldPreview(authToken);

  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-3">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-text-muted">{label}</p>
      {sources.length === 0 ? (
        <p className="mt-2 text-sm leading-6 text-text-secondary">--</p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {sources.map((src) => (
            <button
              key={src.id}
              type="button"
              onClick={(e) => openPopup(src, e.currentTarget)}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition',
                popupDatasetId === src.id
                  ? 'border-sky-300 bg-sky-100 text-sky-800'
                  : 'border-border bg-surface-secondary text-text-primary hover:border-sky-200 hover:bg-sky-50 hover:text-sky-700',
              )}
            >
              {resolveDatasetDisplayName(src)}
              <span className="text-[10px] opacity-50">字段</span>
            </button>
          ))}
        </div>
      )}
      {popupDatasetId ? (() => {
        const pd = sources.find((s) => s.id === popupDatasetId);
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
  );
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

function RemoteDatasetSelector({
  side,
  title,
  description,
  authToken,
  businessGoal,
  sideDescription,
  selectedSources,
  onConfirmSelection,
}: {
  side: 'left' | 'right';
  title: string;
  description: string;
  authToken?: string | null;
  businessGoal: string;
  sideDescription: string;
  selectedSources: SchemeSourceOption[];
  onConfirmSelection: (sources: SchemeSourceOption[]) => void;
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
  const displayText = selectedNames.length > 0 ? selectedNames.join('、') : '点击搜索并选择数据集';

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
        return prev.filter((item) => item.id !== source.id);
      }
      return [...prev, source];
    });
  };

  const handleConfirm = () => {
    onConfirmSelection(draftSources);
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
          已选 {selectedSources.length}
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
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={handleConfirm}
                  className="rounded-xl bg-sky-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-sky-500"
                >
                  确定（{draftSources.length}）
                </button>
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
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSource(resolved)}
                          onClick={(e) => e.stopPropagation()}
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
                description="根据当前数据整理配置生成的左侧标准化结果。"
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
                description="根据当前数据整理配置生成的右侧标准化结果。"
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
  existingProcOptions,
  procCompatibility,
  onChangeSourceSelection,
  onProcConfigModeChange,
  onSelectExistingProcConfig,
  isGeneratingProc = false,
  generationSkill = '整理配置生成器',
  generationPhase = 'generating_rule',
  generationMessage = '正在分析左右数据集结构与描述，并生成数据整理 JSON。',
  isTrialingProc = false,
  onGenerateProc,
  onTrialProc,
  onProcDraftChange,
  onViewProcJson,
  procJsonPreview,
  procTrialPreview,
}: SchemeWizardTargetProcStepProps) {
  const previewAnchorRef = useRef<HTMLDivElement | null>(null);
  const scrollToPreviewPendingRef = useRef(false);
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

  const handleTrialProc = () => {
    scrollToPreviewPendingRef.current = true;
    onTrialProc();
  };

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-5">
        <p className="text-sm font-semibold text-text-primary">先选择左右原始数据</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          第二步只负责数据准备。先选中左右侧原始数据，再生成和试跑当前的数据整理配置。
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <RemoteDatasetSelector
            side="left"
            title="左侧原始数据"
            description="按关键字远程搜索候选数据集，可多选并确认。"
            authToken={authToken}
            businessGoal={schemeDraft.businessGoal}
            sideDescription={schemeDraft.leftDescription}
            selectedSources={selectedLeftSources}
            onConfirmSelection={(sources) => onChangeSourceSelection('left', sources)}
          />
          <RemoteDatasetSelector
            side="right"
            title="右侧原始数据"
            description="按关键字远程搜索候选数据集，可多选并确认。"
            authToken={authToken}
            businessGoal={schemeDraft.businessGoal}
            sideDescription={schemeDraft.rightDescription}
            selectedSources={selectedRightSources}
            onConfirmSelection={(sources) => onChangeSourceSelection('right', sources)}
          />
        </div>

        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface px-4 py-3">
          <p className="text-xs font-medium text-text-secondary">筛选数据 / 行数据操作（后续支持）</p>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            当前版本先保留这块展示位。后续会在这里提供筛选条件、行处理和字段级操作的可视化配置。
          </p>
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-surface-secondary p-4">
        <p className="text-sm font-semibold text-text-primary">配置方式</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onProcConfigModeChange('ai')}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition',
              schemeDraft.procConfigMode === 'ai'
                ? 'border-sky-200 bg-sky-50 text-sky-700'
                : 'border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
            )}
          >
            AI生成配置
          </button>
          <button
            type="button"
            onClick={() => onProcConfigModeChange('existing')}
            className={cn(
              'rounded-xl border px-3 py-1.5 text-sm font-medium transition',
              schemeDraft.procConfigMode === 'existing'
                ? 'border-sky-200 bg-sky-50 text-sky-700'
                : 'border-border bg-surface text-text-secondary hover:border-sky-200 hover:text-sky-700',
            )}
          >
            选择已有配置
          </button>
        </div>

        {schemeDraft.procConfigMode === 'existing' ? (
          <label className="mt-4 block">
            <span className="text-xs font-medium text-text-secondary">已有数据整理配置</span>
            <select
              value={schemeDraft.selectedProcConfigId}
              onChange={(event) => onSelectExistingProcConfig(event.target.value)}
              className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
            >
              <option value="">请选择一条已有配置</option>
              {existingProcOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {showCompatibility ? (
          <div
            className={cn(
              'mt-4 rounded-2xl border px-4 py-3 text-sm',
              procCompatibility.status === 'passed'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : procCompatibility.status === 'warning'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : procCompatibility.status === 'failed'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : 'border-border bg-surface text-text-secondary',
            )}
          >
            <p>{procCompatibility.message}</p>
            {procCompatibility.details.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {procCompatibility.details.map((detail) => (
                  <span
                    key={detail}
                    className="rounded-full border border-current/15 bg-white/70 px-2.5 py-1 text-xs"
                  >
                    {detail}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {schemeDraft.procConfigMode === 'ai' ? (
        <div className="rounded-3xl border border-border bg-surface-secondary p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-sky-600" />
            <p className="text-sm font-semibold text-text-primary">数据整理</p>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <SourcesPreviewCard label="左侧数据" sources={selectedLeftSources} authToken={authToken} />
            <SourcesPreviewCard label="右侧数据" sources={selectedRightSources} authToken={authToken} />
          </div>
        </div>
      ) : null}

      {isTrialingProc ? (
        <div className="flex items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50/60 px-5 py-4">
          <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
          <span className="text-sm font-medium text-sky-700">AI 正在试跑数据整理，请稍候…</span>
        </div>
      ) : null}

      {schemeDraft.procConfigMode === 'ai' ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {isGeneratingProc ? (
              <div className="w-full rounded-2xl border border-sky-200 bg-sky-50/70 px-4 py-3 text-sky-700">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-sky-200 border-t-sky-600" />
                  AI 正在生成整理配置，请稍候…
                </div>
                <div className="mt-2 space-y-1 text-xs leading-6 text-sky-700/90">
                  <p>
                    当前生成器：
                    <span className="ml-1 rounded-full border border-sky-200 bg-white/70 px-2 py-0.5 font-semibold text-sky-700">
                      {generationSkill}
                    </span>
                  </p>
                  <p>当前阶段：{formatGenerationPhase(generationPhase)}</p>
                  <p>{generationMessage}</p>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={onGenerateProc}
                disabled={isTrialingProc}
                className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Sparkles className="h-4 w-4" />
                AI生成整理配置
              </button>
            )}
          </div>

          <label className="block">
            <span className="text-xs font-medium text-text-secondary">数据整理配置</span>
            <textarea
              value={schemeDraft.procDraft}
              onChange={(event) => onProcDraftChange(event.target.value)}
              rows={14}
              className="mt-1.5 w-full rounded-2xl border border-border bg-surface px-4 py-3 text-sm leading-7 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
              placeholder="如需改动说明，请修改后重新点击 AI 生成整理配置。"
            />
            <p className="mt-2 text-xs leading-5 text-text-muted">
              手动修改这里的说明后，需要重新点击“AI生成整理配置”。
              当前说明不为空时，系统会优先按这份说明生成 JSON；如果说明为空，则会重新生成新的整理说明和 JSON。
            </p>
          </label>
        </>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleTrialProc}
          disabled={
            isTrialingProc
            || isGeneratingProc
            || !procJsonPreview
          }
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <CheckCircle2 className="h-4 w-4" />
          试跑验证
        </button>
        <button
          type="button"
          onClick={onViewProcJson}
          disabled={
            isTrialingProc
            || isGeneratingProc
            || (
              !procJsonPreview
              || (
                !schemeDraft.procDraft.trim()
                && !(schemeDraft.procConfigMode === 'existing' && schemeDraft.selectedProcConfigId)
              )
            )
          }
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          JSON
        </button>
        {procJsonPreview ? <span className="text-xs text-text-secondary">已生成 JSON</span> : null}
      </div>

      <div ref={previewAnchorRef} className="scroll-mt-24">
        <ProcTrialPreviewPanel
          draftStatus={schemeDraft.procTrialStatus}
          draftSummary={schemeDraft.procTrialSummary}
          preview={procTrialPreview}
        />
      </div>
    </div>
  );
}
