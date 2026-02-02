import { useMemo, useState, useEffect } from 'react';
import type { Server } from '../types/server';

export interface UseServerFilteringOptions {
  itemsPerPage?: number;
}

export interface UseServerFilteringResult {
  // State
  searchQuery: string;
  sortBy: 'name-asc' | 'name-desc' | 'status' | 'recent';
  filterBy: 'all' | 'running' | 'stopped' | 'error';
  currentPage: number;

  // Setters
  setSearchQuery: (query: string) => void;
  setSortBy: (sort: string) => void;
  setFilterBy: (filter: string) => void;
  setCurrentPage: (page: number) => void;

  // Computed
  filteredServers: Server[];
  paginatedServers: Server[];
  totalPages: number;
  totalFilteredCount: number;
}

export function useServerFiltering(
  servers: Server[],
  options: UseServerFilteringOptions = {}
): UseServerFilteringResult {
  const { itemsPerPage = 20 } = options;

  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'name-asc' | 'name-desc' | 'status' | 'recent'>('name-asc');
  const [filterBy, setFilterBy] = useState<'all' | 'running' | 'stopped' | 'error'>('all');
  const [currentPage, setCurrentPage] = useState(1);

  // Filter and sort
  const filteredServers = useMemo(() => {
    let result = [...servers];

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter((server) =>
        server.name.toLowerCase().includes(query) ||
        server.id.toLowerCase().includes(query) ||
        server.description?.toLowerCase().includes(query)
      );
    }

    // Status filter
    if (filterBy !== 'all') {
      result = result.filter((server) => {
        const state = server.status?.state || 'stopped';
        if (filterBy === 'running') return state === 'running';
        if (filterBy === 'stopped') return state === 'stopped';
        if (filterBy === 'error') return state === 'failed';
        return true;
      });
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'name-asc':
          return a.name.localeCompare(b.name);
        case 'name-desc':
          return b.name.localeCompare(a.name);
        case 'status': {
          const aState = a.status?.state || 'stopped';
          const bState = b.status?.state || 'stopped';
          if (aState === 'running' && bState !== 'running') return -1;
          if (aState !== 'running' && bState === 'running') return 1;
          return a.name.localeCompare(b.name);
        }
        case 'recent': {
          // Sort by uptime (lower uptime = more recently started)
          const aTime = a.status?.uptime || Number.MAX_SAFE_INTEGER;
          const bTime = b.status?.uptime || Number.MAX_SAFE_INTEGER;
          return aTime - bTime; // Lower uptime first (more recent)
        }
        default:
          return 0;
      }
    });

    return result;
  }, [servers, searchQuery, filterBy, sortBy]);

  // Paginate
  const paginatedServers = useMemo(() => {
    const startIdx = (currentPage - 1) * itemsPerPage;
    const endIdx = startIdx + itemsPerPage;
    return filteredServers.slice(startIdx, endIdx);
  }, [filteredServers, currentPage, itemsPerPage]);

  const totalPages = Math.ceil(filteredServers.length / itemsPerPage);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, filterBy, sortBy]);

  return {
    searchQuery,
    sortBy,
    filterBy,
    currentPage,
    setSearchQuery,
    setSortBy: (sort) => setSortBy(sort as any),
    setFilterBy: (filter) => setFilterBy(filter as any),
    setCurrentPage,
    filteredServers,
    paginatedServers,
    totalPages,
    totalFilteredCount: filteredServers.length,
  };
}
