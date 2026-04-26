import { useState, useCallback } from 'react';
import type { TablePreferences, ViewMode } from '../components/ResponsiveTable/types';
import { DEFAULT_PREFERENCES } from '../components/ResponsiveTable/types';

const STORAGE_KEY = 'table-preferences';

function loadPreferences(tableId: string): TablePreferences {
  try {
    const stored = localStorage.getItem(`${STORAGE_KEY}-${tableId}`);
    if (stored) {
      const parsed = JSON.parse(stored);
      return { ...DEFAULT_PREFERENCES, ...parsed };
    }
  } catch (e) {
    console.warn('Failed to load table preferences:', e);
  }
  return DEFAULT_PREFERENCES;
}

export function useTablePreferences(tableId: string) {
  const [loadedTableId, setLoadedTableId] = useState(tableId);
  const [preferences, setPreferences] = useState<TablePreferences>(() => loadPreferences(tableId));

  if (loadedTableId !== tableId) {
    setLoadedTableId(tableId);
    setPreferences(loadPreferences(tableId));
  }

  const savePreferences = useCallback((newPrefs: Partial<TablePreferences>) => {
    setPreferences((prev) => {
      const updated = { ...prev, ...newPrefs };
      try {
        localStorage.setItem(`${STORAGE_KEY}-${tableId}`, JSON.stringify(updated));
      } catch (e) {
        console.warn('Failed to save table preferences:', e);
      }
      return updated;
    });
  }, [tableId]);

  const setViewMode = useCallback((viewMode: ViewMode) => {
    savePreferences({ viewMode });
  }, [savePreferences]);

  const toggleColumnVisibility = useCallback((columnKey: string) => {
    setPreferences((prev) => {
      const newVisibility = {
        ...prev.columnVisibility,
        [columnKey]: !prev.columnVisibility[columnKey],
      };
      savePreferences({ columnVisibility: newVisibility });
      return { ...prev, columnVisibility: newVisibility };
    });
  }, [savePreferences]);

  const setColumnWidth = useCallback((columnKey: string, width: number) => {
    setPreferences((prev) => {
      const newWidths = { ...prev.columnWidths, [columnKey]: width };
      savePreferences({ columnWidths: newWidths });
      return { ...prev, columnWidths: newWidths };
    });
  }, [savePreferences]);

  const setFilenameTruncationLength = useCallback((length: number) => {
    savePreferences({ filenameTruncationLength: length });
  }, [savePreferences]);

  return {
    preferences,
    isLoaded: true,
    setViewMode,
    toggleColumnVisibility,
    setColumnWidth,
    setFilenameTruncationLength,
  };
}
