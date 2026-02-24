import { AlertCircle, Activity, Cloud, Cpu, RefreshCw, Square } from "lucide-react";
import type { LLMModel } from "../types/llm";
import { isProcessBasedModel, isReplicateModel } from "../types/llm";

interface LLMModelCardProps {
  model: LLMModel;
  onRestart?: () => void;
  onStop?: () => void;
  onViewDetails: () => void;
  isRestarting?: boolean;
  isStopping?: boolean;
}

export default function LLMModelCard({
  model,
  onRestart,
  onStop,
  onViewDetails,
  isRestarting = false,
  isStopping = false,
}: LLMModelCardProps) {
  const isRunning = model.is_running;
  const isHealthy = model.is_healthy;
  const isProcess = isProcessBasedModel(model);
  const isReplicate = isReplicateModel(model);

  const getStatusColor = () => {
    if (!isRunning) {
      return "text-zinc-400 bg-zinc-500/10 border-zinc-500/30";
    }
    if (!isHealthy) {
      return "text-red-400 bg-red-500/10 border-red-500/30";
    }
    return "text-green-400 bg-green-500/10 border-green-500/30";
  };

  const getHealthBadge = () => {
    if (!isRunning) {
      return null;
    }
    if (isHealthy) {
      return (
        <div className="flex items-center gap-1 px-2 py-1 border rounded-full bg-green-500/10 border-green-500/30 text-green-400">
          <Activity className="w-3 h-3" />
          <span className="text-xs font-medium">Healthy</span>
        </div>
      );
    }
    return (
      <div className="flex items-center gap-1 px-2 py-1 border rounded-full bg-red-500/10 border-red-500/30 text-red-400">
        <AlertCircle className="w-3 h-3" />
        <span className="text-xs font-medium">Unhealthy</span>
      </div>
    );
  };

  const formatUptime = (seconds: number | null) => {
    if (!seconds) return "N/A";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  return (
    <div className="relative group">
      {/* Glow effect */}
      <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-2xl opacity-0 group-hover:opacity-20 blur transition-all duration-500" />

      {/* Card */}
      <div className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6 shadow-2xl transition-all duration-300 hover:scale-[1.02] hover:shadow-indigo-500/20">
        {/* Header */}
        <div className="flex items-start justify-between mb-4 gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              {isReplicate ? (
                <Cloud className="w-5 h-5 text-purple-400" />
              ) : (
                <Cpu className="w-5 h-5 text-blue-400" />
              )}
              <h3 className="text-xl font-bold text-white truncate">{model.id}</h3>
            </div>
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="px-2 py-0.5 bg-zinc-700/50 rounded">
                {isReplicate ? "Cloud" : "Local Process"}
              </span>
              {isProcess && (
                <span className="px-2 py-0.5 bg-zinc-700/50 rounded">
                  Restarts: {model.restart_count}/{model.max_restarts}
                </span>
              )}
            </div>
          </div>

          {/* Status indicators */}
          <div className="flex flex-col items-end gap-2">
            <div className={`flex items-center gap-1 px-2 py-1 border rounded-full whitespace-nowrap ${getStatusColor()}`}>
              <span className="text-xs font-medium">{isRunning ? "Running" : "Stopped"}</span>
            </div>
            {getHealthBadge()}
          </div>
        </div>

        {/* Health Message */}
        <div className="mb-4">
          <p className="text-sm text-zinc-300 line-clamp-2 min-h-[2.5rem]">
            {model.health_message || "No health information available"}
          </p>
        </div>

        {/* Metadata */}
        <div className="flex items-center gap-4 mb-4 text-sm flex-wrap">
          {isProcess && model.uptime_seconds !== null && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400">⏱️</span>
              <span className="text-zinc-300">Uptime: {formatUptime(model.uptime_seconds)}</span>
            </div>
          )}
          {isReplicate && model.model && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400">🤖</span>
              <span className="text-zinc-300 truncate max-w-[200px]">{model.model}</span>
            </div>
          )}
          {isProcess && model.consecutive_health_failures > 0 && (
            <div className="flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4 text-red-400" />
              <span className="text-red-300">{model.consecutive_health_failures} failures</span>
            </div>
          )}
        </div>

        {/* CUDA OOM Warning */}
        {isProcess && model.has_cuda_oom && (
          <div className="mb-4 p-2 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span className="text-xs text-red-300">CUDA Out of Memory detected</span>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-4 border-t border-zinc-700/50">
          {isProcess && isRunning && onRestart && (
            <button
              onClick={onRestart}
              disabled={isRestarting}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-all duration-200 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-4 h-4 ${isRestarting ? 'animate-spin' : ''}`} />
              <span>{isRestarting ? "Restarting..." : "Restart"}</span>
            </button>
          )}
          {isProcess && isRunning && onStop && (
            <button
              onClick={onStop}
              disabled={isStopping}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-all duration-200 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Square className="w-4 h-4" />
              <span>{isStopping ? "Stopping..." : "Stop"}</span>
            </button>
          )}
          <button
            onClick={onViewDetails}
            className="flex-1 px-4 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200"
          >
            Details
          </button>
        </div>
      </div>
    </div>
  );
}
