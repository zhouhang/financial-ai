import { useState } from 'react';
import {
  MessageSquare,
  Plus,
  Trash2,
  History,
} from 'lucide-react';
import type { ConnectionStatus, Conversation, AgentType } from '../types';
import AgentSelector from './AgentSelector';

// 过滤会话标题中的 Agent 前缀
function filterConvTitle(title: string): string {
  return title.replace(/^\[AGENT:data_process\]\s*/, '');
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
  selectedAgent?: AgentType;
  onSelectAgent?: (agent: AgentType) => void;
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
  selectedAgent = 'reconciliation',
  onSelectAgent,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // 调试：打印 Sidebar 渲染信息
  console.log('[Sidebar] 渲染', {
    conversations: conversations?.length,
    currentUser: currentUser ? '✅' : '❌',
    selectedAgent,
  });

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('确定要删除这个会话吗？')) {
      onDeleteConversation?.(id);
    }
  };

  return (
    <aside 
      style={{ 
        width: '256px', 
        minWidth: '256px',
        maxWidth: '256px',
        background: 'white',
        borderRight: '1px solid #f1f5f9',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        flexShrink: 0,
      }}
    >
      {/* ── 顶部：新建会话 ── */}
      <div className="p-3">
        <button
          onClick={onNewConversation}
          className="w-full flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 rounded-lg
            text-gray-700 text-sm font-medium hover:bg-gray-50 hover:border-gray-300
            transition-all duration-150 cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>新建会话</span>
        </button>
      </div>

      {/* ── Agent 选择器 ── */}
      <AgentSelector
        selectedAgent={selectedAgent}
        onSelectAgent={onSelectAgent}
      />

      {/* ── 历史会话 ── */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <div className="flex items-center gap-2 px-2 mb-2">
          <History className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-xs font-medium text-gray-500">历史会话</span>
        </div>
        
        <div className="space-y-0.5">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`
                relative flex items-center gap-2 px-3 py-2.5 rounded-lg
                text-left transition-all duration-150 cursor-pointer group
                ${activeConversationId === conv.id
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-700 hover:bg-gray-100'
                }
              `}
              onClick={() => onSelectConversation(conv.id)}
              onMouseEnter={() => setHoveredId(conv.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <MessageSquare className={`w-4 h-4 shrink-0 ${activeConversationId === conv.id ? 'text-blue-600' : 'text-gray-400'}`} />
              <div className="flex-1 min-w-0">
                <span className="block truncate text-sm font-medium">{filterConvTitle(conv.title)}</span>
                <span className={`block text-xs mt-0.5 ${activeConversationId === conv.id ? 'text-blue-400' : 'text-gray-400'}`}>
                  {new Date(conv.updatedAt).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </span>
              </div>
              {/* 删除按钮 */}
              {hoveredId === conv.id && onDeleteConversation && (
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all"
                  title="删除会话"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── 底部：用户信息 ── */}
      {currentUser && (
        <div className="p-3 border-t border-gray-100">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <span className="text-xs font-medium text-blue-600">
                  {(currentUser.username?.toString() || 'U').charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {currentUser.username?.toString() || '用户'}
                </p>
                {currentUser.company_name && typeof currentUser.company_name === 'string' && (
                  <p className="text-xs text-gray-400 truncate">
                    {currentUser.company_name}
                  </p>
                )}
              </div>
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                className="p-1.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all cursor-pointer"
                title="退出登录"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── 连接状态 ── */}
      <div className="px-3 py-2 border-t border-gray-100">
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              connectionStatus === 'connected'
                ? 'bg-green-500'
                : connectionStatus === 'connecting'
                ? 'bg-yellow-500 animate-pulse'
                : 'bg-red-500'
            }`}
          />
          <span className="text-xs text-gray-500 font-medium">
            {connectionStatus === 'connected'
              ? '已连接'
              : connectionStatus === 'connecting'
              ? '连接中...'
              : '未连接'}
          </span>
        </div>
      </div>
    </aside>
  );
}
