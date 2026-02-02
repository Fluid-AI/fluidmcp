import React from 'react';

export interface ServerListControlsProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  sortBy: 'name-asc' | 'name-desc' | 'status' | 'recent';
  onSortChange: (sort: string) => void;
  filterBy: 'all' | 'running' | 'stopped' | 'error';
  onFilterChange: (filter: string) => void;
}

export const ServerListControls: React.FC<ServerListControlsProps> = ({
  searchQuery,
  onSearchChange,
  sortBy,
  onSortChange,
  filterBy,
  onFilterChange,
}) => {
  return (
    <div className="server-list-controls">
      <div className="control-group">
        <label htmlFor="server-search">Search</label>
        <input
          id="server-search"
          type="text"
          placeholder="Search servers..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="search-input"
        />
      </div>

      <div className="control-group">
        <label htmlFor="server-sort">Sort by</label>
        <select
          id="server-sort"
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value)}
          className="sort-select"
        >
          <option value="name-asc">Name (A-Z)</option>
          <option value="name-desc">Name (Z-A)</option>
          <option value="status">Status (Running first)</option>
          <option value="recent">Recently started</option>
        </select>
      </div>

      <div className="control-group">
        <label htmlFor="server-filter">Filter</label>
        <select
          id="server-filter"
          value={filterBy}
          onChange={(e) => onFilterChange(e.target.value)}
          className="filter-select"
        >
          <option value="all">All servers</option>
          <option value="running">Running only</option>
          <option value="stopped">Stopped only</option>
          <option value="error">Errors only</option>
        </select>
      </div>
    </div>
  );
};
