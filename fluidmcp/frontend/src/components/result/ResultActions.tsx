import React from 'react';

interface ResultActionsProps {
  onCopy: () => void;
  onDownload: () => void;
  canExpand?: boolean;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

export const ResultActions: React.FC<ResultActionsProps> = ({
  onCopy,
  onDownload,
  canExpand = false,
  isExpanded = false,
  onToggleExpand,
}) => {
  return (
    <div className="result-actions">
      {canExpand && onToggleExpand && (
        <button onClick={onToggleExpand} className="btn-text">
          {isExpanded ? 'Collapse All' : 'Expand All'}
        </button>
      )}
      <button onClick={onCopy} className="btn-text">
        Copy
      </button>
      <button onClick={onDownload} className="btn-text">
        Download JSON
      </button>
    </div>
  );
};
