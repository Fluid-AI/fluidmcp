import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, RefreshCw, Square, Activity, AlertCircle, Clock, PlayCircle, Edit2, Trash2 } from "lucide-react";
import * as Collapsible from "@radix-ui/react-collapsible";
import apiClient from "../services/api";
import type { LLMModel, LLMModelLogsResponse, ReplicateModel } from "../types/llm";
import { isProcessBasedModel, isReplicateModel } from "../types/llm";

interface LLMModelRowProps {
  model: LLMModel;
  onRestart: (modelId: string) => Promise<void>;
  onStop: (modelId: string) => Promise<void>;
  onHealthCheck: (modelId: string) => Promise<void>;
  onEdit?: (model: ReplicateModel) => void;
  onDelete?: (modelId: string) => void;
  isPerformingAction: boolean;
}

export default function LLMModelRow({ model, onRestart, onStop, onHealthCheck, onEdit, onDelete, isPerformingAction }: LLMModelRowProps) {
  const navigate = useNavigate();
  const [isExpanded, setIsExpanded] = useState(false);
  const [logsLoaded, setLogsLoaded] = useState(false);
  const [cachedLogs, setCachedLogs] = useState<LLMModelLogsResponse | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);

  const isProcess = isProcessBasedModel(model);
  const isReplicate = isReplicateModel(model);

  // Lazy load logs when expanded
  useEffect(() => {
    if (isExpanded && !logsLoaded && isProcess) {
      setLogsLoading(true);
      apiClient.getLLMModelLogs(model.id, 100)
        .then(data => {
          setCachedLogs(data);
          setLogsLoaded(true);
        })
        .catch(err => {
          console.error('Failed to fetch logs:', err);
        })
        .finally(() => {
          setLogsLoading(false);
        });
    }
  }, [isExpanded, logsLoaded, model.id, isProcess]);

  const formatUptime = (seconds: number | null) => {
    if (seconds === null || seconds === undefined) return "N/A";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
    return `${minutes}m ${secs}s`;
  };

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return "Never";
    return new Date(timestamp).toLocaleString();
  };

  const handleQuickTry = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row expansion
    navigate(`/llm/playground?model=${model.id}`);
  };

  return (
    <Collapsible.Root
      open={isExpanded}
      onOpenChange={setIsExpanded}
      className="bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl overflow-hidden transition-all hover:border-zinc-600/50"
    >
      {/* Header - Always Visible */}
      <Collapsible.Trigger asChild>
        <button className="w-full p-6 flex items-center justify-between cursor-pointer group">
          <div className="flex items-center gap-4 flex-1">
            {/* Left: Icon + Model ID + Type Badge */}
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                model.is_running ? 'bg-green-500/20 text-green-400' : 'bg-zinc-700/50 text-zinc-400'
              }`}>
                <PlayCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-left">{model.id}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                    isProcess ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
                  }`}>
                    {model.type}
                  </span>
                </div>
              </div>
            </div>

            {/* Middle: Status Badges + Quick Stats */}
            <div className="flex items-center gap-3 ml-auto mr-4">
              {/* Running/Stopped Status */}
              <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                model.is_running
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-zinc-700 text-zinc-400'
              }`}>
                {model.is_running ? 'Running' : 'Stopped'}
              </span>

              {/* Health Status */}
              <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                model.is_healthy
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-red-500/20 text-red-400'
              }`}>
                {model.is_healthy ? 'Healthy' : 'Unhealthy'}
              </span>

              {/* Quick Stats for Process Models */}
              {isProcess && (
                <>
                  {model.uptime_seconds !== null && (
                    <span className="text-xs text-zinc-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatUptime(model.uptime_seconds)}
                    </span>
                  )}
                  {model.restart_count > 0 && (
                    <span className="text-xs text-zinc-400">
                      {model.restart_count} restarts
                    </span>
                  )}
                </>
              )}

              {/* CUDA OOM Warning */}
              {isProcess && model.has_cuda_oom && (
                <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-500/20 text-red-400">
                  CUDA OOM
                </span>
              )}
            </div>
          </div>

          {/* Right: Quick Try Button + Chevron */}
          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            {model.is_running && model.is_healthy && (
              <button
                onClick={handleQuickTry}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-all"
              >
                Quick Try
              </button>
            )}
            <ChevronDown
              className={`w-5 h-5 text-zinc-400 transition-transform duration-200 ${
                isExpanded ? 'transform rotate-180' : ''
              }`}
            />
          </div>
        </button>
      </Collapsible.Trigger>

      {/* Expandable Content */}
      <Collapsible.Content className="overflow-hidden">
        <div className="border-t border-zinc-700/50 p-6 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Status & Warnings */}
            <div className="space-y-4">
              {/* Status Card */}
              <div className="bg-zinc-800/50 rounded-xl p-4">
                <h4 className="text-sm font-semibold mb-3">Status Details</h4>
                <div className="space-y-2 text-sm">
                  <div>
                    <div className="text-zinc-400">State</div>
                    <div className="font-semibold">{model.is_running ? 'Running' : 'Stopped'}</div>
                  </div>
                  <div>
                    <div className="text-zinc-400">Health</div>
                    <div className="font-semibold">{model.health_message}</div>
                  </div>
                  {isProcess && (
                    <>
                      <div>
                        <div className="text-zinc-400">Uptime</div>
                        <div className="font-semibold flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatUptime(model.uptime_seconds)}
                        </div>
                      </div>
                      <div>
                        <div className="text-zinc-400">Restart Count</div>
                        <div className="font-semibold">
                          {model.restart_count} / {model.max_restarts}
                        </div>
                      </div>
                      <div>
                        <div className="text-zinc-400">Restart Policy</div>
                        <div className="font-semibold capitalize">{model.restart_policy}</div>
                      </div>
                    </>
                  )}
                  {isReplicate && (
                    <>
                      <div>
                        <div className="text-zinc-400">Model</div>
                        <div className="text-xs font-mono break-all">{model.model}</div>
                      </div>
                      <div>
                        <div className="text-zinc-400">Endpoint</div>
                        <div className="text-xs font-mono break-all">{model.endpoint}</div>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Warnings */}
              {isProcess && model.consecutive_health_failures > 0 && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-sm font-semibold text-red-400">Health Failures</div>
                      <div className="text-xs text-red-300 mt-1">
                        {model.consecutive_health_failures} consecutive failure(s)
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {isProcess && model.has_cuda_oom && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-sm font-semibold text-red-400">CUDA OOM Detected</div>
                      <div className="text-xs text-red-300 mt-1">
                        GPU memory exhausted. Consider reducing batch size.
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Timeline */}
              {isProcess && (
                <div className="bg-zinc-800/50 rounded-xl p-4">
                  <h4 className="text-sm font-semibold mb-3">Timeline</h4>
                  <div className="space-y-2 text-xs">
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

              {/* Action Buttons */}
              <div className="space-y-4">
                {/* Process-specific actions */}
                {isProcess && model.is_running && (
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => onRestart(model.id)}
                      disabled={isPerformingAction}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
                    >
                      <RefreshCw className={`w-4 h-4 ${isPerformingAction ? 'animate-spin' : ''}`} />
                      Restart
                    </button>
                    <button
                      onClick={() => onStop(model.id)}
                      disabled={isPerformingAction}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
                    >
                      <Square className="w-4 h-4" />
                      Stop
                    </button>
                    <button
                      onClick={() => onHealthCheck(model.id)}
                      disabled={isPerformingAction}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
                    >
                      <Activity className="w-4 h-4" />
                      Health Check
                    </button>
                  </div>
                )}

                {/* Edit and Delete actions (available for all models, especially Replicate) */}
                {isReplicate && onEdit && onDelete && (
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => onEdit(model as ReplicateModel)}
                      disabled={isPerformingAction}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
                    >
                      <Edit2 className="w-4 h-4" />
                      Edit
                    </button>
                    <button
                      onClick={() => onDelete(model.id)}
                      disabled={isPerformingAction}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-all disabled:opacity-50"
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Right: Logs or Config */}
            {isProcess && (
              <div className="lg:col-span-2">
                <div className="bg-zinc-800/50 rounded-xl overflow-hidden">
                  <div className="flex items-center justify-between p-4 border-b border-zinc-700/50">
                    <h4 className="text-sm font-semibold">Logs (stderr)</h4>
                    <button
                      onClick={() => {
                        setLogsLoaded(false); // Force reload
                      }}
                      disabled={logsLoading}
                      className="flex items-center gap-2 px-3 py-1 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-xs transition-all disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3 h-3 ${logsLoading ? 'animate-spin' : ''}`} />
                      Refresh
                    </button>
                  </div>
                  <div className="p-4 bg-black font-mono text-xs overflow-x-auto max-h-[400px] overflow-y-auto">
                    {logsLoading ? (
                      <div className="text-zinc-500">Loading logs...</div>
                    ) : cachedLogs?.lines && cachedLogs.lines.length > 0 ? (
                      <pre className="text-zinc-300 whitespace-pre-wrap break-words">
                        {cachedLogs.lines.join('')}
                      </pre>
                    ) : (
                      <div className="text-zinc-500">
                        {cachedLogs?.message || "No logs available"}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {isReplicate && (
              <div className="lg:col-span-2">
                <div className="bg-zinc-800/50 rounded-xl p-4">
                  <h4 className="text-sm font-semibold mb-4">Cloud Model Configuration</h4>
                  <div className="space-y-3 text-sm">
                    <div>
                      <div className="text-zinc-400">Model Name</div>
                      <div className="font-mono">{model.model}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">API Endpoint</div>
                      <div className="font-mono break-all text-xs">{model.endpoint}</div>
                    </div>
                    {model.timeout && (
                      <div>
                        <div className="text-zinc-400">Timeout</div>
                        <div>{model.timeout}s</div>
                      </div>
                    )}
                    {model.max_retries !== undefined && (
                      <div>
                        <div className="text-zinc-400">Max Retries</div>
                        <div>{model.max_retries}</div>
                      </div>
                    )}
                    <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg">
                      <div className="text-xs text-purple-300">
                        This is a cloud-based model running on Replicate. No local resources are consumed.
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
