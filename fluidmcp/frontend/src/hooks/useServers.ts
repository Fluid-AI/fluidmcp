import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient from '../services/api';
import type { Server } from '../types/server';

export function useServers() {
  const [servers, setServers] = useState<Server[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchServers = useCallback(async () => {
    // Abort any existing request
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (!isMountedRef.current) return;
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.listServers({ signal: controller.signal });
      if (isMountedRef.current) {
        setServers(response.servers);
      }
    } catch (err) {
      // Only set error if not aborted and still mounted
      if (!controller.signal.aborted && isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch servers');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchServers();

    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, [fetchServers]);

  const startServer = async (serverId: string) => {
    try {
      await apiClient.startServer(serverId);
      // NOTE: This refetch will be replaced by polling in follow-up PR
      if (isMountedRef.current) {
        await fetchServers();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to start server');
    }
  };

  const stopServer = async (serverId: string) => {
    try {
      await apiClient.stopServer(serverId);
      // NOTE: This refetch will be replaced by polling in follow-up PR
      if (isMountedRef.current) {
        await fetchServers();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to stop server');
    }
  };

  const restartServer = async (serverId: string) => {
    try {
      await apiClient.restartServer(serverId);
      // NOTE: This refetch will be replaced by polling in follow-up PR
      if (isMountedRef.current) {
        await fetchServers();
      }
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