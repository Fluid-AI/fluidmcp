import React from 'react';

interface ResultActionsProps {
  onCopy: () => void;
  onDownload: () => void;
}

export const ResultActions: React.FC<ResultActionsProps> = ({
  onCopy,
  onDownload,
}) => {
  return (
    <div className="result-actions">
      <button onClick={onCopy} className="btn-text">
        Copy
      </button>
      <button onClick={onDownload} className="btn-text">
        Download JSON
      </button>
    </div>
  );
};
