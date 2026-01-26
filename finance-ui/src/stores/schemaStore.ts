/**
 * Schema state management with Zustand
 */
import { create } from 'zustand';
import { schemaApi } from '@/api/schemas';
import {
  SchemaState,
  Schema,
  SchemaDetail,
  CreateSchemaRequest,
  UpdateSchemaRequest,
  SchemaFilters,
} from '@/types/schema';

export const useSchemaStore = create<SchemaState>((set, get) => ({
  schemas: [],
  currentSchema: null,
  loading: false,

  fetchSchemas: async (filters?: SchemaFilters) => {
    set({ loading: true });
    try {
      const response = await schemaApi.getSchemas(filters);
      set({ schemas: response.schemas, loading: false });
    } catch (error) {
      console.error('Failed to fetch schemas:', error);
      set({ loading: false });
      throw error;
    }
  },

  createSchema: async (data: CreateSchemaRequest): Promise<Schema> => {
    set({ loading: true });
    try {
      const schema = await schemaApi.createSchema(data);
      set((state) => ({
        schemas: [schema, ...state.schemas],
        loading: false,
      }));
      return schema;
    } catch (error) {
      console.error('Failed to create schema:', error);
      set({ loading: false });
      throw error;
    }
  },

  updateSchema: async (id: number, data: UpdateSchemaRequest): Promise<Schema> => {
    set({ loading: true });
    try {
      const schema = await schemaApi.updateSchema(id, data);
      set((state) => ({
        schemas: state.schemas.map((s) => (s.id === id ? schema : s)),
        loading: false,
      }));
      return schema;
    } catch (error) {
      console.error('Failed to update schema:', error);
      set({ loading: false });
      throw error;
    }
  },

  deleteSchema: async (id: number) => {
    set({ loading: true });
    try {
      await schemaApi.deleteSchema(id);
      set((state) => ({
        schemas: state.schemas.filter((s) => s.id !== id),
        loading: false,
      }));
    } catch (error) {
      console.error('Failed to delete schema:', error);
      set({ loading: false });
      throw error;
    }
  },

  getSchema: async (id: number): Promise<SchemaDetail> => {
    set({ loading: true });
    try {
      const schema = await schemaApi.getSchema(id);
      set({ currentSchema: schema, loading: false });
      return schema;
    } catch (error) {
      console.error('Failed to get schema:', error);
      set({ loading: false });
      throw error;
    }
  },
}));
