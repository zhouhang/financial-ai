import { useState } from 'react';
import { Bot } from 'lucide-react';
import { cn, type ReconRuleListItem } from './types';

interface ReconRulesListProps {
  rules: ReconRuleListItem[];
  loading?: boolean;
  className?: string;
  title?: string;
  subtitle?: string;
  loadingText?: string;
  emptyText?: string;
  aiEntryLabel?: string;
  showCreatePlaceholder?: boolean;
  onCreateByAI?: () => void;
  onCloseCreatePlaceholder?: () => void;
}

export default function ReconRulesList({
  rules,
  loading = false,
  className,
  title = '规则列表',
  subtitle = '当前仅展示规则，不提供详情面板、选中态和规则修改入口。',
  loadingText = '正在加载规则列表...',
  emptyText = '当前暂无规则，请先新增规则。',
  aiEntryLabel = 'AI 新增规则',
  showCreatePlaceholder,
  onCreateByAI,
  onCloseCreatePlaceholder,
}: ReconRulesListProps) {
  const [localShowPlaceholder, setLocalShowPlaceholder] = useState(false);
  const isPlaceholderVisible = showCreatePlaceholder ?? localShowPlaceholder;

  const handleCreateByAI = () => {
    if (showCreatePlaceholder === undefined) {
      setLocalShowPlaceholder(true);
    }
    onCreateByAI?.();
  };

  const handleClosePlaceholder = () => {
    if (showCreatePlaceholder === undefined) {
      setLocalShowPlaceholder(false);
    }
    onCloseCreatePlaceholder?.();
  };

  return (
    <section className={cn('rounded-2xl border border-border bg-surface p-5 shadow-sm', className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-text-primary">{title}</h3>
          <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>
        </div>
        <button
          type="button"
          onClick={handleCreateByAI}
          className="inline-flex items-center gap-2 rounded-xl border border-dashed border-sky-200 bg-sky-50 px-3.5 py-2 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100"
        >
          <Bot className="h-4 w-4" />
          {aiEntryLabel}
        </button>
      </div>

      {isPlaceholderVisible && (
        <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
          <div className="text-sm font-medium text-sky-800">占位交互</div>
          <p className="mt-1 text-sm text-sky-700">
            已进入「AI 新增规则」占位流程。后续可在这里接入规则生成向导。
          </p>
          <button
            type="button"
            onClick={handleClosePlaceholder}
            className="mt-3 inline-flex items-center rounded-lg border border-sky-300 bg-white px-3 py-1.5 text-xs font-medium text-sky-700 transition-colors hover:bg-sky-100"
          >
            关闭
          </button>
        </div>
      )}

      <div className="mt-4 space-y-2">
        {loading && (
          <div className="rounded-2xl border border-border bg-surface-secondary px-4 py-8 text-center text-sm text-text-secondary">
            {loadingText}
          </div>
        )}

        {!loading && rules.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-secondary">
            {emptyText}
          </div>
        )}

        {!loading &&
          rules.map((rule) => (
            <div
              key={rule.rule_code}
              className="rounded-2xl border border-border bg-surface-secondary px-4 py-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-text-primary">{rule.name}</div>
                  <div className="mt-1 text-xs text-text-secondary">{rule.rule_code}</div>
                </div>
                <span className="rounded-full bg-surface px-2.5 py-1 text-xs text-text-secondary">
                  {rule.updated_hint || '规则实例'}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-text-secondary">
                <span>任务：{rule.task_name}</span>
                {rule.file_rule_code && <span>文件校验：{rule.file_rule_code}</span>}
                <span>类型：{rule.rule_type}</span>
              </div>
              {rule.remark && <p className="mt-2 text-sm text-text-secondary">{rule.remark}</p>}
            </div>
          ))}
      </div>
    </section>
  );
}
