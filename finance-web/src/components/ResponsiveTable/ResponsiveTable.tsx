import { useRef, useState, useCallback } from 'react';
import { GripVertical, Columns3 } from 'lucide-react';
import type { TableColumn, ViewMode } from './types';

interface ResponsiveTableProps<T extends Record<string, unknown>> {
  data: T[];
  columns: TableColumn[];
  viewMode: ViewMode;
  columnVisibility: Record<string, boolean>;
  columnWidths: Record<string, number>;
  filenameTruncationLength: number;
  onViewModeChange: (mode: ViewMode) => void;
  onColumnVisibilityChange: (columnKey: string) => void;
  onColumnWidthChange: (columnKey: string, width: number) => void;
  onFilenameTruncationChange?: (length: number) => void;
  /** 是否显示视图切换栏（紧凑/标准/展开），默认 true */
  showViewMode?: boolean;
}

const VIEW_MODE_STYLES: Record<ViewMode, { padding: string; fontSize: string; rowHeight: string }> = {
  compact: { padding: 'px-2 py-1', fontSize: 'text-xs', rowHeight: 'h-8' },
  standard: { padding: 'px-3 py-2', fontSize: 'text-sm', rowHeight: 'h-10' },
  expanded: { padding: 'px-4 py-3', fontSize: 'text-base', rowHeight: 'h-12' },
};

export default function ResponsiveTable<T extends Record<string, unknown>>({
  data,
  columns,
  viewMode,
  columnVisibility,
  columnWidths,
  filenameTruncationLength,
  onViewModeChange,
  onColumnVisibilityChange,
  onColumnWidthChange,
  showViewMode = true,
}: ResponsiveTableProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showColumnMenu, setShowColumnMenu] = useState(false);
  const [resizingColumn, setResizingColumn] = useState<string | null>(null);

  const visibleColumns = columns.filter((col) => columnVisibility[col.key] !== false);
  const style = VIEW_MODE_STYLES[viewMode];

  const handleMouseDown = useCallback((columnKey: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    setResizingColumn(columnKey);

    const startX = e.clientX;
    const startWidth = columnWidths[columnKey] || columns.find((c) => c.key === columnKey)?.width || 100;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = Math.max(
        columns.find((c) => c.key === columnKey)?.minWidth || 50,
        startWidth + moveEvent.clientX - startX
      );
      onColumnWidthChange(columnKey, newWidth);
    };

    const handleMouseUp = () => {
      setResizingColumn(null);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [columnWidths, columns, onColumnWidthChange]);

  const truncateFilename = (filename: string): string => {
    if (filename.length <= filenameTruncationLength) return filename;
    return filename.slice(0, filenameTruncationLength - 3) + '...';
  };

  const isEssentialColumn = (key: string): boolean => {
    return columns.find((c) => c.key === key)?.essential === true;
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
        {showViewMode ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">视图:</span>
            {(['compact', 'standard', 'expanded'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => onViewModeChange(mode)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  viewMode === mode
                    ? 'bg-blue-500 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'
                }`}
              >
                {mode === 'compact' ? '紧凑' : mode === 'standard' ? '标准' : '展开'}
              </button>
            ))}
          </div>
        ) : (
          <div />
        )}
        <div className="relative">
          <button
            onClick={() => setShowColumnMenu(!showColumnMenu)}
            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded border border-gray-200"
          >
            <Columns3 className="w-3 h-3" />
            列
          </button>
          {showColumnMenu && (
            <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 min-w-40">
              {columns.map((col) => (
                <label
                  key={col.key}
                  className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={columnVisibility[col.key] !== false}
                    onChange={() => onColumnVisibilityChange(col.key)}
                    disabled={isEssentialColumn(col.key)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-xs text-gray-700">{col.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Table Container */}
      <div ref={containerRef} className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-gray-50">
              {visibleColumns.map((col, index) => (
                <th
                  key={col.key}
                  className={`relative ${style.padding} text-left text-xs font-medium text-gray-600 border-b border-gray-200 select-none`}
                  style={{
                    width: columnWidths[col.key] || col.width,
                    minWidth: col.minWidth,
                    position: 'sticky',
                    top: 0,
                    zIndex: index === 0 ? 2 : 1,
                    left: index === 0 ? 0 : undefined,
                    backgroundColor: '#f9fafb',
                  }}
                >
                  <div className="flex items-center gap-1">
                    <span>{col.label}</span>
                    {index === 0 && <GripVertical className="w-3 h-3 text-gray-400 cursor-grab" />}
                  </div>
                  <div
                    className={`absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-400 ${
                      resizingColumn === col.key ? 'bg-blue-500' : ''
                    }`}
                    onMouseDown={handleMouseDown(col.key)}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className={`${style.rowHeight} hover:bg-gray-50 transition-colors border-b border-gray-100`}
              >
                {visibleColumns.map((col, colIndex) => (
                  <td
                    key={col.key}
                    className={`${style.padding} ${style.fontSize} text-gray-700 border-r border-gray-100 last:border-r-0`}
                    style={{
                      width: columnWidths[col.key] || col.width,
                      minWidth: col.minWidth,
                      position: 'sticky',
                      left: colIndex === 0 ? 0 : undefined,
                      zIndex: colIndex === 0 ? 1 : 0,
                      backgroundColor: colIndex === 0 ? 'white' : 'inherit',
                    }}
                  >
                    {col.key === 'filename' ? (
                      <span
                        className="block truncate"
                        title={String(row[col.key] || '')}
                      >
                        {truncateFilename(String(row[col.key] || ''))}
                      </span>
                    ) : (
                      String(row[col.key] ?? '')
                    )}
                  </td>
                ))}
              </tr>
            ))}
            {data.length === 0 && (
              <tr>
                <td
                  colSpan={visibleColumns.length}
                  className={`${style.padding} text-center text-gray-400`}
                >
                  暂无数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
