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

interface ActiveReconRule {
  recon: {
    key_columns: {
      mappings: unknown[];
    };
    compare_columns: {
      columns: unknown[];
    };
  };
}

interface NormalizedReconPair {
  leftField: string;
  rightField: string;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function findFirstActiveRule(reconRuleJson: Record<string, unknown>): ActiveReconRule | null {
  const rules = reconRuleJson.rules;
  if (!Array.isArray(rules)) return null;

  const activeRule = rules.find((rule) => isRecord(rule) && rule.enabled !== false);
  if (!isRecord(activeRule)) return null;

  const recon = activeRule.recon;
  if (!isRecord(recon)) return null;

  const keyColumns = recon.key_columns;
  const compareColumns = recon.compare_columns;
  if (!isRecord(keyColumns) || !isRecord(compareColumns)) return null;
  if (!Array.isArray(keyColumns.mappings) || !Array.isArray(compareColumns.columns)) {
    return null;
  }

  return {
    recon: {
      key_columns: {
        mappings: keyColumns.mappings,
      },
      compare_columns: {
        columns: compareColumns.columns,
      },
    },
  };
}

function normalizeCurrentPairs(pairs: ReconFieldPairDraft[]): NormalizedReconPair[] {
  return pairs.map((pair) => ({
    leftField: pair.leftField.trim(),
    rightField: pair.rightField.trim(),
  }));
}

function normalizeJsonMatchPairs(activeRule: ActiveReconRule): NormalizedReconPair[] {
  return activeRule.recon.key_columns.mappings
    .filter(isRecord)
    .map((mapping) => ({
      leftField: typeof mapping.source_field === 'string' ? mapping.source_field.trim() : '',
      rightField: typeof mapping.target_field === 'string' ? mapping.target_field.trim() : '',
    }))
    .filter((pair) => pair.leftField && pair.rightField);
}

function normalizeJsonComparePairs(activeRule: ActiveReconRule): NormalizedReconPair[] {
  return activeRule.recon.compare_columns.columns
    .filter(isRecord)
    .map((column) => ({
      leftField: typeof column.source_column === 'string' ? column.source_column.trim() : '',
      rightField: typeof column.target_column === 'string' ? column.target_column.trim() : '',
    }))
    .filter((pair) => pair.leftField && pair.rightField);
}

function pairKey(pair: NormalizedReconPair): string {
  return `${pair.leftField}\u0000${pair.rightField}`;
}

function missingJsonPairMessage(
  pairType: '匹配' | '对比',
  pair: NormalizedReconPair,
  leftFieldLabelMap: Record<string, string> | undefined,
  rightFieldLabelMap: Record<string, string> | undefined,
): string {
  const leftField = displayFieldName(pair.leftField, leftFieldLabelMap);
  const rightField = displayFieldName(pair.rightField, rightFieldLabelMap);
  return `JSON 缺少${pairType}字段「${leftField} ↔ ${rightField}」。`;
}

function extraJsonPairMessage(
  pairType: '匹配' | '对比',
  pair: NormalizedReconPair,
  leftFieldLabelMap: Record<string, string> | undefined,
  rightFieldLabelMap: Record<string, string> | undefined,
): string {
  const leftField = displayFieldName(pair.leftField, leftFieldLabelMap);
  const rightField = displayFieldName(pair.rightField, rightFieldLabelMap);
  return `JSON 包含未配置的${pairType}字段「${leftField} ↔ ${rightField}」。`;
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

  const activeRule = findFirstActiveRule(input.reconRuleJson);
  if (!activeRule) {
    return {
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 结构不完整，请重新生成对账字段配置。',
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

  const currentMatchPairs = normalizeCurrentPairs(completeMatchPairs);
  const currentComparePairs = normalizeCurrentPairs(completeComparePairs);
  const jsonMatchPairs = normalizeJsonMatchPairs(activeRule);
  const jsonComparePairs = normalizeJsonComparePairs(activeRule);
  const currentMatchPairKeys = new Set(currentMatchPairs.map(pairKey));
  const currentComparePairKeys = new Set(currentComparePairs.map(pairKey));
  const jsonMatchPairKeys = new Set(jsonMatchPairs.map(pairKey));
  const jsonComparePairKeys = new Set(jsonComparePairs.map(pairKey));
  const jsonPairDetails = [
    ...currentMatchPairs
      .filter((pair) => !jsonMatchPairKeys.has(pairKey(pair)))
      .map((pair) =>
        missingJsonPairMessage('匹配', pair, input.leftFieldLabelMap, input.rightFieldLabelMap),
      ),
    ...currentComparePairs
      .filter((pair) => !jsonComparePairKeys.has(pairKey(pair)))
      .map((pair) =>
        missingJsonPairMessage('对比', pair, input.leftFieldLabelMap, input.rightFieldLabelMap),
      ),
    ...jsonMatchPairs
      .filter((pair) => !currentMatchPairKeys.has(pairKey(pair)))
      .map((pair) =>
        extraJsonPairMessage('匹配', pair, input.leftFieldLabelMap, input.rightFieldLabelMap),
      ),
    ...jsonComparePairs
      .filter((pair) => !currentComparePairKeys.has(pairKey(pair)))
      .map((pair) =>
        extraJsonPairMessage('对比', pair, input.leftFieldLabelMap, input.rightFieldLabelMap),
      ),
  ];
  const uniqueJsonPairDetails = Array.from(new Set(jsonPairDetails));
  if (uniqueJsonPairDetails.length > 0) {
    return {
      ok: false,
      status: 'failed',
      message: '对账规则 JSON 与当前字段配置不一致，请重新生成或查看 JSON。',
      details: uniqueJsonPairDetails,
    };
  }

  return {
    ok: true,
    status: RECON_STRUCTURE_CHECK_STATUS,
    message: RECON_STRUCTURE_CHECK_SUMMARY,
    details: [],
  };
}
