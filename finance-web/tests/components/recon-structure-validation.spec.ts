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

const validRule = { schema_version: '1.6', rules: [] };
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
    expect(result.message).toBe('请先完成对账字段配置，生成可保存的对账规则 JSON。');
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
    expect(result.message).toBe('请至少配置一组完整的匹配字段。');
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
    expect(result.message).toBe('请至少配置一组完整的对比字段。');
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
    expect(result.message).toBe('对账规则字段不存在: 右侧字段「缺失平台单号」不在第二步输出字段中。');
    expect(result.details).toEqual(['右侧字段「缺失平台单号」不在第二步输出字段中。']);
  });
});
