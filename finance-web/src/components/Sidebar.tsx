import { useState, useEffect } from 'react';
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  LogOut,
  MessageSquare,
  Trash2,
  User,
  Users,
  Zap,
} from 'lucide-react';
import type { ConnectionStatus, Conversation, DigitalEmployee, EmployeeRule } from '../types';

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
  connectionStatus: ConnectionStatus;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation?: (id: string) => void;
  currentUser?: Record<string, unknown> | null;
  onLogout?: () => void;
  collapsed?: boolean;
  onSelectRule?: (employee: DigitalEmployee, rule: EmployeeRule) => void;
  selectedRuleCode?: string | null;
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
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  
  // 数字员工状态
  const [employees, setEmployees] = useState<DigitalEmployee[]>([]);
  const [expandedEmployeeCode, setExpandedEmployeeCode] = useState<string | null>(null);
  const [employeeRules, setEmployeeRules] = useState<Record<string, EmployeeRule[]>>({});
  const [loadingRules, setLoadingRules] = useState<string | null>(null);
  
  // 加载数字员工列表
  useEffect(() => {
    const fetchEmployees = async () => {
      try {
        const response = await fetch('/api/proc/list_digital_employees');
        const data = await response.json();
        if (data.success && data.employees) {
          setEmployees(data.employees);
        }
      } catch (error) {
        console.error('加载数字员工列表失败:', error);
      }
    };
    fetchEmployees();
  }, []);
  
  // 点击数字员工，展开/收起规则列表
  const handleEmployeeClick = async (employee: DigitalEmployee) => {
    if (expandedEmployeeCode === employee.code) {
      setExpandedEmployeeCode(null);
      return;
    }
    
    setExpandedEmployeeCode(employee.code);
    
    // 如果还没加载过该员工的规则，则加载
    if (!employeeRules[employee.code]) {
      setLoadingRules(employee.code);
      try {
        const response = await fetch(`/api/proc/list_rules_by_employee?employee_code=${employee.code}`);
        const data = await response.json();
        if (data.success && data.rules) {
          setEmployeeRules(prev => ({ ...prev, [employee.code]: data.rules }));
        }
      } catch (error) {
        console.error('加载规则列表失败:', error);
      } finally {
        setLoadingRules(null);
      }
    }
  };
  
  // 点击规则
  const handleRuleClick = (employee: DigitalEmployee, rule: EmployeeRule) => {
    onSelectRule?.(employee, rule);
  };

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

      {/* ── Digital Employees Section ── */}
      {!collapsed && employees.length > 0 && (
        <div className="px-4 mb-3">
          <p className="text-gray-500 text-xs font-medium mb-2">选择数字员工</p>
          <div className="space-y-1">
            {employees.map((emp) => (
              <div key={emp.code}>
                {/* 数字员工项 */}
                <div
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all ${
                    expandedEmployeeCode === emp.code
                      ? 'bg-blue-50 text-blue-600'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                  onClick={() => handleEmployeeClick(emp)}
                >
                  {expandedEmployeeCode === emp.code ? (
                    <ChevronDown className="w-4 h-4 shrink-0" />
                  ) : (
                    <ChevronRight className="w-4 h-4 shrink-0" />
                  )}
                  <Users className="w-4 h-4 shrink-0" />
                  <span className="flex-1 truncate text-sm font-medium">{emp.name}</span>
                </div>
                
                {/* 规则列表（二级菜单） */}
                {expandedEmployeeCode === emp.code && (
                  <div className="ml-6 mt-1 space-y-1">
                    {loadingRules === emp.code ? (
                      <div className="px-3 py-2 text-xs text-gray-400">加载中...</div>
                    ) : employeeRules[emp.code]?.length ? (
                      employeeRules[emp.code].map((rule) => (
                        <div
                          key={rule.code}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all ${
                            selectedRuleCode === rule.code
                              ? 'bg-blue-100 text-blue-700 font-medium'
                              : 'text-gray-600 hover:bg-gray-50'
                          }`}
                          onClick={() => handleRuleClick(emp, rule)}
                          title={rule.desc_text || rule.name}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                            selectedRuleCode === rule.code ? 'bg-blue-500' : 'bg-gray-400'
                          }`} />
                          <span className="truncate text-sm">{rule.name}</span>
                        </div>
                      ))
                    ) : (
                      <div className="px-3 py-2 text-xs text-gray-400">暂无规则</div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      
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
                    {formatConversationTime(conv.updatedAt)}
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
