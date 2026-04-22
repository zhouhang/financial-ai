import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Link2, Plus, Trash2 } from 'lucide-react';
import {
  createOutputFieldConcatPart,
  createOutputFieldDraft,
  type OutputFieldDraft,
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
}

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

export default function SchemeWizardOutputFieldEditor({
  authToken,
  title,
  sources,
  fields,
  onChange,
}: SchemeWizardOutputFieldEditorProps) {
  const [fieldCache, setFieldCache] = useState<Record<string, FieldItem[]>>({});
  const [loadingIds, setLoadingIds] = useState<string[]>([]);

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

  const datasetOptions = useMemo(
    () => sources.map((source) => ({ value: source.id, label: resolveDatasetDisplayName(source) })),
    [sources],
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
        sourceDatasetId: sources[0]?.id || '',
      },
    ]);
  }, [fields, onChange, sources]);

  const anyLoading = loadingIds.length > 0;

  return (
    <div className="rounded-3xl border border-border bg-surface-secondary p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="mt-1 text-xs leading-5 text-text-secondary">
            定义这一侧最终输出表要保留哪些字段，以及每个字段如何取值。
          </p>
        </div>
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

      {sources.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface px-4 py-4 text-sm text-text-secondary">
          先选择这一侧的原始数据集，再配置输出字段。
        </div>
      ) : fields.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-border bg-surface px-4 py-4">
          <p className="text-sm text-text-secondary">当前还没有输出字段。</p>
          <button
            type="button"
            onClick={addField}
            className="mt-3 inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700 transition hover:bg-sky-100"
          >
            <Plus className="h-4 w-4" />
            添加第一个字段
          </button>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {fields.map((field, index) => {
            const selectedFieldOptions = field.sourceDatasetId ? fieldCache[field.sourceDatasetId] || [] : [];
            return (
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

                <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_220px]">
                  <label className="block">
                    <span className="text-xs font-medium text-text-secondary">输出字段名</span>
                    <input
                      value={field.outputName}
                      onChange={(event) =>
                        replaceField(field.id, (current) => ({ ...current, outputName: event.target.value }))
                      }
                      className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                      placeholder="例如：订单号、业务日期、金额"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-text-secondary">取值方式</span>
                    <select
                      value={field.valueMode}
                      onChange={(event) => {
                        const nextMode = event.target.value as OutputFieldDraft['valueMode'];
                        replaceField(field.id, (current) => ({
                          ...current,
                          valueMode: nextMode,
                          sourceDatasetId:
                            nextMode === 'source_field' && !current.sourceDatasetId
                              ? sources[0]?.id || ''
                              : current.sourceDatasetId,
                          sourceField: nextMode === 'source_field' ? current.sourceField : '',
                          concatParts:
                            nextMode === 'concat' && current.concatParts.length === 0
                              ? [{ ...createOutputFieldConcatPart(), datasetId: sources[0]?.id || '' }]
                              : nextMode === 'concat'
                              ? current.concatParts
                              : [],
                        }));
                      }}
                      className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                    >
                      <option value="source_field">源字段映射</option>
                      <option value="fixed_value">固定值</option>
                      <option value="formula">简单公式</option>
                      <option value="concat">多字段拼接</option>
                    </select>
                  </label>
                </div>

                {field.valueMode === 'source_field' ? (
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    <label className="block">
                      <span className="text-xs font-medium text-text-secondary">来源数据集</span>
                      <select
                        value={field.sourceDatasetId}
                        onChange={(event) =>
                          replaceField(field.id, (current) => ({
                            ...current,
                            sourceDatasetId: event.target.value,
                            sourceField: '',
                          }))
                        }
                        className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                      >
                        <option value="">请选择数据集</option>
                        {datasetOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      <span className="text-xs font-medium text-text-secondary">来源字段</span>
                      <select
                        value={field.sourceField}
                        onChange={(event) =>
                          replaceField(field.id, (current) => ({ ...current, sourceField: event.target.value }))
                        }
                        disabled={!field.sourceDatasetId}
                        className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <option value="">请选择字段</option>
                        {selectedFieldOptions.map((option) => (
                          <option key={option.rawName} value={option.rawName}>
                            {renderFieldOptionLabel(option)}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                ) : null}

                {field.valueMode === 'fixed_value' ? (
                  <label className="mt-4 block">
                    <span className="text-xs font-medium text-text-secondary">固定值</span>
                    <input
                      value={field.fixedValue}
                      onChange={(event) =>
                        replaceField(field.id, (current) => ({ ...current, fixedValue: event.target.value }))
                      }
                      className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                      placeholder="例如：支付宝、线上订单"
                    />
                  </label>
                ) : null}

                {field.valueMode === 'formula' ? (
                  <label className="mt-4 block">
                    <span className="text-xs font-medium text-text-secondary">公式表达式</span>
                    <input
                      value={field.formula}
                      onChange={(event) =>
                        replaceField(field.id, (current) => ({ ...current, formula: event.target.value }))
                      }
                      className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                      placeholder="例如：round(order_amount, 2)"
                    />
                    <p className="mt-2 text-xs leading-5 text-text-muted">
                      这里保留简单公式入口，后续会直接接入执行与试跑。
                    </p>
                  </label>
                ) : null}

                {field.valueMode === 'concat' ? (
                  <div className="mt-4 space-y-3">
                    <div className="grid gap-3 lg:grid-cols-[160px_minmax(0,1fr)]">
                      <label className="block">
                        <span className="text-xs font-medium text-text-secondary">连接符</span>
                        <input
                          value={field.concatDelimiter}
                          onChange={(event) =>
                            replaceField(field.id, (current) => ({
                              ...current,
                              concatDelimiter: event.target.value,
                            }))
                          }
                          className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                          placeholder="如：-"
                        />
                      </label>
                      <div className="rounded-xl border border-border bg-surface-secondary px-3 py-3 text-xs leading-5 text-text-secondary">
                        系统会按当前顺序拼接多个来源字段。
                      </div>
                    </div>

                    <div className="space-y-2">
                      {field.concatParts.map((part, partIndex) => {
                        const partFieldOptions = part.datasetId ? fieldCache[part.datasetId] || [] : [];
                        return (
                          <div
                            key={part.id}
                            className="grid gap-2 rounded-xl border border-border bg-surface px-3 py-3 lg:grid-cols-[130px_minmax(0,1fr)_40px]"
                          >
                            <label className="block">
                              <span className="text-xs font-medium text-text-secondary">数据集</span>
                              <select
                                value={part.datasetId}
                                onChange={(event) =>
                                  replaceField(field.id, (current) => ({
                                    ...current,
                                    concatParts: current.concatParts.map((item) =>
                                      item.id === part.id
                                        ? { ...item, datasetId: event.target.value, fieldName: '' }
                                        : item,
                                    ),
                                  }))
                                }
                                className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                              >
                                <option value="">请选择</option>
                                {datasetOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="block">
                              <span className="text-xs font-medium text-text-secondary">字段 {partIndex + 1}</span>
                              <select
                                value={part.fieldName}
                                onChange={(event) =>
                                  replaceField(field.id, (current) => ({
                                    ...current,
                                    concatParts: current.concatParts.map((item) =>
                                      item.id === part.id ? { ...item, fieldName: event.target.value } : item,
                                    ),
                                  }))
                                }
                                disabled={!part.datasetId}
                                className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                <option value="">请选择字段</option>
                                {partFieldOptions.map((option) => (
                                  <option key={option.rawName} value={option.rawName}>
                                    {renderFieldOptionLabel(option)}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <button
                              type="button"
                              onClick={() =>
                                replaceField(field.id, (current) => ({
                                  ...current,
                                  concatParts: current.concatParts.filter((item) => item.id !== part.id),
                                }))
                              }
                              className="mt-6 rounded-lg border border-rose-200 p-2 text-rose-600 transition hover:bg-rose-50"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        );
                      })}
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        replaceField(field.id, (current) => ({
                          ...current,
                          concatParts: [
                            ...current.concatParts,
                            { ...createOutputFieldConcatPart(), datasetId: sources[0]?.id || '' },
                          ],
                        }))
                      }
                      className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
                    >
                      <Link2 className="h-4 w-4" />
                      添加拼接字段
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-text-muted">
        <span>支持源字段映射、固定值、简单公式和多字段拼接。</span>
        {anyLoading ? (
          <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-sky-700">
            正在加载字段元数据…
          </span>
        ) : null}
      </div>
    </div>
  );
}
