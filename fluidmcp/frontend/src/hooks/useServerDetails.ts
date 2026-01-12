import { useState, useEffect, useCallback } from 'react';
import apiClient from '../services/api';
import type { ServerDetailsResponse, ToolsResponse } from '../types/server';

export function useServerDetails(serverId: string) {
  const [serverDetails, setServerDetails] = useState<ServerDetailsResponse | null>(null);
  const [tools, setTools] = useState<ToolsResponse | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetails = useCallback(async () => {
    // Guard against missing serverId to prevent loading deadlock
    if (!serverId) {
      setLoading(false);
      setError('Server ID is required');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [detailsRes, toolsRes] = await Promise.all([
        apiClient.getServerDetails(serverId),
        // Tool discovery failure should not block server details view
        // If tools endpoint fails, we show server info without tools
        apiClient.getServerTools(serverId).catch(() => ({ server_id: serverId, tools: [], count: 0 })),
      ]);
      setServerDetails(detailsRes);
      setTools(toolsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch server details');
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    fetchDetails();
  }, [fetchDetails]);

  // Fetch server logs
  const fetchLogs = useCallback(async (lines = 100) => {
    if (!serverId) return;
    try {
      const logsRes = await apiClient.getServerLogs(serverId, lines);
      setLogs(logsRes.logs || []);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      // Don't throw error - logs are optional
    }
  }, [serverId]);

  // Server control actions
  const startServer = async () => {
    try {
      await apiClient.startServer(serverId);
      await fetchDetails(); // Refresh after starting
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to start server');
    }
  };

  const stopServer = async () => {
    try {
      await apiClient.stopServer(serverId);
      await fetchDetails();
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to stop server');
    }
  };

  const restartServer = async () => {
    try {
      await apiClient.restartServer(serverId);
      await fetchDetails();
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
