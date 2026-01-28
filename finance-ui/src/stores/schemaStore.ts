/**
 * Schema state management with Zustand
 * Note: All schema operations are now handled through Dify API
 * This store only manages local schema state
 */
import { create } from 'zustand';
import {
  SchemaState,
  Schema,
  SchemaDetail,
} from '@/types/schema';

export const useSchemaStore = create<SchemaState>((set) => ({
  schemas: [],
  currentSchema: null,
  loading: false,

  // All schema operations are now handled through Dify chat
  // These methods update local state based on Dify responses

  setSchemas: (schemas: Schema[]) => {
    set({ schemas });
  },

  addSchema: (schema: Schema) => {
    set((state) => ({
      schemas: [schema, ...state.schemas],
    }));
  },

  updateSchemaInList: (id: number, schema: Schema) => {
    set((state) => ({
      schemas: state.schemas.map((s) => (s.id === id ? schema : s)),
    }));
  },

  removeSchema: (id: number) => {
    set((state) => ({
      schemas: state.schemas.filter((s) => s.id !== id),
    }));
  },

  setCurrentSchema: (schema: SchemaDetail | null) => {
    set({ currentSchema: schema });
  },

  setLoading: (loading: boolean) => {
    set({ loading });
  },

  // Legacy methods - kept for compatibility but should not be called directly
  fetchSchemas: async () => {
    console.warn('Schema operations should be handled through Dify chat interface');
    throw new Error('Please use Dify chat interface for schema operations');
  },

  createSchema: async () => {
    console.warn('Schema operations should be handled through Dify chat interface');
    throw new Error('Please use Dify chat interface for schema operations');
  },

  updateSchema: async () => {
    console.warn('Schema operations should be handled through Dify chat interface');
    throw new Error('Please use Dify chat interface for schema operations');
  },

  deleteSchema: async () => {
    console.warn('Schema operations should be handled through Dify chat interface');
    throw new Error('Please use Dify chat interface for schema operations');
  },

  getSchema: async () => {
    console.warn('Schema operations should be handled through Dify chat interface');
    throw new Error('Please use Dify chat interface for schema operations');
  },
}));
