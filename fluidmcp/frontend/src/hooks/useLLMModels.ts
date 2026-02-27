import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient from '../services/api';
import type { LLMModel } from '../types/llm';

export function useLLMModels() {
  const [models, setModels] = useState<LLMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchModels = useCallback(async () => {
    // Abort any existing request
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (!isMountedRef.current) return;
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.listLLMModels({ signal: controller.signal });
      if (isMountedRef.current) {
        setModels(response.models);
      }
    } catch (err) {
      // Only set error if not aborted and still mounted
      if (!controller.signal.aborted && isMountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch LLM models');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchModels();

    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, [fetchModels]);

  const restartModel = async (modelId: string) => {
    try {
      await apiClient.restartLLMModel(modelId);
      if (isMountedRef.current) {
        await fetchModels();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to restart model');
    }
  };

  const stopModel = async (modelId: string, force = false) => {
    try {
      await apiClient.stopLLMModel(modelId, force);
      if (isMountedRef.current) {
        await fetchModels();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to stop model');
    }
  };

  const triggerHealthCheck = async (modelId: string) => {
    try {
      const result = await apiClient.triggerLLMHealthCheck(modelId);
      if (isMountedRef.current) {
        await fetchModels();
      }
      return result;
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to trigger health check');
    }
  };

  // Computed properties for common filters
  const runningModels = models.filter(model => model.is_running);
  const healthyModels = models.filter(model => model.is_healthy);
  const unhealthyModels = models.filter(model => !model.is_healthy && model.is_running);
  const processModels = models.filter(model => model.type === 'process');
  const replicateModels = models.filter(model => model.type === 'replicate');

  return {
    models,
    runningModels,
    healthyModels,
    unhealthyModels,
    processModels,
    replicateModels,
    loading,
    error,
    refetch: fetchModels,
    restartModel,
    stopModel,
    triggerHealthCheck,
  };
}
