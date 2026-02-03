/**
 * Premium ServerCard Component
 * A glassmorphic card with smooth animations and gradient effects
 */

import { useState } from 'react';
import { Download, Star, ChevronDown, Shield, AlertCircle } from 'lucide-react';

export interface ServerPackageVersion {
  id: string;
  version: string;
  isLatest?: boolean;
  createdAt: string;
}

export interface ServerCardData {
  packageName: string;
  description?: string;
  author: string;
  versions: ServerPackageVersion[];
  isVerified: boolean;
  sourceType: string;
  downloadsCount?: number;
  starsCount?: number;
  reportedIssuesCount?: number;
}

export interface ServerCardProps {
  data: ServerCardData;
  defaultVersionIndex?: number;
  isStarred?: boolean;
  onStar?: () => void;
  onDownload?: (version: ServerPackageVersion) => void;
  className?: string;
}

export function EnhancedServerCard({
  data,
  defaultVersionIndex = 0,
  isStarred = false,
  onStar,
  onDownload,
  className = '',
}: ServerCardProps) {
  const [selectedVersionIndex, setSelectedVersionIndex] = useState(defaultVersionIndex);
  const [isVersionDropdownOpen, setIsVersionDropdownOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const selectedVersion = data.versions[selectedVersionIndex];
  const hasMultipleVersions = data.versions.length > 1;

  const handleVersionSelect = (index: number) => {
    setSelectedVersionIndex(index);
    setIsVersionDropdownOpen(false);
  };

  const handleDownload = () => {
    if (onDownload && selectedVersion) {
      onDownload(selectedVersion);
    }
  };

  return (
    <div
      className={`relative group ${className}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Glow effect */}
      <div
        className={`absolute -inset-0.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-2xl opacity-0 group-hover:opacity-20 blur transition-all duration-500 ${
          isHovered ? 'animate-pulse' : ''
        }`}
      />

      {/* Card */}
      <div className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6 shadow-2xl transition-all duration-300 hover:scale-[1.02] hover:shadow-indigo-500/20">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-xl font-bold text-white truncate">
                {data.packageName}
              </h3>
              {data.isVerified && (
                <div className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 border border-green-500/30 rounded-full">
                  <Shield className="w-3 h-3 text-green-400" />
                  <span className="text-xs text-green-400 font-medium">Verified</span>
                </div>
              )}
              {!data.isVerified && (
                <div className="flex items-center gap-1 px-2 py-0.5 bg-yellow-500/10 border border-yellow-500/30 rounded-full">
                  <AlertCircle className="w-3 h-3 text-yellow-400" />
                  <span className="text-xs text-yellow-400 font-medium">Under Review</span>
                </div>
              )}
            </div>
            <p className="text-sm text-zinc-400">by {data.author}</p>
          </div>

          {/* Star button */}
          {onStar && (
            <button
              onClick={onStar}
              className="ml-2 p-2 rounded-lg hover:bg-zinc-700/50 transition-colors"
              aria-label="Star package"
            >
              <Star
                className={`w-5 h-5 transition-colors ${
                  isStarred
                    ? 'fill-yellow-400 text-yellow-400'
                    : 'text-zinc-400 hover:text-yellow-400'
                }`}
              />
            </button>
          )}
        </div>

        {/* Description */}
        {data.description && (
          <p className="text-sm text-zinc-300 mb-4 line-clamp-2 min-h-[2.5rem]">
            {data.description}
          </p>
        )}

        {/* Version selector and Download button */}
        <div className="flex items-center gap-2 mb-4">
          {hasMultipleVersions ? (
            <div className="relative flex-1">
              <button
                onClick={() => setIsVersionDropdownOpen(!isVersionDropdownOpen)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 bg-zinc-800/50 border border-zinc-600/50 rounded-lg hover:bg-zinc-700/50 transition-colors"
              >
                <span className="text-sm text-white">
                  v{selectedVersion.version}
                  {selectedVersion.isLatest && (
                    <span className="ml-2 text-xs text-green-400">(latest)</span>
                  )}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-zinc-400 transition-transform ${
                    isVersionDropdownOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {/* Dropdown */}
              {isVersionDropdownOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl z-10 overflow-hidden">
                  {data.versions.map((version, index) => (
                    <button
                      key={version.id}
                      onClick={() => handleVersionSelect(index)}
                      className="w-full flex items-center justify-between px-3 py-2 text-sm text-white hover:bg-zinc-700 transition-colors"
                    >
                      <span>v{version.version}</span>
                      {version.isLatest && (
                        <span className="text-xs text-green-400">latest</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 px-3 py-2 bg-zinc-800/50 border border-zinc-600/50 rounded-lg">
              <span className="text-sm text-white">
                v{selectedVersion.version}
                {selectedVersion.isLatest && (
                  <span className="ml-2 text-xs text-green-400">(latest)</span>
                )}
              </span>
            </div>
          )}

          <button
            onClick={handleDownload}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white rounded-lg font-medium transition-all duration-200 hover:shadow-lg hover:shadow-indigo-500/50"
          >
            <Download className="w-4 h-4" />
            <span className="hidden sm:inline">Download</span>
          </button>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-4 pt-4 border-t border-zinc-700/50">
          <div className="flex items-center gap-1.5">
            <Download className="w-4 h-4 text-zinc-400" />
            <span className="text-sm text-zinc-300">
              {data.downloadsCount?.toLocaleString() || 0}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Star className="w-4 h-4 text-zinc-400" />
            <span className="text-sm text-zinc-300">
              {data.starsCount?.toLocaleString() || 0}
            </span>
          </div>
          {(data.reportedIssuesCount || 0) > 0 && (
            <div className="flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4 text-yellow-400" />
              <span className="text-sm text-yellow-300">
                {data.reportedIssuesCount}
              </span>
            </div>
          )}
          <div className="ml-auto">
            <span className="text-xs px-2 py-1 bg-zinc-800/50 border border-zinc-600/50 rounded text-zinc-400">
              {data.sourceType}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default EnhancedServerCard;
