type RunStatusInput = {
  executionStatus?: string | null;
};

export type ReconRunPrimaryAction = 'retry' | 'digest';

export function normalizedExecutionStatus(input: RunStatusInput | string | null | undefined): string {
  const value = typeof input === 'string' ? input : input?.executionStatus;
  return String(value ?? '').trim().toLowerCase();
}

export function canRetryRun(input: RunStatusInput | string | null | undefined): boolean {
  return normalizedExecutionStatus(input) === 'failed';
}

export function canDigestRun(input: RunStatusInput | string | null | undefined): boolean {
  return normalizedExecutionStatus(input) === 'success';
}

export function runActionForStatus(
  input: RunStatusInput | string | null | undefined,
): ReconRunPrimaryAction | null {
  if (canRetryRun(input)) return 'retry';
  if (canDigestRun(input)) return 'digest';
  return null;
}
