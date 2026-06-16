import { describe, expect, it } from 'vitest';

import { buildDatasetSamplePayloadForTest } from '../../src/components/ReconWorkspace';
import { filterBrowserCollectionFieldItems } from '../../src/components/recon/browserCollectionSchema';
import { extractDatasetPreviewRows } from '../../src/components/recon/datasetPreview';
import { normalizeCandidateDataset } from '../../src/components/recon/SchemeWizardTargetProcStep';
import {
  applyRuleGenerationEventToDraft,
  createEmptyAiProcSideDraft,
  serializeSchemeSourceForRuleGeneration,
} from '../../src/components/recon/ruleGenerationState';

describe('normalizeCandidateDataset', () => {
  it('保留 browser_playbook 候选数据集', () => {
    const candidate = normalizeCandidateDataset({
      id: 'dataset-browser-1',
      dataset_code: 'browser-collection-af74d2b25a',
      dataset_name: '单枪旗舰店-收支账单',
      resource_key: 'browser-collection-af74d2b25a@1',
      source_id: 'source-browser-1',
      source_name: '单枪旗舰店-收支账单',
      source_kind: 'browser_playbook',
      provider_code: 'browser_playbook',
      publish_status: 'published',
      status: 'active',
      enabled: true,
      business_name: '单枪旗舰店-收支账单',
    });

    expect(candidate).toMatchObject({
      id: 'dataset-browser-1',
      name: '单枪旗舰店-收支账单',
      sourceId: 'source-browser-1',
      sourceKind: 'browser_playbook',
      providerCode: 'browser_playbook',
      resourceKey: 'browser-collection-af74d2b25a@1',
    });
  });

  it('browser_playbook 候选数据集不把 storage/source_type 当作业务字段', () => {
    const candidate = normalizeCandidateDataset({
      id: 'dataset-browser-1',
      dataset_code: 'browser-collection-af74d2b25a',
      dataset_name: '单枪旗舰店-收支账单',
      resource_key: 'browser-collection-af74d2b25a@1',
      source_id: 'source-browser-1',
      source_name: '单枪旗舰店-收支账单',
      source_kind: 'browser_playbook',
      provider_code: 'browser_playbook',
      publish_status: 'published',
      status: 'active',
      enabled: true,
      schema_summary: {
        storage: 'browser_collection_records',
        source_type: 'browser_collection_records',
      },
      extract_config: {
        storage: 'browser_collection_records',
        source_type: 'browser_collection_records',
      },
    });

    expect(candidate?.schemaSummary).toEqual({});
    expect(candidate?.extractConfig).toMatchObject({
      storage: 'browser_collection_records',
      source_type: 'browser_collection_records',
    });
  });

  it('browser_playbook 技术 schema 不生成 storage/source_type 假样例', () => {
    const payload = buildDatasetSamplePayloadForTest(
      {
        id: 'dataset-browser-1',
        name: '亨创数娱充值店-收支账单',
        sourceId: 'source-browser-1',
        sourceName: '亨创数娱充值店-收支账单',
        sourceKind: 'browser_playbook',
        providerCode: 'browser_playbook',
        datasetCode: 'browser-collection-04576bddc3',
        resourceKey: 'browser-collection-04576bddc3@1',
        schemaSummary: {
          storage: 'browser_collection_records',
          source_type: 'browser_collection_records',
        },
        extractConfig: {
          storage: 'browser_collection_records',
          source_type: 'browser_collection_records',
        },
      },
      'left',
    );

    expect(payload.sample_rows).toEqual([]);
  });

  it('browser_playbook 字段列表不把 storage/source_type 当作业务字段', () => {
    const fields = filterBrowserCollectionFieldItems(
      [
        { raw_name: 'storage', display_name: 'storage' },
        { raw_name: 'source_type', display_name: 'source_type' },
        { raw_name: '账期', display_name: '账期' },
      ],
      {
        sourceKind: 'browser_playbook',
        schemaSummary: {
          storage: 'browser_collection_records',
          source_type: 'browser_collection_records',
        },
      },
    );

    expect(fields).toEqual([{ raw_name: '账期', display_name: '账期' }]);
  });

  it('browser_playbook preview 返回采集记录时提取 payload 样例行', () => {
    const rows = extractDatasetPreviewRows(
      {
        rows: [
          {
            payload: {
              订单号: 'JD1001',
              实收金额: '12.30',
            },
          },
        ],
      },
      10,
    );

    expect(rows).toEqual([{ 订单号: 'JD1001', 实收金额: '12.30' }]);
  });

  it('规则生成 payload 不把 browser_playbook 技术 schema 作为字段候选', () => {
    const payload = serializeSchemeSourceForRuleGeneration({
      id: 'dataset-browser-1',
      name: '亨创数娱充值店-收支账单',
      sourceId: 'source-browser-1',
      sourceName: '亨创数娱充值店-收支账单',
      sourceKind: 'browser_playbook',
      providerCode: 'browser_playbook',
      datasetCode: 'browser-collection-04576bddc3',
      resourceKey: 'browser-collection-04576bddc3@1',
      fieldLabelMap: {
        storage: 'storage',
        source_type: 'source_type',
      },
      schemaSummary: {
        storage: 'browser_collection_records',
        source_type: 'browser_collection_records',
      },
    });

    expect(payload.fields).toEqual([]);
  });

  it('AI 输出预览不把 __tally_source_record 当作用户字段', () => {
    const draft = createEmptyAiProcSideDraft();

    const result = applyRuleGenerationEventToDraft(draft, '左侧', {
      event: 'graph_completed',
      proc_rule_json: {
        steps: [],
      },
      output_fields: [
        { name: 'biz_key', label: '业务主键' },
        { name: '__tally_source_record', label: '__tally_source_record' },
      ],
      output_preview_rows: [
        {
          biz_key: 'ORD-001',
          __tally_source_record: { order_no: 'ORD-001', amount: 100 },
        },
      ],
      assumptions: [],
      validations: [],
      warnings: [],
    });

    expect(result.draft.outputRows).toEqual([{ biz_key: 'ORD-001' }]);
    expect(result.outputFields.map((field) => field.outputName)).toEqual(['biz_key']);
    expect(result.draft.outputFieldLabelMap).toEqual({ biz_key: '业务主键' });
  });
});
