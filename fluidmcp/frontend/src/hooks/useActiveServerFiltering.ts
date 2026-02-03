import { useMemo, useState, useEffect } from 'react';
import type { Server } from '../types/server';

export interface UseActiveServerFilteringOptions {
  itemsPerPage?: number;
}

export interface UseActiveServerFilteringResult {
  searchQuery: string;
  sortBy: 'name-asc' | 'name-desc' | 'recent' | 'uptime';
  currentPage: number;
  setSearchQuery: (query: string) => void;
  setSortBy: (sort: string) => void;
  setCurrentPage: (page: number) => void;
  filteredServers: Server[];
  paginatedServers: Server[];
  totalPages: number;
  totalFilteredCount: number;
}

export function useActiveServerFiltering(
  servers: Server[],
  options: UseActiveServerFilteringOptions = {}
): UseActiveServerFilteringResult {
  const { itemsPerPage = 6 } = options;

  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'name-asc' | 'name-desc' | 'recent' | 'uptime'>('recent');
  const [currentPage, setCurrentPage] = useState(1);

  // Filter and sort
  const filteredServers = useMemo(() => {
    let result = [...servers];

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter((server) =>
        server.name.toLowerCase().includes(query) ||
        server.id.toLowerCase().includes(query)
      );
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'name-asc':
          return a.name.localeCompare(b.name);
        case 'name-desc':
          return b.name.localeCompare(a.name);
        case 'recent': {
          // Sort by uptime (lower uptime = more recently started)
          const aTime = a.status?.uptime || Number.MAX_SAFE_INTEGER;
          const bTime = b.status?.uptime || Number.MAX_SAFE_INTEGER;
          return aTime - bTime; // Lower uptime first (more recent)
        }
        case 'uptime': {
          // Sort by uptime (higher uptime = longest running)
          const aTime = a.status?.uptime || 0;
          const bTime = b.status?.uptime || 0;
          return bTime - aTime; // Higher uptime first (longest running)
        }
        default:
          return 0;
      }
    });

    return result;
  }, [servers, searchQuery, sortBy]);

  // Paginate
  const paginatedServers = useMemo(() => {
    const startIdx = (currentPage - 1) * itemsPerPage;
    const endIdx = startIdx + itemsPerPage;
    return filteredServers.slice(startIdx, endIdx);
  }, [filteredServers, currentPage, itemsPerPage]);

  const totalPages = Math.ceil(filteredServers.length / itemsPerPage);

  // Reset to page 1 when filters change (must happen before pagination is computed)
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, sortBy]);

  return {
    searchQuery,
    sortBy,
    currentPage,
    setSearchQuery,
    setSortBy: (sort) => setSortBy(sort as any),
    setCurrentPage,
    filteredServers,
    paginatedServers,
    totalPages,
    totalFilteredCount: filteredServers.length,
  };
}
