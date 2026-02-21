import { useCallback, useRef, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import { useWebSocket } from './hooks/useWebSocket';
import { useConversations } from './hooks/useConversations';
import type {
  Conversation,
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

export default function App() {
  // ── 会话状态 ──────────────────────────────────────────────
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string>('');

  // ── 当前会话 ──────────────────────────────────────────────
  const activeConv = conversations.find((c) => c.id === activeConvId);
  const messages = activeConv?.messages || [];

  // ── 认证状态 ────────────────────────────────────────────────
  const [authToken, setAuthToken] = useState<string | null>(() => {
    return localStorage.getItem('finflux_auth_token');
  });
  const [currentUser, setCurrentUser] = useState<Record<string, unknown> | null>(() => {
    const saved = localStorage.getItem('finflux_current_user');
    return saved ? JSON.parse(saved) : null;
  });

  // ── 服务器会话管理 ──────────────────────────────────────────
  const {
    serverConversations,
    isLoading: _isLoadingConversations,
    loadConversations,
    loadConversation,
    deleteConversation: deleteServerConversation,
    clearCache: clearConversationsCache,
  } = useConversations({ authToken });
  // TODO: 使用 _isLoadingConversations 显示加载状态
  void _isLoadingConversations;

  // 跟踪本地会话与服务器会话的映射（本地临时ID -> 服务器ID）
  const convIdMapRef = useRef<Map<string, string>>(new Map());
  
  // 追踪对账任务状态（用于在任务完成时删除"任务启动"消息）
  const taskStartedRef = useRef<Map<string, boolean>>(new Map());

  // ── 加载和中断状态 ────────────────────────────────────────
  const [isLoading, setIsLoading] = useState(false);
  const [waitingForFileUpload, setWaitingForFileUpload] = useState(false);
  
  // ── 流式输出状态 ──────────────────────────────────────────
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  // ── 响应目标会话追踪 ───────────────────────────────────────
  const pendingConvIdRef = useRef<string | null>(null);

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
            let content = '';
            
            // 添加步骤指示器
            content += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;
            content += question;
            
            if (hint) {
              content += `\n\n${hint}`;
            }
            
            content += `\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
            
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
          break;

        case 'auth':
          // 登录/注册成功，保存 token
          if (data.token) {
            setAuthToken(data.token);
            localStorage.setItem('finflux_auth_token', data.token);
            if (data.user) {
              setCurrentUser(data.user);
              localStorage.setItem('finflux_current_user', JSON.stringify(data.user));
            }
          }
          break;

        case 'auth_verify':
          // 认证验证响应（WebSocket连接建立后验证现有token）
          if (data.success) {
            // token 仍然有效，同步用户信息（如果返回了）
            if (data.user) {
              setCurrentUser(data.user);
              localStorage.setItem('finflux_current_user', JSON.stringify(data.user));
            }
            console.log('Auth token verified successfully');
          } else {
            // token 已过期或无效，清除本地凭证
            console.log('Auth token verification failed, clearing stored credentials');
            setAuthToken(null);
            setCurrentUser(null);
            localStorage.removeItem('finflux_auth_token');
            localStorage.removeItem('finflux_current_user');
          }
          break;

        case 'conversation_created':
          // 服务器创建了新会话，记录映射关系
          if (data.conversation_id && data.thread_id) {
            convIdMapRef.current.set(data.thread_id, data.conversation_id);
            // 刷新会话列表
            loadConversations();
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
      // 只在非静默模式下显示用户消息（表单提交时silent=true，避免暴露密码）
      if (!silent) {
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
      sendMessage(text, activeConvId, shouldResume, authToken || undefined, filesToSend, conversationId);
    },
    [appendMessage, sendMessage, activeConvId, waitingForFileUpload, authToken, pendingConvIdRef, convIdMapRef]
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
    localStorage.removeItem('finflux_auth_token');
    localStorage.removeItem('finflux_current_user');
    
    // 清除服务器会话缓存
    clearConversationsCache();
    convIdMapRef.current.clear();
    
    // 清除所有会话，重新开始
    const newConv = createConversation();
    setConversations([newConv]);
    setActiveConvId(newConv.id);
    setIsLoading(false);
    setTasks([]);
    setUploadedFiles([]);
    setTaskResult(null);
    setWaitingForFileUpload(false);
  }, [clearConversationsCache]);

  // ── 新建会话 ──────────────────────────────────────────────
  const handleNewConversation = useCallback(() => {
    // 如果正在加载中，不允许创建新会话（避免消息显示错乱）
    if (isLoading) {
      return;
    }
    const conv = createConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveConvId(conv.id);
    setTasks([]);
    setUploadedFiles([]);
    setTaskResult(null);
  }, [isLoading]);

  // ── 切换会话 ──────────────────────────────────────────────
  const handleSelectConversation = useCallback(async (id: string) => {
    setActiveConvId(id);
    setIsLoading(false);
    
    // 如果是服务器会话且本地没有消息，从服务器加载
    const localConv = conversations.find((c) => c.id === id);
    const isServerConv = serverConversations.some((c) => c.id === id);
    
    if (isServerConv && (!localConv || localConv.messages.length === 0)) {
      const serverConv = await loadConversation(id);
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
        // 没有其他会话，清空当前会话（用户可以点击"开始新分析"创建）
        setActiveConvId('');
      }
    }
  }, [activeConvId, conversations, serverConversations, deleteServerConversation]);

  // ── 合并本地和服务器会话 ────────────────────────────────────
  // 服务器会话优先，本地会话补充（未同步的新会话）
  const mergedConversations = useCallback(() => {
    const serverIds = new Set(serverConversations.map((c) => c.id));
    // 本地会话中不在服务器列表中的（新创建的、未保存的）
    const localOnly = conversations.filter((c) => !serverIds.has(c.id));
    // 服务器会话 + 本地未同步的会话
    return [...localOnly, ...serverConversations];
  }, [conversations, serverConversations]);

  const displayConversations = mergedConversations();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-secondary">
      <Sidebar
        conversations={displayConversations}
        activeConversationId={activeConvId}
        connectionStatus={status}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        currentUser={currentUser}
        onLogout={handleLogout}
      />
      <ChatArea
        messages={messages}
        isLoading={isLoading}
        connectionStatus={status}
        onSendMessage={handleSendMessage}
        onFileUploaded={handleFileUploaded}
        threadId={activeConvId}
        showInput={!!activeConvId}
      />
    </div>
  );
}
