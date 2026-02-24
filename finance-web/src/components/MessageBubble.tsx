import { useState, useEffect, useRef } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  FileText,
  FileSpreadsheet,
  Pencil,
  User,
} from 'lucide-react';
import type { Message, MessageAttachment } from '../types';

interface MessageBubbleProps {
  message: Message;
  onFormSubmit?: (formData: Record<string, unknown>) => void;
  /** 是否正在流式输出（显示闪烁光标） */
  isStreaming?: boolean;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/** 文件附件卡片 */
function FileAttachmentCard({ attachment }: { attachment: MessageAttachment }) {
  return (
    <div className="flex items-center gap-3 bg-white rounded-xl px-3.5 py-2.5 border border-gray-200 shadow-sm max-w-xs">
      <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
        <FileSpreadsheet className="w-4.5 h-4.5 text-blue-500" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800 truncate">{attachment.name}</p>
        <p className="text-xs text-gray-500">{formatFileSize(attachment.size)}</p>
      </div>
    </div>
  );
}

/** System action 消息（READ / WRITE / TOOL） */
function SystemActionMessage({ message }: { message: Message }) {
  const [expanded, setExpanded] = useState(false);

  const iconMap: Record<string, typeof FileText> = {
    read: FileText,
    write: Pencil,
  };
  const Icon = iconMap[message.action || ''] || FileText;

  const labelMap: Record<string, string> = {
    read: 'READ',
    write: 'WRITE',
    tool: 'TOOL',
    info: 'INFO',
  };
  const label = labelMap[message.action || ''] || 'INFO';

  // 根据 action 类型决定颜色主题
  const isWrite = message.action === 'write';
  const iconBgColor = isWrite ? 'bg-blue-50' : 'bg-primary-50';
  const iconColor = isWrite ? 'text-blue-600' : 'text-primary';
  const labelColor = isWrite ? 'text-blue-600' : 'text-primary-dark';

  const statusColor = message.actionDone
    ? 'text-success bg-success/10'
    : 'text-warning bg-warning/10';
  const statusText = message.actionDone ? '已完成' : '进行中';

  return (
    <div className="flex justify-center animate-fade-in-up">
      <div className="bg-white rounded-xl border border-border px-4 py-3 max-w-lg w-full shadow-sm">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center justify-between w-full gap-3 cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <div className={`w-7 h-7 rounded-lg ${iconBgColor} flex items-center justify-center`}>
              <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
            </div>
            <div className="text-left">
              <span className={`text-xs font-semibold ${labelColor} mr-2`}>
                {label}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${statusColor}`}>
                {statusText}
              </span>
            </div>
          </div>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-text-muted" />
          ) : (
            <ChevronRight className="w-4 h-4 text-text-muted" />
          )}
        </button>
        {message.actionDetail && (
          <p className="text-xs text-text-secondary mt-1.5 ml-9.5 truncate">
            {message.actionDetail}
          </p>
        )}
        {expanded && message.content && (
          <div className="mt-3 ml-9.5 p-3 bg-surface-secondary rounded-lg text-xs text-text-secondary leading-relaxed border border-border/50">
            {message.content}
          </div>
        )}
      </div>
    </div>
  );
}

/** 打字机效果组件 - 逐字显示文本（仅用于流式输出的新消息） */
function TypewriterText({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  // 追踪是否曾经处于流式状态（用于区分新消息和历史消息）
  const hasBeenStreamingRef = useRef(isStreaming);
  const [displayedLength, setDisplayedLength] = useState(() => {
    // 如果初始时不是流式状态，说明是历史消息，直接显示全部
    return isStreaming ? 0 : content.length;
  });
  const [isTyping, setIsTyping] = useState(false);
  const prevContentRef = useRef(content);
  const targetLengthRef = useRef(content.length);
  
  // 记录曾经处于流式状态
  useEffect(() => {
    if (isStreaming) {
      hasBeenStreamingRef.current = true;
    }
  }, [isStreaming]);
  
  useEffect(() => {
    // 如果从未处于流式状态（历史消息），直接显示全部内容
    if (!hasBeenStreamingRef.current) {
      setDisplayedLength(content.length);
      return;
    }
    
    // 检测新内容
    const prevContent = prevContentRef.current;
    const newContent = content;
    
    // 如果内容变化了
    if (newContent !== prevContent) {
      // 如果是追加内容（流式输出场景）
      if (newContent.startsWith(prevContent)) {
        // 保持当前显示位置，继续打字
        targetLengthRef.current = newContent.length;
      } else {
        // 内容完全变化，重新开始
        setDisplayedLength(0);
        targetLengthRef.current = newContent.length;
      }
      prevContentRef.current = newContent;
    }
    
    // 如果还没显示完，继续打字
    if (displayedLength < targetLengthRef.current) {
      setIsTyping(true);
      const timer = setTimeout(() => {
        setDisplayedLength((prev) => Math.min(prev + 1, targetLengthRef.current));
      }, 60); // 每个字符 60ms
      return () => clearTimeout(timer);
    } else {
      setIsTyping(false);
    }
  }, [content, displayedLength]);
  
  // 历史消息或打字完成后直接显示完整内容
  const displayContent = !hasBeenStreamingRef.current || (!isStreaming && !isTyping) 
    ? content 
    : content.slice(0, displayedLength);
  const showCursor = hasBeenStreamingRef.current && (isStreaming || isTyping);
  
  return (
    <>
      {displayContent.split(/\{\{?SPINNER\}\}?/).map((part, i, arr) => (
        <span key={i}>
          {part}
          {i < arr.length - 1 && (
            <span className="inline-flex gap-1 ml-0.5 align-middle">
              <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
              <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
              <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            </span>
          )}
        </span>
      ))}
      {/* 打字中或流式输出时显示闪烁光标 */}
      {showCursor && (
        <span className="streaming-cursor inline-block w-0.5 h-4 bg-blue-500 ml-0.5 align-middle animate-pulse" />
      )}
    </>
  );
}

/** AI 消息 */
function AssistantMessage({ message, onFormSubmit, isStreaming = false }: { message: Message; onFormSubmit?: (formData: Record<string, unknown>) => void; isStreaming?: boolean }) {
  const formRef = useRef<HTMLDivElement>(null);
  const isHtmlForm = message.content.includes('<form');
  const isSavingMessage = /^正在保存\.*$/.test(message.content.trim());

  useEffect(() => {
    if (!isHtmlForm || !formRef.current || !onFormSubmit) return;

    const formElement = formRef.current.querySelector('form');
    if (!formElement) return;

    // 调试：检查表单内容
    const formId = formElement.id;
    const inputCount = formElement.querySelectorAll('input').length;
    console.log(`Form rendered: id=${formId}, input count=${inputCount}`);

    // 聚焦第一个输入框
    const firstInput = formElement.querySelector('input:not([type="hidden"]):not([type="submit"])') as HTMLInputElement | null;
    if (firstInput) {
      // 使用 setTimeout 确保 DOM 完全渲染后再聚焦
      setTimeout(() => {
        firstInput.focus();
        console.log(`Focused on first input: ${firstInput.name || firstInput.id}`);
      }, 100);
    }

    const handleSubmit = (e: Event) => {
      e.preventDefault();
      const form = e.target as HTMLFormElement;
      const formData = new FormData(form);
      const data: Record<string, unknown> = {};
      
      // 获取表单类型（login/register）
      const formId = form.id;
      data.form_type = formId.replace('-form', '');
      
      // 收集表单数据
      formData.forEach((value, key) => {
        data[key] = value;
      });

      console.log('Form submitted:', data);
      onFormSubmit(data);
    };

    formElement.addEventListener('submit', handleSubmit);
    return () => formElement.removeEventListener('submit', handleSubmit);
  }, [isHtmlForm, onFormSubmit, message.content]);

  return (
    <div className="flex gap-3 animate-fade-in-up">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shrink-0 mt-0.5 shadow-md shadow-blue-500/20">
        <Bot className="w-4.5 h-4.5 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="bg-white rounded-2xl rounded-tl-md px-4 py-3 shadow-sm border border-border/50 max-w-2xl">
          {isHtmlForm ? (
            <div 
              ref={formRef}
              className="auth-form-wrapper"
              dangerouslySetInnerHTML={{ __html: message.content }}
            />
          ) : isSavingMessage ? (
            <div className="px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-text-secondary">正在保存</span>
                <div className="flex gap-1 ml-1">
                  <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
                  <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
                  <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
                </div>
              </div>
              <p className="text-xs text-text-muted mt-1">请稍候，正在处理您的请求</p>
            </div>
          ) : (
          <div className="message-content text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
            <TypewriterText content={message.content} isStreaming={isStreaming} />
          </div>
          )}
        </div>
        <p className="text-xs text-text-muted mt-1.5 ml-1">
          {formatTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}

/** 用户消息 */
function UserMessage({ message }: { message: Message }) {
  const hasAttachments = message.attachments && message.attachments.length > 0;

  return (
    <div className="flex gap-3 justify-end animate-fade-in-up">
      <div className="flex-1 min-w-0 flex flex-col items-end">
        <div className="bg-gradient-to-r from-blue-500 to-blue-600 rounded-2xl rounded-tr-md px-4 py-3 shadow-md shadow-blue-500/20 max-w-2xl">
          <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
        {/* 文件附件卡片 - 在气泡外面，文字之后 */}
        {hasAttachments && (
          <div className="flex flex-col items-end gap-2 mt-2">
            {message.attachments!.map((att, i) => (
              <FileAttachmentCard key={i} attachment={att} />
            ))}
          </div>
        )}
        <p className="text-xs text-text-muted mt-1.5 mr-1">
          {formatTime(message.timestamp)}
        </p>
      </div>
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shrink-0 mt-0.5 shadow-md shadow-blue-500/20">
        <User className="w-4.5 h-4.5 text-white" />
      </div>
    </div>
  );
}

export default function MessageBubble({ message, onFormSubmit, isStreaming }: MessageBubbleProps) {
  if (message.role === 'system' && message.action) {
    return <SystemActionMessage message={message} />;
  }
  if (message.role === 'assistant') {
    return <AssistantMessage message={message} onFormSubmit={onFormSubmit} isStreaming={isStreaming} />;
  }
  return <UserMessage message={message} />;
}

/** 加载指示器 */
export function LoadingIndicator() {
  return (
    <div className="flex gap-3 animate-fade-in-up">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center shrink-0 mt-0.5">
        <Bot className="w-4.5 h-4.5 text-blue-600" />
      </div>
      <div className="bg-white rounded-2xl rounded-tl-md px-5 py-4 shadow-sm border border-border/50">
        <div className="flex items-center gap-2">
          <span className="text-sm text-text-secondary">AI 正在分析...</span>
          <div className="flex gap-1 ml-1">
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
          </div>
        </div>
        <p className="text-xs text-text-muted mt-1">请稍候，正在处理您的请求</p>
      </div>
    </div>
  );
}
