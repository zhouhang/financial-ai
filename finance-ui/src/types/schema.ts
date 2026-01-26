/**
 * TypeScript type definitions for schemas
 */

export enum WorkType {
  DATA_PREPARATION = 'data_preparation',
  RECONCILIATION = 'reconciliation',
}

export enum SchemaStatus {
  DRAFT = 'draft',
  PUBLISHED = 'published',
}

export interface Schema {
  id: number;
  user_id: number;
  name_cn: string;
  type_key: string;
  work_type: WorkType;
  schema_path: string;
  config_path: string;
  version: string;
  status: SchemaStatus;
  is_public: boolean;
  callback_url?: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface SchemaDetail extends Schema {
  schema_content?: Record<string, any>;
}

export interface CreateSchemaRequest {
  name_cn: string;
  work_type: WorkType;
  callback_url?: string;
  description?: string;
}

export interface UpdateSchemaRequest {
  name_cn?: string;
  schema_content?: Record<string, any>;
  status?: SchemaStatus;
  callback_url?: string;
  description?: string;
}

export interface SchemaListResponse {
  total: number;
  schemas: Schema[];
}

export interface SchemaState {
  schemas: Schema[];
  currentSchema: SchemaDetail | null;
  loading: boolean;
  fetchSchemas: (filters?: SchemaFilters) => Promise<void>;
  createSchema: (data: CreateSchemaRequest) => Promise<Schema>;
  updateSchema: (id: number, data: UpdateSchemaRequest) => Promise<Schema>;
  deleteSchema: (id: number) => Promise<void>;
  getSchema: (id: number) => Promise<SchemaDetail>;
}

export interface SchemaFilters {
  work_type?: WorkType;
  status?: SchemaStatus;
  skip?: number;
  limit?: number;
}
