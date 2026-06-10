import type { PublicReconDigestView } from '../../publicReconDigestRoute';

export type DigestMetricValue = string | number | boolean | null;

export type DigestRow = Record<string, DigestMetricValue | DigestMetricValue[] | Record<string, unknown>>;

export type DigestSectionType =
  | 'funnel'
  | 'ranking_table'
  | 'metric_kpi'
  | 'alert_list'
  | 'diff_list'
  | 'distribution'
  | 'locked_placeholder'
  | 'narrative';

export interface DigestMetricLayout {
  metric: string;
  label?: string;
}

export interface DigestLockedMetricLayout extends DigestMetricLayout {
  state: 'beta' | 'locked';
  unlock: string;
}

export interface DigestLayoutSection {
  type: DigestSectionType;
  title?: string;
  caption?: string;
  metrics?: string[];
  stages?: DigestMetricLayout[];
  columns?: string[];
  entity?: string;
  sort?: string;
  group_by?: string;
  group_label_map?: Record<string, string>;
  metric_label_map?: Record<string, string>;
  alert_code?: string;
  drilldown?: Record<string, unknown>;
  items?: DigestLockedMetricLayout[];
}

export interface DigestLayout {
  layout_code: string;
  domain: string;
  view: PublicReconDigestView;
  sections: DigestLayoutSection[];
  version: number;
}

export interface DigestSampling {
  loaded: number;
  total: number;
  truncated: boolean;
}

export interface DigestBundle {
  success: boolean;
  view: PublicReconDigestView;
  domain: string;
  biz_date: string;
  digest: {
    id: string;
    structured: Record<string, unknown>;
    narrative: string;
    period_start: string;
    period_end: string;
  };
  layout: DigestLayout;
  data: {
    rollups: DigestRow[];
    totals: Record<string, DigestMetricValue>;
    alerts: DigestRow[];
    canonical_lines: DigestRow[];
    sampling: DigestSampling;
  };
}

export interface DigestExportRows {
  rows: DigestRow[];
  total: number;
}
