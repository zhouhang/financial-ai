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
    connect_timeout: string;
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
  } catch (error) {
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
      connect_timeout: databaseConfig?.connect_timeout ? String(databaseConfig.connect_timeout) : '',
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
            connect_timeout: asNumber(databaseConfigRaw.connect_timeout),
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
    discover_summary: discoverSummaryRaw
      ? {
          discovered_count: asNumber(discoverSummaryRaw.discovered_count),
          enabled_count: asNumber(discoverSummaryRaw.enabled_count),
          last_discover_at: asStringOrNull(discoverSummaryRaw.last_discover_at),
          last_discover_status: asString(discoverSummaryRaw.last_discover_status),
          last_discover_error: asStringOrNull(discoverSummaryRaw.last_discover_error),
        }
      : undefined,
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
  const [sourceDetails, setSourceDetails] = useState<Record<string, SourceDetailState>>({});
  const [sourceForms, setSourceForms] = useState<Record<string, EditableSourceConfig>>({});
  const [expandedSourceConfigIds, setExpandedSourceConfigIds] = useState<string[]>([]);
  const [sourceActionBusy, setSourceActionBusy] = useState<string | null>(null);
  const [sourceActionError, setSourceActionError] = useState('');
  const [sourceActionNotice, setSourceActionNotice] = useState('');
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
    setShops([]);
    setShopError('');
  }, [selectedConnectionView, selectedSourceKind, selectedCollaborationProvider]);

  useEffect(() => {
    if (selectedConnectionView !== 'collaboration_channels') return;
    if (editingChannel && editingChannel.provider !== selectedCollaborationProvider) {
      setEditingChannel(null);
      setChannelError('');
    }
  }, [editingChannel, selectedCollaborationProvider, selectedConnectionView]);

  useEffect(() => {
    saveCollaborationChannelDrafts(draftChannels);
  }, [draftChannels]);

  const authHeaders = useMemo(
    () => ({
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    }),
    [authToken],
  );

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
      primeSourceForm(source);
      primeSourceDetail(source);
      void hydrateSourceDetail(source.id);
    },
    [hydrateSourceDetail, primeSourceDetail, primeSourceForm],
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
      const trimmedName = form.name.trim();

      let connectionConfig: Record<string, unknown> = {};
      let authConfig: Record<string, unknown> = {};
      try {
        if (source.source_kind === 'database') {
          const dbType = inferDatabaseType(source.provider_code, form.database.db_type);
          connectionConfig = compactObject({
            db_type: dbType,
            host: form.database.host.trim(),
            port: parseOptionalNumber(form.database.port, '端口'),
            database: form.database.database.trim(),
            username: form.database.username.trim(),
            connect_timeout: parseOptionalNumber(form.database.connect_timeout, '连接超时'),
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
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '连接配置格式不正确');
        setSourceActionNotice('');
        return;
      }

      const payload = {
        name:
          trimmedName ||
          source.name ||
          `${source.source_kind === 'database' ? '数据库' : source.source_kind === 'api' ? 'API' : '文件'}连接`,
        description: form.description.trim(),
        connection_config: connectionConfig,
        ...(Object.keys(authConfig).length > 0 ? { auth_config: authConfig } : {}),
      };

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
          name: payload.name,
          description: payload.description,
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
                    name: payload.name,
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
      setSourceActionBusy(`test:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${source.id}/test`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '测试连接失败'));
        }
        setSourceActionNotice(String(data?.message || '连接测试通过'));
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
    async (source: DataSourceListItem) => {
      if (!authToken || draftSourceIdSet.has(source.id)) return;
      setSourceActionBusy(`discover:${source.id}`);
      setSourceActionError('');
      setSourceActionNotice('');
      try {
        const response = await fetch(`/api/data-sources/${source.id}/discover`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            persist: true,
            schema_whitelist: [],
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
        updateSourceDetail(source.id, (current) => ({
          ...current,
          datasets: datasets.length > 0 ? datasets : current.datasets,
          datasetsApiAvailable: true,
          datasetsError: '',
        }));
        setSourceActionNotice(String(data?.message || '数据集目录已刷新'));
        await fetchRemoteSources();
        await fetchSourceEvents(source.id);
      } catch (error) {
        setSourceActionError(error instanceof Error ? error.message : '重新发现数据集失败');
      } finally {
        setSourceActionBusy(null);
      }
    },
    [authHeaders, authToken, draftSourceIdSet, fetchRemoteSources, fetchSourceEvents, updateSourceDetail],
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

  const renderSourceList = (kind: Extract<DataSourceKind, 'database' | 'api' | 'file'>) => {
    const rows = selectedKindSources.filter((item) => item.source_kind === kind);
    const activeSource =
      selectedSource && selectedSource.source_kind === kind
        ? selectedSource
        : rows.find((item) => item.id === selectedSourceId) ?? rows[0] ?? null;
    const detailState = activeSource ? sourceDetails[activeSource.id] ?? createDefaultSourceDetail() : createDefaultSourceDetail();
    const datasets = detailState.datasets.length > 0 ? detailState.datasets : activeSource?.datasets ?? [];
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

    return (
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
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

        <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          {!activeSource ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-12 text-center text-sm text-text-secondary">
              选择左侧连接后，在这里查看连接详情和数据集目录。
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
                    onClick={() => {
                      primeSourceDetail(activeSource);
                      void hydrateSourceDetail(activeSource.id);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary transition-colors hover:bg-surface-tertiary"
                  >
                    <RefreshCw className="h-4 w-4" />
                    刷新状态
                  </button>
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
                          恢复已保存
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
                        <span className="text-xs text-text-muted">连接超时（秒）</span>
                        <input
                          value={sourceForm.database.connect_timeout}
                          onChange={(event) =>
                            updateSourceForm(activeSource.id, (current) => ({
                              ...current,
                              database: {
                                ...current.database,
                                connect_timeout: event.target.value,
                              },
                            }))
                          }
                          className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition-colors focus:border-blue-300"
                          placeholder="默认 5"
                        />
                      </label>

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
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-semibold text-text-primary">数据集目录</h4>
                    <p className="mt-1 text-xs text-text-secondary">
                      连接只解决接入，真正给规则绑定的是这里的数据集。
                    </p>
                  </div>
                  <span className="rounded-full bg-surface-secondary px-3 py-1 text-xs text-text-secondary">
                    {datasets.length} 个数据集
                  </span>
                </div>

                {detailState.datasetsLoading ? (
                  <div className="flex items-center justify-center rounded-xl border border-border-subtle bg-surface-secondary px-4 py-8 text-sm text-text-secondary">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    正在加载数据集目录
                  </div>
                ) : detailState.datasetsError ? (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                    {detailState.datasetsError}
                  </div>
                ) : detailState.datasetsApiAvailable === false ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                    当前环境尚未接入数据集目录接口。
                  </div>
                ) : datasets.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
                    暂无数据集，可通过上方“更新数据集”或本页配置生成目录。
                  </div>
                ) : (
                  <div className="space-y-2">
                    {datasets.map((dataset) => (
                      <div key={dataset.id} className="rounded-2xl border border-border bg-surface-secondary px-4 py-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-sm font-medium text-text-primary">{dataset.dataset_name}</p>
                              <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${statusBadgeClass(dataset.health_status || dataset.status)}`}>
                                {getStatusLabel(dataset.health_status || dataset.status)}
                              </span>
                              <span className="inline-flex rounded-full bg-surface px-2 py-0.5 text-[11px] text-text-secondary">
                                {dataset.dataset_kind || 'dataset'}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-text-muted">
                              {dataset.dataset_code}
                              {dataset.resource_key ? ` · ${dataset.resource_key}` : ''}
                            </p>
                          </div>
                          <div className="text-right text-xs text-text-secondary">
                            <p>最近同步：{formatTime(dataset.last_sync_at)}</p>
                            <p>最近检查：{formatTime(dataset.last_checked_at)}</p>
                          </div>
                        </div>
                        {dataset.last_error_message && (
                          <p className="mt-2 text-xs text-red-600">{dataset.last_error_message}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </div>
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
