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
          'mx-auto flex w-full max-w-6xl items-center justify-between gap-3',
          contentClassName,
        )}
      >
        <div className="inline-flex max-w-full items-center gap-2 overflow-x-auto rounded-2xl border border-border bg-surface-secondary/90 p-1 shadow-sm">
          {tabs.map((tab) => {
            const isActive = tab.key === activeTab;
            return (
              <button
                key={tab.key}
                type="button"
                disabled={tab.disabled}
                onClick={() => onTabChange(tab.key)}
                className={cn(
                  'relative inline-flex min-w-fit items-center justify-center rounded-xl px-4 py-2.5 text-sm font-medium transition-all',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-surface',
                  tab.disabled
                    ? 'cursor-not-allowed text-text-muted opacity-50'
                    : isActive
                    ? 'bg-surface text-sky-700 shadow-[0_10px_24px_rgba(14,165,233,0.12)]'
                    : 'text-text-secondary hover:bg-surface hover:text-text-primary',
                )}
                aria-pressed={isActive}
              >
                <span
                  className={cn(
                    'absolute inset-x-3 bottom-1 h-0.5 rounded-full transition-opacity',
                    isActive ? 'bg-sky-400 opacity-100' : 'opacity-0',
                  )}
                />
                <span className="relative z-10 whitespace-nowrap">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {rightSlot ? <div className="shrink-0">{rightSlot}</div> : null}
      </div>
    </div>
  );
}
