import React, { useState, useEffect } from 'react';
import { ResultActions } from './ResultActions';
import { JsonResultView } from './JsonResultView';
import { TextResultView } from './TextResultView';
import { TableResultView } from './TableResultView';

enum ResultFormat {
  MCP_CONTENT = 'mcp_content',
  TABLE = 'table',
  JSON_OBJECT = 'json_object',
  TEXT_BLOCK = 'text_block',
  TEXT = 'text',
  PRIMITIVE = 'primitive',
}

function detectResultFormat(result: any): ResultFormat {
  // MCP content array
  if (
    Array.isArray(result) &&
    result.length > 0 &&
    result.every((item) => item.type && item.text)
  ) {
    return ResultFormat.MCP_CONTENT;
  }

  // Table (array of similar objects)
  if (
    Array.isArray(result) &&
    result.length > 0 &&
    result.every((item) => typeof item === 'object' && item !== null)
  ) {
    const keys = Object.keys(result[0]);
    if (
      result.every(
        (item) =>
          keys.every((k) => k in item) && Object.keys(item).length === keys.length
      )
    ) {
      return ResultFormat.TABLE;
    }
    return ResultFormat.JSON_OBJECT;
  }

  // Text
  if (typeof result === 'string') {
    if (result.includes('\n') && result.length > 200) {
      return ResultFormat.TEXT_BLOCK;
    }
    return ResultFormat.TEXT;
  }

  // Complex objects
  if (typeof result === 'object' && result !== null) {
    return ResultFormat.JSON_OBJECT;
  }

  return ResultFormat.PRIMITIVE;
}

interface ToolResultProps {
  result: any;
  error?: string;
  loading?: boolean;
  executionTime?: number | null;
}

export const ToolResult: React.FC<ToolResultProps> = ({
  result,
  error,
  loading,
  executionTime,
}) => {
  const [format, setFormat] = useState<ResultFormat>(ResultFormat.PRIMITIVE);

  useEffect(() => {
    if (result !== null && !error) {
      setFormat(detectResultFormat(result));
    }
  }, [result, error]);

  const handleCopy = () => {
    let textToCopy: string;

    try {
      switch (format) {
        case ResultFormat.TEXT:
        case ResultFormat.TEXT_BLOCK:
          textToCopy = String(result);
          break;
        case ResultFormat.MCP_CONTENT:
          textToCopy = result.map((c: any) => c.text).join('\n');
          break;
        default:
          textToCopy = JSON.stringify(result, null, 2);
      }

      navigator.clipboard.writeText(textToCopy);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleDownload = () => {
    try {
      const dataStr = JSON.stringify(result, null, 2);
      const blob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tool-result-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download:', err);
      alert('Failed to download result. It may contain circular references.');
    }
  };

  return (
    <div className="tool-runner-section">
      <div className="section-header">
        <h2>Results</h2>
        {result !== null && !error && (
          <ResultActions
            result={result}
            onCopy={handleCopy}
            onDownload={handleDownload}
          />
        )}
      </div>

      {/* Execution Info */}
      {executionTime !== null && (
        <div className="execution-info">
          <span>
            Execution Time: <strong>{executionTime.toFixed(2)}s</strong>
          </span>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="result-error">
          <h3>Error</h3>
          <p>{error}</p>
        </div>
      )}

      {/* Result Display */}
      {!error && result !== null && (
        <>
          {format === ResultFormat.MCP_CONTENT && (
            <TextResultView
              text={result.map((c: any) => c.text).join('\n')}
              isLongText={true}
            />
          )}
          {format === ResultFormat.TABLE && <TableResultView data={result} />}
          {format === ResultFormat.JSON_OBJECT && <JsonResultView data={result} />}
          {format === ResultFormat.TEXT_BLOCK && (
            <TextResultView text={result} isLongText={true} />
          )}
          {format === ResultFormat.TEXT && <TextResultView text={result} />}
          {format === ResultFormat.PRIMITIVE && (
            <TextResultView text={JSON.stringify(result)} />
          )}
        </>
      )}
    </div>
  );
};
