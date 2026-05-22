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
    description: '淘宝/天猫、支付宝账号授权管理',
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
    title: 'API（待开发）',
    description: '配置 API 认证，支持 OpenAPI 导入与手工 endpoint',
    execution_mode: 'deterministic',
    provider_code: 'rest_api',
    behavior: 'managed',
    accent: 'text-violet-700 bg-violet-50',
  },
  {
    source_kind: 'browser_playbook',
    title: '浏览器',
    description: '确定性 Playbook 浏览器采集（千牛、淘宝等）。注册时填入商家凭证 + playbook,自动触发首次验证 dry-run,通过后激活。',
    execution_mode: 'deterministic',
    provider_code: 'qianniu',
    behavior: 'managed',
    accent: 'text-cyan-700 bg-cyan-50',
  },
];

export function sourceKindLabel(kind: DataSourceKind): string {
  if (kind === 'platform_oauth') return '平台授权';
  if (kind === 'database') return '数据库';
  if (kind === 'api') return 'API（待开发）';
  if (kind === 'file') return '文件';
  if (kind === 'browser_playbook') return '浏览器';
  if (kind === 'browser') return '浏览器（旧占位）';
  if (kind === 'desktop_cli') return '客户端/CLI';
  return kind;
}
