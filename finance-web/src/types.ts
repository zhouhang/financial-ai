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

// ── 数字员工和规则类型 ───────────────────────────────────────────────────

export interface DigitalEmployee {
  id: number;
  code: string;
  name: string;
  desc_text?: string;
  type: string;
  memo?: string;
}

export interface EmployeeRule {
  id: number;
  code: string;
  name: string;
  desc_text?: string;
  type: string;
  parent_code?: string;
  memo?: string;
  file_rule_code?: string;  // 文件校验规则编码
}
