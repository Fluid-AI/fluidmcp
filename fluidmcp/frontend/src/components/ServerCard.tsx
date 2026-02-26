import React from "react";
import { AlertCircle, Play } from "lucide-react";
import type { Server } from "../types/server";

interface ServerCardProps {
  server: Server;
  onStart: () => void;
  onViewDetails: () => void;
  isStarting: boolean;
}

function ServerCard({
  server,
  onStart,
  onViewDetails,
  isStarting,
}: ServerCardProps) {
  const isStopped =
    server.status?.state === "stopped" ||
    server.status?.state === "failed" ||
    server.status?.state === "not_found" ||
    !server.status;

  const toolCount = server.tools?.length || 0;
  const lastUpdated = server.updated_at
    ? new Date(server.updated_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  const getStatusColor = () => {
    const state = server.status?.state || "stopped";
    switch (state) {
      case "running":
        return "text-green-400 bg-green-500/10 border-green-500/30";
      case "stopped":
        return "text-zinc-400 bg-zinc-500/10 border-zinc-500/30";
      case "failed":
        return "text-red-400 bg-red-500/10 border-red-500/30";
      case "starting":
      case "restarting":
        return "text-yellow-400 bg-yellow-500/10 border-yellow-500/30";
      default:
        return "text-zinc-400 bg-zinc-500/10 border-zinc-500/30";
    }
  };

  return (
    <div className="relative group">
      {/* Glow effect - removed animate-pulse */}
      <div
        className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-2xl opacity-0 group-hover:opacity-20 blur transition-all duration-500"
      />

      {/* Card */}
      <div className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6 shadow-2xl transition-all duration-300 hover:scale-[1.02] hover:shadow-indigo-500/20">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-xl font-bold text-white truncate">
              {server.name}
            </h3>
          </div>

          {/* Status indicator */}
          <div className={`flex items-center gap-1 px-2 py-1 border rounded-full whitespace-nowrap ${getStatusColor()}`}>
            {server.status?.state === "failed" && <AlertCircle className="w-3 h-3" />}
            <span className="text-xs font-medium capitalize">
              {server.status?.state || "stopped"}
            </span>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-zinc-300 mb-4 line-clamp-2 min-h-[2.5rem]">
          {server.description || "No description available"}
        </p>

        {/* Metadata */}
        <div className="flex items-center gap-4 mb-4 text-sm">
          {toolCount > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400">🔧</span>
              <span className="text-zinc-300">
                {toolCount} {toolCount === 1 ? 'tool' : 'tools'}
              </span>
            </div>
          )}
          {lastUpdated && (
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-400 text-xs">
                Updated {lastUpdated}
              </span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-4 border-t border-zinc-700/50">
          {isStopped && (
            <button
              onClick={onStart}
              disabled={isStarting}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play className="w-4 h-4" />
              <span>{isStarting ? "Starting..." : "Start"}</span>
            </button>
          )}
          <button
            onClick={onViewDetails}
            className={`${isStopped ? 'flex-1' : 'w-full'} px-4 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200`}
          >
            Details
          </button>
        </div>
      </div>
    </div>
  );
}

export default React.memo(ServerCard);