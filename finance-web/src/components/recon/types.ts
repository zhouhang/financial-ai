export type ReconCenterTab = 'schemes' | 'tasks' | 'runs';

export type StartMode = 'upload' | 'source';

export type NoticeTone = 'info' | 'success' | 'warning';

export interface ReconRuleListItem {
  id: number;
  user_id?: string | null;
  task_id?: number | null;
  rule_code: string;
  name: string;
  rule_type: string;
  remark?: string;
  task_code: string;
  task_name: string;
  task_type: 'proc' | 'recon' | string;
  file_rule_code?: string;
  supported_entry_modes?: string[];
  updated_hint?: string;
}

export interface ReconAutoTaskItem {
  id: string;
  name: string;
  company: string;
  ruleCode: string;
  ruleName: string;
  schedule: string;
  dateOffset: string;
  ownerMode: string;
  channel: string;
  status: 'enabled' | 'paused';
}

export interface ReconRunItem {
  id: string;
  autoTaskId: string;
  taskName: string;
  triggerMode: string;
  businessDate: string;
  status: 'success' | 'running' | 'warning' | 'failed';
  dataReady: string;
  exceptionCount: number;
  closureStatus: string;
  startedAt: string;
  finishedAt: string;
}

export interface ReconExceptionItem {
  id: string;
  type: string;
  summary: string;
  owner: string;
  reminderStatus: string;
  feedback: string;
  handlingStatus: string;
}

export interface ReconSchemeListItem {
  id: string;
  schemeCode: string;
  name: string;
  description: string;
  fileRuleCode: string;
  procRuleCode: string;
  reconRuleCode: string;
  status: 'enabled' | 'paused';
  updatedAt: string;
  createdAt: string;
  raw: Record<string, unknown>;
}

export interface ReconTaskListItem {
  id: string;
  planCode: string;
  name: string;
  schemeCode: string;
  schemeName: string;
  scheduleType: string;
  scheduleExpr: string;
  bizDateOffset: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  channelConfigId: string;
  summaryRecipient: string;
  ownerSummary: string;
  status: 'enabled' | 'paused';
  updatedAt: string;
  createdAt: string;
  raw: Record<string, unknown>;
}

export interface ReconCenterRunItem {
  id: string;
  runCode: string;
  schemeCode: string;
  planCode: string;
  schemeName: string;
  planName: string;
  executionStatus: string;
  triggerType: string;
  entryMode: string;
  anomalyCount: number;
  failedStage: string;
  failedReason: string;
  startedAt: string;
  finishedAt: string;
  raw: Record<string, unknown>;
}

export interface ReconRunExceptionDetail {
  id: string;
  anomalyType: string;
  summary: string;
  ownerName: string;
  reminderStatus: string;
  processingStatus: string;
  fixStatus: string;
  latestFeedback: string;
  isClosed: boolean;
  createdAt: string;
  updatedAt: string;
  raw: Record<string, unknown>;
}

export interface ReconSchemeListItem {
  id: string;
  schemeCode: string;
  name: string;
  description: string;
  fileRuleCode: string;
  procRuleCode: string;
  reconRuleCode: string;
  status: 'enabled' | 'paused';
  updatedAt: string;
  createdAt: string;
  raw: Record<string, unknown>;
}

export interface ReconTaskListItem {
  id: string;
  planCode: string;
  name: string;
  schemeCode: string;
  schemeName: string;
  scheduleType: string;
  scheduleExpr: string;
  bizDateOffset: string;
  leftTimeSemantic: string;
  rightTimeSemantic: string;
  channelConfigId: string;
  ownerSummary: string;
  status: 'enabled' | 'paused';
  updatedAt: string;
  createdAt: string;
  raw: Record<string, unknown>;
}

export interface ReconCenterRunItem {
  id: string;
  runCode: string;
  schemeCode: string;
  planCode: string;
  schemeName: string;
  planName: string;
  executionStatus: string;
  triggerType: string;
  entryMode: string;
  anomalyCount: number;
  failedStage: string;
  failedReason: string;
  startedAt: string;
  finishedAt: string;
  raw: Record<string, unknown>;
}

export interface ReconRunExceptionDetail {
  id: string;
  anomalyType: string;
  summary: string;
  ownerName: string;
  reminderStatus: string;
  processingStatus: string;
  fixStatus: string;
  latestFeedback: string;
  isClosed: boolean;
  createdAt: string;
  updatedAt: string;
  raw: Record<string, unknown>;
}

export interface LaunchNotice {
  tone: NoticeTone;
  text: string;
}

export function cn(...classNames: Array<string | false | null | undefined>) {
  return classNames.filter(Boolean).join(' ');
}
