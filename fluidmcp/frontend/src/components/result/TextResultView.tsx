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
    <div className={`result-text ${isLongText ? 'result-text-long' : ''}`}>
      {displayText}
    </div>
  );
};
