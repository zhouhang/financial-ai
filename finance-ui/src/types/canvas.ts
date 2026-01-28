/**
 * TypeScript type definitions for Canvas functionality
 */

import { WorkType } from './schema';

export interface SchemaMetadata {
  name_cn: string;
  type_key: string;
  work_type: WorkType;
  description?: string;
}

export interface UploadedFile {
  id: string;
  filename: string;
  path: string;
  sheets: SheetData[];
}

export interface SheetData {
  name: string;
  headers: string[];
  rows: any[][];
  total_rows: number;
  total_columns: number;
}

export interface SchemaStep {
  id: string;
  type: StepType;
  name: string;
  config: StepConfig;
  order: number;
}

export type StepType = 'extract' | 'transform' | 'validate' | 'conditional' | 'merge' | 'output';

export interface StepConfig {
  // Dynamic based on step type
  [key: string]: any;
}

export interface ExtractConfig extends StepConfig {
  source_file: string;
  source_sheet: string;
  source_columns: string[];
  target_name: string;
}

export interface TransformConfig extends StepConfig {
  source: string;
  operation: 'map' | 'filter' | 'calculate';
  expression: string;
  target_column?: string;
}

export interface ValidateConfig extends StepConfig {
  source: string;
  rules: ValidationRule[];
}

export interface ValidationRule {
  column: string;
  rule_type: 'required' | 'unique' | 'range' | 'pattern';
  parameters: any;
}

export interface ConditionalConfig extends StepConfig {
  condition: {
    source_file: string;
    source_column: string;
    operator: 'equals' | 'contains' | 'greater_than' | 'less_than' | 'not_equals';
    value: string;
  };
  then_action: {
    source_file: string;
    source_column: string;
    target_file: string;
    target_column: string;
  };
  else_action?: {
    source_file: string;
    source_column: string;
    target_file: string;
    target_column: string;
  };
}

export interface MergeConfig extends StepConfig {
  sources: string[];
  merge_type: 'inner' | 'left' | 'right' | 'outer';
  join_keys: { [source: string]: string };
  target_name: string;
}

export interface OutputConfig extends StepConfig {
  source: string;
  output_columns: string[];
  output_format: 'excel' | 'csv' | 'json';
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface TestResult {
  success: boolean;
  output_preview: any[][];
  errors: string[];
  execution_time: number;
}

export interface HistoryState {
  steps: SchemaStep[];
  uploadedFiles: UploadedFile[];
  timestamp: number;
}

export interface CanvasState {
  uploadedFiles: UploadedFile[];
  steps: SchemaStep[];
  currentStepIndex: number;
  history: HistoryState[];
  historyIndex: number;

  // Actions
  uploadFiles: (files: File[]) => Promise<void>;
  addStep: (step: SchemaStep) => void;
  updateStep: (index: number, step: SchemaStep) => void;
  deleteStep: (index: number) => void;
  reorderSteps: (fromIndex: number, toIndex: number) => void;
  setCurrentStepIndex: (index: number) => void;
  undo: () => void;
  redo: () => void;
  validateSchema: () => Promise<ValidationResult>;
  testSchema: () => Promise<TestResult>;
  saveSchema: (metadata: SchemaMetadata) => Promise<any>;
  reset: () => void;
}

export interface Schema {
  id: number;
  name_cn: string;
  type_key: string;
  work_type: WorkType;
  schema_path: string;
  config_path: string;
  version: string;
  status: string;
  description?: string;
  created_at: string;
  updated_at: string;
}
