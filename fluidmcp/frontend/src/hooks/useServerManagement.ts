import { useState, useCallback } from 'react';
import apiClient from '../services/api';
import { Server } from '../types/server';
import { showSuccess, showError } from '../services/toast';

export function useServerManagement(includeDeleted: boolean = false) {
  const [servers, setServers] = useState<Server[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchServers = useCallback(async (forceIncludeDeleted?: boolean) => {
    setLoading(true);
    setError(null);
    try {
      // Fetch all servers including disabled ones for management page
      const response = await apiClient.listServers({
        enabled_only: false,
        include_deleted: forceIncludeDeleted ?? includeDeleted
      });
      setServers(response.servers);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load servers';
      setError(message);
      showError(message);
    } finally {
      setLoading(false);
    }
  }, [includeDeleted]);

  const createServer = useCallback(async (config: any) => {
    try {
      await apiClient.addServer(config);
      showSuccess(`Server '${config.name}' created successfully`);
      await fetchServers();
      return true;
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to create server');
      return false;
    }
  }, [fetchServers]);

  const updateServer = useCallback(async (serverId: string, config: any) => {
    try {
      await apiClient.updateServer(serverId, config);
      showSuccess('Server updated successfully');
      await fetchServers();
      return true;
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to update server');
      return false;
    }
  }, [fetchServers]);

  const deleteServer = useCallback(async (serverId: string, serverName: string) => {
    try {
      await apiClient.deleteServer(serverId);
      showSuccess(`Server '${serverName}' deleted successfully`);
      await fetchServers();
      return true;
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to delete server');
      return false;
    }
  }, [fetchServers]);

  return {
    servers,
    loading,
    error,
    refetch: fetchServers,
    createServer,
    updateServer,
    deleteServer,
  };
}
