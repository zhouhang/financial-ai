import { useState } from 'react';
import {
  BarChart3,
  LogOut,
  MessageSquare,
  Trash2,
  User,
  Zap,
} from 'lucide-react';
import type { ConnectionStatus, Conversation } from '../types';

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
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation(); // 防止触发选择会话
    if (confirm('确定要删除这个会话吗？')) {
      onDeleteConversation?.(id);
    }
  };
  return (
    <aside
      className={`relative bg-white flex flex-col h-full shrink-0 border-r border-gray-200 transition-all duration-200 overflow-hidden ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* ── Brand ── */}
      <div className={`pt-5 pb-4 flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3 px-4'}`}>
        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shrink-0">
          <BarChart3 className="w-6 h-6 text-white" />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <h1 className="text-gray-900 font-semibold text-base leading-tight">Tally</h1>
            <p className="text-gray-500 text-xs">智能财务助手</p>
          </div>
        )}
      </div>

      {/* ── New Analysis Button ── */}
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

      {/* ── Conversation List ── */}
      <div className={`flex-1 overflow-y-auto ${collapsed ? 'px-2' : 'px-4'}`}>
        {!collapsed && (
          <p className="text-gray-500 text-xs font-medium mb-2">历史对话</p>
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
                  : 'text-gray-600 hover:bg-gray-50'
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
                  <span className="block text-xs text-gray-400 mt-0.5">
                    {new Date(conv.updatedAt).toLocaleTimeString('zh-CN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
              )}
              {!collapsed && hoveredId === conv.id && onDeleteConversation && (
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                  title="删除会话"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── User / Status ── */}
      <div className={`py-4 border-t border-gray-100 ${collapsed ? 'px-2' : 'px-4'}`}>
        {currentUser && !collapsed && (
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-blue-600" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {currentUser.username as string}
                </p>
                {typeof currentUser.company_name === 'string' && currentUser.company_name && (
                  <p className="text-xs text-gray-400 truncate">{currentUser.company_name}</p>
                )}
              </div>
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
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
            <span className="text-gray-700 text-xs font-medium">
              {connectionStatus === 'connected'
                ? '系统就绪'
                : connectionStatus === 'connecting'
                ? '正在连接...'
                : '连接断开'}
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}
