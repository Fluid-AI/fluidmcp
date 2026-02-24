import { useParams, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { ArrowLeft, RefreshCw, Square, Activity, AlertCircle, Clock } from "lucide-react";
import apiClient from "../services/api";
import type { LLMModel, LLMModelLogsResponse } from "../types/llm";
import { isProcessBasedModel, isReplicateModel } from "../types/llm";
import ErrorMessage from "../components/ErrorMessage";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";

export default function LLMModelDetails() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const [model, setModel] = useState<LLMModel | null>(null);
  const [logs, setLogs] = useState<LLMModelLogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchModelDetails = async () => {
    if (!modelId) return;

    try {
      const data = await apiClient.getLLMModelDetails(modelId);
      setModel(data as LLMModel);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch model details');
    } finally {
      setLoading(false);
    }
  };

  const fetchLogs = async () => {
    if (!modelId) return;
    if (model?.type !== 'process') return;

    setLogsLoading(true);
    try {
      const data = await apiClient.getLLMModelLogs(modelId, 100);
      setLogs(data);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    fetchModelDetails();
    fetchLogs();
  }, [modelId]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchModelDetails();
      if (model?.type === 'process') {
        fetchLogs();
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [autoRefresh, model?.type]);

  const handleRestart = async () => {
    if (!modelId || model?.type !== 'process') return;

    const toastId = `model-${modelId}`;
    setActionLoading('restart');
    showLoading(`Restarting model "${modelId}"...`, toastId);

    try {
      await apiClient.restartLLMModel(modelId);
      showSuccess(`Model "${modelId}" restarted successfully`, toastId);
      await fetchModelDetails();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to restart model', toastId);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    if (!modelId || model?.type !== 'process') return;

    const toastId = `model-${modelId}`;
    setActionLoading('stop');
    showLoading(`Stopping model "${modelId}"...`, toastId);

    try {
      await apiClient.stopLLMModel(modelId, false);
      showSuccess(`Model "${modelId}" stopped successfully`, toastId);
      await fetchModelDetails();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to stop model', toastId);
    } finally {
      setActionLoading(null);
    }
  };

  const handleHealthCheck = async () => {
    if (!modelId || model?.type !== 'process') return;

    const toastId = `health-${modelId}`;
    showLoading(`Running health check...`, toastId);

    try {
      const result = await apiClient.triggerLLMHealthCheck(modelId);
      if (result.is_healthy) {
        showSuccess('Health check passed', toastId);
      } else {
        showError(`Health check failed: ${result.health_message}`, toastId);
      }
      await fetchModelDetails();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to run health check', toastId);
    }
  };

  const formatUptime = (seconds: number | null) => {
    if (!seconds) return "N/A";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
    if (minutes > 0) return `${minutes}m ${secs}s`;
    return `${secs}s`;
  };

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return "Never";
    return new Date(timestamp).toLocaleString();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Skeleton className="h-12 w-64 mb-8 bg-zinc-900" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Skeleton className="h-96 bg-zinc-900" />
            <Skeleton className="h-96 lg:col-span-2 bg-zinc-900" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !model) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center p-4">
        <ErrorMessage message={error || "Model not found"} />
      </div>
    );
  }

  const isProcess = isProcessBasedModel(model);
  const isReplicate = isReplicateModel(model);

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <div className="bg-zinc-900/50 border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center gap-4 mb-4">
            <button
              onClick={() => navigate('/llm/models')}
              className="p-2 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex-1">
              <h1 className="text-3xl font-bold">{modelId}</h1>
              <div className="flex items-center gap-2 mt-2">
                <span className="px-2 py-1 bg-zinc-800 rounded text-xs">
                  {isReplicate ? "Cloud (Replicate)" : "Local Process"}
                </span>
                {model.is_running ? (
                  <span className={`px-2 py-1 rounded text-xs ${model.is_healthy ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                    {model.is_healthy ? 'Healthy' : 'Unhealthy'}
                  </span>
                ) : (
                  <span className="px-2 py-1 bg-zinc-700 rounded text-xs text-zinc-400">
                    Stopped
                  </span>
                )}
              </div>
            </div>

            {/* Auto-refresh toggle */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-zinc-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-indigo-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
              <span className="text-sm text-zinc-400">Auto-refresh</span>
            </label>
          </div>

          {/* Action Buttons */}
          {isProcess && (
            <div className="flex items-center gap-2 flex-wrap">
              {model.is_running && (
                <>
                  <button
                    onClick={handleRestart}
                    disabled={actionLoading !== null}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${actionLoading === 'restart' ? 'animate-spin' : ''}`} />
                    Restart
                  </button>
                  <button
                    onClick={handleStop}
                    disabled={actionLoading !== null}
                    className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
                  >
                    <Square className="w-4 h-4" />
                    Stop
                  </button>
                  <button
                    onClick={handleHealthCheck}
                    disabled={actionLoading !== null}
                    className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
                  >
                    <Activity className="w-4 h-4" />
                    Health Check
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  fetchModelDetails();
                  fetchLogs();
                }}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg font-medium transition-all disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Sidebar - Model Info */}
          <div className="space-y-6">
            {/* Status Card */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
              <h2 className="text-xl font-bold mb-4">Status</h2>
              <div className="space-y-3">
                <div>
                  <div className="text-sm text-zinc-400">State</div>
                  <div className="text-lg font-semibold">
                    {model.is_running ? 'Running' : 'Stopped'}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-zinc-400">Health</div>
                  <div className="text-lg font-semibold">
                    {model.health_message}
                  </div>
                </div>
                {isProcess && (
                  <>
                    <div>
                      <div className="text-sm text-zinc-400">Uptime</div>
                      <div className="text-lg font-semibold flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        {formatUptime(model.uptime_seconds)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-zinc-400">Restart Count</div>
                      <div className="text-lg font-semibold">
                        {model.restart_count} / {model.max_restarts}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-zinc-400">Restart Policy</div>
                      <div className="text-lg font-semibold capitalize">
                        {model.restart_policy}
                      </div>
                    </div>
                  </>
                )}
                {isReplicate && (
                  <>
                    <div>
                      <div className="text-sm text-zinc-400">Model</div>
                      <div className="text-sm font-mono">{model.model}</div>
                    </div>
                    <div>
                      <div className="text-sm text-zinc-400">Endpoint</div>
                      <div className="text-sm font-mono break-all">{model.endpoint}</div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Warnings */}
            {isProcess && model.consecutive_health_failures > 0 && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-red-400">Health Failures</div>
                    <div className="text-sm text-red-300 mt-1">
                      {model.consecutive_health_failures} consecutive failure(s) detected
                    </div>
                  </div>
                </div>
              </div>
            )}

            {isProcess && model.has_cuda_oom && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-red-400">CUDA OOM Detected</div>
                    <div className="text-sm text-red-300 mt-1">
                      GPU memory exhausted. Consider reducing batch size or model size.
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Timestamps */}
            {isProcess && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <h2 className="text-xl font-bold mb-4">Timeline</h2>
                <div className="space-y-3 text-sm">
                  <div>
                    <div className="text-zinc-400">Last Health Check</div>
                    <div className="font-mono">{formatTimestamp(model.last_health_check_time)}</div>
                  </div>
                  <div>
                    <div className="text-zinc-400">Last Restart</div>
                    <div className="font-mono">{formatTimestamp(model.last_restart_time)}</div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right Content - Logs */}
          {isProcess && (
            <div className="lg:col-span-2">
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b border-zinc-800">
                  <h2 className="text-xl font-bold">Logs (stderr)</h2>
                  <button
                    onClick={fetchLogs}
                    disabled={logsLoading}
                    className="flex items-center gap-2 px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm transition-all disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 ${logsLoading ? 'animate-spin' : ''}`} />
                    Refresh
                  </button>
                </div>
                <div className="p-4 bg-black font-mono text-xs overflow-x-auto max-h-[600px] overflow-y-auto">
                  {logsLoading ? (
                    <div className="text-zinc-500">Loading logs...</div>
                  ) : logs?.lines && logs.lines.length > 0 ? (
                    <pre className="text-zinc-300 whitespace-pre-wrap break-words">
                      {logs.lines.join('')}
                    </pre>
                  ) : (
                    <div className="text-zinc-500">
                      {logs?.message || "No logs available"}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Replicate Info */}
          {isReplicate && (
            <div className="lg:col-span-2">
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
                <h2 className="text-xl font-bold mb-4">Cloud Model Configuration</h2>
                <div className="space-y-4">
                  <div>
                    <div className="text-sm text-zinc-400">Model Name</div>
                    <div className="text-lg font-mono">{model.model}</div>
                  </div>
                  <div>
                    <div className="text-sm text-zinc-400">API Endpoint</div>
                    <div className="text-lg font-mono break-all">{model.endpoint}</div>
                  </div>
                  {model.timeout && (
                    <div>
                      <div className="text-sm text-zinc-400">Timeout</div>
                      <div className="text-lg">{model.timeout}s</div>
                    </div>
                  )}
                  {model.max_retries !== undefined && (
                    <div>
                      <div className="text-sm text-zinc-400">Max Retries</div>
                      <div className="text-lg">{model.max_retries}</div>
                    </div>
                  )}
                  <div className="mt-6 p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                    <div className="text-sm text-blue-300">
                      This is a cloud-based model running on Replicate. No local resources are consumed.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <Footer />
    </div>
  );
}
