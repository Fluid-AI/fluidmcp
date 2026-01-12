import { useState, useEffect, useCallback } from 'react';
import apiClient from '../services/api';
import type { Server } from '../types/server';

export function useServers() {
  const [servers, setServers] = useState<Server[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchServers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.listServers();
      setServers(response.servers);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch servers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  const startServer = async (serverId: string) => {
    // Note: UI should prevent concurrent start clicks by tracking loading state
    // (e.g., startingServerId state in Dashboard component)
    try {
      await apiClient.startServer(serverId);
      // Server status is refreshed after explicit user actions (no polling yet)
      await fetchServers();
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to start server');
    }
  };

  const stopServer = async (serverId: string) => {
    try {
      await apiClient.stopServer(serverId);
      await fetchServers();
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to stop server');
    }
  };

  const restartServer = async (serverId: string) => {
    try {
      await apiClient.restartServer(serverId);
      await fetchServers();
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to restart server');
    }
  };

  // Computed properties for common filters
  const activeServers = servers.filter(
    (server) =>
      server.status &&
      (server.status.state === "running" || server.status.state === "starting")
  );

  const stoppedServers = servers.filter(
    (server) =>
      !server.status ||
      server.status.state === "stopped" ||
      server.status.state === "failed"
  );

  return {
    servers,
    activeServers,
    stoppedServers,
    loading,
    error,
    refetch: fetchServers,
    startServer,
    stopServer,
    restartServer,
  };
}
