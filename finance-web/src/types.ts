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
}

// ── 会话类型 ──────────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
  messages: Message[];
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

// ── Agent 类型 ──────────────────────────────────────────────────────────────

export type AgentType = 'reconciliation' | 'data_process';

export interface AgentInfo {
  id: AgentType;
  name: string;
  description: string;
  icon: string;
}

// 可用的 Agent 列表
export const AVAILABLE_AGENTS: AgentInfo[] = [
  {
    id: 'reconciliation',
    name: '智能对账助手',
    description: '专业的财务对账助手，支持对账规则生成和执行',
    icon: 'BarChart3',
  },
  {
    id: 'data_process',
    name: '数据整理数字员工',
    description: '通用的数据整理平台，支持审计数据整理等业务',
    icon: 'FileSpreadsheet',
  },
];

// ── WebSocket 消息协议 ───────────────────────────────────────────────────

export interface WsIncoming {
  message: string;
  thread_id: string;
  resume?: boolean;
}

export interface WsOutgoing {
  type: 'message' | 'stream' | 'interrupt' | 'done' | 'error' | 'auth' | 'auth_verify' | 'conversation_created';
  content?: string;
  payload?: Record<string, unknown>;
  thread_id?: string;
  node?: string;
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
