import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient from '../services/api';
import type { ServerDetailsResponse, ToolsResponse } from '../types/server';

export function useServerDetails(serverId: string) {
  const [serverDetails, setServerDetails] = useState<ServerDetailsResponse | null>(null);
  const [tools, setTools] = useState<ToolsResponse | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchDetails = useCallback(async () => {
    // Guard against missing serverId
    if (!serverId) {
      setLoading(false);
      setError('Server ID is required');
      return;
    }

    // Abort any existing request
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (!isMountedRef.current) return;
    setLoading(true);
    setError(null);

    try {
      const [detailsRes, toolsRes] = await Promise.all([
        apiClient.getServerDetails(serverId, { signal: controller.signal }),
        // Tool discovery failure should not block server details view
        apiClient.getServerTools(serverId, { signal: controller.signal })
          .catch(() => ({ server_id: serverId, tools: [], count: 0 })),
      ]);

      if (isMountedRef.current) {
        setServerDetails(detailsRes);
        setTools(toolsRes);
      }
    } catch (err) {
      // Only set error if not aborted and still mounted
      if (!controller.signal.aborted && isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch server details');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [serverId]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchDetails();

    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, [fetchDetails]);

  // Fetch server logs
  const fetchLogs = useCallback(async (lines = 100) => {
    if (!serverId || !isMountedRef.current) return;
    try {
      const logsRes = await apiClient.getServerLogs(serverId, lines);
      if (isMountedRef.current) {
        setLogs(logsRes.logs || []);
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      // Don't throw error - logs are optional
    }
  }, [serverId]);

  // Server control actions
  const startServer = async () => {
    try {
      await apiClient.startServer(serverId);
      // NOTE: This refetch will be replaced by polling in follow-up PR
      if (isMountedRef.current) {
        await fetchDetails();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to start server');
    }
  };

  const stopServer = async () => {
    try {
      await apiClient.stopServer(serverId);
      // NOTE: This refetch will be replaced by polling in follow-up PR
      if (isMountedRef.current) {
        await fetchDetails();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to stop server');
    }
  };

  const restartServer = async () => {
    try {
      await apiClient.restartServer(serverId);
      // NOTE: This refetch will be replaced by polling in follow-up PR
      if (isMountedRef.current) {
        await fetchDetails();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to restart server');
    }
  };

  // Computed properties
  const hasTools = (tools?.tools?.length ?? 0) > 0;
  const isRunning = serverDetails?.status.state === "running";
  const isStopped = !serverDetails?.status ||
                    serverDetails.status.state === "stopped" ||
                    serverDetails.status.state === "failed";

  return {
    serverDetails,
    tools: tools?.tools || [],
    logs,
    hasTools,
    isRunning,
    isStopped,
    loading,
    error,
    refetch: fetchDetails,
    fetchLogs,
    startServer,
    stopServer,
    restartServer,
  };
}