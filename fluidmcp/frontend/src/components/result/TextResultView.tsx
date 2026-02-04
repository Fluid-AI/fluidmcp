import React from 'react';

interface TextResultViewProps {
  text: string;
  isLongText?: boolean;
}

export const TextResultView: React.FC<TextResultViewProps> = ({
  text,
  isLongText = false,
}) => {
  // Handle undefined/null text
  const displayText = text ?? 'No result';

  return (
    <div style={{ 
      color: '#e5e7eb',
      fontSize: isLongText ? '0.95rem' : '1rem',
      lineHeight: '1.8',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      fontFamily: isLongText ? 'ui-monospace, monospace' : 'system-ui, -apple-system, sans-serif',
      padding: '0.5rem 0'
    }}>
      {displayText}
    </div>
  );
};
