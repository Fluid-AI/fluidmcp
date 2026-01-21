import React from 'react';

interface TableResultViewProps {
  data: Array<Record<string, unknown>>;
}

export const TableResultView: React.FC<TableResultViewProps> = ({ data }) => {
  if (!data || data.length === 0) {
    return <div className="result-text">Empty array</div>;
  }

  const columns = Object.keys(data[0]);

  const renderCell = (value: unknown): string => {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  };

  return (
    <div className="result-table-wrapper">
      <table className="result-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr key={idx}>
              {columns.map((col) => (
                <td key={col}>{renderCell(row[col])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
