export type ViewMode = 'compact' | 'standard' | 'expanded';

export interface TableColumn {
  key: string;
  label: string;
  width?: number;
  minWidth?: number;
  visible?: boolean;
  essential?: boolean;
}

export interface TablePreferences {
  viewMode: ViewMode;
  columnVisibility: Record<string, boolean>;
  columnWidths: Record<string, number>;
  filenameTruncationLength: number;
}

export const DEFAULT_PREFERENCES: TablePreferences = {
  viewMode: 'standard',
  columnVisibility: {},
  columnWidths: {},
  filenameTruncationLength: 30,
};

export const DEFAULT_COLUMNS: TableColumn[] = [
  { key: 'filename', label: '文件名', width: 200, minWidth: 100, essential: true },
  { key: 'size', label: '大小', width: 100, minWidth: 60, essential: true },
  { key: 'type', label: '类型', width: 100, minWidth: 60, essential: false },
  { key: 'status', label: '状态', width: 100, minWidth: 60, essential: true },
  { key: 'date', label: '日期', width: 150, minWidth: 80, essential: true },
];
