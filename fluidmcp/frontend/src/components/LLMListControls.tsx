import React from 'react';

export interface LLMListControlsProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  sortBy: 'name-asc' | 'name-desc' | 'health' | 'uptime';
  onSortChange: (sort: string) => void;
  filterBy: 'all' | 'running' | 'stopped' | 'healthy' | 'unhealthy' | 'process' | 'replicate';
  onFilterChange: (filter: string) => void;
  onClearFilters?: () => void;
}

export const LLMListControls: React.FC<LLMListControlsProps> = ({
  searchQuery,
  onSearchChange,
  sortBy,
  onSortChange,
  filterBy,
  onFilterChange,
  onClearFilters,
}) => {
  const hasActiveFilters = searchQuery !== '' || sortBy !== 'name-asc' || filterBy !== 'all';

  return (
    <div className="server-list-controls">
      <div className="control-group">
        <label htmlFor="llm-search">Search</label>
        <input
          id="llm-search"
          type="text"
          placeholder="Search models..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="search-input"
        />
      </div>

      <div className="control-group">
        <label htmlFor="llm-sort">Sort by</label>
        <select
          id="llm-sort"
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value)}
          className="sort-select"
        >
          <option value="name-asc">Name (A-Z)</option>
          <option value="name-desc">Name (Z-A)</option>
          <option value="health">Health Status</option>
          <option value="uptime">Uptime</option>
        </select>
      </div>

      <div className="control-group">
        <label htmlFor="llm-filter">Filter</label>
        <select
          id="llm-filter"
          value={filterBy}
          onChange={(e) => onFilterChange(e.target.value)}
          className="filter-select"
        >
          <option value="all">All models</option>
          <option value="running">Running only</option>
          <option value="stopped">Stopped only</option>
          <option value="healthy">Healthy only</option>
          <option value="unhealthy">Unhealthy only</option>
          <option value="process">Local Process</option>
          <option value="replicate">Cloud (Replicate)</option>
        </select>
      </div>

      {hasActiveFilters && onClearFilters && (
        <div className="control-group control-group-button">
          <label>&nbsp;</label>
          <button onClick={onClearFilters} className="clear-filters-btn">
            Clear Filters
          </button>
        </div>
      )}
    </div>
  );
};
