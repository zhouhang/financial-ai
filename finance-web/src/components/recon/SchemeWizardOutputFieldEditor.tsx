import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, Plus, Sparkles, Trash2 } from 'lucide-react';
import {
  createOutputFieldDraft,
  inferOutputFieldSemanticRole,
  normalizeOutputFieldSemanticRole,
  resolveOutputFieldSemanticRoleLabel,
  type OutputFieldDraft,
  type OutputFieldSemanticRole,
  type SchemeSourceSelection,
} from './schemeWizardState';

interface FieldItem {
  rawName: string;
  displayName: string;
}

interface SchemeWizardOutputFieldEditorProps {
  authToken?: string | null;
  title: string;
  sources: SchemeSourceSelection[];
  fields: OutputFieldDraft[];
  onChange: (fields: OutputFieldDraft[]) => void;
  onRecommend?: () => void;
  recommendDisabled?: boolean;
}

const OUTPUT_FIELD_ROLE_OPTIONS: OutputFieldSemanticRole[] = [
  'normal',
  'match_key',
  'compare_field',
];

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function resolveDatasetDisplayName(source: SchemeSourceSelection): string {
  return source.businessName?.trim() || source.name;
}

function extractFieldItemsFromSchemaSummary(schemaSummary: Record<string, unknown> | undefined): FieldItem[] {
  const summary = asRecord(schemaSummary);
  const columns = Array.isArray(summary.columns) ? summary.columns : [];
  if (columns.length > 0) {
    return columns
      .map((item) => {
        const column = asRecord(item);
        const rawName = String(column.name || column.column_name || '').trim();
        if (!rawName) return null;
        return { rawName, displayName: rawName } satisfies FieldItem;
      })
      .filter(Boolean) as FieldItem[];
  }

  return Object.keys(summary)
    .filter((key) => key !== 'columns' && key.trim())
    .map((key) => ({ rawName: key, displayName: key }));
}

function buildFieldItems(source: SchemeSourceSelection): FieldItem[] {
  if (source.fieldLabelMap && Object.keys(source.fieldLabelMap).length > 0) {
    return Object.entries(source.fieldLabelMap).map(([rawName, displayName]) => ({
      rawName,
      displayName: displayName || rawName,
    }));
  }
  return extractFieldItemsFromSchemaSummary(source.schemaSummary);
}

function renderFieldOptionLabel(field: FieldItem): string {
  return field.displayName !== field.rawName
    ? `${field.displayName} (${field.rawName})`
    : field.rawName;
}

function normalizeVisibleOutputFieldRole(role: unknown): OutputFieldSemanticRole {
  const normalized = normalizeOutputFieldSemanticRole(role);
  return normalized === 'time_field' ? 'normal' : normalized;
}


export default function SchemeWizardOutputFieldEditor({
  authToken,
  title,
  sources,
  fields,
  onChange,
  onRecommend,
  recommendDisabled = false,
}: SchemeWizardOutputFieldEditorProps) {
  const [fieldCache, setFieldCache] = useState<Record<string, FieldItem[]>>({});
  const [loadingIds, setLoadingIds] = useState<string[]>([]);
  const primarySource = sources[0];
  const configuredFieldCount = fields.filter((field) => field.outputName.trim()).length;

  const loadDatasetFields = useCallback(
    async (source: SchemeSourceSelection) => {
      if (fieldCache[source.id]) return;

      const localFields = buildFieldItems(source);
      if (localFields.length > 0) {
        setFieldCache((prev) => ({ ...prev, [source.id]: localFields }));
        return;
      }
      if (!authToken || !source.sourceId) {
        setFieldCache((prev) => ({ ...prev, [source.id]: [] }));
        return;
      }

      setLoadingIds((prev) => (prev.includes(source.id) ? prev : [...prev, source.id]));
      try {
        const response = await fetch('/api/recon/schemes/design/dataset-fields', {
          method: 'POST',
          headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_id: source.sourceId,
            resource_key: source.resourceKey || source.datasetCode || '',
            dataset_id: source.id,
          }),
        });
        const data = await response.json().catch(() => ({}));
        const nextFields = response.ok && Array.isArray(data.fields)
          ? (data.fields as Array<Record<string, string>>)
            .map((item) => ({
              rawName: String(item.raw_name || '').trim(),
              displayName: String(item.display_name || item.raw_name || '').trim(),
            }))
            .filter((item) => item.rawName)
          : [];
        setFieldCache((prev) => ({ ...prev, [source.id]: nextFields }));
      } catch {
        setFieldCache((prev) => ({ ...prev, [source.id]: [] }));
      } finally {
        setLoadingIds((prev) => prev.filter((item) => item !== source.id));
      }
    },
    [authToken, fieldCache],
  );

  useEffect(() => {
    sources.forEach((source) => {
      if (!fieldCache[source.id]) {
        void loadDatasetFields(source);
      }
    });
  }, [fieldCache, loadDatasetFields, sources]);

  const selectedFieldOptions = useMemo(
    () => (primarySource ? fieldCache[primarySource.id] || [] : []),
    [fieldCache, primarySource],
  );

  const replaceField = useCallback(
    (fieldId: string, updater: (field: OutputFieldDraft) => OutputFieldDraft) => {
      onChange(fields.map((field) => (field.id === fieldId ? updater(field) : field)));
    },
    [fields, onChange],
  );

  const removeField = useCallback(
    (fieldId: string) => {
      onChange(fields.filter((field) => field.id !== fieldId));
    },
    [fields, onChange],
  );

  const moveField = useCallback(
    (fieldId: string, direction: 'up' | 'down') => {
      const index = fields.findIndex((field) => field.id === fieldId);
      if (index < 0) return;
      const targetIndex = direction === 'up' ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= fields.length) return;
      const next = [...fields];
      const [item] = next.splice(index, 1);
      next.splice(targetIndex, 0, item);
      onChange(next);
    },
    [fields, onChange],
  );

  const addField = useCallback(() => {
    onChange([
      ...fields,
      {
        ...createOutputFieldDraft(),
        valueMode: 'source_field',
        sourceDatasetId: primarySource?.id || '',
      },
    ]);
  }, [fields, onChange, primarySource]);

  useEffect(() => {
    if (!primarySource) return;
    const nextSourceId = primarySource.id;
    const normalizedFields = fields
      .filter((field) => field.valueMode === 'source_field')
      .map((field) => ({
        ...field,
        valueMode: 'source_field' as const,
        sourceDatasetId: nextSourceId,
        sourceField: field.sourceDatasetId === nextSourceId ? field.sourceField : '',
        fixedValue: '',
        formula: '',
        concatDelimiter: '',
        concatParts: [],
      }));
    const needsNormalization =
      normalizedFields.length !== fields.length
      || normalizedFields.some((field, index) => {
        const current = fields[index];
        return (
          !current
          || current.sourceDatasetId !== field.sourceDatasetId
          || current.sourceField !== field.sourceField
          || current.fixedValue !== ''
          || current.formula !== ''
          || current.concatDelimiter !== ''
          || current.concatParts.length > 0
        );
      });
    if (!needsNormalization) return;

    onChange(normalizedFields);
  }, [fields, onChange, primarySource]);

  const anyLoading = loadingIds.length > 0;

  return (
    <div className="rounded-3xl border border-border bg-surface-secondary p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">
            选完数据集后，系统会先推荐一版输出字段。你可以继续调整字段名、字段角色和来源字段。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary">
            已配 {configuredFieldCount} 个字段
          </span>
          <button
            type="button"
            onClick={onRecommend}
            disabled={sources.length === 0 || recommendDisabled}
            className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Sparkles className="h-4 w-4" />
            智能推荐
          </button>
          <button
            type="button"
            onClick={addField}
            disabled={sources.length === 0}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Plus className="h-4 w-4" />
            新增字段
          </button>
        </div>
      </div>

      {sources.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-sm text-text-secondary">
          先选择这一侧的原始数据集，再配置输出字段。
        </div>
      ) : fields.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface px-4 py-4">
          <p className="text-sm text-text-secondary">当前还没有输出字段，先试试智能推荐，再按需要微调。</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRecommend}
              disabled={recommendDisabled}
              className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Sparkles className="h-4 w-4" />
              先推荐一版
            </button>
            <button
              type="button"
              onClick={addField}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
            >
              <Plus className="h-4 w-4" />
              手动添加
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {fields.map((field, index) => (
            <div key={field.id} className="rounded-2xl border border-border bg-surface px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="rounded-full border border-border bg-surface-secondary px-2.5 py-1 text-xs font-medium text-text-secondary">
                  字段 {index + 1}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => moveField(field.id, 'up')}
                    disabled={index === 0}
                    className="rounded-lg border border-border p-1.5 text-text-secondary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveField(field.id, 'down')}
                    disabled={index === fields.length - 1}
                    className="rounded-lg border border-border p-1.5 text-text-secondary transition hover:border-sky-200 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ArrowDown className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeField(field.id)}
                    className="rounded-lg border border-rose-200 p-1.5 text-rose-600 transition hover:bg-rose-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="mt-4 grid gap-3 xl:grid-cols-3">
                <label className="block">
                  <span className="text-xs font-medium text-text-secondary">输出字段名</span>
                  <input
                    value={field.outputName}
                    onChange={(event) =>
                      replaceField(field.id, (current) => ({
                        ...current,
                        outputName: event.target.value,
                        semanticRole:
                          normalizeOutputFieldSemanticRole(current.semanticRole) === 'normal'
                            ? inferOutputFieldSemanticRole(event.target.value, current.sourceField)
                            : current.semanticRole,
                      }))
                    }
                    className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                    placeholder="例如：订单号、业务日期、金额"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-text-secondary">字段角色</span>
                  <div className="relative mt-1.5">
                    <select
                      value={normalizeVisibleOutputFieldRole(field.semanticRole)}
                      onChange={(event) =>
                        replaceField(field.id, (current) => ({
                          ...current,
                          semanticRole: normalizeVisibleOutputFieldRole(event.target.value),
                        }))
                      }
                      className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                    >
                      {OUTPUT_FIELD_ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {resolveOutputFieldSemanticRoleLabel(role)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown
                      className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
                      aria-hidden="true"
                    />
                  </div>
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-text-secondary">来源字段</span>
                  <div className="relative mt-1.5">
                    <select
                      value={field.sourceField}
                      onChange={(event) =>
                        replaceField(field.id, (current) => ({
                          ...current,
                          semanticRole:
                            normalizeOutputFieldSemanticRole(current.semanticRole) === 'normal'
                              ? inferOutputFieldSemanticRole(current.outputName, event.target.value)
                              : current.semanticRole,
                          valueMode: 'source_field',
                          sourceDatasetId: primarySource?.id || '',
                          sourceField: event.target.value,
                          fixedValue: '',
                          formula: '',
                          concatDelimiter: '',
                          concatParts: [],
                        }))
                      }
                      disabled={!primarySource}
                      className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-8 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <option value="">{primarySource ? '请选择字段' : '请先选择数据集'}</option>
                      {primarySource && selectedFieldOptions.length > 0
                        ? (
                          <optgroup label={resolveDatasetDisplayName(primarySource)}>
                            {selectedFieldOptions.map((option) => (
                              <option key={option.rawName} value={option.rawName}>
                                {renderFieldOptionLabel(option)}
                              </option>
                            ))}
                          </optgroup>
                        )
                        : null}
                    </select>
                    <ChevronDown
                      className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
                      aria-hidden="true"
                    />
                  </div>
                </label>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-muted">
        <span>先标注匹配字段、对比字段，再把输出结构试跑通过。对账日期字段会在运行计划中配置。</span>
        {anyLoading ? (
          <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-sky-700">
            正在加载字段元数据…
          </span>
        ) : null}
      </div>
    </div>
  );
}
