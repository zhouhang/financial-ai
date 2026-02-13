import { useState } from 'react';
import {
  CheckCircle2,
  Circle,
  FileSpreadsheet,
  Loader2,
  Settings2,
  XCircle,
  File,
  Terminal,
} from 'lucide-react';
import type { Task, TaskStatus, UploadedFile } from '../types';

interface WorkbenchProps {
  tasks: Task[];
  uploadedFiles: UploadedFile[];
  results: Record<string, unknown> | null;
}

type TabKey = 'tasks' | 'results' | 'files';

const STATUS_CONFIG: Record<
  TaskStatus,
  { icon: typeof Circle; color: string; label: string; bgColor: string }
> = {
  pending: {
    icon: Circle,
    color: 'text-text-muted',
    label: '待处理',
    bgColor: 'bg-gray-50',
  },
  running: {
    icon: Loader2,
    color: 'text-primary',
    label: '运行中',
    bgColor: 'bg-primary-50',
  },
  completed: {
    icon: CheckCircle2,
    color: 'text-success',
    label: '已完成',
    bgColor: 'bg-green-50',
  },
  failed: {
    icon: XCircle,
    color: 'text-error',
    label: '失败',
    bgColor: 'bg-red-50',
  },
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export default function Workbench({
  tasks,
  uploadedFiles,
  results,
}: WorkbenchProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('tasks');
  const [isCollapsed, setIsCollapsed] = useState(false);

  const tabs: { key: TabKey; label: string; icon: typeof Settings2; badge?: number }[] = [
    { key: 'tasks', label: '任务', icon: Settings2, badge: tasks.length > 0 ? tasks.length : undefined },
    { key: 'results', label: '终端', icon: Terminal },
    { key: 'files', label: '文件', icon: File, badge: uploadedFiles.length > 0 ? uploadedFiles.length : undefined },
  ];

  // 收起状态下的小按钮
  if (isCollapsed) {
    return (
      <div className="w-12 bg-white border-l border-gray-200 flex flex-col items-center py-4 shrink-0">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-100 to-blue-50 flex items-center justify-center text-blue-600 hover:from-blue-200 hover:to-blue-100 transition-colors"
          title="展开工作台"
        >
          <Settings2 className="w-4.5 h-4.5" />
        </button>
      </div>
    );
  }

  return (
    <aside className="w-80 bg-white border-l border-gray-200 flex flex-col h-full shrink-0">
      {/* ── Header ── */}
      <div className="px-5 pt-4 pb-3 border-b border-gray-200">
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setIsCollapsed(true)}
            className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-100 to-blue-50 flex items-center justify-center text-blue-600 hover:from-blue-200 hover:to-blue-100 transition-colors cursor-pointer"
            title="收起工作台"
          >
            <Settings2 className="w-4.5 h-4.5" />
          </button>
          <div>
            <h2 className="font-semibold text-gray-900 text-sm">AI 工作台</h2>
            <p className="text-xs text-gray-500">实时任务与文件管理</p>
          </div>
        </div>
      </div>

      {/* ── 悬浮胶囊 Tabs ── */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex gap-2 bg-gray-100/80 rounded-xl p-1.5">
        {tabs.map((tab) => {
          const Icon = tab.icon;
            const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
                className={`flex-1 relative flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-medium
                  rounded-lg transition-all duration-200 cursor-pointer ${
                    isActive
                      ? 'bg-white text-blue-600 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                }`}
            >
              <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
                {tab.badge !== undefined && (
                  <span className={`absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    isActive ? 'bg-orange-500 text-white' : 'bg-gray-300 text-gray-600'
                  }`}>
                    {tab.badge}
                  </span>
                )}
            </button>
          );
        })}
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto">
        {/* Tasks */}
        {activeTab === 'tasks' && (
          <div className="px-4 py-4 space-y-2">
            {tasks.length === 0 ? (
              <div className="text-center py-16">
                <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                  <Settings2 className="w-6 h-6 text-gray-400" />
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">暂无任务</p>
                <p className="text-xs text-gray-400">
                  开始对话后将自动生成任务
                </p>
              </div>
            ) : (
              tasks.map((task) => {
                const config = STATUS_CONFIG[task.status];
                const Icon = config.icon;
                return (
                  <div
                    key={task.id}
                    className={`flex items-start gap-3 p-3 rounded-xl border border-border/50 ${config.bgColor}`}
                  >
                    <Icon
                      className={`w-4.5 h-4.5 shrink-0 mt-0.5 ${config.color} ${
                        task.status === 'running' ? 'animate-spin' : ''
                      }`}
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">
                        {task.title}
                      </p>
                      <span
                        className={`text-xs ${config.color} font-medium`}
                      >
                        {config.label}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Results */}
        {activeTab === 'results' && (
          <div className="px-4 py-3">
            {results ? (
              <div className="space-y-3">
                {/* Summary */}
                {!!(results as Record<string, unknown>).summary && (
                  <div className="p-3 bg-success/5 rounded-xl border border-success/20">
                    <p className="text-sm font-medium text-text-primary mb-2">
                      对账结果摘要
                    </p>
                    {Object.entries(
                      (results as Record<string, unknown>).summary as Record<string, unknown>
                    ).map(([key, val]) => (
                      <div
                        key={key}
                        className="flex justify-between text-xs py-1"
                      >
                        <span className="text-text-secondary">{key}</span>
                        <span className="font-medium text-text-primary">
                          {String(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-16">
                <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                  <Terminal className="w-6 h-6 text-gray-400" />
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">暂无终端输出</p>
                <p className="text-xs text-gray-400">
                  执行任务时终端输出将在此显示
                </p>
              </div>
            )}
          </div>
        )}

        {/* Files */}
        {activeTab === 'files' && (
          <div className="px-4 py-4 space-y-2">
            {uploadedFiles.length === 0 ? (
              <div className="text-center py-16">
                <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                  <File className="w-6 h-6 text-gray-400" />
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">暂无文件</p>
                <p className="text-xs text-gray-400">
                  上传文件后将在此列出
                </p>
              </div>
            ) : (
              uploadedFiles.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 p-3 bg-surface-secondary rounded-xl border border-border/50"
                >
                  <div className="w-9 h-9 rounded-lg bg-success/10 flex items-center justify-center shrink-0">
                    <FileSpreadsheet className="w-4 h-4 text-success" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {f.name}
                    </p>
                    <p className="text-xs text-text-muted">
                      {formatFileSize(f.size)} ·{' '}
                      {f.uploadedAt.toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                  <span className="text-xs text-success bg-success/10 px-2 py-0.5 rounded-full font-medium">
                    已上传
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
