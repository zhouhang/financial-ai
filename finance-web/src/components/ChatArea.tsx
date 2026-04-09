import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Paperclip,
  Send,
  Loader2,
  X,
  FileSpreadsheet,
} from 'lucide-react';
import type { ConnectionStatus, Message, MessageAttachment, UploadedFile, UserTaskRule } from '../types';
import MessageBubble, { LoadingIndicator } from './MessageBubble';
import type { ReconExecutionMode } from './recon/ReconConversationBar';

/** 仅允许上传 Excel 和 CSV 文件 */
const ALLOWED_EXTENSIONS = ['.xlsx', '.xls', '.xlsm', '.xlsb', '.csv'];

/** 暂存文件（本地还没上传的） */
interface StagedFile {
  file: File;
  name: string;
  size: number;
}

const EMPTY_STATE_CAPABILITIES = [
  {
    key: 'proc',
    label: '数据整理',
    accentClass: 'border-[rgba(59,130,246,0.24)] bg-[rgba(59,130,246,0.1)] text-blue-600',
  },
  {
    key: 'recon',
    label: '数据对账',
    accentClass: 'border-[rgba(14,165,233,0.24)] bg-[rgba(14,165,233,0.1)] text-sky-600',
  },
  {
    key: 'insight',
    label: '数据洞察',
    accentClass: 'border-[rgba(245,158,11,0.24)] bg-[rgba(245,158,11,0.1)] text-amber-600',
  },
] as const;

function _formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
void _formatFileSize; // Reserved for future use

interface ChatAreaProps {
  messages: Message[];
  isLoading: boolean;
  isLoadingConversation?: boolean;
  connectionStatus: ConnectionStatus;
  onSendMessage: (text: string, attachments?: MessageAttachment[], silent?: boolean) => void;
  onFileUploaded: (file: UploadedFile) => void;
  threadId: string;
  showInput?: boolean;
  currentUser?: Record<string, unknown> | null;
  /** 对话名称，显示在顶部左侧 */
  conversationTitle?: string;
  /** 未登录时显示登录按钮，点击回调 */
  onLogin?: () => void;
  /** 侧边栏是否收起 */
  sidebarCollapsed?: boolean;
  /** 切换侧边栏收起/展开 */
  /** 认证 token */
  authToken?: string | null;
  onToggleSidebar?: () => void;
  /** 正在流式输出的消息 ID */
  streamingMessageId?: string | null;
  /** 选中的任务 */
  selectedTask?: UserTaskRule | null;
  /** 当前任务下可选规则 */
  taskRules?: UserTaskRule[];
  /** 当前选中的规则 code */
  selectedRuleCode?: string | null;
  /** 切换规则 */
  onSelectTaskRule?: (ruleCode: string) => void;
  /** 对账规则列表，主线程接入后可启用规则切换 */
  reconRules?: UserTaskRule[];
  /** 当前选中的对账规则 code */
  selectedReconRuleCode?: string | null;
  /** 当前对账执行方式 */
  reconExecutionMode?: ReconExecutionMode;
  /** 切换对账规则 */
  onSelectReconRule?: (ruleCode: string) => void;
  /** 切换对账执行方式 */
  onChangeReconExecutionMode?: (mode: ReconExecutionMode) => void;
  /** 打开数据连接入口 */
  onOpenDataConnections?: () => void;
  /** 嵌入对账工作台时隐藏聊天页自身头部，避免和工作台头部重叠 */
  hideHeader?: boolean;
}

export default function ChatArea({
  messages,
  isLoading,
  isLoadingConversation = false,
  connectionStatus,
  onSendMessage,
  onFileUploaded,
  threadId,
  showInput = true,
  currentUser,
  conversationTitle,
  onLogin,
  sidebarCollapsed = false,
  onToggleSidebar,
  streamingMessageId,
  authToken,
  selectedTask,
  taskRules = [],
  selectedRuleCode,
  onSelectTaskRule,
  reconRules = [],
  selectedReconRuleCode,
  reconExecutionMode,
  onSelectReconRule,
  hideHeader = false,
}: ChatAreaProps) {
  const [inputText, setInputText] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [internalReconExecutionMode, setInternalReconExecutionMode] =
    useState<ReconExecutionMode>('upload');
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const isProcContext = selectedTask?.task_type === 'proc';
  const isReconContext = selectedTask?.task_type === 'recon';
  const availableTaskRules =
    isProcContext && taskRules.length > 0
      ? taskRules
      : isProcContext && selectedTask
        ? [selectedTask]
        : [];
  const currentTaskRule =
    availableTaskRules.find((rule) => rule.rule_code === selectedRuleCode) ??
    (isProcContext ? selectedTask : null) ??
    availableTaskRules[0] ??
    null;
  const availableReconRules = isReconContext
    ? reconRules.filter((rule) => rule.task_type === 'recon')
    : [];
  const resolvedReconExecutionMode =
    reconExecutionMode ?? internalReconExecutionMode;
  const currentReconRule = isReconContext
    ? availableReconRules.find((rule) => rule.rule_code === selectedReconRuleCode) ??
      selectedTask ??
      availableReconRules[0] ??
      null
    : null;
  const headerRuleOptions = isProcContext
    ? availableTaskRules
    : isReconContext
      ? availableReconRules
      : [];
  const headerSelectedRuleCode = isProcContext
    ? selectedRuleCode ?? currentTaskRule?.rule_code ?? ''
    : isReconContext
      ? selectedReconRuleCode ?? currentReconRule?.rule_code ?? ''
      : '';
  const activeStagedFiles =
    isReconContext && resolvedReconExecutionMode === 'data_source'
      ? []
      : stagedFiles;
  const canStartReconFromDataSource =
    isReconContext &&
    resolvedReconExecutionMode === 'data_source' &&
    Boolean(currentReconRule);

  useEffect(() => {
    if (reconExecutionMode) {
      setInternalReconExecutionMode(reconExecutionMode);
    }
  }, [reconExecutionMode]);

  const scrollMessagesToBottom = useCallback((behavior: ScrollBehavior) => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({
      top: container.scrollHeight,
      behavior,
    });
  }, []);

  // 自动滚动到最新消息
  useEffect(() => {
    // 会话加载完成后滚动到底部（不使用动画，直接跳转）
    if (!isLoadingConversation && messages.length > 0) {
      // 使用 setTimeout 确保 DOM 完全渲染后再滚动（修复刷新页面不滚动的问题）
      const timer = setTimeout(() => {
        scrollMessagesToBottom('auto');
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isLoadingConversation, messages.length, scrollMessagesToBottom]);

  // 新消息时平滑滚动（避免在初始加载时触发）
  useEffect(() => {
    // 只在消息数量变化且不在加载会话时才平滑滚动
    if (!isLoadingConversation && messages.length > 0) {
      scrollMessagesToBottom('smooth');
    }
  }, [messages.length, isLoading, isLoadingConversation, scrollMessagesToBottom]);

  // 流式消息内容变化时也触发滚动（确保长消息流式输出时页面自动下滑）
  useEffect(() => {
    if (!isLoadingConversation && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'assistant') {
        scrollMessagesToBottom('smooth');
      }
    }
  }, [messages.map(m => m.content).join(''), isLoadingConversation, scrollMessagesToBottom]);

  // 聚焦输入框
  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showInput, threadId]);

  // 暴露聚焦函数给父组件
  useEffect(() => {
    // 可以通过其他方式触发聚焦
  }, []);

  // 确保上传状态正确初始化
  useEffect(() => {
    console.log('ChatArea mounted, resetting upload state');
    setIsUploading(false);
  }, []);

  // 发送消息（含文件上传）
  const handleSend = useCallback(async () => {
    const text = inputText.trim();
    if ((!text && activeStagedFiles.length === 0 && !canStartReconFromDataSource) || isLoading || isUploading) return;

    let attachments: MessageAttachment[] | undefined;
    let uploadedList: UploadedFile[] = [];

    // 有暂存文件时先上传
    if (activeStagedFiles.length > 0) {
      setIsUploading(true);
      let uploadFailed = false;
      let uploadErrorMessage = '';
      let authExpired = false;
      try {
        const attachmentsList: MessageAttachment[] = [];

        for (const [index, staged] of activeStagedFiles.entries()) {
          const formData = new FormData();
          formData.append('file', staged.file);
          formData.append('thread_id', threadId);
          // 第一个文件时设置 is_first_file=1，其他为0，避免字符串 "false" 被后端当成真值。
          formData.append('is_first_file', index === 0 ? '1' : '0');
          if (authToken) {
            formData.append('auth_token', authToken);
          }

          const resp = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            const detail = String(err.detail || err.message || '上传失败');
            uploadFailed = true;
            uploadErrorMessage = detail;
            authExpired =
              resp.status === 401 ||
              detail.includes('无效的 auth_token') ||
              detail.includes('token') ||
              detail.includes('登录');
            break;
          }

          const result = await resp.json();
          attachmentsList.push({
            name: result.filename,
            size: result.size,
            path: result.file_path,
          });
          uploadedList.push({
            name: result.filename,
            path: result.file_path,
            size: result.size,
            uploadedAt: new Date(),
          });
        }

        if (uploadFailed) {
          const message = authExpired
            ? '登录已过期，请重新登录后再上传文件。'
            : uploadErrorMessage || '文件上传失败，请重试。';
          window.alert(message);
          if (authExpired) {
            onLogin?.();
          }
          return;
        }

        attachments = attachmentsList;
      } catch {
        window.alert('文件上传失败，请重试。');
        return;
      } finally {
        setIsUploading(false);
        if (attachments) {
          setStagedFiles([]);
        }
      }
    }

    const finalText =
      text ||
      (attachments && attachments.length > 0
        ? `已上传 ${attachments.length} 个文件，请按当前规则处理。`
        : isReconContext
          ? `请按规则「${currentReconRule?.name || '当前对账规则'}」使用数据源执行对账。`
          : `请按规则「${currentTaskRule?.name || '当前规则'}」处理。`);

    // 先发送用户消息（显示文件附件）
    onSendMessage(finalText, attachments);
      
    // 然后通知父组件文件已上传（显示系统消息）
    uploadedList.forEach((f) => onFileUploaded(f));
    
    setInputText('');
  }, [
    activeStagedFiles,
    canStartReconFromDataSource,
    currentReconRule?.name,
    currentTaskRule?.name,
    inputText,
    isLoading,
    isUploading,
    authToken,
    isReconContext,
    onFileUploaded,
    onLogin,
    onSendMessage,
    threadId,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // 忽略输入法组合过程中的按键事件（中文、日文等）
    if (e.nativeEvent.isComposing) {
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 选文件 → 暂存到本地（不上传），仅允许 Excel/CSV，最多 2 个
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const rejected: string[] = [];
    const newStaged: StagedFile[] = [];
    for (const file of Array.from(files)) {
      const ext = '.' + (file.name.split('.').pop()?.toLowerCase() || '');
      if (ALLOWED_EXTENSIONS.includes(ext)) {
        newStaged.push({ file, name: file.name, size: file.size });
      } else {
        rejected.push(file.name);
      }
    }

    if (rejected.length > 0) {
      alert(`仅支持 Excel 和 CSV 文件（.xlsx、.xls、.xlsm、.xlsb、.csv），以下文件已忽略：\n${rejected.join('\n')}`);
    }
    if (newStaged.length > 0) {
      setStagedFiles((prev) => [...prev, ...newStaged]);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  // 点击上传按钮
  const handleUploadClick = useCallback(() => {
    console.log('Upload button clicked, isUploading:', isUploading);
    if (isUploading) {
      console.warn('Already uploading, ignoring click');
      return;
    }
    fileInputRef.current?.click();
  }, [isUploading]);

  // 移除暂存文件
  const removeStagedFile = useCallback((index: number) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // 处理表单提交（登录/注册）- 不显示明文消息
  const handleFormSubmit = useCallback((formData: Record<string, unknown>) => {
    console.log('Handling form submit (silent):', { ...formData, password: '***' });
    // 静默发送，不在UI中显示（避免暴露密码）
    const jsonMessage = JSON.stringify(formData);
    onSendMessage(jsonMessage, undefined, true); // silent = true
  }, [onSendMessage]);

  const inputPlaceholder = isReconContext
    ? resolvedReconExecutionMode === 'data_source'
      ? `当前规则：${currentReconRule?.name || '未选择规则'}。可直接发送开始按数据源执行，或补充说明。`
      : `当前规则：${currentReconRule?.name || '未选择规则'}。可上传待对账文件，或补充执行说明。`
    : selectedTask
      ? `当前规则：${currentTaskRule?.name || selectedTask.name || '未选择规则'}。可上传文件，或补充执行说明。`
      : '描述您的分析需求 (Shift+Enter 换行)...';

  return (
    <div className="flex min-h-0 flex-1 flex-col min-w-0 bg-surface-secondary relative">
      {/* ── Header ── */}
      {!hideHeader && (
        <header className="sticky top-0 z-20 h-14 bg-surface border-b border-border flex items-center justify-between gap-4 px-6 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            {onToggleSidebar && (
              <button
                onClick={onToggleSidebar}
                className="p-1.5 rounded-lg text-text-secondary hover:bg-surface-tertiary hover:text-text-primary transition-colors shrink-0"
                title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
              >
                {sidebarCollapsed ? (
                  <ChevronRight className="w-5 h-5" />
                ) : (
                  <ChevronLeft className="w-5 h-5" />
                )}
              </button>
            )}

            <div
              className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                connectionStatus === 'connected'
                  ? 'bg-green-500'
                  : connectionStatus === 'connecting'
                    ? 'bg-yellow-500 animate-pulse'
                    : 'bg-red-500'
              }`}
            />
            <span className="text-sm font-medium text-text-primary truncate">
              {conversationTitle || 'Tally 智能财务助手'}
            </span>
          </div>
          <div className="flex min-w-0 items-center justify-end gap-2 shrink-0">
            {(isProcContext || isReconContext) && (
              <div className="relative min-w-[240px] max-w-[360px]">
                <select
                  value={headerSelectedRuleCode}
                  onChange={(event) => {
                    if (isProcContext) {
                      onSelectTaskRule?.(event.target.value);
                      return;
                    }
                    onSelectReconRule?.(event.target.value);
                  }}
                  disabled={headerRuleOptions.length === 0}
                  className="h-11 w-full appearance-none rounded-xl border border-border bg-surface pl-4 pr-12 text-sm font-medium text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-surface-secondary disabled:text-text-muted"
                >
                  {headerRuleOptions.map((rule) => (
                    <option key={rule.rule_code} value={rule.rule_code}>
                      {rule.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              </div>
            )}
            {!currentUser && onLogin ? (
              <button
                onClick={onLogin}
                className="px-4 py-2 text-sm font-medium bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors"
              >
                登录
              </button>
            ) : currentUser ? null : (
              <span
                className={`text-xs font-medium px-3 py-1.5 rounded-full ${
                  connectionStatus === 'connected'
                    ? 'bg-green-50 text-green-600'
                    : connectionStatus === 'connecting'
                      ? 'bg-yellow-50 text-yellow-600'
                      : 'bg-red-50 text-red-600'
                }`}
              >
                {connectionStatus === 'connected'
                  ? '已连接'
                  : connectionStatus === 'connecting'
                    ? '连接中'
                    : '未连接'}
              </span>
            )}
          </div>
        </header>
      )}

      {/* ── Messages ── */}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-6 pt-6 pb-32 space-y-5">
        {/* 会话加载中 */}
        {isLoadingConversation && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-4" />
              <p className="text-sm text-text-secondary">正在加载会话...</p>
            </div>
          </div>
        )}
        
        {/* 空状态 */}
        {!isLoadingConversation && messages.length === 0 && !isLoading && (
          <div className="flex justify-center pt-10">
            <div className="w-full max-w-2xl text-center">
              <h3 className="text-base font-semibold text-text-primary">
                {currentUser ? '开始一条财务对话' : 'Tally 财务助手已就绪'}
              </h3>
              <p className="mt-2 text-sm text-text-secondary leading-6">
                直接输入需求或上传文件，我会自动匹配处理流程。
              </p>

              <div className="mt-4 flex flex-wrap items-center justify-center gap-2.5">
                {EMPTY_STATE_CAPABILITIES.map((capability) => (
                  <span
                    key={capability.key}
                    className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${capability.accentClass}`}
                  >
                    {capability.label}
                  </span>
                ))}
              </div>

              {!currentUser && onLogin && (
                <div className="mt-4">
                  <p className="text-xs text-text-muted">
                    登录后即可使用以上能力，并保存您的规则与对话记录。请点击右上角登录。
                  </p>
                </div>
              )}

              <p className="mt-4 text-xs text-text-muted">
                例如：整理本月台账、对比两份结算明细、给出经营洞察建议
              </p>
            </div>
          </div>
        )}

        {/* 消息列表 */}
        {!isLoadingConversation && messages.map((msg) => (
          <MessageBubble 
            key={msg.id} 
            message={msg} 
            onFormSubmit={handleFormSubmit}
            isStreaming={msg.id === streamingMessageId}
          />
        ))}

        {isLoading && <LoadingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Floating Input Bar ── */}
      {showInput && (
      <div className="absolute bottom-0 left-0 right-0 pointer-events-none z-10">
        <div className="px-6 pb-3 pointer-events-none">
          <div className="max-w-4xl mx-auto pointer-events-none">
            {/* Floating container with shadow */}
            <div className="bg-surface-elevated rounded-2xl shadow-lg border border-border pointer-events-auto overflow-hidden">
              {/* 暂存文件预览条 */}
              {activeStagedFiles.length > 0 && (
                <div className="px-3 pt-3 flex flex-wrap gap-2">
                  {activeStagedFiles.map((sf, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2 text-sm group animate-fade-in-up"
                    >
                      <FileSpreadsheet className="w-4 h-4 text-blue-500 shrink-0" />
                      <span className="text-text-primary font-medium truncate max-w-40">
                        {sf.name}
                      </span>
                      <button
                        onClick={() => removeStagedFile(i)}
                        className="w-5 h-5 rounded-full bg-surface-tertiary hover:bg-red-100 flex items-center justify-center text-text-secondary hover:text-red-500 transition-colors shrink-0 cursor-pointer"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2.5 p-3">
                {/* File upload */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xls,.xlsm,.xlsb,.csv"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                />
                {(!isReconContext || resolvedReconExecutionMode === 'upload') && (
                  <button
                    type="button"
                    onClick={handleUploadClick}
                    disabled={isUploading}
                    className="w-9 h-9 rounded-lg flex items-center justify-center
                      text-text-secondary hover:text-blue-500 hover:bg-blue-50
                      transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0 cursor-pointer"
                    title={'添加 Excel 或 CSV 文件（.xlsx、.xls、.xlsm、.xlsb、.csv）'}
                  >
                    {isUploading ? (
                      <Loader2 className="w-4.5 h-4.5 animate-spin text-blue-500" />
                    ) : (
                      <Paperclip className="w-4.5 h-4.5" />
                    )}
                  </button>
                )}

                {/* Text input */}
                <div className="flex-1 relative">
                  <textarea
                    ref={inputRef}
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={inputPlaceholder}
                    rows={1}
                    className="w-full px-3 py-2 text-sm rounded-lg
                      bg-transparent text-text-primary resize-none
                      focus:outline-none
                      placeholder:text-gray-400"
                    style={{ height: '36px', maxHeight: '120px' }}
                    onInput={(e) => {
                      const target = e.target as HTMLTextAreaElement;
                      target.style.height = '36px';
                      target.style.height = Math.min(target.scrollHeight, 120) + 'px';
                    }}
                  />
                </div>

                {/* Send button */}
                <button
                  onClick={handleSend}
                  disabled={(!inputText.trim() && activeStagedFiles.length === 0 && !canStartReconFromDataSource) || isLoading || isUploading}
                  className="sidebar-primary-cta w-9 h-9 rounded-full flex items-center justify-center shrink-0 text-white
                    disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none cursor-pointer"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            {/* Bottom hint text */}
            <div className="mt-2">
              <p className="text-center text-[11px] text-text-muted">
                AI 分析结果仅供参考，请结合实际数据进行判断
              </p>
            </div>
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
