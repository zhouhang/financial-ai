import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  FileSpreadsheet,
  Pencil,
  Tag,
  User,
} from 'lucide-react';
import type { Message, MessageAttachment, SkillHitInfo } from '../types';

interface MessageBubbleProps {
  message: Message;
  onFormSubmit?: (formData: Record<string, unknown>) => void;
  /** 是否正在流式输出（显示闪烁光标） */
  isStreaming?: boolean;
}

// 过滤用户消息中的 Agent 前缀
function filterUserMessage(content: string): string {
  return content.replace(/^\[AGENT:data_process\]\s*/, '');
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

/** deep_agent 思考过程折叠块 */
function ThinkingBlock({ thinkingContent }: { thinkingContent: string }) {
  const [expanded, setExpanded] = useState(false);

  // 把思考过程拆成可读的步骤列表
  const steps = thinkingContent
    .split(/\n\n+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 20); // 最多展示 20 条

  return (
    <div className="flex justify-start animate-fade-in-up mb-3">
      <div className="bg-slate-50 border border-slate-200 rounded-xl max-w-2xl w-full overflow-hidden">
        {/* 标题行 */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center justify-between w-full px-4 py-2.5 gap-3 cursor-pointer hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm">🧠</span>
            <span className="text-xs font-medium text-slate-600">AI 思考过程</span>
            <span className="text-xs text-slate-400 bg-slate-200 px-1.5 py-0.5 rounded-full">
              {steps.length} 步
            </span>
          </div>
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          )}
        </button>

        {/* 展开内容 */}
        {expanded && (
          <div className="px-4 pb-3 space-y-2 border-t border-slate-200">
            <div className="mt-2 space-y-1.5">
              {steps.map((step, i) => (
                <div key={i} className="flex gap-2.5 text-xs text-slate-500">
                  <span className="shrink-0 w-4 h-4 rounded-full bg-slate-200 text-slate-500 flex items-center justify-center font-medium text-[10px]">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{step.slice(0, 200)}{step.length > 200 ? '...' : ''}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Skill 命中卡片：展示匹配到的 skill 名称、描述、标签、所需文件 */
function SkillHitCard({ skillHit }: { skillHit: SkillHitInfo }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="flex justify-start animate-fade-in-up mb-3">
      <div className="max-w-2xl w-full">
        {/* 卡片外层：渐变边框 + 圆角 */}
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl overflow-hidden shadow-sm">
          {/* 头部行 */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-blue-100">
            {/* 图标 */}
            <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center text-xl shrink-0 shadow-sm shadow-blue-300">
              {skillHit.skillIcon}
            </div>
            {/* 标题 & 状态 */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-blue-900">{skillHit.skillName}</span>
                <span className="flex items-center gap-1 text-xs text-green-700 bg-green-100 border border-green-200 px-2 py-0.5 rounded-full font-medium">
                  <CheckCircle2 className="w-3 h-3" />
                  已命中
                </span>
              </div>
              <span className="text-xs text-blue-500 font-mono">{skillHit.skillId}</span>
            </div>
            {/* 折叠按鈕 */}
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 rounded-lg hover:bg-blue-100 transition-colors text-blue-400"
            >
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          </div>

          {/* 展开内容 */}
          {expanded && (
            <div className="px-4 py-3 space-y-3">
              {/* 描述 */}
              <p className="text-sm text-blue-800 leading-relaxed">{skillHit.skillDescription}</p>

              {/* 标签列表 */}
              {skillHit.skillTags.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <Tag className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                  {skillHit.skillTags.map((tag, i) => (
                    <span
                      key={i}
                      className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full border border-blue-200"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* 所需文件 */}
              {skillHit.skillInputFiles.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-blue-600 mb-1.5">需要文件</p>
                  <div className="space-y-1">
                    {skillHit.skillInputFiles.map((file, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span
                          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                            file.required ? 'bg-red-400' : 'bg-gray-300'
                          }`}
                        />
                        <span className="font-medium text-blue-800">{file.name}</span>
                        {file.required ? (
                          <span className="text-red-500">必填</span>
                        ) : (
                          <span className="text-gray-400">可选</span>
                        )}
                        {file.hint && (
                          <span className="text-blue-400">· {file.hint}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 状态提示 */}
              <div className="flex items-center gap-2 text-xs text-blue-500 bg-blue-100/60 rounded-lg px-3 py-2">
                <span className="animate-pulse">●</span>
                <span>正在执行数据处理，请稍候...</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Markdown 渲染组件，支持流式打字效果 */
function MarkdownContent({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  // 追踪是否曾经处于流式状态（用于区分新消息和历史消息）
  const hasBeenStreamingRef = useRef(isStreaming);
  const [displayedLength, setDisplayedLength] = useState(() => {
    return isStreaming ? 0 : content.length;
  });
  const [isTyping, setIsTyping] = useState(false);
  const prevContentRef = useRef(content);
  const targetLengthRef = useRef(content.length);

  useEffect(() => {
    if (isStreaming) hasBeenStreamingRef.current = true;
  }, [isStreaming]);

  useEffect(() => {
    if (!hasBeenStreamingRef.current) {
      setDisplayedLength(content.length);
      return;
    }
    const newContent = content;
    if (newContent !== prevContentRef.current) {
      if (newContent.startsWith(prevContentRef.current)) {
        targetLengthRef.current = newContent.length;
      } else {
        setDisplayedLength(0);
        targetLengthRef.current = newContent.length;
      }
      prevContentRef.current = newContent;
    }
    if (displayedLength < targetLengthRef.current) {
      setIsTyping(true);
      const timer = setTimeout(() => {
        setDisplayedLength((prev) => Math.min(prev + 3, targetLengthRef.current));
      }, 16);
      return () => clearTimeout(timer);
    } else {
      setIsTyping(false);
    }
  }, [content, displayedLength]);

  const displayContent =
    !hasBeenStreamingRef.current || (!isStreaming && !isTyping)
      ? content
      : content.slice(0, displayedLength);
  const showCursor = hasBeenStreamingRef.current && (isStreaming || isTyping);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 链接：下载文件用 fetch+blob 触发，普通链接新标签打开
          a: ({ href, children }) => {
            const isDownload =
              href &&
              (href.includes('/result/') ||
                href.match(/\.(xlsx|xls|csv|zip|pdf)(\?|$)/i));

            const handleDownload = async (e: React.MouseEvent<HTMLAnchorElement>) => {
              if (!href) return;
              e.preventDefault();
              // 将绝对 URL 中的 host 剥离，走 Vite 代理（/result/...）
              let proxyUrl = href;
              try {
                const u = new URL(href);
                proxyUrl = u.pathname + u.search;
              } catch {
                // 已经是相对路径
              }
              try {
                const resp = await fetch(proxyUrl);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const blob = await resp.blob();
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = decodeURIComponent(proxyUrl.split('/').pop() || 'download');
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
              } catch (err) {
                console.error('Download failed:', err);
                window.open(href, '_blank');
              }
            };

            return (
              <a
                href={href}
                onClick={isDownload ? handleDownload : undefined}
                target={!isDownload ? '_blank' : undefined}
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800 underline underline-offset-2 cursor-pointer"
              >
                {children}
              </a>
            );
          },
          // 强调
          strong: ({ children }) => (
            <strong className="font-semibold text-text-primary">{children}</strong>
          ),
          // 无序列表
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 my-2 pl-1">{children}</ul>
          ),
          // 有序列表
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 my-2 pl-1">{children}</ol>
          ),
          li: ({ children }) => <li className="text-sm">{children}</li>,
          // 段落
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          // 代码块
          code: ({ children, className }) => {
            const isBlock = className?.startsWith('language-');
            return isBlock ? (
              <pre className="bg-gray-50 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono border border-gray-200">
                <code>{children}</code>
              </pre>
            ) : (
              <code className="bg-gray-100 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
            );
          },
        }}
      >
        {displayContent}
      </ReactMarkdown>
      {showCursor && (
        <span className="streaming-cursor inline-block w-0.5 h-4 bg-blue-500 ml-0.5 align-middle animate-pulse" />
      )}
    </div>
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
          <div className="message-content text-sm text-text-primary leading-relaxed">
            <MarkdownContent content={message.content} isStreaming={isStreaming} />
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
  // 过滤掉 Agent 前缀
  const displayContent = filterUserMessage(message.content);

  return (
    <div className="flex gap-3 justify-end animate-fade-in-up">
      <div className="flex-1 min-w-0 flex flex-col items-end">
        <div className="bg-gradient-to-r from-blue-500 to-blue-600 rounded-2xl rounded-tr-md px-4 py-3 shadow-md shadow-blue-500/20 max-w-2xl">
          <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">
            {displayContent}
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
  // deep_agent 思考过程消息：展示为折叠块
  if (message.isThinking && message.thinkingContent) {
    return <ThinkingBlock thinkingContent={message.thinkingContent} />;
  }
  // skill 命中卡片消息：展示为独立卡片
  if (message.skillHit) {
    return <SkillHitCard skillHit={message.skillHit} />;
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
