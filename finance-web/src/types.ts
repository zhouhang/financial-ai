// ── 消息类型 ──────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'system';

export type SystemAction = 'read' | 'write' | 'tool' | 'info';

export interface MessageAttachment {
  name: string;
  size: number;
  path?: string;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  /** 消息附件（文件） */
  attachments?: MessageAttachment[];
  /** 系统消息的操作类型 */
  action?: SystemAction;
  /** 系统消息的详情（如文件路径） */
  actionDetail?: string;
  /** 系统消息是否完成 */
  actionDone?: boolean;
  /** 节点级进度消息对应的节点名 */
  nodeName?: string;
  /** 节点级进度消息当前状态 */
  nodeStatus?: 'running' | 'completed';
  /** 节点级进度消息展示标签 */
  nodeLabel?: string;
  /** 节点级进度消息辅助说明 */
  nodeDetail?: string;
}

// ── 会话类型 ──────────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
  messages: Message[];
  taskContext?: UserTaskRule | null;
}

// ── 任务类型 ──────────────────────────────────────────────────────────────

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  detail?: string;
}

// ── 文件类型 ──────────────────────────────────────────────────────────────

export interface UploadedFile {
  name: string;
  path: string;
  size: number;
  uploadedAt: Date;
}

// ── WebSocket 消息协议 ───────────────────────────────────────────────────

export interface WsIncoming {
  message: string;
  thread_id: string;
  resume?: boolean;
}

export interface WsOutgoing {
  type: 'message' | 'stream' | 'interrupt' | 'done' | 'error' | 'auth' | 'auth_verify' | 'conversation_created' | 'node_status';
  content?: string;
  payload?: Record<string, unknown>;
  thread_id?: string;
  node?: string;
  status?: 'running' | 'completed';
  label?: string;
  detail?: string;
  /** auth 和 auth_verify 类型专用 */
  token?: string;
  user?: Record<string, unknown>;
  /** auth_verify 类型专用 - 验证是否成功 */
  success?: boolean;
  /** conversation_created 类型专用 */
  conversation_id?: string;
}

// ── 连接状态 ─────────────────────────────────────────────────────────────

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

// ── 任务类型 ──────────────────────────────────────────────────────────────

export interface UserTaskRule {
  id: number;
  user_id?: string | null;
  task_id?: number | null;
  rule_code: string;
  name: string;
  rule_type: string;
  remark?: string;
  task_code: string;
  task_name: string;
  task_type: 'proc' | 'recon' | string;
  file_rule_code?: string;
  supported_entry_modes?: string[];
}

export interface UserTask {
  id: number;
  user_id?: string | null;
  task_code: string;
  task_name: string;
  description?: string;
  task_type: 'proc' | 'recon' | string;
  rules: UserTaskRule[];
}

// ── 数据连接类型 ────────────────────────────────────────────────────────────

export type AppSection = 'chat' | 'data-connections';
export type ReconWorkspaceMode = 'upload' | 'center';

export type DataConnectionView = 'data_sources' | 'collaboration_channels';

export type PlatformCode =
  | 'taobao'
  | 'tmall'
  | 'douyin_shop'
  | 'kuaishou'
  | 'jd'
  | 'pinduoduo'
  | string;

export interface PlatformConnectionSummary {
  platform_code: PlatformCode;
  platform_name: string;
  authorized_shop_count: number;
  error_shop_count: number;
  last_sync_at?: string | null;
  status?: string;
}

export interface ShopConnection {
  id: string;
  platform_code: PlatformCode;
  external_shop_id: string;
  external_shop_name: string;
  auth_status: string;
  status?: string;
  token_expires_at?: string | null;
  last_sync_at?: string | null;
  last_status?: string | null;
}

export interface AuthCallbackPayload {
  platformCode: string;
  status: string;
  message: string;
  shopName?: string;
}

export type DataSourceKind =
  | 'platform_oauth'
  | 'database'
  | 'api'
  | 'file'
  | 'browser'
  | 'desktop_cli';

export type DataSourceExecutionMode = 'deterministic' | 'agent_assisted';

export type DataSourceHealthStatus =
  | 'healthy'
  | 'warning'
  | 'error'
  | 'auth_expired'
  | 'disabled'
  | 'active'
  | 'pending'
  | string;

export interface DataSourceHealthSummary {
  connection_status?: DataSourceHealthStatus;
  dataset_status?: DataSourceHealthStatus;
  warning_count?: number;
  error_count?: number;
  last_checked_at?: string | null;
  last_sync_at?: string | null;
  last_error_message?: string | null;
}

export interface DataSourceDatasetSummary {
  id: string;
  dataset_code: string;
  dataset_name: string;
  origin_type?: 'fixed' | 'discovered' | 'imported_openapi' | 'manual' | string;
  dataset_kind?: string;
  resource_key?: string;
  status?: string;
  is_enabled?: boolean;
  health_status?: DataSourceHealthStatus;
  last_checked_at?: string | null;
  last_sync_at?: string | null;
  last_error_message?: string | null;
  extract_config?: Record<string, unknown>;
  schema_summary?: Record<string, unknown>;
  sync_strategy?: Record<string, unknown>;
  meta?: Record<string, unknown>;
}

export interface DataSourceEventSummary {
  id: string;
  level?: 'info' | 'warning' | 'error' | string;
  event_type?: string;
  message: string;
  created_at?: string | null;
  dataset_code?: string | null;
  meta?: Record<string, unknown>;
}

export interface DataSourceDatabaseConfig {
  db_type?: string;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string;
  ssl_mode?: string;
  connect_timeout?: number;
  schema_whitelist?: string[];
}

export interface DataSourceApiConfig {
  base_url?: string;
  auth_mode?: string;
  credential_kind?: string;
  auth_request_url?: string;
  auth_request_method?: string;
  auth_request_payload_type?: string;
  auth_apply_value_template?: string;
  auth_response_path?: string;
  auth_apply_header_name?: string;
  auth_apply_prefix?: string;
  auth_request_configured?: boolean;
  auth_request_headers?: Record<string, string>;
  auth_request_params?: Record<string, string>;
  auth_request_json_payload?: Record<string, unknown>;
  auth_request_payload?: Record<string, unknown>;
  auth_type?: string;
  token?: string;
  api_key?: string;
  api_key_header?: string;
  basic_auth_header?: string;
  health_path?: string;
  timeout_seconds?: number;
  rate_limit_qps?: number;
  openapi_source?: string;
}

export interface DataSourceDiscoverSummary {
  discovered_count?: number;
  enabled_count?: number;
  last_discover_at?: string | null;
  last_discover_status?: string;
  last_discover_error?: string | null;
}

export interface DataSourceCapabilities {
  can_discover?: boolean;
  can_import_openapi?: boolean;
  can_add_manual_endpoint?: boolean;
  can_manage_datasets?: boolean;
}

export interface DataSourceListItem {
  id: string;
  source_kind: DataSourceKind;
  provider_code: string;
  name: string;
  status: string;
  execution_mode: DataSourceExecutionMode;
  code?: string;
  description?: string;
  updated_at?: string | null;
  health_status?: DataSourceHealthStatus;
  last_checked_at?: string | null;
  last_error_message?: string | null;
  health_summary?: DataSourceHealthSummary;
  source_summary?: Record<string, unknown>;
  dataset_summary?: Record<string, unknown>;
  datasets?: DataSourceDatasetSummary[];
  recent_events?: DataSourceEventSummary[];
  connection_config?: {
    database?: DataSourceDatabaseConfig;
    api?: DataSourceApiConfig;
    auth_status?: string;
    token_expires_at?: string | null;
  };
  discover_summary?: DataSourceDiscoverSummary;
  capabilities?: DataSourceCapabilities;
  metadata?: Record<string, unknown>;
}

export type CollaborationProvider = 'dingtalk_dws' | 'feishu' | 'wechat_work' | string;

export interface CollaborationChannelListItem {
  id: string;
  provider: CollaborationProvider;
  channel_code: string;
  name: string;
  client_id?: string;
  client_secret?: string;
  robot_code?: string;
  is_default?: boolean;
  is_enabled?: boolean;
  updated_at?: string | null;
  extra?: Record<string, unknown>;
}
