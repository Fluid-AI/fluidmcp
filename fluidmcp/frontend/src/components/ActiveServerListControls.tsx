import React from 'react';

export interface ActiveServerListControlsProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  sortBy: 'name-asc' | 'name-desc' | 'recent' | 'uptime';
  onSortChange: (sort: string) => void;
}

export const ActiveServerListControls: React.FC<ActiveServerListControlsProps> = ({
  searchQuery,
  onSearchChange,
  sortBy,
  onSortChange,
}) => {
  return (
    <div className="server-list-controls">
      <div className="control-group">
        <label htmlFor="active-server-search">Search</label>
        <input
          id="active-server-search"
          type="text"
          placeholder="Search active servers..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="search-input"
          aria-label="Search active servers by name or ID"
        />
      </div>

      <div className="control-group">
        <label htmlFor="active-server-sort">Sort by</label>
        <select
          id="active-server-sort"
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value)}
          className="sort-select"
        >
          <option value="recent">Recently started</option>
          <option value="name-asc">Name (A-Z)</option>
          <option value="name-desc">Name (Z-A)</option>
          <option value="uptime">Uptime (longest first)</option>
        </select>
      </div>
    </div>
  );
};
