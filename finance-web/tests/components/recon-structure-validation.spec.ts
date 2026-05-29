import { describe, expect, it } from 'vitest';

import {
  RECON_STRUCTURE_CHECK_STATUS,
  RECON_STRUCTURE_CHECK_SUMMARY,
  validateReconStructureForSave,
} from '../../src/components/recon/reconStructureValidation';
import type { OutputFieldDraft, ReconFieldPairDraft } from '../../src/components/recon/schemeWizardState';

function outputField(outputName: string): OutputFieldDraft {
  return {
    id: `field-${outputName}`,
    outputName,
    semanticRole: 'normal',
    valueMode: 'source_field',
    sourceDatasetId: '',
    sourceField: '',
    fixedValue: '',
    formula: '',
    concatDelimiter: '',
    concatParts: [],
  };
}

function pair(id: string, leftField: string, rightField: string): ReconFieldPairDraft {
  return { id, leftField, rightField };
}

const validRule = {
  schema_version: '1.6',
  rules: [
    {
      id: 'rule-1',
      enabled: true,
      recon: {
        key_columns: {
          mappings: [
            {
              source_field: 'biz_key',
              target_field: 'biz_key',
            },
          ],
        },
        compare_columns: {
          columns: [
            {
              source_column: 'amount',
              target_column: 'amount',
            },
          ],
        },
      },
    },
  ],
};
const leftFields = [outputField('biz_key'), outputField('amount')];
const rightFields = [outputField('biz_key'), outputField('amount')];

describe('validateReconStructureForSave', () => {
  it('passes when recon JSON and complete field pairs match output fields', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result).toEqual({
      ok: true,
      status: RECON_STRUCTURE_CHECK_STATUS,
      message: RECON_STRUCTURE_CHECK_SUMMARY,
      details: [],
    });
  });

  it('fails when recon JSON is missing', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: null,
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe('failed');
    expect(result.message).toBe('请先完成对账字段配置，生成可保存的对账规则 JSON。');
    expect(result.details).toEqual([]);
  });

  it('fails when recon JSON shape is incomplete', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: { schema_version: '1.6', rules: [] },
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result).toEqual({
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 结构不完整，请重新生成对账字段配置。',
      details: [],
    });
  });

  it('fails when every recon JSON rule is disabled', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: {
        schema_version: '1.6',
        rules: [
          {
            enabled: false,
            recon: {
              key_columns: {
                mappings: [{ source_field: 'biz_key', target_field: 'biz_key' }],
              },
              compare_columns: {
                columns: [{ source_column: 'amount', target_column: 'amount' }],
              },
            },
          },
        ],
      },
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result).toEqual({
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 结构不完整，请重新生成对账字段配置。',
      details: [],
    });
  });

  it('fails when no complete match pair exists', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', '')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe('failed');
    expect(result.message).toBe('请至少配置一组完整的匹配字段。');
    expect(result.details).toEqual([]);
  });

  it('fails when no complete compare pair exists', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', '', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe('failed');
    expect(result.message).toBe('请至少配置一组完整的对比字段。');
    expect(result.details).toEqual([]);
  });

  it('fails when a left field is not in the prepared left output fields', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'missing_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
      leftFieldLabelMap: { missing_key: '缺失业务单号' },
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe('failed');
    expect(result.message).toBe('对账规则字段不存在: 左侧字段「缺失业务单号」不在第二步输出字段中。');
    expect(result.details).toEqual(['左侧字段「缺失业务单号」不在第二步输出字段中。']);
  });

  it('fails when a right field is not in the prepared right output fields', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: validRule,
      matchFieldPairs: [pair('match-1', 'biz_key', 'missing_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
      rightFieldLabelMap: { missing_key: '缺失平台单号' },
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe('failed');
    expect(result.message).toBe('对账规则字段不存在: 右侧字段「缺失平台单号」不在第二步输出字段中。');
    expect(result.details).toEqual(['右侧字段「缺失平台单号」不在第二步输出字段中。']);
  });

  it('fails when recon JSON omits configured field pairs', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: {
        schema_version: '1.6',
        rules: [
          {
            recon: {
              key_columns: {
                mappings: [],
              },
              compare_columns: {
                columns: [],
              },
            },
          },
        ],
      },
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: leftFields,
      rightOutputFields: rightFields,
      leftFieldLabelMap: {
        biz_key: '客户订单号',
        amount: '含税销售金额',
      },
      rightFieldLabelMap: {
        biz_key: '商户订单号',
        amount: '订单金额',
      },
    });

    expect(result).toEqual({
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 与当前字段配置不一致，请重新生成或查看 JSON。',
      details: [
        'JSON 缺少匹配字段「客户订单号 ↔ 商户订单号」。',
        'JSON 缺少对比字段「含税销售金额 ↔ 订单金额」。',
      ],
    });
  });

  it('fails when recon JSON contains a stale unconfigured match pair', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: {
        schema_version: '1.6',
        rules: [
          {
            recon: {
              key_columns: {
                mappings: [
                  { source_field: 'biz_key', target_field: 'biz_key' },
                  { source_field: 'legacy_key', target_field: 'legacy_key' },
                ],
              },
              compare_columns: {
                columns: [{ source_column: 'amount', target_column: 'amount' }],
              },
            },
          },
        ],
      },
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: [...leftFields, outputField('legacy_key')],
      rightOutputFields: [...rightFields, outputField('legacy_key')],
      leftFieldLabelMap: {
        legacy_key: '客户订单号',
      },
      rightFieldLabelMap: {
        legacy_key: '商户订单号',
      },
    });

    expect(result).toEqual({
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 与当前字段配置不一致，请重新生成或查看 JSON。',
      details: ['JSON 包含未配置的匹配字段「客户订单号 ↔ 商户订单号」。'],
    });
  });

  it('fails when recon JSON contains a stale unconfigured compare pair', () => {
    const result = validateReconStructureForSave({
      reconRuleJson: {
        schema_version: '1.6',
        rules: [
          {
            recon: {
              key_columns: {
                mappings: [{ source_field: 'biz_key', target_field: 'biz_key' }],
              },
              compare_columns: {
                columns: [
                  { source_column: 'amount', target_column: 'amount' },
                  { source_column: 'legacy_amount', target_column: 'legacy_amount' },
                ],
              },
            },
          },
        ],
      },
      matchFieldPairs: [pair('match-1', 'biz_key', 'biz_key')],
      compareFieldPairs: [pair('compare-1', 'amount', 'amount')],
      leftOutputFields: [...leftFields, outputField('legacy_amount')],
      rightOutputFields: [...rightFields, outputField('legacy_amount')],
      leftFieldLabelMap: {
        legacy_amount: '含税销售金额',
      },
      rightFieldLabelMap: {
        legacy_amount: '订单金额',
      },
    });

    expect(result).toEqual({
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 与当前字段配置不一致，请重新生成或查看 JSON。',
      details: ['JSON 包含未配置的对比字段「含税销售金额 ↔ 订单金额」。'],
    });
  });
});
