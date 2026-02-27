import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Paperclip,
  Send,
  Loader2,
  X,
  FileSpreadsheet,
  Sparkles,
  MessageSquare,
} from 'lucide-react';
import type { ConnectionStatus, Message, MessageAttachment, UploadedFile, AgentType } from '../types';
import { AVAILABLE_AGENTS } from '../types';
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
  onSendMessage: (text: string, attachments?: MessageAttachment[], silent?: boolean, agentType?: AgentType) => void;
  onFileUploaded: (file: UploadedFile) => void;
  threadId: string;
  showInput?: boolean;
  currentUser?: Record<string, unknown> | null;
  /** 正在流式输出的消息 ID */
  streamingMessageId?: string | null;
  selectedAgent?: AgentType;
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
  streamingMessageId,
  selectedAgent = 'reconciliation',
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
    onSendMessage(finalText, attachments, false, selectedAgent);
      
    // 然后通知父组件文件已上传（显示系统消息）
    uploadedList.forEach((f) => onFileUploaded(f));
    
    setInputText('');
  }, [inputText, isLoading, isUploading, stagedFiles, threadId, onFileUploaded, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
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
    <div style={{
      flex: '1 1 0%',
      display: 'flex',
      flexDirection: 'column',
      minWidth: 0,
      background: '#f8fafc',
      height: '100%',
      overflow: 'hidden',
    }}>
      {/* ── Header ── */}
      <header style={{
        height: '48px',
        background: 'white',
        borderBottom: '1px solid #f1f5f9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        flexShrink: 0,
      }}>
        <div className="flex items-center gap-2">
          {/* 当前选中的数字员工 */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 rounded-md">
            {selectedAgent === 'data_process' ? (
              <Sparkles className="w-3.5 h-3.5 text-blue-600" />
            ) : (
              <MessageSquare className="w-3.5 h-3.5 text-blue-600" />
            )}
            <span className="text-xs font-medium text-blue-600">
              {selectedAgent === 'data_process' ? '数据整理数字员工' : '智能对账助手'}
            </span>
          </div>
          <div className="w-px h-4 bg-gray-200" />
          <h2 className="text-sm font-medium text-gray-700">分析会话</h2>
        </div>
      </header>

      {/* ── AI 正在处理横幅 ── */}
      {isLoading && (
        <div style={{
          background: 'white',
          borderBottom: '1px solid #f1f5f9',
          padding: '8px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexShrink: 0,
        }}>
          <div className="flex gap-1">
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
          </div>
          <span className="text-xs text-gray-500">
            AI 正在处理...
          </span>
        </div>
      )}

      {/* ── Messages ── */}
      <div style={{
        flex: '1 1 0%',
        overflowY: 'auto',
        padding: '24px 16px 0 16px',
        minHeight: 0,
        marginBottom: '16px',
      }}>
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
            <div className="text-center max-w-md">
              <div className="w-16 h-16 rounded-2xl bg-white border border-gray-100 flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              {currentUser ? (
                <>
                  <h3 className="text-base font-medium text-gray-800 mb-2">
                    开启新对话
                  </h3>
                  <p className="text-sm text-gray-500">
                    上传数据文件或直接描述您的分析需求
                  </p>
                </>
              ) : (
                <>
                  <h3 className="text-base font-medium text-gray-800 mb-2">
                    未登录
                  </h3>
                  <p className="text-sm text-gray-500">
                    发送"登录"或"注册"进行身份验证
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

      {/* ── Input Bar ── */}
      {showInput && (
      <div style={{
        padding: '0 16px 16px 16px',
        flexShrink: 0,
      }}>
        <div style={{ maxWidth: '768px', margin: '0 auto' }}>
          {/* Input container */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
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

              <div className="flex items-center gap-3 p-3">
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
                    text-gray-400 hover:text-blue-500 hover:bg-blue-50
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
                    placeholder="尽管问..."
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
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0
                    bg-blue-500 text-white
                    hover:bg-blue-600 transition-colors
                    disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-blue-500 cursor-pointer"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Bottom hint text */}
            <div className="mt-3 text-center">
              <p className="text-xs text-gray-400">
                智能财务助手
              </p>
            </div>
        </div>
      </div>
      )}
    </div>
  );
}
