import React from 'react';
import { ResultActions } from './ResultActions';
import { JsonResultView } from './JsonResultView';
import { TextResultView } from './TextResultView';
import { TableResultView } from './TableResultView';

const ResultFormat = {
  MCP_CONTENT: 'mcp_content',
  TABLE: 'table',
  JSON_OBJECT: 'json_object',
  TEXT_BLOCK: 'text_block',
  TEXT: 'text',
  PRIMITIVE: 'primitive',
} as const;

type ResultFormatType = typeof ResultFormat[keyof typeof ResultFormat];

function detectResultFormat(result: unknown): ResultFormatType {
  // MCP content array
  if (
    Array.isArray(result) &&
    result.length > 0 &&
    result.every((item: unknown) =>
      typeof item === 'object' && item !== null &&
      'type' in item && 'text' in item
    )
  ) {
    return ResultFormat.MCP_CONTENT;
  }

  // Table (array of similar objects)
  if (
    Array.isArray(result) &&
    result.length > 0 &&
    result.every((item: unknown) => typeof item === 'object' && item !== null)
  ) {
    const keys = Object.keys(result[0] as Record<string, unknown>);
    if (
      result.every(
        (item: unknown) =>
          keys.every((k) => k in (item as Record<string, unknown>)) &&
          Object.keys(item as Record<string, unknown>).length === keys.length
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
  result: unknown;
  error?: string;
  loading?: boolean;
  executionTime?: number | null;
}

export const ToolResult: React.FC<ToolResultProps> = ({
  result,
  error,
  executionTime,
}) => {
  const format = result !== null && !error ? detectResultFormat(result) : ResultFormat.PRIMITIVE;

  const handleCopy = () => {
    let textToCopy: string;

    try {
      switch (format) {
        case ResultFormat.TEXT:
        case ResultFormat.TEXT_BLOCK:
          textToCopy = String(result);
          break;
        case ResultFormat.MCP_CONTENT:
          textToCopy = Array.isArray(result)
            ? result.map((c: { text: string }) => c.text).join('\n')
            : String(result);
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
      {executionTime !== null && executionTime !== undefined && (
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
          {format === ResultFormat.MCP_CONTENT && Array.isArray(result) && (
            <TextResultView
              text={result.map((c: { text: string }) => c.text).join('\n')}
              isLongText={true}
            />
          )}
          {format === ResultFormat.TABLE && Array.isArray(result) && (
            <TableResultView data={result as Array<Record<string, unknown>>} />
          )}
          {format === ResultFormat.JSON_OBJECT && <JsonResultView data={result} />}
          {format === ResultFormat.TEXT_BLOCK && typeof result === 'string' && (
            <TextResultView text={result} isLongText={true} />
          )}
          {format === ResultFormat.TEXT && typeof result === 'string' && (
            <TextResultView text={result} />
          )}
          {format === ResultFormat.PRIMITIVE && (
            <TextResultView text={JSON.stringify(result)} />
          )}
        </>
      )}
    </div>
  );
};
