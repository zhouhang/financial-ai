import { useState, useEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import {
  Cpu,
  Database,
  FileSpreadsheet,
  Globe,
  LogOut,
  MessageSquare,
  MonitorSmartphone,
  ChevronDown,
  ChevronRight,
  Store,
  Trash2,
  User,
  Zap,
  Moon,
  SunMedium,
  ShieldCheck,
} from 'lucide-react';
import { COLLABORATION_CHANNEL_CARDS } from '../collaborationChannelConfig';
import { SOURCE_TYPE_CARDS } from '../dataSourceConfig';
import { getThemeMode, subscribeTheme, toggleTheme } from '../theme';
import { ruleSupportsEntryMode } from '../utils/ruleEntryModes';
import type {
  AppSection,
  CollaborationProvider,
  ConnectionStatus,
  Conversation,
  DataConnectionView,
  DataSourceKind,
  ReconWorkspaceMode,
  UserTask,
  UserTaskRule,
} from '../types';
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

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  activeSection?: AppSection;
  connectionStatus: ConnectionStatus;
  onNewConversation: () => void;
  onSelectSection?: (section: AppSection) => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation?: (id: string) => void;
  currentUser?: Record<string, unknown> | null;
  onLogout?: () => void;
  collapsed?: boolean;
  onSelectRule?: (rule: UserTaskRule) => void;
  onOpenTask?: (task: UserTask) => void;
  selectedRuleCode?: string | null;
  authToken?: string | null;
  selectedDataConnectionView?: DataConnectionView;
  onSelectDataConnectionView?: (view: DataConnectionView) => void;
  selectedDataSourceKind?: DataSourceKind;
  onSelectDataSourceKind?: (kind: DataSourceKind) => void;
  selectedCollaborationProvider?: CollaborationProvider;
  onSelectCollaborationProvider?: (provider: CollaborationProvider) => void;
  selectedReconEntry?: ReconWorkspaceMode;
  onSelectReconEntry?: (entry: ReconWorkspaceMode) => void;
  rulesVersion?: number;
}

function sourceKindIcon(kind: DataSourceKind) {
  if (kind === 'platform_oauth') return <Store className="h-4 w-4" />;
  if (kind === 'database') return <Database className="h-4 w-4" />;
  if (kind === 'api') return <Globe className="h-4 w-4" />;
  if (kind === 'file') return <FileSpreadsheet className="h-4 w-4" />;
  if (kind === 'browser') return <MonitorSmartphone className="h-4 w-4" />;
  return <Cpu className="h-4 w-4" />;
}

function collaborationProviderIcon(provider: CollaborationProvider) {
  if (provider === 'dingtalk_dws') return <MessageSquare className="h-4 w-4" />;
  if (provider === 'feishu') return <Globe className="h-4 w-4" />;
  if (provider === 'wechat_work') return <ShieldCheck className="h-4 w-4" />;
  return <MessageSquare className="h-4 w-4" />;
}

export default function Sidebar({
  conversations,
  activeConversationId,
  activeSection = 'chat',
  onNewConversation,
  onSelectSection,
  onSelectConversation,
  onDeleteConversation,
  currentUser,
  onLogout,
  collapsed = false,
  onSelectRule,
  selectedRuleCode,
  authToken,
  selectedDataConnectionView = 'data_sources',
  onSelectDataConnectionView,
  selectedDataSourceKind = 'platform_oauth',
  onSelectDataSourceKind,
  selectedCollaborationProvider = 'dingtalk_dws',
  onSelectCollaborationProvider,
  selectedReconEntry = 'upload',
  onSelectReconEntry,
  rulesVersion,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<UserTask[]>([]);
  const [manualProcMenuExpanded, setManualProcMenuExpanded] = useState<boolean | null>(null);
  const [manualReconMenuExpanded, setManualReconMenuExpanded] = useState<boolean | null>(null);
  const [userConnectionGroups, setUserConnectionGroups] = useState<DataConnectionView[]>([
    selectedDataConnectionView,
  ]);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const themeMode = useSyncExternalStore(subscribeTheme, getThemeMode, getThemeMode);
  const displayName = typeof currentUser?.username === 'string' && currentUser.username
    ? currentUser.username
    : '用户';

  useEffect(() => {
    if (!isProfileMenuOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!profileMenuRef.current?.contains(event.target as Node)) {
        setIsProfileMenuOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsProfileMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isProfileMenuOpen]);

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
        }
      } catch (error) {
        console.error('加载任务列表失败:', error);
      }
    };

    fetchTasks();
  }, [authToken, selectedRuleCode, rulesVersion]);

  const normalizeRuleFromTask = (task: UserTask, rule: UserTaskRule): UserTaskRule => {
    return {
      ...rule,
      task_code: rule.task_code || task.task_code,
      task_name: rule.task_name || task.task_name,
      task_type: rule.task_type || task.task_type,
    };
  };

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('确定要删除这个会话吗？')) {
      onDeleteConversation?.(id);
    }
  };

  const toggleConnectionGroup = (view: DataConnectionView) => {
    setUserConnectionGroups((prev) =>
      prev.includes(view) ? prev.filter((item) => item !== view) : [...prev, view],
    );
    onSelectDataConnectionView?.(view);
  };

  const dataSourceGroupPreview = `${SOURCE_TYPE_CARDS.length} 个数据源`;
  const collaborationGroupPreview = COLLABORATION_CHANNEL_CARDS.map((card) => card.title).join('、');
  const visibleTasks = authToken ? tasks : [];
  const procTasks = visibleTasks.filter((task) => task.task_type === 'proc');
  const reconTasks = visibleTasks.filter((task) => task.task_type === 'recon');
  const procRules = procTasks.flatMap((task) =>
    (task.rules || []).map((rule) => normalizeRuleFromTask(task, rule)),
  );
  const reconRules = reconTasks.flatMap((task) =>
    (task.rules || []).map((rule) => normalizeRuleFromTask(task, rule)),
  );
  const uploadProcRules = procRules.filter((rule) => ruleSupportsEntryMode(rule, 'upload'));
  const uploadReconRules = reconRules.filter((rule) => ruleSupportsEntryMode(rule, 'upload'));
  const isReconCenterActive = selectedReconEntry === 'center';
  const selectedProcRule = isReconCenterActive
    ? null
    : uploadProcRules.find((rule) => rule.rule_code === selectedRuleCode) || null;
  const selectedReconRule =
    selectedReconEntry === 'upload'
      ? uploadReconRules.find((rule) => rule.rule_code === selectedRuleCode) || null
      : null;
  const selectedProcRuleCode = selectedProcRule?.rule_code || null;
  const reconAutoOpenKey = selectedReconEntry === 'center'
    ? 'center'
    : selectedReconRule?.rule_code || null;
  const isProcMenuExpanded = Boolean(authToken) && (manualProcMenuExpanded ?? Boolean(selectedProcRuleCode));
  const isReconMenuExpanded = Boolean(authToken) && (manualReconMenuExpanded ?? Boolean(reconAutoOpenKey));
  const expandedConnectionGroups = useMemo(() => {
    const groups = new Set<DataConnectionView>(userConnectionGroups);
    groups.add(selectedDataConnectionView);
    return Array.from(groups);
  }, [selectedDataConnectionView, userConnectionGroups]);
  const isConnectionGroupExpanded = (view: DataConnectionView) => expandedConnectionGroups.includes(view);

  const handleOpenProcUpload = () => {
    if (uploadProcRules[0]) {
      onSelectRule?.(uploadProcRules[0]);
    }
  };

  const handleProfileMenuToggle = () => {
    setIsProfileMenuOpen((prev) => !prev);
  };

  const handleLogoutClick = () => {
    setIsProfileMenuOpen(false);
    if (confirm('确认退出登录？')) {
      onLogout?.();
    }
  };

  const profileMenuItems = onLogout
    ? [
        {
          key: 'logout',
          label: '退出登录',
          icon: LogOut,
          onClick: handleLogoutClick,
        },
      ]
    : [];

  return (
    <aside
      className={`sticky top-0 self-start bg-surface flex flex-col h-screen shrink-0 border-r border-border transition-all duration-200 overflow-hidden ${
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
          className={`sidebar-primary-cta w-full flex items-center justify-center py-3 rounded-xl text-white font-medium text-sm cursor-pointer ${collapsed ? 'px-0' : 'gap-2'}`}
          title={collapsed ? '开启新对话' : undefined}
        >
          <Zap className="w-4 h-4 shrink-0" />
          {!collapsed && <span>开启新对话</span>}
        </button>
      </div>

      {!collapsed && authToken && (
        <div className="px-4 mb-3">
          <div className={`grid gap-2 rounded-xl border border-border bg-surface-secondary p-1 ${authToken ? 'grid-cols-2' : 'grid-cols-1'}`}>
            <button
              type="button"
              onClick={() => onSelectSection?.('chat')}
              className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium transition-colors ${
                activeSection === 'chat'
                  ? 'bg-surface text-blue-600 shadow-sm'
                  : 'text-text-secondary hover:bg-surface-tertiary'
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              对话
            </button>
            {authToken && (
              <button
                type="button"
                onClick={() => onSelectSection?.('data-connections')}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium transition-colors ${
                  activeSection === 'data-connections'
                    ? 'bg-surface text-blue-600 shadow-sm'
                    : 'text-text-secondary hover:bg-surface-tertiary'
                }`}
              >
                <Database className="h-3.5 w-3.5" />
                数据连接
              </button>
            )}
          </div>
        </div>
      )}

      {collapsed && authToken && (
        <div className="px-2 mb-3 space-y-1">
          <button
            type="button"
            onClick={() => onSelectSection?.('chat')}
            className={`w-full flex items-center justify-center py-2.5 rounded-lg transition-colors ${
              activeSection === 'chat'
                ? 'bg-blue-50 text-blue-600'
                : 'text-text-secondary hover:bg-surface-tertiary'
            }`}
            title="对话"
          >
            <MessageSquare className="h-4 w-4" />
          </button>
          {authToken && (
            <button
              type="button"
              onClick={() => onSelectSection?.('data-connections')}
              className={`w-full flex items-center justify-center py-2.5 rounded-lg transition-colors ${
                activeSection === 'data-connections'
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-text-secondary hover:bg-surface-tertiary'
              }`}
              title="数据连接"
            >
              <Database className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {!collapsed && activeSection === 'chat' && !!authToken && (
        <div className="px-4 mb-3">
          <div className="mb-2 px-0.5">
            <p className="text-[11px] font-semibold tracking-[0.12em] text-text-muted">选择任务</p>
          </div>
          <div className="space-y-2.5">
            <div
              className="rounded-2xl border border-[rgba(59,130,246,0.18)] bg-[rgba(59,130,246,0.08)] p-1.5 transition-all duration-200 hover:border-white/70 hover:shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_10px_24px_rgba(15,23,42,0.14)]"
              title="数据整理"
            >
              <button
                type="button"
                onClick={() => setManualProcMenuExpanded((prev) => !(prev ?? Boolean(selectedProcRuleCode)))}
                className={`w-full flex items-center gap-2.5 rounded-[14px] px-3 py-2.5 text-left transition-all duration-200 ${
                  isProcMenuExpanded
                    ? 'bg-surface-elevated text-text-primary shadow-sm ring-1 ring-white/80'
                    : 'text-text-secondary hover:bg-surface-elevated hover:ring-1 hover:ring-white/55'
                }`}
              >
                <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-blue-500" />
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-sm font-semibold leading-5 text-text-primary">
                    数据整理
                  </span>
                </span>
                <ChevronRight
                  className={`h-4 w-4 shrink-0 text-text-muted transition-transform duration-200 ${
                    isProcMenuExpanded ? 'rotate-90 text-text-secondary' : ''
                  }`}
                />
              </button>
              {isProcMenuExpanded && (
                <div className="mt-1.5 space-y-1 rounded-[14px] border border-border-subtle bg-surface-elevated p-1.5">
                  <button
                    type="button"
                    onClick={handleOpenProcUpload}
                    className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-sm transition-colors ${
                      selectedProcRule
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-text-secondary hover:bg-surface-secondary'
                    }`}
                  >
                    <span>上传文件整理</span>
                    <ChevronRight className="h-4 w-4 shrink-0" />
                  </button>
                </div>
              )}
            </div>

            <div
              className="rounded-2xl border border-[rgba(14,165,233,0.18)] bg-[rgba(14,165,233,0.08)] p-1.5 transition-all duration-200 hover:border-white/70 hover:shadow-[0_0_0_1px_rgba(255,255,255,0.28),0_10px_24px_rgba(15,23,42,0.14)]"
              title="数据对账"
            >
              <button
                type="button"
                onClick={() => setManualReconMenuExpanded((prev) => !(prev ?? Boolean(reconAutoOpenKey)))}
                className={`w-full flex items-center gap-2.5 rounded-[14px] px-3 py-2.5 text-left transition-all duration-200 ${
                  isReconMenuExpanded
                    ? 'bg-surface-elevated text-text-primary shadow-sm ring-1 ring-white/80'
                    : 'text-text-secondary hover:bg-surface-elevated hover:ring-1 hover:ring-white/55'
                }`}
              >
                <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-sky-500" />
                <span className="min-w-0 flex-1 text-sm font-semibold text-text-primary">数据对账</span>
                <ChevronRight
                  className={`h-4 w-4 shrink-0 text-text-muted transition-transform duration-200 ${
                    isReconMenuExpanded ? 'rotate-90 text-text-secondary' : ''
                  }`}
                />
              </button>
              {isReconMenuExpanded && (
                <div className="mt-1.5 space-y-1 rounded-[14px] border border-border-subtle bg-surface-elevated p-1.5">
                  <button
                    type="button"
                    onClick={() => onSelectReconEntry?.('upload')}
                    className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-sm transition-colors ${
                      selectedReconEntry === 'upload' && selectedReconRule
                        ? 'bg-sky-50 text-sky-700'
                        : 'text-text-secondary hover:bg-surface-secondary'
                    }`}
                  >
                    <span>上传文件对账</span>
                    <ChevronRight className="h-4 w-4 shrink-0" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectReconEntry?.('center')}
                    className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-sm transition-colors ${
                      selectedReconEntry === 'center'
                        ? 'bg-sky-50 text-sky-700'
                        : 'text-text-secondary hover:bg-surface-secondary'
                    }`}
                  >
                    <span>对账中心</span>
                    <ChevronRight className="h-4 w-4 shrink-0" />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className={`flex-1 overflow-y-auto ${collapsed ? 'px-2' : 'px-4'}`}>
        {!collapsed && activeSection === 'chat' && (
          <p className="text-text-secondary text-xs font-medium mb-2">历史对话</p>
        )}
        {activeSection === 'chat' ? (
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
        ) : (
          <div className="space-y-2">
            {!collapsed ? (
              <>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <button
                      type="button"
                      onClick={() => toggleConnectionGroup('data_sources')}
                      className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
                        selectedDataConnectionView === 'data_sources'
                          ? 'bg-surface-secondary text-blue-600'
                          : 'text-text-secondary hover:bg-surface-secondary'
                      }`}
                    >
                      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-surface-accent text-blue-600">
                        <Database className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-text-primary">数据源</span>
                        <span className="block truncate text-xs text-text-secondary">{dataSourceGroupPreview}</span>
                      </span>
                      {isConnectionGroupExpanded('data_sources') ? (
                        <ChevronDown className="h-4 w-4 shrink-0 text-text-muted" />
                      ) : (
                        <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
                      )}
                    </button>
                    {isConnectionGroupExpanded('data_sources') && (
                      <div className="ml-4 space-y-1.5 border-l border-border-subtle pl-3">
                        {SOURCE_TYPE_CARDS.map((card) => {
                          const isActive = selectedDataSourceKind === card.source_kind;
                          return (
                            <button
                              key={card.source_kind}
                              type="button"
                              onClick={() => {
                                onSelectDataConnectionView?.('data_sources');
                                onSelectDataSourceKind?.(card.source_kind);
                              }}
                              className={`flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                                isActive
                                  ? 'border-blue-200 bg-blue-50 text-blue-600 shadow-sm'
                                  : 'border-transparent bg-surface text-text-secondary hover:border-border-subtle hover:bg-surface-secondary'
                              }`}
                            >
                              {sourceKindIcon(card.source_kind)}
                              <span>{card.title}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div className="space-y-1">
                    <button
                      type="button"
                      onClick={() => toggleConnectionGroup('collaboration_channels')}
                      className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
                        selectedDataConnectionView === 'collaboration_channels'
                          ? 'bg-surface-secondary text-blue-600'
                          : 'text-text-secondary hover:bg-surface-secondary'
                      }`}
                    >
                      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-surface-accent text-blue-600">
                        <MessageSquare className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-text-primary">协作通道</span>
                        <span className="block truncate text-xs text-text-secondary">{collaborationGroupPreview}</span>
                      </span>
                      {isConnectionGroupExpanded('collaboration_channels') ? (
                        <ChevronDown className="h-4 w-4 shrink-0 text-text-muted" />
                      ) : (
                        <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
                      )}
                    </button>
                    {isConnectionGroupExpanded('collaboration_channels') && (
                      <div className="ml-4 space-y-1.5 border-l border-border-subtle pl-3">
                        {COLLABORATION_CHANNEL_CARDS.map((card) => {
                          const isActive = selectedCollaborationProvider === card.provider;
                          return (
                            <button
                              key={card.provider}
                              type="button"
                              onClick={() => {
                                onSelectDataConnectionView?.('collaboration_channels');
                                onSelectCollaborationProvider?.(card.provider);
                              }}
                              className={`flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                                isActive
                                  ? 'border-blue-200 bg-blue-50 text-blue-600 shadow-sm'
                                  : 'border-transparent bg-surface text-text-secondary hover:border-border-subtle hover:bg-surface-secondary'
                              }`}
                            >
                              {collaborationProviderIcon(card.provider)}
                              <span>{card.title}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="space-y-1">
                  <button
                    type="button"
                    onClick={() => onSelectDataConnectionView?.('data_sources')}
                    className={`w-full flex items-center justify-center py-2.5 rounded-lg transition-colors ${
                      selectedDataConnectionView === 'data_sources'
                        ? 'bg-blue-50 text-blue-600'
                        : 'text-text-secondary hover:bg-surface-tertiary'
                    }`}
                    title="数据源连接"
                  >
                    <Database className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectDataConnectionView?.('collaboration_channels')}
                    className={`w-full flex items-center justify-center py-2.5 rounded-lg transition-colors ${
                      selectedDataConnectionView === 'collaboration_channels'
                        ? 'bg-blue-50 text-blue-600'
                        : 'text-text-secondary hover:bg-surface-tertiary'
                    }`}
                    title="协作通道连接"
                  >
                    <MessageSquare className="h-4 w-4" />
                  </button>
                </div>
                {(selectedDataConnectionView === 'data_sources' ? SOURCE_TYPE_CARDS : COLLABORATION_CHANNEL_CARDS).map((card) => {
                  const isSourceCard = 'source_kind' in card;
                  const isActive = isSourceCard
                    ? selectedDataSourceKind === card.source_kind
                    : selectedCollaborationProvider === card.provider;
                  return (
                    <button
                      key={isSourceCard ? card.source_kind : card.provider}
                      type="button"
                      onClick={() =>
                        isSourceCard
                          ? onSelectDataSourceKind?.(card.source_kind)
                          : onSelectCollaborationProvider?.(card.provider)
                      }
                      className={`w-full flex items-center justify-center py-2.5 rounded-lg transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-600'
                          : 'text-text-secondary hover:bg-surface-tertiary'
                      }`}
                      title={card.title}
                    >
                      {isSourceCard ? sourceKindIcon(card.source_kind) : collaborationProviderIcon(card.provider)}
                    </button>
                  );
                })}
              </>
            )}
          </div>
        )}
      </div>

      <div className={`py-2 border-t border-border-subtle ${collapsed ? 'px-2' : 'px-4'}`}>
        <div className={`flex items-center gap-1.5 ${currentUser ? 'justify-between' : 'justify-end'}`}>
          {currentUser && (
            <div ref={profileMenuRef} className="relative min-w-0">
              <button
                type="button"
                onClick={handleProfileMenuToggle}
                className={`group flex items-center border border-transparent transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(59,130,246,0.18)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${
                  collapsed
                    ? 'justify-center h-8 w-8 rounded-lg hover:bg-surface-secondary'
                    : 'gap-2 px-1.5 py-0.5 rounded-lg hover:bg-surface-secondary'
                }`}
                title={displayName}
                aria-label="用户菜单"
                aria-expanded={isProfileMenuOpen}
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                  <User className="h-3 w-3" />
                </span>
                {!collapsed && (
                  <>
                    <span className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-text-primary">
                      {displayName}
                    </span>
                    <ChevronRight className="h-3 w-3 shrink-0 text-text-muted transition-colors group-hover:text-text-secondary" />
                  </>
                )}
              </button>

              {isProfileMenuOpen && profileMenuItems.length > 0 && (
                <div
                  className={`absolute bottom-full z-20 mb-1.5 rounded-xl border border-border bg-surface-elevated p-0.5 shadow-[0_14px_30px_rgba(15,23,42,0.12)] ${
                    collapsed ? 'left-1/2 -translate-x-1/2 w-36' : 'left-0 w-36'
                  }`}
                >
                  {profileMenuItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={item.onClick}
                        className="flex w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-left text-sm font-medium text-text-primary hover:bg-surface-secondary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(59,130,246,0.18)]"
                      >
                        <Icon className="h-3 w-3 shrink-0" />
                        <span>{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={() => toggleTheme()}
            className="h-6 w-6 rounded-md border border-border bg-surface-elevated text-text-secondary hover:bg-surface-tertiary hover:text-text-primary transition-colors flex items-center justify-center shrink-0"
            title={themeMode === 'light' ? '切换到深色模式' : '切换到浅色模式'}
            aria-label={themeMode === 'light' ? '切换到深色模式' : '切换到浅色模式'}
          >
            {themeMode === 'light' ? <Moon className="w-3 h-3" /> : <SunMedium className="w-3 h-3" />}
          </button>
        </div>
      </div>
    </aside>
  );
}
