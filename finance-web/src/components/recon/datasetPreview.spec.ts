import { describe, expect, it } from 'vitest';

import {
  buildDatasetPreviewRequestBody,
  extractDatasetPreviewRows,
  extractPreviewSampleRows,
} from './datasetPreview';

describe('dataset preview helpers', () => {
  it('extracts rows from preview_sample before collection-style fields', () => {
    const rows = extractDatasetPreviewRows(
      {
        preview_sample: {
          rows: [
            { id: 1, amount: 100 },
            { id: 2, amount: 200 },
          ],
        },
        collection_records: [{ payload: { id: 999 } }],
      },
      1,
    );

    expect(rows).toEqual([{ id: 1, amount: 100 }]);
  });

  it('extracts rows from dataset meta preview sample', () => {
    const rows = extractPreviewSampleRows(
      {
        meta: {
          preview_sample: {
            rows: [{ id: 3, amount: 300 }],
          },
        },
      },
      10,
    );

    expect(rows).toEqual([{ id: 3, amount: 300 }]);
  });

  it('builds resource-specific preview request body', () => {
    expect(
      buildDatasetPreviewRequestBody({
        datasetId: 'dataset-1',
        resourceKey: 'public.orders',
        limit: 10,
      }),
    ).toEqual({
      dataset_id: 'dataset-1',
      resource_key: 'public.orders',
      limit: 10,
    });
  });
});
