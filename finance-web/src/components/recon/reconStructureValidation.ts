import type { OutputFieldDraft, ReconFieldPairDraft } from './schemeWizardState';

export const RECON_STRUCTURE_CHECK_STATUS = 'structure_checked';
export const RECON_STRUCTURE_CHECK_SUMMARY = '已完成对账规则结构校验，待首次真实运行验证';

export interface ReconStructureValidationInput {
  reconRuleJson: Record<string, unknown> | null | undefined;
  matchFieldPairs: ReconFieldPairDraft[];
  compareFieldPairs: ReconFieldPairDraft[];
  leftOutputFields: OutputFieldDraft[];
  rightOutputFields: OutputFieldDraft[];
  leftFieldLabelMap?: Record<string, string>;
  rightFieldLabelMap?: Record<string, string>;
}

export interface ReconStructureValidationResult {
  ok: boolean;
  status: typeof RECON_STRUCTURE_CHECK_STATUS | 'failed';
  message: string;
  details: string[];
}

function completePairs(pairs: ReconFieldPairDraft[]): ReconFieldPairDraft[] {
  return pairs.filter((pair) => pair.leftField.trim() && pair.rightField.trim());
}

function outputFieldNameSet(fields: OutputFieldDraft[]): Set<string> {
  return new Set(fields.map((field) => field.outputName.trim()).filter(Boolean));
}

function displayFieldName(fieldName: string, labelMap: Record<string, string> | undefined): string {
  const normalized = fieldName.trim();
  return labelMap?.[normalized]?.trim() || normalized;
}

function missingFieldMessage(sideLabel: string, fieldName: string): string {
  return `${sideLabel}字段「${fieldName}」不在第二步输出字段中。`;
}

export function validateReconStructureForSave(
  input: ReconStructureValidationInput,
): ReconStructureValidationResult {
  if (!input.reconRuleJson || Object.keys(input.reconRuleJson).length === 0) {
    return {
      ok: false,
      status: 'failed',
      message: '请先完成对账字段配置，生成可保存的对账规则 JSON。',
      details: [],
    };
  }

  const completeMatchPairs = completePairs(input.matchFieldPairs);
  if (completeMatchPairs.length === 0) {
    return {
      ok: false,
      status: 'failed',
      message: '请至少配置一组完整的匹配字段。',
      details: [],
    };
  }

  const completeComparePairs = completePairs(input.compareFieldPairs);
  if (completeComparePairs.length === 0) {
    return {
      ok: false,
      status: 'failed',
      message: '请至少配置一组完整的对比字段。',
      details: [],
    };
  }

  const leftOutputNames = outputFieldNameSet(input.leftOutputFields);
  const rightOutputNames = outputFieldNameSet(input.rightOutputFields);
  const allPairs = [...completeMatchPairs, ...completeComparePairs];
  const details: string[] = [];

  allPairs.forEach((pair) => {
    const leftField = pair.leftField.trim();
    const rightField = pair.rightField.trim();
    if (!leftOutputNames.has(leftField)) {
      details.push(missingFieldMessage('左侧', displayFieldName(leftField, input.leftFieldLabelMap)));
    }
    if (!rightOutputNames.has(rightField)) {
      details.push(missingFieldMessage('右侧', displayFieldName(rightField, input.rightFieldLabelMap)));
    }
  });

  const uniqueDetails = Array.from(new Set(details));
  if (uniqueDetails.length > 0) {
    return {
      ok: false,
      status: 'failed',
      message: `对账规则字段不存在: ${uniqueDetails[0]}`,
      details: uniqueDetails,
    };
  }

  return {
    ok: true,
    status: RECON_STRUCTURE_CHECK_STATUS,
    message: RECON_STRUCTURE_CHECK_SUMMARY,
    details: [],
  };
}
