/**
 * Canvas state management with Zustand
 */
import { create } from 'zustand';
import {
  CanvasState,
  SchemaStep,
  UploadedFile,
  HistoryState,
  ValidationResult,
  TestResult,
  SchemaMetadata,
} from '@/types/canvas';
import { schemaApi } from '@/api/schemas';

const MAX_HISTORY = 50;

export const useCanvasStore = create<CanvasState>((set, get) => ({
  uploadedFiles: [],
  steps: [],
  currentStepIndex: -1,
  history: [],
  historyIndex: -1,

  uploadFiles: async (files: File[]) => {
    // TODO: Implement file upload logic
    // For now, create mock uploaded files
    const newFiles: UploadedFile[] = files.map((file, index) => ({
      id: `file-${Date.now()}-${index}`,
      filename: file.name,
      path: `/uploads/${file.name}`,
      sheets: [
        {
          name: 'Sheet1',
          headers: ['Column1', 'Column2', 'Column3'],
          rows: [
            ['Data1', 'Data2', 'Data3'],
            ['Data4', 'Data5', 'Data6'],
          ],
          total_rows: 2,
          total_columns: 3,
        },
      ],
    }));

    set((state) => {
      const newState = {
        uploadedFiles: [...state.uploadedFiles, ...newFiles],
      };
      return {
        ...newState,
        ...saveToHistory(state, newState),
      };
    });
  },

  addStep: (step: SchemaStep) => {
    set((state) => {
      const newSteps = [...state.steps, { ...step, order: state.steps.length }];
      const newState = {
        steps: newSteps,
        currentStepIndex: newSteps.length - 1,
      };
      return {
        ...newState,
        ...saveToHistory(state, newState),
      };
    });
  },

  updateStep: (index: number, step: SchemaStep) => {
    set((state) => {
      const newSteps = [...state.steps];
      newSteps[index] = { ...step, order: index };
      const newState = {
        steps: newSteps,
      };
      return {
        ...newState,
        ...saveToHistory(state, newState),
      };
    });
  },

  deleteStep: (index: number) => {
    set((state) => {
      const newSteps = state.steps.filter((_, i) => i !== index);
      // Reorder remaining steps
      newSteps.forEach((step, i) => {
        step.order = i;
      });
      const newState = {
        steps: newSteps,
        currentStepIndex: state.currentStepIndex >= newSteps.length ? newSteps.length - 1 : state.currentStepIndex,
      };
      return {
        ...newState,
        ...saveToHistory(state, newState),
      };
    });
  },

  reorderSteps: (fromIndex: number, toIndex: number) => {
    set((state) => {
      const newSteps = [...state.steps];
      const [movedStep] = newSteps.splice(fromIndex, 1);
      newSteps.splice(toIndex, 0, movedStep);
      // Reorder all steps
      newSteps.forEach((step, i) => {
        step.order = i;
      });
      const newState = {
        steps: newSteps,
      };
      return {
        ...newState,
        ...saveToHistory(state, newState),
      };
    });
  },

  setCurrentStepIndex: (index: number) => {
    set({ currentStepIndex: index });
  },

  undo: () => {
    set((state) => {
      if (state.historyIndex <= 0) return state;

      const newIndex = state.historyIndex - 1;
      const historyState = state.history[newIndex];

      return {
        steps: historyState.steps,
        uploadedFiles: historyState.uploadedFiles,
        historyIndex: newIndex,
      };
    });
  },

  redo: () => {
    set((state) => {
      if (state.historyIndex >= state.history.length - 1) return state;

      const newIndex = state.historyIndex + 1;
      const historyState = state.history[newIndex];

      return {
        steps: historyState.steps,
        uploadedFiles: historyState.uploadedFiles,
        historyIndex: newIndex,
      };
    });
  },

  validateSchema: async (): Promise<ValidationResult> => {
    const state = get();
    const schemaContent = buildSchemaContent(state);

    try {
      const result = await schemaApi.validateSchema(schemaContent);
      return result;
    } catch (error) {
      console.error('Schema validation error:', error);
      return {
        valid: false,
        errors: [error instanceof Error ? error.message : 'Validation failed'],
        warnings: [],
      };
    }
  },

  testSchema: async (): Promise<TestResult> => {
    const state = get();
    const schemaContent = buildSchemaContent(state);
    const filePaths = state.uploadedFiles.map((f) => f.path);

    try {
      const result = await schemaApi.testSchema(schemaContent, filePaths);
      return result;
    } catch (error) {
      console.error('Schema test error:', error);
      return {
        success: false,
        output_preview: [],
        errors: [error instanceof Error ? error.message : 'Test failed'],
        execution_time: 0,
      };
    }
  },

  saveSchema: async (metadata: SchemaMetadata) => {
    const state = get();
    const schemaContent = buildSchemaContent(state);

    try {
      // Create schema with metadata
      const schema = await schemaApi.createSchema({
        name_cn: metadata.name_cn,
        work_type: metadata.work_type,
        description: metadata.description,
      });

      // Update schema with content
      await schemaApi.updateSchema(schema.id, {
        schema_content: schemaContent,
      });

      return schema;
    } catch (error) {
      console.error('Schema save error:', error);
      throw error;
    }
  },

  reset: () => {
    set({
      uploadedFiles: [],
      steps: [],
      currentStepIndex: -1,
      history: [],
      historyIndex: -1,
    });
  },
}));

// Helper function to save state to history
function saveToHistory(
  currentState: CanvasState,
  newState: Partial<CanvasState>
): Partial<CanvasState> {
  const historyState: HistoryState = {
    steps: newState.steps || currentState.steps,
    uploadedFiles: newState.uploadedFiles || currentState.uploadedFiles,
    timestamp: Date.now(),
  };

  // Remove any history after current index (for redo)
  const newHistory = currentState.history.slice(0, currentState.historyIndex + 1);
  newHistory.push(historyState);

  // Limit history size
  if (newHistory.length > MAX_HISTORY) {
    newHistory.shift();
  }

  return {
    history: newHistory,
    historyIndex: newHistory.length - 1,
  };
}

// Helper function to build schema content from canvas state
function buildSchemaContent(state: CanvasState): any {
  return {
    version: '1.0',
    schema_type: 'step_based',
    metadata: {
      project_name: 'Canvas Schema',
      author: 'User',
      description: 'Schema created from canvas',
    },
    processing_steps: state.steps.map((step) => ({
      step_name: step.name,
      step_type: step.type,
      config: step.config,
      order: step.order,
    })),
    uploaded_files: state.uploadedFiles.map((file) => ({
      filename: file.filename,
      path: file.path,
      sheets: file.sheets.map((sheet) => sheet.name),
    })),
  };
}
