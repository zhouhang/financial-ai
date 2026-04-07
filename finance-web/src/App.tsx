import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import DataConnectionsPanel from './components/DataConnectionsPanel';
import ReconWorkspace from './components/ReconWorkspace';
import LoginModal from './components/LoginModal';
import type { ReconExecutionMode } from './components/recon/ReconConversationBar';
import { useWebSocket } from './hooks/useWebSocket';
import { useConversations } from './hooks/useConversations';
import type {
  AppSection,
  AuthCallbackPayload,
  CollaborationProvider,
  Conversation,
  DataConnectionView,
  DataSourceKind,
  Message,
  ReconWorkspaceMode,
  Task,
  UploadedFile,
  UserTaskRule,
  WsOutgoing,
} from './types';

type MainPanelView = 'conversation' | 'data-connections';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function createConversation(taskContext: UserTaskRule | null = null): Conversation {
  return {
    id: generateId(),
    title: '新对话',
    createdAt: new Date(),
    updatedAt: new Date(),
    messages: [],
    taskContext,
  };
}

// localStorage 键名
const STORAGE_KEY_ACTIVE_CONV = 'tally_active_conversation_id';
const STORAGE_KEY_IS_NEW_CONV = 'tally_is_new_conversation';
const STORAGE_KEY_GUEST_CONV = 'tally_guest_conversation';
const EMPTY_RECON_RULE: UserTaskRule = {
  id: 0,
  rule_code: '',
  name: '未命名方案',
  rule_type: 'recon',
  task_code: 'recon',
  task_name: '数据对账',
  task_type: 'recon',
};

function parsePanelViewFromLocation(): MainPanelView {
  const path = window.location.pathname.toLowerCase();
  const section = new URLSearchParams(window.location.search).get('section');
  if (section === 'data-connections') {
    return 'data-connections';
  }
  if (path.includes('/data-connections')) {
    return 'data-connections';
  }
  return 'conversation';
}

function parseAuthCallbackPayloadFromLocation(): AuthCallbackPayload | null {
  const path = window.location.pathname.toLowerCase();
  const params = new URLSearchParams(window.location.search);
  const status = params.get('platform_auth_status') || params.get('status');
  const platformCode = params.get('platform_code') || params.get('platform') || '';
  const message = params.get('platform_auth_message') || params.get('message') || '';
  const shopName = params.get('shop_name') || undefined;

  if (!status && !path.includes('auth-callback') && !path.includes('auth_result')) {
    return null;
  }

  return {
    platformCode: platformCode || 'unknown',
    status: status || 'unknown',
    message: message || '授权流程已返回，请检查授权结果。',
    shopName,
  };
}

/** 序列化会话用于 localStorage（Date 转为 ISO 字符串） */
function serializeGuestConv(conv: Conversation): string {
  return JSON.stringify({
    id: conv.id,
    title: conv.title,
    createdAt: conv.createdAt.toISOString(),
    updatedAt: conv.updatedAt.toISOString(),
    messages: conv.messages.map((m) => ({
      ...m,
      timestamp: m.timestamp.toISOString(),
    })),
  });
}

/** 从 localStorage 解析游客会话 */
function parseGuestConv(json: string): Conversation | null {
  try {
    const parsed = JSON.parse(json);
    if (!parsed?.id) return null;
    return {
      id: parsed.id,
      title: parsed.title || '新对话',
      createdAt: new Date(parsed.createdAt || Date.now()),
      updatedAt: new Date(parsed.updatedAt || Date.now()),
      messages: (parsed.messages || []).map((m: { timestamp: string; [k: string]: unknown }) => ({
        ...m,
        timestamp: new Date(m.timestamp),
      })),
    };
  } catch {
    return null;
  }
}

function isBlockingBackdrop(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element);
  if (style.position !== 'fixed' || style.pointerEvents === 'none') {
    return false;
  }

  const rect = element.getBoundingClientRect();
  const coversViewport =
    rect.top <= 1 &&
    rect.left <= 1 &&
    rect.width >= window.innerWidth - 1 &&
    rect.height >= window.innerHeight - 1;

  if (!coversViewport) {
    return false;
  }

  const zIndex = Number(style.zIndex);
  const background = style.backgroundColor.replace(/\s+/g, '');
  const isDarkBackdrop = /^rgba?\(0,0,0(?:,[0-9.]+)?\)$/.test(background);

  return Number.isFinite(zIndex) && zIndex >= 40 && isDarkBackdrop;
}

function removeBlockingBackdrop(element: HTMLElement): void {
  element.style.display = 'none';
  element.style.pointerEvents = 'none';
  element.setAttribute('aria-hidden', 'true');
  element.remove();
}

function clearResidualBlockingBackdrops(): void {
  document.body.style.removeProperty('overflow');

  document.querySelectorAll<HTMLElement>('[data-login-modal-backdrop="true"]').forEach((element) => {
    removeBlockingBackdrop(element);
  });

  document.querySelectorAll<HTMLElement>('body *').forEach((element) => {
    if (!isBlockingBackdrop(element)) {
      return;
    }

    removeBlockingBackdrop(element);
  });
}

// 从 localStorage 读取初始会话状态（区分游客/登录）
function getInitialConversationState(): {
  activeId: string;
  isNewConv: boolean;
  conversations: Conversation[];
  pendingNew: Conversation | null;
} {
  const token = localStorage.getItem('tally_auth_token');
  if (!token) {
    // 游客模式：从本地存储恢复
    const guest = localStorage.getItem(STORAGE_KEY_GUEST_CONV);
    const conv = guest ? parseGuestConv(guest) : null;
    if (conv) {
      return { activeId: conv.id, isNewConv: false, conversations: [conv], pendingNew: null };
    }
    const newConv = createConversation();
    return { activeId: newConv.id, isNewConv: true, conversations: [], pendingNew: newConv };
  }
  // 已登录
  const savedActiveId = localStorage.getItem(STORAGE_KEY_ACTIVE_CONV);
  if (savedActiveId) {
    return { activeId: savedActiveId, isNewConv: false, conversations: [], pendingNew: null };
  }
  return { activeId: '', isNewConv: false, conversations: [], pendingNew: null };
}

const initialState = getInitialConversationState();

export default function App() {
  // ── 会话状态 ──────────────────────────────────────────────
  const [conversations, setConversations] = useState<Conversation[]>(initialState.conversations);
  const [activeConvId, setActiveConvId] = useState<string>(initialState.activeId);
  
  // ── 当前会话 ──────────────────────────────────────────────
  // 追踪"待确认"的新会话（用户点击新建或刷新页面时，还没发消息）
  const pendingNewConvRef = useRef<Conversation | null>(initialState.pendingNew);
  
  // ── 会话加载状态 ──────────────────────────────────────────
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  
  const activeConv = conversations.find((c) => c.id === activeConvId) 
    || (pendingNewConvRef.current?.id === activeConvId ? pendingNewConvRef.current : undefined);
  const messages = activeConv?.messages || [];
  const selectedTask = activeConv?.taskContext ?? null;

  // ── 认证状态 ────────────────────────────────────────────────
  const [authToken, setAuthToken] = useState<string | null>(() => {
    return localStorage.getItem('tally_auth_token');
  });
  const [currentUser, setCurrentUser] = useState<Record<string, unknown> | null>(() => {
    const saved = localStorage.getItem('tally_current_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  /** 登录框标题提示，如「登录后使用完整功能」；为空时显示默认「登录」/「注册」 */
  const [loginModalTitleHint, setLoginModalTitleHint] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [panelView, setPanelView] = useState<MainPanelView>(() => parsePanelViewFromLocation());
  const [selectedDataConnectionView, setSelectedDataConnectionView] = useState<DataConnectionView>('data_sources');
  const [selectedDataSourceKind, setSelectedDataSourceKind] = useState<DataSourceKind>('platform_oauth');
  const [selectedCollaborationProvider, setSelectedCollaborationProvider] = useState<CollaborationProvider>('dingtalk_dws');
  const [reconRules, setReconRules] = useState<UserTaskRule[]>([]);
  const [reconExecutionMode, setReconExecutionMode] = useState<ReconExecutionMode>('upload');
  const [reconWorkspaceMode, setReconWorkspaceMode] = useState<ReconWorkspaceMode>('upload');
  const [hiddenConversationIds, setHiddenConversationIds] = useState<string[]>([]);
  const [authCallbackPayload] = useState<AuthCallbackPayload | null>(() =>
    parseAuthCallbackPayloadFromLocation(),
  );

  const isGuest = !authToken;

  useEffect(() => {
    if (!authToken) return;
    setIsLoginModalOpen(false);
    setLoginModalTitleHint(null);
  }, [authToken]);

  useEffect(() => {
    let aborted = false;

    if (!authToken) {
      setReconRules([]);
      return undefined;
    }

    const loadReconRules = async () => {
      try {
        const response = await fetch('/api/proc/list_user_tasks', {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(data?.detail || data?.message || '加载对账规则失败'));
        }

        const tasks = Array.isArray(data?.tasks) ? data.tasks : [];
        const rules = tasks
          .filter((task: { task_type?: string }) => task.task_type === 'recon')
          .flatMap((task: {
            task_code?: string;
            task_name?: string;
            task_type?: string;
            rules?: Array<Record<string, unknown>>;
          }) =>
            (task.rules || []).map((rule) => ({
              id: Number(rule.id || 0),
              user_id: typeof rule.user_id === 'string' ? rule.user_id : null,
              task_id: typeof rule.task_id === 'number' ? rule.task_id : null,
              rule_code: String(rule.rule_code || ''),
              name: String(rule.name || ''),
              rule_type: String(rule.rule_type || ''),
              remark: typeof rule.remark === 'string' ? rule.remark : '',
              task_code: String(task.task_code || ''),
              task_name: String(task.task_name || ''),
              task_type: String(task.task_type || 'recon'),
              file_rule_code:
                typeof rule.file_rule_code === 'string' ? rule.file_rule_code : undefined,
            })),
          )
          .filter((rule: UserTaskRule) => rule.rule_code);

        if (!aborted) {
          setReconRules(rules);
        }
      } catch (error) {
        if (!aborted) {
          console.error('加载对账规则失败:', error);
          setReconRules([]);
        }
      }
    };

    void loadReconRules();
    return () => {
      aborted = true;
    };
  }, [authToken]);

  useEffect(() => {
    if (authToken) return;
    if (panelView !== 'data-connections') return;
    setPanelView('conversation');
  }, [panelView, authToken]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (panelView === 'data-connections') {
      url.searchParams.set('section', 'data-connections');
    } else {
      url.searchParams.delete('section');
      [
        'platform_auth_status',
        'platform_code',
        'platform_auth_message',
        'status',
        'platform',
        'message',
        'shop_name',
      ].forEach((key) => url.searchParams.delete(key));
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }, [panelView]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [panelView, selectedTask?.rule_code, activeConvId]);

  useLayoutEffect(() => {
    if (isLoginModalOpen) {
      return;
    }

    const clearStaleBackdrop = () => {
      clearResidualBlockingBackdrops();
    };

    clearStaleBackdrop();
    const rafId = window.requestAnimationFrame(clearStaleBackdrop);
    const timerId = window.setTimeout(clearStaleBackdrop, 120);
    const laterTimerId = window.setTimeout(clearStaleBackdrop, 600);

    const handlePageShow = () => {
      clearStaleBackdrop();
    };
    window.addEventListener('pageshow', handlePageShow);

    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timerId);
      window.clearTimeout(laterTimerId);
      window.removeEventListener('pageshow', handlePageShow);
    };
  }, [isLoginModalOpen, authToken, currentUser]);

  // 保存当前会话状态到 localStorage（游客用 guest 存储，已登录用 active/id）
  useEffect(() => {
    if (isGuest) {
      const conv = conversations.find((c) => c.id === activeConvId)
        || (pendingNewConvRef.current?.id === activeConvId ? pendingNewConvRef.current : null);
      if (conv) {
        localStorage.setItem(STORAGE_KEY_GUEST_CONV, serializeGuestConv(conv));
        console.log('[localStorage] 保存游客对话:', activeConvId);
      }
    } else {
      const isNewConv = pendingNewConvRef.current?.id === activeConvId;
      console.log('[localStorage] 检查保存条件:', {
        isNewConv,
        activeConvId,
        pendingNewConvId: pendingNewConvRef.current?.id,
      });
      if (isNewConv) {
        localStorage.setItem(STORAGE_KEY_IS_NEW_CONV, 'true');
        localStorage.removeItem(STORAGE_KEY_ACTIVE_CONV);
        console.log('[localStorage] 标记为新对话，不保存 activeConvId');
      } else if (activeConvId) {
        localStorage.setItem(STORAGE_KEY_ACTIVE_CONV, activeConvId);
        localStorage.setItem(STORAGE_KEY_IS_NEW_CONV, 'false');
        console.log('[localStorage] ✅ 保存 activeConvId:', activeConvId);
      }
    }
  }, [isGuest, activeConvId, conversations]);

  // ── 服务器会话管理（需在 handleLoginSuccess 之前，供其使用）──────────────────────────────────────────
  const {
    serverConversations,
    isLoading: isLoadingConversations,
    loadConversations,
    loadConversation,
    deleteConversation: deleteServerConversation,
    clearCache: clearConversationsCache,
  } = useConversations({ authToken });

  const convIdMapRef = useRef<Map<string, string>>(new Map());

  // ── 登录成功处理 ──────────────────────────────────────────────
  const handleLoginSuccess = useCallback(async (user: { username: string; userId: string }) => {
    const newToken = localStorage.getItem('tally_auth_token') || localStorage.getItem('finflux_auth_token');
    if (newToken) {
      setAuthToken(newToken);
    }
    setCurrentUser({ username: user.username, id: user.userId });

    localStorage.removeItem('pending_rule_name');
    localStorage.removeItem('pending_source_rule_id');
    localStorage.removeItem('pending_rule_id');
    localStorage.removeItem(STORAGE_KEY_GUEST_CONV);
    localStorage.removeItem(STORAGE_KEY_ACTIVE_CONV);
    localStorage.removeItem(STORAGE_KEY_IS_NEW_CONV);

    setIsLoginModalOpen(false);
    // 清除游客对话缓存，不保存为登录后会话
    clearConversationsCache();
    localStorage.removeItem(STORAGE_KEY_GUEST_CONV);
    convIdMapRef.current.clear();
    setConversations([]);
    setIsLoading(false);
    setTasks([]);
    setUploadedFiles([]);
    setTaskResult(null);
    setWaitingForFileUpload(false);
    // 标记刚登录，加载会话列表后选择最近会话
    hasLoadedInitialConvRef.current = false;
    justLoggedInRef.current = true;
    void loadConversations();
  }, [clearConversationsCache, loadConversations]);

  // 追踪对账任务状态（用于在任务完成时删除"任务启动"消息）
  const taskStartedRef = useRef<Map<string, boolean>>(new Map());
  
  // 追踪是否刚刚登录（用于在会话列表加载后自动选择最新会话）
  const justLoggedInRef = useRef(false);
  // 追踪登录时的会话ID（本地ID和服务器ID，用于登录成功后清除）
  const loginConvIdRef = useRef<{ localId: string | null; serverId: string | null }>({ localId: null, serverId: null });
  // 追踪是否已加载初始会话（用于防止刷新时重复加载）
  const hasLoadedInitialConvRef = useRef<boolean>(false);

  // 登录成功后，等会话列表加载完成，选中最近对话（不创建新对话）
  useEffect(() => {
    console.log('[登录选择对话] effect触发', {
      authToken: !!authToken,
      justLoggedIn: justLoggedInRef.current,
      isLoadingConversations,
      serverConversationsLength: serverConversations.length,
    });
    // 未登录时不处理
    if (!authToken) return;
    // 未标记刚登录时不处理
    if (!justLoggedInRef.current) return;
    
    // 等待会话列表加载完成：
    // 1. 如果正在加载，等待
    // 2. 如果刚登录但还未开始加载（serverConversations为空），也等待
    if (isLoadingConversations || serverConversations.length === 0) return;

    console.log('[登录选择对话] 准备加载对话, serverConversations=', serverConversations);
    if (serverConversations.length > 0) {
      justLoggedInRef.current = false;
      pendingNewConvRef.current = null;
      const latestConv = serverConversations[0];
      console.log('[登录选择对话] 加载最近对话:', latestConv.id, latestConv.title);
      setIsLoadingConversation(true);
      loadConversation(latestConv.id).then((conv) => {
        if (conv) {
          setConversations([conv]);
          setActiveConvId(conv.id);
        } else {
          setActiveConvId(latestConv.id);
        }
        setIsLoadingConversation(false);
      });
    } else {
      // 无历史对话时才创建新对话（有历史时始终选中最近一个）
      console.log('[登录选择对话] 无历史对话，创建新对话');
      justLoggedInRef.current = false;
      const newConv = createConversation();
      pendingNewConvRef.current = newConv;
      setActiveConvId(newConv.id);
      loginConvIdRef.current = { localId: null, serverId: null };
    }
  }, [authToken, serverConversations, isLoadingConversations, loadConversation]);
  
  // 刷新页面时：优先恢复已保存会话；否则选最近历史；仅在完全没有历史时创建新对话
  useEffect(() => {
    console.log('[刷新加载] effect触发', {
      hasLoaded: hasLoadedInitialConvRef.current,
      authToken: !!authToken,
      activeId: initialState.activeId,
      serverConversationsCount: serverConversations.length,
      isLoadingConversations,
    });

    if (hasLoadedInitialConvRef.current) {
      console.log('[刷新加载] 跳过：已加载过');
      return;
    }

    if (!authToken || isLoadingConversations) {
      console.log('[刷新加载] 跳过：等待认证或列表加载完成');
      return;
    }

    if (serverConversations.length === 0) {
      console.log('[刷新加载] 无历史对话，创建新对话');
      hasLoadedInitialConvRef.current = true;
      const newConv = createConversation();
      pendingNewConvRef.current = newConv;
      setActiveConvId(newConv.id);
      return;
    }

    const savedConvId = initialState.activeId;
    if (!savedConvId) {
      console.log('[刷新加载] 未保存活动会话，切换到最近对话');
      hasLoadedInitialConvRef.current = true;
      pendingNewConvRef.current = null;
      setActiveConvId(serverConversations[0].id);
      return;
    }

    const savedConvExists = serverConversations.some((c) => c.id === savedConvId);
    console.log('[刷新加载] savedConvExists:', savedConvExists, 'activeId:', savedConvId);

    if (savedConvExists) {
      console.log('[刷新加载] 开始加载对话:', savedConvId);
      hasLoadedInitialConvRef.current = true;
      pendingNewConvRef.current = null;
      setActiveConvId(savedConvId);

      setIsLoadingConversation(true);
      loadConversation(savedConvId)
        .then((conv) => {
          console.log('[刷新加载] 加载完成，消息数:', conv?.messages.length || 0);
          if (conv) {
            setConversations((prev) => {
              const existing = prev.find((c) => c.id === savedConvId);
              if (existing) {
                return prev.map((c) =>
                  c.id === savedConvId
                    ? { ...c, ...conv, taskContext: conv.taskContext ?? null }
                    : c
                );
              } else {
                return [conv, ...prev];
              }
            });
          }
          setIsLoadingConversation(false);
        })
        .catch((err) => {
          console.error('[刷新加载] 加载对话失败:', err);
          setIsLoadingConversation(false);
          if (serverConversations.length > 0) {
            console.log('[刷新加载] 降级到第一个对话:', serverConversations[0].id);
            setActiveConvId(serverConversations[0].id);
          }
        });
    } else {
      console.log('[刷新加载] savedConvId不存在，切换到最新对话');
      hasLoadedInitialConvRef.current = true;
      pendingNewConvRef.current = null;
      const latestConv = serverConversations[0];
      if (latestConv) {
        console.log('[刷新加载] 切换到:', latestConv.id);
        setActiveConvId(latestConv.id);
      }
    }
  }, [
    serverConversations,
    loadConversation,
    authToken,
    isLoadingConversations,
    initialState.activeId,
  ]);

  // ── 加载和中断状态 ────────────────────────────────────────
  const [isLoading, setIsLoading] = useState(false);
  const [waitingForFileUpload, setWaitingForFileUpload] = useState(false);
  
  // ── 流式输出状态 ──────────────────────────────────────────
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const nodeStatusMessageIdsRef = useRef<Map<string, string>>(new Map());

  // ── 响应目标会话追踪 ───────────────────────────────────────
  const pendingConvIdRef = useRef<string | null>(null);
  /** 无对话时发送的第一条消息：暂存会话，供 conversation_created 早于 state 更新时使用 */
  const pendingSendConvRef = useRef<{ threadId: string; conv: Conversation } | null>(null);

  // ── 任务和文件 ────────────────────────────────────────────
  // TODO: 这些状态变量用于任务面板功能，目前仅使用 setter
  const [tasks, setTasks] = useState<Task[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [taskResult, setTaskResult] = useState<Record<string, unknown> | null>(
    null
  );
  void tasks; void uploadedFiles; void taskResult;

  // ── 辅助函数：追加消息 ───────────────────────────────────
  const appendMessage = useCallback(
    (msg: Message) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeConvId
            ? {
                ...c,
                messages: [...c.messages, msg],
                updatedAt: new Date(),
                title:
                  c.messages.length === 0 && msg.role === 'user'
                    ? msg.content.slice(0, 20) + (msg.content.length > 20 ? '...' : '')
                    : c.title,
              }
            : c
        )
      );
    },
    [activeConvId]
  );

  const makeNodeStatusKey = useCallback((conversationId: string, nodeName: string) => {
    return `${conversationId}::${nodeName}`;
  }, []);

  const upsertRunningNodeMessage = useCallback((
    conversationId: string,
    nodeName: string,
    label: string,
    detail?: string,
  ) => {
    const key = makeNodeStatusKey(conversationId, nodeName);
    const existingId = nodeStatusMessageIdsRef.current.get(key);
    const messageId = existingId || generateId();

    nodeStatusMessageIdsRef.current.set(key, messageId);

    setConversations((prev) =>
      prev.map((conversation) => {
        if (conversation.id !== conversationId) return conversation;

        const existingIndex = conversation.messages.findIndex((message) => message.id === messageId);
        const nextMessage: Message = {
          id: messageId,
          role: 'assistant',
          content: '',
          timestamp: new Date(),
          nodeName,
          nodeStatus: 'running',
          nodeLabel: label,
          nodeDetail: detail,
        };

        if (existingIndex >= 0) {
          const updated = [...conversation.messages];
          updated[existingIndex] = {
            ...updated[existingIndex],
            ...nextMessage,
          };
          return { ...conversation, messages: updated, updatedAt: new Date() };
        }

        return {
          ...conversation,
          messages: [...conversation.messages, nextMessage],
          updatedAt: new Date(),
        };
      }),
    );
  }, [makeNodeStatusKey]);

  const completeNodeMessage = useCallback((
    conversationId: string,
    nodeName: string,
    content: string,
    label?: string,
  ) => {
    const key = makeNodeStatusKey(conversationId, nodeName);
    const existingId = nodeStatusMessageIdsRef.current.get(key);
    if (existingId) {
      nodeStatusMessageIdsRef.current.delete(key);
    }

    const resolvedId = existingId || generateId();

    setConversations((prev) =>
      prev.map((conversation) => {
        if (conversation.id !== conversationId) return conversation;

        const existingIndex = conversation.messages.findIndex((message) => message.id === resolvedId);
        const nextMessage: Message = {
          id: resolvedId,
          role: 'assistant',
          content,
          timestamp: new Date(),
          nodeName,
          nodeStatus: 'completed',
          nodeLabel: label,
        };

        if (existingIndex >= 0) {
          const updated = [...conversation.messages];
          updated[existingIndex] = {
            ...updated[existingIndex],
            ...nextMessage,
          };
          return { ...conversation, messages: updated, updatedAt: new Date() };
        }

        return {
          ...conversation,
          messages: [...conversation.messages, nextMessage],
          updatedAt: new Date(),
        };
      }),
    );
  }, [makeNodeStatusKey]);

  const clearRunningNodeMessages = useCallback((conversationId: string) => {
    setConversations((prev) =>
      prev.map((conversation) => {
        if (conversation.id !== conversationId) return conversation;
        return {
          ...conversation,
          messages: conversation.messages.map((message) =>
            message.nodeStatus === 'running'
              ? { ...message, nodeStatus: 'completed', content: message.content || `已结束：${message.nodeLabel || '当前步骤'}` }
              : message,
          ),
          updatedAt: new Date(),
        };
      }),
    );

    Array.from(nodeStatusMessageIdsRef.current.keys())
      .filter((key) => key.startsWith(`${conversationId}::`))
      .forEach((key) => nodeStatusMessageIdsRef.current.delete(key));
  }, []);

  const remapNodeStatusConversationId = useCallback((fromConversationId: string, toConversationId: string) => {
    if (!fromConversationId || !toConversationId || fromConversationId === toConversationId) {
      return;
    }

    const remapped = new Map<string, string>();
    nodeStatusMessageIdsRef.current.forEach((messageId, key) => {
      if (key.startsWith(`${fromConversationId}::`)) {
        remapped.set(key.replace(`${fromConversationId}::`, `${toConversationId}::`), messageId);
        return;
      }
      remapped.set(key, messageId);
    });
    nodeStatusMessageIdsRef.current = remapped;
  }, []);

  // ── WebSocket 连接时的认证验证 ─────────────────────────
  const handleWsConnected = useCallback(
    (sendMessage: (msg: string, threadId: string, resume?: boolean, token?: string) => boolean) => {
      // WebSocket 连接建立后，如果有保存的 authToken，发送验证请求
      if (authToken) {
        console.log('WebSocket connected, verifying stored auth token...');
        sendMessage('', activeConvId, false, authToken);
      }
    },
    [authToken, activeConvId]
  );

  // ── WebSocket ─────────────────────────────────────────────
  const handleWsMessage = useCallback(
    (data: WsOutgoing) => {
      const targetConvId = pendingConvIdRef.current || activeConvId;
      switch (data.type) {
        case 'node_status':
          setIsLoading(false);
          setStreamingMessageId(null);
          if (data.node && data.status === 'running') {
            upsertRunningNodeMessage(
              targetConvId,
              data.node,
              data.label || data.content || '处理中',
              data.detail,
            );
          } else if (data.node && data.status === 'completed') {
            completeNodeMessage(
              targetConvId,
              data.node,
              data.content || '当前节点已完成',
              data.label,
            );
          }
          break;

        case 'stream':
          // 流式输出：逐步更新消息内容
          setIsLoading(false);
          setConversations((prev) =>
            prev.map((c) => {
              if (c.id !== targetConvId) return c;
              
              // 查找或创建流式消息
              const existingMsgIndex = c.messages.findIndex(
                (m) => m.id === streamingMessageId
              );
              
              if (existingMsgIndex >= 0) {
                // 累积内容
                const updatedMessages = [...c.messages];
                updatedMessages[existingMsgIndex] = {
                  ...updatedMessages[existingMsgIndex],
                  content: updatedMessages[existingMsgIndex].content + (data.content || ''),
                };
                return {
                  ...c,
                  messages: updatedMessages,
                  updatedAt: new Date(),
                };
              } else {
                // 创建新的流式消息
                const newMsgId = generateId();
                setStreamingMessageId(newMsgId);
                return {
                  ...c,
                  messages: [
                    ...c.messages,
                    {
                      id: newMsgId,
                      role: 'assistant' as const,
                      content: data.content || '',
                      timestamp: new Date(),
                    },
                  ],
                  updatedAt: new Date(),
                };
              }
            })
          );
          break;
        
        case 'message': {
          setIsLoading(false);
          const currentStreamingId = streamingMessageId;
          setStreamingMessageId(null); // 完整消息，清除流式状态
          const newContent = data.content || '';
          
          // 检测是否是对账任务启动消息
          const isTaskStarted = /^🚀 对账任务已启动/.test(newContent);
          
          setConversations((prev) =>
            prev.map((c) => {
              if (c.id !== targetConvId) return c;
              
              let filteredMessages = c.messages;
              
              // 如果之前有任务启动消息标记，现在收到新消息时删除启动消息
              // 但如果是自己刚收到的任务启动消息，则不删除
              if (taskStartedRef.current.get(targetConvId) && !isTaskStarted) {
                filteredMessages = c.messages.filter(
                  (m) => !(m.role === 'assistant' && /^🚀 对账任务已启动/.test(m.content))
                );
                taskStartedRef.current.delete(targetConvId);
              }
              
              // 如果当前消息是任务启动消息，设置标记（下次收到新消息时删除）
              if (isTaskStarted) {
                taskStartedRef.current.set(targetConvId, true);
              }
              
              // 检查是否有正在流式输出的消息，如果有则更新它而不是创建新消息
              if (currentStreamingId) {
                const streamingIndex = filteredMessages.findIndex((m) => m.id === currentStreamingId);
                if (streamingIndex >= 0) {
                  // 更新现有的流式消息
                  const updatedMessages = [...filteredMessages];
                  updatedMessages[streamingIndex] = {
                    ...updatedMessages[streamingIndex],
                    content: newContent,
                  };
                  return { ...c, messages: updatedMessages, updatedAt: new Date() };
                }
              }
              
              const lastMsg = filteredMessages[filteredMessages.length - 1];
              const isLastSaving =
                lastMsg?.role === 'assistant' &&
                /^正在保存\.*$/.test(String(lastMsg.content || '').trim());
              const messages = isLastSaving
                ? [...filteredMessages.slice(0, -1), { id: generateId(), role: 'assistant' as const, content: newContent, timestamp: new Date() }]
                : [...filteredMessages, { id: generateId(), role: 'assistant' as const, content: newContent, timestamp: new Date() }];
              return { ...c, messages, updatedAt: new Date() };
            })
          );

          // 尝试从 AI 消息中解析任务
          parseTasksFromMessage(newContent);
          break;
        }

        case 'interrupt': {
          setIsLoading(false);
          const payload = data.payload || {};
          const question = (payload.question as string) || '';
          const hint = (payload.hint as string) || '';
          const step = (payload.step as string) || '';
          
          // 只在创建规则流程（有step字段）时显示 interrupt 消息
          // 使用已有规则时（无step字段）不显示，避免重复提示
          if (step && question) {
            let content = question;
            if (hint) {
              content += `\n\n${hint}`;
            }
            
            setConversations((prev) =>
              prev.map((c) =>
                c.id === targetConvId
                  ? {
                      ...c,
                      messages: [
                        ...c.messages,
                        {
                          id: generateId(),
                          role: 'assistant' as const,
                          content,
                          timestamp: new Date(),
                        },
                      ],
                      updatedAt: new Date(),
                    }
                  : c
              )
            );
          }
          
          // 标记等待用户回复
          setWaitingForFileUpload(true);
          pendingConvIdRef.current = null;
          break;
        }

        case 'done':
          setIsLoading(false);
          setWaitingForFileUpload(false);
          setStreamingMessageId(null); // 清除流式状态
          clearRunningNodeMessages(targetConvId);
          pendingConvIdRef.current = null;
          pendingSendConvRef.current = null; // 响应完成，清除无对话发送的暂存
          break;

        case 'auth':
          // 登录/注册成功，保存 token
          if (data.token) {
            setAuthToken(data.token);
            localStorage.setItem('tally_auth_token', data.token);
            if (data.user) {
              setCurrentUser(data.user);
              localStorage.setItem('tally_current_user', JSON.stringify(data.user));
            }
            // 记录登录时的会话ID（本地ID），标记需要在会话列表加载后选择最新会话
            loginConvIdRef.current = { 
              localId: activeConvId, 
              serverId: convIdMapRef.current.get(activeConvId) || null 
            };
            justLoggedInRef.current = true;
          }
          break;

        case 'auth_verify':
          // 认证验证响应（WebSocket连接建立后验证现有token）
          if (data.success) {
            // token 仍然有效，同步用户信息（如果返回了）
            if (data.user) {
              setCurrentUser(data.user);
              localStorage.setItem('tally_current_user', JSON.stringify(data.user));
            }
            console.log('Auth token verified successfully');
          } else {
            const reason =
              data.payload && typeof data.payload.reason === 'string'
                ? data.payload.reason
                : 'unknown';

            if (reason === 'invalid_token') {
              // token 已过期或无效，清除本地凭证
              console.log('Auth token invalid, clearing stored credentials');
              setAuthToken(null);
              setCurrentUser(null);
              localStorage.removeItem('tally_auth_token');
              localStorage.removeItem('tally_current_user');
            } else {
              console.warn('Auth verification skipped due to transient backend issue:', data.payload);
            }
          }
          break;

        case 'conversation_created':
          // 服务器创建了新会话，记录映射关系；保留当前消息并切换为服务器 ID（避免闪屏）
          if (data.conversation_id && data.thread_id) {
            console.log('[conversation_created] 本地ID:', data.thread_id, '→ 服务器ID:', data.conversation_id);
            convIdMapRef.current.set(data.thread_id, data.conversation_id);
            setHiddenConversationIds((prev) => {
              if (!prev.includes(data.thread_id as string)) return prev;
              if (prev.includes(data.conversation_id as string)) return prev;
              return [...prev, data.conversation_id as string];
            });
            remapNodeStatusConversationId(data.thread_id, data.conversation_id);
            // 如果是登录会话，更新服务器ID
            if (loginConvIdRef.current.localId === data.thread_id) {
              loginConvIdRef.current.serverId = data.conversation_id;
            }
            setConversations((prev) => {
              const current = prev.find((c) => c.id === data.thread_id);
              const rest = prev.filter((c) => c.id !== data.thread_id);
              if (current) {
                return [{ ...current, id: data.conversation_id as string }, ...rest];
              }
              // conversation_created 可能早于 handleSendMessage 的 state 更新，使用暂存的会话
              const pending = pendingSendConvRef.current;
              if (pending && pending.threadId === data.thread_id) {
                pendingSendConvRef.current = null;
                const convWithServerId: Conversation = { ...pending.conv, id: data.conversation_id as string };
                return [convWithServerId, ...rest];
              }
              return rest;
            });
            loadConversations();
            if (activeConvId === data.thread_id) {
              pendingConvIdRef.current = data.conversation_id;
              setActiveConvId(data.conversation_id);
            }
          }
          break;

        case 'error':
          setIsLoading(false);
          clearRunningNodeMessages(targetConvId);
          setConversations((prev) =>
            prev.map((c) =>
              c.id === targetConvId
                ? {
                    ...c,
                    messages: [
                      ...c.messages,
                      {
                        id: generateId(),
                        role: 'system' as const,
                        content: data.content || '发生错误',
                        timestamp: new Date(),
                        action: 'info',
                        actionDetail: '处理出错',
                        actionDone: true,
                      },
                    ],
                    updatedAt: new Date(),
                  }
                : c
            )
          );
          break;
      }
    },
    [
      activeConvId,
      appendMessage,
      clearRunningNodeMessages,
      completeNodeMessage,
      loadConversations,
      pendingConvIdRef,
      remapNodeStatusConversationId,
      streamingMessageId,
      upsertRunningNodeMessage,
    ]
  );

  const { status, sendMessage } = useWebSocket({
    onMessage: handleWsMessage,
    onConnect: handleWsConnected,
  });

  // ── 从 AI 消息中提取任务列表 ──────────────────────────────
  const parseTasksFromMessage = (content: string) => {
    // 解析阶段性消息来更新任务
    const phaseKeywords: { keyword: string; title: string }[] = [
      { keyword: '文件分析', title: '加载并解析数据文件' },
      { keyword: '数据清洗', title: '数据清洗和预处理' },
      { keyword: '字段映射', title: '字段映射分析' },
      { keyword: '规则配置', title: '对账规则配置' },
      { keyword: '预览', title: '验证预览' },
      { keyword: '保存', title: '保存对账规则' },
      { keyword: '对账完成', title: '生成对账结果' },
    ];

    setTasks((prev) => {
      // 初始化默认任务列表（如果为空）
      if (prev.length === 0) {
        return phaseKeywords.map((p, i) => ({
          id: `task-${i}`,
          title: p.title,
          status: 'pending' as const,
        }));
      }

      // 根据内容更新任务状态
      const updated = [...prev];
      for (const phase of phaseKeywords) {
        if (content.includes(phase.keyword)) {
          const task = updated.find((t) => t.title === phase.title);
          if (task) {
            task.status = content.includes('完成') || content.includes('确认')
              ? 'completed'
              : 'running';
          }
        }
      }
      return updated;
    });

    // 解析对账结果
    if (content.includes('对账完成') && content.includes('业务记录数')) {
      try {
        const summary: Record<string, string> = {};
        const lines = content.split('\n');
        for (const line of lines) {
          const match = line.match(/•\s*(.+?)：(.+)/);
          if (match) {
            summary[match[1].trim()] = match[2].trim();
          }
        }
        if (Object.keys(summary).length > 0) {
          setTaskResult({ summary });
        }
      } catch {
        // ignore parse errors
      }
    }
  };

  // ── 发送消息 ──────────────────────────────────────────────
  const handleSendMessage = useCallback(
    (text: string, attachments?: import('./types').MessageAttachment[], silent = false) => {
      // 游客：仅当本地对话数大于 1 时弹出登录框（保持 1 个对话可正常使用）
      if (isGuest) {
        const totalConvs = conversations.length + (pendingNewConvRef.current ? 1 : 0);
        if (totalConvs > 1) {
          setLoginModalTitleHint('登录后使用完整功能');
          setIsLoginModalOpen(true);
          return;
        }
      }

      // 如果正在流式输出，中断当前流式输出
      if (streamingMessageId) {
        setStreamingMessageId(null);
      }
      
      // 无对话或当前活动会话不在列表中时：先创建对话（含用户消息），再发送，确保 AI 回复前对话已存在
      const activeConvInList = conversations.some((c) => c.id === activeConvId);
      const isNewConvFirstMessage = !activeConvInList && activeConvId;
      if (isNewConvFirstMessage && !silent) {
        const baseConv = pendingNewConvRef.current?.id === activeConvId
          ? pendingNewConvRef.current
          : createConversation();
        const userMsg: Message = {
          id: generateId(),
          role: 'user',
          content: text,
          timestamp: new Date(),
          attachments,
        };
        const newConv: Conversation = {
          ...baseConv,
          id: activeConvId,
          title: text.slice(0, 20) + (text.length > 20 ? '...' : ''),
          messages: [userMsg],
        };
        pendingSendConvRef.current = { threadId: newConv.id, conv: newConv };
        setConversations((prev) => [newConv, ...prev]);
        pendingNewConvRef.current = null;
      } else if (isNewConvFirstMessage && silent) {
        const baseConv = pendingNewConvRef.current?.id === activeConvId
          ? pendingNewConvRef.current
          : createConversation();
        const newConv: Conversation = { ...baseConv, id: activeConvId, title: text.slice(0, 20) + (text.length > 20 ? '...' : '') };
        setConversations((prev) => [newConv, ...prev]);
        pendingNewConvRef.current = null;
      } else if (!silent) {
        appendMessage({
          id: generateId(),
          role: 'user',
          content: text,
          timestamp: new Date(),
          attachments,
        });
      }

      pendingConvIdRef.current = activeConvId;
      setIsLoading(true);
      const shouldResume = waitingForFileUpload;
      setWaitingForFileUpload(false);
      // 附件中有 path 时一并发送，供服务端检测文件（避免 _thread_files 为空）
      const filesToSend = attachments
        ?.filter((a): a is import('./types').MessageAttachment & { path: string } => !!a.path)
        .map((a) => ({ name: a.name, path: a.path }));
      // 获取对应的 server conversation_id
      // activeConvId 可能是本地 ID（随机字符串）或服务器 ID（UUID）
      // 如果是服务器 ID（UUID 格式），直接使用；否则从映射表查找
      const isServerId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(activeConvId);
      const conversationId = isServerId ? activeConvId : convIdMapRef.current.get(activeConvId);
      const activeTaskContext =
        panelView !== 'data-connections'
          ? activeConv?.taskContext ?? null
          : null;
      sendMessage(
        text,
        activeConvId,
        shouldResume,
        authToken || undefined,
        filesToSend,
        conversationId,
        activeTaskContext?.task_type,
        activeTaskContext?.rule_code,
        activeTaskContext?.name,
        activeTaskContext?.file_rule_code,
      );
    },
    [isGuest, conversations.length, appendMessage, sendMessage, activeConvId, waitingForFileUpload, authToken, pendingConvIdRef, convIdMapRef, streamingMessageId, activeConv, panelView]
  );

  // ── 文件上传回调 ──────────────────────────────────────────
  const handleFileUploaded = useCallback((file: UploadedFile) => {
    setUploadedFiles((prev) => [...prev, file]);

    // 不再显示"WRITE 已完成"消息，用户可以在附件卡片中看到上传的文件
  }, []);

  // ── 登出 ────────────────────────────────────────────────────
  const handleLogout = useCallback(() => {
    console.log('Logging out...');
    // 清除认证状态
    setAuthToken(null);
    setCurrentUser(null);
    localStorage.removeItem('tally_auth_token');
    localStorage.removeItem('tally_current_user');
    localStorage.removeItem(STORAGE_KEY_ACTIVE_CONV);
    localStorage.removeItem(STORAGE_KEY_IS_NEW_CONV);
    
    // 清除服务器会话缓存
    clearConversationsCache();
    convIdMapRef.current.clear();
    
    // 清除所有会话，创建新的待确认会话
    const newConv = createConversation();
    pendingNewConvRef.current = newConv;
    setConversations([]);
    setActiveConvId(newConv.id);
    setIsLoading(false);
    setTasks([]);
    setUploadedFiles([]);
    setTaskResult(null);
    setWaitingForFileUpload(false);
    setHiddenConversationIds([]);
    hasLoadedInitialConvRef.current = false;
  }, [clearConversationsCache]);

  // ── 新建会话 ──────────────────────────────────────────────
  const handleNewConversation = useCallback(() => {
    // 如果正在加载中，不允许创建新会话（避免消息显示错乱）
    if (isLoading) return;
    setPanelView('conversation');
    setReconWorkspaceMode('upload');
    setReconExecutionMode('upload');
    const conv = createConversation();
    pendingNewConvRef.current = conv;
    setActiveConvId(conv.id);
    setTasks([]);
    setUploadedFiles([]);
    setTaskResult(null);
    // 游客模式：不清除已有本地对话，保持始终可使用一个对话
  }, [isLoading]);

  // ── 切换会话 ──────────────────────────────────────────────
  const handleSelectConversation = useCallback(async (id: string) => {
    if (panelView === 'data-connections') {
      setPanelView('conversation');
    }
    setReconWorkspaceMode('upload');
    // 切换到其他会话时，清除待确认的新会话
    pendingNewConvRef.current = null;
    setConversations((prev) =>
      prev.map((conversation) =>
        conversation.id === id && conversation.taskContext
          ? {
              ...conversation,
              taskContext: null,
            }
          : conversation,
      ),
    );
    setActiveConvId(id);
    setIsLoading(false);
    
    // 如果是服务器会话且本地没有消息，从服务器加载
    const localConv = conversations.find((c) => c.id === id);
    const isServerConv = serverConversations.some((c) => c.id === id);
    
    if (isServerConv && (!localConv || localConv.messages.length === 0)) {
      // 显示加载状态
      setIsLoadingConversation(true);
      const serverConv = await loadConversation(id);
      setIsLoadingConversation(false);
      if (serverConv && serverConv.messages.length > 0) {
        setConversations((prev) => {
          const existing = prev.find((c) => c.id === id);
          if (existing) {
            // 服务端会话以服务端返回为准，避免残留本地 taskContext
            return prev.map((c) =>
              c.id === id
                ? { ...c, ...serverConv, taskContext: serverConv.taskContext ?? null }
                : c
            );
          } else {
            // 添加新会话
            return [serverConv, ...prev];
          }
        });
      }
    }
  }, [conversations, serverConversations, loadConversation, panelView]);

  // ── 删除会话 ──────────────────────────────────────────────
  const handleDeleteConversation = useCallback(async (id: string) => {
    console.log('handleDeleteConversation called, id:', id);
    
    // 检查是否是服务器会话 ID（UUID 格式）
    const isServerId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
    
    // 如果是服务器会话，调用删除 API
    if (isServerId) {
      await deleteServerConversation(id);
    }
    
    // 无论服务器删除成功与否，都从本地列表中移除
    setConversations((prev) => prev.filter((c) => c.id !== id));
    setHiddenConversationIds((prev) => prev.filter((item) => item !== id));
    
    // 如果删除的是当前活动会话，切换到其他会话
    if (activeConvId === id) {
      // 合并后的列表（排除被删除的）
      const remaining = [...conversations, ...serverConversations].filter((c: import('./types').Conversation) => c.id !== id);
      if (remaining.length > 0) {
        setActiveConvId(remaining[0].id);
      } else {
        // 没有其他会话时，自动创建新对话，保持对话框可用
        const newConv = createConversation();
        pendingNewConvRef.current = newConv;
        setActiveConvId(newConv.id);
      }
    }
  }, [activeConvId, conversations, serverConversations, deleteServerConversation]);

  const updateConversationTaskContext = useCallback((conversationId: string, task: UserTaskRule | null) => {
    if (!conversationId) return;

    if (pendingNewConvRef.current?.id === conversationId) {
      pendingNewConvRef.current = {
        ...pendingNewConvRef.current,
        taskContext: task,
      };
    }

    setConversations((prev) =>
      prev.map((conversation) =>
        conversation.id === conversationId
          ? {
              ...conversation,
              taskContext: task,
            }
          : conversation,
      ),
    );
  }, []);

  // ── 选择任务 ────────────────────────────────────────────────
  const handleSelectTask = useCallback((task: UserTaskRule) => {
    setPanelView('conversation');
    setReconWorkspaceMode('upload');
    setReconExecutionMode('upload');
    const conversation = createConversation(task);
    pendingNewConvRef.current = conversation;
    setHiddenConversationIds((prev) =>
      prev.includes(conversation.id) ? prev : [...prev, conversation.id],
    );
    setActiveConvId(conversation.id);
    setTasks([]);
    setUploadedFiles([]);
    setTaskResult(null);
    setWaitingForFileUpload(false);
    setIsLoading(false);
    console.log('选中规则:', task.task_type, '-', task.task_name, '-', task.name);
  }, []);

  const handleSelectReconEntry = useCallback((entry: ReconWorkspaceMode) => {
    setPanelView('conversation');
    setReconWorkspaceMode(entry);
    setReconExecutionMode('upload');

    const targetRule =
      selectedTask?.task_type === 'recon'
        ? selectedTask
        : reconRules.find((rule) => rule.rule_code) ?? null;

    if (!targetRule) {
      if (entry === 'upload') {
        window.alert('暂无可用的数据对账规则，请先创建对账方案。');
      }
      return;
    }

    handleSelectTask(targetRule);
    setReconWorkspaceMode(entry);
  }, [handleSelectTask, reconRules, selectedTask]);

  const handleOpenTask = useCallback((task: { task_type?: string; task_name?: string }) => {
    setPanelView('conversation');
    console.log('打开任务工作台:', task.task_type, '-', task.task_name);
  }, []);

  const handleSelectSection = useCallback((section: AppSection) => {
    if (section === 'data-connections') {
      setPanelView('data-connections');
      return;
    }
    setPanelView('conversation');
  }, []);

  const handleBackToChat = useCallback(() => {
    setPanelView('conversation');
  }, []);

  const handleOpenCollaborationChannels = useCallback((provider?: CollaborationProvider) => {
    setSelectedDataConnectionView('collaboration_channels');
    if (provider) {
      setSelectedCollaborationProvider(provider);
    }
    setPanelView('data-connections');
  }, []);

  const availableReconRules = useMemo(() => {
    if (selectedTask?.task_type !== 'recon') return reconRules;
    if (reconRules.some((rule) => rule.rule_code === selectedTask.rule_code)) return reconRules;
    return [...reconRules, selectedTask];
  }, [reconRules, selectedTask]);

  const handleSelectReconRule = useCallback(
    (ruleCode: string) => {
      const rule = availableReconRules.find((item) => item.rule_code === ruleCode);
      if (!rule) return;
      updateConversationTaskContext(activeConvId, rule);
    },
    [activeConvId, availableReconRules, updateConversationTaskContext],
  );

  // ── 合并本地和服务器会话 ────────────────────────────────────
  // 服务器会话优先，本地会话补充（未同步的新会话）
  // 如果刚登录，排除登录会话
  // 无会话时，将待确认的新对话加入列表，确保对话框可正常显示和提交
  const mergedConversations = useCallback(() => {
    const loginLocalId = loginConvIdRef.current.localId;
    const loginServerId = loginConvIdRef.current.serverId;
    
    const serverIds = new Set(serverConversations.map((c) => c.id));
    // 本地会话中不在服务器列表中的（新创建的、未保存的），排除登录会话
    const localOnly = conversations.filter(
      (c) =>
        !serverIds.has(c.id) &&
        c.id !== loginLocalId &&
        !hiddenConversationIds.includes(c.id),
    );
    // 服务器会话，如果刚登录则排除登录会话
    const serverFiltered = justLoggedInRef.current && loginServerId
      ? serverConversations.filter((c) => c.id !== loginServerId)
      : serverConversations;
    const base = [...localOnly, ...serverFiltered.filter((c) => !hiddenConversationIds.includes(c.id))];
    // 无会话时，将待确认的新对话加入列表（用户提交后即创建新对话）
    const pending = pendingNewConvRef.current;
    if (
      pending &&
      activeConvId === pending.id &&
      !hiddenConversationIds.includes(pending.id) &&
      !base.some((c) => c.id === pending.id)
    ) {
      return [pending, ...base];
    }
    return base;
  }, [conversations, serverConversations, activeConvId, hiddenConversationIds]);

  const displayConversations = mergedConversations();
  const activeSection: AppSection =
    panelView === 'data-connections' ? 'data-connections' : 'chat';
  const reconWorkspaceRule =
    selectedTask?.task_type === 'recon'
      ? selectedTask
      : reconRules.find((rule) => rule.rule_code) ?? EMPTY_RECON_RULE;
  const isReconWorkspace =
    panelView !== 'data-connections' &&
    (selectedTask?.task_type === 'recon' || reconWorkspaceMode === 'center');
  const chatAreaNode = (
    <ChatArea
      onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
      sidebarCollapsed={sidebarCollapsed}
      messages={messages}
      isLoading={isLoading}
      isLoadingConversation={isLoadingConversation}
      connectionStatus={status}
      onSendMessage={handleSendMessage}
      onFileUploaded={handleFileUploaded}
      threadId={activeConvId}
      showInput={!!activeConvId}
      currentUser={currentUser}
      conversationTitle={activeConv?.title}
      authToken={authToken}
      onLogin={() => {
        setLoginModalTitleHint(null);
        setIsLoginModalOpen(true);
      }}
      streamingMessageId={streamingMessageId}
      selectedTask={selectedTask?.task_type === 'recon' ? selectedTask : null}
      reconRules={selectedTask?.task_type === 'recon' ? availableReconRules : []}
      selectedReconRuleCode={
        selectedTask?.task_type === 'recon'
          ? selectedTask.rule_code
          : null
      }
      reconExecutionMode={reconExecutionMode}
      onSelectReconRule={handleSelectReconRule}
      onChangeReconExecutionMode={setReconExecutionMode}
      onOpenDataConnections={() => setPanelView('data-connections')}
      hideHeader={isReconWorkspace}
    />
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-secondary text-text-primary">
      <Sidebar
        collapsed={sidebarCollapsed}
        conversations={displayConversations}
        activeConversationId={activeConvId}
        activeSection={activeSection}
        connectionStatus={status}
        onNewConversation={handleNewConversation}
        onSelectSection={handleSelectSection}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={currentUser ? handleDeleteConversation : undefined}
        currentUser={currentUser}
        onLogout={handleLogout}
        onSelectRule={handleSelectTask}
        onOpenTask={handleOpenTask}
        selectedRuleCode={selectedTask?.rule_code}
        authToken={authToken}
        selectedDataConnectionView={selectedDataConnectionView}
        onSelectDataConnectionView={setSelectedDataConnectionView}
        selectedDataSourceKind={selectedDataSourceKind}
        onSelectDataSourceKind={setSelectedDataSourceKind}
        selectedCollaborationProvider={selectedCollaborationProvider}
        onSelectCollaborationProvider={setSelectedCollaborationProvider}
        selectedReconEntry={reconWorkspaceMode}
        onSelectReconEntry={handleSelectReconEntry}
      />
      {panelView !== 'data-connections' ? (
        isReconWorkspace ? (
          <ReconWorkspace
            selectedTask={reconWorkspaceRule}
            mode={reconWorkspaceMode}
            availableRules={availableReconRules}
            selectedRuleCode={selectedTask?.task_type === 'recon' ? selectedTask.rule_code : null}
            executionMode={reconExecutionMode}
            authToken={authToken}
            onSelectRule={handleSelectReconRule}
            onChangeExecutionMode={setReconExecutionMode}
            onOpenDataConnections={() => setPanelView('data-connections')}
            onOpenCollaborationChannels={handleOpenCollaborationChannels}
          >
            {chatAreaNode}
          </ReconWorkspace>
        ) : (
          chatAreaNode
        )
      ) : (
        <DataConnectionsPanel
          authToken={authToken}
          initialCallback={authCallbackPayload}
          onBackToChat={handleBackToChat}
          selectedConnectionView={selectedDataConnectionView}
          selectedSourceKind={selectedDataSourceKind}
          selectedCollaborationProvider={selectedCollaborationProvider}
        />
      )}
      {!authToken && isLoginModalOpen && (
        <LoginModal
          isOpen={isLoginModalOpen}
          onClose={() => {
            setIsLoginModalOpen(false);
            setLoginModalTitleHint(null);
          }}
          onLoginSuccess={handleLoginSuccess}
          titleHint={loginModalTitleHint}
        />
      )}
    </div>
  );
}
