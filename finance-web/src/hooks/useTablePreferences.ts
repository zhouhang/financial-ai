import { useState, useCallback, useEffect } from 'react';
import type { TablePreferences, ViewMode } from '../components/ResponsiveTable/types';
import { DEFAULT_PREFERENCES } from '../components/ResponsiveTable/types';

const STORAGE_KEY = 'table-preferences';

export function useTablePreferences(tableId: string) {
  const [preferences, setPreferences] = useState<TablePreferences>(DEFAULT_PREFERENCES);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(`${STORAGE_KEY}-${tableId}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        setPreferences({ ...DEFAULT_PREFERENCES, ...parsed });
      }
    } catch (e) {
      console.warn('Failed to load table preferences:', e);
    }
    setIsLoaded(true);
  }, [tableId]);

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
    isLoaded,
    setViewMode,
    toggleColumnVisibility,
    setColumnWidth,
    setFilenameTruncationLength,
  };
}
