import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../services/api';
import { toolHistoryService, ToolExecution } from '../services/toolHistory';

interface UseToolRunnerResult {
  execute: (args: Record<string, any>) => Promise<void>;
  result: any;
  error: string | null;
  loading: boolean;
  executionTime: number | null;
  history: ToolExecution[];
  loadFromHistory: (executionId: string) => Record<string, any> | null;
  clearHistory: () => void;
}

export function useToolRunner(
  serverId: string,
  serverName: string,
  toolName: string
): UseToolRunnerResult {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [executionTime, setExecutionTime] = useState<number | null>(null);
  const [history, setHistory] = useState<ToolExecution[]>([]);

  // Load history on mount and when tool changes
  useEffect(() => {
    loadHistory();
  }, [serverId, toolName]);

  const loadHistory = useCallback(() => {
    const toolHistory = toolHistoryService.getHistory(serverId, toolName);
    setHistory(toolHistory);
  }, [serverId, toolName]);

  const execute = useCallback(
    async (args: Record<string, any>) => {
      setLoading(true);
      setError(null);
      setResult(null);
      setExecutionTime(null);

      const startTime = performance.now();

      try {
        const response = await apiClient.runTool(serverId, toolName, args);
        const endTime = performance.now();
        const duration = (endTime - startTime) / 1000; // Convert to seconds

        setResult(response.result);
        setExecutionTime(duration);

        // Save successful execution to history
        toolHistoryService.saveExecution({
          serverId,
          serverName,
          toolName,
          arguments: args,
          result: response.result,
          success: true,
          executionTime: duration,
        });

        // Reload history
        loadHistory();
      } catch (err: any) {
        const endTime = performance.now();
        const duration = (endTime - startTime) / 1000;

        const errorMessage = err.message || 'Failed to execute tool';
        setError(errorMessage);
        setExecutionTime(duration);

        // Save failed execution to history
        toolHistoryService.saveExecution({
          serverId,
          serverName,
          toolName,
          arguments: args,
          result: null,
          success: false,
          error: errorMessage,
          executionTime: duration,
        });

        // Reload history
        loadHistory();
      } finally {
        setLoading(false);
      }
    },
    [serverId, serverName, toolName, loadHistory]
  );

  const loadFromHistory = useCallback(
    (executionId: string): Record<string, any> | null => {
      const execution = toolHistoryService.getExecutionById(executionId);
      if (!execution) return null;

      // Set result and execution time from history
      setResult(execution.result);
      setError(execution.error || null);
      setExecutionTime(execution.executionTime || null);

      return execution.arguments;
    },
    []
  );

  const clearHistory = useCallback(() => {
    toolHistoryService.clearHistory(serverId, toolName);
    setHistory([]);
  }, [serverId, toolName]);

  return {
    execute,
    result,
    error,
    loading,
    executionTime,
    history,
    loadFromHistory,
    clearHistory,
  };
}
