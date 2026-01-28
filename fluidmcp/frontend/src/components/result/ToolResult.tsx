import React, { useState } from 'react';
import { ResultActions } from './ResultActions';
import { JsonResultView } from './JsonResultView';
import { TextResultView } from './TextResultView';
import { TableResultView } from './TableResultView';
import { McpContentView } from './McpContentView';
import { ErrorBoundary } from '../ErrorBoundary';

const ResultFormat = {
  MCP_CONTENT: 'mcp_content',
  TABLE: 'table',
  JSON_OBJECT: 'json_object',
  TEXT_BLOCK: 'text_block',
  TEXT: 'text',
  PRIMITIVE: 'primitive',
} as const;

type ResultFormatType = typeof ResultFormat[keyof typeof ResultFormat];

// Type definitions for MCP result structures
interface McpContent {
  type: 'text' | 'image' | 'resource' | string;
  text?: string;
  data?: string;
  mimeType?: string;
  uri?: string;
}

interface McpResult {
  content: McpContent[];
}

// Type guard to check if result is an MCP result object
function isMcpResult(result: unknown): result is McpResult {
  return (
    typeof result === 'object' &&
    result !== null &&
    'content' in result &&
    Array.isArray((result as McpResult).content)
  );
}

// Type guard to check if result is an MCP content array
function isMcpContentArray(result: unknown): result is McpContent[] {
  return (
    Array.isArray(result) &&
    result.length > 0 &&
    result.every((item: unknown) =>
      typeof item === 'object' && item !== null && 'type' in item
    )
  );
}

function detectResultFormat(result: unknown): ResultFormatType {
  // MCP result object with content array (standard MCP response format)
  if (isMcpResult(result)) {
    return ResultFormat.MCP_CONTENT;
  }

  // MCP content array (direct array format) - check for objects with 'type' field (text, image, resource, etc.)
  if (isMcpContentArray(result)) {
    return ResultFormat.MCP_CONTENT;
  }

  // Table (array of similar flat objects)
  if (
    Array.isArray(result) &&
    result.length > 0 &&
    result.every((item: unknown) => typeof item === 'object' && item !== null)
  ) {
    // Helper to check if object is flat (no nested objects)
    const isFlatObject = (obj: Record<string, unknown>) =>
      Object.values(obj).every(
        v => typeof v !== 'object' || v === null
      );

    const keys = Object.keys(result[0] as Record<string, unknown>);
    if (
      result.every(
        (item: unknown) => {
          const itemObj = item as Record<string, unknown>;
          return (
            isFlatObject(itemObj) &&
            keys.every((k) => k in itemObj) &&
            Object.keys(itemObj).length === keys.length
          );
        }
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

// Extract text to copy based on result format
function extractCopyText(result: unknown, format: ResultFormatType): string {
  switch (format) {
    case ResultFormat.TEXT:
    case ResultFormat.TEXT_BLOCK:
      return String(result);

    case ResultFormat.MCP_CONTENT:
      const contentArray = isMcpContentArray(result)
        ? result
        : isMcpResult(result)
        ? result.content
        : [];

      return contentArray.map((c) => {
        if (c.type === 'text' && c.text) return c.text;
        if (c.type === 'image') return `[Image: ${c.mimeType || 'unknown'}]`;
        if (c.type === 'resource' && c.uri) return c.uri;
        return JSON.stringify(c);
      }).join('\n');

    default:
      return JSON.stringify(result, null, 2);
  }
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
  const [expandAll, setExpandAll] = useState(false);

  const handleCopy = () => {
    try {
      const textToCopy = extractCopyText(result, format);
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
            onCopy={handleCopy}
            onDownload={handleDownload}
            canExpand={format === ResultFormat.JSON_OBJECT}
            isExpanded={expandAll}
            onToggleExpand={() => setExpandAll(!expandAll)}
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
          {format === ResultFormat.MCP_CONTENT && (
            <ErrorBoundary>
              <McpContentView
                content={
                  isMcpContentArray(result)
                    ? result
                    : isMcpResult(result)
                    ? result.content
                    : []
                }
              />
            </ErrorBoundary>
          )}
          {format === ResultFormat.TABLE && Array.isArray(result) && (
            <TableResultView data={result as Array<Record<string, unknown>>} />
          )}
          {format === ResultFormat.JSON_OBJECT && <JsonResultView data={result} expandAll={expandAll} />}
          {format === ResultFormat.TEXT_BLOCK && typeof result === 'string' && (
            <TextResultView text={result} isLongText={true} />
          )}
          {format === ResultFormat.TEXT && typeof result === 'string' && (
            <TextResultView text={result} />
          )}
          {format === ResultFormat.PRIMITIVE && (
            <TextResultView text={result === undefined ? 'undefined' : JSON.stringify(result)} />
          )}
        </>
      )}
    </div>
  );
};
