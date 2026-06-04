import { describe, expect, it } from 'vitest';

import { buildRuntimeSummaryView } from '../../src/components/recon/runRuntimeSummary';

describe('buildRuntimeSummaryView exception sampling', () => {
  it('normalizes exception sampling metadata from runtime summary', () => {
    const view = buildRuntimeSummaryView({
      raw: {
        artifacts_json: {
          runtime_summary: {
            exception_sampling: {
              enabled: true,
              total_count: 35665,
              sample_count: 200,
              sample_limit: 200,
              threshold: 1000,
              strategy: 'stratified_by_anomaly_type_owner',
              fallback_used: false,
            },
          },
        },
      },
    });

    expect(view.exceptionSampling.enabled).toBe(true);
    expect(view.exceptionSampling.totalCount).toBe(35665);
    expect(view.exceptionSampling.sampleCount).toBe(200);
    expect(view.exceptionSampling.sampleLimit).toBe(200);
    expect(view.exceptionSampling.threshold).toBe(1000);
    expect(view.exceptionSampling.strategy).toBe('stratified_by_anomaly_type_owner');
    expect(view.exceptionSampling.fallbackUsed).toBe(false);
  });

  it('falls back to disabled exception sampling when metadata is absent', () => {
    const view = buildRuntimeSummaryView({ raw: { artifacts_json: {} } });

    expect(view.exceptionSampling).toEqual({
      enabled: false,
      totalCount: null,
      sampleCount: null,
      sampleLimit: null,
      threshold: null,
      strategy: '',
      fallbackUsed: false,
    });
  });
});
