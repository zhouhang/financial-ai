import { describe, expect, it } from 'vitest';

import { SOURCE_TYPE_CARDS, sourceKindLabel } from '../../src/dataSourceConfig';

describe('数据连接来源配置', () => {
  it('只展示当前生产支持的数据连接卡片', () => {
    expect(SOURCE_TYPE_CARDS.map((card) => card.source_kind)).toEqual([
      'platform_oauth',
      'database',
      'api',
      'browser_playbook',
    ]);
  });

  it('将 API 标记为待开发能力', () => {
    const apiCard = SOURCE_TYPE_CARDS.find((card) => card.source_kind === 'api');

    expect(apiCard?.title).toBe('API（待开发）');
    expect(sourceKindLabel('api')).toBe('API（待开发）');
  });
});
