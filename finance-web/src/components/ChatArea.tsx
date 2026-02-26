import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Paperclip,
  Send,
  Loader2,
  X,
  FileSpreadsheet,
} from 'lucide-react';
import type { ConnectionStatus, Message, MessageAttachment, UploadedFile } from '../types';
import MessageBubble, { LoadingIndicator } from './MessageBubble';

/** 暂存文件（本地还没上传的） */
interface StagedFile {
  file: File;
  name: string;
  size: number;
}

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
  onToggleSidebar?: () => void;
  /** 正在流式输出的消息 ID */
  streamingMessageId?: string | null;
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
}: ChatAreaProps) {
  const [inputText, setInputText] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚动到最新消息
  useEffect(() => {
    // 会话加载完成后滚动到底部（不使用动画，直接跳转）
    if (!isLoadingConversation && messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [isLoadingConversation, messages.length]);
  
  // 新消息时平滑滚动
  useEffect(() => {
    if (!isLoadingConversation) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading, isLoadingConversation]);

  // 流式消息内容变化时也触发滚动（确保长消息流式输出时页面自动下滑）
  useEffect(() => {
    if (!isLoadingConversation && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'assistant') {
        // 当助手消息内容增长时滚动到底部
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [messages.map(m => m.content).join(''), isLoadingConversation]);

  // 聚焦输入框
  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showInput, threadId]);

  // 解析消息中的 SAVE_RULE / SAVE_NEW_RULE 标记，写入 localStorage 供登录后保存使用
  useEffect(() => {
    for (const msg of messages) {
      if (msg.role === 'assistant') {
        const saveRuleMatch = msg.content.match(/\[SAVE_RULE:([^:]+):([^\]]+)\]/);
        if (saveRuleMatch) {
          localStorage.setItem('pending_rule_name', saveRuleMatch[1]);
          localStorage.setItem('pending_source_rule_id', saveRuleMatch[2]);
          localStorage.removeItem('pending_thread_id');
          localStorage.removeItem('pending_is_new_rule');
        }
        const saveNewRuleMatch = msg.content.match(/\[SAVE_NEW_RULE:([^\]]+)\]/);
        if (saveNewRuleMatch) {
          localStorage.setItem('pending_rule_name', saveNewRuleMatch[1]);
          localStorage.setItem('pending_thread_id', threadId);
          localStorage.setItem('pending_is_new_rule', 'true');
          localStorage.removeItem('pending_source_rule_id');
        }
      }
    }
  }, [messages, threadId]);

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
    if ((!text && stagedFiles.length === 0) || isLoading || isUploading) return;

    let attachments: MessageAttachment[] | undefined;
    let uploadedList: UploadedFile[] = [];

    // 有暂存文件时先上传
    if (stagedFiles.length > 0) {
    setIsUploading(true);
    try {
        const attachmentsList: MessageAttachment[] = [];

        for (const [index, staged] of stagedFiles.entries()) {
        try {
          const formData = new FormData();
            formData.append('file', staged.file);
          formData.append('thread_id', threadId);
          // ⚠️ 修复：第一个文件时设置 is_first_file=1，其他为0（避免字符串"false"被当成真值）
          formData.append('is_first_file', index === 0 ? '1' : '0');

          const resp = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
          });

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || '上传失败');
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
        } catch (err) {
            console.error('File upload error:', err);
            // 上传失败也加入附件列表，但不设 path
            attachmentsList.push({
              name: staged.name,
              size: staged.size,
            });
        }
        }

        attachments = attachmentsList;
      } catch {
        // ignore
      } finally {
        setIsUploading(false);
        setStagedFiles([]);
        }
    }

    // 如果没有文字但有文件，自动生成文字
    const finalText = text || `已上传 ${attachments?.length || 0} 个文件，请处理。`;

    // 先发送用户消息（显示文件附件）
    onSendMessage(finalText, attachments);
      
    // 然后通知父组件文件已上传（显示系统消息）
    uploadedList.forEach((f) => onFileUploaded(f));
    
    setInputText('');
  }, [inputText, isLoading, isUploading, stagedFiles, threadId, onFileUploaded, onSendMessage]);

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

  // 选文件 → 暂存到本地（不上传）
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const newStaged: StagedFile[] = Array.from(files).map((file) => ({
      file,
      name: file.name,
      size: file.size,
    }));

    setStagedFiles((prev) => [...prev, ...newStaged]);
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

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-surface-secondary relative">
      {/* ── Header ── */}
      <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          {onToggleSidebar && (
            <button
              onClick={onToggleSidebar}
              className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors shrink-0"
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
          <span className="text-sm font-medium text-gray-800 truncate">
            {conversationTitle || 'Tally 智能财务助手'}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
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

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-6 pt-6 pb-32 space-y-5">
        {/* 会话加载中 */}
        {isLoadingConversation && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-4" />
              <p className="text-sm text-gray-500">正在加载会话...</p>
            </div>
          </div>
        )}
        
        {/* 空状态 */}
        {!isLoadingConversation && messages.length === 0 && !isLoading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              {currentUser ? (
                <>
                  <h3 className="text-base font-medium text-gray-800 mb-2">
                    开启新对话，开始交流
                  </h3>
                  <p className="text-sm text-gray-500">
                    上传数据文件或直接描述您的分析需求
                  </p>
                </>
              ) : (
                <>
                  <h3 className="text-base font-medium text-gray-800 mb-2">
                    您好！我是 Tally 智能财务助手
                  </h3>
                  <p className="text-sm text-gray-500">
                    我可以帮助您进行财务数据对账，上传文件即可开始
                  </p>
                </>
              )}
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
            <div className="bg-white rounded-2xl shadow-lg border border-gray-200 pointer-events-auto overflow-hidden">
              {/* 暂存文件预览条 */}
              {stagedFiles.length > 0 && (
                <div className="px-3 pt-3 flex flex-wrap gap-2">
                  {stagedFiles.map((sf, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-3 py-2 text-sm group animate-fade-in-up"
                    >
                      <FileSpreadsheet className="w-4 h-4 text-blue-500 shrink-0" />
                      <span className="text-gray-800 font-medium truncate max-w-40">
                        {sf.name}
                      </span>
                      <button
                        onClick={() => removeStagedFile(i)}
                        className="w-5 h-5 rounded-full bg-gray-200 hover:bg-red-100 flex items-center justify-center text-gray-500 hover:text-red-500 transition-colors shrink-0 cursor-pointer"
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
                  accept=".csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={handleUploadClick}
                  disabled={isUploading}
                  className="w-9 h-9 rounded-lg flex items-center justify-center
                    text-gray-500 hover:text-blue-500 hover:bg-blue-50
                    transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0 cursor-pointer"
                  title="添加文件（支持多选）"
                >
                  {isUploading ? (
                    <Loader2 className="w-4.5 h-4.5 animate-spin text-blue-500" />
                  ) : (
                    <Paperclip className="w-4.5 h-4.5" />
                  )}
                </button>

                {/* Text input */}
                <div className="flex-1 relative">
                  <textarea
                    ref={inputRef}
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="描述您的分析需求 (Shift+Enter 换行)..."
                    rows={1}
                    className="w-full px-3 py-2 text-sm rounded-lg
                      bg-transparent resize-none
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
                  disabled={(!inputText.trim() && stagedFiles.length === 0) || isLoading || isUploading}
                  className="w-9 h-9 rounded-full flex items-center justify-center shrink-0
                    bg-gradient-to-r from-blue-500 to-blue-600 text-white
                    hover:shadow-md hover:shadow-blue-500/30 transition-all
                    disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none cursor-pointer"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            {/* Bottom hint text */}
            <div className="mt-2">
              <p className="text-center text-[11px] text-gray-400">
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
