import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  Ban,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Database,
  ExternalLink,
  FileSpreadsheet,
  Globe,
  Link2,
  Loader2,
  MessageSquare,
  MonitorSmartphone,
  Plus,
  RefreshCw,
  ShieldCheck,
  Store,
  Trash2,
} from 'lucide-react';
import {
  COLLABORATION_CHANNEL_CARDS,
  collaborationProviderLabel,
} from '../collaborationChannelConfig';
import {
  loadCollaborationChannelDrafts,
  normalizeChannelConfig,
  saveCollaborationChannelDrafts,
} from '../collaborationChannelDrafts';
import { SOURCE_TYPE_CARDS, sourceKindLabel } from '../dataSourceConfig';
import type {
  AuthCallbackPayload,
  CollaborationChannelListItem,
  CollaborationProvider,
  DataConnectionView,
  DataSourceApiConfig,
  DataSourceDatabaseConfig,
  DataSourceDatasetSummary,
  DataSourceExecutionMode,
  DataSourceEventSummary,
  DataSourceKind,
  DataSourceListItem,
  PlatformConnectionSummary,
  PlatformCode,
  ShopConnection,
} from '../types';

type DataConnectionsMode = 'overview' | 'platform' | 'callback';

interface DataConnectionsPanelProps {
  authToken?: string | null;
  initialCallback?: AuthCallbackPayload | null;
  onBackToChat?: () => void;
  selectedConnectionView: DataConnectionView;
  selectedSourceKind: DataSourceKind;
  selectedCollaborationProvider: CollaborationProvider;
}

interface AuthSessionResponse {
  success?: boolean;
  auth_url?: string;
  message?: string;
}

interface DraftDataSource {
  id: string;
  source_kind: Extract<DataSourceKind, 'database' | 'api' | 'file'>;
  name: string;
  provider_code: string;
  execution_mode: DataSourceExecutionMode;
  status: string;
  updated_at: string;
}

interface EditableChannelConfig {
  id: string;
  provider: CollaborationProvider;
  channel_code: string;
  name: string;
  client_id: string;
  client_secret: string;
  robot_code: string;
  is_default: boolean;
  is_enabled: boolean;
  extraText: string;
  isDraft: boolean;
}

interface EditableSourceConfig {
  id: string;
  source_kind: Extract<DataSourceKind, 'database' | 'api' | 'file'>;
  name: string;
  description: string;
  database: {
    db_type: string;
    host: string;
    port: string;
    database: string;
    username: string;
    password: string;
  };
  api: {
    auth_mode: string;
    auth_request_url: string;
    auth_request_method: string;
    auth_request_payload_type: string;
    auth_request_headers: EditableKeyValueRow[];
    auth_request_params: EditableKeyValueRow[];
    auth_request_json_text: string;
    auth_apply_header_name: string;
    auth_apply_value_template: string;
  };
}

interface EditableKeyValueRow {
  id: string;
  key: string;
  value: string;
}

interface SourceDetailState {
  datasets: DataSourceDatasetSummary[];
  events: DataSourceEventSummary[];
  datasetsLoading: boolean;
  eventsLoading: boolean;
  datasetsError: string;
  eventsError: string;
  datasetsApiAvailable: boolean | null;
  eventsApiAvailable: boolean | null;
}

type DatasetViewTab = 'available' | 'physical';

interface DatasetListPageState {
  rows: DataSourceDatasetSummary[];
  loading: boolean;
  error: string;
  apiAvailable: boolean | null;
  total: number;
  page: number;
  pageSize: number;
}

interface DatasetDetailState {
  datasetId: string | null;
  dataset: DataSourceDatasetSummary | null;
  loading: boolean;
  error: string;
}

interface PhysicalCatalogFilterState {
  keyword: string;
  schema: string;
  objectType: string;
  publishStatus: string;
  verifiedStatus: string;
  page: number;
  pageSize: number;
}

interface ApiDiscoveryFormState {
  discoveryMode: 'document' | 'manual';
  documentInputMode: 'url' | 'content';
  documentUrl: string;
  documentContent: string;
  manualDatasetName: string;
  manualApiPath: string;
  manualMethod: 'GET' | 'POST';
  manualParamType: 'params' | 'json';
  manualParams: EditableKeyValueRow[];
  manualJsonText: string;
}

interface DatasetSemanticInfo {
  businessName?: string;
  keyFields: string[];
  keyFieldsExplicit: boolean;
  fieldLabelMap: Record<string, string>;
}

interface DiscoverSourceOptions {
  limit?: number;
  offset?: number;
  targetResourceKeys?: string[];
}

interface TargetedDiscoverDialogState {
  sourceId: string;
  resourceKeysText: string;
}

interface PhysicalCatalogDetailDialogState {
  sourceId: string;
  datasetId: string;
}

interface EditableDatasetSemantic {
  sourceId: string;
  sourceName: string;
  datasetId: string;
  datasetCode: string;
  datasetName: string;
  resourceKey: string;
  schemaName: string;
  objectName: string;
  objectType: string;
  businessName: string;
  // Reserved for future governance routing. Kept in payload, hidden in current publish UI.
  businessObjectType: string;
  // Reserved for future grain-aware matching. Kept in payload, hidden in current publish UI.
  grain: string;
  verifiedStatus: string;
  publishStatus: string;
  uniqueIdentifierRawNames: string[];
  collectionDateField: string;
  collectionScheduleFrequency: string;
  collectionScheduleTime: string;
  fieldRows: EditableDatasetSemanticFieldRow[];
}

interface DatasetCollectionDetailDialogState {
  sourceId: string;
  sourceName: string;
  datasetId: string;
  datasetName: string;
  resourceKey: string;
  loading: boolean;
  error: string;
  actionError: string;
  lastLoadedAt: string;
  detail: Record<string, unknown> | null;
}

interface EditableDatasetSemanticFieldRow {
  id: string;
  rawName: string;
  displayName: string;
  semanticType: string;
  businessRole: string;
  description: string;
  confidence: number | null;
  confirmedByUser: boolean;
  pending: boolean;
  sampleValues: string[];
}

const PLATFORM_FIXED_DATASET_FALLBACK = ['订单', '支付单', '退款单', '结算单'];

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function asStringOrNull(value: unknown): string | null | undefined {
  if (value === null) return null;
  return typeof value === 'string' ? value : undefined;
}

function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value;
  return undefined;
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return undefined;
}

function asNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const entries = Object.entries(value as Record<string, unknown>).filter(
    ([, item]) => typeof item === 'number' && Number.isFinite(item),
  );
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries) as Record<string, number>;
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter((item): item is string => typeof item === 'string');
}

function asStringRecord(value: unknown): Record<string, string> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const entries = Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => [key, typeof item === 'string' ? item.trim() : ''] as const)
    .filter(([key, item]) => key.trim().length > 0 && item.length > 0);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries);
}

function buildSampleTableColumns(rows: Record<string, unknown>[], maxColumns = 12): string[] {
  const columns: string[] = [];
  const seen = new Set<string>();
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (seen.has(key) || columns.length >= maxColumns) return;
      seen.add(key);
      columns.push(key);
    });
  });
  return columns;
}

function formatSampleCellValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'string') return value.trim() || '-';
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function normalizeDiscoverSummary(raw: unknown): DataSourceListItem['discover_summary'] | undefined {
  const value = asRecord(raw);
  if (!value) return undefined;
  const summary = {
    discovered_count: asNumber(value.discovered_count),
    enabled_count: asNumber(value.enabled_count),
    last_discover_at: asStringOrNull(value.last_discover_at),
    last_discover_status: asString(value.last_discover_status),
    last_discover_error: asStringOrNull(value.last_discover_error),
    scan_mode: asString(value.scan_mode),
    scanned_count: asNumber(value.scanned_count),
    total_count: asNumber(value.total_count),
    offset: asNumber(value.offset),
    requested_limit: asNumber(value.requested_limit),
    has_more: asBoolean(value.has_more),
    next_offset: asNumber(value.next_offset) ?? null,
    requested_count: asNumber(value.requested_count),
    matched_count: asNumber(value.matched_count),
    missing_targets: asStringArray(value.missing_targets),
  };
  const hasContent = Object.values(summary).some((item) => (Array.isArray(item) ? item.length > 0 : item !== undefined && item !== null && item !== ''));
  return hasContent ? summary : undefined;
}

function parseTargetResourceKeys(text: string): string[] {
  const seen = new Set<string>();
  const rows = text
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
  return rows.filter((item) => {
    const lowered = item.toLowerCase();
    if (seen.has(lowered)) return false;
    seen.add(lowered);
    return true;
  });
}

function extractDatasetSchemaFields(dataset: DataSourceDatasetSummary): string[] {
  const schema = asRecord(dataset.schema_summary);
  if (!schema) return [];
  const columns = Array.isArray(schema.columns) ? schema.columns : [];
  const names: string[] = [];

  columns.forEach((column) => {
    if (typeof column === 'string') {
      const trimmed = column.trim();
      if (trimmed) names.push(trimmed);
      return;
    }
    const item = asRecord(column);
    const name =
      asString(item?.name) ??
      asString(item?.column_name) ??
      asString(item?.field) ??
      asString(item?.key) ??
      '';
    if (name.trim()) names.push(name.trim());
  });

  return Array.from(new Set(names));
}

function extractDatasetSchemaColumns(
  dataset: DataSourceDatasetSummary,
): Array<{ name: string; dataType: string; nullable: boolean | null }> {
  const schema = asRecord(dataset.schema_summary);
  if (!schema) return [];
  const columns = Array.isArray(schema.columns) ? schema.columns : [];
  const normalized: Array<{ name: string; dataType: string; nullable: boolean | null }> = [];

  columns.forEach((column) => {
    if (typeof column === 'string') {
      const trimmed = column.trim();
      if (!trimmed) return;
      normalized.push({
        name: trimmed,
        dataType: 'unknown',
        nullable: null,
      });
      return;
    }
    const item = asRecord(column);
    if (!item) return;
    const name =
      asString(item.name) ??
      asString(item.column_name) ??
      asString(item.field) ??
      asString(item.key) ??
      '';
    const dataType = asString(item.data_type) ?? asString(item.type) ?? 'unknown';
    const nullable = typeof item.nullable === 'boolean' ? item.nullable : null;
    if (!name.trim()) return;
    normalized.push({
      name: name.trim(),
      dataType: dataType.trim() || 'unknown',
      nullable,
    });
  });

  return normalized;
}

function readDatasetSemanticInfo(dataset: DataSourceDatasetSummary): DatasetSemanticInfo {
  const datasetRecord = asRecord(dataset as unknown) ?? {};
  const metaRecord = asRecord(dataset.meta) ?? {};
  const semanticRecord =
    asRecord(datasetRecord.semantic_profile) ??
    asRecord(metaRecord.semantic_profile) ??
    asRecord(metaRecord.semantic) ??
    {};

  let fieldLabelMap =
    asStringRecord(datasetRecord.field_label_map) ??
    asStringRecord(semanticRecord.field_label_map) ??
    asStringRecord(metaRecord.field_label_map) ??
    {};

  if (Object.keys(fieldLabelMap).length === 0) {
    const semanticFields = Array.isArray(semanticRecord.fields) ? semanticRecord.fields : [];
    const fallbackEntries = semanticFields
      .map((item) => asRecord(item))
      .map((item) => {
        const rawName = asString(item?.raw_name) ?? asString(item?.field_name) ?? asString(item?.name) ?? '';
        const displayName =
          asString(item?.display_name) ??
          asString(item?.display_name_zh) ??
          asString(item?.label) ??
          '';
        return [rawName.trim(), displayName.trim()] as const;
      })
      .filter(([rawName, displayName]) => rawName.length > 0 && displayName.length > 0);
    if (fallbackEntries.length > 0) {
      fieldLabelMap = Object.fromEntries(fallbackEntries);
    }
  }

  const businessName =
    asString(datasetRecord.business_name) ??
    asString(semanticRecord.business_name) ??
    asString(metaRecord.business_name) ??
    undefined;

  const explicitKeyFields =
    asStringArray(datasetRecord.key_fields) ??
    asStringArray(semanticRecord.key_fields) ??
    asStringArray(metaRecord.key_fields);
  const keyFields = explicitKeyFields ?? [];

  return {
    businessName: businessName?.trim() || undefined,
    keyFields: keyFields.map((item) => item.trim()).filter(Boolean),
    keyFieldsExplicit: explicitKeyFields !== undefined,
    fieldLabelMap,
  };
}

function hasDatasetSemanticCache(dataset: DataSourceDatasetSummary): boolean {
  const semanticRecord = readDatasetSemanticRecord(dataset);
  const semanticStatus = (dataset.semantic_status ?? asString(semanticRecord.status) ?? '').trim().toLowerCase();
  if (semanticStatus && semanticStatus !== 'missing') return true;
  if ((dataset.semantic_updated_at ?? asString(semanticRecord.updated_at) ?? '').trim()) return true;

  const semanticFields = Array.isArray(dataset.semantic_fields)
    ? dataset.semantic_fields
    : Array.isArray(semanticRecord.fields)
      ? semanticRecord.fields
      : [];
  if (semanticFields.length > 0) return true;

  const fieldLabelMap =
    asStringRecord(dataset.field_label_map) ??
    asStringRecord(semanticRecord.field_label_map) ??
    {};
  if (Object.keys(fieldLabelMap).length > 0) return true;

  const semanticKeyFields =
    asStringArray(semanticRecord.key_fields) ??
    asStringArray(asRecord(dataset.meta)?.key_fields) ??
    [];
  if (semanticKeyFields.length > 0) return true;

  return Boolean(asString(semanticRecord.business_name)?.trim());
}

function readDatasetSemanticRecord(dataset: DataSourceDatasetSummary): Record<string, unknown> {
  const datasetRecord = asRecord(dataset as unknown) ?? {};
  const metaRecord = asRecord(dataset.meta) ?? {};
  return (
    asRecord(datasetRecord.semantic_profile) ??
    asRecord(metaRecord.semantic_profile) ??
    asRecord(metaRecord.semantic) ??
    {}
  );
}

function readDatasetPublishStatus(dataset: DataSourceDatasetSummary): string {
  const semanticRecord = readDatasetSemanticRecord(dataset);
  const normalized = (
    asString(dataset.publish_status) ??
    asString(semanticRecord.publish_status) ??
    'unpublished'
  )
    .trim()
    .toLowerCase();
  if (
    normalized === 'published' ||
    normalized === 'unpublished' ||
    normalized === 'draft' ||
    normalized === 'archived' ||
    normalized === 'deprecated'
  ) {
    return normalized;
  }
  return 'unpublished';
}

function readDatasetVerifiedStatus(dataset: DataSourceDatasetSummary): string {
  const semanticRecord = readDatasetSemanticRecord(dataset);
  const normalized = (
    asString(dataset.verified_status) ??
    asString(semanticRecord.verified_status) ??
    'unverified'
  )
    .trim()
    .toLowerCase();
  if (normalized === 'verified' || normalized === 'unverified' || normalized === 'rejected') {
    return normalized;
  }
  return 'unverified';
}

function readDatasetBusinessObjectType(dataset: DataSourceDatasetSummary): string {
  const semanticRecord = readDatasetSemanticRecord(dataset);
  return (
    asString(dataset.business_object_type) ??
    asString(semanticRecord.business_object_type) ??
    asString(semanticRecord.business_type) ??
    ''
  )
    .trim();
}

function readDatasetGrain(dataset: DataSourceDatasetSummary): string {
  const semanticRecord = readDatasetSemanticRecord(dataset);
  return (asString(dataset.grain) ?? asString(semanticRecord.grain) ?? '').trim();
}

function readDatasetLastUsedAt(dataset: DataSourceDatasetSummary): string | null {
  const semanticRecord = readDatasetSemanticRecord(dataset);
  return (
    asStringOrNull(dataset.last_used_at) ??
    asStringOrNull(semanticRecord.last_used_at) ??
    asStringOrNull(semanticRecord.last_used_time) ??
    null
  );
}

function readDatasetPendingFieldCount(dataset: DataSourceDatasetSummary): number {
  if (!hasDatasetSemanticCache(dataset)) {
    return Math.max(1, extractDatasetSchemaFields(dataset).length);
  }
  const explicitCount = asNumber((dataset as unknown as Record<string, unknown>).semantic_pending_count);
  if (typeof explicitCount === 'number') return explicitCount;
  const semanticFields = Array.isArray(dataset.semantic_fields) ? dataset.semantic_fields : [];
  const pendingSet = new Set((dataset.low_confidence_fields ?? []).map((item) => item.trim()).filter(Boolean));
  semanticFields.forEach((field) => {
    const value = asRecord(field);
    const rawName = asString(value?.raw_name) ?? asString(value?.name) ?? '';
    if (!rawName.trim()) return;
    const confidence = asNumber(value?.confidence);
    const confirmedByUser = asBoolean(value?.confirmed_by_user) ?? false;
    if (!confirmedByUser && typeof confidence === 'number' && confidence < 0.75) {
      pendingSet.add(rawName.trim());
    }
  });
  return pendingSet.size;
}

function parseSchemaAndObjectName(dataset: DataSourceDatasetSummary): { schemaName: string; objectName: string } {
  const schemaName = (dataset.schema_name || '').trim();
  const objectName = (dataset.object_name || '').trim();
  if (schemaName || objectName) {
    return {
      schemaName: schemaName || '-',
      objectName: objectName || dataset.dataset_name || dataset.dataset_code || '-',
    };
  }
  const resource = (dataset.resource_key || dataset.dataset_name || dataset.dataset_code || '').trim();
  if (!resource) {
    return { schemaName: '-', objectName: '-' };
  }
  const parts = resource.split('.');
  if (parts.length >= 2) {
    return {
      schemaName: parts[0] || '-',
      objectName: parts.slice(1).join('.') || '-',
    };
  }
  return {
    schemaName: '-',
    objectName: resource,
  };
}

function readDatasetObjectType(dataset: DataSourceDatasetSummary): string {
  return (dataset.object_type || dataset.dataset_kind || 'table').toString().trim().toLowerCase() || 'table';
}

function isDatasetEnabled(dataset: DataSourceDatasetSummary): boolean {
  return dataset.is_enabled !== false;
}

function isDatasetAvailable(dataset: DataSourceDatasetSummary): boolean {
  const normalizedStatus = (dataset.status || '').toLowerCase().trim();
  const isDirectoryActive =
    !normalizedStatus ||
    normalizedStatus === 'active' ||
    ['healthy', 'warning', 'error', 'auth_expired', 'unknown'].includes(normalizedStatus);
  return readDatasetPublishStatus(dataset) === 'published' && isDatasetEnabled(dataset) && isDirectoryActive;
}

function buildDatasetTechSubtitle(source: DataSourceListItem, dataset: DataSourceDatasetSummary): string {
  const provider = source.provider_code || sourceKindLabel(source.source_kind);
  const sourceName = source.name || source.id;
  const techDataset = dataset.resource_key || dataset.dataset_name || dataset.dataset_code;
  return `${provider} / ${sourceName} / ${techDataset}`;
}

const DATASET_FIELD_TOKEN_LABELS: Record<string, string> = {
  account: '账户',
  actual: '实付',
  alipay: '支付宝',
  api: '接口',
  bank: '银行',
  base: '基础',
  batch: '批次',
  biz: '业务',
  buyer: '买家',
  cash: '现金',
  channel: '渠道',
  code: '编码',
  company: '公司',
  coupon: '优惠券',
  create: '创建',
  created: '创建',
  crm: 'CRM',
  customer: '客户',
  date: '日期',
  discount: '优惠',
  fee: '费用',
  goods: '商品',
  id: 'ID',
  invoice: '发票',
  item: '明细',
  jd: '京东',
  merchant: '商户',
  money: '金额',
  name: '名称',
  no: '编号',
  number: '编号',
  open: '开放',
  openid: 'OpenID',
  order: '订单',
  paid: '已付',
  pay: '支付',
  payment: '支付',
  pdd: '拼多多',
  platform: '平台',
  price: '价格',
  product: '商品',
  qty: '数量',
  quantity: '数量',
  receivable: '应收',
  record: '记录',
  refund: '退款',
  seller: '卖家',
  settle: '结算',
  settlement: '结算',
  shop: '店铺',
  sku: 'SKU',
  source: '来源',
  status: '状态',
  submit: '提交',
  success: '成功',
  target: '目标',
  tax: '税费',
  time: '时间',
  total: '总',
  trade: '交易',
  transaction: '交易',
  txn: '交易',
  type: '类型',
  uid: '用户ID',
  unionid: 'UnionID',
  update: '更新',
  updated: '更新',
  user: '用户',
  wechat: '微信',
  weixin: '微信',
  wx: '微信',
};

const DATASET_FIELD_SUFFIX_LABELS: Record<string, string> = {
  amount: '金额',
  amout: '金额',
  amt: '金额',
  code: '编码',
  count: '数量',
  date: '日期',
  fee: '费用',
  id: 'ID',
  money: '金额',
  name: '名称',
  no: '编号',
  num: '数量',
  number: '编号',
  order: '订单号',
  price: '价格',
  qty: '数量',
  quantity: '数量',
  sn: '序号',
  status: '状态',
  time: '时间',
  type: '类型',
};

const DATASET_FIELD_COMPOUND_SUFFIX_LABELS: Record<string, string> = {
  created_at: '创建时间',
  order_code: '订单编码',
  order_id: '订单ID',
  order_no: '订单号',
  paid_at: '支付时间',
  pay_time: '支付时间',
  refund_at: '退款时间',
  trade_code: '交易编码',
  trade_id: '交易ID',
  trade_no: '交易号',
  updated_at: '更新时间',
};

const GENERIC_DATASET_FIELD_DISPLAY_NAMES = new Set([
  'ID',
  'id',
  '编码',
  '代码',
  '名称',
  '字段',
  '标识',
  '编号',
  '订单号',
  '金额',
  '价格',
  '费用',
  '数量',
  '状态',
  '时间',
  '日期',
  '类型',
]);

function splitDatasetFieldTokens(rawName: string): string[] {
  return rawName
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((token) => token.trim())
    .filter(Boolean);
}

function combineDatasetFieldLabel(prefixLabel: string, suffixLabel: string): string {
  if (!prefixLabel) return suffixLabel;
  if (suffixLabel === '订单号') {
    return prefixLabel.endsWith('订单') ? `${prefixLabel}号` : `${prefixLabel}${suffixLabel}`;
  }
  if (suffixLabel === '订单ID' || suffixLabel === '订单编码') {
    return prefixLabel.endsWith('订单') ? `${prefixLabel}${suffixLabel.slice(2)}` : `${prefixLabel}${suffixLabel}`;
  }
  if (suffixLabel.startsWith(prefixLabel)) return suffixLabel;
  return `${prefixLabel}${suffixLabel}`;
}

function translateDatasetFieldTokens(tokens: string[]): string {
  return tokens
    .map((token) => DATASET_FIELD_TOKEN_LABELS[token] ?? token.toUpperCase())
    .join('');
}

function inferDatasetFieldDisplayName(rawName: string): string {
  const tokens = splitDatasetFieldTokens(rawName);
  if (tokens.length === 0) return rawName;

  if (tokens.length >= 2) {
    const compoundSuffix = `${tokens[tokens.length - 2]}_${tokens[tokens.length - 1]}`;
    const compoundLabel = DATASET_FIELD_COMPOUND_SUFFIX_LABELS[compoundSuffix];
    if (compoundLabel) {
      return combineDatasetFieldLabel(translateDatasetFieldTokens(tokens.slice(0, -2)), compoundLabel);
    }
  }

  const suffixToken = tokens[tokens.length - 1];
  const suffixLabel = DATASET_FIELD_SUFFIX_LABELS[suffixToken];
  if (suffixLabel) {
    return combineDatasetFieldLabel(translateDatasetFieldTokens(tokens.slice(0, -1)), suffixLabel);
  }

  return translateDatasetFieldTokens(tokens) || rawName;
}

function isWeakDatasetFieldDisplayName(rawName: string, displayName: string): boolean {
  const normalizedDisplayName = displayName.trim();
  if (!normalizedDisplayName) return true;
  if (normalizedDisplayName === rawName.trim()) return true;
  if (normalizedDisplayName.includes('*')) return true;
  if (/^[a-z0-9_.\-\s]+$/i.test(normalizedDisplayName)) return true;
  const compactDisplayName = normalizedDisplayName.replace(/\s+/g, '');
  if (GENERIC_DATASET_FIELD_DISPLAY_NAMES.has(compactDisplayName)) {
    return splitDatasetFieldTokens(rawName).length > 1;
  }
  return false;
}

function resolveDatasetFieldDisplayName(
  rawName: string,
  semanticDisplayName: string,
  confirmedByUser: boolean,
): string {
  const inferredDisplayName = inferDatasetFieldDisplayName(rawName);
  if (!semanticDisplayName.trim()) return inferredDisplayName || rawName;
  if (isWeakDatasetFieldDisplayName(rawName, semanticDisplayName)) {
    return inferredDisplayName || semanticDisplayName.trim();
  }
  if (!confirmedByUser && /^[a-z0-9_.\-\s]+$/i.test(semanticDisplayName.trim())) {
    return inferredDisplayName || semanticDisplayName.trim();
  }
  return semanticDisplayName.trim();
}

function inferDatasetFieldBusinessRole(rawName: string): string {
  const tokens = splitDatasetFieldTokens(rawName);
  if (tokens.length === 0) return '';
  if (tokens.length >= 2) {
    const compoundSuffix = `${tokens[tokens.length - 2]}_${tokens[tokens.length - 1]}`;
    if (['order_id', 'order_code', 'order_no', 'trade_id', 'trade_code', 'trade_no'].includes(compoundSuffix)) {
      return 'identifier';
    }
    if (['created_at', 'updated_at', 'paid_at', 'pay_time', 'refund_at'].includes(compoundSuffix)) {
      return 'time';
    }
  }
  const suffixToken = tokens[tokens.length - 1];
  if (['id', 'code', 'order', 'no', 'number', 'sn'].includes(suffixToken)) return 'identifier';
  if (['amount', 'amout', 'amt', 'money', 'price', 'fee'].includes(suffixToken)) return 'amount';
  if (['date', 'time'].includes(suffixToken)) return 'time';
  if (suffixToken === 'status') return 'status';
  if (suffixToken === 'type') return 'type';
  if (suffixToken === 'name') return 'name';
  return '';
}

function inferDatasetFieldSemanticType(rawName: string): string {
  const businessRole = inferDatasetFieldBusinessRole(rawName);
  if (businessRole === 'identifier') return 'identifier';
  if (businessRole === 'amount') return 'amount';
  if (businessRole === 'time') return 'datetime';
  if (businessRole === 'status') return 'enum';
  if (businessRole === 'type') return 'enum';
  if (businessRole === 'name') return 'text';
  return '';
}

function datasetFieldBusinessRoleLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === 'unknown') return '';
  if (normalized === 'identifier') return '唯一标识';
  if (normalized === 'amount') return '金额';
  if (normalized === 'time') return '时间';
  if (normalized === 'status') return '状态';
  if (normalized === 'type') return '类型';
  if (normalized === 'name') return '名称';
  if (normalized === 'order_id' || normalized === 'trade_id' || normalized === 'code') return '唯一标识';
  return value;
}

function datasetFieldSemanticTypeLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === 'unknown') return '';
  if (normalized === 'identifier') return '标识字段';
  if (normalized === 'amount') return '金额字段';
  if (normalized === 'datetime') return '时间字段';
  if (normalized === 'enum') return '枚举字段';
  if (normalized === 'text' || normalized === 'string') return '文本字段';
  if (normalized === 'number') return '数值字段';
  return value;
}

function buildDatasetFieldSummary(row: EditableDatasetSemanticFieldRow): string {
  const parts: string[] = [];
  const roleLabel = datasetFieldBusinessRoleLabel(row.businessRole);
  const semanticTypeLabel = datasetFieldSemanticTypeLabel(row.semanticType);
  if (roleLabel) parts.push(roleLabel);
  if (semanticTypeLabel && semanticTypeLabel !== roleLabel) parts.push(semanticTypeLabel);
  if (typeof row.confidence === 'number') {
    parts.push(`置信度 ${Math.round(row.confidence * 100)}%`);
  }
  return parts.join(' · ');
}

function formatSemanticKeyFieldLabel(field: string, fieldLabelMap: Record<string, string>): string {
  const displayName = fieldLabelMap[field]?.trim();
  if (!displayName || displayName === field) return field;
  return `${displayName} · ${field}`;
}

function buildUniqueIdentifierRawNames(
  existingKeyFields: string[],
  fieldRows: EditableDatasetSemanticFieldRow[],
  shouldInfer: boolean,
): string[] {
  const rawNames: string[] = [];
  const seen = new Set<string>();
  const normalizedRowByRawName = new Map(fieldRows.map((row) => [row.rawName.trim().toLowerCase(), row]));
  const normalizedRowByDisplayName = new Map<string, EditableDatasetSemanticFieldRow>();
  fieldRows.forEach((row) => {
    const displayName = row.displayName.trim().toLowerCase();
    if (displayName && !normalizedRowByDisplayName.has(displayName)) {
      normalizedRowByDisplayName.set(displayName, row);
    }
  });

  const pushRawName = (rawName: string) => {
    const normalized = rawName.trim().toLowerCase();
    if (!normalized || seen.has(normalized)) return;
    const matchedRow = normalizedRowByRawName.get(normalized);
    if (!matchedRow) return;
    seen.add(normalized);
    rawNames.push(matchedRow.rawName);
  };

  existingKeyFields.forEach((field) => {
    const normalized = field.trim().toLowerCase();
    if (!normalized) return;
    const matchedRow = normalizedRowByRawName.get(normalized) ?? normalizedRowByDisplayName.get(normalized);
    if (matchedRow) {
      pushRawName(matchedRow.rawName);
    }
  });

  if (shouldInfer && rawNames.length === 0) {
    fieldRows
      .filter((row) => inferDatasetFieldBusinessRole(row.rawName) === 'identifier' || row.businessRole === 'identifier')
      .forEach((row) => pushRawName(row.rawName));
  }

  return rawNames.slice(0, 5);
}

function buildEditableDatasetSemanticFieldRows(dataset: DataSourceDatasetSummary): EditableDatasetSemanticFieldRow[] {
  const cachedSemantic = hasDatasetSemanticCache(dataset);
  const semanticInfo = readDatasetSemanticInfo(dataset);
  const semanticFields = Array.isArray(dataset.semantic_fields)
    ? dataset.semantic_fields.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
    : [];
  const pendingSet = new Set((dataset.low_confidence_fields ?? []).map((item) => item.trim()).filter(Boolean));
  const schemaFields = extractDatasetSchemaFields(dataset);
  const orderedKeys = Array.from(
    new Set([
      ...schemaFields,
      ...Object.keys(semanticInfo.fieldLabelMap),
      ...semanticFields
        .map((field) => {
          const value = asRecord(field);
          return asString(value?.raw_name) ?? asString(value?.name) ?? '';
        })
        .map((item) => item.trim())
        .filter(Boolean),
    ]),
  );
  const semanticFieldMap = new Map<string, Record<string, unknown>>();
  semanticFields.forEach((field) => {
    const value = asRecord(field);
    const rawName = (asString(value?.raw_name) ?? asString(value?.name) ?? '').trim();
    if (!rawName) return;
    semanticFieldMap.set(rawName, value ?? {});
  });
  return orderedKeys.map((rawName) => {
    const semanticField = semanticFieldMap.get(rawName) ?? {};
    const confidence = asNumber(semanticField.confidence);
    const confirmedByUser = asBoolean(semanticField.confirmed_by_user) ?? false;
    const semanticDisplayName =
      (asString(semanticField.display_name) ??
        asString(semanticField.display_name_zh) ??
        semanticInfo.fieldLabelMap[rawName] ??
        '')
        .trim();
    const pending =
      !cachedSemantic ||
      pendingSet.has(rawName) ||
      (!confirmedByUser && typeof confidence === 'number' && Number.isFinite(confidence) && confidence < 0.75);
    return {
      id: `semantic-field-${rawName}`,
      rawName,
      displayName: resolveDatasetFieldDisplayName(rawName, semanticDisplayName, confirmedByUser),
      semanticType: (asString(semanticField.semantic_type) ?? inferDatasetFieldSemanticType(rawName)).trim(),
      businessRole: (asString(semanticField.business_role) ?? inferDatasetFieldBusinessRole(rawName)).trim(),
      description: (asString(semanticField.description) ?? '').trim(),
      confidence: typeof confidence === 'number' && Number.isFinite(confidence) ? confidence : null,
      confirmedByUser,
      pending,
      sampleValues: asStringArray(semanticField.sample_values) ?? [],
    };
  });
}

function buildEditableDatasetSemanticState(
  source: Pick<DataSourceListItem, 'id' | 'name'>,
  dataset: DataSourceDatasetSummary,
): EditableDatasetSemantic {
  const semantic = readDatasetSemanticInfo(dataset);
  const collectionConfig = asRecord(dataset.collection_config) ?? asRecord(asRecord(dataset.meta)?.collection_config) ?? {};
  const collectionSchedule = asRecord(collectionConfig.schedule) ?? {};
  const { schemaName, objectName } = parseSchemaAndObjectName(dataset);
  const fieldRows = buildEditableDatasetSemanticFieldRows(dataset);
  const uniqueIdentifierRawNames = buildUniqueIdentifierRawNames(
    semantic.keyFields,
    fieldRows,
    !semantic.keyFieldsExplicit,
  );
  return {
    sourceId: source.id,
    sourceName: source.name || source.id,
    datasetId: dataset.id,
    datasetCode: dataset.dataset_code,
    datasetName: dataset.dataset_name,
    resourceKey: dataset.resource_key || '',
    schemaName,
    objectName,
    objectType: readDatasetObjectType(dataset),
    businessName: semantic.businessName || dataset.business_name || dataset.dataset_name,
    businessObjectType: readDatasetBusinessObjectType(dataset),
    grain: readDatasetGrain(dataset),
    verifiedStatus: readDatasetVerifiedStatus(dataset),
    publishStatus: readDatasetPublishStatus(dataset),
    uniqueIdentifierRawNames,
    collectionDateField: asString(collectionConfig.date_field) ?? '',
    collectionScheduleFrequency: asString(collectionSchedule.frequency) ?? 'daily',
    collectionScheduleTime: asString(collectionSchedule.time) ?? '08:30',
    fieldRows,
  };
}

function normalizeUniqueIdentifierRawNames(
  rawNames: string[],
  fieldRows: EditableDatasetSemanticFieldRow[],
): string[] {
  const validRawNames = new Map(fieldRows.map((row) => [row.rawName.trim().toLowerCase(), row.rawName]));
  const seen = new Set<string>();
  const normalized: string[] = [];
  rawNames.forEach((rawName) => {
    const key = rawName.trim().toLowerCase();
    const validRawName = validRawNames.get(key);
    if (!validRawName || seen.has(key)) return;
    seen.add(key);
    normalized.push(validRawName);
  });
  return normalized;
}

function stabilizeDatasetRowOrder(
  previousRows: DataSourceDatasetSummary[],
  nextRows: DataSourceDatasetSummary[],
): DataSourceDatasetSummary[] {
  if (previousRows.length === 0 || nextRows.length <= 1) return nextRows;
  const previousOrder = new Map<string, number>();
  previousRows.forEach((row, index) => {
    const key = row.id || row.dataset_code;
    if (key && !previousOrder.has(key)) previousOrder.set(key, index);
  });

  const withKnownOrder: Array<{ row: DataSourceDatasetSummary; index: number }> = [];
  const appended: DataSourceDatasetSummary[] = [];

  nextRows.forEach((row) => {
    const key = row.id || row.dataset_code;
    const previousIndex = key ? previousOrder.get(key) : undefined;
    if (previousIndex === undefined) {
      appended.push(row);
      return;
    }
    withKnownOrder.push({ row, index: previousIndex });
  });

  withKnownOrder.sort((left, right) => left.index - right.index);
  return [...withKnownOrder.map((item) => item.row), ...appended];
}

function isSourceKind(value: string): value is DataSourceKind {
  return ['platform_oauth', 'database', 'api', 'file', 'browser', 'desktop_cli'].includes(value);
}

function inferDatabaseType(providerCode: string, dbType?: string): string {
  const normalizedType = String(dbType || '').trim().toLowerCase();
  if (normalizedType === 'mysql') return 'mysql';
  if (normalizedType === 'hologres' || normalizedType === 'postgresql' || normalizedType === 'postgres') {
    return 'hologres';
  }

  const normalizedProvider = providerCode.trim().toLowerCase();
  if (normalizedProvider.includes('hologres')) return 'hologres';
  if (normalizedProvider.includes('mysql')) return 'mysql';
  return 'hologres';
}

function databaseTypeLabel(value: string): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'hologres') return 'Hologres';
  if (normalized === 'mysql') return 'MySQL';
  return 'Hologres';
}

function dataSourceSubtitle(source: DataSourceListItem): string {
  if (source.source_kind === 'database') {
    return `${databaseTypeLabel(inferDatabaseType(source.provider_code, source.connection_config?.database?.db_type))} 数据库连接`;
  }
  if (source.source_kind === 'api') {
    const apiConfig = source.connection_config?.api;
    const usesRequestAuth =
      apiConfig?.auth_mode === 'request' ||
      Boolean(apiConfig?.auth_request_url || apiConfig?.auth_request_configured || apiConfig?.auth_apply_header_name);
    const authLabel = usesRequestAuth ? '已配置鉴权' : '无鉴权';
    return `HTTP API · ${authLabel}`;
  }
  return sourceKindLabel(source.source_kind);
}

function databaseConnectionAccount(source: DataSourceListItem): string {
  const username = source.connection_config?.database?.username?.trim();
  return username ? `账号：${username}` : '账号未配置';
}

function splitMultilineOrComma(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseOptionalNumber(value: string, fieldLabel: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${fieldLabel} 必须是数字`);
  }
  return parsed;
}

function parseJsonObjectText(value: string, fieldLabel: string): Record<string, unknown> | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${fieldLabel} 不是合法 JSON`);
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${fieldLabel} 必须是 JSON 对象`);
  }
  return parsed as Record<string, unknown>;
}

function createEditableKeyValueRow(key = '', value = ''): EditableKeyValueRow {
  return {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    key,
    value,
  };
}

function createEditableKeyValueRows(value?: Record<string, unknown>): EditableKeyValueRow[] {
  const entries = Object.entries(value || {}).map(([key, item]) => createEditableKeyValueRow(key, String(item ?? '')));
  return entries.length > 0 ? entries : [createEditableKeyValueRow()];
}

function keyValueRowsToRecord(rows: EditableKeyValueRow[]): Record<string, string> | undefined {
  const entries = rows
    .map((item) => [item.key.trim(), item.value] as const)
    .filter(([key]) => key.length > 0);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries);
}

function compactObject<T extends Record<string, unknown>>(value: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => {
      if (item === undefined || item === null) return false;
      if (typeof item === 'string') return item.trim().length > 0;
      if (Array.isArray(item)) return item.length > 0;
      return true;
    }),
  ) as Partial<T>;
}
void splitMultilineOrComma;
void parseOptionalNumber;
void parseJsonObjectText;
void compactObject;

function createEditableSourceConfig(source: DataSourceListItem): EditableSourceConfig {
  const databaseConfig = source.connection_config?.database;
  const apiConfig = source.connection_config?.api;

  return {
    id: source.id,
    source_kind: source.source_kind as Extract<DataSourceKind, 'database' | 'api' | 'file'>,
    name: source.name || '',
    description: source.description || '',
    database: {
      db_type: inferDatabaseType(source.provider_code, databaseConfig?.db_type),
      host: databaseConfig?.host || '',
      port: databaseConfig?.port ? String(databaseConfig.port) : '',
      database: databaseConfig?.database || '',
      username: databaseConfig?.username || '',
      password: databaseConfig?.password || '',
    },
    api: {
      auth_mode: apiConfig?.auth_mode || (apiConfig?.auth_request_url ? 'request' : 'none'),
      auth_request_url: apiConfig?.auth_request_url || '',
      auth_request_method: apiConfig?.auth_request_method || 'POST',
      auth_request_payload_type: apiConfig?.auth_request_payload_type || 'json',
      auth_request_headers: createEditableKeyValueRows(apiConfig?.auth_request_headers),
      auth_request_params: createEditableKeyValueRows(
        apiConfig?.auth_request_params ?? (apiConfig?.auth_request_payload as Record<string, unknown> | undefined),
      ),
      auth_request_json_text: apiConfig?.auth_request_json_payload
        ? JSON.stringify(apiConfig.auth_request_json_payload, null, 2)
        : '',
      auth_apply_header_name: apiConfig?.auth_apply_header_name || '',
      auth_apply_value_template:
        apiConfig?.auth_apply_value_template ||
        (apiConfig?.auth_response_path
          ? apiConfig.auth_apply_prefix
            ? `${apiConfig.auth_apply_prefix}{${apiConfig.auth_response_path}}`
            : apiConfig.auth_response_path
          : ''),
    },
  };
}

function buildSourceConnectionConfigs(
  source: DataSourceListItem,
  form: EditableSourceConfig,
): {
  connectionConfig: Record<string, unknown>;
  authConfig: Record<string, unknown>;
} {
  let connectionConfig: Record<string, unknown> = {};
  let authConfig: Record<string, unknown> = {};

  if (source.source_kind === 'database') {
    const dbType = inferDatabaseType(source.provider_code, form.database.db_type);
    connectionConfig = compactObject({
      db_type: dbType,
      host: form.database.host.trim(),
      port: parseOptionalNumber(form.database.port, '端口'),
      database: form.database.database.trim(),
      username: form.database.username.trim(),
    });
    authConfig = compactObject({
      password: form.database.password.trim(),
    });
  } else if (source.source_kind === 'api') {
    const authMode = form.api.auth_mode.trim() || 'none';
    const authRequestHeaders = keyValueRowsToRecord(form.api.auth_request_headers);
    const authRequestParams = keyValueRowsToRecord(form.api.auth_request_params);
    const authRequestJsonPayload =
      form.api.auth_request_payload_type === 'json'
        ? parseJsonObjectText(form.api.auth_request_json_text, '鉴权请求参数')
        : undefined;

    if (authMode === 'request') {
      if (!form.api.auth_request_url.trim()) {
        throw new Error('请填写鉴权请求地址');
      }
      if (!form.api.auth_apply_header_name.trim()) {
        throw new Error('请填写凭证写入的 Header 名称');
      }
      if (!form.api.auth_apply_value_template.trim()) {
        throw new Error('请填写 Header 取值');
      }
    }

    connectionConfig = compactObject({
      auth_mode: authMode,
      auth_request_url: authMode === 'request' ? form.api.auth_request_url.trim() : '',
      auth_request_method: authMode === 'request' ? form.api.auth_request_method.trim() : '',
      auth_request_payload_type: authMode === 'request' ? form.api.auth_request_payload_type.trim() : '',
      auth_apply_header_name: authMode === 'request' ? form.api.auth_apply_header_name.trim() : '',
      auth_apply_value_template: authMode === 'request' ? form.api.auth_apply_value_template.trim() : '',
      auth_request_configured: authMode === 'request',
    });
    authConfig =
      authMode === 'request'
        ? compactObject({
            auth_request_headers: authRequestHeaders ?? {},
            auth_request_params: form.api.auth_request_payload_type !== 'json' ? authRequestParams ?? {} : {},
            auth_request_json_payload: form.api.auth_request_payload_type === 'json' ? authRequestJsonPayload ?? {} : {},
          })
        : {};
  }

  return { connectionConfig, authConfig };
}

function buildSourceSavePayload(
  source: DataSourceListItem,
  form: EditableSourceConfig,
): {
  payload: Record<string, unknown>;
  connectionConfig: Record<string, unknown>;
  authConfig: Record<string, unknown>;
} {
  const trimmedName = form.name.trim();
  const { connectionConfig, authConfig } = buildSourceConnectionConfigs(source, form);

  return {
    connectionConfig,
    authConfig,
    payload: {
      name:
        trimmedName ||
        source.name ||
        `${source.source_kind === 'database' ? '数据库' : source.source_kind === 'api' ? 'API' : '文件'}连接`,
      description: form.description.trim(),
      connection_config: connectionConfig,
      ...(Object.keys(authConfig).length > 0 ? { auth_config: authConfig } : {}),
    },
  };
}

function normalizeDataset(raw: unknown): DataSourceDatasetSummary | null {
  const value = asRecord(raw);
  if (!value) return null;
  const id = asString(value.id) ?? asString(value.dataset_id) ?? '';
  const datasetCode = asString(value.dataset_code) ?? asString(value.code) ?? '';
  const datasetName = asString(value.dataset_name) ?? asString(value.name) ?? datasetCode;
  if (!id && !datasetCode && !datasetName) return null;

  return {
    id: id || datasetCode || `dataset-${datasetName}`,
    dataset_code: datasetCode || id || datasetName,
    dataset_name: datasetName || datasetCode || id,
    updated_at: asStringOrNull(value.updated_at),
    schema_name: asString(value.schema_name),
    object_name: asString(value.object_name),
    object_type: asString(value.object_type),
    publish_status: asString(value.publish_status),
    verified_status: asString(value.verified_status),
    business_domain: asString(value.business_domain),
    business_object_type: asString(value.business_object_type),
    grain: asString(value.grain),
    usage_count: asNumber(value.usage_count),
    last_used_at: asStringOrNull(value.last_used_at),
    business_name: asString(value.business_name),
    business_description: asString(value.business_description),
    semantic_status: asString(value.semantic_status),
    semantic_updated_at: asStringOrNull(value.semantic_updated_at),
    semantic_pending_count: asNumber(value.semantic_pending_count),
    key_fields: asStringArray(value.key_fields),
    field_label_map: asStringRecord(value.field_label_map),
    semantic_fields: Array.isArray(value.semantic_fields)
      ? value.semantic_fields.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
      : undefined,
    low_confidence_fields: asStringArray(value.low_confidence_fields),
    collection_config: asRecord(value.collection_config) ?? undefined,
    origin_type: asString(value.origin_type),
    dataset_kind: asString(value.dataset_kind),
    resource_key: asString(value.resource_key),
    status: asString(value.status),
    is_enabled: asBoolean(value.is_enabled) ?? asBoolean(value.enabled),
    health_status: asString(value.health_status),
    last_checked_at: asStringOrNull(value.last_checked_at),
    last_sync_at: asStringOrNull(value.last_sync_at),
    last_error_message: asStringOrNull(value.last_error_message),
    extract_config: asRecord(value.extract_config) ?? undefined,
    schema_summary: asRecord(value.schema_summary) ?? undefined,
    sync_strategy: asRecord(value.sync_strategy) ?? undefined,
    meta: asRecord(value.meta) ?? asRecord(value.metadata) ?? undefined,
    source: asRecord(value.source)
      ? {
          id: asString(asRecord(value.source)?.id),
          name: asString(asRecord(value.source)?.name),
          source_kind: asString(asRecord(value.source)?.source_kind),
          provider_code: asString(asRecord(value.source)?.provider_code),
        }
      : undefined,
  };
}

function normalizeEvent(raw: unknown): DataSourceEventSummary | null {
  const value = asRecord(raw);
  if (!value) return null;
  const id = asString(value.id) ?? '';
  const message = asString(value.message) ?? '';
  if (!id && !message) return null;
  return {
    id: id || `event-${Date.now().toString(36)}`,
    level: asString(value.level) ?? asString(value.event_level),
    event_type: asString(value.event_type),
    message: message || asString(value.event_message) || asString(value.detail) || '无描述',
    created_at: asStringOrNull(value.created_at),
    dataset_code: asStringOrNull(value.dataset_code),
    meta: asRecord(value.meta) ?? asRecord(value.payload) ?? asRecord(value.event_payload) ?? undefined,
  };
}

function normalizeSourceItem(raw: unknown): DataSourceListItem | null {
  const value = asRecord(raw);
  if (!value) return null;

  const id = asString(value.id) ?? '';
  const sourceKindRaw = asString(value.source_kind) ?? '';
  const sourceKind = isSourceKind(sourceKindRaw) ? sourceKindRaw : undefined;
  if (!id || !sourceKind) return null;

  const metadata = asRecord(value.metadata) ?? {};
  const healthSummaryRaw = asRecord(value.health_summary);
  const sourceHealthRaw = asRecord(healthSummaryRaw?.source);
  const datasetHealthRaw = asRecord(healthSummaryRaw?.datasets);
  const datasetHealthCounts = asNumberRecord(datasetHealthRaw?.by_health_status);
  const connectionConfigRaw = asRecord(value.connection_config);
  const capabilityList = asStringArray(value.capabilities) ?? [];
  const databaseConfigRaw =
    asRecord(connectionConfigRaw?.database) ??
    (sourceKind === 'database' ? connectionConfigRaw : null) ??
    asRecord(metadata.database_config);
  const apiConfigRaw =
    asRecord(connectionConfigRaw?.api) ??
    (sourceKind === 'api' ? connectionConfigRaw : null) ??
    asRecord(metadata.api_config);
  const discoverSummaryRaw = asRecord(value.discover_summary) ?? asRecord(metadata.discover_summary);
  const capabilitiesRaw = asRecord(value.capabilities) ?? asRecord(metadata.capabilities);

  const datasetsRaw = Array.isArray(value.datasets) ? value.datasets : [];
  const eventsRaw = Array.isArray(value.recent_events) ? value.recent_events : [];

  return {
    id,
    source_kind: sourceKind,
    provider_code: asString(value.provider_code) ?? 'unknown',
    name: asString(value.name) ?? id,
    code: asString(value.code),
    status: asString(value.status) ?? 'unknown',
    execution_mode: value.execution_mode === 'agent_assisted' ? 'agent_assisted' : 'deterministic',
    description: asString(value.description),
    updated_at: asStringOrNull(value.updated_at),
    health_status: asString(value.health_status),
    last_checked_at: asStringOrNull(value.last_checked_at),
    last_error_message: asStringOrNull(value.last_error_message),
    health_summary: {
      connection_status:
        asString(healthSummaryRaw?.connection_status) ??
        asString(sourceHealthRaw?.health_status) ??
        asString(healthSummaryRaw?.overall_status) ??
        asString(metadata.connection_status) ??
        asString(value.status),
      dataset_status:
        asString(healthSummaryRaw?.dataset_status) ??
        asString(datasetHealthRaw?.health_status) ??
        asString(healthSummaryRaw?.overall_status) ??
        asString(metadata.dataset_status),
      warning_count:
        asNumber(healthSummaryRaw?.warning_count) ??
        datasetHealthCounts?.warning ??
        asNumber(metadata.warning_count),
      error_count:
        asNumber(healthSummaryRaw?.error_count) ??
        ((datasetHealthCounts?.error ?? 0) +
          (datasetHealthCounts?.auth_expired ?? 0) +
          (datasetHealthCounts?.disabled ?? 0)),
      last_checked_at:
        asStringOrNull(healthSummaryRaw?.last_checked_at) ??
        asStringOrNull(sourceHealthRaw?.last_checked_at) ??
        asStringOrNull(datasetHealthRaw?.last_checked_at),
      last_sync_at:
        asStringOrNull(healthSummaryRaw?.last_sync_at) ??
        asStringOrNull(datasetHealthRaw?.last_sync_at) ??
        asStringOrNull(value.last_sync_at) ??
        asStringOrNull(value.updated_at),
      last_error_message:
        asStringOrNull(healthSummaryRaw?.last_error_message) ??
        asStringOrNull(sourceHealthRaw?.last_error_message) ??
        asStringOrNull(metadata.last_error_message),
    },
    datasets: datasetsRaw.map((item) => normalizeDataset(item)).filter(Boolean) as DataSourceDatasetSummary[],
    recent_events: eventsRaw.map((item) => normalizeEvent(item)).filter(Boolean) as DataSourceEventSummary[],
    connection_config: {
      database: databaseConfigRaw
        ? {
            db_type: asString(databaseConfigRaw.db_type),
            host: asString(databaseConfigRaw.host),
            port: asNumber(databaseConfigRaw.port),
            database: asString(databaseConfigRaw.database),
            username: asString(databaseConfigRaw.username),
            password: asString(databaseConfigRaw.password),
            ssl_mode: asString(databaseConfigRaw.ssl_mode),
            schema_whitelist: asStringArray(databaseConfigRaw.schema_whitelist),
          }
        : undefined,
      api: apiConfigRaw
        ? {
            base_url: asString(apiConfigRaw.base_url),
            auth_mode: asString(apiConfigRaw.auth_mode),
            credential_kind: asString(apiConfigRaw.credential_kind),
            auth_request_url: asString(apiConfigRaw.auth_request_url),
            auth_request_method: asString(apiConfigRaw.auth_request_method),
            auth_request_payload_type: asString(apiConfigRaw.auth_request_payload_type),
            auth_apply_value_template: asString(apiConfigRaw.auth_apply_value_template),
            auth_response_path: asString(apiConfigRaw.auth_response_path),
            auth_apply_header_name: asString(apiConfigRaw.auth_apply_header_name),
            auth_apply_prefix: asString(apiConfigRaw.auth_apply_prefix),
            auth_request_configured: asBoolean(apiConfigRaw.auth_request_configured),
            auth_request_headers: asRecord(apiConfigRaw.auth_request_headers) as Record<string, string> | undefined,
            auth_request_params: asRecord(apiConfigRaw.auth_request_params) as Record<string, string> | undefined,
            auth_request_json_payload: asRecord(apiConfigRaw.auth_request_json_payload) ?? undefined,
            auth_request_payload: asRecord(apiConfigRaw.auth_request_payload) ?? undefined,
            auth_type: asString(apiConfigRaw.auth_type),
            token: asString(apiConfigRaw.token),
            api_key: asString(apiConfigRaw.api_key),
            api_key_header: asString(apiConfigRaw.api_key_header),
            basic_auth_header: asString(apiConfigRaw.basic_auth_header),
            health_path: asString(apiConfigRaw.health_path),
            timeout_seconds: asNumber(apiConfigRaw.timeout_seconds ?? apiConfigRaw.timeout_ms),
            rate_limit_qps: asNumber(apiConfigRaw.rate_limit_qps),
            openapi_source: asString(apiConfigRaw.openapi_source),
          }
        : undefined,
      auth_status:
        asString(connectionConfigRaw?.auth_status) ?? asString(metadata.auth_status) ?? asString(value.status),
      token_expires_at:
        asStringOrNull(connectionConfigRaw?.token_expires_at) ?? asStringOrNull(metadata.token_expires_at),
    },
    discover_summary: normalizeDiscoverSummary(discoverSummaryRaw),
    capabilities: capabilitiesRaw
      ? {
          can_discover: asBoolean(capabilitiesRaw.can_discover),
          can_import_openapi: asBoolean(capabilitiesRaw.can_import_openapi),
          can_add_manual_endpoint: asBoolean(capabilitiesRaw.can_add_manual_endpoint),
          can_manage_datasets: asBoolean(capabilitiesRaw.can_manage_datasets),
        }
      : capabilityList.length > 0
      ? {
          can_discover: capabilityList.includes('discover_datasets'),
          can_import_openapi: capabilityList.includes('import_openapi'),
          can_add_manual_endpoint: capabilityList.includes('discover_datasets'),
          can_manage_datasets:
            capabilityList.includes('list_datasets') || capabilityList.includes('discover_datasets'),
        }
      : undefined,
    metadata,
    source_summary: asRecord(value.source_summary) ?? undefined,
    dataset_summary: asRecord(value.dataset_summary) ?? undefined,
  };
}

function normalizePlatformSummary(raw: unknown): PlatformConnectionSummary | null {
  const value = asRecord(raw);
  if (!value) return null;
  const platformCode = asString(value.platform_code) ?? '';
  const platformName = asString(value.platform_name) ?? '';
  if (!platformCode || !platformName) return null;
  return {
    platform_code: platformCode,
    platform_name: platformName,
    authorized_shop_count: asNumber(value.authorized_shop_count) ?? 0,
    error_shop_count: asNumber(value.error_shop_count) ?? 0,
    last_sync_at: asStringOrNull(value.last_sync_at) ?? null,
    status: asString(value.status) ?? undefined,
  };
}

function executionModeLabel(mode: DataSourceExecutionMode): string {
  return mode === 'agent_assisted' ? 'Agent Assisted' : 'Deterministic';
}

function sourceKindIcon(kind: DataSourceKind) {
  if (kind === 'platform_oauth') return <Store className="h-4 w-4" />;
  if (kind === 'database') return <Database className="h-4 w-4" />;
  if (kind === 'api') return <Globe className="h-4 w-4" />;
  if (kind === 'file') return <FileSpreadsheet className="h-4 w-4" />;
  if (kind === 'browser') return <MonitorSmartphone className="h-4 w-4" />;
  return <Cpu className="h-4 w-4" />;
}

function collaborationProviderIcon(provider: CollaborationProvider) {
  if (provider === 'dingtalk_dws') return <MessageSquare className="h-4 w-4" />;
  if (provider === 'feishu') return <Globe className="h-4 w-4" />;
  if (provider === 'wechat_work') return <ShieldCheck className="h-4 w-4" />;
  return <MessageSquare className="h-4 w-4" />;
}

function collaborationProviderCard(provider: CollaborationProvider) {
  return COLLABORATION_CHANNEL_CARDS.find((item) => item.provider === provider) ?? COLLABORATION_CHANNEL_CARDS[0];
}

function channelConfigStatus(config: CollaborationChannelListItem): string {
  if (config.is_enabled === false) return 'disabled';
  if (!config.client_id || !config.client_secret) return 'pending';
  return 'active';
}

function buildDraftChannel(provider: CollaborationProvider): EditableChannelConfig {
  const card = collaborationProviderCard(provider);
  return {
    id: `draft-channel-${provider}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    provider,
    channel_code: 'default',
    name: card.defaultName,
    client_id: '',
    client_secret: '',
    robot_code: '',
    is_default: true,
    is_enabled: true,
    extraText: '',
    isDraft: true,
  };
}

function formatTime(value?: string | null): string {
  if (!value) return '暂无';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '暂无';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function getStatusLabel(status?: string): string {
  const normalized = (status || '').toLowerCase();
  if (normalized === 'success') return '成功';
  if (normalized === 'failed') return '失败';
  if (normalized === 'authorized') return '已授权';
  if (normalized === 'active') return '活跃';
  if (normalized === 'pending') return '待配置';
  if (normalized === 'draft') return '占位草稿';
  if (normalized === 'token_expiring') return '即将过期';
  if (normalized === 'token_expired') return '已过期';
  if (normalized === 'reauth_required') return '需重授权';
  if (normalized === 'disabled') return '已停用';
  if (normalized === 'sync_error') return '同步异常';
  if (normalized === 'error') return '异常';
  return status || '未知';
}

function statusTone(status?: string): 'ok' | 'warn' | 'error' | 'neutral' {
  const normalized = (status || '').toLowerCase();
  if (['healthy', 'success', 'active', 'connected', 'authorized'].includes(normalized)) return 'ok';
  if (['warning', 'pending', 'token_expiring'].includes(normalized)) return 'warn';
  if (
    ['error', 'failed', 'sync_error', 'auth_expired', 'token_expired', 'reauth_required', 'disconnected'].includes(
      normalized,
    )
  ) {
    return 'error';
  }
  return 'neutral';
}

function statusBadgeClass(status?: string): string {
  const tone = statusTone(status);
  if (tone === 'ok') return 'bg-emerald-500/10 text-emerald-600';
  if (tone === 'warn') return 'bg-amber-500/10 text-amber-600';
  if (tone === 'error') return 'bg-red-500/10 text-red-600';
  return 'bg-surface-accent text-text-secondary';
}

function createDefaultSourceDetail(): SourceDetailState {
  return {
    datasets: [],
    events: [],
    datasetsLoading: false,
    eventsLoading: false,
    datasetsError: '',
    eventsError: '',
    datasetsApiAvailable: null,
    eventsApiAvailable: null,
  };
}

function createDefaultDatasetListPageState(pageSize = 20): DatasetListPageState {
  return {
    rows: [],
    loading: false,
    error: '',
    apiAvailable: null,
    total: 0,
    page: 1,
    pageSize,
  };
}

function createDefaultDatasetDetailState(): DatasetDetailState {
  return {
    datasetId: null,
    dataset: null,
    loading: false,
    error: '',
  };
}

function createDefaultPhysicalCatalogFilterState(): PhysicalCatalogFilterState {
  return {
    keyword: '',
    schema: 'all',
    objectType: 'all',
    publishStatus: 'all',
    verifiedStatus: 'all',
    page: 1,
    pageSize: 20,
  };
}

function publishStatusLabel(status: string): string {
  if (status === 'published') return '已发布';
  if (status === 'unpublished') return '未发布';
  if (status === 'draft') return '草稿';
  if (status === 'archived') return '已归档';
  if (status === 'deprecated') return '已废弃';
  return status || '未知';
}

function verifiedStatusLabel(status: string): string {
  if (status === 'verified') return '已验证';
  if (status === 'unverified') return '未验证';
  if (status === 'rejected') return '已驳回';
  return status || '未知';
}

function createDefaultApiDiscoveryForm(): ApiDiscoveryFormState {
  return {
    discoveryMode: 'document',
    documentInputMode: 'url',
    documentUrl: '',
    documentContent: '',
    manualDatasetName: '',
    manualApiPath: '',
    manualMethod: 'GET',
    manualParamType: 'params',
    manualParams: [createEditableKeyValueRow()],
    manualJsonText: '',
  };
}

export default function DataConnectionsPanel({
  authToken,
  initialCallback = null,
  onBackToChat,
  selectedConnectionView,
  selectedSourceKind,
  selectedCollaborationProvider,
}: DataConnectionsPanelProps) {
  const clearCallbackQuery = useCallback((nextSection: 'chat' | 'data-connections' = 'data-connections') => {
    const url = new URL(window.location.href);
    url.searchParams.delete('platform_auth_status');
    url.searchParams.delete('platform_code');
    url.searchParams.delete('platform_auth_message');
    url.searchParams.delete('status');
    url.searchParams.delete('platform');
    url.searchParams.delete('message');
    url.searchParams.delete('shop_name');
    if (nextSection === 'data-connections') {
      url.searchParams.set('section', 'data-connections');
    } else {
      url.searchParams.delete('section');
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }, []);

  const [mode, setMode] = useState<DataConnectionsMode>(initialCallback ? 'callback' : 'overview');
  const [platforms, setPlatforms] = useState<PlatformConnectionSummary[]>([]);
  const [loadingPlatforms, setLoadingPlatforms] = useState(false);
  const [platformError, setPlatformError] = useState<string>('');
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformConnectionSummary | null>(null);
  const [shops, setShops] = useState<ShopConnection[]>([]);
  const [loadingShops, setLoadingShops] = useState(false);
  const [shopError, setShopError] = useState<string>('');
  const [actioningShopId, setActioningShopId] = useState<string | null>(null);
  const [callbackPayload, setCallbackPayload] = useState<AuthCallbackPayload | null>(initialCallback);
  const [launchingAuthPlatform, setLaunchingAuthPlatform] = useState<PlatformCode | null>(null);
  const [draftSources, setDraftSources] = useState<DraftDataSource[]>([]);
  const [remoteSources, setRemoteSources] = useState<DataSourceListItem[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [sourcesError, setSourcesError] = useState('');
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [databaseDetailSourceId, setDatabaseDetailSourceId] = useState<string | null>(null);
  const [sourceDetails, setSourceDetails] = useState<Record<string, SourceDetailState>>({});
  const [sourceForms, setSourceForms] = useState<Record<string, EditableSourceConfig>>({});
  const [expandedSourceConfigIds, setExpandedSourceConfigIds] = useState<string[]>([]);
  const [sourceActionBusy, setSourceActionBusy] = useState<string | null>(null);
  const [sourceActionError, setSourceActionError] = useState('');
  const [sourceActionNotice, setSourceActionNotice] = useState('');
  const [datasetActionError, setDatasetActionError] = useState('');
  const [datasetActionNotice, setDatasetActionNotice] = useState('');
  const [targetedDiscoverDialog, setTargetedDiscoverDialog] = useState<TargetedDiscoverDialogState | null>(null);
  const [apiDiscoveryForms, setApiDiscoveryForms] = useState<Record<string, ApiDiscoveryFormState>>({});
  const [remoteChannels, setRemoteChannels] = useState<CollaborationChannelListItem[]>([]);
  const [draftChannels, setDraftChannels] = useState<CollaborationChannelListItem[]>(() =>
    loadCollaborationChannelDrafts(),
  );
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [channelError, setChannelError] = useState('');
  const [channelNotice, setChannelNotice] = useState('');
  const [channelApiAvailable, setChannelApiAvailable] = useState<boolean | null>(null);
  const [editingChannel, setEditingChannel] = useState<EditableChannelConfig | null>(null);
  const [savingChannel, setSavingChannel] = useState(false);
  const [editingDatasetSemantic, setEditingDatasetSemantic] = useState<EditableDatasetSemantic | null>(null);
  const [savingDatasetSemantic, setSavingDatasetSemantic] = useState(false);
  const [datasetSemanticError, setDatasetSemanticError] = useState('');
  const [datasetSemanticNotice, setDatasetSemanticNotice] = useState('');
  const [refreshingDatasetSemantic, setRefreshingDatasetSemantic] = useState(false);
  const [collectionDetailDialog, setCollectionDetailDialog] = useState<DatasetCollectionDetailDialogState | null>(null);
  const [datasetViewTabsBySource, setDatasetViewTabsBySource] = useState<Record<string, DatasetViewTab>>({});
  const [physicalCatalogFiltersBySource, setPhysicalCatalogFiltersBySource] = useState<
    Record<string, PhysicalCatalogFilterState>
  >({});
  const [physicalDetailDatasetBySource, setPhysicalDetailDatasetBySource] = useState<Record<string, string | null>>({});
  const [physicalDetailDialog, setPhysicalDetailDialog] = useState<PhysicalCatalogDetailDialogState | null>(null);
  const [availableDatasetPagesBySource, setAvailableDatasetPagesBySource] = useState<
    Record<string, DatasetListPageState>
  >({});
  const [physicalDatasetPagesBySource, setPhysicalDatasetPagesBySource] = useState<
    Record<string, DatasetListPageState>
  >({});
  const [physicalDatasetDetailBySource, setPhysicalDatasetDetailBySource] = useState<
    Record<string, DatasetDetailState>
  >({});
  const [currentUserRole, setCurrentUserRole] = useState<string>('');

  useEffect(() => {
    if (!initialCallback) return;
    setCallbackPayload(initialCallback);
    setMode('callback');
  }, [initialCallback]);

  useEffect(() => {
    if (mode === 'callback') return;
    setMode('overview');
    setSelectedPlatform(null);
    setSelectedSourceId(null);
    setDatabaseDetailSourceId(null);
    setPhysicalDetailDialog(null);
    setDatasetActionError('');
    setDatasetActionNotice('');
    setShops([]);
    setShopError('');
  }, [selectedConnectionView, selectedSourceKind, selectedCollaborationProvider]);

  useEffect(() => {
    if (!physicalDetailDialog) return;
    if (selectedConnectionView !== 'data_sources') {
      setPhysicalDetailDialog(null);
      return;
    }
    if (!selectedSourceId || physicalDetailDialog.sourceId !== selectedSourceId) {
      setPhysicalDetailDialog(null);
    }
  }, [physicalDetailDialog, selectedConnectionView, selectedSourceId]);

  useEffect(() => {
    if (selectedConnectionView !== 'collaboration_channels') return;
    if (editingChannel && editingChannel.provider !== selectedCollaborationProvider) {
      setEditingChannel(null);
      setChannelError('');
    }
  }, [editingChannel, selectedCollaborationProvider, selectedConnectionView]);

  const authHeaders = useMemo(
    () => ({
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    }),
    [authToken],
  );

  useEffect(() => {
    if (!authToken) {
      setCurrentUserRole('');
      return;
    }
    let cancelled = false;
    const loadRole = async () => {
      try {
        const response = await fetch('/api/auth/me', {
          method: 'GET',
          headers: authHeaders,
        });
        if (!response.ok) return;
        const data = await response.json().catch(() => ({}));
        if (cancelled) return;
        const role =
          asString((data as Record<string, unknown>)?.role) ??
          asString((data as Record<string, unknown>)?.user_role) ??
          asString(asRecord((data as Record<string, unknown>)?.user)?.role) ??
          '';
        setCurrentUserRole((role || '').trim().toLowerCase());
      } catch {
        if (!cancelled) setCurrentUserRole('');
      }
    };
    void loadRole();
    return () => {
      cancelled = true;
    };
  }, [authHeaders, authToken]);

  useEffect(() => {
    saveCollaborationChannelDrafts(draftChannels);
  }, [draftChannels]);

  const fetchPlatforms = useCallback(async () => {
    if (!authToken) return;
    setLoadingPlatforms(true);
    setPlatformError('');
    try {
      const response = await fetch('/api/platform-connections', {
        method: 'GET',
        headers: authHeaders,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载平台连接失败'));
      }
      const list = Array.isArray(data?.platforms)
        ? data.platforms
        : Array.isArray(data?.data?.platforms)
        ? data.data.platforms
        : [];
      setPlatforms(list.map((item: unknown) => normalizePlatformSummary(item)).filter(Boolean) as PlatformConnectionSummary[]);
    } catch (error) {
      setPlatforms([]);
      setPlatformError(error instanceof Error ? error.message : '加载平台连接失败');
    } finally {
      setLoadingPlatforms(false);
    }
  }, [authHeaders, authToken]);

  const fetchRemoteSources = useCallback(async () => {
    if (!authToken) return;
    setLoadingSources(true);
    setSourcesError('');
    try {
      const response = await fetch('/api/data-sources', {
        method: 'GET',
        headers: authHeaders,
      });
      if (response.status === 404 || response.status === 405 || response.status === 501) {
        setRemoteSources([]);
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载数据源列表失败'));
      }
      const list = Array.isArray(data?.data_sources)
        ? data.data_sources
        : Array.isArray(data?.sources)
        ? data.sources
        : Array.isArray(data?.items)
        ? data.items
        : [];
      setRemoteSources(list.map((item: unknown) => normalizeSourceItem(item)).filter(Boolean) as DataSourceListItem[]);
    } catch (error) {
      setRemoteSources([]);
      setSourcesError(error instanceof Error ? error.message : '加载数据源列表失败');
    } finally {
      setLoadingSources(false);
    }
  }, [authHeaders, authToken]);

  const updateSourceDetail = useCallback((sourceId: string, updater: (current: SourceDetailState) => SourceDetailState) => {
    setSourceDetails((prev) => {
      const current = prev[sourceId] ?? createDefaultSourceDetail();
      return {
        ...prev,
        [sourceId]: updater(current),
      };
    });
  }, []);

  const updateAvailableDatasetPageState = useCallback(
    (sourceId: string, updater: (current: DatasetListPageState) => DatasetListPageState) => {
      setAvailableDatasetPagesBySource((prev) => {
        const current = prev[sourceId] ?? createDefaultDatasetListPageState(100);
        return {
          ...prev,
          [sourceId]: updater(current),
        };
      });
    },
    [],
  );

  const updatePhysicalDatasetPageState = useCallback(
    (sourceId: string, updater: (current: DatasetListPageState) => DatasetListPageState) => {
      setPhysicalDatasetPagesBySource((prev) => {
        const current = prev[sourceId] ?? createDefaultDatasetListPageState();
        return {
          ...prev,
          [sourceId]: updater(current),
        };
      });
    },
    [],
  );

  const updatePhysicalDatasetDetailState = useCallback(
    (sourceId: string, updater: (current: DatasetDetailState) => DatasetDetailState) => {
      setPhysicalDatasetDetailBySource((prev) => {
        const current = prev[sourceId] ?? createDefaultDatasetDetailState();
        return {
          ...prev,
          [sourceId]: updater(current),
        };
      });
    },
    [],
  );

  const canManagePhysicalCatalogForSource = useCallback(
    (source: DataSourceListItem | null): boolean => {
      if (!source) return false;
      const sourceMetadata = asRecord(source.metadata);
      return Boolean(
        source.capabilities?.can_manage_datasets === true ||
          asBoolean(sourceMetadata?.can_manage_datasets) === true ||
          asBoolean(sourceMetadata?.is_admin) === true ||
          ['admin', 'owner', 'super_admin'].includes(currentUserRole),
      );
    },
    [currentUserRole],
  );

  const setDatasetViewTab = useCallback((sourceId: string, tab: DatasetViewTab) => {
    setDatasetViewTabsBySource((prev) => ({
      ...prev,
      [sourceId]: tab,
    }));
  }, []);

  const updatePhysicalCatalogFilter = useCallback(
    (sourceId: string, patch: Partial<PhysicalCatalogFilterState>) => {
      setPhysicalCatalogFiltersBySource((prev) => {
        const current = prev[sourceId] ?? createDefaultPhysicalCatalogFilterState();
        const next: PhysicalCatalogFilterState = {
          ...current,
          ...patch,
        };
        if (patch.keyword !== undefined || patch.schema !== undefined || patch.objectType !== undefined || patch.publishStatus !== undefined || patch.verifiedStatus !== undefined || patch.pageSize !== undefined) {
          next.page = 1;
        }
        return {
          ...prev,
          [sourceId]: next,
        };
      });
    },
    [],
  );

  const fetchSourceDatasets = useCallback(
    async (sourceId: string) => {
      if (!authToken) return;
      updateSourceDetail(sourceId, (current) => ({
        ...current,
        datasetsLoading: true,
        datasetsError: '',
      }));
      try {
        const response = await fetch(`/api/data-sources/${sourceId}/datasets`, {
          method: 'GET',
          headers: authHeaders,
        });
        if (response.status === 404 || response.status === 405 || response.status === 501) {
          updateSourceDetail(sourceId, (current) => ({
            ...current,
            datasetsLoading: false,
            datasetsApiAvailable: false,
          }));
          return;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载数据集失败'));
        }
        const rows = Array.isArray(data?.datasets)
          ? data.datasets
          : Array.isArray(data?.data?.datasets)
          ? data.data.datasets
          : Array.isArray(data?.items)
          ? data.items
          : [];
        const datasets = rows
          .map((item: unknown) => normalizeDataset(item))
          .filter(Boolean) as DataSourceDatasetSummary[];
        updateSourceDetail(sourceId, (current) => ({
          ...current,
          datasets,
          datasetsLoading: false,
          datasetsApiAvailable: true,
          datasetsError: '',
        }));
      } catch (error) {
        updateSourceDetail(sourceId, (current) => ({
          ...current,
          datasetsLoading: false,
          datasetsError: error instanceof Error ? error.message : '加载数据集失败',
        }));
      }
    },
    [authHeaders, authToken, updateSourceDetail],
  );

  const fetchAvailableDatasets = useCallback(
    async (sourceId: string, page = 1, pageSize = 100) => {
      if (!authToken) return;
      updateAvailableDatasetPageState(sourceId, (current) => ({
        ...current,
        loading: true,
        error: '',
        page,
        pageSize,
      }));
      try {
        const params = new URLSearchParams();
        params.set('only_published', 'true');
        params.set('include_heavy', 'false');
        params.set('page', String(page));
        params.set('page_size', String(pageSize));
        params.set('sort_by', '-updated_at');
        const response = await fetch(`/api/data-sources/${sourceId}/datasets?${params.toString()}`, {
          method: 'GET',
          headers: authHeaders,
        });
        if (response.status === 404 || response.status === 405 || response.status === 501) {
          updateAvailableDatasetPageState(sourceId, (current) => ({
            ...current,
            loading: false,
            apiAvailable: false,
            rows: [],
            total: 0,
          }));
          return;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载可用数据集失败'));
        }
        const rows = Array.isArray(data?.datasets)
          ? data.datasets
          : Array.isArray(data?.data?.datasets)
          ? data.data.datasets
          : Array.isArray(data?.items)
          ? data.items
          : [];
        const datasets = rows
          .map((item: unknown) => normalizeDataset(item))
          .filter(Boolean) as DataSourceDatasetSummary[];
        updateAvailableDatasetPageState(sourceId, (current) => ({
          rows: stabilizeDatasetRowOrder(current.rows, datasets),
          loading: false,
          error: '',
          apiAvailable: true,
          total: Number(data?.total ?? datasets.length) || datasets.length,
          page: Number(data?.page ?? page) || page,
          pageSize: Number(data?.page_size ?? pageSize) || pageSize,
        }));
      } catch (error) {
        updateAvailableDatasetPageState(sourceId, (current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : '加载可用数据集失败',
        }));
      }
    },
    [authHeaders, authToken, updateAvailableDatasetPageState],
  );

  const fetchPhysicalCatalogDatasets = useCallback(
    async (sourceId: string, filter: PhysicalCatalogFilterState) => {
      if (!authToken) return;
      updatePhysicalDatasetPageState(sourceId, (current) => ({
        ...current,
        loading: true,
        error: '',
      }));
      try {
        const params = new URLSearchParams();
        if (filter.keyword.trim()) params.set('keyword', filter.keyword.trim());
        if (filter.schema !== 'all') params.set('schema_name', filter.schema);
        if (filter.objectType !== 'all') params.set('object_type', filter.objectType);
        if (filter.publishStatus !== 'all') params.set('publish_status', filter.publishStatus);
        if (filter.verifiedStatus !== 'all') params.set('verified_status', filter.verifiedStatus);
        params.set('page', String(Math.max(1, filter.page || 1)));
        params.set('page_size', String(Math.max(5, filter.pageSize || 20)));
        params.set('include_heavy', 'false');
        params.set('sort_by', '-updated_at');
        const response = await fetch(`/api/data-sources/${sourceId}/datasets?${params.toString()}`, {
          method: 'GET',
          headers: authHeaders,
        });
        if (response.status === 404 || response.status === 405 || response.status === 501) {
          updatePhysicalDatasetPageState(sourceId, (current) => ({
            ...current,
            loading: false,
            apiAvailable: false,
            rows: [],
            total: 0,
          }));
          return;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载物理目录失败'));
        }
        const rows = Array.isArray(data?.datasets)
          ? data.datasets
          : Array.isArray(data?.data?.datasets)
          ? data.data.datasets
          : Array.isArray(data?.items)
          ? data.items
          : [];
        const datasets = rows
          .map((item: unknown) => normalizeDataset(item))
          .filter(Boolean) as DataSourceDatasetSummary[];
        const nextPage = Number(data?.page ?? filter.page) || filter.page;
        const nextPageSize = Number(data?.page_size ?? filter.pageSize) || filter.pageSize;
        updatePhysicalDatasetPageState(sourceId, (current) => ({
          rows: stabilizeDatasetRowOrder(current.rows, datasets),
          loading: false,
          error: '',
          apiAvailable: true,
          total: Number(data?.total ?? datasets.length) || datasets.length,
          page: Math.max(1, nextPage),
          pageSize: Math.max(5, nextPageSize),
        }));
        setPhysicalDetailDatasetBySource((prev) => {
          const currentId = prev[sourceId] ?? null;
          if (currentId && datasets.some((dataset) => dataset.id === currentId)) return prev;
          return {
            ...prev,
            [sourceId]: datasets[0]?.id ?? null,
          };
        });
      } catch (error) {
        updatePhysicalDatasetPageState(sourceId, (current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : '加载物理目录失败',
        }));
      }
    },
    [authHeaders, authToken, updatePhysicalDatasetPageState],
  );

  const requestDatasetDetail = useCallback(
    async (sourceId: string, datasetId: string): Promise<DataSourceDatasetSummary | null> => {
      if (!authToken || !datasetId) return null;
      const response = await fetch(`/api/data-sources/${sourceId}/datasets/${encodeURIComponent(datasetId)}`, {
        method: 'GET',
        headers: authHeaders,
      });
      if (response.status === 404 || response.status === 405 || response.status === 501) {
        return null;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载目录详情失败'));
      }
      return normalizeDataset(data?.dataset ?? data?.data?.dataset ?? data?.item);
    },
    [authHeaders, authToken],
  );

  const fetchPhysicalDatasetDetail = useCallback(
    async (sourceId: string, datasetId: string) => {
      if (!authToken || !datasetId) return null;
      updatePhysicalDatasetDetailState(sourceId, (current) => ({
        ...current,
        datasetId,
        loading: true,
        error: '',
      }));
      try {
        const dataset = await requestDatasetDetail(sourceId, datasetId);
        if (!dataset) {
          updatePhysicalDatasetDetailState(sourceId, (current) => ({
            ...current,
            loading: false,
          }));
          return null;
        }
        updatePhysicalDatasetDetailState(sourceId, (current) => ({
          ...current,
          datasetId,
          dataset,
          loading: false,
          error: '',
        }));
        return dataset;
      } catch (error) {
        updatePhysicalDatasetDetailState(sourceId, (current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : '加载目录详情失败',
        }));
        return null;
      }
    },
    [authToken, requestDatasetDetail, updatePhysicalDatasetDetailState],
  );

  const fetchSourceEvents = useCallback(
    async (sourceId: string) => {
      if (!authToken) return;
      updateSourceDetail(sourceId, (current) => ({
        ...current,
        eventsLoading: true,
        eventsError: '',
      }));
      try {
        const response = await fetch(`/api/data-sources/${sourceId}/events`, {
          method: 'GET',
          headers: authHeaders,
        });
        if (response.status === 404 || response.status === 405 || response.status === 501) {
          updateSourceDetail(sourceId, (current) => ({
            ...current,
            eventsLoading: false,
            eventsApiAvailable: false,
          }));
          return;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载最近事件失败'));
        }
        const rows = Array.isArray(data?.events)
          ? data.events
          : Array.isArray(data?.data?.events)
          ? data.data.events
          : Array.isArray(data?.items)
          ? data.items
          : [];
        const events = rows.map((item: unknown) => normalizeEvent(item)).filter(Boolean) as DataSourceEventSummary[];
        updateSourceDetail(sourceId, (current) => ({
          ...current,
          events,
          eventsLoading: false,
          eventsApiAvailable: true,
          eventsError: '',
        }));
      } catch (error) {
        updateSourceDetail(sourceId, (current) => ({
          ...current,
          eventsLoading: false,
          eventsError: error instanceof Error ? error.message : '加载最近事件失败',
        }));
      }
    },
    [authHeaders, authToken, updateSourceDetail],
  );

  const hydrateSourceDetail = useCallback(
    async (sourceId: string) => {
      await Promise.all([fetchSourceDatasets(sourceId), fetchSourceEvents(sourceId)]);
    },
    [fetchSourceDatasets, fetchSourceEvents],
  );

  const fetchCollaborationChannels = useCallback(async () => {
    if (!authToken) return;
    setLoadingChannels(true);
    setChannelError('');
    try {
      const response = await fetch('/api/collaboration-channels', {
        method: 'GET',
        headers: authHeaders,
      });
      if (response.status === 404 || response.status === 405 || response.status === 501) {
        setRemoteChannels([]);
        setChannelApiAvailable(false);
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载协作通道配置失败'));
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
      setRemoteChannels(
        rows
          .map((item: unknown) => normalizeChannelConfig(item))
          .filter(Boolean) as CollaborationChannelListItem[],
      );
      setChannelApiAvailable(true);
    } catch (error) {
      setRemoteChannels([]);
      setChannelError(error instanceof Error ? error.message : '加载协作通道配置失败');
    } finally {
      setLoadingChannels(false);
    }
  }, [authHeaders, authToken]);

  const fetchShops = useCallback(
    async (platformCode: PlatformCode) => {
      if (!authToken) return;
      setLoadingShops(true);
      setShopError('');
      try {
        const response = await fetch(`/api/platform-connections/${platformCode}/shops`, {
          method: 'GET',
          headers: authHeaders,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载店铺列表失败'));
        }
        const list = Array.isArray(data?.data?.shops)
          ? data.data.shops
          : Array.isArray(data?.shops)
          ? data.shops
          : [];
        setShops(list);
      } catch (error) {
        setShops([]);
        setShopError(error instanceof Error ? error.message : '加载店铺列表失败');
      } finally {
        setLoadingShops(false);
      }
    },
    [authHeaders, authToken],
  );

  useEffect(() => {
    if (!authToken) return;
    void fetchPlatforms();
    void fetchRemoteSources();
    void fetchCollaborationChannels();
  }, [authToken, fetchCollaborationChannels, fetchPlatforms, fetchRemoteSources]);

  const createDraftSource = useCallback((kind: Extract<DataSourceKind, 'database' | 'api' | 'file'>) => {
    const prefix = kind === 'database' ? '数据库' : kind === 'api' ? 'API' : '文件';
    const provider = kind === 'database' ? 'postgresql' : kind === 'api' ? 'rest_api' : 'manual_file';
    const now = new Date().toISOString();
    const id = `${kind}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    setDraftSources((prev) => [
      {
        id,
        source_kind: kind,
        name: `${prefix}连接（占位）`,
        provider_code: provider,
        execution_mode: 'deterministic',
        status: 'draft',
        updated_at: now,
      },
      ...prev,
    ]);
  }, []);

  const removeDraftSource = useCallback((id: string) => {
    setDraftSources((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const createDraftChannel = useCallback((provider: CollaborationProvider) => {
    const draft = buildDraftChannel(provider);
    setEditingChannel(draft);
    setChannelError('');
    setChannelNotice('');
  }, []);

  const removeDraftChannel = useCallback((id: string) => {
    setDraftChannels((prev) => prev.filter((item) => item.id !== id));
    setEditingChannel((prev) => (prev?.id === id ? null : prev));
  }, []);

  const startEditChannel = useCallback((item: CollaborationChannelListItem) => {
    setEditingChannel({
      id: item.id,
      provider: item.provider,
      channel_code: item.channel_code,
      name: item.name,
      client_id: item.client_id || '',
      client_secret: '',
      robot_code: item.robot_code || '',
      is_default: Boolean(item.is_default),
      is_enabled: item.is_enabled !== false,
      extraText: item.extra && Object.keys(item.extra).length > 0 ? JSON.stringify(item.extra, null, 2) : '',
      isDraft: item.id.startsWith('draft-channel-'),
    });
    setChannelError('');
    setChannelNotice('');
  }, []);

  const saveEditingChannel = useCallback(async () => {
    if (!editingChannel) return;

    let parsedExtra: Record<string, unknown> = {};
    if (editingChannel.extraText.trim()) {
      try {
        const parsed = JSON.parse(editingChannel.extraText);
        parsedExtra = parsed && typeof parsed === 'object' ? parsed : {};
      } catch {
        setChannelError('扩展配置 JSON 格式无效，请检查后重试。');
        return;
      }
    }

    const payload = {
      provider: editingChannel.provider,
      channel_code: editingChannel.channel_code.trim() || 'default',
      name: editingChannel.name.trim() || collaborationProviderCard(editingChannel.provider).defaultName,
      client_id: editingChannel.client_id.trim(),
      client_secret: editingChannel.client_secret.trim(),
      robot_code: editingChannel.robot_code.trim(),
      is_default: editingChannel.is_default,
      is_enabled: editingChannel.is_enabled,
      extra: parsedExtra,
    };

    const applyLocalSave = (message: string) => {
      const localItem: CollaborationChannelListItem = {
        id: editingChannel.id,
        provider: payload.provider,
        channel_code: payload.channel_code,
        name: payload.name,
        client_id: payload.client_id,
        client_secret: payload.client_secret,
        robot_code: payload.robot_code,
        is_default: payload.is_default,
        is_enabled: payload.is_enabled,
        updated_at: new Date().toISOString(),
        extra: payload.extra,
      };
      setDraftChannels((prev) => {
        const next = prev.filter((item) => item.id !== localItem.id);
        return [localItem, ...next];
      });
      setEditingChannel(null);
      setChannelNotice(message);
      setChannelError('');
    };

    setSavingChannel(true);
    setChannelError('');

    try {
      const requestPath = editingChannel.isDraft
        ? '/api/collaboration-channels'
        : `/api/collaboration-channels/${editingChannel.id}`;
      const requestMethod = editingChannel.isDraft ? 'POST' : 'PUT';
      const response = await fetch(requestPath, {
        method: requestMethod,
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (response.status === 404 || response.status === 405 || response.status === 501) {
        setChannelApiAvailable(false);
        applyLocalSave('后端协作通道接口暂未接入，当前已保存为前端本地草稿。');
        return;
      }

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '保存协作通道配置失败'));
      }

      const saved = normalizeChannelConfig(data?.channel ?? data?.config ?? data?.item ?? data);
      if (saved) {
        setRemoteChannels((prev) => {
          const next = prev.filter((item) => item.id !== saved.id);
          return [saved, ...next];
        });
        setDraftChannels((prev) => prev.filter((item) => item.id !== editingChannel.id));
        setEditingChannel(null);
        setChannelNotice('协作通道配置已保存。');
        setChannelApiAvailable(true);
        return;
      }

      applyLocalSave('当前仅完成前端编辑 UI，保存结果暂存在浏览器会话中。');
    } catch (error) {
      setChannelError(error instanceof Error ? error.message : '保存协作通道配置失败');
    } finally {
      setSavingChannel(false);
    }
  }, [authHeaders, channelApiAvailable, editingChannel]);

  const launchAuthFlow = useCallback(
    async (platformCode: PlatformCode) => {
      if (!authToken) return;
      setLaunchingAuthPlatform(platformCode);
      try {
        const response = await fetch(`/api/platform-connections/${platformCode}/auth-sessions`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            return_path: window.location.pathname || '/',
          }),
        });
        const data: AuthSessionResponse = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String((data as { detail?: string }).detail || data?.message || '创建授权会话失败'));
        }
        if (!data?.auth_url) {
          throw new Error('后端未返回授权链接 auth_url');
        }
        window.location.assign(data.auth_url);
      } catch (error) {
        const message = error instanceof Error ? error.message : '创建授权会话失败';
        setPlatformError(message);
      } finally {
        setLaunchingAuthPlatform(null);
      }
    },
    [authHeaders, authToken],
  );

  const handleSelectPlatform = useCallback(
    async (platform: PlatformConnectionSummary) => {
      setSelectedPlatform(platform);
      setMode('platform');
      await fetchShops(platform.platform_code);
    },
    [fetchShops],
  );

  const handleBackToOverview = useCallback(() => {
    setMode('overview');
    setSelectedPlatform(null);
    setShops([]);
    setShopError('');
  }, []);

  const handleReauthorize = useCallback(
    async (shop: ShopConnection) => {
      if (!authToken) return;
      setActioningShopId(shop.id);
      try {
        const response = await fetch(`/api/shop-connections/${shop.id}/reauthorize`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            return_path: window.location.pathname || '/',
          }),
        });
        const data: AuthSessionResponse = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String((data as { detail?: string }).detail || data?.message || '发起重新授权失败'));
        }
        if (data.auth_url) {
          window.location.assign(data.auth_url);
          return;
        }
        if (selectedPlatform) {
          await fetchShops(selectedPlatform.platform_code);
        }
        await fetchPlatforms();
      } catch (error) {
        setShopError(error instanceof Error ? error.message : '发起重新授权失败');
      } finally {
        setActioningShopId(null);
      }
    },
    [authHeaders, authToken, fetchPlatforms, fetchShops, selectedPlatform],
  );

  const handleDisable = useCallback(
    async (shop: ShopConnection) => {
      if (!authToken) return;
      setActioningShopId(shop.id);
      try {
        const response = await fetch(`/api/shop-connections/${shop.id}/disable`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '停用授权失败'));
        }
        if (selectedPlatform) {
          await fetchShops(selectedPlatform.platform_code);
        }
        await fetchPlatforms();
      } catch (error) {
        setShopError(error instanceof Error ? error.message : '停用授权失败');
      } finally {
        setActioningShopId(null);
      }
    },
    [authHeaders, authToken, fetchPlatforms, fetchShops, selectedPlatform],
  );

  const platformSources = useMemo<DataSourceListItem[]>(
    () =>
      platforms.map((platform) => ({
        id: `platform-${platform.platform_code}`,
        source_kind: 'platform_oauth',
        provider_code: platform.platform_code,
        name: platform.platform_name,
        status: platform.authorized_shop_count > 0 ? 'active' : 'pending',
        execution_mode: 'deterministic',
        updated_at: platform.last_sync_at ?? null,
        metadata: {
          authorized_shop_count: platform.authorized_shop_count,
          error_shop_count: platform.error_shop_count,
        },
      })),
    [platforms],
  );

  const mergedSources = useMemo<DataSourceListItem[]>(() => {
    const map = new Map<string, DataSourceListItem>();
    remoteSources.forEach((item) => map.set(item.id, item));
    platformSources.forEach((item) => {
      if (!map.has(item.id)) map.set(item.id, item);
    });
    draftSources.forEach((item) => {
      map.set(item.id, {
        id: item.id,
        source_kind: item.source_kind,
        provider_code: item.provider_code,
        name: item.name,
        status: item.status,
        execution_mode: item.execution_mode,
        updated_at: item.updated_at,
      });
    });
    return Array.from(map.values());
  }, [draftSources, platformSources, remoteSources]);

  const mergedChannels = useMemo<CollaborationChannelListItem[]>(() => {
    const map = new Map<string, CollaborationChannelListItem>();
    remoteChannels.forEach((item) => map.set(item.id, item));
    draftChannels.forEach((item) => map.set(item.id, item));
    return Array.from(map.values()).sort((left, right) => {
      const leftDefault = left.is_default ? 1 : 0;
      const rightDefault = right.is_default ? 1 : 0;
      if (leftDefault !== rightDefault) return rightDefault - leftDefault;
      return String(right.updated_at || '').localeCompare(String(left.updated_at || ''));
    });
  }, [draftChannels, remoteChannels]);

  const draftSourceIdSet = useMemo(() => new Set(draftSources.map((item) => item.id)), [draftSources]);
  const draftChannelIdSet = useMemo(() => new Set(draftChannels.map((item) => item.id)), [draftChannels]);
  const selectedSourceCard = useMemo(
    () => SOURCE_TYPE_CARDS.find((item) => item.source_kind === selectedSourceKind) ?? SOURCE_TYPE_CARDS[0],
    [selectedSourceKind],
  );
  const selectedChannelCard = useMemo(
    () => collaborationProviderCard(selectedCollaborationProvider),
    [selectedCollaborationProvider],
  );
  const selectedKindSources = useMemo(
    () => mergedSources.filter((item) => item.source_kind === selectedSourceKind),
    [mergedSources, selectedSourceKind],
  );
  const selectedProviderChannels = useMemo(
    () => mergedChannels.filter((item) => item.provider === selectedCollaborationProvider),
    [mergedChannels, selectedCollaborationProvider],
  );
  const selectedSource = useMemo(
    () => selectedKindSources.find((item) => item.id === selectedSourceId) ?? null,
    [selectedKindSources, selectedSourceId],
  );
  const primeSourceForm = useCallback((source: DataSourceListItem) => {
    setSourceForms((prev) => {
      if (prev[source.id]) return prev;
      return {
        ...prev,
        [source.id]: createEditableSourceConfig(source),
      };
    });
  }, []);

  const resetSourceForm = useCallback((source: DataSourceListItem) => {
    setSourceForms((prev) => ({
      ...prev,
      [source.id]: createEditableSourceConfig(source),
    }));
  }, []);

  const updateSourceForm = useCallback((sourceId: string, updater: (current: EditableSourceConfig) => EditableSourceConfig) => {
    setSourceForms((prev) => {
      const current = prev[sourceId];
      if (!current) return prev;
      return {
        ...prev,
        [sourceId]: updater(current),
      };
    });
  }, []);

  const updateApiKeyValueRow = useCallback(
    (
      sourceId: string,
      field: 'auth_request_headers' | 'auth_request_params',
      rowId: string,
      patch: Partial<EditableKeyValueRow>,
    ) => {
      updateSourceForm(sourceId, (current) => ({
        ...current,
        api: {
          ...current.api,
          [field]: current.api[field].map((item) => (item.id === rowId ? { ...item, ...patch } : item)),
        },
      }));
    },
    [updateSourceForm],
  );

  const addApiKeyValueRow = useCallback(
    (sourceId: string, field: 'auth_request_headers' | 'auth_request_params') => {
      updateSourceForm(sourceId, (current) => ({
        ...current,
        api: {
          ...current.api,
          [field]: [...current.api[field], createEditableKeyValueRow()],
        },
      }));
    },
    [updateSourceForm],
  );

  const removeApiKeyValueRow = useCallback(
    (sourceId: string, field: 'auth_request_headers' | 'auth_request_params', rowId: string) => {
      updateSourceForm(sourceId, (current) => {
        const nextRows = current.api[field].filter((item) => item.id !== rowId);
        return {
          ...current,
          api: {
            ...current.api,
            [field]: nextRows.length > 0 ? nextRows : [createEditableKeyValueRow()],
          },
        };
      });
    },
    [updateSourceForm],
  );

  const isSourceConfigExpanded = useCallback(
    (sourceId: string) => expandedSourceConfigIds.includes(sourceId),
    [expandedSourceConfigIds],
  );

  const toggleSourceConfig = useCallback((sourceId: string) => {
    setExpandedSourceConfigIds((prev) =>
      prev.includes(sourceId) ? prev.filter((item) => item !== sourceId) : [...prev, sourceId],
    );
  }, []);

  useEffect(() => {
    if (!selectedSource) return;
    primeSourceForm(selectedSource);
  }, [primeSourceForm, selectedSource]);

  useEffect(() => {
    if (!selectedSource) return;
    if (!draftSourceIdSet.has(selectedSource.id)) return;
    setExpandedSourceConfigIds((prev) =>
      prev.includes(selectedSource.id) ? prev : [...prev, selectedSource.id],
    );
  }, [draftSourceIdSet, selectedSource]);

  const primeSourceDetail = useCallback((source: DataSourceListItem) => {
    setSourceDetails((prev) => {
      if (prev[source.id]) return prev;
      return {
        ...prev,
        [source.id]: {
          ...createDefaultSourceDetail(),
          datasets: source.datasets ?? [],
          events: source.recent_events ?? [],
        },
      };
    });
  }, []);

  const handleSelectSource = useCallback(
    (source: DataSourceListItem) => {
      setSelectedSourceId(source.id);
      setSourceActionError('');
      setSourceActionNotice('');
      setDatasetActionError('');
      setDatasetActionNotice('');
      primeSourceForm(source);
      primeSourceDetail(source);
      void hydrateSourceDetail(source.id);
    },
    [hydrateSourceDetail, primeSourceDetail, primeSourceForm],
  );

  const openDatabaseSourceDetail = useCallback(
    (source: DataSourceListItem) => {
      handleSelectSource(source);
      setDatabaseDetailSourceId(source.id);
    },
    [handleSelectSource],
  );

  useEffect(() => {
    if (selectedConnectionView !== 'data_sources') return;
    if (!['database', 'api', 'file'].includes(selectedSourceKind)) return;
    if (selectedKindSources.length === 0) {
      if (selectedSourceId !== null) setSelectedSourceId(null);
      return;
    }
    const hasActiveSelection = selectedSourceId
      ? selectedKindSources.some((item) => item.id === selectedSourceId)
      : false;
    if (hasActiveSelection) return;
    const next = selectedKindSources[0];
    setSelectedSourceId(next.id);
    primeSourceForm(next);
    primeSourceDetail(next);
    void hydrateSourceDetail(next.id);
  }, [
    hydrateSourceDetail,
    primeSourceDetail,
    primeSourceForm,
    selectedConnectionView,
    selectedKindSources,
    selectedSourceId,
    selectedSourceKind,
  ]);

  useEffect(() => {
    if (selectedConnectionView !== 'data_sources') return;
    if (!selectedSource) return;
    if (!['database', 'api', 'file'].includes(selectedSource.source_kind)) return;
    if (draftSourceIdSet.has(selectedSource.id)) return;
    void fetchAvailableDatasets(selectedSource.id);
  }, [draftSourceIdSet, fetchAvailableDatasets, selectedConnectionView, selectedSource]);

  useEffect(() => {
    if (selectedConnectionView !== 'data_sources') return;
    if (!selectedSource) return;
    if (!['database', 'api', 'file'].includes(selectedSource.source_kind)) return;
    if (!canManagePhysicalCatalogForSource(selectedSource)) return;
    const currentTab = datasetViewTabsBySource[selectedSource.id] ?? 'available';
    if (currentTab !== 'physical') return;
    if (draftSourceIdSet.has(selectedSource.id)) return;
    const filter = physicalCatalogFiltersBySource[selectedSource.id] ?? createDefaultPhysicalCatalogFilterState();
    void fetchPhysicalCatalogDatasets(selectedSource.id, filter);
  }, [
    canManagePhysicalCatalogForSource,
    datasetViewTabsBySource,
    draftSourceIdSet,
    fetchPhysicalCatalogDatasets,
    physicalCatalogFiltersBySource,
    selectedConnectionView,
    selectedSource,
  ]);

  useEffect(() => {
    if (selectedConnectionView !== 'data_sources' || selectedSourceKind !== 'database') return;
    if (!databaseDetailSourceId) return;
    if (selectedKindSources.some((item) => item.id === databaseDetailSourceId)) return;
    setDatabaseDetailSourceId(null);
  }, [databaseDetailSourceId, selectedConnectionView, selectedKindSources, selectedSourceKind]);

  useEffect(() => {
    if (selectedConnectionView !== 'data_sources') return;
    if (!selectedSource) return;
    if (!['database', 'api', 'file'].includes(selectedSource.source_kind)) return;
    if (!canManagePhysicalCatalogForSource(selectedSource)) return;
    const currentTab = datasetViewTabsBySource[selectedSource.id] ?? 'available';
    if (currentTab !== 'physical') return;
    const datasetId = physicalDetailDatasetBySource[selectedSource.id] ?? null;
    if (!datasetId) return;
    if (draftSourceIdSet.has(selectedSource.id)) return;
    void fetchPhysicalDatasetDetail(selectedSource.id, datasetId);
  }, [
    canManagePhysicalCatalogForSource,
    datasetViewTabsBySource,
    draftSourceIdSet,
    fetchPhysicalDatasetDetail,
    physicalDetailDatasetBySource,
    selectedConnectionView,
    selectedSource,
  ]);

  const updateApiDiscoveryForm = useCallback((sourceId: string, patch: Partial<ApiDiscoveryFormState>) => {
    setApiDiscoveryForms((prev) => ({
      ...prev,
      [sourceId]: {
        ...(prev[sourceId] ?? createDefaultApiDiscoveryForm()),
        ...patch,
      },
    }));
  }, []);

  const updateApiDiscoveryKeyValueRow = useCallback(
    (sourceId: string, rowId: string, patch: Partial<EditableKeyValueRow>) => {
      setApiDiscoveryForms((prev) => {
        const current = prev[sourceId] ?? createDefaultApiDiscoveryForm();
        return {
          ...prev,
          [sourceId]: {
            ...current,
            manualParams: current.manualParams.map((item) => (item.id === rowId ? { ...item, ...patch } : item)),
          },
        };
      });
    },
    [],
  );

  const addApiDiscoveryKeyValueRow = useCallback((sourceId: string) => {
    setApiDiscoveryForms((prev) => {
      const current = prev[sourceId] ?? createDefaultApiDiscoveryForm();
      return {
        ...prev,
        [sourceId]: {
          ...current,
          manualParams: [...current.manualParams, createEditableKeyValueRow()],
        },
      };
    });
  }, []);

  const removeApiDiscoveryKeyValueRow = useCallback((sourceId: string, rowId: string) => {
    setApiDiscoveryForms((prev) => {
      const current = prev[sourceId] ?? createDefaultApiDiscoveryForm();
      const nextRows = current.manualParams.filter((item) => item.id !== rowId);
      return {
        ...prev,
        [sourceId]: {
          ...current,
          manualParams: nextRows.length > 0 ? nextRows : [createEditableKeyValueRow()],
        },
      };
    });
  }, []);

  const handleSaveSource = useCallback(
    async (source: DataSourceListItem) => {
      if (!authToken) return;

      const form = sourceForms[source.id] ?? createEditableSourceConfig(source);

      let connectionConfig: Record<string, unknown> = {};
      let authConfig: Record<string, unknown> = {};
      let payload: Record<string, unknown> = {};
      try {
        ({ connectionConfig, authConfig, payload } = buildSourceSavePayload(source, form));
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '连接配置格式不正确');
        setSourceActionNotice('');
        return;
      }
      const sourceName = asString(payload.name) ?? source.name;
      const sourceDescription = asString(payload.description) ?? source.description ?? '';

      const buildLocalSource = (): DataSourceListItem => {
        const localConnectionConfig =
          source.source_kind === 'database'
            ? ({
                database: {
                  ...(connectionConfig as DataSourceDatabaseConfig),
                  password: String(authConfig.password || ''),
                },
              } as DataSourceListItem['connection_config'])
            : source.source_kind === 'api'
            ? ({
                api: {
                  ...(connectionConfig as DataSourceApiConfig),
                  auth_request_headers:
                    (authConfig.auth_request_headers as Record<string, string> | undefined) ?? undefined,
                  auth_request_params:
                    (authConfig.auth_request_params as Record<string, string> | undefined) ?? undefined,
                  auth_request_json_payload:
                    (authConfig.auth_request_json_payload as Record<string, unknown> | undefined) ?? undefined,
                },
              } as DataSourceListItem['connection_config'])
            : source.connection_config;

        return {
          ...source,
          name: sourceName,
          description: sourceDescription,
          updated_at: new Date().toISOString(),
          connection_config: localConnectionConfig,
        };
      };

      const applyLocalSave = (message: string) => {
        const localSource = buildLocalSource();
        if (draftSourceIdSet.has(source.id)) {
          setDraftSources((prev) =>
            prev.map((item) =>
              item.id === source.id
                ? {
                    ...item,
                    name: sourceName,
                    updated_at: localSource.updated_at || new Date().toISOString(),
                  }
                : item,
            ),
          );
        } else {
          setRemoteSources((prev) => prev.map((item) => (item.id === source.id ? localSource : item)));
        }
        resetSourceForm(localSource);
        setSourceActionNotice(message);
        setSourceActionError('');
      };

      setSourceActionBusy(`save:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');

      try {
        if (draftSourceIdSet.has(source.id)) {
          const response = await fetch('/api/data-sources', {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({
              ...payload,
              source_kind: source.source_kind,
              domain_type: 'internal_business',
              execution_mode: source.execution_mode || 'deterministic',
            }),
          });

          if (response.status === 404 || response.status === 405 || response.status === 501) {
            applyLocalSave('后端数据源保存接口暂未接入，当前已保存为前端本地草稿。');
            return;
          }

          const data = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(String(data?.detail || data?.message || '创建数据源失败'));
          }

          const saved = normalizeSourceItem(data?.source ?? data?.item ?? data);
          if (!saved) {
            throw new Error('后端返回的数据源结构无效');
          }

          setDraftSources((prev) => prev.filter((item) => item.id !== source.id));
          setRemoteSources((prev) => [saved, ...prev.filter((item) => item.id !== saved.id)]);
          setSelectedSourceId(saved.id);
          if (saved.source_kind === 'database') {
            setDatabaseDetailSourceId(saved.id);
          }
          resetSourceForm(saved);
          primeSourceDetail(saved);
          setSourceActionNotice(String(data?.message || '数据源配置已创建'));
          return;
        }

        const response = await fetch(`/api/data-sources/${source.id}`, {
          method: 'PATCH',
          headers: authHeaders,
          body: JSON.stringify(payload),
        });

        if (response.status === 404 || response.status === 405 || response.status === 501) {
          applyLocalSave('后端数据源更新接口暂未接入，当前修改仅保存在前端会话中。');
          return;
        }

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '更新数据源失败'));
        }

        const saved = normalizeSourceItem(data?.source ?? data?.item ?? data);
        if (!saved) {
          throw new Error('后端返回的数据源结构无效');
        }

        setRemoteSources((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
        resetSourceForm(saved);
        setSourceActionNotice(String(data?.message || '连接配置已保存'));
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '保存连接配置失败');
      } finally {
        setSourceActionBusy(null);
      }
    },
    [authHeaders, authToken, draftSourceIdSet, primeSourceDetail, resetSourceForm, sourceForms],
  );

  const handleTestSource = useCallback(
    async (source: DataSourceListItem) => {
      if (!authToken || draftSourceIdSet.has(source.id)) return;
      const form = sourceForms[source.id] ?? createEditableSourceConfig(source);
      let connectionConfig: Record<string, unknown> = {};
      let authConfig: Record<string, unknown> = {};
      try {
        ({ connectionConfig, authConfig } = buildSourceConnectionConfigs(source, form));
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '连接配置格式不正确');
        setSourceActionNotice('');
        return;
      }
      setSourceActionBusy(`test:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${source.id}/test`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            ...(Object.keys(connectionConfig).length > 0 ? { connection_config: connectionConfig } : {}),
            ...(Object.keys(authConfig).length > 0 ? { auth_config: authConfig } : {}),
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || data?.result?.message || '测试连接失败'));
        }
        setSourceActionNotice(String(data?.message || data?.result?.message || '连接测试通过'));
        await fetchRemoteSources();
        await hydrateSourceDetail(source.id);
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '测试连接失败');
      } finally {
        setSourceActionBusy(null);
      }
    },
    [authHeaders, authToken, draftSourceIdSet, fetchRemoteSources, hydrateSourceDetail],
  );

  const handleDiscoverSource = useCallback(
    async (source: DataSourceListItem, options: DiscoverSourceOptions = {}) => {
      if (!authToken || draftSourceIdSet.has(source.id)) return false;
      const form = sourceForms[source.id] ?? createEditableSourceConfig(source);
      let connectionConfig: Record<string, unknown> = {};
      let authConfig: Record<string, unknown> = {};
      try {
        ({ connectionConfig, authConfig } = buildSourceConnectionConfigs(source, form));
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '连接配置格式不正确');
        setSourceActionNotice('');
        return false;
      }
      setSourceActionBusy(`discover:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const requestedLimit = Math.max(1, Math.min(options.limit ?? 500, 1000));
        const response = await fetch(`/api/data-sources/${source.id}/discover`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            persist: true,
            limit: requestedLimit,
            ...(typeof options.offset === 'number' ? { offset: Math.max(0, options.offset) } : {}),
            schema_whitelist: [],
            ...(options.targetResourceKeys?.length ? { target_resource_keys: options.targetResourceKeys } : {}),
            ...(Object.keys(connectionConfig).length > 0 ? { connection_config: connectionConfig } : {}),
            ...(Object.keys(authConfig).length > 0 ? { auth_config: authConfig } : {}),
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '重新发现数据集失败'));
        }

        const rows = Array.isArray(data?.datasets)
          ? data.datasets
          : Array.isArray(data?.data?.datasets)
          ? data.data.datasets
          : [];
        const datasets = rows
          .map((item: unknown) => normalizeDataset(item))
          .filter(Boolean) as DataSourceDatasetSummary[];
        const discoverSummary = normalizeDiscoverSummary(data?.discover_summary ?? data?.scan_summary);
        updateSourceDetail(source.id, (current) => ({
          ...current,
          datasets: datasets.length > 0 ? datasets : current.datasets,
          datasetsApiAvailable: true,
          datasetsError: '',
        }));
        if (discoverSummary) {
          setRemoteSources((prev) =>
            prev.map((item) =>
              item.id === source.id
                ? {
                    ...item,
                    discover_summary: discoverSummary,
                  }
                : item,
            ),
          );
        }
        if (discoverSummary?.scan_mode === 'targeted') {
          setSourceActionNotice(
            `已更新 ${discoverSummary.matched_count ?? datasets.length} / ${discoverSummary.requested_count ?? options.targetResourceKeys?.length ?? datasets.length} 个指定表`,
          );
        } else if ((discoverSummary?.total_count ?? 0) > 0) {
          setSourceActionNotice(
            `本次扫描 ${discoverSummary?.scanned_count ?? datasets.length} / ${discoverSummary?.total_count} 个对象${discoverSummary?.has_more ? '，可继续扫描下一批' : ''}`,
          );
        } else {
          setSourceActionNotice(String(data?.message || '数据集目录已刷新'));
        }
        await fetchRemoteSources();
        await hydrateSourceDetail(source.id);
        const availableState = availableDatasetPagesBySource[source.id] ?? createDefaultDatasetListPageState(100);
        await fetchAvailableDatasets(source.id, availableState.page, availableState.pageSize);
        if (canManagePhysicalCatalogForSource(source)) {
          const physicalFilter =
            physicalCatalogFiltersBySource[source.id] ?? createDefaultPhysicalCatalogFilterState();
          await fetchPhysicalCatalogDatasets(source.id, physicalFilter);
        }
        return true;
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '重新发现数据集失败');
        return false;
      } finally {
        setSourceActionBusy(null);
      }
    },
    [
      authHeaders,
      authToken,
      availableDatasetPagesBySource,
      canManagePhysicalCatalogForSource,
      draftSourceIdSet,
      fetchAvailableDatasets,
      fetchPhysicalCatalogDatasets,
      fetchRemoteSources,
      hydrateSourceDetail,
      physicalCatalogFiltersBySource,
      updateSourceDetail,
    ],
  );

  const handleDeleteSource = useCallback(
    async (source: DataSourceListItem) => {
      if (draftSourceIdSet.has(source.id)) {
        setDraftSources((prev) => prev.filter((item) => item.id !== source.id));
        setSourceDetails((prev) => {
          const next = { ...prev };
          delete next[source.id];
          return next;
        });
        if (selectedSourceId === source.id) {
          setSelectedSourceId(null);
        }
        if (databaseDetailSourceId === source.id) {
          setDatabaseDetailSourceId(null);
        }
        setSourceActionNotice('本地草稿已删除');
        return;
      }
      if (!authToken) return;
      const confirmed = window.confirm(`确认删除“${source.name || '未命名连接'}”？此操作不可恢复。`);
      if (!confirmed) return;

      setSourceActionBusy(`delete:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${source.id}`, {
          method: 'DELETE',
          headers: authHeaders,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '删除连接失败'));
        }
        setRemoteSources((prev) => prev.filter((item) => item.id !== source.id));
        setSourceDetails((prev) => {
          const next = { ...prev };
          delete next[source.id];
          return next;
        });
        if (selectedSourceId === source.id) {
          setSelectedSourceId(null);
        }
        if (databaseDetailSourceId === source.id) {
          setDatabaseDetailSourceId(null);
        }
        setSourceActionNotice(String(data?.message || '连接已删除'));
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '删除连接失败');
      } finally {
        setSourceActionBusy(null);
      }
    },
    [authHeaders, authToken, databaseDetailSourceId, draftSourceIdSet, selectedSourceId],
  );

  const handleSubmitTargetedDiscover = useCallback(async () => {
    if (!targetedDiscoverDialog) return;
    const source = mergedSources.find((item) => item.id === targetedDiscoverDialog.sourceId);
    if (!source) return;
    const targetResourceKeys = parseTargetResourceKeys(targetedDiscoverDialog.resourceKeysText);
    if (targetResourceKeys.length === 0) {
      setSourceActionError('请至少填写一个表名，支持多行或逗号分隔。');
      setSourceActionNotice('');
      return;
    }
    const success = await handleDiscoverSource(source, {
      targetResourceKeys,
      limit: targetResourceKeys.length,
    });
    if (success) {
      setTargetedDiscoverDialog(null);
    }
  }, [handleDiscoverSource, mergedSources, targetedDiscoverDialog]);

  const handleContinueDiscover = useCallback(
    async (source: DataSourceListItem) => {
      const summary = source.discover_summary;
      if (!summary?.has_more || summary.next_offset === null || summary.next_offset === undefined) return;
      await handleDiscoverSource(source, {
        offset: summary.next_offset,
        limit: summary.requested_limit ?? 500,
      });
    },
    [handleDiscoverSource],
  );

  const handleGenerateApiDatasetsFromDocument = useCallback(
    async (source: DataSourceListItem) => {
      if (!authToken || draftSourceIdSet.has(source.id)) return;
      const form = apiDiscoveryForms[source.id] ?? createDefaultApiDiscoveryForm();
      const documentInputMode = form.documentInputMode;
      const documentUrl = form.documentUrl.trim();
      const documentContent = form.documentContent.trim();
      if (documentInputMode === 'url' && !documentUrl) {
        setSourceActionError('请提供文档地址。');
        setSourceActionNotice('');
        return;
      }
      if (documentInputMode === 'content' && !documentContent) {
        setSourceActionError('请先粘贴文档内容。');
        setSourceActionNotice('');
        return;
      }

      setSourceActionBusy(`document:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${source.id}/discover`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            persist: true,
            discover_mode: 'document',
            document_input_mode: documentInputMode,
            document_url: documentInputMode === 'url' ? documentUrl : undefined,
            document_content: documentInputMode === 'content' ? documentContent : undefined,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '根据文档生成数据集失败'));
        }
        const rows = Array.isArray(data?.datasets)
          ? data.datasets
          : Array.isArray(data?.data?.datasets)
          ? data.data.datasets
          : [];
        const datasets = rows
          .map((item: unknown) => normalizeDataset(item))
          .filter(Boolean) as DataSourceDatasetSummary[];
        updateSourceDetail(source.id, (current) => ({
          ...current,
          datasets: datasets.length > 0 ? datasets : current.datasets,
          datasetsApiAvailable: true,
          datasetsError: '',
        }));
        setSourceActionNotice(String(data?.message || '文档已解析并生成 API 数据集'));
        await fetchRemoteSources();
        await fetchSourceEvents(source.id);
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '根据文档生成数据集失败');
      } finally {
        setSourceActionBusy(null);
      }
    },
    [apiDiscoveryForms, authHeaders, authToken, draftSourceIdSet, fetchRemoteSources, fetchSourceEvents, updateSourceDetail],
  );

  const handleApplyManualEndpoint = useCallback(
    async (source: DataSourceListItem) => {
      if (!authToken || draftSourceIdSet.has(source.id)) return;
      const form = apiDiscoveryForms[source.id] ?? createDefaultApiDiscoveryForm();
      const manualApiPath = form.manualApiPath.trim();
      if (!manualApiPath) {
        setSourceActionError('请先填写 API 地址。');
        setSourceActionNotice('');
        return;
      }

      let requestParams: Record<string, unknown> | undefined;
      try {
        requestParams =
          form.manualParamType === 'json'
            ? parseJsonObjectText(form.manualJsonText, '请求参数')
            : keyValueRowsToRecord(form.manualParams);
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '请求参数格式不正确');
        setSourceActionNotice('');
        return;
      }

      setSourceActionBusy(`manual:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${source.id}/discover`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            persist: true,
            discover_mode: 'manual',
            manual_endpoint: {
              dataset_name: form.manualDatasetName.trim(),
              path: manualApiPath,
              method: form.manualMethod,
              request_param_type: form.manualParamType,
              request_params: requestParams ?? {},
            },
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '手工 endpoint 生成数据集失败'));
        }
        const rows = Array.isArray(data?.datasets)
          ? data.datasets
          : Array.isArray(data?.data?.datasets)
          ? data.data.datasets
          : [];
        const datasets = rows
          .map((item: unknown) => normalizeDataset(item))
          .filter(Boolean) as DataSourceDatasetSummary[];
        updateSourceDetail(source.id, (current) => ({
          ...current,
          datasets: datasets.length > 0 ? datasets : current.datasets,
          datasetsApiAvailable: true,
          datasetsError: '',
        }));
        setSourceActionNotice(String(data?.message || '手工 endpoint 已生成 API 数据集'));
        await fetchRemoteSources();
        await fetchSourceEvents(source.id);
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '手工 endpoint 生成数据集失败');
      } finally {
        setSourceActionBusy(null);
      }
    },
    [apiDiscoveryForms, authHeaders, authToken, draftSourceIdSet, fetchRemoteSources, fetchSourceEvents, updateSourceDetail],
  );

  const handleRunApiDiscovery = useCallback(
    async (source: DataSourceListItem) => {
      const form = apiDiscoveryForms[source.id] ?? createDefaultApiDiscoveryForm();
      if (form.discoveryMode === 'manual') {
        await handleApplyManualEndpoint(source);
        return;
      }
      await handleGenerateApiDatasetsFromDocument(source);
    },
    [apiDiscoveryForms, handleApplyManualEndpoint, handleGenerateApiDatasetsFromDocument],
  );

  const updateDatasetInState = useCallback(
    (
      sourceId: string,
      datasetId: string,
      datasetCode: string,
      updater: (dataset: DataSourceDatasetSummary) => DataSourceDatasetSummary,
    ) => {
      const applyPatch = (dataset: DataSourceDatasetSummary): DataSourceDatasetSummary => {
        const matched = dataset.id === datasetId || (datasetCode && dataset.dataset_code === datasetCode);
        return matched ? updater(dataset) : dataset;
      };

      updateSourceDetail(sourceId, (current) => ({
        ...current,
        datasets: current.datasets.map((dataset) => applyPatch(dataset)),
      }));

      setRemoteSources((prev) =>
        prev.map((source) => {
          if (source.id !== sourceId || !Array.isArray(source.datasets)) return source;
          return {
            ...source,
            datasets: source.datasets.map((dataset) => applyPatch(dataset)),
          };
        }),
      );

      setAvailableDatasetPagesBySource((prev) => {
        const current = prev[sourceId];
        if (!current) return prev;
        return {
          ...prev,
          [sourceId]: {
            ...current,
            rows: current.rows.map((dataset) => applyPatch(dataset)),
          },
        };
      });

      setPhysicalDatasetPagesBySource((prev) => {
        const current = prev[sourceId];
        if (!current) return prev;
        return {
          ...prev,
          [sourceId]: {
            ...current,
            rows: current.rows.map((dataset) => applyPatch(dataset)),
          },
        };
      });

      setPhysicalDatasetDetailBySource((prev) => {
        const current = prev[sourceId];
        if (!current?.dataset) return prev;
        const shouldPatch = current.dataset.id === datasetId || (datasetCode && current.dataset.dataset_code === datasetCode);
        if (!shouldPatch) return prev;
        return {
          ...prev,
          [sourceId]: {
            ...current,
            dataset: applyPatch(current.dataset),
          },
        };
      });
    },
    [updateSourceDetail],
  );

  const closeEditingDatasetSemantic = useCallback(() => {
    setEditingDatasetSemantic(null);
    setDatasetSemanticError('');
    setDatasetSemanticNotice('');
    setRefreshingDatasetSemantic(false);
  }, []);

  const refreshDatasetSemanticSuggestions = useCallback(
    async (source: Pick<DataSourceListItem, 'id' | 'name'>, dataset: DataSourceDatasetSummary) => {
      setDatasetSemanticError('');
      setDatasetSemanticNotice('');
      if (!authToken || draftSourceIdSet.has(source.id)) {
        setDatasetSemanticNotice('当前环境未连接后端语义接口，已展示现有治理信息。');
        return null;
      }

      setRefreshingDatasetSemantic(true);
      try {
        const response = await fetch(
          `/api/data-sources/${source.id}/datasets/${encodeURIComponent(dataset.id)}/semantic-profile`,
          {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({
              dataset_code: dataset.dataset_code,
              resource_key: dataset.resource_key || dataset.dataset_code,
              sample_limit: 10,
            }),
          },
        );
        if (response.status === 404 || response.status === 405 || response.status === 501) {
          setDatasetSemanticNotice('当前环境尚未接入语义建议刷新，已展示现有治理信息。');
          return null;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '刷新语义建议失败'));
        }
        const savedDataset = normalizeDataset(data?.dataset ?? data?.item ?? data?.data?.dataset);
        if (savedDataset) {
          updateDatasetInState(source.id, dataset.id, dataset.dataset_code, () => savedDataset);
          setEditingDatasetSemantic((prev) =>
            prev && prev.sourceId === source.id && prev.datasetId === dataset.id
              ? buildEditableDatasetSemanticState(source, savedDataset)
              : prev,
          );
          setDatasetSemanticNotice(String(data?.message || '已刷新语义建议，请确认后发布。'));
          return savedDataset;
        }
        return null;
      } catch (error) {
        setDatasetSemanticError(error instanceof Error ? error.message : '刷新语义建议失败');
        return null;
      } finally {
        setRefreshingDatasetSemantic(false);
      }
    },
    [authHeaders, authToken, draftSourceIdSet, updateDatasetInState],
  );

  const startEditDatasetSemantic = useCallback(
    async (source: DataSourceListItem, dataset: DataSourceDatasetSummary) => {
      setDatasetSemanticError('');
      setDatasetSemanticNotice('');
      let nextDataset = dataset;
      setEditingDatasetSemantic(buildEditableDatasetSemanticState(source, nextDataset));

      if (authToken && !draftSourceIdSet.has(source.id)) {
        try {
          const detailedDataset = await requestDatasetDetail(source.id, dataset.id);
          if (detailedDataset) {
            nextDataset = detailedDataset;
            updateDatasetInState(source.id, dataset.id, dataset.dataset_code, () => detailedDataset);
            setEditingDatasetSemantic(buildEditableDatasetSemanticState(source, detailedDataset));
          }
        } catch (error) {
          setDatasetSemanticError(error instanceof Error ? error.message : '加载目录详情失败');
        }
      }

      if (hasDatasetSemanticCache(nextDataset)) {
        return;
      }
      await refreshDatasetSemanticSuggestions(source, nextDataset);
    },
    [authToken, draftSourceIdSet, refreshDatasetSemanticSuggestions, requestDatasetDetail, updateDatasetInState],
  );

  const openDatasetCollectionDetail = useCallback(
    async (source: DataSourceListItem, dataset: DataSourceDatasetSummary) => {
      const baseState: DatasetCollectionDetailDialogState = {
        sourceId: source.id,
        sourceName: source.name || source.id,
        datasetId: dataset.id,
        datasetName: dataset.business_name || dataset.dataset_name || dataset.dataset_code,
        resourceKey: dataset.resource_key || dataset.dataset_code,
        loading: true,
        error: '',
        actionError: '',
        lastLoadedAt: '',
        detail: null,
      };
      setCollectionDetailDialog(baseState);
      if (!authToken || draftSourceIdSet.has(source.id)) {
        setCollectionDetailDialog({
          ...baseState,
          loading: false,
          error: '当前环境未连接后端采集详情接口。',
        });
        return;
      }
      try {
        const params = new URLSearchParams({
          resource_key: dataset.resource_key || dataset.dataset_code,
          limit: '10',
          sample_limit: '10',
        });
        const response = await fetch(
          `/api/data-sources/${source.id}/datasets/${encodeURIComponent(dataset.id)}/collection-detail?${params.toString()}`,
          { headers: authHeaders },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '获取采集详情失败'));
        }
        setCollectionDetailDialog({
          ...baseState,
          loading: false,
          detail: asRecord(data) ?? {},
          lastLoadedAt: new Date().toISOString(),
        });
      } catch (error) {
        setCollectionDetailDialog({
          ...baseState,
          loading: false,
          error: error instanceof Error ? error.message : '获取采集详情失败',
        });
      }
    },
    [authHeaders, authToken, draftSourceIdSet],
  );

  const retryCollectionDetailDataset = useCallback(async () => {
    if (!collectionDetailDialog || !authToken || draftSourceIdSet.has(collectionDetailDialog.sourceId)) return;
    const source = remoteSources.find((item) => item.id === collectionDetailDialog.sourceId);
    const dataset = source?.datasets?.find((item) => item.id === collectionDetailDialog.datasetId) ?? {
      id: collectionDetailDialog.datasetId,
      dataset_code: collectionDetailDialog.resourceKey,
      dataset_name: collectionDetailDialog.datasetName,
      resource_key: collectionDetailDialog.resourceKey,
    } as DataSourceDatasetSummary;
    setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: true, actionError: '' } : prev));
    try {
      const response = await fetch(
        `/api/data-sources/${collectionDetailDialog.sourceId}/datasets/${encodeURIComponent(collectionDetailDialog.datasetId)}/collection`,
        {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          resource_key: collectionDetailDialog.resourceKey,
          params: {
            resource_key: collectionDetailDialog.resourceKey,
            query: { resource_key: collectionDetailDialog.resourceKey },
          },
        }),
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '立即采集失败'));
      }
      if (source) {
        await openDatasetCollectionDetail(source, dataset);
      } else {
        setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: false } : prev));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '立即采集失败';
      if (source) {
        await openDatasetCollectionDetail(source, dataset);
        setCollectionDetailDialog((prev) => (prev ? { ...prev, actionError: message } : prev));
      } else {
        setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: false, actionError: message } : prev));
      }
    }
  }, [authHeaders, authToken, collectionDetailDialog, draftSourceIdSet, openDatasetCollectionDetail, remoteSources]);

  const refreshCollectionDetailDialog = useCallback(async () => {
    if (!collectionDetailDialog || !authToken || draftSourceIdSet.has(collectionDetailDialog.sourceId)) return;
    const params = new URLSearchParams({
      resource_key: collectionDetailDialog.resourceKey,
      limit: '10',
      sample_limit: '10',
    });
    try {
      const response = await fetch(
        `/api/data-sources/${collectionDetailDialog.sourceId}/datasets/${encodeURIComponent(collectionDetailDialog.datasetId)}/collection-detail?${params.toString()}`,
        { headers: authHeaders },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '刷新采集详情失败'));
      }
      setCollectionDetailDialog((prev) =>
        prev
          ? {
              ...prev,
              loading: false,
              error: '',
              detail: asRecord(data) ?? {},
              lastLoadedAt: new Date().toISOString(),
            }
          : prev,
      );
    } catch (error) {
      setCollectionDetailDialog((prev) =>
        prev
          ? {
              ...prev,
              loading: false,
              actionError: error instanceof Error ? error.message : '刷新采集详情失败',
            }
          : prev,
      );
    }
  }, [authHeaders, authToken, collectionDetailDialog, draftSourceIdSet]);

  const collectionDetailHasRunningJob = useMemo(() => {
    const jobs = Array.isArray(collectionDetailDialog?.detail?.jobs) ? collectionDetailDialog.detail.jobs : [];
    return jobs.some((job) => {
      const status = asString(asRecord(job)?.status) || asString(asRecord(job)?.job_status) || '';
      return status.toLowerCase() === 'running';
    });
  }, [collectionDetailDialog?.detail]);

  useEffect(() => {
    if (!collectionDetailDialog || !collectionDetailHasRunningJob) return undefined;
    const timer = window.setInterval(() => {
      void refreshCollectionDetailDialog();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [collectionDetailDialog, collectionDetailHasRunningJob, refreshCollectionDetailDialog]);

  const refreshEditingDatasetSemantic = useCallback(async () => {
    if (!editingDatasetSemantic) return;
    await refreshDatasetSemanticSuggestions(
      {
        id: editingDatasetSemantic.sourceId,
        name: editingDatasetSemantic.sourceName,
      },
      {
        id: editingDatasetSemantic.datasetId,
        dataset_code: editingDatasetSemantic.datasetCode,
        dataset_name: editingDatasetSemantic.datasetName,
        resource_key: editingDatasetSemantic.resourceKey,
      },
    );
  }, [editingDatasetSemantic, refreshDatasetSemanticSuggestions]);

  const updateEditingDatasetSemanticField = useCallback(
    (
      rowId: string,
      patch: Partial<
        Pick<EditableDatasetSemanticFieldRow, 'displayName' | 'semanticType' | 'businessRole' | 'description'>
      >,
    ) => {
      setEditingDatasetSemantic((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          fieldRows: prev.fieldRows.map((row) => {
            if (row.id !== rowId) return row;
            const nextRow = {
              ...row,
              ...patch,
            };
            if (
              patch.displayName !== undefined ||
              patch.semanticType !== undefined ||
              patch.businessRole !== undefined ||
              patch.description !== undefined
            ) {
              nextRow.confirmedByUser = true;
              nextRow.pending = false;
            }
            return nextRow;
          }),
        };
      });
    },
    [],
  );

  const toggleEditingDatasetSemanticUniqueIdentifier = useCallback((rawName: string) => {
    const normalizedRawName = rawName.trim().toLowerCase();
    if (!normalizedRawName) return;
    setEditingDatasetSemantic((prev) => {
      if (!prev) return prev;
      const targetRow = prev.fieldRows.find((row) => row.rawName.trim().toLowerCase() === normalizedRawName);
      if (!targetRow) return prev;
      const isSelected = prev.uniqueIdentifierRawNames.some(
        (item) => item.trim().toLowerCase() === normalizedRawName,
      );
      const uniqueIdentifierRawNames = isSelected
        ? prev.uniqueIdentifierRawNames.filter((item) => item.trim().toLowerCase() !== normalizedRawName)
        : normalizeUniqueIdentifierRawNames([...prev.uniqueIdentifierRawNames, targetRow.rawName], prev.fieldRows);
      return {
        ...prev,
        uniqueIdentifierRawNames,
        fieldRows: prev.fieldRows.map((row) => {
          if (row.rawName !== targetRow.rawName || isSelected) return row;
          return {
            ...row,
            semanticType: row.semanticType.trim() || 'identifier',
            businessRole: 'identifier',
            confirmedByUser: true,
            pending: false,
          };
        }),
      };
    });
  }, []);

  const setEditingDatasetCollectionDateField = useCallback((rawName: string) => {
    setEditingDatasetSemantic((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        collectionDateField: rawName,
        fieldRows: prev.fieldRows.map((row) => {
          if (row.rawName !== rawName) return row;
          return {
            ...row,
            semanticType: row.semanticType.trim() || 'datetime',
            businessRole: row.businessRole.trim() || 'time_field',
            confirmedByUser: true,
            pending: false,
          };
        }),
      };
    });
  }, []);

  const acceptAllEditingDatasetSemanticSuggestions = useCallback(() => {
    setEditingDatasetSemantic((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        verifiedStatus: 'verified',
        fieldRows: prev.fieldRows.map((row) => ({
          ...row,
          displayName: row.displayName.trim() || row.rawName,
          confirmedByUser: true,
          pending: false,
        })),
      };
    });
  }, []);

  const saveEditingDatasetSemantic = useCallback(async () => {
    if (!editingDatasetSemantic) return;

    const businessName = editingDatasetSemantic.businessName.trim() || editingDatasetSemantic.datasetName;
    const businessObjectType = editingDatasetSemantic.businessObjectType.trim();
    const grain = editingDatasetSemantic.grain.trim();
    const verifiedStatus = editingDatasetSemantic.verifiedStatus || 'unverified';
    const keyFields = normalizeUniqueIdentifierRawNames(
      editingDatasetSemantic.uniqueIdentifierRawNames,
      editingDatasetSemantic.fieldRows,
    );
    const normalizedFields = editingDatasetSemantic.fieldRows
      .map((row) => {
        const rawName = row.rawName.trim();
        if (!rawName) return null;
        const displayName = row.displayName.trim() || rawName;
        return {
          raw_name: rawName,
          display_name: displayName,
          semantic_type: row.semanticType.trim() || 'unknown',
          business_role: row.businessRole.trim() || 'unknown',
          description: row.description.trim(),
          confidence:
            typeof row.confidence === 'number' && Number.isFinite(row.confidence)
              ? Math.max(0, Math.min(row.confidence, 1))
              : row.confirmedByUser
                ? 1
                : 0.5,
          sample_values: row.sampleValues.filter((item) => item.trim().length > 0),
          confirmed_by_user: row.confirmedByUser,
        };
      })
      .filter((row): row is NonNullable<typeof row> => Boolean(row));
    const fieldLabelMap = Object.fromEntries(normalizedFields.map((row) => [row.raw_name, row.display_name]));
    const pendingFieldNames = editingDatasetSemantic.fieldRows
      .filter((row) => row.pending && !row.confirmedByUser)
      .map((row) => row.rawName.trim())
      .filter(Boolean);
    const updatedAt = new Date().toISOString();
    const semanticProfile = {
      version: 1,
      status: 'manual_updated',
      business_name: businessName,
      business_object_type: businessObjectType,
      grain,
      verified_status: verifiedStatus,
      publish_status: 'published',
      field_label_map: fieldLabelMap,
      key_fields: keyFields,
      fields: normalizedFields,
      low_confidence_fields: pendingFieldNames,
      tech_name: editingDatasetSemantic.resourceKey || editingDatasetSemantic.datasetName,
      updated_at: updatedAt,
    };
    const collectionConfig = {
      mode: editingDatasetSemantic.collectionDateField.trim() ? 'date_field' : 'manual',
      date_field: editingDatasetSemantic.collectionDateField.trim(),
      schedule: {
        enabled: true,
        frequency: editingDatasetSemantic.collectionScheduleFrequency || 'daily',
        time: editingDatasetSemantic.collectionScheduleTime || '08:30',
      },
    };

    const applyLocalUpdate = (notice: string) => {
      updateDatasetInState(
        editingDatasetSemantic.sourceId,
        editingDatasetSemantic.datasetId,
        editingDatasetSemantic.datasetCode,
        (dataset) => ({
          ...dataset,
          business_name: businessName,
          business_object_type: businessObjectType,
          grain,
          verified_status: verifiedStatus,
          publish_status: 'published',
          key_fields: keyFields,
          field_label_map: fieldLabelMap,
          semantic_fields: normalizedFields,
          low_confidence_fields: pendingFieldNames,
          semantic_pending_count: pendingFieldNames.length,
          semantic_status: 'manual_updated',
          semantic_updated_at: updatedAt,
          collection_config: collectionConfig,
          meta: {
            ...(dataset.meta || {}),
            semantic_profile: semanticProfile,
            collection_config: collectionConfig,
          },
        }),
      );
      setEditingDatasetSemantic((prev) =>
        prev
          ? {
              ...prev,
              businessName,
              businessObjectType,
              grain,
              verifiedStatus,
              publishStatus: 'published',
              uniqueIdentifierRawNames: keyFields,
              collectionDateField: collectionConfig.date_field,
              collectionScheduleFrequency: collectionConfig.schedule.frequency,
              collectionScheduleTime: collectionConfig.schedule.time,
              fieldRows: prev.fieldRows.map((row) => ({
                ...row,
                displayName: fieldLabelMap[row.rawName] || row.displayName,
                confirmedByUser:
                  normalizedFields.find((field) => field.raw_name === row.rawName)?.confirmed_by_user ?? row.confirmedByUser,
                pending: pendingFieldNames.includes(row.rawName),
              })),
            }
          : prev,
      );
      setDatasetSemanticNotice(notice);
      setDatasetSemanticError('');
    };

    if (!authToken || draftSourceIdSet.has(editingDatasetSemantic.sourceId)) {
      applyLocalUpdate('当前环境未连接后端发布接口，已在本地会话标记为已发布。');
      return;
    }

    setSavingDatasetSemantic(true);
    setDatasetSemanticError('');
    setDatasetSemanticNotice('');
    try {
      const response = await fetch(
        `/api/data-sources/${editingDatasetSemantic.sourceId}/datasets/${encodeURIComponent(editingDatasetSemantic.datasetId)}/publish`,
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            dataset_code: editingDatasetSemantic.datasetCode,
            resource_key: editingDatasetSemantic.resourceKey || editingDatasetSemantic.datasetCode,
            business_name: businessName,
            business_description: '',
            key_fields: keyFields,
            field_label_map: fieldLabelMap,
            fields: normalizedFields,
            status: 'manual_updated',
            schema_name: editingDatasetSemantic.schemaName === '-' ? '' : editingDatasetSemantic.schemaName,
            object_name: editingDatasetSemantic.objectName === '-' ? '' : editingDatasetSemantic.objectName,
            object_type: editingDatasetSemantic.objectType,
            business_object_type: businessObjectType,
            grain,
            verified_status: verifiedStatus,
            collection_config: collectionConfig,
          }),
        },
      );

      if (response.status === 404 || response.status === 405 || response.status === 501) {
        applyLocalUpdate('当前环境未接入发布接口，已在本地会话标记为已发布。');
        return;
      }

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '保存发布信息失败'));
      }

      const savedDataset = normalizeDataset(data?.dataset ?? data?.item ?? data?.data?.dataset);
      if (savedDataset) {
        updateDatasetInState(
          editingDatasetSemantic.sourceId,
          editingDatasetSemantic.datasetId,
          editingDatasetSemantic.datasetCode,
          () => savedDataset,
        );
        setEditingDatasetSemantic((prev) =>
          prev &&
          prev.sourceId === editingDatasetSemantic.sourceId &&
          prev.datasetId === editingDatasetSemantic.datasetId
            ? buildEditableDatasetSemanticState(
                { id: editingDatasetSemantic.sourceId, name: editingDatasetSemantic.sourceName },
                savedDataset,
              )
            : prev,
        );
      }
      setDatasetSemanticNotice(
        String(
          data?.message ||
            (editingDatasetSemantic.publishStatus === 'published' ? '发布信息已更新' : '已发布为可用数据集'),
        ),
      );
      await Promise.all([
        hydrateSourceDetail(editingDatasetSemantic.sourceId),
        (async () => {
          const availableState =
            availableDatasetPagesBySource[editingDatasetSemantic.sourceId] ?? createDefaultDatasetListPageState(100);
          await fetchAvailableDatasets(
            editingDatasetSemantic.sourceId,
            availableState.page,
            availableState.pageSize,
          );
        })(),
        (async () => {
          const physicalFilter =
            physicalCatalogFiltersBySource[editingDatasetSemantic.sourceId] ?? createDefaultPhysicalCatalogFilterState();
          await fetchPhysicalCatalogDatasets(editingDatasetSemantic.sourceId, physicalFilter);
        })(),
      ]);
    } catch (error) {
      setDatasetSemanticError(error instanceof Error ? error.message : '保存发布信息失败');
    } finally {
      setSavingDatasetSemantic(false);
    }
  }, [
    authHeaders,
    authToken,
    availableDatasetPagesBySource,
    draftSourceIdSet,
    editingDatasetSemantic,
    fetchAvailableDatasets,
    fetchPhysicalCatalogDatasets,
    hydrateSourceDetail,
    physicalCatalogFiltersBySource,
    updateDatasetInState,
  ]);

  const unpublishEditingDatasetSemantic = useCallback(async () => {
    if (!editingDatasetSemantic || editingDatasetSemantic.publishStatus !== 'published') return;

    const applyLocalUpdate = (notice: string) => {
      updateDatasetInState(
        editingDatasetSemantic.sourceId,
        editingDatasetSemantic.datasetId,
        editingDatasetSemantic.datasetCode,
        (dataset) => ({
          ...dataset,
          publish_status: 'unpublished',
        }),
      );
      setEditingDatasetSemantic((prev) => (prev ? { ...prev, publishStatus: 'unpublished' } : prev));
      setDatasetSemanticNotice(notice);
      setDatasetSemanticError('');
    };

    if (!authToken || draftSourceIdSet.has(editingDatasetSemantic.sourceId)) {
      applyLocalUpdate('当前环境未连接后端取消发布接口，已在本地会话取消发布。');
      return;
    }

    setSavingDatasetSemantic(true);
    setDatasetSemanticError('');
    setDatasetSemanticNotice('');
    try {
      const response = await fetch(
        `/api/data-sources/${editingDatasetSemantic.sourceId}/datasets/${encodeURIComponent(editingDatasetSemantic.datasetId)}/unpublish`,
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            dataset_code: editingDatasetSemantic.datasetCode,
            resource_key: editingDatasetSemantic.resourceKey || editingDatasetSemantic.datasetCode,
            reason: 'manual_unpublish',
          }),
        },
      );

      if (response.status === 404 || response.status === 405 || response.status === 501) {
        applyLocalUpdate('当前环境未接入取消发布接口，已在本地会话取消发布。');
        return;
      }

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '取消发布失败'));
      }

      const savedDataset = normalizeDataset(data?.dataset ?? data?.item ?? data?.data?.dataset);
      if (savedDataset) {
        updateDatasetInState(
          editingDatasetSemantic.sourceId,
          editingDatasetSemantic.datasetId,
          editingDatasetSemantic.datasetCode,
          () => savedDataset,
        );
        setEditingDatasetSemantic((prev) =>
          prev &&
          prev.sourceId === editingDatasetSemantic.sourceId &&
          prev.datasetId === editingDatasetSemantic.datasetId
            ? buildEditableDatasetSemanticState(
                { id: editingDatasetSemantic.sourceId, name: editingDatasetSemantic.sourceName },
                savedDataset,
              )
            : prev,
        );
      } else {
        setEditingDatasetSemantic((prev) => (prev ? { ...prev, publishStatus: 'unpublished' } : prev));
      }
      setDatasetSemanticNotice(String(data?.message || '已取消发布'));
      await Promise.all([
        hydrateSourceDetail(editingDatasetSemantic.sourceId),
        (async () => {
          const availableState =
            availableDatasetPagesBySource[editingDatasetSemantic.sourceId] ?? createDefaultDatasetListPageState(100);
          await fetchAvailableDatasets(
            editingDatasetSemantic.sourceId,
            availableState.page,
            availableState.pageSize,
          );
        })(),
        (async () => {
          const physicalFilter =
            physicalCatalogFiltersBySource[editingDatasetSemantic.sourceId] ?? createDefaultPhysicalCatalogFilterState();
          await fetchPhysicalCatalogDatasets(editingDatasetSemantic.sourceId, physicalFilter);
        })(),
      ]);
    } catch (error) {
      setDatasetSemanticError(error instanceof Error ? error.message : '取消发布失败');
    } finally {
      setSavingDatasetSemantic(false);
    }
  }, [
    authHeaders,
    authToken,
    availableDatasetPagesBySource,
    draftSourceIdSet,
    editingDatasetSemantic,
    fetchAvailableDatasets,
    fetchPhysicalCatalogDatasets,
    hydrateSourceDetail,
    physicalCatalogFiltersBySource,
    updateDatasetInState,
  ]);

  const renderSourceList = (kind: Extract<DataSourceKind, 'database' | 'api' | 'file'>) => {
    const rows = selectedKindSources.filter((item) => item.source_kind === kind);
    const defaultActiveSource =
      selectedSource && selectedSource.source_kind === kind
        ? selectedSource
        : rows.find((item) => item.id === selectedSourceId) ?? rows[0] ?? null;
    const activeSource =
      kind === 'database' ? rows.find((item) => item.id === databaseDetailSourceId) ?? null : defaultActiveSource;
    const showDatabaseOverview = kind === 'database' && !databaseDetailSourceId;
    const detailState = activeSource ? sourceDetails[activeSource.id] ?? createDefaultSourceDetail() : createDefaultSourceDetail();
    const fallbackDatasets = detailState.datasets.length > 0 ? detailState.datasets : activeSource?.datasets ?? [];
    const isDraftSource = activeSource ? draftSourceIdSet.has(activeSource.id) : false;
    const connectionStatus = activeSource?.health_summary?.connection_status ?? activeSource?.status;
    const datasetStatus = activeSource?.health_summary?.dataset_status;
    const canDiscover =
      !isDraftSource &&
      Boolean(activeSource?.capabilities?.can_discover || activeSource?.source_kind === 'database' || activeSource?.source_kind === 'api');
    const apiForm =
      activeSource?.source_kind === 'api'
        ? apiDiscoveryForms[activeSource.id] ?? createDefaultApiDiscoveryForm()
        : createDefaultApiDiscoveryForm();
    const sourceForm = activeSource
      ? sourceForms[activeSource.id] ?? createEditableSourceConfig(activeSource)
      : null;
    const discoverSummary = activeSource?.discover_summary;
    const canManagePhysicalCatalog = canManagePhysicalCatalogForSource(activeSource);
    const currentDatasetTab: DatasetViewTab =
      activeSource && canManagePhysicalCatalog
        ? datasetViewTabsBySource[activeSource.id] ?? 'available'
        : 'available';
    const targetedDiscoverSource = targetedDiscoverDialog
      ? mergedSources.find((item) => item.id === targetedDiscoverDialog.sourceId) ?? null
      : null;
    const physicalFilter =
      activeSource && canManagePhysicalCatalog
        ? physicalCatalogFiltersBySource[activeSource.id] ?? createDefaultPhysicalCatalogFilterState()
        : createDefaultPhysicalCatalogFilterState();
    const availableState =
      activeSource ? availableDatasetPagesBySource[activeSource.id] ?? createDefaultDatasetListPageState(100) : createDefaultDatasetListPageState(100);
    const availableDatasets = (isDraftSource ? fallbackDatasets : availableState.rows).filter((dataset) =>
      isDatasetAvailable(dataset),
    );
    const physicalState =
      activeSource ? physicalDatasetPagesBySource[activeSource.id] ?? createDefaultDatasetListPageState() : createDefaultDatasetListPageState();
    const physicalCatalogRows = isDraftSource ? fallbackDatasets : physicalState.rows;
    const schemaOptions = Array.from(
      new Set(
        physicalCatalogRows
          .map((dataset) => parseSchemaAndObjectName(dataset).schemaName)
          .filter((item) => item && item !== '-'),
      ),
    ).sort((left, right) => left.localeCompare(right));
    const objectTypeOptions = Array.from(
      new Set(
        physicalCatalogRows
          .map((dataset) => readDatasetObjectType(dataset))
          .filter((item) => Boolean(item)),
      ),
    ).sort((left, right) => left.localeCompare(right));
    const pageSize = Math.max(5, physicalState.pageSize || physicalFilter.pageSize || 20);
    const totalPhysicalCount = isDraftSource ? physicalCatalogRows.length : Math.max(0, physicalState.total || 0);
    const totalPhysicalPages = Math.max(1, Math.ceil(totalPhysicalCount / pageSize));
    const currentPhysicalPage = Math.min(Math.max(1, physicalState.page || physicalFilter.page || 1), totalPhysicalPages);
    const datasetListLoading = currentDatasetTab === 'physical' ? physicalState.loading : availableState.loading;
    const datasetListError = currentDatasetTab === 'physical' ? physicalState.error : availableState.error;
    const datasetListApiAvailable =
      currentDatasetTab === 'physical' ? physicalState.apiAvailable : availableState.apiAvailable;
    const selectedPhysicalDetailId =
      activeSource && canManagePhysicalCatalog ? physicalDetailDatasetBySource[activeSource.id] ?? null : null;
    const selectedPhysicalDetailState =
      activeSource ? physicalDatasetDetailBySource[activeSource.id] ?? createDefaultDatasetDetailState() : createDefaultDatasetDetailState();
    const physicalDetailDialogDatasetId =
      activeSource && physicalDetailDialog?.sourceId === activeSource.id ? physicalDetailDialog.datasetId : null;
    const currentPhysicalDetailId = physicalDetailDialogDatasetId ?? selectedPhysicalDetailId;
    const selectedPhysicalDetail =
      (selectedPhysicalDetailState.datasetId === currentPhysicalDetailId ? selectedPhysicalDetailState.dataset : null) ??
      physicalCatalogRows.find((dataset) => dataset.id === currentPhysicalDetailId) ??
      null;
    const selectedPhysicalDetailSemantic = selectedPhysicalDetail ? readDatasetSemanticInfo(selectedPhysicalDetail) : null;
    const selectedPhysicalDetailSchemaColumns = selectedPhysicalDetail
      ? extractDatasetSchemaColumns(selectedPhysicalDetail)
      : [];
    const editingUniqueIdentifierRawNameSet = new Set(editingDatasetSemantic?.uniqueIdentifierRawNames ?? []);
    const editingSemanticFieldRows = editingDatasetSemantic ? editingDatasetSemantic.fieldRows : [];
    const editingUniqueIdentifierRows = editingSemanticFieldRows.filter((row) =>
      editingUniqueIdentifierRawNameSet.has(row.rawName),
    );
    const editingPendingFieldCount = editingSemanticFieldRows.filter((row) => row.pending).length;
    const isPhysicalDetailDialogOpen =
      Boolean(activeSource) && physicalDetailDialog?.sourceId === activeSource?.id && Boolean(physicalDetailDialogDatasetId);

    return (
      <>
        {showDatabaseOverview ? (
          <div className="space-y-4">
            {sourcesError && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {sourcesError}
              </div>
            )}
            {sourceActionError && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {sourceActionError}
              </div>
            )}
            {sourceActionNotice && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                {sourceActionNotice}
              </div>
            )}
            <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-text-primary">数据库连接列表</h3>
                  <p className="mt-1 text-sm text-text-secondary">
                    展示已配置数据库连接，点击可查看配置、数据集和目录。
                  </p>
                </div>
                <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-xs text-text-secondary">
                  共 {rows.length} 个连接
                </span>
              </div>

              {rows.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
                  当前类型暂无连接，可先新增占位连接。
                </div>
              ) : (
                <div className="overflow-auto rounded-xl border border-border">
                  <table className="min-w-[780px] w-full table-fixed text-sm">
                    <colgroup>
                      <col className="w-[46%]" />
                      <col className="w-[14%]" />
                      <col className="w-[10%]" />
                      <col className="w-[18%]" />
                      <col className="w-[12%]" />
                    </colgroup>
                    <thead className="bg-surface-secondary text-left text-text-secondary">
                      <tr>
                        <th className="px-4 py-3 font-medium">连接</th>
                        <th className="px-4 py-3 font-medium whitespace-nowrap">状态</th>
                        <th className="px-4 py-3 font-medium whitespace-nowrap">数据集</th>
                        <th className="px-4 py-3 font-medium whitespace-nowrap">最近更新</th>
                        <th className="px-4 py-3 font-medium text-right whitespace-nowrap">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((source) => {
                        const datasetCount =
                          typeof source.dataset_summary?.total === 'number'
                            ? source.dataset_summary.total
                            : source.datasets?.length ?? 0;
                        const connectionHealth = source.health_summary?.connection_status || source.status;
                        const databaseType = databaseTypeLabel(
                          inferDatabaseType(source.provider_code, source.connection_config?.database?.db_type),
                        );
                        const accountLabel = databaseConnectionAccount(source);
                        return (
                          <tr
                            key={source.id}
                            className="group cursor-pointer border-t border-border-subtle text-text-primary transition-colors hover:bg-surface-secondary"
                            onClick={() => openDatabaseSourceDetail(source)}
                          >
                            <td className="min-w-[320px] px-4 py-3.5 align-middle">
                              <div className="flex items-center gap-3">
                                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-accent text-blue-600">
                                  {sourceKindIcon(source.source_kind)}
                                </span>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <p className="truncate text-sm font-medium text-text-primary">{source.name}</p>
                                    {draftSourceIdSet.has(source.id) && (
                                      <span className="rounded-full border border-dashed border-border px-2 py-0.5 text-[11px] text-text-muted">
                                        草稿
                                      </span>
                                    )}
                                  </div>
                                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                    <span className="inline-flex max-w-full items-center rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
                                      {databaseType}
                                    </span>
                                    <span
                                      className="inline-flex max-w-full items-center rounded-full border border-border px-2.5 py-1 text-xs text-text-primary"
                                      title={accountLabel}
                                    >
                                      <span className="truncate">{accountLabel}</span>
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3.5 align-middle whitespace-nowrap">
                              <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(connectionHealth)}`}>
                                {getStatusLabel(connectionHealth)}
                              </span>
                            </td>
                            <td className="px-4 py-3.5 align-middle text-sm font-medium text-text-primary whitespace-nowrap">
                              {datasetCount}
                            </td>
                            <td className="px-4 py-3.5 align-middle text-text-secondary whitespace-nowrap">
                              {formatTime(source.health_summary?.last_sync_at || source.updated_at)}
                            </td>
                            <td className="px-4 py-3.5 align-middle text-right whitespace-nowrap">
                              <span className="inline-flex items-center rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-text-primary transition-colors group-hover:bg-surface-tertiary">
                                进入详情
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className={kind === 'database' ? 'space-y-4' : 'grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]'}>
            {kind === 'database' ? (
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => setDatabaseDetailSourceId(null)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                >
                  <ArrowLeft className="h-4 w-4" />
                  返回数据库列表
                </button>
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-surface p-4 shadow-sm">
                {sourcesError && (
                  <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                    {sourcesError}
                  </div>
                )}

                {rows.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
                    当前类型暂无连接，可先新增占位连接。
                  </div>
                ) : (
                  <div className="space-y-2">
                    {rows.map((source) => {
                      const selected = activeSource?.id === source.id;
                      const datasetCount =
                        typeof source.dataset_summary?.total === 'number'
                          ? source.dataset_summary.total
                          : source.datasets?.length ?? 0;
                      return (
                        <button
                          key={source.id}
                          type="button"
                          onClick={() => handleSelectSource(source)}
                          className={`w-full rounded-2xl border px-4 py-3 text-left transition-colors ${
                            selected
                              ? 'border-border bg-surface-secondary shadow-sm ring-1 ring-[color:var(--color-border)]'
                              : 'border-border bg-surface hover:bg-surface-secondary'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-surface-accent text-blue-600">
                                  {sourceKindIcon(source.source_kind)}
                                </span>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold text-text-primary">{source.name}</p>
                                  <p className="truncate text-xs text-text-muted">{dataSourceSubtitle(source)}</p>
                                </div>
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(source.health_summary?.connection_status || source.status)}`}>
                                  {getStatusLabel(source.health_summary?.connection_status || source.status)}
                                </span>
                                <span className="inline-flex rounded-full bg-surface-accent px-2.5 py-1 text-xs text-text-secondary">
                                  {datasetCount} 个数据集
                                </span>
                              </div>
                            </div>
                            {draftSourceIdSet.has(source.id) && (
                              <span className="rounded-full border border-dashed border-border px-2 py-1 text-[11px] text-text-muted">
                                草稿
                              </span>
                            )}
                          </div>
                          <div className="mt-3 flex items-center justify-between gap-3 text-xs text-text-secondary">
                            <span>{executionModeLabel(source.execution_mode)}</span>
                            <span>{formatTime(source.health_summary?.last_sync_at || source.updated_at)}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
              {!activeSource ? (
                <div className="rounded-xl border border-dashed border-border px-4 py-12 text-center text-sm text-text-secondary">
                  {kind === 'database' ? '未找到对应数据库连接，请返回列表重新选择。' : '选择左侧连接后，在这里查看连接详情和数据集目录。'}
                </div>
              ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-surface-accent text-blue-600">
                      {sourceKindIcon(activeSource.source_kind)}
                    </span>
                    <div className="min-w-0">
                      <h3 className="truncate text-base font-semibold text-text-primary">{activeSource.name}</h3>
                      <p className="mt-1 text-sm text-text-secondary">
                        {activeSource.description || `${sourceKindLabel(activeSource.source_kind)}连接`}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(connectionStatus)}`}>
                      连接{getStatusLabel(connectionStatus)}
                    </span>
                    {datasetStatus && (
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(datasetStatus)}`}>
                        数据集{getStatusLabel(datasetStatus)}
                      </span>
                    )}
                    <span className="inline-flex rounded-full bg-surface-accent px-2.5 py-1 text-xs text-text-secondary">
                      {executionModeLabel(activeSource.execution_mode)}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(activeSource.source_kind === 'database' || activeSource.source_kind === 'api') && (
                    <button
                      type="button"
                      onClick={() => toggleSourceConfig(activeSource.id)}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                    >
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${isSourceConfigExpanded(activeSource.id) ? 'rotate-180' : ''}`}
                      />
                      {isSourceConfigExpanded(activeSource.id) ? '收起配置' : '编辑配置'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleTestSource(activeSource)}
                    disabled={sourceActionBusy !== null || isDraftSource}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {sourceActionBusy === `test:${activeSource.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                    测试连接
                  </button>
                  {canDiscover && (
                    <button
                      type="button"
                      onClick={() =>
                        activeSource.source_kind === 'api'
                          ? void handleRunApiDiscovery(activeSource)
                          : void handleDiscoverSource(activeSource)
                      }
                      disabled={sourceActionBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {sourceActionBusy === `discover:${activeSource.id}` ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                      更新数据集
                    </button>
                  )}
                  {activeSource.source_kind === 'database' && canDiscover && (
                    <button
                      type="button"
                      onClick={() =>
                        setTargetedDiscoverDialog({
                          sourceId: activeSource.id,
                          resourceKeysText: '',
                        })
                      }
                      disabled={sourceActionBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <Database className="h-4 w-4" />
                      指定表更新
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleDeleteSource(activeSource)}
                    disabled={sourceActionBusy !== null}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {sourceActionBusy === `delete:${activeSource.id}` ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    删除连接
                  </button>
                  {isDraftSource && (
                    <button
                      type="button"
                      onClick={() => removeDraftSource(activeSource.id)}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 px-3 py-2 text-sm text-red-600 transition-colors hover:bg-red-50"
                    >
                      <Trash2 className="h-4 w-4" />
                      移除草稿
                    </button>
                  )}
                </div>
              </div>

              {sourceActionError && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                  {sourceActionError}
                </div>
              )}
              {sourceActionNotice && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                  {sourceActionNotice}
                </div>
              )}
              {discoverSummary && (
                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <h4 className="text-sm font-semibold text-text-primary">
                        {discoverSummary.scan_mode === 'targeted' ? '指定表更新结果' : '最近一次目录扫描'}
                      </h4>
                      {discoverSummary.scan_mode === 'targeted' ? (
                        <p className="text-sm text-text-secondary">
                          已命中 {discoverSummary.matched_count ?? 0} / {discoverSummary.requested_count ?? 0} 个指定表
                        </p>
                      ) : (
                        <p className="text-sm text-text-secondary">
                          本次扫描 {discoverSummary.scanned_count ?? 0} / {discoverSummary.total_count ?? 0} 个对象
                        </p>
                      )}
                      {discoverSummary.last_discover_at && (
                        <p className="text-xs text-text-muted">更新时间：{formatTime(discoverSummary.last_discover_at)}</p>
                      )}
                    </div>
                    {activeSource.source_kind === 'database' && discoverSummary.has_more && (
                      <button
                        type="button"
                        onClick={() => void handleContinueDiscover(activeSource)}
                        disabled={sourceActionBusy !== null}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {sourceActionBusy === `discover:${activeSource.id}` ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <RefreshCw className="h-4 w-4" />
                        )}
                        继续扫描下一批
                      </button>
                    )}
                  </div>
                  {discoverSummary.scan_mode === 'targeted' && (discoverSummary.missing_targets?.length ?? 0) > 0 && (
                    <p className="mt-2 text-xs text-amber-700">
                      未命中：{discoverSummary.missing_targets?.slice(0, 6).join('，')}
                      {(discoverSummary.missing_targets?.length ?? 0) > 6 ? ' 等' : ''}
                    </p>
                  )}
                  {discoverSummary.last_discover_status === 'error' && discoverSummary.last_discover_error && (
                    <p className="mt-2 text-xs text-red-600">{discoverSummary.last_discover_error}</p>
                  )}
                </div>
              )}
              {activeSource.health_summary?.last_error_message && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                  {activeSource.health_summary.last_error_message}
                </div>
              )}

              {(activeSource.source_kind === 'database' || activeSource.source_kind === 'api') && sourceForm && (
                <section className="overflow-hidden rounded-2xl border border-border bg-surface-secondary">
                  <button
                    type="button"
                    onClick={() => toggleSourceConfig(activeSource.id)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-surface"
                  >
                    <div>
                      <h4 className="text-sm font-semibold text-text-primary">连接配置</h4>
                      <p className="mt-1 text-xs text-text-secondary">
                        编辑数据库或 API 接入参数，保存后再测试连接或更新数据集。
                      </p>
                    </div>
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1 text-xs text-text-secondary">
                      {isSourceConfigExpanded(activeSource.id) ? '收起' : '展开'}
                      <ChevronDown
                        className={`h-3.5 w-3.5 transition-transform ${isSourceConfigExpanded(activeSource.id) ? 'rotate-180' : ''}`}
                      />
                    </span>
                  </button>

                  {isSourceConfigExpanded(activeSource.id) && (
                    <div className="space-y-3 border-t border-border px-4 py-4">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => resetSourceForm(activeSource)}
                          disabled={sourceActionBusy !== null}
                          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          <RefreshCw className="h-4 w-4" />
                          还原已保存配置
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleSaveSource(activeSource)}
                          disabled={sourceActionBusy !== null}
                          className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {sourceActionBusy === `save:${activeSource.id}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <CheckCircle2 className="h-4 w-4" />
                          )}
                          保存配置
                        </button>
                      </div>

                  {activeSource.source_kind === 'database' && (
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">连接名称</span>
                        <input
                          value={sourceForm.name}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              name: event.target.value,
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：财务中台 Hologres 只读连接"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">数据库类型</span>
                        <div className="relative mt-2">
                          <select
                            value={sourceForm.database.db_type}
                            onChange={(event) =>
                              updateSourceForm(activeSource.id, (current) => ({
                                ...current,
                                database: {
                                  ...current.database,
                                  db_type: event.target.value,
                                },
                              }))
                            }
                            className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          >
                            <option value="hologres">Hologres</option>
                            <option value="mysql">MySQL</option>
                          </select>
                          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                            <ChevronDown className="h-4 w-4" />
                          </span>
                        </div>
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">主机</span>
                        <input
                          value={sourceForm.database.host}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              database: {
                                ...current.database,
                                host: event.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：db.internal.company.com"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">端口</span>
                        <input
                          value={sourceForm.database.port}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              database: {
                                ...current.database,
                                port: event.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：5432"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">数据库</span>
                        <input
                          value={sourceForm.database.database}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              database: {
                                ...current.database,
                                database: event.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：finance"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">用户名</span>
                        <input
                          value={sourceForm.database.username}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              database: {
                                ...current.database,
                                username: event.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：finance_reader"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">密码</span>
                        <input
                          type="password"
                          value={sourceForm.database.password}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              database: {
                                ...current.database,
                                password: event.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="数据库密码"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">说明</span>
                        <div className="mt-1 text-xs text-text-muted">连接超时固定为 5 秒，无需额外配置。</div>
                        <textarea
                          value={sourceForm.description}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              description: event.target.value,
                            }))
                          }
                          className="mt-2 min-h-24 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：仅用于账单对账，不允许写入"
                        />
                      </label>
                    </div>
                  )}

                  {activeSource.source_kind === 'api' && (
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">连接名称</span>
                        <input
                          value={sourceForm.name}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              name: event.target.value,
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：银行流水 API 连接"
                        />
                      </label>

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <span className="text-xs text-text-muted">鉴权方式</span>
                        <div className="relative mt-2">
                          <select
                            value={sourceForm.api.auth_mode}
                            onChange={(event) =>
                              updateSourceForm(activeSource.id, (current) => ({
                                ...current,
                                api: {
                                  ...current.api,
                                  auth_mode: event.target.value,
                                },
                              }))
                            }
                            className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          >
                            <option value="none">无需鉴权</option>
                            <option value="request">通过请求获取凭证</option>
                          </select>
                          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                            <ChevronDown className="h-4 w-4" />
                          </span>
                        </div>
                      </label>

                      {sourceForm.api.auth_mode === 'request' && (
                        <>
                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3 md:col-span-2">
                            <span className="text-xs text-text-muted">鉴权请求地址</span>
                            <input
                              value={sourceForm.api.auth_request_url}
                              onChange={(event) =>
                                updateSourceForm(activeSource.id, (current) => ({
                                  ...current,
                                  api: {
                                    ...current.api,
                                    auth_request_url: event.target.value,
                                  },
                                }))
                              }
                              className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              placeholder="例如：https://openapi.bank.com/oauth/token"
                            />
                          </label>

                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <span className="text-xs text-text-muted">请求方式</span>
                            <div className="relative mt-2">
                              <select
                                value={sourceForm.api.auth_request_method}
                                onChange={(event) =>
                                  updateSourceForm(activeSource.id, (current) => ({
                                    ...current,
                                    api: {
                                      ...current.api,
                                      auth_request_method: event.target.value,
                                    },
                                  }))
                                }
                                className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              >
                                <option value="POST">POST</option>
                                <option value="GET">GET</option>
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                                <ChevronDown className="h-4 w-4" />
                              </span>
                            </div>
                          </label>

                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <span className="text-xs text-text-muted">参数类型</span>
                            <div className="relative mt-2">
                              <select
                                value={sourceForm.api.auth_request_payload_type}
                                onChange={(event) =>
                                  updateSourceForm(activeSource.id, (current) => ({
                                    ...current,
                                    api: {
                                      ...current.api,
                                      auth_request_payload_type: event.target.value,
                                    },
                                  }))
                                }
                                className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              >
                                <option value="json">JSON</option>
                                <option value="params">Params</option>
                                <option value="form">Form</option>
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                                <ChevronDown className="h-4 w-4" />
                              </span>
                            </div>
                          </label>

                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3 md:col-span-2">
                            <span className="text-xs text-text-muted">鉴权请求头</span>
                            <div className="mt-2 space-y-2">
                              {sourceForm.api.auth_request_headers.map((row) => (
                                <div key={row.id} className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                                  <input
                                    value={row.key}
                                    onChange={(event) =>
                                      updateApiKeyValueRow(activeSource.id, 'auth_request_headers', row.id, {
                                        key: event.target.value,
                                      })
                                    }
                                    className="rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                    placeholder="Header 名称"
                                  />
                                  <input
                                    value={row.value}
                                    onChange={(event) =>
                                      updateApiKeyValueRow(activeSource.id, 'auth_request_headers', row.id, {
                                        value: event.target.value,
                                      })
                                    }
                                    className="rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                    placeholder="Header 值"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => removeApiKeyValueRow(activeSource.id, 'auth_request_headers', row.id)}
                                    className="inline-flex items-center justify-center rounded-xl border border-border bg-surface px-3 text-text-secondary transition-colors hover:bg-surface-tertiary"
                                    aria-label="删除请求头"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </button>
                                </div>
                              ))}
                              <button
                                type="button"
                                onClick={() => addApiKeyValueRow(activeSource.id, 'auth_request_headers')}
                                className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                              >
                                <Plus className="h-4 w-4" />
                                新增请求头
                              </button>
                            </div>
                          </label>

                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3 md:col-span-2">
                            <span className="text-xs text-text-muted">鉴权请求参数</span>
                            {sourceForm.api.auth_request_payload_type === 'json' ? (
                              <textarea
                                value={sourceForm.api.auth_request_json_text}
                                onChange={(event) =>
                                  updateSourceForm(activeSource.id, (current) => ({
                                    ...current,
                                    api: {
                                      ...current.api,
                                      auth_request_json_text: event.target.value,
                                    },
                                  }))
                                }
                                className="mt-2 min-h-28 w-full rounded-xl border border-border bg-surface px-3 py-2.5 font-mono text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                placeholder={'例如：{\n  "client_id": "xxx",\n  "client_secret": "xxx"\n}'}
                              />
                            ) : (
                              <div className="mt-2 space-y-2">
                                {sourceForm.api.auth_request_params.map((row) => (
                                  <div key={row.id} className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                                    <input
                                      value={row.key}
                                      onChange={(event) =>
                                        updateApiKeyValueRow(activeSource.id, 'auth_request_params', row.id, {
                                          key: event.target.value,
                                        })
                                      }
                                      className="rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                      placeholder="参数名"
                                    />
                                    <input
                                      value={row.value}
                                      onChange={(event) =>
                                        updateApiKeyValueRow(activeSource.id, 'auth_request_params', row.id, {
                                          value: event.target.value,
                                        })
                                      }
                                      className="rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                      placeholder="参数值"
                                    />
                                    <button
                                      type="button"
                                      onClick={() => removeApiKeyValueRow(activeSource.id, 'auth_request_params', row.id)}
                                      className="inline-flex items-center justify-center rounded-xl border border-border bg-surface px-3 text-text-secondary transition-colors hover:bg-surface-tertiary"
                                      aria-label="删除请求参数"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </button>
                                  </div>
                                ))}
                                <button
                                  type="button"
                                  onClick={() => addApiKeyValueRow(activeSource.id, 'auth_request_params')}
                                  className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                                >
                                  <Plus className="h-4 w-4" />
                                  新增请求参数
                                </button>
                              </div>
                            )}
                          </label>

                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <span className="text-xs text-text-muted">写入 Header 名称</span>
                            <input
                              value={sourceForm.api.auth_apply_header_name}
                              onChange={(event) =>
                                updateSourceForm(activeSource.id, (current) => ({
                                  ...current,
                                  api: {
                                    ...current.api,
                                    auth_apply_header_name: event.target.value,
                                  },
                                }))
                              }
                              className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              placeholder="例如：Authorization"
                            />
                          </label>

                          <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <span className="text-xs text-text-muted">Header 取值</span>
                            <input
                              value={sourceForm.api.auth_apply_value_template}
                              onChange={(event) =>
                                updateSourceForm(activeSource.id, (current) => ({
                                  ...current,
                                  api: {
                                    ...current.api,
                                    auth_apply_value_template: event.target.value,
                                  },
                                }))
                              }
                              className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              placeholder="填写响应取值路径，如：data.access_token"
                            />
                          </label>

                          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-700 md:col-span-2">
                            鉴权请求中的敏感参数不会从后端回显。重新保存时，如需变更，请重新填写。
                          </div>
                        </>
                      )}

                      <label className="rounded-2xl border border-border bg-surface-secondary px-4 py-3 md:col-span-2">
                        <span className="text-xs text-text-muted">说明</span>
                        <textarea
                          value={sourceForm.description}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              description: event.target.value,
                            }))
                          }
                          className="mt-2 min-h-24 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="例如：用于拉取银行流水和账户余额"
                        />
                      </label>
                    </div>
                  )}
                    </div>
                  )}
                </section>
              )}

              {activeSource.source_kind === 'api' && (
                <section className="space-y-3">
                  <div>
                    <h4 className="text-sm font-semibold text-text-primary">API 数据集生成</h4>
                    <p className="mt-1 text-xs text-text-secondary">
                      选择按文档生成，或手工配置单个 endpoint 生成数据集。
                    </p>
                  </div>

                  <div className="rounded-2xl border border-border bg-surface-secondary p-4">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => updateApiDiscoveryForm(activeSource.id, { discoveryMode: 'document' })}
                        className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                          apiForm.discoveryMode === 'document'
                            ? 'bg-blue-600 text-white'
                            : 'bg-surface text-text-secondary hover:bg-surface-tertiary'
                        }`}
                      >
                        文档
                      </button>
                      <button
                        type="button"
                        onClick={() => updateApiDiscoveryForm(activeSource.id, { discoveryMode: 'manual' })}
                        className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                          apiForm.discoveryMode === 'manual'
                            ? 'bg-blue-600 text-white'
                            : 'bg-surface text-text-secondary hover:bg-surface-tertiary'
                        }`}
                      >
                        手工 endpoint
                      </button>
                    </div>

                    {apiForm.discoveryMode === 'document' ? (
                      <div className="mt-4 space-y-3">
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => updateApiDiscoveryForm(activeSource.id, { documentInputMode: 'url' })}
                            className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                              apiForm.documentInputMode === 'url'
                                ? 'bg-surface-accent text-text-primary'
                                : 'bg-surface text-text-secondary hover:bg-surface-tertiary'
                            }`}
                          >
                            文档地址
                          </button>
                          <button
                            type="button"
                            onClick={() => updateApiDiscoveryForm(activeSource.id, { documentInputMode: 'content' })}
                            className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                              apiForm.documentInputMode === 'content'
                                ? 'bg-surface-accent text-text-primary'
                                : 'bg-surface text-text-secondary hover:bg-surface-tertiary'
                            }`}
                          >
                            文档内容
                          </button>
                        </div>

                        {apiForm.documentInputMode === 'url' ? (
                          <input
                            value={apiForm.documentUrl}
                            onChange={(event) =>
                              updateApiDiscoveryForm(activeSource.id, { documentUrl: event.target.value })
                            }
                            className="w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                            placeholder="例如：https://example.com/openapi.json"
                          />
                        ) : (
                          <textarea
                            value={apiForm.documentContent}
                            onChange={(event) =>
                              updateApiDiscoveryForm(activeSource.id, { documentContent: event.target.value })
                            }
                            className="min-h-40 w-full rounded-xl border border-border bg-surface px-3 py-2.5 font-mono text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                            placeholder="粘贴 OpenAPI、Swagger 或普通 API 文档内容，系统会自动生成数据集"
                          />
                        )}

                        <button
                          type="button"
                          onClick={() => void handleGenerateApiDatasetsFromDocument(activeSource)}
                          disabled={sourceActionBusy !== null || isDraftSource}
                          className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {sourceActionBusy === `document:${activeSource.id}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Globe className="h-4 w-4" />
                          )}
                          生成 API 数据集
                        </button>
                      </div>
                    ) : (
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        <label className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <span className="text-xs text-text-muted">数据集名称</span>
                          <input
                            value={apiForm.manualDatasetName}
                            onChange={(event) =>
                              updateApiDiscoveryForm(activeSource.id, { manualDatasetName: event.target.value })
                            }
                            className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                            placeholder="例如：订单明细"
                          />
                        </label>

                        <label className="rounded-2xl border border-border bg-surface px-4 py-3 md:col-span-2">
                          <span className="text-xs text-text-muted">API 地址</span>
                          <input
                            value={apiForm.manualApiPath}
                            onChange={(event) =>
                              updateApiDiscoveryForm(activeSource.id, { manualApiPath: event.target.value })
                            }
                            className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                            placeholder="例如：/v1/orders 或完整 URL"
                          />
                        </label>

                        <label className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <span className="text-xs text-text-muted">请求方式</span>
                          <div className="relative mt-2">
                            <select
                              value={apiForm.manualMethod}
                              onChange={(event) =>
                                updateApiDiscoveryForm(activeSource.id, {
                                  manualMethod: event.target.value as ApiDiscoveryFormState['manualMethod'],
                                })
                              }
                              className="w-full appearance-none rounded-xl border border-border bg-surface-secondary px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                            >
                              <option value="GET">GET</option>
                              <option value="POST">POST</option>
                            </select>
                            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                              <ChevronDown className="h-4 w-4" />
                            </span>
                          </div>
                        </label>

                        <label className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <span className="text-xs text-text-muted">请求参数类型</span>
                          <div className="relative mt-2">
                            <select
                              value={apiForm.manualParamType}
                              onChange={(event) =>
                                updateApiDiscoveryForm(activeSource.id, {
                                  manualParamType: event.target.value as ApiDiscoveryFormState['manualParamType'],
                                })
                              }
                              className="w-full appearance-none rounded-xl border border-border bg-surface-secondary px-3 py-2.5 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                            >
                              <option value="params">Params</option>
                              <option value="json">JSON</option>
                            </select>
                            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                              <ChevronDown className="h-4 w-4" />
                            </span>
                          </div>
                        </label>

                        <label className="rounded-2xl border border-border bg-surface px-4 py-3 md:col-span-2">
                          <span className="text-xs text-text-muted">请求参数</span>
                          {apiForm.manualParamType === 'json' ? (
                            <textarea
                              value={apiForm.manualJsonText}
                              onChange={(event) =>
                                updateApiDiscoveryForm(activeSource.id, { manualJsonText: event.target.value })
                              }
                              className="mt-2 min-h-32 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 font-mono text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              placeholder={'例如：{\n  "page": 1,\n  "page_size": 100\n}'}
                            />
                          ) : (
                            <div className="mt-2 space-y-2">
                              {apiForm.manualParams.map((row) => (
                                <div key={row.id} className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                                  <input
                                    value={row.key}
                                    onChange={(event) =>
                                      updateApiDiscoveryKeyValueRow(activeSource.id, row.id, {
                                        key: event.target.value,
                                      })
                                    }
                                    className="rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                    placeholder="参数名"
                                  />
                                  <input
                                    value={row.value}
                                    onChange={(event) =>
                                      updateApiDiscoveryKeyValueRow(activeSource.id, row.id, {
                                        value: event.target.value,
                                      })
                                    }
                                    className="rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                                    placeholder="参数值"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => removeApiDiscoveryKeyValueRow(activeSource.id, row.id)}
                                    className="inline-flex items-center justify-center rounded-xl border border-border bg-surface-secondary px-3 text-text-secondary transition-colors hover:bg-surface-tertiary"
                                    aria-label="删除请求参数"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </button>
                                </div>
                              ))}
                              <button
                                type="button"
                                onClick={() => addApiDiscoveryKeyValueRow(activeSource.id)}
                                className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                              >
                                <Plus className="h-4 w-4" />
                                新增请求参数
                              </button>
                            </div>
                          )}
                        </label>

                        <div className="md:col-span-2">
                          <button
                            type="button"
                            onClick={() => void handleApplyManualEndpoint(activeSource)}
                            disabled={sourceActionBusy !== null || isDraftSource}
                            className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {sourceActionBusy === `manual:${activeSource.id}` ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Link2 className="h-4 w-4" />
                            )}
                            生成 API 数据集
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              )}

              <section className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-semibold text-text-primary">数据集视图</h4>
                    <p className="mt-1 text-xs text-text-secondary">
                      可用数据集用于业务使用，物理目录用于管理员治理海量对象。
                    </p>
                  </div>
                  <div className="inline-flex rounded-xl border border-border bg-surface-secondary p-1">
                    <button
                      type="button"
                      onClick={() => activeSource && setDatasetViewTab(activeSource.id, 'available')}
                      className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
                        currentDatasetTab === 'available'
                          ? 'bg-surface text-text-primary shadow-sm'
                          : 'text-text-secondary hover:bg-surface-tertiary'
                      }`}
                    >
                      可用数据集
                    </button>
                    {canManagePhysicalCatalog && (
                      <button
                        type="button"
                        onClick={() => activeSource && setDatasetViewTab(activeSource.id, 'physical')}
                        className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
                          currentDatasetTab === 'physical'
                            ? 'bg-surface text-text-primary shadow-sm'
                            : 'text-text-secondary hover:bg-surface-tertiary'
                        }`}
                      >
                        物理目录
                      </button>
                    )}
                  </div>
                </div>

                {datasetActionError && (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                    {datasetActionError}
                  </div>
                )}
                {datasetActionNotice && (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                    {datasetActionNotice}
                  </div>
                )}

                {datasetListLoading ? (
                  <div className="flex items-center justify-center rounded-xl border border-border-subtle bg-surface-secondary px-4 py-8 text-sm text-text-secondary">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    正在加载数据集目录
                  </div>
                ) : datasetListError ? (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                    {datasetListError}
                  </div>
                ) : datasetListApiAvailable === false ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                    当前环境尚未接入数据集目录接口。
                  </div>
                ) : currentDatasetTab === 'available' && availableDatasets.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                    暂无数据集，可通过上方“更新数据集”或本页配置生成目录。
                  </div>
                ) : currentDatasetTab === 'available' ? (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="rounded-full bg-surface-secondary px-3 py-1 text-xs text-text-secondary">
                        {availableDatasets.length} 个可用数据集
                      </span>
                    </div>
                    {availableDatasets.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                        当前没有可用数据集。请管理员在“物理目录”中发布数据集后再使用。
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {availableDatasets.map((dataset) => {
                          const semanticInfo = readDatasetSemanticInfo(dataset);
                          const title = semanticInfo.businessName || dataset.business_name || dataset.dataset_name;
                          const keyFields = semanticInfo.keyFields.slice(0, 6);
                          const techSubtitle = buildDatasetTechSubtitle(activeSource, dataset);
                          const lastUsedAt = readDatasetLastUsedAt(dataset);
                          return (
                            <div key={dataset.id} className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <p className="text-sm font-medium text-text-primary">{title}</p>
                                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${statusBadgeClass(dataset.health_status || dataset.status)}`}>
                                      {getStatusLabel(dataset.health_status || dataset.status)}
                                    </span>
                                  </div>
                                  <p className="mt-1 truncate text-xs text-text-muted" title={techSubtitle}>
                                    {techSubtitle}
                                  </p>
                                </div>
                                <div className="text-right text-xs text-text-secondary">
                                  <p>最近使用：{formatTime(lastUsedAt)}</p>
                                  <p>最近同步：{formatTime(dataset.last_sync_at)}</p>
                                  <button
                                    type="button"
                                    onClick={() => void openDatasetCollectionDetail(activeSource, dataset)}
                                    className="mt-2 inline-flex items-center justify-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1.5 text-xs whitespace-nowrap text-blue-700 transition-colors hover:bg-blue-100"
                                  >
                                    采集详情
                                  </button>
                                </div>
                              </div>

                              {keyFields.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  {keyFields.map((field) => (
                                    <span
                                      key={`${dataset.id}-${field}`}
                                      className="inline-flex rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-text-secondary"
                                    >
                                      {formatSemanticKeyFieldLabel(field, semanticInfo.fieldLabelMap)}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-2xl border border-border bg-surface-secondary p-3">
                      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
                        <input
                          value={physicalFilter.keyword}
                          onChange={(event) =>
                            activeSource &&
                            updatePhysicalCatalogFilter(activeSource.id, {
                              keyword: event.target.value,
                            })
                          }
                          className="rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="搜索表名/业务名/关键字"
                        />
                        <div className="relative">
                          <select
                            value={physicalFilter.schema}
                            onChange={(event) =>
                              activeSource && updatePhysicalCatalogFilter(activeSource.id, { schema: event.target.value })
                            }
                            className="w-full appearance-none rounded-xl border border-border bg-surface py-2 pl-3 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          >
                            <option value="all">全部 schema</option>
                            {schemaOptions.map((item) => (
                              <option key={item} value={item}>
                                {item}
                              </option>
                            ))}
                          </select>
                          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                            <ChevronDown className="h-4 w-4" />
                          </span>
                        </div>
                        <div className="relative">
                          <select
                            value={physicalFilter.objectType}
                            onChange={(event) =>
                              activeSource && updatePhysicalCatalogFilter(activeSource.id, { objectType: event.target.value })
                            }
                            className="w-full appearance-none rounded-xl border border-border bg-surface py-2 pl-3 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          >
                            <option value="all">全部对象类型</option>
                            {objectTypeOptions.map((item) => (
                              <option key={item} value={item}>
                                {item}
                              </option>
                            ))}
                          </select>
                          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                            <ChevronDown className="h-4 w-4" />
                          </span>
                        </div>
                        <div className="relative">
                          <select
                            value={physicalFilter.publishStatus}
                            onChange={(event) =>
                              activeSource &&
                              updatePhysicalCatalogFilter(activeSource.id, { publishStatus: event.target.value })
                            }
                            className="w-full appearance-none rounded-xl border border-border bg-surface py-2 pl-3 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          >
                            <option value="all">全部发布状态</option>
                            <option value="published">已发布</option>
                            <option value="unpublished">未发布</option>
                            <option value="deprecated">已废弃</option>
                          </select>
                          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                            <ChevronDown className="h-4 w-4" />
                          </span>
                        </div>
                        <div className="relative">
                          <select
                            value={physicalFilter.verifiedStatus}
                            onChange={(event) =>
                              activeSource &&
                              updatePhysicalCatalogFilter(activeSource.id, { verifiedStatus: event.target.value })
                            }
                            className="w-full appearance-none rounded-xl border border-border bg-surface py-2 pl-3 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          >
                            <option value="all">全部验证状态</option>
                            <option value="verified">已验证</option>
                            <option value="unverified">未验证</option>
                            <option value="rejected">已驳回</option>
                          </select>
                          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                            <ChevronDown className="h-4 w-4" />
                          </span>
                        </div>
                      </div>
                    </div>

                    {physicalCatalogRows.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                        未找到匹配的物理目录对象，请调整筛选条件。
                      </div>
                    ) : (
                      <>
                        <div className="overflow-x-auto rounded-xl border border-border">
                          <table className="min-w-[820px] w-full table-fixed text-sm">
                            <colgroup>
                              <col className="w-[30%]" />
                              <col className="w-[28%]" />
                              <col className="w-[12%]" />
                              <col className="w-[14%]" />
                              <col className="w-[16%]" />
                            </colgroup>
                            <thead className="bg-surface-secondary text-left text-text-secondary">
                              <tr>
                                <th className="px-4 py-3 font-medium">技术对象</th>
                                <th className="px-4 py-3 font-medium">业务治理</th>
                                <th className="px-4 py-3 font-medium whitespace-nowrap">发布状态</th>
                                <th className="px-4 py-3 font-medium whitespace-nowrap">更新时间</th>
                                <th className="border-l border-border-subtle bg-surface-secondary px-4 py-3 font-medium text-right whitespace-nowrap">
                                  操作
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {physicalCatalogRows.map((dataset) => {
                                const semanticInfo = readDatasetSemanticInfo(dataset);
                                const { schemaName, objectName } = parseSchemaAndObjectName(dataset);
                                const publishStatus = readDatasetPublishStatus(dataset);
                                const verifiedStatus = readDatasetVerifiedStatus(dataset);
                                const objectType = readDatasetObjectType(dataset);
                                const objectLabel = `${schemaName}.${objectName}`;
                                const businessName = semanticInfo.businessName || dataset.business_name || '未命名';
                                const pendingCount = readDatasetPendingFieldCount(dataset);
                                const isSelected =
                                  isPhysicalDetailDialogOpen && physicalDetailDialogDatasetId === dataset.id;
                                return (
                                  <tr
                                    key={dataset.id}
                                    className={`group cursor-pointer border-t border-border-subtle text-text-primary transition-colors hover:bg-surface-secondary ${isSelected ? 'bg-surface-tertiary' : ''}`}
                                    onClick={() => {
                                      setPhysicalDetailDatasetBySource((prev) => ({
                                        ...prev,
                                        [activeSource.id]: dataset.id,
                                      }));
                                      setPhysicalDetailDialog({
                                        sourceId: activeSource.id,
                                        datasetId: dataset.id,
                                      });
                                    }}
                                  >
                                    <td className="px-4 py-3 align-top text-text-secondary">
                                      <div className="min-w-0">
                                        <p
                                          className="truncate text-sm font-medium text-text-primary"
                                          title={objectLabel}
                                        >
                                          {objectLabel}
                                        </p>
                                        <p
                                          className="truncate text-xs text-text-muted"
                                          title={dataset.dataset_code}
                                        >
                                          {dataset.dataset_code}
                                        </p>
                                      </div>
                                    </td>
                                    <td className="px-4 py-3 align-top text-text-secondary">
                                      <div className="min-w-0">
                                        <p className="truncate text-sm text-text-primary" title={businessName}>
                                          {businessName}
                                        </p>
                                        <div className="mt-1 flex flex-wrap items-center gap-2">
                                          <span
                                            className="inline-flex rounded-full bg-surface-tertiary px-2.5 py-1 text-xs font-medium text-text-secondary"
                                            title={objectType}
                                          >
                                            {objectType}
                                          </span>
                                          <span
                                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(verifiedStatus)}`}
                                          >
                                            {verifiedStatusLabel(verifiedStatus)}
                                          </span>
                                          <span
                                            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                                              pendingCount > 0
                                                ? 'bg-amber-100 text-amber-800'
                                                : 'bg-emerald-100 text-emerald-700'
                                            }`}
                                          >
                                            {pendingCount > 0 ? `待确认 ${pendingCount} 项` : '语义已确认'}
                                          </span>
                                        </div>
                                      </div>
                                    </td>
                                    <td className="px-4 py-3 align-top whitespace-nowrap">
                                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(publishStatus)}`}>
                                        {publishStatusLabel(publishStatus)}
                                      </span>
                                    </td>
                                    <td className="px-4 py-3 align-top text-xs leading-5 text-text-secondary">
                                      {formatTime(dataset.updated_at || dataset.last_sync_at)}
                                    </td>
                                    <td className="border-l border-border-subtle px-4 py-3 align-top">
                                      <div className="flex min-w-[112px] flex-col items-end gap-1.5">
                                        <button
                                          type="button"
                                          onClick={(event) => {
                                            event.stopPropagation();
                                            void startEditDatasetSemantic(activeSource, dataset);
                                          }}
                                          className="inline-flex min-w-[88px] items-center justify-center gap-1 rounded-lg border border-border px-2 py-1.5 text-xs whitespace-nowrap text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                          {publishStatus === 'published' ? '管理发布' : '发布'}
                                        </button>
                                      </div>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-secondary px-3 py-2">
                          <p className="text-xs text-text-secondary">
                            共 {totalPhysicalCount} 条，当前第 {currentPhysicalPage}/{totalPhysicalPages} 页
                          </p>
                          <div className="flex items-center gap-2">
                            <div className="relative">
                              <select
                                value={pageSize}
                                onChange={(event) =>
                                  activeSource &&
                                  updatePhysicalCatalogFilter(activeSource.id, {
                                    pageSize: Number(event.target.value) || 20,
                                  })
                                }
                                className="appearance-none rounded-lg border border-border bg-surface py-1 pl-2 pr-8 text-xs text-text-primary outline-none transition-colors focus:border-blue-300"
                              >
                                <option value={10}>10 / 页</option>
                                <option value={20}>20 / 页</option>
                                <option value={50}>50 / 页</option>
                              </select>
                              <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-text-muted">
                                <ChevronDown className="h-3.5 w-3.5" />
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() =>
                                activeSource &&
                                updatePhysicalCatalogFilter(activeSource.id, { page: Math.max(1, currentPhysicalPage - 1) })
                              }
                              disabled={currentPhysicalPage <= 1}
                              className="rounded-lg border border-border bg-surface px-2.5 py-1 text-xs text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              上一页
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                activeSource &&
                                updatePhysicalCatalogFilter(activeSource.id, {
                                  page: Math.min(totalPhysicalPages, currentPhysicalPage + 1),
                                })
                              }
                              disabled={currentPhysicalPage >= totalPhysicalPages}
                              className="rounded-lg border border-border bg-surface px-2.5 py-1 text-xs text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              下一页
                            </button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </section>
            </div>
          )}
            </div>
          </div>
        )}
      {isPhysicalDetailDialogOpen && activeSource && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/35 px-4 py-6"
          onClick={() => setPhysicalDetailDialog(null)}
        >
          <div
            className="w-full max-w-5xl rounded-2xl border border-border bg-surface p-5 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h4 className="truncate text-base font-semibold text-text-primary">
                  目录详情：{selectedPhysicalDetail ? `${parseSchemaAndObjectName(selectedPhysicalDetail).schemaName}.${parseSchemaAndObjectName(selectedPhysicalDetail).objectName}` : '加载中'}
                </h4>
                {selectedPhysicalDetail && (
                  <p className="mt-1 truncate text-sm text-text-secondary">
                    业务名：{selectedPhysicalDetailSemantic?.businessName || selectedPhysicalDetail.business_name || '未命名'}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setPhysicalDetailDialog(null)}
                className="inline-flex items-center rounded-lg border border-border bg-surface-secondary px-3 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
              >
                关闭
              </button>
            </div>

            {selectedPhysicalDetail && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="inline-flex rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
                  数据集编码：{selectedPhysicalDetail.dataset_code}
                </span>
                <span className="inline-flex rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
                  对象类型：{readDatasetObjectType(selectedPhysicalDetail)}
                </span>
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(readDatasetPublishStatus(selectedPhysicalDetail))}`}>
                  {publishStatusLabel(readDatasetPublishStatus(selectedPhysicalDetail))}
                </span>
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(readDatasetVerifiedStatus(selectedPhysicalDetail))}`}>
                  {verifiedStatusLabel(readDatasetVerifiedStatus(selectedPhysicalDetail))}
                </span>
              </div>
            )}

            <div className="mt-4">
              {selectedPhysicalDetailState.error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                  {selectedPhysicalDetailState.error}
                </div>
              ) : selectedPhysicalDetailState.loading && selectedPhysicalDetailSchemaColumns.length === 0 ? (
                <div className="flex items-center justify-center rounded-xl border border-border-subtle bg-surface-secondary px-4 py-12 text-sm text-text-secondary">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载目录详情
                </div>
              ) : selectedPhysicalDetail && selectedPhysicalDetailSchemaColumns.length > 0 ? (
                <div className="max-h-[65vh] overflow-auto rounded-xl border border-border bg-surface">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-surface-secondary text-text-secondary">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium">字段名</th>
                        <th className="px-3 py-2 text-left font-medium">类型</th>
                        <th className="px-3 py-2 text-left font-medium">可空</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPhysicalDetailSchemaColumns.map((column) => (
                        <tr key={`${selectedPhysicalDetail.id}-${column.name}`} className="border-t border-border-subtle text-text-primary">
                          <td className="px-3 py-2">{column.name}</td>
                          <td className="px-3 py-2 text-text-secondary">{column.dataType}</td>
                          <td className="px-3 py-2 text-text-secondary">
                            {column.nullable === null ? '-' : column.nullable ? '是' : '否'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-border px-3 py-8 text-sm text-text-secondary">
                  当前对象暂无字段结构信息，可通过“更新数据集”或连接器补充 schema。
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {targetedDiscoverDialog && targetedDiscoverSource && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/35 px-4 py-6">
          <div className="w-full max-w-2xl rounded-2xl border border-border bg-surface p-5 shadow-lg">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h4 className="text-base font-semibold text-text-primary">指定表更新</h4>
                <p className="mt-1 text-xs text-text-secondary">
                  数据源：{targetedDiscoverSource.name}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setTargetedDiscoverDialog(null)}
                className="inline-flex items-center rounded-lg border border-border bg-surface-secondary px-3 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
              >
                关闭
              </button>
            </div>
            <div className="mt-4 space-y-3">
              <p className="text-sm text-text-secondary">
                输入要更新的表名，支持多行或逗号分隔。建议使用完整名，如 <span className="font-mono">public.orders</span>。
              </p>
              <textarea
                value={targetedDiscoverDialog.resourceKeysText}
                onChange={(event) =>
                  setTargetedDiscoverDialog((prev) =>
                    prev
                      ? {
                          ...prev,
                          resourceKeysText: event.target.value,
                        }
                      : prev,
                  )
                }
                rows={8}
                placeholder={'public.orders\npublic.order_items'}
                className="w-full rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setTargetedDiscoverDialog(null)}
                  disabled={sourceActionBusy === `discover:${targetedDiscoverSource.id}`}
                  className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleSubmitTargetedDiscover()}
                  disabled={sourceActionBusy === `discover:${targetedDiscoverSource.id}`}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {sourceActionBusy === `discover:${targetedDiscoverSource.id}` ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  开始更新
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {editingDatasetSemantic && (
        <div className="fixed inset-0 z-40 bg-black/35" onClick={closeEditingDatasetSemantic}>
          <div
            className="ml-auto flex h-full w-full max-w-2xl flex-col border-l border-border bg-surface shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-border px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-base font-semibold text-text-primary">
                      {editingDatasetSemantic.publishStatus === 'published' ? '管理发布' : '发布数据集'}
                    </h4>
                    <span
                      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(editingDatasetSemantic.publishStatus)}`}
                    >
                      {publishStatusLabel(editingDatasetSemantic.publishStatus)}
                    </span>
                    <span
                      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(editingDatasetSemantic.verifiedStatus)}`}
                    >
                      {verifiedStatusLabel(editingDatasetSemantic.verifiedStatus)}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-sm text-text-primary">{editingDatasetSemantic.datasetName}</p>
                  <p className="mt-1 truncate text-xs text-text-secondary">
                    {editingDatasetSemantic.sourceName} · {editingDatasetSemantic.schemaName}.{editingDatasetSemantic.objectName}
                    {editingDatasetSemantic.resourceKey ? ` · ${editingDatasetSemantic.resourceKey}` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeEditingDatasetSemantic}
                  className="inline-flex items-center rounded-lg border border-border bg-surface-secondary px-3 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
                >
                  关闭
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-5">
              <div className="space-y-4">
                {refreshingDatasetSemantic && (
                  <div className="flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在刷新语义建议，请稍候。
                  </div>
                )}

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block rounded-2xl border border-border bg-surface-secondary px-4 py-3 sm:col-span-2">
                    <span className="text-xs text-text-muted">业务名称</span>
                    <input
                      value={editingDatasetSemantic.businessName}
                      onChange={(event) =>
                        setEditingDatasetSemantic((prev) =>
                          prev
                            ? {
                                ...prev,
                                businessName: event.target.value,
                              }
                            : prev,
                        )
                      }
                      className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                      placeholder="例如：订单交易明细"
                    />
                  </label>

                  <label className="block rounded-2xl border border-border bg-surface-secondary px-4 py-3 sm:col-span-2">
                    <span className="text-xs text-text-muted">验证状态</span>
                    <div className="relative mt-2">
                      <select
                        value={editingDatasetSemantic.verifiedStatus}
                        onChange={(event) =>
                          setEditingDatasetSemantic((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  verifiedStatus: event.target.value,
                                }
                              : prev,
                        )
                      }
                      className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                    >
                        <option value="verified">已验证</option>
                        <option value="unverified">未验证</option>
                        <option value="rejected">已驳回</option>
                      </select>
                      <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                        <ChevronDown className="h-4 w-4" />
                      </span>
                    </div>
                  </label>
                </div>

                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-text-secondary" />
                    <span className="text-sm font-medium text-text-primary">唯一标识字段</span>
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">
                    用于数据采集幂等：系统会用唯一标识判断同一条源数据，重复采集时更新同一条记录而不是新增重复数据。
                  </p>
                  {editingUniqueIdentifierRows.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {editingUniqueIdentifierRows.map((row) => (
                        <span
                          key={`unique-identifier-${row.rawName}`}
                          className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                        >
                          {row.displayName || row.rawName}
                          <span className="ml-1 font-mono text-blue-500">{row.rawName}</span>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-border px-3 py-2 text-sm text-text-secondary">
                      当前还没有明确的唯一标识字段，请在下方字段列表中勾选。
                    </div>
                  )}
                  <p className="mt-3 text-xs text-text-muted">
                    需要调整时，直接在字段行里切换“作为唯一标识”。
                  </p>
                </div>

                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                  <div className="flex items-center gap-2">
                    <RefreshCw className="h-4 w-4 text-text-secondary" />
                    <span className="text-sm font-medium text-text-primary">采集配置</span>
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">
                    优先选择更新时间字段，确保能采集到新增和更新的数据；没有更新时间字段时选择创建时间字段，至少能采集到新创建的数据。
                  </p>
                  <p className="mt-1 text-xs text-blue-700">
                    发布后系统会按采集计划独立采集数据，写入数据资产层，供对账和后续 AI 数据统计使用。
                  </p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <label className="block">
                      <span className="text-xs text-text-muted">采集时间字段</span>
                      <div className="relative mt-2">
                        <select
                          value={editingDatasetSemantic.collectionDateField}
                          onChange={(event) => setEditingDatasetCollectionDateField(event.target.value)}
                          className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                        >
                          <option value="">暂不设置</option>
                          {editingSemanticFieldRows.map((row) => (
                            <option key={`collection-date-${row.rawName}`} value={row.rawName}>
                              {(row.displayName || row.rawName) === row.rawName
                                ? row.rawName
                                : `${row.displayName || row.rawName}（${row.rawName}）`}
                            </option>
                          ))}
                        </select>
                        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                          <ChevronDown className="h-4 w-4" />
                        </span>
                      </div>
                    </label>
                    <label className="block">
                      <span className="text-xs text-text-muted">频率</span>
                      <div className="relative mt-2">
                        <select
                          value={editingDatasetSemantic.collectionScheduleFrequency}
                          onChange={(event) =>
                            setEditingDatasetSemantic((prev) =>
                              prev ? { ...prev, collectionScheduleFrequency: event.target.value } : prev,
                            )
                          }
                          className="w-full appearance-none rounded-xl border border-border bg-surface px-3 py-2.5 pr-9 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                        >
                          <option value="daily">每日</option>
                        </select>
                        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-text-muted">
                          <ChevronDown className="h-4 w-4" />
                        </span>
                      </div>
                    </label>
                    <label className="block">
                      <span className="text-xs text-text-muted">执行时间</span>
                      <input
                        type="time"
                        value={editingDatasetSemantic.collectionScheduleTime}
                        onChange={(event) =>
                          setEditingDatasetSemantic((prev) =>
                            prev ? { ...prev, collectionScheduleTime: event.target.value } : prev,
                          )
                        }
                        className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                      />
                    </label>
                  </div>
                </div>

                <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4 text-text-secondary" />
                        <span className="text-sm font-medium text-text-primary">字段语义确认</span>
                      </div>
                      <p className="mt-1 text-xs text-text-secondary">
                        合并展示全部字段，直接用状态区分待确认和已确认。当前共 {editingSemanticFieldRows.length} 个字段，待确认 {editingPendingFieldCount} 个。
                      </p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => void refreshEditingDatasetSemantic()}
                        disabled={refreshingDatasetSemantic || savingDatasetSemantic}
                        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {refreshingDatasetSemantic ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <RefreshCw className="h-4 w-4" />
                        )}
                        刷新语义建议
                      </button>
                      <button
                        type="button"
                        onClick={acceptAllEditingDatasetSemanticSuggestions}
                        disabled={editingPendingFieldCount === 0}
                        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        全部接受建议
                      </button>
                    </div>
                  </div>

                  <div className="mt-4 max-h-[30rem] space-y-3 overflow-y-auto pr-1">
                    {editingSemanticFieldRows.map((row) => {
                      const isUniqueIdentifier = editingUniqueIdentifierRawNameSet.has(row.rawName);
                      return (
                        <div key={row.id} className="rounded-2xl border border-border bg-surface px-4 py-3">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-text-primary">{row.rawName}</p>
                              <p className="mt-1 text-xs text-text-secondary">
                                {buildDatasetFieldSummary(row) || '待补充字段语义'}
                              </p>
                            </div>
                            <div className="flex flex-wrap justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => toggleEditingDatasetSemanticUniqueIdentifier(row.rawName)}
                                className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                                  isUniqueIdentifier
                                    ? 'border border-blue-200 bg-blue-50 text-blue-700'
                                    : 'border border-border bg-surface-secondary text-text-secondary hover:bg-surface-tertiary'
                                }`}
                              >
                                {isUniqueIdentifier ? '唯一标识' : '作为唯一标识'}
                              </button>
                              {row.pending ? (
                                <span className="inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800">
                                  待确认
                                </span>
                              ) : (
                                <span className="inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700">
                                  已确认
                                </span>
                              )}
                            </div>
                          </div>
                          {row.sampleValues.length > 0 && (
                            <p className="mt-2 text-xs text-text-muted">
                              示例值：{row.sampleValues.slice(0, 3).join(' / ')}
                            </p>
                          )}
                          <label className="mt-3 block">
                            <span className="text-xs text-text-muted">中文名</span>
                            <input
                              value={row.displayName}
                              onChange={(event) =>
                                updateEditingDatasetSemanticField(row.id, { displayName: event.target.value })
                              }
                              className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                              placeholder={`例如：${inferDatasetFieldDisplayName(row.rawName)}`}
                            />
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {datasetSemanticError && (
                  <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                    {datasetSemanticError}
                  </div>
                )}
                {datasetSemanticNotice && (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                    {datasetSemanticNotice}
                  </div>
                )}
              </div>
            </div>

            <div className="border-t border-border bg-surface px-5 py-4">
              <div className="flex flex-wrap items-center justify-end gap-2">
                {editingDatasetSemantic.publishStatus === 'published' && (
                  <button
                    type="button"
                    onClick={() => void unpublishEditingDatasetSemantic()}
                    disabled={savingDatasetSemantic}
                    className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {savingDatasetSemantic ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertCircle className="h-4 w-4" />}
                    取消发布
                  </button>
                )}
                <button
                  type="button"
                  onClick={closeEditingDatasetSemantic}
                  className="inline-flex items-center rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void saveEditingDatasetSemantic()}
                  disabled={savingDatasetSemantic || refreshingDatasetSemantic}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {savingDatasetSemantic ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  {editingDatasetSemantic.publishStatus === 'published' ? '保存发布信息' : '确认发布'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {collectionDetailDialog && (
        <div className="fixed inset-0 z-40 bg-black/35" onClick={() => setCollectionDetailDialog(null)}>
          <div
            className="ml-auto flex h-full w-full max-w-3xl flex-col border-l border-border bg-surface shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-border px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h4 className="text-base font-semibold text-text-primary">采集详情</h4>
                  <p className="mt-1 truncate text-sm text-text-primary">{collectionDetailDialog.datasetName}</p>
                  <p className="mt-1 truncate text-xs text-text-secondary">
                    {collectionDetailDialog.sourceName} · {collectionDetailDialog.resourceKey}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setCollectionDetailDialog(null)}
                  className="inline-flex items-center rounded-lg border border-border bg-surface-secondary px-3 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-5">
              {collectionDetailDialog.loading ? (
                <div className="flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在加载采集详情。
                </div>
              ) : collectionDetailDialog.error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {collectionDetailDialog.error}
                </div>
              ) : (
                <div className="space-y-4">
                  {collectionDetailDialog.actionError && (
                    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                      {collectionDetailDialog.actionError}
                    </div>
                  )}
                  {(() => {
                    const detail = collectionDetailDialog.detail ?? {};
                    const jobs = Array.isArray(detail.jobs)
                      ? detail.jobs.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
                      : [];
                    const rows = Array.isArray(detail.rows)
                      ? detail.rows.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
                      : [];
                    const completedJobs = jobs.filter((job) => {
                      const status = (asString(job.status) || asString(job.job_status) || '').toLowerCase();
                      return status === 'success' || status === 'succeeded' || status === 'completed';
                    });
                    const latestJob = jobs[0] ?? {};
                    const collectedCount = jobs.reduce((total, job) => {
                      const metrics = asRecord(job.metrics) ?? {};
                      return total + (asNumber(metrics.collection_upserted) ?? asNumber(metrics.row_count) ?? asNumber(metrics.rows) ?? 0);
                    }, 0);
                    return (
                      <>
                        <div className="grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <p className="text-xs text-text-muted">采集任务</p>
                            <p className="mt-2 text-lg font-semibold text-text-primary">
                              {jobs.length} 次
                            </p>
                          </div>
                          <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <p className="text-xs text-text-muted">采集记录数</p>
                            <p className="mt-2 text-lg font-semibold text-text-primary">
                              {collectedCount || rows.length}
                            </p>
                          </div>
                          <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                            <p className="text-xs text-text-muted">最近采集</p>
                            <p className="mt-2 text-sm font-medium text-text-primary">
                              {formatTime(asString(latestJob.completed_at) || asString(latestJob.created_at))}
                            </p>
                          </div>
                        </div>

                        <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <p className="text-sm font-medium text-text-primary">最近采集任务</p>
                              <p className="mt-1 text-xs text-text-secondary">
                                展示该数据集最近的采集成功、失败和原因。成功 {completedJobs.length} 次。
                                {collectionDetailDialog.lastLoadedAt ? ` 最近刷新：${formatTime(collectionDetailDialog.lastLoadedAt)}` : ''}
                              </p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <button
                                type="button"
                                onClick={() => void refreshCollectionDetailDialog()}
                                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                              >
                                <RefreshCw className="h-4 w-4" />
                                刷新
                              </button>
                              <button
                                type="button"
                                onClick={() => void retryCollectionDetailDataset()}
                                className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
                              >
                                <RefreshCw className="h-4 w-4" />
                                立即采集
                              </button>
                            </div>
                          </div>
                          <div className="mt-3 space-y-2">
                            {jobs.length === 0 ? (
                              <p className="rounded-xl border border-dashed border-border px-3 py-2 text-sm text-text-secondary">
                                暂无采集任务。
                              </p>
                            ) : (
                              jobs.map((job) => {
                                const status = asString(job.status) || asString(job.job_status) || 'unknown';
                                const metrics = asRecord(job.metrics) ?? {};
                                const rowCount = asNumber(metrics.collection_upserted) ?? asNumber(metrics.row_count) ?? '';
                                return (
                                  <div key={asString(job.id) || JSON.stringify(job)} className="rounded-xl border border-border bg-surface px-3 py-2">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(status)}`}>
                                        {status}
                                      </span>
                                      <span className="text-xs text-text-muted">
                                        {formatTime(asString(job.completed_at) || asString(job.created_at))}
                                      </span>
                                    </div>
                                    <p className="mt-1 text-xs text-text-secondary">
                                      {rowCount !== '' ? `采集 ${rowCount} 条` : '未返回采集行数'}
                                    </p>
                                    {asString(job.error_message) && (
                                      <p className="mt-1 text-xs text-red-600">失败原因：{asString(job.error_message)}</p>
                                    )}
                                  </div>
                                );
                              })
                            )}
                          </div>
                        </div>

                        <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                          <p className="text-sm font-medium text-text-primary">最新 10 条数据</p>
                          <div className="mt-3 max-h-80 overflow-auto rounded-xl border border-border bg-surface">
                            {rows.length === 0 ? (
                              <p className="px-3 py-3 text-sm text-text-secondary">暂无样本数据。</p>
                            ) : (() => {
                              const sampleRows = rows.slice(0, 10).map((row) => asRecord(row) ?? {});
                              const columns = buildSampleTableColumns(sampleRows);
                              if (columns.length === 0) {
                                return <p className="px-3 py-3 text-sm text-text-secondary">暂无可展示字段。</p>;
                              }
                              return (
                                <table className="min-w-full divide-y divide-border text-left text-xs">
                                  <thead className="sticky top-0 z-10 bg-surface-secondary text-text-secondary">
                                    <tr>
                                      {columns.map((column) => (
                                        <th key={column} className="whitespace-nowrap px-3 py-2 font-medium">
                                          {column}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-border text-text-primary">
                                    {sampleRows.map((row, rowIndex) => (
                                      <tr key={`collection-sample-${rowIndex}`} className="hover:bg-surface-secondary/60">
                                        {columns.map((column) => (
                                          <td key={`${rowIndex}-${column}`} className="max-w-56 truncate px-3 py-2" title={formatSampleCellValue(row[column])}>
                                            {formatSampleCellValue(row[column])}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              );
                            })()}
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
    );
  };

  const renderReservedPanel = (kind: Extract<DataSourceKind, 'browser' | 'desktop_cli'>) => {
    const currentCard = SOURCE_TYPE_CARDS.find((item) => item.source_kind === kind);
    return (
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-text-primary">{currentCard?.title}</h3>
            <p className="mt-1 text-sm text-text-secondary">{currentCard?.description}</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-1.5 text-xs text-text-secondary">
            <Cpu className="h-3.5 w-3.5" />
            预留能力（Agent Assisted）
          </span>
        </div>
        <div className="mt-4 rounded-xl border border-dashed border-border px-4 py-8 text-sm text-text-secondary">
          该类型当前只保留扩展位。后续会接入 agent loop，由 agent 自主决策调用浏览器或客户端执行器抓取数据。
        </div>
      </div>
    );
  };

  const renderCollaborationPanel = () => {
    const rows = selectedProviderChannels;
    const providerCard = selectedChannelCard;
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-text-primary">{providerCard.title} 协作通道</h3>
              <p className="mt-1 text-sm text-text-secondary">{providerCard.description}</p>
            </div>
            <button
              type="button"
              onClick={() => createDraftChannel(selectedCollaborationProvider)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
            >
              <Plus className="h-4 w-4" />
              新增配置
            </button>
          </div>

          {channelApiAvailable === false && (
            <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              当前后端协作通道接口未接入，保存结果会先停留在前端本地草稿，不会写入服务端。
            </div>
          )}
          {channelError && (
            <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {channelError}
            </div>
          )}
          {channelNotice && (
            <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {channelNotice}
            </div>
          )}

          {rows.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
              当前协作通道还没有配置，可先新增默认通道。
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-sm">
                <thead className="bg-surface-secondary text-left text-text-secondary">
                  <tr>
                    <th className="px-4 py-3 font-medium">配置名称</th>
                    <th className="px-4 py-3 font-medium">通道编码</th>
                    <th className="px-4 py-3 font-medium">{providerCard.clientIdLabel}</th>
                    <th className="px-4 py-3 font-medium">状态</th>
                    <th className="px-4 py-3 font-medium">默认</th>
                    <th className="px-4 py-3 font-medium">更新时间</th>
                    <th className="px-4 py-3 font-medium text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((channel) => (
                    <tr key={channel.id} className="border-t border-border-subtle text-text-primary">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex h-7 w-7 items-center justify-center rounded-md ${providerCard.accent}`}>
                            {collaborationProviderIcon(channel.provider)}
                          </span>
                          <span>{channel.name || collaborationProviderLabel(channel.provider)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{channel.channel_code || 'default'}</td>
                      <td className="px-4 py-3 text-text-secondary">{channel.client_id || '未配置'}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-surface-accent px-2.5 py-1 text-xs font-medium text-blue-600">
                          {getStatusLabel(channelConfigStatus(channel))}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{channel.is_default ? '是' : '否'}</td>
                      <td className="px-4 py-3 text-text-secondary">{formatTime(channel.updated_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => startEditChannel(channel)}
                            className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary hover:bg-surface-tertiary transition-colors"
                          >
                            编辑
                          </button>
                          {draftChannelIdSet.has(channel.id) && (
                            <button
                              type="button"
                              onClick={() => removeDraftChannel(channel.id)}
                              className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 transition-colors"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              移除
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          {!editingChannel ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
              请选择一条协作通道配置进行编辑，或点击“新增配置”创建新的通道。
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm">
                  <span className="font-medium text-text-primary">通道名称</span>
                  <input
                    value={editingChannel.name}
                    onChange={(event) =>
                      setEditingChannel((prev) => (prev ? { ...prev, name: event.target.value } : prev))
                    }
                    className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                    placeholder={collaborationProviderCard(editingChannel.provider).defaultName}
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span className="font-medium text-text-primary">通道编码</span>
                  <input
                    value={editingChannel.channel_code}
                    onChange={(event) =>
                      setEditingChannel((prev) => (prev ? { ...prev, channel_code: event.target.value } : prev))
                    }
                    className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                    placeholder="default"
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span className="font-medium text-text-primary">{collaborationProviderCard(editingChannel.provider).clientIdLabel}</span>
                  <input
                    value={editingChannel.client_id}
                    onChange={(event) =>
                      setEditingChannel((prev) => (prev ? { ...prev, client_id: event.target.value } : prev))
                    }
                    className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                    placeholder="请输入"
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span className="font-medium text-text-primary">{collaborationProviderCard(editingChannel.provider).clientSecretLabel}</span>
                  <input
                    type="password"
                    value={editingChannel.client_secret}
                    onChange={(event) =>
                      setEditingChannel((prev) => (prev ? { ...prev, client_secret: event.target.value } : prev))
                    }
                    className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                    placeholder={editingChannel.isDraft ? '请输入' : '留空表示暂不修改'}
                  />
                </label>
              </div>

              <label className="space-y-2 text-sm block">
                <span className="font-medium text-text-primary">{collaborationProviderCard(editingChannel.provider).robotCodeLabel}</span>
                <input
                  value={editingChannel.robot_code}
                  onChange={(event) =>
                    setEditingChannel((prev) => (prev ? { ...prev, robot_code: event.target.value } : prev))
                  }
                  className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                  placeholder="可选"
                />
              </label>

              <label className="space-y-2 text-sm block">
                <span className="font-medium text-text-primary">扩展配置（JSON）</span>
                <textarea
                  value={editingChannel.extraText}
                  onChange={(event) =>
                    setEditingChannel((prev) => (prev ? { ...prev, extraText: event.target.value } : prev))
                  }
                  className="min-h-28 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 font-mono text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                  placeholder='例如：{"bot_scope":"internal"}'
                />
              </label>

              <div className="flex flex-wrap gap-5 text-sm text-text-secondary">
                <label className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={editingChannel.is_default}
                    onChange={(event) =>
                      setEditingChannel((prev) => (prev ? { ...prev, is_default: event.target.checked } : prev))
                    }
                  />
                  设为默认通道
                </label>
                <label className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={editingChannel.is_enabled}
                    onChange={(event) =>
                      setEditingChannel((prev) => (prev ? { ...prev, is_enabled: event.target.checked } : prev))
                    }
                  />
                  启用该通道
                </label>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void saveEditingChannel()}
                  disabled={savingChannel}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 transition-colors"
                >
                  {savingChannel ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  保存配置
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditingChannel(null);
                    setChannelError('');
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
                >
                  取消编辑
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderPlatformOverview = () => (
    <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-text-primary">平台授权</h3>
          <p className="mt-1 text-sm text-text-secondary">统一管理已接入平台的授权状态和店铺连接。</p>
        </div>
        {loadingPlatforms && (
          <span className="inline-flex items-center gap-2 text-xs text-text-secondary">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载中
          </span>
        )}
      </div>
      {platformError && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {platformError}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {platforms.map((platform) => (
          <div
            key={platform.platform_code}
            className="rounded-2xl border border-border bg-surface-secondary p-4 transition-shadow hover:shadow-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-text-primary">{platform.platform_name}</p>
                <p className="mt-1 text-xs text-text-muted">编码：{platform.platform_code}</p>
              </div>
              <Store className="h-4 w-4 shrink-0 text-text-muted" />
            </div>
            <div className="mt-3 space-y-1 text-xs text-text-secondary">
              <p>已授权店铺：{platform.authorized_shop_count ?? 0}</p>
              <p>异常店铺：{platform.error_shop_count ?? 0}</p>
              <p>最近同步：{formatTime(platform.last_sync_at)}</p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleSelectPlatform(platform)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                查看店铺
              </button>
              <button
                type="button"
                onClick={() => void launchAuthFlow(platform.platform_code)}
                disabled={launchingAuthPlatform === platform.platform_code}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
              >
                {launchingAuthPlatform === platform.platform_code ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Plus className="h-3.5 w-3.5" />
                )}
                新增授权
              </button>
            </div>
          </div>
        ))}
        {!loadingPlatforms && platforms.length === 0 && (
          <div className="col-span-full rounded-2xl border border-dashed border-border bg-surface-secondary p-10 text-center">
            <p className="text-sm text-text-secondary">暂无平台连接数据，请稍后重试。</p>
          </div>
        )}
      </div>
    </div>
  );

  const renderPlatformDetails = () =>
    selectedPlatform && (
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleBackToOverview}
              className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回平台总览
            </button>
            <h3 className="text-base font-semibold text-text-primary">{selectedPlatform.platform_name} 店铺列表</h3>
          </div>
          <button
            type="button"
            onClick={() => void launchAuthFlow(selectedPlatform.platform_code)}
            disabled={launchingAuthPlatform === selectedPlatform.platform_code}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {launchingAuthPlatform === selectedPlatform.platform_code ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            新增店铺授权
          </button>
        </div>
        <div className="mb-4 rounded-2xl border border-border bg-surface-secondary p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold text-text-primary">固定数据集</h4>
              <p className="mt-1 text-xs text-text-secondary">
                平台授权完成后，系统会自动生成可供规则绑定的数据集目录。
              </p>
            </div>
            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(selectedPlatform.status || (selectedPlatform.authorized_shop_count > 0 ? 'active' : 'pending'))}`}>
              {getStatusLabel(selectedPlatform.status || (selectedPlatform.authorized_shop_count > 0 ? 'active' : 'pending'))}
            </span>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {PLATFORM_FIXED_DATASET_FALLBACK.map((datasetName) => (
              <div key={datasetName} className="rounded-xl border border-border bg-surface px-3 py-3">
                <p className="text-sm font-medium text-text-primary">{datasetName}</p>
                <p className="mt-1 text-xs text-text-secondary">最近同步：{formatTime(selectedPlatform.last_sync_at)}</p>
              </div>
            ))}
          </div>
        </div>
        {shopError && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            {shopError}
          </div>
        )}
        {loadingShops ? (
          <div className="flex items-center justify-center rounded-xl border border-border-subtle bg-surface-secondary px-4 py-10 text-sm text-text-secondary">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载店铺列表
          </div>
        ) : shops.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
            当前平台暂无店铺授权记录。
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-secondary text-left text-text-secondary">
                <tr>
                  <th className="px-4 py-3 font-medium">店铺名称</th>
                  <th className="px-4 py-3 font-medium">店铺 ID</th>
                  <th className="px-4 py-3 font-medium">授权状态</th>
                  <th className="px-4 py-3 font-medium">Token 到期</th>
                  <th className="px-4 py-3 font-medium">最近同步</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {shops.map((shop) => (
                  <tr key={shop.id} className="border-t border-border-subtle text-text-primary">
                    <td className="px-4 py-3">{shop.external_shop_name}</td>
                    <td className="px-4 py-3 text-text-secondary">{shop.external_shop_id}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-full bg-surface-accent px-2.5 py-1 text-xs font-medium text-blue-600">
                        {getStatusLabel(shop.auth_status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{formatTime(shop.token_expires_at)}</td>
                    <td className="px-4 py-3 text-text-secondary">{formatTime(shop.last_sync_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => void handleReauthorize(shop)}
                          disabled={actioningShopId === shop.id}
                          className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary hover:bg-surface-tertiary disabled:opacity-60 transition-colors"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          重授权
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDisable(shop)}
                          disabled={actioningShopId === shop.id}
                          className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-60 transition-colors"
                        >
                          <Ban className="h-3.5 w-3.5" />
                          停用
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );

  const renderSelectedPanel = () => {
    if (selectedConnectionView === 'collaboration_channels') {
      return renderCollaborationPanel();
    }
    if (selectedSourceKind === 'platform_oauth') {
      if (mode === 'platform' && selectedPlatform) return renderPlatformDetails();
      return renderPlatformOverview();
    }
    if (selectedSourceKind === 'database' || selectedSourceKind === 'api' || selectedSourceKind === 'file') {
      return renderSourceList(selectedSourceKind);
    }
    return renderReservedPanel(selectedSourceKind);
  };

  if (!authToken) {
    return (
      <div className="flex-1 flex items-center justify-center bg-surface-secondary p-6">
        <div className="w-full max-w-xl rounded-2xl border border-border bg-surface p-8 text-center shadow-sm">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-accent text-blue-600">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <h2 className="text-xl font-semibold text-text-primary">登录后管理数据连接</h2>
          <p className="mt-2 text-sm text-text-secondary">
            数据连接用于统一管理数据源接入和公司级协作通道配置。
          </p>
        </div>
      </div>
    );
  }

  if (mode === 'callback' && callbackPayload) {
    const isSuccess = callbackPayload.status === 'success';
    return (
      <div className="flex-1 overflow-y-auto bg-surface-secondary p-6">
        <div className="mx-auto w-full max-w-3xl space-y-4">
          <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
            <div className="flex items-start gap-4">
              <div
                className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                  isSuccess ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-500'
                }`}
              >
                {isSuccess ? <CheckCircle2 className="h-5 w-5" /> : <AlertCircle className="h-5 w-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-xl font-semibold text-text-primary">授权完成页</h2>
                <p className="mt-1 text-sm text-text-secondary">
                  平台：{callbackPayload.platformCode}，状态：{getStatusLabel(callbackPayload.status)}
                </p>
                <p className="mt-3 rounded-xl bg-surface-secondary px-3 py-2 text-sm text-text-primary">
                  {callbackPayload.message || (isSuccess ? '授权成功，已记录店铺连接信息。' : '授权失败，请重新发起授权。')}
                </p>
                {callbackPayload.shopName && (
                  <p className="mt-2 text-sm text-text-secondary">店铺：{callbackPayload.shopName}</p>
                )}
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => {
                  clearCallbackQuery('data-connections');
                  setMode('overview');
                  setCallbackPayload(null);
                  void fetchPlatforms();
                  void fetchCollaborationChannels();
                }}
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
              >
                <Link2 className="h-4 w-4" />
                前往数据连接
              </button>
              {onBackToChat && (
                <button
                  type="button"
                  onClick={() => {
                    clearCallbackQuery('chat');
                    onBackToChat();
                  }}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
                >
                  返回对话
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-surface-secondary p-6">
      <div className="mx-auto w-full max-w-6xl space-y-4">
        <section className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${
                      selectedConnectionView === 'collaboration_channels'
                        ? selectedChannelCard.accent
                        : selectedSourceCard.accent
                    }`}
                  >
                    {selectedConnectionView === 'collaboration_channels'
                      ? collaborationProviderIcon(selectedCollaborationProvider)
                      : sourceKindIcon(selectedSourceCard.source_kind)}
                  </span>
                  <div>
                    <h3 className="text-base font-semibold text-text-primary">
                      {selectedConnectionView === 'collaboration_channels'
                        ? `${selectedChannelCard.title} 协作通道`
                        : selectedSourceCard.title}
                    </h3>
                    <p className="mt-1 text-sm text-text-secondary">
                      {selectedConnectionView === 'collaboration_channels'
                        ? selectedChannelCard.description
                        : selectedSourceCard.description}
                    </p>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {selectedConnectionView === 'data_sources' &&
                  ['database', 'api', 'file'].includes(selectedSourceKind) && (
                    <button
                      type="button"
                      onClick={() => void createDraftSource(selectedSourceKind as Extract<DataSourceKind, 'database' | 'api' | 'file'>)}
                      className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary transition-colors hover:bg-surface-tertiary"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      新增
                    </button>
                  )}
                <button
                  type="button"
                  onClick={() => {
                    if (selectedConnectionView === 'collaboration_channels') {
                      void fetchCollaborationChannels();
                      return;
                    }
                    if (mode === 'platform' && selectedPlatform) {
                      void fetchShops(selectedPlatform.platform_code);
                      return;
                    }
                    void fetchPlatforms();
                    void fetchRemoteSources();
                  }}
                  className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary transition-colors hover:bg-surface-tertiary"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  刷新
                </button>
                <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary">
                  {selectedConnectionView === 'collaboration_channels'
                    ? 'Company Scoped'
                    : executionModeLabel(selectedSourceCard.execution_mode)}
                </span>
                <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary">
                  当前 {selectedConnectionView === 'collaboration_channels' ? `${selectedProviderChannels.length} 个通道` : `${selectedKindSources.length} 个连接`}
                </span>
                {selectedConnectionView === 'collaboration_channels' && loadingChannels && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    刷新中
                  </span>
                )}
                {selectedConnectionView === 'data_sources' && selectedSourceKind !== 'platform_oauth' && loadingSources && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    刷新中
                  </span>
                )}
              </div>
            </div>
          </div>
          {renderSelectedPanel()}
        </section>
      </div>
    </div>
  );
}
