import { Database, Files, Link2 } from 'lucide-react';
import type { UserTaskRule } from '../../types';

export type ReconExecutionMode = 'upload' | 'data_source';

interface ReconConversationBarProps {
  ruleName?: string | null;
  rules?: UserTaskRule[];
  selectedRuleCode?: string | null;
  executionMode: ReconExecutionMode;
  showRuleSelector?: boolean;
  onSelectRule?: (ruleCode: string) => void;
  onChangeExecutionMode?: (mode: ReconExecutionMode) => void;
  onOpenDataConnections?: () => void;
}

export default function ReconConversationBar({
  ruleName,
  rules = [],
  selectedRuleCode,
  executionMode,
  showRuleSelector = true,
  onSelectRule,
  onChangeExecutionMode,
  onOpenDataConnections,
}: ReconConversationBarProps) {
  const selectedRule =
    rules.find((rule) => rule.rule_code === selectedRuleCode) ??
    rules[0] ??
    null;
  const resolvedRuleName = ruleName ?? selectedRule?.name ?? '未选择对账规则';
  const canSelectRule = rules.length > 0 && Boolean(onSelectRule);

  const helperText =
    executionMode === 'data_source'
      ? '将按当前规则直接使用已连接数据源执行对账，无需先上传文件。'
      : '先上传 Excel 或 CSV 文件，再通过对话直接发起当前规则的对账。';

  return (
    <div className="mb-4 rounded-2xl border border-[rgba(14,165,233,0.18)] bg-[linear-gradient(180deg,rgba(240,249,255,0.96),rgba(255,255,255,0.96))] p-4 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-600">
            当前对账上下文
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full border border-[rgba(14,165,233,0.2)] bg-white px-3 py-1 text-xs font-medium text-sky-700">
              数据对账
            </span>
            <span className="inline-flex items-center rounded-full border border-[rgba(15,23,42,0.08)] bg-[rgba(255,255,255,0.86)] px-3 py-1 text-xs font-medium text-text-primary">
              {resolvedRuleName}
            </span>
          </div>
        </div>

        <p className="max-w-sm text-xs leading-5 text-text-secondary">
          在这里确认规则和执行方式后，直接继续对话即可，不需要离开当前会话。
        </p>
      </div>

      <div className={`mt-4 grid gap-3 ${showRuleSelector ? 'md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]' : 'md:grid-cols-1'}`}>
        {showRuleSelector && (
          <label className="block min-w-0">
            <span className="text-xs font-medium text-text-secondary">当前规则</span>
            {rules.length > 0 ? (
              <select
                value={selectedRuleCode ?? selectedRule?.rule_code ?? ''}
                onChange={(event) => onSelectRule?.(event.target.value)}
                disabled={!canSelectRule}
                className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-surface-secondary disabled:text-text-muted"
              >
                {rules.map((rule) => (
                  <option key={rule.rule_code} value={rule.rule_code}>
                    {rule.name}
                  </option>
                ))}
              </select>
            ) : (
              <div className="mt-1.5 rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary">
                {resolvedRuleName}
              </div>
            )}
          </label>
        )}

        <div>
          <span className="text-xs font-medium text-text-secondary">执行方式</span>
          <div className="mt-1.5 inline-flex w-full rounded-xl bg-surface-secondary p-1">
            <button
              type="button"
              onClick={() => onChangeExecutionMode?.('upload')}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                executionMode === 'upload'
                  ? 'bg-white text-sky-700 shadow-sm'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <span className="inline-flex items-center gap-2">
                <Files className="h-4 w-4" />
                上传文件
              </span>
            </button>
            <button
              type="button"
              onClick={() => onChangeExecutionMode?.('data_source')}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                executionMode === 'data_source'
                  ? 'bg-white text-sky-700 shadow-sm'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <span className="inline-flex items-center gap-2">
                <Database className="h-4 w-4" />
                数据源
              </span>
            </button>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-2 rounded-xl border border-[rgba(15,23,42,0.06)] bg-[rgba(255,255,255,0.72)] px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-5 text-text-secondary">{helperText}</p>
        {executionMode === 'data_source' && onOpenDataConnections && (
          <button
            type="button"
            onClick={onOpenDataConnections}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-xs font-medium text-text-primary transition hover:border-sky-200 hover:text-sky-700"
          >
            <Link2 className="h-4 w-4" />
            去配置数据连接
          </button>
        )}
      </div>
    </div>
  );
}
