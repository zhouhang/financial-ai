import type { MessageAttachment, UserTaskRule } from '../types';

interface BuildConversationTitleArgs {
  text: string;
  attachments?: MessageAttachment[];
  taskContext?: Pick<UserTaskRule, 'task_type' | 'task_name' | 'name'> | null;
  date: Date;
}

function padDatePart(value: number): string {
  return String(value).padStart(2, '0');
}

export function formatConversationTitleDate(date: Date): string {
  const year = date.getFullYear();
  const month = padDatePart(date.getMonth() + 1);
  const day = padDatePart(date.getDate());

  return `${year}-${month}-${day}`;
}

function normalizeRuleName(taskContext: BuildConversationTitleArgs['taskContext']): string {
  const ruleName = taskContext?.name?.trim();
  if (ruleName) return ruleName;

  const taskName = taskContext?.task_name?.trim();
  if (taskName) return taskName;

  return '当前规则';
}

function buildNormalChatTitle(text: string): string {
  const normalized = text.trim();
  if (!normalized) return '新对话';

  return normalized.slice(0, 20) + (normalized.length > 20 ? '...' : '');
}

export function buildConversationTitle({
  text,
  attachments = [],
  taskContext = null,
  date,
}: BuildConversationTitleArgs): string {
  const taskType = taskContext?.task_type;
  const ruleName = normalizeRuleName(taskContext);
  const formattedDate = formatConversationTitleDate(date);

  if (taskType === 'recon') {
    return `数据对账 · ${ruleName} · ${formattedDate}`;
  }

  if (taskType === 'proc') {
    if (attachments.length > 0) {
      return `数据整理 · ${ruleName} · ${attachments.length}个文件`;
    }

    return `数据整理 · ${ruleName} · ${formattedDate}`;
  }

  return buildNormalChatTitle(text);
}
