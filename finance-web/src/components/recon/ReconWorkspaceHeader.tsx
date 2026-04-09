import type { ReactNode } from 'react';
import { cn, type ReconCenterTab } from './types';
import { CENTER_TABS } from './workspaceCopy';

export interface ReconWorkspaceHeaderTab {
  key: ReconCenterTab;
  label: string;
  disabled?: boolean;
}

export interface ReconWorkspaceHeaderProps {
  activeTab: ReconCenterTab;
  onTabChange: (tab: ReconCenterTab) => void;
  tabs?: ReconWorkspaceHeaderTab[];
  className?: string;
  contentClassName?: string;
  rightSlot?: ReactNode;
}

export default function ReconWorkspaceHeader({
  activeTab,
  onTabChange,
  tabs = CENTER_TABS,
  className,
  contentClassName,
  rightSlot,
}: ReconWorkspaceHeaderProps) {
  return (
    <div className={cn('sticky top-0 z-20 shrink-0 border-b border-border bg-surface/95 px-6 py-4 backdrop-blur', className)}>
      <div
        className={cn(
          'mx-auto flex w-full max-w-6xl flex-wrap items-start justify-between gap-4',
          contentClassName,
        )}
      >
        <div className="flex max-w-full flex-wrap items-center gap-4">
          {tabs.map((tab) => {
            const isActive = tab.key === activeTab;
            return (
              <button
                key={tab.key}
                type="button"
                disabled={tab.disabled}
                onClick={() => onTabChange(tab.key)}
                className={cn(
                  'relative inline-flex min-w-[132px] items-center justify-center rounded-2xl border bg-surface px-6 py-3 text-sm font-semibold transition-all',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-surface',
                  tab.disabled
                    ? 'cursor-not-allowed border-border text-text-muted opacity-50'
                    : isActive
                    ? 'border-sky-200 text-sky-700 shadow-[0_12px_28px_rgba(14,165,233,0.14)]'
                    : 'border-border text-text-secondary shadow-sm hover:border-sky-200 hover:text-text-primary',
                )}
                aria-pressed={isActive}
              >
                <span
                  className={cn(
                    'absolute inset-x-4 bottom-2 h-0.5 rounded-full transition-opacity',
                    isActive ? 'bg-sky-400 opacity-100' : 'opacity-0',
                  )}
                />
                <span className="relative z-10 whitespace-nowrap">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {rightSlot ? <div className="shrink-0 self-center">{rightSlot}</div> : null}
      </div>
    </div>
  );
}
