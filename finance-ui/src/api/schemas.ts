/**
 * Schema API
 */
import apiClient from './client';
import {
  Schema,
  SchemaDetail,
  CreateSchemaRequest,
  UpdateSchemaRequest,
  SchemaListResponse,
  SchemaFilters,
} from '@/types/schema';

export const schemaApi = {
  /**
   * Get list of schemas
   */
  getSchemas: async (filters?: SchemaFilters): Promise<SchemaListResponse> => {
    const response = await apiClient.get<SchemaListResponse>('/schemas', {
      params: filters,
    });
    return response.data;
  },

  /**
   * Create a new schema
   */
  createSchema: async (data: CreateSchemaRequest): Promise<Schema> => {
    const response = await apiClient.post<Schema>('/schemas', data);
    return response.data;
  },

  /**
   * Get schema details
   */
  getSchema: async (id: number): Promise<SchemaDetail> => {
    const response = await apiClient.get<SchemaDetail>(`/schemas/${id}`);
    return response.data;
  },

  /**
   * Update schema
   */
  updateSchema: async (id: number, data: UpdateSchemaRequest): Promise<Schema> => {
    const response = await apiClient.put<Schema>(`/schemas/${id}`, data);
    return response.data;
  },

  /**
   * Delete schema
   */
  deleteSchema: async (id: number): Promise<void> => {
    await apiClient.delete(`/schemas/${id}`);
  },

  /**
   * Generate type_key from Chinese name
   */
  generateTypeKey: async (nameCn: string): Promise<{ type_key: string }> => {
    const response = await apiClient.post<{ type_key: string }>('/schemas/generate-type-key', {
      name_cn: nameCn,
    });
    return response.data;
  },

  /**
   * Check if name_cn already exists for current user
   */
  checkNameExists: async (nameCn: string): Promise<{ exists: boolean }> => {
    const response = await apiClient.get<{ exists: boolean }>('/schemas/check-name-exists', {
      params: { name_cn: nameCn },
    });
    return response.data;
  },

  /**
   * Validate schema content structure
   */
  validateSchema: async (schemaContent: any): Promise<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  }> => {
    const response = await apiClient.post('/schemas/validate-content', {
      schema_content: schemaContent,
    });
    return response.data;
  },

  /**
   * Test schema execution with files
   */
  testSchema: async (
    schemaContent: any,
    filePaths: string[]
  ): Promise<{
    success: boolean;
    output_preview: any[][];
    errors: string[];
    execution_time: number;
  }> => {
    const response = await apiClient.post('/schemas/test', {
      schema_content: schemaContent,
      file_paths: filePaths,
    });
    return response.data;
  },
};
