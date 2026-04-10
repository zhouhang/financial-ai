import type { DataSourceExecutionMode, DataSourceKind } from './types';

export interface SourceTypeCard {
  source_kind: DataSourceKind;
  title: string;
  description: string;
  execution_mode: DataSourceExecutionMode;
  provider_code: string;
  behavior: 'platform' | 'managed' | 'draft_create' | 'reserved';
  accent: string;
}

export const SOURCE_TYPE_CARDS: SourceTypeCard[] = [
  {
    source_kind: 'platform_oauth',
    title: '电商平台授权',
    description: '淘宝、天猫、抖店等账号授权管理',
    execution_mode: 'deterministic',
    provider_code: 'multi_platform',
    behavior: 'platform',
    accent: 'text-blue-600 bg-blue-50',
  },
  {
    source_kind: 'database',
    title: '数据库连接',
    description: '连接数据库并发现可用表/视图，再选择启用数据集',
    execution_mode: 'deterministic',
    provider_code: 'postgresql',
    behavior: 'managed',
    accent: 'text-emerald-700 bg-emerald-50',
  },
  {
    source_kind: 'api',
    title: 'API 连接',
    description: '配置 API 认证，支持 OpenAPI 导入与手工 endpoint',
    execution_mode: 'deterministic',
    provider_code: 'rest_api',
    behavior: 'managed',
    accent: 'text-violet-700 bg-violet-50',
  },
  {
    source_kind: 'file',
    title: '文件连接',
    description: '文件类数据接入（一期保持轻量，后续统一到数据集目录）',
    execution_mode: 'deterministic',
    provider_code: 'manual_file',
    behavior: 'managed',
    accent: 'text-amber-700 bg-amber-50',
  },
  {
    source_kind: 'browser',
    title: '浏览器抓取',
    description: '预留能力，未来由 agent assisted 执行',
    execution_mode: 'agent_assisted',
    provider_code: 'playwright',
    behavior: 'reserved',
    accent: 'text-cyan-700 bg-cyan-50',
  },
  {
    source_kind: 'desktop_cli',
    title: '客户端/CLI 抓取',
    description: '预留能力，未来由 agent assisted 执行',
    execution_mode: 'agent_assisted',
    provider_code: 'desktop_cli',
    behavior: 'reserved',
    accent: 'text-rose-700 bg-rose-50',
  },
];

export function sourceKindLabel(kind: DataSourceKind): string {
  if (kind === 'platform_oauth') return '平台授权';
  if (kind === 'database') return '数据库';
  if (kind === 'api') return 'API';
  if (kind === 'file') return '文件';
  if (kind === 'browser') return '浏览器';
  if (kind === 'desktop_cli') return '客户端/CLI';
  return kind;
}
