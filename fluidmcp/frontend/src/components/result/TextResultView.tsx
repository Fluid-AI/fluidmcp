import React from 'react';

interface TextResultViewProps {
  text: string;
  isLongText?: boolean;
}

export const TextResultView: React.FC<TextResultViewProps> = ({
  text,
  isLongText = false,
}) => {
  return (
    <div className={`result-text ${isLongText ? 'result-text-long' : ''}`}>
      {text}
    </div>
  );
};
