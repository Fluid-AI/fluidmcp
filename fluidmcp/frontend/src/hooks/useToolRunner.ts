import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../services/api';
import { toolHistoryService } from '../services/toolHistory';
import type { ToolExecution } from '../services/toolHistory';

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

  // Track mount status to prevent state updates on unmounted component
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadHistory = useCallback(() => {
    const toolHistory = toolHistoryService.getHistory(serverId, toolName);
    if (isMountedRef.current) {
      setHistory(toolHistory);
    }
  }, [serverId, toolName]);

  // Load history on mount and when tool changes
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const execute = useCallback(
    async (args: Record<string, any>) => {
      // NOTE: Execution cancellation will be added in a follow-up PR
      if (isMountedRef.current) {
        setLoading(true);
        setError(null);
        setResult(null);
        setExecutionTime(null);
      }

      const startTime = performance.now();

      try {
        const response = await apiClient.runTool(serverId, toolName, args);
        const endTime = performance.now();
        const duration = (endTime - startTime) / 1000; // Convert to seconds

        if (isMountedRef.current) {
          setResult(response.result);
          setExecutionTime(duration);
        }

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

        // Reload history with mount guard
        if (isMountedRef.current) {
          loadHistory();
        }
      } catch (err: any) {
        const endTime = performance.now();
        const duration = (endTime - startTime) / 1000;

        const errorMessage = err.message || 'Failed to execute tool';

        if (isMountedRef.current) {
          setError(errorMessage);
          setExecutionTime(duration);
        }

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

        // Reload history with mount guard
        if (isMountedRef.current) {
          loadHistory();
        }
      } finally {
        if (isMountedRef.current) {
          setLoading(false);
        }
      }
    },
    [serverId, serverName, toolName, loadHistory]
  );

  const loadFromHistory = useCallback(
    (executionId: string): Record<string, any> | null => {
      const execution = toolHistoryService.getExecutionById(executionId);
      if (!execution) return null;

      // Set result and execution time from history
      if (isMountedRef.current) {
        setResult(execution.result);
        setError(execution.error || null);
        setExecutionTime(execution.executionTime || null);
      }

      return execution.arguments;
    },
    []
  );

  const clearHistory = useCallback(() => {
    toolHistoryService.clearHistory(serverId, toolName);
    if (isMountedRef.current) {
      setHistory([]);
    }
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
