import { useCallback, useEffect, useRef, useState } from 'react';
import {
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
  connectionStatus: ConnectionStatus;
  onSendMessage: (text: string, attachments?: MessageAttachment[], silent?: boolean) => void;
  onFileUploaded: (file: UploadedFile) => void;
  threadId: string;
  showInput?: boolean;
}

export default function ChatArea({
  messages,
  isLoading,
  connectionStatus,
  onSendMessage,
  onFileUploaded,
  threadId,
  showInput = true,
}: ChatAreaProps) {
  const [inputText, setInputText] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 自动滚动到最新消息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

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
        <div className="flex items-center gap-3">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              connectionStatus === 'connected'
                ? 'bg-green-500'
                : connectionStatus === 'connecting'
                ? 'bg-yellow-500 animate-pulse'
                : 'bg-red-500'
            }`}
          />
          <div className="flex items-baseline gap-2">
            <h2 className="text-base font-semibold text-gray-900">分析会话</h2>
            <span className="text-xs text-gray-500">
              Tally 智能财务助手
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
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
        </div>
      </header>

      {/* ── AI 正在处理横幅 ── */}
      {isLoading && (
        <div className="bg-blue-50 border-b border-blue-100 px-6 py-2.5 flex items-center gap-2">
          <div className="flex gap-1">
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
          </div>
          <span className="text-sm text-blue-600 font-medium">
            AI 正在处理您的请求...
          </span>
        </div>
      )}

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-6 pt-6 pb-32 space-y-5">
        {messages.length === 0 && !isLoading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <h3 className="text-base font-medium text-gray-800 mb-2">
                开启新会话，开始对话
              </h3>
              <p className="text-sm text-gray-500">
                上传数据文件或直接描述您的分析需求
              </p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onFormSubmit={handleFormSubmit} />
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
