// ── 消息类型 ──────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'system';

export type SystemAction = 'read' | 'write' | 'tool' | 'info';

export interface MessageAttachment {
  name: string;
  size: number;
  path?: string;
}

// ── Skill 命中卡片类型 ─────────────────────────────────────────

export interface SkillInputFile {
  name: string;
  required: boolean;
  hint?: string;
}

export interface SkillHitInfo {
  skillId: string;
  skillName: string;
  skillDescription: string;
  skillTags: string[];
  skillIcon: string;
  skillInputFiles: SkillInputFile[];
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
  /** deep_agent 思考过程内容（折叠展示） */
  thinkingContent?: string;
  /** 是否为 deep_agent 思考过程消息 */
  isThinking?: boolean;
  /** skill 命中信息（展示为独立卡片） */
  skillHit?: SkillHitInfo;
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

/**
 * stream 消息的子类型（subtype）
 * - 'continue'  ：默认，继续在当前气泡内累积内容
 * - 'new_bubble'：强制开启新气泡，将后续内容放到独立对话框内
 */
export type StreamSubtype = 'continue' | 'new_bubble';

export interface WsOutgoing {
  type: 'message' | 'stream' | 'thinking' | 'skill_hit' | 'interrupt' | 'done' | 'error' | 'auth' | 'auth_verify' | 'conversation_created';
  content?: string;
  /** stream 类型专用 - 分气泡控制 */
  subtype?: StreamSubtype;
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
  /** skill_hit 类型专用 */
  skill_id?: string;
  skill_name?: string;
  skill_description?: string;
  skill_tags?: string[];
  skill_icon?: string;
  skill_input_files?: SkillInputFile[];
}

// ── 连接状态 ─────────────────────────────────────────────────────────────

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';
