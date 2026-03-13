import React from "react";
import { AlertCircle, Activity, Cloud, Cpu, MessageSquare } from "lucide-react";
import type { LLMModel } from "../types/llm";
import { isProcessBasedModel, isReplicateModel } from "../types/llm";

interface LLMModelCardProps {
  model: LLMModel;
  onViewDetails: () => void;
  onQuickTry: () => void;
}

function LLMModelCard({
  model,
  onViewDetails,
  onQuickTry,
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

  const formatUptime = (seconds: number | null) => {
    if (seconds === null || seconds === undefined) return "N/A";
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
        <div className="flex items-center justify-between mb-4 gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              {isReplicate ? (
                <Cloud className="w-5 h-5 text-purple-400 flex-shrink-0" />
              ) : (
                <Cpu className="w-5 h-5 text-blue-400 flex-shrink-0" />
              )}
              <h3 className="text-xl font-bold text-white truncate" title={model.id}>
                {model.id}
              </h3>
            </div>
          </div>

          {/* Status indicator */}
          <div className={`flex items-center gap-1 px-2 py-1 border rounded-full whitespace-nowrap ${getStatusColor()}`}>
            <span className="text-xs font-medium">{isRunning ? "Running" : "Stopped"}</span>
          </div>
        </div>

        {/* Health + Type info */}
        <p className="text-sm text-zinc-300 mb-4 line-clamp-2 min-h-[2.5rem]">
          {model.health_message || (isReplicate ? "Cloud inference model" : "Local process model")}
        </p>

        {/* Metadata */}
        <div className="flex items-center gap-4 mb-4 text-sm flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-400 text-xs px-2 py-0.5 bg-zinc-700/50 rounded">
              {isReplicate ? "Cloud" : "Local Process"}
            </span>
          </div>
          {isRunning && (
            <div className="flex items-center gap-1">
              {isHealthy ? (
                <Activity className="w-3 h-3 text-green-400" />
              ) : (
                <AlertCircle className="w-3 h-3 text-red-400" />
              )}
              <span className={`text-xs ${isHealthy ? 'text-green-400' : 'text-red-400'}`}>
                {isHealthy ? "Healthy" : "Unhealthy"}
              </span>
            </div>
          )}
          {isProcess && model.uptime_seconds !== null && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400 text-xs">
                Uptime: {formatUptime(model.uptime_seconds)}
              </span>
            </div>
          )}
          {isReplicate && model.model && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400 text-xs truncate max-w-[150px]" title={model.model}>
                {model.model}
              </span>
            </div>
          )}
        </div>

        {/* Actions - matching ServerCard pattern */}
        <div className="flex items-center gap-2 pt-4 border-t border-zinc-700/50">
          <button
            onClick={onQuickTry}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200 hover:shadow-lg"
          >
            <MessageSquare className="w-4 h-4" />
            <span>Quick Try</span>
          </button>
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

export default React.memo(LLMModelCard);
