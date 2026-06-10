import { useState } from 'react';
import { Download, ExternalLink, Lock, ShieldAlert } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { sortRowsBySpec } from './csvExport';
import { formatMetricValue } from './format';
import type { DigestBundle, DigestLayoutSection, DigestRow } from './types';

function sectionTitle(section: DigestLayoutSection): string {
  return section.title || '';
}

function metricLabel(section: DigestLayoutSection, metric: string): string {
  return section.metric_label_map?.[metric] || metric;
}

function drilldownLabel(section: DigestLayoutSection, metric: string): string {
  const labels = section.drilldown?.metric_label_map;
  if (labels && typeof labels === 'object' && !Array.isArray(labels)) {
    return (labels as Record<string, string>)[metric] || metricLabel(section, metric);
  }
  return metricLabel(section, metric);
}

function totalValue(bundle: DigestBundle, metric: string): unknown {
  return bundle.data.totals?.[metric];
}

function asRows(rows: DigestRow[]): Array<Record<string, unknown>> {
  return rows as Array<Record<string, unknown>>;
}

function sumMetric(rows: Array<Record<string, unknown>>, metric: string): number {
  return rows.reduce((total, row) => total + Number(row[metric] ?? 0), 0);
}

function groupRows(
  rows: Array<Record<string, unknown>>,
  groupBy = '',
  labels: Record<string, string> = {},
) {
  if (!groupBy) {
    return [{ key: '', label: '', rows }];
  }
  const groups = new Map<string, Array<Record<string, unknown>>>();
  rows.forEach((row) => {
    const key = String(row[groupBy] ?? '');
    groups.set(key, [...(groups.get(key) || []), row]);
  });
  return Array.from(groups.entries()).map(([key, value]) => ({
    key,
    label: labels[key] || key || '未分组',
    rows: value,
  }));
}

function ReportBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-border-subtle py-5 last:border-b-0">
      {title ? <h2 className="text-base font-semibold text-text-primary">{title}</h2> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function MetricCardGrid({
  entries,
}: {
  entries: Array<{ metric: string; label: string; value: unknown }>;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {entries.map((entry) => (
        <div key={`${entry.metric}-${entry.label}`} className="rounded-md border border-border bg-surface px-4 py-3">
          <p className="break-words text-xs text-text-secondary">{entry.label}</p>
          <p className="mt-2 break-words text-lg font-semibold text-text-primary">
            {formatMetricValue(entry.metric, entry.value)}
          </p>
        </div>
      ))}
    </div>
  );
}

function MetricKpi({ bundle, section }: { bundle: DigestBundle; section: DigestLayoutSection }) {
  const metrics = section.metrics || [];
  const rollups = asRows(bundle.data.rollups);

  return (
    <ReportBlock title={sectionTitle(section)}>
      {section.group_by ? (
        <div className="space-y-4">
          {groupRows(rollups, section.group_by, section.group_label_map).map((group) => (
            <div key={group.key || 'all'} className="space-y-2">
              {group.label ? <h3 className="text-sm font-medium text-text-secondary">{group.label}</h3> : null}
              <MetricCardGrid
                entries={metrics.map((metric) => ({
                  metric,
                  label: metricLabel(section, metric),
                  value: sumMetric(group.rows, metric),
                }))}
              />
            </div>
          ))}
        </div>
      ) : (
        <MetricCardGrid
          entries={metrics.map((metric) => ({
            metric,
            label: metricLabel(section, metric),
            value: totalValue(bundle, metric),
          }))}
        />
      )}
      {section.caption ? <p className="mt-3 text-xs text-text-muted">{section.caption}</p> : null}
    </ReportBlock>
  );
}

function Funnel({ bundle, section }: { bundle: DigestBundle; section: DigestLayoutSection }) {
  return (
    <ReportBlock title={sectionTitle(section)}>
      <div className="grid gap-2 md:grid-cols-5">
        {(section.stages || []).map((stage) => (
          <div key={stage.metric} className="rounded-md border border-border bg-surface px-3 py-3">
            <p className="break-words text-xs text-text-secondary">{stage.label || stage.metric}</p>
            <p className="mt-2 break-words text-base font-semibold text-text-primary">
              {formatMetricValue(stage.metric, totalValue(bundle, stage.metric))}
            </p>
          </div>
        ))}
      </div>
      {section.caption ? <p className="mt-3 text-xs text-text-muted">{section.caption}</p> : null}
    </ReportBlock>
  );
}

function EntityTable({ bundle, section }: { bundle: DigestBundle; section: DigestLayoutSection }) {
  const columns = section.columns || section.metrics || [];
  const rows = sortRowsBySpec(asRows(bundle.data.rollups), section.sort || '');
  const planLabel = (row: Record<string, unknown>) => String(row.plan_name_snapshot || row.plan_code || '--');

  return (
    <ReportBlock title={sectionTitle(section)}>
      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs text-text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">对账计划</th>
              {columns.map((column) => (
                <th key={column} className="px-3 py-2 font-medium">{metricLabel(section, column)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.plan_code || index}`} className="border-b border-border-subtle last:border-b-0">
                <td className="px-3 py-2">{planLabel(row)}</td>
                {columns.map((column) => (
                  <td key={column} className="px-3 py-2">{formatMetricValue(column, row[column])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid gap-3 md:hidden">
        {rows.map((row, index) => (
          <article key={`${row.plan_code || index}`} className="rounded-md border border-border bg-surface px-3 py-3">
            <p className="break-words text-sm font-medium text-text-primary">{planLabel(row)}</p>
            {columns.slice(0, 4).map((column) => (
              <div key={column} className="flex items-start justify-between gap-3 py-1 text-sm">
                <span className="break-words text-text-secondary">{metricLabel(section, column)}</span>
                <span className="break-words text-right font-medium text-text-primary">
                  {formatMetricValue(column, row[column])}
                </span>
              </div>
            ))}
          </article>
        ))}
      </div>
    </ReportBlock>
  );
}

function exceptionHref(row: Record<string, unknown>): string {
  const runId = String(row.execution_run_id || '');
  return runId ? `/recon/runs/${encodeURIComponent(runId)}/exceptions` : '';
}

function DiffList({
  bundle,
  section,
  onExportCsv,
}: {
  bundle: DigestBundle;
  section: DigestLayoutSection;
  onExportCsv: (reconType: string, columns: string[]) => void;
}) {
  const columns = section.columns || [];
  const groups = groupRows(asRows(bundle.data.canonical_lines), section.group_by, section.group_label_map);
  const sampling = bundle.data.sampling;

  return (
    <ReportBlock title={sectionTitle(section)}>
      {sampling?.truncated ? (
        <p className="mb-3 rounded-md border border-border bg-surface-secondary px-3 py-2 text-xs text-text-secondary">
          已采样 {sampling.loaded}/{sampling.total}，导出取全量
        </p>
      ) : null}
      <div className="space-y-4">
        {groups.map((group) => (
          <div key={group.key || 'all'} className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              {group.label ? <h3 className="text-sm font-medium text-text-secondary">{group.label}</h3> : <span />}
              <button
                type="button"
                onClick={() => onExportCsv(group.key, columns)}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-sm font-medium text-text-primary"
              >
                <Download className="h-4 w-4" />
                导出底稿
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="hidden min-w-full text-left text-sm md:table">
                <thead className="border-b border-border-subtle text-xs text-text-muted">
                  <tr>
                    {columns.map((column) => (
                      <th key={column} className="px-3 py-2 font-medium">{metricLabel(section, column)}</th>
                    ))}
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row, index) => (
                    <tr key={String(row.id || index)} className="border-b border-border-subtle last:border-b-0">
                      {columns.map((column) => (
                        <td key={column} className="px-3 py-2">{formatMetricValue(column, row[column])}</td>
                      ))}
                      <td className="px-3 py-2 text-right">
                        {exceptionHref(row) ? (
                          <a href={exceptionHref(row)} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs">
                            去处理 <ExternalLink className="h-3 w-3" />
                          </a>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="grid gap-3 md:hidden">
                {group.rows.map((row, index) => (
                  <article key={String(row.id || index)} className="rounded-md border border-border bg-surface px-3 py-3">
                    {columns.map((column) => (
                      <div key={column} className="flex items-start justify-between gap-3 py-1 text-sm">
                        <span className="break-words text-text-secondary">{metricLabel(section, column)}</span>
                        <span className="break-words text-right font-medium text-text-primary">
                          {formatMetricValue(column, row[column])}
                        </span>
                      </div>
                    ))}
                    {exceptionHref(row) ? (
                      <a href={exceptionHref(row)} className="mt-3 inline-flex min-h-9 items-center gap-1 rounded-md border border-border px-3 text-sm">
                        去处理 <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </ReportBlock>
  );
}

function AlertList({ bundle, section }: { bundle: DigestBundle; section: DigestLayoutSection }) {
  const [openId, setOpenId] = useState('');
  const columns = (section.drilldown?.columns as string[] | undefined) || [];
  const filter = String(section.drilldown?.filter || '');
  const wantsLeftOnly = /match_status\s*=\s*left_only/.test(filter);
  const agingMatch = filter.match(/aging\s*>\s*(\d+)/);
  const minAgingDays = agingMatch ? Number(agingMatch[1]) : null;
  const alerts = asRows(bundle.data.alerts).filter((alert) => {
    if (!section.alert_code) return true;
    return String(alert.alert_code || '') === section.alert_code;
  });

  function drillRows(alert: Record<string, unknown>): Array<Record<string, unknown>> {
    return asRows(bundle.data.canonical_lines).filter((line) => {
      if (alert.plan_code && line.plan_code !== alert.plan_code) return false;
      if (wantsLeftOnly && line.match_status !== 'left_only') return false;
      if (minAgingDays !== null && Number(line.aging_days ?? -1) <= minAgingDays) return false;
      return true;
    });
  }

  return (
    <ReportBlock title={sectionTitle(section)}>
      <div className="grid gap-3">
        {alerts.length === 0 ? <p className="text-sm text-text-secondary">暂无记录</p> : null}
        {alerts.map((alert, index) => {
          const id = String(alert.id || index);
          const open = openId === id;
          const rows = open ? drillRows(alert) : [];
          return (
            <article key={id} className="rounded-md border border-border bg-surface px-4 py-3">
              <div className="flex items-start gap-2">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm font-medium text-text-primary">
                    {String(alert.title || alert.alert_code || alert.status || '--')}
                  </p>
                  {alert.explain_text ? (
                    <p className="mt-1 break-words text-xs text-text-secondary">{String(alert.explain_text)}</p>
                  ) : null}
                  {columns.length ? (
                    <button
                      type="button"
                      onClick={() => setOpenId(open ? '' : id)}
                      className="mt-2 text-xs font-medium text-text-primary underline"
                    >
                      {open ? '收起明细' : '查看明细'}
                    </button>
                  ) : null}
                  {open ? (
                    <div className="mt-2 overflow-x-auto">
                      <table className="min-w-full text-left text-xs">
                        <thead className="border-b border-border-subtle text-text-muted">
                          <tr>
                            {columns.map((column) => (
                              <th key={column} className="px-2 py-1 font-medium">{drilldownLabel(section, column)}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.length === 0 ? (
                            <tr><td className="px-2 py-1 text-text-secondary" colSpan={columns.length}>无明细</td></tr>
                          ) : null}
                          {rows.map((row, rowIndex) => (
                            <tr key={String(row.id || rowIndex)} className="border-b border-border-subtle last:border-b-0">
                              {columns.map((column) => (
                                <td key={column} className="px-2 py-1">{formatMetricValue(column, row[column])}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </ReportBlock>
  );
}

function LockedPlaceholder({ section }: { section: DigestLayoutSection }) {
  return (
    <ReportBlock title={sectionTitle(section)}>
      <div className="grid gap-3 md:grid-cols-2">
        {(section.items || []).map((item) => (
          <article key={item.metric} className="rounded-md border border-dashed border-border bg-surface-secondary px-4 py-4 text-text-secondary">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Lock className="h-4 w-4" />
              {item.label || item.metric}
            </div>
            <p className="mt-2 text-sm">{item.unlock}</p>
          </article>
        ))}
      </div>
    </ReportBlock>
  );
}

export default function DigestDetailRenderer({
  bundle,
  onExportCsv,
}: {
  bundle: DigestBundle;
  onExportCsv: (reconType: string, columns: string[]) => void;
}) {
  return (
    <div className="divide-y divide-border-subtle">
      {bundle.layout.sections.map((section, index) => {
        const key = `${section.type}-${index}`;
        if (section.type === 'narrative') {
          return (
            <ReportBlock key={key} title={sectionTitle(section)}>
              <div className="prose prose-sm max-w-none text-text-primary">
                <ReactMarkdown>{bundle.digest.narrative || ''}</ReactMarkdown>
              </div>
            </ReportBlock>
          );
        }
        if (section.type === 'metric_kpi') return <MetricKpi key={key} bundle={bundle} section={section} />;
        if (section.type === 'funnel') return <Funnel key={key} bundle={bundle} section={section} />;
        if (section.type === 'ranking_table' || section.type === 'distribution') return <EntityTable key={key} bundle={bundle} section={section} />;
        if (section.type === 'alert_list') return <AlertList key={key} bundle={bundle} section={section} />;
        if (section.type === 'diff_list') return <DiffList key={key} bundle={bundle} section={section} onExportCsv={onExportCsv} />;
        if (section.type === 'locked_placeholder') return <LockedPlaceholder key={key} section={section} />;
        return null;
      })}
    </div>
  );
}
