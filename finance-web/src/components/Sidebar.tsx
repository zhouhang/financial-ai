import { useState, useEffect } from 'react';
import {
  LogOut,
  MessageSquare,
  ChevronRight,
  Trash2,
  User,
  Zap,
} from 'lucide-react';
import type { ConnectionStatus, Conversation, UserTask, UserTaskRule } from '../types';
import BrandMark from './BrandMark';

/** 历史对话时间格式化：今天→时间，昨天→昨天，2-7天→过去7天，8-30天→过去30天，1月-1年→月份，1年+→年份 */
function formatConversationTime(date: Date | string): string {
  const d = new Date(date);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dateStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.floor((todayStart.getTime() - dateStart.getTime()) / (24 * 60 * 60 * 1000));

  if (diffDays === 0) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  if (diffDays === 1) {
    return '昨天';
  }
  if (diffDays >= 2 && diffDays <= 7) {
    return '过去7天';
  }
  if (diffDays >= 8 && diffDays <= 30) {
    return '过去30天';
  }
  if (diffDays <= 365) {
    return d.toLocaleDateString('zh-CN', { month: 'long', year: 'numeric' });
  }
  return d.toLocaleDateString('zh-CN', { year: 'numeric' });
}

function getTaskTypeMeta(taskType: string): {
  dotClass: string;
  badgeClass: string;
  panelClass: string;
} {
  switch (taskType) {
    case 'proc':
      return {
        dotClass: 'bg-blue-500',
        badgeClass: 'bg-[rgba(59,130,246,0.12)] text-blue-600',
        panelClass: 'border-[rgba(59,130,246,0.18)] bg-[rgba(59,130,246,0.08)]',
      };
    case 'recon':
      return {
        dotClass: 'bg-sky-500',
        badgeClass: 'bg-[rgba(14,165,233,0.12)] text-sky-600',
        panelClass: 'border-[rgba(14,165,233,0.18)] bg-[rgba(14,165,233,0.08)]',
      };
    default:
      return {
        dotClass: 'bg-blue-500',
        badgeClass: 'bg-[rgba(59,130,246,0.12)] text-blue-600',
        panelClass: 'border-border bg-surface-tertiary',
      };
  }
}

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  connectionStatus: ConnectionStatus;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation?: (id: string) => void;
  currentUser?: Record<string, unknown> | null;
  onLogout?: () => void;
  collapsed?: boolean;
  onSelectRule?: (rule: UserTaskRule) => void;
  selectedRuleCode?: string | null;
  authToken?: string | null;
}

export default function Sidebar({
  conversations,
  activeConversationId,
  connectionStatus,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
  currentUser,
  onLogout,
  collapsed = false,
  onSelectRule,
  selectedRuleCode,
  authToken,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<UserTask[]>([]);
  const [expandedTaskCodes, setExpandedTaskCodes] = useState<string[]>([]);

  useEffect(() => {
    if (authToken) return;
    setTasks([]);
    setExpandedTaskCodes([]);
  }, [authToken]);

  useEffect(() => {
    if (!authToken) return;

    const fetchTasks = async () => {
      try {
        const response = await fetch('/api/proc/list_user_tasks', {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const data = await response.json();
        if (data.success && data.tasks) {
          setTasks(data.tasks);
          setExpandedTaskCodes((prev) => {
            if (prev.length > 0) return prev;
            if (!selectedRuleCode) return [];

            const activeTask = data.tasks.find((task: UserTask) =>
              task.rules?.some((rule) => rule.rule_code === selectedRuleCode)
            );
            return activeTask ? [activeTask.task_code] : [];
          });
        }
      } catch (error) {
        console.error('加载任务列表失败:', error);
      }
    };

    fetchTasks();
  }, [authToken, selectedRuleCode]);

  const handleRuleClick = (rule: UserTaskRule) => {
    onSelectRule?.(rule);
  };

  const handleToggleTask = (taskCode: string) => {
    setExpandedTaskCodes((prev) =>
      prev.includes(taskCode)
        ? prev.filter((code) => code !== taskCode)
        : [...prev, taskCode]
    );
  };

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('确定要删除这个会话吗？')) {
      onDeleteConversation?.(id);
    }
  };

  return (
    <aside
      className={`relative bg-surface flex flex-col h-full shrink-0 border-r border-border transition-all duration-200 overflow-hidden ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      <div className={`pt-5 pb-4 flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3 px-4'}`}>
        <BrandMark className="h-11 w-11 shrink-0" />
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <h1 className="text-text-primary font-semibold text-base leading-tight">Tally</h1>
            <p className="text-text-secondary text-xs">智能财务助手</p>
          </div>
        )}
      </div>

      <div className={`mb-3 ${collapsed ? 'px-2' : 'px-4'}`}>
        <button
          onClick={onNewConversation}
          className={`w-full flex items-center justify-center py-3 rounded-xl
            bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium text-sm
            hover:shadow-lg hover:shadow-blue-500/30 transition-all cursor-pointer ${collapsed ? 'px-0' : 'gap-2'}`}
          title={collapsed ? '开启新对话' : undefined}
        >
          <Zap className="w-4 h-4 shrink-0" />
          {!collapsed && <span>开启新对话</span>}
        </button>
      </div>

      {!collapsed && !!authToken && tasks.length > 0 && (
        <div className="px-4 mb-3">
          <div className="mb-2 px-0.5">
            <p className="text-[11px] font-semibold tracking-[0.12em] text-text-muted">选择任务</p>
          </div>
          <div className="space-y-2.5">
            {tasks.map((task) => {
              const isExpanded = expandedTaskCodes.includes(task.task_code);
              const isTaskActive = task.rules?.some((rule) => rule.rule_code === selectedRuleCode);
              const ruleCount = task.rules?.length ?? 0;
              const taskMeta = getTaskTypeMeta(task.task_type);

              return (
                <div
                  key={task.task_code}
                  className={`rounded-2xl border p-1.5 transition-all duration-200 ${
                    taskMeta.panelClass
                  } ${
                    isTaskActive
                      ? 'hover:border-white/80 hover:shadow-[0_0_0_1px_rgba(255,255,255,0.42),0_12px_28px_rgba(15,23,42,0.18)]'
                      : 'hover:border-white/70 hover:shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_10px_24px_rgba(15,23,42,0.14)]'
                  }`}
                  title={task.description || task.task_name}
                >
                  <button
                    type="button"
                    onClick={() => handleToggleTask(task.task_code)}
                    className={`w-full flex items-center gap-2.5 rounded-[14px] px-3 py-2.5 text-left transition-all duration-200 ${
                      isExpanded
                        ? 'bg-surface-elevated text-text-primary'
                        : 'text-text-secondary hover:bg-surface-elevated'
                    } ${
                      isTaskActive
                        ? 'shadow-sm ring-1 ring-white/80'
                        : 'hover:ring-1 hover:ring-white/55'
                    }`}
                    title={task.description || task.task_name}
                  >
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${taskMeta.dotClass}`} />
                    <span className="min-w-0 flex-1 text-left">
                      <span className="block truncate text-sm font-semibold leading-5">
                        {task.task_name}
                      </span>
                    </span>
                    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${taskMeta.badgeClass}`}>
                      {ruleCount}
                    </span>
                    <ChevronRight
                      className={`h-4 w-4 shrink-0 text-text-muted transition-transform duration-200 ${
                        isExpanded ? 'rotate-90 text-text-secondary' : ''
                      }`}
                    />
                  </button>
                  {isExpanded && task.rules && task.rules.length > 0 && (
                    <div className="mt-1.5 space-y-1 rounded-[14px] border border-border-subtle bg-surface-elevated p-1.5">
                      {task.rules.map((rule) => {
                        const isSelected = selectedRuleCode === rule.rule_code;

                        return (
                          <button
                            key={rule.rule_code}
                            type="button"
                            className={`group flex w-full items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition-all duration-200 ${
                              isSelected
                                ? 'border-[rgba(59,130,246,0.18)] bg-surface-accent text-blue-600 shadow-sm'
                                : 'border-transparent bg-transparent text-text-secondary hover:border-border-subtle hover:bg-surface-tertiary hover:text-text-primary'
                            }`}
                            onClick={() => handleRuleClick(rule)}
                            title={rule.name}
                          >
                            <span
                              className={`h-1.5 w-1.5 shrink-0 rounded-full transition-colors ${
                                isSelected ? 'bg-blue-500' : 'bg-slate-300 group-hover:bg-blue-300'
                              }`}
                            />
                            <span className="min-w-0 flex-1 truncate text-sm font-medium">
                              {rule.name}
                            </span>
                            {isSelected && (
                              <span className="shrink-0 text-[11px] font-medium text-blue-500">
                                当前
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className={`flex-1 overflow-y-auto ${collapsed ? 'px-2' : 'px-4'}`}>
        {!collapsed && (
          <p className="text-text-secondary text-xs font-medium mb-2">历史对话</p>
        )}
        <div className="space-y-1">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`relative flex items-center rounded-lg transition-all cursor-pointer ${
                collapsed ? 'justify-center px-2 py-2.5' : 'items-start gap-2.5 px-3 py-2.5'
              } ${
                activeConversationId === conv.id
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-text-secondary hover:bg-surface-tertiary'
              }`}
              onClick={() => onSelectConversation(conv.id)}
              onMouseEnter={() => setHoveredId(conv.id)}
              onMouseLeave={() => setHoveredId(null)}
              title={collapsed ? conv.title : undefined}
            >
              <MessageSquare className="w-4 h-4 shrink-0 mt-0.5" />
              {!collapsed && (
                <div className="flex-1 min-w-0">
                  <span className="block truncate text-sm font-medium">{conv.title}</span>
                  <span className="block text-xs text-text-muted mt-0.5">
                    {formatConversationTime(conv.updatedAt)}
                  </span>
                </div>
              )}
              {!collapsed && hoveredId === conv.id && onDeleteConversation && (
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-text-muted hover:text-red-500 hover:bg-red-50 transition-colors"
                  title="删除会话"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className={`py-4 border-t border-border-subtle ${collapsed ? 'px-2' : 'px-4'}`}>
        {currentUser && !collapsed && (
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-blue-600" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">
                  {currentUser.username as string}
                </p>
                {typeof currentUser.company_name === 'string' && currentUser.company_name && (
                  <p className="text-xs text-text-muted truncate">{currentUser.company_name}</p>
                )}
              </div>
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                className="p-1.5 rounded-lg text-text-muted hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
                title="退出登录"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
        )}
        {currentUser && collapsed && (
          <div className="flex justify-center mb-2">
            <div
              className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center"
              title={currentUser.username as string}
            >
              <User className="w-4 h-4 text-blue-600" />
            </div>
          </div>
        )}
        <div className={`flex items-center gap-2 ${collapsed ? 'justify-center' : ''}`}>
          <div
            className={`w-2 h-2 rounded-full shrink-0 ${
              connectionStatus === 'connected'
                ? 'bg-green-500'
                : connectionStatus === 'connecting'
                ? 'bg-yellow-500 animate-pulse'
                : 'bg-red-500'
            }`}
          />
          {!collapsed && (
            <span className="text-xs text-text-secondary">
              {connectionStatus === 'connected'
                ? '已连接'
                : connectionStatus === 'connecting'
                ? '连接中'
                : '已断开'}
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}
