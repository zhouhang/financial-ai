/**
 * Canvas state management with Zustand
 * Note: Schema validation, testing, and saving are now handled through Dify API
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
    // Schema validation is now handled through Dify API
    console.warn('Schema validation should be handled through Dify chat interface');
    return {
      valid: false,
      errors: ['Please use Dify chat interface for schema validation'],
      warnings: [],
    };
  },

  testSchema: async (): Promise<TestResult> => {
    // Schema testing is now handled through Dify API
    console.warn('Schema testing should be handled through Dify chat interface');
    return {
      success: false,
      output_preview: [],
      errors: ['Please use Dify chat interface for schema testing'],
      execution_time: 0,
    };
  },

  saveSchema: async (metadata: SchemaMetadata) => {
    // Schema saving is now handled through Dify API
    console.warn('Schema saving should be handled through Dify chat interface');
    throw new Error('Please use Dify chat interface for schema operations');
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
