import type { UserTaskRule } from '../types';

export type RuleEntryMode = 'upload' | 'dataset';

const VALID_ENTRY_MODES: RuleEntryMode[] = ['upload', 'dataset'];

type RuleLike = Partial<Pick<UserTaskRule, 'rule_type' | 'file_rule_code' | 'supported_entry_modes'>>;

export function normalizeSupportedEntryModes(rule: RuleLike | null | undefined): RuleEntryMode[] {
  const rawModes = Array.isArray(rule?.supported_entry_modes) ? rule?.supported_entry_modes : [];
  const normalizedModes = rawModes
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item): item is RuleEntryMode => VALID_ENTRY_MODES.includes(item as RuleEntryMode));

  if (normalizedModes.length > 0) {
    return Array.from(new Set(normalizedModes));
  }

  if ((rule?.rule_type || '').trim().toLowerCase() === 'file') {
    return ['upload'];
  }

  if ((rule?.file_rule_code || '').trim()) {
    return ['upload'];
  }

  return ['dataset'];
}

export function ruleSupportsEntryMode(
  rule: RuleLike | null | undefined,
  entryMode: RuleEntryMode,
): boolean {
  return normalizeSupportedEntryModes(rule).includes(entryMode);
}
