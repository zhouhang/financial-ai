import { useCallback, useEffect, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import LoginModal from './components/LoginModal';
import { useWebSocket } from './hooks/useWebSocket';
import { useConversations } from './hooks/useConversations';
import type {
  Conversation,
  DigitalEmployee,
  EmployeeRule,
  Message,
  Task,
  UploadedFile,
  WsOutgoing,
} from './types';

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function createConversation(): Conversation {
  return {
    id: generateId(),
    title: '新对话',
    createdAt: new Date(),
    updatedAt: new Date(),
    messages: [],
  };
}

// localStorage 键名
const STORAGE_KEY_ACTIVE_CONV = 'tally_active_conversation_id';
const STORAGE_KEY_IS_NEW_CONV = 'tally_is_new_conversation';
const STORAGE_KEY_GUEST_CONV = 'tally_guest_conversation';

// 创建初始会话（在组件外部，确保只创建一次）
const initialPendingConv = createConversation();

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
  const savedIsNewConv = localStorage.getItem(STORAGE_KEY_IS_NEW_CONV) === 'true';
  if (savedIsNewConv || !savedActiveId) {
    return { activeId: initialPendingConv.id, isNewConv: true, conversations: [], pendingNew: initialPendingConv };
  }
  return { activeId: savedActiveId, isNewConv: false, conversations: [], pendingNew: null };
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
  /** 规则保存成功提示 */
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);
  
  /** 选中的数字员工和规则 */
  const [selectedEmployee, setSelectedEmployee] = useState<DigitalEmployee | null>(null);
  const [selectedRule, setSelectedRule] = useState<EmployeeRule | null>(null);

  const isGuest = !authToken;

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
    
    const pendingRuleName = localStorage.getItem('pending_rule_name');
    const pendingSourceRuleId = localStorage.getItem('pending_source_rule_id');
    const pendingThreadId = localStorage.getItem('pending_thread_id');
    const pendingIsNewRule = localStorage.getItem('pending_is_new_rule') === 'true';
    
    localStorage.removeItem(STORAGE_KEY_GUEST_CONV);
    localStorage.removeItem(STORAGE_KEY_ACTIVE_CONV);
    localStorage.removeItem(STORAGE_KEY_IS_NEW_CONV);
    
    let ruleJustSaved = false;
    console.log('[handleLoginSuccess] pendingRuleName=', pendingRuleName, 'pendingSourceRuleId=', pendingSourceRuleId, 'pendingIsNewRule=', pendingIsNewRule, 'newToken=', newToken ? 'exists' : 'null');
    if (pendingRuleName && newToken) {
      try {
        if (pendingIsNewRule && pendingThreadId) {
          // 新建规则：从 thread 状态恢复并保存
          console.log('[handleLoginSuccess] 保存新建规则, threadId=', pendingThreadId);
          const response = await fetch('/api/save-pending-rule', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${newToken}`,
            },
            body: JSON.stringify({
              thread_id: pendingThreadId,
              rule_name: pendingRuleName,
            }),
          });
          const data = await response.json();
          console.log('[handleLoginSuccess] save-pending-rule响应:', data);
          if (data.success) {
            ruleJustSaved = true;
            localStorage.removeItem('pending_rule_name');
            localStorage.removeItem('pending_thread_id');
            localStorage.removeItem('pending_is_new_rule');
          } else {
            console.error('保存新建规则失败:', data.error || data.detail || '未知错误');
          }
        } else if (pendingSourceRuleId) {
          // 推荐规则：复制
          console.log('[handleLoginSuccess] 复制规则, sourceRuleId=', pendingSourceRuleId);
          const response = await fetch('/api/copy-rule', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${newToken}`,
            },
            body: JSON.stringify({
              source_rule_id: pendingSourceRuleId,
              new_rule_name: pendingRuleName,
            }),
          });
          const data = await response.json();
          console.log('[handleLoginSuccess] copy-rule响应:', data);
          if (data.success) {
            ruleJustSaved = true;
            localStorage.removeItem('pending_rule_name');
            localStorage.removeItem('pending_source_rule_id');
          } else {
            console.error('复制规则失败:', data.error || data.detail || '未知错误');
          }
        }
        console.log('[handleLoginSuccess] ruleJustSaved=', ruleJustSaved);
        if (ruleJustSaved) {
          localStorage.removeItem('pending_rule_id');
          // 显示成功提示
          setSaveSuccessMessage(`✅ 规则「${pendingRuleName}」已成功保存到您的个人规则列表！`);
        }
      } catch (e) {
        console.error('保存规则失败:', e);
        // 失败时不清除 pending_*，便于用户重试
      }
    }
    
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
  
  // 刷新页面时，如果有保存的会话ID且不是新对话，尝试加载该会话
  useEffect(() => {
    console.log('[刷新加载] effect触发', {
      hasLoaded: hasLoadedInitialConvRef.current,
      authToken: !!authToken,
      activeId: initialState.activeId,
      serverConversationsCount: serverConversations.length,
      isNewConv: initialState.isNewConv,
    });

    // 保护 1: 已经加载过初始对话
    if (hasLoadedInitialConvRef.current) {
      console.log('[刷新加载] 跳过：已加载过');
      return;
    }

    // 保护 2: 必要条件不满足
    if (!authToken || !initialState.activeId || serverConversations.length === 0) {
      console.log('[刷新加载] 跳过：条件不满足');
      return;
    }

    // 保护 3: 如果是新对话，不需要恢复
    if (initialState.isNewConv) {
      console.log('[刷新加载] 跳过：是新对话');
      return;
    }

    // 检查 savedConvId 是否在 serverConversations 中
    const savedConvExists = serverConversations.some((c) => c.id === initialState.activeId);
    console.log('[刷新加载] savedConvExists:', savedConvExists, 'activeId:', initialState.activeId);

    if (savedConvExists) {
      console.log('[刷新加载] 开始加载对话:', initialState.activeId);
      // 标记为已加载（防止重复触发）
      hasLoadedInitialConvRef.current = true;

      // 加载对话详情
      setIsLoadingConversation(true);
      loadConversation(initialState.activeId)
        .then((conv) => {
          console.log('[刷新加载] 加载完成，消息数:', conv?.messages.length || 0);
          if (conv && conv.messages.length > 0) {
            setConversations((prev) => {
              const existing = prev.find((c) => c.id === initialState.activeId);
              if (existing) {
                return prev.map((c) =>
                  c.id === initialState.activeId
                    ? { ...c, messages: conv.messages, title: conv.title }
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
          // 降级：切换到第一个可用对话
          if (serverConversations.length > 0) {
            console.log('[刷新加载] 降级到第一个对话:', serverConversations[0].id);
            setActiveConvId(serverConversations[0].id);
          }
        });
    } else {
      // savedConvId 不存在，切换到最新对话
      console.log('[刷新加载] savedConvId不存在，切换到最新对话');
      hasLoadedInitialConvRef.current = true;
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
    initialState.activeId,
    initialState.isNewConv,
  ]);

  // ── 加载和中断状态 ────────────────────────────────────────
  const [isLoading, setIsLoading] = useState(false);
  const [waitingForFileUpload, setWaitingForFileUpload] = useState(false);
  
  // ── 流式输出状态 ──────────────────────────────────────────
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

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
        
        case 'message':
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

          // 游客保存规则：收到 SAVE_RULE 或 SAVE_NEW_RULE 时自动弹出登录框并存储待保存信息
          const saveRuleMatch = newContent.match(/\[SAVE_RULE:([^:]+):([^\]]+)\]/);
          const saveNewRuleMatch = newContent.match(/\[SAVE_NEW_RULE:([^\]]+)\]/);
          if (saveRuleMatch) {
            localStorage.setItem('pending_rule_name', saveRuleMatch[1]);
            localStorage.setItem('pending_source_rule_id', saveRuleMatch[2]);
            setLoginModalTitleHint('登录后可完成保存规则');
            setIsLoginModalOpen(true);
          } else if (saveNewRuleMatch) {
            localStorage.setItem('pending_rule_name', saveNewRuleMatch[1]);
            // 优先使用服务端返回的 thread_id（与 LangGraph 状态一致）
            localStorage.setItem('pending_thread_id', (data.thread_id as string) || targetConvId);
            localStorage.setItem('pending_is_new_rule', 'true');
            setLoginModalTitleHint('登录后可完成保存规则');
            setIsLoginModalOpen(true);
          }
          break;

        case 'interrupt':
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

        case 'done':
          setIsLoading(false);
          setWaitingForFileUpload(false);
          setStreamingMessageId(null); // 清除流式状态
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
            // token 已过期或无效，清除本地凭证
            console.log('Auth token verification failed, clearing stored credentials');
            setAuthToken(null);
            setCurrentUser(null);
            localStorage.removeItem('tally_auth_token');
            localStorage.removeItem('tally_current_user');
          }
          break;

        case 'conversation_created':
          // 服务器创建了新会话，记录映射关系；保留当前消息并切换为服务器 ID（避免闪屏）
          if (data.conversation_id && data.thread_id) {
            console.log('[conversation_created] 本地ID:', data.thread_id, '→ 服务器ID:', data.conversation_id);
            convIdMapRef.current.set(data.thread_id, data.conversation_id);
            // 如果是登录会话，更新服务器ID
            if (loginConvIdRef.current.localId === data.thread_id) {
              loginConvIdRef.current.serverId = data.conversation_id;
            }
            setConversations((prev) => {
              const current = prev.find((c) => c.id === data.thread_id);
              const rest = prev.filter((c) => c.id !== data.thread_id);
              if (current) {
                return [{ ...current, id: data.conversation_id }, ...rest];
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
    [appendMessage, streamingMessageId, activeConvId, pendingConvIdRef, loadConversations]
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
      sendMessage(text, activeConvId, shouldResume, authToken || undefined, filesToSend, conversationId, selectedEmployee?.code, selectedRule?.code, selectedRule?.name);
    },
    [isGuest, conversations.length, appendMessage, sendMessage, activeConvId, waitingForFileUpload, authToken, pendingConvIdRef, convIdMapRef, streamingMessageId, selectedEmployee, selectedRule]
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
    hasLoadedInitialConvRef.current = false;
  }, [clearConversationsCache]);

  // ── 新建会话 ──────────────────────────────────────────────
  const handleNewConversation = useCallback(() => {
    // 如果正在加载中，不允许创建新会话（避免消息显示错乱）
    if (isLoading) return;
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
    // 切换到其他会话时，清除待确认的新会话
    pendingNewConvRef.current = null;
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
            // 更新现有会话的消息
            return prev.map((c) =>
              c.id === id
                ? { ...c, messages: serverConv.messages, title: serverConv.title }
                : c
            );
          } else {
            // 添加新会话
            return [serverConv, ...prev];
          }
        });
      }
    }
  }, [conversations, serverConversations, loadConversation]);

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

  // ── 选择数字员工规则 ──────────────────────────────────────────
  const handleSelectRule = useCallback((employee: DigitalEmployee, rule: EmployeeRule) => {
    setSelectedEmployee(employee);
    setSelectedRule(rule);
    console.log('选中规则:', employee.name, '-', rule.name);
    // TODO: 可以在这里触发其他操作，如发送消息给AI、开始新对话等
  }, []);

  // ── 合并本地和服务器会话 ────────────────────────────────────
  // 服务器会话优先，本地会话补充（未同步的新会话）
  // 如果刚登录，排除登录会话
  // 无会话时，将待确认的新对话加入列表，确保对话框可正常显示和提交
  const mergedConversations = useCallback(() => {
    const loginLocalId = loginConvIdRef.current.localId;
    const loginServerId = loginConvIdRef.current.serverId;
    
    const serverIds = new Set(serverConversations.map((c) => c.id));
    // 本地会话中不在服务器列表中的（新创建的、未保存的），排除登录会话
    const localOnly = conversations.filter((c) => !serverIds.has(c.id) && c.id !== loginLocalId);
    // 服务器会话，如果刚登录则排除登录会话
    const serverFiltered = justLoggedInRef.current && loginServerId
      ? serverConversations.filter((c) => c.id !== loginServerId)
      : serverConversations;
    const base = [...localOnly, ...serverFiltered];
    // 无会话时，将待确认的新对话加入列表（用户提交后即创建新对话）
    const pending = pendingNewConvRef.current;
    if (pending && activeConvId === pending.id && !base.some((c) => c.id === pending.id)) {
      return [pending, ...base];
    }
    return base;
  }, [conversations, serverConversations, activeConvId]);

  const displayConversations = mergedConversations();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-secondary">
      <Sidebar
        collapsed={sidebarCollapsed}
        conversations={displayConversations}
        activeConversationId={activeConvId}
        connectionStatus={status}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={currentUser ? handleDeleteConversation : undefined}
        currentUser={currentUser}
        onLogout={handleLogout}
        onSelectRule={handleSelectRule}
        selectedRuleCode={selectedRule?.code}
        authToken={authToken}
      />
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
        selectedEmployee={selectedEmployee}
        selectedRule={selectedRule}
      />
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={() => {
          setIsLoginModalOpen(false);
          setLoginModalTitleHint(null);
        }}
        onLoginSuccess={handleLoginSuccess}
        titleHint={loginModalTitleHint}
      />
      {/* 规则保存成功提示 */}
      {saveSuccessMessage && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg shadow-lg z-50 flex items-center gap-3">
          <span>{saveSuccessMessage}</span>
          <button 
            onClick={() => setSaveSuccessMessage(null)} 
            className="text-green-500 hover:text-green-700 font-bold"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
