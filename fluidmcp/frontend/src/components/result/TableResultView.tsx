import React, { useState, useMemo } from 'react';

// Constants
const DEFAULT_ROWS_PER_PAGE = 50;
const MAX_ROWS_WARNING_THRESHOLD = 10000;

interface TableResultViewProps {
  data: Array<Record<string, unknown>>;
  maxRowsPerPage?: number;
}

export const TableResultView: React.FC<TableResultViewProps> = ({
  data,
  maxRowsPerPage = DEFAULT_ROWS_PER_PAGE
}) => {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [currentPage, setCurrentPage] = useState(1);

  if (!data || data.length === 0) {
    return <div className="result-text">Empty array</div>;
  }

  // Warning for large datasets
  if (data.length > MAX_ROWS_WARNING_THRESHOLD) {
    return (
      <div className="result-error">
        <h3>Dataset Too Large</h3>
        <p>
          The result contains {data.length.toLocaleString()} rows, which exceeds the maximum
          display limit of {MAX_ROWS_WARNING_THRESHOLD.toLocaleString()} rows.
        </p>
        <p>
          Consider filtering your data or exporting it for analysis in external tools.
        </p>
      </div>
    );
  }

  const columns = Object.keys(data[0]);

  // Sorting logic
  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
    setCurrentPage(1); // Reset to first page on sort
  };

  const sortedData = useMemo(() => {
    if (!sortColumn) return data;

    return [...data].sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];

      // Handle null/undefined
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      // Compare values
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
      }

      const aStr = String(aVal);
      const bStr = String(bVal);
      const comparison = aStr.localeCompare(bStr);
      return sortDirection === 'asc' ? comparison : -comparison;
    });
  }, [data, sortColumn, sortDirection]);

  // Pagination logic
  const totalPages = Math.ceil(sortedData.length / maxRowsPerPage);
  const startIdx = (currentPage - 1) * maxRowsPerPage;
  const endIdx = startIdx + maxRowsPerPage;
  const paginatedData = sortedData.slice(startIdx, endIdx);

  const renderCell = (value: unknown): string => {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  };

  return (
    <div>
      <div className="result-table-wrapper">
        <table className="result-table" role="table" aria-label="Data table with sortable columns">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  className={sortColumn === col ? `sorted-${sortDirection}` : ''}
                  role="columnheader"
                  aria-sort={sortColumn === col ? sortDirection === 'asc' ? 'ascending' : 'descending' : 'none'}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleSort(col);
                    }
                  }}
                  style={{ cursor: 'pointer' }}
                  title={`Sort by ${col}`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((row, idx) => (
              <tr key={startIdx + idx}>
                {columns.map((col) => (
                  <td key={col}>{renderCell(row[col])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="result-pagination" role="navigation" aria-label="Table pagination">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            aria-label="Go to previous page"
          >
            Previous
          </button>
          <span className="result-pagination-info" aria-live="polite" aria-atomic="true">
            Page {currentPage} of {totalPages} ({sortedData.length} rows)
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            aria-label="Go to next page"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
