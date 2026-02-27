import { useState, useEffect, useRef, useMemo } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  FileText,
  FileSpreadsheet,
  Pencil,
  User,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { Message, MessageAttachment } from '../types';
import { ResponsiveTable, type TableColumn } from './ResponsiveTable';
import { useTablePreferences } from '../hooks/useTablePreferences';

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

/** 移除 SAVE_RULE / SAVE_NEW_RULE 内部标记，不展示给用户 */
function stripSaveRuleTag(content: string): string {
  return content
    .replace(/\[SAVE_RULE:[^\]]+\]\s*/g, '')
    .replace(/\[SAVE_NEW_RULE:[^\]]+\]\s*/g, '')
    .trim();
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

const SPINNER_REGEX = /\{\{?SPINNER\}\}?/;

interface ParsedTable {
  headers: string[];
  rows: string[][];
  isColumnTable?: boolean;
}

function parseMarkdownTable(content: string): ParsedTable | null {
  const lines = content.trim().split('\n');
  if (lines.length < 2) return null;

  const headerLine = lines[0];
  const separatorLine = lines[1];

  if (!separatorLine.includes('|') || !separatorLine.includes('-')) return null;

  const headers = headerLine
    .split('|')
    .slice(1, -1)
    .map((h) => h.trim());

  const rows: string[][] = [];
  for (let i = 2; i < lines.length; i++) {
    const row = lines[i]
      .split('|')
      .slice(1, -1)
      .map((cell) => cell.trim());
    if (row.some((c) => c !== '')) {
      rows.push(row);
    }
  }

  if (headers.length === 0) return null;

  const isColumnTable = headers.length === 1 && headers[0] === '列名';

  return { headers, rows, isColumnTable };
}

function extractFileColumnTables(content: string): {
  columnTables: { filename: string; columns: string[]; rowCount?: number; sampleRows?: string[][] }[];
  before: string;
  after: string;
} {
  const results: { filename: string; columns: string[]; rowCount?: number; sampleRows?: string[][] }[] = [];
  const analysisCompleteIndex = content.indexOf('文件展示如下');
  const searchStart = analysisCompleteIndex >= 0 ? analysisCompleteIndex : 0;
  const searchContent = content.slice(searchStart);

  // 支持两种格式：简单 (985行) 和复杂 (财务 85%) 976行
  const tableBlockRegex = /\*\*([^*]+)\*\*\s*(?:\((\d+)行\)|\([^)]*\)\s*(\d+)行)\s*\n(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)*)/g;
  let lastTableEnd = 0;
  let firstFileIndex = searchStart;
  let match;

  while ((match = tableBlockRegex.exec(searchContent)) !== null) {
    const filename = match[1].trim();
    const rowCount = parseInt(match[2] || match[3], 10) || 0;
    if (filename.includes('文件分析')) continue;

    const tableContent = match[4];
    const parsed = parseMarkdownTable(tableContent);

    if (parsed && parsed.headers.length > 0) {
      const columns = parsed.headers.filter((c) => c && !c.startsWith('…'));
      const sampleRows = parsed.rows;
      if (columns.length > 0) {
        if (results.length === 0) firstFileIndex = searchStart + match.index;
        results.push({ filename, columns, rowCount, sampleRows });
        lastTableEnd = searchStart + match.index + match[0].length;
      }
    }
  }

  if (results.length >= 1) {
    return {
      columnTables: results,
      before: content.slice(0, firstFileIndex),
      after: lastTableEnd > 0 ? content.slice(lastTableEnd) : '',
    };
  }

  return { columnTables: [], before: content, after: '' };
}

function mergeColumnTables(tables: { filename: string; columns: string[] }[]): ParsedTable | null {
  if (tables.length === 0) return null;

  const maxRows = Math.max(...tables.map(t => t.columns.length));
  
  const headers = tables.map(t => t.filename);
  const rows: string[][] = [];

  for (let i = 0; i < maxRows; i++) {
    const row = tables.map(t => t.columns[i] || '');
    rows.push(row);
  }

  return { headers, rows, isColumnTable: true };
}

function HorizontalColumnTable({
  filename,
  columns,
  rowCount,
  sampleRows,
}: {
  filename: string;
  columns: string[];
  rowCount?: number;
  sampleRows?: string[][];
}) {
  const displayName = rowCount != null && rowCount > 0 ? `${filename} (${rowCount} 行)` : filename;
  return (
    <div className="my-3">
      <div className="text-sm font-medium text-gray-700 mb-1">{displayName}</div>
      <div className="border border-gray-200 rounded-lg overflow-x-auto bg-white" style={{ WebkitOverflowScrolling: 'touch' }}>
        <table className="text-sm min-w-max">
          <thead>
            <tr className="bg-gray-50">
              {columns.map((col, i) => (
                <th key={i} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          {sampleRows && sampleRows.length > 0 && (
            <tbody>
              {sampleRows.map((row, ri) => (
                <tr key={ri}>
                  {columns.map((_, i) => (
                    <td key={i} className="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">
                      {row[i] ?? ''}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          )}
        </table>
      </div>
    </div>
  );
}

function extractTablesFromMarkdown(content: string): { table: ParsedTable; before: string; after: string }[] {
  const results: { table: ParsedTable; before: string; after: string }[] = [];
  const tableRegex = /\|[^\n]+\|[^\n]*\n\|[-:\s|]+\|\n((?:\|[^\n]+\|\n?)+)/g;
  
  let lastIndex = 0;
  let match;
  
  while ((match = tableRegex.exec(content)) !== null) {
    const tableContent = match[0];
    const parsed = parseMarkdownTable(tableContent);
    
    if (parsed) {
      results.push({
        table: parsed,
        before: content.slice(lastIndex, match.index),
        after: '',
      });
      lastIndex = match.index + tableContent.length;
    }
  }
  
  if (results.length > 0) {
    results[results.length - 1].after = content.slice(lastIndex);
  }
  
  return results;
}

function TableRenderer({ table, beforeContent }: { table: ParsedTable; beforeContent?: string }) {
  const tableId = useMemo(() => `msg-table-${Math.random().toString(36).slice(2, 9)}`, []);
  const { preferences, isLoaded, setViewMode, toggleColumnVisibility, setColumnWidth } = useTablePreferences(tableId);

  if (table.isColumnTable && table.headers[0] === '列名' && table.rows.length > 0) {
    const columns = table.rows.map((r) => r[0] || '').filter(Boolean);
    const filenameMatch = beforeContent?.match(/\*\*([^*]+)\*\*\s*(?:\((\d+)行\)|\([^)]*\)\s*(\d+)行)/);
    const filename = filenameMatch?.[1]?.trim() || '文件';
    const rowCount = parseInt(filenameMatch?.[2] || filenameMatch?.[3] || '0', 10) || 0;
    return (
      <HorizontalColumnTable
        filename={filename}
        columns={columns}
        rowCount={rowCount || undefined}
        sampleRows={[]}
      />
    );
  }

  const columns: TableColumn[] = table.headers.map((header, index) => ({
    key: `col-${index}`,
    label: header,
    width: index === 0 ? 200 : 120,
    minWidth: 60,
    essential: index === 0,
  }));

  const data = table.rows.map((row) => {
    const rowData: Record<string, unknown> = {};
    row.forEach((cell, index) => {
      rowData[`col-${index}`] = cell;
    });
    return rowData;
  });

  if (!isLoaded) {
    return <div className="animate-pulse h-32 bg-gray-100 rounded"></div>;
  }

  const isExceptionTable = table.headers.includes('异常订单号') && table.headers.includes('异常原因');
  const isColumnRequirementsTable = beforeContent?.includes('列名要求') || beforeContent?.includes('列名未能与');
  const hideToolbar = isExceptionTable || isColumnRequirementsTable;

  return (
    <div className="my-2">
      <ResponsiveTable
        data={data}
        columns={columns}
        viewMode={preferences.viewMode}
        columnVisibility={preferences.columnVisibility}
        columnWidths={preferences.columnWidths}
        filenameTruncationLength={preferences.filenameTruncationLength}
        onViewModeChange={setViewMode}
        onColumnVisibilityChange={toggleColumnVisibility}
        onColumnWidthChange={setColumnWidth}
        showViewMode={!hideToolbar}
        showToolbar={!hideToolbar}
      />
    </div>
  );
}

function preprocessBulletList(content: string): string {
  let normalized = content.replace(/^• (.+)$/gm, '- $1');
  // 兼容后端/中间层把换行压平成空格的场景，尽量恢复 Markdown 结构
  normalized = normalized
    .replace(/\\n/g, '\n')
    .replace(/([^\n])\s+(#{2,6}\s)/g, '$1\n\n$2')
    .replace(/([^\n])\s+(-\s+`[^`]+`)/g, '$1\n$2');
  return normalized;
}

/** 将内容按 HTML 表格拆分为 [文本, 表格, 文本, ...]，确保非表格文字走 Markdown 渲染 */
function splitByHtmlTables(content: string): ({ type: 'markdown'; text: string } | { type: 'html'; html: string })[] {
  const tableRegex = /<table[\s\S]*?<\/table>/gi;
  const parts: ({ type: 'markdown'; text: string } | { type: 'html'; html: string })[] = [];
  let lastIndex = 0;
  let match;
  while ((match = tableRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'markdown', text: content.slice(lastIndex, match.index) });
    }
    parts.push({ type: 'html', html: match[0] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    parts.push({ type: 'markdown', text: content.slice(lastIndex) });
  }
  return parts;
}

/** 渲染带有表格支持的内容 */
function ContentWithTables({ content }: { content: string }) {
  const processedContent = useMemo(() => preprocessBulletList(content), [content]);
  const { columnTables, before, after } = useMemo(() => extractFileColumnTables(processedContent), [processedContent]);
  const regularTables = useMemo(() => extractTablesFromMarkdown(processedContent), [processedContent]);

  if (columnTables.length >= 1) {
    return (
      <>
        {before && (
          <div className="[&_ul]:list-disc [&_ul]:list-inside [&_ol]:list-decimal [&_ol]:list-inside [&_*]:my-0.5">
            <ReactMarkdown>{before}</ReactMarkdown>
          </div>
        )}
        {columnTables.map((table, idx) => (
          <HorizontalColumnTable
            key={idx}
            filename={table.filename}
            columns={table.columns}
            rowCount={table.rowCount}
            sampleRows={table.sampleRows}
          />
        ))}
        {after && (
          <div className="[&_ul]:list-disc [&_ul]:list-inside [&_ol]:list-decimal [&_ol]:list-inside [&_*]:my-0.5">
            <ReactMarkdown>{after}</ReactMarkdown>
          </div>
        )}
      </>
    );
  }

  if (regularTables.length === 0) {
    const htmlTableParts = splitByHtmlTables(processedContent);
    const hasHtmlTables = htmlTableParts.some((p) => p.type === 'html');
    const markdownComponents = {
      p: ({ children }: { children?: React.ReactNode }) => <p className="my-1">{children}</p>,
      ul: ({ children }: { children?: React.ReactNode }) => <ul className="list-disc list-inside my-1">{children}</ul>,
      ol: ({ children }: { children?: React.ReactNode }) => <ol className="list-decimal list-inside my-1">{children}</ol>,
      strong: ({ children }: { children?: React.ReactNode }) => <strong className="font-semibold">{children}</strong>,
      blockquote: ({ children }: { children?: React.ReactNode }) => (
        <blockquote className="pl-4 my-1 text-text-secondary [&+blockquote]:mt-0">{children}</blockquote>
      ),
      code: ({ children }: { children?: React.ReactNode }) => (
        <code className="px-1 py-0.5 rounded bg-gray-100 text-sm">{children}</code>
      ),
    };

    if (hasHtmlTables && htmlTableParts.length > 0) {
      return (
        <div className="[&_ul]:list-disc [&_ul]:list-inside [&_ol]:list-decimal [&_ol]:list-inside [&_*]:my-0.5">
          {htmlTableParts.map((part, idx) =>
            part.type === 'markdown' ? (
              part.text.trim() ? (
                <ReactMarkdown key={idx} components={markdownComponents}>
                  {part.text}
                </ReactMarkdown>
              ) : (
                <span key={idx} />
              )
            ) : (
              <div
                key={idx}
                className="overflow-x-auto my-3 [&_table]:text-sm [&_table]:min-w-max"
                dangerouslySetInnerHTML={{ __html: part.html }}
              />
            )
          )}
        </div>
      );
    }

    return (
      <div className="[&_ul]:list-disc [&_ul]:list-inside [&_ol]:list-decimal [&_ol]:list-inside [&_*]:my-0.5">
        <ReactMarkdown components={markdownComponents}>{processedContent}</ReactMarkdown>
      </div>
    );
  }

  return (
    <>
      {regularTables.map((item: { table: ParsedTable; before: string; after: string }, idx: number) => (
        <div key={idx}>
          {item.before && (
            <div className="[&_ul]:list-disc [&_ul]:list-inside [&_ol]:list-decimal [&_ol]:list-inside [&_*]:my-0.5">
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="my-1">{children}</p>,
                  ul: ({ children }) => <ul className="list-disc list-inside my-1">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside my-1">{children}</ol>,
                  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
blockquote: ({ children }) => (
                    <blockquote className="pl-4 my-1 text-text-secondary [&+blockquote]:mt-0">
                      {children}
                    </blockquote>
                  ),
                    code: ({ children }) => (
                      <code className="px-1 py-0.5 rounded bg-gray-100 text-sm">{children}</code>
                    ),
                }}
              >
                {item.before}
              </ReactMarkdown>
            </div>
          )}
          <TableRenderer table={item.table} beforeContent={item.before} />
          {item.after && (
            <div className="[&_ul]:list-disc [&_ul]:list-inside [&_ol]:list-decimal [&_ol]:list-inside [&_*]:my-0.5">
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="my-1">{children}</p>,
                  ul: ({ children }) => <ul className="list-disc list-inside my-1">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside my-1">{children}</ol>,
                  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
blockquote: ({ children }) => (
                <blockquote className="pl-4 my-1 text-text-secondary [&+blockquote]:mt-0">
                  {children}
                </blockquote>
              ),
                  code: ({ children }) => (
                    <code className="px-1 py-0.5 rounded bg-gray-100 text-sm">{children}</code>
                  ),
                }}
              >
                {item.after}
              </ReactMarkdown>
            </div>
          )}
        </div>
      ))}
    </>
  );
}

/** Markdown 消息内容：支持 SPINNER 占位符与流式光标 */
function MarkdownMessageContent({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  const parts = content.split(SPINNER_REGEX);
  return (
    <>
      {parts.map((part, i, arr) => (
        <span key={i}>
          <ContentWithTables content={part} />
          {i < arr.length - 1 && (
            <span className="inline-flex gap-1 ml-0.5 align-middle">
              <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
              <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
              <span className="loading-dot w-1.5 h-1.5 bg-blue-500 rounded-full inline-block" />
            </span>
          )}
        </span>
      ))}
      {isStreaming && (
        <span className="streaming-cursor inline-block w-0.5 h-4 bg-blue-500 ml-0.5 align-middle animate-pulse" />
      )}
    </>
  );
}

/** AI 消息 */
function AssistantMessage({ message, onFormSubmit, isStreaming = false }: { message: Message; onFormSubmit?: (formData: Record<string, unknown>) => void; isStreaming?: boolean }) {
  const formRef = useRef<HTMLDivElement>(null);
  const isHtmlForm = message.content.includes('<form');
  // 表格消息也走 Markdown 渲染管线（ContentWithTables）以支持表格外文本的 Markdown
  const isHtmlContent = isHtmlForm;
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
          {isHtmlContent ? (
            <div
              ref={formRef}
              className={isHtmlForm ? "auth-form-wrapper" : "html-content-wrapper text-sm text-text-primary leading-relaxed"}
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
            <MarkdownMessageContent
              content={stripSaveRuleTag(message.content)}
              isStreaming={isStreaming}
            />
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
