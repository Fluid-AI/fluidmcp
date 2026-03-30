import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../services/api';
import type { ServerEnvMetadataResponse } from '../types/server';

interface UseServerEnvResult {
  envMetadata: ServerEnvMetadataResponse;
  loading: boolean;
  error: string | null;
  updateEnv: (newEnv: Record<string, string>) => Promise<void>;
  refetch: () => Promise<void>;
}

/**
 * Custom hook for managing server instance environment variables
 *
 * @param serverId - The server ID to fetch env metadata for
 * @returns Environment metadata, loading state, error state, and update function
 */
export function useServerEnv(serverId: string | undefined): UseServerEnvResult {
  const [envMetadata, setEnvMetadata] = useState<ServerEnvMetadataResponse>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadEnv = useCallback(async () => {
    if (!serverId) {
      setEnvMetadata({});
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const metadata = await apiClient.getServerInstanceEnv(serverId);
      setEnvMetadata(metadata);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load environment variables';
      setError(errorMessage);
      console.error('Error loading server env:', err);
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  const updateEnv = useCallback(async (newEnv: Record<string, string>) => {
    if (!serverId) {
      throw new Error('No server ID provided');
    }

    setLoading(true);
    setError(null);

    try {
      await apiClient.updateServerInstanceEnv(serverId, newEnv);
      // Refetch metadata after successful update
      await loadEnv();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update environment variables';
      setError(errorMessage);
      throw err; // Re-throw so caller can handle
    } finally {
      setLoading(false);
    }
  }, [serverId, loadEnv]);

  // Load env metadata on mount and when serverId changes
  useEffect(() => {
    loadEnv();
  }, [loadEnv]);

  return {
    envMetadata,
    loading,
    error,
    updateEnv,
    refetch: loadEnv,
  };
}
