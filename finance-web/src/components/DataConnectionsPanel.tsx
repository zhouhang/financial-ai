import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  Ban,
  CalendarDays,
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
  X,
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
import { BrowserPlaybookPanel } from './BrowserPlaybookPanel';
import type {
  AuthCallbackPayload,
  BrowserVerificationSummary,
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
  DataSourcePreviewSample,
  PlatformConnectionSummary,
  PlatformCode,
  ShopConnection,
} from '../types';

type DataConnectionsMode = 'overview' | 'platform' | 'callback';

const DISPLAY_PLATFORM_CODES = new Set<string>(['taobao', 'alipay']);

interface DataConnectionsPanelProps {
  authToken?: string | null;
  initialCallback?: AuthCallbackPayload | null;
  onBackToChat?: () => void;
  onLoginRequired?: () => void;
  selectedConnectionView: DataConnectionView;
  selectedSourceKind: DataSourceKind;
  selectedCollaborationProvider: CollaborationProvider;
}

interface AuthSessionResponse {
  success?: boolean;
  auth_url?: string;
  message?: string;
  state?: string;
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

interface PlatformAppConfigFormState {
  appKey: string;
  appSecret: string;
  redirectUri: string;
  merchantAuthMode: string;
  merchantAuthPcUrl: string;
  merchantAuthQrUrl: string;
  appPublicCert: string;
  alipayPublicCert: string;
  alipayRootCert: string;
  hasAppSecret: boolean;
  hasAppPublicCert: boolean;
  hasAlipayPublicCert: boolean;
  hasAlipayRootCert: boolean;
  loading: boolean;
  saving: boolean;
  error: string;
  notice: string;
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

interface AlipayAuthDialogState {
  merchantDisplayName: string;
  authUrl: string;
  notice: string;
  error: string;
}

interface PlatformPendingAuthorization {
  id: string;
  platform_code: string;
  claim_code: string;
  status: string;
  app_id?: string;
  source?: string;
  external_shop_id?: string;
  external_seller_id?: string;
  merchant_display_name?: string;
  expires_at?: string | null;
  created_at?: string | null;
  last_error?: string;
}

interface AlipayClaimFormState {
  pendingAuthorizationId: string;
  claimCode: string;
  merchantDisplayName: string;
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
  publishStatus: string;
  uniqueIdentifierRawNames: string[];
  collectionDateField: string;
  collectionDateFormat: string;
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

interface DatasetDetailDialogState {
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

interface DateCollectionDialogState {
  sourceId: string;
  sourceName: string;
  datasetId: string;
  datasetName: string;
  resourceKey: string;
  dateField: string;
  selectedDate: string;
  submitting: boolean;
  error: string;
}

interface PlatformDatasetFieldGroup {
  key: string;
  label: string;
  defaultOpen: boolean;
  fields: Record<string, unknown>[];
}

interface PlatformDatasetCollectionStatus {
  status: string;
  message: string;
  canInitialize: boolean;
  canRetryInitialize: boolean;
  isRunning: boolean | null;
  latestJob: Record<string, unknown> | null;
  rowCount: number | null;
  totalCount: number | null;
  latestCollectionDate: string;
}

interface PlatformDatasetSemanticStatus {
  status: string;
  message: string;
  canRefresh: boolean;
  canRetry: boolean;
}

interface PlatformShopDatasetDetail {
  sourceId: string;
  source: DataSourceListItem;
  dataset: DataSourceDatasetSummary;
  collectionStatus: PlatformDatasetCollectionStatus;
  semanticStatus: PlatformDatasetSemanticStatus;
  fieldGroups: PlatformDatasetFieldGroup[];
  rows: Record<string, unknown>[];
  loading: boolean;
  error: string;
  loadedAt: string;
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

interface SampleTableColumn {
  rawName: string;
  displayName: string;
}

const ALIPAY_AUTH_COLLECTION_COPY =
  '一个支付宝商户授权后会生成资金账单和交易账单两个数据集，每天 10:30 采集 T-1 账单。';
const PLATFORM_COLLECTION_RUNNING_STATUSES = ['running', 'queued', 'pending', 'loading', 'initializing'];
const PLATFORM_SEMANTIC_RUNNING_STATUSES = ['running', 'queued', 'pending', 'loading', 'refreshing'];
const NON_PUBLISHABLE_SEMANTIC_RAW_NAMES = new Set(['raw', 'payload', 'meta', 'metadata']);

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') return null;
  return value as Record<string, unknown>;
}

function isPublishableDatasetSemanticRawName(rawName: string): boolean {
  const normalized = rawName.trim();
  const lower = normalized.toLowerCase();
  if (!normalized) return false;
  if (NON_PUBLISHABLE_SEMANTIC_RAW_NAMES.has(lower)) return false;
  return !lower.startsWith('raw.');
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

function buildSemanticSampleTableColumns(
  fieldGroups: PlatformDatasetFieldGroup[],
  rows: Record<string, unknown>[],
  maxColumns = 12,
): SampleTableColumn[] {
  const columns: SampleTableColumn[] = [];
  const seen = new Set<string>();
  const businessGroups = fieldGroups.filter((group) => group.key.trim().toLowerCase() !== 'system');

  businessGroups.forEach((group) => {
    group.fields.forEach((field) => {
      const rawName = rawFieldName(field).trim();
      if (!isPublishableDatasetSemanticRawName(rawName) || seen.has(rawName) || columns.length >= maxColumns) return;
      seen.add(rawName);
      columns.push({
        rawName,
        displayName: displayFieldName(field).trim() || rawName,
      });
    });
  });

  if (columns.length > 0) return columns;

  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!isPublishableDatasetSemanticRawName(key) || seen.has(key) || columns.length >= maxColumns) return;
      seen.add(key);
      columns.push({
        rawName: key,
        displayName: key,
      });
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

function platformDatasetStatusClass(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (['succeeded', 'success', 'completed', 'generated', 'generated_with_samples', 'ready'].includes(normalized)) {
    return 'bg-green-50 text-green-700';
  }
  if (['running', 'queued', 'pending', 'loading', 'initializing', 'refreshing'].includes(normalized)) {
    return 'bg-blue-50 text-blue-700';
  }
  if (['failed', 'error'].includes(normalized)) return 'bg-red-50 text-red-700';
  if (['missing', 'not_started', 'none'].includes(normalized)) return 'bg-amber-50 text-amber-700';
  return 'bg-surface-accent text-blue-600';
}

function isPlatformCollectionRunning(collectionStatus: PlatformDatasetCollectionStatus): boolean {
  if (collectionStatus.isRunning !== null) return collectionStatus.isRunning;
  return PLATFORM_COLLECTION_RUNNING_STATUSES.includes(collectionStatus.status.trim().toLowerCase());
}

function isPlatformSemanticRunning(semanticStatus: PlatformDatasetSemanticStatus): boolean {
  return PLATFORM_SEMANTIC_RUNNING_STATUSES.includes(semanticStatus.status.trim().toLowerCase());
}

function isPlatformStatusSucceeded(status: string): boolean {
  return ['succeeded', 'success', 'completed', 'generated', 'generated_with_samples', 'ready'].includes(
    status.trim().toLowerCase(),
  );
}

function isPlatformStatusFailed(status: string): boolean {
  return ['failed', 'error'].includes(status.trim().toLowerCase());
}

function platformDatasetCollectionLabel(detail: PlatformShopDatasetDetail): string {
  const status = detail.collectionStatus.status.trim().toLowerCase();
  const message = detail.collectionStatus.message.trim();
  const count = detail.collectionStatus.totalCount ?? detail.collectionStatus.rowCount;

  if (isPlatformStatusFailed(status)) {
    return `初始化失败：${message || '数据采集失败'}`;
  }
  if (isPlatformCollectionRunning(detail.collectionStatus)) return '初始化中';
  if (isPlatformStatusSucceeded(status)) {
    if (typeof count === 'number' && count > 0) return `初始化：已采集真实样本 ${count} 条`;
    return '初始化：已采集真实样本';
  }
  if (['missing', 'not_started', 'none'].includes(status)) return '未初始化';
  return `初始化：${message || detail.collectionStatus.status || '未知'}`;
}

function platformDatasetDailyCollectionLabel(detail: PlatformShopDatasetDetail): string {
  const date = detail.collectionStatus.latestCollectionDate.trim();
  const count = detail.collectionStatus.totalCount ?? detail.collectionStatus.rowCount;
  if (!date) return '';
  if (typeof count === 'number') return `每日采集：最近 ${date}，${count} 条`;
  return `每日采集：最近 ${date}`;
}

function canPublishPlatformDataset(detail: PlatformShopDatasetDetail): boolean {
  if (detail.loading || detail.error) return false;
  if (!isPlatformStatusSucceeded(detail.collectionStatus.status)) return false;
  if (!isPlatformStatusSucceeded(detail.semanticStatus.status)) return false;
  if (isPlatformCollectionRunning(detail.collectionStatus) || isPlatformSemanticRunning(detail.semanticStatus)) return false;
  const count = detail.collectionStatus.totalCount ?? detail.collectionStatus.rowCount ?? detail.rows.length;
  return count > 0;
}

function platformPublishButtonLabel(detail: PlatformShopDatasetDetail): string {
  return readDatasetPublishStatus(detail.dataset) === 'published' ? '管理发布' : '发布';
}

function displayFieldName(field: Record<string, unknown>): string {
  return (
    asString(field.display_name) ??
    asString(field.displayName) ??
    asString(field.label) ??
    asString(field.business_name) ??
    rawFieldName(field) ??
    '字段'
  );
}

function rawFieldName(field: Record<string, unknown>): string {
  return (
    asString(field.raw_name) ??
    asString(field.rawName) ??
    asString(field.field_name) ??
    asString(field.name) ??
    asString(field.key) ??
    ''
  );
}

function formatPreviewCell(value: unknown): string {
  const formatted = formatSampleCellValue(value);
  return formatted.length > 80 ? `${formatted.slice(0, 80)}...` : formatted;
}

function isCompactDatePartitionField(fieldName: string): boolean {
  return ['pt', 'dt', 'biz_dt', 'bizdate', 'biz_date_yyyymmdd', 'date_key'].includes(
    fieldName.trim().toLowerCase(),
  );
}

function normalizeCollectionDateFormat(value: unknown, fieldName = ''): string {
  const normalized = String(value ?? '').trim().toLowerCase().replaceAll('-', '_');
  if (['native', 'date', 'datetime', 'timestamp', 'iso', 'iso_date', 'iso_datetime', 'yyyy_mm_dd'].includes(normalized)) {
    return 'native';
  }
  if (['compact', 'yyyymmdd', 'compact_date', 'partition_date'].includes(normalized)) {
    return 'compact_date';
  }
  if (['yyyymmddhhmmss', 'compact_datetime'].includes(normalized)) {
    return 'compact_datetime';
  }
  if (['slash_date', 'yyyy/mm/dd'].includes(normalized)) {
    return 'slash_date';
  }
  if (['slash_datetime', 'yyyy/mm/dd hh:mm:ss'].includes(normalized)) {
    return 'slash_datetime';
  }
  if (['unix', 'unix_seconds', 'epoch_seconds'].includes(normalized)) {
    return 'unix_seconds';
  }
  if (['unix_millis', 'unix_milliseconds', 'epoch_millis'].includes(normalized)) {
    return 'unix_millis';
  }
  if (isCompactDatePartitionField(fieldName)) return 'compact_date';
  return 'native';
}

function inferCollectionDateFormat(fieldName: string, sampleValues: string[]): string {
  if (isCompactDatePartitionField(fieldName)) return 'compact_date';
  const samples = sampleValues.map((item) => item.trim()).filter(Boolean);
  const first = samples[0] ?? '';
  if (/^\d{8}$/.test(first)) return 'compact_date';
  if (/^\d{14}$/.test(first)) return 'compact_datetime';
  if (/^\d{4}\/\d{1,2}\/\d{1,2}$/.test(first)) return 'slash_date';
  if (/^\d{4}\/\d{1,2}\/\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?$/.test(first)) return 'slash_datetime';
  if (/^\d{13}$/.test(first)) return 'unix_millis';
  if (/^\d{10}$/.test(first)) return 'unix_seconds';
  return 'native';
}

function collectionDateFormatLabel(format: string): string {
  const normalized = normalizeCollectionDateFormat(format);
  if (normalized === 'compact_date') return 'YYYYMMDD 文本/分区字段';
  if (normalized === 'compact_datetime') return 'YYYYMMDDHHmmss 文本时间';
  if (normalized === 'slash_date') return 'YYYY/MM/DD 文本日期';
  if (normalized === 'slash_datetime') return 'YYYY/MM/DD HH:mm:ss 文本时间';
  if (normalized === 'unix_seconds') return 'Unix 秒时间戳';
  if (normalized === 'unix_millis') return 'Unix 毫秒时间戳';
  return '数据库日期/时间字段';
}

function readCollectionDateFieldFromDetail(
  detail: Record<string, unknown> | null | undefined,
  fallbackDataset?: DataSourceDatasetSummary,
): string {
  const detailDataset = asRecord(detail?.dataset);
  const detailMeta = asRecord(detailDataset?.meta);
  const detailCatalogProfile =
    asRecord(detailDataset?.catalog_profile) ?? asRecord(detailMeta?.catalog_profile);
  const detailCollectionConfig =
    asRecord(detailDataset?.collection_config) ??
    asRecord(detailMeta?.collection_config) ??
    asRecord(detailCatalogProfile?.collection_config);
  const fallbackDatasetRecord = asRecord(fallbackDataset);
  const fallbackMeta = asRecord(fallbackDataset?.meta);
  const fallbackCatalogProfile =
    asRecord(fallbackDatasetRecord?.catalog_profile) ?? asRecord(fallbackMeta?.catalog_profile);
  const fallbackCollectionConfig =
    asRecord(fallbackDataset?.collection_config) ??
    asRecord(fallbackMeta?.collection_config) ??
    asRecord(fallbackCatalogProfile?.collection_config);

  return (
    asString(detailCollectionConfig?.date_field) ||
    asString(detailCollectionConfig?.collection_date_field) ||
    asString(detailCollectionConfig?.physical_date_field) ||
    asString(fallbackCollectionConfig?.date_field) ||
    asString(fallbackCollectionConfig?.collection_date_field) ||
    asString(fallbackCollectionConfig?.physical_date_field) ||
    ''
  );
}

function formatCollectionFilterDisplay(dateField: string, bizDate: string, format = ''): string {
  const field = dateField.trim();
  const dateValue = bizDate.trim();
  const dateFormat = normalizeCollectionDateFormat(format, field);
  if (!field || !dateValue) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateValue)) {
    if (dateFormat === 'compact_date') {
      return `${field} = ${dateValue.replaceAll('-', '')}`;
    }
    if (dateFormat === 'compact_datetime') {
      const compactDate = dateValue.replaceAll('-', '');
      return `${field} >= ${compactDate}000000 且 < 下日 000000`;
    }
    if (dateFormat === 'slash_date') {
      const slashDate = dateValue.replaceAll('-', '/');
      return `${field} >= ${slashDate} 且 < 下一日`;
    }
    if (dateFormat === 'slash_datetime') {
      const slashDate = dateValue.replaceAll('-', '/');
      return `${field} >= ${slashDate} 00:00:00 且 < 下一日 00:00:00`;
    }
    if (dateFormat === 'unix_seconds') return `${field} >= 当日 00:00:00 秒时间戳 且 < 下一日`;
    if (dateFormat === 'unix_millis') return `${field} >= 当日 00:00:00 毫秒时间戳 且 < 下一日`;
    const nextDate = new Date(`${dateValue}T00:00:00`);
    if (!Number.isNaN(nextDate.getTime())) {
      nextDate.setDate(nextDate.getDate() + 1);
      return `${field} >= ${dateValue} 且 < ${nextDate.toISOString().slice(0, 10)}`;
    }
  }
  return `${field} = ${dateValue}`;
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
    keyFields: keyFields.map((item) => item.trim()).filter(isPublishableDatasetSemanticRawName),
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
  ).filter(isPublishableDatasetSemanticRawName);
  const semanticFieldMap = new Map<string, Record<string, unknown>>();
  semanticFields.forEach((field) => {
    const value = asRecord(field);
    const rawName = (asString(value?.raw_name) ?? asString(value?.name) ?? '').trim();
    if (!isPublishableDatasetSemanticRawName(rawName)) return;
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
    publishStatus: readDatasetPublishStatus(dataset),
    uniqueIdentifierRawNames,
    collectionDateField: asString(collectionConfig.date_field) ?? '',
    collectionDateFormat: normalizeCollectionDateFormat(collectionConfig.date_format, asString(collectionConfig.date_field) ?? ''),
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
  return ['platform_oauth', 'database', 'api', 'file', 'browser_playbook', 'browser', 'desktop_cli'].includes(value);
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
    preview_sample: (asRecord(value.preview_sample) ?? asRecord(asRecord(value.meta)?.preview_sample) ?? asRecord(asRecord(value.metadata)?.preview_sample) ?? undefined) as DataSourcePreviewSample | undefined,
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

function normalizePlatformFieldGroups(raw: unknown): PlatformDatasetFieldGroup[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      const value = asRecord(item);
      if (!value) return null;
      const key = asString(value.key) ?? asString(value.group_key) ?? '';
      const label = asString(value.label) ?? asString(value.name) ?? key;
      const fields = Array.isArray(value.fields)
        ? value.fields.filter((field): field is Record<string, unknown> => Boolean(asRecord(field)))
        : [];
      if (!key && !label && fields.length === 0) return null;
      return {
        key: key || label || 'fields',
        label: label || key || '字段',
        defaultOpen: asBoolean(value.default_open) ?? asBoolean(value.defaultOpen) ?? true,
        fields,
      };
    })
    .filter((item): item is PlatformDatasetFieldGroup => Boolean(item));
}

function normalizePlatformDetailDataset(
  raw: unknown,
  fallbackDataset: DataSourceDatasetSummary,
): DataSourceDatasetSummary {
  const value = asRecord(raw);
  if (!value) return fallbackDataset;
  const base = normalizeDataset(value) ?? fallbackDataset;
  const explicitDatasetCode = asString(value.dataset_code) ?? asString(value.datasetCode);
  const explicitDatasetName = asString(value.dataset_name) ?? asString(value.datasetName);

  return {
    ...base,
    id: asString(value.id) ?? base.id ?? fallbackDataset.id,
    data_source_id:
      asString(value.data_source_id) ??
      asString(value.dataSourceId) ??
      asString((base as DataSourceDatasetSummary & { data_source_id?: string }).data_source_id) ??
      asString((fallbackDataset as DataSourceDatasetSummary & { data_source_id?: string }).data_source_id),
    dataset_code:
      explicitDatasetCode ??
      fallbackDataset.dataset_code ??
      base.dataset_code,
    dataset_name:
      explicitDatasetName ??
      fallbackDataset.dataset_name ??
      base.dataset_name,
    resource_key:
      asString(value.resource_key) ??
      asString(value.resourceKey) ??
      base.resource_key ??
      fallbackDataset.resource_key ??
      fallbackDataset.dataset_code,
    business_name:
      asString(value.business_name) ??
      asString(value.businessName) ??
      base.business_name ??
      fallbackDataset.business_name,
    business_description:
      asString(value.business_description) ??
      asString(value.businessDescription) ??
      base.business_description ??
      fallbackDataset.business_description,
    publish_status:
      asString(value.publish_status) ??
      asString(value.publishStatus) ??
      base.publish_status ??
      fallbackDataset.publish_status,
    semantic_status:
      asString(value.semantic_status) ??
      asString(value.semanticStatus) ??
      base.semantic_status ??
      fallbackDataset.semantic_status,
    last_error_message:
      asStringOrNull(value.last_error_message) ??
      asStringOrNull(value.lastErrorMessage) ??
      base.last_error_message ??
      fallbackDataset.last_error_message,
    field_label_map:
      asStringRecord(value.field_label_map) ??
      asStringRecord(value.fieldLabelMap) ??
      base.field_label_map ??
      fallbackDataset.field_label_map,
    semantic_fields:
      (Array.isArray(value.semantic_fields)
        ? value.semantic_fields.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
        : undefined) ??
      (Array.isArray(value.semanticFields)
        ? value.semanticFields.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
        : undefined) ??
      base.semantic_fields ??
      fallbackDataset.semantic_fields,
  } as DataSourceDatasetSummary;
}

function normalizePlatformDatasetDetail(
  source: DataSourceListItem,
  dataset: DataSourceDatasetSummary,
  raw: unknown,
): PlatformShopDatasetDetail {
  const value = asRecord(raw) ?? {};
  const nextDataset = normalizePlatformDetailDataset(value.dataset, dataset);
  const collectionStatusRaw = asRecord(value.collection_status) ?? asRecord(value.collectionStatus) ?? {};
  const collectionStatsRaw = asRecord(value.collection_stats) ?? asRecord(value.collectionStats) ?? {};
  const semanticStatusRaw = asRecord(value.semantic_status) ?? asRecord(value.semanticStatus) ?? {};
  const latestJob = asRecord(collectionStatusRaw.latest_job) ?? asRecord(collectionStatusRaw.latestJob);
  const latestJobMetrics = asRecord(latestJob?.metrics) ?? {};
  const latestJobCheckpoint = asRecord(latestJob?.checkpoint_after) ?? asRecord(latestJob?.checkpointAfter) ?? {};
  const latestJobRequestPayload = asRecord(latestJob?.request_payload) ?? asRecord(latestJob?.requestPayload) ?? {};
  const rows = Array.isArray(value.rows)
    ? value.rows.filter((item): item is Record<string, unknown> => Boolean(asRecord(item))).slice(0, 20)
    : [];
  const rowCount =
    asNumber(collectionStatusRaw.row_count) ??
    asNumber(collectionStatusRaw.rowCount) ??
    asNumber(latestJobMetrics.row_count) ??
    null;
  const totalCount =
    asNumber(collectionStatusRaw.total_count) ??
    asNumber(collectionStatusRaw.totalCount) ??
    asNumber(collectionStatsRaw.total_count) ??
    asNumber(collectionStatsRaw.totalCount) ??
    asNumber(collectionStatsRaw.record_count) ??
    asNumber(collectionStatsRaw.recordCount) ??
    asNumber(latestJobCheckpoint.last_row_count) ??
    asNumber(latestJobCheckpoint.lastRowCount) ??
    asNumber(latestJobMetrics.collection_upserted) ??
    asNumber(latestJobMetrics.collectionUpserted) ??
    rowCount;
  const latestCollectionDate =
    asString(latestJobRequestPayload.bill_date) ??
    asString(latestJobRequestPayload.billDate) ??
    asString(latestJobRequestPayload.biz_date) ??
    asString(latestJobRequestPayload.bizDate) ??
    '';

  return {
    sourceId: source.id,
    source,
    dataset: nextDataset,
    collectionStatus: {
      status:
        asString(collectionStatusRaw.status) ??
        asString(collectionStatusRaw.state) ??
        asString(nextDataset.status) ??
        'unknown',
      message:
        asString(collectionStatusRaw.message) ??
        asString(collectionStatusRaw.error_message) ??
        '',
      canInitialize: asBoolean(collectionStatusRaw.can_initialize) ?? asBoolean(collectionStatusRaw.canInitialize) ?? false,
      canRetryInitialize:
        asBoolean(collectionStatusRaw.can_retry_initialize) ??
        asBoolean(collectionStatusRaw.canRetryInitialize) ??
        false,
      isRunning: asBoolean(collectionStatusRaw.is_running) ?? asBoolean(collectionStatusRaw.isRunning) ?? null,
      latestJob,
      rowCount,
      totalCount,
      latestCollectionDate,
    },
    semanticStatus: {
      status:
        asString(semanticStatusRaw.status) ??
        asString(nextDataset.semantic_status) ??
        asString(readDatasetSemanticRecord(nextDataset).status) ??
        'unknown',
      message:
        asString(semanticStatusRaw.message) ??
        asString(semanticStatusRaw.error_message) ??
        '',
      canRefresh: asBoolean(semanticStatusRaw.can_refresh) ?? asBoolean(semanticStatusRaw.canRefresh) ?? false,
      canRetry: asBoolean(semanticStatusRaw.can_retry) ?? asBoolean(semanticStatusRaw.canRetry) ?? false,
    },
    fieldGroups: normalizePlatformFieldGroups(value.field_groups ?? value.fieldGroups),
    rows,
    loading: false,
    error: '',
    loadedAt: new Date().toISOString(),
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

function normalizeBrowserVerification(raw: unknown): BrowserVerificationSummary | undefined {
  const value = asRecord(raw);
  if (!value) return undefined;
  return {
    sync_job_id: asString(value.sync_job_id),
    job_status: asString(value.job_status),
    browser_fail_reason: asString(value.browser_fail_reason),
    error_message: asString(value.error_message),
    updated_at: asStringOrNull(value.updated_at),
    completed_at: asStringOrNull(value.completed_at),
    is_verification: asBoolean(value.is_verification),
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
    browser_verification: normalizeBrowserVerification(value.browser_verification),
  };
}

function normalizePlatformSummary(raw: unknown): PlatformConnectionSummary | null {
  const value = asRecord(raw);
  if (!value) return null;
  const platformCode = normalizePlatformCode(asString(value.platform_code) ?? '');
  const platformName = platformCode === 'taobao' ? '淘宝/天猫' : asString(value.platform_name) ?? '';
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

function normalizePendingAuthorization(raw: unknown): PlatformPendingAuthorization | null {
  const value = asRecord(raw);
  if (!value) return null;
  const id = asString(value.id) ?? asString(value.pending_authorization_id) ?? '';
  if (!id) return null;
  return {
    id,
    platform_code: asString(value.platform_code) ?? 'alipay',
    claim_code: asString(value.claim_code) ?? '',
    status: asString(value.status) ?? 'pending_claim',
    app_id: asString(value.app_id),
    source: asString(value.source),
    external_shop_id: asString(value.external_shop_id),
    external_seller_id: asString(value.external_seller_id),
    merchant_display_name: asString(value.merchant_display_name),
    expires_at: asString(value.expires_at),
    created_at: asString(value.created_at),
    last_error: asString(value.last_error),
  };
}

function normalizePlatformCode(platformCode: string): PlatformCode {
  return platformCode === 'tmall' ? 'taobao' : platformCode;
}

function defaultPlatformRedirectUri(platformCode: PlatformCode): string {
  if (platformCode === 'taobao') return 'https://tally.example.com/api/platform-auth/callback/taobao';
  if (platformCode === 'alipay') return 'https://tally.example.com/api/platform-auth/callback/alipay';
  return '';
}

function createPlatformAppConfigFormState(platformCode: PlatformCode): PlatformAppConfigFormState {
  return {
    appKey: '',
    appSecret: '',
    redirectUri: defaultPlatformRedirectUri(platformCode),
    merchantAuthMode: 'static_invite',
    merchantAuthPcUrl: '',
    merchantAuthQrUrl: '',
    appPublicCert: '',
    alipayPublicCert: '',
    alipayRootCert: '',
    hasAppSecret: false,
    hasAppPublicCert: false,
    hasAlipayPublicCert: false,
    hasAlipayRootCert: false,
    loading: false,
    saving: false,
    error: '',
    notice: '',
  };
}

function platformConnectionListHeading(platformCode: PlatformCode): string {
  const normalizedPlatformCode = normalizePlatformCode(platformCode);
  if (normalizedPlatformCode === 'alipay') return '支付宝商户列表';
  if (normalizedPlatformCode === 'taobao') return '淘宝/天猫 店铺列表';
  return '店铺列表';
}

function latestPlatformSyncAt(left?: string | null, right?: string | null): string | null {
  if (!left) return right ?? null;
  if (!right) return left ?? null;
  const leftTime = new Date(left).getTime();
  const rightTime = new Date(right).getTime();
  if (Number.isNaN(leftTime)) return right;
  if (Number.isNaN(rightTime)) return left;
  return rightTime > leftTime ? right : left;
}

function mergePlatformSummaries(platforms: PlatformConnectionSummary[]): PlatformConnectionSummary[] {
  const merged = new Map<string, PlatformConnectionSummary>();
  const order: string[] = [];
  platforms
    .filter((platform) => DISPLAY_PLATFORM_CODES.has(normalizePlatformCode(platform.platform_code)))
    .forEach((platform) => {
      const platformCode = normalizePlatformCode(platform.platform_code);
      const normalized: PlatformConnectionSummary = {
        ...platform,
        platform_code: platformCode,
        platform_name: platformCode === 'taobao' ? '淘宝/天猫' : platform.platform_name,
      };
      const existing = merged.get(platformCode);
      if (!existing) {
        merged.set(platformCode, normalized);
        order.push(platformCode);
        return;
      }
      merged.set(platformCode, {
        ...existing,
        platform_name: existing.platform_name || normalized.platform_name,
        authorized_shop_count:
          (existing.authorized_shop_count ?? 0) + (normalized.authorized_shop_count ?? 0),
        error_shop_count: (existing.error_shop_count ?? 0) + (normalized.error_shop_count ?? 0),
        last_sync_at: latestPlatformSyncAt(existing.last_sync_at, normalized.last_sync_at),
        status: existing.status || normalized.status,
      });
    });
  return order.map((platformCode) => merged.get(platformCode)).filter(Boolean) as PlatformConnectionSummary[];
}

function sourceKindIcon(kind: DataSourceKind) {
  if (kind === 'platform_oauth') return <Store className="h-4 w-4" />;
  if (kind === 'database') return <Database className="h-4 w-4" />;
  if (kind === 'api') return <Globe className="h-4 w-4" />;
  if (kind === 'file') return <FileSpreadsheet className="h-4 w-4" />;
  if (kind === 'browser_playbook' || kind === 'browser') return <MonitorSmartphone className="h-4 w-4" />;
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
  onLoginRequired,
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
  const [shopNotice, setShopNotice] = useState<string>('');
  const [platformAppConfigs, setPlatformAppConfigs] = useState<Record<string, PlatformAppConfigFormState>>({});
  const [actioningShopId, setActioningShopId] = useState<string | null>(null);
  const [disableConfirmShop, setDisableConfirmShop] = useState<ShopConnection | null>(null);
  const [expandedShopDatasetId, setExpandedShopDatasetId] = useState<string | null>(null);
  const [shopDatasetDetails, setShopDatasetDetails] = useState<Record<string, PlatformShopDatasetDetail[]>>({});
  const [shopDatasetActionError, setShopDatasetActionError] = useState('');
  const [callbackPayload, setCallbackPayload] = useState<AuthCallbackPayload | null>(initialCallback);
  const [launchingAuthPlatform, setLaunchingAuthPlatform] = useState<PlatformCode | null>(null);
  const [alipayAuthDialog, setAlipayAuthDialog] = useState<AlipayAuthDialogState | null>(null);
  const [uploadingAlipayMerchantQr, setUploadingAlipayMerchantQr] = useState(false);
  const [alipayClaimForm, setAlipayClaimForm] = useState<AlipayClaimFormState>({
    pendingAuthorizationId: '',
    claimCode: initialCallback?.claimCode ?? '',
    merchantDisplayName: initialCallback?.shopName ?? '',
  });
  const [claimingAlipayAuthorization, setClaimingAlipayAuthorization] = useState(false);
  const [alipayClaimError, setAlipayClaimError] = useState('');
  const [alipayClaimNotice, setAlipayClaimNotice] = useState('');
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
  const [platformDatasetCollectionActionIds, setPlatformDatasetCollectionActionIds] = useState<Set<string>>(
    () => new Set(),
  );
  const platformDatasetCollectionActionIdsRef = useRef<Set<string>>(new Set());
  const [collectionDetailDialog, setCollectionDetailDialog] = useState<DatasetCollectionDetailDialogState | null>(null);
  const [datasetDetailDialog, setDatasetDetailDialog] = useState<DatasetDetailDialogState | null>(null);
  const [dateCollectionDialog, setDateCollectionDialog] = useState<DateCollectionDialogState | null>(null);
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
  const [editingPlatformAppCode, setEditingPlatformAppCode] = useState<PlatformCode | null>(null);
  const [browserCreateSignal, setBrowserCreateSignal] = useState(0);

  const openAlipayAuthDialog = useCallback((merchantDisplayName = '') => {
    setAlipayAuthDialog({
      merchantDisplayName,
      authUrl: '',
      notice: '',
      error: '',
    });
  }, []);

  useEffect(() => {
    if (!initialCallback) return;
    setCallbackPayload(initialCallback);
    setMode('callback');
    if (initialCallback.claimCode) {
      setAlipayClaimForm((current) => ({
        ...current,
        claimCode: initialCallback.claimCode || current.claimCode,
        pendingAuthorizationId: initialCallback.pendingAuthorizationId || current.pendingAuthorizationId,
        merchantDisplayName: initialCallback.shopName || current.merchantDisplayName,
      }));
    }
  }, [initialCallback]);

  useEffect(() => {
    if (mode === 'callback') return;
    setMode('overview');
    setSelectedPlatform(null);
    setEditingPlatformAppCode(null);
    setSelectedSourceId(null);
    setDatabaseDetailSourceId(null);
    setPhysicalDetailDialog(null);
    setDatasetActionError('');
    setDatasetActionNotice('');
    setShops([]);
    setShopError('');
    setExpandedShopDatasetId(null);
    setShopDatasetDetails({});
    setShopDatasetActionError('');
    setAlipayClaimError('');
    setAlipayClaimNotice('');
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
        const payload = data as Record<string, unknown>;
        const user = asRecord(payload?.user);
        const role =
          asString(payload?.role) ??
          asString(payload?.user_role) ??
          asString(user?.role) ??
          '';
        setCurrentUserRole((role || '').trim().toLowerCase());
      } catch {
        if (!cancelled) {
          setCurrentUserRole('');
        }
      }
    };
    void loadRole();
    return () => {
      cancelled = true;
    };
  }, [authHeaders, authToken]);

  const canManageServiceProviderApps = useMemo(
    () => ['admin', 'owner', 'super_admin'].includes(currentUserRole),
    [currentUserRole],
  );

  useEffect(() => {
    saveCollaborationChannelDrafts(draftChannels);
  }, [draftChannels]);

  const fetchPlatforms = useCallback(async () => {
    if (!authToken) return;
    setLoadingPlatforms(true);
    setPlatformError('');
    try {
      const response = await fetch('/api/platform-connections?mode=real', {
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
      setPlatforms(
        mergePlatformSummaries(
          list.map((item: unknown) => normalizePlatformSummary(item)).filter(Boolean) as PlatformConnectionSummary[],
        ),
      );
    } catch (error) {
      setPlatforms([]);
      setPlatformError(error instanceof Error ? error.message : '加载平台连接失败');
    } finally {
      setLoadingPlatforms(false);
    }
  }, [authHeaders, authToken]);

  const fetchRemoteSources = useCallback(async (): Promise<DataSourceListItem[]> => {
    if (!authToken) return [];
    setLoadingSources(true);
    setSourcesError('');
    try {
      const response = await fetch('/api/data-sources', {
        method: 'GET',
        headers: authHeaders,
      });
      if (response.status === 404 || response.status === 405 || response.status === 501) {
        setRemoteSources([]);
        return [];
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
      const nextSources = list
        .map((item: unknown) => normalizeSourceItem(item))
        .filter(Boolean) as DataSourceListItem[];
      setRemoteSources(nextSources);
      return nextSources;
    } catch (error) {
      setRemoteSources([]);
      setSourcesError(error instanceof Error ? error.message : '加载数据源列表失败');
      return [];
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
        if (
          patch.keyword !== undefined ||
          patch.schema !== undefined ||
          patch.objectType !== undefined ||
          patch.pageSize !== undefined
        ) {
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
    async (platformCode: PlatformCode): Promise<ShopConnection[]> => {
      if (!authToken) return [];
      setLoadingShops(true);
      setShopError('');
      setShopNotice('');
      try {
        const normalizedPlatformCode = normalizePlatformCode(platformCode);
        const response = await fetch(`/api/platform-connections/${normalizedPlatformCode}/shops?mode=real`, {
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
        const nextShops = list as ShopConnection[];
        setShops(nextShops);
        return nextShops;
      } catch (error) {
        setShops([]);
        setShopError(error instanceof Error ? error.message : '加载店铺列表失败');
        return [];
      } finally {
        setLoadingShops(false);
      }
    },
    [authHeaders, authToken],
  );

  const fetchAlipayPendingAuthorizations = useCallback(async (): Promise<PlatformPendingAuthorization[]> => {
    if (!authToken) return [];
    setAlipayClaimError('');
    try {
      const response = await fetch('/api/platform-connections/alipay/pending-authorizations?status=pending_claim&mode=real', {
        method: 'GET',
        headers: authHeaders,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '加载支付宝待绑定授权失败'));
      }
      const rows = Array.isArray(data?.pending_authorizations)
        ? data.pending_authorizations
        : Array.isArray(data?.items)
        ? data.items
        : [];
      const pendingAuthorizations = rows
        .map((item: unknown) => normalizePendingAuthorization(item))
        .filter(Boolean) as PlatformPendingAuthorization[];
      if (pendingAuthorizations.length > 0) {
        setAlipayClaimForm((current) => {
          if (current.pendingAuthorizationId || current.claimCode) return current;
          return {
            ...current,
            pendingAuthorizationId: pendingAuthorizations[0].id,
            claimCode: pendingAuthorizations[0].claim_code,
          };
        });
      }
      return pendingAuthorizations;
    } catch (error) {
      setAlipayClaimError(error instanceof Error ? error.message : '加载支付宝待绑定授权失败');
      return [];
    }
  }, [authHeaders, authToken]);

  useEffect(() => {
    if (!authToken || !callbackPayload) return;
    if (callbackPayload.platformCode !== 'alipay' || callbackPayload.status !== 'success') return;
    if (callbackPayload.pendingAuthorizationId && callbackPayload.claimCode) return;

    setSelectedPlatform({
      platform_code: 'alipay',
      platform_name: '支付宝',
      authorized_shop_count: 0,
      error_shop_count: 0,
    });
    setMode('platform');
    setShopNotice(callbackPayload.message || '支付宝授权已完成，请查看绑定结果。');
    clearCallbackQuery('data-connections');
    void fetchShops('alipay');
  }, [authToken, callbackPayload, clearCallbackQuery, fetchShops]);

  const claimAlipayPendingAuthorization = useCallback(async () => {
    if (!authToken) return;
    const pendingId = alipayClaimForm.pendingAuthorizationId.trim();
    const claimCode = alipayClaimForm.claimCode.trim();
    const merchantDisplayName = alipayClaimForm.merchantDisplayName.trim();
    if (!pendingId) {
      setAlipayClaimError('请选择待绑定授权');
      return;
    }
    if (!claimCode) {
      setAlipayClaimError('待绑定授权缺少校验信息，请刷新后重试');
      return;
    }
    if (!merchantDisplayName) {
      setAlipayClaimError('请输入支付宝商户名称');
      return;
    }
    setClaimingAlipayAuthorization(true);
    setAlipayClaimError('');
    setAlipayClaimNotice('');
    try {
      const response = await fetch(`/api/platform-connections/alipay/pending-authorizations/${encodeURIComponent(pendingId)}/claim`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          claim_code: claimCode,
          merchant_display_name: merchantDisplayName,
          mode: 'real',
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '绑定支付宝授权失败'));
      }
      setAlipayClaimNotice(String(data?.message || '支付宝商户授权已绑定'));
      setAlipayClaimForm({ pendingAuthorizationId: '', claimCode: '', merchantDisplayName: '' });
      setSelectedPlatform({
        platform_code: 'alipay',
        platform_name: '支付宝',
        authorized_shop_count: 1,
        error_shop_count: 0,
        status: 'active',
      });
      setMode('platform');
      setCallbackPayload(null);
      clearCallbackQuery('data-connections');
      await Promise.all([
        fetchShops('alipay'),
        fetchPlatforms(),
        fetchRemoteSources(),
      ]);
    } catch (error) {
      setAlipayClaimError(error instanceof Error ? error.message : '绑定支付宝授权失败');
    } finally {
      setClaimingAlipayAuthorization(false);
    }
  }, [
    alipayClaimForm,
    authHeaders,
    authToken,
    fetchPlatforms,
    fetchRemoteSources,
    fetchShops,
  ]);

  const fillAlipayClaimFormFromCallback = useCallback((payload: AuthCallbackPayload) => {
    setAlipayClaimForm((current) => ({
      ...current,
      claimCode: payload.claimCode || current.claimCode,
      pendingAuthorizationId: payload.pendingAuthorizationId || current.pendingAuthorizationId,
      merchantDisplayName: payload.shopName || current.merchantDisplayName,
    }));
  }, []);

  const updatePlatformAppConfig = useCallback(
    (
      platformCode: PlatformCode,
      updater: (current: PlatformAppConfigFormState) => PlatformAppConfigFormState,
    ) => {
      const normalizedPlatformCode = normalizePlatformCode(platformCode);
      setPlatformAppConfigs((prev) => {
        const current = prev[normalizedPlatformCode] ?? createPlatformAppConfigFormState(normalizedPlatformCode);
        return {
          ...prev,
          [normalizedPlatformCode]: updater(current),
        };
      });
    },
    [],
  );

  const fetchPlatformAppConfig = useCallback(
    async (platformCode: PlatformCode) => {
      if (!authToken) return;
      const normalizedPlatformCode = normalizePlatformCode(platformCode);
      updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
        ...current,
        loading: true,
        error: '',
        notice: '',
      }));
      try {
        const response = await fetch(`/api/platform-connections/${normalizedPlatformCode}/app-config?mode=real`, {
          method: 'GET',
          headers: authHeaders,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载平台应用配置失败'));
        }
        const config = data?.config && typeof data.config === 'object' ? data.config : {};
        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
          ...current,
          appKey: String(config.app_key || ''),
          appSecret: '',
          redirectUri: String(config.redirect_uri || '') || defaultPlatformRedirectUri(normalizedPlatformCode),
          merchantAuthMode: String(config.merchant_auth_mode || 'static_invite'),
          merchantAuthPcUrl: String(config.merchant_auth_pc_url || ''),
          merchantAuthQrUrl: String(config.merchant_auth_qr_url || ''),
          appPublicCert: '',
          alipayPublicCert: '',
          alipayRootCert: '',
          hasAppSecret: Boolean(config.has_app_secret),
          hasAppPublicCert: Boolean(config.has_app_public_cert),
          hasAlipayPublicCert: Boolean(config.has_alipay_public_cert),
          hasAlipayRootCert: Boolean(config.has_alipay_root_cert),
          loading: false,
          error: '',
          notice: '',
        }));
      } catch (error) {
        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : '加载平台应用配置失败',
        }));
      }
    },
    [authHeaders, authToken, updatePlatformAppConfig],
  );

  const savePlatformAppConfig = useCallback(
    async (platformCode: PlatformCode) => {
      if (!authToken) return;
      const normalizedPlatformCode = normalizePlatformCode(platformCode);
      const form = platformAppConfigs[normalizedPlatformCode] ?? createPlatformAppConfigFormState(normalizedPlatformCode);
      updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
        ...current,
        saving: true,
        error: '',
        notice: '',
      }));
      try {
        const body: Record<string, string> = {
          app_key: form.appKey.trim(),
          app_secret: form.appSecret.trim(),
          redirect_uri: form.redirectUri.trim(),
          app_public_cert: form.appPublicCert.trim(),
          alipay_public_cert: form.alipayPublicCert.trim(),
          alipay_root_cert: form.alipayRootCert.trim(),
          mode: 'real',
        };
        if (normalizedPlatformCode === 'alipay') {
          body.merchant_auth_mode = form.merchantAuthMode.trim() || 'static_invite';
          body.merchant_auth_pc_url = form.merchantAuthPcUrl.trim();
          body.merchant_auth_qr_url = form.merchantAuthQrUrl.trim();
        }
        const response = await fetch(`/api/platform-connections/${normalizedPlatformCode}/app-config`, {
          method: 'PUT',
          headers: authHeaders,
          body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '保存平台应用配置失败'));
        }
        const config = data?.config && typeof data.config === 'object' ? data.config : {};
        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
          ...current,
          appKey: String(config.app_key || form.appKey),
          appSecret: '',
          redirectUri: String(config.redirect_uri || form.redirectUri),
          merchantAuthMode: String(config.merchant_auth_mode || form.merchantAuthMode || 'static_invite'),
          merchantAuthPcUrl: String(config.merchant_auth_pc_url || form.merchantAuthPcUrl),
          merchantAuthQrUrl: String(config.merchant_auth_qr_url || form.merchantAuthQrUrl),
          appPublicCert: '',
          alipayPublicCert: '',
          alipayRootCert: '',
          hasAppSecret: Boolean(config.has_app_secret) || Boolean(form.appSecret.trim()),
          hasAppPublicCert: Boolean(config.has_app_public_cert) || Boolean(form.appPublicCert.trim()),
          hasAlipayPublicCert: Boolean(config.has_alipay_public_cert) || Boolean(form.alipayPublicCert.trim()),
          hasAlipayRootCert: Boolean(config.has_alipay_root_cert) || Boolean(form.alipayRootCert.trim()),
          saving: false,
          error: '',
          notice: String(data?.message || '平台应用配置已保存。'),
        }));
      } catch (error) {
        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
          ...current,
          saving: false,
          error: error instanceof Error ? error.message : '保存平台应用配置失败',
        }));
      }
    },
    [authHeaders, authToken, platformAppConfigs, updatePlatformAppConfig],
  );

  const uploadAlipayMerchantQr = useCallback(
    async (file: File | null) => {
      if (!authToken || !file) return;
      if (file.size > 2 * 1024 * 1024) {
        updatePlatformAppConfig('alipay', (current) => ({
          ...current,
          error: '二维码图片不能超过 2MB',
          notice: '',
        }));
        return;
      }
      const allowedTypes = new Set(['image/png', 'image/jpeg', 'image/webp']);
      if (file.type && !allowedTypes.has(file.type)) {
        updatePlatformAppConfig('alipay', (current) => ({
          ...current,
          error: '仅支持 png、jpg、jpeg、webp 二维码图片',
          notice: '',
        }));
        return;
      }
      setUploadingAlipayMerchantQr(true);
      updatePlatformAppConfig('alipay', (current) => ({
        ...current,
        error: '',
        notice: '',
      }));
      try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/platform-connections/alipay/app-config/merchant-auth-qr', {
          method: 'POST',
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
          body: formData,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '上传支付宝商家授权二维码失败'));
        }
        const config = data?.config && typeof data.config === 'object' ? data.config : {};
        const qrUrl = String(data?.merchant_auth_qr_url || config.merchant_auth_qr_url || '');
        updatePlatformAppConfig('alipay', (current) => ({
          ...current,
          appKey: String(config.app_key || current.appKey),
          merchantAuthQrUrl: qrUrl || current.merchantAuthQrUrl,
          hasAppSecret: Boolean(config.has_app_secret) || current.hasAppSecret,
          hasAppPublicCert: Boolean(config.has_app_public_cert) || current.hasAppPublicCert,
          hasAlipayPublicCert: Boolean(config.has_alipay_public_cert) || current.hasAlipayPublicCert,
          hasAlipayRootCert: Boolean(config.has_alipay_root_cert) || current.hasAlipayRootCert,
          error: '',
          notice: String(data?.message || '支付宝商家授权二维码已上传'),
        }));
      } catch (error) {
        updatePlatformAppConfig('alipay', (current) => ({
          ...current,
          error: error instanceof Error ? error.message : '上传支付宝商家授权二维码失败',
          notice: '',
        }));
      } finally {
        setUploadingAlipayMerchantQr(false);
      }
    },
    [authToken, updatePlatformAppConfig],
  );

  const renderServiceProviderAppStatus = useCallback(
    (appConfig: PlatformAppConfigFormState) => {
      if (appConfig.loading) {
        return (
          <span className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载中
          </span>
        );
      }
      if (appConfig.error) {
        return <span className="text-xs text-red-600">{appConfig.error}</span>;
      }
      if (appConfig.appKey && appConfig.hasAppSecret) {
        return <span className="text-xs text-green-700">Tally 服务商应用已配置</span>;
      }
      return <span className="text-xs text-amber-700">Tally 服务商应用待配置</span>;
    },
    [],
  );

  const renderServiceProviderAppConfigPanel = () => {
    if (!editingPlatformAppCode || !canManageServiceProviderApps) return null;
    const normalizedPlatformCode = normalizePlatformCode(editingPlatformAppCode);
    const appConfig =
      platformAppConfigs[normalizedPlatformCode] ??
      createPlatformAppConfigFormState(normalizedPlatformCode);
    const isAlipayConfig = normalizedPlatformCode === 'alipay';
    const appKeyLabel = isAlipayConfig ? 'AppID' : 'AppKey';
    const appSecretLabel = isAlipayConfig ? '应用私钥' : 'AppSecret';
    const redirectLabel = isAlipayConfig ? '授权回调地址' : '回调地址';

    return (
      <div
        className="fixed inset-0 z-40 bg-black/35"
        onClick={() => setEditingPlatformAppCode(null)}
      >
        <div
          className="ml-auto flex h-full w-full max-w-xl flex-col border-l border-border bg-surface shadow-2xl"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="border-b border-border px-5 py-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-base font-semibold text-text-primary">服务商应用配置</h4>
                <p className="mt-1 text-sm text-text-secondary">配置平台服务商应用参数。</p>
              </div>
              <button
                type="button"
                onClick={() => setEditingPlatformAppCode(null)}
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-5">
            <div className="space-y-4">
              <div className="inline-flex rounded-xl border border-border bg-surface-secondary p-1">
                {([
                  ['taobao', '淘宝/天猫'],
                  ['alipay', '支付宝'],
                ] as Array<[PlatformCode, string]>).map(([platformCode, label]) => {
                  const isActive = normalizedPlatformCode === platformCode;
                  return (
                    <button
                      key={platformCode}
                      type="button"
                      onClick={() => {
                        setEditingPlatformAppCode(platformCode);
                        void fetchPlatformAppConfig(platformCode);
                      }}
                      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                        isActive
                          ? 'bg-surface text-text-primary shadow-sm'
                          : 'text-text-secondary hover:text-text-primary'
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              {appConfig.error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {appConfig.error}
                </div>
              )}
              {appConfig.notice && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {appConfig.notice}
                </div>
              )}
              {appConfig.loading ? (
                <div className="flex items-center gap-2 rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm text-text-secondary">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在加载应用配置
                </div>
              ) : (
                <>
                  <label className="block text-sm font-medium text-text-primary">
                    {appKeyLabel}
                    <input
                      type="text"
                      value={appConfig.appKey}
                      onChange={(event) =>
                        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                          ...current,
                          appKey: event.target.value,
                          notice: '',
                        }))
                      }
                      className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                      placeholder={isAlipayConfig ? '支付宝开放平台 AppID' : '淘宝开放平台 AppKey'}
                    />
                  </label>
                  <label className="block text-sm font-medium text-text-primary">
                    {appSecretLabel}
                    <textarea
                      value={appConfig.appSecret}
                      onChange={(event) =>
                        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                          ...current,
                          appSecret: event.target.value,
                          notice: '',
                        }))
                      }
                      className="mt-2 min-h-24 w-full resize-y rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                      placeholder={
                        isAlipayConfig
                          ? appConfig.hasAppSecret
                            ? '留空则沿用已保存应用私钥'
                            : '粘贴应用私钥 PEM 内容'
                          : appConfig.hasAppSecret
                            ? '留空则沿用已保存密钥'
                            : '淘宝开放平台 AppSecret'
                      }
                    />
                  </label>
                  {isAlipayConfig && (
                    <>
                      <label className="block text-sm font-medium text-text-primary">
                        商家授权 PC 链接
                        <input
                          type="url"
                          value={appConfig.merchantAuthPcUrl}
                          onChange={(event) =>
                            updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                              ...current,
                              merchantAuthPcUrl: event.target.value,
                              notice: '',
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="支付宝开放平台商家授权 PC 链接"
                        />
                      </label>
                      <div className="block text-sm font-medium text-text-primary">
                        商家授权二维码
                        <div className="mt-2 flex flex-wrap items-center gap-3">
                          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary">
                            {uploadingAlipayMerchantQr ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <FileSpreadsheet className="h-4 w-4" />
                            )}
                            {uploadingAlipayMerchantQr ? '上传中' : '上传二维码图片'}
                            <input
                              type="file"
                              accept="image/png,image/jpeg,image/webp"
                              className="sr-only"
                              disabled={uploadingAlipayMerchantQr}
                              onChange={(event) => {
                                void uploadAlipayMerchantQr(event.target.files?.[0] ?? null);
                                event.target.value = '';
                              }}
                            />
                          </label>
                          <span className="text-xs text-text-secondary">支持 png、jpg、webp，最大 2MB</span>
                        </div>
                        {appConfig.merchantAuthQrUrl ? (
                          <img
                            src={appConfig.merchantAuthQrUrl}
                            alt="已上传支付宝商家授权二维码"
                            className="mt-3 h-28 w-28 rounded-lg border border-border bg-white object-contain"
                          />
                        ) : (
                          <p className="mt-2 text-xs text-text-secondary">尚未上传二维码图片。</p>
                        )}
                      </div>
                      <label className="block text-sm font-medium text-text-primary">
                        应用公钥证书
                        <textarea
                          value={appConfig.appPublicCert}
                          onChange={(event) =>
                            updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                              ...current,
                              appPublicCert: event.target.value,
                              notice: '',
                            }))
                          }
                          className="mt-2 min-h-24 w-full resize-y rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder={
                            appConfig.hasAppPublicCert
                              ? '留空则沿用已保存应用公钥证书'
                              : '粘贴 appCertPublicKey_*.crt 内容'
                          }
                        />
                      </label>
                      <label className="block text-sm font-medium text-text-primary">
                        支付宝公钥证书
                        <textarea
                          value={appConfig.alipayPublicCert}
                          onChange={(event) =>
                            updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                              ...current,
                              alipayPublicCert: event.target.value,
                              notice: '',
                            }))
                          }
                          className="mt-2 min-h-24 w-full resize-y rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder={
                            appConfig.hasAlipayPublicCert
                              ? '留空则沿用已保存支付宝公钥证书'
                              : '粘贴 alipayCertPublicKey_RSA2.crt 内容'
                          }
                        />
                      </label>
                      <label className="block text-sm font-medium text-text-primary">
                        支付宝根证书
                        <textarea
                          value={appConfig.alipayRootCert}
                          onChange={(event) =>
                            updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                              ...current,
                              alipayRootCert: event.target.value,
                              notice: '',
                            }))
                          }
                          className="mt-2 min-h-24 w-full resize-y rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder={
                            appConfig.hasAlipayRootCert
                              ? '留空则沿用已保存支付宝根证书'
                              : '粘贴 alipayRootCert.crt 内容'
                          }
                        />
                      </label>
                    </>
                  )}
                  <label className="block text-sm font-medium text-text-primary">
                    {redirectLabel}
                    <input
                      type="url"
                      value={appConfig.redirectUri}
                      onChange={(event) =>
                        updatePlatformAppConfig(normalizedPlatformCode, (current) => ({
                          ...current,
                          redirectUri: event.target.value,
                          notice: '',
                        }))
                      }
                      className="mt-2 w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                      placeholder={defaultPlatformRedirectUri(normalizedPlatformCode)}
                    />
                  </label>
                  <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3 text-sm text-text-secondary">
                    {appConfig.appKey && appConfig.hasAppSecret
                      ? '当前服务商应用已配置。'
                      : `保存完整应用配置后，后续可接入${isAlipayConfig ? '支付宝' : '淘宝/天猫'}授权。`}
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="border-t border-border bg-surface px-5 py-4">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingPlatformAppCode(null)}
                className="inline-flex items-center rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void savePlatformAppConfig(normalizedPlatformCode)}
                disabled={appConfig.loading || appConfig.saving}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {appConfig.saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                保存应用配置
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

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
    async (platformCode: PlatformCode, merchantDisplayName = '') => {
      if (!authToken) return;
      const normalizedPlatformCode = normalizePlatformCode(platformCode);
      const trimmedMerchantDisplayName = merchantDisplayName.trim();
      setLaunchingAuthPlatform(normalizedPlatformCode);
      const isDetailPage = mode === 'platform' && selectedPlatform?.platform_code === normalizedPlatformCode;
      if (isDetailPage) {
        setShopError('');
      } else {
        setPlatformError('');
      }
      if (normalizedPlatformCode === 'alipay') {
        setAlipayAuthDialog((current) => (current ? { ...current, error: '' } : current));
      }
      try {
        const body: Record<string, string> = {
          return_path:
            normalizedPlatformCode === 'alipay'
              ? '/data-connections?mode=platform&platform=alipay'
              : window.location.pathname || '/',
          mode: 'real',
        };
        if (normalizedPlatformCode === 'alipay') {
          body.merchant_display_name = trimmedMerchantDisplayName;
        }
        const response = await fetch(`/api/platform-connections/${normalizedPlatformCode}/auth-sessions`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify(body),
        });
        const data: AuthSessionResponse = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String((data as { detail?: string }).detail || data?.message || '创建授权会话失败'));
        }
        if (!data?.auth_url) {
          throw new Error('后端未返回授权链接 auth_url');
        }
        if (normalizedPlatformCode === 'alipay') {
          setAlipayAuthDialog((current) =>
            current
              ? {
                  ...current,
                  authUrl: String(data.auth_url || ''),
                  notice: '已生成企业专属授权链接，可复制发送给商户管理员，或在本机打开完成授权。',
                  error: '',
                }
              : current,
          );
          return;
        }
        window.location.assign(data.auth_url);
      } catch (error) {
        const message = error instanceof Error ? error.message : '创建授权会话失败';
        if (normalizedPlatformCode === 'alipay') {
          setAlipayAuthDialog((current) => (current ? { ...current, error: message } : current));
        }
        if (isDetailPage) {
          setShopError(message);
        } else {
          setPlatformError(message);
        }
      } finally {
        setLaunchingAuthPlatform(null);
      }
    },
    [authHeaders, authToken, mode, selectedPlatform],
  );

  const handleLaunchAuth = useCallback(
    (platformCode: PlatformCode) => {
      const normalizedPlatformCode = normalizePlatformCode(platformCode);
      if (normalizedPlatformCode === 'alipay') {
        setSelectedPlatform({
          platform_code: 'alipay',
          platform_name: '支付宝',
          authorized_shop_count: 0,
          error_shop_count: 0,
        });
        setMode('platform');
        void Promise.all([fetchShops('alipay'), fetchPlatformAppConfig('alipay')]);
        openAlipayAuthDialog();
        return;
      }
      void launchAuthFlow(normalizedPlatformCode);
    },
    [fetchPlatformAppConfig, fetchShops, launchAuthFlow, openAlipayAuthDialog],
  );

  const handleSelectPlatform = useCallback(
    async (platform: PlatformConnectionSummary) => {
      const normalizedPlatform = {
        ...platform,
        platform_code: normalizePlatformCode(platform.platform_code),
        platform_name: normalizePlatformCode(platform.platform_code) === 'taobao' ? '淘宝/天猫' : platform.platform_name,
      };
      setSelectedPlatform(normalizedPlatform);
      setMode('platform');
      const loadingTasks: Promise<unknown>[] = [
        fetchShops(normalizedPlatform.platform_code),
        fetchPlatformAppConfig(normalizedPlatform.platform_code),
      ];
      await Promise.all(loadingTasks);
    },
    [fetchPlatformAppConfig, fetchShops],
  );

  const handleBackToOverview = useCallback(() => {
    setMode('overview');
    setSelectedPlatform(null);
    setShops([]);
    setShopError('');
    setShopNotice('');
    setPlatformError('');
    setAlipayClaimError('');
    setAlipayClaimNotice('');
  }, []);

  const handleReauthorize = useCallback(
    async (shop: ShopConnection) => {
      if (!authToken) return;
      setActioningShopId(shop.id);
      setShopError('');
      setShopNotice('');
      try {
        const response = await fetch(`/api/shop-connections/${shop.id}/reauthorize`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            return_path: window.location.pathname || '/',
            mode: 'real',
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
      setShopError('');
      setShopNotice('');
      try {
        const response = await fetch(`/api/shop-connections/${shop.id}/disable`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ mode: 'real' }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '停用授权失败'));
        }
        const responseConnection = data?.connection ?? data?.shop;
        if (responseConnection && typeof responseConnection === 'object') {
          setShops((current) =>
            current.map((item) => (item.id === shop.id ? ({ ...item, ...responseConnection } as ShopConnection) : item)),
          );
        }
        let nextShops: ShopConnection[] = [];
        if (selectedPlatform) {
          nextShops = await fetchShops(selectedPlatform.platform_code);
        }
        await fetchPlatforms();
        const disabledConnection =
          nextShops.find((item) => item.id === shop.id) ??
          (responseConnection && typeof responseConnection === 'object' ? (responseConnection as ShopConnection) : null);
        if (disabledConnection) {
          setShops((current) =>
            current.map((item) => (item.id === shop.id ? ({ ...item, ...disabledConnection } as ShopConnection) : item)),
          );
        }
        setShopNotice(String(data?.message || '授权已停用'));
      } catch (error) {
        setShopError(error instanceof Error ? error.message : '停用授权失败');
      } finally {
        setActioningShopId(null);
        setDisableConfirmShop(null);
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
  // 电商平台授权的“连接数”应为各平台已授权店铺数之和(而非固定的支持平台目录条数)。
  const totalAuthorizedShops = useMemo(
    () => platforms.reduce((sum, item) => sum + (item.authorized_shop_count ?? 0), 0),
    [platforms],
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

      setShopDatasetDetails((prev) => {
        let hasChanges = false;
        const nextEntries = Object.entries(prev).map(([shopId, details]) => {
          const nextDetails = details.map((detail) => {
            if (detail.sourceId !== sourceId) return detail;
            const matched =
              detail.dataset.id === datasetId ||
              (datasetCode && detail.dataset.dataset_code === datasetCode);
            if (!matched) return detail;
            hasChanges = true;
            return {
              ...detail,
              dataset: applyPatch(detail.dataset),
            };
          });
          return [shopId, nextDetails] as const;
        });
        if (!hasChanges) return prev;
        return Object.fromEntries(nextEntries);
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

  const findPlatformShopDatasets = useCallback(
    (
      shop: ShopConnection,
      sourcesOverride: DataSourceListItem[] = remoteSources,
    ): Array<{ source: DataSourceListItem; dataset: DataSourceDatasetSummary }> => {
      const shopId = shop.id.trim();
      const platformCode = shop.platform_code.trim().toLowerCase();
      return sourcesOverride.flatMap((source) => {
        if (source.source_kind !== 'platform_oauth') return [];
        if (source.provider_code.trim().toLowerCase() !== platformCode) return [];
        return (source.datasets ?? [])
          .filter((dataset) => {
            const resourceKey = (dataset.resource_key || dataset.dataset_code || '').trim();
            if (platformCode === 'taobao') return resourceKey === `taobao_order_lines:${shopId}`;
            if (platformCode === 'alipay') {
              const parts = resourceKey.split(':');
              return parts.length >= 3 && parts[0] === 'alipay_bill' && parts[2] === shopId;
            }
            return false;
          })
          .map((dataset) => ({ source, dataset }));
      });
    },
    [remoteSources],
  );

  const loadPlatformShopDatasetDetails = useCallback(
    async (shop: ShopConnection, sourcesOverride?: DataSourceListItem[]) => {
      setShopDatasetActionError('');
      setExpandedShopDatasetId(shop.id);

      const matches = findPlatformShopDatasets(shop, sourcesOverride);
      if (matches.length === 0) {
        setShopDatasetDetails((prev) => ({ ...prev, [shop.id]: [] }));
        return;
      }

      const loadingDetails: PlatformShopDatasetDetail[] = matches.map(({ source, dataset }) => ({
        sourceId: source.id,
        source,
        dataset,
        collectionStatus: {
          status: 'loading',
          message: '',
          canInitialize: false,
          canRetryInitialize: false,
          isRunning: true,
          latestJob: null,
          rowCount: null,
          totalCount: null,
          latestCollectionDate: '',
        },
        semanticStatus: {
          status: 'loading',
          message: '',
          canRefresh: false,
          canRetry: false,
        },
        fieldGroups: [],
        rows: [],
        loading: true,
        error: '',
        loadedAt: '',
      }));
      setShopDatasetDetails((prev) => ({ ...prev, [shop.id]: loadingDetails }));

      if (!authToken) {
        setShopDatasetDetails((prev) => ({
          ...prev,
          [shop.id]: loadingDetails.map((detail) => ({
            ...detail,
            loading: false,
            error: '当前环境未连接后端数据集详情接口。',
          })),
        }));
        return;
      }

      const loadedDetails = await Promise.all(
        matches.map(async ({ source, dataset }) => {
          const resourceKey = dataset.resource_key || dataset.dataset_code;
          const baseDetail = loadingDetails.find(
            (detail) => detail.sourceId === source.id && detail.dataset.id === dataset.id,
          );
          if (draftSourceIdSet.has(source.id)) {
            return {
              ...(baseDetail as PlatformShopDatasetDetail),
              loading: false,
              error: '草稿连接尚未创建后端数据集。',
            };
          }
          try {
            const params = new URLSearchParams({
              resource_key: resourceKey,
              limit: '10',
              sample_limit: '20',
            });
            const response = await fetch(
              `/api/data-sources/${source.id}/datasets/${encodeURIComponent(dataset.id)}/collection-detail?${params.toString()}`,
              { headers: authHeaders },
            );
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
              throw new Error(String(data?.detail || data?.message || '获取数据集详情失败'));
            }
            return normalizePlatformDatasetDetail(source, dataset, data);
          } catch (error) {
            return {
              ...(baseDetail as PlatformShopDatasetDetail),
              loading: false,
              error: error instanceof Error ? error.message : '获取数据集详情失败',
            };
          }
        }),
      );
      setShopDatasetDetails((prev) => ({ ...prev, [shop.id]: loadedDetails }));
    },
    [authHeaders, authToken, draftSourceIdSet, findPlatformShopDatasets],
  );

  const refreshCurrentConnectionView = useCallback(async () => {
    if (selectedConnectionView === 'collaboration_channels') {
      await fetchCollaborationChannels();
      return;
    }
    if (mode === 'platform' && selectedPlatform) {
      const [nextShops, nextSources] = await Promise.all([
        fetchShops(selectedPlatform.platform_code),
        fetchRemoteSources(),
      ]);
      const expandedShop = nextShops.find((shop) => shop.id === expandedShopDatasetId);
      if (expandedShop) {
        await loadPlatformShopDatasetDetails(expandedShop, nextSources);
      }
      return;
    }
    await fetchPlatforms();
    await fetchRemoteSources();
  }, [
    expandedShopDatasetId,
    fetchCollaborationChannels,
    fetchPlatforms,
    fetchRemoteSources,
    fetchShops,
    loadPlatformShopDatasetDetails,
    mode,
    selectedConnectionView,
    selectedPlatform,
  ]);

  const retryPlatformDatasetCollection = useCallback(
    async (shop: ShopConnection, detail: PlatformShopDatasetDetail) => {
      setShopDatasetActionError('');
      const actionId = `${detail.sourceId}:${detail.dataset.id}`;
      if (platformDatasetCollectionActionIdsRef.current.has(actionId)) {
        return;
      }
      if (isPlatformCollectionRunning(detail.collectionStatus)) {
        return;
      }
      if (!authToken || draftSourceIdSet.has(detail.sourceId)) {
        setShopDatasetActionError('当前环境未连接后端初始化接口。');
        return;
      }
      platformDatasetCollectionActionIdsRef.current = new Set(platformDatasetCollectionActionIdsRef.current).add(actionId);
      setPlatformDatasetCollectionActionIds(platformDatasetCollectionActionIdsRef.current);
      try {
        const resourceKey = detail.dataset.resource_key || detail.dataset.dataset_code;
        const response = await fetch(
          `/api/data-sources/${detail.sourceId}/datasets/${encodeURIComponent(detail.dataset.id)}/collection`,
          {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({
              resource_key: resourceKey,
              background: true,
              trigger_mode: 'initial',
              params: {
                dataset_id: detail.dataset.id,
                resource_key: resourceKey,
                query: { resource_key: resourceKey },
              },
            }),
          },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '初始化数据集失败'));
        }
        await loadPlatformShopDatasetDetails(shop);
        setExpandedShopDatasetId(shop.id);
      } catch (error) {
        setShopDatasetActionError(error instanceof Error ? error.message : '初始化数据集失败');
      } finally {
        const nextActionIds = new Set(platformDatasetCollectionActionIdsRef.current);
        nextActionIds.delete(actionId);
        platformDatasetCollectionActionIdsRef.current = nextActionIds;
        setPlatformDatasetCollectionActionIds(nextActionIds);
      }
    },
    [authHeaders, authToken, draftSourceIdSet, loadPlatformShopDatasetDetails],
  );

  const openDatasetDetail = useCallback(
    async (source: DataSourceListItem, dataset: DataSourceDatasetSummary) => {
      const baseState: DatasetDetailDialogState = {
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
      setDatasetDetailDialog(baseState);
      if (!authToken || draftSourceIdSet.has(source.id)) {
        setDatasetDetailDialog({
          ...baseState,
          loading: false,
          error: '当前环境未连接后端详情接口。',
        });
        return;
      }
      try {
        const params = new URLSearchParams({
          resource_key: dataset.resource_key || dataset.dataset_code,
          sample_limit: '10',
        });
        const response = await fetch(
          `/api/data-sources/${source.id}/datasets/${encodeURIComponent(dataset.id)}/detail?${params.toString()}`,
          { headers: authHeaders },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '获取详情失败'));
        }
        setDatasetDetailDialog({
          ...baseState,
          loading: false,
          detail: asRecord(data) ?? {},
          lastLoadedAt: new Date().toISOString(),
        });
      } catch (error) {
        setDatasetDetailDialog({
          ...baseState,
          loading: false,
          error: error instanceof Error ? error.message : '获取详情失败',
        });
      }
    },
    [authHeaders, authToken, draftSourceIdSet],
  );

  const refreshDatasetDetailDialog = useCallback(async () => {
    if (!datasetDetailDialog || !authToken || draftSourceIdSet.has(datasetDetailDialog.sourceId)) return;
    const params = new URLSearchParams({
      resource_key: datasetDetailDialog.resourceKey,
      sample_limit: '10',
      refresh: 'true',
    });
    try {
      const response = await fetch(
        `/api/data-sources/${datasetDetailDialog.sourceId}/datasets/${encodeURIComponent(datasetDetailDialog.datasetId)}/detail?${params.toString()}`,
        { headers: authHeaders },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(data?.detail || data?.message || '刷新详情失败'));
      setDatasetDetailDialog((prev) =>
        prev
          ? {
              ...prev,
              loading: false,
              error: '',
              actionError: '',
              detail: asRecord(data) ?? {},
              lastLoadedAt: new Date().toISOString(),
            }
          : prev,
      );
    } catch (error) {
      setDatasetDetailDialog((prev) =>
        prev
          ? {
              ...prev,
              loading: false,
              actionError: error instanceof Error ? error.message : '刷新详情失败',
            }
          : prev,
      );
    }
  }, [authHeaders, authToken, datasetDetailDialog, draftSourceIdSet]);

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
          sample_limit: '20',
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

  const triggerCollectionDetailDataset = useCallback(
    async (options?: { bizDate?: string; onSuccess?: () => void }) => {
      if (!collectionDetailDialog || !authToken || draftSourceIdSet.has(collectionDetailDialog.sourceId)) return;
      const source = remoteSources.find((item) => item.id === collectionDetailDialog.sourceId);
      const dataset = source?.datasets?.find((item) => item.id === collectionDetailDialog.datasetId) ?? {
        id: collectionDetailDialog.datasetId,
        dataset_code: collectionDetailDialog.resourceKey,
        dataset_name: collectionDetailDialog.datasetName,
        resource_key: collectionDetailDialog.resourceKey,
      } as DataSourceDatasetSummary;
      const bizDate = (options?.bizDate || '').trim();
      setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: true, actionError: '' } : prev));
      try {
        const body: Record<string, unknown> = {
          resource_key: collectionDetailDialog.resourceKey,
          trigger_mode: 'manual',
          params: {
            resource_key: collectionDetailDialog.resourceKey,
            ...(bizDate ? { biz_date: bizDate } : {}),
            query: { resource_key: collectionDetailDialog.resourceKey },
          },
        };
        if (bizDate) {
          body.idempotency_key = `manual-date-collection:${collectionDetailDialog.sourceId}:${collectionDetailDialog.datasetId}:${bizDate}`;
        }
        const response = await fetch(
          `/api/data-sources/${collectionDetailDialog.sourceId}/datasets/${encodeURIComponent(collectionDetailDialog.datasetId)}/collection`,
          {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify(body),
          },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || (bizDate ? '按日期采集失败' : '立即采集失败')));
        }
        options?.onSuccess?.();
        if (source) {
          await openDatasetCollectionDetail(source, dataset);
        } else {
          setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: false } : prev));
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : bizDate ? '按日期采集失败' : '立即采集失败';
        if (source) {
          await openDatasetCollectionDetail(source, dataset);
          setCollectionDetailDialog((prev) => (prev ? { ...prev, actionError: message } : prev));
        } else {
          setCollectionDetailDialog((prev) => (prev ? { ...prev, loading: false, actionError: message } : prev));
        }
        throw error;
      }
    },
    [authHeaders, authToken, collectionDetailDialog, draftSourceIdSet, openDatasetCollectionDetail, remoteSources],
  );

  const retryCollectionDetailDataset = useCallback(async () => {
    await triggerCollectionDetailDataset();
  }, [triggerCollectionDetailDataset]);

  const openDateCollectionDialog = useCallback(() => {
    if (!collectionDetailDialog) return;
    const source = remoteSources.find((item) => item.id === collectionDetailDialog.sourceId);
    const dataset = source?.datasets?.find((item) => item.id === collectionDetailDialog.datasetId);
    const dateField = readCollectionDateFieldFromDetail(collectionDetailDialog.detail, dataset);
    if (!dateField) {
      setCollectionDetailDialog((prev) =>
        prev
          ? {
              ...prev,
              actionError: '该数据集未配置采集时间字段，无法按日期采集。',
            }
          : prev,
      );
      return;
    }
    setDateCollectionDialog({
      sourceId: collectionDetailDialog.sourceId,
      sourceName: collectionDetailDialog.sourceName,
      datasetId: collectionDetailDialog.datasetId,
      datasetName: collectionDetailDialog.datasetName,
      resourceKey: collectionDetailDialog.resourceKey,
      dateField,
      selectedDate: '',
      submitting: false,
      error: '',
    });
  }, [collectionDetailDialog, remoteSources]);

  const submitDateCollectionDialog = useCallback(async () => {
    if (!dateCollectionDialog || dateCollectionDialog.submitting) return;
    const selectedDate = dateCollectionDialog.selectedDate.trim();
    if (!selectedDate) {
      setDateCollectionDialog((prev) => (prev ? { ...prev, error: '请选择采集日期。' } : prev));
      return;
    }
    setDateCollectionDialog((prev) => (prev ? { ...prev, submitting: true, error: '' } : prev));
    try {
      await triggerCollectionDetailDataset({
        bizDate: selectedDate,
        onSuccess: () => setDateCollectionDialog(null),
      });
    } catch (error) {
      setDateCollectionDialog((prev) =>
        prev
          ? {
              ...prev,
              submitting: false,
              error: error instanceof Error ? error.message : '按日期采集失败',
            }
          : prev,
      );
    }
  }, [dateCollectionDialog, triggerCollectionDetailDataset]);

  const refreshCollectionDetailDialog = useCallback(async () => {
    if (!collectionDetailDialog || !authToken || draftSourceIdSet.has(collectionDetailDialog.sourceId)) return;
    const params = new URLSearchParams({
      resource_key: collectionDetailDialog.resourceKey,
      limit: '10',
      sample_limit: '20',
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
      return ['queued', 'running'].includes(status.toLowerCase());
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
      const targetRow = prev.fieldRows.find((row) => row.rawName === rawName);
      return {
        ...prev,
        collectionDateField: rawName,
        collectionDateFormat: rawName
          ? inferCollectionDateFormat(rawName, targetRow?.sampleValues ?? [])
          : 'native',
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
    const keyFields = normalizeUniqueIdentifierRawNames(
      editingDatasetSemantic.uniqueIdentifierRawNames,
      editingDatasetSemantic.fieldRows,
    );
    const normalizedFields = editingDatasetSemantic.fieldRows
      .map((row) => {
        const rawName = row.rawName.trim();
        if (!isPublishableDatasetSemanticRawName(rawName)) return null;
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
          confirmed_by_user: true,
        };
      })
      .filter((row): row is NonNullable<typeof row> => Boolean(row));
    const fieldLabelMap = Object.fromEntries(normalizedFields.map((row) => [row.raw_name, row.display_name]));
    const publishableFieldNameSet = new Set(normalizedFields.map((row) => row.raw_name.trim().toLowerCase()));
    const publishableKeyFields = keyFields.filter((field) => publishableFieldNameSet.has(field.trim().toLowerCase()));
    const pendingFieldNames: string[] = [];
    const updatedAt = new Date().toISOString();
    const semanticProfile = {
      version: 1,
      status: 'manual_updated',
      business_name: businessName,
      business_object_type: businessObjectType,
      grain,
      publish_status: 'published',
      field_label_map: fieldLabelMap,
      key_fields: publishableKeyFields,
      fields: normalizedFields,
      low_confidence_fields: pendingFieldNames,
      tech_name: editingDatasetSemantic.resourceKey || editingDatasetSemantic.datasetName,
      updated_at: updatedAt,
    };
    const collectionConfig = {
      mode: editingDatasetSemantic.collectionDateField.trim() ? 'date_field' : 'manual',
      date_field: editingDatasetSemantic.collectionDateField.trim(),
      date_format: inferCollectionDateFormat(
        editingDatasetSemantic.collectionDateField,
        editingDatasetSemantic.fieldRows.find((row) => row.rawName === editingDatasetSemantic.collectionDateField)
          ?.sampleValues ?? [],
      ),
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
          publish_status: 'published',
          key_fields: publishableKeyFields,
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
              publishStatus: 'published',
              uniqueIdentifierRawNames: publishableKeyFields,
              collectionDateField: collectionConfig.date_field,
              collectionDateFormat: collectionConfig.date_format,
              fieldRows: prev.fieldRows.map((row) => ({
                ...row,
                displayName: fieldLabelMap[row.rawName] || row.displayName,
                confirmedByUser: true,
                pending: false,
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
            key_fields: publishableKeyFields,
            field_label_map: fieldLabelMap,
            fields: normalizedFields,
            status: 'manual_updated',
            schema_name: editingDatasetSemantic.schemaName === '-' ? '' : editingDatasetSemantic.schemaName,
            object_name: editingDatasetSemantic.objectName === '-' ? '' : editingDatasetSemantic.objectName,
            object_type: editingDatasetSemantic.objectType,
            business_object_type: businessObjectType,
            grain,
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
        const publishedDataset = {
          ...savedDataset,
          publish_status: 'published',
        };
        updateDatasetInState(
          editingDatasetSemantic.sourceId,
          editingDatasetSemantic.datasetId,
          editingDatasetSemantic.datasetCode,
          () => publishedDataset,
        );
        setEditingDatasetSemantic((prev) =>
          prev &&
          prev.sourceId === editingDatasetSemantic.sourceId &&
          prev.datasetId === editingDatasetSemantic.datasetId
            ? buildEditableDatasetSemanticState(
                { id: editingDatasetSemantic.sourceId, name: editingDatasetSemantic.sourceName },
                publishedDataset,
              )
            : prev,
        );
      } else {
        applyLocalUpdate(String(data?.message || '已发布为可用数据集'));
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
    // database 与 api 都用「列表总览 → 进入详情」的导航式布局(由 databaseDetailSourceId 驱动);
    // file 仍用左列表右详情的并排网格。
    const usesListDetailLayout = kind === 'database' || kind === 'api';
    const activeSource =
      usesListDetailLayout ? rows.find((item) => item.id === databaseDetailSourceId) ?? null : defaultActiveSource;
    const showListOverview = usesListDetailLayout && !databaseDetailSourceId;
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
        {showListOverview ? (
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
                  <h3 className="text-base font-semibold text-text-primary">{kind === 'api' ? 'API 连接列表' : '数据库连接列表'}</h3>
                  <p className="mt-1 text-sm text-text-secondary">
                    {kind === 'api'
                      ? '展示已配置 API 连接，点击可进入查看配置与数据集。'
                      : '展示已配置数据库连接，点击可查看配置、数据集和目录。'}
                  </p>
                </div>
                <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-xs text-text-secondary">
                  共 {rows.length} 个连接
                </span>
              </div>

              {loadingSources && rows.length === 0 ? (
                <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在加载连接列表
                </div>
              ) : rows.length === 0 ? (
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
                                    {kind === 'api' ? (
                                      <span
                                        className="inline-flex max-w-full items-center rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary"
                                        title={dataSourceSubtitle(source)}
                                      >
                                        <span className="truncate">{dataSourceSubtitle(source)}</span>
                                      </span>
                                    ) : (
                                      <>
                                        <span className="inline-flex max-w-full items-center rounded-full bg-surface-secondary px-2.5 py-1 text-xs text-text-secondary">
                                          {databaseType}
                                        </span>
                                        <span
                                          className="inline-flex max-w-full items-center rounded-full border border-border px-2.5 py-1 text-xs text-text-primary"
                                          title={accountLabel}
                                        >
                                          <span className="truncate">{accountLabel}</span>
                                        </span>
                                      </>
                                    )}
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
          <div className={usesListDetailLayout ? 'space-y-4' : 'grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]'}>
            {usesListDetailLayout ? (
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => setDatabaseDetailSourceId(null)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                >
                  <ArrowLeft className="h-4 w-4" />
                  {kind === 'api' ? '返回 API 列表' : '返回数据库列表'}
                </button>
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-surface p-4 shadow-sm">
                {sourcesError && (
                  <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                    {sourcesError}
                  </div>
                )}

                {loadingSources && rows.length === 0 ? (
                  <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在加载连接列表
                  </div>
                ) : rows.length === 0 ? (
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
                          <div className="mt-3 flex items-center justify-end gap-3 text-xs text-text-secondary">
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
                  {usesListDetailLayout ? '未找到对应连接，请返回列表重新选择。' : '选择左侧连接后，在这里查看连接详情和数据集目录。'}
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
                                    onClick={() => void (activeSource.source_kind === 'database'
                                      ? openDatasetDetail(activeSource, dataset)
                                      : openDatasetCollectionDetail(activeSource, dataset))}
                                    className="mt-2 inline-flex items-center justify-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1.5 text-xs whitespace-nowrap text-blue-700 transition-colors hover:bg-blue-100"
                                  >
                                    {activeSource.source_kind === 'database' ? '详情' : '采集详情'}
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
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
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
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
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
        <div className="fixed inset-0 z-[60] bg-black/35" onClick={closeEditingDatasetSemantic}>
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
                  aria-label="关闭"
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-5">
              <div className="space-y-4">
                {datasetSemanticError && (
                  <div className="sticky top-0 z-10 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 shadow-sm">
                    {datasetSemanticError}
                  </div>
                )}
                {datasetSemanticNotice && (
                  <div className="sticky top-0 z-10 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 shadow-sm">
                    {datasetSemanticNotice}
                  </div>
                )}
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
                    <span className="text-sm font-medium text-text-primary">手动采集字段</span>
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">
                    有 update_time / updated_at / modified_at 时优先选它，可以采集新增和更新；没有更新时间字段时选择 create_time / created_at，只能稳定采集新创建的数据。
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
      {datasetDetailDialog && (
        <div className="fixed inset-0 z-[60] bg-black/35" onClick={() => setDatasetDetailDialog(null)}>
          <div
            className="ml-auto flex h-full w-full max-w-3xl flex-col border-l border-border bg-surface shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-border px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h4 className="text-base font-semibold text-text-primary">详情</h4>
                  <p className="mt-1 truncate text-sm text-text-primary">{datasetDetailDialog.datasetName}</p>
                  <p className="mt-1 truncate text-xs text-text-secondary">
                    {datasetDetailDialog.sourceName} · {datasetDetailDialog.resourceKey}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setDatasetDetailDialog(null)}
                  aria-label="关闭"
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-5">
              {datasetDetailDialog.loading ? (
                <div className="flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在加载详情。
                </div>
              ) : datasetDetailDialog.error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {datasetDetailDialog.error}
                </div>
              ) : (
                <div className="space-y-4">
                  {datasetDetailDialog.actionError && (
                    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                      {datasetDetailDialog.actionError}
                    </div>
                  )}
                  <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-text-primary">最新 10 条数据</p>
                        <p className="mt-1 text-xs text-text-secondary">
                          {datasetDetailDialog.lastLoadedAt ? `最近刷新：${formatTime(datasetDetailDialog.lastLoadedAt)}` : ''}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void refreshDatasetDetailDialog()}
                        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                      >
                        <RefreshCw className="h-4 w-4" />
                        刷新
                      </button>
                    </div>
                    <div className="mt-3 max-h-80 overflow-auto rounded-xl border border-border bg-surface">
                      {(() => {
                        const detail = datasetDetailDialog.detail ?? {};
                        const sampleRows = (
                          Array.isArray(detail.rows)
                            ? detail.rows.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
                            : []
                        ).slice(0, 10).map((row) => asRecord(row) ?? {});
                        const fieldGroups = normalizePlatformFieldGroups(detail.field_groups ?? detail.fieldGroups);
                        const columns = buildSemanticSampleTableColumns(fieldGroups, sampleRows);
                        if (sampleRows.length === 0) {
                          return <p className="px-3 py-3 text-sm text-text-secondary">暂无样本数据。</p>;
                        }
                        if (columns.length === 0) {
                          return <p className="px-3 py-3 text-sm text-text-secondary">暂无可展示字段。</p>;
                        }
                        return (
                          <table className="min-w-full divide-y divide-border text-left text-xs">
                            <thead className="sticky top-0 z-10 bg-surface-secondary text-text-secondary">
                              <tr>
                                {columns.map((column) => (
                                  <th key={column.rawName} className="whitespace-nowrap px-3 py-2 font-medium">
                                    {column.displayName}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border text-text-primary">
                              {sampleRows.map((row, rowIndex) => (
                                <tr key={`dataset-detail-sample-${rowIndex}`} className="hover:bg-surface-secondary/60">
                                  {columns.map((column) => (
                                    <td
                                      key={`${rowIndex}-${column.rawName}`}
                                      className="max-w-56 truncate px-3 py-2"
                                      title={formatSampleCellValue(row[column.rawName])}
                                    >
                                      {formatSampleCellValue(row[column.rawName])}
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
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {collectionDetailDialog && !dateCollectionDialog && (
        <div className="fixed inset-0 z-[60] bg-black/35" onClick={() => setCollectionDetailDialog(null)}>
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
                  aria-label="关闭"
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
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
                    const collectionStats = asRecord(detail.collection_stats) ?? {};
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
                    const totalRecordCount =
                      asNumber(collectionStats.total_count) ??
                      asNumber(collectionStats.record_count) ??
                      collectedCount ??
                      rows.length;
                    const sourceForCollectionDetail = remoteSources.find(
                      (item) => item.id === collectionDetailDialog.sourceId,
                    );
                    const datasetForCollectionDetail = sourceForCollectionDetail?.datasets?.find(
                      (item) => item.id === collectionDetailDialog.datasetId,
                    );
                    const collectionDateField = readCollectionDateFieldFromDetail(
                      collectionDetailDialog.detail,
                      datasetForCollectionDetail,
                    );
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
                              {totalRecordCount || rows.length}
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
                                onClick={openDateCollectionDialog}
                                disabled={!collectionDateField}
                                title={!collectionDateField ? '该数据集未配置采集时间字段，无法按日期采集' : undefined}
                                className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                <CalendarDays className="h-4 w-4" />
                                按日期采集
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
                                const requestPayload = asRecord(job.request_payload) ?? {};
                                const queryPayload = asRecord(requestPayload.query) ?? {};
                                const sourceRowCount = asNumber(metrics.row_count);
                                const collectionInputCount = asNumber(metrics.collection_input);
                                const collectionUpsertedCount = asNumber(metrics.collection_upserted);
                                const collectionInsertedCount = asNumber(metrics.collection_inserted);
                                const collectionUpdatedCount = asNumber(metrics.collection_updated);
                                const collectionUnchangedCount = asNumber(metrics.collection_unchanged);
                                const collectionSkippedEmptyKeyCount = asNumber(metrics.collection_skipped_empty_key);
                                const skippedEmptyKeySamples = Array.isArray(metrics.collection_skipped_empty_key_samples)
                                  ? metrics.collection_skipped_empty_key_samples
                                      .map((item) => asRecord(item))
                                      .filter((item): item is Record<string, unknown> => Boolean(item))
                                  : [];
                                const dateField =
                                  asString(requestPayload.date_field) || asString(queryPayload.date_field) || '';
                                const dateFormat =
                                  asString(requestPayload.date_format) || asString(queryPayload.date_format) || '';
                                const bizDate = asString(requestPayload.biz_date) || '';
                                const filterDisplay = formatCollectionFilterDisplay(dateField, bizDate, dateFormat);
                                const hasSourceRows = typeof sourceRowCount === 'number' && sourceRowCount > 0;
                                const keyFields = Array.isArray(requestPayload.key_fields)
                                  ? requestPayload.key_fields
                                      .map((item) => (typeof item === 'string' ? item.trim() : ''))
                                      .filter(Boolean)
                                  : [];
                                const isZeroSourceResult = sourceRowCount === 0;
                                const isCompressedByKey =
                                  hasSourceRows &&
                                  typeof collectionInputCount === 'number' &&
                                  collectionInputCount > 0 &&
                                  collectionInputCount < sourceRowCount;
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
                                    <div className="mt-2 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
                                      <p>
                                        源表读取：
                                        <span className="font-medium text-text-primary">
                                          {typeof sourceRowCount === 'number' ? sourceRowCount : '未返回'}
                                        </span>
                                        条
                                      </p>
                                      <p>
                                        资产记录：
                                        <span className="font-medium text-text-primary">
                                          {typeof collectionUpsertedCount === 'number' ? collectionUpsertedCount : '未返回'}
                                        </span>
                                        条
                                      </p>
                                      {typeof collectionInsertedCount === 'number' && (
                                        <p>新增：{collectionInsertedCount} 条</p>
                                      )}
                                      {typeof collectionUpdatedCount === 'number' && (
                                        <p>更新：{collectionUpdatedCount} 条</p>
                                      )}
                                      {typeof collectionUnchangedCount === 'number' && (
                                        <p>未变化：{collectionUnchangedCount} 条</p>
                                      )}
                                      {typeof collectionSkippedEmptyKeyCount === 'number' && collectionSkippedEmptyKeyCount > 0 && (
                                        <p>跳过异常行：{collectionSkippedEmptyKeyCount} 条</p>
                                      )}
                                      {dateField && <p>采集时间字段：{dateField}</p>}
                                      {dateFormat && <p>字段格式：{collectionDateFormatLabel(dateFormat)}</p>}
                                      {bizDate && <p>采集日期：{bizDate}</p>}
                                    </div>
                                    {typeof collectionSkippedEmptyKeyCount === 'number' && collectionSkippedEmptyKeyCount > 0 && (
                                      <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
                                        <p>
                                          已跳过 {collectionSkippedEmptyKeyCount} 条唯一标识全空的源数据，避免写入无法幂等更新的脏数据。
                                        </p>
                                        {skippedEmptyKeySamples.length > 0 && (
                                          <p className="mt-1">
                                            示例：
                                            {skippedEmptyKeySamples
                                              .map((item) => {
                                                const rowNumber = asNumber(item.row_number);
                                                const message = asString(item.message) || '';
                                                return `第 ${rowNumber ?? '-'} 行（${message || '唯一标识为空'}）`;
                                              })
                                              .join('；')}
                                          </p>
                                        )}
                                      </div>
                                    )}
                                    {filterDisplay && (
                                      <p className="mt-2 rounded-lg bg-surface-secondary px-2 py-1 text-xs text-text-secondary">
                                        本次过滤：{filterDisplay}
                                      </p>
                                    )}
                                    {isZeroSourceResult && (
                                      <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
                                        源表在本次采集日期范围内没有数据。请检查采集时间字段是否选对，或源表是否已经产出当天数据。
                                      </p>
                                    )}
                                    {isCompressedByKey && (
                                      <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
                                        源表读取 {sourceRowCount} 条，但按唯一标识
                                        {keyFields.length > 0 ? `（${keyFields.join(' + ')}）` : ''}
                                        去重后只有 {collectionInputCount} 条。请检查唯一标识是否应选择订单号、流水号等更细粒度字段。
                                      </p>
                                    )}
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
                              const fieldGroups = normalizePlatformFieldGroups(
                                collectionDetailDialog.detail?.field_groups ??
                                  collectionDetailDialog.detail?.fieldGroups,
                              );
                              const columns = buildSemanticSampleTableColumns(
                                fieldGroups,
                                sampleRows,
                              );
                              if (columns.length === 0) {
                                return <p className="px-3 py-3 text-sm text-text-secondary">暂无可展示字段。</p>;
                              }
                              return (
                                <table className="min-w-full divide-y divide-border text-left text-xs">
                                  <thead className="sticky top-0 z-10 bg-surface-secondary text-text-secondary">
                                    <tr>
                                      {columns.map((column) => (
                                        <th key={column.rawName} className="whitespace-nowrap px-3 py-2 font-medium">
                                          {column.displayName}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-border text-text-primary">
                                    {sampleRows.map((row, rowIndex) => (
                                      <tr key={`collection-sample-${rowIndex}`} className="hover:bg-surface-secondary/60">
                                        {columns.map((column) => (
                                          <td
                                            key={`${rowIndex}-${column.rawName}`}
                                            className="max-w-56 truncate px-3 py-2"
                                            title={formatSampleCellValue(row[column.rawName])}
                                          >
                                            {formatSampleCellValue(row[column.rawName])}
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
      {dateCollectionDialog && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/35 px-4" onClick={() => setDateCollectionDialog(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="date-collection-title"
            className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 id="date-collection-title" className="text-base font-semibold text-text-primary">
                  按日期采集
                </h4>
                <p className="mt-1 text-sm text-text-primary">数据集：{dateCollectionDialog.datasetName}</p>
                <p className="mt-1 text-xs text-text-secondary">
                  {dateCollectionDialog.sourceName} · {dateCollectionDialog.resourceKey}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDateCollectionDialog(null)}
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
              采集时间字段：{dateCollectionDialog.dateField}
            </div>
            {dateCollectionDialog.error && (
              <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {dateCollectionDialog.error}
              </div>
            )}
            <label className="mt-4 block text-sm font-medium text-text-primary" htmlFor="date-collection-date">
              采集日期
            </label>
            <input
              id="date-collection-date"
              type="date"
              value={dateCollectionDialog.selectedDate}
              onChange={(event) =>
                setDateCollectionDialog((prev) =>
                  prev ? { ...prev, selectedDate: event.target.value, error: '' } : prev,
                )
              }
              className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-blue-400"
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDateCollectionDialog(null)}
                disabled={dateCollectionDialog.submitting}
                className="inline-flex items-center rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void submitDateCollectionDialog()}
                disabled={dateCollectionDialog.submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {dateCollectionDialog.submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarDays className="h-4 w-4" />}
                采集
              </button>
            </div>
          </div>
        </div>
      )}
    </>
    );
  };

  const renderReservedPanel = (kind: Extract<DataSourceKind, 'browser_playbook' | 'browser' | 'desktop_cli'>) => {
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

  const renderCollaborationChannelDialog = () => {
    if (!editingChannel) return null;

    const providerCard = collaborationProviderCard(editingChannel.provider);
    const dialogTitle = `${editingChannel.isDraft ? '新增' : '编辑'}${providerCard.title}协作通道配置`;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="collaboration-channel-dialog-title"
          className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-border bg-surface shadow-xl"
        >
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0">
              <h3 id="collaboration-channel-dialog-title" className="text-base font-semibold text-text-primary">
                {dialogTitle}
              </h3>
              <p className="mt-1 text-sm text-text-secondary">{providerCard.description}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setEditingChannel(null);
                setChannelError('');
              }}
              aria-label="关闭"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="overflow-y-auto px-5 py-4">
            {channelError && (
              <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {channelError}
              </div>
            )}

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
                    placeholder={providerCard.defaultName}
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
                  <span className="font-medium text-text-primary">{providerCard.clientIdLabel}</span>
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
                  <span className="font-medium text-text-primary">{providerCard.clientSecretLabel}</span>
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
                <span className="font-medium text-text-primary">{providerCard.robotCodeLabel}</span>
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
                  取消
                </button>
              </div>
            </div>
          </div>
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
          {channelError && !editingChannel && (
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
        <div className="flex flex-wrap items-center justify-end gap-2">
          {canManageServiceProviderApps && (
            <button
              type="button"
              onClick={() => {
                setEditingPlatformAppCode('taobao');
                void fetchPlatformAppConfig('taobao');
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              服务商应用配置
            </button>
          )}
          {loadingPlatforms && (
            <span className="inline-flex items-center gap-2 text-xs text-text-secondary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              加载中
            </span>
          )}
        </div>
      </div>
      {platformError && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {platformError}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {platforms.map((platform) => {
          const isTaobaoPlatform = platform.platform_code === 'taobao';
          const isAuthEnabled = platform.platform_code === 'alipay';
          const authButtonLabel = isTaobaoPlatform
            ? 'ISV申请中'
            : isAuthEnabled
              ? '新增授权'
              : '待接入';
          return (
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
              {platform.platform_code === 'taobao' && (
                <p className="mt-2 text-xs leading-5 text-text-secondary">
                  一个淘宝/天猫店铺授权后会生成一个订单明细数据集，首次仅初始化 T-1 订单，之后每 2 小时同步订单变更。
                </p>
              )}
              {platform.platform_code === 'alipay' && (
                <p className="mt-2 text-xs leading-5 text-text-secondary">
                  {ALIPAY_AUTH_COLLECTION_COPY}
                </p>
              )}
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
                  onClick={() => handleLaunchAuth(platform.platform_code)}
                  disabled={!isAuthEnabled || launchingAuthPlatform === platform.platform_code}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-surface-tertiary disabled:text-text-muted disabled:hover:bg-surface-tertiary transition-colors"
                >
                  {launchingAuthPlatform === platform.platform_code ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Plus className="h-3.5 w-3.5" />
                  )}
                  {authButtonLabel}
                </button>
              </div>
            </div>
          );
        })}
        {!loadingPlatforms && platforms.length === 0 && (
          <div className="col-span-full rounded-2xl border border-dashed border-border bg-surface-secondary p-10 text-center">
            <p className="text-sm text-text-secondary">暂无平台连接数据，请稍后重试。</p>
          </div>
        )}
      </div>
    </div>
  );

  const renderPlatformDatasetDialog = () => {
    const shop = shops.find((item) => item.id === expandedShopDatasetId);
    if (!shop) return null;
    const details = shopDatasetDetails[shop.id] ?? [];
    const normalizedPlatformCode = shop.platform_code.trim().toLowerCase();
    const connectionNoun = normalizedPlatformCode === 'alipay' ? '商户' : '店铺';
    const dialogTitle =
      normalizedPlatformCode === 'alipay'
        ? '支付宝商户数据集'
        : normalizedPlatformCode === 'taobao'
          ? '淘宝/天猫店铺数据集'
          : `${connectionNoun}数据集`;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="platform-dataset-dialog-title"
          className="flex max-h-[88vh] w-full max-w-6xl flex-col rounded-2xl border border-border bg-surface shadow-xl"
        >
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0">
              <h3 id="platform-dataset-dialog-title" className="text-base font-semibold text-text-primary">
                {dialogTitle}
              </h3>
              <p className="mt-1 truncate text-sm text-text-secondary">
                {shop.external_shop_name || `${connectionNoun}未命名`} · {connectionNoun} ID：{shop.external_shop_id || '未知'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setExpandedShopDatasetId(null)}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              aria-label="关闭"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="overflow-y-auto px-5 py-4">
            {shopDatasetActionError && (
              <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {shopDatasetActionError}
              </div>
            )}
            {details.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-surface px-3 py-3 text-sm text-text-secondary">
                未找到该{connectionNoun}的数据集。
              </div>
            ) : (
              <div className="space-y-3">
                {details.map((detail) => {
                  const datasetName =
                    detail.dataset.dataset_name ||
                    detail.dataset.business_name ||
                    detail.dataset.dataset_code;
                  const collectionStatus = detail.collectionStatus.status || 'unknown';
                  const semanticStatus = detail.semanticStatus.status || 'unknown';
                  const isCollectionRunning = isPlatformCollectionRunning(detail.collectionStatus);
                  const collectionActionId = `${detail.sourceId}:${detail.dataset.id}`;
                  const isCollectionActionBusy = platformDatasetCollectionActionIds.has(collectionActionId);
                  const isCollectionFailed = isPlatformStatusFailed(collectionStatus);
                  const canRetryCollection =
                    !isCollectionRunning &&
                    !isCollectionActionBusy &&
                    (isCollectionFailed ||
                      detail.collectionStatus.canRetryInitialize ||
                      detail.collectionStatus.canInitialize ||
                      ['missing', 'not_started', 'none'].includes(collectionStatus.trim().toLowerCase()));
                  const collectionLabel = platformDatasetCollectionLabel(detail);
                  const dailyCollectionLabel = platformDatasetDailyCollectionLabel(detail);
                  const canPublishDataset = canPublishPlatformDataset(detail);
                  const previewRows = detail.rows.slice(0, 20);
                  const previewColumns = buildSemanticSampleTableColumns(detail.fieldGroups, previewRows, 100);

                  return (
                    <div key={`${detail.sourceId}-${detail.dataset.id}`} className="rounded-xl border border-border bg-surface px-4 py-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-text-primary">{datasetName}</p>
                            <span className="text-xs text-text-muted">
                              {detail.dataset.resource_key || detail.dataset.dataset_code}
                            </span>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2 text-xs">
                            <span className={`inline-flex rounded-full px-2.5 py-1 font-medium ${platformDatasetStatusClass(collectionStatus)}`}>
                              {collectionLabel}
                            </span>
                            {dailyCollectionLabel && (
                              <span className="inline-flex rounded-full bg-surface-secondary px-2.5 py-1 font-medium text-text-secondary">
                                {dailyCollectionLabel}
                              </span>
                            )}
                            <span className={`inline-flex rounded-full px-2.5 py-1 font-medium ${platformDatasetStatusClass(semanticStatus)}`}>
                              语义：{semanticStatus}
                            </span>
                            {detail.loadedAt && (
                              <span className="inline-flex rounded-full bg-surface-secondary px-2.5 py-1 text-text-secondary">
                                {formatTime(detail.loadedAt)}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                          {canRetryCollection && (
                            <button
                              type="button"
                              onClick={() => void retryPlatformDatasetCollection(shop, detail)}
                              disabled={isCollectionActionBusy}
                              className="inline-flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {isCollectionActionBusy ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <RefreshCw className="h-3.5 w-3.5" />
                              )}
                              重新初始化
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              closeEditingDatasetSemantic();
                              void openDatasetCollectionDetail(detail.source, detail.dataset);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                          >
                            <FileSpreadsheet className="h-3.5 w-3.5" />
                            采集详情
                          </button>
                          {canPublishDataset && (
                            <button
                              type="button"
                              onClick={() => {
                                setCollectionDetailDialog(null);
                                void startEditDatasetSemantic(detail.source, detail.dataset);
                              }}
                              className="inline-flex items-center gap-1 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              {platformPublishButtonLabel(detail)}
                            </button>
                          )}
                        </div>
                      </div>

                      {detail.loading ? (
                        <div className="mt-3 flex items-center gap-2 text-sm text-text-secondary">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          正在加载数据集详情
                        </div>
                      ) : detail.error ? (
                        <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                          {detail.error}
                        </div>
                      ) : (
                        <div className="mt-3 space-y-3">
                          {(detail.collectionStatus.message || detail.semanticStatus.message) && (
                            <div className="grid gap-2 text-xs text-text-secondary md:grid-cols-2">
                              {detail.collectionStatus.message && (
                                <p className="rounded-lg bg-surface-secondary px-2.5 py-2">
                                  初始化：{detail.collectionStatus.message}
                                </p>
                              )}
                              {detail.semanticStatus.message && (
                                <p className="rounded-lg bg-surface-secondary px-2.5 py-2">
                                  语义：{detail.semanticStatus.message}
                                </p>
                              )}
                            </div>
                          )}

                          <div>
                            <p className="text-xs font-medium text-text-secondary">数据预览</p>
                            <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-border bg-surface">
                              {previewColumns.length === 0 ? (
                                <p className="px-3 py-3 text-sm text-text-secondary">暂无可展示字段。</p>
                              ) : (
                                <table className="min-w-full divide-y divide-border text-left text-xs">
                                  <thead className="sticky top-0 z-10 bg-surface-secondary text-text-secondary">
                                    <tr>
                                      {previewColumns.map((column) => (
                                        <th
                                          key={column.rawName}
                                          className="whitespace-nowrap px-3 py-2 font-medium"
                                          title={column.rawName}
                                        >
                                          {column.displayName}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-border text-text-primary">
                                    {previewRows.length === 0 ? (
                                      <tr>
                                        <td colSpan={previewColumns.length} className="px-3 py-3 text-sm text-text-secondary">
                                          暂无数据。
                                        </td>
                                      </tr>
                                    ) : (
                                      previewRows.map((row, rowIndex) => (
                                        <tr key={`platform-dataset-row-${rowIndex}`} className="hover:bg-surface-secondary/60">
                                          {previewColumns.map((column) => (
                                            <td
                                              key={`${rowIndex}-${column.rawName}`}
                                              className="max-w-56 truncate px-3 py-2"
                                              title={formatSampleCellValue(row[column.rawName])}
                                            >
                                              {formatPreviewCell(row[column.rawName])}
                                            </td>
                                          ))}
                                        </tr>
                                      ))
                                    )}
                                  </tbody>
                                </table>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderPlatformDetails = () => {
    if (!selectedPlatform) return null;
    const appConfig =
      platformAppConfigs[selectedPlatform.platform_code] ??
      createPlatformAppConfigFormState(selectedPlatform.platform_code);
    const isTaobaoPlatform = selectedPlatform.platform_code === 'taobao';
    const isAlipayPlatform = selectedPlatform.platform_code === 'alipay';
    const isAuthEnabled = selectedPlatform.platform_code === 'alipay';
    const authButtonLabel = isTaobaoPlatform ? 'ISV申请中' : '新增授权';
    const connectionNoun = isAlipayPlatform ? '商户' : '店铺';

    return (
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
            <h3 className="text-base font-semibold text-text-primary">
              {platformConnectionListHeading(selectedPlatform.platform_code)}
            </h3>
          </div>
          <button
            type="button"
            onClick={() => handleLaunchAuth(selectedPlatform.platform_code)}
            disabled={!isAuthEnabled || launchingAuthPlatform === selectedPlatform.platform_code}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-surface-tertiary disabled:text-text-muted disabled:hover:bg-surface-tertiary transition-colors"
          >
            {launchingAuthPlatform === selectedPlatform.platform_code ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            {authButtonLabel}
          </button>
        </div>
        {isTaobaoPlatform ? (
          <div className="mb-4 rounded-2xl border border-border bg-surface-secondary p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-text-primary">Tally 服务商应用</h4>
                <p className="mt-1 text-xs text-text-secondary">
                  Tally 使用武汉对对科技有限公司的淘宝开放平台应用发起授权，客户只需要完成店铺授权。
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {renderServiceProviderAppStatus(appConfig)}
                {canManageServiceProviderApps && (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingPlatformAppCode('taobao');
                      void fetchPlatformAppConfig('taobao');
                    }}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                  >
                    <ShieldCheck className="h-3.5 w-3.5" />
                    服务商应用配置
                  </button>
                )}
              </div>
            </div>
            {appConfig.appKey && appConfig.hasAppSecret && (
              <p className="mt-3 text-sm text-green-700">
                Tally 服务商应用已配置，客户只需要完成店铺授权。
              </p>
            )}
            {!appConfig.loading && !appConfig.error && (!appConfig.appKey || !appConfig.hasAppSecret) && (
              <p className="mt-3 text-sm text-amber-700">
                Tally 服务商应用尚未配置，需由 Tally 管理员配置 AppKey、AppSecret 和回调地址后才能授权店铺。
              </p>
            )}
          </div>
        ) : null}
        {shopError && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            {shopError}
          </div>
        )}
        {shopNotice && (
          <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {shopNotice}
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
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="min-w-[1100px] w-full table-fixed text-sm">
              <colgroup>
                <col className="w-[20%]" />
                <col className="w-[20%]" />
                <col className="w-[10%]" />
                <col className="w-[15%]" />
                <col className="w-[13%]" />
                <col className="w-[22%]" />
              </colgroup>
              <thead className="bg-surface-secondary text-left text-text-secondary">
                <tr>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">{connectionNoun}名称</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">{connectionNoun} ID</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">授权状态</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">Token 到期</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">最近同步</th>
                  <th className="px-4 py-3 font-medium text-right whitespace-nowrap">操作</th>
                </tr>
              </thead>
              <tbody>
                {shops.map((shop) => {
                  const normalizedShopStatus = (shop.auth_status || shop.status || '').toLowerCase();
                  const isShopDisabled = ['disabled', 'revoked'].includes(normalizedShopStatus);

                  return (
                    <tr key={shop.id} className="border-t border-border-subtle text-text-primary">
                      <td className="px-4 py-3 truncate" title={shop.external_shop_name}>{shop.external_shop_name}</td>
                      <td className="px-4 py-3 truncate text-text-secondary" title={shop.external_shop_id}>{shop.external_shop_id}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(shop.auth_status || shop.status)}`}>
                          {getStatusLabel(shop.auth_status || shop.status)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{formatTime(shop.token_expires_at)}</td>
                      <td className="px-4 py-3 text-text-secondary">{formatTime(shop.last_sync_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => void loadPlatformShopDatasetDetails(shop)}
                            className="inline-flex whitespace-nowrap items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
                          >
                            <Database className="h-3.5 w-3.5" />
                            数据集
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleReauthorize(shop)}
                            disabled={actioningShopId === shop.id}
                            className="inline-flex whitespace-nowrap items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary hover:bg-surface-tertiary disabled:opacity-60 transition-colors"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            {isShopDisabled ? '重新授权启用' : '重授权'}
                          </button>
                          {!isShopDisabled && (
                            <button
                              type="button"
                              onClick={() => setDisableConfirmShop(shop)}
                              disabled={actioningShopId === shop.id}
                              className="inline-flex whitespace-nowrap items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-60 transition-colors"
                            >
                              <Ban className="h-3.5 w-3.5" />
                              停用
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  const renderDisableConfirmDialog = () => {
    if (!disableConfirmShop) return null;
    const normalizedPlatformCode = disableConfirmShop.platform_code.trim().toLowerCase();
    const connectionNoun = normalizedPlatformCode === 'alipay' ? '商户' : '店铺';
    const displayName =
      disableConfirmShop.external_shop_name ||
      disableConfirmShop.external_shop_id ||
      `${connectionNoun}授权`;
    const isDisabling = actioningShopId === disableConfirmShop.id;

    return (
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4 py-6">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="disable-shop-confirm-title"
          className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-xl"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 id="disable-shop-confirm-title" className="text-base font-semibold text-text-primary">
                确认停用授权？
              </h3>
              <p className="mt-1 truncate text-sm text-text-primary">{displayName}</p>
            </div>
            <button
              type="button"
              onClick={() => setDisableConfirmShop(null)}
              disabled={isDisabling}
              aria-label="关闭"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="mt-4 text-sm leading-6 text-text-secondary">
            停用后该{connectionNoun}授权将不可用于后续采集；如需恢复，需要重新授权。
          </p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setDisableConfirmShop(null)}
              disabled={isDisabling}
              className="inline-flex min-h-10 items-center justify-center rounded-xl border border-border bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void handleDisable(disableConfirmShop)}
              disabled={isDisabling}
              className="inline-flex min-h-10 min-w-28 items-center justify-center gap-2 rounded-xl border border-red-600 bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isDisabling && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
              确认停用
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderPlatformDatasetSemanticDrawer = () => {
    if (!editingDatasetSemantic || selectedSourceKind !== 'platform_oauth') return null;
    const editingSemanticFieldRows = editingDatasetSemantic.fieldRows;
    const editingUniqueIdentifierRawNameSet = new Set(editingDatasetSemantic.uniqueIdentifierRawNames);
    const editingUniqueIdentifierRows = editingSemanticFieldRows.filter((row) =>
      editingUniqueIdentifierRawNameSet.has(row.rawName),
    );
    const editingPendingFieldCount = editingSemanticFieldRows.filter((row) => row.pending).length;

    return (
      <div className="fixed inset-0 z-[60] bg-black/35" onClick={closeEditingDatasetSemantic}>
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
                </div>
                <p className="mt-1 truncate text-sm text-text-primary">{editingDatasetSemantic.datasetName}</p>
                <p className="mt-1 truncate text-xs text-text-secondary">
                  {editingDatasetSemantic.sourceName}
                  {editingDatasetSemantic.resourceKey ? ` · ${editingDatasetSemantic.resourceKey}` : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={closeEditingDatasetSemantic}
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-5">
            <div className="space-y-4">
              {datasetSemanticError && (
                <div className="sticky top-0 z-10 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 shadow-sm">
                  {datasetSemanticError}
                </div>
              )}
              {datasetSemanticNotice && (
                <div className="sticky top-0 z-10 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 shadow-sm">
                  {datasetSemanticNotice}
                </div>
              )}
              {refreshingDatasetSemantic && (
                <div className="flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在刷新语义建议，请稍候。
                </div>
              )}

              <label className="block rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                <span className="text-xs text-text-muted">业务名称</span>
                <input
                  value={editingDatasetSemantic.businessName}
                  onChange={(event) =>
                    setEditingDatasetSemantic((prev) =>
                      prev ? { ...prev, businessName: event.target.value } : prev,
                    )
                  }
                  className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                  placeholder="例如：支付宝资金账单"
                />
              </label>

              <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-text-secondary" />
                  <span className="text-sm font-medium text-text-primary">唯一标识字段</span>
                </div>
                {editingUniqueIdentifierRows.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {editingUniqueIdentifierRows.map((row) => (
                      <span
                        key={`platform-unique-identifier-${row.rawName}`}
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
              </div>

              <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-text-secondary" />
                      <span className="text-sm font-medium text-text-primary">字段语义确认</span>
                    </div>
                    <p className="mt-1 text-xs text-text-secondary">
                      当前共 {editingSemanticFieldRows.length} 个字段，待确认 {editingPendingFieldCount} 个。
                    </p>
                  </div>
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

                <div className="mt-4 max-h-[34rem] space-y-3 overflow-y-auto pr-1">
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
                        </div>
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

            </div>
          </div>

          <div className="border-t border-border bg-surface px-5 py-4">
            <div className="flex flex-wrap items-center justify-end gap-2">
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
    );
  };

  const renderPlatformCollectionDetailDrawer = () => {
    if (!collectionDetailDialog || selectedSourceKind !== 'platform_oauth') return null;
    const detail = collectionDetailDialog.detail ?? {};
    const collectionStats = asRecord(detail.collection_stats) ?? {};
    const jobs = Array.isArray(detail.jobs)
      ? detail.jobs.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
      : [];
    const rows = Array.isArray(detail.rows)
      ? detail.rows.filter((item): item is Record<string, unknown> => Boolean(asRecord(item)))
      : [];
    const latestJob = jobs[0] ?? {};
    const collectedCount = jobs.reduce((total, job) => {
      const metrics = asRecord(job.metrics) ?? {};
      return total + (asNumber(metrics.collection_upserted) ?? asNumber(metrics.row_count) ?? asNumber(metrics.rows) ?? 0);
    }, 0);
    const totalRecordCount =
      asNumber(collectionStats.total_count) ??
      asNumber(collectionStats.record_count) ??
      collectedCount ??
      rows.length;

    return (
      <div className="fixed inset-0 z-[60] bg-black/35" onClick={() => setCollectionDetailDialog(null)}>
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
                aria-label="关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
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
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                    <p className="text-xs text-text-muted">采集任务</p>
                    <p className="mt-2 text-lg font-semibold text-text-primary">{jobs.length} 次</p>
                  </div>
                  <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                    <p className="text-xs text-text-muted">采集记录数</p>
                    <p className="mt-2 text-lg font-semibold text-text-primary">{totalRecordCount || rows.length}</p>
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
                    <p className="text-sm font-medium text-text-primary">最近采集任务</p>
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
                        const requestPayload = asRecord(job.request_payload) ?? {};
                        const sourceRowCount = asNumber(metrics.row_count);
                        const collectionUpsertedCount = asNumber(metrics.collection_upserted);
                        const billDate = asString(requestPayload.bill_date) || asString(requestPayload.biz_date) || '';
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
                            <div className="mt-2 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
                              <p>源表读取：{typeof sourceRowCount === 'number' ? sourceRowCount : '未返回'} 条</p>
                              <p>资产记录：{typeof collectionUpsertedCount === 'number' ? collectionUpsertedCount : '未返回'} 条</p>
                              {billDate && <p>采集日期：{billDate}</p>}
                            </div>
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
                      const fieldGroups = normalizePlatformFieldGroups(detail.field_groups ?? detail.fieldGroups);
                      const columns = buildSemanticSampleTableColumns(fieldGroups, sampleRows);
                      if (columns.length === 0) {
                        return <p className="px-3 py-3 text-sm text-text-secondary">暂无可展示字段。</p>;
                      }
                      return (
                        <table className="min-w-full divide-y divide-border text-left text-xs">
                          <thead className="sticky top-0 z-10 bg-surface-secondary text-text-secondary">
                            <tr>
                              {columns.map((column) => (
                                <th key={column.rawName} className="whitespace-nowrap px-3 py-2 font-medium">
                                  {column.displayName}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border text-text-primary">
                            {sampleRows.map((row, rowIndex) => (
                              <tr key={`platform-collection-sample-${rowIndex}`} className="hover:bg-surface-secondary/60">
                                {columns.map((column) => (
                                  <td
                                    key={`${rowIndex}-${column.rawName}`}
                                    className="max-w-56 truncate px-3 py-2"
                                    title={formatSampleCellValue(row[column.rawName])}
                                  >
                                    {formatSampleCellValue(row[column.rawName])}
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
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderAlipayAuthDialog = () => {
    if (!alipayAuthDialog) return null;
    const merchantDisplayName = alipayAuthDialog.merchantDisplayName;
    const trimmedMerchantDisplayName = merchantDisplayName.trim();
    const isSubmitting = launchingAuthPlatform === 'alipay';

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
        <div role="dialog" aria-modal="true" aria-labelledby="alipay-auth-title" className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-xl">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 id="alipay-auth-title" className="text-base font-semibold text-text-primary">
                新增支付宝商户授权
              </h3>
              <p className="mt-1 text-sm text-text-secondary">
                生成绑定当前 Tally 企业的专属授权链接，可发给商户管理员在任意电脑完成授权。
              </p>
            </div>
            <button
              type="button"
              onClick={() => setAlipayAuthDialog(null)}
              disabled={isSubmitting}
              aria-label="关闭"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-text-secondary transition-colors hover:bg-surface-tertiary hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <label className="mt-4 block space-y-2 text-sm">
            <span className="font-medium text-text-primary">商户显示名称</span>
            <input
              value={merchantDisplayName}
              onChange={(event) =>
                setAlipayAuthDialog((current) =>
                  current
                    ? {
                        ...current,
                        merchantDisplayName: event.target.value,
                        authUrl: '',
                        notice: '',
                        error: '',
                      }
                    : current,
                )
              }
              className="w-full rounded-xl border border-border bg-surface-secondary px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
              placeholder="例如：福游网络"
              autoFocus
            />
          </label>

          {alipayAuthDialog.error && (
            <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {alipayAuthDialog.error}
            </div>
          )}

          {alipayAuthDialog.notice && (
            <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {alipayAuthDialog.notice}
            </div>
          )}

          {alipayAuthDialog.authUrl && (
            <div className="mt-4 rounded-xl border border-border bg-surface-secondary p-3">
              <p className="text-xs font-medium text-text-primary">企业专属授权链接</p>
              <textarea
                value={alipayAuthDialog.authUrl}
                readOnly
                className="mt-2 min-h-24 w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-xs text-text-primary outline-none"
                aria-label="企业专属授权链接"
              />
              <div className="mt-3 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(alipayAuthDialog.authUrl);
                    setAlipayAuthDialog((current) =>
                      current ? { ...current, notice: '授权链接已复制。' } : current,
                    );
                  }}
                  className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-surface-tertiary"
                >
                  <Link2 className="h-3.5 w-3.5" />
                  复制链接
                </button>
                <a
                  href={alipayAuthDialog.authUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-500"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  打开授权
                </a>
              </div>
            </div>
          )}

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setAlipayAuthDialog(null)}
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-60"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void launchAuthFlow('alipay', trimmedMerchantDisplayName)}
              disabled={!trimmedMerchantDisplayName || isSubmitting}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              生成专属授权链接
            </button>
          </div>
        </div>
      </div>
    );
  };

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
    if (selectedSourceKind === 'browser_playbook') {
      return (
        <BrowserPlaybookPanel
          authToken={authToken ?? null}
          sources={selectedKindSources}
          loadingSources={loadingSources}
          openCreateSignal={browserCreateSignal}
          onRegistered={refreshCurrentConnectionView}
        />
      );
    }
    return renderReservedPanel(selectedSourceKind);
  };

  if (!authToken && mode === 'callback' && callbackPayload) {
    const isSuccess = callbackPayload.status === 'success';
    return (
      <div className="flex-1 flex items-center justify-center bg-surface-secondary p-6">
        <div className="w-full max-w-xl rounded-2xl border border-border bg-surface p-8 text-center shadow-sm">
          <div
            className={`mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl ${
              isSuccess ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-500'
            }`}
          >
            {isSuccess ? <CheckCircle2 className="h-6 w-6" /> : <AlertCircle className="h-6 w-6" />}
          </div>
          <h2 className="text-xl font-semibold text-text-primary">
            {isSuccess ? '支付宝授权已完成' : '支付宝授权未完成'}
          </h2>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            {callbackPayload.message ||
              (isSuccess
                ? '授权结果已返回 Tally，请登录后查看绑定结果。'
                : '授权流程返回失败，请登录后重新发起授权。')}
          </p>
          {callbackPayload.shopName && (
            <p className="mt-2 text-sm text-text-secondary">支付宝商户：{callbackPayload.shopName}</p>
          )}
          <button
            type="button"
            onClick={onLoginRequired}
            className="mt-5 inline-flex items-center justify-center rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
          >
            登录
          </button>
        </div>
      </div>
    );
  }

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
    const canBindAlipayCallback =
      isSuccess &&
      callbackPayload.platformCode === 'alipay' &&
      Boolean(callbackPayload.pendingAuthorizationId && callbackPayload.claimCode);
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
                  <p className="mt-2 text-sm text-text-secondary">支付宝商户：{callbackPayload.shopName}</p>
                )}
                {canBindAlipayCallback && (
                  <div className="mt-4 rounded-xl border border-border bg-surface-secondary p-4">
                    <h3 className="text-sm font-semibold text-text-primary">绑定支付宝授权到当前企业</h3>
                    <label className="mt-3 block text-sm font-medium text-text-primary">
                      支付宝商户名称
                      <input
                        value={alipayClaimForm.merchantDisplayName}
                        onChange={(event) =>
                          setAlipayClaimForm((current) => ({
                            ...current,
                            merchantDisplayName: event.target.value,
                          }))
                        }
                        className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                        placeholder="例如：福游网络"
                      />
                    </label>
                    {alipayClaimError && (
                      <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                        {alipayClaimError}
                      </div>
                    )}
                    {alipayClaimNotice && (
                      <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                        {alipayClaimNotice}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => void claimAlipayPendingAuthorization()}
                      disabled={claimingAlipayAuthorization || !alipayClaimForm.merchantDisplayName.trim()}
                      className="mt-3 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {claimingAlipayAuthorization ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4" />
                      )}
                      绑定到当前企业
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => {
                  clearCallbackQuery('data-connections');
                  if (callbackPayload.platformCode === 'alipay') {
                    setSelectedPlatform({
                      platform_code: 'alipay',
                      platform_name: '支付宝',
                      authorized_shop_count: 0,
                      error_shop_count: 0,
                    });
                    if (callbackPayload.claimCode) {
                      fillAlipayClaimFormFromCallback(callbackPayload);
                    }
                    setMode('platform');
                    const loadingTasks: Promise<unknown>[] = [
                      fetchPlatformAppConfig('alipay'),
                      fetchShops('alipay'),
                    ];
                    if (callbackPayload.claimCode) {
                      loadingTasks.push(fetchAlipayPendingAuthorizations());
                    }
                    void Promise.all(loadingTasks);
                  } else {
                    setMode('overview');
                  }
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
                {selectedConnectionView === 'data_sources' && selectedSourceKind === 'browser_playbook' && (
                  <button
                    type="button"
                    onClick={() => setBrowserCreateSignal((current) => current + 1)}
                    className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary transition-colors hover:bg-surface-tertiary"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    新增
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void refreshCurrentConnectionView()}
                  className="inline-flex items-center gap-1.5 rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary transition-colors hover:bg-surface-tertiary"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  刷新
                </button>
                <span className="rounded-full bg-surface-secondary px-3 py-1.5 text-text-secondary">
                  当前 {selectedConnectionView === 'collaboration_channels'
                    ? `${selectedProviderChannels.length} 个通道`
                    : selectedSourceKind === 'platform_oauth'
                    ? `${totalAuthorizedShops} 个连接`
                    : `${selectedKindSources.length} 个连接`}
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
          {renderServiceProviderAppConfigPanel()}
          {renderCollaborationChannelDialog()}
          {renderPlatformDatasetDialog()}
          {renderPlatformDatasetSemanticDrawer()}
          {renderPlatformCollectionDetailDrawer()}
          {renderDisableConfirmDialog()}
          {renderAlipayAuthDialog()}
        </section>
      </div>
    </div>
  );
}
