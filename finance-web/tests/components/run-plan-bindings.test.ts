import { describe, expect, it } from 'vitest';

import { resolveDatasetSourceType } from '../../src/components/recon/runPlanBindings';

describe('resolveDatasetSourceType', () => {
  it('keeps platform_order_lines compatibility', () => {
    expect(resolveDatasetSourceType({
      extractConfig: { storage: 'platform_order_lines' },
      schemaSummary: {},
    })).toBe('platform_order_lines');
  });

  it('uses explicit dataset_source_type for alipay parsed tables', () => {
    expect(resolveDatasetSourceType({
      extractConfig: {
        collection_driver: 'alipay_bill_download_import',
        dataset_source_type: 'alipay_bill_lines',
        storage: 'alipay_bill_lines',
      },
      schemaSummary: {},
    })).toBe('alipay_bill_lines');
  });

  it('defaults database-like datasets to collection_records', () => {
    expect(resolveDatasetSourceType({
      extractConfig: { storage: 'dataset_collection_records' },
      schemaSummary: {},
    })).toBe('collection_records');
  });

  it('does not treat openapi schema provenance as a dataset source type', () => {
    expect(resolveDatasetSourceType({
      extractConfig: {},
      schemaSummary: { source: 'openapi' },
    })).toBe('collection_records');
  });

  it('does not treat manual schema provenance as a dataset source type', () => {
    expect(resolveDatasetSourceType({
      extractConfig: {},
      schemaSummary: { source: 'manual' },
    })).toBe('collection_records');
  });
});
