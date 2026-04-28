import type { DataSourceKind } from '../../types';
import { extractCollectionDetailSampleRows } from './datasetPreview';
import {
  createOutputFieldDraft,
  inferOutputFieldSemanticRole,
  normalizeOutputFieldSemanticRole,
  type OutputFieldDraft,
} from './schemeWizardState';
import type {
  AiProcQuestionCandidate,
  AiProcQuestion,
  AiProcSide,
  AiProcSideDraft,
  RuleGenerationNodeTrace,
} from './SchemeWizardTargetProcStep';

type SupportedSourceKind = Extract<
  DataSourceKind,
  'platform_oauth' | 'database' | 'api' | 'file' | 'browser' | 'desktop_cli'
>;

type PreviewCellValue = string | number | null;

export interface PreviewTableRow {
  [key: string]: PreviewCellValue;
}

export interface RuleGenerationSourceOption {
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

export interface RuleGenerationEventDraftUpdate {
  draft: AiProcSideDraft;
  outputFields: OutputFieldDraft[];
}

const RULE_GENERATION_NODE_DEFS = [
  ['prepare_context', '准备上下文'],
  ['understand_rule', '理解业务规则'],
  ['validate_ir_structure', '校验 IR 结构'],
  ['resolve_source_bindings', '绑定源字段'],
  ['lint_ir', '校验规则 IR'],
  ['repair_ir', '修复规则 IR'],
  ['semantic_resolution', '自动消除歧义'],
  ['ambiguity_gate', '判断是否需要补充'],
  ['generate_proc_json', '生成规则'],
  ['check_ir_dsl_consistency', '检查规则一致性'],
  ['lint_proc_json', '校验规则可执行性'],
  ['build_sample_inputs', '读取真实样例数据'],
  ['run_sample', '样例执行'],
  ['diagnose_sample', '诊断样例结果'],
  ['assert_output', '校验输出结果'],
  ['result', '生成结果'],
] as const;

const RULE_GENERATION_SAMPLE_ROW_LIMIT = 20;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
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
  const record = asRecord(value);
  const entries = Object.entries(record)
    .map(([key, raw]) => [key.trim(), toText(raw).trim()] as const)
    .filter(([key, label]) => Boolean(key && label));
  if (entries.length === 0) {
    return undefined;
  }
  return Object.fromEntries(entries);
}

function mergeFieldLabelMaps(
  primary?: Record<string, string>,
  secondary?: Record<string, string>,
): Record<string, string> | undefined {
  const merged = { ...(secondary || {}), ...(primary || {}) };
  return Object.keys(merged).length > 0 ? merged : undefined;
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
  return text;
}

function resolveSchemaFieldType(schemaSummary: Record<string, unknown> | undefined, rawName: string): string {
  const summary = asRecord(schemaSummary);
  const columns = asList(summary.columns);
  for (const item of columns) {
    const column = asRecord(item);
    const columnName = toText(column.name, toText(column.column_name)).trim();
    if (columnName === rawName) {
      return normalizeSchemaType(column.data_type || column.type || column.schema_type);
    }
  }
  const fields = asList(summary.fields);
  for (const item of fields) {
    const field = asRecord(item);
    const fieldName = toText(field.raw_name, toText(field.name, toText(field.field_name))).trim();
    if (fieldName === rawName) {
      return normalizeSchemaType(field.data_type || field.type || field.schema_type);
    }
  }
  return normalizeSchemaType(summary[rawName]);
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
  const fields = asList(summary.fields);
  if (fields.length > 0) {
    return fields
      .map((item) => {
        if (typeof item === 'string') return item.trim();
        const field = asRecord(item);
        return toText(field.raw_name, toText(field.name, toText(field.field_name))).trim();
      })
      .filter(Boolean);
  }
  return Object.keys(summary).filter((key) => key !== 'columns');
}

function extractFieldLabelMapFromDataset(value: unknown): Record<string, string> | undefined {
  const dataset = asRecord(value);
  const metadata = asRecord(dataset.metadata);
  const semanticProfile = asRecord(metadata.semantic_profile);
  return mergeFieldLabelMaps(
    normalizeFieldLabelMap(dataset.field_label_map),
    normalizeFieldLabelMap(semanticProfile.field_label_map),
  );
}

function extractSchemaSummaryFromDataset(value: unknown): Record<string, unknown> | undefined {
  const dataset = asRecord(value);
  const schemaSummary = asRecord(dataset.schema_summary);
  if (Object.keys(schemaSummary).length > 0) return schemaSummary;
  const semanticFields = asList(dataset.semantic_fields);
  if (semanticFields.length > 0) return { fields: semanticFields };
  const metadata = asRecord(dataset.metadata);
  const semanticProfile = asRecord(metadata.semantic_profile);
  const profileFields = asList(semanticProfile.fields);
  if (profileFields.length > 0) return { fields: profileFields };
  return undefined;
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

function resolveSourceFieldLabelMap(
  source: RuleGenerationSourceOption | null | undefined,
): Record<string, string> | undefined {
  if (!source) return undefined;
  return normalizeFieldLabelMap(source.fieldLabelMap);
}

function collectSourceFieldCandidates(source: RuleGenerationSourceOption) {
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
      schemaType: resolveSchemaFieldType(source.schemaSummary, rawName),
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

export function resolveDatasetTableName(source: RuleGenerationSourceOption): string {
  return source.resourceKey || source.datasetCode || source.name;
}

export function toPreviewTableRows(value: unknown): PreviewTableRow[] {
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

export function createDefaultRuleGenerationNodeTraces(): RuleGenerationNodeTrace[] {
  return RULE_GENERATION_NODE_DEFS.map(([code, name]) => ({
    code,
    name,
    status: 'pending',
    message: '',
    attempt: 1,
  }));
}

export function createEmptyAiProcSideDraft(): AiProcSideDraft {
  return {
    ruleDraft: '',
    status: 'idle',
    summary: '',
    error: '',
    failureReasons: [],
    nodeTraces: createDefaultRuleGenerationNodeTraces(),
    questions: [],
    assumptions: [],
    validations: [],
    warnings: [],
    outputRows: [],
    outputFieldLabelMap: {},
    outputColumnHints: {},
  };
}

export function createEmptyAiProcSideDrafts(): Record<AiProcSide, AiProcSideDraft> {
  return {
    left: createEmptyAiProcSideDraft(),
    right: createEmptyAiProcSideDraft(),
  };
}

export function parseSseFrame(frame: string): Record<string, unknown> | null {
  const dataLines = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace(/^data:\s?/, ''));
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join('\n')) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function serializeSchemeSourceForRuleGeneration(
  source: RuleGenerationSourceOption,
  sampleRows: PreviewTableRow[] = [],
): Record<string, unknown> {
  return {
    source_id: source.sourceId,
    dataset_id: source.id,
    id: source.id,
    resource_key: source.resourceKey || source.datasetCode || source.technicalName || source.id,
    table_name: resolveDatasetTableName(source),
    dataset_name: source.name,
    business_name: source.businessName || source.name,
    source_kind: source.sourceKind,
    provider_code: source.providerCode,
    description: source.description || '',
    field_label_map: source.fieldLabelMap || {},
    fields: collectSourceFieldCandidates(source).map((field) => ({
      name: field.rawName,
      label: field.label || field.rawName,
      data_type: field.schemaType || 'string',
    })),
    sample_rows: sampleRows,
  };
}

export async function fetchRuleGenerationSampleRows(
  source: RuleGenerationSourceOption,
  authToken?: string | null,
): Promise<PreviewTableRow[]> {
  if (!authToken || !source.sourceId || !source.id) {
    return [];
  }
  try {
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
    if (!response.ok) return [];
    return toPreviewTableRows(extractCollectionDetailSampleRows(data, RULE_GENERATION_SAMPLE_ROW_LIMIT))
      .slice(0, RULE_GENERATION_SAMPLE_ROW_LIMIT);
  } catch {
    return [];
  }
}

async function fetchRuleGenerationSourceMetadata(
  source: RuleGenerationSourceOption,
  authToken?: string | null,
): Promise<{ sampleRows: PreviewTableRow[]; fieldLabelMap?: Record<string, string>; schemaSummary?: Record<string, unknown> }> {
  if (!authToken || !source.sourceId || !source.id) {
    return { sampleRows: [] };
  }
  try {
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
    if (!response.ok) return { sampleRows: [] };
    return {
      sampleRows: toPreviewTableRows(extractCollectionDetailSampleRows(data, RULE_GENERATION_SAMPLE_ROW_LIMIT))
        .slice(0, RULE_GENERATION_SAMPLE_ROW_LIMIT),
      fieldLabelMap: extractFieldLabelMapFromDataset(asRecord(data).dataset),
      schemaSummary: extractSchemaSummaryFromDataset(asRecord(data).dataset),
    };
  } catch {
    return { sampleRows: [] };
  }
}

export async function buildRuleGenerationSourcePayloads(
  sources: RuleGenerationSourceOption[],
  authToken?: string | null,
): Promise<Array<Record<string, unknown>>> {
  return Promise.all(
    sources.map(async (source) => {
      const metadata = await fetchRuleGenerationSourceMetadata(source, authToken);
      return serializeSchemeSourceForRuleGeneration(
        {
          ...source,
          fieldLabelMap: mergeFieldLabelMaps(source.fieldLabelMap, metadata.fieldLabelMap),
          schemaSummary: Object.keys(source.schemaSummary || {}).length > 0
            ? source.schemaSummary
            : metadata.schemaSummary || source.schemaSummary,
        },
        metadata.sampleRows,
      );
    }),
  );
}

export function normalizeAiOutputFields(value: unknown): OutputFieldDraft[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => {
      const name = String(item.name || item.label || '').trim();
      const draft = createOutputFieldDraft(name);
      const dataType = String(item.data_type || item.dataType || '').trim().toLowerCase();
      const sourceFields = normalizeStringList(item.source_fields || item.sourceFields);
      const inferredRole = /date|time|timestamp|datetime/.test(dataType)
        ? 'time_field'
        : inferOutputFieldSemanticRole(name);
      draft.semanticRole = normalizeOutputFieldSemanticRole(
        item.semantic_role ?? item.semanticRole ?? inferredRole,
      );
      draft.valueMode = item.is_derived === true ? 'formula' : 'source_field';
      draft.sourceField = sourceFields[0] || '';
      if (draft.valueMode === 'formula') {
        draft.formula = normalizeStringList(item.source_labels || item.sourceLabels).join(' + ');
      }
      return draft;
    })
    .filter((field) => field.outputName.trim());
}

function normalizeAiOutputFieldLabelMap(value: unknown): Record<string, string> {
  if (!Array.isArray(value)) return {};
  return Object.fromEntries(
    value
      .filter((item): item is Record<string, unknown> => isRecord(item))
      .map((item) => {
        const name = String(item.name || '').trim();
        const label = String(item.label || item.display_name || name).trim();
        return [name, label] as const;
      })
      .filter(([name]) => Boolean(name)),
  );
}

function normalizeAiOutputColumnHints(value: unknown): Record<string, {
  helper?: string;
  tone?: 'sky' | 'emerald' | 'amber' | 'violet';
}> {
  if (!Array.isArray(value)) return {};
  return Object.fromEntries(
    value
      .filter((item): item is Record<string, unknown> => isRecord(item))
      .map((item) => {
        const name = String(item.name || '').trim();
        const sourceLabels = normalizeStringList(item.source_labels || item.sourceLabels);
        if (!name || item.is_derived !== true || sourceLabels.length === 0) {
          return ['', {}] as const;
        }
        return [
          name,
          {
            helper: `源字段：${sourceLabels.join(' / ')}`,
            tone: 'violet' as const,
          },
        ] as const;
      })
      .filter(([name]) => Boolean(name)),
  );
}

export function normalizeAiOutputRows(value: unknown): PreviewTableRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((row) => {
      const normalized: PreviewTableRow = {};
      Object.entries(row).forEach(([key, cell]) => {
        normalized[key] = typeof cell === 'number' || typeof cell === 'string' || cell === null ? cell : String(cell ?? '');
      });
      return normalized;
    });
}

export function updateRuleGenerationTraces(
  traces: RuleGenerationNodeTrace[],
  payload: Record<string, unknown>,
): RuleGenerationNodeTrace[] {
  const node = isRecord(payload.node) ? payload.node : null;
  const code = String(node?.code || '').trim();
  if (!code) return traces;
  const nodeName = toText(node?.name).trim();
  const status = normalizeRuleNodeStatus(String(node?.status || 'running'));
  const attempt = Number(node?.attempt || 1);
  const next = traces.length > 0 ? traces : createDefaultRuleGenerationNodeTraces();
  return next.map((trace) => {
    if (trace.code !== code) return trace;
    return {
      ...trace,
      name: nodeName || trace.name,
      status,
      message: String(payload.message || trace.message || ''),
      attempt: Number.isFinite(attempt) ? attempt : trace.attempt,
      durationMs: typeof payload.duration_ms === 'number' ? payload.duration_ms : trace.durationMs,
      summary: isRecord(payload.summary) ? payload.summary : trace.summary,
      errors: Array.isArray(payload.errors) ? payload.errors.filter(isRecord) : trace.errors,
    };
  });
}

function normalizeRuleNodeStatus(status: string): RuleGenerationNodeTrace['status'] {
  if (status === 'completed') return 'completed';
  if (status === 'failed') return 'failed';
  if (status === 'skipped') return 'skipped';
  if (status === 'needs_user_input') return 'needs_user_input';
  return 'running';
}

function normalizeQuestionCandidate(value: unknown): AiProcQuestionCandidate | null {
  if (isRecord(value)) {
    const rawName = toText(value.raw_name, toText(value.name)).trim();
    const displayName = toText(value.display_name, toText(value.label, rawName)).trim();
    const sourceTable = toText(value.source_table, toText(value.table_name)).trim();
    if (!rawName && !displayName) return null;
    return {
      rawName,
      displayName: displayName || rawName,
      sourceTable,
    };
  }
  const text = toText(value).trim();
  return text ? text : null;
}

function normalizeQuestions(value: unknown): AiProcQuestion[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((item) => ({
    id: String(item.id || item.question || 'question'),
    question: String(item.question || ''),
    role: toText(item.role).trim() || undefined,
    mention: toText(item.mention).trim() || undefined,
    candidates: Array.isArray(item.candidates)
      ? item.candidates.map(normalizeQuestionCandidate).filter((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate))
      : undefined,
    evidence: Array.isArray(item.evidence) ? item.evidence.map(String) : undefined,
  }));
}

function normalizeFailureReasons(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const errorItems = value.filter(isRecord);
  const terminalItems = errorItems.filter((item) => {
    const stage = toText(item.stage, toText(item.node)).trim();
    return stage && stage !== 'run_sample';
  });
  const items = terminalItems.length > 0 ? terminalItems : errorItems;
  return items
    .filter(isRecord)
    .map((item) => {
      const stage = toText(item.stage, toText(item.node)).trim();
      const stepId = toText(item.step_id).trim();
      const message = toText(item.message, toText(item.error)).trim();
      const parts = [stage, stepId, message].filter(Boolean);
      return parts.join(' - ');
    })
    .filter(Boolean);
}

export function applyRuleGenerationEventToDraft(
  current: AiProcSideDraft,
  sideLabel: string,
  payload: Record<string, unknown>,
): RuleGenerationEventDraftUpdate {
  const eventName = String(payload.event || '');
  const nextDraft: AiProcSideDraft = {
    ...current,
    nodeTraces: updateRuleGenerationTraces(current.nodeTraces, payload),
  };
  let outputFields: OutputFieldDraft[] = [];

  if (eventName === 'needs_user_input') {
    nextDraft.status = 'needs_user_input';
    nextDraft.summary = '规则存在需要确认的字段或业务口径，请修改上方完整规则描述后重新生成。';
    nextDraft.questions = normalizeQuestions(payload.questions);
    nextDraft.failureReasons = [];
  }

  if (eventName === 'graph_completed') {
    const outputRows = normalizeAiOutputRows(payload.output_preview_rows);
    outputFields = normalizeAiOutputFields(payload.output_fields);
    const outputFieldLabelMap = normalizeAiOutputFieldLabelMap(payload.output_fields);
    const outputColumnHints = normalizeAiOutputColumnHints(payload.output_fields);
    nextDraft.status = 'succeeded';
    nextDraft.summary = `${sideLabel}输出数据已生成，已通过 rule_generation 校验。`;
    nextDraft.error = '';
    nextDraft.failureReasons = [];
    nextDraft.questions = [];
    nextDraft.outputRows = outputRows;
    nextDraft.outputFieldLabelMap = Object.keys(outputFieldLabelMap).length > 0
      ? outputFieldLabelMap
      : Object.fromEntries(outputFields.map((field) => [field.outputName, field.outputName]));
    nextDraft.outputColumnHints = outputColumnHints;
    nextDraft.procRuleJson = isRecord(payload.proc_rule_json) ? payload.proc_rule_json : undefined;
    nextDraft.procSteps = isRecord(payload.proc_rule_json) && Array.isArray(payload.proc_rule_json.steps)
      ? payload.proc_rule_json.steps.filter(isRecord)
      : [];
    nextDraft.assumptions = Array.isArray(payload.assumptions) ? payload.assumptions.filter(isRecord) : [];
    nextDraft.validations = Array.isArray(payload.validations) ? payload.validations.filter(isRecord) : [];
    nextDraft.warnings = Array.isArray(payload.warnings) ? payload.warnings.map(String) : [];
  }

  if (eventName === 'graph_failed') {
    const failureReasons = normalizeFailureReasons(payload.errors);
    nextDraft.status = 'failed';
    nextDraft.summary = `${sideLabel}AI生成失败。`;
    nextDraft.error = failureReasons[0] || String(payload.message || 'AI生成输出数据失败');
    nextDraft.failureReasons = failureReasons;
  }

  if (eventName === 'repair_started') {
    nextDraft.summary = String(payload.message || '正在根据校验结果修复规则。');
  } else if (eventName.startsWith('node_')) {
    nextDraft.summary = String(payload.message || nextDraft.summary || '正在执行 rule_generation。');
  }

  return { draft: nextDraft, outputFields };
}

export function buildAiSideProcRuleJson(options: {
  schemeName: string;
  businessGoal: string;
  leftRule?: Record<string, unknown>;
  rightRule?: Record<string, unknown>;
}): Record<string, unknown> {
  const leftSteps = normalizeAiProcStepsForSide(
    Array.isArray(options.leftRule?.steps) ? options.leftRule.steps : [],
    'left',
  );
  const rightSteps = normalizeAiProcStepsForSide(
    Array.isArray(options.rightRule?.steps) ? options.rightRule.steps : [],
    'right',
  );
  const leftConstraints = isRecord(options.leftRule?.dsl_constraints) ? options.leftRule.dsl_constraints : {};
  const rightConstraints = isRecord(options.rightRule?.dsl_constraints) ? options.rightRule.dsl_constraints : {};

  return {
    role_desc: options.businessGoal.trim() || `${options.schemeName.trim() || '未命名方案'}AI数据整理规则`,
    file_rule_code: '',
    version: '1.0',
    metadata: {
      generation_mode: 'ai_complex_rule',
    },
    global_config: isRecord(options.leftRule?.global_config) ? options.leftRule.global_config : options.rightRule?.global_config || {},
    dsl_constraints: mergeAiProcDslConstraints(leftConstraints, rightConstraints),
    steps: [
      ...leftSteps,
      ...rightSteps,
    ],
  };
}

function normalizeAiProcStepsForSide(steps: unknown[], side: AiProcSide): Record<string, unknown>[] {
  const prefix = `ai_${side}_`;
  const validSteps = steps.filter(isRecord);
  const firstStepIdByRawId = new Map<string, string>();
  const stepIdsByIndex: string[] = [];
  const usedStepIds = new Set<string>();
  validSteps.forEach((step, index) => {
    const rawStepId = String(step.step_id || '').trim();
    if (!rawStepId) return;
    const baseStepId = rawStepId.startsWith(prefix) ? rawStepId : `${prefix}${rawStepId}`;
    const nextStepId = buildUniqueStepId(baseStepId, usedStepIds, index + 1);
    stepIdsByIndex[index] = nextStepId;
    if (!firstStepIdByRawId.has(rawStepId)) {
      firstStepIdByRawId.set(rawStepId, nextStepId);
    }
  });
  return validSteps.map((step, index) => {
    const rawStepId = String(step.step_id || '').trim();
    const nextStepId = rawStepId ? stepIdsByIndex[index] || `${prefix}${rawStepId}` : '';
    const dependsOn = Array.isArray(step.depends_on)
      ? step.depends_on.map((item) => firstStepIdByRawId.get(String(item || '').trim()) || item)
      : step.depends_on;
    return {
      ...step,
      ...(nextStepId ? { step_id: nextStepId } : {}),
      ...(Array.isArray(dependsOn) ? { depends_on: dependsOn } : {}),
    };
  });
}

function buildUniqueStepId(baseStepId: string, usedStepIds: Set<string>, fallbackIndex: number): string {
  const normalizedBase = baseStepId.trim() || `step_${fallbackIndex}`;
  let candidate = normalizedBase;
  let suffix = 2;
  while (usedStepIds.has(candidate)) {
    candidate = `${normalizedBase}_${suffix}`;
    suffix += 1;
  }
  usedStepIds.add(candidate);
  return candidate;
}

function mergeAiProcDslConstraints(
  leftConstraints: Record<string, unknown>,
  rightConstraints: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...leftConstraints, ...rightConstraints };
  new Set([...Object.keys(leftConstraints), ...Object.keys(rightConstraints)]).forEach((key) => {
    const leftValue = leftConstraints[key];
    const rightValue = rightConstraints[key];
    if (Array.isArray(leftValue) || Array.isArray(rightValue)) {
      merged[key] = Array.from(new Set([...(Array.isArray(leftValue) ? leftValue : []), ...(Array.isArray(rightValue) ? rightValue : [])]));
    }
  });
  return merged;
}
